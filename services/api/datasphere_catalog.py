"""SAP Datasphere Catalog REST client — headless inventory extraction path.

Lists spaces and repository objects (views, tables, flows, analytic models, …)
via the Datasphere Catalog API using the same OAuth2 client-credentials flow as
``datasphere.py``. This is the *default* extraction path: it runs without the
Datasphere CLI and reliably returns object lists and per-object metadata
(technicalName / objectType / businessName / status where the catalog exposes
them).

Honesty note on scope
----------------------
The Catalog REST API is dependable for *listings and metadata*. Full CSN /
object definitions are frequently NOT served by the catalog endpoints — that is
the CLI path's job (task B). Accordingly :meth:`CatalogClient.read_object_definition`
returns ``None`` whenever the catalog does not expose a usable definition,
rather than fabricating one.

Configuration reuses the existing settings (services/api/settings.py):
  DATASPHERE_BASE_URL       https://<tenant>.<region>.hcs.cloud.sap
  DATASPHERE_CLIENT_ID      OAuth2 client id
  DATASPHERE_CLIENT_SECRET  OAuth2 client secret
  DATASPHERE_TOKEN_URL      Optional override; defaults to {base_url}/oauth/token

This module makes its OWN sibling client (it does not import datasphere.py's
singleton) so the catalog path can be configured / pooled independently while
sharing the proven token-cache pattern.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any

import httpx

logger = logging.getLogger("dq_cockpit.datasphere.catalog")

# Datasphere Catalog API v1 path prefix
_CATALOG = "/api/v1/dwc/catalog"


class CatalogError(Exception):
    """Raised when the Datasphere Catalog API returns an unexpected response."""


class CatalogClient:
    """Thin HTTP client for the SAP Datasphere Catalog REST API.

    Thread-safe: the OAuth token is refreshed under a lock; each request opens a
    short-lived ``httpx.Client`` so the instance can be shared across FastAPI
    worker threads without connection-pool contention. Mirrors the token-cache
    approach of :class:`services.api.datasphere.DatasphereClient`.
    """

    def __init__(
        self,
        base_url: str,
        client_id: str,
        client_secret: str,
        token_url: str = "",
        timeout: float = 30.0,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._client_id = client_id
        self._client_secret = client_secret
        self._token_url = token_url or f"{self._base}/oauth/token"
        self._timeout = timeout
        self._token: str | None = None
        self._expires_at: float = 0.0
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Auth (same client-credentials flow + thread-safe cache as datasphere.py)
    # ------------------------------------------------------------------

    def _fetch_token(self) -> str:
        with httpx.Client(timeout=self._timeout) as client:
            resp = client.post(
                self._token_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                },
            )
        _raise_for_status(resp, "token fetch")
        payload = resp.json()
        token = payload["access_token"]
        expires_in = int(payload.get("expires_in", 3600))
        self._expires_at = time.monotonic() + expires_in - 60  # 60 s buffer
        return token

    def _token_header(self) -> dict[str, str]:
        with self._lock:
            if self._token is None or time.monotonic() >= self._expires_at:
                self._token = self._fetch_token()
        return {"Authorization": f"Bearer {self._token}"}

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    def _get(self, path: str, params: dict | None = None) -> Any:
        url = f"{self._base}{path}"
        with httpx.Client(timeout=self._timeout) as client:
            resp = client.get(
                url,
                params=params,
                headers={"Accept": "application/json", **self._token_header()},
            )
        _raise_for_status(resp, f"GET {path}")
        if not resp.content:
            return {}
        return resp.json()

    # ------------------------------------------------------------------
    # Catalog queries
    # ------------------------------------------------------------------

    def list_spaces(self) -> list[dict]:
        """List all spaces visible to the configured technical user.

        Catalog API:
          GET /api/v1/dwc/catalog/spaces  ->  {"value": [ {spaceId, ...}, ... ]}
        """
        data = self._get(f"{_CATALOG}/spaces")
        return _extract_list(data)

    def list_objects(self, space_id: str) -> list[dict]:
        """List repository objects (catalog metadata) for one space.

        Catalog API:
          GET /api/v1/dwc/catalog/spaces('{space_id}')/objects
            ->  {"value": [ {technicalName, objectType, businessName, status, ...}, ... ]}

        Returns the raw catalog object dicts; callers map them onto the inventory
        schema. Where the catalog omits fields (e.g. businessName), they are
        simply absent — no values are invented here.
        """
        path = f"{_CATALOG}/spaces({_odata_quote(space_id)})/objects"
        data = self._get(path)
        return _extract_list(data)

    def read_object_definition(
        self, space_id: str, technical_name: str
    ) -> dict | None:
        """Return a single object's CSN / definition when the catalog exposes it.

        Catalog API (best effort):
          GET /api/v1/dwc/catalog/spaces('{space_id}')/objects('{name}')

        The catalog object detail endpoint reliably returns metadata but often
        does NOT include the full CSN/definition — that is the CLI path's domain
        (task B). This method returns the embedded definition only when present,
        and otherwise ``None`` (including on HTTP 404/4xx, which we treat as
        "not available via catalog" rather than a hard failure).
        """
        path = (
            f"{_CATALOG}/spaces({_odata_quote(space_id)})"
            f"/objects({_odata_quote(technical_name)})"
        )
        try:
            data = self._get(path, {"$expand": "definition"})
        except CatalogError as exc:
            logger.debug(
                "object definition for %r/%r not available via catalog: %s",
                space_id,
                technical_name,
                exc,
            )
            return None
        return _extract_definition(data)


# ------------------------------------------------------------------
# Module-level factory (sibling to datasphere.get_client; NOT a shared singleton)
# ------------------------------------------------------------------

_client: CatalogClient | None = None
_client_lock = threading.Lock()


def get_catalog_client() -> CatalogClient | None:
    """Return a lazily-built :class:`CatalogClient`, or ``None`` if unconfigured.

    Reads the *effective* connector config (env vars win, then ``datasphere.yml``)
    so the REST/OAuth details can be set either via env or the connector UI. When
    base_url or client_id are missing the catalog path is considered unconfigured
    and ``None`` is returned so callers fall back to the CLI / file path.
    """
    from .connector_config import (
        effective_base_url,
        effective_client_id,
        effective_client_secret,
        effective_token_url,
    )
    from .settings import get_settings

    global _client
    settings = get_settings()
    base_url = effective_base_url(settings)
    client_id = effective_client_id(settings)
    if not base_url or not client_id:
        return None
    with _client_lock:
        if _client is None:
            _client = CatalogClient(
                base_url=base_url,
                client_id=client_id,
                client_secret=effective_client_secret(settings),
                token_url=effective_token_url(settings),
            )
    return _client


def reset_catalog_client() -> None:
    """Drop the cached client so the next call rebuilds it from current config.

    Call after the connector config changes via the UI (new base_url / secret).
    """
    global _client
    with _client_lock:
        _client = None


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _extract_list(data: Any) -> list[dict]:
    """Normalise OData-style {value: [...]} or plain list responses.

    Mirrors datasphere._extract_list so both clients agree on shape handling.
    """
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        for key in ("value", "objects", "items", "results"):
            inner = data.get(key)
            if isinstance(inner, list):
                return [item for item in inner if isinstance(item, dict)]
    return []


def _extract_definition(data: Any) -> dict | None:
    """Pull an embedded CSN/definition out of a catalog object-detail payload.

    Returns the definition dict if the catalog included one, else ``None``.
    """
    if not isinstance(data, dict):
        return None
    for key in ("definition", "csn", "csnDefinition"):
        value = data.get(key)
        if isinstance(value, dict) and value:
            return value
    return None


def _odata_quote(value: str) -> str:
    """Render an OData key segment: ('VALUE') with single-quotes escaped."""
    return "'" + value.replace("'", "''") + "'"


def _raise_for_status(resp: httpx.Response, context: str) -> None:
    if resp.is_error:
        raise CatalogError(
            f"Datasphere Catalog API {context} returned HTTP "
            f"{resp.status_code}: {resp.text[:200]}"
        )
