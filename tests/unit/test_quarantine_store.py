"""Quarantäne-Episoden im Result-Store: Lifecycle open → reconciled →
released → resolved (+ superseded), Dedupe je Produkt, Übergangs-Guards und
Persistenz der Enforcement-Spalten (Migration 016)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "packages"))

from dq_core.engine.models import CheckResult, RunSummary
from dq_core.store.sqlite_store import ResultStore


@pytest.fixture
def store(tmp_path):
    return ResultStore(tmp_path / "test.db")


def _summary(verdict="quarantine", enforcement="quarantine"):
    return RunSummary(
        run_id="r1", dataset="DS", schema="S",
        started_at="2026-07-10T00:00:00", finished_at="2026-07-10T00:01:00",
        overall_status="fail", total=1, passed=0, failed=1, warnings=0,
        gate_verdict=verdict,
        results=[CheckResult(
            name="c1", sql="SELECT 1", expect="= 0", severity="fail",
            passed=False, enforcement=enforcement,
        )],
    )


class TestEnforcementPersistence:
    def test_gate_verdict_and_enforcement_persisted(self, store):
        store.save_run(_summary())
        run = store.get_run("r1")
        assert run["gate_verdict"] == "quarantine"
        assert run["results"][0]["enforcement_mode"] == "quarantine"

    def test_try_begin_run_persists_verdict_default(self, store):
        summary = _summary(verdict="proceed")
        summary.run_state = "running"
        assert store.try_begin_run(summary)
        assert store.get_run("r1")["gate_verdict"] == "proceed"


class TestQuarantineLifecycle:
    def test_open_and_dedupe_bumps_generation(self, store):
        qid = store.open_quarantine("DS", "r1", ["c1"], contract_version="1.0.0")
        again = store.open_quarantine("DS", "r2", ["c1", "c2"])
        assert again == qid
        episode = store.get_quarantine(qid)
        assert episode["generation"] == 2
        assert episode["failed_checks"] == ["c1", "c2"]
        assert episode["run_id"] == "r2"

    def test_full_lifecycle(self, store):
        qid = store.open_quarantine("DS", "r1", ["c1"])
        episode = store.reconcile_quarantine(qid, 42)
        assert episode["status"] == "reconciled" and episode["row_count"] == 42
        episode = store.release_quarantine(qid, "steward-1", "geprüft")
        assert episode["status"] == "released" and episode["released_by"] == "steward-1"
        episode = store.resolve_quarantine(qid, "steward-1", reason="reprocessed")
        assert episode["status"] == "resolved" and episode["resolve_reason"] == "reprocessed"
        actions = [e["action"] for e in store.get_quarantine(qid)["events"]]
        assert actions == ["opened", "reconciled", "released", "resolved"]

    def test_terminal_episode_rejects_transitions(self, store):
        qid = store.open_quarantine("DS", "r1", ["c1"])
        store.resolve_quarantine(qid, "steward-1", reason="manual")
        with pytest.raises(ValueError):
            store.release_quarantine(qid, "steward-1")

    def test_terminal_episode_allows_new_one(self, store):
        first = store.open_quarantine("DS", "r1", ["c1"])
        store.resolve_quarantine(first, "s", reason="manual")
        second = store.open_quarantine("DS", "r9", ["c1"])
        assert second != first

    def test_supersede(self, store):
        qid = store.open_quarantine("DS", "r1", ["c1"])
        episode = store.supersede_quarantine(qid, note="Contract v2.0.0")
        assert episode["status"] == "superseded"
        assert episode["resolve_reason"] == "superseded"

    def test_list_filters(self, store):
        a = store.open_quarantine("DS_A", "r1", ["c1"])
        store.open_quarantine("DS_B", "r2", ["c2"])
        store.resolve_quarantine(a, "s", reason="manual")
        assert len(store.list_quarantine()) == 2
        assert len(store.list_quarantine(status="open")) == 1
        assert store.list_quarantine(product="DS_A")[0]["product"] == "DS_A"

    def test_missing_episode_returns_none(self, store):
        assert store.get_quarantine(999) is None
        assert store.release_quarantine(999, "s") is None
