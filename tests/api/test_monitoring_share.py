"""„Für Monitoring verfügbar machen" — Hybrid (ADR-0002).

Signal hält nur den Soll-Zustand; ein externes Skript provisioniert Share+View.
Getestet: die reinen Helfer (View-Name, Projektions-SQL), der Request→Manifest→
Status-Callback-Fluss und die Reconcile-Semantik beim Entfernen.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "packages"))
sys.path.insert(0, str(Path(__file__).parents[2]))

import pytest
from fastapi.testclient import TestClient

from services.api.monitoring_share import (
    build_projection_sql,
    normalize_columns,
    view_name,
)


# --- pure helpers ---

def test_view_name_prefixes_space_and_sanitizes():
    assert view_name("SP1", "CUSTOMERS") == "SP1__CUSTOMERS"
    assert view_name("S-P/1", "A.B") == "S_P_1__A_B"


def test_normalize_columns_handles_str_and_dict():
    assert normalize_columns(["A", {"name": "B"}, {"technicalName": "C"}, {}, 5]) == ["A", "B", "C"]
    assert normalize_columns(None) == []


def test_build_projection_sql_explicit_columns():
    sql = build_projection_sql(
        monitoring_space="MON", view="SP1__CUST",
        source_space="SP1", technical_name="CUST", columns=["A", "B"],
    )
    assert sql == 'CREATE VIEW "MON"."SP1__CUST" AS SELECT "A", "B" FROM "SP1"."CUST"'


def test_build_projection_sql_falls_back_to_star():
    sql = build_projection_sql(
        monitoring_space="MON", view="V", source_space="SP1",
        technical_name="CUST", columns=[],
    )
    assert "SELECT * FROM" in sql


# --- endpoints ---

@pytest.fixture
def client(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    contracts = tmp_path / "contracts"
    checks = tmp_path / "checks"
    for d in (data_dir, contracts, checks):
        d.mkdir()
    inv = data_dir / "inventory.json"
    inv.write_text(json.dumps({"objects": [
        {"id": "OBJ_A", "technicalName": "OBJ_A", "name": "OBJ_A", "space": "SP1",
         "columns": [{"name": "C1"}, {"name": "C2"}]},
    ]}))

    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.setenv("INVENTORY_FILE", str(inv))
    monkeypatch.setenv("CONTRACTS_DIR", str(contracts))
    monkeypatch.setenv("CHECKS_DIR", str(checks))
    monkeypatch.setenv("SQLITE_DB", str(tmp_path / "t.db"))

    import services.api.settings as settings_mod
    import services.api.deps as deps_mod
    settings_mod._settings = None
    deps_mod._store_instance = None

    from services.api.main import create_app
    yield TestClient(create_app()), monkeypatch, settings_mod

    settings_mod._settings = None
    deps_mod._store_instance = None


def _enable(mp, settings_mod):
    mp.setenv("DATASPHERE_MONITORING_SPACE", "MON")
    settings_mod._settings = None


def test_disabled_without_monitoring_space(client):
    c, _, _ = client
    assert c.get("/api/monitoring/config").json()["enabled"] is False
    assert c.get("/api/monitoring/shares").json() == {"shares": []}
    assert c.post("/api/monitoring/shares/OBJ_A").status_code == 503
    assert c.get("/api/monitoring/manifest").status_code == 503


def test_request_records_desired_state_no_write(client):
    c, mp, settings_mod = client
    _enable(mp, settings_mod)

    assert c.get("/api/monitoring/config").json() == {"enabled": True, "monitoring_space": "MON"}

    entry = c.post("/api/monitoring/shares/OBJ_A").json()
    assert entry["status"] == "requested"
    assert entry["view"] == "SP1__OBJ_A"
    assert entry["columns"] == ["C1", "C2"]

    shares = c.get("/api/monitoring/shares").json()["shares"]
    assert shares == [{"object_id": "OBJ_A", "status": "requested", "view": "SP1__OBJ_A", "error": None}]


def test_manifest_carries_projection_sql_for_the_script(client):
    c, mp, settings_mod = client
    _enable(mp, settings_mod)
    c.post("/api/monitoring/shares/OBJ_A")

    man = c.get("/api/monitoring/manifest").json()
    assert man["monitoring_space"] == "MON"
    e = man["entries"][0]
    assert e["object_id"] == "OBJ_A"
    assert e["projection_sql"] == (
        'CREATE VIEW "MON"."SP1__OBJ_A" AS SELECT "C1", "C2" FROM "SP1"."OBJ_A"'
    )


def test_status_callback_roundtrip(client):
    c, mp, settings_mod = client
    _enable(mp, settings_mod)
    c.post("/api/monitoring/shares/OBJ_A")

    r = c.put("/api/monitoring/shares/OBJ_A/status", json={"status": "provisioned"})
    assert r.status_code == 200
    assert r.json()["status"] == "provisioned"
    assert r.json()["provisioned_at"] is not None

    # unknown object → 404; invalid status → 422
    assert c.put("/api/monitoring/shares/NOPE/status", json={"status": "provisioned"}).status_code == 404
    assert c.put("/api/monitoring/shares/OBJ_A/status", json={"status": "bogus"}).status_code == 422


def test_request_is_idempotent_and_keeps_status(client):
    c, mp, settings_mod = client
    _enable(mp, settings_mod)
    c.post("/api/monitoring/shares/OBJ_A")
    c.put("/api/monitoring/shares/OBJ_A/status", json={"status": "provisioned"})
    # re-request must not reset a provisioned object back to requested
    again = c.post("/api/monitoring/shares/OBJ_A").json()
    assert again["status"] == "provisioned"
    assert len(c.get("/api/monitoring/shares").json()["shares"]) == 1


def test_remove_drops_from_desired_state(client):
    c, mp, settings_mod = client
    _enable(mp, settings_mod)
    c.post("/api/monitoring/shares/OBJ_A")
    assert c.request("DELETE", "/api/monitoring/shares/OBJ_A").json()["status"] == "removed"
    assert c.get("/api/monitoring/shares").json()["shares"] == []
    assert c.request("DELETE", "/api/monitoring/shares/OBJ_A").json()["status"] == "not_found"


def test_request_unknown_object_404(client):
    c, mp, settings_mod = client
    _enable(mp, settings_mod)
    assert c.post("/api/monitoring/shares/NOPE").status_code == 404


# --- S-2: AuthZ auf den Schreib-/Skript-Endpunkten ---

def test_viewer_cannot_mutate_shares(client):
    c, mp, settings_mod = client
    _enable(mp, settings_mod)
    v = {"X-DQ-Role": "viewer"}
    assert c.post("/api/monitoring/shares/OBJ_A", headers=v).status_code == 403
    assert c.request("DELETE", "/api/monitoring/shares/OBJ_A", headers=v).status_code == 403


def test_service_endpoints_require_token_when_configured(client):
    c, mp, settings_mod = client
    _enable(mp, settings_mod)
    mp.setenv("MONITORING_SERVICE_TOKEN", "s3cr3t")
    settings_mod._settings = None
    c.post("/api/monitoring/shares/OBJ_A")  # noauth admin darf vormerken

    # Ohne/mit falschem Token → 401
    assert c.get("/api/monitoring/manifest").status_code == 401
    assert c.get("/api/monitoring/manifest", headers={"X-Service-Token": "nope"}).status_code == 401
    assert c.put("/api/monitoring/shares/OBJ_A/status", json={"status": "provisioned"}).status_code == 401

    # Mit korrektem Token → normaler Ablauf
    tok = {"X-Service-Token": "s3cr3t"}
    assert c.get("/api/monitoring/manifest", headers=tok).status_code == 200
    r = c.put("/api/monitoring/shares/OBJ_A/status", json={"status": "provisioned"}, headers=tok)
    assert r.status_code == 200 and r.json()["status"] == "provisioned"
