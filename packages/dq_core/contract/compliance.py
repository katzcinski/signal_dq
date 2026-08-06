# Compliance-state computation (WS2-5) — framework-free, lives in dq_core.
# [A1] compliance lives only in the store, never in the contract YAML.
from __future__ import annotations

from typing import Any, Iterable

# Severities that count toward a breach when their check fails.
BREACHING_SEVERITIES = {"fail", "critical"}

COMPLIANT = "compliant"
BREACHED = "breached"
UNKNOWN = "unknown"


def compute_compliance(results: Iterable[Any]) -> str:
    """Derive compliance state from a run's check results.

    Rule v1 (HANDOVER WS2-5): ``breached`` if >=1 check with severity in
    {fail, critical} did not pass; auto-recovery to ``compliant`` once every
    such check passes. ``unknown`` only when there are no results at all.

    Accepts either engine ``CheckResult`` dataclasses (``.severity``/``.passed``)
    or plain dicts (``severity``/``passed``), so it works for both the live
    engine output and persisted store rows.
    """
    results = list(results)
    if not results:
        return UNKNOWN

    for r in results:
        severity = _get(r, "severity")
        passed = _get(r, "passed")
        if severity in BREACHING_SEVERITIES and not _truthy_pass(passed):
            return BREACHED
    return COMPLIANT


def _get(row: Any, key: str) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    return getattr(row, key, None)


def _truthy_pass(passed: Any) -> bool:
    # store rows persist `passed` as 0/1 integers; engine uses bool.
    return bool(passed)
