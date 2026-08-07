"""Inventory-object assembly + object-level lineage graph (Task C).

Pure transforms ported from the Meridian inventory engine. Tests run on
SYNTHETIC CSN fixtures only — no DB, no live Datasphere, no customer data.
The fixtures use made-up names (``Sales_Orders``, ``r_Customers``, ...).
"""

from __future__ import annotations

from dq_core.lineage.inventory import (
    build_inventory_object,
    build_lineage_graph,
)
from dq_core.lineage._semantics import (
    NamingModel,
    QUNIS_DEFAULT,
    parse_external_source,
    sql_fingerprint,
)
from dq_core.lineage._column_lineage import build_column_lineage


# ---------------------------------------------------------------------------
# Synthetic CSN fixtures
# ---------------------------------------------------------------------------

def _order_summary_csn() -> dict:
    """Graphical view: passthrough + aggregate over a single source."""
    return {
        "definitions": {
            "s_OrderSummary_fact_v": {
                "kind": "entity",
                "elements": {
                    "OrderID": {"type": "cds.Integer", "key": True,
                                "@EndUserText.label": "Order ID"},
                    "TotalAmount": {"type": "cds.Decimal",
                                    "@Aggregation.default": {"#": "SUM"}},
                },
                "query": {
                    "SELECT": {
                        "from": {"ref": ["Sales_Orders"], "as": "o"},
                        "columns": [
                            {"ref": ["o", "OrderID"], "as": "OrderID"},
                            {"func": "SUM", "args": [{"ref": ["o", "Amount"]}],
                             "as": "TotalAmount"},
                        ],
                    }
                },
            }
        }
    }


def _joined_view_csn() -> dict:
    """View joining a local table and an external-space source."""
    return {
        "definitions": {
            "ic_OrderEnriched": {
                "kind": "entity",
                "elements": {
                    "OrderID": {"type": "cds.Integer", "key": True},
                    "CustName": {"type": "cds.String"},
                },
                "query": {
                    "SELECT": {
                        "from": {
                            "join": "left",
                            "args": [
                                {"ref": ["Sales_Orders"], "as": "o"},
                                {"ref": ["Ext.Customers"], "as": "c"},
                            ],
                            "on": [
                                {"ref": ["o", "CustID"]}, "=", {"ref": ["c", "ID"]},
                            ],
                        },
                        "columns": [
                            {"ref": ["o", "OrderID"], "as": "OrderID"},
                            {"ref": ["c", "Name"], "as": "CustName"},
                        ],
                    }
                },
            }
        }
    }


def _sales_orders_obj() -> dict:
    """A raw source table assembled as an INVOBJ (leaf, no query)."""
    return build_inventory_object(
        {
            "definitions": {
                "Sales_Orders": {
                    "kind": "entity",
                    "elements": {
                        "OrderID": {"type": "cds.Integer", "key": True},
                        "Amount": {"type": "cds.Decimal"},
                        "CustID": {"type": "cds.Integer"},
                    },
                }
            }
        },
        technical_name="Sales_Orders",
        object_type="local-tables",
        status="Deployed",
        space="DEMO",
    )


# ---------------------------------------------------------------------------
# build_inventory_object — INVOBJ shape
# ---------------------------------------------------------------------------

def test_invobj_top_level_shape():
    obj = build_inventory_object(
        _order_summary_csn(),
        technical_name="s_OrderSummary_fact_v",
        object_type="views",
        status="Deployed",
        space="DEMO",
        business_name="Order Summary",
        semantic_usage="Analytical Dataset",
    )

    # Required top-level keys from the locked schema.
    for key in (
        "space", "objectType", "kind", "technicalName", "businessName",
        "semanticUsage", "status", "columnCount", "columns", "sqlFound",
        "sqlPath", "sql", "sqlReconstruction", "sqlReconstructionAvailable",
        "sqlReconstructionStatus", "sqlReconstructionWarningCount",
        "csnProjection", "analyticModel", "dataAccessControl",
        "appliedDataAccessControls", "flowLineage", "lineageEdges",
        "lineageSources", "error", "layer", "layerCode", "role",
        "isGraphical", "sqlSize", "sqlFingerprintExact", "confidence",
    ):
        assert key in obj, f"missing INVOBJ key: {key}"

    assert obj["technicalName"] == "s_OrderSummary_fact_v"
    assert obj["objectType"] == "views"
    assert obj["columnCount"] == 2
    assert {c["name"] for c in obj["columns"]} == {"OrderID", "TotalAmount"}

    # Graphical view with no raw SQL → reconstruction kicks in.
    assert obj["sqlFound"] is False
    assert obj["isGraphical"] is True
    assert obj["sqlReconstructionAvailable"] is True
    assert obj["sqlReconstruction"]["sql"].startswith(
        'CREATE VIEW "s_OrderSummary_fact_v"'
    )


