"""Data profiling endpoint (Tier-2) — exposes dq_core.profile over a live HANA
connection.

Profiling runs aggregate-only queries (COUNT / COUNT DISTINCT / MIN / MAX /
MEDIAN, never SELECT *) by default and returns per-column statistics plus
primary-key candidates with name-based heuristic scoring. Optional sample rows
are a separate [PII-GATE] path: default off, projected to server-allowlisted
columns only.

[AUTHZ] Like a DQ run, profiling loads HANA — viewer must not trigger it.
Fail-closed (S-13): profiling requires a configured environment; it never runs
against the mock (which cannot produce meaningful statistics).
"""
from __future__ import annotations

import json
import logging
import threading
import uuid
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..auth.provider import PrincipalDep
from ..deps import StoreDep, get_environment, get_inventory
from ..sse import make_progress_callback
from ..settings import get_settings

logger = logging.getLogger("dq_cockpit.profile")

router = APIRouter(prefix="/api/objects", tags=["profile"])


class ProfileRequest(BaseModel):
    environment: str | None = None
    include_composite: bool = True
    include_samples: bool = False
    sample_limit: int = 20


class DiffRequest(BaseModel):
    """§B: Data-Diff zweier gespeicherter Profil-Snapshots. Ohne IDs werden die
    zwei jüngsten Snapshots des Objekts verglichen (base = älterer)."""
    base_snapshot_id: int | None = None
    head_snapshot_id: int | None = None
    mode: str = "distribution"          # distribution | keys
    key_columns: list[str] | None = None


def _sample_payload(
    *,
    enabled: bool,
    columns: list[str],
    rows: list[dict[str, Any]] | None = None,
    reason: str = "",
) -> dict[str, Any]:
    return {
        "enabled": enabled,
        "columns": columns,
        "rows": rows or [],
        "reason": reason,
    }


def _fetch_sample_rows(cursor: Any, schema: str, table: str, columns: list[str], limit: int) -> list[dict[str, Any]]:
    from dq_core.connect.query_helpers import jsonable, qualified, quote_identifier

    selected = ", ".join(quote_identifier(col) for col in columns)
    cursor.execute(f"SELECT {selected} FROM {qualified(schema, table)} LIMIT {limit}")
    names = [col[0] for col in (getattr(cursor, "description", None) or [])]
    raw_rows = cursor.fetchall()
    return [
        {name: jsonable(value) for name, value in zip(names, row)}
        for row in raw_rows
    ]


def _maybe_add_sample_rows(result: dict[str, Any], cursor: Any, schema: str, table: str, body: ProfileRequest) -> None:
    if not body.include_samples:
        return

    settings = get_settings()
    if not settings.allow_profile_samples:
        result["sample_rows"] = _sample_payload(
            enabled=False,
            columns=[],
            reason="Profile samples are disabled by server policy.",
        )
        return

    available = {str(col.get("column")) for col in result.get("columns", []) if col.get("column")}
    columns = [col for col in settings.profile_sample_columns if col in available]
    if not columns:
        result["sample_rows"] = _sample_payload(
            enabled=False,
            columns=[],
            reason="No profile sample columns are allowlisted.",
        )
        return

    limit = min(max(int(body.sample_limit or 20), 1), 50)
    try:
        result["sample_rows"] = _sample_payload(
            enabled=True,
            columns=columns,
            rows=_fetch_sample_rows(cursor, schema, table, columns, limit),
        )
    except Exception:  # noqa: BLE001 - sample rows are optional; keep aggregates usable.
        logger.warning("Sample-row profiling failed for %s.%s", schema, table, exc_info=True)
        result["sample_rows"] = _sample_payload(
            enabled=False,
            columns=columns,
            reason="Sample rows could not be read.",
        )


