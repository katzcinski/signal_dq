from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Callable

from .model import Product


@dataclass
class ProductAggregate:
    product: Product
    interior: set[str]
    inbound_sources: list[str]
    resolved_inbound_deps: list[str]
    subgraph_nodes: list[dict[str, Any]]
    subgraph_edges: list[dict[str, Any]]


def build_port_index(manifests: list[Product]) -> dict[str, list[str]]:
    port_index: dict[str, list[str]] = defaultdict(list)
    for manifest in sorted(manifests, key=lambda item: item.product):
        for port in manifest.output_ports:
            port_index[port.dataset].append(manifest.product)
    return dict(port_index)


def clean_port_index(port_index: dict[str, list[str]]) -> dict[str, str]:
    return {
        dataset: owners[0]
        for dataset, owners in port_index.items()
        if len(owners) == 1
    }


def looks_external(node_id: str, node: dict[str, Any] | None = None) -> bool:
    """Best-effort external source classifier matching lineage inventory signals."""
    data = node or {}
    if data.get("sourceScope") == "external_system":
        return True
    if str(data.get("type") or "").lower() == "external":
        return True
    if str(data.get("layer") or "").lower() == "external":
        return True

    n = (node_id or "").strip()
    if n.upper().startswith("S4:"):
        return True
    return n.lower().startswith("ext")


def _append_unique(items: list[str], value: str) -> None:
    if value not in items:
        items.append(value)


def _node_record(node_id: str, node_data: dict[str, dict]) -> dict[str, Any]:
    return node_data.get(node_id) or {
        "id": node_id,
        "label": node_id,
        "layer": "unknown",
        "role": "unknown",
    }


def _append_edge(
    edges: list[dict[str, Any]],
    seen: set[tuple[str, str]],
    source: str,
    target: str,
) -> None:
    key = (source, target)
    if key in seen:
        return
    seen.add(key)
    edge = {
        "id": f"{source}->{target}",
        "source": source,
        "target": target,
    }
    edges.append(edge)


def walk_all(
    manifests: list[Product],
    upstream: dict[str, list[str]],
    downstream: dict[str, list[str]],
    node_data: dict[str, dict],
    is_external: Callable[[str], bool],
    port_index: dict[str, list[str]] | None = None,
) -> list[ProductAggregate]:
    del downstream  # retained in the signature for the caller's shared graph context

    manifests_by_name = {manifest.product: manifest for manifest in manifests}
    ports = port_index if port_index is not None else build_port_index(manifests)
    clean_ports = clean_port_index(ports)

    aggregates: list[ProductAggregate] = []
    for manifest in sorted(manifests, key=lambda item: item.product):
        interior: set[str] = set()
        inbound_sources: list[str] = []
        resolved_inbound_deps: list[str] = []
        subgraph_nodes_by_id: dict[str, dict[str, Any]] = {}
        subgraph_edges: list[dict[str, Any]] = []
        subgraph_edge_keys: set[tuple[str, str]] = set()

        visited: set[str] = set()
        queue = [port.dataset for port in manifest.output_ports]

        for port in manifest.output_ports:
            if port.dataset in node_data:
                subgraph_nodes_by_id[port.dataset] = node_data[port.dataset]

        while queue:
            node_id = queue.pop()
            if node_id in visited:
                continue
            visited.add(node_id)

            for up in sorted(upstream.get(node_id, [])):
                if up in clean_ports:
                    owner = clean_ports[up]
                    if owner != manifest.product:
                        manifest_owner = manifests_by_name[owner]
                        if set(manifest_owner.owners) != set(manifest.owners):
                            _append_unique(resolved_inbound_deps, up)
                    if up in node_data:
                        subgraph_nodes_by_id[up] = node_data[up]
                    _append_edge(subgraph_edges, subgraph_edge_keys, up, node_id)
                    continue

                if is_external(up):
                    _append_unique(inbound_sources, up)
                    _append_edge(subgraph_edges, subgraph_edge_keys, up, node_id)
                    continue

                interior.add(up)
                subgraph_nodes_by_id[up] = _node_record(up, node_data)
                _append_edge(subgraph_edges, subgraph_edge_keys, up, node_id)
                queue.append(up)

        aggregates.append(
            ProductAggregate(
                product=manifest,
                interior=interior,
                inbound_sources=sorted(inbound_sources),
                resolved_inbound_deps=sorted(resolved_inbound_deps),
                subgraph_nodes=[
                    subgraph_nodes_by_id[node_id]
                    for node_id in sorted(subgraph_nodes_by_id)
                ],
                subgraph_edges=sorted(
                    subgraph_edges,
                    key=lambda edge: (str(edge["source"]), str(edge["target"])),
                ),
            )
        )

    return aggregates
