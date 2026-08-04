from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
from typing import Any, Generator

from ..engine.models import CheckResult, RunSummary
from ..library.check_library import check_ids_where


@dataclass(frozen=True)
class IncidentOpenResult:
    incident_id: int
    created: bool
    cluster_id: str = ""
    correlation_key: str = ""
    is_representative: bool = True
    member_count: int = 1


class ResultStore:
    """SQLite-backed result store. [SCHEMA-MAP] schema binding lives at run-time."""

    def __init__(
        self,
        db_path: str | Path = "signal.db",
        *,
        allow_diagnostics: bool = False,
        diagnostics_columns: list[str] | None = None,
        diagnostics_ttl_days: int = 0,
    ) -> None:
        self.db_path = str(db_path)
        # [PII-GATE] Default off. Only persist diagnostic_rows when explicitly enabled (S1/G8).
        self._allow_diagnostics = allow_diagnostics
        self._diagnostics_columns = set(diagnostics_columns) if diagnostics_columns else None
        self._init_db()
        # [PII-GATE] Retention-TTL: abgelaufene Diagnostik beim Öffnen löschen.
        if diagnostics_ttl_days > 0:
            self._cleanup_diagnostics(diagnostics_ttl_days)

    # ------------------------------------------------------------------
    # Connection helper
    # ------------------------------------------------------------------

    @contextmanager
    def _conn(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Schema initialisation (migration runner)
    # ------------------------------------------------------------------

    def _init_db(self) -> None:
        migrations_dir = Path(__file__).parent / "migrations"
        with self._conn() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations "
                "(version TEXT PRIMARY KEY, applied_at TEXT)"
            )
            applied = {
                row[0]
                for row in conn.execute("SELECT version FROM schema_migrations").fetchall()
            }
            for path in sorted(migrations_dir.glob("*.sql")):
                version = path.stem
                if version not in applied:
                    self._run_migration(conn, path.read_text(encoding="utf-8"))
                    conn.execute(
                        "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                        (version, datetime.now(timezone.utc).isoformat()),
                    )

    @staticmethod
    def _run_migration(conn: sqlite3.Connection, sql: str) -> None:
        """Run a migration statement-by-statement, skipping ADD COLUMN
        statements that fail because the column already exists.

        Comment-only lines are stripped *before* splitting on ';' — a semicolon
        inside a comment would otherwise cut a statement in half and produce a
        syntax error far from its cause.
        """
        body = "\n".join(
            ln for ln in sql.splitlines() if not ln.strip().startswith("--")
        )
        for stmt in body.split(";"):
            executable = stmt.strip()
            if not executable:
                continue
            try:
                conn.execute(executable)
            except sqlite3.OperationalError as e:
                if "duplicate column" in str(e).lower():
                    continue
                raise

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def save_run(self, summary: RunSummary) -> None:
        with self._conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO dq_runs
                   (run_id, dataset, schema_name, started_at, finished_at,
                    overall_status, total_checks, passed_checks, failed_checks,
                    warning_checks, triggered_by, contract_version, contract_hash,
                    actor, run_state, gate_verdict)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    summary.run_id, summary.dataset, summary.schema,
                    summary.started_at, summary.finished_at,
                    summary.overall_status, summary.total, summary.passed,
                    summary.failed, summary.warnings, summary.triggered_by,
                    summary.contract_version, summary.contract_hash,
                    summary.actor, summary.run_state, summary.gate_verdict,
                ),
            )
            for result in summary.results:
                row = conn.execute(
                    """INSERT INTO dq_check_results
                       (run_id, check_name, sql_text, expect_expr, severity,
                        passed, actual_value, error_message, duration_ms, state, check_type, kind,
                        enforcement_mode)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        summary.run_id, result.name, result.sql, result.expect,
                        result.severity, int(result.passed),
                        str(result.actual_value) if result.actual_value is not None else None,
                        result.error, result.duration_ms, result.state, result.type, result.kind,
                        result.enforcement,
                    ),
                ).lastrowid
                # [PII-GATE] Only persist diagnostics when explicitly enabled (S1/G8).
                if self._allow_diagnostics and result.diagnostic_rows:
                    for diag in result.diagnostic_rows:
                        # Apply column allowlist when configured.
                        if self._diagnostics_columns:
                            diag = {k: v for k, v in diag.items() if k in self._diagnostics_columns}
                        conn.execute(
                            "INSERT INTO dq_diagnostics(result_id, run_id, check_name, row_data) "
                            "VALUES (?,?,?,?)",
                            (row, summary.run_id, result.name, json.dumps(diag)),
                        )

    def set_run_state(self, run_id: str, state: str, finished_at: str | None = None) -> None:
        with self._conn() as conn:
            if finished_at:
                conn.execute(
                    "UPDATE dq_runs SET run_state=?, finished_at=? WHERE run_id=?",
                    (state, finished_at, run_id),
                )
            else:
                conn.execute(
                    "UPDATE dq_runs SET run_state=? WHERE run_id=?",
                    (state, run_id),
                )

    def set_compliance(self, product: str, version: str, compliance: str, run_id: str) -> None:
        """WS2-5: Übergänge als Events; `since` markiert den letzten ÜBERGANG,
        nicht den letzten Lauf. Gibt es keinen Zustandswechsel, bleibt `since`."""
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            row = conn.execute(
                "SELECT compliance, since FROM dq_compliance WHERE product=?", (product,)
            ).fetchone()
            previous = row["compliance"] if row else None
            since = now if previous != compliance else row["since"]
            conn.execute(
                """INSERT OR REPLACE INTO dq_compliance
                   (product, contract_version, compliance, since, last_run_id)
                   VALUES (?,?,?,?,?)""",
                (product, version, compliance, since, run_id),
            )
            if previous != compliance:
                conn.execute(
                    """INSERT INTO dq_compliance_events
                       (product, from_state, to_state, contract_version, run_id, at)
                       VALUES (?,?,?,?,?,?)""",
                    (product, previous or "unknown", compliance, version, run_id, now),
                )

    def get_compliance_events(self, product: str, limit: int = 100) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM dq_compliance_events WHERE product=? ORDER BY id DESC LIMIT ?",
                (product, limit),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_diagnostics(self, run_id: str, check_name: str | None = None) -> list[dict[str, Any]]:
        """Diagnostik-Zeilen eines Runs. Zeilen wurden beim Schreiben bereits
        durch das PII-Gate (enabled + Allowlist) gefiltert — hier nur lesen."""
        with self._conn() as conn:
            if check_name:
                rows = conn.execute(
                    "SELECT check_name, row_data FROM dq_diagnostics "
                    "WHERE run_id=? AND check_name=? ORDER BY id",
                    (run_id, check_name),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT check_name, row_data FROM dq_diagnostics WHERE run_id=? ORDER BY id",
                    (run_id,),
                ).fetchall()
        out = []
        for r in rows:
            try:
                data = json.loads(r["row_data"])
            except (TypeError, ValueError):
                data = {}
            out.append({"check_name": r["check_name"], "row": data})
        return out

    def save_segment_results(
        self,
        run_id: str,
        check_name: str,
        segment_column: str,
        rows: list[dict[str, Any]],
    ) -> None:
        """Persist allowlisted aggregate segment details for one check."""
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            conn.execute(
                "DELETE FROM dq_segment_results WHERE run_id=? AND check_name=?",
                (run_id, check_name),
            )
            for rank, row in enumerate(rows, 1):
                conn.execute(
                    """INSERT INTO dq_segment_results
                       (run_id, check_name, segment_column, segment_value,
                        actual_value, threshold_value, rank, created_at)
                       VALUES (?,?,?,?,?,?,?,?)""",
                    (
                        run_id,
                        check_name,
                        segment_column,
                        str(row.get("segment_value", "")),
                        row.get("actual_value"),
                        row.get("threshold_value"),
                        rank,
                        now,
                    ),
                )

    def get_segment_results(self, run_id: str, check_name: str) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT id, run_id, check_name, segment_column, segment_value,
                          actual_value, threshold_value, rank, created_at
                   FROM dq_segment_results
                   WHERE run_id=? AND check_name=?
                   ORDER BY rank, id""",
                (run_id, check_name),
            ).fetchall()
            return [dict(r) for r in rows]

    def try_begin_run(self, summary: RunSummary) -> bool:
        """F2: Run-Registrierung mit Store-seitigem Doppellauf-Schutz.

        Returns False, wenn für das Dataset bereits ein Run läuft (partieller
        Unique-Index idx_dq_runs_one_running) — check-then-act-frei. Bewusst
        plain INSERT: save_run (INSERT OR REPLACE) würde den Konflikt still
        durch Ersetzen auflösen.
        """
        try:
            with self._conn() as conn:
                conn.execute(
                    """INSERT INTO dq_runs
                       (run_id, dataset, schema_name, started_at, finished_at,
                        overall_status, total_checks, passed_checks, failed_checks,
                        warning_checks, triggered_by, contract_version, contract_hash,
                        actor, run_state, gate_verdict)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        summary.run_id, summary.dataset, summary.schema,
                        summary.started_at, summary.finished_at,
                        summary.overall_status, summary.total, summary.passed,
                        summary.failed, summary.warnings, summary.triggered_by,
                        summary.contract_version, summary.contract_hash,
                        summary.actor, summary.run_state, summary.gate_verdict,
                    ),
                )
            return True
        except sqlite3.IntegrityError:
            return False

    def append_progress(self, stream_id: str, line: str) -> int:
        """Append one progress line to the generic stream and return its row id."""
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO dq_progress(stream_id, ts, line) VALUES (?,?,?)",
                (stream_id, now, line),
            )
            return int(cur.lastrowid)

    def get_progress(self, stream_id: str, after_id: int = 0) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, stream_id, ts, line FROM dq_progress "
                "WHERE stream_id=? AND id>? ORDER BY id",
                (stream_id, int(after_id or 0)),
            ).fetchall()
            return [dict(r) for r in rows]

    def begin_operation(self, op_id: str, kind: str, created_by: str = "") -> bool:
        """Register a background operation once; duplicate op_ids are rejected."""
        try:
            with self._conn() as conn:
                conn.execute(
                    """INSERT INTO dq_operations
                       (op_id, kind, state, created_by, started_at)
                       VALUES (?,?,?,?,?)""",
                    (
                        op_id,
                        kind,
                        "running",
                        created_by,
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )
            return True
        except sqlite3.IntegrityError:
            return False

    def finish_operation(
        self,
        op_id: str,
        state: str,
        result_json: str | None = None,
        error: str | None = None,
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """UPDATE dq_operations
                   SET state=?, finished_at=?, result_json=?, error=?
                   WHERE op_id=?""",
                (
                    state,
                    datetime.now(timezone.utc).isoformat(),
                    result_json,
                    error,
                    op_id,
                ),
            )

    def get_operation(self, op_id: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM dq_operations WHERE op_id=?", (op_id,)
            ).fetchone()
            return dict(row) if row else None

    # ------------------------------------------------------------------
    # Schedules (Option E) — durable cadence + due-run claim queue
    # ------------------------------------------------------------------

    @staticmethod
    def _advance_due(observed_iso: str, interval_seconds: int, now_iso: str) -> str:
        """Next due time after a claim.

        Cadence is anchored on the previous due time (observed + interval) so a
        steady tick does not drift. If the scheduler was down long enough that
        the next slot is still in the past, skip ahead to now + interval — one
        catch-up run, never a backfill burst.
        """
        from datetime import timedelta
        observed = datetime.fromisoformat(observed_iso)
        now = datetime.fromisoformat(now_iso)
        candidate = observed + timedelta(seconds=interval_seconds)
        if candidate <= now:
            candidate = now + timedelta(seconds=interval_seconds)
        return candidate.isoformat()

    def create_schedule(
        self,
        *,
        schedule_id: str,
        object_id: str,
        interval_seconds: int = 0,
        mode: str = "internal",
        environment: str = "",
        execution_mode: str = "auto",
        enabled: bool = True,
        next_due_at: str | None = None,
        created_by: str = "",
    ) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        # A new internal schedule is due immediately by default so the first run
        # does not wait a full interval; callers may pin a later first slot.
        # External schedules are never claimed, so the due time is inert.
        due = next_due_at or now
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO dq_schedules
                   (schedule_id, object_id, mode, environment, execution_mode,
                    interval_seconds, enabled, next_due_at, created_by,
                    created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    schedule_id, object_id, mode, environment, execution_mode,
                    int(interval_seconds), 1 if enabled else 0, due,
                    created_by, now, now,
                ),
            )
        return self.get_schedule(schedule_id)  # type: ignore[return-value]

    def get_schedule(self, schedule_id: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM dq_schedules WHERE schedule_id=?", (schedule_id,)
            ).fetchone()
            return dict(row) if row else None

    def list_schedules(self, object_id: str | None = None) -> list[dict[str, Any]]:
        with self._conn() as conn:
            if object_id:
                rows = conn.execute(
                    "SELECT * FROM dq_schedules WHERE object_id=? ORDER BY object_id, schedule_id",
                    (object_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM dq_schedules ORDER BY object_id, schedule_id"
                ).fetchall()
            return [dict(r) for r in rows]

    def update_schedule(self, schedule_id: str, **fields: Any) -> dict[str, Any] | None:
        """Patch mutable columns. Unknown keys are ignored (fail-closed shape)."""
        allowed = {"mode", "environment", "execution_mode", "interval_seconds", "enabled", "next_due_at", "last_external_run_id"}
        updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
        if not updates:
            return self.get_schedule(schedule_id)
        if "enabled" in updates:
            updates["enabled"] = 1 if updates["enabled"] else 0
        if "interval_seconds" in updates:
            updates["interval_seconds"] = int(updates["interval_seconds"])
        updates["updated_at"] = datetime.now(timezone.utc).isoformat()
        cols = ", ".join(f"{k}=?" for k in updates)
        with self._conn() as conn:
            conn.execute(
                f"UPDATE dq_schedules SET {cols} WHERE schedule_id=?",
                (*updates.values(), schedule_id),
            )
        return self.get_schedule(schedule_id)

    def delete_schedule(self, schedule_id: str) -> bool:
        with self._conn() as conn:
            cur = conn.execute(
                "DELETE FROM dq_schedules WHERE schedule_id=?", (schedule_id,)
            )
            return cur.rowcount > 0

    def claim_due_schedules(self, now_iso: str, limit: int = 50) -> list[dict[str, Any]]:
        """Atomically claim enabled schedules whose next_due_at has passed.

        For each due schedule we advance next_due_at under an optimistic guard
        (``next_due_at = <observed>``). Whichever transaction commits first wins
        the slot; a competing worker's guard no longer matches and it skips the
        row. This is best-effort dedup only — the real duplicate-run guard is
        try_begin_run's partial unique index, so a lost race never produces a
        double run, just a wasted wake-up. Returns the claimed rows (with the
        advanced next_due_at) for the caller to launch.
        """
        claimed: list[dict[str, Any]] = []
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM dq_schedules "
                "WHERE mode='internal' AND enabled=1 AND next_due_at<=? "
                "ORDER BY next_due_at LIMIT ?",
                (now_iso, int(limit)),
            ).fetchall()
            for row in rows:
                sched = dict(row)
                observed = sched["next_due_at"]
                new_due = self._advance_due(observed, int(sched["interval_seconds"]), now_iso)
                cur = conn.execute(
                    "UPDATE dq_schedules SET next_due_at=?, updated_at=? "
                    "WHERE schedule_id=? AND next_due_at=? AND enabled=1",
                    (new_due, now_iso, sched["schedule_id"], observed),
                )
                if cur.rowcount == 1:
                    sched["next_due_at"] = new_due
                    claimed.append(sched)
        return claimed

    def record_schedule_run(
        self, schedule_id: str, run_id: str, status: str
    ) -> None:
        """Stamp the outcome of a triggered run onto its schedule (audit/UI)."""
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            conn.execute(
                "UPDATE dq_schedules SET last_run_at=?, last_run_id=?, last_status=?, "
                "updated_at=? WHERE schedule_id=?",
                (now, run_id, status, now, schedule_id),
            )

    # ------------------------------------------------------------------
    # Incidents (R4-1) — persistente Breach-Episoden mit Timeline
    # ------------------------------------------------------------------

    def open_incident(
        self,
        product: str,
        run_id: str,
        severity: str,
        title: str,
        failed_checks: list[str],
        contract_version: str = "",
        kind: str = "consumer_contract",
        actor: str = "",
        impacted_objects: list[dict[str, Any]] | None = None,
    ) -> int | None:
        """Eröffnet ein Incident — höchstens EINES je product+Breach-Episode:
        existiert bereits ein ungelöstes Incident für das Produkt, wird nur
        ein Event angehängt (Sifflet-Lektion: gruppieren, nicht fluten)."""
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            row = conn.execute(
                "SELECT id FROM dq_incidents WHERE product=? AND status != 'resolved' "
                "ORDER BY id DESC LIMIT 1",
                (product,),
            ).fetchone()
            if row:
                if impacted_objects is not None:
                    conn.execute(
                        "UPDATE dq_incidents SET impacted_objects=? WHERE id=?",
                        (json.dumps(impacted_objects), row["id"]),
                    )
                conn.execute(
                    "INSERT INTO dq_incident_events(incident_id, at, actor, action, note) "
                    "VALUES (?,?,?,?,?)",
                    (row["id"], now, actor, "note",
                     f"Erneuter Breach in Run {run_id}: {', '.join(failed_checks)}"),
                )
                return row["id"]
            cur = conn.execute(
                """INSERT INTO dq_incidents
                   (product, run_id, severity, status, title, failed_checks,
                    opened_at, contract_version, kind, impacted_objects)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (product, run_id, severity, "open", title,
                 json.dumps(failed_checks), now, contract_version, kind,
                 json.dumps(impacted_objects or [])),
            )
            incident_id = cur.lastrowid
            conn.execute(
                "INSERT INTO dq_incident_events(incident_id, at, actor, action, note) "
                "VALUES (?,?,?,?,?)",
                (incident_id, now, actor, "opened", title),
            )
            return incident_id

    def open_incident_record(
        self,
        product: str,
        run_id: str,
        severity: str,
        title: str,
        failed_checks: list[str],
        contract_version: str = "",
        kind: str = "consumer_contract",
        actor: str = "",
        impacted_objects: list[dict[str, Any]] | None = None,
    ) -> IncidentOpenResult | None:
        """Open or update an incident and return creation metadata."""
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM dq_incidents WHERE product=? AND status != 'resolved' "
                "ORDER BY id DESC LIMIT 1",
                (product,),
            ).fetchone()
            if row:
                if impacted_objects is not None:
                    conn.execute(
                        "UPDATE dq_incidents SET impacted_objects=? WHERE id=?",
                        (json.dumps(impacted_objects), row["id"]),
                    )
                conn.execute(
                    "INSERT INTO dq_incident_events(incident_id, at, actor, action, note) "
                    "VALUES (?,?,?,?,?)",
                    (
                        row["id"],
                        now,
                        actor,
                        "note",
                        f"Erneuter Breach in Run {run_id}: {', '.join(failed_checks)}",
                    ),
                )
                cluster_id = row["cluster_id"] or ""
                return IncidentOpenResult(
                    incident_id=int(row["id"]),
                    created=False,
                    cluster_id=cluster_id,
                    correlation_key=row["correlation_key"] or "",
                    is_representative=self._is_cluster_representative(conn, int(row["id"])),
                    member_count=self._cluster_member_count(conn, cluster_id),
                )

            cur = conn.execute(
                """INSERT INTO dq_incidents
                   (product, run_id, severity, status, title, failed_checks,
                    opened_at, contract_version, kind, impacted_objects)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    product,
                    run_id,
                    severity,
                    "open",
                    title,
                    json.dumps(failed_checks),
                    now,
                    contract_version,
                    kind,
                    json.dumps(impacted_objects or []),
                ),
            )
            incident_id = int(cur.lastrowid)
            conn.execute(
                "INSERT INTO dq_incident_events(incident_id, at, actor, action, note) "
                "VALUES (?,?,?,?,?)",
                (incident_id, now, actor, "opened", title),
            )
            return IncidentOpenResult(incident_id=incident_id, created=True)

    def auto_resolve_incidents(self, product: str, run_id: str) -> None:
        """Recovery: offener Incident wird automatisch gelöst, mit Event."""
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id FROM dq_incidents WHERE product=? AND status != 'resolved'",
                (product,),
            ).fetchall()
            for row in rows:
                conn.execute(
                    "UPDATE dq_incidents SET status='resolved', resolved_at=? WHERE id=?",
                    (now, row["id"]),
                )
                conn.execute(
                    "INSERT INTO dq_incident_events(incident_id, at, actor, action, note) "
                    "VALUES (?,?,?,?,?)",
                    (row["id"], now, "system", "auto_resolved",
                     f"Folgelauf {run_id} vollständig grün — automatisch gelöst."),
                )

    # ------------------------------------------------------------------
    # Capability-Probe (Rest-O5/O6) — verifizierte Tenant-Fähigkeiten
    # ------------------------------------------------------------------

    def set_capability(self, key: str, status: str, detail: str = "", environment: str = "") -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO dq_capabilities(key, status, detail, environment, checked_at) "
                "VALUES (?,?,?,?,?)",
                (key, status, detail[:500], environment,
                 datetime.now(timezone.utc).isoformat()),
            )

    def list_capabilities(self) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT key, status, detail, environment, checked_at FROM dq_capabilities ORDER BY key"
            ).fetchall()
            return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Quarantäne-Episoden (Enforcement-Achse) — Lifecycle analog Incidents:
    # open → reconciled → released → resolved (+ superseded). Signal speichert
    # nur Counts + Prädikat-Träger (Check-Namen); Rohzeilen bleiben in HANA (G8).
    # ------------------------------------------------------------------

    _QUARANTINE_TERMINAL = ("resolved", "superseded")

    def open_quarantine(
        self,
        product: str,
        run_id: str,
        failed_checks: list[str],
        contract_version: str = "",
        manifest_hash: str = "",
        actor: str = "",
    ) -> int:
        """Eröffnet eine Quarantäne-Episode — höchstens EINE nicht-terminale je
        Produkt: existiert bereits eine, wird nur ein Event angehängt und die
        Generation erhöht (gleiche Anti-Flut-Disziplin wie open_incident)."""
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            row = conn.execute(
                "SELECT id, generation FROM dq_quarantine "
                "WHERE product=? AND status NOT IN (?,?) ORDER BY id DESC LIMIT 1",
                (product, *self._QUARANTINE_TERMINAL),
            ).fetchone()
            if row:
                conn.execute(
                    "UPDATE dq_quarantine SET run_id=?, failed_checks=?, "
                    "generation=?, manifest_hash=? WHERE id=?",
                    (run_id, json.dumps(failed_checks),
                     int(row["generation"]) + 1, manifest_hash, row["id"]),
                )
                conn.execute(
                    "INSERT INTO dq_quarantine_events(quarantine_id, at, actor, action, note) "
                    "VALUES (?,?,?,?,?)",
                    (row["id"], now, actor or "system", "note",
                     f"Erneutes Quarantäne-Verdict in Run {run_id}: {', '.join(failed_checks)}"),
                )
                return int(row["id"])
            cur = conn.execute(
                """INSERT INTO dq_quarantine
                   (product, run_id, status, failed_checks, contract_version,
                    manifest_hash, generation, opened_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (product, run_id, "open", json.dumps(failed_checks),
                 contract_version, manifest_hash, 1, now),
            )
            quarantine_id = int(cur.lastrowid)
            conn.execute(
                "INSERT INTO dq_quarantine_events(quarantine_id, at, actor, action, note) "
                "VALUES (?,?,?,?,?)",
                (quarantine_id, now, actor or "system", "opened",
                 f"Quarantäne-Verdict in Run {run_id}: {', '.join(failed_checks)}"),
            )
            return quarantine_id

    def reconcile_quarantine(self, quarantine_id: int, row_count: int, actor: str = "") -> dict[str, Any] | None:
        """Split/Snapshot ist materialisiert — Episode kennt ihre Zeilenzahl."""
        return self._transition_quarantine(
            quarantine_id, "reconciled", allowed_from=("open", "reconciled"),
            actor=actor or "system", note=f"{int(row_count)} Zeilen quarantänisiert",
            extra_sql="row_count=?", extra_params=(int(row_count),),
        )

    def release_quarantine(self, quarantine_id: int, actor: str, note: str = "") -> dict[str, Any] | None:
        """Steward-Freigabe: Zeilen erscheinen in der Release-View des Kunden-Flows."""
        now = datetime.now(timezone.utc).isoformat()
        return self._transition_quarantine(
            quarantine_id, "released", allowed_from=("open", "reconciled"),
            actor=actor, note=note,
            extra_sql="released_at=?, released_by=?", extra_params=(now, actor),
        )

    def resolve_quarantine(
        self, quarantine_id: int, actor: str, reason: str = "reprocessed", note: str = ""
    ) -> dict[str, Any] | None:
        """Abschluss: reprocessed (Rückführung bestätigt) | expired (TTL) | manual."""
        now = datetime.now(timezone.utc).isoformat()
        return self._transition_quarantine(
            quarantine_id, "resolved", allowed_from=("open", "reconciled", "released"),
            actor=actor, note=note or reason,
            extra_sql="resolved_at=?, resolve_reason=?", extra_params=(now, reason),
        )

    def supersede_quarantine(self, quarantine_id: int, actor: str = "", note: str = "") -> dict[str, Any] | None:
        """Contract/Prädikat hat sich geändert — Episode ist obsolet."""
        now = datetime.now(timezone.utc).isoformat()
        return self._transition_quarantine(
            quarantine_id, "superseded", allowed_from=("open", "reconciled", "released"),
            actor=actor or "system", note=note,
            extra_sql="resolved_at=?, resolve_reason=?", extra_params=(now, "superseded"),
        )

    def _transition_quarantine(
        self,
        quarantine_id: int,
        status: str,
        *,
        allowed_from: tuple[str, ...],
        actor: str,
        note: str,
        extra_sql: str = "",
        extra_params: tuple = (),
    ) -> dict[str, Any] | None:
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM dq_quarantine WHERE id=?", (quarantine_id,)
            ).fetchone()
            if not row:
                return None
            if row["status"] not in allowed_from:
                raise ValueError(
                    f"Quarantäne-Übergang {row['status']!r} → {status!r} ist nicht erlaubt."
                )
            set_clause = "status=?" + (f", {extra_sql}" if extra_sql else "")
            conn.execute(
                f"UPDATE dq_quarantine SET {set_clause} WHERE id=?",
                (status, *extra_params, quarantine_id),
            )
            conn.execute(
                "INSERT INTO dq_quarantine_events(quarantine_id, at, actor, action, note) "
                "VALUES (?,?,?,?,?)",
                (quarantine_id, now, actor, status, note),
            )
            updated = conn.execute(
                "SELECT * FROM dq_quarantine WHERE id=?", (quarantine_id,)
            ).fetchone()
            return self._quarantine_row(updated)

    def list_quarantine(
        self,
        status: str | None = None,
        product: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        where, params = [], []
        if status:
            where.append("status=?")
            params.append(status)
        if product:
            where.append("product=?")
            params.append(product)
        clause = ("WHERE " + " AND ".join(where)) if where else ""
        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT * FROM dq_quarantine {clause} ORDER BY id DESC LIMIT ? OFFSET ?",
                (*params, limit, offset),
            ).fetchall()
            return [self._quarantine_row(r) for r in rows]

    def get_quarantine(self, quarantine_id: int) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM dq_quarantine WHERE id=?", (quarantine_id,)
            ).fetchone()
            if not row:
                return None
            episode = self._quarantine_row(row)
            events = conn.execute(
                "SELECT id, at, actor, action, note FROM dq_quarantine_events "
                "WHERE quarantine_id=? ORDER BY id",
                (quarantine_id,),
            ).fetchall()
            episode["events"] = [dict(e) for e in events]
            return episode

    @staticmethod
    def _quarantine_row(row: sqlite3.Row) -> dict[str, Any]:
        episode = dict(row)
        try:
            episode["failed_checks"] = json.loads(episode.get("failed_checks") or "[]")
        except (TypeError, ValueError):
            episode["failed_checks"] = []
        return episode

    # ------------------------------------------------------------------
    # Profil-Snapshots (Konzept Data-Diff §B) — Distribution-/Key-Diff
    # ------------------------------------------------------------------

    def save_profile_snapshot(
        self, object_name: str, stats: dict[str, Any], environment: str = ""
    ) -> int:
        """Aggregat-Profil ablegen (ohne sample_rows — G8)."""
        now = datetime.now(timezone.utc).isoformat()
        stats = {k: v for k, v in (stats or {}).items() if k != "sample_rows"}
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO dq_profile_snapshots(object_name, environment, captured_at, stats_json) "
                "VALUES (?,?,?,?)",
                (object_name, environment or "", now, json.dumps(stats)),
            )
            return int(cur.lastrowid)

    def list_profile_snapshots(self, object_name: str, limit: int = 50) -> list[dict[str, Any]]:
        """Snapshot-Metadaten (ohne stats-Body) für den Auswahl-Picker."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, object_name, environment, captured_at FROM dq_profile_snapshots "
                "WHERE object_name=? ORDER BY id DESC LIMIT ?",
                (object_name, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_profile_snapshot(self, snapshot_id: int) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM dq_profile_snapshots WHERE id=?", (snapshot_id,)
            ).fetchone()
        if not row:
            return None
        out = dict(row)
        out["stats"] = json.loads(out.pop("stats_json"))
        return out

    # ------------------------------------------------------------------
    # Schema-Drift (Konzept Shift-Left §A) — Snapshots + Drift-Befunde
    # ------------------------------------------------------------------

    def save_schema_snapshot(
        self, object_name: str, columns: list[dict[str, Any]], inventory_hash: str
    ) -> int:
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO dq_schema_snapshots(object_name, captured_at, columns_json, inventory_hash) "
                "VALUES (?,?,?,?)",
                (object_name, now, json.dumps(columns), inventory_hash),
            )
            return int(cur.lastrowid)

    def get_latest_schema_snapshot(self, object_name: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM dq_schema_snapshots WHERE object_name=? "
                "ORDER BY id DESC LIMIT 1",
                (object_name,),
            ).fetchone()
        return dict(row) if row else None

    def record_schema_drift(
        self,
        object_name: str,
        findings: list[dict[str, Any]],
        contract_version: str = "",
        incident_id: int | None = None,
    ) -> None:
        """Persistiert die je Extrakt erkannten Drift-Befunde (Historie)."""
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            for f in findings:
                conn.execute(
                    "INSERT INTO dq_schema_drift(object_name, detected_at, category, "
                    "column_name, before_value, after_value, breaking, contract_version, incident_id) "
                    "VALUES (?,?,?,?,?,?,?,?,?)",
                    (
                        object_name, now, f.get("category", ""),
                        f.get("column", ""), str(f.get("before", "")),
                        str(f.get("after", "")), int(bool(f.get("breaking"))),
                        contract_version, incident_id,
                    ),
                )

    def get_schema_drift(self, object_name: str, limit: int = 100) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM dq_schema_drift WHERE object_name=? "
                "ORDER BY id DESC LIMIT ?",
                (object_name, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_schema_snapshots(self, object_name: str, limit: int = 50) -> list[dict[str, Any]]:
        """Snapshot-Historie eines Objekts, **älteste zuerst** (Evolution über Zeit).

        Das Limit greift auf die jüngsten Snapshots — bei mehr Historie fällt
        der älteste Rand weg, nicht der aktuelle."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM ("
                "  SELECT * FROM dq_schema_snapshots WHERE object_name=? "
                "  ORDER BY id DESC LIMIT ?"
                ") ORDER BY id ASC",
                (object_name, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def list_schema_drift_objects(self) -> list[dict[str, Any]]:
        """Rollup je Objekt über Snapshots × Drift-Befunde (Evolution-Overview).

        Ein Objekt erscheint, sobald es mindestens einen Snapshot **oder** einen
        Drift-Befund trägt; `last_incident_id` ist das Incident des jüngsten
        Befunds mit Incident (Incident-IDs wachsen monoton)."""
        with self._conn() as conn:
            snap_rows = conn.execute(
                "SELECT object_name, COUNT(*) AS snapshots, "
                "MIN(captured_at) AS first_captured_at, MAX(captured_at) AS last_captured_at, "
                "COUNT(DISTINCT inventory_hash) AS distinct_schemas "
                "FROM dq_schema_snapshots GROUP BY object_name"
            ).fetchall()
            drift_rows = conn.execute(
                "SELECT object_name, COUNT(*) AS findings, "
                "COALESCE(SUM(breaking), 0) AS breaking, "
                "MAX(detected_at) AS last_detected_at, "
                "(SELECT d2.incident_id FROM dq_schema_drift d2 "
                "  WHERE d2.object_name = d.object_name AND d2.incident_id IS NOT NULL "
                "  ORDER BY d2.id DESC LIMIT 1) AS last_incident_id "
                "FROM dq_schema_drift d GROUP BY object_name"
            ).fetchall()

        base = {
            "snapshots": 0, "first_captured_at": None, "last_captured_at": None,
            "distinct_schemas": 0, "findings": 0, "breaking": 0,
            "last_detected_at": None, "last_incident_id": None,
        }
        merged: dict[str, dict[str, Any]] = {}
        for r in snap_rows:
            merged[r["object_name"]] = {**base, "object_name": r["object_name"], **dict(r)}
        for r in drift_rows:
            row = merged.setdefault(
                r["object_name"], {**base, "object_name": r["object_name"]}
            )
            row.update({k: r[k] for k in r.keys() if k != "object_name"})
        return sorted(merged.values(), key=lambda r: r["object_name"])

    # ------------------------------------------------------------------
    # Healing-Workbench (Migration 019) — H1 Korrekturen, H3 Patches
    # ------------------------------------------------------------------

    def add_healing_correction(
        self,
        *,
        object_id: str,
        episode_id: int,
        row_key: dict[str, Any],
        column_name: str,
        before_value: Any,
        after_value: Any,
        reason: str = "",
        actor: str = "",
        applied: bool = False,
        apply_error: str = "",
    ) -> dict[str, Any]:
        """H1: Korrektur auditieren. Der Store ist die Wahrheit — die
        HANA-Materialisierung ist opt-in und wird über `applied` ausgewiesen
        (G6-Disziplin: ein nicht materialisierter Eintrag ist sichtbar, nicht
        stillschweigend verschwunden)."""
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO dq_healing_corrections(object_id, episode_id, row_key, "
                "column_name, before_value, after_value, reason, actor, created_at, "
                "applied, apply_error) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    object_id, int(episode_id), json.dumps(row_key, sort_keys=True),
                    column_name,
                    None if before_value is None else str(before_value),
                    None if after_value is None else str(after_value),
                    reason, actor, now, int(bool(applied)), apply_error,
                ),
            )
            row = conn.execute(
                "SELECT * FROM dq_healing_corrections WHERE id=?", (cur.lastrowid,)
            ).fetchone()
        return self._correction_row(row)

    @staticmethod
    def _correction_row(row: Any) -> dict[str, Any]:
        d = dict(row)
        d["applied"] = bool(d.get("applied", 0))
        try:
            d["row_key"] = json.loads(d.get("row_key") or "{}")
        except (TypeError, ValueError):
            d["row_key"] = {}
        return d

    def list_healing_corrections(
        self, *, object_id: str | None = None, episode_id: int | None = None, limit: int = 200
    ) -> list[dict[str, Any]]:
        where, params = [], []
        if object_id:
            where.append("object_id=?")
            params.append(object_id)
        if episode_id is not None:
            where.append("episode_id=?")
            params.append(int(episode_id))
        clause = ("WHERE " + " AND ".join(where)) if where else ""
        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT * FROM dq_healing_corrections {clause} ORDER BY id DESC LIMIT ?",
                (*params, limit),
            ).fetchall()
        return [self._correction_row(r) for r in rows]

    def correction_actors(self, episode_id: int) -> set[str]:
        """Akteure, die an dieser Episode korrigiert haben — Grundlage der
        Vier-Augen-Regel bei Contract-Kinds (Korrigierender ≠ Freigebender)."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT DISTINCT actor FROM dq_healing_corrections WHERE episode_id=?",
                (int(episode_id),),
            ).fetchall()
        return {str(r["actor"]) for r in rows if r["actor"]}

    def upsert_healing_patch(
        self,
        *,
        patch_id: str,
        object_id: str,
        keys: dict[str, Any],
        values: dict[str, Any],
        reason: str = "",
        actor: str = "",
        valid_until: str | None = None,
        applied: bool = False,
        apply_error: str = "",
    ) -> dict[str, Any]:
        """H3: Patch anlegen/ersetzen. Ein aktiver Patch je (Objekt, Schlüssel) —
        ein neuer Patch auf denselben Schlüssel ersetzt den alten (`revoked`),
        damit die Healed-View nie zwei Wahrheiten kennt."""
        now = datetime.now(timezone.utc).isoformat()
        key_json = json.dumps(keys, sort_keys=True)
        with self._conn() as conn:
            conn.execute(
                "UPDATE dq_healing_patches SET status='revoked', revoked_at=?, revoked_by=? "
                "WHERE object_id=? AND key_json=? AND status='active'",
                (now, actor, object_id, key_json),
            )
            conn.execute(
                "INSERT INTO dq_healing_patches(id, object_id, key_json, patch_json, reason, "
                "actor, created_at, valid_until, status, applied, apply_error) "
                "VALUES (?,?,?,?,?,?,?,?,'active',?,?)",
                (
                    patch_id, object_id, key_json, json.dumps(values, sort_keys=True),
                    reason, actor, now, valid_until, int(bool(applied)), apply_error,
                ),
            )
            row = conn.execute("SELECT * FROM dq_healing_patches WHERE id=?", (patch_id,)).fetchone()
        return self._patch_row(row)

    @staticmethod
    def _patch_row(row: Any) -> dict[str, Any]:
        d = dict(row)
        d["applied"] = bool(d.get("applied", 0))
        for field, target in (("key_json", "keys"), ("patch_json", "values")):
            try:
                d[target] = json.loads(d.get(field) or "{}")
            except (TypeError, ValueError):
                d[target] = {}
        return d

    def list_healing_patches(
        self, *, object_id: str | None = None, status: str | None = None, limit: int = 200
    ) -> list[dict[str, Any]]:
        """Patches auflisten; abgelaufene werden beim Lesen als `expired`
        ausgewiesen (die Healed-View filtert sie ohnehin über valid_until)."""
        where, params = [], []
        if object_id:
            where.append("object_id=?")
            params.append(object_id)
        if status:
            where.append("status=?")
            params.append(status)
        clause = ("WHERE " + " AND ".join(where)) if where else ""
        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT * FROM dq_healing_patches {clause} ORDER BY created_at DESC LIMIT ?",
                (*params, limit),
            ).fetchall()
        now = datetime.now(timezone.utc).isoformat()
        out = []
        for r in rows:
            patch = self._patch_row(r)
            if patch["status"] == "active" and patch.get("valid_until") and patch["valid_until"] <= now:
                patch["status"] = "expired"
            out.append(patch)
        return out

    def get_healing_patch(self, patch_id: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM dq_healing_patches WHERE id=?", (patch_id,)).fetchone()
        return self._patch_row(row) if row else None

    def revoke_healing_patch(self, patch_id: str, actor: str) -> dict[str, Any] | None:
        """Zurücknehmen statt löschen: die Zeile bleibt als Audit stehen."""
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            cur = conn.execute(
                "UPDATE dq_healing_patches SET status='revoked', revoked_at=?, revoked_by=? "
                "WHERE id=? AND status='active'",
                (now, actor, patch_id),
            )
            if cur.rowcount == 0:
                row = conn.execute(
                    "SELECT * FROM dq_healing_patches WHERE id=?", (patch_id,)
                ).fetchone()
                if row is None:
                    return None
                raise ValueError("Patch ist nicht aktiv — bereits zurückgenommen oder abgelaufen")
            row = conn.execute("SELECT * FROM dq_healing_patches WHERE id=?", (patch_id,)).fetchone()
        return self._patch_row(row)

    def mark_healing_applied(self, *, correction_id: int | None = None,
                             patch_id: str | None = None,
                             applied: bool = True, error: str = "") -> None:
        """Materialisierungs-Ergebnis nachtragen (HANA-Projektion)."""
        with self._conn() as conn:
            if correction_id is not None:
                conn.execute(
                    "UPDATE dq_healing_corrections SET applied=?, apply_error=? WHERE id=?",
                    (int(bool(applied)), error, int(correction_id)),
                )
            if patch_id is not None:
                conn.execute(
                    "UPDATE dq_healing_patches SET applied=?, apply_error=? WHERE id=?",
                    (int(bool(applied)), error, patch_id),
                )

    # ------------------------------------------------------------------
    # Meta-KV + Digest-Claim (Migration 018)
    # ------------------------------------------------------------------

    def get_meta(self, key: str) -> str | None:
        with self._conn() as conn:
            row = conn.execute("SELECT value FROM dq_meta WHERE key=?", (key,)).fetchone()
        return row["value"] if row else None

    def set_meta(self, key: str, value: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO dq_meta(key, value) VALUES (?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )

    def claim_digest_slot(self, now_iso: str, interval_hours: int) -> bool:
        """Atomarer Claim für den periodischen Digest-Versand.

        Wie ``claim_due_schedules``: der optimistische Guard auf dem zuletzt
        gesehenen Wert stellt sicher, dass bei mehreren Workern genau einer den
        fälligen Slot gewinnt. ``True`` = dieser Prozess sendet."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT value FROM dq_meta WHERE key='digest_last_sent'"
            ).fetchone()
            if row is None:
                try:
                    conn.execute(
                        "INSERT INTO dq_meta(key, value) VALUES ('digest_last_sent', ?)",
                        (now_iso,),
                    )
                    return True
                except sqlite3.IntegrityError:
                    return False  # anderer Worker war schneller
            last = row["value"]
            try:
                due_at = datetime.fromisoformat(last) + timedelta(hours=int(interval_hours))
                if datetime.fromisoformat(now_iso) < due_at:
                    return False
            except ValueError:
                pass  # kaputter Anker → Claim versuchen, Guard entscheidet
            cur = conn.execute(
                "UPDATE dq_meta SET value=? WHERE key='digest_last_sent' AND value=?",
                (now_iso, last),
            )
            return cur.rowcount == 1

    def list_incidents(
        self,
        status: str | None = None,
        severity: str | None = None,
        kind: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        where, params = [], []
        if status:
            where.append("status=?")
            params.append(status)
        if severity:
            where.append("severity=?")
            params.append(severity)
        if kind:
            where.append("kind=?")
            params.append(kind)
        clause = ("WHERE " + " AND ".join(where)) if where else ""
        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT * FROM dq_incidents {clause} ORDER BY id DESC LIMIT ? OFFSET ?",
                (*params, limit, offset),
            ).fetchall()
            return [self._incident_row(r) for r in rows]

    def get_incident(self, incident_id: int) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM dq_incidents WHERE id=?", (incident_id,)
            ).fetchone()
            if not row:
                return None
            incident = self._incident_row(row)
            events = conn.execute(
                "SELECT id, at, actor, action, note FROM dq_incident_events "
                "WHERE incident_id=? ORDER BY id",
                (incident_id,),
            ).fetchall()
            incident["events"] = [dict(e) for e in events]
            return incident

    def transition_incident(
        self,
        incident_id: int,
        status: str | None,
        actor: str,
        owner: str | None = None,
        note: str = "",
    ) -> dict[str, Any] | None:
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM dq_incidents WHERE id=?", (incident_id,)
            ).fetchone()
            if not row:
                return None
            if status and status != row["status"]:
                resolved_at = now if status == "resolved" else None
                conn.execute(
                    "UPDATE dq_incidents SET status=?, resolved_at=? WHERE id=?",
                    (status, resolved_at, incident_id),
                )
                conn.execute(
                    "INSERT INTO dq_incident_events(incident_id, at, actor, action, note) "
                    "VALUES (?,?,?,?,?)",
                    (incident_id, now, actor, "status_changed",
                     f"{row['status']} → {status}" + (f" — {note}" if note else "")),
                )
            if owner is not None and owner != row["owner"]:
                conn.execute(
                    "UPDATE dq_incidents SET owner=? WHERE id=?", (owner, incident_id)
                )
                conn.execute(
                    "INSERT INTO dq_incident_events(incident_id, at, actor, action, note) "
                    "VALUES (?,?,?,?,?)",
                    (incident_id, now, actor, "assigned", owner),
                )
            if note and not status:
                conn.execute(
                    "INSERT INTO dq_incident_events(incident_id, at, actor, action, note) "
                    "VALUES (?,?,?,?,?)",
                    (incident_id, now, actor, "note", note),
                )
        return self.get_incident(incident_id)

    @staticmethod
    def _incident_row(row) -> dict[str, Any]:
        d = dict(row)
        d["kind"] = d.get("kind") or "consumer_contract"
        d["cluster_id"] = d.get("cluster_id") or ""
        d["correlation_key"] = d.get("correlation_key") or ""
        try:
            d["failed_checks"] = json.loads(d.get("failed_checks") or "[]")
        except (TypeError, ValueError):
            d["failed_checks"] = []
        try:
            d["impacted_objects"] = json.loads(d.get("impacted_objects") or "[]")
        except (TypeError, ValueError):
            d["impacted_objects"] = []
        return d

    def count_open_incidents(self, kind: str) -> int:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM dq_incidents WHERE status != 'resolved' AND kind=?",
                (kind,),
            ).fetchone()
            return int(row["n"] if row else 0)

    def assign_incident_cluster(self, incident_id: int, correlation_key: str) -> dict[str, Any]:
        """Assign an incident to a stable cluster and refresh representative data."""
        key = str(correlation_key or "").strip() or f"incident:{incident_id}"
        cluster_id = "cluster_" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            incident = conn.execute(
                "SELECT * FROM dq_incidents WHERE id=?", (incident_id,)
            ).fetchone()
            if not incident:
                return {}
            existing = conn.execute(
                "SELECT * FROM dq_incident_clusters WHERE cluster_id=?", (cluster_id,)
            ).fetchone()
            if not existing:
                conn.execute(
                    """INSERT INTO dq_incident_clusters
                       (cluster_id, correlation_key, representative_incident_id,
                        opened_at, updated_at, member_count)
                       VALUES (?,?,?,?,?,?)""",
                    (cluster_id, key, incident_id, now, now, 1),
                )
            conn.execute(
                "UPDATE dq_incidents SET cluster_id=?, correlation_key=? WHERE id=?",
                (cluster_id, key, incident_id),
            )
            member_count = self._cluster_member_count(conn, cluster_id)
            representative = self._choose_cluster_representative(conn, cluster_id)
            representative_id = int(representative["id"]) if representative else incident_id
            conn.execute(
                """UPDATE dq_incident_clusters
                   SET representative_incident_id=?, updated_at=?, member_count=?
                   WHERE cluster_id=?""",
                (representative_id, now, member_count, cluster_id),
            )
            return {
                "cluster_id": cluster_id,
                "correlation_key": key,
                "representative_incident_id": representative_id,
                "is_representative": representative_id == incident_id,
                "member_count": member_count,
            }

    def list_incident_clusters(
        self,
        status: str | None = None,
        severity: str | None = None,
        kind: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        where, params = ["i.cluster_id IS NOT NULL", "i.cluster_id != ''"], []
        if status:
            where.append("i.status=?")
            params.append(status)
        if severity:
            where.append("i.severity=?")
            params.append(severity)
        if kind:
            where.append("i.kind=?")
            params.append(kind)
        clause = "WHERE " + " AND ".join(where)
        with self._conn() as conn:
            rows = conn.execute(
                f"""SELECT c.*, i.*
                    FROM dq_incident_clusters c
                    JOIN dq_incidents i ON i.id = c.representative_incident_id
                    {clause}
                    ORDER BY c.updated_at DESC
                    LIMIT ? OFFSET ?""",
                (*params, limit, offset),
            ).fetchall()
            out: list[dict[str, Any]] = []
            for row in rows:
                item = self._incident_row(row)
                item["cluster_id"] = row["cluster_id"]
                item["correlation_key"] = row["correlation_key"]
                item["representative_incident_id"] = row["representative_incident_id"]
                item["member_count"] = row["member_count"]
                out.append(item)
            return out

    def _cluster_member_count(self, conn: sqlite3.Connection, cluster_id: str | None) -> int:
        if not cluster_id:
            return 1
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM dq_incidents WHERE cluster_id=?",
            (cluster_id,),
        ).fetchone()
        return int(row["n"] if row else 1)

    def _is_cluster_representative(self, conn: sqlite3.Connection, incident_id: int) -> bool:
        row = conn.execute(
            "SELECT cluster_id FROM dq_incidents WHERE id=?", (incident_id,)
        ).fetchone()
        if not row or not row["cluster_id"]:
            return True
        rep = self._choose_cluster_representative(conn, row["cluster_id"])
        return bool(rep and int(rep["id"]) == incident_id)

    def _choose_cluster_representative(self, conn: sqlite3.Connection, cluster_id: str):
        severity_rank = {"critical": 3, "fail": 2, "warn": 1}
        kind_rank = {"consumer_contract": 2, "provider_contract": 2, "internal_gate": 1}
        rows = conn.execute(
            "SELECT * FROM dq_incidents WHERE cluster_id=?", (cluster_id,)
        ).fetchall()
        if not rows:
            return None
        return sorted(
            rows,
            key=lambda r: (
                -severity_rank.get(r["severity"], 0),
                -kind_rank.get(r["kind"] or "internal_gate", 0),
                r["id"],
            ),
        )[0]

    def save_incident_rca(self, incident_id: int, snapshot: dict[str, Any]) -> None:
        computed_at = snapshot.get("computed_at") or datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO dq_incident_rca
                   (incident_id, probable_cause_object, cause_confidence,
                    cause_candidates_json, affected_contracts_json,
                    affected_internal_gates_json, recurrence_count,
                    recurrence_last_at, computed_at)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (
                    incident_id,
                    snapshot.get("probable_cause_object") or "",
                    snapshot.get("cause_confidence"),
                    json.dumps(snapshot.get("cause_candidates") or []),
                    json.dumps(snapshot.get("affected_contracts") or []),
                    json.dumps(snapshot.get("affected_internal_gates") or []),
                    int(snapshot.get("recurrence_count") or 0),
                    snapshot.get("recurrence_last_at") or "",
                    computed_at,
                ),
            )

    def get_incident_rca(self, incident_id: int) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM dq_incident_rca WHERE incident_id=?", (incident_id,)
            ).fetchone()
        if not row:
            return None
        d = dict(row)
        parsed: dict[str, list[Any]] = {}
        for src, dst in (
            ("cause_candidates_json", "cause_candidates"),
            ("affected_contracts_json", "affected_contracts"),
            ("affected_internal_gates_json", "affected_internal_gates"),
        ):
            try:
                parsed[dst] = json.loads(d.get(src) or "[]")
            except (TypeError, ValueError):
                parsed[dst] = []
        return {
            "incident_id": d["incident_id"],
            "probable_cause_object": d.get("probable_cause_object") or "",
            "cause_confidence": d.get("cause_confidence"),
            **parsed,
            "recurrence_count": d.get("recurrence_count") or 0,
            "recurrence_last_at": d.get("recurrence_last_at") or "",
            "computed_at": d.get("computed_at") or "",
        }

    def get_contract_index(self) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM contract_index").fetchall()
            return [dict(r) for r in rows]

    def get_recent_failures(self, before_at: str, window_minutes: int = 120) -> list[dict[str, Any]]:
        from datetime import timedelta

        before = _parse_iso(before_at) or datetime.now(timezone.utc)
        after = before - timedelta(minutes=int(window_minutes))
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT r.dataset, r.run_id, r.started_at, cr.check_name,
                          cr.check_type, cr.severity, cr.passed, cr.state, cr.kind
                   FROM dq_check_results cr
                   JOIN dq_runs r ON cr.run_id = r.run_id
                   WHERE cr.passed=0 AND cr.state IN ('executed','error')
                     AND r.run_state='finished'
                   ORDER BY r.started_at DESC"""
            ).fetchall()
        out = []
        for row in rows:
            at = _parse_iso(row["started_at"])
            if at and after <= at <= before:
                out.append(dict(row))
        return out

    def get_prior_incidents(self, product: str, before_at: str, days: int = 90) -> list[dict[str, Any]]:
        from datetime import timedelta

        before = _parse_iso(before_at) or datetime.now(timezone.utc)
        after = before - timedelta(days=int(days))
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM dq_incidents WHERE product=? ORDER BY opened_at DESC",
                (product,),
            ).fetchall()
        out = []
        for row in rows:
            opened = _parse_iso(row["opened_at"])
            if opened and after <= opened < before:
                out.append(self._incident_row(row))
        return out

    # ------------------------------------------------------------------
    # SLA über Zeitfenster (R4-3) — aus dem Compliance-Event-Log
    # ------------------------------------------------------------------

    def get_sla(self, product: str, days: int) -> float | None:
        """% der Zeit im Zustand 'compliant' innerhalb der letzten *days* Tage.

        Timeline aus dq_compliance_events; gemessen ab max(Fensterbeginn,
        erstem bekannten Zustand). None, wenn keine Events existieren.
        """
        from datetime import timedelta

        now = datetime.now(timezone.utc)
        window_start = now - timedelta(days=days)
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT from_state, to_state, at FROM dq_compliance_events "
                "WHERE product=? ORDER BY id",
                (product,),
            ).fetchall()
        if not rows:
            return None

        def _ts(s: str) -> datetime:
            ts = datetime.fromisoformat(s)
            return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)

        events = [(_ts(r["at"]), r["from_state"], r["to_state"]) for r in rows]
        # Zustand am Fensterbeginn: letztes Event davor, sonst from_state des ersten
        state = events[0][1]
        start = max(window_start, events[0][0]) if events[0][0] > window_start else window_start
        for at, _from, to in events:
            if at <= window_start:
                state = to
        # Messbeginn: Fensterstart, außer der erste bekannte Zustand liegt später
        measure_start = max(window_start, min(e[0] for e in events))
        compliant_s = 0.0
        cursor = measure_start
        cur_state = state
        for at, _from, to in events:
            if at <= measure_start:
                cur_state = to
                continue
            if cur_state == "compliant":
                compliant_s += (at - cursor).total_seconds()
            cursor = at
            cur_state = to
        if cur_state == "compliant":
            compliant_s += (now - cursor).total_seconds()
        total_s = (now - measure_start).total_seconds()
        if total_s <= 0:
            return None
        return round(100.0 * compliant_s / total_s, 2)

    # ------------------------------------------------------------------
    # Familien-Status (R3-2) — Objekt × Familie statt Entweder-oder
    # ------------------------------------------------------------------

    # Welche Check-Typen zur Observability-Familie zählen, kommt aus der
    # Check-Bibliothek (`library/check_library.json`, Feld `family`) — dieselbe
    # Quelle wie der Picker, statt hier dupliziert. `sorted` hält die
    # Placeholder-Reihenfolge deterministisch.
    _OBS_TYPES = tuple(sorted(check_ids_where("family", "observability")))

    def get_object_family_status(self) -> dict[str, dict[str, str]]:
        """Je Dataset der schlechteste Status getrennt nach Familie
        (Observability = Frische/Volumen/Schema, Quality = Rest), aus dem
        jeweils jüngsten abgeschlossenen Lauf. Gating-Zustände zählen nicht."""
        placeholders = ",".join("?" for _ in self._OBS_TYPES)
        with self._conn() as conn:
            rows = conn.execute(
                f"""SELECT
                      r.dataset,
                      CASE WHEN cr.check_type IN ({placeholders})
                           THEN 'observability' ELSE 'quality' END AS family,
                      MAX(CASE WHEN cr.state != 'executed' THEN 0
                               WHEN cr.severity='critical' AND cr.passed=0 THEN 4
                               WHEN cr.severity='fail'     AND cr.passed=0 THEN 3
                               WHEN cr.severity='warn'     AND cr.passed=0 THEN 2
                               WHEN cr.error_message IS NOT NULL          THEN 1
                               ELSE 0 END) AS worst_score
                    FROM dq_check_results cr
                    JOIN dq_runs r ON cr.run_id = r.run_id
                    WHERE r.started_at = (
                      SELECT MAX(r2.started_at) FROM dq_runs r2
                      WHERE r2.dataset = r.dataset AND r2.run_state='finished'
                    )
                    GROUP BY r.dataset, family""",
                self._OBS_TYPES,
            ).fetchall()
        status_map = {0: "pass", 1: "error", 2: "warn", 3: "fail", 4: "critical"}
        out: dict[str, dict[str, str]] = {}
        for r in rows:
            out.setdefault(r["dataset"], {})[r["family"]] = status_map.get(r["worst_score"], "unknown")
        return out

    def _cleanup_diagnostics(self, ttl_days: int) -> None:
        with self._conn() as conn:
            conn.execute(
                """DELETE FROM dq_diagnostics WHERE run_id IN (
                     SELECT run_id FROM dq_runs
                     WHERE started_at < datetime('now', ?)
                   )""",
                (f"-{int(ttl_days)} days",),
            )

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM dq_runs WHERE run_id=?", (run_id,)
            ).fetchone()
            if not row:
                return None
            run = dict(row)
            results = conn.execute(
                "SELECT * FROM dq_check_results WHERE run_id=? ORDER BY id",
                (run_id,),
            ).fetchall()
            run["results"] = [dict(r) for r in results]
            return run

    def get_runs(self, dataset: str, limit: int = 100) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM dq_runs WHERE dataset=? ORDER BY started_at DESC LIMIT ?",
                (dataset, limit),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_all_runs(self, limit: int = 200, offset: int = 0) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM dq_runs ORDER BY started_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_previous_actuals(self, dataset: str) -> dict[str, str]:
        """Return the latest actual_value per check_name for *dataset*."""
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT cr.check_name, cr.actual_value
                   FROM dq_check_results cr
                   JOIN dq_runs r ON cr.run_id = r.run_id
                   WHERE r.dataset = ? AND r.run_state = 'finished'
                   AND r.started_at = (
                       SELECT MAX(r2.started_at) FROM dq_runs r2
                       WHERE r2.dataset = ? AND r2.run_state = 'finished'
                   )""",
                (dataset, dataset),
            ).fetchall()
            return {r["check_name"]: r["actual_value"] for r in rows if r["actual_value"] is not None}

    def get_check_history(self, dataset: str, check_name: str, limit: int = 50) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT cr.actual_value, cr.passed, cr.state, r.started_at, r.run_id
                   FROM dq_check_results cr
                   JOIN dq_runs r ON cr.run_id = r.run_id
                   WHERE r.dataset=? AND cr.check_name=?
                   ORDER BY r.started_at DESC LIMIT ?""",
                (dataset, check_name, limit),
            ).fetchall()
            return [dict(r) for r in rows]

    # Observability metric families for the time-series view (UX-N1).
    # row_count/volume_anomaly → "volume"; freshness/replication-lag → "freshness".
    _METRIC_FAMILY = {
        "row_count": "volume",
        "volume_anomaly": "volume",
        "freshness": "freshness",
        "freshness_anomaly": "freshness",
    }

    def get_metric_series(self, dataset: str, limit: int = 200) -> dict[str, Any]:
        """UX-N1: per observability check, the chronological actual_value series
        with its rolling baseline band (mean ± 3σ from dq_baselines) and
        per-point anomaly flags. Source for the Freshness/Volume time-series.

        A point is an anomaly when the check did not pass, or when its numeric
        value falls outside the baseline band. Non-numeric actuals carry a null
        value and are excluded from band/anomaly logic.
        """
        metric_types = tuple(self._METRIC_FAMILY)
        placeholders = ",".join("?" for _ in metric_types)
        with self._conn() as conn:
            rows = conn.execute(
                f"""SELECT cr.check_name, cr.check_type, cr.actual_value, cr.passed,
                           cr.state, r.started_at, r.run_id
                    FROM dq_check_results cr
                    JOIN dq_runs r ON cr.run_id = r.run_id
                    WHERE r.dataset=? AND cr.check_type IN ({placeholders})
                      AND r.run_state='finished'
                    ORDER BY cr.check_name, r.started_at DESC""",
                (dataset, *metric_types),
            ).fetchall()
            baseline_rows = conn.execute(
                "SELECT * FROM dq_baselines WHERE dataset=?", (dataset,)
            ).fetchall()

        baselines = {b["metric"]: dict(b) for b in baseline_rows}

        def _num(v: Any) -> float | None:
            try:
                return float(v)
            except (TypeError, ValueError):
                return None

        grouped: dict[str, list[Any]] = {}
        order: list[str] = []
        for r in rows:
            name = r["check_name"]
            if name not in grouped:
                grouped[name] = []
                order.append(name)
            if len(grouped[name]) < limit:
                grouped[name].append(r)

        series: list[dict[str, Any]] = []
        for name in order:
            recs = list(reversed(grouped[name]))  # oldest → newest
            check_type = recs[0]["check_type"]
            metric = self._METRIC_FAMILY.get(check_type, "observability")

            base = baselines.get(name)
            band = None
            if base and not base.get("warmup_remaining"):
                mean = base.get("mean_v") or 0.0
                std = base.get("stddev_v") or 0.0
                band = {
                    "mean": mean,
                    "lower": mean - 3 * std,
                    "upper": mean + 3 * std,
                    "p01": base.get("p01"),
                    "p99": base.get("p99"),
                }

            points = []
            for rec in recs:
                value = _num(rec["actual_value"])
                passed = bool(rec["passed"])
                out_of_band = (
                    band is not None
                    and value is not None
                    and (value < band["lower"] or value > band["upper"])
                )
                points.append({
                    "at": rec["started_at"],
                    "value": value,
                    "raw": rec["actual_value"],
                    "passed": passed,
                    "state": rec["state"],
                    "run_id": rec["run_id"],
                    "anomaly": bool((not passed) or out_of_band),
                })

            series.append({
                "check_name": name,
                "check_type": check_type,
                "metric": metric,
                "baseline": band,
                "points": points,
            })

        return {"dataset": dataset, "series": series}

    def get_health_trend(self) -> dict[str, Any]:
        """UX-N12: data-health trend. Per dataset, compare the latest finished
        run's status to the run before it; report the share of datasets passing
        now vs. one run earlier (over datasets that have ≥2 finished runs, so the
        comparison is apples-to-apples). Direction source for the health gauge."""
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT dataset, overall_status,
                          ROW_NUMBER() OVER (
                            PARTITION BY dataset ORDER BY started_at DESC, run_id DESC
                          ) AS rn
                   FROM dq_runs WHERE run_state='finished'"""
            ).fetchall()

        latest: dict[str, str] = {}
        prior: dict[str, str] = {}
        for r in rows:
            if r["rn"] == 1:
                latest[r["dataset"]] = r["overall_status"]
            elif r["rn"] == 2:
                prior[r["dataset"]] = r["overall_status"]

        def pct(status_map: dict[str, str]) -> float | None:
            if not status_map:
                return None
            passing = sum(1 for v in status_map.values() if v == "pass")
            return round(100.0 * passing / len(status_map), 1)

        # Trend over the common set (datasets with a prior run).
        common = {d: latest[d] for d in prior if d in latest}
        return {
            "current_pct": pct(common),
            "previous_pct": pct(prior),
            "datasets": len(common),
        }

    # GitHub-contribution-style reliability score per day (higher = worse).
    _STATUS_SCORE = {"pass": 0, "unknown": 0, "error": 1, "warn": 2, "fail": 3, "critical": 4}
    _SCORE_STATUS = {0: "pass", 1: "error", 2: "warn", 3: "fail", 4: "critical"}

    def get_status_heatmap(self, days: int = 30) -> dict[str, Any]:
        """UX-N10: per-object × per-day worst run status over the last N days.
        At-a-glance reliability — a day with no run is omitted (rendered neutral)."""
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT dataset, date(started_at) AS day, overall_status
                   FROM dq_runs
                   WHERE run_state='finished'
                     AND date(started_at) >= date('now', ?)""",
                (f"-{int(days)} days",),
            ).fetchall()

        worst: dict[str, dict[str, int]] = {}
        for r in rows:
            score = self._STATUS_SCORE.get(r["overall_status"], 0)
            cell = worst.setdefault(r["dataset"], {})
            day = r["day"]
            if day not in cell or score > cell[day]:
                cell[day] = score

        # Dense day axis (today back to days-1), oldest → newest.
        from datetime import date, timedelta
        today = date.today()
        day_axis = [(today - timedelta(days=i)).isoformat() for i in range(days - 1, -1, -1)]

        matrix = {
            ds: {day: self._SCORE_STATUS[s] for day, s in cells.items()}
            for ds, cells in worst.items()
        }
        return {"days": day_axis, "datasets": sorted(matrix), "matrix": matrix}

    # ------------------------------------------------------------------
    # UX-N2: notification routing (channels / rules / mute windows)
    # ------------------------------------------------------------------

    def list_notification_channels(self) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM dq_notification_channels ORDER BY id"
            ).fetchall()
            return [self._channel_row(r) for r in rows]

    @staticmethod
    def _channel_row(r: Any) -> dict[str, Any]:
        d = dict(r)
        d["enabled"] = bool(d.get("enabled", 1))
        d["digest_enabled"] = bool(d.get("digest_enabled", 0))
        return d

    def create_notification_channel(
        self, *, name: str, type: str, url: str, enabled: bool = True, actor: str = ""
    ) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            cur = conn.execute(
                """INSERT INTO dq_notification_channels(name, type, url, enabled, created_at, created_by)
                   VALUES (?,?,?,?,?,?)""",
                (name, type, url, int(enabled), now, actor),
            )
            cid = cur.lastrowid
            row = conn.execute(
                "SELECT * FROM dq_notification_channels WHERE id=?", (cid,)
            ).fetchone()
        return self._channel_row(row)

    def update_notification_channel(
        self, channel_id: int, *, name: str | None = None, type: str | None = None,
        url: str | None = None, enabled: bool | None = None,
        digest_enabled: bool | None = None,
    ) -> dict[str, Any] | None:
        sets, params = [], []
        for col, val in (("name", name), ("type", type), ("url", url)):
            if val is not None:
                sets.append(f"{col}=?")
                params.append(val)
        if enabled is not None:
            sets.append("enabled=?")
            params.append(int(enabled))
        if digest_enabled is not None:
            sets.append("digest_enabled=?")
            params.append(int(digest_enabled))
        if not sets:
            return self.get_notification_channel(channel_id)
        params.append(channel_id)
        with self._conn() as conn:
            conn.execute(
                f"UPDATE dq_notification_channels SET {', '.join(sets)} WHERE id=?",
                params,
            )
            row = conn.execute(
                "SELECT * FROM dq_notification_channels WHERE id=?", (channel_id,)
            ).fetchone()
        return self._channel_row(row) if row else None

    def get_notification_channel(self, channel_id: int) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM dq_notification_channels WHERE id=?", (channel_id,)
            ).fetchone()
        return self._channel_row(row) if row else None

    def delete_notification_channel(self, channel_id: int) -> bool:
        with self._conn() as conn:
            cur = conn.execute(
                "DELETE FROM dq_notification_channels WHERE id=?", (channel_id,)
            )
            # FK ON DELETE CASCADE removes dependent rules.
            return cur.rowcount > 0

    def list_notification_rules(self) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM dq_notification_rules ORDER BY id"
            ).fetchall()
            return [self._rule_row(r) for r in rows]

    @staticmethod
    def _rule_row(r: Any) -> dict[str, Any]:
        d = dict(r)
        d["enabled"] = bool(d.get("enabled", 1))
        return d

    def create_notification_rule(
        self, *, name: str, channel_id: int, match_severity: str = "",
        match_space: str = "", match_product: str = "", match_owned_by: str = "",
        match_owner: str = "", match_kind: str = "", enabled: bool = True, actor: str = "",
    ) -> dict[str, Any] | None:
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            if not conn.execute(
                "SELECT 1 FROM dq_notification_channels WHERE id=?", (channel_id,)
            ).fetchone():
                return None
            cur = conn.execute(
                """INSERT INTO dq_notification_rules
                   (name, channel_id, match_severity, match_space, match_product,
                    match_owned_by, match_owner, match_kind, enabled, created_at, created_by)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (name, channel_id, match_severity, match_space, match_product,
                 match_owned_by, match_owner, match_kind, int(enabled), now, actor),
            )
            row = conn.execute(
                "SELECT * FROM dq_notification_rules WHERE id=?", (cur.lastrowid,)
            ).fetchone()
        return self._rule_row(row)

    def delete_notification_rule(self, rule_id: int) -> bool:
        with self._conn() as conn:
            cur = conn.execute(
                "DELETE FROM dq_notification_rules WHERE id=?", (rule_id,)
            )
            return cur.rowcount > 0

    def list_notification_mutes(self) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM dq_notification_mutes ORDER BY id"
            ).fetchall()
            return [dict(r) for r in rows]

    def create_notification_mute(
        self, *, starts_at: str, ends_at: str, reason: str = "",
        match_space: str = "", match_product: str = "", actor: str = "",
    ) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            cur = conn.execute(
                """INSERT INTO dq_notification_mutes
                   (reason, match_space, match_product, starts_at, ends_at, created_at, created_by)
                   VALUES (?,?,?,?,?,?,?)""",
                (reason, match_space, match_product, starts_at, ends_at, now, actor),
            )
            row = conn.execute(
                "SELECT * FROM dq_notification_mutes WHERE id=?", (cur.lastrowid,)
            ).fetchone()
        return dict(row)

    def delete_notification_mute(self, mute_id: int) -> bool:
        with self._conn() as conn:
            cur = conn.execute(
                "DELETE FROM dq_notification_mutes WHERE id=?", (mute_id,)
            )
            return cur.rowcount > 0

    def get_compliance(self, product: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM dq_compliance WHERE product=?", (product,)
            ).fetchone()
            return dict(row) if row else None

    def get_latest_run(self, dataset: str) -> dict[str, Any] | None:
        runs = self.get_runs(dataset, limit=1)
        if not runs:
            return None
        return self.get_run(runs[0]["run_id"])

    def get_object_status(self) -> list[dict[str, Any]]:
        """Rollup: per object/dataset the worst active status across all families."""
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT
                     r.dataset,
                     MAX(CASE WHEN cr.severity='critical' AND cr.passed=0 THEN 4
                              WHEN cr.severity='fail'     AND cr.passed=0 THEN 3
                              WHEN cr.severity='warn'     AND cr.passed=0 THEN 2
                              WHEN cr.error_message IS NOT NULL        THEN 1
                              ELSE 0 END) AS worst_score,
                     SUM(cr.passed) AS passed_checks,
                     COUNT(cr.id)   AS total_checks,
                     MAX(r.finished_at) AS last_run,
                     r.run_id AS last_run_id
                   FROM dq_check_results cr
                   JOIN dq_runs r ON cr.run_id = r.run_id
                   WHERE r.started_at = (
                     SELECT MAX(r2.started_at) FROM dq_runs r2
                     WHERE r2.dataset = r.dataset AND r2.run_state='finished'
                   )
                   GROUP BY r.dataset""",
                (),
            ).fetchall()
            status_map = {0: "pass", 1: "error", 2: "warn", 3: "fail", 4: "critical"}
            return [
                {**dict(r), "status": status_map.get(r["worst_score"], "unknown")}
                for r in rows
            ]


def _parse_iso(value: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None
