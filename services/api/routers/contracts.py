# [CONTRACT-SQL-FREE] — all contract writes go through validator (G1)
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Optional

import yaml
from fastapi import APIRouter, Body, Depends, HTTPException, Query, status

from ..auth.provider import PrincipalDep, can_write_contract_data
from ..deps import StoreDep, get_inventory
from ..git_repo import GitPushRejected, GitRepo
from ..schemas.contract_schemas import (
    BacktestCheckOut, BacktestIn, BacktestOut, BacktestSummaryWindow,
    CompileOut, ContractIn, ContractOut,
    ObservedOut, ObservedGuarantee, ObservedCheck, ObservedPoint,
)
from ..settings import get_settings

router = APIRouter(prefix="/api/contracts", tags=["contracts"])

# S2/S-11: product wird Dateiname und SQL-Identifier — gleiche Policy wie Spalten.
_SAFE_PRODUCT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _validate_product(product: str) -> str:
    if not _SAFE_PRODUCT.match(product or ""):
        raise HTTPException(
            status_code=422,
            detail=f"Invalid product name {product!r} (allowed: ^[A-Za-z_][A-Za-z0-9_]*$)",
        )
    return product


def _contracts_dir() -> Path:
    return Path(get_settings().contracts_dir)


def _contract_path(product: str) -> Path:
    """Return the on-disk path for a contract, tolerating .yaml and .yml.

    Prefers an existing file (whatever its extension); falls back to .yaml
    for new writes so seeded `<product>.yaml` files stay the source of truth.
    """
    base = _contracts_dir()
    for ext in (".yaml", ".yml"):
        candidate = base / f"{product}{ext}"
        if candidate.exists():
            return candidate
    return base / f"{product}.yaml"


def _load_contract(product: str) -> dict[str, Any] | None:
    path = _contract_path(product)
    if not path.exists():
        return None
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _is_governance_contract(data: dict[str, Any]) -> bool:
    return data.get("kind", "internal_gate") in {"consumer_contract", "provider_contract"}


def _save_contract(product: str, data: dict[str, Any]) -> None:
    _contracts_dir().mkdir(parents=True, exist_ok=True)
    path = _contract_path(product)
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")


def _active_snapshot_path(product: str) -> Path:
    """Certified-version snapshot used as the diff baseline for approvals."""
    return _contracts_dir() / f"{product}.active.yml"


def _require_write(principal, existing: dict[str, Any] | None) -> None:
    """[AUTHZ] S-2: Entscheidung anhand des bestehenden Contracts, nie des Bodys."""
    if not can_write_contract_data(principal, existing):
        raise HTTPException(status_code=403, detail="Insufficient permissions for this contract.")


def _contract_out(store, product: str, data: dict[str, Any]) -> ContractOut:
    compliance_row = store.get_compliance(product) if _is_governance_contract(data) else None
    return ContractOut(
        product=data.get("product") or product,
        kind=data.get("kind", "internal_gate"),
        dataset=data.get("dataset", ""),
        owned_by=data.get("owned_by", "platform"),
        owners=data.get("owners") or [],
        version=str(data.get("version", "0.1.0")),
        lifecycle=data.get("lifecycle", "draft"),
        description=str(data.get("description") or ""),
        guarantees=data.get("guarantees") or {},
        observability=data.get("observability") or {},
        checks=data.get("checks") or [],
        compliance=compliance_row["compliance"] if compliance_row else None,
        certified=_active_snapshot_path(product).exists(),
    )


def _reindex(store) -> None:
    """A3: contract_index aus dem Working Tree neu aufbauen (lazy, wenn leer
    oder explizit über POST /reindex — z. B. nach externem git pull)."""
    contracts_dir = _contracts_dir()
    if not contracts_dir.exists():
        return
    for path in sorted(contracts_dir.glob("*.y*ml")):
        if path.name.endswith(".active.yml"):
            continue
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:
            continue
        if data:
            _update_index(store, data.get("product") or path.stem, data)


