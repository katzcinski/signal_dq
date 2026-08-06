from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from ..auth.provider import PrincipalDep
from ..deps import StoreDep
from ..sse import sse_generator

router = APIRouter(prefix="/api/operations", tags=["operations"])


def _parse_result(value: str | None) -> Any:
    if not value:
        return None
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return None


def _require_operation_access(operation: dict[str, Any], principal) -> None:
    if principal.has_role("admin"):
        return
    if operation.get("created_by") == principal.sub:
        return
    raise HTTPException(status_code=403, detail="Operation access requires admin or creator.")


@router.get("/{op_id}")
def get_operation(op_id: str, principal: PrincipalDep, store: StoreDep = ...):
    operation = store.get_operation(op_id)
    if operation is None:
        raise HTTPException(status_code=404, detail=f"Operation {op_id!r} not found")
    _require_operation_access(operation, principal)
    return {
        "op_id": operation["op_id"],
        "kind": operation.get("kind", ""),
        "state": operation.get("state", ""),
        "created_by": operation.get("created_by", ""),
        "started_at": operation.get("started_at"),
        "finished_at": operation.get("finished_at"),
        "result": _parse_result(operation.get("result_json")),
        "error": operation.get("error"),
        "progress": store.get_progress(op_id),
    }


@router.get("/{op_id}/events")
def get_operation_events(op_id: str, principal: PrincipalDep, store: StoreDep = ...):
    operation = store.get_operation(op_id)
    if operation is None:
        raise HTTPException(status_code=404, detail=f"Operation {op_id!r} not found")
    _require_operation_access(operation, principal)
    return StreamingResponse(
        sse_generator(store, op_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
