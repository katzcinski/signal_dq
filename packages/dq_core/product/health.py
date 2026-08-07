from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from dq_core.store.base import ResultStoreProtocol

from .model import Product
from .walk import ProductAggregate


@dataclass(frozen=True)
class UpstreamRiskEntry:
    product: str
    pinned_version: str
    current_version: str | None
    compliance: str | None
    upstream_breach: bool
    version_drift: bool


_STATUS_RANK = {
    "unknown": 0,
    "pass": 1,
    "compliant": 1,
    "warn": 2,
    "warning": 2,
    "fail": 3,
    "breached": 3,
    "critical": 4,
}

_CANONICAL_HEALTH = {
    "compliant": "pass",
    "breached": "fail",
    "warning": "warn",
}


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


def _rank(status: str | None) -> int:
    return _STATUS_RANK.get(str(status or "unknown"), 0)


def worst_of(statuses: list[str]) -> str:
    if not statuses:
        return "unknown"
    worst = max(statuses, key=_rank)
    return _CANONICAL_HEALTH.get(worst, worst if worst in _STATUS_RANK else "unknown")


def own_health(
    agg: ProductAggregate,
    contracts: dict[str, Any],
    store: ResultStoreProtocol,
) -> str:
    governance_statuses: list[str] = []
    for port in agg.product.output_ports:
        contract = contracts.get(port.dataset)
        if contract is None:
            continue
        if _field(contract, "kind", "internal_gate") not in {"consumer_contract", "provider_contract"}:
            continue
        if _field(contract, "lifecycle", "draft") != "active":
            continue
        compliance = store.get_compliance(port.dataset)
        if compliance:
            governance_statuses.append(str(compliance["compliance"]))

    return worst_of(governance_statuses)


def upstream_risk(
    agg: ProductAggregate,
    all_manifests: list[Product],
    contracts: dict[str, Any],
    store: ResultStoreProtocol,
) -> list[UpstreamRiskEntry]:
    del contracts  # contract metadata is intentionally not needed for this v1 read

    manifests_by_name = {manifest.product: manifest for manifest in all_manifests}
    entries: list[UpstreamRiskEntry] = []
    for dep in agg.product.inbound:
        upstream_manifest = manifests_by_name.get(dep.product)
        if not upstream_manifest:
            continue

        worst_compliance: str | None = None
        worst_version: str | None = None
        for port in upstream_manifest.output_ports:
            rec = store.get_compliance(port.dataset)
            if not rec:
                continue
            compliance = str(rec["compliance"])
            version = rec.get("contract_version")
            if worst_compliance is None or _rank(compliance) > _rank(worst_compliance):
                worst_compliance = compliance
                if version is not None:
                    worst_version = version
            elif worst_version is None and version is not None:
                worst_version = version

        entries.append(
            UpstreamRiskEntry(
                product=dep.product,
                pinned_version=dep.version,
                current_version=worst_version,
                compliance=worst_compliance,
                upstream_breach=worst_compliance in {"breached", "fail", "critical"},
                version_drift=worst_version is not None and worst_version != dep.version,
            )
        )

    return entries
