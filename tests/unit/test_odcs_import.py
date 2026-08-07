"""E1 — ODCS-3.1-Import (Entropy authort → Signal erzwingt).

Kernnachweise: (1) Round-Trip to_odcs→from_odcs rekonstruiert die Garantien,
(2) der Import ist SQL-frei und besteht validate_contract (G1), (3) nicht
abbildbare Regeln werden ehrlich in `dropped` berichtet, (4) unsichere
Identifier werden nie geraten.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "packages"))

from dq_core.contract.odcs_export import to_odcs
from dq_core.contract.odcs_import import from_odcs
from dq_core.contract.validator import validate_contract


def _full_contract() -> dict:
    return {
        "product": "DS_SALES_ORDERS",
        "kind": "consumer_contract",
        "dataset": "DS_SALES_ORDERS",
        "owned_by": "product",
        "owners": ["grp:data-platform"],
        "version": "1.0.0",
        "lifecycle": "active",
        "description": "Sales order fact table",
        "guarantees": {
            "schema": {"columns": ["ORDER_ID", "CUSTOMER_ID", "NET_AMOUNT", "ORDER_DATE"], "mode": "closed"},
            "keys": [{"columns": ["ORDER_ID"], "unique": True, "severity": "critical"}],
            "referential": [{"fk": ["CUSTOMER_ID"], "parent": "DS_CUSTOMERS",
                             "parent_key": ["CUSTOMER_ID"], "severity": "fail"}],
            "freshness": {"column": "ORDER_DATE", "max_age": "PT26H", "severity": "warn"},
            "volume": {"min_rows": 1000, "severity": "warn"},
            "completeness": [{"column": "NET_AMOUNT", "min_pct": 99.5, "severity": "warn"}],
            "not_null": [{"columns": ["ORDER_ID", "CUSTOMER_ID"], "severity": "fail"}],
        },
    }


def test_roundtrip_reconstructs_guarantees():
    odcs = to_odcs(_full_contract())
    result = from_odcs(odcs)
    c = result.contract
    g = c["guarantees"]

    assert c["product"] == "DS_SALES_ORDERS"
    assert c["kind"] == "consumer_contract"
    assert c["owned_by"] == "product"
    assert c["owners"] == ["grp:data-platform"]
    assert c["version"] == "1.0.0"
    # Import ist immer ein Draft — Zertifizierung ist ein bewusster Akt.
    assert c["lifecycle"] == "draft"

    assert g["schema"]["columns"] == ["ORDER_ID", "CUSTOMER_ID", "NET_AMOUNT", "ORDER_DATE"]
    assert g["schema"]["mode"] == "closed"
    assert g["keys"] == [{"columns": ["ORDER_ID"], "unique": True}]
    assert {"columns": ["ORDER_ID", "CUSTOMER_ID"]} in g["not_null"]
    assert g["completeness"] == [{"column": "NET_AMOUNT", "min_pct": 99.5}]
    assert g["referential"][0]["fk"] == ["CUSTOMER_ID"]
    assert g["referential"][0]["parent"] == "DS_CUSTOMERS"
    assert g["freshness"] == {"column": "ORDER_DATE", "max_age": "PT26H"}
    assert g["volume"] == {"min_rows": 1000}


def test_import_is_sql_free_and_valid():
    odcs = to_odcs(_full_contract())
    result = from_odcs(odcs)
    # G1: the reconstructed contract must pass the validator with zero errors.
    assert validate_contract(result.contract) == []


def test_quality_rule_with_sql_is_dropped_not_imported():
    odcs = to_odcs(_full_contract())
    # Ein Marktplatz-Contract mit handgeschriebener SodaCL/SQL-Regel:
    odcs["schema"][0]["properties"][0].setdefault("quality", []).append(
        {"type": "sql", "engine": "soda", "implementation": "SELECT count(*) FROM t WHERE x < 0"}
    )
    result = from_odcs(odcs)
    # Kein SQL im Contract — die Regel landet in dropped, nie in guarantees.
    assert any("dropped" in d.lower() or "no sql-free" in d.lower() for d in result.dropped)
    assert validate_contract(result.contract) == []


def test_unsafe_identifier_rejected():
    with pytest.raises(ValueError):
        from_odcs({"id": "order-id", "name": "order-id", "schema": [{"name": "t", "properties": []}]})


def test_internal_gate_kind_is_corrected():
    odcs = to_odcs(_full_contract())
    odcs["customProperties"] = [{"property": "signal_kind", "value": "internal_gate"}]
    result = from_odcs(odcs)
    # ODCS an einer Parteigrenze kann kein internes Gate sein.
    assert result.contract["kind"] == "consumer_contract"
    assert any("internal_gate" in w for w in result.warnings)
