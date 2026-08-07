"""Lite-Modus one-step certify (N1/D8): save → active → compile in einem Call.

Schließt die Lücke, dass ein rein in Lite erstellter Contract bisher als Draft
hängen blieb und damit NICHT im persistenten Cockpit (Status/Compliance/Coverage)
sichtbar wurde. Der Certify-Pfad zertifiziert + kompiliert direkt, ohne die
SemVer-/Approval-Zeremonie des Voll-Modus — aber mit unveränderten Gates G1/G3.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "packages"))
sys.path.insert(0, str(Path(__file__).parents[2]))


def _lite_body(**overrides):
    body = {
        "product": "DS_SALES_ORDERS",
        "kind": "consumer_contract",
        "dataset": "DS_SALES_ORDERS",
        "owned_by": "product",
        "version": "1.0.0",
        "guarantees": {
            "keys": [{"columns": ["ORDER_ID"], "unique": True, "severity": "critical"}],
            "not_null": [{"columns": ["ORDER_ID", "CUSTOMER_ID"], "severity": "fail"}],
            "volume": {"min_rows": 1000, "severity": "warn"},
        },
    }
    body.update(overrides)
    return body


def test_certify_lights_up_persistent_substrate(api_client):
    """Ein Lite-Certify macht den Contract aktiv, kompiliert die Checks und
    lässt das Objekt in der Coverage-Map als 'covered' erscheinen — der ganze
    Punkt des Lite-Ansatzes (Verbindlichkeit ohne Governance-Zeremonie)."""
    resp = api_client.post("/api/contracts/DS_SALES_ORDERS/certify", json=_lite_body())
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["lifecycle"] == "active", body
    # Compliance-Ampel existiert ab jetzt (unknown bis zum ersten Lauf).
    assert body["compliance"] == "unknown", body

    # Der Contract liegt aktiv auf Platte und wird so ausgeliefert.
    got = api_client.get("/api/contracts/DS_SALES_ORDERS")
    assert got.status_code == 200
    assert got.json()["lifecycle"] == "active"

    # Coverage-Map: kompilierte Checks vorhanden ⇒ 'covered' (vorher 'gap'/out_of_scope).
    objects = {o["id"]: o for o in api_client.get("/api/objects").json()}
    assert objects["DS_SALES_ORDERS"]["cov_flag"] == "covered", objects["DS_SALES_ORDERS"]
    assert objects["DS_SALES_ORDERS"]["contract_status"] == "active"


def test_get_contract_reports_certified_snapshot_flag(api_client):
    draft = api_client.put("/api/contracts/DS_SALES_ORDERS", json=_lite_body())
    assert draft.status_code == 200, draft.text
    assert draft.json()["certified"] is False

    got_draft = api_client.get("/api/contracts/DS_SALES_ORDERS")
    assert got_draft.status_code == 200
    assert got_draft.json()["certified"] is False

    resp = api_client.post("/api/contracts/DS_SALES_ORDERS/certify", json=_lite_body())
    assert resp.status_code == 200, resp.text
    assert resp.json()["certified"] is True

    got_active = api_client.get("/api/contracts/DS_SALES_ORDERS")
    assert got_active.status_code == 200
    assert got_active.json()["certified"] is True


def test_certify_internal_gate_stays_out_of_compliance(api_client):
    """Batch 4: active gates compile checks, but never seed governance compliance/SLA."""
    resp = api_client.post(
        "/api/contracts/DS_SALES_ORDERS/certify",
        json=_lite_body(kind="internal_gate"),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["kind"] == "internal_gate"
    assert body["compliance"] is None

    sla = api_client.get("/api/contracts/DS_SALES_ORDERS/sla").json()
    assert sla["kind"] == "internal_gate"
    assert sla["current"] == "unknown"
    assert sla["windows"] == {"7d": None, "30d": None, "90d": None}

    badge = api_client.get("/api/badge/DS_SALES_ORDERS?format=json").json()
    assert badge["compliance"] == "unknown"
    assert badge["contract_version"] == ""


def test_certify_rejects_zero_check_contract(api_client):
    """Ein Contract ohne kompilierbare Garantie darf nicht zertifizieren —
    sonst stünde eine leere Ampel ohne irgendeine Messung."""
    resp = api_client.post(
        "/api/contracts/DS_SALES_ORDERS/certify",
        json=_lite_body(guarantees={}),
    )
    assert resp.status_code == 422, resp.text
    # Nichts wurde aktiviert.
    assert api_client.get("/api/contracts/DS_SALES_ORDERS").status_code == 404


def test_certify_rejects_sql_smuggling_g1(api_client):
    """G1 bleibt scharf: SQL im Contract wird auch über den Lite-Pfad abgewiesen."""
    resp = api_client.post(
        "/api/contracts/DS_SALES_ORDERS/certify",
        json=_lite_body(guarantees={
            "keys": [{"columns": ["ORDER_ID; DROP TABLE x"], "unique": True}],
        }),
    )
    assert resp.status_code == 422, resp.text


def test_certify_keeps_breaking_gate_for_certified_contract_g3(api_client):
    """G3 bleibt intakt: Lite darf ein Produkt von Null aufsetzen, aber keinen
    *breaking* Change an einer bereits zertifizierten Version am Gate
    vorbeischmuggeln — der muss über den Voll-Modus (/approve)."""
    first = api_client.post("/api/contracts/DS_SALES_ORDERS/certify", json=_lite_body())
    assert first.status_code == 200, first.text

    # Key-Wechsel = breaking; gleiche Major-Version ⇒ blockiert.
    breaking = _lite_body(guarantees={
        "keys": [{"columns": ["CUSTOMER_ID"], "unique": True, "severity": "critical"}],
    })
    resp = api_client.post("/api/contracts/DS_SALES_ORDERS/certify", json=breaking)
    assert resp.status_code == 409, resp.text
    assert "G3" in resp.json()["detail"]["message"]


def test_certify_internal_gate_breaking_change_without_major_bump(api_client):
    first = api_client.post(
        "/api/contracts/DS_SALES_ORDERS/certify",
        json=_lite_body(kind="internal_gate"),
    )
    assert first.status_code == 200, first.text

    breaking = _lite_body(
        kind="internal_gate",
        version="1.1.0",
        guarantees={
            "keys": [{"columns": ["CUSTOMER_ID"], "unique": True, "severity": "critical"}],
        },
    )
    resp = api_client.post("/api/contracts/DS_SALES_ORDERS/certify", json=breaking)

    assert resp.status_code == 200, resp.text
    assert resp.json()["lifecycle"] == "active"


def test_certify_allows_non_breaking_amendment(api_client):
    """Eine additive, nicht-breaking Änderung (lockerere Severity) darf der
    Lite-Pfad direkt re-zertifizieren."""
    assert api_client.post("/api/contracts/DS_SALES_ORDERS/certify", json=_lite_body()).status_code == 200

    relaxed = _lite_body(guarantees={
        "keys": [{"columns": ["ORDER_ID"], "unique": True, "severity": "critical"}],
        "not_null": [{"columns": ["ORDER_ID", "CUSTOMER_ID"], "severity": "fail"}],
        "volume": {"min_rows": 500, "severity": "warn"},  # lowering min_rows = not breaking
    })
    resp = api_client.post("/api/contracts/DS_SALES_ORDERS/certify", json=relaxed)
    assert resp.status_code == 200, resp.text
    assert resp.json()["lifecycle"] == "active"


def test_certify_requires_write_permission(api_client):
    """[AUTHZ] viewer darf nicht zertifizieren."""
    resp = api_client.post(
        "/api/contracts/DS_SALES_ORDERS/certify",
        json=_lite_body(),
        headers={"X-DQ-Role": "viewer"},
    )
    assert resp.status_code == 403, resp.text
