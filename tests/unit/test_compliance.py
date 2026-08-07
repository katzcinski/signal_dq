"""WS2-5 compliance computation."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "packages"))

from dq_core.contract.compliance import compute_compliance, COMPLIANT, BREACHED, UNKNOWN
from dq_core.engine.models import CheckResult


def _r(name, severity, passed):
    return CheckResult(name=name, sql="", expect="", severity=severity, passed=passed)


def test_empty_results_unknown():
    assert compute_compliance([]) == UNKNOWN


def test_all_pass_compliant():
    assert compute_compliance([_r("a", "fail", True), _r("b", "critical", True)]) == COMPLIANT


def test_failed_fail_severity_breached():
    assert compute_compliance([_r("a", "fail", False)]) == BREACHED


def test_failed_critical_breached():
    assert compute_compliance([_r("a", "warn", True), _r("b", "critical", False)]) == BREACHED


def test_failed_warn_only_still_compliant():
    # warn failures do not breach compliance (rule v1: only fail/critical)
    assert compute_compliance([_r("a", "warn", False)]) == COMPLIANT


def test_accepts_dict_rows():
    rows = [{"severity": "fail", "passed": 0}]  # store persists passed as int
    assert compute_compliance(rows) == BREACHED
