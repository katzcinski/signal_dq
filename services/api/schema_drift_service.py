"""Shift-Left-Schema-Drift — geteilte Logik (Konzept §A).

Genutzt von `routers/contracts.py` (Read-only-Report) und `routers/extract.py`
(Persistenz + kind-aware Incident beim Extrakt). Die reine Diff-Mechanik liegt
frameworkfrei in `dq_core.contract.schema_drift` (G7); hier kommt nur die
Orchestrierung (Inventar-Lookup, Snapshot-Persistenz, Incident-Routing) dazu.
"""
from __future__ import annotations

from typing import Any

from dq_core.contract.schema_drift import (
    columns_hash,
    detect_schema_drift,
    summarize_drift,
)

# kind → Incident-Klassifikation (wie Compliance-Trennung in Migration 007).
_GOVERNANCE_KINDS = {"consumer_contract", "provider_contract"}


def inventory_columns_for(inventory: list[dict[str, Any]], dataset: str) -> list[dict[str, Any]] | None:
    """Spaltenliste des Inventar-Objekts, das zum Contract-`dataset` gehört.

    Liefert ``None``, wenn das Objekt nicht im Inventar ist (≠ leere Spaltenliste,
    die einen vollständigen column_removed-Drift bedeuten würde)."""
    for obj in inventory or []:
        ident = obj.get("id") or obj.get("technicalName") or obj.get("name")
        if ident == dataset:
            return list(obj.get("columns") or [])
    return None


def evaluate_contract_drift(
    contract: dict[str, Any], source_columns: list[dict[str, Any]]
) -> dict[str, Any]:
    """Read-only-Report: Findings + Summary für einen Contract."""
    findings = detect_schema_drift(contract, source_columns)
    return {
        "findings": [f.to_dict() for f in findings],
        "summary": summarize_drift(findings),
    }


def persist_and_alert(
    store: Any,
    contract: dict[str, Any],
    source_columns: list[dict[str, Any]],
) -> dict[str, Any]:
    """Snapshot + Drift persistieren und bei breaking-Drift kind-aware ein
    Incident eröffnen. Liefert das Report-Dict (+ ggf. ``incident_id``)."""
    product = contract.get("product") or contract.get("dataset") or ""
    dataset = contract.get("dataset") or product
    version = str(contract.get("version") or "")
    kind = contract.get("kind", "internal_gate")

    findings = detect_schema_drift(contract, source_columns)
    summary = summarize_drift(findings)

    # Snapshot immer (Historie), auch ohne Drift.
    store.save_schema_snapshot(dataset, source_columns, columns_hash(source_columns))

    incident_id: int | None = None
    if findings:
        if summary["has_breaking"]:
            incident_kind = "consumer_contract" if kind in _GOVERNANCE_KINDS else "internal_gate"
            cols = sorted({f.column for f in findings if f.breaking})
            title = (
                f"Schema-Drift: Quelle weicht vom Contract-Versprechen ab "
                f"({summary['breaking']} breaking)"
            )
            incident_id = store.open_incident(
                product=product,
                run_id="",
                severity="fail",
                title=title,
                failed_checks=cols,
                contract_version=version,
                kind=incident_kind,
                actor="system",
            )
        store.record_schema_drift(
            dataset,
            [f.to_dict() for f in findings],
            contract_version=version,
            incident_id=incident_id,
        )

    return {
        "findings": [f.to_dict() for f in findings],
        "summary": summary,
        "incident_id": incident_id,
    }
