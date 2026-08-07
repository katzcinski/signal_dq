"""Entropy-Publisher: opt-in, fail-open, Dry-Run-Disziplin, kein PII-/Token-Leak."""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parents[2] / "packages"))
sys.path.insert(0, str(Path(__file__).parents[2]))

from services.api import entropy


def _settings(**over):
    base = dict(
        entropy_publish_enabled=True,
        entropy_url="https://market.example.com/api",
        entropy_token="secret-token",
        entropy_allowlist=[r".*\.example\.com"],
        entropy_source_of_truth="signal",
        entropy_marketplace_verified=False,
    )
    base.update(over)
    return SimpleNamespace(**base)


def _summary():
    results = [
        SimpleNamespace(name="rows", type="row_count", passed=True, severity="warn",
                        state="executed", actual_value=1200, expect=">= 1000", expect_expr=">= 1000"),
        SimpleNamespace(name="nulls", type="missing", passed=False, severity="fail",
                        state="executed", actual_value=3, expect="= 0", expect_expr="= 0"),
    ]
    return SimpleNamespace(
        run_id="run-1", dataset="DS_SALES_ORDERS", started_at="2026-07-23T10:00:00Z",
        finished_at="2026-07-23T10:00:05Z", overall_status="fail", gate_verdict="block",
        contract_version="1.0.0", results=results,
    )


def test_disabled_is_skipped():
    res = entropy.publish_run_result(_summary(), None, _settings(entropy_publish_enabled=False))
    assert res["status"] == "skipped"


def test_unverified_marketplace_is_dry_run_and_does_not_send():
    res = entropy.publish_run_result(_summary(), {"kind": "consumer_contract"}, _settings())
    assert res["status"] == "dry_run"
    # Payload gebaut, aber nicht gesendet — enthält die Aggregat-Ergebnisse …
    payload = res["payload"]
    assert payload["summary"] == {"total": 2, "passed": 1, "failed": 1}
    assert payload["engine"]["readOnly"] is True
    # … und niemals Rohzeilen (G8): nur name/type/status/value.
    for c in payload["checks"]:
        assert set(c) <= {"name", "type", "passed", "severity", "state", "value", "expectation"}


def test_contract_registration_skipped_in_entropy_authored_mode():
    res = entropy.publish_contract_registration(
        {"product": "P", "kind": "consumer_contract", "version": "1.0.0",
         "dataset": "P", "guarantees": {"volume": {"min_rows": 1}}},
        _settings(entropy_source_of_truth="entropy"),
    )
    # E1: kein Push-Back, wenn der Marktplatz authort (keine bidirektionale Sync).
    assert res["status"] == "skipped"
    assert "source_of_truth" in res["reason"]


def test_internal_gate_not_published_as_contract():
    res = entropy.publish_contract_registration(
        {"product": "P", "kind": "internal_gate", "version": "1.0.0",
         "dataset": "P", "guarantees": {"volume": {"min_rows": 1}}},
        _settings(),
    )
    assert res["status"] == "skipped"


def test_config_status_never_leaks_token():
    status = entropy.config_status(_settings())
    assert status["token_set"] is True
    assert "secret-token" not in str(status)
    assert status["mode"] == "dry_run"  # enabled but not verified
    assert entropy.config_status(_settings(entropy_marketplace_verified=True))["mode"] == "live"
    assert entropy.config_status(_settings(entropy_publish_enabled=False))["mode"] == "off"
