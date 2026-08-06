"""Split-Artefakte (Slice ④) & episodische Quarantäne (Slice ⑤). [DETERMINISM]

Erzeugt aus Quarantäne-Checks (enforcement=quarantine) die Zeilen-Prädikate
und daraus die SQL-Bausteine der kontinuierlichen Quarantäne — **Variante A**
des Integrations-Konzepts §5.1: `DQ_CLEAN_<OBJ>` als materialisierte Tabelle,
Refresh je Lauf (punktgenau konsistent zum Verdict) — sowie das episodische
Zeilen-Parken (`DQ_Q_<OBJ>`, Release-View, Episoden-Spiegel, TTL).

Frameworkfrei (G7); reine Text→Text-Erzeugung. Zwei Laufzeit-Bindungen (G2):
das Quell-Schema steckt bereits gebunden im Check-SQL (bind_schema), das
Signal-Schema bindet `bind_signal_schema`.

Fähigkeits-Matrix (Review §3.3): zeilenfähig sind `missing`/`not_null`,
`completeness_pct`, `duplicate`, `duplicate_composite`, `reference_integrity`
sowie generische `COUNT(*) … WHERE`-Formen ohne Subquery-Klauseln. Nicht
zeilenfähige Familien (`freshness`, `volume`, `schema` …) werden **explizit**
als übersprungen ausgewiesen (G6-Disziplin), nie still ausgelassen.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any

from .ddl import bind_signal_schema

# Alias der Quelle in allen erzeugten SELECTs — Prädikate mit Subqueries
# (duplicate/referential) müssen äußere Spalten qualifizieren können.
SRC = "DQ_SRC"

_FROM_SOURCE = re.compile(
    r'(?is)^SELECT\s+COUNT\s*\(\s*\*\s*\)\s+FROM\s+("(?:[^"]|"")+"\."(?:[^"]|"")+")\s*(?:WHERE\s+(.+))?$'
)
# Klauseln, deren WHERE-Extraktion die Semantik ändern würde (analog
# _DIAG_UNSAFE im Engine-Diagnosepfad).
_UNSAFE = re.compile(r"(?i)\b(?:GROUP\s+BY|HAVING|UNION|INTERSECT|EXCEPT|LIMIT|OFFSET|JOIN|SELECT)\b")

_COMPLETENESS_COL = re.compile(r'(?is)CASE\s+WHEN\s+("(?:[^"]|"")+")\s+IS\s+NULL')
_DUPLICATE_COL = re.compile(r'(?is)COUNT\s*\(\s*DISTINCT\s+("(?:[^"]|"")+")\s*\)')
_DUPLICATE_EXPR = re.compile(r'(?is)COUNT\s*\(\s*DISTINCT\s+(.+?)\s*\)\s+FROM')
_REFERENTIAL = re.compile(
    r'(?is)FROM\s+("(?:[^"]|"")+"\."(?:[^"]|"")+")\s+f\s+LEFT\s+JOIN\s+'
    r'("(?:[^"]|"")+"\."(?:[^"]|"")+")\s+d\s+ON\s+f\.("(?:[^"]|"")+")\s*=\s*d\.("(?:[^"]|"")+")'
)


@dataclass(frozen=True)
class RowPredicate:
    """Boolesche Bad-Zeilen-Bedingung, formuliert über den Quell-Alias SRC."""

    check_name: str
    check_type: str
    sql: str


@dataclass(frozen=True)
class SkippedCheck:
    """Explizit nicht zeilenfähiger Quarantäne-Check (G6: sichtbar, nie still)."""

    check_name: str
    check_type: str
    reason: str


@dataclass
class SplitSpec:
    """Soll-Zustand der Split-/Quarantäne-Artefakte eines Objekts."""

    object_id: str
    source: str                      # gebundene Quelle: "SCHEMA"."OBJEKT"
    predicates: list[RowPredicate] = field(default_factory=list)
    skipped: list[SkippedCheck] = field(default_factory=list)
    columns: list[str] = field(default_factory=list)  # leer ⇒ SRC.* (Fallback, ADR-0002 §7)

    @property
    def clean_table(self) -> str:
        return artifact_name("DQ_CLEAN_", self.object_id)

    @property
    def quarantine_table(self) -> str:
        return artifact_name("DQ_Q_", self.object_id)

    @property
    def released_view(self) -> str:
        return artifact_name("V_DQ_RELEASED_", self.object_id)

    @property
    def bad_condition(self) -> str:
        return " OR ".join(f"({p.sql})" for p in self.predicates)

    @property
    def manifest_hash(self) -> str:
        payload = self.source + "|" + "|".join(
            f"{p.check_name}:{p.sql}" for p in self.predicates
        ) + "|" + ",".join(self.columns)
        return hashlib.sha256(" ".join(payload.split()).encode("utf-8")).hexdigest()[:16]


_SAFE_CHARS = re.compile(r"[^A-Za-z0-9_]")


def artifact_name(prefix: str, object_id: str) -> str:
    """Deterministischer, HANA-tauglicher Artefakt-Name. Lange Objekt-IDs
    werden gekürzt und mit Hash-Suffix eindeutig gehalten (Limit 128)."""
    base = _SAFE_CHARS.sub("_", str(object_id)).upper().strip("_") or "OBJ"
    name = prefix + base
    if len(name) > 100:
        digest = hashlib.sha256(str(object_id).encode("utf-8")).hexdigest()[:10].upper()
        name = (prefix + base)[:89] + "_" + digest
    return name


# ---------------------------------------------------------------------------
# Zeilen-Prädikate aus kompilierten Checks
# ---------------------------------------------------------------------------

def row_predicate(check_type: str, check_name: str, sql: str) -> RowPredicate | SkippedCheck:
    """Bad-Zeilen-Prädikat eines Quarantäne-Checks — oder expliziter Skip.

    Arbeitet auf dem **gebundenen** Check-SQL (Schema bereits aufgelöst), wie
    es in `CheckResult.sql` vorliegt — die Ableitung funktioniert damit sowohl
    aus der Konfiguration als auch aus einem abgeschlossenen Lauf.
    """
    cleaned = str(sql or "").strip().rstrip(";").strip()

    if check_type in ("duplicate",):
        m = _DUPLICATE_COL.search(cleaned)
        src = _source_of(cleaned)
        if m and src:
            col = m.group(1)
            return RowPredicate(check_name, check_type, (
                f'{SRC}.{col} IN (SELECT DQ_I.{col} FROM {src} DQ_I '
                f'GROUP BY DQ_I.{col} HAVING COUNT(*) > 1)'
            ))
        return SkippedCheck(check_name, check_type, "Duplikat-Spalte nicht extrahierbar")

    if check_type in ("duplicate_composite",):
        m = _DUPLICATE_EXPR.search(cleaned)
        src = _source_of(cleaned)
        if m and src:
            expr = m.group(1).strip()
            inner = _qualify(expr, "DQ_I")
            outer = _qualify(expr, SRC)
            return RowPredicate(check_name, check_type, (
                f'{outer} IN (SELECT {inner} FROM {src} DQ_I '
                f'GROUP BY {inner} HAVING COUNT(*) > 1)'
            ))
        return SkippedCheck(check_name, check_type, "Schlüssel-Ausdruck nicht extrahierbar")

    if check_type in ("reference_integrity",):
        m = _REFERENTIAL.search(cleaned)
        if m:
            _, parent, fk, pk = m.groups()
            return RowPredicate(check_name, check_type, (
                f'{SRC}.{fk} IS NOT NULL AND NOT EXISTS '
                f'(SELECT 1 FROM {parent} DQ_P WHERE DQ_P.{pk} = {SRC}.{fk})'
            ))
        return SkippedCheck(check_name, check_type, "Join-Form nicht extrahierbar")

    if check_type in ("completeness_pct",):
        m = _COMPLETENESS_COL.search(cleaned)
        if m:
            # Zeilen-Form der Vollständigkeit: eine NULL-Zeile ist eine
            # Bad-Zeile — strenger als die Aggregat-Schwelle, bewusst
            # (Review §3.3: completeness ist zeilenfähig via IS NULL).
            return RowPredicate(check_name, check_type, f"{SRC}.{m.group(1)} IS NULL")
        return SkippedCheck(check_name, check_type, "Spalte nicht extrahierbar")

    # Generische COUNT(*)-…-WHERE-Form (missing/not_null, value_set, …):
    # WHERE-Rumpf übernehmen, sofern keine Subquery-/Aggregat-Klauseln.
    m = _FROM_SOURCE.match(cleaned)
    if m and m.group(2):
        where = m.group(2).strip()
        if not _UNSAFE.search(where):
            return RowPredicate(check_name, check_type, where)
        return SkippedCheck(check_name, check_type, "WHERE-Form enthält nicht übertragbare Klauseln")
    return SkippedCheck(
        check_name, check_type,
        "Objekt-Eigenschaft oder nicht zeilenfähige Form — wirkt über das Objekt-Gate (B2)",
    )


def build_spec(
    object_id: str,
    checks: list[Any],
    *,
    columns: list[str] | None = None,
) -> SplitSpec | None:
    """SplitSpec aus Quarantäne-Checks (CheckDef ODER CheckResult — beide
    tragen name/type/sql/enforcement). None, wenn das Objekt keine
    Quarantäne-Checks hat."""
    quarantine = [c for c in checks if getattr(c, "enforcement", "monitor") == "quarantine"]
    if not quarantine:
        return None
    source = ""
    predicates: list[RowPredicate] = []
    skipped: list[SkippedCheck] = []
    for check in quarantine:
        if not source:
            source = _source_of(str(check.sql or "")) or ""
        outcome = row_predicate(check.type, check.name, check.sql)
        if isinstance(outcome, RowPredicate):
            predicates.append(outcome)
        else:
            skipped.append(outcome)
    if not source:
        return None
    spec = SplitSpec(object_id=object_id, source=source, predicates=predicates, skipped=skipped)
    spec.columns = [c for c in (columns or []) if c]
    return spec


def _source_of(sql: str) -> str | None:
    m = re.search(r'(?is)FROM\s+("(?:[^"]|"")+"\."(?:[^"]|"")+")', str(sql or ""))
    return m.group(1) if m else None


def _qualify(expr: str, alias: str) -> str:
    """Quoted-Identifier eines Ausdrucks (z. B. "A" || '|' || "B") auf einen
    Alias qualifizieren — String-Literale bleiben unangetastet."""
    out: list[str] = []
    i = 0
    while i < len(expr):
        ch = expr[i]
        if ch == "'":  # String-Literal überspringen
            j = i + 1
            while j < len(expr):
                if expr[j] == "'" and not (j + 1 < len(expr) and expr[j + 1] == "'"):
                    break
                j += 2 if expr[j] == "'" else 1
            out.append(expr[i:j + 1]); i = j + 1
        elif ch == '"':
            j = expr.index('"', i + 1)
            while j + 1 < len(expr) and expr[j + 1] == '"':
                j = expr.index('"', j + 2)
            out.append(f"{alias}." + expr[i:j + 1]); i = j + 1
        else:
            out.append(ch); i += 1
    return "".join(out)


# ---------------------------------------------------------------------------
# SQL-Bausteine — Variante A (CLEAN-Tabelle) + Episodik
# ---------------------------------------------------------------------------

def _projection(spec: SplitSpec, alias: str = SRC) -> str:
    if spec.columns:
        return ", ".join(f'{alias}."{c}"' for c in spec.columns)
    return f"{alias}.*"  # Fallback ohne bekannte Spalten (ADR-0002 §7)


def clean_create_ddl(spec: SplitSpec, schema: str) -> str:
    """CTAS-Hülle (leerer Bestand); Spalten/Typen kommen aus der Quelle."""
    return bind_signal_schema(
        f'CREATE TABLE "{{signal_schema}}"."{spec.clean_table}" AS '
        f"(SELECT {_projection(spec)} FROM {spec.source} {SRC} WHERE 1 = 0)",
        schema,
    )


def clean_refresh_statements(spec: SplitSpec, schema: str) -> list[str]:
    """Refresh je Lauf: DELETE + INSERT WHERE NOT(<bad>) — im selben
    Post-Run-Schritt wie der Verdict-Upsert, damit CLEAN und Verdict
    punktgenau zusammenpassen."""
    if not spec.predicates:
        return []
    return [
        bind_signal_schema(f'DELETE FROM "{{signal_schema}}"."{spec.clean_table}"', schema),
        bind_signal_schema(
            f'INSERT INTO "{{signal_schema}}"."{spec.clean_table}" '
            f"SELECT {_projection(spec)} FROM {spec.source} {SRC} "
            f"WHERE NOT ({spec.bad_condition})",
            schema,
        ),
    ]


def quarantine_create_ddl(spec: SplitSpec, schema: str) -> str:
    """DQ_Q_<OBJ>: Quell-Spalten + _DQ_*-Systemspalten (Episode, Generation,
    Zeitstempel, Heal-Zustand — vorbereitet für das Healing-Konzept)."""
    return bind_signal_schema(
        f'CREATE TABLE "{{signal_schema}}"."{spec.quarantine_table}" AS ('
        "SELECT "
        'CAST(0 AS INTEGER) AS "_DQ_EPISODE_ID", '
        'CAST(0 AS INTEGER) AS "_DQ_GENERATION", '
        "CAST('' AS NVARCHAR(64)) AS \"_DQ_RUN_ID\", "
        'CURRENT_UTCTIMESTAMP AS "_DQ_QUARANTINED_AT", '
        "CAST('quarantined' AS NVARCHAR(16)) AS \"_DQ_HEAL_STATE\", "
        f"{_projection(spec)} FROM {spec.source} {SRC} WHERE 1 = 0)",
        schema,
    )


def quarantine_snapshot_statement(
    spec: SplitSpec, schema: str, *, episode_id: int, generation: int, run_id: str
) -> tuple[str, tuple[Any, ...]]:
    """Idempotenter Snapshot der Bad-Zeilen je (Episode, Generation):
    dieselbe Generation zweimal anwenden = No-Op (NOT-EXISTS-Guard)."""
    sql = bind_signal_schema(
        f'INSERT INTO "{{signal_schema}}"."{spec.quarantine_table}" '
        f"SELECT ?, ?, ?, CURRENT_UTCTIMESTAMP, 'quarantined', {_projection(spec)} "
        f"FROM {spec.source} {SRC} "
        f"WHERE ({spec.bad_condition}) "
        f'AND NOT EXISTS (SELECT 1 FROM "{{signal_schema}}"."{spec.quarantine_table}" DQ_E '
        'WHERE DQ_E."_DQ_EPISODE_ID" = ? AND DQ_E."_DQ_GENERATION" = ?)',
        schema,
    )
    return sql, (int(episode_id), int(generation), str(run_id), int(episode_id), int(generation))


def released_view_ddl(spec: SplitSpec, schema: str) -> str:
    """Release-View: nur Zeilen freigegebener Episoden — der Kunden-Flow
    liest hieraus zurück (Signal schiebt nie)."""
    return bind_signal_schema(
        f'CREATE OR REPLACE VIEW "{{signal_schema}}"."{spec.released_view}" AS\n'
        f'SELECT DQ_Q.* FROM "{{signal_schema}}"."{spec.quarantine_table}" DQ_Q\n'
        f'JOIN "{{signal_schema}}"."DQ_EPISODES" DQ_EP\n'
        '  ON DQ_EP."EPISODE_ID" = DQ_Q."_DQ_EPISODE_ID"\n'
        "WHERE DQ_EP.\"STATUS\" = 'released'",
        schema,
    )


def episode_mirror_statement(
    schema: str,
    *,
    episode_id: int,
    object_id: str,
    status: str,
    run_id: str = "",
    generation: int | None = None,
    row_count: int | None = None,
    opened_at: str | None = None,
    released_at: str | None = None,
    resolved_at: str | None = None,
) -> tuple[str, tuple[Any, ...]]:
    """Episoden-Status nach HANA spiegeln (Quelle der Wahrheit: Result-Store)."""
    sql = bind_signal_schema(
        'UPSERT "{signal_schema}"."DQ_EPISODES" '
        '("EPISODE_ID","OBJECT_ID","STATUS","RUN_ID","GENERATION","ROW_COUNT",'
        '"OPENED_AT","RELEASED_AT","RESOLVED_AT","UPDATED_AT") '
        "VALUES (?,?,?,?,?,?,?,?,?,CURRENT_UTCTIMESTAMP) WITH PRIMARY KEY",
        schema,
    )
    return sql, (
        int(episode_id), object_id, status, run_id,
        generation, row_count,
        _ts(opened_at), _ts(released_at), _ts(resolved_at),
    )


def ttl_purge_statement(spec: SplitSpec, schema: str, ttl_days: int) -> tuple[str, tuple[Any, ...]]:
    """Retention: abgelaufene Quarantäne-Zeilen purgen (Pflicht-TTL, §5.2).
    Der zugehörige Episoden-Abschluss (`resolved(expired)`) passiert im Store."""
    sql = bind_signal_schema(
        f'DELETE FROM "{{signal_schema}}"."{spec.quarantine_table}" '
        'WHERE "_DQ_QUARANTINED_AT" < ADD_DAYS(CURRENT_UTCTIMESTAMP, ?)',
        schema,
    )
    return sql, (-abs(int(ttl_days)),)


def quarantine_row_count_statement(spec: SplitSpec, schema: str, episode_id: int) -> tuple[str, tuple[Any, ...]]:
    sql = bind_signal_schema(
        f'SELECT COUNT(*) FROM "{{signal_schema}}"."{spec.quarantine_table}" '
        'WHERE "_DQ_EPISODE_ID" = ?',
        schema,
    )
    return sql, (int(episode_id),)


def _ts(iso: str | None) -> str | None:
    if not iso:
        return None
    from datetime import datetime, timezone
    dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt.strftime("%Y-%m-%d %H:%M:%S.%f")


# ---------------------------------------------------------------------------
# Registry-Statements (Reconciler, Konzept §7)
# ---------------------------------------------------------------------------

def registry_upsert_statement(
    schema: str, *, name: str, kind: str, object_id: str, hash_: str, status: str = "active"
) -> tuple[str, tuple[Any, ...]]:
    sql = bind_signal_schema(
        'UPSERT "{signal_schema}"."DQ_OBJECTS" '
        '("NAME","KIND","OBJECT_ID","MANIFEST_HASH","GENERATION","STATUS","CREATED_AT","UPDATED_AT","INVALIDATED_AT") '
        "SELECT ?, ?, ?, ?, COALESCE((SELECT \"GENERATION\" + 1 FROM \"{signal_schema}\".\"DQ_OBJECTS\" WHERE \"NAME\" = ?), 1), "
        "?, COALESCE((SELECT \"CREATED_AT\" FROM \"{signal_schema}\".\"DQ_OBJECTS\" WHERE \"NAME\" = ?), CURRENT_UTCTIMESTAMP), "
        "CURRENT_UTCTIMESTAMP, "
        "CASE WHEN ? = 'invalidated' THEN CURRENT_UTCTIMESTAMP END "
        "FROM DUMMY WITH PRIMARY KEY",
        schema,
    )
    return sql, (name, kind, object_id, hash_, name, status, name, status)


def registry_select_statement(schema: str) -> str:
    return bind_signal_schema(
        'SELECT "NAME","KIND","OBJECT_ID","MANIFEST_HASH","STATUS",'
        '"INVALIDATED_AT" FROM "{signal_schema}"."DQ_OBJECTS"',
        schema,
    )


def registry_mark_statement(schema: str, *, name: str, status: str) -> tuple[str, tuple[Any, ...]]:
    sql = bind_signal_schema(
        'UPDATE "{signal_schema}"."DQ_OBJECTS" SET "STATUS" = ?, "UPDATED_AT" = CURRENT_UTCTIMESTAMP, '
        "\"INVALIDATED_AT\" = CASE WHEN ? = 'invalidated' THEN CURRENT_UTCTIMESTAMP ELSE \"INVALIDATED_AT\" END "
        'WHERE "NAME" = ?',
        schema,
    )
    return sql, (status, status, name)


def drop_statement(schema: str, *, name: str, kind: str) -> str:
    word = "VIEW" if kind == "view" else "TABLE"
    return bind_signal_schema(f'DROP {word} "{{signal_schema}}"."{name}"', schema)


__all__ = [
    "SRC", "RowPredicate", "SkippedCheck", "SplitSpec",
    "artifact_name", "row_predicate", "build_spec",
    "clean_create_ddl", "clean_refresh_statements",
    "quarantine_create_ddl", "quarantine_snapshot_statement",
    "released_view_ddl", "episode_mirror_statement",
    "ttl_purge_statement", "quarantine_row_count_statement",
    "registry_upsert_statement", "registry_select_statement",
    "registry_mark_statement", "drop_statement",
]
