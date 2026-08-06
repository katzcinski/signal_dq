from __future__ import annotations

from collections import deque
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Query

from ..deps import StoreDep, get_inventory, get_lineage

router = APIRouter(prefix="/api/lineage", tags=["lineage"])


def _scan_contracts(contracts_dir: Path) -> tuple[list[str], set[str], set[str], dict[str, str]]:
    """Scan the contracts dir once: who is contracted, gates vs. boundary, kinds."""
    import yaml as _yaml

    contracted: list[str] = []
    gate_products: set[str] = set()
    contract_products: set[str] = set()
    contract_kinds: dict[str, str] = {}
    if not contracts_dir.exists():
        return contracted, gate_products, contract_products, contract_kinds
    for path in contracts_dir.glob("*.y*ml"):
        if path.name.endswith(".active.yml"):
            continue
        product = path.stem
        contracted.append(product)
        try:
            data = _yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:
            gate_products.add(product)
            continue
        kind = data.get("kind", "internal_gate")
        if kind == "internal_gate":
            gate_products.add(product)
        else:
            contract_products.add(product)
            contract_kinds[product] = kind
    return contracted, gate_products, contract_products, contract_kinds


def _seed_subgraph(
    seeds: list[str],
    edges: list[dict],
    column_edges: list[dict],
    depth: int,
) -> set[str]:
    """Objekt-IDs im ungerichteten ``depth``-Umkreis der Seeds (inkl. Seeds).

    Adjazenz aus Objekt-Edges und aus Column-Edges abgeleiteten Objektpaaren,
    damit der Teilgraph auch dort zusammenhängt, wo nur Spalten-Lineage
    vorliegt. Zyklensicher über das ``keep``-Set.
    """
    adj: dict[str, set[str]] = {}
    for e in (*edges, *column_edges):
        s, t = e.get("source"), e.get("target")
        if not s or not t or s == t:
            continue
        adj.setdefault(s, set()).add(t)
        adj.setdefault(t, set()).add(s)

    keep: set[str] = set()
    frontier: deque[tuple[str, int]] = deque()
    for s in seeds:
        if s not in keep:
            keep.add(s)
            frontier.append((s, 0))
    while frontier:
        cur, d = frontier.popleft()
        if d >= depth:
            continue
        for nb in adj.get(cur, ()):
            if nb not in keep:
                keep.add(nb)
                frontier.append((nb, d + 1))
    return keep


@router.get("")
def get_lineage_graph(
    space: str | None = Query(default=None),
    seed: list[str] | None = Query(default=None),
    depth: int = Query(default=2, ge=0, le=20),
    lineage: dict = Depends(get_lineage),
    store: StoreDep = ...,
):
    from dq_core.lineage.loader import get_coverage
    from ..settings import get_settings

    settings = get_settings()
    nodes = lineage.get("nodes") or []
    edges = lineage.get("edges") or []
    column_edges = lineage.get("columnEdges") or []

    if space:
        nodes = [n for n in nodes if n.get("space") == space]
        node_ids = {n.get("id") for n in nodes}
        edges = [e for e in edges if e.get("source") in node_ids or e.get("target") in node_ids]
        column_edges = [
            e for e in column_edges
            if e.get("source") in node_ids or e.get("target") in node_ids
        ]

    # Seed-Scoping: statt des kompletten Graphen nur den Teilgraphen rund um
    # ein oder mehrere Seed-Objekte liefern (UX: Board nicht überfrachten).
    # BFS in beide Richtungen über das Objekt-Adjazenznetz (echte Objekt-Edges
    # ∪ aus Column-Edges abgeleitete Paare) bis ``depth`` Hops. Ohne Seed bleibt
    # der volle Graph erhalten (Rückwärtskompatibilität für ObjectDetail/Tests).
    seeds = [s for s in (seed or []) if s]
    if seeds:
        keep = _seed_subgraph(seeds, edges, column_edges, depth)
        nodes = [n for n in nodes if n.get("id") in keep]
        edges = [
            e for e in edges
            if e.get("source") in keep and e.get("target") in keep
        ]
        column_edges = [
            e for e in column_edges
            if e.get("source") in keep and e.get("target") in keep
        ]

    # Annotate with live DQ status and coverage flags
    object_statuses = store.get_object_status()
    contracted, gate_products, contract_products, contract_kinds = _scan_contracts(
        Path(settings.contracts_dir)
    )

    annotated_nodes = get_coverage(
        nodes,
        object_statuses,
        contracted,
        gate_products=gate_products,
        contract_products=contract_products,
        contract_kinds=contract_kinds,
    )

    # F5: Extrakt-Alter — FE zeigt eine Staleness-Warnung darauf an.
    extract_age_days = None
    extracted_at = None
    stale = False
    lineage_path = Path(settings.lineage_file)
    if lineage_path.exists():
        from datetime import datetime, timezone
        mtime = datetime.fromtimestamp(lineage_path.stat().st_mtime, tz=timezone.utc)
        extracted_at = mtime.isoformat()
        extract_age_days = (datetime.now(timezone.utc) - mtime).days
        stale = extract_age_days > settings.extract_stale_days

    return {
        "nodes": annotated_nodes,
        "edges": edges,
        "columnEdges": column_edges,
        "extracted_at": extracted_at,
        "extract_age": extract_age_days,
        "stale": stale,
    }


