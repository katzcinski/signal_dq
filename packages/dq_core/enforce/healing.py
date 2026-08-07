# [ENGINE-ADJACENT] frameworkfrei (G7) — kein FastAPI/Flask/Starlette-Import.
"""Healing-Artefakte: Parkbucht-Korrektur (H1) und Patch-Overlay (H3).

Umsetzung von [`Konzept_Manuelles_Healing.md`](../../../docs/Konzept_Manuelles_Healing.md)
§3.1 (H1) und §3.3 (H3). Dieses Modul ERZEUGT nur SQL-Text — Ausführung,
Gating und Audit leben in `services/` (wie `enforce/split.py`).

Leitplanken aus dem Konzept, hier technisch verankert:

* **Quelle bleibt read-only** (ADR-0002): geschrieben wird ausschließlich im
  Signal-Schema — H1 in `DQ_Q_<OBJ>` (geparkte Kopie), H3 in `DQ_PATCH_<OBJ>`
  (Overlay-Tabelle). Kein Statement hier fasst die Quelltabelle schreibend an.
* **Heal → Re-Check → Release**: `recheck_statement` zählt die Zeilen einer
  Episode, die das Bad-Prädikat *weiterhin* erfüllen. Solange > 0, ist die
  Episode nicht release-fähig — die Freigabe bleibt an das Prädikat gebunden,
  nicht an eine Behauptung.
* **Audit ohne Konvention**: Korrekturen sichern den Vorher-Zustand in die
  Schattenspalte `_DQ_ORIGINAL` und stempeln Akteur/Zeit/Grund in die Zeile;
  die DEFINER-Prozedur `P_DQ_CORRECT_ROW` ist die SQL-seitige Tür (kein
  Tabellen-Grant an menschliche DB-User).
* **S2/G2**: Spalten- und Schema-Bezeichner durchlaufen dieselbe
  Identifier-Verteidigung wie im Compiler; `{signal_schema}` wird erst zur
  Laufzeit gebunden.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from .ddl import SAFE_IDENTIFIER, bind_signal_schema
from .split import SRC, SplitSpec, artifact_name

# Systemspalten der Parkbucht, die H1 ergänzt. `_DQ_HEAL_STATE` legt bereits
# `quarantine_create_ddl` an (Slice ⑤ hat sie fürs Healing vorbereitet).
HEAL_COLUMNS: list[tuple[str, str]] = [
    ("_DQ_ORIGINAL", "NCLOB"),                  # JSON: {spalte: vorher}
    ("_DQ_CORRECTED_BY", "NVARCHAR(128)"),
    ("_DQ_CORRECTED_AT", "TIMESTAMP"),
    ("_DQ_CORRECTION_REASON", "NVARCHAR(500)"),
]

# Heal-Zustände der Zeile (G6-Disziplin: explizit, nie stilles Auslassen).
HEAL_STATES = ("quarantined", "corrected", "released")

# Audit-Spalten des Patch-Overlays (H3).
PATCH_SYSTEM_COLUMNS: list[tuple[str, str]] = [
    ("_DQ_PATCH_ID", "NVARCHAR(64)"),
    ("_DQ_PATCHED_BY", "NVARCHAR(128)"),
    ("_DQ_PATCHED_AT", "TIMESTAMP"),
    ("_DQ_PATCH_REASON", "NVARCHAR(500)"),
    ("_DQ_VALID_UNTIL", "TIMESTAMP"),           # NULL = unbefristet
    ("_DQ_PATCH_STATUS", "NVARCHAR(16)"),       # active | revoked
]


class HealingError(ValueError):
    """Ungültige Healing-Anforderung (unbekannte Spalte, unsicherer Bezeichner)."""


def _quote(identifier: str) -> str:
    """Spaltenname → sicheres HANA-Quoted-Identifier (S2).

    Bezeichner kommen aus Nutzereingaben (Korrektur-Formular), deshalb dieselbe
    Verteidigung wie im Compiler: Allowlist-Regex statt Escaping-Vertrauen."""
    name = str(identifier or "")
    if not SAFE_IDENTIFIER.match(name):
        raise HealingError(f"[S2] Unsicherer Spaltenname {name!r}")
    return f'"{name}"'


def _validate_known(column: str, known: list[str]) -> str:
    """Spalte muss zum Objekt gehören — verhindert Korrekturen auf
    Systemspalten oder erfundenen Feldern."""
    if known and column not in known:
        raise HealingError(f"Unbekannte Spalte {column!r} für dieses Objekt")
    if column.startswith("_DQ_"):
        raise HealingError(f"Systemspalte {column!r} ist nicht korrigierbar")
    return column


# ---------------------------------------------------------------------------
# H1 — Korrektur in der Quarantäne-Parkbucht
# ---------------------------------------------------------------------------

def heal_upgrade_statements(spec: SplitSpec, schema: str) -> list[str]:
    """`DQ_Q_<OBJ>` um die Heal-Schattenspalten erweitern.

    Bestehende Parkbuchten wurden vor H1 angelegt; die Tabelle trägt geparkte
    Zeilen und wird nie ersetzt (Reconciler-Regel), also additiv per ALTER.
    Der Aufrufer führt idempotent aus (bereits vorhandene Spalte = No-Op)."""
    return [
        bind_signal_schema(
            f'ALTER TABLE "{{signal_schema}}"."{spec.quarantine_table}" '
            f'ADD ({_quote(name)} {type_})',
            schema,
        )
        for name, type_ in HEAL_COLUMNS
    ]


def _key_clause(keys: dict[str, Any], known: list[str], alias: str = "") -> tuple[str, list[Any]]:
    """Deterministische WHERE-Klausel über die Schlüsselspalten der Zeile."""
    if not keys:
        raise HealingError("Zeilenschlüssel fehlt — Korrektur ohne Treffergarantie")
    prefix = f"{alias}." if alias else ""
    parts, params = [], []
    for column in sorted(keys):
        _validate_known(column, known)
        parts.append(f"{prefix}{_quote(column)} = ?")
        params.append(keys[column])
    return " AND ".join(parts), params


def correction_statement(
    spec: SplitSpec,
    schema: str,
    *,
    episode_id: int,
    keys: dict[str, Any],
    column: str,
    new_value: Any,
    actor: str,
    reason: str,
) -> tuple[str, tuple[Any, ...]]:
    """Parametrisiertes UPDATE einer geparkten Zeile (H1).

    Schreibt ausschließlich in `DQ_Q_<OBJ>` (Signal-Schema) — die Quelle bleibt
    unangetastet. Der Vorher-Wert wandert in `_DQ_ORIGINAL` (JSON-Fragment, per
    Spalte akkumuliert), Akteur/Zeit/Grund werden gestempelt und der
    Heal-Zustand auf `corrected` gesetzt.

    Der Guard bindet die Korrektur an (Episode × Schlüssel × nicht-freigegeben):
    eine bereits freigegebene Zeile ist unveränderlich."""
    known = list(spec.columns)
    _validate_known(column, known)
    col = _quote(column)
    key_sql, key_params = _key_clause(keys, known)

    # _DQ_ORIGINAL akkumuliert je Spalte den ersten gesehenen Vorher-Wert:
    # steht bereits ein Eintrag für diese Spalte, bleibt er stehen (die erste
    # Korrektur trägt den echten Quellwert).
    original_fragment = (
        'CASE WHEN "_DQ_ORIGINAL" IS NULL THEN \'{"\' || ? || \'":\' '
        "|| COALESCE('\"' || CAST(" + col + " AS NVARCHAR(5000)) || '\"', 'null') || '}' "
        'WHEN LOCATE("_DQ_ORIGINAL", \'"\' || ? || \'":\') > 0 THEN "_DQ_ORIGINAL" '
        'ELSE SUBSTRING("_DQ_ORIGINAL", 1, LENGTH("_DQ_ORIGINAL") - 1) || \',"\' || ? || \'":\' '
        "|| COALESCE('\"' || CAST(" + col + " AS NVARCHAR(5000)) || '\"', 'null') || '}' END"
    )
    sql = bind_signal_schema(
        f'UPDATE "{{signal_schema}}"."{spec.quarantine_table}" SET '
        f'"_DQ_ORIGINAL" = {original_fragment}, '
        f"{col} = ?, "
        '"_DQ_HEAL_STATE" = \'corrected\', '
        '"_DQ_CORRECTED_BY" = ?, '
        '"_DQ_CORRECTED_AT" = CURRENT_UTCTIMESTAMP, '
        '"_DQ_CORRECTION_REASON" = ? '
        f'WHERE "_DQ_EPISODE_ID" = ? AND "_DQ_HEAL_STATE" <> \'released\' AND {key_sql}',
        schema,
    )
    params = (
        column, column, column,       # drei Bindings des CASE-Ausdrucks
        new_value, actor, reason,
        int(episode_id), *key_params,
    )
    return sql, params


def recheck_statement(spec: SplitSpec, schema: str, episode_id: int) -> tuple[str, tuple[Any, ...]]:
    """Zählt die Zeilen der Episode, die das Bad-Prädikat **weiterhin** erfüllen.

    Das ist der Re-Check aus dem Konzept (Heal → Re-Check → Release): erst wenn
    dieser Zähler 0 ist, sind die korrigierten Zeilen release-fähig. Das
    Prädikat ist dasselbe, das die Zeilen quarantänisiert hat — die Freigabe
    hängt damit am Contract, nicht an einer Zusicherung."""
    if not spec.predicates:
        raise HealingError("Kein zeilenfähiges Prädikat — Episode wirkt über das Objekt-Gate (B2)")
    sql = bind_signal_schema(
        f'SELECT COUNT(*) FROM "{{signal_schema}}"."{spec.quarantine_table}" {SRC} '
        f'WHERE {SRC}."_DQ_EPISODE_ID" = ? AND ({spec.bad_condition})',
        schema,
    )
    return sql, (int(episode_id),)


def mark_released_statement(spec: SplitSpec, schema: str, episode_id: int) -> tuple[str, tuple[Any, ...]]:
    """Heal-Zustand der Episode auf `released` setzen (Zeilen werden unveränderlich)."""
    sql = bind_signal_schema(
        f'UPDATE "{{signal_schema}}"."{spec.quarantine_table}" '
        "SET \"_DQ_HEAL_STATE\" = 'released' "
        'WHERE "_DQ_EPISODE_ID" = ?',
        schema,
    )
    return sql, (int(episode_id),)


def correct_row_procedure_ddl() -> str:
    """`P_DQ_CORRECT_ROW` — SQL-seitige Korrektur-Tür (Konzept §3.1).

    SECURITY DEFINER, damit DB-User **kein** UPDATE-Grant auf `DQ_Q_*` brauchen.
    Zwei Verteidigungslinien gegen Identifier-Injection im dynamischen SQL:

    1. Die Zieltabelle muss in der Registry `DQ_OBJECTS` als aktives,
       Signal-verwaltetes `DQ_Q_*`-Artefakt stehen.
    2. Tabellen- und Spaltenname müssen im Katalog existieren und dürfen keine
       Systemspalte sein — geprüft gegen `SYS.TABLE_COLUMNS`.

    Jede Korrektur landet zusätzlich in `DQ_HEAL_LOG` (Append-only-Audit).
    """
    # Python-String in """-Quotes: der SQLScript-Rumpf enthält verdoppelte
    # Single-Quotes ('') als Literal-Escapes.
    return """CREATE OR REPLACE PROCEDURE "{signal_schema}"."P_DQ_CORRECT_ROW" (
  IN IN_TABLE_NAME NVARCHAR(128),
  IN IN_EPISODE_ID INTEGER,
  IN IN_KEY_COLUMN NVARCHAR(128),
  IN IN_KEY_VALUE  NVARCHAR(5000),
  IN IN_COLUMN     NVARCHAR(128),
  IN IN_NEW_VALUE  NVARCHAR(5000),
  IN IN_REASON     NVARCHAR(500)
)
LANGUAGE SQLSCRIPT
SQL SECURITY DEFINER
AS
BEGIN
  DECLARE V_OK INTEGER;

  -- (1) Nur Signal-verwaltete Parkbuchten sind Ziel.
  SELECT COUNT(*) INTO V_OK
    FROM "{signal_schema}"."DQ_OBJECTS"
    WHERE "NAME" = :IN_TABLE_NAME AND "STATUS" = 'active' AND "KIND" = 'table'
      AND "NAME" LIKE 'DQ\\_Q\\_%' ESCAPE '\\';
  IF :V_OK = 0 THEN
    SIGNAL SQL_ERROR_CODE 10060
      SET MESSAGE_TEXT = 'DQ-Heal: keine verwaltete Quarantaene-Tabelle: ' || :IN_TABLE_NAME;
  END IF;

  -- (2) Spalten müssen im Katalog existieren und dürfen keine Systemspalten sein.
  SELECT COUNT(*) INTO V_OK
    FROM SYS.TABLE_COLUMNS
    WHERE SCHEMA_NAME = CURRENT_SCHEMA AND TABLE_NAME = :IN_TABLE_NAME
      AND COLUMN_NAME = :IN_COLUMN AND COLUMN_NAME NOT LIKE '\\_DQ\\_%' ESCAPE '\\';
  IF :V_OK = 0 THEN
    SIGNAL SQL_ERROR_CODE 10061
      SET MESSAGE_TEXT = 'DQ-Heal: unbekannte oder geschuetzte Spalte: ' || :IN_COLUMN;
  END IF;

  SELECT COUNT(*) INTO V_OK
    FROM SYS.TABLE_COLUMNS
    WHERE SCHEMA_NAME = CURRENT_SCHEMA AND TABLE_NAME = :IN_TABLE_NAME
      AND COLUMN_NAME = :IN_KEY_COLUMN;
  IF :V_OK = 0 THEN
    SIGNAL SQL_ERROR_CODE 10061
      SET MESSAGE_TEXT = 'DQ-Heal: unbekannte Schluesselspalte: ' || :IN_KEY_COLUMN;
  END IF;

  EXEC 'UPDATE "' || CURRENT_SCHEMA || '"."' || :IN_TABLE_NAME || '" SET ' ||
       '"' || :IN_COLUMN || '" = ''' || :IN_NEW_VALUE || ''', ' ||
       '"_DQ_HEAL_STATE" = ''corrected'', ' ||
       '"_DQ_CORRECTED_BY" = ''' || CURRENT_USER || ''', ' ||
       '"_DQ_CORRECTED_AT" = CURRENT_UTCTIMESTAMP, ' ||
       '"_DQ_CORRECTION_REASON" = ''' || :IN_REASON || ''' ' ||
       'WHERE "_DQ_EPISODE_ID" = ' || :IN_EPISODE_ID || ' ' ||
       'AND "_DQ_HEAL_STATE" <> ''released'' ' ||
       'AND "' || :IN_KEY_COLUMN || '" = ''' || :IN_KEY_VALUE || '''';

  INSERT INTO "{signal_schema}"."DQ_HEAL_LOG"
    ("TABLE_NAME","EPISODE_ID","KEY_COLUMN","KEY_VALUE","COLUMN_NAME",
     "NEW_VALUE","REASON","ACTOR","CORRECTED_AT","SOURCE")
    VALUES (:IN_TABLE_NAME, :IN_EPISODE_ID, :IN_KEY_COLUMN, :IN_KEY_VALUE,
            :IN_COLUMN, :IN_NEW_VALUE, :IN_REASON, CURRENT_USER,
            CURRENT_UTCTIMESTAMP, 'procedure');
END"""


