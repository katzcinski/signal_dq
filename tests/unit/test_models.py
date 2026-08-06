"""Tests for models.py — dataclass defaults and constants."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[2] / "packages"))

from dq_core.engine.models import (
    CheckDef, CheckResult, DatasetConfig, RunSummary,
    VALID_OWNERS, VALID_SEVERITIES, VALID_KINDS,
)


def test_valid_owners_set():
    assert "platform" in VALID_OWNERS
    assert "product" in VALID_OWNERS


def test_valid_severities_set():
    assert {"critical", "fail", "warn"} == VALID_SEVERITIES


def test_valid_kinds_set():
    assert {"internal_gate", "consumer_contract", "provider_contract"} == VALID_KINDS


def test_check_def_defaults():
    cd = CheckDef(name="test", sql="SELECT 1", expect="= 1")
    assert cd.severity == "fail"
    assert cd.enabled is True
    assert cd.timeout_s == 60
    assert cd.owned_by == "platform"
    assert cd.kind == "internal_gate"


def test_check_result_defaults():
    cr = CheckResult(name="test", sql="SELECT 1", expect="= 1", severity="fail", passed=True)
    assert cr.actual_value is None
    assert cr.error is None
    assert cr.state == "executed"
    assert cr.kind == "internal_gate"
    assert cr.diagnostic_rows == []


def test_dataset_config_defaults():
    dc = DatasetConfig(dataset="DS", schema="SCH")
    assert dc.owned_by == "platform"
    assert dc.checks == []


def test_run_summary_defaults():
    rs = RunSummary(
        run_id="r1", dataset="DS", schema="SCH",
        started_at="2026-01-01T00:00:00Z", finished_at="2026-01-01T00:01:00Z",
        overall_status="pass", total=1, passed=1, failed=0, warnings=0,
    )
    assert rs.triggered_by == "manual"
    assert rs.run_state == "finished"
    assert rs.results == []
