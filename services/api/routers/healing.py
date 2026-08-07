"""Healing-Workbench (Konzept_Manuelles_Healing H1/H3).

Zwei Wege, eine Oberfläche:

* **H1 — Parkbucht-Korrektur** (`steward+`): Werte geparkter Quarantäne-Zeilen
  korrigieren. Wirkt episodisch, überlebt keinen Reload. Vor der Freigabe läuft
  der Re-Check gegen dasselbe Prädikat, das die Zeilen quarantänisiert hat.
* **H3 — Patch-Overlay** (`owner+`): dauerhafte Korrektur über
  `DQ_PATCH_<OBJ>` + `V_DQ_HEALED_<OBJ>`; überlebt Reloads, ist reversibel und
  je Feld auditiert.

Beides schreibt ausschließlich im Signal-Schema — die Quelle bleibt read-only
(ADR-0002). Der Result-Store ist die Wahrheit; die HANA-Projektion ist opt-in
(`ENFORCEMENT_MATERIALIZE_ENABLED`) und wird je Eintrag über `applied`
ausgewiesen, nie stillschweigend unterschlagen (G6).

G8 bleibt unangetastet: dieser Router liefert **keine** Rohzeilen aus. Der
Nutzer benennt Zeilenschlüssel und Zielwert; die Anzeige der Zeileninhalte
läuft weiterhin über den gegateten Diagnostics-/Profil-Pfad.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import BaseModel, Field

from dq_core.enforce.healing import HealingError, build_patch_spec

from ..auth.provider import PrincipalDep
from ..deps import StoreDep, get_inventory
from ..healing import (
    apply_correction, apply_patch, contract_kind_of, key_columns_of,
    object_columns, requires_four_eyes, revoke_patch, run_recheck,
    source_of, split_spec_for,
)
from ..settings import get_settings

router = APIRouter(prefix="/api/healing", tags=["healing"])


def _require_steward(principal) -> None:
    if not principal.has_role("steward", "owner", "admin"):
        raise HTTPException(status_code=403, detail="Healing requires steward role or higher.")


def _require_owner(principal) -> None:
    if not principal.has_role("owner", "admin"):
        raise HTTPException(status_code=403, detail="Patch overlays require owner role or higher.")


class CorrectionIn(BaseModel):
    keys: dict[str, str] = Field(..., description="Zeilenschlüssel {Spalte: Wert}")
    column: str
    new_value: str
    before_value: Optional[str] = None
    reason: str = Field(default="", max_length=500)


class PatchIn(BaseModel):
    object_id: str
    keys: dict[str, str]
    values: dict[str, str]
    reason: str = Field(default="", max_length=500)
    valid_until: Optional[str] = None
    key_columns: Optional[list[str]] = None
    patch_columns: Optional[list[str]] = None


def _patch_spec_for(object_id: str, inventory: list[dict], settings,
                    *, key_columns: list[str] | None, patch_columns: list[str] | None):
    """Overlay-Zuschnitt bauen — Schlüssel aus dem Inventar, sofern nicht
    explizit angegeben."""
    source = source_of(inventory, object_id, settings)
    if not source:
        raise HTTPException(status_code=422, detail=f"Object {object_id!r} not in inventory (no schema).")
    columns = [
        str(c.get("name")) for c in object_columns(inventory, object_id)
        if isinstance(c, dict) and c.get("name")
    ]
    keys = list(key_columns or key_columns_of(inventory, object_id))
    if not keys:
        raise HTTPException(
            status_code=422,
            detail="No key columns known for this object — pass key_columns explicitly.",
        )
    patches = list(patch_columns or [c for c in columns if c not in keys])
    try:
        return build_patch_spec(
            object_id, source, key_columns=keys, patch_columns=patches, all_columns=columns,
        )
    except HealingError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/overview")
def healing_overview(principal: PrincipalDep, store: StoreDep = ...):
    """Einstieg der Workbench: heilbare Episoden + aktive Patches je Objekt."""
    _require_steward(principal)
    settings = get_settings()
    from ..enforcement import materialization_enabled

    episodes = [
        e for e in store.list_quarantine(limit=200)
        if e.get("status") in ("open", "reconciled")
    ]
    corrections = store.list_healing_corrections(limit=500)
    patches = store.list_healing_patches(limit=500)

    by_episode: dict[int, int] = {}
    for c in corrections:
        by_episode[c["episode_id"]] = by_episode.get(c["episode_id"], 0) + 1

    rows = []
    for e in episodes:
        rows.append({
            "episode_id": e["id"],
            "object_id": e.get("product", ""),
            "status": e.get("status"),
            "row_count": e.get("row_count"),
            "failed_checks": e.get("failed_checks", []),
            "opened_at": e.get("opened_at"),
            "corrections": by_episode.get(e["id"], 0),
            "kind": contract_kind_of(e.get("product", ""), settings),
            "four_eyes": requires_four_eyes(e.get("product", ""), settings),
        })

    return {
        "materialization_enabled": materialization_enabled(settings),
        "signal_schema": settings.datasphere_signal_schema,
        "episodes": rows,
        "patches": [p for p in patches if p["status"] == "active"],
        "patches_total": len(patches),
        "corrections_total": len(corrections),
    }


@router.get("/episodes/{episode_id}")
def episode_detail(episode_id: int, principal: PrincipalDep, store: StoreDep = ...):
    """Episode + korrigierbare Spalten + bisherige Korrekturen + Re-Check."""
    _require_steward(principal)
    episode = store.get_quarantine(episode_id)
    if not episode:
        raise HTTPException(status_code=404, detail=f"Quarantine episode {episode_id} not found")

    settings = get_settings()
    inventory = get_inventory()
    object_id = episode.get("product", "")
    spec = split_spec_for(settings, inventory, object_id)
    columns = [
        str(c.get("name")) for c in object_columns(inventory, object_id)
        if isinstance(c, dict) and c.get("name")
    ]
    remaining = run_recheck(settings, spec, episode_id) if spec is not None else None

    return {
        "episode": episode,
        "object_id": object_id,
        "kind": contract_kind_of(object_id, settings),
        "four_eyes": requires_four_eyes(object_id, settings),
        "columns": columns,
        "key_columns": key_columns_of(inventory, object_id),
        # G6: nicht zeilenfähige Prädikate sind sichtbar, nicht still weg.
        "row_capable": spec is not None and bool(spec.predicates),
        "predicates": [
            {"check": p.check_name, "type": p.check_type} for p in (spec.predicates if spec else [])
        ],
        "skipped": [
            {"check": s.check_name, "type": s.check_type, "reason": s.reason}
            for s in (spec.skipped if spec else [])
        ],
        "remaining_bad_rows": remaining,
        "release_ready": remaining == 0,
        "corrections": store.list_healing_corrections(episode_id=episode_id),
        "correction_actors": sorted(store.correction_actors(episode_id)),
    }


@router.post("/episodes/{episode_id}/corrections", status_code=201)
def create_correction(
    episode_id: int,
    principal: PrincipalDep,
    body: CorrectionIn = Body(...),
    store: StoreDep = ...,
):
    """H1: Wert einer geparkten Zeile korrigieren (`steward+`).

    Der Eintrag wird immer im Store auditiert; die HANA-Projektion läuft nur
    bei aktiver Materialisierung und wird über `applied` ausgewiesen."""
    _require_steward(principal)
    episode = store.get_quarantine(episode_id)
    if not episode:
        raise HTTPException(status_code=404, detail=f"Quarantine episode {episode_id} not found")
    if episode.get("status") not in ("open", "reconciled"):
        raise HTTPException(
            status_code=409,
            detail=f"Episode is {episode.get('status')!r} — only open/reconciled episodes are healable.",
        )

    settings = get_settings()
    inventory = get_inventory()
    object_id = episode.get("product", "")
    spec = split_spec_for(settings, inventory, object_id)
    if spec is None:
        raise HTTPException(
            status_code=409,
            detail="No row-level quarantine spec for this object — healing works on the parked rows.",
        )

    applied, error = False, ""
    try:
        applied, error = apply_correction(
            settings, spec, episode_id=episode_id, keys=body.keys, column=body.column,
            new_value=body.new_value, actor=principal.name, reason=body.reason,
        )
    except HealingError as exc:
        # Unsichere/unbekannte Bezeichner → Eingabefehler, nichts wird auditiert.
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    correction = store.add_healing_correction(
        object_id=object_id, episode_id=episode_id, row_key=body.keys,
        column_name=body.column, before_value=body.before_value,
        after_value=body.new_value, reason=body.reason, actor=principal.name,
        applied=applied, apply_error=error,
    )
    remaining = run_recheck(settings, spec, episode_id)
    return {
        "correction": correction,
        "remaining_bad_rows": remaining,
        "release_ready": remaining == 0,
    }


@router.post("/episodes/{episode_id}/recheck")
def recheck_episode(episode_id: int, principal: PrincipalDep, store: StoreDep = ...):
    """Re-Check gegen das ursprüngliche Bad-Prädikat — Vorbedingung der Freigabe."""
    _require_steward(principal)
    episode = store.get_quarantine(episode_id)
    if not episode:
        raise HTTPException(status_code=404, detail=f"Quarantine episode {episode_id} not found")
    settings = get_settings()
    spec = split_spec_for(settings, get_inventory(), episode.get("product", ""))
    if spec is None or not spec.predicates:
        raise HTTPException(
            status_code=409,
            detail="No row-level predicate for this object — release is governed by the object gate.",
        )
    remaining = run_recheck(settings, spec, episode_id)
    return {
        "episode_id": episode_id,
        "remaining_bad_rows": remaining,
        "release_ready": remaining == 0,
        "materialized": remaining is not None,
    }


# --------------------------------------------------------------------------- #
# H3 — Patch-Overlay
# --------------------------------------------------------------------------- #

@router.get("/patches")
def list_patches(
    principal: PrincipalDep,
    object_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
    store: StoreDep = ...,
):
    _require_steward(principal)
    if status and status not in {"active", "revoked", "expired"}:
        raise HTTPException(status_code=422, detail=f"Unknown status {status!r}")
    return {"patches": store.list_healing_patches(object_id=object_id, status=status)}


@router.post("/patches", status_code=201)
def create_patch(
    principal: PrincipalDep,
    body: PatchIn = Body(...),
    store: StoreDep = ...,
):
    """H3: dauerhaften Patch setzen (`owner+`) — überlebt Reloads, wirkt über
    `V_DQ_HEALED_<OBJ>`. Ein neuer Patch auf denselben Schlüssel ersetzt den
    vorigen, damit die View nie zwei Wahrheiten kennt."""
    _require_owner(principal)
    settings = get_settings()
    inventory = get_inventory()
    spec = _patch_spec_for(
        body.object_id, inventory, settings,
        key_columns=body.key_columns, patch_columns=body.patch_columns,
    )
    if body.valid_until:
        try:
            datetime.fromisoformat(body.valid_until.replace("Z", "+00:00"))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="valid_until must be ISO-8601") from exc

    patch_id = str(uuid.uuid4())
    try:
        applied, error = apply_patch(
            settings, spec, patch_id=patch_id, keys=body.keys, values=body.values,
            actor=principal.name, reason=body.reason, valid_until=body.valid_until,
        )
    except HealingError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    patch = store.upsert_healing_patch(
        patch_id=patch_id, object_id=body.object_id, keys=body.keys, values=body.values,
        reason=body.reason, actor=principal.name, valid_until=body.valid_until,
        applied=applied, apply_error=error,
    )
    return {
        "patch": patch,
        "patch_table": spec.patch_table,
        "healed_view": spec.healed_view,
    }


@router.post("/patches/{patch_id}/revoke")
def revoke_patch_route(patch_id: str, principal: PrincipalDep, store: StoreDep = ...):
    """Patch zurücknehmen — die Zeile bleibt als Audit stehen (`owner+`)."""
    _require_owner(principal)
    existing = store.get_healing_patch(patch_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Patch {patch_id} not found")
    try:
        patch = store.revoke_healing_patch(patch_id, principal.name)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    settings = get_settings()
    try:
        spec = _patch_spec_for(
            existing["object_id"], get_inventory(), settings,
            key_columns=list(existing.get("keys") or {}) or None, patch_columns=None,
        )
        revoke_patch(settings, spec, patch_id)
    except HTTPException:
        pass  # Store-Rücknahme gilt; die Projektion holt der nächste Apply nach
    return {"patch": patch}


@router.get("/plan")
def healing_plan(
    principal: PrincipalDep,
    object_id: str = Query(...),
    store: StoreDep = ...,
):
    """DDL-Vorschau der Healing-Artefakte eines Objekts (Dry-Run, `steward+`):
    Schattenspalten der Parkbucht (H1) sowie Patch-Tabelle und Healed-View (H3)."""
    _require_steward(principal)
    settings = get_settings()
    inventory = get_inventory()
    from dq_core.enforce import healing as heal_sql
    from ..enforcement import materialization_enabled

    schema = settings.datasphere_signal_schema or "SIGNAL_SCHEMA"
    out: dict[str, Any] = {
        "object_id": object_id,
        "enabled": materialization_enabled(settings),
        "signal_schema": settings.datasphere_signal_schema,
        "h1": None,
        "h3": None,
    }

    spec = split_spec_for(settings, inventory, object_id)
    if spec is not None:
        out["h1"] = {
            "quarantine_table": spec.quarantine_table,
            "upgrade": heal_sql.heal_upgrade_statements(spec, schema),
            "procedure": heal_sql.correct_row_procedure_ddl().replace("{signal_schema}", schema),
            "row_capable": bool(spec.predicates),
        }

    try:
        patch_spec = _patch_spec_for(object_id, inventory, settings, key_columns=None, patch_columns=None)
    except HTTPException:
        patch_spec = None
    if patch_spec is not None:
        out["h3"] = {
            "patch_table": patch_spec.patch_table,
            "healed_view": patch_spec.healed_view,
            "key_columns": patch_spec.key_columns,
            "patch_columns": patch_spec.patch_columns,
            "ddl": [
                heal_sql.patch_table_ddl(patch_spec, schema),
                heal_sql.healed_view_ddl(patch_spec, schema),
            ],
        }
    return out
