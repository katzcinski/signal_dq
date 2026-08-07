"""GET /api/lineage?seed=…&depth=… — Seed-Scoping des Lineage-Graphen.

Statt des kompletten Graphen liefert die API nur den Teilgraphen im
``depth``-Umkreis der Seeds (BFS in beide Richtungen über Objekt- und
Column-Edges). Ohne Seed bleibt der volle Graph erhalten.
"""
import json
from pathlib import Path


def _seed_chain(api_client):
    """A -> B -> C -> D (Objekt-Edges) plus isoliertes X."""
    import services.api.settings as sm
    lin_path = Path(sm.get_settings().lineage_file)
    lin_path.write_text(json.dumps({
        "nodes": [{"id": n} for n in ("A", "B", "C", "D", "X")],
        "edges": [
            {"id": "e1", "source": "A", "target": "B"},
            {"id": "e2", "source": "B", "target": "C"},
            {"id": "e3", "source": "C", "target": "D"},
        ],
        "columnEdges": [],
    }), encoding="utf-8")


def _ids(resp):
    return {n["id"] for n in resp.json()["nodes"]}


def test_no_seed_returns_full_graph(api_client):
    _seed_chain(api_client)
    resp = api_client.get("/api/lineage")
    assert resp.status_code == 200
    assert _ids(resp) == {"A", "B", "C", "D", "X"}


def test_seed_depth_one_keeps_direct_neighbours(api_client):
    _seed_chain(api_client)
    resp = api_client.get("/api/lineage", params={"seed": "B", "depth": 1})
    assert resp.status_code == 200
    # B plus die unmittelbaren Nachbarn A und C — nicht D, nicht das isolierte X.
    assert _ids(resp) == {"A", "B", "C"}


def test_seed_depth_two_reaches_further(api_client):
    _seed_chain(api_client)
    resp = api_client.get("/api/lineage", params={"seed": "B", "depth": 2})
    assert _ids(resp) == {"A", "B", "C", "D"}


def test_seed_edges_are_closed_to_subgraph(api_client):
    _seed_chain(api_client)
    resp = api_client.get("/api/lineage", params={"seed": "A", "depth": 1})
    body = resp.json()
    assert _ids(resp) == {"A", "B"}
    # Nur Kanten, deren beide Enden im Teilgraphen liegen.
    for e in body["edges"]:
        assert e["source"] in {"A", "B"} and e["target"] in {"A", "B"}


def test_multiple_seeds_union(api_client):
    _seed_chain(api_client)
    resp = api_client.get("/api/lineage", params=[("seed", "A"), ("seed", "D"), ("depth", 0)])
    # depth=0 → nur die Seeds selbst.
    assert _ids(resp) == {"A", "D"}


def test_isolated_seed_returns_itself(api_client):
    _seed_chain(api_client)
    resp = api_client.get("/api/lineage", params={"seed": "X", "depth": 3})
    assert _ids(resp) == {"X"}
    assert resp.json()["edges"] == []
