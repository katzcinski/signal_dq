"""G6 + G8 gate tests.

G6: skipped_stale state is never silently omitted — stored and returned explicitly.
G8: without allow_diagnostics=True, no rows land in dq_diagnostics; with flag,
    only columns in the allowlist are persisted.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "packages"))

import sqlite3
import json

import pytest

from dq_core.store.sqlite_store import ResultStore
from dq_core.engine.models import CheckResult, RunSummary


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_store(tmp_path, **kwargs) -> ResultStore:
    return ResultStore(tmp_path / "test.db", **kwargs)


def _make_run(run_id: str = "r1", results: list[CheckResult] | None = None) -> RunSummary:
    if results is None:
        results = [
            CheckResult(
                name="check_1",
                sql="SELECT 0",
                expect="= 0",
                severity="fail",
                passed=True,
                actual_value="0",
                duration_ms=1,
            )
        ]
    return RunSummary(
        run_id=run_id,
        dataset="DS",
        schema="SCH",
        started_at="2026-01-01T00:00:00Z",
        finished_at="2026-01-01T00:01:00Z",
        overall_status="pass",
        total=len(results),
        passed=sum(1 for r in results if r.passed),
        failed=sum(1 for r in results if not r.passed),
        warnings=0,
        triggered_by="test",
        results=results,
    )


# ---------------------------------------------------------------------------
# G6 — skipped_stale is never silently omitted
# ---------------------------------------------------------------------------

def test_g6_executed_state_persisted(tmp_path):
    store = _make_store(tmp_path)
    run = _make_run()
    run.results[0].state = "executed"
    store.save_run(run)
    fetched = store.get_run("r1")
    assert fetched["results"][0]["state"] == "executed"


def test_g6_skipped_stale_state_persisted(tmp_path):
    """skipped_stale MUST appear explicitly — not like pass, not silently omitted."""
    store = _make_store(tmp_path)
    result = CheckResult(
        name="stale_check",
        sql="SELECT 0",
        expect="= 0",
        severity="fail",
        passed=False,
        state="skipped_stale",
    )
    run = _make_run(results=[result])
    store.save_run(run)

    fetched = store.get_run("r1")
    assert fetched is not None
    assert len(fetched["results"]) == 1
    stored = fetched["results"][0]
    # Must be 'skipped_stale', not 'pass' or 'executed' or absent
    assert stored["state"] == "skipped_stale", (
        f"G6 FAIL: expected 'skipped_stale', got {stored['state']!r}"
    )


def test_g6_skipped_dependency_state_persisted(tmp_path):
    store = _make_store(tmp_path)
    result = CheckResult(
        name="dep_check",
        sql="SELECT 0",
        expect="= 0",
        severity="fail",
        passed=False,
        state="skipped_dependency",
    )
    run = _make_run(results=[result])
    store.save_run(run)

    fetched = store.get_run("r1")
    assert fetched["results"][0]["state"] == "skipped_dependency"


def test_g6_all_valid_states_distinct(tmp_path):
    """Each valid state must be stored and retrieved as-is."""
    store = _make_store(tmp_path)
    states = ["executed", "skipped_stale", "skipped_dependency", "downgraded", "error"]
    results = [
        CheckResult(
            name=f"check_{i}",
            sql="SELECT 0",
            expect="= 0",
            severity="fail",
            passed=False,
            state=s,
        )
        for i, s in enumerate(states)
    ]
    run = _make_run(results=results)
    store.save_run(run)

    fetched = store.get_run("r1")
    stored_states = [r["state"] for r in fetched["results"]]
    assert stored_states == states, f"G6 FAIL: states not preserved: {stored_states}"


# ---------------------------------------------------------------------------
# G8 — PII gate: no diagnostic rows without explicit flag
# ---------------------------------------------------------------------------

def _count_diagnostics(db_path: str) -> int:
    conn = sqlite3.connect(db_path)
    count = conn.execute("SELECT COUNT(*) FROM dq_diagnostics").fetchone()[0]
    conn.close()
    return count


def _make_result_with_diag(diag_rows: list[dict]) -> CheckResult:
    r = CheckResult(
        name="check_with_diag",
        sql="SELECT COUNT(*) FROM t WHERE x IS NULL",
        expect="= 0",
        severity="fail",
        passed=False,
        actual_value="3",
    )
    r.diagnostic_rows = diag_rows
    return r


def test_g8_no_diagnostics_by_default(tmp_path):
    """Without allow_diagnostics=True, zero rows in dq_diagnostics."""
    store = _make_store(tmp_path)  # default: allow_diagnostics=False
    diag_rows = [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]
    run = _make_run(results=[_make_result_with_diag(diag_rows)])
    store.save_run(run)

    assert _count_diagnostics(str(tmp_path / "test.db")) == 0, (
        "G8 FAIL: diagnostic rows were stored without ALLOW_LOCAL_DIAGNOSTICS"
    )


def test_g8_diagnostics_stored_when_enabled(tmp_path):
    """With allow_diagnostics=True, rows are persisted."""
    store = _make_store(tmp_path, allow_diagnostics=True)
    diag_rows = [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]
    run = _make_run(results=[_make_result_with_diag(diag_rows)])
    store.save_run(run)

    assert _count_diagnostics(str(tmp_path / "test.db")) == 2


def test_g8_column_allowlist_filters_pii_columns(tmp_path):
    """When diagnostics_columns is set, only allowed columns are persisted."""
    store = _make_store(tmp_path, allow_diagnostics=True, diagnostics_columns=["id"])
    diag_rows = [{"id": 1, "name": "Alice", "ssn": "123-45-6789"}]
    run = _make_run(results=[_make_result_with_diag(diag_rows)])
    store.save_run(run)

    conn = sqlite3.connect(str(tmp_path / "test.db"))
    rows = conn.execute("SELECT row_data FROM dq_diagnostics").fetchall()
    conn.close()
    assert len(rows) == 1
    stored = json.loads(rows[0][0])
    assert "id" in stored
    assert "name" not in stored, "G8 FAIL: 'name' column leaked past allowlist"
    assert "ssn" not in stored, "G8 FAIL: 'ssn' column leaked past allowlist"


def test_g8_no_diagnostics_even_with_diag_rows_if_disabled(tmp_path):
    """Explicit allow_diagnostics=False clears all rows regardless of content."""
    store = _make_store(tmp_path, allow_diagnostics=False)
    diag_rows = [{"col": "value"} for _ in range(50)]
    run = _make_run(results=[_make_result_with_diag(diag_rows)])
    store.save_run(run)

    assert _count_diagnostics(str(tmp_path / "test.db")) == 0
