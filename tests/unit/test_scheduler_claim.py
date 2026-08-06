"""Option E store layer: schedule CRUD, due-claim semantics, mode filter.

The hard duplicate-run guarantee (try_begin_run partial unique index) is covered
by test_multi_worker_f2; here we verify the claim queue itself — that a due slot
is handed out exactly once per advance, that external/disabled schedules are
never claimed, and that the catch-up policy skips ahead instead of bursting.
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "packages"))

from dq_core.store.sqlite_store import ResultStore


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _store(tmp_path) -> ResultStore:
    return ResultStore(str(tmp_path / "sched.db"))


def test_internal_schedule_claimed_once_per_slot(tmp_path):
    store = _store(tmp_path)
    past = _iso(datetime.now(timezone.utc) - timedelta(seconds=10))
    store.create_schedule(
        schedule_id="obj:A", object_id="A", interval_seconds=3600, next_due_at=past
    )
    now = _iso(datetime.now(timezone.utc))

    first = store.claim_due_schedules(now)
    assert [s["schedule_id"] for s in first] == ["obj:A"]

    # Same instant: already advanced one interval into the future → not due.
    assert store.claim_due_schedules(now) == []

    after = store.get_schedule("obj:A")
    assert after["next_due_at"] > now


def test_external_and_disabled_never_claimed(tmp_path):
    store = _store(tmp_path)
    past = _iso(datetime.now(timezone.utc) - timedelta(seconds=10))
    store.create_schedule(
        schedule_id="obj:EXT", object_id="EXT", mode="external",
        interval_seconds=3600, next_due_at=past,
    )
    store.create_schedule(
        schedule_id="obj:OFF", object_id="OFF", enabled=False,
        interval_seconds=3600, next_due_at=past,
    )
    now = _iso(datetime.now(timezone.utc))
    assert store.claim_due_schedules(now) == []


def test_advance_skips_ahead_after_long_outage(tmp_path):
    store = _store(tmp_path)
    # next_due far in the past, small interval → catch-up must NOT backfill many
    # slots; the new due is exactly one interval ahead of *now*.
    long_ago = _iso(datetime.now(timezone.utc) - timedelta(days=2))
    store.create_schedule(
        schedule_id="obj:S", object_id="S", interval_seconds=60, next_due_at=long_ago
    )
    now_dt = datetime.now(timezone.utc)
    now = _iso(now_dt)
    claimed = store.claim_due_schedules(now)
    assert len(claimed) == 1
    new_due = datetime.fromisoformat(claimed[0]["next_due_at"])
    assert new_due > now_dt
    assert new_due <= now_dt + timedelta(seconds=61)


def test_update_and_record_run(tmp_path):
    store = _store(tmp_path)
    store.create_schedule(schedule_id="obj:A", object_id="A", interval_seconds=3600)

    store.update_schedule("obj:A", mode="external", enabled=False)
    row = store.get_schedule("obj:A")
    assert row["mode"] == "external"
    assert row["enabled"] == 0

    store.record_schedule_run("obj:A", "run-xyz", "started")
    row = store.get_schedule("obj:A")
    assert row["last_run_id"] == "run-xyz"
    assert row["last_status"] == "started"

    assert store.delete_schedule("obj:A") is True
    assert store.get_schedule("obj:A") is None
