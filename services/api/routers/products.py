from __future__ import annotations

from collections import defaultdict
from collections import deque
from dataclasses import asdict
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
import yaml

from dq_core.product.health import own_health, upstream_risk
from dq_core.product.model import Product, load_all_manifests
from dq_core.product.reconcile import Finding, reconcile
from dq_core.product.walk import (
    ProductAggregate,
    build_port_index,
    looks_external,
    walk_all,
)

from ..deps import StoreDep, get_lineage
from ..schemas.product_schemas import (
    LineageSubgraphOut,
    ProductDetailOut,
    ProductFindingOut,
    ProductInboundDependencyOut,
    ProductInteriorOut,
    ProductListItem,
    ProductPortOut,
)
from ..settings import get_settings

router = APIRouter(prefix="/api/products", tags=["products"])


def _field(contract: Any, name: str, default: Any = None) -> Any:
    if contract is None:
        return default
    if isinstance(contract, dict):
        return contract.get(name, default)
    raw = getattr(contract, "raw", None)
    if isinstance(raw, dict) and name in raw:
        return raw.get(name, default)
    return getattr(contract, name, default)


def _is_governance_contract(contract: Any) -> bool:
    return _field(contract, "kind", "internal_gate") in {"consumer_contract", "provider_contract"}


def _load_contracts_by_dataset(contracts_dir: str | Path) -> dict[str, dict[str, Any]]:
    base = Path(contracts_dir)
    if not base.exists():
        return {}

    contracts: dict[str, tuple[int, dict[str, Any]]] = {}
    for path in sorted(base.glob("*.y*ml")):
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:  # noqa: BLE001 - bad contracts are ignored by this read model
            continue
        if not isinstance(data, dict):
            continue
        active = path.name.endswith((".active.yml", ".active.yaml"))
        stem = path.name.rsplit(".active.", 1)[0] if active else path.stem
        dataset = str(data.get("dataset") or stem)
        priority = 1 if active else 0
        current = contracts.get(dataset)
        if current is None or priority >= current[0]:
            contracts[dataset] = (priority, data)
    return {dataset: data for dataset, (_priority, data) in contracts.items()}


def _graph_maps(lineage: dict[str, Any]) -> tuple[dict[str, dict], dict[str, list[str]], dict[str, list[str]]]:
    nodes = lineage.get("nodes") or []
    edges = lineage.get("edges") or []

    node_data = {
        str(node.get("id")): node
        for node in nodes
        if node.get("id") is not None
    }
    upstream: dict[str, list[str]] = defaultdict(list)
    downstream: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        source = str(edge.get("source") or "")
        target = str(edge.get("target") or "")
        if not source or not target:
            continue
        downstream[source].append(target)
        upstream[target].append(source)

    return node_data, dict(upstream), dict(downstream)


def _node_record(node_id: str, node_data: dict[str, dict]) -> dict[str, Any]:
    return node_data.get(node_id) or {
        "id": node_id,
        "label": node_id,
        "layer": "unknown",
        "role": "unknown",
    }


def _upstream_preview_subgraph(
    seeds: list[str],
    node_data: dict[str, dict],
    upstream: dict[str, list[str]],
) -> LineageSubgraphOut:
    nodes_by_id: dict[str, dict[str, Any]] = {}
    edge_keys: set[tuple[str, str]] = set()
    edges: list[dict[str, Any]] = []
    visited: set[str] = set()
    queue: deque[str] = deque(sorted(set(seeds)))

    while queue:
        node_id = queue.popleft()
        if node_id in visited:
            continue
        visited.add(node_id)
        nodes_by_id[node_id] = _node_record(node_id, node_data)

        for source in sorted(upstream.get(node_id, [])):
            nodes_by_id[source] = _node_record(source, node_data)
            key = (source, node_id)
            if key not in edge_keys:
                edge_keys.add(key)
                edges.append({
                    "id": f"{source}->{node_id}",
                    "source": source,
                    "target": node_id,
                })
            if source not in visited:
                queue.append(source)

    return LineageSubgraphOut(
        nodes=[nodes_by_id[node_id] for node_id in sorted(nodes_by_id)],
        edges=sorted(edges, key=lambda edge: (str(edge["source"]), str(edge["target"]))),
    )


def _build_context(lineage: dict[str, Any]) -> tuple[
    list[Product],
    list[ProductAggregate],
    dict[str, list[str]],
    dict[str, Any],
    list[Finding],
]:
    settings = get_settings()
    manifests = load_all_manifests(settings.products_dir)
    contracts = _load_contracts_by_dataset(settings.contracts_dir)
    node_data, upstream, downstream = _graph_maps(lineage)
    port_index = build_port_index(manifests)

    def is_external(node_id: str) -> bool:
        return looks_external(node_id, node_data.get(node_id))

    aggregates = walk_all(
        manifests,
        upstream=upstream,
        downstream=downstream,
        node_data=node_data,
        is_external=is_external,
        port_index=port_index,
    )
    findings = reconcile(
        aggregates,
        port_index,
        downstream,
        manifests,
        contracts,
        set(node_data),
    )
    return manifests, aggregates, port_index, contracts, findings


def _derive_lifecycle(product: Product, contracts: dict[str, Any]) -> str:
    lifecycles = [
        str(_field(contract, "lifecycle", "draft"))
        for port in product.output_ports
        if (contract := contracts.get(port.dataset)) is not None and _is_governance_contract(contract)
    ]
    if any(lifecycle == "active" for lifecycle in lifecycles):
        return "active"
    if lifecycles and all(lifecycle == "deprecated" for lifecycle in lifecycles):
        return "deprecated"
    return "draft"


