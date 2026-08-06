"""R4-1 Incidents · R4-3 SLA · R3-1 Gating (skipped_stale-Produktion)."""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "packages"))

from dq_core.engine.check_engine import run_checks
from dq_core.engine.models import CheckDef, DatasetConfig
from dq_core.store.sqlite_store import ResultStore


# ---------------------------------------------------------------- Incidents

def test_incident_lifecycle(tmp_path):
    store = ResultStore(tmp_path / "t.db")
    iid = store.open_incident(
        "DS_X", "r1", "critical", "Contract-Breach: DS_X v1.0.0",
        ["key_unique", "amount_not_null"], "1.0.0", actor="system",
    )
    assert iid is not None

    # Dedupe: zweiter Breach derselben Episode → KEIN neues Incident, nur Event
    iid2 = store.open_incident("DS_X", "r2", "fail", "again", ["key_unique"], "1.0.0")
    assert iid2 == iid
    incident = store.get_incident(iid)
    assert incident["status"] == "open"
    assert incident["kind"] == "consumer_contract"
    assert incident["failed_checks"] == ["key_unique", "amount_not_null"]
    assert len(incident["events"]) == 2  # opened + note

    # Transition mit Owner + Note → Events
    store.transition_incident(iid, "acknowledged", actor="Alice", owner="Bob")
    incident = store.get_incident(iid)
    assert incident["status"] == "acknowledged"
    assert incident["owner"] == "Bob"
    actions = [e["action"] for e in incident["events"]]
    assert "status_changed" in actions and "assigned" in actions

    # Auto-Resolve bei Recovery
    store.auto_resolve_incidents("DS_X", "r3")
    incident = store.get_incident(iid)
    assert incident["status"] == "resolved"
    assert incident["resolved_at"]
    assert incident["events"][-1]["action"] == "auto_resolved"

    # Nach Resolve eröffnet ein neuer Breach eine NEUE Episode
    iid3 = store.open_incident("DS_X", "r4", "fail", "new episode", ["c"], "1.0.0")
    assert iid3 != iid


def test_incident_filters(tmp_path):
    store = ResultStore(tmp_path / "t.db")
    store.open_incident("A", "r1", "critical", "t", [], "")
    store.open_incident("B", "r2", "fail", "t", [], "", kind="internal_gate")
    assert len(store.list_incidents()) == 2
    assert len(store.list_incidents(status="open")) == 2
    assert len(store.list_incidents(severity="critical")) == 1
    assert len(store.list_incidents(kind="internal_gate")) == 1
    assert store.count_open_incidents(kind="internal_gate") == 1
    assert store.list_incidents(status="resolved") == []


def test_incident_record_clustering_and_rca_snapshot(tmp_path):
    store = ResultStore(tmp_path / "t.db")
    first = store.open_incident_record(
        "A",
        "r1",
        "fail",
        "t",
        ["c"],
        "",
        kind="consumer_contract",
        impacted_objects=[{"product": "B", "distance": 1}],
    )
    second = store.open_incident_record("B", "r2", "critical", "t", ["c"], "", kind="internal_gate")
    assert first and second and first.created and second.created
    assert store.get_incident(first.incident_id)["impacted_objects"] == [
        {"product": "B", "distance": 1}
    ]

    again = store.open_incident_record(
        "A",
        "r3",
        "fail",
        "again",
        ["c"],
        "",
        kind="consumer_contract",
        impacted_objects=[{"product": "C", "distance": 1}],
    )
    assert again and not again.created
    assert store.get_incident(first.incident_id)["impacted_objects"] == [
        {"product": "C", "distance": 1}
    ]

    c1 = store.assign_incident_cluster(first.incident_id, "cause:SRC|window:1")
    c2 = store.assign_incident_cluster(second.incident_id, "cause:SRC|window:1")
    assert c1["cluster_id"] == c2["cluster_id"]
    assert c2["member_count"] == 2
    grouped = store.list_incident_clusters()
    assert len(grouped) == 1
    assert grouped[0]["member_count"] == 2

    store.save_incident_rca(first.incident_id, {
        "probable_cause_object": "SRC",
        "cause_confidence": 0.7,
        "affected_contracts": [{"product": "A"}],
        "affected_internal_gates": [{"product": "B"}],
        "cause_candidates": [],
        "recurrence_count": 0,
    })
    assert store.get_incident_rca(first.incident_id)["probable_cause_object"] == "SRC"


# ---------------------------------------------------------------- SLA

