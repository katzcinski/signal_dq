"""B-1 Value-Diff (§B.2): /api/runs/compare trägt value_delta je Check."""
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "packages"))
sys.path.insert(0, str(Path(__file__).parents[2]))


def _result(name, actual, passed=True):
    from dq_core.engine.models import CheckResult
    return CheckResult(
        name=name, sql="SELECT 1", expect=">= 0", severity="warn",
        passed=passed, actual_value=actual, type="row_count", state="executed",
    )


def _save_run(store, run_id, results):
    from dq_core.engine.models import RunSummary
    now = datetime.now(timezone.utc).isoformat()
    store.save_run(RunSummary(
        run_id=run_id, dataset="DS_SALES_ORDERS", schema="S",
        started_at=now, finished_at=now, overall_status="pass",
        total=len(results), passed=len(results), failed=0, warnings=0,
        results=results, run_state="finished",
    ))


def test_compare_includes_value_delta(api_client):
    import services.api.deps as deps_mod
    store = deps_mod.get_store()

    _save_run(store, "v-base", [_result("rows", "1000"), _result("nulls", "5")])
    _save_run(store, "v-head", [_result("rows", "900"), _result("nulls", "5")])

    resp = api_client.get("/api/runs/compare", params={"base": "v-base", "head": "v-head"})
    assert resp.status_code == 200, resp.text
    changes = {c["check_name"]: c for c in resp.json()["changes"]}

    rows = changes["rows"]["value_delta"]
    assert rows["base"] == "1000" and rows["head"] == "900"
    assert rows["abs_delta"] == -100.0
    assert rows["pct_delta"] == -10.0

    nulls = changes["nulls"]["value_delta"]
    assert nulls["abs_delta"] == 0.0


def test_value_delta_handles_non_numeric(api_client):
    import services.api.deps as deps_mod
    store = deps_mod.get_store()
    _save_run(store, "s-base", [_result("schema", "ok")])
    _save_run(store, "s-head", [_result("schema", "changed")])

    resp = api_client.get("/api/runs/compare", params={"base": "s-base", "head": "s-head"})
    vd = resp.json()["changes"][0]["value_delta"]
    assert vd["abs_delta"] is None and vd["pct_delta"] is None
    assert vd["base"] == "ok" and vd["head"] == "changed"
