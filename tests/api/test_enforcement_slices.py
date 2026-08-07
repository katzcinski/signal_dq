"""Slices ④–⑦ auf Service-Ebene: Post-Run-Pipeline (Verdict → CLEAN-Refresh →
Snapshot → Episoden-Spiegel → TTL), Reconciler (invalidate-then-drop),
Bridge-Poller-Claim und Outbound-Trigger — alle hinter ihren Opt-ins."""
from __future__ import annotations

import pytest


class FakeCursor:
    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql, params=None):
        self._conn.executed.append((str(sql), params))
        self._conn.last = str(sql)

    def fetchall(self):
        for pattern, rows in self._conn.results:
            if pattern in self._conn.last:
                return rows
        return []

    def close(self):
        pass


class FakeConn:
    """Statement-Recorder mit Muster-basierten fetchall-Antworten."""

    def __init__(self, results=None):
        self.executed: list[tuple[str, object]] = []
        self.results = results or []
        self.last = ""

    def cursor(self):
        return FakeCursor(self)

    def close(self):
        pass

    def sql(self):
        return [s for s, _ in self.executed]


class Cfg:
    """Settings-Stub — enforcement liest per getattr (Namespace genügt)."""

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
    return ResultStore(tmp_path / "slices.db")


def _summary(verdict="quarantine"):
    from dq_core.engine.models import CheckResult, RunSummary
    return RunSummary(
        run_id="r1", dataset="DS", schema="CORE_DWH",
        started_at="2026-07-11T00:00:00+00:00", finished_at="2026-07-11T00:01:00+00:00",
        overall_status="fail", total=1, passed=0, failed=1, warnings=0,
        gate_verdict=verdict,
        results=[CheckResult(
            name="A_not_null", sql='SELECT COUNT(*) FROM "CORE_DWH"."DS" WHERE "A" IS NULL',
            expect="= 0", severity="fail", passed=False,
            type="missing", enforcement="quarantine",
        )],
    )


class TestPostRun:
    def test_full_pipeline_on_quarantine_verdict(self, store):
        from services.api import enforcement as enf
        enf.reset_bootstrap_cache()
        eid = store.open_quarantine("DS", "r1", ["A_not_null"])
        conn = FakeConn(results=[('SELECT COUNT(*) FROM "SIG"."DQ_Q_', [(5,)])])

        enf.post_run(conn, _summary(), Cfg(), store, episode_id=eid)

        sql = conn.sql()
        assert any('UPSERT "SIG"."DQ_GATE_STATUS"' in s for s in sql)          # Slice ③
        assert any('INSERT INTO "SIG"."DQ_CLEAN_DS"' in s for s in sql)        # Slice ④ Refresh
        assert any('INSERT INTO "SIG"."DQ_Q_DS"' in s for s in sql)            # Slice ⑤ Snapshot
        assert any('UPSERT "SIG"."DQ_EPISODES"' in s for s in sql)             # Episoden-Spiegel
        assert any(s.startswith('DELETE FROM "SIG"."DQ_Q_DS"') for s in sql)   # TTL
        episode = store.get_quarantine(eid)
        assert episode["status"] == "reconciled" and episode["row_count"] == 5
        enf.reset_bootstrap_cache()

    def test_kill_switch_off_is_noop(self, store):
        from services.api import enforcement as enf
        conn = FakeConn()
        enf.post_run(conn, _summary(), Cfg(enforcement_materialize_enabled=False), store)
        assert conn.executed == []

    def test_expired_episode_resolved_explicitly(self, store):
        from services.api import enforcement as enf
        from dq_core.enforce import split
        import sqlite3
        eid = store.open_quarantine("DS", "r0", ["A_not_null"])
        # Episode künstlich altern lassen (über die TTL hinaus).
        conn_db = sqlite3.connect(store.db_path)
        conn_db.execute("UPDATE dq_quarantine SET opened_at='2020-01-01T00:00:00+00:00' WHERE id=?", (eid,))
        conn_db.commit(); conn_db.close()

        spec = split.build_spec("DS", _summary().results)
        expired = enf.expire_quarantine(FakeConn(), Cfg(), store, spec)
        assert expired == 1
        episode = store.get_quarantine(eid)
        assert episode["status"] == "resolved" and episode["resolve_reason"] == "expired"


class TestReconciler:
    def test_orphan_invalidated_then_dropped_after_grace(self, store):
        from services.api import enforcement as enf
        # Registry kennt ein aktives Waisen-Artefakt und ein überfälliges
        # invalidiertes; DQ_Q_ ist vom Drop ausgenommen.
        registry_rows = [
            ("DQ_CLEAN_GONE", "table", "GONE", "h1", "active", None),
            ("V_DQ_RELEASED_OLD", "view", "OLD", "h2", "invalidated", "x"),
            ("DQ_Q_OLD", "table", "OLD", "h3", "invalidated", "x"),
        ]
        conn = FakeConn(results=[
            ('FROM "SIG"."DQ_OBJECTS"\nWHERE', []),
            ('SELECT "NAME","KIND"', registry_rows),
            ('CASE WHEN "INVALIDATED_AT"', [(1,)]),  # Grace abgelaufen
        ])
        result = enf.reconcile_split(conn, Cfg(), specs=[])
        assert result["invalidated"] == ["DQ_CLEAN_GONE"]
        assert result["dropped"] == ["V_DQ_RELEASED_OLD"]  # DQ_Q_OLD nie droppen
        sql = conn.sql()
        assert any(s.startswith('DROP VIEW "SIG"."V_DQ_RELEASED_OLD"') for s in sql)
        assert not any("DROP" in s and "DQ_Q_OLD" in s for s in sql)

    def test_grace_not_due_keeps_object(self):
        from services.api import enforcement as enf
        conn = FakeConn(results=[
            ('SELECT "NAME","KIND"', [("DQ_CLEAN_X", "table", "X", "h", "invalidated", "x")]),
            ('CASE WHEN "INVALIDATED_AT"', [(0,)]),
        ])
        result = enf.reconcile_split(conn, Cfg(), specs=[])
        assert result["dropped"] == []
        assert not any("DROP" in s for s in conn.sql())


