"""R4/R5-Endpunkte: Incidents-Lifecycle, SLA, Coverage, Badge, Environments, ODCS."""


def _activate_contract(client, product="DS_SALES_ORDERS"):
    client.put(
        f"/api/contracts/{product}",
        json={
            "product": product, "dataset": product, "owned_by": "platform",
            "kind": "consumer_contract",
            "version": "1.0.0",
            "guarantees": {"keys": [{"columns": ["ORDER_ID"], "unique": True}]},
        },
    )
    return client.post(f"/api/contracts/{product}/approve")


def test_incident_endpoints(api_client):
    # leer
    assert api_client.get("/api/incidents").json() == []
    # alte abgeleitete Sicht lebt unter /checks weiter
    assert api_client.get("/api/incidents/checks").status_code == 200
    # ungültiger Statusfilter
    assert api_client.get("/api/incidents?status=bogus").status_code == 422
    # Transition auf nicht existentes Incident
    assert api_client.post("/api/incidents/999/transition", json={"status": "resolved"}).status_code == 404
    # Viewer darf nicht transitionieren
    resp = api_client.post(
        "/api/incidents/1/transition", json={"status": "resolved"},
        headers={"X-DQ-Role": "viewer"},
    )
    assert resp.status_code == 403


def test_sla_endpoint(api_client):
    assert _activate_contract(api_client).status_code == 200
    resp = api_client.get("/api/contracts/DS_SALES_ORDERS/sla")
    assert resp.status_code == 200
    body = resp.json()
    assert body["current"] in ("unknown", "compliant", "breached")
    assert body["kind"] == "consumer_contract"
    assert set(body["windows"].keys()) == {"7d", "30d", "90d"}
    assert api_client.get("/api/contracts/NOPE/sla").status_code == 404


def test_coverage_summary(api_client):
    resp = api_client.get("/api/coverage/summary")
    assert resp.status_code == 200
    body = resp.json()
    assert body["objects_total"] >= 1
    assert "contract_coverage_pct" in body
    assert "contracts_breached" in body
    assert "gates_failing" in body
    assert isinstance(body["unvalidated_30d"], list)


def test_badge(api_client):
    _activate_contract(api_client)
    svg = api_client.get("/api/badge/DS_SALES_ORDERS")
    assert svg.status_code == 200
    assert svg.headers["content-type"].startswith("image/svg+xml")
    assert "DQ DS_SALES_ORDERS" in svg.text

    js = api_client.get("/api/badge/DS_SALES_ORDERS?format=json").json()
    assert js["product"] == "DS_SALES_ORDERS"
    assert api_client.get("/api/badge/bad%20name").status_code == 422


def test_environments_no_secrets(api_client, tmp_path, monkeypatch):
    env_file = tmp_path / "environments.yml"
    env_file.write_text(
        "dev:\n  host: hana.example.com\n  port: 443\n  schema: DEV_SCHEMA\n"
        "  user: SECRET_USER\n  password: SECRET_PW\n"
    )
    monkeypatch.setenv("ENVIRONMENTS_FILE", str(env_file))
    import services.api.settings as settings_mod
    settings_mod._settings = None

    resp = api_client.get("/api/environments")
    assert resp.status_code == 200
    body = resp.json()
    assert body["environments"] == [{
        "name": "dev",
        "schema": "DEV_SCHEMA",
        "host": "***.example.com",
        "secret_status": True,
    }]
    assert set(body["environments"][0]) == {"name", "schema", "host", "secret_status"}
    assert "SECRET" not in resp.text  # S-13: nie Credentials ausliefern

    settings_mod._settings = None


