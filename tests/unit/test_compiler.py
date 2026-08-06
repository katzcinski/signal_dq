"""Compiler-Tests: §1.5-Garantien → CheckDefs. [DETERMINISM] [SCHEMA-MAP] G1/G2/S2."""
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parents[2] / "packages"))

from dq_core.contract.compiler import (
    CompileError,
    bind_schema,
    compile_contract,
    compiler_hash,
    parse_iso_duration,
)
from dq_core.engine.check_engine import dataset_config_to_yaml


def _shipped_contract() -> dict:
    path = Path(__file__).parents[2] / "contracts" / "DS_SALES_ORDERS.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_compiles_shipped_contract_to_checks():
    """§0-Regression: der Repo-Contract muss kompilieren — und zwar nicht leer."""
    config = compile_contract(_shipped_contract())
    assert config.dataset == "DS_SALES_ORDERS"
    assert len(config.checks) >= 6  # schema + key + 4×not_null + volume + freshness
    names = {c.name for c in config.checks}
    assert "key_ORDER_ID_unique" in names
    assert "volume_min_rows" in names
    assert "freshness_ORDER_DATE" in names


def test_schema_placeholder_preserved_g2():
    """L-2: '{schema}' bleibt wörtlich im Output — Bindung erst zur Laufzeit."""
    config = compile_contract(_shipped_contract())
    assert config.schema == "{schema}"
    assert all("{schema}" in c.sql for c in config.checks)
    # und im serialisierten Artefakt
    assert "'{schema}'" in dataset_config_to_yaml(config) or "{schema}" in dataset_config_to_yaml(config)


def test_bind_schema_resolves_placeholder():
    config = compile_contract(_shipped_contract())
    bind_schema(config, "CORE_DWH")
    assert config.schema == "CORE_DWH"
    assert all("{schema}" not in c.sql for c in config.checks)
    assert any('"CORE_DWH"' in c.sql for c in config.checks)


def test_bind_schema_rejects_unsafe_schema():
    config = compile_contract(_shipped_contract())
    with pytest.raises(CompileError):
        bind_schema(config, 'X"; DROP TABLE y; --')


def test_determinism_nonempty_byte_identical():
    """L-1: Determinismus-Test mit Nicht-leer-Wache — nie wieder vakuum."""
    a = compile_contract(_shipped_contract())
    b = compile_contract(_shipped_contract())
    assert len(a.checks) > 0
    assert dataset_config_to_yaml(a) == dataset_config_to_yaml(b)
    assert compiler_hash(_shipped_contract()) == compiler_hash(_shipped_contract())


def test_compiler_hash_changes_with_contract():
    base = _shipped_contract()
    changed = yaml.safe_load(yaml.safe_dump(base))
    changed["guarantees"]["volume"]["min_rows"] = 9999
    assert compiler_hash(base) != compiler_hash(changed)


def test_observability_only_change_does_not_change_compiler_output():
    base = _shipped_contract()
    changed = yaml.safe_load(yaml.safe_dump(base))
    changed["observability"] = {
        "volume": {"baseline": "seasonal", "season": ["dow"], "sensitivity": "high"}
    }
    assert dataset_config_to_yaml(compile_contract(base)) == dataset_config_to_yaml(compile_contract(changed))
    assert compiler_hash(base) == compiler_hash(changed)


def test_injection_in_key_columns_raises():
    """S-4: der frühere Verifikationsfall 'A" OR 1=1 --' muss hart scheitern."""
    bad = {
        "product": "X", "dataset": "X", "version": "1.0.0",
        "guarantees": {"keys": [{"columns": ['A" OR 1=1 --'], "unique": True}]},
    }
    with pytest.raises(CompileError):
        compile_contract(bad)


def test_no_raw_sql_path_exists():
    """S-3: type:sql existiert nicht mehr — unbekannte Garantie-Keys werden ignoriert,
    es gibt keinen Pfad, der einen String als SQL übernimmt."""
    contract = {
        "product": "X", "dataset": "X", "version": "1.0.0",
        "guarantees": {"keys": [{"columns": ["ID"], "unique": True}]},
        # smuggle attempt — Compiler liest dieses Feld schlicht nicht
        "quality": [{"type": "sql", "query": "SELECT 1; DROP TABLE x"}],
    }
    config = compile_contract(contract)
    assert all("DROP" not in c.sql for c in config.checks)


