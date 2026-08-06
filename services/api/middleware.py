"""Self-observability: request-ID injection, access logging, in-memory metrics.

Uses a pure ASGI middleware class (not BaseHTTPMiddleware) so it is
transparent to StreamingResponse / SSE — it never buffers the body.
"""
from __future__ import annotations

import logging
import time
import uuid
from typing import Any

logger = logging.getLogger("dq_cockpit")

# ---------------------------------------------------------------------------
# In-memory metrics (module-level singleton, single-process)
# ---------------------------------------------------------------------------

_metrics: dict[str, Any] = {
    "requests_total": 0,
    "requests_4xx": 0,
    "requests_5xx": 0,
    "started_at": time.time(),
}
_latencies: list[float] = []  # ring-buffer of last N request durations (ms)
_MAX_LATENCY_SAMPLES = 1000


def get_metrics() -> dict[str, Any]:
    """Point-in-time snapshot of service health metrics."""
    samples = sorted(_latencies)
    def _p(pct: float) -> float | None:
        if not samples:
            return None
        return round(samples[int(len(samples) * pct)], 1)

    return {
        "requests_total": _metrics["requests_total"],
        "requests_4xx": _metrics["requests_4xx"],
        "requests_5xx": _metrics["requests_5xx"],
        "uptime_s": round(time.time() - _metrics["started_at"], 1),
        "latency_p50_ms": _p(0.50),
        "latency_p95_ms": _p(0.95),
        "latency_p99_ms": _p(0.99),
    }


# ---------------------------------------------------------------------------
# ASGI middleware
# ---------------------------------------------------------------------------

class ObservabilityMiddleware:
    """Pure ASGI middleware: request-ID + access log + in-memory counters.

    Does not use BaseHTTPMiddleware so SSE / StreamingResponse flows are not
    interrupted — only the http.response.start message is inspected.
    """

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # --- Request-ID: use caller-supplied header or generate fresh UUID ---
        raw_headers: list[tuple[bytes, bytes]] = scope.get("headers", [])
        req_id = next(
            (v.decode() for k, v in raw_headers if k.lower() == b"x-request-id"),
            str(uuid.uuid4()),
        )

        # Store in scope for downstream access (compatible with both dict and State).
        state = scope.get("state")
        if state is None:
            scope["state"] = {"request_id": req_id}
        elif isinstance(state, dict):
            state["request_id"] = req_id
        else:
            # Starlette State object
            try:
                state.request_id = req_id
            except Exception:
                pass

        method = scope.get("method", "?")
        path = scope.get("path", "?")
        start = time.perf_counter()
        status_holder: list[int] = [200]

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                status_holder[0] = message.get("status", 200)
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", req_id.encode()))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_wrapper)

        duration_ms = (time.perf_counter() - start) * 1000
        status = status_holder[0]

        _metrics["requests_total"] += 1
        if 400 <= status < 500:
            _metrics["requests_4xx"] += 1
        elif status >= 500:
            _metrics["requests_5xx"] += 1

        _latencies.append(duration_ms)
        if len(_latencies) > _MAX_LATENCY_SAMPLES:
            _latencies.pop(0)

        logger.info(
            "request_id=%s method=%s path=%s status=%d duration_ms=%.1f",
            req_id, method, path, status, round(duration_ms, 1),
        )
