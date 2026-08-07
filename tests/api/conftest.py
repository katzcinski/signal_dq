"""Shared fixtures for API tests.

Provides an isolated TestClient bound to a fresh temp store/contracts dir per
test, without disturbing the module-level client in test_api_basic.py.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "packages"))
sys.path.insert(0, str(Path(__file__).parents[2]))

import json
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def api_client(tmp_path, monkeypatch):
    contracts = tmp_path / "contracts"
    checks = tmp_path / "checks"
    contracts.mkdir()
    checks.mkdir()
    inv = tmp_path / "inventory.json"
    lin = tmp_path / "lineage.json"
    inv.write_text(json.dumps({"objects": [
        {"id": "DS_SALES_ORDERS", "name": "DS_SALES_ORDERS", "schema": "CORE_DWH",
         "space": "SALES", "layer": "consumption", "family": "quality",
         "lifecycle": "active", "owned_by": "product"},
    ]}))
    lin.write_text(json.dumps({"nodes": [{"id": "DS_SALES_ORDERS"}], "edges": []}))

    monkeypatch.setenv("SQLITE_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("CONTRACTS_DIR", str(contracts))
    monkeypatch.setenv("CHECKS_DIR", str(checks))
    monkeypatch.setenv("INVENTORY_FILE", str(inv))
    monkeypatch.setenv("LINEAGE_FILE", str(lin))
    monkeypatch.setenv("CONNECTOR_FILE", str(tmp_path / "datasphere.yml"))
    monkeypatch.setenv("ENVIRONMENTS_FILE", str(tmp_path / "environments.yml"))
    monkeypatch.setenv("SECRETS_FILE", str(tmp_path / "secrets.local.yml"))

    import services.api.settings as settings_mod
    import services.api.deps as deps_mod
    import services.api.datasphere as datasphere_mod
    import services.api.datasphere_catalog as catalog_mod
    settings_mod._settings = None
    deps_mod._store_instance = None
    datasphere_mod.reset_client()
    catalog_mod.reset_catalog_client()

    from services.api.main import create_app
    client = TestClient(create_app())
    yield client

    settings_mod._settings = None
    deps_mod._store_instance = None
    datasphere_mod.reset_client()
    catalog_mod.reset_catalog_client()