def heal_log_statement(
    schema: str,
    *,
    table_name: str,
    episode_id: int,
    key_column: str,
    key_value: Any,
    column: str,
    new_value: Any,
    reason: str,
    actor: str,
) -> tuple[str, tuple[Any, ...]]:
    """Audit-Zeile für den API-Pfad — dieselbe Tabelle wie die Prozedur-Tür,
    unterschieden über `SOURCE` (`api` vs. `procedure`)."""
    sql = bind_signal_schema(
        'INSERT INTO "{signal_schema}"."DQ_HEAL_LOG" '
        '("TABLE_NAME","EPISODE_ID","KEY_COLUMN","KEY_VALUE","COLUMN_NAME",'
        '"NEW_VALUE","REASON","ACTOR","CORRECTED_AT","SOURCE") '
        "VALUES (?,?,?,?,?,?,?,?,CURRENT_UTCTIMESTAMP,'api')",
        schema,
    )
    return sql, (
        table_name, int(episode_id), key_column, str(key_value),
        column, str(new_value), reason, actor,
    )


# ---------------------------------------------------------------------------
# H3 — Korrektur-Overlay (Patch-Tabelle + Healed-View)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PatchSpec:
    """Soll-Zustand des Overlays eines Objekts (Konzept §3.3).

    `key_columns` identifizieren die Zeile in der Quelle, `patch_columns` sind
    die überschreibbaren Felder. Beide sind Teil des Manifest-Hashes: ändert
    sich der Zuschnitt, ist das Overlay ein anderes Artefakt."""

    object_id: str
    source: str                                   # gebundene Quelle: "SCHEMA"."OBJEKT"
    key_columns: list[str] = field(default_factory=list)
    patch_columns: list[str] = field(default_factory=list)
    all_columns: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.key_columns:
            raise HealingError("Patch-Overlay braucht mindestens eine Schlüsselspalte")
        if not self.patch_columns:
            raise HealingError("Patch-Overlay braucht mindestens eine Patch-Spalte")
        for col in [*self.key_columns, *self.patch_columns]:
            _validate_known(col, list(self.all_columns))
        overlap = set(self.key_columns) & set(self.patch_columns)
        if overlap:
            raise HealingError(
                f"Schlüsselspalten sind nicht patchbar: {', '.join(sorted(overlap))}"
            )

    @property
    def patch_table(self) -> str:
        return artifact_name("DQ_PATCH_", self.object_id)

    @property
    def healed_view(self) -> str:
        return artifact_name("V_DQ_HEALED_", self.object_id)

    @property
    def manifest_hash(self) -> str:
        payload = (
            self.source + "|" + ",".join(self.key_columns) + "|" + ",".join(self.patch_columns)
        )
        return hashlib.sha256(" ".join(payload.split()).encode("utf-8")).hexdigest()[:16]