@router.post("/{object_id}/profile", status_code=status.HTTP_202_ACCEPTED)
def profile_object(
    object_id: str,
    principal: PrincipalDep,
    body: ProfileRequest = Body(default=ProfileRequest()),
    store: StoreDep = ...,
    inventory: list[dict] = Depends(get_inventory),
):
    """Profile one object's columns over a live HANA connection.

    Returns per-column stats, PK candidates (single + composite), and
    heuristic key scores. Requires steward role or higher and a configured
    environment with a real HANA connection.
    """
    if not principal.has_role("steward", "owner", "admin"):
        raise HTTPException(status_code=403, detail="Profiling requires steward role or higher.")

    obj = next(
        (o for o in inventory if (o.get("id") or o.get("technicalName") or o.get("name")) == object_id),
        None,
    )
    if not obj:
        raise HTTPException(status_code=404, detail=f"Object {object_id!r} not found")

    env_cfg = get_environment(body.environment) if body.environment else None
    if body.environment and env_cfg is None:
        raise HTTPException(status_code=422, detail=f"Unknown environment {body.environment!r}")
    if env_cfg is None:
        # [SCHEMA-MAP]/S-13: profiling needs real data — no mock fallback.
        raise HTTPException(
            status_code=422,
            detail="Profiling requires a configured environment with a live HANA connection.",
        )

    schema = env_cfg.get("schema") or obj.get("schema") or "LOCAL"  # [SCHEMA-MAP]
    table = obj.get("technicalName") or obj.get("name") or object_id

    op_id = str(uuid.uuid4())
    if not store.begin_operation(op_id, "profile", created_by=principal.sub):
        raise HTTPException(status_code=409, detail="Operation already exists.")

    def _worker() -> None:
        from dq_core.connect.db_connection import get_connection
        from dq_core.profile.heuristics import enrich_result_with_context
        from dq_core.profile.pk_detection import (
            analyze_composite_candidates,
            rank_single_candidates,
        )
        from dq_core.profile.profiler import profile_table

        callback = make_progress_callback(op_id, store)
        conn = None
        try:
            callback(f'Profiling fuer "{object_id}" wird vorbereitet ...')
            conn = get_connection(
                host=env_cfg.get("host", ""),
                port=int(env_cfg.get("port", 443)),
                user=env_cfg.get("user", ""),
                password=env_cfg.get("password", ""),
                schema=schema,
                on_progress=callback,
            )
            cursor = conn.cursor()

            callback(f'Profiliere "{schema}"."{table}" ...')
            result = profile_table(cursor, schema, table, on_progress=callback)
            result["view"] = table  # heuristics.enrich_result_with_context keys off 'view'

            callback("Bewerte Single-Column-Key-Kandidaten ...")
            ranked_single = rank_single_candidates(result["columns"])
            exact_combos: list = []
            ranked_composite: list = []
            search_meta: dict = {}
            if body.include_composite:
                callback("Pruefe Composite-Key-Kandidaten ...")
                exact_combos, ranked_composite, search_meta = analyze_composite_candidates(
                    result["columns"], ranked_single, cursor, schema, table, max_cols=3, on_progress=callback
                )

            result["pk_candidates"] = {
                "single": (result.get("pk_candidates") or {}).get("single", []),
                "composite": [list(c) for c in exact_combos],
                "ranked_single": ranked_single,
                "ranked_composite": ranked_composite,
                "search_meta": search_meta,
            }

            if body.include_samples:
                callback("Sample Rows [PII-GATE] pruefen ...")
            _maybe_add_sample_rows(result, cursor, schema, table, body)

            try:
                callback("Profiling-Ergebnis wird angereichert ...")
                result = enrich_result_with_context(result, obj)
            except Exception:  # noqa: BLE001 - heuristics are an enhancement; never fail the profile
                logger.warning("Heuristic enrichment failed for %s; returning base profile.", object_id, exc_info=True)
            # §B.3: Aggregat-Profil als Snapshot ablegen (Basis für Data-Diff).
            try:
                store.save_profile_snapshot(object_id, result, environment=body.environment or "")
            except Exception:  # noqa: BLE001 - Snapshot ist additiv; Profil bleibt nutzbar
                logger.warning("Profile snapshot persist failed for %s", object_id, exc_info=True)
            store.finish_operation(op_id, "finished", result_json=json.dumps(result))
        except RuntimeError as exc:
            store.finish_operation(op_id, "error", error=str(exc))
        except Exception:  # noqa: BLE001 - unexpected internals stay out of the API result
            logger.warning("Profile operation failed for %s", object_id, exc_info=True)
            store.finish_operation(op_id, "error", error="Profiling failed to complete.")
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:  # noqa: BLE001
                    pass

    threading.Thread(target=_worker, daemon=True).start()
    return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content={"op_id": op_id})


@router.post("/{object_id}/diff")
def diff_object(
    object_id: str,
    principal: PrincipalDep,
    body: DiffRequest = Body(default=DiffRequest()),
    store: StoreDep = ...,
):
    """§B.2/§B.3: Distribution- bzw. Key-Reconciliation-Diff zweier Profil-Snapshots.

    Liest ausschließlich gespeicherte Aggregat-Snapshots (kein HANA, keine
    Rohzeilen — G8). Snapshots entstehen bei `POST /objects/{id}/profile`."""
    from dq_core.profile.diff import diff_profiles, reconcile_keys

    if not principal.has_role("steward", "owner", "admin"):
        raise HTTPException(status_code=403, detail="Diff requires steward role or higher.")

    base_id = body.base_snapshot_id
    head_id = body.head_snapshot_id
    if base_id is None or head_id is None:
        snaps = store.list_profile_snapshots(object_id, limit=2)
        if len(snaps) < 2:
            raise HTTPException(
                status_code=422,
                detail="Mindestens zwei Profil-Snapshots nötig (erst profilieren).",
            )
        # list ist DESC (neuester zuerst): head = neuer, base = älter.
        head_id = head_id if head_id is not None else snaps[0]["id"]
        base_id = base_id if base_id is not None else snaps[1]["id"]

    base_snap = store.get_profile_snapshot(int(base_id))
    head_snap = store.get_profile_snapshot(int(head_id))
    if not base_snap or not head_snap:
        raise HTTPException(status_code=404, detail="Snapshot nicht gefunden.")

    base_stats = base_snap["stats"]
    head_stats = head_snap["stats"]

    result: dict[str, Any] = {
        "object_id": object_id,
        "mode": body.mode,
        "base": {"snapshot_id": base_snap["id"], "captured_at": base_snap["captured_at"],
                 "environment": base_snap["environment"]},
        "head": {"snapshot_id": head_snap["id"], "captured_at": head_snap["captured_at"],
                 "environment": head_snap["environment"]},
    }

    if body.mode == "keys":
        key_columns = body.key_columns or (base_stats.get("pk_candidates") or {}).get("single") or []
        result["reconciliation"] = reconcile_keys(base_stats, head_stats, key_columns)
    else:
        result["distribution"] = diff_profiles(base_stats, head_stats)
    return result