class TestBridge:
    def test_disabled_returns_zero(self, store):
        from services.api import enforcement as enf
        assert enf.bridge_tick(Cfg(), store, [], launch=lambda *a: "x") == 0

    def test_claim_launch_and_stamp(self, store, monkeypatch):
        from services.api import enforcement as enf
        cfg = Cfg(enforcement_sql_bridge_enabled=True, enforcement_environment="dev")
        conn = FakeConn(results=[
            ("WHERE \"STATUS\" = 'requested'", [("req1", "DS")]),
            ("WHERE \"STATUS\" = 'claimed'", []),
        ])
        monkeypatch.setattr(enf, "get_enforcement_connection", lambda s: conn)
        import services.api.deps as deps_mod
        monkeypatch.setattr(deps_mod, "get_environment", lambda name: {"schema": "CORE_DWH"})
        inventory = [{"id": "DS", "schema": "CORE_DWH"}]

        launched = enf.bridge_tick(cfg, store, inventory, launch=lambda oid, obj, env: "run-42")
        assert launched == 1
        sql = conn.sql()
        assert any("'claimed'" in s for s in sql)
        assert any(('"RUN_ID" = ?' in s) for s in sql)

    def test_unknown_object_stamped_error(self, store, monkeypatch):
        from services.api import enforcement as enf
        cfg = Cfg(enforcement_sql_bridge_enabled=True, enforcement_environment="dev")
        conn = FakeConn(results=[("WHERE \"STATUS\" = 'requested'", [("req1", "NOPE")])])
        monkeypatch.setattr(enf, "get_enforcement_connection", lambda s: conn)
        import services.api.deps as deps_mod
        monkeypatch.setattr(deps_mod, "get_environment", lambda name: {"schema": "X"})

        assert enf.bridge_tick(cfg, store, [], launch=lambda *a: "x") == 0
        executed = [(s, p) for s, p in conn.executed if "FINISHED_AT" in s]
        assert executed and executed[0][1][0] == "error"


class TestOutboundTrigger:
    def test_disabled_or_unmapped_is_noop(self, store):
        from services.api.enforcement import trigger_remediation
        assert trigger_remediation(Cfg(), store, object_id="DS", run_id="r1") is False
        cfg = Cfg(datasphere_allow_trigger=True)  # kein Mapping
        assert trigger_remediation(cfg, store, object_id="DS", run_id="r1") is False

    def test_triggers_and_audits(self, store, monkeypatch):
        from services.api import enforcement as enf
        calls = []

        class Client:
            def trigger_task_chain(self, space, chain):
                calls.append((space, chain))
                return {}

        import services.api.datasphere as dsp
        monkeypatch.setattr(dsp, "get_client", lambda: Client())
        cfg = Cfg(datasphere_allow_trigger=True,
                  quarantine_trigger_chains={"DS": "SALES/QUARANTINE_CHAIN"})
        assert enf.trigger_remediation(cfg, store, object_id="DS", run_id="r1") is True
        assert calls == [("SALES", "QUARANTINE_CHAIN")]

    def test_client_error_audited_as_error(self, store, monkeypatch):
        from services.api import enforcement as enf

        class Client:
            def trigger_task_chain(self, space, chain):
                raise RuntimeError("boom")

        import services.api.datasphere as dsp
        monkeypatch.setattr(dsp, "get_client", lambda: Client())
        cfg = Cfg(datasphere_allow_trigger=True, quarantine_trigger_chains={"DS": "S/C"})
        assert enf.trigger_remediation(cfg, store, object_id="DS", run_id="r1") is False


class TestPlanEndpoint:
    def test_plan_includes_split_artifacts_and_skips(self, api_client):
        from services.api.settings import get_settings
        from pathlib import Path
        checks = Path(get_settings().checks_dir) / "DS_SALES_ORDERS.yml"
        checks.write_text(
            """dataset: DS_SALES_ORDERS
schema: "{schema}"
checks:
  - name: A_not_null
    sql: SELECT COUNT(*) FROM "{schema}"."DS_SALES_ORDERS" WHERE "A" IS NULL
    expect: "= 0"
    severity: fail
    type: missing
    enforcement: quarantine
  - name: fresh_TS
    sql: SELECT SECONDS_BETWEEN(MAX("TS"), CURRENT_TIMESTAMP) FROM "{schema}"."DS_SALES_ORDERS"
    expect: "< 86400"
    severity: warn
    type: freshness
    enforcement: quarantine
""",
            encoding="utf-8",
        )
        body = api_client.get("/api/enforcement/plan").json()
        assert body["bridge_enabled"] is False
        artifacts = body["split_artifacts"]
        assert len(artifacts) == 1
        art = artifacts[0]
        assert art["clean_table"] == "DQ_CLEAN_DS_SALES_ORDERS"
        # Inventar-Schema (CORE_DWH) wurde zur Laufzeit gebunden (G2).
        assert art["source"] == '"CORE_DWH"."DS_SALES_ORDERS"'
        assert [p["type"] for p in art["predicates"]] == ["missing"]
        # G6: nicht zeilenfähiger Quarantäne-Check explizit ausgewiesen.
        assert [s["type"] for s in art["skipped"]] == ["freshness"]
