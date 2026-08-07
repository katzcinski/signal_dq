"""Incident-Lifecycle (R4-1): persistente Breach-Episoden mit Status, Owner
und Aktions-Timeline. Die abgeleitete Sicht auf fehlgeschlagene Checks bleibt
unter /api/incidents/checks erhalten (Drilldown-Quelle)."""
from __future__ import annotations

import sqlite3

import yaml
from fastapi import APIRouter, Body, HTTPException, Query
from pathlib import Path
from pydantic import BaseModel

from ..auth.provider import PrincipalDep
from ..deps import StoreDep, get_inventory
from ..settings import get_settings

router = APIRouter(prefix="/api/incidents", tags=["incidents"])

VALID_INCIDENT_STATUS = {"open", "acknowledged", "investigating", "resolved"}
VALID_INCIDENT_KIND = {"internal_gate", "consumer_contract", "provider_contract"}


def _product_space(product: str) -> str:
    """Space of a product from inventory — drives space-scoped routing/mute (UX-N2)."""
    for obj in get_inventory():
        if (obj.get("id") or obj.get("technicalName") or obj.get("name")) == product:
            return str(obj.get("space", ""))
    return ""


def _contract_owner(product: str) -> tuple[str, list[str]]:
    """Return (owned_by, owners) from the contract file for notification routing."""
    base = Path(get_settings().contracts_dir)
    for ext in (".yaml", ".yml"):
        path = base / f"{product}{ext}"
        if path.exists():
            try:
                data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            except Exception:
                return "", []
            owners = data.get("owners") or []
            if not isinstance(owners, list):
                owners = [owners]
            return str(data.get("owned_by", "")), [str(o) for o in owners]
    return "", []


class IncidentTransitionIn(BaseModel):
    status: str | None = None
    owner: str | None = None
    note: str = ""


@router.get("")
def list_incidents(
    status: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    kind: str | None = Query(default=None),
    group: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    store: StoreDep = ...,
):
    if status and status not in VALID_INCIDENT_STATUS:
        raise HTTPException(status_code=422, detail=f"Unknown status {status!r}")
    if kind and kind not in VALID_INCIDENT_KIND:
        raise HTTPException(status_code=422, detail=f"Unknown kind {kind!r}")
    if group and group != "cluster":
        raise HTTPException(status_code=422, detail=f"Unknown group {group!r}")
    if group == "cluster":
        return store.list_incident_clusters(status=status, severity=severity, kind=kind, limit=limit, offset=offset)
    return store.list_incidents(status=status, severity=severity, kind=kind, limit=limit, offset=offset)


@router.get("/checks")
def list_failing_checks(
    severity: str | None = Query(default=None),
    dataset: str | None = Query(default=None),
    store: StoreDep = ...,
):
    """Derived view: breached check results within last 7 days (not a separate store)."""
    conn = sqlite3.connect(store.db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row

    where_clauses = [
        "cr.passed = 0",
        "cr.severity IN ('critical', 'fail')",
        "cr.state IN ('executed', 'error')",
        "r.started_at >= datetime('now', '-7 days')",
        "r.run_state = 'finished'",
    ]
    params: list = []
    if severity:
        where_clauses.append("cr.severity = ?")
        params.append(severity)
    if dataset:
        where_clauses.append("r.dataset = ?")
        params.append(dataset)

    sql = f"""
        SELECT
          cr.check_name,
          r.dataset,
          cr.severity,
          cr.expect_expr,
          cr.actual_value,
          cr.error_message,
          cr.state,
          r.run_id,
          r.started_at,
          r.schema_name
        FROM dq_check_results cr
        JOIN dq_runs r ON cr.run_id = r.run_id
        WHERE {' AND '.join(where_clauses)}
        ORDER BY r.started_at DESC
        LIMIT 200
    """
    rows = conn.execute(sql, params).fetchall()
    conn.close()

    # Stabile id für FE-Row-Keys (run_id × check_name ist eindeutig je Lauf).
    return [{**dict(r), "id": f"{r['run_id']}:{r['check_name']}"} for r in rows]


@router.get("/{incident_id}")
def get_incident(incident_id: int, store: StoreDep = ...):
    incident = store.get_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found")
    return incident


@router.get("/{incident_id}/rca")
def get_incident_rca(incident_id: int, store: StoreDep = ...):
    if not store.get_incident(incident_id):
        raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found")
    snapshot = store.get_incident_rca(incident_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail=f"RCA snapshot for incident {incident_id} not found")
    return snapshot


@router.post("/{incident_id}/transition")
def transition_incident(
    incident_id: int,
    principal: PrincipalDep,
    body: IncidentTransitionIn = Body(...),
    store: StoreDep = ...,
):
    """[AUTHZ] Statuswechsel/Assign/Note — jede Aktion landet in der Timeline."""
    if not principal.has_role("steward", "owner", "admin"):
        raise HTTPException(status_code=403, detail="Incident actions require steward role or higher.")
    if body.status and body.status not in VALID_INCIDENT_STATUS:
        raise HTTPException(status_code=422, detail=f"Unknown status {body.status!r}")

    # Snapshot pre-transition state to detect what actually changed.
    before = store.get_incident(incident_id)
    if not before:
        raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found")

    incident = store.transition_incident(
        incident_id, body.status, principal.name, owner=body.owner, note=body.note
    )
    if not incident:
        raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found")

    status_changed = body.status and body.status != before.get("status")
    owner_changed = body.owner is not None and body.owner != before.get("owner")
    if status_changed or owner_changed:
        try:
            from ..notify import notify_incident_transition
            owned_by, owners = _contract_owner(incident["product"])
            notify_incident_transition(
                product=incident["product"],
                incident_id=incident_id,
                severity=incident.get("severity", "fail"),
                title=incident.get("title", ""),
                action="status_changed" if status_changed else "assigned",
                actor=principal.name,
                note=body.note,
                new_status=body.status,
                new_owner=body.owner,
                owned_by=owned_by,
                owners=owners,
                settings=get_settings(),
                store=store,
                space=_product_space(incident["product"]),
                kind=incident.get("kind", "consumer_contract"),
            )
        except Exception:
            pass  # notifications are best-effort; never fail the API response

    return incident
