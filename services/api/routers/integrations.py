"""Integrations-Router — Entropy Data (Contract-/Result-Marktplatz).

Bündelt die maschinell/manuell auslösbaren Publish-Aktionen sowie den
nicht-sensiblen Konfig-Status für die UI. Der automatische Ergebnis-Publish
hängt am Run-Abschluss (`routers/objects.py`), nicht hier — dieser Router
liefert den manuellen Trigger, die Config-Sicht und den ODCS-Import-Adapter.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, Body, HTTPException

from ..auth.provider import PrincipalDep
from ..deps import StoreDep
from .. import entropy
from ..settings import get_settings

router = APIRouter(prefix="/api/integrations", tags=["integrations"])


def _load_contract(product: str) -> dict[str, Any] | None:
    base = Path(get_settings().contracts_dir)
    for ext in (".yaml", ".yml"):
        p = base / f"{product}{ext}"
        if p.exists():
            return yaml.safe_load(p.read_text(encoding="utf-8"))
    return None


@router.get("/entropy")
def entropy_config():
    """Nicht-sensibler Konfig-Status (nie Token/URL im Klartext, S-14)."""
    return entropy.config_status(get_settings())


@router.post("/entropy/contracts/{product}")
def publish_contract(product: str, principal: PrincipalDep):
    """Contract als ODCS-Derivat an Entropy registrieren (Einweg-Export).

    steward+; nur `*_contract`. Läuft als Dry-Run, solange der Marktplatz nicht
    gegenverifiziert ist (E2/E3) — der Payload wird gebaut, aber nicht gesendet.
    """
    if not principal.has_role("steward", "owner", "admin"):
        raise HTTPException(status_code=403, detail="Publishing requires steward role or higher.")
    data = _load_contract(product)
    if not data:
        raise HTTPException(status_code=404, detail=f"Contract {product!r} not found")
    result = entropy.publish_contract_registration(data, get_settings())
    return {"product": product, **result}


@router.post("/entropy/results/{product}")
def publish_latest_result(product: str, principal: PrincipalDep, store: StoreDep = ...):
    """Jüngsten Lauf eines Objekts als Quality-Ergebnis an Entropy publizieren.

    steward+. Rekonstruiert eine RunSummary-artige Sicht aus dem Store; dieselbe
    Dry-Run-Disziplin wie oben.
    """
    if not principal.has_role("steward", "owner", "admin"):
        raise HTTPException(status_code=403, detail="Publishing requires steward role or higher.")
    runs = store.get_runs(product, limit=1)
    if not runs:
        raise HTTPException(status_code=404, detail=f"No runs found for {product!r}")
    run = store.get_run(runs[0]["run_id"])  # get_run embeds the check results
    summary = _RunView(run or runs[0])
    result = entropy.publish_run_result(summary, _load_contract(product), get_settings())
    return {"product": product, "run_id": summary.run_id, **result}


class _RunView:
    """Leichte, attribut-kompatible Sicht auf einen persistierten Lauf, damit der
    Entropy-Mapper (`_quality_payload`) unverändert Duck-Typing nutzen kann."""

    def __init__(self, run: dict[str, Any]):
        self.run_id = str(run.get("run_id", ""))
        self.dataset = str(run.get("dataset", ""))
        self.started_at = str(run.get("started_at", ""))
        self.finished_at = str(run.get("finished_at", ""))
        self.overall_status = str(run.get("overall_status", ""))
        self.gate_verdict = str(run.get("gate_verdict", "") or "")
        self.contract_version = str(run.get("contract_version", "") or "")
        self.results = [_ResultView(r) for r in (run.get("results") or [])]


class _ResultView:
    def __init__(self, row: dict[str, Any]):
        self.name = str(row.get("check_name", row.get("name", "")))
        self.type = str(row.get("type", "") or "")
        self.passed = bool(row.get("passed", False))
        self.severity = str(row.get("severity", "") or "")
        self.state = str(row.get("state", "executed") or "executed")
        self.actual_value = row.get("actual_value")
        self.expect = str(row.get("expect_expr", row.get("expect", "")) or "")
        self.expect_expr = self.expect


@router.post("/entropy/import/odcs")
def import_odcs(
    principal: PrincipalDep,
    body: dict[str, Any] = Body(...),
    store: StoreDep = ...,
):
    """E1 — „Entropy authort → Signal erzwingt": ODCS-Dokument → Signal-Draft.

    Nimmt `{ "odcs": {...}, "dry_run": bool }`. Rekonstruiert ein Contract-Dict
    (nur Garantien, kein SQL — G1), validiert es und speichert es (sofern nicht
    `dry_run`) als Draft. Nicht abbildbare Regeln werden ehrlich in `dropped`
    berichtet. steward+.
    """
    from dq_core.contract.odcs_import import from_odcs
    from dq_core.contract.validator import validate_contract
    from .contracts import _save_contract, _update_index, _validate_product

    if not principal.has_role("steward", "owner", "admin"):
        raise HTTPException(status_code=403, detail="Importing contracts requires steward role or higher.")

    odcs = body.get("odcs")
    if not isinstance(odcs, dict):
        raise HTTPException(status_code=422, detail="Body must contain an 'odcs' object.")
    dry_run = bool(body.get("dry_run", False))

    try:
        result = from_odcs(odcs)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    contract = result.contract
    _validate_product(contract["product"])

    errors = validate_contract(contract)
    if errors:
        raise HTTPException(
            status_code=422,
            detail={"message": "Imported contract failed validation (Gate G1)", "errors": errors,
                    "dropped": result.dropped, "warnings": result.warnings},
        )

    if not dry_run:
        _save_contract(contract["product"], contract)
        _update_index(store, contract["product"], contract)

    return {
        "product": contract["product"],
        "persisted": not dry_run,
        "contract": contract,
        "dropped": result.dropped,
        "warnings": result.warnings,
    }