def _risk_count(entries: list[ProductInboundDependencyOut]) -> int:
    return sum(1 for entry in entries if entry.upstream_breach or entry.version_drift)


def _findings_for(findings: list[Finding], product: str) -> list[ProductFindingOut]:
    return [
        ProductFindingOut(
            finding_type=finding.finding_type,
            scope=finding.scope,
            object_id=finding.object_id,
            detail=finding.detail,
        )
        for finding in findings
        if finding.product == product
    ]


def _risk_entries(
    aggregate: ProductAggregate,
    manifests: list[Product],
    contracts: dict[str, Any],
    store,
) -> list[ProductInboundDependencyOut]:
    return [
        ProductInboundDependencyOut(**asdict(entry))
        for entry in upstream_risk(aggregate, manifests, contracts, store)
    ]


def _port_out(port_dataset: str, contracts: dict[str, Any], store) -> ProductPortOut:
    contract = contracts.get(port_dataset)
    compliance = store.get_compliance(port_dataset)
    version = _field(contract, "version") if contract else None
    return ProductPortOut(
        dataset=port_dataset,
        kind=_field(contract, "kind") if contract else None,
        lifecycle=_field(contract, "lifecycle") if contract else None,
        compliance=compliance["compliance"] if compliance else None,
        version=str(version) if version is not None else None,
    )


def _interior_out(aggregate: ProductAggregate) -> list[ProductInteriorOut]:
    by_id = {
        str(node.get("id")): node
        for node in aggregate.subgraph_nodes
        if str(node.get("id")) in aggregate.interior
    }
    return [
        ProductInteriorOut(
            id=node_id,
            layer=node.get("layer"),
            role=node.get("role"),
            coverage_flag=node.get("coverage_flag") or node.get("coverageFlag"),
        )
        for node_id, node in sorted(by_id.items())
    ]


@router.get("", response_model=list[ProductListItem])
def list_products(
    lineage: dict = Depends(get_lineage),
    store: StoreDep = ...,
):
    manifests, aggregates, _port_index, contracts, findings = _build_context(lineage)
    aggregates_by_product = {aggregate.product.product: aggregate for aggregate in aggregates}
    findings_by_product = defaultdict(int)
    for finding in findings:
        findings_by_product[finding.product] += 1

    items: list[ProductListItem] = []
    for product in sorted(manifests, key=lambda item: item.product):
        aggregate = aggregates_by_product[product.product]
        risk_entries = _risk_entries(aggregate, manifests, contracts, store)
        items.append(
            ProductListItem(
                product=product.product,
                owners=product.owners,
                port_count=len(product.output_ports),
                own_health=own_health(aggregate, contracts, store),
                upstream_risk_count=_risk_count(risk_entries),
                finding_count=findings_by_product[product.product],
                lifecycle=_derive_lifecycle(product, contracts),
            )
        )
    return items


@router.get("/{product}", response_model=ProductDetailOut)
def get_product(
    product: str,
    lineage: dict = Depends(get_lineage),
    store: StoreDep = ...,
):
    manifests, aggregates, _port_index, contracts, findings = _build_context(lineage)
    aggregate = next(
        (item for item in aggregates if item.product.product == product),
        None,
    )
    if aggregate is None:
        raise HTTPException(status_code=404, detail=f"Product {product!r} not found")

    risk_entries = _risk_entries(aggregate, manifests, contracts, store)
    finding_entries = _findings_for(findings, product)
    ports = [
        _port_out(port.dataset, contracts, store)
        for port in aggregate.product.output_ports
    ]
    node_data, upstream, _downstream = _graph_maps(lineage)
    return ProductDetailOut(
        product=aggregate.product.product,
        owners=aggregate.product.owners,
        lifecycle=_derive_lifecycle(aggregate.product, contracts),
        own_health=own_health(aggregate, contracts, store),
        ports=ports,
        interior=_interior_out(aggregate),
        inbound_sources=aggregate.inbound_sources,
        upstream_risk=risk_entries,
        findings=finding_entries,
        subgraph=_upstream_preview_subgraph(
            [port.dataset for port in aggregate.product.output_ports],
            node_data=node_data,
            upstream=upstream,
        ),
    )


@router.get("/{product}/export/odps")
def export_odps(product: str):
    """E3: ODPS-1.0-Export des Product-Manifests (Einweg-Derivat, YAML=SoT).

    Produktseitiges Analog zum ODCS-Contract-Export. ⚠ Best-Guess-Feldschema:
    solange kein realer ODPS-Marktplatz gegenverifiziert ist (Setting
    `entropy_marketplace_verified`), trägt das Dokument `x-signal-validation:
    unverified` — der Aufrufer sieht ehrlich, dass die Form noch aussteht.
    """
    from dq_core.product.odps_export import to_odps
    from dq_core.product.model import load_all_manifests

    settings = get_settings()
    manifest = next(
        (m for m in load_all_manifests(settings.products_dir) if m.product == product),
        None,
    )
    if manifest is None:
        raise HTTPException(status_code=404, detail=f"Product {product!r} not found")

    contracts_by_dataset = _load_contracts_by_dataset(settings.contracts_dir)
    doc = to_odps(
        manifest,
        contract_lookup=lambda dataset: contracts_by_dataset.get(dataset),
        verified=bool(getattr(settings, "entropy_marketplace_verified", False)),
    )
    return doc
