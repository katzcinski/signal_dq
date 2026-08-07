"""Data-Diff über Profil-Snapshots (Konzept §B.2/§B.3) — reine Aggregat-Diffs."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "packages"))
sys.path.insert(0, str(Path(__file__).parents[2]))

from dq_core.profile.diff import diff_profiles, reconcile_keys


def _profile(row_count, columns):
    return {
        "row_count": row_count,
        "column_count": len(columns),
        "columns": columns,
        "pk_candidates": {"single": [c["column"] for c in columns if c.get("pk")]},
    }


def test_row_count_delta_and_pct():
    base = _profile(1000, [{"column": "A", "null_pct": 0.0, "distinct": 1000}])
    head = _profile(900, [{"column": "A", "null_pct": 0.0, "distinct": 900}])
    d = diff_profiles(base, head)
    assert d["row_count"]["delta"] == -100
    assert d["row_count"]["pct_delta"] == -10.0


def test_column_metric_delta_flags_change():
    base = _profile(100, [{"column": "AMT", "null_pct": 0.1, "distinct": 50}])
    head = _profile(100, [{"column": "AMT", "null_pct": 4.0, "distinct": 50}])
    d = diff_profiles(base, head)
    col = next(c for c in d["columns"] if c["column"] == "AMT")
    assert col["changed"] is True
    assert col["metrics"]["null_pct"]["delta"] == 3.9
    assert "AMT" in d["changed_columns"]


def test_added_and_removed_columns():
    base = _profile(10, [{"column": "A", "distinct": 10}, {"column": "B", "distinct": 5}])
    head = _profile(10, [{"column": "A", "distinct": 10}, {"column": "C", "distinct": 7}])
    d = diff_profiles(base, head)
    assert d["added_columns"] == ["C"]
    assert d["removed_columns"] == ["B"]


def test_unchanged_column_not_flagged():
    base = _profile(10, [{"column": "A", "null_pct": 0.0, "distinct": 10, "min": 1, "max": 9}])
    head = _profile(10, [{"column": "A", "null_pct": 0.0, "distinct": 10, "min": 1, "max": 9}])
    d = diff_profiles(base, head)
    assert d["changed_columns"] == []


def test_reconcile_keys_distinct_and_duplicates():
    # base: 1000 rows, key distinct 1000 (unique). head: 1000 rows, distinct 990 → Duplikate.
    base = _profile(1000, [{"column": "ID", "distinct": 1000, "pk": True}])
    head = _profile(1000, [{"column": "ID", "distinct": 990}])
    rec = reconcile_keys(base, head, ["ID"])
    key = rec["keys"][0]
    assert key["distinct_delta"] == -10
    assert key["base_duplicates"] is False
    assert key["head_duplicates"] is True
    assert rec["row_delta"] == 0


def test_reconcile_keys_handles_missing_numbers():
    base = _profile(None, [{"column": "ID"}])
    head = _profile(5, [{"column": "ID", "distinct": 5}])
    rec = reconcile_keys(base, head, ["ID"])
    assert rec["keys"][0]["base_distinct"] is None
    assert rec["row_delta"] is None