@router.get("", response_model=list[ContractOut])
def list_contracts(
    lifecycle: str | None = Query(default=None),
    store: StoreDep = ...,
):
    """A3: Liste aus contract_index — Git ist keine Query-DB. `guarantees`
    ist hier leer; das volle Contract liefert GET /api/contracts/{product}."""
    import sqlite3

    def _query():
        conn = sqlite3.connect(store.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        clause, params = "", []
        if lifecycle:
            clause = "WHERE lifecycle=?"
            params.append(lifecycle)
        rows = conn.execute(
            f"SELECT * FROM contract_index {clause} ORDER BY product", params
        ).fetchall()
        conn.close()
        return rows

    rows = _query()
    if not rows and not lifecycle:
        _reindex(store)
        rows = _query()

    result = []
    for row in rows:
        data = _load_contract(row["product"]) or {}
        compliance_row = store.get_compliance(row["product"]) if _is_governance_contract(data) else None
        result.append(ContractOut(
            product=row["product"],
            kind=data.get("kind", "internal_gate"),
            dataset=row["product"],
            owned_by=row["owned_by"] or "platform",
            owners=[],
            version=row["version"] or "0.1.0",
            lifecycle=row["lifecycle"] or "draft",
            guarantees={},
            observability={},
            compliance=compliance_row["compliance"] if compliance_row else None,
        ))
    return result


@router.post("/reindex")
def reindex_contracts(principal: PrincipalDep, store: StoreDep = ...):
    """Index-Rebuild nach externen Änderungen (git pull) — steward+."""
    if not principal.has_role("steward", "owner", "admin"):
        raise HTTPException(status_code=403, detail="Reindex requires steward role or higher.")
    _reindex(store)
    return {"status": "reindexed"}


@router.get("/{product}", response_model=ContractOut)
def get_contract(product: str, store: StoreDep = ...):
    _validate_product(product)
    data = _load_contract(product)
    if not data:
        raise HTTPException(status_code=404, detail=f"Contract {product!r} not found")
    return _contract_out(store, product, data)


@router.put("/{product}", response_model=ContractOut)
def update_contract(
    product: str,
    principal: PrincipalDep,
    body: ContractIn = Body(...),
    store: StoreDep = ...,
):
    """[CONTRACT-SQL-FREE] [AUTHZ] Update a contract — Gate G1 enforced here.

    Lifecycle ist kein Eingabefeld: das Ergebnis eines PUT ist IMMER ein Draft.
    Ein PUT auf einen aktiven Contract erzeugt damit ein Draft-Amendment — die
    zertifizierte Version bleibt als `.active.yml`-Snapshot die G3-Diff-Basis,
    bis ein erneutes Approve sie ersetzt.
    """
    from dq_core.contract.validator import validate_contract

    _validate_product(product)
    existing = _load_contract(product)

    # [AUTHZ] — S-2: gegen den bestehenden Contract entscheiden, nicht den Body.
    _require_write(principal, existing)

    data = body.model_dump()
    data["lifecycle"] = "draft"

    # [CONTRACT-SQL-FREE] Gate G1
    errors = validate_contract(data)
    if errors:
        raise HTTPException(
            status_code=422,
            detail={"message": "Contract validation failed (Gate G1)", "errors": errors},
        )

    _save_contract(product, data)
    _update_index(store, product, data)
    return _contract_out(store, product, data)


@router.post("/{product}/seed", response_model=ContractOut)
def seed_contract(
    product: str,
    principal: PrincipalDep,
    inventory: list[dict] = Depends(get_inventory),
    store: StoreDep = ...,
):
    """[AUTHZ] Seed a draft contract from the inventory object (WS2-2)."""
    from dq_core.contract.seed import seed_from_inventory

    _validate_product(product)
    existing = _load_contract(product)
    _require_write(principal, existing)
    if existing and existing.get("lifecycle") not in (None, "draft"):
        raise HTTPException(
            status_code=409,
            detail=f"Contract {product!r} is {existing.get('lifecycle')!r} — seeding would overwrite a certified contract.",
        )

    obj = next(
        (o for o in inventory if (o.get("id") or o.get("technicalName") or o.get("name")) == product),
        None,
    )
    if not obj:
        raise HTTPException(status_code=404, detail=f"Object {product!r} not found in inventory")

    data = seed_from_inventory(obj)
    _save_contract(product, data)
    _update_index(store, product, data)
    return _contract_out(store, product, data)


@router.post("/{product}/promote", response_model=ContractOut)
def promote_to_contract(
    product: str,
    principal: PrincipalDep,
    store: StoreDep = ...,
):
    """ADR-0001: copy guarantees from an internal gate into a new contract draft."""
    from dq_core.contract.validator import validate_contract

    _validate_product(product)
    data = _load_contract(product)
    if not data:
        raise HTTPException(status_code=404, detail=f"Contract {product!r} not found")

    kind = data.get("kind", "internal_gate")
    if kind != "internal_gate":
        raise HTTPException(
            status_code=409,
            detail=f"Only internal_gate artifacts can be promoted (got {kind!r}).",
        )

    _require_write(principal, data)

    contract_product = f"{product}_contract"
    if _load_contract(contract_product):
        raise HTTPException(
            status_code=409,
            detail=f"Contract {contract_product!r} already exists. Edit it directly in the workbench.",
        )

    promoted = dict(data)
    promoted["product"] = contract_product
    promoted["kind"] = "consumer_contract"
    promoted["lifecycle"] = "draft"
    promoted["version"] = "1.0.0"

    errors = validate_contract(promoted)
    if errors:
        raise HTTPException(
            status_code=422,
            detail={"message": "Promoted contract validation failed (Gate G1)", "errors": errors},
        )

    _save_contract(contract_product, promoted)
    _update_index(store, contract_product, promoted)
    return _contract_out(store, contract_product, promoted)


@router.post("/{product}/diff")
def diff_contract(
    product: str,
    body: ContractIn = Body(...),
):
    """Compare submitted contract against current version (WS2-4)."""
    from dq_core.contract.diff import diff_contracts, is_breaking

    _validate_product(product)
    current = _load_contract(product)
    if not current:
        kind = body.kind or "internal_gate"
        ceremony_required = kind in ("consumer_contract", "provider_contract")
        return {
            "kind": kind,
            "ceremony_required": ceremony_required,
            "breaking": False,
            "blocking": False,
            "entries": [],
            "message": "No existing contract",
        }

    entries = diff_contracts(current, body.model_dump())
    kind = current.get("kind", "internal_gate")
    ceremony_required = kind in ("consumer_contract", "provider_contract")
    breaking = is_breaking(entries)
    return {
        "kind": kind,
        "ceremony_required": ceremony_required,
        "breaking": breaking,
        "blocking": ceremony_required and breaking,
        "entries": [
            {"kind": e.kind, "path": e.path, "old": e.old_value, "new": e.new_value, "breaking": e.breaking}
            for e in entries
        ],
    }


@router.get("/{product}/drift")
def schema_drift_report(
    product: str,
    store: StoreDep = ...,
    inventory: list[dict] = Depends(get_inventory),
):
    """Shift-Left (§A): Read-only-Report, ob die **Quelle** vom Schema-Versprechen
    des Contracts abweicht. Persistenz + Incident laufen beim Extrakt, nicht hier.
    Liefert zusätzlich die jüngste gespeicherte Drift-Historie."""
    from ..schema_drift_service import evaluate_contract_drift, inventory_columns_for

    _validate_product(product)
    contract = _load_contract(product)
    if not contract:
        raise HTTPException(status_code=404, detail=f"Contract {product!r} not found")

    dataset = contract.get("dataset") or product
    columns = inventory_columns_for(inventory, dataset)
    if columns is None:
        return {
            "product": product,
            "dataset": dataset,
            "object_found": False,
            "kind": contract.get("kind", "internal_gate"),
            "findings": [],
            "summary": {"total": 0, "breaking": 0, "has_breaking": False, "by_category": {}},
            "history": store.get_schema_drift(dataset),
        }

    report = evaluate_contract_drift(contract, columns)
    return {
        "product": product,
        "dataset": dataset,
        "object_found": True,
        "kind": contract.get("kind", "internal_gate"),
        **report,
        "history": store.get_schema_drift(dataset),
    }


@router.post("/{product}/backtest", response_model=BacktestOut)
def backtest_contract(
    product: str,
    body: BacktestIn,
    store: StoreDep = ...,
    inventory: list[dict] = Depends(get_inventory),
):
    """Garantie-Backtesting (V1): Expectation-Entwürfe gegen die persistierte
    Messwert-Historie simulieren — rein lesend, kein Lauf gegen HANA.

    Zwei Eingabeformen: `contract` (kompletter Entwurf; der deterministische
    Compiler liefert die Check-Namen — G1 gilt auch hier) **oder** `checks`
    (explizite Paare, z. B. der `proposed_expect` eines Proposals)."""
    from dq_core.contract.compiler import CompileError
    from dq_core.contract.validator import validate_contract
    from dq_core.obs.backtest import backtest_expectation

    _validate_product(product)

    window_days = sorted({int(d) for d in (body.window_days or []) if 0 < int(d) <= 365}) or [30, 90]

    dataset = product
    targets: list[tuple[str, str, str, str]] = []  # (name, expect, type, severity)
    if body.contract:
        data = dict(body.contract)
        errors = validate_contract(data)  # [CONTRACT-SQL-FREE] G1 auch für Entwürfe
        if errors:
            raise HTTPException(
                status_code=422,
                detail={"message": "Contract validation failed (Gate G1)", "errors": errors},
            )
        try:
            _yaml, _conflicts, _hash, config = _compile_contract_data(product, data, inventory)
        except CompileError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        dataset = config.dataset or (data.get("dataset") or product)
        targets = [(c.name, c.expect, c.type, c.severity) for c in config.checks]
    elif body.checks:
        targets = [(c.check_name, c.expect, "", "") for c in body.checks]
    else:
        raise HTTPException(status_code=422, detail="Provide either 'contract' or 'checks'.")

    results: list[BacktestCheckOut] = []
    with_history = 0
    for name, expect, ctype, severity in targets:
        history = store.get_check_history(dataset, name, limit=500)
        history.reverse()  # Store liefert DESC; Backtest erwartet chronologisch
        try:
            report = backtest_expectation(history, expect, window_days=tuple(window_days))
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid expectation for {name!r}: {exc}",
            )
        if report["points"]:
            with_history += 1
        results.append(BacktestCheckOut(
            check_name=name, expect=expect, type=ctype, severity=severity,
            **{k: report[k] for k in (
                "points", "evaluated", "skipped", "breaches", "breach_rate",
                "first_breach_at", "last_breach_at", "sample", "windows",
            )},
        ))

    summary = [
        BacktestSummaryWindow(
            days=days,
            breaches=sum(w.breaches for r in results for w in r.windows if w.days == days),
            checks_firing=sum(
                1 for r in results if any(w.days == days and w.breaches for w in r.windows)
            ),
        )
        for days in window_days
    ]

    return BacktestOut(
        product=product,
        dataset=dataset,
        window_days=window_days,
        checks=results,
        checks_total=len(results),
        checks_with_history=with_history,
        summary_windows=summary,
    )


