"""Server-Sent Events backed by the result store.

Progress is persisted in a generic stream. DQ Runs keep their historical event
names; Operations use generic terminal events with their result payload.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncGenerator

_POLL_INTERVAL_S = 0.5
_KEEPALIVE_EVERY = 30  # polls between keepalives


def _sse(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event)}\n\n"


def _parse_json(value: str | None) -> Any:
    if not value:
        return None
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return None


def _stream_state(store: Any, stream_id: str) -> dict[str, Any]:
    operation = store.get_operation(stream_id)
    if operation is not None:
        return {"kind": "operation", "operation": operation, "run": None}
    run = store.get_run(stream_id)
    if run is not None:
        return {"kind": "run", "operation": None, "run": run}
    return {"kind": "unknown", "operation": None, "run": None}


def _connected_event(stream_id: str, state: dict[str, Any]) -> dict[str, Any]:
    if state["kind"] == "operation":
        op = state["operation"]
        return {"type": "connected", "stream_id": stream_id, "op_id": stream_id, "kind": op.get("kind")}
    if state["kind"] == "run":
        return {"type": "connected", "stream_id": stream_id, "run_id": stream_id}
    return {"type": "connected", "stream_id": stream_id}


def _progress_event(stream_id: str, state: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    event = {
        "type": "progress",
        "stream_id": stream_id,
        "ts": row["ts"],
        "line": row["line"],
    }
    if state["kind"] == "operation":
        event["op_id"] = stream_id
    elif state["kind"] == "run":
        event["run_id"] = stream_id
    return event


async def sse_generator(store: Any, stream_id: str) -> AsyncGenerator[str, None]:
    """Stream progress and terminal state for a run or operation."""
    state = await asyncio.to_thread(_stream_state, store, stream_id)
    yield _sse(_connected_event(stream_id, state))

    if state["kind"] == "run":
        run = state["run"]
        yield _sse({"type": "run_started", "run_id": stream_id, "dataset": run["dataset"]})

    cursor = 0
    idle = 0
    while True:
        rows = await asyncio.to_thread(store.get_progress, stream_id, cursor)
        for row in rows:
            cursor = row["id"]
            yield _sse(_progress_event(stream_id, state, row))

        state = await asyncio.to_thread(_stream_state, store, stream_id)
        if state["kind"] == "operation":
            op = state["operation"]
            if op["state"] == "finished":
                yield _sse({
                    "type": "finished",
                    "op_id": stream_id,
                    "kind": op.get("kind"),
                    "result": _parse_json(op.get("result_json")),
                })
                return
            if op["state"] == "error":
                yield _sse({
                    "type": "error",
                    "op_id": stream_id,
                    "kind": op.get("kind"),
                    "error": op.get("error") or "Operation failed.",
                })
                return

        if state["kind"] == "run":
            run = state["run"]
            if run["run_state"] == "finished":
                yield _sse({
                    "type": "run_finished",
                    "run_id": stream_id,
                    "overall_status": run["overall_status"],
                })
                return
            if run["run_state"] == "error":
                yield _sse({
                    "type": "run_error",
                    "run_id": stream_id,
                    "error": "Run failed - see progress log.",
                })
                return

        idle += 1
        if idle >= _KEEPALIVE_EVERY:
            idle = 0
            yield ": keepalive\n\n"
        await asyncio.sleep(_POLL_INTERVAL_S)


def make_progress_callback(stream_id: str, store: Any) -> Any:
    """Return an on_progress callback that persists progress lines."""

    def callback(line: str) -> None:
        try:
            store.append_progress(stream_id, line)
        except Exception:
            pass

    return callback
