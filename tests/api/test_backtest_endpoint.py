"""V1: POST /api/contracts/{product}/backtest — Contract- und Checks-Modus."""
from datetime import datetime, timedelta, timezone

from dq_core.engine.models import CheckResult, RunSummary
from services.api.deps import get_store

NOW = datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc)


def _seed_run(store, days_ago: int, value: str, check_name: str = "volume_min_rows"):
    at = (NOW - timedelta(days=days_ago)).isoformat()
    store.save_run(RunSummary(
        run_id=f"run-{check_name}-{days_ago}", dataset="DS_SALES_ORDERS", schema="X",
        started_at=at, finished_at=at, overall_status="pass",
        total=1, passed=1, failed=0, warnings=0,
        results=[CheckResult(
            name=check_name, sql="", expect=">= 1", severity="fail",
            passed=True, actual_value=value, type="row_count",
        )],
    ))


def test_backtest_checks_mode_counts_breaches(api_client):
    store = get_store()
    for days_ago, value in [(60, "900"), (10, "1200"), (1, "800")]:
        _seed_run(store, days_ago, value)

    resp = api_client.post("/api/contracts/DS_SALES_ORDERS/backtest", json={
        "checks": [{"check_name": "volume_min_rows", "expect": ">= 1000"}],
        "window_days": [30, 90],
    })
    assert resp.status_code == 200
    body = resp.json()

    assert body["checks_total"] == 1
    assert body["checks_with_history"] == 1
    check = body["checks"][0]
    assert check["points"] == 3
    assert check["breaches"] == 2
    assert [w["breaches"] for w in check["windows"]] == [1, 2]
    assert body["summary_windows"] == [
        {"days": 30, "breaches": 1, "checks_firing": 1},
        {"days": 90, "breaches": 2, "checks_firing": 1},
    ]


def test_backtest_contract_mode_compiles_draft(api_client):
    store = get_store()
    _seed_run(store, 5, "500")
    _seed_run(store, 2, "1500")

    contract = {
        "product": "DS_SALES_ORDERS", "dataset": "DS_SALES_ORDERS",
        "version": "1.0.0", "kind": "internal_gate", "lifecycle": "draft",
        "owned_by": "platform",
        "guarantees": {"volume": {"min_rows": 1000}},
    }
    resp = api_client.post("/api/contracts/DS_SALES_ORDERS/backtest", json={"contract": contract})
    assert resp.status_code == 200
    body = resp.json()

    names = [c["check_name"] for c in body["checks"]]
    assert "volume_min_rows" in names
    vol = next(c for c in body["checks"] if c["check_name"] == "volume_min_rows")
    assert vol["expect"] == ">= 1000"
    assert vol["breaches"] == 1  # der 500er-Lauf hätte gefeuert


def test_backtest_without_history_is_calm(api_client):
    resp = api_client.post("/api/contracts/DS_SALES_ORDERS/backtest", json={
        "checks": [{"check_name": "unknown_check", "expect": ">= 1"}],
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["checks_with_history"] == 0
    assert body["checks"][0]["points"] == 0


def test_backtest_requires_contract_or_checks(api_client):
    assert api_client.post("/api/contracts/DS_SALES_ORDERS/backtest", json={}).status_code == 422


def test_backtest_invalid_expectation_422(api_client):
    resp = api_client.post("/api/contracts/DS_SALES_ORDERS/backtest", json={
        "checks": [{"check_name": "volume_min_rows", "expect": "NOT A GRAMMAR"}],
    })
    assert resp.status_code == 422


def test_backtest_sql_in_contract_is_rejected(api_client):
    # G1: auch der Backtest-Pfad schmuggelt kein SQL am Validator vorbei.
    contract = {
        "product": "DS_SALES_ORDERS", "dataset": "DS_SALES_ORDERS",
        "version": "1.0.0", "kind": "internal_gate", "lifecycle": "draft",
        "guarantees": {"volume": {"min_rows": 1000}},
        "sql": "SELECT * FROM T",
    }
    resp = api_client.post("/api/contracts/DS_SALES_ORDERS/backtest", json={"contract": contract})
    assert resp.status_code == 422