@router.get("/{product}/diff/active")
@router.get("/{product}/version-diff")
def version_diff_contract(product: str):
    """UX-N13: semantic diff of the working contract against the last certified
    version (`.active.yml`). Reuses the breaking-change engine so the FE can
    explain the *meaning* of each change, not just two code spans."""
    from dq_core.contract.diff import diff_contracts, is_breaking

    _validate_product(product)
    current = _load_contract(product)
    if not current:
        raise HTTPException(status_code=404, detail=f"Contract {product!r} not found")

    kind = current.get("kind", "internal_gate")
    ceremony_required = kind in ("consumer_contract", "provider_contract")
    snapshot_path = _active_snapshot_path(product)
    if not snapshot_path.exists():
        # No certified baseline yet — nothing to diff against.
        return {
            "available": False,
            "kind": kind,
            "ceremony_required": ceremony_required,
            "from_version": None,
            "to_version": str(current.get("version", "")),
            "breaking": False,
            "blocking": False,
            "entries": [],
        }

    prior = yaml.safe_load(snapshot_path.read_text(encoding="utf-8")) or {}
    entries = diff_contracts(prior, current)
    breaking = is_breaking(entries)
    return {
        "available": True,
        "kind": kind,
        "ceremony_required": ceremony_required,
        "from_version": str(prior.get("version", "")),
        "to_version": str(current.get("version", "")),
        "lifecycle": current.get("lifecycle", "draft"),
        "breaking": breaking,
        "blocking": ceremony_required and breaking,
        "entries": [
            {"kind": e.kind, "path": e.path, "old": e.old_value, "new": e.new_value, "breaking": e.breaking}
            for e in entries
        ],
    }


