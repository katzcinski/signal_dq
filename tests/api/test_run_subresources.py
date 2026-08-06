"""R2-6: Run-Sub-Ressourcen /results und /diagnostics (PII-gated).
F3: Run↔Contract-Verknüpfung (contract_version / contract_hash / actor in dq_runs)."""
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "packages"))
sys.path.insert(0, str(Path(__file__).parents[2]))


def _seed_run(db_path, *, with_diagnostics: bool):
    from dq_core.engine.models import CheckResult, RunSummary
    from dq_core.store.sqlite_store import ResultStore

    store = ResultStore(db_path, allow_diagnostics=with_diagnostics)
    now = datetime.now(timezone.utc).isoformat()
    result = CheckResult(
        name="amount_not_null", sql="SELECT 1", expect="= 0", severity="fail",
        passed=False, actual_value=3, type="missing",
        diagnostic_rows=[{"ORDER_ID": 1}, {"ORDER_ID": 2}],
    )
    store.save_run(RunSummary(
        run_id="run-1", dataset="DS_SALES_ORDERS", schema="S",
        started_at=now, finished_at=now, overall_status="fail",
        total=1, passed=0, failed=1, warnings=0,
        results=[result], run_state="finished",
    ))
    return store


def test_results_endpoint(api_client):
    import services.api.deps as deps_mod
    _seed_run(deps_mod.get_store().db_path, with_diagnostics=False)

    resp = api_client.get("/api/runs/run-1/results")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["name"] == "amount_not_null"
    assert body[0]["state"] == "executed"
    assert body[0]["type"] == "missing"
    assert body[0]["kind"] == "internal_gate"
    assert api_client.get("/api/runs/nope/results").status_code == 404


def test_segment_results_endpoint(api_client):
    import services.api.deps as deps_mod
    store = _seed_run(deps_mod.get_store().db_path, with_diagnostics=False)
    store.save_segment_results(
        "run-1",
        "amount_not_null",
        "REGION",
        [{"segment_value": "DE", "actual_value": 7.5, "threshold_value": 0.5}],
    )

    resp = api_client.get("/api/runs/run-1/results/amount_not_null/segments")
    assert resp.status_code == 200
    assert resp.json()[0]["segment_value"] == "DE"
    assert api_client.get("/api/runs/run-1/results/missing/segments").status_code == 404


def test_diagnostics_endpoint_authz_and_gate(api_client):
    import services.api.deps as deps_mod
    _seed_run(deps_mod.get_store().db_path, with_diagnostics=False)

    # viewer darf nie Rohzeilen sehen
    resp = api_client.get("/api/runs/run-1/diagnostics", headers={"X-DQ-Role": "viewer"})
    assert resp.status_code == 403

    # Gate war off → nichts persistiert, leere Antwort (kein 500)
    resp = api_client.get("/api/runs/run-1/diagnostics")
    assert resp.status_code == 200
    assert resp.json() == []
    assert api_client.get("/api/runs/nope/diagnostics").status_code == 404


def test_diagnostics_returned_when_gate_enabled(api_client):
    import services.api.deps as deps_mod
    _seed_run(deps_mod.get_store().db_path, with_diagnostics=True)

    resp = api_client.get("/api/runs/run-1/diagnostics")
    assert resp.status_code == 200
    rows = resp.json()
    assert rows == [
        {"check_name": "amount_not_null", "row": {"ORDER_ID": 1}},
        {"check_name": "amount_not_null", "row": {"ORDER_ID": 2}},
    ]
    # Filter auf check_name
    assert api_client.get("/api/runs/run-1/diagnostics?check_name=other").json() == []


def test_run_carries_contract_version_and_hash(api_client):
    """F3: dq_runs.contract_version / contract_hash / actor are persisted and
    returned by GET /api/runs/{run_id} so compliance can be attributed to the
    exact contract revision that was certified when the run executed."""
    import services.api.deps as deps_mod
    from dq_core.engine.models import CheckResult, RunSummary
    from dq_core.store.sqlite_store import ResultStore

    store = ResultStore(deps_mod.get_store().db_path)
    now = datetime.now(timezone.utc).isoformat()
    store.save_run(RunSummary(
        run_id="run-f3",
        dataset="DS_SALES_ORDERS",
        schema="CORE_DWH",
        started_at=now,
        finished_at=now,
        overall_status="pass",
        total=1, passed=1, failed=0, warnings=0,
        results=[CheckResult(name="c", sql="SELECT 1", expect="= 1",
                             severity="fail", passed=True)],
        run_state="finished",
        contract_version="1.0.0",
        contract_hash="abc123def456",
        actor="steward@example.com",
        triggered_by="steward-sub",
    ))

    resp = api_client.get("/api/runs/run-f3")
    assert resp.status_code == 200
    body = resp.json()
    assert body["contract_version"] == "1.0.0", body
    assert body["contract_hash"] == "abc123def456", body
    assert body["actor"] == "steward@example.com", body
    assert all("kind" in r for r in body["results"])