def test_invobj_csn_projection_present():
    obj = build_inventory_object(
        _order_summary_csn(),
        technical_name="s_OrderSummary_fact_v",
        object_type="views",
        status="Deployed",
        space="DEMO",
    )
    csn = obj["csnProjection"]
    # aliasMap + projectionLineage come straight from extract_query_details.
    assert csn["aliasMap"] == {"o": "Sales_Orders"}
    assert csn["querySources"] == ["Sales_Orders"]
    assert csn["keyColumns"] == ["OrderID"]

    by_out = {p["output"]: p for p in csn["projectionLineage"]}
    assert by_out["OrderID"]["allSourceRefs"] == ["Sales_Orders.OrderID"]
    assert by_out["OrderID"]["expression"] == ""           # direct passthrough
    assert by_out["TotalAmount"]["allSourceRefs"] == ["Sales_Orders.Amount"]
    assert by_out["TotalAmount"]["expression"]              # aggregate -> expr

    # sqlReconstructionStatus mirrors the reconstruction object.
    assert csn["sqlReconstructionStatus"] == obj["sqlReconstruction"]["status"]


def test_invobj_semantics_stamp():
    obj = build_inventory_object(
        _order_summary_csn(),
        technical_name="s_OrderSummary_fact_v",
        object_type="views",
        status="Deployed",
        space="DEMO",
        semantic_usage="Fact",
    )
    # s_ prefix -> serving layer; _fact(_v)? suffix -> fact role.
    assert (obj["layer"], obj["layerCode"]) == ("serving", "s")
    assert obj["role"] == "fact"
    assert 0.0 <= obj["confidence"] <= 1.0
    assert obj["confidence"] > 0.8  # prefix + suffix + semanticUsage all agree


def test_invobj_unknown_prefix_is_tolerated():
    # Uppercase legacy/tenant prefix -> unknown layer (expected per Meridian).
    obj = build_inventory_object(
        {"definitions": {"B_Legacy": {"kind": "entity", "elements": {}}}},
        technical_name="B_Legacy",
        object_type="local-tables",
        status="Deployed",
        space="DEMO",
    )
    assert obj["layer"] == "unknown"
    assert obj["layerCode"] == "?"


def test_invobj_safe_on_empty_def():
    obj = build_inventory_object(
        {},
        technical_name="v_empty",
        object_type="views",
        status="",
        space="DEMO",
    )
    assert obj["columnCount"] == 0
    assert obj["csnProjection"]["projectionLineage"] == []
    assert obj["lineageEdges"] == []
    assert obj["sqlReconstruction"]["status"] == "not_applicable"


def test_invobj_with_raw_sql_skips_reconstruction():
    obj = build_inventory_object(
        {"definitions": {"v_raw": {"kind": "entity", "elements": {
            "A": {"type": "cds.String"}}}}},
        technical_name="v_raw",
        object_type="views",
        status="Deployed",
        space="DEMO",
        sql="SELECT a AS A FROM Src",
    )
    assert obj["sqlFound"] is True
    assert obj["isGraphical"] is False
    assert obj["sqlReconstruction"]["status"] == "not_applicable"
    assert obj["sqlFingerprintExact"] == sql_fingerprint("SELECT a AS A FROM Src")


# ---------------------------------------------------------------------------
# build_inventory_object — lineage edges
# ---------------------------------------------------------------------------

def test_invobj_lineage_edges_from_join():
    obj = build_inventory_object(
        _joined_view_csn(),
        technical_name="ic_OrderEnriched",
        object_type="views",
        status="Deployed",
        space="DEMO",
    )
    names = obj["lineageSources"]
    assert "Sales_Orders" in names
    assert "Ext.Customers" in names


# ---------------------------------------------------------------------------
# build_lineage_graph
# ---------------------------------------------------------------------------

def _two_object_inventory() -> list[dict]:
    view = build_inventory_object(
        _order_summary_csn(),
        technical_name="s_OrderSummary_fact_v",
        object_type="views",
        status="Deployed",
        space="DEMO",
        business_name="Order Summary",
    )
    return [view, _sales_orders_obj()]


def test_lineage_graph_nodes_edges_adjacency_upstream():
    graph = build_lineage_graph(_two_object_inventory())

    assert graph["meta"]["schemaVersion"] >= 1
    node_ids = {n["id"] for n in graph["nodes"]}
    assert {"s_OrderSummary_fact_v", "Sales_Orders"} <= node_ids

    # Node carries the locked node fields.
    view_node = next(n for n in graph["nodes"] if n["id"] == "s_OrderSummary_fact_v")
    for key in (
        "id", "businessName", "type", "status", "space", "system",
        "layer", "layerCode", "role", "confidence", "columns", "columnCount",
    ):
        assert key in view_node
    assert view_node["layer"] == "serving"
    assert sorted(view_node["columns"]) == ["OrderID", "TotalAmount"]

    # Edge: Sales_Orders -> s_OrderSummary_fact_v, local & in-space.
    edge = next(
        e for e in graph["edges"]
        if e["source"] == "Sales_Orders" and e["target"] == "s_OrderSummary_fact_v"
    )
    assert edge["sourceInSpace"] is True
    assert edge["sourceScope"] == "local"
    assert edge["confidence"] == 1.0

    assert "s_OrderSummary_fact_v" in graph["adjacency"]["Sales_Orders"]
    assert "Sales_Orders" in graph["upstream"]["s_OrderSummary_fact_v"]


