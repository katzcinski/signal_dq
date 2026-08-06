from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

import yaml
from fastapi import APIRouter, HTTPException, Query

from ..auth.provider import PrincipalDep, can_write_contract_data
from ..deps import StoreDep
from ..schemas.proposal_schemas import ProposalOut

router = APIRouter(prefix="/api/proposals", tags=["proposals"])


def _decision_map(store) -> dict[str, str]:
    """Persistierte Steward-Entscheidungen (dq_proposals) — reject/snooze/accept
    überleben Neustarts, statt bei jedem Re-Mining zurückzukommen."""
    try:
        conn = sqlite3.connect(store.db_path, check_same_thread=False)
        rows = conn.execute("SELECT id, status FROM dq_proposals").fetchall()
        conn.close()
        return {r[0]: r[1] for r in rows}
    except Exception:
        return {}


def _persist_decision(store, proposal, status_value: str) -> None:
    conn = sqlite3.connect(store.db_path, check_same_thread=False)
    conn.execute(
        """INSERT OR REPLACE INTO dq_proposals
           (id, product, guarantee_patch, evidence, status, created_at)
           VALUES (?,?,?,?,?,?)""",
        (
            proposal.id,
            proposal.product,
            proposal.proposed_expect,
            str(proposal.stats),
            status_value,
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()
    conn.close()


def _mine_all(store, dataset: str | None = None):
    from dq_core.obs.miner import ProposalMiner

    all_runs = store.get_all_runs(limit=10)
    datasets = list({r["dataset"] for r in all_runs})
    if dataset:
        datasets = [d for d in datasets if d == dataset]
    miner = ProposalMiner(store)
    out = []
    for ds in datasets:
        out.extend(miner.mine(ds, kind=_contract_kind(ds)))
    return out


def _contract_kind(product: str) -> str:
    from pathlib import Path
    from ..settings import get_settings

    contracts_dir = Path(get_settings().contracts_dir)
    for ext in (".yaml", ".yml"):
        path = contracts_dir / f"{product}{ext}"
        if not path.exists():
            continue
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:
            return "internal_gate"
        return str(data.get("kind", "internal_gate"))
    return "internal_gate"


def _find_proposal(store, proposal_id: str):
    for p in _mine_all(store):
        if p.id == proposal_id:
            return p
    return None


@router.get("", response_model=list[ProposalOut])
def list_proposals(
    dataset: str | None = Query(default=None),
    status: str | None = Query(default=None),
    store: StoreDep = ...,
):
    """Mine proposals; overlay persisted steward decisions. Filter via ?status=open."""
    decisions = _decision_map(store)
    result = []
    for p in _mine_all(store, dataset):
        effective_status = decisions.get(p.id, p.status)
        if status and effective_status != status:
            continue
        result.append(
            ProposalOut(
                id=p.id,
                product=p.product,
                check_name=p.check_name,
                current_expect=p.current_expect,
                proposed_expect=p.proposed_expect,
                rationale=p.rationale,
                confidence=p.confidence,
                stats=p.stats,
                status=effective_status,
                created_at=p.created_at,
                kind=p.kind,
            )
        )
    return result


@router.post("/{proposal_id}/accept")
def accept_proposal(
    proposal_id: str,
    principal: PrincipalDep,
    store: StoreDep = ...,
):
    """[AUTHZ] Accept a proposal — creates a draft contract amendment. No auto-apply (WS5-2)."""
    from pathlib import Path
    from ..settings import get_settings

    target_proposal = _find_proposal(store, proposal_id)
    if not target_proposal:
        raise HTTPException(status_code=404, detail=f"Proposal {proposal_id!r} not found")

    settings = get_settings()
    contracts_dir = Path(settings.contracts_dir)
    contract_path = None
    for ext in (".yaml", ".yml"):
        candidate = contracts_dir / f"{target_proposal.product}{ext}"
        if candidate.exists():
            contract_path = candidate
            break

    if contract_path is None:
        raise HTTPException(
            status_code=404,
            detail=f"No contract found for product {target_proposal.product!r}",
        )

    data = yaml.safe_load(contract_path.read_text(encoding="utf-8")) or {}

    # [AUTHZ] S-6: Ein Accept degradiert den Contract auf draft — das ist eine
    # Contract-Schreiboperation und braucht das entsprechende Recht.
    if not can_write_contract_data(principal, data):
        raise HTTPException(status_code=403, detail="Insufficient permissions for this contract.")

    # Add proposed_expect as a quality annotation in the guarantees — draft amendment only
    if "quality_proposals" not in data:
        data["quality_proposals"] = []
    data["quality_proposals"].append({
        "check_name": target_proposal.check_name,
        "proposed_expect": target_proposal.proposed_expect,
        "rationale": target_proposal.rationale,
        "accepted_by": principal.name,
    })
    # Downgrade to draft so it must be re-approved
    data["lifecycle"] = "draft"

    contract_path.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    _persist_decision(store, target_proposal, "accepted")

    return {
        "id": proposal_id,
        "status": "accepted",
        "product": target_proposal.product,
        "message": (
            f"Draft amendment created for {target_proposal.product!r}. "
            "Contract reverted to 'draft' — review in Workbench and re-approve."
        ),
    }


@router.post("/{proposal_id}/reject")
def reject_proposal(proposal_id: str, principal: PrincipalDep, store: StoreDep = ...):
    if not principal.has_role("steward", "owner", "admin"):
        raise HTTPException(status_code=403, detail="Reviewing proposals requires steward role or higher.")
    proposal = _find_proposal(store, proposal_id)
    if not proposal:
        raise HTTPException(status_code=404, detail=f"Proposal {proposal_id!r} not found")
    _persist_decision(store, proposal, "rejected")
    return {"id": proposal_id, "status": "rejected"}


@router.post("/{proposal_id}/snooze")
def snooze_proposal(proposal_id: str, principal: PrincipalDep, store: StoreDep = ...):
    if not principal.has_role("steward", "owner", "admin"):
        raise HTTPException(status_code=403, detail="Reviewing proposals requires steward role or higher.")
    proposal = _find_proposal(store, proposal_id)
    if not proposal:
        raise HTTPException(status_code=404, detail=f"Proposal {proposal_id!r} not found")
    _persist_decision(store, proposal, "snoozed")
    return {"id": proposal_id, "status": "snoozed"}
