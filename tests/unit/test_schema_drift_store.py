"""Schema-Drift Persistenz + kind-aware Incident (Konzept §A.4) — Store-Ebene."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "packages"))
sys.path.insert(0, str(Path(__file__).parents[2]))

from dq_core.store.sqlite_store import ResultStore
from services.api.schema_drift_service import persist_and_alert


def _store(tmp_path):
    return ResultStore(tmp_path / "drift.db")


def _contract(kind="consumer_contract"):
    return {
        "product": "DS_SALES_ORDERS", "dataset": "DS_SALES_ORDERS",
        "version": "2.0.0", "kind": kind, "lifecycle": "active",
        "guarantees": {"schema": {"columns": ["A", "B", "C"], "mode": "closed"}},
    }


def test_snapshot_always_saved(tmp_path):
    store = _store(tmp_path)
    cols = [{"name": "A"}, {"name": "B"}, {"name": "C"}]
    persist_and_alert(store, _contract(), cols)
    snap = store.get_latest_schema_snapshot("DS_SALES_ORDERS")
    assert snap is not None
    assert snap["object_name"] == "DS_SALES_ORDERS"


def test_breaking_drift_opens_contract_incident(tmp_path):
    store = _store(tmp_path)
    cols = [{"name": "A"}, {"name": "B"}]  # C entfernt → breaking
    report = persist_and_alert(store, _contract("consumer_contract"), cols)

    assert report["summary"]["has_breaking"] is True
    assert report["incident_id"] is not None

    incidents = store.list_incidents(kind="consumer_contract")
    assert len(incidents) == 1
    drift = store.get_schema_drift("DS_SALES_ORDERS")
    assert any(d["category"] == "column_removed" and d["breaking"] == 1 for d in drift)
    assert drift[0]["incident_id"] == report["incident_id"]


def test_internal_gate_drift_opens_engineering_signal(tmp_path):
    store = _store(tmp_path)
    cols = [{"name": "A"}, {"name": "B"}]  # C entfernt → breaking
    persist_and_alert(store, _contract("internal_gate"), cols)
    assert len(store.list_incidents(kind="internal_gate")) == 1
    assert len(store.list_incidents(kind="consumer_contract")) == 0


def test_no_drift_no_incident(tmp_path):
    store = _store(tmp_path)
    cols = [{"name": "A"}, {"name": "B"}, {"name": "C"}]  # exakt das Versprechen
    report = persist_and_alert(store, _contract(), cols)
    assert report["findings"] == []
    assert report["incident_id"] is None
    assert store.list_incidents() == []
