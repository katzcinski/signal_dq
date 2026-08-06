"""Contract lifecycle endpoints — approve / deprecate + breaking guard (WS2-6 / M2)."""


def _put_draft(client, product, version, key_columns, kind="internal_gate"):
    return client.put(
        f"/api/contracts/{product}",
        json={
            "product": product,
            "kind": kind,
            "dataset": product,
            "owned_by": "product",
            "lifecycle": "draft",
            "version": version,
            "guarantees": {"keys": [{"columns": key_columns, "unique": True}]},
        },
    )


def test_approve_promotes_draft_to_active(api_client):
    assert _put_draft(api_client, "P1", "1.0.0", ["ORDER_ID"]).status_code == 200

    resp = api_client.post("/api/contracts/P1/approve")
    assert resp.status_code == 200, resp.text
    assert resp.json()["lifecycle"] == "active"

    # Subsequent GET reflects the active lifecycle.
    assert api_client.get("/api/contracts/P1").json()["lifecycle"] == "active"


def test_approve_rejects_non_draft(api_client):
    _put_draft(api_client, "P2", "1.0.0", ["ORDER_ID"])
    api_client.post("/api/contracts/P2/approve")
    # Already active → cannot approve again.
    resp = api_client.post("/api/contracts/P2/approve")
    assert resp.status_code == 409


def test_breaking_change_requires_major_bump(api_client):
    # Certify v1.
    _put_draft(api_client, "P3", "1.0.0", ["ORDER_ID"], kind="consumer_contract")
    assert api_client.post("/api/contracts/P3/approve").status_code == 200

    # Breaking change (key change) without a major bump → blocked (Gate G3).
    _put_draft(api_client, "P3", "1.1.0", ["ORDER_ID", "ITEM_NO"], kind="consumer_contract")
    resp = api_client.post("/api/contracts/P3/approve")
    assert resp.status_code == 409, resp.text
    assert "major" in str(resp.json()["detail"]).lower()

    # Same breaking change WITH a major bump → allowed.
    _put_draft(api_client, "P3", "2.0.0", ["ORDER_ID", "ITEM_NO"], kind="consumer_contract")
    resp = api_client.post("/api/contracts/P3/approve")
    assert resp.status_code == 200, resp.text
    assert resp.json()["lifecycle"] == "active"


def test_internal_gate_breaking_change_approves_without_major_bump(api_client):
    _put_draft(api_client, "P3_GATE", "1.0.0", ["ORDER_ID"])
    assert api_client.post("/api/contracts/P3_GATE/approve").status_code == 200

    _put_draft(api_client, "P3_GATE", "1.1.0", ["ORDER_ID", "ITEM_NO"])
    resp = api_client.post("/api/contracts/P3_GATE/approve")

    assert resp.status_code == 200, resp.text
    assert resp.json()["lifecycle"] == "active"


def test_draft_amendment_of_active_contract_stays_certified(api_client):
    _put_draft(api_client, "P_CERTIFIED_DRAFT", "1.0.0", ["ORDER_ID"], kind="consumer_contract")
    approved = api_client.post("/api/contracts/P_CERTIFIED_DRAFT/approve")
    assert approved.status_code == 200, approved.text
    assert approved.json()["certified"] is True

    draft = _put_draft(api_client, "P_CERTIFIED_DRAFT", "1.1.0", ["ORDER_ID"], kind="consumer_contract")
    assert draft.status_code == 200, draft.text
    assert draft.json()["lifecycle"] == "draft"
    assert draft.json()["certified"] is True

    got = api_client.get("/api/contracts/P_CERTIFIED_DRAFT")
    assert got.status_code == 200
    assert got.json()["lifecycle"] == "draft"
    assert got.json()["certified"] is True


def test_approve_internal_gate_seeds_no_compliance(api_client):
    from services.api.deps import get_store

    _put_draft(api_client, "P_GATE_COMPLIANCE", "1.0.0", ["ORDER_ID"])
    resp = api_client.post("/api/contracts/P_GATE_COMPLIANCE/approve")

    assert resp.status_code == 200, resp.text
    assert get_store().get_compliance("P_GATE_COMPLIANCE") is None


