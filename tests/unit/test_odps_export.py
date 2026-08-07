"""E3 — ODPS-1.0-Export des Product-Manifests (Einweg-Derivat, flagged)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "packages"))

from dq_core.product.model import Product, OutputPort, InboundDep
from dq_core.product.odps_export import to_odps, UNVERIFIED_MARK


def _product() -> Product:
    return Product(
        product="SALES_DOMAIN",
        owners=["grp:sales-eng"],
        output_ports=[OutputPort(dataset="DS_SALES_ORDERS"), OutputPort(dataset="DS_SALES_RAW")],
        inbound=[InboundDep(product="CRM_DOMAIN", version="2.1.0")],
    )


def test_basic_shape():
    doc = to_odps(_product())
    assert doc["apiVersion"] == "1.0"
    assert doc["kind"] == "DataProduct"
    assert doc["name"] == "SALES_DOMAIN"
    assert doc["info"]["owner"] == "grp:sales-eng"
    assert {p["name"] for p in doc["outputPorts"]} == {"DS_SALES_ORDERS", "DS_SALES_RAW"}
    assert doc["inputPorts"][0]["version"] == "2.1.0"


def test_unverified_by_default():
    doc = to_odps(_product())
    assert doc["x-signal-validation"] == UNVERIFIED_MARK
    assert any(cp["key"] == "signal:validation" for cp in doc["customProperties"])


def test_verified_flag_removes_warning():
    doc = to_odps(_product(), verified=True)
    assert doc["x-signal-validation"] == "verified"
    assert not any(cp["key"] == "signal:validation" for cp in doc["customProperties"])


def test_governed_flag_from_contract_lookup():
    lookup = {
        "DS_SALES_ORDERS": {"product": "DS_SALES_ORDERS", "kind": "consumer_contract", "version": "1.0.0"},
        "DS_SALES_RAW": {"product": "DS_SALES_RAW", "kind": "internal_gate", "version": "0.1.0"},
    }
    doc = to_odps(_product(), contract_lookup=lambda ds: lookup.get(ds))
    ports = {p["name"]: p for p in doc["outputPorts"]}
    # Nur der Grenz-Contract ist ein echtes veröffentlichtes Versprechen.
    assert ports["DS_SALES_ORDERS"]["governed"] is True
    assert ports["DS_SALES_RAW"]["governed"] is False
