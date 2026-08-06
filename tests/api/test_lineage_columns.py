"""GET /api/lineage/columns — per-column lineage served from columnEdges (O3)."""
import json
from pathlib import Path


def _seed_column_edges(api_client):
    import services.api.settings as sm
    lin_path = Path(sm.get_settings().lineage_file)
    data = json.loads(lin_path.read_text(encoding="utf-8"))
    data["columnEdges"] = [
        {"source": "Sales_Orders", "sourceColumn": "OrderID", "target": "v_OrderSummary",
         "targetColumn": "OrderID", "edgeType": "direct", "expression": ""},
        {"source": "Sales_Orders", "sourceColumn": "Amount", "target": "v_OrderSummary",
         "targetColumn": "TotalAmount", "edgeType": "computed", "expression": "SUM(o.Amount)"},
    ]
    lin_path.write_text(json.dumps(data), encoding="utf-8")


def test_columns_for_object(api_client):
    _seed_column_edges(api_client)
    resp = api_client.get("/api/lineage/columns", params={"object": "v_OrderSummary"})
    assert resp.status_code == 200
    cols = resp.json()["columns"]
    assert cols["TotalAmount"]["upstream"][0]["object"] == "Sales_Orders"
    assert cols["TotalAmount"]["upstream"][0]["edgeType"] == "computed"


def test_single_column_lineage(api_client):
    _seed_column_edges(api_client)
    resp = api_client.get(
        "/api/lineage/columns", params={"object": "Sales_Orders", "column": "OrderID"}
    )
    assert resp.status_code == 200
    down = resp.json()["lineage"]["downstream"]
    assert {"object": "v_OrderSummary", "column": "OrderID", "edgeType": "direct"} in down


def test_unknown_object_returns_empty(api_client):
    _seed_column_edges(api_client)
    resp = api_client.get("/api/lineage/columns", params={"object": "nope"})
    assert resp.status_code == 200
    assert resp.json()["columns"] == {}


def _seed_impact_chain(api_client):
    """A.c1 -> B.c1 (direct) -> C.c1 (computed), plus ownership in inventory."""
    import services.api.settings as sm
    settings = sm.get_settings()
    lin_path = Path(settings.lineage_file)
    inv_path = Path(settings.inventory_file)
    lin = json.loads(lin_path.read_text(encoding="utf-8"))
    lin["columnEdges"] = [
        {"source": "A", "sourceColumn": "c1", "target": "B", "targetColumn": "c1",
         "edgeType": "direct", "expression": ""},
        {"source": "B", "sourceColumn": "c1", "target": "C", "targetColumn": "c1",
         "edgeType": "computed", "expression": "ROUND(b.c1)"},
    ]
    lin_path.write_text(json.dumps(lin), encoding="utf-8")
    inv_path.write_text(json.dumps({"objects": [
        {"technicalName": "B", "owned_by": "platform", "owners": ["team-b"]},
        {"technicalName": "C", "owned_by": "product", "owners": ["team-c"]},
    ]}), encoding="utf-8")


def test_impact_transitive_with_ownership(api_client):
    _seed_impact_chain(api_client)
    resp = api_client.get("/api/lineage/columns/impact", params={"object": "A", "column": "c1"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["totalImpacted"] == 2
    assert body["truncated"] is False
    by_obj = {r["object"]: r for r in body["impacted"]}
    assert by_obj["B"]["depth"] == 1 and by_obj["B"]["ownedBy"] == "platform"
    assert by_obj["C"]["depth"] == 2 and by_obj["C"]["edgeType"] == "computed"
    assert by_obj["C"]["owners"] == ["team-c"]


def test_impact_respects_max_depth_and_flags_truncation(api_client):
    _seed_impact_chain(api_client)
    resp = api_client.get(
        "/api/lineage/columns/impact", params={"object": "A", "column": "c1", "max_depth": 1}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["totalImpacted"] == 1  # only B at depth 1
    assert body["truncated"] is True


def test_impact_is_cycle_safe(api_client):
    import services.api.settings as sm
    lin_path = Path(sm.get_settings().lineage_file)
    lin = json.loads(lin_path.read_text(encoding="utf-8"))
    lin["columnEdges"] = [
        {"source": "A", "sourceColumn": "c", "target": "B", "targetColumn": "c",
         "edgeType": "direct", "expression": ""},
        {"source": "B", "sourceColumn": "c", "target": "A", "targetColumn": "c",
         "edgeType": "direct", "expression": ""},
    ]
    lin_path.write_text(json.dumps(lin), encoding="utf-8")
    resp = api_client.get("/api/lineage/columns/impact", params={"object": "A", "column": "c"})
    assert resp.status_code == 200
    # B reached once; A is the start (not re-listed) -> terminates.
    assert {r["object"] for r in resp.json()["impacted"]} == {"B"}


def test_graph_includes_column_edges(api_client):
    """GET /api/lineage liefert columnEdges mit (fuer das Schaltplan-Board)."""
    _seed_column_edges(api_client)
    resp = api_client.get("/api/lineage")
    assert resp.status_code == 200
    body = resp.json()
    assert "columnEdges" in body
    pairs = {
        (e["source"], e["sourceColumn"], e["target"], e["targetColumn"])
        for e in body["columnEdges"]
    }
    assert ("Sales_Orders", "Amount", "v_OrderSummary", "TotalAmount") in pairs
