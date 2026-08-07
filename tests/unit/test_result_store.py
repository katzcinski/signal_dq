"""Tests for result_store.py — round-trip with in-memory SQLite."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[2] / "packages"))

from dq_core.store.sqlite_store import ResultStore
from dq_core.engine.models import CheckDef, CheckResult, DatasetConfig, RunSummary


def make_store(tmp_path):
    return ResultStore(tmp_path / "test.db")


def make_run(run_id="r1", dataset="DS", passed=True):
    result = CheckResult(
        name="check_1",
        sql="SELECT 0",
        expect="= 0",
        severity="fail",
        passed=passed,
        actual_value="0",
        duration_ms=5,
    )
    return RunSummary(
        run_id=run_id,
        dataset=dataset,
        schema="SCH",
        started_at="2026-01-01T00:00:00Z",
        finished_at="2026-01-01T00:01:00Z",
        overall_status="pass" if passed else "fail",
        total=1,
        passed=1 if passed else 0,
        failed=0 if passed else 1,
        warnings=0,
        triggered_by="test",
        results=[result],
    )


def test_save_and_get_run(tmp_path):
    store = make_store(tmp_path)
    run = make_run()
    store.save_run(run)
    fetched = store.get_run("r1")
    assert fetched is not None
    assert fetched["run_id"] == "r1"
    assert fetched["dataset"] == "DS"
    assert len(fetched["results"]) == 1
    assert fetched["results"][0]["kind"] == "internal_gate"


def test_migration_006_adds_kind_column(tmp_path):
    store = make_store(tmp_path)
    with store._conn() as conn:
        cursor = conn.execute("PRAGMA table_info(dq_check_results)")
        columns = {row[1] for row in cursor.fetchall()}
    assert "kind" in columns


def test_get_runs_ordering(tmp_path):
    store = make_store(tmp_path)
    for i, ts in enumerate(["2026-01-01", "2026-01-03", "2026-01-02"]):
        r = make_run(run_id=f"r{i}")
        r.started_at = f"{ts}T00:00:00Z"
        r.run_state = "finished"
        store.save_run(r)
    runs = store.get_runs("DS")
    # Most recent first
    assert runs[0]["started_at"].startswith("2026-01-03")


def test_get_previous_actuals(tmp_path):
    store = make_store(tmp_path)
    run1 = make_run(run_id="r1", dataset="DS")
    run1.results[0].actual_value = "10"
    run1.run_state = "finished"
    store.save_run(run1)
    run2 = make_run(run_id="r2", dataset="DS")
    run2.results[0].actual_value = "20"
    run2.started_at = "2026-01-02T00:00:00Z"
    run2.run_state = "finished"
    store.save_run(run2)
    actuals = store.get_previous_actuals("DS")
    assert actuals["check_1"] == "20"


def test_get_previous_actuals_empty(tmp_path):
    store = make_store(tmp_path)
    assert store.get_previous_actuals("DS") == {}


def test_set_run_state(tmp_path):
    store = make_store(tmp_path)
    run = make_run()
    run.run_state = "running"
    store.save_run(run)
    store.set_run_state("r1", "finished", "2026-01-01T00:02:00Z")
    fetched = store.get_run("r1")
    assert fetched["run_state"] == "finished"


def test_compliance_round_trip(tmp_path):
    store = make_store(tmp_path)
    store.set_compliance("product_a", "1.0.0", "compliant", "r1")
    c = store.get_compliance("product_a")
    assert c is not None
    assert c["compliance"] == "compliant"
