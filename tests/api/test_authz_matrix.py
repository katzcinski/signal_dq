"""[AUTHZ] S-2/S-6: mutierende Endpunkte × Rollen.

NoAuth-Modus simuliert Rollen über X-DQ-Role — der Server bleibt autoritativ.
"""
import pytest


def _put(client, product, role=None, **overrides):
    headers = {"X-DQ-Role": role} if role else {}
    body = {
        "product": product,
        "dataset": product,
        "owned_by": "platform",
        "version": "1.0.0",
        "guarantees": {"keys": [{"columns": ["ORDER_ID"], "unique": True}]},
    }
    body.update(overrides)
    return client.put(f"/api/contracts/{product}", json=body, headers=headers)


def test_viewer_cannot_write_contract(api_client):
    resp = _put(api_client, "AZ1", role="viewer")
    assert resp.status_code == 403


def test_steward_can_write_platform_contract(api_client):
    assert _put(api_client, "AZ2", role="steward").status_code == 200


def test_authz_uses_disk_state_not_body(api_client):
    """S-2: ein product-owned Contract ist für steward tabu — auch wenn der
    Body owned_by=platform behauptet."""
    assert _put(api_client, "AZ3", owned_by="product").status_code == 200  # admin legt an
    resp = _put(api_client, "AZ3", role="steward", owned_by="platform")
    assert resp.status_code == 403, resp.text


def test_put_cannot_set_lifecycle_active(api_client):
    """Lifecycle ist kein Eingabefeld — PUT erzeugt immer einen Draft."""
    resp = _put(api_client, "AZ4")
    assert resp.status_code == 200
    assert resp.json()["lifecycle"] == "draft"
    # selbst mit lifecycle im Body (unbekanntes Feld wird ignoriert)
    resp = api_client.put(
        "/api/contracts/AZ4",
        json={"product": "AZ4", "dataset": "AZ4", "version": "1.0.0",
              "lifecycle": "active", "guarantees": {}},
    )
    assert resp.status_code in (200, 422)
    if resp.status_code == 200:
        assert resp.json()["lifecycle"] == "draft"


def test_viewer_cannot_seed_compile_revert_or_run(api_client):
    headers = {"X-DQ-Role": "viewer"}
    _put(api_client, "AZ5")
    assert api_client.post("/api/contracts/AZ5/seed", headers=headers).status_code == 403
    assert api_client.post("/api/contracts/AZ5/approve", headers=headers).status_code == 403
    api_client.post("/api/contracts/AZ5/approve")  # als admin aktivieren
    assert api_client.post("/api/contracts/AZ5/compile", headers=headers).status_code == 403
    assert api_client.post("/api/checks/AZ5/dry-run", headers=headers, json={}).status_code == 403
    assert api_client.post("/api/checks/AZ5/revert", headers=headers).status_code == 403
    assert (
        api_client.post("/api/objects/DS_SALES_ORDERS/run", headers=headers, json={}).status_code
        == 403
    )


def test_product_name_validation(api_client):
    assert api_client.get("/api/contracts/X.active").status_code == 422
    assert _put(api_client, "bad name").status_code == 422
