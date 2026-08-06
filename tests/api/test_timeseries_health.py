"""UX-N1 / UX-N12: object time-series + health-trend endpoints."""
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "packages"))
sys.path.insert(0, str(Path(__file__).parents[2]))


def _save_obs_run(store, run_id, started_at, row_count, *, dataset="DS_SALES_ORDERS", status="pass"):
    from dq_core.engine.models import CheckResult, RunSummary

    store.save_run(RunSummary(
        run_id=run_id, dataset=dataset, schema="S",
        started_at=started_at, finished_at=started_at,
        overall_status=status, total=1, passed=1 if status == "pass" else 0,
        failed=0 if status == "pass" else 1, warnings=0, run_state="finished",
        results=[CheckResult(
            name="volume_row_count", sql="SELECT COUNT(*)", expect="bounds",
            severity="warn", passed=(status == "pass"), actual_value=str(row_count),
            type="row_count",
        )],
    ))


def test_timeseries_endpoint(api_client):
    import services.api.deps as deps_mod
    from dq_core.store.sqlite_store import ResultStore

    store = ResultStore(deps_mod.get_store().db_path)
    for i, day in enumerate(["2026-05-01", "2026-05-02", "2026-05-03"]):
        _save_obs_run(store, f"ts-{i}", f"{day}T00:00:00Z", 100 + i)

    resp = api_client.get("/api/objects/DS_SALES_ORDERS/timeseries")
    assert resp.status_code == 200
    body = resp.json()
    assert body["dataset"] == "DS_SALES_ORDERS"
    vol = next(s for s in body["series"] if s["check_name"] == "volume_row_count")
    assert vol["metric"] == "volume"
    assert [p["value"] for p in vol["points"]] == [100.0, 101.0, 102.0]


def test_health_trend_endpoint(api_client):
    import services.api.deps as deps_mod
    from dq_core.store.sqlite_store import ResultStore

    store = ResultStore(deps_mod.get_store().db_path)
    # Two datasets, each with a prior (fail) then latest (pass) run → improving.
    for ds in ("DS_A", "DS_B"):
        _save_obs_run(store, f"{ds}-prev", "2026-05-01T00:00:00Z", 100, dataset=ds, status="fail")
        _save_obs_run(store, f"{ds}-cur", "2026-05-02T00:00:00Z", 100, dataset=ds, status="pass")

    resp = api_client.get("/api/coverage/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["current_pct"] == 100.0
    assert body["previous_pct"] == 0.0
    assert body["datasets"] == 2
