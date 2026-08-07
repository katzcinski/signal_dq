"""SAP Datasphere REST API client — data load status (R7).

Connects to the Datasphere Data Integration API using OAuth2 client credentials.
Fetches task chain runs and replication flow runs, normalised into a common
DataLoad structure.

Configure via environment variables:
  DATASPHERE_BASE_URL       https://<tenant>.<region>.hcs.cloud.sap
  DATASPHERE_CLIENT_ID      OAuth2 client id
  DATASPHERE_CLIENT_SECRET  OAuth2 client secret
  DATASPHERE_TOKEN_URL      Optional override; defaults to {base_url}/oauth/token
  DATASPHERE_SPACE_ID       Default space (e.g. SAP_DATASPHERE)
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any

import httpx

logger = logging.getLogger("dq_cockpit.datasphere")

# Datasphere API v1 path prefix
_API = "/api/v1/dwc"

# How many runs to fetch per object when listing all loads
_RUNS_PER_OBJECT = 10


class DatasphereError(Exception):
    """Raised when the Datasphere API returns an unexpected response."""


class DatasphereClient:
    """Thin HTTP client for the SAP Datasphere REST API.

    Thread-safe: token is refreshed under a lock; each request opens a
    short-lived httpx.Client so the instance can be shared across FastAPI
    worker threads without connection-pool contention.
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
    # Auth
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
            resp = client.get(url, params=params, headers=self._token_header())
        _raise_for_status(resp, f"GET {path}")
        return resp.json()

    def _post(self, path: str, payload: dict | None = None) -> Any:
        url = f"{self._base}{path}"
        with httpx.Client(timeout=self._timeout) as client:
            resp = client.post(url, json=payload, headers=self._token_header())
        _raise_for_status(resp, f"POST {path}")
        try:
            return resp.json()
        except ValueError:
            return {}

    # ------------------------------------------------------------------
    # Outbound actions (Slice ⑦) — Handeln auf dem Tenant, kein Daten-Schreiben.
    # Aufrufer (services.api.enforcement.trigger_remediation) erzwingt den
    # Opt-in DATASPHERE_ALLOW_TRIGGER und auditiert jede Auslösung.
    # ------------------------------------------------------------------

    def trigger_task_chain(self, space_id: str, chain: str) -> Any:
        """Task Chain über die öffentliche API starten (Review §4.3 R4)."""
        return self._post(f"/api/v1/datasphere/tasks/chains/{space_id}/run/{chain}")

    # ------------------------------------------------------------------
    # Data load queries
    # ------------------------------------------------------------------

    def get_task_chain_runs(
        self,
        space_id: str,
        technical_name: str | None = None,
        top: int = 50,
    ) -> list[dict]:
        """Task chain run history for a space (or a specific task chain).

        Datasphere API:
          GET /api/v1/dwc/dps/taskChains/{name}/runs?spaceId=…&$top=…
        """
        if technical_name:
            path = f"{_API}/dps/taskChains/{technical_name}/runs"
            params: dict[str, Any] = {"spaceId": space_id, "$top": top}
            data = self._get(path, params)
            runs = _extract_list(data)
            for r in runs:
                r.setdefault("objectId", technical_name)
                r.setdefault("loadType", "task_chain")
            return runs

        # No specific object: list all task chains and collect recent runs.
        chains_data = self._get(f"{_API}/dps/taskChains", {"spaceId": space_id})
        chains = _extract_list(chains_data)
        runs: list[dict] = []
        for chain in chains:
            name = chain.get("technicalName") or chain.get("id") or chain.get("name")
            if not name:
                continue
            try:
                run_data = self._get(
                    f"{_API}/dps/taskChains/{name}/runs",
                    {"spaceId": space_id, "$top": _RUNS_PER_OBJECT},
                )
                for r in _extract_list(run_data):
                    r.setdefault("objectId", name)
                    r.setdefault("loadType", "task_chain")
                    runs.append(r)
            except Exception as exc:
                logger.debug("task chain runs for %r: %s", name, exc)

        return _sort_runs(runs)[:top]

    def get_replication_flow_runs(
        self,
        space_id: str,
        technical_name: str | None = None,
        top: int = 50,
    ) -> list[dict]:
        """Replication flow run history.

        Datasphere API:
          GET /api/v1/dwc/dps/replicationFlows/{name}/runs?spaceId=…&$top=…
        """
        if technical_name:
            path = f"{_API}/dps/replicationFlows/{technical_name}/runs"
            data = self._get(path, {"spaceId": space_id, "$top": top})
            runs = _extract_list(data)
            for r in runs:
                r.setdefault("objectId", technical_name)
                r.setdefault("loadType", "replication_flow")
            return runs

        flows_data = self._get(f"{_API}/dps/replicationFlows", {"spaceId": space_id})
        flows = _extract_list(flows_data)
        runs: list[dict] = []
        for flow in flows:
            name = flow.get("technicalName") or flow.get("id") or flow.get("name")
            if not name:
                continue
            try:
                run_data = self._get(
                    f"{_API}/dps/replicationFlows/{name}/runs",
                    {"spaceId": space_id, "$top": _RUNS_PER_OBJECT},
                )
                for r in _extract_list(run_data):
                    r.setdefault("objectId", name)
                    r.setdefault("loadType", "replication_flow")
                    runs.append(r)
            except Exception as exc:
                logger.debug("replication flow runs for %r: %s", name, exc)

        return _sort_runs(runs)[:top]

    def get_data_loads(
        self,
        space_id: str,
        object_id: str | None = None,
        top: int = 50,
    ) -> list[dict]:
        """Aggregate data loads across task chains and replication flows.

        When object_id is given, only returns loads for that object.
        Results are sorted newest-first.
        """
        task_chain_runs = []
        replication_runs = []

        try:
            task_chain_runs = self.get_task_chain_runs(space_id, object_id, top)
        except DatasphereError as exc:
            logger.warning("task chain runs unavailable: %s", exc)

        try:
            replication_runs = self.get_replication_flow_runs(space_id, object_id, top)
        except DatasphereError as exc:
            logger.warning("replication flow runs unavailable: %s", exc)

        combined = task_chain_runs + replication_runs
        return _sort_runs(combined)[:top]


