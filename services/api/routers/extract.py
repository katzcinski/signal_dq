"""Extract / inventory endpoints (WS1-2, WS2-6).

The analyzer chain extracts inventory and lineage snapshots from Datasphere when
connectivity is configured. In local mode we serve and refresh the snapshot files
on disk. `/inventory` backs the contract-editor object/column picker; lineage is
served by the dedicated `lineage` router.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
import threading
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from ..auth.provider import Principal, PrincipalDep, require_roles
from ..deps import StoreDep, get_environment, get_inventory, get_lineage, read_environments, write_environments

router = APIRouter(prefix="/api", tags=["extract"])
require_admin = require_roles("admin")
require_steward = require_roles("steward", "owner", "admin")

_ENV_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
_NO_LIVE_SOURCE_WARNING = "No live extraction source configured; nothing was extracted."


class ExtractIn(BaseModel):
    """Phase-1 trigger payload for the admin inventory tool."""

    environment: str | None = Field(default=None)
    profile: str | None = Field(default=None)
    spaces: list[str] = Field(default_factory=list)
    include_sql: bool = Field(default=True)
    force: bool = Field(default=False)


class EnvironmentConfigIn(BaseModel):
    host: str = Field(min_length=1, max_length=512)
    port: int = Field(default=443, ge=1, le=65535)
    user: str = Field(min_length=1, max_length=256)
    schema_: str = Field(min_length=1, max_length=256, alias="schema")
    password_ref: str = Field(default="", max_length=512)
    password: str = Field(default="", max_length=4096)
    clear_secret: bool = False

    model_config = {"populate_by_name": True}


_LATEST_STATUS: dict[str, Any] | None = None


def _run_drift_sweep(store: Any, settings: Any) -> dict[str, int]:
    """Run schema-drift persistence after a successful extract.

    Drift is additive: failures are counted but never fail the extract itself.
    """
    import json as _json

    import yaml as _yaml

    from ..schema_drift_service import inventory_columns_for, persist_and_alert

    summary = {"checked": 0, "drifted": 0, "breaking": 0, "errors": 0}
    try:
        inv_path = Path(settings.inventory_file)
        inventory = (
            (_json.loads(inv_path.read_text(encoding="utf-8")) or {}).get("objects", [])
            if inv_path.exists()
            else []
        )
        contracts_dir = Path(settings.contracts_dir)
        if not contracts_dir.exists():
            return summary
        for path in sorted(contracts_dir.glob("*.y*ml")):
            if path.name.endswith(".active.yml"):
                continue
            try:
                contract = _yaml.safe_load(path.read_text(encoding="utf-8")) or {}
                if contract.get("lifecycle", "draft") != "active":
                    continue
                cols = inventory_columns_for(inventory, contract.get("dataset") or contract.get("product") or "")
                if cols is None:
                    continue
                report = persist_and_alert(store, contract, cols)
                summary["checked"] += 1
                if report["findings"]:
                    summary["drifted"] += 1
                if report["summary"]["has_breaking"]:
                    summary["breaking"] += 1
            except Exception:  # noqa: BLE001 - one broken contract must not stop the sweep
                summary["errors"] += 1
    except Exception:  # noqa: BLE001 - drift is additive; extract stays successful
        summary["errors"] += 1
    return summary


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _artifact_paths(settings: Any) -> dict[str, str]:
    return {
        "inventory": str(settings.inventory_file),
        "lineage": str(settings.lineage_file),
    }


def _snapshot_timestamp(settings: Any) -> str | None:
    mtimes = [
        Path(fpath).stat().st_mtime
        for fpath in (settings.inventory_file, settings.lineage_file)
        if Path(fpath).exists()
    ]
    if not mtimes:
        return None
    return datetime.fromtimestamp(max(mtimes), tz=timezone.utc).isoformat()


def _counts(inventory: list[dict], lineage: dict) -> dict[str, int]:
    return {
        "lineage_nodes": len(lineage.get("nodes", [])),
        "lineage_edges": len(lineage.get("edges", [])),
        "inventory_items": len(inventory),
    }


def _mask_host(host: str) -> str:
    if not host:
        return ""
    if "." not in host:
        return "***"
    return f"***.{host.split('.', 1)[1]}"


def _safe_ref(ref: str) -> str:
    """Return the secret reference, masking any inline plain: value."""
    return "" if ref.startswith("plain:") else ref


def _legacy_config_view(name: str, cfg: dict[str, Any]) -> dict[str, Any]:
    from ..secrets import secret_status

    ref = str(cfg.get("password_ref") or "")
    has_inline = bool(cfg.get("password"))
    return {
        "name": name,
        "host": cfg.get("host", ""),
        "port": int(cfg.get("port", 443) or 443),
        "user": cfg.get("user", ""),
        "schema": cfg.get("schema", ""),
        "password_ref": _safe_ref(ref),
        "secret_configured": has_inline or bool(ref),
        "secret_available": has_inline or secret_status(ref),
    }


def _legacy_config_entry(body: EnvironmentConfigIn, existing: dict[str, Any] | None) -> dict[str, Any]:
    entry = dict(existing or {})
    entry.update(
        host=body.host.strip(),
        port=body.port,
        user=body.user.strip(),
        schema=body.schema_.strip(),
    )
    if body.clear_secret:
        entry.pop("password_ref", None)
        entry.pop("password", None)
    elif body.password_ref.strip():
        entry["password_ref"] = body.password_ref.strip()
        entry.pop("password", None)
    elif body.password:
        entry["password"] = body.password
        entry.pop("password_ref", None)
    return entry


def _validate_environment_name(name: str) -> None:
    if not _ENV_NAME_RE.match(name):
        raise HTTPException(status_code=422, detail="Invalid environment name.")


def _status_payload(
    *,
    op_id: str | None,
    status: str,
    environment: str,
    profile: str | None,
    spaces: list[str],
    source: str,
    current_step: str,
    counts: dict[str, int],
    settings: Any,
    started_at: str | None = None,
    updated_at: str | None = None,
    finished_at: str | None = None,
    warnings: list[str] | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    return {
        "op_id": op_id,
        "job_id": op_id,
        "status": status,
        "environment": environment,
        "profile": profile or environment,
        "spaces": spaces,
        "source": source,
        "started_at": started_at,
        "updated_at": updated_at or _utc_now_iso(),
        "finished_at": finished_at,
        "current_step": current_step,
        "counts": counts,
        "warnings": warnings or [],
        "error": error,
        "runtime_artifact_paths": _artifact_paths(settings),
        "published_snapshot_timestamp": _snapshot_timestamp(settings),
    }


@router.post("/extract", status_code=status.HTTP_202_ACCEPTED)
def trigger_extract(
    body: ExtractIn | None = Body(default=None),
    environment: str = Query(default="default"),
    principal: Principal = require_steward,
    store: StoreDep = ...,
    inventory: list[dict] = Depends(get_inventory),
    lineage: dict = Depends(get_lineage),
):
    """Start an operation-backed inventory extraction and return its ``op_id``."""
    from ..extraction import PROGRESS_META_PREFIX, run_extraction
    from ..settings import get_settings
    from ..sse import make_progress_callback

    settings = get_settings()
    selected_environment = (body.environment if body and body.environment else environment) or "default"
    profile = body.profile if body else None
    spaces = body.spaces if body else []
    op_id = str(uuid4())
    started_at = _utc_now_iso()
    baseline_counts = _counts(inventory, lineage)

    global _LATEST_STATUS
    _LATEST_STATUS = _status_payload(
        op_id=op_id,
        status="running",
        environment=selected_environment,
        profile=profile,
        spaces=spaces,
        source="datasphere",
        current_step="starting",
        counts=baseline_counts,
        settings=settings,
        started_at=started_at,
    )

    if not store.begin_operation(op_id, "inventory_extract", created_by=principal.sub):
        raise HTTPException(status_code=409, detail="Operation already exists.")

    space_override = spaces[0].strip() if spaces else None
    persist_progress = make_progress_callback(op_id, store)

    def _set_latest(
        *,
        current_status: str,
        current_step: str,
        current_counts: dict[str, int],
        source: str,
        updated_at: str | None = None,
        finished_at: str | None = None,
        warnings: list[str] | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        global _LATEST_STATUS
        _LATEST_STATUS = _status_payload(
            op_id=op_id,
            status=current_status,
            environment=selected_environment,
            profile=profile,
            spaces=spaces,
            source=source,
            current_step=current_step,
            counts=current_counts,
            settings=settings,
            started_at=started_at,
            updated_at=updated_at,
            finished_at=finished_at,
            warnings=warnings,
            error=error,
        )
        return _LATEST_STATUS

    def _emit_progress(line: str = "", meta: dict[str, Any] | None = None) -> None:
        if meta:
            persist_progress(
                f"{PROGRESS_META_PREFIX}{json.dumps({'kind': 'extract', **meta}, ensure_ascii=False, sort_keys=True)}"
            )
        if line:
            persist_progress(line)

    def _worker() -> None:
        try:
            _set_latest(
                current_status="running",
                current_step="extracting_objects",
                current_counts=baseline_counts,
                source="datasphere",
                updated_at=_utc_now_iso(),
            )
            result = run_extraction(
                settings,
                space_id=space_override or None,
                on_progress=lambda line: _emit_progress(line),
            )

            if result is None:
                finished_at = _utc_now_iso()
                warnings = [_NO_LIVE_SOURCE_WARNING]
                payload = {
                    **_set_latest(
                        current_status="skipped",
                        current_step="no_live_source",
                        current_counts=baseline_counts,
                        source="none",
                        updated_at=finished_at,
                        finished_at=finished_at,
                        warnings=warnings,
                    ),
                    "extracted_at": None,
                    "source": "none",
                    **baseline_counts,
                }
                _emit_progress(
                    _NO_LIVE_SOURCE_WARNING,
                    {"phase": "complete", "status": "skipped", "source": "none"},
                )
                store.finish_operation(op_id, "finished", result_json=json.dumps(payload))
                return

            live_counts = {
                "lineage_nodes": result["lineage_nodes"],
                "lineage_edges": result["lineage_edges"],
                "inventory_items": result["inventory_items"],
                "column_edges": result["column_edges"],
            }
            source = str(result.get("source") or "datasphere")

            _set_latest(
                current_status="running",
                current_step="schema_drift",
                current_counts=live_counts,
                source=source,
                updated_at=_utc_now_iso(),
            )
            _emit_progress(
                "Schema-drift sweep...",
                {"phase": "schema_drift", "status": "running", "source": source},
            )
            drift = _run_drift_sweep(store, settings)
            _emit_progress(
                (
                    "Schema-drift sweep complete: "
                    f"{drift['checked']} checked, {drift['drifted']} drifted, "
                    f"{drift['breaking']} breaking"
                ),
                {"phase": "schema_drift", "status": "finished", "source": source, **drift},
            )

            extracted_at = _snapshot_timestamp(settings) or _utc_now_iso()
            payload = {
                **_set_latest(
                    current_status="succeeded",
                    current_step="published_snapshot",
                    current_counts=live_counts,
                    source=source,
                    updated_at=extracted_at,
                    finished_at=extracted_at,
                ),
                "extracted_at": extracted_at,
                "source": source,
                "schema_drift": drift,
                **live_counts,
            }
            store.finish_operation(op_id, "finished", result_json=json.dumps(payload))
        except Exception as exc:  # noqa: BLE001 - surface extraction failure, never 500 silently
            error = f"Extraction failed: {exc}"
            finished_at = _utc_now_iso()
            _set_latest(
                current_status="failed",
                current_step="failed",
                current_counts=baseline_counts,
                source="datasphere",
                updated_at=finished_at,
                finished_at=finished_at,
                error=error,
            )
            _emit_progress(
                error,
                {"phase": "complete", "status": "failed", "source": "datasphere"},
            )
            store.finish_operation(op_id, "error", error=error)

    threading.Thread(target=_worker, daemon=True).start()
    return {"op_id": op_id}


@router.get("/extract/status")
def extract_status(
    principal: PrincipalDep,
    inventory: list[dict] = Depends(get_inventory),
    lineage: dict = Depends(get_lineage),
):
    """Latest extract status for the platform-admin inventory tool."""
    from ..settings import get_settings

    settings = get_settings()
    if _LATEST_STATUS is not None:
        return {
            **_LATEST_STATUS,
            "can_trigger": principal.has_role("steward", "owner", "admin"),
        }

    snapshot_ts = _snapshot_timestamp(settings)
    current_status = "succeeded" if snapshot_ts else "idle"
    return {
        **_status_payload(
            op_id=None,
            status=current_status,
            environment="default",
            profile="default",
            spaces=[],
            source="local",
            current_step="snapshot_loaded" if snapshot_ts else "waiting_for_first_extract",
            counts=_counts(inventory, lineage),
            settings=settings,
            finished_at=snapshot_ts,
        ),
        "can_trigger": principal.has_role("steward", "owner", "admin"),
    }


@router.get("/inventory")
def list_inventory(inventory: list[dict] = Depends(get_inventory)):
    """Object/column picker source for the ContractEditor autocomplete (U2)."""
    return {"datasets": inventory}


@router.get("/environments")
def list_environments():
    """Environment names for the run trigger dialog, never credentials."""
    from ..secrets import secret_status

    envs = read_environments()
    return {
        "environments": [
            {
                "name": name,
                "schema": (cfg or {}).get("schema", ""),
                "host": _mask_host(str((cfg or {}).get("host", ""))),
                "secret_status": bool((cfg or {}).get("password")) or secret_status((cfg or {}).get("password_ref")),
            }
            for name, cfg in envs.items()
        ]
    }


@router.get("/environments/config")
def list_environment_configs(principal: Principal = require_steward):
    """Legacy non-secret environment config endpoint."""
    envs = read_environments()
    return {
        "environments": [_legacy_config_view(name, cfg) for name, cfg in sorted(envs.items())],
        "can_edit": principal.has_role("admin"),
    }


@router.put("/environments/config/{name}")
def put_environment_config(
    name: str,
    body: EnvironmentConfigIn,
    principal: Principal = require_admin,
):
    _validate_environment_name(name)
    envs = read_environments()
    envs[name] = _legacy_config_entry(body, envs.get(name))
    write_environments(envs)
    return _legacy_config_view(name, envs[name])


@router.delete("/environments/config/{name}", status_code=status.HTTP_204_NO_CONTENT)
def delete_environment_config(name: str, principal: Principal = require_admin):
    envs = read_environments()
    if name not in envs:
        raise HTTPException(status_code=404, detail=f"Environment {name!r} not found.")
    del envs[name]
    write_environments(envs)


@router.post("/environments/{name}/test", status_code=status.HTTP_202_ACCEPTED)
def test_environment_connection(
    name: str,
    principal: PrincipalDep,
    store: StoreDep = ...,
):
    """Start a live HANA/Datasphere connection test for an environment."""
    import uuid

    from dq_core.connect.db_connection import check_connection
    from ..sse import make_progress_callback

    if not principal.has_role("steward", "owner", "admin"):
        raise HTTPException(status_code=403, detail="Connection tests require steward role or higher.")

    env_cfg = get_environment(name)
    if env_cfg is None:
        raise HTTPException(status_code=422, detail=f"Unknown environment {name!r}")

    op_id = str(uuid.uuid4())
    if not store.begin_operation(op_id, "connection_test", created_by=principal.sub):
        raise HTTPException(status_code=409, detail="Operation already exists.")

    def _worker() -> None:
        callback = make_progress_callback(op_id, store)
        try:
            result = check_connection(
                host=env_cfg.get("host", ""),
                port=int(env_cfg.get("port", 443)),
                user=env_cfg.get("user", ""),
                password=env_cfg.get("password", ""),
                schema=env_cfg.get("schema", ""),
                encrypt=bool(env_cfg.get("encrypt", True)),
                validate_cert=bool(env_cfg.get("validate_cert", True)),
                on_progress=callback,
                environment_name=name,
            )
            store.finish_operation(op_id, "finished", result_json=json.dumps(result))
        except Exception:  # noqa: BLE001 - internals stay out of the API result
            store.finish_operation(
                op_id,
                "error",
                error="Connection test failed to complete.",
            )

    threading.Thread(target=_worker, daemon=True).start()
    return {"op_id": op_id}
