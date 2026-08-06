"""A2 / UX-N9: Schema-Evolution über Zeit — eigenständiger Screen-Datenpfad.

Read-only-Aggregation über die beim Extrakt persistierte Historie:

1. `dq_schema_snapshots` — Quellschema je Objekt × Extrakt; konsekutive
   Snapshots werden hier zu Evolution-Schritten gedifft (`diff_snapshots`,
   frameworkfrei in `dq_core.contract.schema_drift`).
2. `dq_schema_drift` — Befunde gegen die `schema`-Garantie des aktiven
   Contracts inkl. `breaking`/`incident_id` (markiert den Contract-Bruch).

Persistenz + Incident laufen weiterhin ausschließlich beim Extrakt
(`routers/extract.py`); hier wird nichts mutiert.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional

import yaml
from fastapi import APIRouter, HTTPException

from dq_core.contract.schema_drift import diff_snapshots
from pydantic import BaseModel

from ..deps import StoreDep
from ..settings import get_settings

router = APIRouter(prefix="/api/schema-drift", tags=["schema-drift"])

# Objektnamen kommen aus Contract-`dataset` bzw. Inventar-IDs; nur als
# SQL-Parameter genutzt, die Validierung hält Pfad-/Header-Sonderfälle draußen.
_SAFE_OBJECT = re.compile(r"^[A-Za-z0-9_.\-]+$")


class DriftObjectRow(BaseModel):
    object_name: str
    snapshots: int
    first_captured_at: Optional[str] = None
    last_captured_at: Optional[str] = None
    distinct_schemas: int = 0
    findings: int = 0
    breaking: int = 0
    last_detected_at: Optional[str] = None
    last_incident_id: Optional[int] = None
    column_count: Optional[int] = None
    # Contract-Bindung (falls ein Contract auf dieses Dataset zeigt)
    product: Optional[str] = None
    kind: Optional[str] = None
    contract_version: Optional[str] = None
    lifecycle: Optional[str] = None


class DriftOverviewOut(BaseModel):
    objects: list[DriftObjectRow]


class EvolutionSnapshot(BaseModel):
    id: int
    captured_at: str
    inventory_hash: str
    column_count: int


class EvolutionChange(BaseModel):
    category: str
    column: str
    before: str
    after: str


class EvolutionStep(BaseModel):
    from_id: int
    to_id: int
    from_at: str
    to_at: str
    changes: list[EvolutionChange]


class DriftEventRow(BaseModel):
    id: int
    detected_at: str
    category: str
    column_name: str
    before_value: str
    after_value: str
    breaking: int
    contract_version: str
    incident_id: Optional[int] = None


class ContractRef(BaseModel):
    product: str
    version: str
    kind: str
    lifecycle: str


class EvolutionOut(BaseModel):
    object_name: str
    contract: Optional[ContractRef] = None
    snapshots: list[EvolutionSnapshot]
    steps: list[EvolutionStep]
    drift_events: list[DriftEventRow]
    latest_columns: list[dict[str, Any]]


def _contracts_by_dataset() -> dict[str, dict[str, Any]]:
    """dataset → Contract-Metadaten (product, version, kind, lifecycle).

    Gleiche Lese-Disziplin wie der Drift-Sweep in `routers/extract.py`: ein
    kaputtes YAML überspringt nur diesen Contract."""
    out: dict[str, dict[str, Any]] = {}
    contracts_dir = Path(get_settings().contracts_dir)
    if not contracts_dir.exists():
        return out
    for path in sorted(contracts_dir.glob("*.y*ml")):
        if path.name.endswith(".active.yml"):
            continue
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:  # noqa: BLE001 - ein defekter Contract stoppt den Report nicht
            continue
        product = data.get("product") or path.stem
        dataset = data.get("dataset") or product
        out[str(dataset)] = {
            "product": str(product),
            "version": str(data.get("version") or ""),
            "kind": str(data.get("kind") or "internal_gate"),
            "lifecycle": str(data.get("lifecycle") or "draft"),
        }
    return out


def _parse_columns(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        cols = json.loads(snapshot.get("columns_json") or "[]")
    except (TypeError, ValueError):
        return []
    return cols if isinstance(cols, list) else []


@router.get("", response_model=DriftOverviewOut)
def drift_overview(store: StoreDep = ...):
    """Rollup je Objekt: Snapshot-Historie × Drift-Befunde × Contract-Bindung."""
    contracts = _contracts_by_dataset()
    rows: list[DriftObjectRow] = []
    for raw in store.list_schema_drift_objects():
        row = DriftObjectRow(**raw)
        latest = store.get_latest_schema_snapshot(row.object_name)
        if latest:
            row.column_count = len(_parse_columns(latest))
        contract = contracts.get(row.object_name)
        if contract:
            row.product = contract["product"]
            row.kind = contract["kind"]
            row.contract_version = contract["version"]
            row.lifecycle = contract["lifecycle"]
        rows.append(row)
    return DriftOverviewOut(objects=rows)


@router.get("/{object_name}", response_model=EvolutionOut)
def schema_evolution(object_name: str, store: StoreDep = ...):
    """Schema-Evolution eines Objekts: Snapshots, konsekutive Diffs und die
    contract-bewerteten Drift-Befunde (Bruch → `breaking` + `incident_id`)."""
    if not _SAFE_OBJECT.match(object_name or ""):
        raise HTTPException(status_code=422, detail="Invalid object name.")

    raw_snapshots = store.get_schema_snapshots(object_name)
    drift_events = store.get_schema_drift(object_name)
    if not raw_snapshots and not drift_events:
        raise HTTPException(status_code=404, detail="No schema history for this object.")

    snapshots: list[EvolutionSnapshot] = []
    columns_by_id: dict[int, list[dict[str, Any]]] = {}
    for snap in raw_snapshots:
        cols = _parse_columns(snap)
        columns_by_id[int(snap["id"])] = cols
        snapshots.append(EvolutionSnapshot(
            id=int(snap["id"]),
            captured_at=str(snap.get("captured_at") or ""),
            inventory_hash=str(snap.get("inventory_hash") or ""),
            column_count=len(cols),
        ))

    # Evolution-Schritte: nur Paare, deren Schema-Hash sich unterscheidet —
    # identische Folge-Snapshots sind Kontinuität, kein Ereignis.
    steps: list[EvolutionStep] = []
    for prev, curr in zip(snapshots, snapshots[1:]):
        if prev.inventory_hash == curr.inventory_hash:
            continue
        changes = diff_snapshots(columns_by_id[prev.id], columns_by_id[curr.id])
        steps.append(EvolutionStep(
            from_id=prev.id, to_id=curr.id,
            from_at=prev.captured_at, to_at=curr.captured_at,
            changes=[EvolutionChange(
                category=c.category, column=c.column, before=c.before, after=c.after,
            ) for c in changes],
        ))
    steps.reverse()  # jüngste Änderung zuerst — wie die Drift-Historie

    contract_meta = _contracts_by_dataset().get(object_name)
    latest_columns = columns_by_id[snapshots[-1].id] if snapshots else []

    return EvolutionOut(
        object_name=object_name,
        contract=ContractRef(**contract_meta) if contract_meta else None,
        snapshots=snapshots,
        steps=steps,
        drift_events=[DriftEventRow(**{
            k: e.get(k) for k in DriftEventRow.model_fields
        }) for e in drift_events],
        latest_columns=latest_columns,
    )