def test_approve_contract_seeds_unknown_compliance(api_client):
    from services.api.deps import get_store

    _put_draft(api_client, "P_CONTRACT_COMPLIANCE", "1.0.0", ["ORDER_ID"], kind="consumer_contract")
    resp = api_client.post("/api/contracts/P_CONTRACT_COMPLIANCE/approve")

    assert resp.status_code == 200, resp.text
    assert get_store().get_compliance("P_CONTRACT_COMPLIANCE")["compliance"] == "unknown"


def test_diff_reports_ceremony_required(api_client):
    _put_draft(api_client, "P_DIFF_GATE", "1.0.0", ["ORDER_ID"])
    gate_body = {
        "product": "P_DIFF_GATE",
        "kind": "internal_gate",
        "dataset": "P_DIFF_GATE",
        "owned_by": "product",
        "version": "1.1.0",
        "guarantees": {"keys": [{"columns": ["ORDER_ID", "ITEM_NO"], "unique": True}]},
    }
    gate_resp = api_client.post("/api/contracts/P_DIFF_GATE/diff", json=gate_body)
    assert gate_resp.status_code == 200, gate_resp.text
    assert gate_resp.json()["ceremony_required"] is False
    assert gate_resp.json()["breaking"] is True
    assert gate_resp.json()["blocking"] is False

    _put_draft(api_client, "P_DIFF_CONTRACT", "1.0.0", ["ORDER_ID"], kind="consumer_contract")
    contract_body = {
        **gate_body,
        "product": "P_DIFF_CONTRACT",
        "kind": "consumer_contract",
        "dataset": "P_DIFF_CONTRACT",
    }
    contract_resp = api_client.post("/api/contracts/P_DIFF_CONTRACT/diff", json=contract_body)
    assert contract_resp.status_code == 200, contract_resp.text
    assert contract_resp.json()["ceremony_required"] is True
    assert contract_resp.json()["breaking"] is True
    assert contract_resp.json()["blocking"] is True


def test_deprecate_active_contract(api_client):
    _put_draft(api_client, "P4", "1.0.0", ["ORDER_ID"])
    api_client.post("/api/contracts/P4/approve")

    resp = api_client.post("/api/contracts/P4/deprecate")
    assert resp.status_code == 200, resp.text
    assert resp.json()["lifecycle"] == "deprecated"


def test_deprecate_rejects_non_active(api_client):
    _put_draft(api_client, "P5", "1.0.0", ["ORDER_ID"])  # still draft
    resp = api_client.post("/api/contracts/P5/deprecate")
    assert resp.status_code == 409


def test_approve_missing_contract_404(api_client):
    assert api_client.post("/api/contracts/NOPE/approve").status_code == 404


def test_promote_creates_consumer_contract(api_client):
    assert _put_draft(api_client, "P_PROMOTE", "1.0.0", ["ORDER_ID"]).status_code == 200

    resp = api_client.post("/api/contracts/P_PROMOTE/promote")

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["kind"] == "consumer_contract"
    assert data["product"] == "P_PROMOTE_contract"
    assert data["lifecycle"] == "draft"


def test_promote_rejects_non_gate(api_client):
    assert _put_draft(
        api_client,
        "P_BOUNDARY",
        "1.0.0",
        ["ORDER_ID"],
        kind="consumer_contract",
    ).status_code == 200

    resp = api_client.post("/api/contracts/P_BOUNDARY/promote")

    assert resp.status_code == 409


def test_promote_rejects_duplicate(api_client):
    assert _put_draft(api_client, "P_DUP", "1.0.0", ["ORDER_ID"]).status_code == 200
    assert api_client.post("/api/contracts/P_DUP/promote").status_code == 200

    resp = api_client.post("/api/contracts/P_DUP/promote")

    assert resp.status_code == 409


def test_approve_returns_409_on_push_rejection(api_client, monkeypatch):
    """F1: Git push rejection surfaces as 409 with rebase hint (WS2-3 / R2-1)."""
    from services.api.git_repo import GitPushRejected, GitRepo

    def _raise_push_rejected(self, *args, **kwargs):
        raise GitPushRejected("Remote rejected — rebase required.")

    monkeypatch.setattr(GitRepo, "write_contract", _raise_push_rejected)

    _put_draft(api_client, "P_PUSH", "1.0.0", ["ORDER_ID"])
    resp = api_client.post("/api/contracts/P_PUSH/approve")
    assert resp.status_code == 409, resp.text
    assert "rejected" in resp.json()["detail"].lower() or "rebase" in resp.json()["detail"].lower()
