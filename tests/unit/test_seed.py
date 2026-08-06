"""Unit tests for contract auto-seeder (seed_from_inventory)."""
from __future__ import annotations

import pytest

from dq_core.contract.seed import _assoc_parent_name, _seed_referential, seed_from_inventory


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _obj(
    *,
    name: str = "FACT_ORDERS",
    columns: list[str] | None = None,
    key_columns: list[str] | None = None,
    csn_columns: list[dict] | None = None,
    assoc_manifest: list[dict] | None = None,
) -> dict:
    obj: dict = {
        "technicalName": name,
        "columns": [{"name": c} for c in (columns or [])],
    }
    csn: dict = {}
    if key_columns is not None:
        csn["keyColumns"] = key_columns
    if csn_columns is not None:
        csn["columns"] = csn_columns
    if assoc_manifest is not None:
        csn["associationManifest"] = assoc_manifest
    if csn:
        obj["csnProjection"] = csn
    return obj


# ---------------------------------------------------------------------------
# _assoc_parent_name
# ---------------------------------------------------------------------------

def test_assoc_parent_name_plain_string():
    assert _assoc_parent_name("DIM_CUSTOMER") == "DIM_CUSTOMER"


def test_assoc_parent_name_qualified():
    assert _assoc_parent_name("SPACE.DIM_CUSTOMER") == "DIM_CUSTOMER"


def test_assoc_parent_name_enum_ref():
    assert _assoc_parent_name({"#": "DIM_CUSTOMER"}) == "DIM_CUSTOMER"


def test_assoc_parent_name_empty():
    assert _assoc_parent_name(None) == ""
    assert _assoc_parent_name("") == ""
    assert _assoc_parent_name({}) == ""


# ---------------------------------------------------------------------------
# _seed_referential
# ---------------------------------------------------------------------------

def _manifest_entry(
    *,
    fk_cols: list[str],
    target: str,
    target_key: list[str],
    name: str = "toCustomer",
) -> dict:
    return {
        "name": name,
        "target": target,
        "targetKeyColumns": target_key,
        "foreignKeyColumns": fk_cols,
    }


def test_seed_referential_basic():
    csn = {
        "associationManifest": [
            _manifest_entry(fk_cols=["CUSTOMER_ID"], target="DIM_CUSTOMER", target_key=["CUSTOMER_ID"]),
        ]
    }
    result = _seed_referential(csn, "FACT_ORDERS")
    assert len(result) == 1
    assert result[0]["fk"] == ["CUSTOMER_ID"]
    assert result[0]["parent"] == "DIM_CUSTOMER"
    assert result[0]["parent_key"] == ["CUSTOMER_ID"]
    assert result[0]["proposed"] is True
    assert result[0]["severity"] == "warn"


def test_seed_referential_qualified_target():
    csn = {
        "associationManifest": [
            _manifest_entry(fk_cols=["MAT_ID"], target="SPACE.DIM_MATERIAL", target_key=["MAT_ID"]),
        ]
    }
    result = _seed_referential(csn, "FACT_ORDERS")
    assert result[0]["parent"] == "DIM_MATERIAL"


def test_seed_referential_skips_missing_fk_cols():
    csn = {
        "associationManifest": [
            {"name": "toX", "target": "DIM_X", "targetKeyColumns": ["ID"], "foreignKeyColumns": []},
        ]
    }
    assert _seed_referential(csn, "FACT_ORDERS") == []


def test_seed_referential_skips_missing_target_key():
    csn = {
        "associationManifest": [
            {"name": "toX", "target": "DIM_X", "targetKeyColumns": [], "foreignKeyColumns": ["X_ID"]},
        ]
    }
    assert _seed_referential(csn, "FACT_ORDERS") == []


def test_seed_referential_skips_self():
    csn = {
        "associationManifest": [
            _manifest_entry(fk_cols=["PARENT_ID"], target="FACT_ORDERS", target_key=["ORDER_ID"]),
        ]
    }
    assert _seed_referential(csn, "FACT_ORDERS") == []


def test_seed_referential_empty_csn():
    assert _seed_referential({}, "FACT_ORDERS") == []
    assert _seed_referential({"associationManifest": []}, "FACT_ORDERS") == []


def test_seed_referential_multiple():
    csn = {
        "associationManifest": [
            _manifest_entry(fk_cols=["CUSTOMER_ID"], target="DIM_CUSTOMER", target_key=["CUSTOMER_ID"], name="toCustomer"),
            _manifest_entry(fk_cols=["PRODUCT_ID"], target="DIM_PRODUCT", target_key=["PRODUCT_ID"], name="toProduct"),
        ]
    }
    result = _seed_referential(csn, "FACT_ORDERS")
    assert len(result) == 2
    parents = {r["parent"] for r in result}
    assert parents == {"DIM_CUSTOMER", "DIM_PRODUCT"}


