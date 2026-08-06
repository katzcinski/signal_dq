"""Quarantäne-Episoden (Enforcement-Achse): persistente Verdicts mit
Lifecycle open → reconciled → released → resolved (+ superseded).

Signal speichert nur Counts + Prädikat-Träger (Check-Namen) — die Rohzeilen
leben in HANA/Datasphere (G8); Drilldown läuft über den bestehenden, gegateten
Diagnostics-Pfad. Freigabe und Reprocess-Bestätigung sind rollen-gegated."""
from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import BaseModel

from ..auth.provider import PrincipalDep
from ..deps import StoreDep

router = APIRouter(prefix="/api/quarantine", tags=["quarantine"])

VALID_QUARANTINE_STATUS = {"open", "reconciled", "released", "resolved", "superseded"}


class QuarantineActionIn(BaseModel):
    note: str = ""


class QuarantineReconcileIn(BaseModel):
    row_count: int


@router.get("")
def list_quarantine(
    status: str | None = Query(default=None),
    product: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    store: StoreDep = ...,
):
    if status and status not in VALID_QUARANTINE_STATUS:
        raise HTTPException(status_code=422, detail=f"Unknown status {status!r}")
    return store.list_quarantine(status=status, product=product, limit=limit, offset=offset)


@router.get("/{quarantine_id}")
def get_quarantine(quarantine_id: int, store: StoreDep = ...):
    episode = store.get_quarantine(quarantine_id)
    if not episode:
        raise HTTPException(status_code=404, detail=f"Quarantine episode {quarantine_id} not found")
    return episode


@router.post("/{quarantine_id}/release")
def release_quarantine(
    quarantine_id: int,
    principal: PrincipalDep,
    body: QuarantineActionIn = Body(default=QuarantineActionIn()),
    store: StoreDep = ...,
):
    """[AUTHZ] Freigabe ist eine Governance-Entscheidung — steward+.

    Healing-Vorbedingungen (Konzept_Manuelles_Healing §2), sobald an dieser
    Episode korrigiert wurde:
    * **Vier-Augen** bei Contract-Kinds — Korrigierender ≠ Freigebender.
    * **Heal → Re-Check → Release** — erfüllt das Bad-Prädikat noch Zeilen,
      ist die Episode nicht freigabefähig.
    Episoden ohne Korrekturen laufen unverändert durch (keine neue Hürde für
    den bestehenden Quarantäne-Fluss).
    """
    if not principal.has_role("steward", "owner", "admin"):
        raise HTTPException(status_code=403, detail="Quarantine release requires steward role or higher.")
    _assert_healing_preconditions(store, quarantine_id, principal)
    return _transition(store.release_quarantine, quarantine_id, principal.name, body.note)


def _assert_healing_preconditions(store, quarantine_id: int, principal) -> None:
    corrections = store.list_healing_corrections(episode_id=quarantine_id, limit=1)
    if not corrections:
        return
    from ..deps import get_inventory
    from ..healing import requires_four_eyes, run_recheck, split_spec_for
    from ..settings import get_settings

    episode = store.get_quarantine(quarantine_id) or {}
    product = episode.get("product", "")
    settings = get_settings()

    if requires_four_eyes(product, settings) and principal.name in store.correction_actors(quarantine_id):
        raise HTTPException(
            status_code=409,
            detail="Four-eyes rule: the corrector of a contract episode must not release it.",
        )

    spec = split_spec_for(settings, get_inventory(), product)
    remaining = run_recheck(settings, spec, quarantine_id) if spec is not None else None
    if remaining:
        raise HTTPException(
            status_code=409,
            detail=f"{remaining} row(s) still violate the quarantine predicate — heal or re-check first.",
        )


@router.post("/{quarantine_id}/confirm-reprocess")
def confirm_reprocess(
    quarantine_id: int,
    principal: PrincipalDep,
    body: QuarantineActionIn = Body(default=QuarantineActionIn()),
    store: StoreDep = ...,
):
    """Rückführung bestätigt (Kunden-Flow hat die Release-View geladen) —
    Episode wird `resolved(reprocessed)`."""
    if not principal.has_role("steward", "owner", "admin"):
        raise HTTPException(status_code=403, detail="Reprocess confirmation requires steward role or higher.")

    def _resolve(qid: int, actor: str, note: str = ""):
        return store.resolve_quarantine(qid, actor, reason="reprocessed", note=note)

    return _transition(_resolve, quarantine_id, principal.name, body.note)


@router.post("/{quarantine_id}/reconcile")
def reconcile_quarantine(
    quarantine_id: int,
    principal: PrincipalDep,
    body: QuarantineReconcileIn = Body(...),
    store: StoreDep = ...,
):
    """Rückkanal für externe Reconcile-Skripte (Fallback-Pfad ohne
    Materialisierung): beobachtete Zeilenzahl melden → Episode `reconciled`."""
    if not principal.has_role("steward", "owner", "admin"):
        raise HTTPException(status_code=403, detail="Quarantine reconcile requires steward role or higher.")
    if body.row_count < 0:
        raise HTTPException(status_code=422, detail="row_count must be >= 0")

    def _reconcile(qid: int, actor: str, note: str = ""):
        return store.reconcile_quarantine(qid, body.row_count, actor=actor)

    return _transition(_reconcile, quarantine_id, principal.name, "")


def _transition(fn, quarantine_id: int, actor: str, note: str):
    try:
        episode = fn(quarantine_id, actor, note)
    except ValueError as exc:
        # Unzulässiger Lifecycle-Übergang (z. B. Release einer resolved-Episode)
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not episode:
        raise HTTPException(status_code=404, detail=f"Quarantine episode {quarantine_id} not found")
    # Slice ⑤: Status nach DQ_EPISODES spiegeln — die Release-View zeigt
    # freigegebene Zeilen erst nach dem Spiegel. Best-effort über das
    # ENFORCEMENT_ENVIRONMENT; ohne Konfiguration spiegelt der nächste Lauf.
    try:
        from ..enforcement import mirror_episode_via_environment
        from ..settings import get_settings
        mirror_episode_via_environment(get_settings(), episode)
    except Exception:  # noqa: BLE001
        pass
    return episode
