"""Schema-Evolution (A2/UX-N9) — Snapshot-Diff + Store-Rollups."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "packages"))
sys.path.insert(0, str(Path(__file__).parents[2]))

from dq_core.contract.schema_drift import diff_snapshots
from dq_core.store.sqlite_store import ResultStore


def _store(tmp_path):
    return ResultStore(tmp_path / "evolution.db")


# ---------------------------------------------------------------- diff_snapshots

def test_diff_snapshots_added_removed_and_type_change():
    before = [
        {"name": "A", "type": "cds.String"},
        {"name": "B", "type": "cds.Integer"},
        {"name": "C", "type": "cds.Decimal"},
    ]
    after = [
        {"name": "A", "type": "NVARCHAR(20)"},   # gleiche Familie → kein Befund
        {"name": "B", "type": "cds.String"},      # integer → string
        {"name": "D", "type": "cds.Date"},        # neu; C entfernt
    ]
    findings = diff_snapshots(before, after)
    cats = [(f.category, f.column) for f in findings]
    assert cats == [
        ("column_added", "D"),
        ("column_removed", "C"),
        ("type_changed", "B"),
    ]
    typed = next(f for f in findings if f.category == "type_changed")
    assert (typed.before, typed.after) == ("integer", "string")
    # Snapshot-Diffs tragen keine Contract-Bewertung.
    assert all(f.breaking is False for f in findings)


def test_diff_snapshots_nullable_and_key_change():
    before = [{"name": "A", "type": "string", "key": True, "nullable": False}]
    after = [{"name": "A", "type": "string", "key": False, "nullable": True}]
    findings = diff_snapshots(before, after)
    cats = {f.category for f in findings}
    assert cats == {"nullable_relaxed", "key_changed"}


def test_diff_snapshots_identical_is_empty():
    cols = [{"name": "A", "type": "string"}, {"name": "B", "type": "integer"}]
    assert diff_snapshots(cols, cols) == []


# ------------------------------------------------------------------- Store-Ebene

def test_get_schema_snapshots_oldest_first_and_limit(tmp_path):
    store = _store(tmp_path)
    for i in range(4):
        store.save_schema_snapshot("DS_X", [{"name": f"C{i}"}], f"hash-{i}")
    snaps = store.get_schema_snapshots("DS_X", limit=3)
    assert [s["inventory_hash"] for s in snaps] == ["hash-1", "hash-2", "hash-3"]


def test_list_schema_drift_objects_rollup(tmp_path):
    store = _store(tmp_path)
    # DS_A: zwei Snapshots (unterschiedliche Schemata) + ein breaking-Befund.
    store.save_schema_snapshot("DS_A", [{"name": "A"}], "h1")
    store.save_schema_snapshot("DS_A", [{"name": "A"}, {"name": "B"}], "h2")
    store.record_schema_drift(
        "DS_A",
        [{"category": "column_removed", "column": "C", "before": "C", "after": "", "breaking": True}],
        contract_version="2.0.0",
        incident_id=7,
    )
    # DS_B: nur Snapshots, kein Drift.
    store.save_schema_snapshot("DS_B", [{"name": "A"}], "h1")

    rows = {r["object_name"]: r for r in store.list_schema_drift_objects()}
    assert set(rows) == {"DS_A", "DS_B"}

    a = rows["DS_A"]
    assert a["snapshots"] == 2
    assert a["distinct_schemas"] == 2
    assert a["findings"] == 1
    assert a["breaking"] == 1
    assert a["last_incident_id"] == 7
    assert a["last_captured_at"] >= a["first_captured_at"]

    b = rows["DS_B"]
    assert b["snapshots"] == 1
    assert b["findings"] == 0
    assert b["last_incident_id"] is None