# ---------------------------------------------------------------------------
# seed_from_inventory — key detection tiers
# ---------------------------------------------------------------------------

def test_keys_from_csn_explicit():
    """Tier 1: CSN keyColumns used directly, no proposed flag."""
    obj = _obj(
        columns=["ORDER_ID", "AMOUNT"],
        key_columns=["ORDER_ID"],
    )
    draft = seed_from_inventory(obj)
    keys = draft["guarantees"]["keys"]
    assert len(keys) == 1
    assert keys[0]["columns"] == ["ORDER_ID"]
    assert "proposed" not in keys[0]


def test_keys_fallback_name_plus_notnull():
    """Tier 2: name heuristic confirmed by CSN notNull — proposed, filtered list."""
    obj = _obj(
        columns=["ORDER_ID", "CUSTOMER_ID", "NET_AMOUNT"],
        csn_columns=[
            {"name": "ORDER_ID", "notNull": True},
            {"name": "CUSTOMER_ID", "notNull": False},
            {"name": "NET_AMOUNT", "notNull": False},
        ],
    )
    draft = seed_from_inventory(obj)
    keys = draft["guarantees"]["keys"]
    assert keys[0]["columns"] == ["ORDER_ID"]  # CUSTOMER_ID filtered out (not notNull)
    assert keys[0]["proposed"] is True


def test_keys_fallback_name_only_when_no_csn_notnull():
    """Tier 3: no CSN notNull info → all name candidates proposed."""
    obj = _obj(columns=["ORDER_ID", "CUSTOMER_ID", "NET_AMOUNT"])
    draft = seed_from_inventory(obj)
    keys = draft["guarantees"]["keys"]
    assert set(keys[0]["columns"]) == {"ORDER_ID", "CUSTOMER_ID"}
    assert keys[0]["proposed"] is True


def test_keys_name_heuristic_unfiltered_when_notnull_has_no_overlap():
    """If CSN notNull exists but no candidate overlaps, fall through to all candidates."""
    obj = _obj(
        columns=["ORDER_ID", "CUSTOMER_ID", "STATUS"],
        csn_columns=[
            {"name": "STATUS", "notNull": True},  # matches notNull but not name heuristic
            {"name": "ORDER_ID", "notNull": False},
            {"name": "CUSTOMER_ID", "notNull": False},
        ],
    )
    draft = seed_from_inventory(obj)
    keys = draft["guarantees"]["keys"]
    # confirmed is empty (ORDER_ID/CUSTOMER_ID not notNull), falls back to all candidates
    assert set(keys[0]["columns"]) == {"ORDER_ID", "CUSTOMER_ID"}
    assert keys[0]["proposed"] is True


def test_keys_omitted_when_no_candidates():
    obj = _obj(columns=["NET_AMOUNT", "STATUS", "DESCRIPTION"])
    draft = seed_from_inventory(obj)
    assert "keys" not in draft["guarantees"]


# ---------------------------------------------------------------------------
# seed_from_inventory — referential guarantees
# ---------------------------------------------------------------------------

def test_referential_seeded_from_csn():
    obj = _obj(
        name="FACT_ORDERS",
        columns=["ORDER_ID", "CUSTOMER_ID"],
        key_columns=["ORDER_ID"],
        assoc_manifest=[
            _manifest_entry(fk_cols=["CUSTOMER_ID"], target="DIM_CUSTOMER", target_key=["CUSTOMER_ID"]),
        ],
    )
    draft = seed_from_inventory(obj)
    refs = draft["guarantees"].get("referential", [])
    assert len(refs) == 1
    assert refs[0]["fk"] == ["CUSTOMER_ID"]
    assert refs[0]["parent"] == "DIM_CUSTOMER"
    assert refs[0]["proposed"] is True


def test_referential_absent_when_no_assoc():
    obj = _obj(columns=["ORDER_ID", "CUSTOMER_ID"], key_columns=["ORDER_ID"])
    draft = seed_from_inventory(obj)
    assert "referential" not in draft["guarantees"]


# ---------------------------------------------------------------------------
# seed_from_inventory — output contract shape
# ---------------------------------------------------------------------------

def test_output_shape():
    obj = _obj(name="FACT_ORDERS", columns=["ORDER_ID", "AMOUNT"], key_columns=["ORDER_ID"])
    draft = seed_from_inventory(obj)
    assert draft["product"] == "FACT_ORDERS"
    assert draft["lifecycle"] == "draft"
    assert draft["version"] == "0.1.0"
    assert draft["kind"] == "internal_gate"
    assert "schema" in draft["guarantees"]
    assert "volume" in draft["guarantees"]


def test_no_sql_in_output():
    """G1: seed must never emit SQL."""
    obj = _obj(columns=["ORDER_ID", "AMOUNT"])
    draft = seed_from_inventory(obj)
    text = str(draft)
    for kw in ("SELECT", "WHERE", "FROM", "CENTRAL"):
        assert kw not in text
