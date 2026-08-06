# [ENGINE-ADJACENT] frameworkfrei (G7) — kein FastAPI/Flask/Starlette-Import.
"""Garantie-Backtesting: „Wie oft hätte diese Expectation historisch gefeuert?"

Bewertet einen Expectation-Entwurf gegen die bereits persistierte Messwert-
Historie (`dq_check_results.actual_value` × `dq_runs.started_at`) — **rein
lesend**, kein SQL gegen HANA, keine neuen Läufe. Zweck: Schwellwerte vor der
Aktivierung kalibrieren (Anti-Alert-Fatigue), Proposal-Entscheidungen mit
„hätte N× in 90 d gefeuert" unterlegen.

Die Bewertung nutzt dieselbe Grammatik wie die Engine (`engine.expectation`),
damit Simulation und späterer Ernstfall nicht auseinanderlaufen. `DELTA`-
Expectations laufen wie im Ernstfall gegen den jeweils vorigen numerischen
Messwert (erster Punkt = Warm-up = pass).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from dq_core.engine.expectation import evaluate, validate_expectation


def _parse_ts(value: Any) -> datetime | None:
    try:
        ts = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts


def backtest_expectation(
    history: list[dict[str, Any]],
    expect: str,
    window_days: tuple[int, ...] = (30, 90),
    now: datetime | None = None,
) -> dict[str, Any]:
    """Simulation einer Expectation über die Messwert-Historie **eines** Checks.

    `history` ist chronologisch (älteste zuerst) mit je `actual_value`,
    `started_at`, `run_id` und optional `state` (G6: nur `executed` zählt).
    Wirft `ValueError` bei ungültiger Expectation (gleiche Grammatik wie Engine).
    """
    validate_expectation(expect)
    now = now or datetime.now(timezone.utc)

    points = 0        # ausführbare Historie (state=executed)
    evaluated = 0     # davon gegen die Expectation bewertbar
    skipped = 0       # nicht bewertbar (z. B. nicht-numerischer Messwert)
    breaches: list[dict[str, Any]] = []
    evaluated_points: list[dict[str, Any]] = []
    prev_value: float | None = None

    for rec in history:
        state = rec.get("state")
        if state and state != "executed":
            continue
        points += 1
        actual = rec.get("actual_value")
        try:
            ok = evaluate(actual, expect, previous_value=prev_value)
        except (TypeError, ValueError):
            skipped += 1
            continue
        evaluated += 1
        point = {
            "run_id": str(rec.get("run_id") or ""),
            "at": str(rec.get("started_at") or ""),
            "value": actual,
            "breach": not ok,
        }
        evaluated_points.append(point)
        if not ok:
            breaches.append(point)
        try:
            prev_value = float(actual)
        except (TypeError, ValueError):
            pass  # nicht-numerischer Punkt setzt die DELTA-Referenz nicht zurück

    windows: list[dict[str, Any]] = []
    for days in window_days:
        cutoff = now - timedelta(days=int(days))
        w_eval = w_breach = 0
        for p in evaluated_points:
            ts = _parse_ts(p["at"])
            if ts is None or ts < cutoff:
                continue
            w_eval += 1
            if p["breach"]:
                w_breach += 1
        windows.append({"days": int(days), "points": w_eval, "breaches": w_breach})

    return {
        "expect": expect,
        "points": points,
        "evaluated": evaluated,
        "skipped": skipped,
        "breaches": len(breaches),
        "breach_rate": (len(breaches) / evaluated) if evaluated else 0.0,
        "first_breach_at": breaches[0]["at"] if breaches else None,
        "last_breach_at": breaches[-1]["at"] if breaches else None,
        # jüngste Verstöße zuerst, gedeckelt — Evidenz, keine Rohdaten (G8-frei:
        # actual_value ist ein Aggregat-Messwert, nie eine Rohzeile).
        "sample": list(reversed(breaches))[:10],
        "windows": windows,
    }
