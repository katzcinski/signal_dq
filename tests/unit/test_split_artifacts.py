"""Slice ④/⑤/⑥ — Split-Artefakte, episodische Quarantäne und Bridge-DDL:
Zeilen-Prädikate je Garantie-Familie, deterministische Namen/Hashes,
Schema-Bindung (G2) und explizite Skips (G6)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "packages"))

from dq_core.contract.compiler import bind_schema, compile_contract
from dq_core.enforce import bridge, split
from dq_core.enforce.split import RowPredicate, SkippedCheck


def _spec(enforcement_default="quarantine", columns=None):
    contract = {
        "product": "SALES_ORDERS", "dataset": "SALES_ORDERS", "version": "1.0.0",
        "enforcement_default": enforcement_default,
        "guarantees": {
            "not_null": [{"columns": ["COUNTRY"]}],
            "completeness": [{"column": "REGION", "min_pct": 95}],
            "keys": [{"columns": ["ORDER_ID"]}, {"columns": ["ORDER_ID", "LINE"]}],
            "referential": [{"fk": ["CUST_ID"], "parent": "DIM_CUSTOMER", "parent_key": ["ID"]}],
            "freshness": {"column": "TS", "max_age": "PT24H"},
        },
    }
    cfg = bind_schema(compile_contract(contract), "CORE_DWH")
    return split.build_spec("SALES_ORDERS", cfg.checks, columns=columns)


class TestRowPredicates:
    def test_families_row_split_capability_matrix(self):
        spec = _spec()
        by_type = {p.check_type: p.sql for p in spec.predicates}
        # zeilenfähig (Review §3.3):
        assert by_type["missing"] == '"COUNTRY" IS NULL'
        assert by_type["completeness_pct"] == f'{split.SRC}."REGION" IS NULL'
        assert 'GROUP BY DQ_I."ORDER_ID" HAVING COUNT(*) > 1' in by_type["duplicate"]
        assert "NOT EXISTS" in by_type["reference_integrity"]
        assert '"DIM_CUSTOMER"' in by_type["reference_integrity"]
        # Objekt-Eigenschaft → expliziter Skip, nie still (G6):
        assert [s.check_type for s in spec.skipped] == ["freshness"]
        assert "Objekt-Gate" in spec.skipped[0].reason

    def test_composite_key_qualified_literals_untouched(self):
        spec = _spec()
        composite = next(p for p in spec.predicates if p.check_type == "duplicate_composite")
        # Äußere Spalten auf SRC qualifiziert, String-Literal '|' unangetastet.
        assert f'{split.SRC}."ORDER_ID"' in composite.sql
        assert "'|'" in composite.sql
        assert f'{split.SRC}.\'|\'' not in composite.sql

    def test_monitor_only_object_has_no_spec(self):
        assert _spec(enforcement_default="monitor") is None

    def test_generic_where_with_unsafe_clause_skipped(self):
        outcome = split.row_predicate(
            "custom", "c1",
            'SELECT COUNT(*) FROM "S"."T" WHERE "A" IN (SELECT "A" FROM "S"."X")',
        )
        assert isinstance(outcome, SkippedCheck)

    def test_predicate_derivable_from_run_results(self):
        # Ableitung funktioniert auch aus CheckResult (Lauf-Summary) — gleiche
        # Felder name/type/sql/enforcement.
        from dq_core.engine.models import CheckResult
        result = CheckResult(
            name="A_not_null", sql='SELECT COUNT(*) FROM "S"."T" WHERE "A" IS NULL',
            expect="= 0", severity="fail", passed=False,
            type="missing", enforcement="quarantine",
        )
        spec = split.build_spec("T", [result])
        assert isinstance(spec.predicates[0], RowPredicate)
        assert spec.source == '"S"."T"'


class TestNaming:
    def test_names_deterministic_and_prefixed(self):
        spec = _spec()
        assert spec.clean_table == "DQ_CLEAN_SALES_ORDERS"
        assert spec.quarantine_table == "DQ_Q_SALES_ORDERS"
        assert spec.released_view == "V_DQ_RELEASED_SALES_ORDERS"

    def test_long_names_truncated_with_hash(self):
        long_id = "X" * 150
        name = split.artifact_name("DQ_CLEAN_", long_id)
        assert len(name) <= 100
        assert name == split.artifact_name("DQ_CLEAN_", long_id)  # deterministisch
        other = split.artifact_name("DQ_CLEAN_", "X" * 149)
        assert name != other  # Hash-Suffix hält lange IDs unterscheidbar

    def test_unsafe_chars_sanitized(self):
        assert split.artifact_name("DQ_Q_", "space.obj-1") == "DQ_Q_SPACE_OBJ_1"


class TestStatements:
    def test_clean_refresh_binds_and_excludes_bad(self):
        spec = _spec()
        stmts = split.clean_refresh_statements(spec, "SIG")
        assert stmts[0] == 'DELETE FROM "SIG"."DQ_CLEAN_SALES_ORDERS"'
        assert "WHERE NOT (" in stmts[1]
        assert "{signal_schema}" not in stmts[1]
        assert "CENTRAL" not in stmts[1]

    def test_projection_uses_columns_when_known(self):
        spec = _spec(columns=["ORDER_ID", "COUNTRY"])
        insert = split.clean_refresh_statements(spec, "SIG")[1]
        assert f'{split.SRC}."ORDER_ID", {split.SRC}."COUNTRY"' in insert
        assert f"{split.SRC}.*" not in insert

    def test_snapshot_idempotent_per_generation(self):
        spec = _spec()
        sql, params = split.quarantine_snapshot_statement(
            spec, "SIG", episode_id=7, generation=2, run_id="r1",
        )
        assert "NOT EXISTS" in sql and '"_DQ_GENERATION"' in sql
        assert params == (7, 2, "r1", 7, 2)

    def test_released_view_joins_episode_mirror(self):
        ddl = split.released_view_ddl(_spec(), "SIG")
        assert '"SIG"."DQ_EPISODES"' in ddl
        assert "'released'" in ddl

    def test_ttl_purge_negative_days(self):
        sql, params = split.ttl_purge_statement(_spec(), "SIG", 30)
        assert "ADD_DAYS" in sql and params == (-30,)

    def test_registry_statements_bind(self):
        sql, params = split.registry_upsert_statement(
            "SIG", name="DQ_CLEAN_X", kind="table", object_id="X", hash_="abc",
        )
        assert "{signal_schema}" not in sql and params[0] == "DQ_CLEAN_X"
        assert split.drop_statement("SIG", name="V_DQ_RELEASED_X", kind="view").startswith('DROP VIEW "SIG"')


class TestBridgeDdl:
    def test_procedures_present_with_error_codes(self):
        gate = bridge.gate_bridge_procedure_ddl()
        assert "SQLSCRIPT_SYNC" in gate
        assert "SQL_ERROR_CODE 10054" in gate  # Timeout, fail-closed
        assert "SQL_ERROR_CODE 10055" in gate  # Lauf-Fehler
        assert 'P_DQ_ASSERT_GATE' in gate
        req = bridge.request_run_procedure_ddl()
        assert "SQL SECURITY DEFINER" in req and "'requested'" in req

    def test_bridge_only_with_opt_in(self):
        from dq_core.enforce import desired_objects
        base = {o.name for o in desired_objects()}
        with_bridge = {o.name for o in desired_objects(include_bridge=True)}
        assert "P_DQ_GATE" not in base
        assert {"P_DQ_GATE", "P_DQ_REQUEST_RUN"} <= with_bridge

    def test_claim_statements_bind(self):
        sql, params = bridge.claim_statement("SIG", request_id="req1", claimed_by="w1")
        assert "'claimed'" in sql and "'requested'" in sql and params == ("w1", "req1")
        sql, params = bridge.finish_statement("SIG", request_id="req1", status="done")
        assert params == ("done", "req1")


class TestFrameworkFree:
    @pytest.mark.parametrize("module", ["split", "bridge"])
    def test_g7_no_web_imports(self, module):
        import importlib
        mod = importlib.import_module(f"dq_core.enforce.{module}")
        source = Path(mod.__file__).read_text(encoding="utf-8")
        for forbidden in ("fastapi", "flask", "starlette"):
            assert forbidden not in source
