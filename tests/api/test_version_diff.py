"""UX-N13: contract version-diff endpoint (working vs. certified)."""


def _put_draft(client, product, version, key_columns):
    return client.put(
        f"/api/contracts/{product}",
        json={
            "product": product, "dataset": product, "owned_by": "product",
            "lifecycle": "draft", "version": version,
            "guarantees": {"keys": [{"columns": key_columns, "unique": True}]},
        },
    )


def test_version_diff_no_baseline(api_client):
    # Draft never approved → no certified snapshot to diff against.
    assert _put_draft(api_client, "VD1", "0.1.0", ["ORDER_ID"]).status_code == 200
    resp = api_client.get("/api/contracts/VD1/version-diff")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["available"] is False
    assert body["kind"] == "internal_gate"
    assert body["ceremony_required"] is False
    assert body["blocking"] is False
    assert body["entries"] == []


def test_version_diff_reports_breaking_change(api_client):
    # Certify v1, then amend with a breaking key change.
    _put_draft(api_client, "VD2", "1.0.0", ["ORDER_ID"])
    assert api_client.post("/api/contracts/VD2/approve").status_code == 200

    # No amendment yet → working == certified → empty diff.
    body = api_client.get("/api/contracts/VD2/version-diff").json()
    assert body["available"] is True
    assert body["entries"] == []

    # Amend (key change is breaking).
    _put_draft(api_client, "VD2", "1.1.0", ["ORDER_ID", "ITEM_NO"])
    body = api_client.get("/api/contracts/VD2/version-diff").json()
    assert body["available"] is True
    assert body["breaking"] is True
    assert body["ceremony_required"] is False
    assert body["blocking"] is False
    assert body["from_version"] == "1.0.0"
    assert body["to_version"] == "1.1.0"
    kinds = {e["kind"] for e in body["entries"]}
    assert "key_change" in kinds


def test_diff_active_alias_reports_ceremony_fields(api_client):
    _put_draft(api_client, "VD3", "1.0.0", ["ORDER_ID"])
    assert api_client.post("/api/contracts/VD3/approve").status_code == 200

    body = api_client.get("/api/contracts/VD3/diff/active").json()

    assert body["available"] is True
    assert body["kind"] == "internal_gate"
    assert body["ceremony_required"] is False
    assert body["blocking"] is False


def test_version_diff_unknown_product_404(api_client):
    assert api_client.get("/api/contracts/NOPE/version-diff").status_code == 404
