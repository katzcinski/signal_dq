"""P6: GET /api/contracts/{product}/observed — beobachtete Realität je Garantie.

Read-only-Rollup: der Compiler bildet Garantien auf Checks ab, die persistierte
Result-Historie liefert letzten Messwert, Sparkline-Reihe und PASS/FAIL.
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "packages"))
sys.path.insert(0, str(Path(__file__).parents[2]))

CONTRACT = {
    "product": "DS_SALES_ORDERS",
    "kind": "internal_gate",
    "dataset": "DS_SALES_ORDERS",
    "owned_by": "platform",
    "version": "0.1.0",
    "guarantees": {
        "volume": {"min_rows": 100, "severity": "warn"},
        "freshness": {"column": "LOAD_TS", "max_age": "PT24H", "severity": "warn"},
    },
}


def _seed_history(db_path, name, dataset, points):
    """points: list of (run_id, started_at_iso, actual_value, passed)."""
    from dq_core.engine.models import CheckResult, RunSummary
    from dq_core.store.sqlite_store import ResultStore

    store = ResultStore(db_path)
    for run_id, at, actual, passed in points:
        store.save_run(RunSummary(
            run_id=run_id, dataset=dataset, schema="S",
            started_at=at, finished_at=at,
            overall_status="pass" if passed else "fail",
            total=1, passed=1 if passed else 0, failed=0 if passed else 1, warnings=0,
            results=[CheckResult(
                name=name, sql="SELECT 1", expect=">= 100", severity="warn",
                passed=passed, actual_value=actual, type="row_count",
            )],
            run_state="finished",
        ))


def test_observed_reality_groups_by_guarantee(api_client):
    import services.api.deps as deps_mod

    assert api_client.put("/api/contracts/DS_SALES_ORDERS", json=CONTRACT).status_code == 200

    db = deps_mod.get_store().db_path
    now = datetime.now(timezone.utc)
    older = (now - timedelta(hours=3)).isoformat()
    newer = now.isoformat()
    # volume compiles to check "volume_min_rows" (type row_count → family volume).
    _seed_history(db, "volume_min_rows", "DS_SALES_ORDERS", [
        ("run-old", older, 120, True),
        ("run-new", newer, 150, True),
    ])

    resp = api_client.get("/api/contracts/DS_SALES_ORDERS/observed")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["product"] == "DS_SALES_ORDERS"
    assert body["dataset"] == "DS_SALES_ORDERS"

    fams = {g["family"]: g for g in body["guarantees"]}
    assert "volume" in fams and "freshness" in fams

    volume = fams["volume"]
    assert volume["state"] == "pass"
    check = volume["checks"][0]
    assert check["name"] == "volume_min_rows"
    assert check["family"] == "volume"
    assert check["passed"] is True
    assert float(check["last_value"]) == 150.0
    # get_check_history liefert DESC → der Endpoint dreht auf aufsteigend (Sparkline).
    assert [p["value"] for p in check["points"]] == [120.0, 150.0]

    # freshness ist definiert, hat aber keine Historie → unknown, keine Punkte.
    freshness = fams["freshness"]
    assert freshness["state"] == "unknown"
    assert freshness["checks"][0]["points"] == []
    assert freshness["checks"][0]["last_value"] is None


def test_observed_reality_marks_failing_family(api_client):
    import services.api.deps as deps_mod

    assert api_client.put("/api/contracts/DS_SALES_ORDERS", json=CONTRACT).status_code == 200
    db = deps_mod.get_store().db_path
    now = datetime.now(timezone.utc).isoformat()
    _seed_history(db, "volume_min_rows", "DS_SALES_ORDERS", [("run-fail", now, 40, False)])

    body = api_client.get("/api/contracts/DS_SALES_ORDERS/observed").json()
    fams = {g["family"]: g for g in body["guarantees"]}
    assert fams["volume"]["state"] == "fail"
    assert fams["volume"]["checks"][0]["passed"] is False


def test_observed_reality_404_for_unknown_contract(api_client):
    assert api_client.get("/api/contracts/NOPE/observed").status_code == 404
