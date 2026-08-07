"""Gate-Konsum-Oberfläche im Signal-Schema: deterministische DDL. [DETERMINISM]

Slice ③ des Integrations-Konzepts (Konzept_Datasphere_Integration_Gating_
Quarantaene §3/§4/§10): Verdict-Tabellen + Lesesicht + `P_DQ_ASSERT_GATE`.
Dieses Modul ERZEUGT nur SQL-Text (frameworkfrei, G7) — Ausführung und
Kill-Switch (`ENFORCEMENT_MATERIALIZE_ENABLED`) leben in `services/`.

Gates:  G1  Contracts bleiben SQL-frei — diese DDL entsteht ausschließlich hier
        G2  kein Schema-Literal: '{signal_schema}' wird zur Laufzeit über
            `bind_signal_schema` gebunden (Setting DATASPHERE_SIGNAL_SCHEMA)
        S2  Schema-Name durchläuft dieselbe Identifier-Verteidigung wie
            `bind_schema` im Compiler
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

SAFE_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

_MIGRATIONS_DIR = Path(__file__).parent / "remote_migrations"

# Fehlercode-Vertrag der Gate-Prozeduren (stabil, dokumentiert; spiegelt die
# CLI-Exit-Codes: block↔1, quarantine↔3). SQLScript-User-Errors: 10000–19999.
GATE_ERROR_CODES: dict[str, int] = {
    "no_verdict": 10050,   # kein Verdict vorhanden (fail-closed)
    "stale": 10051,        # Verdict veraltet / abgelaufen
    "block": 10052,        # Verdict 'block'
    "quarantine": 10053,   # Verdict 'quarantine' (bei fail_on=block_and_quarantine)
    "timeout": 10054,      # reserviert: SQL-Trigger-Bridge (Slice ⑥)
    "run_error": 10055,    # reserviert: SQL-Trigger-Bridge (Slice ⑥)
}


@dataclass(frozen=True)
class RemoteObject:
    """Ein von Signal verwalteter Gegenstand im Open-SQL-Schema."""

    name: str
    kind: str            # table | view | procedure
    ddl: str             # mit '{signal_schema}'-Platzhalter
    manifest_hash: str
    replaceable: bool    # True ⇒ CREATE OR REPLACE (View/Prozedur); Tabellen nie


def bind_signal_schema(sql: str, schema: str) -> str:
    """Laufzeit-Bindung des Signal-Schemas — Analogon zu `bind_schema` (G2).

    Der Schema-Name kommt aus den Settings (DATASPHERE_SIGNAL_SCHEMA), nie aus
    einem Contract oder einer Nutzereingabe im SQL-Pfad.
    """
    s = str(schema or "")
    if not SAFE_IDENTIFIER.match(s):
        raise ValueError(f"[S2] Unsicherer Signal-Schema-Name {s!r}")
    return sql.replace("{signal_schema}", s.replace('"', '""'))


def manifest_hash(ddl: str) -> str:
    """Stabiler Hash der (whitespace-normalisierten) DDL — Drift-Anker der
    Registry (Konzept §7). Gleiches Soll ⇒ gleicher Hash, deterministisch."""
    normalized = " ".join(str(ddl).split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def remote_migration_statements() -> list[tuple[str, list[str]]]:
    """Nummerierte Remote-Migrationen (Tabellen-DDL) als (version, statements).

    Reihe analog store/migrations: bestehende Dateien nie ändern, nur anhängen.
    Statements tragen den '{signal_schema}'-Platzhalter.
    """
    out: list[tuple[str, list[str]]] = []
    for path in sorted(_MIGRATIONS_DIR.glob("*.sql")):
        statements: list[str] = []
        for stmt in path.read_text(encoding="utf-8").split(";"):
            lines = [ln for ln in stmt.splitlines() if not ln.strip().startswith("--")]
            executable = "\n".join(lines).strip()
            if executable:
                statements.append(executable)
        out.append((path.stem, statements))
    return out


def gate_status_view_ddl() -> str:
    """Stabile Lesesicht für Konsumenten — die Tabelle bleibt evolvierbar."""
    return (
        'CREATE OR REPLACE VIEW "{signal_schema}"."V_DQ_GATE_STATUS" AS\n'
        'SELECT "OBJECT_ID", "CONTRACT_ID", "CONTRACT_VERSION", "RUN_ID",\n'
        '       "GATE_VERDICT", "OVERALL_STATUS", "EVALUATED_AT", "EXPIRES_AT"\n'
        'FROM "{signal_schema}"."DQ_GATE_STATUS"'
    )


def assert_gate_procedure_ddl() -> str:
    """`P_DQ_ASSERT_GATE` — fail-closed Gate für Task-Chain-Prozedur-Schritte
    und Kunden-SQLScript (Konzept §4.1).

    SECURITY DEFINER: die Prozedur ist die einzige Tür zur Verdict-Tabelle —
    Aufrufer brauchen nur EXECUTE, nie SELECT auf DQ_GATE_STATUS.
    `IN_FAIL_ON='block'` lässt Quarantäne passieren (Pipeline konsumiert die
    CLEAN-View); Default ist fail-closed (`block_and_quarantine`).
    """
    return f'''CREATE OR REPLACE PROCEDURE "{{signal_schema}}"."P_DQ_ASSERT_GATE" (
  IN IN_OBJECT_ID           NVARCHAR(256),
  IN IN_MAX_AGE_SECONDS     INTEGER       DEFAULT 3600,
  IN IN_MIN_EVALUATED_AFTER TIMESTAMP     DEFAULT NULL,
  IN IN_FAIL_ON             NVARCHAR(32)  DEFAULT 'block_and_quarantine'
)
LANGUAGE SQLSCRIPT
SQL SECURITY DEFINER
READS SQL DATA
AS
BEGIN
  DECLARE V_COUNT        INTEGER;
  DECLARE V_VERDICT      NVARCHAR(16);
  DECLARE V_EVALUATED_AT TIMESTAMP;
  DECLARE V_EXPIRES_AT   TIMESTAMP;

  SELECT COUNT(*) INTO V_COUNT
    FROM "{{signal_schema}}"."DQ_GATE_STATUS"
    WHERE "OBJECT_ID" = :IN_OBJECT_ID;
  IF :V_COUNT = 0 THEN
    SIGNAL SQL_ERROR_CODE {GATE_ERROR_CODES["no_verdict"]}
      SET MESSAGE_TEXT = 'DQ-Gate: kein Verdict (fail-closed): ' || :IN_OBJECT_ID;
  END IF;

  SELECT "GATE_VERDICT", "EVALUATED_AT", "EXPIRES_AT"
    INTO V_VERDICT, V_EVALUATED_AT, V_EXPIRES_AT
    FROM "{{signal_schema}}"."DQ_GATE_STATUS"
    WHERE "OBJECT_ID" = :IN_OBJECT_ID;

  IF SECONDS_BETWEEN(:V_EVALUATED_AT, CURRENT_UTCTIMESTAMP) > :IN_MAX_AGE_SECONDS
     OR (:IN_MIN_EVALUATED_AFTER IS NOT NULL AND :V_EVALUATED_AT < :IN_MIN_EVALUATED_AFTER)
     OR (:V_EXPIRES_AT IS NOT NULL AND CURRENT_UTCTIMESTAMP > :V_EXPIRES_AT) THEN
    SIGNAL SQL_ERROR_CODE {GATE_ERROR_CODES["stale"]}
      SET MESSAGE_TEXT = 'DQ-Gate: Verdict veraltet: ' || :IN_OBJECT_ID;
  END IF;

  IF :V_VERDICT = 'block' THEN
    SIGNAL SQL_ERROR_CODE {GATE_ERROR_CODES["block"]}
      SET MESSAGE_TEXT = 'DQ-Gate: block: ' || :IN_OBJECT_ID;
  END IF;

  IF :V_VERDICT = 'quarantine' AND :IN_FAIL_ON = 'block_and_quarantine' THEN
    SIGNAL SQL_ERROR_CODE {GATE_ERROR_CODES["quarantine"]}
      SET MESSAGE_TEXT = 'DQ-Gate: quarantine: ' || :IN_OBJECT_ID;
  END IF;
END'''


def desired_objects(*, include_bridge: bool = False) -> list[RemoteObject]:
    """Soll-Zustand des Signal-Schemas (globale Infrastruktur) — Grundlage für
    Plan/Apply und die Registry (Konzept §7). Tabellen entstehen über die
    Remote-Migrationen (nie ersetzen); Views/Prozeduren sind idempotent
    CREATE OR REPLACE. Bridge-Prozeduren (Slice ⑥) nur bei Opt-in —
    `SQLSCRIPT_SYNC`-Verfügbarkeit ist Spike O6."""
    objects: list[RemoteObject] = []
    for version, statements in remote_migration_statements():
        for stmt in statements:
            name = _created_table_name(stmt)
            objects.append(RemoteObject(
                name=name or version,
                kind="table",
                ddl=stmt,
                manifest_hash=manifest_hash(stmt),
                replaceable=False,
            ))
    view = gate_status_view_ddl()
    objects.append(RemoteObject(
        name="V_DQ_GATE_STATUS", kind="view", ddl=view,
        manifest_hash=manifest_hash(view), replaceable=True,
    ))
    proc = assert_gate_procedure_ddl()
    objects.append(RemoteObject(
        name="P_DQ_ASSERT_GATE", kind="procedure", ddl=proc,
        manifest_hash=manifest_hash(proc), replaceable=True,
    ))
    # Healing H1: SQL-seitige Korrektur-Tür (DEFINER) — Korrekturen ohne
    # UPDATE-Grant auf DQ_Q_*, jede Ausführung landet in DQ_HEAL_LOG.
    from .healing import correct_row_procedure_ddl
    heal_proc = correct_row_procedure_ddl()
    objects.append(RemoteObject(
        name="P_DQ_CORRECT_ROW", kind="procedure", ddl=heal_proc,
        manifest_hash=manifest_hash(heal_proc), replaceable=True,
    ))
    if include_bridge:
        from .bridge import gate_bridge_procedure_ddl, request_run_procedure_ddl
        for name, ddl in (
            ("P_DQ_REQUEST_RUN", request_run_procedure_ddl()),
            ("P_DQ_GATE", gate_bridge_procedure_ddl()),
        ):
            objects.append(RemoteObject(
                name=name, kind="procedure", ddl=ddl,
                manifest_hash=manifest_hash(ddl), replaceable=True,
            ))
    return objects


_CREATE_TABLE = re.compile(r'(?is)^\s*CREATE\s+TABLE\s+"\{signal_schema\}"\."([A-Za-z0-9_]+)"')


def _created_table_name(stmt: str) -> str:
    m = _CREATE_TABLE.match(stmt)
    return m.group(1) if m else ""


def bootstrap_plan(existing_tables: set[str], schema: str, *, include_bridge: bool = False) -> list[str]:
    """Idempotenter Bootstrap: Tabellen nur wenn abwesend (nie ersetzen —
    sie tragen Zustand), View/Prozedur immer CREATE OR REPLACE. Liefert
    gebundene, ausführbare Statements in Reihenfolge."""
    statements: list[str] = []
    for obj in desired_objects(include_bridge=include_bridge):
        if obj.kind == "table" and obj.name in existing_tables:
            continue
        statements.append(bind_signal_schema(obj.ddl, schema))
    return statements


def _hana_timestamp(iso: str) -> str:
    """ISO-8601 (inkl. 'Z'/Offset) → HANA-TIMESTAMP-Literalformat in UTC."""
    dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt.strftime("%Y-%m-%d %H:%M:%S.%f")


def verdict_upsert_statements(
    *,
    schema: str,
    object_id: str,
    run_id: str,
    gate_verdict: str,
    overall_status: str,
    evaluated_at: str,
    contract_id: str = "",
    contract_version: str = "",
    manifest: str = "",
    generation: int = 1,
    ttl_seconds: int = 0,
) -> list[tuple[str, tuple[Any, ...]]]:
    """Parametrisierte Statements für die Verdict-Publikation: Upsert des
    aktuellen Zustands + Append in die Historie. `ttl_seconds > 0` setzt
    EXPIRES_AT — abgelaufene Verdicts behandelt `P_DQ_ASSERT_GATE` wie
    fehlende (fail-closed)."""
    evaluated = _hana_timestamp(evaluated_at)
    expires = None
    if ttl_seconds > 0:
        dt = datetime.strptime(evaluated, "%Y-%m-%d %H:%M:%S.%f")
        expires = (dt + timedelta(seconds=int(ttl_seconds))).strftime("%Y-%m-%d %H:%M:%S.%f")
    columns = (
        '"OBJECT_ID","CONTRACT_ID","CONTRACT_VERSION","RUN_ID","GATE_VERDICT",'
        '"OVERALL_STATUS","MANIFEST_HASH","GENERATION","EVALUATED_AT","EXPIRES_AT"'
    )
    params = (
        object_id, contract_id, contract_version, run_id, gate_verdict,
        overall_status, manifest, int(generation), evaluated, expires,
    )
    upsert = bind_signal_schema(
        f'UPSERT "{{signal_schema}}"."DQ_GATE_STATUS" ({columns}) '
        "VALUES (?,?,?,?,?,?,?,?,?,?) WITH PRIMARY KEY",
        schema,
    )
    history = bind_signal_schema(
        f'INSERT INTO "{{signal_schema}}"."DQ_GATE_STATUS_HISTORY" ({columns}) '
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        schema,
    )
    return [(upsert, params), (history, params)]