def _semver_major(version: str) -> int:
    try:
        return int(str(version).split(".")[0])
    except (ValueError, IndexError):
        return 0


def _compile_contract_data(product: str, data: dict[str, Any], inventory: list[dict]):
    """Compile a (G1-validated) contract dict → (yaml_out, conflicts, det_hash, config).

    Single source of truth for the contract→checks pipeline, shared by the
    full-mode `/compile` endpoint and the Lite `/certify` one-step path. Performs
    the existing-wins merge against any `checks/<product>/checks.yml` on disk but
    writes nothing — the caller owns persistence. May raise CompileError.
    """
    from dq_core.contract.compiler import (
        compile_contract as _compile,
        compiled_contract_hash,
        compiler_hash,
    )
    from dq_core.engine.check_engine import dataset_config_to_yaml
    from dq_core.engine.models import CheckDef
    from dq_core.library.check_library import load_library

    # S2 Stufe 2: Spalten-Existenzprüfung gegen das Inventar, falls vorhanden.
    inventory_columns: set[str] | None = None
    dataset_name = data.get("dataset") or product
    obj = next(
        (o for o in inventory if (o.get("id") or o.get("technicalName") or o.get("name")) == dataset_name),
        None,
    )
    if obj:
        cols = {
            c.get("name") or c.get("technicalName")
            for c in (obj.get("columns") or obj.get("properties") or [])
        }
        inventory_columns = {c for c in cols if c} or None

    config = _compile(data, inventory_columns=inventory_columns)

    contract_hash = compiled_contract_hash(data)
    library_version = str(load_library().get("version", "1"))
    det_hash = compiler_hash(data)

    # Existing-wins merge: keep handwritten checks when names collide.
    checks_dir = Path(get_settings().checks_dir) / product
    existing_checks_path = checks_dir / "checks.yml"
    conflicts: list[str] = []
    if existing_checks_path.exists():
        try:
            existing_data = yaml.safe_load(existing_checks_path.read_text(encoding="utf-8")) or {}
            existing_by_name = {c["name"]: c for c in (existing_data.get("checks") or [])}
            merged = []
            for c in config.checks:
                if c.name in existing_by_name:
                    conflicts.append(c.name)
                    ec = existing_by_name[c.name]
                    merged.append(CheckDef(
                        name=ec["name"], sql=ec.get("sql", c.sql),
                        expect=ec.get("expect", c.expect), severity=ec.get("severity", c.severity),
                        type=ec.get("type", c.type), unit=ec.get("unit", c.unit),
                        owned_by=ec.get("owned_by", c.owned_by),
                        kind=ec.get("kind", c.kind),
                    ))
                else:
                    merged.append(c)
            config.checks = merged
        except Exception:
            pass  # if existing file is malformed, use compiled checks as-is

    # [DETERMINISM] A4: Hashes stehen IM Artefakt, nicht nur in der Response.
    header = (
        f"# contract_hash: {contract_hash}\n"
        f"# library_version: {library_version}\n"
        f"# compiler_hash: {det_hash}\n"
    )
    yaml_out = header + dataset_config_to_yaml(config)
    return yaml_out, conflicts, det_hash, config


