"""Slice ③ — Gate-Konsum-Oberfläche: deterministische DDL, Schema-Bindung
(G2), Bootstrap-Plan-Idempotenz und Verdict-Statements. `dq_core.enforce`
bleibt frameworkfrei (G7)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "packages"))

from dq_core.enforce import (
    GATE_ERROR_CODES,
    bind_signal_schema,
    bootstrap_plan,
    desired_objects,
    manifest_hash,
    remote_migration_statements,
    verdict_upsert_statements,
)


class TestDesiredObjects:
    def test_slice3_composition(self):
        objs = {(o.name, o.kind) for o in desired_objects()}
        assert ("DQ_GATE_STATUS", "table") in objs
        assert ("DQ_GATE_STATUS_HISTORY", "table") in objs
        assert ("V_DQ_GATE_STATUS", "view") in objs
        assert ("P_DQ_ASSERT_GATE", "procedure") in objs

    def test_tables_are_never_replaceable(self):
        # Tabellen tragen Zustand — der Reconciler ersetzt sie nie.
        for obj in desired_objects():
            assert obj.replaceable == (obj.kind != "table")

    def test_manifest_hash_is_deterministic(self):
        first = {o.name: o.manifest_hash for o in desired_objects()}
        second = {o.name: o.manifest_hash for o in desired_objects()}
        assert first == second
        for obj in desired_objects():
            assert obj.manifest_hash == manifest_hash(obj.ddl)

    def test_no_schema_literal_anywhere(self):
        # G2: nur der Platzhalter, nie ein hartes Schema (CI grept "CENTRAL").
        for obj in desired_objects():
            assert "{signal_schema}" in obj.ddl
            assert "CENTRAL" not in obj.ddl


class TestSchemaBinding:
    def test_bind_replaces_placeholder(self):
        bound = bind_signal_schema('SELECT * FROM "{signal_schema}"."T"', "SIGNAL_SQL")
        assert bound == 'SELECT * FROM "SIGNAL_SQL"."T"'

    @pytest.mark.parametrize("bad", ['BAD"SCHEMA', "BAD-SCHEMA", "1START", "", "A;DROP"])
    def test_unsafe_schema_rejected(self, bad):
        with pytest.raises(ValueError, match=r"\[S2\]"):
            bind_signal_schema("x", bad)


class TestBootstrapPlan:
    def test_full_plan_binds_everything(self):
        plan = bootstrap_plan(existing_tables=set(), schema="SIG")
        tables = {o.name for o in desired_objects() if o.kind == "table"}
        replaceable = [o for o in desired_objects() if o.replaceable]
        assert len(plan) == len(tables) + len(replaceable)
        assert all("{signal_schema}" not in stmt for stmt in plan)
        assert all('"SIG"' in stmt for stmt in plan)

    def test_existing_tables_are_skipped_views_replaced(self):
        tables = {o.name for o in desired_objects() if o.kind == "table"}
        plan = bootstrap_plan(existing_tables=tables, schema="SIG")
        # Nur Views + Prozeduren (CREATE OR REPLACE, idempotent) — Tabellen
        # tragen Zustand und werden nie ersetzt.
        assert plan
        assert all("CREATE OR REPLACE" in stmt for stmt in plan)


class TestProcedureContract:
    def test_error_codes_in_procedure(self):
        proc = next(o for o in desired_objects() if o.name == "P_DQ_ASSERT_GATE")
        for key in ("no_verdict", "stale", "block", "quarantine"):
            assert f"SQL_ERROR_CODE {GATE_ERROR_CODES[key]}" in proc.ddl

    def test_error_codes_avoid_reserved_2(self):
        # Exit 2 der CLI (argparse/--host) darf nie kollidieren; SQLScript-
        # User-Errors liegen im dokumentierten Fenster 10000–19999.
        for code in GATE_ERROR_CODES.values():
            assert 10000 <= code <= 19999

    def test_fail_on_parameter_present(self):
        proc = next(o for o in desired_objects() if o.name == "P_DQ_ASSERT_GATE")
        assert "IN_FAIL_ON" in proc.ddl
        assert "'block_and_quarantine'" in proc.ddl
        assert "SQL SECURITY DEFINER" in proc.ddl


class TestVerdictStatements:
    def test_upsert_and_history(self):
        stmts = verdict_upsert_statements(
            schema="SIG", object_id="OBJ", run_id="r1",
            gate_verdict="quarantine", overall_status="fail",
            evaluated_at="2026-07-10T12:00:00+00:00",
        )
        assert len(stmts) == 2
        upsert, history = stmts
        assert upsert[0].startswith('UPSERT "SIG"."DQ_GATE_STATUS"')
        assert "WITH PRIMARY KEY" in upsert[0]
        assert history[0].startswith('INSERT INTO "SIG"."DQ_GATE_STATUS_HISTORY"')
        assert upsert[1] == history[1]

    def test_ttl_sets_expiry(self):
        (_, params), _ = verdict_upsert_statements(
            schema="SIG", object_id="OBJ", run_id="r1",
            gate_verdict="proceed", overall_status="pass",
            evaluated_at="2026-07-10T12:00:00Z", ttl_seconds=600,
        )
        assert params[-2] == "2026-07-10 12:00:00.000000"
        assert params[-1] == "2026-07-10 12:10:00.000000"

    def test_no_ttl_means_no_expiry(self):
        (_, params), _ = verdict_upsert_statements(
            schema="SIG", object_id="OBJ", run_id="r1",
            gate_verdict="proceed", overall_status="pass",
            evaluated_at="2026-07-10T12:00:00+00:00",
        )
        assert params[-1] is None


class TestFrameworkFree:
    def test_g7_no_web_imports(self):
        # G7: dq_core bleibt frameworkfrei — auch das neue enforce-Paket.
        import dq_core.enforce.ddl as mod
        source = Path(mod.__file__).read_text(encoding="utf-8")
        for forbidden in ("fastapi", "flask", "starlette"):
            assert forbidden not in source

    def test_remote_migrations_are_numbered(self):
        versions = [v for v, _ in remote_migration_statements()]
        assert versions == sorted(versions)
        assert versions[0].startswith("001_")