def test_sla_windows(tmp_path, monkeypatch):
    store = ResultStore(tmp_path / "t.db")
    now = datetime.now(timezone.utc)

    def _event(days_ago: float, from_state: str, to_state: str):
        at = (now - timedelta(days=days_ago)).isoformat()
        with store._conn() as conn:
            conn.execute(
                "INSERT INTO dq_compliance_events(product, from_state, to_state, contract_version, run_id, at) "
                "VALUES ('P','" + from_state + "','" + to_state + "','1.0.0','r','" + at + "')"
            )

    assert store.get_sla("P", 7) is None  # keine Events → null

    # 10 Tage compliant, dann 2 Tage breached, dann wieder compliant bis jetzt
    _event(10, "unknown", "compliant")
    _event(4, "compliant", "breached")
    _event(2, "breached", "compliant")

    sla7 = store.get_sla("P", 7)
    # Fenster 7d: 3d compliant + 2d breached + 2d compliant = 5/7 ≈ 71.4 %
    assert sla7 is not None and 70.0 < sla7 < 73.0
    sla30 = store.get_sla("P", 30)
    # Messbeginn = erstes Event (vor 10d): 8d compliant von 10d = 80 %
    assert sla30 is not None and 78.0 < sla30 < 82.0


# ---------------------------------------------------------------- Gating

class _StaleConn:
    """Frische-Check liefert 999999s (verletzt), alles andere 0."""

    class _Cur:
        def __init__(self):
            self.description = [("v",)]
            self._rows = []

        def execute(self, sql, params=None):
            if str(sql).strip().upper().startswith("SET"):
                self._rows = []
                return
            self._rows = [(999999,)] if "SECONDS_BETWEEN" in sql else [(0,)]

        def fetchone(self):
            return self._rows.pop(0) if self._rows else None

        def fetchmany(self, size=100):
            return []

        def close(self):
            pass

    def cursor(self):
        return self._Cur()


def _config() -> DatasetConfig:
    return DatasetConfig(dataset="DS_X", schema="S", checks=[
        CheckDef(name="freshness_TS", sql='SELECT SECONDS_BETWEEN(MAX("TS"), CURRENT_TIMESTAMP) FROM "S"."T"',
                 expect="< 86400", severity="warn", type="freshness"),
        CheckDef(name="x_not_null", sql='SELECT COUNT(*) FROM "S"."T" WHERE "X" IS NULL',
                 expect="= 0", severity="fail", type="missing"),
        CheckDef(name="ref_check", sql='SELECT COUNT(*) FROM "S"."T" f LEFT JOIN "S"."D" d ON 1=1 WHERE d.X IS NULL',
                 expect="= 0", severity="critical", type="reference_integrity"),
    ])


def test_gating_produces_skipped_stale():
    summary = run_checks(_config(), _StaleConn(), results_db=None,
                         execution_mode="isolated", gating=True)
    by_name = {r.name: r for r in summary.results}
    assert by_name["freshness_TS"].passed is False          # Gate verletzt
    assert by_name["x_not_null"].state == "executed"        # billig → läuft trotzdem
    assert by_name["ref_check"].state == "skipped_stale"    # teuer → übersprungen (G6)
    # Skipped zählt weder als pass noch als fail
    assert summary.failed == 0
    assert summary.overall_status == "warn"  # nur das warn-Gate ist rot
    assert summary.total == 3                # aber sichtbar in der Gesamtzahl


def test_no_gating_runs_everything():
    summary = run_checks(_config(), _StaleConn(), results_db=None,
                         execution_mode="isolated", gating=False)
    assert all(r.state == "executed" for r in summary.results)


def test_gating_passes_through_when_fresh():
    class _FreshConn(_StaleConn):
        class _Cur(_StaleConn._Cur):
            def execute(self, sql, params=None):
                if str(sql).strip().upper().startswith("SET"):
                    self._rows = []
                    return
                self._rows = [(0,)]

        def cursor(self):
            return self._Cur()

    summary = run_checks(_config(), _FreshConn(), results_db=None,
                         execution_mode="isolated", gating=True)
    assert all(r.state == "executed" for r in summary.results)
    assert summary.overall_status == "pass"


def test_family_status_rollup(tmp_path):
    """R3-2: Objekt × Familie aus check_type."""
    from dq_core.engine.models import CheckResult, RunSummary
    store = ResultStore(tmp_path / "t.db")
    now = datetime.now(timezone.utc).isoformat()
    store.save_run(RunSummary(
        run_id="r1", dataset="DS_X", schema="S", started_at=now, finished_at=now,
        overall_status="fail", total=2, passed=1, failed=1, warnings=0,
        results=[
            CheckResult(name="freshness_TS", sql="", expect="", severity="warn",
                        passed=True, type="freshness"),
            CheckResult(name="key_unique", sql="", expect="", severity="critical",
                        passed=False, type="duplicate"),
        ],
        run_state="finished",
    ))
    fam = store.get_object_family_status()
    assert fam["DS_X"]["observability"] == "pass"
    assert fam["DS_X"]["quality"] == "critical"
