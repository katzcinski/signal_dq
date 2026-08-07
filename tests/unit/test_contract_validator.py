"""Gate G1 tests — SQL in contract must be rejected. [CONTRACT-SQL-FREE]

Inkl. der Injection-Fixtures aus dem Review (S-4/S-5): listen-wertige
Garantien, REGEX-Schmuggel, A2-'schema:'-Verbot, eigene Repo-Contracts grün.
"""
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parents[2] / "packages"))

from dq_core.contract.validator import validate_contract


VALID_CONTRACT = {
    "product": "sales_orders",
    "dataset": "Sales_Orders_View",
    "owned_by": "platform",
    "lifecycle": "draft",
    "version": "0.1.0",
    "guarantees": {
        "keys": [{"columns": ["OrderID"], "unique": True}],
        "freshness": {"column": "LOAD_TS", "max_age": "PT24H"},
    },
}


def test_valid_contract_passes():
    errors = validate_contract(VALID_CONTRACT)
    assert errors == []


def test_top_level_observability_is_valid():
    ok = {
        **VALID_CONTRACT,
        "observability": {
            "volume": {"baseline": "seasonal", "season": ["dow", "eom"], "sensitivity": "medium"},
            "freshness": {"baseline": "rolling", "sensitivity": "high"},
        },
    }
    assert validate_contract(ok) == []


def test_trend_observability_is_deferred():
    bad = {
        **VALID_CONTRACT,
        "observability": {"volume": {"baseline": "trend"}},
    }
    assert validate_contract(bad)


def test_shipped_contracts_validate_green():
    """S-5-Regression: der eigene Repo-Contract darf nicht am Validator scheitern."""
    contracts_dir = Path(__file__).parents[2] / "contracts"
    paths = [p for p in contracts_dir.glob("*.y*ml") if not p.name.endswith(".active.yml")]
    assert paths, "Keine Contracts im Repo gefunden"
    for path in paths:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert validate_contract(data) == [], f"{path.name} invalide"


def test_g1_rejects_select_in_value():
    bad = {**VALID_CONTRACT, "guarantees": {"custom": "SELECT * FROM table"}}
    errors = validate_contract(bad)
    assert errors, "SQL-Wert muss abgelehnt werden"


def test_g1_rejects_nested_sql_key():
    bad = {
        **VALID_CONTRACT,
        "guarantees": {"rule": {"sql": "SELECT COUNT(*) FROM foo WHERE x > 0"}},
    }
    errors = validate_contract(bad)
    assert errors, "sql:-Key muss abgelehnt werden"


def test_s2_rejects_unsafe_dataset_identifier():
    bad = {**VALID_CONTRACT, "dataset": "'; DROP TABLE users; --"}
    errors = validate_contract(bad)
    assert errors, "Unsicherer Dataset-Name muss abgelehnt werden"


def test_s2_rejects_injection_in_list_valued_keys():
    """Review S-4: listen-wertige Garantien wurden vorher NICHT geprüft."""
    bad = {
        **VALID_CONTRACT,
        "guarantees": {"keys": [{"columns": ['A" OR 1=1 --'], "unique": True}]},
    }
    errors = validate_contract(bad)
    assert errors, "Injection in keys[].columns muss abgelehnt werden"


def test_s2_rejects_injection_in_completeness_and_not_null():
    bad = {
        **VALID_CONTRACT,
        "guarantees": {
            "completeness": [{"column": 'X"; DROP TABLE y; --', "min_pct": 99.5}],
            "not_null": [{"columns": ["OK_COL", "BAD; --"]}],
        },
    }
    errors = validate_contract(bad)
    assert len(errors) >= 2, errors


def test_a2_rejects_schema_key():
    bad = {**VALID_CONTRACT, "schema": "CORE_DWH"}
    errors = validate_contract(bad)
    assert any("[A2]" in e for e in errors), errors


def test_rejects_legacy_max_age_hours():
    bad = {
        **VALID_CONTRACT,
        "guarantees": {"freshness": {"column": "LOAD_TS", "max_age_hours": 26}},
    }
    errors = validate_contract(bad)
    assert errors, "Nur ISO-8601 max_age ist kanonisch"


def test_invalid_lifecycle():
    bad = {**VALID_CONTRACT, "lifecycle": "published"}
    errors = validate_contract(bad)
    assert any("lifecycle" in e for e in errors), errors


def test_invalid_owned_by():
    bad = {**VALID_CONTRACT, "owned_by": "external"}
    errors = validate_contract(bad)
    assert any("owned_by" in e for e in errors), errors


def test_prose_description_is_allowed():
    ok = {**VALID_CONTRACT, "description": "harmonised from RAW_SALES and RAW_ORDERS"}
    assert validate_contract(ok) == []


# ── checks[]: library-instantiated checks (HANDOVER Iteration 1) ──────────────

def test_checks_array_well_formed_passes():
    ok = {**VALID_CONTRACT, "kind": "internal_gate", "checks": [
        {"id": "value_range", "params": {"<SPALTE>": "AMOUNT", "<MIN>": "0", "<MAX>": "100"},
         "expect": "= 0", "severity": "fail"},
        {"id": "allowed_values", "params": {"<SPALTE>": "STATUS", "<WERTE>": ["A", "B", "C"]}},
    ]}
    assert validate_contract(ok) == []


def test_checks_params_with_quotes_and_regex_not_flagged_as_smuggle():
    """The SQL-smuggle linter must NOT flag legitimate regex/quoted values in
    checks[].params — their injection safety is the compiler's typed binding."""
    ok = {**VALID_CONTRACT, "checks": [
        {"id": "pattern_match", "params": {"<SPALTE>": "CODE", "<REGEX>": "^[A-Z]{2}'[0-9]+$"}},
        {"id": "allowed_values", "params": {"<SPALTE>": "ST", "<WERTE>": ["A'B", "C;D"]}},
    ]}
    assert validate_contract(ok) == []


def test_checks_malformed_shape_rejected():
    bad = {**VALID_CONTRACT, "checks": [{"id": "value_range", "bogus": 1}]}
    assert any("checks" in e for e in validate_contract(bad)), validate_contract(bad)


def test_checks_missing_id_rejected():
    bad = {**VALID_CONTRACT, "checks": [{"params": {"<SPALTE>": "A"}}]}
    assert validate_contract(bad), "check without id must be rejected"


def test_checks_id_still_linted_for_smuggle():
    """params are exempt from the lint, but id/expect/severity are not."""
    bad = {**VALID_CONTRACT, "checks": [{"id": "x; DROP TABLE y"}]}
    assert any("[G1]" in e for e in validate_contract(bad)), validate_contract(bad)


def test_checks_bad_severity_rejected():
    bad = {**VALID_CONTRACT, "checks": [{"id": "value_range", "severity": "blocker"}]}
    assert any("checks" in e for e in validate_contract(bad)), validate_contract(bad)
