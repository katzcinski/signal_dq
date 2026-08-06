"""Garantie-Backtesting (V1) — Simulation gegen die Messwert-Historie."""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "packages"))

from dq_core.obs.backtest import backtest_expectation

NOW = datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc)


def _point(days_ago: int, value, state: str = "executed") -> dict:
    at = (NOW - timedelta(days=days_ago)).isoformat()
    return {"run_id": f"run-{days_ago}", "started_at": at, "actual_value": value, "state": state}


def test_threshold_counts_breaches_and_windows():
    history = [
        _point(100, "1500"),  # außerhalb beider Fenster
        _point(60, "900"),    # Breach, nur im 90d-Fenster
        _point(10, "1200"),
        _point(1, "800"),     # Breach, in beiden Fenstern
    ]
    report = backtest_expectation(history, ">= 1000", window_days=(30, 90), now=NOW)

    assert report["points"] == 4
    assert report["evaluated"] == 4
    assert report["breaches"] == 2
    assert report["breach_rate"] == pytest.approx(0.5)
    assert report["first_breach_at"] < report["last_breach_at"]
    assert [w["breaches"] for w in report["windows"]] == [1, 2]
    assert [w["points"] for w in report["windows"]] == [2, 3]
    # Sample: jüngste Verstöße zuerst
    assert report["sample"][0]["value"] == "800"


def test_delta_uses_previous_value_with_warmup():
    history = [
        _point(3, "1000"),  # Warm-up: kein Vorwert → pass
        _point(2, "1010"),  # 1 % → pass
        _point(1, "600"),   # ~40 % → Breach
    ]
    report = backtest_expectation(history, "DELTA <= 10%", now=NOW)
    assert report["breaches"] == 1
    assert report["sample"][0]["value"] == "600"


def test_non_executed_states_and_non_numeric_values():
    history = [
        _point(4, "1000"),
        _point(3, None, state="skipped_stale"),   # G6: zählt nicht
        _point(2, "n/a"),                          # nicht bewertbar → skipped
        _point(1, "500"),
    ]
    report = backtest_expectation(history, ">= 800", now=NOW)
    assert report["points"] == 3       # skipped_stale ausgefiltert
    assert report["evaluated"] == 2
    assert report["skipped"] == 1
    assert report["breaches"] == 1


def test_invalid_expectation_raises():
    with pytest.raises(ValueError):
        backtest_expectation([_point(1, "1")], "FOO BAR", now=NOW)


def test_empty_history_is_calm():
    report = backtest_expectation([], ">= 1", now=NOW)
    assert report["points"] == 0
    assert report["breaches"] == 0
    assert report["breach_rate"] == 0.0
    assert report["first_breach_at"] is None