def patch_table_ddl(spec: PatchSpec, schema: str) -> str:
    """`DQ_PATCH_<OBJ>`: Schlüssel- + Patch-Spalten (Typen aus der Quelle per
    CTAS-Leerkopie) plus Audit-/Gültigkeits-Spalten. Liegt im Signal-Schema —
    die Quelle bleibt unberührt (ADR-0002)."""
    projected = ", ".join(
        f"{SRC}.{_quote(c)}" for c in [*spec.key_columns, *spec.patch_columns]
    )
    system = ", ".join(
        f"CAST(NULL AS {type_}) AS {_quote(name)}" for name, type_ in PATCH_SYSTEM_COLUMNS
    )
    return bind_signal_schema(
        f'CREATE TABLE "{{signal_schema}}"."{spec.patch_table}" AS '
        f"(SELECT {projected}, {system} FROM {spec.source} {SRC} WHERE 1 = 0)",
        schema,
    )


def healed_view_ddl(spec: PatchSpec, schema: str) -> str:
    """`V_DQ_HEALED_<OBJ>` = Quelle LEFT JOIN Overlay, `COALESCE` je Patch-Spalte.

    Konsumenten lesen die View statt der Quelle; ohne aktiven Patch liefert sie
    exakt die Quellzeile. Der Patch greift nur, solange er `active` und (falls
    befristet) nicht abgelaufen ist — ein verfallener Patch verschwindet
    automatisch aus der Sicht, ohne Aufräum-Job."""
    columns = spec.all_columns or [*spec.key_columns, *spec.patch_columns]
    patched = set(spec.patch_columns)
    projection = ", ".join(
        (
            f"COALESCE(DQ_P.{_quote(c)}, {SRC}.{_quote(c)}) AS {_quote(c)}"
            if c in patched else f"{SRC}.{_quote(c)} AS {_quote(c)}"
        )
        for c in columns
    )
    join = " AND ".join(
        f"DQ_P.{_quote(c)} = {SRC}.{_quote(c)}" for c in spec.key_columns
    )
    return bind_signal_schema(
        f'CREATE OR REPLACE VIEW "{{signal_schema}}"."{spec.healed_view}" AS\n'
        f"SELECT {projection},\n"
        '       DQ_P."_DQ_PATCH_ID" AS "_DQ_PATCH_ID",\n'
        '       CASE WHEN DQ_P."_DQ_PATCH_ID" IS NULL THEN 0 ELSE 1 END AS "_DQ_HEALED"\n'
        f"FROM {spec.source} {SRC}\n"
        f'LEFT JOIN "{{signal_schema}}"."{spec.patch_table}" DQ_P\n'
        f"  ON {join}\n"
        "  AND DQ_P.\"_DQ_PATCH_STATUS\" = 'active'\n"
        '  AND (DQ_P."_DQ_VALID_UNTIL" IS NULL OR DQ_P."_DQ_VALID_UNTIL" > CURRENT_UTCTIMESTAMP)',
        schema,
    )


