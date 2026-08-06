"""UX-N5: run-comparison / regression diff endpoint."""
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "packages"))
sys.path.insert(0, str(Path(__file__).parents[2]))


def _result(name, passed, severity="fail", state="executed"):
    from dq_core.engine.models import CheckResult
    return CheckResult(
        name=name, sql="SELECT 1", expect="= 0", severity=severity,
        passed=passed, actual_value=0 if passed else 1, type="generic", state=state,
    )


def _save_run(store, run_id, results):
    from dq_core.engine.models import RunSummary
    now = datetime.now(timezone.utc).isoformat()
    passed = sum(1 for r in results if r.passed)
    store.save_run(RunSummary(
        run_id=run_id, dataset="DS_SALES_ORDERS", schema="S",
        started_at=now, finished_at=now,
        overall_status="pass" if passed == len(results) else "fail",
        total=len(results), passed=passed, failed=len(results) - passed, warnings=0,
        results=results, run_state="finished",
    ))


def test_compare_lists_status_transitions(api_client):
    import services.api.deps as deps_mod
    store = deps_mod.get_store()

    # base: A pass, B fail. head: A fail (regressed), B pass (recovered), C pass (added).
    _save_run(store, "run-base", [_result("A", True), _result("B", False)])
    _save_run(store, "run-head", [_result("A", False), _result("B", True), _result("C", True)])

    resp = api_client.get("/api/runs/compare", params={"base": "run-base", "head": "run-head"})
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["summary"]["regressed"] == 1
    assert body["summary"]["recovered"] == 1
    assert body["summary"]["added"] == 1

    by_name = {c["check_name"]: c for c in body["changes"]}
    assert by_name["A"]["transition"] == "regressed"
    assert by_name["A"]["base_status"] == "pass" and by_name["A"]["head_status"] == "fail"
    assert by_name["B"]["transition"] == "recovered"
    assert by_name["C"]["transition"] == "added"
    assert by_name["C"]["base_status"] is None


def test_compare_missing_run_404(api_client):
    import services.api.deps as deps_mod
    _save_run(deps_mod.get_store(), "run-only", [_result("A", True)])
    assert api_client.get("/api/runs/compare", params={"base": "run-only", "head": "nope"}).status_code == 404
    assert api_client.get("/api/runs/compare", params={"base": "nope", "head": "run-only"}).status_code == 404
