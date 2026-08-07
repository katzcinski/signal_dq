"""SQL-Trigger-Bridge (Slice ⑥): Lauf-Anforderung und Gate aus purem SQL.

`P_DQ_REQUEST_RUN` legt eine Anforderung in `DQ_RUN_REQUESTS` ab;
`P_DQ_GATE` wartet per `SQLSCRIPT_SYNC` auf das Ergebnis und endet in
`P_DQ_ASSERT_GATE`. Signals Scheduler-Poller claimt die Anforderungen
(services-Seite) und stempelt das Ergebnis zurück.

Frameworkfrei (G7). Die Verfügbarkeit von `SQLSCRIPT_SYNC` im Open-SQL-
Kontext ist Spike O6 — bis dahin bleiben die Prozeduren generierbar, aber
nur auf ausdrücklichen Apply (Opt-in `ENFORCEMENT_SQL_BRIDGE_ENABLED`);
Fallback ohne SYNC: Chain in Request-Schritt + Assert-Schritt teilen.
"""
from __future__ import annotations

from typing import Any

from .ddl import GATE_ERROR_CODES, bind_signal_schema


def request_run_procedure_ddl() -> str:
    """`P_DQ_REQUEST_RUN` — DEFINER-Tür für den INSERT (nie Direkt-Grant)."""
    return '''CREATE OR REPLACE PROCEDURE "{signal_schema}"."P_DQ_REQUEST_RUN" (
  IN  IN_OBJECT_ID  NVARCHAR(256),
  OUT OUT_REQUEST_ID NVARCHAR(64)
)
LANGUAGE SQLSCRIPT
SQL SECURITY DEFINER
AS
BEGIN
  OUT_REQUEST_ID = SYSUUID;
  INSERT INTO "{signal_schema}"."DQ_RUN_REQUESTS"
    ("REQUEST_ID","OBJECT_ID","REQUESTED_BY","REQUESTED_AT","STATUS")
    VALUES (:OUT_REQUEST_ID, :IN_OBJECT_ID, CURRENT_USER, CURRENT_UTCTIMESTAMP, 'requested');
  COMMIT;
END'''


def gate_bridge_procedure_ddl() -> str:
    """`P_DQ_GATE` — voller Loop ohne HTTP: Request → Warten → Assert.

    Fehlercodes: Timeout → 10054 (fail-closed, Request wird `expired`),
    Lauf-Fehler → 10055; das abschließende Assert nutzt den Vertrag von
    `P_DQ_ASSERT_GATE` (10050–10053).
    """
    return f'''CREATE OR REPLACE PROCEDURE "{{signal_schema}}"."P_DQ_GATE" (
  IN IN_OBJECT_ID      NVARCHAR(256),
  IN IN_TIMEOUT_SECONDS INTEGER      DEFAULT 900,
  IN IN_POLL_SECONDS    INTEGER      DEFAULT 10,
  IN IN_FAIL_ON         NVARCHAR(32) DEFAULT 'block_and_quarantine'
)
LANGUAGE SQLSCRIPT
SQL SECURITY DEFINER
AS
BEGIN
  USING SQLSCRIPT_SYNC AS DQ_SYNC;
  DECLARE V_REQUEST NVARCHAR(64);
  DECLARE V_STATUS  NVARCHAR(16);
  DECLARE V_WAITED  INTEGER = 0;

  CALL "{{signal_schema}}"."P_DQ_REQUEST_RUN"(:IN_OBJECT_ID, V_REQUEST);

  WHILE :V_WAITED < :IN_TIMEOUT_SECONDS DO
    CALL DQ_SYNC:SLEEP_SECONDS(:IN_POLL_SECONDS);
    V_WAITED = :V_WAITED + :IN_POLL_SECONDS;
    SELECT "STATUS" INTO V_STATUS
      FROM "{{signal_schema}}"."DQ_RUN_REQUESTS"
      WHERE "REQUEST_ID" = :V_REQUEST;
    IF :V_STATUS = 'done' THEN
      -- Frisches Verdict prüfen; max_age großzügig, weil der Lauf soeben lief.
      CALL "{{signal_schema}}"."P_DQ_ASSERT_GATE"(
        :IN_OBJECT_ID, :IN_TIMEOUT_SECONDS + 3600, NULL, :IN_FAIL_ON);
      RETURN;
    ELSEIF :V_STATUS = 'error' THEN
      SIGNAL SQL_ERROR_CODE {GATE_ERROR_CODES["run_error"]}
        SET MESSAGE_TEXT = 'DQ-Gate: angeforderter Lauf endete mit Fehler: ' || :IN_OBJECT_ID;
    END IF;
  END WHILE;

  UPDATE "{{signal_schema}}"."DQ_RUN_REQUESTS"
    SET "STATUS" = 'expired', "FINISHED_AT" = CURRENT_UTCTIMESTAMP
    WHERE "REQUEST_ID" = :V_REQUEST AND "STATUS" IN ('requested','claimed');
  COMMIT;
  SIGNAL SQL_ERROR_CODE {GATE_ERROR_CODES["timeout"]}
    SET MESSAGE_TEXT = 'DQ-Gate: Timeout beim Warten auf den Lauf (fail-closed): ' || :IN_OBJECT_ID;
END'''