def _write_checks(product: str, yaml_out: str) -> None:
    checks_dir = Path(get_settings().checks_dir) / product
    checks_dir.mkdir(parents=True, exist_ok=True)
    (checks_dir / "checks.yml").write_text(yaml_out, encoding="utf-8")


@router.post("/{product}/approve", response_model=ContractOut)
def approve_contract(
    product: str,
    principal: PrincipalDep,
    store: StoreDep = ...,
):
    """[AUTHZ] Promote a draft contract to active (WS2-6 / M2).

    Server-side breaking guard (G3): if the change is breaking versus the last
    certified version, a SemVer **major** bump is required.
    """
    from dq_core.contract.diff import diff_contracts, is_breaking
    from dq_core.contract.validator import validate_contract

    _validate_product(product)
    data = _load_contract(product)
    if not data:
        raise HTTPException(status_code=404, detail=f"Contract {product!r} not found")
    if data.get("lifecycle") != "draft":
        raise HTTPException(
            status_code=409,
            detail=f"Contract {product!r} is {data.get('lifecycle')!r}, only drafts can be approved.",
        )

    # [AUTHZ] — Entscheidung anhand des Contracts auf Platte.
    _require_write(principal, data)

    # G1 auch auf dem Disk-Pfad: nie einen invaliden Contract zertifizieren.
    errors = validate_contract(data)
    if errors:
        raise HTTPException(
            status_code=422,
            detail={"message": "Contract validation failed (Gate G1)", "errors": errors},
        )

    # G3 — breaking change must carry a major version bump.
    kind = data.get("kind", "internal_gate")
    is_contract = kind in ("consumer_contract", "provider_contract")
    snapshot_path = _active_snapshot_path(product)
    if is_contract and snapshot_path.exists():
        prior = yaml.safe_load(snapshot_path.read_text(encoding="utf-8")) or {}
        entries = diff_contracts(prior, data)
        if is_breaking(entries) and _semver_major(data.get("version", "0")) <= _semver_major(prior.get("version", "0")):
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "Breaking change requires a major version bump (Gate G3).",
                    "from_version": prior.get("version"),
                    "to_version": data.get("version"),
                    "breaking": [
                        {"kind": e.kind, "path": e.path, "old": e.old_value, "new": e.new_value}
                        for e in entries if e.breaking
                    ],
                },
            )

    data["lifecycle"] = "active"
    _save_contract(product, data)
    snapshot_path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    _update_index(store, product, data)

    # One commit per approve. Fehler werden sichtbar gemacht (S-12), aber ein
    # fehlendes Git-Repo (lokaler Modus mit externem CONTRACTS_DIR) ist legal.
    commit_error = None
    try:
        GitRepo(get_settings().contracts_dir, get_settings().git_remote).write_contract(
            product,
            yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
            principal.name,
            f"{principal.sub}@dq-cockpit",
            f"Approve contract {product} v{data.get('version')}",
        )
    except GitPushRejected as exc:
        # Lokal committed, Push abgelehnt → 409 mit Rebase-Hinweis (WS2-3)
        raise HTTPException(status_code=409, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        commit_error = str(exc)

    # Governance contracts start 'unknown' until the first run of the active version.
    # Internal gates never write dq_compliance/dq_compliance_events.
    if is_contract and not store.get_compliance(product):
        store.set_compliance(product, str(data.get("version", "")), "unknown", "")

    out = _contract_out(store, product, data)
    if commit_error:
        # Approve gilt (Datei + Snapshot geschrieben), aber der Commit schlug fehl —
        # niemals stillschweigend verschlucken.
        raise HTTPException(
            status_code=502,
            detail={
                "message": "Contract approved, but the Git commit failed — repository intervention required.",
                "git_error": commit_error,
                "contract": out.model_dump(),
            },
        )
    return out


@router.post("/{product}/deprecate", response_model=ContractOut)
def deprecate_contract(
    product: str,
    principal: PrincipalDep,
    store: StoreDep = ...,
):
    """[AUTHZ] Retire an active contract (WS2-6)."""
    _validate_product(product)
    data = _load_contract(product)
    if not data:
        raise HTTPException(status_code=404, detail=f"Contract {product!r} not found")
    if data.get("lifecycle") != "active":
        raise HTTPException(
            status_code=409,
            detail=f"Only active contracts can be deprecated (got {data.get('lifecycle')!r}).",
        )
    _require_write(principal, data)

    data["lifecycle"] = "deprecated"
    _save_contract(product, data)
    _update_index(store, product, data)
    return _contract_out(store, product, data)


@router.post("/{product}/compile", response_model=CompileOut)
def compile_contract(
    product: str,
    principal: PrincipalDep,
    dry_run: bool = Query(default=False),
    store: StoreDep = ...,
    inventory: list[dict] = Depends(get_inventory),
):
    """[DETERMINISM] [SCHEMA-MAP] Compile contract → CheckDefs.

    G1: der Contract wird auch auf dem Disk-Pfad validiert (kein Schmuggel an
    PUT vorbei). G2: '{schema}' bleibt als Platzhalter im Output. Non-dry-run
    erfordert lifecycle=active (WS3-2) und Schreibrecht.
    """
    from dq_core.contract.compiler import CompileError
    from dq_core.contract.validator import validate_contract

    _validate_product(product)
    data = _load_contract(product)
    if not data:
        raise HTTPException(status_code=404, detail=f"Contract {product!r} not found")

    # [CONTRACT-SQL-FREE] G1 gilt für jeden Ingestion-Pfad (S-3).
    errors = validate_contract(data)
    if errors:
        raise HTTPException(
            status_code=422,
            detail={"message": "Contract validation failed (Gate G1)", "errors": errors},
        )

    if not dry_run:
        _require_write(principal, data)
        if data.get("lifecycle") != "active":
            raise HTTPException(
                status_code=409,
                detail=f"Compile (persist) requires lifecycle=active, got {data.get('lifecycle')!r}. Use dry_run=true.",
            )

    try:
        yaml_out, conflicts, det_hash, config = _compile_contract_data(product, data, inventory)
    except CompileError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    if not config.checks:
        raise HTTPException(
            status_code=422,
            detail="Contract compiles to zero checks — add at least one guarantee.",
        )

    if not dry_run:
        _write_checks(product, yaml_out)

    return CompileOut(
        product=product,
        dataset=config.dataset,
        checks=[
            {
                "name": c.name,
                "sql": c.sql,
                "expect": c.expect,
                "severity": c.severity,
                "type": c.type,
                "unit": c.unit,
                "owned_by": c.owned_by,
                "kind": c.kind,
            }
            for c in config.checks
        ],
        yaml_preview=yaml_out,
        conflicts=conflicts,
        determinism_hash=det_hash,
    )


@router.post("/{product}/certify", response_model=ContractOut)
def certify_contract(
    product: str,
    principal: PrincipalDep,
    body: ContractIn = Body(...),
    store: StoreDep = ...,
    inventory: list[dict] = Depends(get_inventory),
):
    """[AUTHZ] [CONTRACT-SQL-FREE] Lite-Modus: save → active → compile in einem Schritt.

    Der Lite-Modus (HANDOVER N1/D8) trägt bewusst KEINE SemVer-/Approval-Zeremonie:
    es gibt keinen Draft-Zwischenschritt und keine Versions-Promotion von Hand.
    Damit Garantien sofort als persistente Checks + Compliance-Ampel im Cockpit
    erscheinen, zertifiziert dieser Pfad direkt und kompiliert die Check-Suite.

    Was unverändert gilt:
      - G1 (kein SQL im Contract) — jeder Ingestion-Pfad validiert.
      - G3 (Breaking ⇒ Major) bleibt für bereits zertifizierte Produkte scharf:
        Lite darf ein Produkt von Null aufsetzen, aber keinen *breaking* Change an
        einer bestehenden aktiven Version am Gate vorbeischmuggeln — der muss über
        den Voll-Modus (/approve) laufen.
    """
    from dq_core.contract.compiler import CompileError
    from dq_core.contract.diff import diff_contracts, is_breaking
    from dq_core.contract.validator import validate_contract

    _validate_product(product)
    existing = _load_contract(product)

    # [AUTHZ] — S-2: gegen den bestehenden Contract entscheiden, nicht den Body.
    _require_write(principal, existing)

    data = body.model_dump()
    data["lifecycle"] = "active"
    kind = data.get("kind", "internal_gate")
    is_contract = kind in ("consumer_contract", "provider_contract")

    # [CONTRACT-SQL-FREE] Gate G1
    errors = validate_contract(data)
    if errors:
        raise HTTPException(
            status_code=422,
            detail={"message": "Contract validation failed (Gate G1)", "errors": errors},
        )

    # G3 bleibt für zertifizierte Produkte scharf — kein Breaking-Bypass via Lite.
    snapshot_path = _active_snapshot_path(product)
    if is_contract and snapshot_path.exists():
        prior = yaml.safe_load(snapshot_path.read_text(encoding="utf-8")) or {}
        entries = diff_contracts(prior, data)
        if is_breaking(entries) and _semver_major(data.get("version", "0")) <= _semver_major(prior.get("version", "0")):
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "Breaking change on a certified contract — use the full-mode approval flow (Gate G3).",
                    "from_version": prior.get("version"),
                    "to_version": data.get("version"),
                    "breaking": [
                        {"kind": e.kind, "path": e.path, "old": e.old_value, "new": e.new_value}
                        for e in entries if e.breaking
                    ],
                },
            )

    # Compile BEFORE persisting anything: a contract that yields no checks must
    # not certify — nothing would be measured, the ampel would stay meaningless.
    try:
        yaml_out, _conflicts, _det_hash, config = _compile_contract_data(product, data, inventory)
    except CompileError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if not config.checks:
        raise HTTPException(
            status_code=422,
            detail="Contract compiles to zero checks — add at least one guarantee before certifying.",
        )

    # Persist: contract + certified snapshot (G3-Diff-Basis) + index + checks.
    _save_contract(product, data)
    snapshot_path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    _update_index(store, product, data)
    _write_checks(product, yaml_out)

    # One commit per certify. Fehlendes Git-Repo (lokaler Modus) ist legal (S-12).
    commit_error = None
    try:
        GitRepo(get_settings().contracts_dir, get_settings().git_remote).write_contract(
            product,
            yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
            principal.name,
            f"{principal.sub}@dq-cockpit",
            f"Certify (lite) contract {product} v{data.get('version')}",
        )
    except GitPushRejected as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        commit_error = str(exc)

    # Governance contracts start 'unknown' until the first run of the certified version.
    # Internal gates never write dq_compliance/dq_compliance_events.
    if is_contract and not store.get_compliance(product):
        store.set_compliance(product, str(data.get("version", "")), "unknown", "")

    out = _contract_out(store, product, data)
    if commit_error:
        raise HTTPException(
            status_code=502,
            detail={
                "message": "Contract certified, but the Git commit failed — repository intervention required.",
                "git_error": commit_error,
                "contract": out.model_dump(),
            },
        )
    return out


