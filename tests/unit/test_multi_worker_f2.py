"""F2 — Multi-Worker-Wahrheit: Run-Status und Progress leben im Store, nicht
im Prozess-Speicher. Zwei Worker werden als zwei `ResultStore`-Instanzen auf
derselben SQLite-Datei modelliert (getrennte Connections, geteilte DB-Datei —
genau das Verhältnis zweier uvicorn-Worker). Damit ist die HANDOVER-Acceptance
„Multi-Worker-Deployment zeigt denselben Run-Status" ohne 2 reale Prozesse /
Playwright prüfbar.

Belegt:
- Doppellauf-Schutz hält über Instanzgrenzen (partieller Unique-Index, nicht
  In-Memory-Flag): Worker B kann keinen zweiten Run auf demselben Dataset
  starten, während Worker A läuft.
- Run-Zustandsübergänge von Worker A sind für Worker B sofort sichtbar.
- Der SSE-Generator (services/api/sse.py) liest Progress + Terminalzustand,
  die ein anderer Worker geschrieben hat — SSE und Polling teilen dieselbe
  Quelle (S-9: kein geteilter In-Memory-Zustand).
"""
import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "packages"))
sys.path.insert(0, str(Path(__file__).parents[2]))

from dq_core.engine.models import CheckResult, RunSummary
from dq_core.store.sqlite_store import ResultStore
from services.api.sse import make_progress_callback, sse_generator


def _summary(run_id: str, dataset: str = "DS_X", state: str = "running") -> RunSummary:
    return RunSummary(
        run_id=run_id, dataset=dataset, schema="S",
        started_at=datetime.now(timezone.utc).isoformat(),
        finished_at="", overall_status="pass",
        total=1, passed=1, failed=0, warnings=0,
        results=[CheckResult(name="c", sql="SELECT 1", expect="= 1",
                             severity="warn", passed=True)],
        run_state=state,
    )


def test_double_run_guard_holds_across_workers(tmp_path):
    db = tmp_path / "shared.db"
    worker_a = ResultStore(db)
    worker_b = ResultStore(db)  # zweiter „Worker" auf derselben Datei

    # A startet einen Run auf DS_X.
    assert worker_a.try_begin_run(_summary("r1", dataset="DS_X")) is True
    # B sieht denselben laufenden Run und wird abgewiesen — kein Doppellauf,
    # obwohl B den Zustand nie im eigenen Speicher gesehen hat.
    assert worker_b.try_begin_run(_summary("r2", dataset="DS_X")) is False
    # Anderes Dataset bleibt für B frei.
    assert worker_b.try_begin_run(_summary("r3", dataset="DS_Y")) is True


def test_run_state_transition_visible_to_other_worker(tmp_path):
    db = tmp_path / "shared.db"
    worker_a = ResultStore(db)
    worker_b = ResultStore(db)

    worker_a.try_begin_run(_summary("r1", dataset="DS_X"))
    assert worker_b.get_run("r1")["run_state"] == "running"

    # A schließt den Run ab; B liest denselben Übergang.
    worker_a.set_run_state("r1", "finished", datetime.now(timezone.utc).isoformat())
    assert worker_b.get_run("r1")["run_state"] == "finished"

    # Dataset ist danach auch für B wieder startbar.
    assert worker_b.try_begin_run(_summary("r4", dataset="DS_X")) is True


def test_sse_streams_progress_written_by_other_worker(tmp_path):
    """Worker A schreibt Progress + Terminalzustand; ein SSE-Consumer auf einer
    zweiten Store-Instanz sieht beides über seinen Cursor (S-9/A5-Parität)."""
    db = tmp_path / "shared.db"
    worker_a = ResultStore(db)
    consumer_store = ResultStore(db)

    worker_a.try_begin_run(_summary("r1", dataset="DS_X"))

    # A emittiert zwei Progress-Zeilen über den Store-getriebenen Callback.
    emit = make_progress_callback("r1", worker_a)
    emit("Check 1/2 — keys")
    emit("Check 2/2 — freshness")
    worker_a.set_run_state("r1", "finished", datetime.now(timezone.utc).isoformat())

    async def drain() -> list[dict]:
        import json
        events = []
        gen = sse_generator(consumer_store, "r1")
        # sse_generator endet selbst bei Terminalzustand (finished) → kein Timeout nötig.
        async for chunk in gen:
            if chunk.startswith("data: "):
                events.append(json.loads(chunk[len("data: "):].strip()))
        return events

    events = asyncio.run(asyncio.wait_for(drain(), timeout=5))
    types = [e["type"] for e in events]

    assert "connected" in types
    assert "run_started" in types
    lines = [e["line"] for e in events if e["type"] == "progress"]
    assert lines == ["Check 1/2 — keys", "Check 2/2 — freshness"]
    finished = [e for e in events if e["type"] == "run_finished"]
    assert finished and finished[0]["overall_status"] == "pass"