def test_environment_config_crud_masks_and_preserves_secret(api_client, tmp_path, monkeypatch):
    env_file = tmp_path / "environments.yml"
    monkeypatch.setenv("ENVIRONMENTS_FILE", str(env_file))
    monkeypatch.setenv("HANA_PW_DEV", "secret-value")
    import services.api.settings as settings_mod
    settings_mod._settings = None

    viewer = api_client.get(
        "/api/environments/config",
        headers={"X-DQ-Role": "viewer"},
    )
    assert viewer.status_code == 403

    denied = api_client.put(
        "/api/environments/config/dev",
        headers={"X-DQ-Role": "steward"},
        json={
            "host": "hana.example.com",
            "port": 443,
            "user": "SIGNAL_TEST",
            "schema": "DEV_SCHEMA",
            "password_ref": "env:HANA_PW_DEV",
        },
    )
    assert denied.status_code == 403

    created = api_client.put(
        "/api/environments/config/dev",
        json={
            "host": "hana.example.com",
            "port": 443,
            "user": "SIGNAL_TEST",
            "schema": "DEV_SCHEMA",
            "password_ref": "env:HANA_PW_DEV",
        },
    )
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["name"] == "dev"
    assert body["password_ref"] == "env:HANA_PW_DEV"
    assert body["secret_configured"] is True
    assert body["secret_available"] is True
    assert "secret-value" not in created.text

    cfg = api_client.get(
        "/api/environments/config",
        headers={"X-DQ-Role": "steward"},
    ).json()
    assert cfg["can_edit"] is False
    assert cfg["environments"][0]["user"] == "SIGNAL_TEST"
    assert "secret-value" not in str(cfg)

    updated = api_client.put(
        "/api/environments/config/dev",
        json={
            "host": "hana2.example.com",
            "port": 443,
            "user": "SIGNAL_TEST",
            "schema": "DEV_SCHEMA",
        },
    )
    assert updated.status_code == 200
    text = env_file.read_text(encoding="utf-8")
    assert "hana2.example.com" in text
    assert "password_ref: env:HANA_PW_DEV" in text
    assert "secret-value" not in text

    deleted = api_client.delete("/api/environments/config/dev")
    assert deleted.status_code == 204
    assert api_client.get("/api/environments").json() == {"environments": []}

    settings_mod._settings = None


def test_odcs_export_endpoint(api_client):
    _activate_contract(api_client)
    resp = api_client.get("/api/contracts/DS_SALES_ORDERS/export/odcs")
    assert resp.status_code == 200
    body = resp.json()
    assert body["apiVersion"] == "v3.1.0"
    assert body["kind"] == "DataContract"
    assert body["status"] == "active"

    yml = api_client.get("/api/contracts/DS_SALES_ORDERS/export/odcs?format=yaml")
    assert yml.status_code == 200
    assert "DataContract" in yml.text


def test_odcs_export_rejects_internal_gate(api_client):
    api_client.put(
        "/api/contracts/DS_SALES_ORDERS",
        json={
            "product": "DS_SALES_ORDERS",
            "kind": "internal_gate",
            "dataset": "DS_SALES_ORDERS",
            "owned_by": "platform",
            "version": "1.0.0",
            "guarantees": {"keys": [{"columns": ["ORDER_ID"], "unique": True}]},
        },
    )
    resp = api_client.get("/api/contracts/DS_SALES_ORDERS/export/odcs")
    assert resp.status_code == 409


def test_family_status_in_objects(api_client):
    resp = api_client.get("/api/objects")
    assert resp.status_code == 200
    for obj in resp.json():
        fs = obj["family_status"]
        assert set(fs.keys()) == {"observability", "quality"}


def test_contract_list_served_from_index(api_client):
    """A3: Liste kommt aus contract_index (guarantees leer), Detail aus der Datei."""
    _activate_contract(api_client, "IDX1")
    listed = api_client.get("/api/contracts").json()
    entry = next(c for c in listed if c["product"] == "IDX1")
    assert entry["lifecycle"] == "active"
    assert entry["guarantees"] == {}
    detail = api_client.get("/api/contracts/IDX1").json()
    assert detail["guarantees"]["keys"]


# ---- Pagination ----

def test_incidents_pagination(api_client):
    assert api_client.get("/api/incidents?limit=10&offset=0").status_code == 200
    assert api_client.get("/api/incidents?limit=1&offset=0").status_code == 200
    assert api_client.get("/api/incidents?limit=501").status_code == 422
    assert api_client.get("/api/incidents?limit=0").status_code == 422


def test_runs_pagination(api_client):
    assert api_client.get("/api/runs?limit=10&offset=0").status_code == 200
    assert api_client.get("/api/runs?limit=501").status_code == 422
    assert api_client.get("/api/runs?limit=0").status_code == 422


def test_incidents_pagination_offset_reduces_result(api_client):
    """Offset pagination: requesting past the end returns an empty list."""
    result = api_client.get("/api/incidents?limit=50&offset=999").json()
    assert result == []


def test_runs_pagination_offset_reduces_result(api_client):
    result = api_client.get("/api/runs?limit=50&offset=999").json()
    assert result == []


# ---- Observability ----

def test_metrics_health_endpoint(api_client):
    resp = api_client.get("/api/metrics/health")
    assert resp.status_code == 200
    body = resp.json()
    assert "requests_total" in body
    assert "requests_4xx" in body
    assert "requests_5xx" in body
    assert "uptime_s" in body
    assert body["requests_total"] >= 1  # at least this request was counted


def test_request_id_header_injected(api_client):
    resp = api_client.get("/api/health")
    assert resp.status_code == 200
    assert "x-request-id" in resp.headers


def test_request_id_propagated(api_client):
    resp = api_client.get("/api/health", headers={"X-Request-ID": "test-id-123"})
    assert resp.headers.get("x-request-id") == "test-id-123"