def test_lineage_graph_external_space_edge_not_in_space():
    view = build_inventory_object(
        _joined_view_csn(),
        technical_name="ic_OrderEnriched",
        object_type="views",
        status="Deployed",
        space="DEMO",
    )
    graph = build_lineage_graph([view, _sales_orders_obj()])
    ext_edge = next(
        e for e in graph["edges"] if e["source"] == "Ext.Customers"
    )
    assert ext_edge["sourceInSpace"] is False
    assert ext_edge["sourceScope"] == "external_space"
    assert ext_edge["externalSpace"] == "Ext"


def test_lineage_graph_external_system_node_created():
    # A flow-style edge referencing an S4 external system source.
    obj = {
        "technicalName": "tf_Load",
        "objectType": "transformation-flows",
        "businessName": "",
        "status": "Deployed",
        "space": "DEMO",
        "columns": [],
        "columnCount": 0,
        "layer": "unknown",
        "layerCode": "?",
        "role": "flow",
        "confidence": 0.5,
        "lineageEdges": [{"name": "S4:SALESDOC", "type": "select"}],
        "lineageSources": ["S4:SALESDOC"],
    }
    graph = build_lineage_graph([obj])
    ext = next(n for n in graph["nodes"] if n["id"] == "S4:SALESDOC")
    assert ext["type"] == "external"
    assert ext["system"] == "S4"
    assert ext["layer"] == "external"
    edge = next(e for e in graph["edges"] if e["source"] == "S4:SALESDOC")
    assert edge["sourceScope"] == "external_system"


def test_lineage_graph_resolves_space_qualified_local_ref():
    # SQL emitted "DEMO.Sales_Orders" — same space qualifier should resolve
    # back to the bare technical name node.
    view = {
        "technicalName": "v_uses_qualified",
        "objectType": "views",
        "businessName": "",
        "status": "Deployed",
        "space": "DEMO",
        "columns": [],
        "columnCount": 0,
        "layer": "unknown",
        "layerCode": "?",
        "role": "other",
        "confidence": 0.5,
        "lineageEdges": [{"name": "DEMO.Sales_Orders", "type": "select"}],
        "lineageSources": ["DEMO.Sales_Orders"],
    }
    graph = build_lineage_graph([view, _sales_orders_obj()])
    edge = next(e for e in graph["edges"] if e["target"] == "v_uses_qualified")
    assert edge["source"] == "Sales_Orders"          # qualifier stripped
    assert edge["sourceInSpace"] is True
    assert edge["sourceReference"] == "DEMO.Sales_Orders"


# ---------------------------------------------------------------------------
# End-to-end: build_column_lineage over the assembled objects
# ---------------------------------------------------------------------------

def test_column_lineage_over_assembled_objects():
    inventory = _two_object_inventory()
    result = build_column_lineage(inventory)
    edges = {
        (e.source_object, e.source_column, e.target_object, e.target_column): e.edge_type
        for e in result.edges
    }
    assert edges[("Sales_Orders", "OrderID", "s_OrderSummary_fact_v", "OrderID")] == "direct"
    assert edges[("Sales_Orders", "Amount", "s_OrderSummary_fact_v", "TotalAmount")] == "computed"

    serialized = result.serialize()
    assert serialized["columnEdgeMeta"]["totalEdges"] >= 2
    assert len(serialized["columnEdges"]) >= 2
    # Derived-only coverage: every column of the view object is mapped.
    assert result.coverage["derived"]["ratio"] == 1.0


# ---------------------------------------------------------------------------
# Custom naming model + parse_external_source classification
# ---------------------------------------------------------------------------

def test_custom_naming_model_remaps_prefix():
    from dq_core.lineage._semantics import LayerRule

    model = NamingModel(
        name="Acme",
        layers=(LayerRule(prefix="stg_", layer="raw", code="stg"),),
    )
    obj = build_inventory_object(
        {"definitions": {"stg_Orders": {"kind": "entity", "elements": {}}}},
        technical_name="stg_Orders",
        object_type="local-tables",
        status="Deployed",
        space="DEMO",
        naming=model,
    )
    assert (obj["layer"], obj["layerCode"]) == ("raw", "stg")
    # The default model would NOT match stg_ -> stays unknown.
    assert QUNIS_DEFAULT.match_layer("stg_Orders") == ("unknown", "?")


def test_parse_external_source_scopes():
    assert parse_external_source("x", in_space=True)["sourceScope"] == "local"
    assert parse_external_source("S4:DOC", in_space=False)["sourceScope"] == "external_system"
    assert parse_external_source("Ext.Foo", in_space=False)["sourceScope"] == "external_space"
    assert parse_external_source("r_RealName", in_space=False)["sourceScope"] == "external_raw"
    assert parse_external_source("x", in_space=False)["sourceScope"] == "parser_noise"
