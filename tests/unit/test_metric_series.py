"""UX-N1: get_metric_series — freshness/volume time-series with baseline band."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[2] / "packages"))

from dq_core.store.sqlite_store import ResultStore
from dq_core.engine.models import CheckResult, RunSummary


def make_obs_run(run_id, started_at, row_count, *, passed=True, dataset="DS"):
    vol = CheckResult(
        name="volume_row_count",
        sql="SELECT COUNT(*)",
        expect="within bounds",
        severity="warn",
        passed=passed,
        actual_value=str(row_count),
        duration_ms=3,
        type="row_count",
    )
    fresh = CheckResult(
        name="freshness_load_ts",
        sql="SELECT age",
        expect="<= PT24H",
        severity="fail",
        passed=True,
        actual_value="2.0",
        duration_ms=2,
        type="freshness",
    )
    return RunSummary(
        run_id=run_id,
        dataset=dataset,
        schema="SCH",
        started_at=started_at,
        finished_at=started_at,
        overall_status="pass" if passed else "warn",
        total=2,
        passed=2 if passed else 1,
        failed=0,
        warnings=0 if passed else 1,
        triggered_by="test",
        run_state="finished",
        results=[vol, fresh],
    )


def _seed_baseline(store, dataset, metric, mean, stddev):
    with store._conn() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO dq_baselines
               (dataset, metric, n, mean_v, stddev_v, p01, p99, mad, updated_at, warmup_remaining)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (dataset, metric, 10, mean, stddev, mean - 2, mean + 2, 1.0,
             "2026-01-10T00:00:00Z", 0),
        )


def test_series_grouped_by_metric_family(tmp_path):
    store = ResultStore(tmp_path / "t.db")
    for i, day in enumerate(["2026-01-01", "2026-01-02", "2026-01-03"]):
        store.save_run(make_obs_run(f"r{i}", f"{day}T00:00:00Z", 100 + i))

    out = store.get_metric_series("DS")
    assert out["dataset"] == "DS"
    by_name = {s["check_name"]: s for s in out["series"]}
    assert set(by_name) == {"volume_row_count", "freshness_load_ts"}

    vol = by_name["volume_row_count"]
    assert vol["metric"] == "volume"
    # Chronological: oldest first.
    assert [p["value"] for p in vol["points"]] == [100.0, 101.0, 102.0]
    assert by_name["freshness_load_ts"]["metric"] == "freshness"


def test_band_and_anomaly_flags(tmp_path):
    store = ResultStore(tmp_path / "t.db")
    # Baseline mean=100 stddev=2 → band [94, 106].
    _seed_baseline(store, "DS", "volume_row_count", mean=100.0, stddev=2.0)
    store.save_run(make_obs_run("r0", "2026-02-01T00:00:00Z", 100))   # in band, passed
    store.save_run(make_obs_run("r1", "2026-02-02T00:00:00Z", 500))   # out of band
    store.save_run(make_obs_run("r2", "2026-02-03T00:00:00Z", 101, passed=False))  # failed

    vol = next(s for s in store.get_metric_series("DS")["series"]
               if s["check_name"] == "volume_row_count")
    assert vol["baseline"]["lower"] == 94.0
    assert vol["baseline"]["upper"] == 106.0
    flags = [p["anomaly"] for p in vol["points"]]
    assert flags == [False, True, True]  # in-band ok, out-of-band, failed


def test_non_numeric_actual_has_null_value(tmp_path):
    store = ResultStore(tmp_path / "t.db")
    run = make_obs_run("r0", "2026-03-01T00:00:00Z", 100)
    run.results[0].actual_value = "n/a"
    store.save_run(run)
    vol = next(s for s in store.get_metric_series("DS")["series"]
               if s["check_name"] == "volume_row_count")
    assert vol["points"][0]["value"] is None
    # No band → no out-of-band anomaly; passed → not an anomaly.
    assert vol["points"][0]["anomaly"] is False


def test_empty_for_unknown_dataset(tmp_path):
    store = ResultStore(tmp_path / "t.db")
    assert store.get_metric_series("NOPE") == {"dataset": "NOPE", "series": []}


def test_health_trend_improving(tmp_path):
    store = ResultStore(tmp_path / "t.db")
    for ds in ("DS_A", "DS_B"):
        prev = make_obs_run(f"{ds}-0", "2026-04-01T00:00:00Z", 100, passed=False, dataset=ds)
        prev.overall_status = "fail"
        store.save_run(prev)
        cur = make_obs_run(f"{ds}-1", "2026-04-02T00:00:00Z", 100, dataset=ds)
        cur.overall_status = "pass"
        store.save_run(cur)
    trend = store.get_health_trend()
    assert trend == {"current_pct": 100.0, "previous_pct": 0.0, "datasets": 2}


def test_status_heatmap_worst_per_day(tmp_path):
    from datetime import date, timedelta
    store = ResultStore(tmp_path / "t.db")
    today = date.today().isoformat()
    # Two runs same day: pass then fail → worst (fail) wins.
    ok = make_obs_run("h-0", f"{today}T01:00:00Z", 100)
    ok.overall_status = "pass"
    store.save_run(ok)
    bad = make_obs_run("h-1", f"{today}T09:00:00Z", 100, passed=False)
    bad.overall_status = "fail"
    store.save_run(bad)

    hm = store.get_status_heatmap(days=30)
    assert len(hm["days"]) == 30
    assert hm["days"][-1] == today
    assert hm["datasets"] == ["DS"]
    assert hm["matrix"]["DS"][today] == "fail"
    # A day with no run is absent from the dataset's cell map.
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    assert yesterday not in hm["matrix"]["DS"]
