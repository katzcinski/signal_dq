from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parents[2] / "packages"))
sys.path.insert(0, str(Path(__file__).parents[2]))

from fastapi.testclient import TestClient


def _client(tmp_path, monkeypatch) -> TestClient:
    contracts = tmp_path / "contracts"
    checks = tmp_path / "checks"
    products = tmp_path / "products"
    contracts.mkdir()
    checks.mkdir()
    products.mkdir()

    lineage = tmp_path / "lineage.json"
    inventory = tmp_path / "inventory.json"
    lineage.write_text(
        json.dumps({
            "nodes": [
                {"id": "RAW_ORDERS", "layer": "source", "role": "source"},
                {"id": "CORE_ORDERS", "layer": "transformation", "role": "core", "coverage_flag": "covered"},
                {"id": "DS_PRODUCT", "layer": "serving", "role": "consumption"},
            ],
            "edges": [
                {"source": "RAW_ORDERS", "target": "CORE_ORDERS"},
                {"source": "CORE_ORDERS", "target": "DS_PRODUCT"},
            ],
        }),
        encoding="utf-8",
    )
    inventory.write_text('{"objects":[]}', encoding="utf-8")
    (products / "sales_product.yaml").write_text(
        """
product: sales_product
owners:
  - team-sales
output_ports:
  - dataset: DS_PRODUCT
inbound: []
""".strip(),
        encoding="utf-8",
    )
    (contracts / "DS_PRODUCT.yaml").write_text(
        """
product: DS_PRODUCT
kind: provider_contract
dataset: DS_PRODUCT
owned_by: product
owners:
  - team-sales
version: 1.0.0
lifecycle: active
guarantees:
  keys:
    - columns: [ID]
      unique: true
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setenv("SQLITE_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("CONTRACTS_DIR", str(contracts))
    monkeypatch.setenv("CHECKS_DIR", str(checks))
    monkeypatch.setenv("PRODUCTS_DIR", str(products))
    monkeypatch.setenv("INVENTORY_FILE", str(inventory))
    monkeypatch.setenv("LINEAGE_FILE", str(lineage))

    import services.api.deps as deps_mod
    import services.api.settings as settings_mod

    settings_mod._settings = None
    deps_mod._store_instance = None

    from services.api.main import create_app
    from services.api.deps import get_store

    client = TestClient(create_app())
    get_store().set_compliance("DS_PRODUCT", "1.0.0", "compliant", "run-1")
    return client


def test_products_list_returns_array(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    resp = client.get("/api/products")

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data == [{
        "product": "sales_product",
        "owners": ["team-sales"],
        "port_count": 1,
        "own_health": "pass",
        "upstream_risk_count": 0,
        "finding_count": 0,
        "lifecycle": "active",
    }]


def test_product_detail_returns_full_shape(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    resp = client.get("/api/products/sales_product")

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["product"] == "sales_product"
    assert data["own_health"] == "pass"
    assert data["ports"][0]["dataset"] == "DS_PRODUCT"
    assert data["interior"][0]["id"] == "CORE_ORDERS"
    assert data["findings"] == []
    assert data["subgraph"]["nodes"]
    assert data["subgraph"]["edges"]


def test_product_detail_preview_keeps_multi_hop_upstream_context(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    (tmp_path / "products" / "upstream_product.yaml").write_text(
        """
product: upstream_product
owners:
  - team-upstream
output_ports:
  - dataset: UP_PORT
inbound: []
""".strip(),
        encoding="utf-8",
    )
    (tmp_path / "lineage.json").write_text(
        json.dumps({
            "nodes": [
                {"id": "RAW", "layer": "source", "role": "source"},
                {"id": "UP_PORT", "layer": "serving", "role": "consumption"},
                {"id": "DS_PRODUCT", "layer": "serving", "role": "consumption"},
            ],
            "edges": [
                {"source": "RAW", "target": "UP_PORT"},
                {"source": "UP_PORT", "target": "DS_PRODUCT"},
            ],
        }),
        encoding="utf-8",
    )

    detail = client.get("/api/products/sales_product").json()

    assert detail["interior"] == []
    assert {node["id"] for node in detail["subgraph"]["nodes"]} == {"RAW", "UP_PORT", "DS_PRODUCT"}
    assert {(edge["source"], edge["target"]) for edge in detail["subgraph"]["edges"]} == {
        ("RAW", "UP_PORT"),
        ("UP_PORT", "DS_PRODUCT"),
    }


def test_products_prefer_certified_active_snapshot_over_working_draft(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    contracts_dir = tmp_path / "contracts"
    (contracts_dir / "DS_PRODUCT.yaml").write_text(
        """
product: DS_PRODUCT
kind: provider_contract
dataset: DS_PRODUCT
version: 2.0.0
lifecycle: draft
guarantees: {}
""".strip(),
        encoding="utf-8",
    )
    (contracts_dir / "DS_PRODUCT.active.yml").write_text(
        """
product: DS_PRODUCT
kind: provider_contract
dataset: DS_PRODUCT
version: 1.0.0
lifecycle: active
guarantees: {}
""".strip(),
        encoding="utf-8",
    )

    listed = client.get("/api/products").json()[0]
    detail = client.get("/api/products/sales_product").json()

    assert listed["own_health"] == "pass"
    assert listed["lifecycle"] == "active"
    assert detail["ports"][0]["version"] == "1.0.0"


def test_product_port_version_is_null_when_contract_has_no_version(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    (tmp_path / "contracts" / "DS_PRODUCT.yaml").write_text(
        """
product: DS_PRODUCT
kind: provider_contract
dataset: DS_PRODUCT
lifecycle: active
guarantees: {}
""".strip(),
        encoding="utf-8",
    )

    detail = client.get("/api/products/sales_product").json()

    assert detail["ports"][0]["version"] is None


def test_unknown_product_returns_404(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    resp = client.get("/api/products/nope")

    assert resp.status_code == 404
