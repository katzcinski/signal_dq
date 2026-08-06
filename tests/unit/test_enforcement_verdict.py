"""Enforcement-Achse (Layer 1): Verdict-Rollup, Config-Parsing, Compiler-
Propagation und Validator-Ablehnung (Konzept_Enforcement_Modi §4 /
Konzept_Datasphere_Integration §1)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "packages"))

from dq_core.engine.check_engine import _gate_verdict, dataset_config_to_yaml, load_dataset_config
from dq_core.engine.models import CheckResult, VALID_ENFORCEMENT


def _result(*, enforcement="monitor", severity="fail", passed=False, state="executed"):
    return CheckResult(
        name="c", sql="SELECT 1", expect="= 0", severity=severity,
        passed=passed, state=state, enforcement=enforcement,
    )


class TestGateVerdict:
    def test_all_passing_is_proceed(self):
        assert _gate_verdict([_result(passed=True, enforcement="gate")]) == "proceed"

    def test_failed_gate_check_blocks(self):
        assert _gate_verdict([_result(enforcement="gate")]) == "block"

    def test_failed_quarantine_check_quarantines(self):
        assert _gate_verdict([_result(enforcement="quarantine")]) == "quarantine"

    def test_monitor_fail_never_escalates(self):
        assert _gate_verdict([_result(enforcement="monitor", severity="critical")]) == "proceed"

    def test_block_wins_over_quarantine(self):
        results = [_result(enforcement="quarantine"), _result(enforcement="gate")]
        assert _gate_verdict(results) == "block"

    def test_warn_severity_is_soft_signal_only(self):
        # Ein warn-Fail in gate ist ein weiches Signal — blockiert nie.
        assert _gate_verdict([_result(enforcement="gate", severity="warn")]) == "proceed"

    def test_skipped_stale_is_state_neutral(self):
        # G6: übersprungene Checks behalten ihren Modus, bleiben statusneutral.
        assert _gate_verdict([_result(enforcement="gate", state="skipped_stale")]) == "proceed"
        assert _gate_verdict([_result(enforcement="quarantine", state="skipped_dependency")]) == "proceed"
        assert _gate_verdict([_result(enforcement="gate", state="downgraded")]) == "proceed"

    def test_error_state_counts_fail_closed(self):
        # Ein errored gate-Check zählt (state error, passed=False) — fail-closed.
        assert _gate_verdict([_result(enforcement="gate", state="error")]) == "block"

    def test_empty_results_proceed(self):
        assert _gate_verdict([]) == "proceed"


class TestConfigParsing:
    def _config(self, tmp_path, enforcement_line=""):
        yaml_text = (
            "dataset: DEMO\n"
            'schema: "{schema}"\n'
            "checks:\n"
            "  - name: c1\n"
            "    sql: SELECT COUNT(*) FROM DUMMY\n"
            '    expect: "= 0"\n'
            + enforcement_line
        )
        p = tmp_path / "checks.yaml"
        p.write_text(yaml_text, encoding="utf-8")
        return p

    def test_default_is_monitor(self, tmp_path):
        config = load_dataset_config(self._config(tmp_path))
        assert config.checks[0].enforcement == "monitor"

    def test_explicit_enforcement_parsed(self, tmp_path):
        config = load_dataset_config(self._config(tmp_path, "    enforcement: gate\n"))
        assert config.checks[0].enforcement == "gate"

    def test_invalid_enforcement_rejected(self, tmp_path):
        with pytest.raises(ValueError, match="enforcement"):
            load_dataset_config(self._config(tmp_path, "    enforcement: nonsense\n"))

    def test_yaml_roundtrip_keeps_enforcement(self, tmp_path):
        config = load_dataset_config(self._config(tmp_path, "    enforcement: quarantine\n"))
        dumped = dataset_config_to_yaml(config)
        p = tmp_path / "roundtrip.yaml"
        p.write_text(dumped, encoding="utf-8")
        again = load_dataset_config(p)
        assert again.checks[0].enforcement == "quarantine"


class TestCompilerPropagation:
    def _contract(self, **extra):
        return {
            "product": "SALES", "dataset": "SALES", "version": "1.0.0",
            "guarantees": {
                "freshness": {"column": "TS", "max_age": "PT24H"},
                "not_null": [{"columns": ["A"]}],
            },
            **extra,
        }

    def test_default_monitor_without_contract_default(self):
        from dq_core.contract.compiler import compile_contract
        cfg = compile_contract(self._contract())
        assert {c.enforcement for c in cfg.checks} == {"monitor"}

    def test_contract_default_applies_to_all_guarantees(self):
        from dq_core.contract.compiler import compile_contract
        cfg = compile_contract(self._contract(enforcement_default="gate"))
        assert {c.enforcement for c in cfg.checks} == {"gate"}

    def test_guarantee_overrides_contract_default(self):
        from dq_core.contract.compiler import compile_contract
        contract = self._contract(enforcement_default="gate")
        contract["guarantees"]["freshness"]["enforcement"] = "quarantine"
        cfg = compile_contract(contract)
        by_name = {c.name: c.enforcement for c in cfg.checks}
        assert by_name["freshness_TS"] == "quarantine"
        assert by_name["A_not_null"] == "gate"

    def test_invalid_enforcement_default_rejected(self):
        from dq_core.contract.compiler import CompileError, compile_contract
        with pytest.raises(CompileError, match="enforcement_default"):
            compile_contract(self._contract(enforcement_default="nonsense"))

    def test_enforcement_is_dataclass_only_no_sql_change(self):
        # G1/G2: Enforcement ändert nie das kompilierte SQL.
        from dq_core.contract.compiler import compile_contract
        plain = compile_contract(self._contract())
        gated = compile_contract(self._contract(enforcement_default="gate"))
        assert [c.sql for c in plain.checks] == [c.sql for c in gated.checks]


class TestValidator:
    def test_valid_enforcement_accepted(self):
        from dq_core.contract.validator import validate_contract
        for mode in sorted(VALID_ENFORCEMENT):
            errors = validate_contract({
                "product": "X", "dataset": "X", "version": "1.0.0",
                "enforcement_default": mode,
                "guarantees": {"not_null": [{"columns": ["A"], "enforcement": mode}]},
            })
            assert errors == []

    def test_invalid_enforcement_rejected(self):
        from dq_core.contract.validator import validate_contract
        errors = validate_contract({
            "product": "X", "dataset": "X", "version": "1.0.0",
            "guarantees": {"not_null": [{"columns": ["A"], "enforcement": "hard_stop"}]},
        })
        assert any("enforcement" in e for e in errors)

    def test_invalid_default_rejected(self):
        from dq_core.contract.validator import validate_contract
        errors = validate_contract({
            "product": "X", "dataset": "X", "version": "1.0.0",
            "enforcement_default": "nonsense", "guarantees": {},
        })
        assert any("enforcement_default" in e for e in errors)
