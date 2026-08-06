"""Store-Protocol-Konformität (L-8), Compliance-Events (L-4), Doppellauf-Schutz (L-5),
Diagnostics-TTL (S-8)."""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "packages"))

from dq_core.engine.models import CheckResult, RunSummary
from dq_core.store.base import ResultStoreProtocol
from dq_core.store.hana_store import HanaStore
from dq_core.store.sqlite_store import ResultStore


def _summary(run_id: str, dataset: str = "DS_X", state: str = "finished", started_at: str | None = None) -> RunSummary:
    return RunSummary(
        run_id=run_id, dataset=dataset, schema="S",
        started_at=started_at or datetime.now(timezone.utc).isoformat(),
        finished_at="", overall_status="pass",
        total=1, passed=1, failed=0, warnings=0,
        results=[CheckResult(name="c", sql="SELECT 1", expect="= 1",
                             severity="warn", passed=True)],
        run_state=state,
    )


def test_stores_satisfy_protocol():
    assert isinstance(ResultStore(":memory:"), ResultStoreProtocol)
    assert isinstance(HanaStore(connection=None), ResultStoreProtocol)


def test_compliance_since_preserved_and_events_logged(tmp_path):
    store = ResultStore(tmp_path / "t.db")
    store.set_compliance("P", "1.0.0", "compliant", "r1")
    first = store.get_compliance("P")

    # gleicher Zustand → since bleibt, kein neues Event
    store.set_compliance("P", "1.0.0", "compliant", "r2")
    assert store.get_compliance("P")["since"] == first["since"]
    assert len(store.get_compliance_events("P")) == 1

    # Übergang → neues Event, neues since
    store.set_compliance("P", "1.0.0", "breached", "r3")
    events = store.get_compliance_events("P")
    assert len(events) == 2
    assert events[0]["from_state"] == "compliant"
    assert events[0]["to_state"] == "breached"
    assert store.get_compliance("P")["since"] != first["since"]


def test_try_begin_run_blocks_second_running(tmp_path):
    store = ResultStore(tmp_path / "t.db")
    assert store.try_begin_run(_summary("r1", state="running")) is True
    # zweiter Run auf demselben Dataset, solange r1 läuft → abgelehnt
    assert store.try_begin_run(_summary("r2", state="running")) is False
    # anderer Datensatz ist unabhängig
    assert store.try_begin_run(_summary("r3", dataset="DS_Y", state="running")) is True
    # nach Abschluss von r1 ist das Dataset wieder frei
    store.set_run_state("r1", "finished", datetime.now(timezone.utc).isoformat())
    assert store.try_begin_run(_summary("r4", state="running")) is True


def test_diagnostics_ttl_cleanup(tmp_path):
    db = tmp_path / "t.db"
    store = ResultStore(db, allow_diagnostics=True)
    old = _summary("old_run")
    old.started_at = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
    old.results[0].passed = False
    old.results[0].diagnostic_rows = [{"COL": "pii-value"}]
    store.save_run(old)

    import sqlite3
    conn = sqlite3.connect(db)
    assert conn.execute("SELECT COUNT(*) FROM dq_diagnostics").fetchone()[0] == 1
    conn.close()

    # Re-Open mit TTL → alte Diagnostik wird gelöscht
    ResultStore(db, allow_diagnostics=True, diagnostics_ttl_days=7)
    conn = sqlite3.connect(db)
    assert conn.execute("SELECT COUNT(*) FROM dq_diagnostics").fetchone()[0] == 0
    conn.close()
