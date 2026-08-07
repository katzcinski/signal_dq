"""„Für Monitoring verfügbar machen" — Hybrid (ADR-0002, Monitoring-Hub).

Signal hält den Soll-Zustand, ein externes Skript reconciled Share + View:

  Cockpit  --POST /shares/{id}-->  Soll-Zustand (Registry, Status=requested)
  Skript   --GET  /manifest---->   liest Soll-Zustand (+ View-Name, Spalten, SQL)
  Skript   --PUT  /shares/{id}/status-->  meldet provisioned|error zurück
  Cockpit  --GET  /shares------->   zeigt Status je Objekt

Signal schreibt nie nach Datasphere — der Request-Endpunkt mutiert nur Signals
eigene Registry. Entfernen aus dem Soll-Zustand → das Skript droppt die
verwaiste View beim nächsten Reconcile.
"""
from __future__ import annotations

import hmac
import logging
from typing import Any

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Request

from ..auth.provider import Principal, get_principal, require_roles
from ..deps import get_inventory
from ..monitoring_share import (
    VALID_STATUS,
    build_projection_sql,
    load_entries,
    normalize_columns,
    remove_entry,
    set_status,
    upsert_request,
    view_name,
)
from ..settings import get_settings

logger = logging.getLogger("dq_cockpit.monitoring")

router = APIRouter(prefix="/api/monitoring", tags=["monitoring"])

# S-2: Vormerken/Entfernen sind Steward-Operationen wie der Run-Trigger.
require_steward = require_roles("steward", "owner", "admin")


async def require_service_token(
    request: Request,
    x_service_token: str | None = Header(default=None, alias="X-Service-Token"),
) -> None:
    """[AUTHZ] S-2: Gate für die maschinellen Endpunkte des Reconcile-Skripts.

    Ist ``MONITORING_SERVICE_TOKEN`` gesetzt, wird der Header ``X-Service-Token``
    erzwungen (konstante-Zeit-Vergleich). Ohne konfiguriertes Token — z. B. im
    lokalen Einzelbetrieb — greift ein Fallback auf einen steward+-Principal, so
    dass diese Endpunkte nie anonym offen stehen (spoofbarer Callback, S-2)."""
    configured = get_settings().monitoring_service_token
    if configured:
        if x_service_token and hmac.compare_digest(x_service_token, configured):
            return
        raise HTTPException(status_code=401, detail="Ungültiges oder fehlendes Service-Token.")
    principal = await get_principal(
        x_dq_role=request.headers.get("X-DQ-Role"),
        authorization=request.headers.get("authorization"),
    )
    if not principal.has_role("steward", "owner", "admin"):
        raise HTTPException(
            status_code=403,
            detail="Monitoring-Provisioning erfordert ein Service-Token oder die Steward-Rolle.",
        )


@router.get("/config")
def monitoring_config() -> dict[str, Any]:
    """``enabled`` = ein Monitoring-Hub ist konfiguriert (steuert UI-Sichtbarkeit)."""
    space = get_settings().datasphere_monitoring_space
    return {"enabled": bool(space), "monitoring_space": space}


@router.get("/shares")
def list_shares() -> dict[str, list[dict[str, Any]]]:
    """Status je vorgemerktem Objekt — für das Cockpit."""
    shares = [
        {"object_id": e["object_id"], "status": e["status"],
         "view": e.get("view"), "error": e.get("error")}
        for e in load_entries()
    ]
    return {"shares": shares}


@router.get("/manifest")
def manifest(_: None = Depends(require_service_token)) -> dict[str, Any]:
    """Soll-Zustand für das Provisioning-Skript: Identität + View-Name + Spalten
    + vorgeschlagenes (überschreibbares) Projektions-SQL je Objekt."""
    space = get_settings().datasphere_monitoring_space
    if not space:
        raise HTTPException(status_code=503, detail="Kein Monitoring-Space konfiguriert (DATASPHERE_MONITORING_SPACE).")
    entries = []
    for e in load_entries():
        entries.append({
            **{k: e[k] for k in ("object_id", "source_space", "technical_name", "object_type", "columns", "view", "status")},
            "projection_sql": build_projection_sql(
                monitoring_space=space, view=e["view"],
                source_space=e["source_space"], technical_name=e["technical_name"],
                columns=e.get("columns") or [],
            ),
        })
    return {"monitoring_space": space, "entries": entries}


def _resolve_object(object_id: str, inventory: list[dict]) -> dict:
    for obj in inventory:
        if object_id in (obj.get("id"), obj.get("technicalName"), obj.get("name")):
            return obj
    raise HTTPException(status_code=404, detail=f"Objekt {object_id} nicht im Inventar.")


@router.post("/shares/{object_id}")
def request_monitoring(
    object_id: str,
    principal: Principal = require_steward,
    inventory: list[dict] = Depends(get_inventory),
) -> dict[str, Any]:
    """Objekt fürs Monitoring vormerken (Soll-Zustand). Kein Datasphere-Write —
    das Provisioning übernimmt das Skript anhand des Manifests."""
    settings = get_settings()
    if not settings.datasphere_monitoring_space:
        raise HTTPException(status_code=503, detail="Kein Monitoring-Space konfiguriert (DATASPHERE_MONITORING_SPACE).")
    obj = _resolve_object(object_id, inventory)
    source_space = obj.get("space") or obj.get("schema") or ""
    technical_name = obj.get("technicalName") or obj.get("id") or object_id
    entry = upsert_request(
        object_id=object_id,
        source_space=source_space,
        technical_name=technical_name,
        object_type=obj.get("object_type") or "views",
        columns=normalize_columns(obj.get("columns")),
        view=view_name(source_space, object_id),
    )
    logger.info("Objekt %s fürs Monitoring vorgemerkt (View %s).", object_id, entry["view"])
    return entry


@router.put("/shares/{object_id}/status")
def report_status(
    object_id: str,
    body: dict = Body(...),
    _: None = Depends(require_service_token),
) -> dict[str, Any]:
    """Callback für das Provisioning-Skript: provisioned | error melden."""
    status = body.get("status")
    if status not in VALID_STATUS:
        raise HTTPException(status_code=422, detail=f"status muss eines von {sorted(VALID_STATUS)} sein.")
    entry = set_status(object_id, status, view=body.get("view"), error=body.get("error"))
    if entry is None:
        raise HTTPException(status_code=404, detail=f"{object_id} ist nicht im Soll-Zustand.")
    return entry


@router.delete("/shares/{object_id}")
def remove_monitoring(
    object_id: str,
    principal: Principal = require_steward,
) -> dict[str, Any]:
    """Aus dem Soll-Zustand entfernen. Das Skript droppt die verwaiste View beim
    nächsten Reconcile (Manifest = Soll; was nicht drinsteht, wird abgeräumt)."""
    removed = remove_entry(object_id)
    return {"status": "removed" if removed else "not_found", "object_id": object_id}
