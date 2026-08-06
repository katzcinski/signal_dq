from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import logging
from typing import Any, Literal

from .model import Product
from .walk import ProductAggregate

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Finding:
    finding_type: Literal["dangling_port", "contested", "boundary_leak"]
    scope: Literal["port", "interior"] | None
    product: str
    object_id: str
    detail: str


def _field(contract: Any, name: str, default: Any = None) -> Any:
    if contract is None:
        return default
    if isinstance(contract, dict):
        return contract.get(name, default)
    value = getattr(contract, name, None)
    if value is not None:
        return value
    raw = getattr(contract, "raw", None)
    if isinstance(raw, dict):
        return raw.get(name, default)
    return default


def reconcile(
    aggregates: list[ProductAggregate],
    port_index: dict[str, list[str]],
    downstream: dict[str, list[str]],
    all_manifests: list[Product],
    contracts: dict[str, Any],
    lineage_node_ids: set[str],
) -> list[Finding]:
    findings: list[Finding] = []

    for agg in aggregates:
        for port in agg.product.output_ports:
            contract = contracts.get(port.dataset)
            kind = _field(contract, "kind", "internal_gate")
            detail_parts: list[str] = []
            if contract is None:
                detail_parts.append("no governance contract")
            elif kind == "internal_gate":
                detail_parts.append("contract is an internal gate")
            if port.dataset not in lineage_node_ids:
                detail_parts.append("no lineage node")
            if detail_parts:
                findings.append(
                    Finding(
                        "dangling_port",
                        None,
                        agg.product.product,
                        port.dataset,
                        "; ".join(detail_parts),
                    )
                )

    for dataset, claimants in sorted(port_index.items()):
        if len(claimants) > 1:
            detail = f"output port claimed by {', '.join(sorted(claimants))}"
            for claimant in sorted(claimants):
                findings.append(Finding("contested", "port", claimant, dataset, detail))

    interior_membership: dict[str, list[str]] = defaultdict(list)
    for agg in aggregates:
        for node_id in agg.interior:
            interior_membership[node_id].append(agg.product.product)

    for node_id, products in sorted(interior_membership.items()):
        if len(products) > 1:
            detail = f"interior object shared by {', '.join(sorted(products))}"
            for product in sorted(products):
                findings.append(Finding("contested", "interior", product, node_id, detail))

    owner_map = {manifest.product: set(manifest.owners) for manifest in all_manifests}
    seen_leaks: set[tuple[str, str, str, str]] = set()
    for agg in aggregates:
        product_name = agg.product.product
        product_owners = set(agg.product.owners)
        output_ports = {port.dataset for port in agg.product.output_ports}

        for node_id in sorted(agg.interior):
            for downstream_node in sorted(downstream.get(node_id, [])):
                for claimant_product in sorted(port_index.get(downstream_node, [])):
                    if owner_map.get(claimant_product, set()) == product_owners:
                        continue
                    if node_id in output_ports:
                        continue
                    key = (product_name, node_id, downstream_node, claimant_product)
                    if key in seen_leaks:
                        continue
                    seen_leaks.add(key)
                    findings.append(
                        Finding(
                            "boundary_leak",
                            None,
                            product_name,
                            node_id,
                            f"interior object feeds cross-owner port {downstream_node} ({claimant_product})",
                        )
                    )

    logger.debug("Product reconcile v1 does not detect estate-leaving boundary leaks.")
    return findings