@router.get("/{product}/sla")
def get_contract_sla(product: str, store: StoreDep = ...):
    """R4-3: SLA-Compliance über Zeitfenster — %-compliant aus dem
    Compliance-Event-Log, nicht nur Letzter-Lauf-Zustand."""
    _validate_product(product)
    data = _load_contract(product)
    if not data:
        raise HTTPException(status_code=404, detail=f"Contract {product!r} not found")
    kind = data.get("kind", "internal_gate")
    if kind == "internal_gate":
        return {
            "product": product,
            "kind": kind,
            "current": "unknown",
            "windows": {"7d": None, "30d": None, "90d": None},
        }
    compliance_row = store.get_compliance(product)
    return {
        "product": product,
        "kind": kind,
        "current": compliance_row["compliance"] if compliance_row else "unknown",
        "windows": {
            "7d": store.get_sla(product, 7),
            "30d": store.get_sla(product, 30),
            "90d": store.get_sla(product, 90),
        },
    }


def _update_index(store, product: str, data: dict) -> None:
    import sqlite3
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    try:
        conn = sqlite3.connect(store.db_path, check_same_thread=False)
        conn.execute(
            """INSERT OR REPLACE INTO contract_index
               (product, lifecycle, owned_by, version, head_hash, updated_at, kind)
               VALUES (?,?,?,?,?,?,?)""",
            (
                product,
                data.get("lifecycle", "draft"),
                data.get("owned_by", "platform"),
                str(data.get("version", "0.1.0")),
                hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()[:16],
                now,
                data.get("kind", "internal_gate"),
            ),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


@router.get("/{product}/export/odcs")
def export_odcs(product: str, principal: PrincipalDep, format: str = Query(default="json")):
    """R5-1: ODCS-3.1-Export (Bitol) — Interop mit OpenMetadata/Collibra/
    datacontract-cli/Soda. Einweg; Compliance bleibt draußen (A1)."""
    from dq_core.contract.odcs_export import to_odcs

    _validate_product(product)
    data = _load_contract(product)
    if not data:
        raise HTTPException(status_code=404, detail=f"Contract {product!r} not found")
    if data.get("kind", "internal_gate") == "internal_gate":
        raise HTTPException(
            status_code=409,
            detail="Internal gates cannot be exported as ODCS data contracts.",
        )
    odcs = to_odcs(data)
    if format == "yaml":
        from fastapi.responses import Response
        return Response(
            content=yaml.safe_dump(odcs, sort_keys=False, allow_unicode=True),
            media_type="application/yaml",
        )
    return odcs


@router.post("/{product}/export/bdc")
def export_bdc(product: str, principal: PrincipalDep):
    """Generate CSN + ORD artifact fragments for BDC integration. (WS5-4)

    Einseitig (E1): files are returned as JSON for manual deployment.
    Never writes to DB or catalog.
    """
    _validate_product(product)
    data = _load_contract(product)
    if not data:
        raise HTTPException(status_code=404, detail=f"Contract {product!r} not found")

    guarantees = data.get("guarantees") or {}
    dataset = data.get("dataset", product)

    # CSN fragment: custom namespace annotations per column/guarantee
    csn_elements: dict = {}
    schema_g = guarantees.get("schema") or {}
    for col in (schema_g.get("columns") or []):
        csn_elements[col] = {"@DQ.guarantee": "schema", "@DQ.product": product}
    for comp in (guarantees.get("completeness") or []):
        col = comp.get("column", "")
        if col:
            csn_elements.setdefault(col, {})
            csn_elements[col]["@DQ.completeness"] = comp.get("min_pct", 99.0)
    for ref in (guarantees.get("referential") or []):
        for fk_col in (ref.get("fk") or []):
            csn_elements.setdefault(fk_col, {})
            csn_elements[fk_col]["@DQ.referential"] = ref.get("parent", "")

    csn_fragment = {
        "$version": "2.0",
        "definitions": {
            dataset: {
                "kind": "entity",
                "@DQ.product": product,
                "@DQ.lifecycle": data.get("lifecycle", "draft"),
                "elements": csn_elements,
            }
        },
    }

    # ORD fragment: custom labels for product-level guarantees
    guarantee_labels: list[str] = []
    if guarantees.get("keys"):
        guarantee_labels.append("keys:unique")
    if guarantees.get("freshness"):
        freshness = guarantees["freshness"]
        guarantee_labels.append(f"freshness:{freshness.get('max_age','')}")
    if guarantees.get("volume"):
        guarantee_labels.append("volume:baseline")
    if guarantees.get("schema"):
        mode = (guarantees["schema"].get("mode") or "open")
        guarantee_labels.append(f"schema:{mode}")

    ord_fragment = {
        "openResourceDiscovery": "1.9",
        "consumptionBundles": [
            {
                "ordId": f"sap.dq:{product}:consumptionBundle:dq:v1",
                "title": f"DQ Contract — {dataset}",
                "description": f"Data quality guarantees for {dataset}",
                "labels": {
                    "dq:product": [product],
                    "dq:lifecycle": [data.get("lifecycle", "draft")],
                    "dq:guarantee": guarantee_labels,
                    "dq:owned_by": [data.get("owned_by", "platform")],
                },
            }
        ],
    }

    return {"csn_fragment": csn_fragment, "ord_fragment": ord_fragment}


# Compiler-Check-`type` → Garantie-Familie. Deterministisch (compiler.py); die
# Namensbildung bleibt einzige Wahrheit im Engine-Compiler, hier nur die Umkehr.
_TYPE_TO_FAMILY: dict[str, str] = {
    "schema": "schema",
    "duplicate": "keys", "duplicate_composite": "keys",
    "reference_integrity": "referential",
    "freshness": "freshness",
    "row_count": "volume",
    "completeness_pct": "completeness", "completeness_pct_segment": "completeness",
    "missing": "not_null",
}


def _to_float(raw: Any) -> Optional[float]:
    if raw is None or raw == "":
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


@router.get("/{product}/observed", response_model=ObservedOut)
def observed_reality(
    product: str,
    limit: int = Query(default=15, ge=1, le=200),
    store: StoreDep = ...,
    inventory: list[dict] = Depends(get_inventory),
):
    """Beobachtete Realität je Garantie (P6): letzter Messwert, Sparkline-Reihe
    und PASS/FAIL. Read-only-Rollup — der Compiler bildet Garantien auf Checks ab
    (einzige Wahrheit für die Namensbildung), die persistierte Result-Historie
    liefert die Werte. Aggregat-Werte, keine Rohzeilen (G8 unberührt).
    """
    _validate_product(product)
    data = _load_contract(product)
    if data is None:
        raise HTTPException(status_code=404, detail=f"Contract {product!r} not found")

    dataset = str(data.get("dataset") or product)

    # Ein noch nicht valider Entwurf soll die Ansicht nicht mit 500 abbrechen —
    # dann gibt es eben (noch) keine beobachtete Realität.
    try:
        _yaml, _conflicts, _hash, config = _compile_contract_data(product, data, inventory)
    except Exception:  # noqa: BLE001 — defensiv: leer statt 500 bei ungültigem Entwurf
        return ObservedOut(product=product, dataset=dataset, guarantees=[])

    families: dict[str, list[ObservedCheck]] = {}
    for check in config.checks:
        family = _TYPE_TO_FAMILY.get(check.type)
        history = store.get_check_history(dataset, check.name, limit=limit)
        points = [
            ObservedPoint(
                at=str(h.get("started_at") or ""),
                value=_to_float(h.get("actual_value")),
                raw=(None if h.get("actual_value") is None else str(h.get("actual_value"))),
                passed=(None if h.get("passed") is None else bool(h.get("passed"))),
                state=str(h.get("state") or "executed"),
                run_id=str(h.get("run_id") or ""),
            )
            for h in reversed(history)  # get_check_history liefert DESC → aufsteigend für die Sparkline
        ]
        latest = history[0] if history else None
        families.setdefault(family or "checks", []).append(ObservedCheck(
            name=check.name,
            type=check.type,
            family=family,
            severity=check.severity,
            expect=check.expect,
            last_value=(None if not latest or latest.get("actual_value") is None else str(latest.get("actual_value"))),
            passed=(None if not latest or latest.get("passed") is None else bool(latest.get("passed"))),
            state=(str(latest.get("state")) if latest else ""),
            points=points,
        ))

    guarantees: list[ObservedGuarantee] = []
    for family, checks in families.items():
        states = [c.passed for c in checks if c.passed is not None]
        state = "unknown" if not states else "pass" if all(states) else "fail"
        guarantees.append(ObservedGuarantee(family=family, state=state, checks=checks))

    return ObservedOut(product=product, dataset=dataset, guarantees=guarantees)
