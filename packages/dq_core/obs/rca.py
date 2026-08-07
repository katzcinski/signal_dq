"""Pure RCA heuristics for persisted incident snapshots."""
from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from typing import Any


def analyze_incident(
    *,
    incident: dict,
    run: dict,
    lineage: dict,
    contract_index: list[dict],
    recent_failures: list[dict],
    prior_incidents: list[dict],
    window_minutes: int = 120,
) -> dict:
    product = str(incident.get("product") or run.get("dataset") or "")
    run_at = _parse_dt(run.get("started_at") or incident.get("opened_at"))
    upstream = _distances(lineage, product, reverse=True)
    downstream = _distances(lineage, product, reverse=False)

    candidates = _rank_candidates(
        product=product,
        run_at=run_at,
        upstream=upstream,
        recent_failures=recent_failures,
        window_minutes=window_minutes,
    )
    probable = candidates[0] if candidates else {}
    affected_contracts, affected_internal = _blast_radius(downstream, contract_index)
    recurrence = _recurrence(prior_incidents)

    return {
        "probable_cause_object": probable.get("object", ""),
        "cause_confidence": probable.get("confidence"),
        "cause_candidates": candidates[:5],
        "affected_contracts": affected_contracts,
        "affected_internal_gates": affected_internal,
        "recurrence_count": recurrence["count"],
        "recurrence_last_at": recurrence["last_at"],
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }


def _rank_candidates(
    *,
    product: str,
    run_at: datetime,
    upstream: dict[str, int],
    recent_failures: list[dict],
    window_minutes: int,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for failure in recent_failures:
        dataset = str(failure.get("dataset") or "")
        if dataset == product or dataset not in upstream:
            continue
        failed_at = _parse_dt(failure.get("started_at"))
        age_minutes = max(0.0, (run_at - failed_at).total_seconds() / 60.0)
        if age_minutes > window_minutes:
            continue
        distance = upstream[dataset]
        distance_score = 1.0 / max(distance, 1)
        time_score = max(0.1, 1.0 - (age_minutes / max(window_minutes, 1)))
        severity_score = {"critical": 1.0, "fail": 0.8, "warn": 0.5}.get(
            str(failure.get("severity") or ""), 0.4
        )
        family_score = _family_score(str(failure.get("check_type") or ""))
        confidence = round(distance_score * time_score * severity_score * family_score, 3)
        candidates.append({
            "object": dataset,
            "distance": distance,
            "run_id": failure.get("run_id", ""),
            "check_name": failure.get("check_name", ""),
            "check_type": failure.get("check_type", ""),
            "severity": failure.get("severity", ""),
            "failed_at": failure.get("started_at", ""),
            "confidence": confidence,
        })
    return sorted(
        candidates,
        key=lambda c: (-float(c["confidence"]), int(c["distance"]), c["failed_at"]),
    )


def _blast_radius(
    downstream: dict[str, int],
    contract_index: list[dict],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    by_product = {str(row.get("product") or ""): row for row in contract_index}
    affected_contracts: list[dict[str, Any]] = []
    affected_internal: list[dict[str, Any]] = []
    for product, distance in sorted(downstream.items(), key=lambda item: (item[1], item[0])):
        row = by_product.get(product)
        if not row or row.get("lifecycle") != "active":
            continue
        item = {
            "product": product,
            "kind": row.get("kind") or "internal_gate",
            "distance": distance,
            "version": row.get("version") or "",
        }
        if item["kind"] in ("consumer_contract", "provider_contract"):
            affected_contracts.append(item)
        elif item["kind"] == "internal_gate":
            affected_internal.append(item)
    return affected_contracts, affected_internal


def _recurrence(prior_incidents: list[dict]) -> dict[str, Any]:
    if not prior_incidents:
        return {"count": 0, "last_at": ""}
    last = max(str(i.get("opened_at") or "") for i in prior_incidents)
    return {"count": len(prior_incidents), "last_at": last}


def _distances(lineage: dict, root: str, *, reverse: bool) -> dict[str, int]:
    graph: dict[str, set[str]] = {}
    for edge in lineage.get("edges") or []:
        source = str(edge.get("source") or "")
        target = str(edge.get("target") or "")
        if not source or not target:
            continue
        a, b = (target, source) if reverse else (source, target)
        graph.setdefault(a, set()).add(b)

    distances: dict[str, int] = {}
    queue: deque[tuple[str, int]] = deque([(root, 0)])
    seen = {root}
    while queue:
        node, distance = queue.popleft()
        for nxt in sorted(graph.get(node, ())):
            if nxt in seen:
                continue
            seen.add(nxt)
            distances[nxt] = distance + 1
            queue.append((nxt, distance + 1))
    return distances


def _family_score(check_type: str) -> float:
    if check_type in {"schema", "row_count", "volume_anomaly", "freshness", "freshness_anomaly"}:
        return 1.0
    if check_type in {"missing", "completeness_pct", "completeness_pct_segment"}:
        return 0.75
    return 0.65


def _parse_dt(value: Any) -> datetime:
    try:
        dt = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)
