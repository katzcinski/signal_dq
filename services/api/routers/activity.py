"""UX-N15: Activity / Audit feed.

Aggregates "who did what" across three authoritative sources into one
reverse-chronological stream:

1. Incident lifecycle events (`dq_incident_events`) — who acknowledged /
   resolved which incident.
2. Steward decisions on mined proposals (`dq_proposals`) — accepted / rejected
   / snoozed; actor is best-effort from the contract's `quality_proposals`.
3. Contract approvals from the contracts Git history — who certified which
   contract version (author + commit message).

Read-only: no source is mutated here.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, Query
from pydantic import BaseModel

from ..deps import StoreDep
from ..settings import get_settings

router = APIRouter(prefix="/api/activity", tags=["activity"])


class ActivityItem(BaseModel):
    kind: str       # incident | proposal | contract
    action: str     # opened | status_changed | assigned | resolved | accepted | approved | …
    actor: str
    at: str         # ISO-8601 timestamp
    product: str
    summary: str
    ref: str        # incident id / proposal id / commit hash


def _incident_events(db_path: str, limit: int) -> list[ActivityItem]:
    if not Path(db_path).exists():
        return []
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """SELECT e.id, e.incident_id, e.at, e.actor, e.action, e.note,
                      i.product, i.title
                 FROM dq_incident_events e
                 JOIN dq_incidents i ON i.id = e.incident_id
                ORDER BY e.id DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()

    items: list[ActivityItem] = []
    for r in rows:
        items.append(ActivityItem(
            kind="incident",
            action=r["action"] or "",
            actor=r["actor"] or "system",
            at=r["at"] or "",
            product=r["product"] or "",
            summary=r["note"] or r["title"] or "",
            ref=str(r["incident_id"]),
        ))
    return items


def _proposal_decisions(db_path: str, limit: int) -> list[ActivityItem]:
    if not Path(db_path).exists():
        return []
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """SELECT id, product, status, created_at FROM dq_proposals
                WHERE status != 'open' ORDER BY created_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()

    # Best-effort actor for accepted proposals: dq_proposals stores no actor, but
    # accepting one stamps `accepted_by` into the contract. Proposal ids are
    # UUIDs with no join key, so we attribute by product (last accepter wins).
    accepted_by = _accepted_by_index()
    items: list[ActivityItem] = []
    for r in rows:
        actor = accepted_by.get(r["product"], "") if r["status"] == "accepted" else ""
        items.append(ActivityItem(
            kind="proposal",
            action=r["status"] or "",
            actor=actor or "—",
            at=r["created_at"] or "",
            product=r["product"] or "",
            summary=f"Vorschlag {r['status']}",
            ref=str(r["id"]),
        ))
    return items


def _accepted_by_index() -> dict[str, str]:
    """Map product → most recent `accepted_by` from contract amendments.

    Proposals don't persist an actor, but accepting one stamps `accepted_by`
    into the contract's `quality_proposals`. Best-effort attribution by product.
    """
    out: dict[str, str] = {}
    contracts_dir = Path(get_settings().contracts_dir)
    if not contracts_dir.exists():
        return out
    for path in contracts_dir.glob("*.y*ml"):
        if path.name.endswith(".active.yml"):
            continue
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:
            continue
        product = data.get("product") or path.stem
        for qp in (data.get("quality_proposals") or []):
            by = qp.get("accepted_by")
            if by:
                out[product] = by  # later entries win → most recent accepter
    return out


def _contract_approvals(limit: int) -> list[ActivityItem]:
    """Read contract approval commits from the contracts Git history.

    Legal to have no repo (external CONTRACTS_DIR in local mode) — returns [].
    """
    settings = get_settings()
    contracts_dir = Path(settings.contracts_dir)
    if not contracts_dir.exists():
        return []
    try:
        import git
    except ImportError:
        return []
    try:
        repo = git.Repo(contracts_dir, search_parent_directories=True)
    except Exception:
        return []

    items: list[ActivityItem] = []
    try:
        commits = repo.iter_commits(paths=str(contracts_dir), max_count=limit * 4)
    except Exception:
        return []
    for commit in commits:
        message = (commit.message or "").strip().splitlines()[0] if commit.message else ""
        if not message.startswith("Approve contract "):
            continue
        # "Approve contract <product> v<version>"
        parts = message.split()
        product = parts[2] if len(parts) > 2 else ""
        items.append(ActivityItem(
            kind="contract",
            action="approved",
            actor=str(commit.author.name or ""),
            at=commit.authored_datetime.isoformat(),
            product=product,
            summary=message,
            ref=commit.hexsha[:12],
        ))
        if len(items) >= limit:
            break
    return items


@router.get("", response_model=list[ActivityItem])
def list_activity(
    limit: int = Query(default=30, ge=1, le=200),
    store: StoreDep = ...,
):
    """Merged, reverse-chronological activity across incidents, proposals and
    contract approvals."""
    items: list[ActivityItem] = []
    items.extend(_incident_events(store.db_path, limit))
    items.extend(_proposal_decisions(store.db_path, limit))
    items.extend(_contract_approvals(limit))
    items.sort(key=lambda it: it.at, reverse=True)
    return items[:limit]