def patch_upsert_statement(
    spec: PatchSpec,
    schema: str,
    *,
    patch_id: str,
    keys: dict[str, Any],
    values: dict[str, Any],
    actor: str,
    reason: str,
    valid_until: str | None = None,
) -> tuple[str, tuple[Any, ...]]:
    """Overlay-Zeile setzen/ersetzen (UPSERT über die Schlüsselspalten).

    Nicht gepatchte Spalten bleiben NULL — die Healed-View fällt für sie per
    `COALESCE` auf die Quelle zurück."""
    for col in keys:
        if col not in spec.key_columns:
            raise HealingError(f"{col!r} ist keine Schlüsselspalte dieses Overlays")
    if set(keys) != set(spec.key_columns):
        raise HealingError("Vollständiger Zeilenschlüssel erforderlich")
    if not values:
        raise HealingError("Patch ohne Werte")
    for col in values:
        if col not in spec.patch_columns:
            raise HealingError(f"{col!r} ist keine Patch-Spalte dieses Overlays")

    ordered_keys = sorted(keys)
    ordered_values = sorted(values)
    columns = (
        [_quote(c) for c in ordered_keys]
        + [_quote(c) for c in ordered_values]
        + ['"_DQ_PATCH_ID"', '"_DQ_PATCHED_BY"', '"_DQ_PATCHED_AT"',
           '"_DQ_PATCH_REASON"', '"_DQ_VALID_UNTIL"', '"_DQ_PATCH_STATUS"']
    )
    placeholders = ["?"] * (len(ordered_keys) + len(ordered_values)) + [
        "?", "?", "CURRENT_UTCTIMESTAMP", "?", "?", "'active'",
    ]
    sql = bind_signal_schema(
        f'UPSERT "{{signal_schema}}"."{spec.patch_table}" ({", ".join(columns)}) '
        f'VALUES ({", ".join(placeholders)}) '
        f'WHERE {" AND ".join(f"{_quote(c)} = ?" for c in ordered_keys)}',
        schema,
    )
    params = (
        *[keys[c] for c in ordered_keys],
        *[values[c] for c in ordered_values],
        patch_id, actor, reason, valid_until,
        *[keys[c] for c in ordered_keys],
    )
    return sql, params


def patch_revoke_statement(spec: PatchSpec, schema: str, patch_id: str) -> tuple[str, tuple[Any, ...]]:
    """Patch zurücknehmen: Zeile bleibt als Audit stehen, verlässt aber die
    Healed-View (Status `revoked`)."""
    sql = bind_signal_schema(
        f'UPDATE "{{signal_schema}}"."{spec.patch_table}" '
        "SET \"_DQ_PATCH_STATUS\" = 'revoked' WHERE \"_DQ_PATCH_ID\" = ?",
        schema,
    )
    return sql, (str(patch_id),)


def build_patch_spec(
    object_id: str,
    source: str,
    *,
    key_columns: list[str],
    patch_columns: list[str],
    all_columns: list[str] | None = None,
) -> PatchSpec:
    """Overlay-Spezifikation bauen (validiert Zuschnitt und Bezeichner)."""
    return PatchSpec(
        object_id=object_id,
        source=source,
        key_columns=list(key_columns),
        patch_columns=list(patch_columns),
        all_columns=list(all_columns or []),
    )
