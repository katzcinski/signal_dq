# [ENGINE-ADJACENT] frameworkfrei (G7) — reine Aggregat-Diffs, kein Web-Import.
"""Data-Diff über Profil-Snapshots (Konzept §B.2/§B.3).

Vergleicht zwei Aggregat-Profile desselben logischen Datasets — zwei Zeitpunkte
(Versions-/Deploy-Diff) oder zwei Environments (dev vs. prod). Arbeitet
**ausschließlich auf Aggregaten/Verteilungen** (count/null%/distinct/min/max);
Sample-Rows bleiben hinter dem PII-Gate (G8). Vollständiger zeilenweiser Row-Diff
ist v1 bewusst out-of-scope.

Eingabe ist die `profile_table`-Result-Form: ``{row_count, column_count,
columns:[{column, null_pct, distinct, uniqueness_pct, min, max, ...}]}``.
"""
from __future__ import annotations

from typing import Any


def _num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _delta(base: Any, head: Any) -> float | None:
    b, h = _num(base), _num(head)
    if b is None or h is None:
        return None
    return round(h - b, 4)


def _index_columns(profile: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(c.get("column")): c for c in (profile.get("columns") or []) if c.get("column")}


# Pro Spalte verglichene Metriken (numerische Aggregate aus dem Profiler).
_COLUMN_METRICS = ("null_pct", "distinct", "uniqueness_pct", "min", "max", "avg", "median")


def diff_profiles(base: dict[str, Any], head: dict[str, Any]) -> dict[str, Any]:
    """B-2: Verteilungs-Diff zweier Profil-Snapshots.

    Liefert Row-/Column-Count-Deltas, je-Spalte-Metrik-Deltas sowie
    hinzugekommene/entfernte Spalten."""
    base_cols = _index_columns(base)
    head_cols = _index_columns(head)

    column_diffs: list[dict[str, Any]] = []
    for name in sorted(base_cols.keys() & head_cols.keys()):
        b, h = base_cols[name], head_cols[name]
        deltas = {
            m: {"base": b.get(m), "head": h.get(m), "delta": _delta(b.get(m), h.get(m))}
            for m in _COLUMN_METRICS
        }
        changed = any(d["delta"] not in (None, 0) for d in deltas.values())
        column_diffs.append({"column": name, "metrics": deltas, "changed": changed})

    added = sorted(head_cols.keys() - base_cols.keys())
    removed = sorted(base_cols.keys() - head_cols.keys())

    return {
        "row_count": {
            "base": base.get("row_count"),
            "head": head.get("row_count"),
            "delta": _delta(base.get("row_count"), head.get("row_count")),
            "pct_delta": _pct(base.get("row_count"), head.get("row_count")),
        },
        "column_count": {
            "base": base.get("column_count"),
            "head": head.get("column_count"),
            "delta": _delta(base.get("column_count"), head.get("column_count")),
        },
        "columns": column_diffs,
        "added_columns": added,
        "removed_columns": removed,
        "changed_columns": [c["column"] for c in column_diffs if c["changed"]],
    }


def _pct(base: Any, head: Any) -> float | None:
    b, h = _num(base), _num(head)
    if b is None or h is None or b == 0:
        return None
    return round((h - b) / abs(b) * 100, 2)


def reconcile_keys(
    base: dict[str, Any], head: dict[str, Any], key_columns: list[str]
) -> dict[str, Any]:
    """B-3: Key-Reconciliation über Snapshot-Kardinalitäten.

    Aus zwei Profil-Snapshots: je Key-Spalte Volumen-/Distinct-/Uniqueness-Drift
    und ein Duplikat-Indikator (rows > distinct). Die vollständige Mengen-Differenz
    (only_base/only_head via live EXCEPT) ist die spätere Erweiterung — wird, falls
    von einer Live-Erfassung mitgeliefert, unverändert durchgereicht."""
    base_cols = _index_columns(base)
    head_cols = _index_columns(head)
    base_rows = _num(base.get("row_count"))
    head_rows = _num(head.get("row_count"))

    per_key: list[dict[str, Any]] = []
    for col in key_columns:
        b, h = base_cols.get(col, {}), head_cols.get(col, {})
        b_distinct, h_distinct = _num(b.get("distinct")), _num(h.get("distinct"))
        per_key.append({
            "column": col,
            "base_distinct": b_distinct,
            "head_distinct": h_distinct,
            "distinct_delta": _delta(b_distinct, h_distinct),
            "base_duplicates": (base_rows is not None and b_distinct is not None and base_rows > b_distinct),
            "head_duplicates": (head_rows is not None and h_distinct is not None and head_rows > h_distinct),
        })

    return {
        "key_columns": list(key_columns),
        "base_rows": base_rows,
        "head_rows": head_rows,
        "row_delta": _delta(base_rows, head_rows),
        "row_pct_delta": _pct(base.get("row_count"), head.get("row_count")),
        "keys": per_key,
    }
