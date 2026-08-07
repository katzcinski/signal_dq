"""Runtime resolution for adaptive observability checks."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..contract.compiler import SAFE_IDENTIFIER
from ..engine.models import CheckDef, CheckResult, DatasetConfig, RunSummary
from .baselines import BaselineManager


@dataclass
class ObservabilityResolution:
    config: DatasetConfig
    downgraded_results: list[CheckResult] = field(default_factory=list)


def resolve_observability_checks(
    config: DatasetConfig,
    contract: dict[str, Any] | None,
    manager: BaselineManager,
    *,
    started_at: str,
) -> ObservabilityResolution:
    obs = (contract or {}).get("observability") or {}
    if not isinstance(obs, dict) or not obs:
        return ObservabilityResolution(config=config)

    checks = list(config.checks)
    downgraded: list[CheckResult] = []

    volume_cfg = _family_cfg(obs.get("volume"))
    if volume_cfg is not None:
        check, skipped = _volume_check(config, volume_cfg, manager, started_at=started_at)
        if check is not None:
            checks.append(check)
        elif skipped is not None:
            downgraded.append(skipped)

    freshness_cfg = _family_cfg(obs.get("freshness"))
    if freshness_cfg is not None:
        check, skipped = _freshness_check(config, contract or {}, freshness_cfg, manager, started_at=started_at)
        if check is not None:
            checks.append(check)
        elif skipped is not None:
            downgraded.append(skipped)

    config.checks = checks
    return ObservabilityResolution(config=config, downgraded_results=downgraded)


def append_downgraded(summary: RunSummary, downgraded: list[CheckResult]) -> RunSummary:
    if not downgraded:
        return summary
    summary.results.extend(downgraded)
    executed = [r for r in summary.results if r.state in ("executed", "error")]
    summary.total = len(summary.results)
    summary.passed = sum(1 for r in executed if r.passed)
    summary.failed = sum(
        1 for r in executed
        if not r.passed and r.severity in {"critical", "fail"}
    )
    summary.warnings = sum(
        1 for r in executed
        if not r.passed and r.severity == "warn"
    )
    summary.overall_status = _overall_status(executed)
    return summary


def _family_cfg(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        return None
    return {
        "baseline": str(value.get("baseline") or "rolling"),
        "season": list(value.get("season") or ["dow"]),
        "sensitivity": str(value.get("sensitivity") or "medium"),
    }


def _volume_check(
    config: DatasetConfig,
    obs_cfg: dict[str, Any],
    manager: BaselineManager,
    *,
    started_at: str,
) -> tuple[CheckDef | None, CheckResult | None]:
    metric = _first_check_name(config, {"row_count"}, default="volume_min_rows")
    name = "volume_adaptive_rows"
    sql = f'SELECT COUNT(*) FROM "{config.schema}"."{config.dataset}"'
    baseline = _baseline_for(config.dataset, metric, obs_cfg, manager, started_at)
    if not _baseline_ready(baseline):
        return None, _downgraded(name, sql, "volume_anomaly", baseline)
    k = manager.sensitivity_k(obs_cfg.get("sensitivity"))
    lo, hi = manager.compute_robust_bounds(baseline, k=k)
    return CheckDef(
        name=name,
        sql=sql,
        expect=f"BETWEEN {_num(lo)} AND {_num(hi)}",
        severity="warn",
        type="volume_anomaly",
        unit="rows",
        owned_by=config.owned_by,
        kind="internal_gate",
    ), None


def _freshness_check(
    config: DatasetConfig,
    contract: dict[str, Any],
    obs_cfg: dict[str, Any],
    manager: BaselineManager,
    *,
    started_at: str,
) -> tuple[CheckDef | None, CheckResult | None]:
    fresh = (contract.get("guarantees") or {}).get("freshness") or {}
    column = str(fresh.get("column") or "")
    if not SAFE_IDENTIFIER.match(column):
        return None, None
    metric = _first_check_name(config, {"freshness"}, default=f"freshness_{column}")
    name = f"freshness_adaptive_{column}"
    sql = (
        f'SELECT SECONDS_BETWEEN(MAX("{column}"), CURRENT_TIMESTAMP) '
        f'FROM "{config.schema}"."{config.dataset}"'
    )
    baseline = _baseline_for(config.dataset, metric, obs_cfg, manager, started_at)
    if not _baseline_ready(baseline):
        return None, _downgraded(name, sql, "freshness_anomaly", baseline)
    k = manager.sensitivity_k(obs_cfg.get("sensitivity"))
    lo, hi = manager.compute_robust_bounds(baseline, k=k)
    return CheckDef(
        name=name,
        sql=sql,
        expect=f"BETWEEN {_num(lo)} AND {_num(hi)}",
        severity="warn",
        type="freshness_anomaly",
        unit="s",
        owned_by=config.owned_by,
        kind="internal_gate",
    ), None


def _baseline_for(
    dataset: str,
    metric: str,
    obs_cfg: dict[str, Any],
    manager: BaselineManager,
    started_at: str,
) -> dict | None:
    strategy = str(obs_cfg.get("baseline") or "rolling")
    if strategy == "seasonal":
        bucket_key = manager.bucket_key_for(started_at, obs_cfg.get("season") or ["dow"])
        return manager.get_baseline(dataset, metric, strategy="seasonal", bucket_key=bucket_key)
    return manager.get_baseline(dataset, metric)


def _baseline_ready(baseline: dict | None) -> bool:
    if not baseline:
        return False
    if int(baseline.get("warmup_remaining") or 0) > 0:
        return False
    return baseline.get("median_v") is not None or baseline.get("mean_v") is not None


def _downgraded(name: str, sql: str, check_type: str, baseline: dict | None) -> CheckResult:
    error = "baseline_missing" if not baseline else "baseline_warmup"
    return CheckResult(
        name=name,
        sql=sql,
        expect="baseline_ready",
        severity="warn",
        passed=False,
        actual_value=None,
        error=error,
        state="downgraded",
        type=check_type,
        kind="internal_gate",
    )


def _first_check_name(config: DatasetConfig, types: set[str], *, default: str) -> str:
    for check in config.checks:
        if check.type in types:
            return check.name
    return default


def _num(value: float) -> str:
    return f"{float(value):.6f}".rstrip("0").rstrip(".")


def _overall_status(executed: list[CheckResult]) -> str:
    if any(r.error for r in executed):
        return "error"
    failed = [r.severity for r in executed if not r.passed]
    if "critical" in failed:
        return "critical"
    if "fail" in failed:
        return "fail"
    if "warn" in failed:
        return "warn"
    return "pass"