def test_inventory_existence_check_s2_stage2():
    contract = {
        "product": "X", "dataset": "X", "version": "1.0.0",
        "guarantees": {"not_null": [{"columns": ["GHOST_COL"]}]},
    }
    with pytest.raises(CompileError, match="existiert nicht im Inventar"):
        compile_contract(contract, inventory_columns={"REAL_COL"})
    # mit passendem Inventar kompiliert es
    contract["guarantees"]["not_null"][0]["columns"] = ["REAL_COL"]
    assert compile_contract(contract, inventory_columns={"REAL_COL"}).checks


def test_composite_key_uses_composite_template():
    contract = {
        "product": "X", "dataset": "X", "version": "1.0.0",
        "guarantees": {"keys": [{"columns": ["ORDER_ID", "ITEM_NO"], "unique": True}]},
    }
    config = compile_contract(contract)
    assert config.checks[0].type == "duplicate_composite"
    assert '"ORDER_ID" || \'|\' || "ITEM_NO"' in config.checks[0].sql


def test_internal_templates_are_not_compiled_from_contract_v1():
    contract = {
        "product": "X", "dataset": "X", "version": "1.0.0",
        "guarantees": {
            "schema": {"columns": ["ORDER_DATE"], "mode": "closed"},
            "volume": {"min_rows": 1, "baseline": "rolling"},
        },
    }

    config = compile_contract(contract)
    types = {check.type for check in config.checks}

    assert types == {"schema", "row_count"}
    assert not {"volume_anomaly", "cross_field_consistency", "type_conformance"} & types


def test_completeness_maps_min_pct_to_null_quote():
    contract = {
        "product": "X", "dataset": "X", "version": "1.0.0",
        "guarantees": {"completeness": [{"column": "AMOUNT", "min_pct": 99.5}]},
    }
    config = compile_contract(contract)
    assert config.checks[0].expect == "<= 0.5"


def test_segmented_completeness_compiles_scalar_count():
    contract = {
        "product": "X", "dataset": "X", "version": "1.0.0",
        "guarantees": {
            "completeness": [{
                "column": "AMOUNT",
                "min_pct": 99.5,
                "segment_by": "REGION",
                "max_segments": 20,
            }]
        },
    }
    config = compile_contract(contract)
    check = config.checks[0]
    assert check.name == "completeness_AMOUNT_by_REGION"
    assert check.type == "completeness_pct_segment"
    assert check.expect == "= 0"
    assert check.sql.startswith("SELECT COUNT(*) FROM (")
    assert 'GROUP BY "REGION"' in check.sql


def test_parse_iso_duration():
    assert parse_iso_duration("PT26H") == 26 * 3600
    assert parse_iso_duration("P1D") == 86400
    assert parse_iso_duration("PT30M") == 1800
    with pytest.raises(CompileError):
        parse_iso_duration("26h")


# ── checks[]: library-instantiated checks (HANDOVER Iteration 1) ──────────────

def _with_checks(checks: list) -> dict:
    return {"product": "X", "dataset": "X", "version": "1.0.0",
            "guarantees": {}, "checks": checks}


def test_checks_value_range_binds_identifier_and_numbers():
    config = compile_contract(_with_checks([
        {"id": "value_range",
         "params": {"<SPALTE>": "NET_AMOUNT", "<MIN>": "0", "<MAX>": "100"},
         "expect": "= 0", "severity": "fail"},
    ]))
    c = config.checks[-1]
    assert c.type == "value_range"            # type == library id → family rollup
    assert c.name == "value_range_NET_AMOUNT"
    assert '"NET_AMOUNT" < 0 OR "NET_AMOUNT" > 100' in c.sql
    assert "{schema}" in c.sql                # G2: schema bound only at runtime
    assert c.expect == "= 0" and c.severity == "fail"


def test_checks_prefill_expect_and_severity_from_library_defaults():
    c = compile_contract(_with_checks([
        {"id": "duplicate_approx", "params": {"<SPALTE>": "ID"}},
    ])).checks[-1]
    assert c.expect == "= 0"      # default_expect
    assert c.severity == "warn"   # default_severity
    assert c.type == "duplicate_approx"


def test_checks_value_list_assembles_quoted_list_with_escaping():
    c = compile_contract(_with_checks([
        {"id": "allowed_values",
         "params": {"<SPALTE>": "STATUS", "<WERTE>": ["A", "B'C"]}},
    ])).checks[-1]
    assert "NOT IN ('A', 'B''C')" in c.sql     # per-item quote-escaping


