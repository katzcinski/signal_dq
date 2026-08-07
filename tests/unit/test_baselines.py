import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "packages"))

from dq_core.obs.baselines import BaselineManager
from dq_core.store.sqlite_store import ResultStore


def test_median_is_persisted(tmp_path):
    store = ResultStore(tmp_path / "b.db")
    manager = BaselineManager(store)

    manager.update_baseline("DS", "volume_min_rows", [10, 11, 12, 13, 1000])
    baseline = manager.get_baseline("DS", "volume_min_rows")

    assert baseline is not None
    assert baseline["median_v"] == 12.0


def test_robust_bounds_resist_outlier(tmp_path):
    store = ResultStore(tmp_path / "b.db")
    manager = BaselineManager(store)
    baseline = manager.update_baseline("DS", "m", [100, 101, 102, 99, 100, 10_000])

    lo, hi = manager.compute_robust_bounds(baseline, k=3)

    assert lo > 90
    assert hi < 110


def test_mad_zero_falls_back_without_division(tmp_path):
    store = ResultStore(tmp_path / "b.db")
    manager = BaselineManager(store)
    baseline = manager.update_baseline("DS", "m", [5, 5, 5, 5, 5])

    assert manager.robust_zscore(5, baseline) is None
    assert manager.compute_robust_bounds(baseline) == (5.0, 5.0)


def test_seasonal_bucket_is_persisted_per_key(tmp_path):
    store = ResultStore(tmp_path / "b.db")
    manager = BaselineManager(store)
    bucket = manager.bucket_key_for("2026-06-29T10:00:00+00:00", ["dow", "eom"])

    manager.update_baseline("DS", "volume_min_rows", [10, 11, 12, 13, 14], strategy="seasonal", bucket_key=bucket)
    baseline = manager.get_baseline("DS", "volume_min_rows", strategy="seasonal", bucket_key=bucket)

    assert bucket == "dow=0|eom=0"
    assert baseline is not None
    assert baseline["warmup_remaining"] == 0
