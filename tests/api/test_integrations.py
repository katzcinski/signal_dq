"""Integrations-Router (Entropy): Config-Status, ODCS-Import, Publish-Dry-Run."""


def _odcs_doc():
    return {
        "apiVersion": "v3.1.0",
        "kind": "DataContract",
        "id": "DS_MARKET_ORDERS",
        "name": "DS_MARKET_ORDERS",
        "version": "2.0.0",
        "status": "active",
        "schema": [{
            "name": "DS_MARKET_ORDERS",
            "properties": [
                {"name": "ORDER_ID", "required": True, "primaryKey": True, "primaryKeyPosition": 1, "unique": True},
                {"name": "AMOUNT", "quality": [
                    {"type": "library", "metric": "nullValues", "unit": "percent", "mustBeLessOrEqualTo": 0.5}
                ]},
            ],
            "quality": [{"type": "library", "metric": "rowCount", "mustBeGreaterOrEqualTo": 100}],
        }],
        "customProperties": [{"property": "signal_kind", "value": "consumer_contract"}],
    }


def test_entropy_config_default_off(api_client):
    resp = api_client.get("/api/integrations/entropy")
    assert resp.status_code == 200
    body = resp.json()
    assert body["enabled"] is False
    assert body["mode"] == "off"
    assert body["source_of_truth"] == "signal"
    # Never leak secrets.
    assert "token" not in body or body.get("token_set") in (True, False)
    assert "entropy_token" not in body


def test_import_odcs_creates_draft(api_client):
    resp = api_client.post("/api/integrations/entropy/import/odcs", json={"odcs": _odcs_doc()})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["persisted"] is True
    assert body["product"] == "DS_MARKET_ORDERS"
    g = body["contract"]["guarantees"]
    assert g["keys"] == [{"columns": ["ORDER_ID"], "unique": True}]
    assert g["volume"] == {"min_rows": 100}
    # The imported contract is now readable as a draft.
    got = api_client.get("/api/contracts/DS_MARKET_ORDERS")
    assert got.status_code == 200
    assert got.json()["lifecycle"] == "draft"
    assert got.json()["kind"] == "consumer_contract"


def test_import_odcs_dry_run_does_not_persist(api_client):
    resp = api_client.post(
        "/api/integrations/entropy/import/odcs",
        json={"odcs": _odcs_doc(), "dry_run": True},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["persisted"] is False
    assert api_client.get("/api/contracts/DS_MARKET_ORDERS").status_code == 404


def test_publish_contract_skipped_when_disabled(api_client):
    # Seed a governance contract first.
    api_client.put("/api/contracts/DS_PUB", json={
        "product": "DS_PUB", "kind": "consumer_contract", "dataset": "DS_PUB",
        "owned_by": "product", "version": "1.0.0",
        "guarantees": {"volume": {"min_rows": 1}},
    })
    resp = api_client.post("/api/integrations/entropy/contracts/DS_PUB")
    assert resp.status_code == 200, resp.text
    # Publish disabled by default → skipped, never an error.
    assert resp.json()["status"] == "skipped"
