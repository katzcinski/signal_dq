"""Batch 3: Capability-Probe (Rest-O5/O6), Quarantäne-Policy (style /
auto_release), Reconciler-Drift und on_load-Schedule-Modus (AP-5)."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest


class FakeCursor:
    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql, params=None):
        self._conn.executed.append((str(sql), params))
        self._conn.last = str(sql)
        for pattern in self._conn.fail_on:
            if pattern in self._conn.last:
                raise RuntimeError(f"probe failure: {pattern}")

    def fetchall(self):
        for pattern, rows in self._conn.results:
            if pattern in self._conn.last:
                return rows
        return []

    def close(self):
        pass


class FakeConn:
    def __init__(self, results=None, fail_on=None):
        self.executed = []
        self.results = results or []
        self.fail_on = fail_on or []
        self.last = ""

    def cursor(self):
        return FakeCursor(self)

    def close(self):
        pass

    def sql(self):
        return [s for s, _ in self.executed]


class Cfg:
    def __init__(self, **kw):
        self.enforcement_materialize_enabled = True
        self.datasphere_signal_schema = "SIG"
        self.enforcement_verdict_ttl_seconds = 0
        self.quarantine_ttl_days = 30
        self.reconciler_drop_grace_days = 14
        self.enforcement_environment = ""
        self.enforcement_sql_bridge_enabled = False
        self.datasphere_allow_trigger = False
        self.quarantine_trigger_chains = {}
        for k, v in kw.items():
            setattr(self, k, v)


@pytest.fixture
def store(tmp_path):
    from dq_core.store.sqlite_store import ResultStore
    return ResultStore(tmp_path / "batch3.db")


def _summary(run_id, verdict):
    from dq_core.engine.models import CheckResult, RunSummary
    return RunSummary(
        run_id=run_id, dataset="DS", schema="S",
        started_at="2026-07-11T00:00:00+00:00", finished_at="2026-07-11T00:01:00+00:00",
        overall_status="pass" if verdict == "proceed" else "fail",
        total=1, passed=1, failed=0, warnings=0, gate_verdict=verdict,
        results=[CheckResult(
            name="A_not_null", sql='SELECT COUNT(*) FROM "S"."DS" WHERE "A" IS NULL',
            expect="= 0", severity="fail", passed=(verdict == "proceed"),
            type="missing", enforcement="quarantine",
        )],
    )


class TestCapabilityProbe:
    def test_probes_persisted_with_manual_pending(self, store):
        from services.api.enforcement import MANUAL_CAPABILITIES, run_capability_probes
        results = run_capability_probes(FakeConn(), Cfg(), store)
        assert {k: v["status"] for k, v in results.items()} == {
            "open_sql_table_write": "ok", "open_sql_view": "ok",
            "sqlscript_sync": "ok", "catalog_tables_read": "ok",
        }
        caps = {c["key"]: c["status"] for c in store.list_capabilities()}
        assert caps["open_sql_table_write"] == "ok"
        for key in MANUAL_CAPABILITIES:
            assert caps[key] == "manual"  # offene manuelle Checks sichtbar (G6)

    def test_sync_failure_is_unavailable_not_error(self, store):
        from services.api.enforcement import run_capability_probes
        conn = FakeConn(fail_on=["SQLSCRIPT_SYNC"])
        results = run_capability_probes(conn, Cfg(), store)
        assert results["sqlscript_sync"]["status"] == "unavailable"
        assert results["open_sql_table_write"]["status"] == "ok"

    def test_endpoints_roles_and_validation(self, api_client):
        # Liste zeigt offene manuelle Checks auch ohne Probe (G6)
        body = api_client.get("/api/enforcement/capabilities").json()
        assert any(c["status"] == "manual" for c in body["capabilities"])
        # Eintragen: viewer 403, owner ok, unbekannter Status 422
        assert api_client.post(
            "/api/enforcement/capabilities", headers={"X-DQ-Role": "viewer"},
            json={"key": "flow_view_import", "status": "ok"},
        ).status_code == 403
        assert api_client.post(
            "/api/enforcement/capabilities",
            json={"key": "flow_view_import", "status": "weird"},
        ).status_code == 422
        resp = api_client.post(
            "/api/enforcement/capabilities",
            json={"key": "flow_view_import", "status": "ok", "detail": "Data Builder ok"},
        )
        assert resp.status_code == 200
        caps = {c["key"]: c["status"] for c in resp.json()["capabilities"]}
        assert caps["flow_view_import"] == "ok"
        # Probe: ohne Signal-Schema 409 (Pre-Flight braucht nur das Schema)
        assert api_client.post(
            "/api/enforcement/probe", json={"environment": "dev"},
        ).status_code == 409


class TestQuarantinePolicy:
    def test_validator_accepts_policy_block(self):
        from dq_core.contract.validator import validate_contract
        assert validate_contract({
            "product": "X", "dataset": "X", "version": "1.0.0", "guarantees": {},
            "quarantine": {"style": "episodic", "auto_release_after_green_runs": 3},
        }) == []
        assert validate_contract({
            "product": "X", "dataset": "X", "version": "1.0.0", "guarantees": {},
            "quarantine": {"style": "sometimes"},
        })

    def test_style_continuous_skips_snapshot(self, store):
        from services.api import enforcement as enf
        enf.reset_bootstrap_cache()
        eid = store.open_quarantine("DS", "r1", ["A_not_null"])
        conn = FakeConn(results=[("SYS.TABLES", [])])
        enf.post_run(conn, _summary("r1", "quarantine"), Cfg(), store,
                     episode_id=eid, policy={"style": "continuous"})
        sql = conn.sql()
        assert any('DQ_CLEAN_DS' in s for s in sql)
        assert not any('INSERT INTO "SIG"."DQ_Q_DS"' in s for s in sql)
        enf.reset_bootstrap_cache()

    def test_style_episodic_skips_clean(self, store):
        from services.api import enforcement as enf
        enf.reset_bootstrap_cache()
        eid = store.open_quarantine("DS", "r1", ["A_not_null"])
        conn = FakeConn(results=[
            ("SYS.TABLES", []),
            ('SELECT COUNT(*) FROM "SIG"."DQ_Q_', [(3,)]),
        ])
        enf.post_run(conn, _summary("r1", "quarantine"), Cfg(), store,
                     episode_id=eid, policy={"style": "episodic"})
        sql = conn.sql()
        assert any('INSERT INTO "SIG"."DQ_Q_DS"' in s for s in sql)
        assert not any("DQ_CLEAN_DS" in s for s in sql)
        assert store.get_quarantine(eid)["row_count"] == 3
        enf.reset_bootstrap_cache()

    def test_auto_release_after_n_green_runs(self, store):
        from services.api.enforcement import auto_release
        eid = store.open_quarantine("DS", "r0", ["A_not_null"])
        for rid in ("r1", "r2", "r3"):
            store.save_run(_summary(rid, "proceed"))
        assert auto_release(Cfg(), store, object_id="DS",
                            policy={"auto_release_after_green_runs": 3}) == 1
        episode = store.get_quarantine(eid)
        assert episode["status"] == "released" and episode["released_by"] == "system"
        # Policy aus (Default) ⇒ nie automatisch
        store.open_quarantine("DS2", "r0", ["c"])
        assert auto_release(Cfg(), store, object_id="DS2", policy={}) == 0

    def test_auto_release_blocked_by_red_run(self, store):
        from services.api.enforcement import auto_release
        store.open_quarantine("DS", "r0", ["A_not_null"])
        store.save_run(_summary("r1", "proceed"))
        store.save_run(_summary("r2", "quarantine"))
        store.save_run(_summary("r3", "proceed"))
        assert auto_release(Cfg(), store, object_id="DS",
                            policy={"auto_release_after_green_runs": 3}) == 0


class TestReconcilerDrift:
    def test_hash_change_recreates_clean_keeps_quarantine(self):
        from services.api import enforcement as enf
        from dq_core.enforce import split
        spec = split.build_spec("DS", _summary("r1", "quarantine").results)
        conn = FakeConn(results=[
            ('SELECT "NAME","KIND"', [
                ("DQ_CLEAN_DS", "table", "DS", "OLDHASH", "active", None),
                ("DQ_Q_DS", "table", "DS", "OLDHASH", "active", None),
            ]),
            ("SYS.TABLES", []),
        ])
        result = enf.reconcile_split(conn, Cfg(), [spec])
        assert result["drifted"] == ["DQ_CLEAN_DS"]
        assert result["drift_kept"] == ["DQ_Q_DS"]
        assert any(s.startswith('DROP TABLE "SIG"."DQ_CLEAN_DS"') for s in conn.sql())
        assert not any("DROP" in s and "DQ_Q_DS" in s for s in conn.sql())


class TestOnLoadTick:
    def _setup(self, api_client, monkeypatch, loads):
        import services.api.deps as deps_mod
        import services.api.scheduler as scheduler
        import services.api.datasphere as dsp
        from services.api.routers import objects as objects_mod

        store = deps_mod.get_store()
        store.create_schedule(
            schedule_id="obj:DS_SALES_ORDERS", object_id="DS_SALES_ORDERS",
            mode="on_load", interval_seconds=0,
            next_due_at=datetime.now(timezone.utc).isoformat(),
        )

        class Client:
            def get_data_loads(self, space, object_id=None, top=50):
                return loads

        launches: list[str] = []

        def fake_start(**kwargs):
            launches.append(kwargs["object_id"])
            return {"run_id": f"run-{len(launches)}", "status": "started"}

        monkeypatch.setattr(dsp, "get_client", lambda: Client())
        monkeypatch.setattr(objects_mod, "start_object_run", fake_start)
        return store, scheduler, launches

    def test_new_successful_load_launches_once(self, api_client, monkeypatch):
        loads = [
            {"id": "ext-2", "status": "COMPLETED"},
            {"id": "ext-1", "status": "FAILED"},
        ]
        store, scheduler, launches = self._setup(api_client, monkeypatch, loads)
        assert scheduler._on_load_tick() == 1
        assert launches == ["DS_SALES_ORDERS"]
        sched = store.get_schedule("obj:DS_SALES_ORDERS")
        assert sched["last_external_run_id"] == "ext-2"
        # Derselbe Load erneut geliefert ⇒ kein zweiter Lauf (Dedupe)
        assert scheduler._on_load_tick() == 0
        assert launches == ["DS_SALES_ORDERS"]

    def test_no_successful_load_no_launch(self, api_client, monkeypatch):
        _, scheduler, launches = self._setup(
            api_client, monkeypatch, [{"id": "x", "status": "RUNNING"}],
        )
        assert scheduler._on_load_tick() == 0
        assert launches == []
