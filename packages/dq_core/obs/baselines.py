"""Observability baselines for rolling and seasonal anomaly checks."""
from __future__ import annotations

import calendar
import statistics
from datetime import datetime, timezone
from typing import Any, Optional


SENSITIVITY_K = {"low": 4.0, "medium": 3.0, "high": 2.0}


class BaselineManager:
    WARMUP_N = 5

    def __init__(self, store: Any) -> None:
        self._store = store

    def update_baseline(
        self,
        dataset: str,
        metric: str,
        values: list[float],
        *,
        strategy: str = "rolling",
        bucket_key: str = "",
    ) -> dict:
        numeric = [float(v) for v in values]
        stats = self._stats(dataset, metric, numeric)
        if strategy == "seasonal" or bucket_key:
            stats["strategy"] = strategy or "seasonal"
            stats["bucket_key"] = bucket_key
            self._persist_bucket(stats)
        else:
            self._persist_global(stats)
        return stats

    def get_baseline(
        self,
        dataset: str,
        metric: str,
        *,
        strategy: str = "rolling",
        bucket_key: str = "",
    ) -> Optional[dict]:
        if not hasattr(self._store, "_conn"):
            return None
        if strategy == "seasonal" or bucket_key:
            with self._store._conn() as conn:
                row = conn.execute(
                    """SELECT * FROM dq_baseline_buckets
                       WHERE dataset=? AND metric=? AND strategy=? AND bucket_key=?""",
                    (dataset, metric, strategy or "seasonal", bucket_key),
                ).fetchone()
            return dict(row) if row else None
        with self._store._conn() as conn:
            row = conn.execute(
                "SELECT * FROM dq_baselines WHERE dataset=? AND metric=?",
                (dataset, metric),
            ).fetchone()
        return dict(row) if row else None

    def compute_bounds(
        self,
        baseline: dict,
        sigma: float = 3.0,
        *,
        method: str = "classic",
    ) -> tuple[float, float]:
        if method == "robust":
            return self.compute_robust_bounds(baseline, k=sigma)
        mean = float(baseline.get("mean_v") or 0.0)
        std = float(baseline.get("stddev_v") or 0.0)
        return (mean - sigma * std, mean + sigma * std)

    def compute_robust_bounds(self, baseline: dict, *, k: float = 3.0) -> tuple[float, float]:
        median = baseline.get("median_v")
        if median is None:
            median = baseline.get("mean_v")
        median_f = float(median or 0.0)
        mad = baseline.get("mad")
        if mad is not None and float(mad) > 0:
            robust_sigma = float(mad) / 0.6745
            return (median_f - k * robust_sigma, median_f + k * robust_sigma)

        p01 = baseline.get("p01")
        p99 = baseline.get("p99")
        if p01 is not None and p99 is not None and float(p01) != float(p99):
            return (float(p01), float(p99))
        return (median_f, median_f)

    def robust_zscore(self, value: float, baseline: dict) -> float | None:
        median = baseline.get("median_v")
        mad = baseline.get("mad")
        if median is None or mad is None or float(mad) == 0:
            return None
        return 0.6745 * (float(value) - float(median)) / float(mad)

    @staticmethod
    def sensitivity_k(sensitivity: str | None) -> float:
        return SENSITIVITY_K.get(str(sensitivity or "medium"), 3.0)

    @staticmethod
    def bucket_key_for(at: str | datetime, season: list[str] | tuple[str, ...] | None) -> str:
        dt = _parse_dt(at)
        axes = sorted(str(axis) for axis in (season or ["dow"]) if str(axis))
        parts: list[str] = []
        for axis in axes:
            if axis == "dow":
                parts.append(f"dow={dt.weekday()}")
            elif axis == "eom":
                last_day = calendar.monthrange(dt.year, dt.month)[1]
                parts.append(f"eom={1 if dt.day == last_day else 0}")
            elif axis == "hour":
                parts.append(f"hour={dt.hour}")
        return "|".join(parts) if parts else "global"

    def _stats(self, dataset: str, metric: str, values: list[float]) -> dict:
        n = len(values)
        warmup_remaining = max(0, self.WARMUP_N - n)
        if not values:
            return {
                "dataset": dataset,
                "metric": metric,
                "n": 0,
                "mean_v": None,
                "stddev_v": None,
                "median_v": None,
                "p01": None,
                "p99": None,
                "mad": None,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "warmup_remaining": warmup_remaining,
            }

        mean_v = statistics.mean(values)
        stddev_v = statistics.stdev(values) if n > 1 else 0.0
        sorted_v = sorted(values)
        p01 = sorted_v[max(0, int((n - 1) * 0.01))]
        p99 = sorted_v[min(n - 1, int((n - 1) * 0.99))]
        median_v = statistics.median(values)
        mad = statistics.median([abs(v - median_v) for v in values])
        return {
            "dataset": dataset,
            "metric": metric,
            "n": n,
            "mean_v": mean_v,
            "stddev_v": stddev_v,
            "median_v": median_v,
            "p01": p01,
            "p99": p99,
            "mad": mad,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "warmup_remaining": warmup_remaining,
        }

    def _persist_global(self, baseline: dict) -> None:
        if not hasattr(self._store, "_conn"):
            return
        with self._store._conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO dq_baselines
                   (dataset, metric, n, mean_v, stddev_v, p01, p99, mad,
                    updated_at, warmup_remaining, median_v)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    baseline["dataset"],
                    baseline["metric"],
                    baseline.get("n"),
                    baseline.get("mean_v"),
                    baseline.get("stddev_v"),
                    baseline.get("p01"),
                    baseline.get("p99"),
                    baseline.get("mad"),
                    baseline.get("updated_at"),
                    baseline.get("warmup_remaining", 0),
                    baseline.get("median_v"),
                ),
            )

    def _persist_bucket(self, baseline: dict) -> None:
        if not hasattr(self._store, "_conn"):
            return
        with self._store._conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO dq_baseline_buckets
                   (dataset, metric, strategy, bucket_key, n, mean_v, stddev_v,
                    median_v, p01, p99, mad, updated_at, warmup_remaining)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    baseline["dataset"],
                    baseline["metric"],
                    baseline.get("strategy", "seasonal"),
                    baseline.get("bucket_key", ""),
                    baseline.get("n"),
                    baseline.get("mean_v"),
                    baseline.get("stddev_v"),
                    baseline.get("median_v"),
                    baseline.get("p01"),
                    baseline.get("p99"),
                    baseline.get("mad"),
                    baseline.get("updated_at"),
                    baseline.get("warmup_remaining", 0),
                ),
            )


def _parse_dt(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        return value
    text = str(value or "")
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(timezone.utc)
