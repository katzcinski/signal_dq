from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ..auth.provider import PrincipalDep
from ..deps import StoreDep
from ..schemas.run_schemas import RunSummaryOut, RunListItem, CheckResultOut, RunStatusOut

router = APIRouter(prefix="/api/runs", tags=["runs"])

# Normalised per-check status used for the regression diff (UX-N5). Gating
# states (skipped/downgraded) never collapse into pass/fail (G6).
_STATUS_RANK = {"pass": 0, "skipped": 0, "warn": 1, "fail": 2, "error": 3}


def _check_status(res: CheckResultOut) -> str:
    if res.state == "error":
        return "error"
    if res.state in ("skipped_stale", "skipped_dependency"):
        return "skipped"
    if res.passed:
        return "pass"
    return "warn" if res.severity == "warn" else "fail"


def _transition(base: str | None, head: str | None) -> str:
    """Classify a per-check status change between two runs (base → head)."""
    if base is None:
        return "added"
    if head is None:
        return "removed"
    if base == head:
        return "unchanged"
    base_rank = _STATUS_RANK.get(base, 0)
    head_rank = _STATUS_RANK.get(head, 0)
    if head_rank > base_rank:
        return "regressed"
    if head_rank < base_rank:
        return "recovered"
    return "changed"


def _to_number(value) -> float | None:
    """actual_value wird als String persistiert — best-effort numerische Sicht."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _value_delta(base, head) -> dict:
    """B-1 (§B.2): vorher/nachher je Check, inkl. absolutem und prozentualem Delta.
    Nicht-numerische actual_values liefern nur base/head (delta = None)."""
    b, h = _to_number(base), _to_number(head)
    abs_delta = (h - b) if (b is not None and h is not None) else None
    pct_delta = None
    if abs_delta is not None and b not in (None, 0):
        pct_delta = round(abs_delta / abs(b) * 100, 2)
    return {
        "base": base,
        "head": head,
        "abs_delta": abs_delta,
        "pct_delta": pct_delta,
    }


def _result_out(row: dict) -> CheckResultOut:
    """Map a raw dq_check_results row to the API/FE field names."""
    return CheckResultOut(
        name=row.get("check_name", ""),
        sql=row.get("sql_text", "") or "",
        expect=row.get("expect_expr", "") or "",
        severity=row.get("severity", "fail"),
        passed=bool(row.get("passed")),
        actual_value=row.get("actual_value"),
        error=row.get("error_message"),
        duration_ms=row.get("duration_ms", 0) or 0,
        state=row.get("state", "executed"),
        type=row.get("check_type", "") or "",
        kind=row.get("kind", "internal_gate") or "internal_gate",
        enforcement=row.get("enforcement_mode", "monitor") or "monitor",
    )


def _run_out(run: dict) -> RunSummaryOut:
    """Normalise a raw dq_runs row (+ results) into the FE-facing schema."""
    return RunSummaryOut(
        run_id=run["run_id"],
        dataset=run.get("dataset", ""),
        schema_name=run.get("schema_name", ""),
        started_at=run.get("started_at", "") or "",
        finished_at=run.get("finished_at", "") or "",
        overall_status=run.get("overall_status", "pass"),
        total=run.get("total_checks", 0) or 0,
        passed=run.get("passed_checks", 0) or 0,
        failed=run.get("failed_checks", 0) or 0,
        warnings=run.get("warning_checks", 0) or 0,
        triggered_by=run.get("triggered_by", "manual"),
        contract_version=run.get("contract_version", "") or "",
        contract_hash=run.get("contract_hash", "") or "",
        actor=run.get("actor", "") or "",
        run_state=run.get("run_state", "finished"),
        gate_verdict=run.get("gate_verdict", "proceed") or "proceed",
        results=[_result_out(r) for r in run.get("results", [])],
    )


@router.get("", response_model=list[RunListItem])
def list_runs(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    store: StoreDep = ...,
):
    runs = store.get_all_runs(limit=limit, offset=offset)
    return [RunListItem(**{k: v for k, v in r.items() if k in RunListItem.model_fields}) for r in runs]


def _compare_header(run: dict) -> dict:
    return {
        "run_id": run["run_id"],
        "dataset": run.get("dataset", ""),
        "started_at": run.get("started_at", "") or "",
        "finished_at": run.get("finished_at", "") or "",
        "overall_status": run.get("overall_status", "pass"),
        "total": run.get("total_checks", 0) or 0,
        "passed": run.get("passed_checks", 0) or 0,
        "failed": run.get("failed_checks", 0) or 0,
        "warnings": run.get("warning_checks", 0) or 0,
    }


@router.get("/compare")
def compare_runs(
    base: str = Query(..., description="Baseline run_id (earlier)"),
    head: str = Query(..., description="Comparison run_id (later)"),
    store: StoreDep = ...,
):
    """UX-N5: regression diff of two runs — per-check status transitions
    (newly red vs. recovered). Server-authoritative so the FE only renders."""
    base_run = store.get_run(base)
    if not base_run:
        raise HTTPException(status_code=404, detail=f"Run {base!r} not found")
    head_run = store.get_run(head)
    if not head_run:
        raise HTTPException(status_code=404, detail=f"Run {head!r} not found")

    base_out = [_result_out(x) for x in base_run.get("results", [])]
    head_out = [_result_out(x) for x in head_run.get("results", [])]
    base_status = {r.name: _check_status(r) for r in base_out}
    head_status = {r.name: _check_status(r) for r in head_out}
    # B-1 Value-Diff (§B.2): actual_value je Check, numerisch wo möglich.
    base_actual = {r.name: r.actual_value for r in base_out}
    head_actual = {r.name: r.actual_value for r in head_out}

    changes = []
    summary = {"regressed": 0, "recovered": 0, "added": 0, "removed": 0, "changed": 0, "unchanged": 0}
    for name in sorted(base_status.keys() | head_status.keys()):
        b = base_status.get(name)
        h = head_status.get(name)
        transition = _transition(b, h)
        summary[transition] = summary.get(transition, 0) + 1
        changes.append({
            "check_name": name,
            "base_status": b,
            "head_status": h,
            "transition": transition,
            "value_delta": _value_delta(base_actual.get(name), head_actual.get(name)),
        })

    return {
        "base": _compare_header(base_run),
        "head": _compare_header(head_run),
        "summary": summary,
        "changes": changes,
    }


@router.get("/{run_id}", response_model=RunSummaryOut)
def get_run(run_id: str, store: StoreDep = ...):
    run = store.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id!r} not found")
    return _run_out(run)


_VALID_FAIL_ON = {"block", "block_and_quarantine"}


@router.get("/{run_id}/status", response_model=RunStatusOut)
def get_run_status(
    run_id: str,
    fail_on: str = Query(default="block_and_quarantine"),
    store: StoreDep = ...,
):
    """API-Task-Vertrag (AP-1): Status-Endpoint für den asynchronen
    Task-Chain-Aufruf. Solange der Lauf läuft RUNNING, danach das binäre
    Verdict-Mapping: `proceed` → COMPLETED, `block` → FAILED; `quarantine`
    folgt `fail_on` — Pipelines, die aus der CLEAN-View lesen, setzen
    `fail_on=block` und laufen bei Quarantäne weiter (Isolation trägt die
    View). Default ist fail-closed (`block_and_quarantine`). Ein Lauf im
    Zustand `error` ist immer FAILED (fail-closed)."""
    if fail_on not in _VALID_FAIL_ON:
        raise HTTPException(status_code=422, detail=f"Unknown fail_on {fail_on!r}")
    run = store.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id!r} not found")

    run_state = run.get("run_state", "finished")
    verdict = run.get("gate_verdict", "proceed") or "proceed"
    if run_state == "running":
        status = "RUNNING"
    elif run_state == "error":
        status = "FAILED"
    elif verdict == "block" or (verdict == "quarantine" and fail_on == "block_and_quarantine"):
        status = "FAILED"
    else:
        status = "COMPLETED"
    return RunStatusOut(
        status=status,
        run_id=run_id,
        run_state=run_state,
        overall_status=run.get("overall_status", "pass"),
        gate_verdict=verdict,
        fail_on=fail_on,
    )


@router.get("/{run_id}/results", response_model=list[CheckResultOut])
def get_run_results(run_id: str, store: StoreDep = ...):
    """WS1-2: nur die Check-Ergebnisse eines Runs (ohne Run-Header)."""
    run = store.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id!r} not found")
    return [_result_out(r) for r in run.get("results", [])]


@router.get("/{run_id}/diagnostics")
def get_run_diagnostics(
    run_id: str,
    principal: PrincipalDep,
    check_name: str | None = Query(default=None),
    store: StoreDep = ...,
):
    """[PII-GATE] Diagnostik-Zeilen (bereits allowlist-projiziert persistiert).

    Defense-in-depth: Rohzeilen-Sicht erfordert steward+ — viewer sieht
    Skalare, nie Datensätze.
    """
    if not principal.has_role("steward", "owner", "admin"):
        raise HTTPException(status_code=403, detail="Diagnostics require steward role or higher.")
    if not store.get_run(run_id):
        raise HTTPException(status_code=404, detail=f"Run {run_id!r} not found")
    return store.get_diagnostics(run_id, check_name)


@router.get("/{run_id}/results/{check_name}/segments")
def get_run_result_segments(run_id: str, check_name: str, store: StoreDep = ...):
    run = store.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id!r} not found")
    names = {r.get("check_name") for r in run.get("results", [])}
    if check_name not in names:
        raise HTTPException(status_code=404, detail=f"Check {check_name!r} not found in run {run_id!r}")
    return store.get_segment_results(run_id, check_name)


@router.get("/{run_id}/events")
def get_run_events(run_id: str, store: StoreDep = ...):
    """Polling fallback for SSE (A5): returns persisted progress lines."""
    return store.get_progress(run_id)
