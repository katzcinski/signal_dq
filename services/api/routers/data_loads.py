"""Datasphere data load status endpoints.

Proxies task-chain-run and replication-flow-run history from the
SAP Datasphere API (R7).  Returns 503 when Datasphere credentials are
not configured (DATASPHERE_BASE_URL / DATASPHERE_CLIENT_ID).
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ..datasphere import DatasphereError, get_client
from ..settings import get_settings

router = APIRouter(prefix="/api/datasphere", tags=["datasphere"])


class DataLoadOut(BaseModel):
    object_id: str
    load_type: str  # "task_chain" | "replication_flow"
    run_id: str | None = None
    status: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    duration_ms: int | None = None
    error_message: str | None = None
    triggered_by: str | None = None
    raw: dict[str, Any] = {}


def _client_or_503():
    client = get_client()
    if client is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "Datasphere API is not configured. "
                "Set DATASPHERE_BASE_URL and DATASPHERE_CLIENT_ID."
            ),
        )
    return client


def _normalise(raw: dict) -> DataLoadOut:
    """Map Datasphere API run dict → DataLoadOut."""
    return DataLoadOut(
        object_id=raw.get("objectId") or raw.get("technicalName") or "",
        load_type=raw.get("loadType") or raw.get("type") or "unknown",
        run_id=(
            raw.get("runId")
            or raw.get("id")
            or raw.get("taskChainRunId")
        ),
        status=(
            raw.get("status")
            or raw.get("state")
            or raw.get("runStatus")
        ),
        started_at=(
            raw.get("startTime")
            or raw.get("start_time")
            or raw.get("startedAt")
            or raw.get("createdAt")
        ),
        finished_at=(
            raw.get("endTime")
            or raw.get("end_time")
            or raw.get("finishedAt")
            or raw.get("completedAt")
        ),
        duration_ms=_to_ms(raw),
        error_message=raw.get("errorMessage") or raw.get("error") or raw.get("message"),
        triggered_by=raw.get("triggeredBy") or raw.get("createdBy") or raw.get("user"),
        raw=raw,
    )


def _to_ms(raw: dict) -> int | None:
    v = raw.get("durationMs") or raw.get("duration_ms") or raw.get("durationInMs")
    if v is not None:
        return int(v)
    return None


def _resolve_space(space: str | None) -> str:
    # Effective space: explicit query arg → env → connector.yml (UI). Mirrors the
    # client resolution in datasphere.get_client so a space configured via the
    # connector UI applies to data-loads too (not only DATASPHERE_SPACE_ID).
    if space:
        return space
    from ..connector_config import effective_space_id
    return effective_space_id(get_settings())


@router.get("/data-loads", response_model=list[DataLoadOut])
def list_data_loads(
    space: str | None = Query(default=None, description="Datasphere space ID"),
    top: int = Query(default=50, ge=1, le=200),
):
    """List recent data loads (task chains + replication flows) across all objects."""
    client = _client_or_503()
    space_id = _resolve_space(space)
    if not space_id:
        raise HTTPException(
            status_code=422,
            detail="Provide ?space= or set DATASPHERE_SPACE_ID in the environment.",
        )
    try:
        runs = client.get_data_loads(space_id=space_id, top=top)
    except DatasphereError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return [_normalise(r) for r in runs]


@router.get("/data-loads/{object_id}", response_model=list[DataLoadOut])
def get_object_data_loads(
    object_id: str,
    space: str | None = Query(default=None, description="Datasphere space ID"),
    top: int = Query(default=20, ge=1, le=100),
):
    """List recent data loads for a specific Datasphere object."""
    client = _client_or_503()
    space_id = _resolve_space(space)
    if not space_id:
        raise HTTPException(
            status_code=422,
            detail="Provide ?space= or set DATASPHERE_SPACE_ID in the environment.",
        )
    try:
        runs = client.get_data_loads(space_id=space_id, object_id=object_id, top=top)
    except DatasphereError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return [_normalise(r) for r in runs]
