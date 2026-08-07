from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parents[2] / "packages"))

from dq_core.product.model import OutputPort, Product
from dq_core.product.walk import build_port_index, clean_port_index, walk_all


def _maps(edges: list[tuple[str, str]]):
    upstream: dict[str, list[str]] = {}
    downstream: dict[str, list[str]] = {}
    for source, target in edges:
        downstream.setdefault(source, []).append(target)
        upstream.setdefault(target, []).append(source)
    return upstream, downstream


def _nodes(*ids: str) -> dict[str, dict]:
    return {node_id: {"id": node_id, "role": "other"} for node_id in ids}


def _product(name: str, owners: list[str], ports: list[str]) -> Product:
    return Product(name, owners, [OutputPort(port) for port in ports], [])


def _aggregate(aggregates, product: str):
    return next(agg for agg in aggregates if agg.product.product == product)


def test_same_owner_foreign_port_stops_without_inbound_dep():
    upstream, downstream = _maps([("UP_PORT", "OUT"), ("RAW", "UP_PORT")])
    manifests = [
        _product("consumer", ["team-a"], ["OUT"]),
        _product("upstream", ["team-a"], ["UP_PORT"]),
    ]

    aggregates = walk_all(manifests, upstream, downstream, _nodes("OUT", "UP_PORT", "RAW"), lambda _: False)
    consumer = _aggregate(aggregates, "consumer")

    assert consumer.resolved_inbound_deps == []
    assert consumer.interior == set()
    assert {"source": "UP_PORT", "target": "OUT"} in [
        {"source": edge["source"], "target": edge["target"]}
        for edge in consumer.subgraph_edges
    ]


def test_different_owner_foreign_port_becomes_resolved_inbound_dep():
    upstream, downstream = _maps([("UP_PORT", "OUT"), ("RAW", "UP_PORT")])
    manifests = [
        _product("consumer", ["team-a"], ["OUT"]),
        _product("upstream", ["team-b"], ["UP_PORT"]),
    ]

    aggregates = walk_all(manifests, upstream, downstream, _nodes("OUT", "UP_PORT", "RAW"), lambda _: False)
    consumer = _aggregate(aggregates, "consumer")

    assert consumer.resolved_inbound_deps == ["UP_PORT"]
    assert consumer.interior == set()


def test_contested_ports_are_excluded_from_stop_index_and_walked_as_interior():
    manifests = [
        _product("a", ["team-a"], ["SHARED"]),
        _product("b", ["team-b"], ["SHARED"]),
        _product("consumer", ["team-c"], ["OUT"]),
    ]
    port_index = build_port_index(manifests)
    assert port_index["SHARED"] == ["a", "b"]
    assert "SHARED" not in clean_port_index(port_index)

    upstream, downstream = _maps([("SHARED", "OUT"), ("RAW", "SHARED")])
    aggregates = walk_all(manifests, upstream, downstream, _nodes("OUT", "SHARED", "RAW"), lambda _: False)

    assert _aggregate(aggregates, "consumer").interior == {"RAW", "SHARED"}


def test_diamond_graph_and_cycles_are_safe_and_deterministic():
    upstream, downstream = _maps([
        ("A", "OUT"),
        ("B", "OUT"),
        ("C", "A"),
        ("C", "B"),
        ("B", "C"),
    ])
    manifests = [_product("p", ["team-a"], ["OUT"])]

    first = walk_all(manifests, upstream, downstream, _nodes("OUT", "A", "B", "C"), lambda _: False)
    second = walk_all(manifests, upstream, downstream, _nodes("OUT", "A", "B", "C"), lambda _: False)

    assert _aggregate(first, "p").interior == {"A", "B", "C"}
    assert _aggregate(second, "p").interior == {"A", "B", "C"}
    assert _aggregate(first, "p").subgraph_edges == _aggregate(second, "p").subgraph_edges


def test_external_sources_are_collected_without_becoming_interior():
    upstream, downstream = _maps([("S4:ORDERS", "OUT")])
    manifests = [_product("p", ["team-a"], ["OUT"])]

    aggregates = walk_all(manifests, upstream, downstream, _nodes("OUT"), lambda node: node.startswith("S4:"))
    agg = _aggregate(aggregates, "p")

    assert agg.inbound_sources == ["S4:ORDERS"]
    assert agg.interior == set()


def test_missing_interior_node_still_appears_in_subgraph_nodes():
    upstream, downstream = _maps([("MISSING_INTERIOR", "OUT")])
    manifests = [_product("p", ["team-a"], ["OUT"])]

    aggregates = walk_all(manifests, upstream, downstream, _nodes("OUT"), lambda _: False)
    agg = _aggregate(aggregates, "p")

    assert agg.interior == {"MISSING_INTERIOR"}
    assert "MISSING_INTERIOR" in {node["id"] for node in agg.subgraph_nodes}