# ---------------------------------------------------------------------------
# Poller-Statements (Ausführung in services/, Claim-Muster wie dq_schedules)
# ---------------------------------------------------------------------------

def select_requested_statement(schema: str) -> str:
    return bind_signal_schema(
        'SELECT "REQUEST_ID","OBJECT_ID" FROM "{signal_schema}"."DQ_RUN_REQUESTS" '
        "WHERE \"STATUS\" = 'requested' ORDER BY \"REQUESTED_AT\"",
        schema,
    )


def claim_statement(schema: str, *, request_id: str, claimed_by: str) -> tuple[str, tuple[Any, ...]]:
    """Optimistischer Claim — greift nur, wenn der Request noch `requested` ist."""
    sql = bind_signal_schema(
        'UPDATE "{signal_schema}"."DQ_RUN_REQUESTS" '
        "SET \"STATUS\" = 'claimed', \"CLAIMED_BY\" = ? "
        "WHERE \"REQUEST_ID\" = ? AND \"STATUS\" = 'requested'",
        schema,
    )
    return sql, (claimed_by, request_id)


def stamp_run_statement(schema: str, *, request_id: str, run_id: str) -> tuple[str, tuple[Any, ...]]:
    sql = bind_signal_schema(
        'UPDATE "{signal_schema}"."DQ_RUN_REQUESTS" SET "RUN_ID" = ? WHERE "REQUEST_ID" = ?',
        schema,
    )
    return sql, (run_id, request_id)


def select_claimed_statement(schema: str, *, claimed_by: str) -> tuple[str, tuple[Any, ...]]:
    sql = bind_signal_schema(
        'SELECT "REQUEST_ID","RUN_ID" FROM "{signal_schema}"."DQ_RUN_REQUESTS" '
        "WHERE \"STATUS\" = 'claimed' AND \"CLAIMED_BY\" = ? AND \"RUN_ID\" IS NOT NULL",
        schema,
    )
    return sql, (claimed_by,)


def finish_statement(schema: str, *, request_id: str, status: str) -> tuple[str, tuple[Any, ...]]:
    """Abschluss-Stempel: done | error (G6: nie stilles Auslassen)."""
    sql = bind_signal_schema(
        'UPDATE "{signal_schema}"."DQ_RUN_REQUESTS" '
        'SET "STATUS" = ?, "FINISHED_AT" = CURRENT_UTCTIMESTAMP WHERE "REQUEST_ID" = ?',
        schema,
    )
    return sql, (status, request_id)


__all__ = [
    "request_run_procedure_ddl", "gate_bridge_procedure_ddl",
    "select_requested_statement", "claim_statement", "stamp_run_statement",
    "select_claimed_statement", "finish_statement",
]