@router.get("/columns")
def get_column_lineage(
    object_id: str = Query(..., alias="object"),
    column: str | None = Query(default=None),
    lineage: dict = Depends(get_lineage),
):
    """Per-column upstream/downstream lineage for one object (O3).

    Built from the columnEdges produced by the extract chain
    (build_column_lineage). Returns the per-column index for the object, or a
    single column's lineage when ``column`` is given.
    """
    from dq_core.lineage._column_lineage import (
        ColumnEdge,
        ColumnLineageResult,
        build_column_indexes,
    )

    edges = [
        ColumnEdge(
            source_object=e.get("source", ""),
            source_column=e.get("sourceColumn", ""),
            target_object=e.get("target", ""),
            target_column=e.get("targetColumn", ""),
            edge_type=e.get("edgeType", "direct"),
            expression=e.get("expression", ""),
        )
        for e in (lineage.get("columnEdges") or [])
    ]
    idx = build_column_indexes(
        ColumnLineageResult(edges=edges, coverage={}, unmapped_objects=[])
    )
    obj_idx = idx.get(object_id, {})
    if column is not None:
        return {
            "object": object_id,
            "column": column,
            "lineage": obj_idx.get(column, {"upstream": [], "downstream": []}),
        }
    return {"object": object_id, "columns": obj_idx}


def _downstream_adjacency(column_edges: list[dict]) -> dict[tuple[str, str], list[dict[str, str]]]:
    """``(object, column) -> [{target, column, edgeType, expression}, ...]``."""
    adj: dict[tuple[str, str], list[dict[str, str]]] = {}
    for e in column_edges:
        key = (e.get("source", ""), e.get("sourceColumn", ""))
        adj.setdefault(key, []).append({
            "object": e.get("target", ""),
            "column": e.get("targetColumn", ""),
            "edgeType": e.get("edgeType", "direct"),
            "expression": e.get("expression", ""),
        })
    return adj


@router.get("/columns/impact")
def get_column_impact(
    object_id: str = Query(..., alias="object"),
    column: str = Query(...),
    max_depth: int = Query(default=25, ge=1, le=100),
    lineage: dict = Depends(get_lineage),
    inventory: list[dict] = Depends(get_inventory),
    store: StoreDep = ...,
):
    """Transitive downstream impact of one column (UX-N7 / WS-C).

    BFS over ``columnEdges`` from ``(object, column)``; every reachable
    downstream column is reported once at its minimum hop distance, enriched
    with the consumer object's ownership and coverage flag. Cycle-safe via a
    visited set; ``truncated`` signals edges left unexplored at ``max_depth``.
    """
    from dq_core.lineage.loader import get_coverage
    from ..settings import get_settings

    adj = _downstream_adjacency(lineage.get("columnEdges") or [])

    seen: set[tuple[str, str]] = {(object_id, column)}
    impacted: list[dict[str, Any]] = []
    queue: deque[tuple[str, str, int]] = deque([(object_id, column, 0)])
    truncated = False
    while queue:
        obj, col, depth = queue.popleft()
        children = adj.get((obj, col), [])
        if depth >= max_depth:
            if children:
                truncated = True
            continue
        for child in children:
            node = (child["object"], child["column"])
            if node in seen:
                continue
            seen.add(node)
            impacted.append({
                "object": child["object"],
                "column": child["column"],
                "edgeType": child["edgeType"],
                "expression": child["expression"],
                "depth": depth + 1,
            })
            queue.append((child["object"], child["column"], depth + 1))

    # Enrich affected objects with ownership (inventory) + coverage flag (store).
    own_by_id: dict[str, dict] = {o.get("technicalName", ""): o for o in inventory}
    settings = get_settings()
    contracted, gate_products, contract_products, contract_kinds = _scan_contracts(
        Path(settings.contracts_dir)
    )
    affected_ids = {row["object"] for row in impacted}
    cov_nodes = get_coverage(
        [{"id": oid, **{k: v for k, v in own_by_id.get(oid, {}).items()
                        if k in ("objectType", "space")}} for oid in affected_ids],
        store.get_object_status(),
        contracted,
        gate_products=gate_products,
        contract_products=contract_products,
        contract_kinds=contract_kinds,
    )
    cov_by_id = {n["id"]: n for n in cov_nodes}

    for row in impacted:
        inv = own_by_id.get(row["object"], {})
        cov = cov_by_id.get(row["object"], {})
        row["ownedBy"] = inv.get("owned_by", "")
        row["owners"] = inv.get("owners", [])
        row["coverageFlag"] = cov.get("coverage_flag", "○")
        row["dqStatus"] = cov.get("dq_status", "unknown")

    impacted.sort(key=lambda r: (r["depth"], r["object"], r["column"]))
    return {
        "object": object_id,
        "column": column,
        "impacted": impacted,
        "totalImpacted": len(impacted),
        "maxDepth": max(((r["depth"]) for r in impacted), default=0),
        "truncated": truncated,
    }