def test_checks_string_and_regex_params_escape_single_quotes():
    cfg = compile_contract(_with_checks([
        {"id": "pattern_match", "params": {"<SPALTE>": "CODE", "<REGEX>": "^A'B$"}},
        {"id": "type_conformance",
         "params": {"<SPALTE>": "ORDER_DATE", "<DATA_TYPE_NAME>": "DATE"}},
    ]))
    assert "LIKE_REGEXPR '^A''B$'" in cfg.checks[-2].sql
    assert "<> 'DATE'" in cfg.checks[-1].sql


def test_checks_identifier_param_blocks_injection_s2():
    with pytest.raises(CompileError, match="Unsicherer Identifier"):
        compile_contract(_with_checks([
            {"id": "value_range",
             "params": {"<SPALTE>": 'X" OR 1=1 --', "<MIN>": "0", "<MAX>": "1"}},
        ]))


def test_checks_number_param_rejects_non_numeric_smuggle():
    with pytest.raises(CompileError, match="keine Zahl"):
        compile_contract(_with_checks([
            {"id": "value_range",
             "params": {"<SPALTE>": "A", "<MIN>": "0); DROP TABLE x --", "<MAX>": "1"}},
        ]))


def test_checks_identifier_respects_inventory_existence():
    contract = _with_checks([
        {"id": "value_range", "params": {"<SPALTE>": "GHOST", "<MIN>": "0", "<MAX>": "1"}},
    ])
    with pytest.raises(CompileError, match="existiert nicht im Inventar"):
        compile_contract(contract, inventory_columns={"REAL"})


def test_checks_unknown_id_rejected():
    with pytest.raises(CompileError, match="unbekannte Check-ID"):
        compile_contract(_with_checks([{"id": "does_not_exist", "params": {}}]))


def test_checks_missing_and_extra_params_rejected():
    with pytest.raises(CompileError, match="fehlende Parameter"):
        compile_contract(_with_checks([{"id": "value_range", "params": {"<SPALTE>": "A"}}]))
    with pytest.raises(CompileError, match="unbekannte Parameter"):
        compile_contract(_with_checks([
            {"id": "duplicate_approx", "params": {"<SPALTE>": "A", "<BOGUS>": "1"}},
        ]))


def test_checks_custom_sql_empty_template_rejected():
    """custom_sql has an empty sql_template → naturally excluded (raw SQL deferred)."""
    with pytest.raises(CompileError, match="kein sql_template"):
        compile_contract(_with_checks([{"id": "custom_sql", "params": {}}]))


def test_checks_expr_param_type_is_deferred():
    """<REGEL> (cross_field) / <KEY_EXPR> (duplicate_composite) are raw-SQL
    expression params — not bindable in the checks: path (HANDOVER §5)."""
    with pytest.raises(CompileError, match="deferred"):
        compile_contract(_with_checks([
            {"id": "cross_field_consistency", "params": {"<REGEL>": '"A" >= "B"'}},
        ]))


def test_checks_are_additive_to_guarantees_and_change_hash():
    base = {"product": "X", "dataset": "X", "version": "1.0.0",
            "guarantees": {"not_null": [{"columns": ["A"]}]}}
    with_checks = dict(base, checks=[{"id": "duplicate_approx", "params": {"<SPALTE>": "A"}}])
    assert len(compile_contract(with_checks).checks) == len(compile_contract(base).checks) + 1
    assert compiler_hash(base) != compiler_hash(with_checks)


def test_checks_duplicate_name_is_disambiguated():
    cfg = compile_contract(_with_checks([
        {"id": "value_range", "params": {"<SPALTE>": "A", "<MIN>": "0", "<MAX>": "1"}},
        {"id": "value_range", "params": {"<SPALTE>": "A", "<MIN>": "5", "<MAX>": "9"}},
    ]))
    names = [c.name for c in cfg.checks]
    assert names == ["value_range_A", "value_range_A_1"]


def test_checks_value_literal_with_token_like_text_not_resubstituted():
    """Single-pass binding: a regex value containing another token ('<MIN>') must
    survive verbatim inside the string literal, not be re-substituted."""
    c = compile_contract(_with_checks([
        {"id": "pattern_match", "params": {"<SPALTE>": "C", "<REGEX>": "<MIN>"}},
    ])).checks[-1]
    assert "LIKE_REGEXPR '<MIN>'" in c.sql
