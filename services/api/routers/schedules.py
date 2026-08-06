"""Per-object scheduling toggle (Option E).

Scheduling is a property of an object, switchable between three states:

* **manual**   — no schedule row; the object only runs when triggered by hand.
* **internal** — ``mode=internal``; Signal's poller (services/api/scheduler.py)
  runs the object every ``interval_seconds``.
* **external** — ``mode=external``; an outside orchestrator (SAP Datasphere Task
  Chain, cron, Airflow → ``cli/dq_check_runner.py``) drives the cadence. Signal's
  poller never claims it; the row documents intent and stamps ``last_run`` so the
  cockpit still shows that the object is governed by a schedule.

There is at most one schedule per object (deterministic id ``obj:<object_id>``),
so the object-detail page can render a single toggle. Managing a schedule mirrors
the authority to trigger a run: steward role or higher.
"""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, status

from ..auth.provider import PrincipalDep
from ..deps import StoreDep, get_inventory
from ..schemas.schedule_schemas import ScheduleOut, ScheduleUpsertIn

router = APIRouter(tags=["schedules"])


def _schedule_id(object_id: str) -> str:
    return f"obj:{object_id}"


def _require_steward(principal) -> None:
    if not principal.has_role("steward", "owner", "admin"):
        raise HTTPException(
            status_code=403,
            detail="Managing schedules requires steward role or higher.",
        )


def _object_exists(inventory: list[dict], object_id: str) -> bool:
    return any(
        (o.get("id") or o.get("technicalName") or o.get("name")) == object_id
        for o in inventory
    )


@router.get("/api/schedules", response_model=list[ScheduleOut])
def list_schedules(principal: PrincipalDep, store: StoreDep = ...):
    """All schedules — the platform ops view across objects."""
    _require_steward(principal)
    return [ScheduleOut(**_coerce(s)) for s in store.list_schedules()]


@router.get("/api/objects/{object_id}/schedule", response_model=ScheduleOut | None)
def get_object_schedule(object_id: str, principal: PrincipalDep, store: StoreDep = ...):
    """The object's schedule, or null when scheduling is manual."""
    _require_steward(principal)
    sched = store.get_schedule(_schedule_id(object_id))
    return ScheduleOut(**_coerce(sched)) if sched else None


@router.put("/api/objects/{object_id}/schedule", response_model=ScheduleOut)
def upsert_object_schedule(
    object_id: str,
    principal: PrincipalDep,
    body: ScheduleUpsertIn = Body(...),
    store: StoreDep = ...,
    inventory: list[dict] = Depends(get_inventory),
):
    """Set the object's scheduling mode (internal/external) and cadence."""
    _require_steward(principal)
    if not _object_exists(inventory, object_id):
        raise HTTPException(status_code=404, detail=f"Object {object_id!r} not found")
    if body.mode == "internal" and body.interval_seconds < 60:
        raise HTTPException(
            status_code=422,
            detail="An internal schedule needs interval_seconds >= 60.",
        )

    sid = _schedule_id(object_id)
    existing = store.get_schedule(sid)
    if existing is None:
        sched = store.create_schedule(
            schedule_id=sid,
            object_id=object_id,
            mode=body.mode,
            interval_seconds=body.interval_seconds,
            environment=body.environment,
            execution_mode=body.execution_mode,
            enabled=body.enabled,
            created_by=principal.sub,
        )
    else:
        # Re-arm the next slot when (re)enabling an internal cadence so it fires
        # on the next tick rather than inheriting a stale due time.
        from datetime import datetime, timezone
        next_due = (
            datetime.now(timezone.utc).isoformat()
            if body.mode == "internal" and body.enabled
            else None
        )
        sched = store.update_schedule(
            sid,
            mode=body.mode,
            interval_seconds=body.interval_seconds,
            environment=body.environment,
            execution_mode=body.execution_mode,
            enabled=body.enabled,
            next_due_at=next_due,
        )
    return ScheduleOut(**_coerce(sched))


@router.delete("/api/objects/{object_id}/schedule", status_code=status.HTTP_204_NO_CONTENT)
def delete_object_schedule(object_id: str, principal: PrincipalDep, store: StoreDep = ...):
    """Back to manual scheduling for this object."""
    _require_steward(principal)
    if not store.delete_schedule(_schedule_id(object_id)):
        raise HTTPException(status_code=404, detail="No schedule for this object.")


def _coerce(row: dict) -> dict:
    """Map a raw dq_schedules row to the API shape (int enabled → bool)."""
    out = dict(row)
    out["enabled"] = bool(out.get("enabled"))
    out["interval_seconds"] = int(out.get("interval_seconds") or 0)
    return out