# ------------------------------------------------------------------
# Module-level singleton, initialised lazily
# ------------------------------------------------------------------

_client: DatasphereClient | None = None
_client_lock = threading.Lock()


def get_client() -> DatasphereClient | None:
    """Return the singleton DatasphereClient, or None if not configured.

    Reads the *effective* connector config (env vars win, then ``datasphere.yml``)
    so the REST/OAuth details can come from env or the connector UI.
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
            _client = DatasphereClient(
                base_url=base_url,
                client_id=client_id,
                client_secret=effective_client_secret(settings),
                token_url=effective_token_url(settings),
            )
    return _client


def reset_client() -> None:
    """Drop the cached client so the next call rebuilds from current config."""
    global _client
    with _client_lock:
        _client = None


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _extract_list(data: Any) -> list[dict]:
    """Normalise OData-style {value: [...]} or plain list responses."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("value", "runs", "items", "results"):
            if key in data and isinstance(data[key], list):
                return data[key]
    return []


def _sort_runs(runs: list[dict]) -> list[dict]:
    """Sort runs newest-first by startTime / start_time / createdAt."""
    def _key(r: dict) -> str:
        return (
            r.get("startTime")
            or r.get("start_time")
            or r.get("createdAt")
            or r.get("created_at")
            or ""
        )
    return sorted(runs, key=_key, reverse=True)


def _raise_for_status(resp: httpx.Response, context: str) -> None:
    if resp.is_error:
        raise DatasphereError(
            f"Datasphere API {context} returned HTTP {resp.status_code}: {resp.text[:200]}"
        )
