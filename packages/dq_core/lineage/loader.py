from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_lineage(path: str | Path) -> dict[str, Any]:
    """Load lineage.json and return nodes/edges dict."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return {
        "nodes": data.get("nodes") or [],
        "edges": data.get("edges") or [],
    }


def get_coverage(
    nodes: list[dict],
    object_statuses: list[dict],
    contracts: list[str],
    *,
    gate_products: set[str] | None = None,
    contract_products: set[str] | None = None,
    contract_kinds: dict[str, str] | None = None,
) -> list[dict]:
    """Annotate lineage nodes with coverage flags.

    Coverage flags stay object-granular here; column derivation is exposed
    separately via lineage.columnEdges and /api/lineage/columns:
    ● (covered) — active contract + passing checks
    ◐ (partial)  — contract exists but some checks fail/missing
    ▲ (gap)      — no contract or key gap flagged
    ○ (out-of-scope) — external_raw / unresolved upstream
    """
    status_by_name = {s.get("dataset"): s for s in object_statuses}
    contracted = set(contracts)
    gates = gate_products or set()
    contracts_set = contract_products or set()
    kinds = contract_kinds or {}

    result = []
    for node in nodes:
        node_id = node.get("id") or node.get("technicalName") or ""
        status = status_by_name.get(node_id, {})
        has_any_contract = node_id in contracted
        has_gate = node_id in gates
        has_boundary_contract = node_id in contracts_set
        node_kind = ""
        if has_gate:
            node_kind = "internal_gate"
        elif has_boundary_contract:
            node_kind = kinds.get(node_id, "consumer_contract")

        if node.get("objectType") in ("external_raw", "unknown") or not node_id:
            flag = "○"
        elif not has_any_contract:
            flag = "▲"
        elif status.get("status") in ("fail", "critical", "error"):
            flag = "◐"
        elif status.get("status") == "pass":
            flag = "●"
        else:
            flag = "◐"

        result.append({
            **node,
            "coverage_flag": flag,
            "dq_status": status.get("status", "unknown"),
            "last_run": status.get("last_run"),
            "has_contract": has_any_contract,
            "has_internal_gate": has_gate,
            "has_boundary_contract": has_boundary_contract,
            "kind": node_kind,
        })
    return result
