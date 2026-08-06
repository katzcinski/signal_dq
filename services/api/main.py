"""FastAPI application factory. [ENGINE-FROZEN] dq_core is never modified here."""
from __future__ import annotations

import ipaddress
import logging
import sys
from pathlib import Path

# Ensure dq_core is importable
_root = Path(__file__).resolve().parents[2]
for _pkg in [str(_root / "packages"), str(_root)]:
    if _pkg not in sys.path:
        sys.path.insert(0, _pkg)

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .middleware import ObservabilityMiddleware
from .secrets import init_resolver
from .settings import get_settings
from .routers import library, objects, runs, lineage, contracts, incidents, proposals, stream, checks, extract, metrics, data_loads, activity, notifications, profile, operations, environments, products, schedules, monitoring, quarantine, enforcement, integrations, schema_drift, healing

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("dq_cockpit")


def _is_loopback_bind(host: str) -> bool:
    """S5: normalisierte Prüfung statt String-Vergleich — '::', '0:0::0',
    leere Strings und Hostnames werden korrekt als nicht-loopback erkannt."""
    if not host:
        return False
    if host in ("localhost",):
        return True
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return False  # Hostname → fail-closed behandeln
    return addr.is_loopback


def assert_bind_policy(settings) -> None:
    """S5 fail-closed: NoAuth darf nur auf Loopback binden."""
    if settings.auth_mode == "noauth" and not _is_loopback_bind(settings.bind_host):
        raise RuntimeError(
            f"SECURITY: BIND_HOST={settings.bind_host!r} ist nicht loopback und "
            "AUTH_MODE=noauth. Setze AUTH_MODE=oidc oder BIND_HOST=127.0.0.1."
        )


# S-1: fail-closed globales AuthN. Öffentliche Fläche ist eine explizite
# Allowlist — alles andere braucht im oidc-Modus einen gültigen Principal, auch
# Routen, die die per-Route-`PrincipalDep` vergessen. Im noauth-Modus (nur
# Loopback, S5) ist dies ein No-Op; der per-Route-Admin-Principal gilt weiter.
_PUBLIC_EXACT = {"/api/health"}
_PUBLIC_PREFIXES = ("/api/docs", "/api/redoc", "/api/openapi.json")


def _is_public_path(path: str) -> bool:
    return path in _PUBLIC_EXACT or path.startswith(_PUBLIC_PREFIXES)


def _is_monitoring_service_endpoint(request: Request) -> bool:
    """Die maschinellen Monitoring-Endpunkte (GET /manifest, PUT …/status)
    authentifizieren über ein Service-Token (`require_service_token`), nicht über
    einen Nutzer-Principal — vom OIDC-Zaun ausnehmen, damit der Token-Pfad greift."""
    path = request.url.path
    if request.method == "GET" and path == "/api/monitoring/manifest":
        return True
    if (
        request.method == "PUT"
        and path.startswith("/api/monitoring/shares/")
        and path.endswith("/status")
    ):
        return True
    return False


async def enforce_authentication(request: Request) -> None:
    if request.method == "OPTIONS":
        return  # CORS-Preflight trägt keine Credentials
    path = request.url.path
    if _is_public_path(path) or _is_monitoring_service_endpoint(request):
        return
    settings = get_settings()
    if settings.auth_mode == "noauth":
        return
    from .auth.oidc import get_oidc_principal

    get_oidc_principal(request.headers.get("authorization"))


def _problem(status_code: int, title: str, detail) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        media_type="application/problem+json",
        content={
            "type": "about:blank",
            "title": title,
            "detail": detail,
            "status": status_code,
        },
    )


def create_app() -> FastAPI:
    settings = get_settings()
    assert_bind_policy(settings)
    init_resolver(settings.secrets_file)

    app = FastAPI(
        title="DQ & Observability Cockpit API",
        version="0.1.0",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        # S-1: äußerer Zaun — greift vor jeder Route, opt-out statt opt-in.
        dependencies=[Depends(enforce_authentication)],
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    # Pure ASGI middleware — request-ID header propagation + access log + metrics.
    # Must be added after CORS so CORS runs first (innermost), observability outermost.
    app.add_middleware(ObservabilityMiddleware)

    # RFC-7807 für beide Pfade: HTTPException UND Unbehandeltes.
    @app.exception_handler(HTTPException)
    async def _http_error(request: Request, exc: HTTPException):
        return _problem(exc.status_code, exc.__class__.__name__, exc.detail)

    @app.exception_handler(Exception)
    async def _generic_error(request: Request, exc: Exception):
        # Interna gehören ins Log, nicht in die Response (S-14).
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return _problem(500, "Internal Server Error", "An internal error occurred.")

    from .routers import connector
    for router in [library.router, objects.router, runs.router, lineage.router,
                   contracts.router, incidents.router, proposals.router, stream.router,
                   checks.router, extract.router, metrics.router, data_loads.router,
                   activity.router, notifications.router, profile.router, operations.router,
                   environments.router, products.router, schedules.router,
                   monitoring.router, connector.router, quarantine.router,
                   enforcement.router, integrations.router, schema_drift.router,
                   healing.router]:
        app.include_router(router)

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    # Option E: start the in-process schedule poller when opted in. Each worker
    # runs its own poller; claim + try_begin_run keep that duplicate-free.
    if settings.scheduler_enabled:
        from . import scheduler
        scheduler.start(settings.scheduler_tick_seconds)
        logger.info("Scheduler poller enabled (tick=%ss)", settings.scheduler_tick_seconds)

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn
    settings = get_settings()
    uvicorn.run("services.api.main:app", host=settings.bind_host, port=settings.bind_port, reload=settings.debug)
