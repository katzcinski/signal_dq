"""GET /api/contracts/{product}/drift — Read-only Schema-Drift-Report (§A.6)."""
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parents[2] / "packages"))
sys.path.insert(0, str(Path(__file__).parents[2]))

from services.api.deps import get_inventory
from services.api.settings import get_settings


def _write_contract(columns, mode="closed", kind="consumer_contract"):
    cdir = Path(get_settings().contracts_dir)
    cdir.mkdir(parents=True, exist_ok=True)
    contract = {
        "product": "DS_SALES_ORDERS", "dataset": "DS_SALES_ORDERS",
        "version": "1.0.0", "kind": kind, "lifecycle": "active",
        "guarantees": {"schema": {"columns": columns, "mode": mode}},
    }
    (cdir / "DS_SALES_ORDERS.yaml").write_text(yaml.safe_dump(contract), encoding="utf-8")


def _override_inventory(client, columns):
    client.app.dependency_overrides[get_inventory] = lambda: [
        {"id": "DS_SALES_ORDERS", "dataset": "DS_SALES_ORDERS", "columns": columns}
    ]


def test_drift_report_detects_removed_column(api_client):
    _write_contract(["A", "B", "C"])
    _override_inventory(api_client, [{"name": "A"}, {"name": "B"}])  # C fehlt
    try:
        resp = api_client.get("/api/contracts/DS_SALES_ORDERS/drift")
    finally:
        api_client.app.dependency_overrides.pop(get_inventory, None)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["object_found"] is True
    assert body["summary"]["has_breaking"] is True
    cats = {(f["category"], f["column"]) for f in body["findings"]}
    assert ("column_removed", "C") in cats


def test_drift_report_clean_when_source_matches(api_client):
    _write_contract(["A", "B"])
    _override_inventory(api_client, [{"name": "A"}, {"name": "B"}])
    try:
        resp = api_client.get("/api/contracts/DS_SALES_ORDERS/drift")
    finally:
        api_client.app.dependency_overrides.pop(get_inventory, None)
    body = resp.json()
    assert body["findings"] == []
    assert body["summary"]["has_breaking"] is False


def test_drift_report_404_for_unknown_contract(api_client):
    resp = api_client.get("/api/contracts/NOPE/drift")
    assert resp.status_code == 404
