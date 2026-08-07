from __future__ import annotations

from collections import deque
from typing import Any


def downstream_impact(
    *,
    lineage: dict[str, Any],
    root: str,
    inventory: list[dict[str, Any]] | None = None,
    contract_index: list[dict[str, Any]] | None = None,
    max_depth: int = 25,
) -> list[dict[str, Any]]:
    """Return downstream object impact for an object-level lineage graph."""
    graph = _downstream_graph(lineage)
    root_id = str(root or "")
    if not root_id:
        return []

    inventory_by_id = {_object_id(obj): obj for obj in inventory or []}
    inventory_by_id.pop("", None)
    nodes_by_id = {_object_id(node): node for node in lineage.get("nodes") or []}
    nodes_by_id.pop("", None)
    contracts_by_product = {
        str(row.get("product") or ""): row for row in contract_index or []
    }
    contracts_by_product.pop("", None)

    limit = max(1, int(max_depth or 1))
    seen = {root_id}
    queue: deque[tuple[str, int]] = deque([(root_id, 0)])
    impacted: list[dict[str, Any]] = []

    while queue:
        node, distance = queue.popleft()
        if distance >= limit:
            continue
        for child in sorted(graph.get(node, ())):
            if child in seen:
                continue
            seen.add(child)
            child_distance = distance + 1
            impacted.append(
                _impact_row(
                    product=child,
                    distance=child_distance,
                    inventory=inventory_by_id.get(child, {}),
                    node=nodes_by_id.get(child, {}),
                    contract=contracts_by_product.get(child, {}),
                )
            )
            queue.append((child, child_distance))

    return sorted(impacted, key=lambda row: (row["distance"], row["product"]))


def _downstream_graph(lineage: dict[str, Any]) -> dict[str, set[str]]:
    graph: dict[str, set[str]] = {}
    for edge in lineage.get("edges") or []:
        source = str(edge.get("source") or "")
        target = str(edge.get("target") or "")
        if source and target:
            graph.setdefault(source, set()).add(target)
    return graph


def _impact_row(
    *,
    product: str,
    distance: int,
    inventory: dict[str, Any],
    node: dict[str, Any],
    contract: dict[str, Any],
) -> dict[str, Any]:
    return {
        "product": product,
        "distance": distance,
        "label": str(node.get("label") or inventory.get("name") or product),
        "business_name": str(node.get("businessName") or inventory.get("businessName") or ""),
        "object_type": str(
            inventory.get("objectType")
            or inventory.get("type")
            or node.get("objectType")
            or node.get("type")
            or ""
        ),
        "space": str(inventory.get("space") or node.get("space") or ""),
        "layer": str(inventory.get("layer") or node.get("layer") or ""),
        "role": str(inventory.get("role") or node.get("role") or ""),
        "owned_by": str(inventory.get("owned_by") or inventory.get("ownedBy") or ""),
        "owners": _owners(inventory.get("owners")),
        "lifecycle": str(contract.get("lifecycle") or ""),
        "kind": str(contract.get("kind") or ""),
        "version": str(contract.get("version") or ""),
    }


def _object_id(obj: dict[str, Any]) -> str:
    return str(obj.get("id") or obj.get("technicalName") or obj.get("name") or "")


def _owners(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]
