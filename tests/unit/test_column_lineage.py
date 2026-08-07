"""Column-level lineage chain (O3): SQL parser + CSN reconstructor + builder.

Ported from the Meridian (datasphere-tools) inventory engine. These tests
exercise the chain against fixtures only — no DB, no live Datasphere.
"""
import pytest

from dq_core.lineage._sql_column_parser import extract_sql_column_lineage, HAS_SQLGLOT
from dq_core.lineage._csn_reconstructor import extract_query_details, build_sql_reconstruction
from dq_core.lineage._column_lineage import (
    build_column_lineage,
    build_column_indexes,
)


# --- CSN reconstructor (pure stdlib, no sqlglot) ---

def _orders_csn_obj():
    """A small graphical-view CSN: SELECT a passthrough + an aggregate."""
    return {
        "query": {
            "SELECT": {
                "from": {"ref": ["Sales_Orders"], "as": "o"},
                "columns": [
                    {"ref": ["o", "OrderID"], "as": "OrderID"},
                    {"func": "SUM", "args": [{"ref": ["o", "Amount"]}], "as": "TotalAmount"},
                ],
            }
        }
    }


def test_csn_extract_query_details_maps_alias_to_source():
    details = extract_query_details(_orders_csn_obj())
    assert details["aliasMap"] == {"o": "Sales_Orders"}

    by_out = {p["output"]: p for p in details["projectionLineage"]}
    assert by_out["OrderID"]["allSourceRefs"] == ["Sales_Orders.OrderID"]
    assert by_out["OrderID"]["expression"] == ""  # direct passthrough
    assert by_out["TotalAmount"]["allSourceRefs"] == ["Sales_Orders.Amount"]
    assert by_out["TotalAmount"]["expression"]  # aggregate -> rendered expression


def test_csn_build_sql_reconstruction_emits_create_view():
    recon = build_sql_reconstruction("v_OrderSummary", _orders_csn_obj())
    assert recon["available"] is True
    assert recon["status"] in ("ok", "partial")
    assert recon["sql"].startswith('CREATE VIEW "v_OrderSummary"')


def test_csn_empty_query_is_safe():
    details = extract_query_details({"query": {}})
    assert details == {"joinDetails": [], "projectionLineage": [], "aliasMap": {}}


# --- Cross-object column lineage via CSN projection (no sqlglot) ---

def _orders_inventory():
    details = extract_query_details(_orders_csn_obj())
    return [
        {
            "technicalName": "v_OrderSummary",
            "objectType": "views",
            "columnCount": 2,
            "csnProjection": {
                "projectionLineage": details["projectionLineage"],
                "aliasMap": details["aliasMap"],
                "querySources": ["Sales_Orders"],
            },
        },
        {
            "technicalName": "Sales_Orders",
            "objectType": "local-tables",
            "columns": [{"name": "OrderID"}, {"name": "Amount"}],
        },
    ]


def test_build_column_lineage_from_csn():
    result = build_column_lineage(_orders_inventory())
    edges = {
        (e.source_object, e.source_column, e.target_object, e.target_column): e.edge_type
        for e in result.edges
    }
    assert edges[("Sales_Orders", "OrderID", "v_OrderSummary", "OrderID")] == "direct"
    assert edges[("Sales_Orders", "Amount", "v_OrderSummary", "TotalAmount")] == "computed"

    # The view's 2 columns are mapped; the Sales_Orders leaf's 2 columns have
    # no upstream, so overall coverage is diluted by source leaves...
    assert result.coverage["mapped"] == 2
    assert result.coverage["unmapped"] == 2
    assert result.coverage["ratio"] == 0.5
    assert "Sales_Orders" in result.unmapped_objects
    # ...which is why the derived-only ratio is the fair headline: every
    # column of the (derived) view object is mapped.
    assert result.coverage["derived"]["ratio"] == 1.0


def test_serialize_and_indexes():
    result = build_column_lineage(_orders_inventory())
    serialized = result.serialize()
    assert serialized["columnEdgeMeta"]["totalEdges"] == 2
    assert len(serialized["columnEdges"]) == 2

    idx = build_column_indexes(result)
    up = idx["v_OrderSummary"]["TotalAmount"]["upstream"]
    assert up == [{
        "object": "Sales_Orders",
        "column": "Amount",
        "edgeType": "computed",
        "expression": up[0]["expression"],
    }]
    down = idx["Sales_Orders"]["OrderID"]["downstream"]
    assert {"object": "v_OrderSummary", "column": "OrderID", "edgeType": "direct"} in down


def test_unmapped_object_without_projection_or_sql():
    inventory = [
        {"technicalName": "v_opaque", "objectType": "views", "columnCount": 3},
    ]
    result = build_column_lineage(inventory)
    assert result.edges == []
    assert result.coverage["unmapped"] == 3
    assert "v_opaque" in result.unmapped_objects


# --- SQL parser path (requires sqlglot) ---

skip_no_sqlglot = pytest.mark.skipif(not HAS_SQLGLOT, reason="sqlglot not installed")


@skip_no_sqlglot
def test_sql_parser_direct_literal_and_expression():
    sql = (
        "SELECT o.OrderID AS OrderID, o.Qty * o.Price AS Total, 'NEW' AS Status "
        "FROM Sales_Orders AS o"
    )
    by_out = {e["output"]: e for e in extract_sql_column_lineage(sql, "v_t", ["Sales_Orders"])}

    assert by_out["OrderID"]["sourceRef"] == "Sales_Orders.OrderID"
    assert by_out["OrderID"]["expression"] == ""

    assert by_out["Total"]["expression"]  # arithmetic -> expression
    assert set(by_out["Total"]["allSourceRefs"]) == {"Sales_Orders.Qty", "Sales_Orders.Price"}

    assert by_out["Status"]["sourceRef"] == ""  # literal -> no source


@skip_no_sqlglot
def test_sql_parser_star_is_unsupported():
    entries = extract_sql_column_lineage("SELECT * FROM t", "v", ["t"])
    assert len(entries) == 1
    assert entries[0]["unsupported"] is True


@skip_no_sqlglot
def test_build_column_lineage_from_sql_fallback():
    inventory = [
        {
            "technicalName": "v_sql",
            "objectType": "views",
            "columnCount": 1,
            "sql": "SELECT t.A AS A FROM Src AS t",
            "lineageSources": ["Src"],
        },
    ]
    result = build_column_lineage(inventory)
    assert any(
        e.source_object == "Src" and e.source_column == "A"
        and e.target_object == "v_sql" and e.target_column == "A"
        for e in result.edges
    )
