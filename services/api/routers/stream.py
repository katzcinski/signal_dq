from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from ..deps import StoreDep
from ..sse import sse_generator

router = APIRouter(prefix="/api/stream", tags=["stream"])


@router.get("")
def stream_events(run_id: str, store: StoreDep = ...):
    """SSE für einen Run — Store-getrieben, multi-worker-fest (F2/A5).

    Polling-Fallback mit identischem Inhalt: /api/runs/{id}/events.
    """
    if not run_id:
        raise HTTPException(status_code=422, detail="run_id is required")
    return StreamingResponse(
        sse_generator(store, run_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # nginx proxy buffering disable
        },
    )
