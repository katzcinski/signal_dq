"""Primary-Key-Kandidaten-Erkennung (framework-free).

Bewertet pro-Spalten-Statistiken (aus :mod:`profiler`) auf Eignung als
Primärschlüssel und sucht zusätzlich Mehrspalten-(Composite-)Kandidaten über
``COUNT(DISTINCT combo)``-Aggregate. Nur Aggregate — keine Nutzdatenzeilen.

Combo-Caps wie in Meridian beibehalten:
  * <= 20 null-freie Spalten  -> exakte Vollsuche aller Kombinationen
  * sonst                      -> 8-Spalten-Budget, max. 30 Kombinationen
"""
from __future__ import annotations

from itertools import combinations
from typing import Any

from dq_core.connect.query_helpers import qualified, quote_identifier

__all__ = [
    "rank_single_candidates",
    "analyze_composite_candidates",
    "count_distinct_combo",
]

_COMPOSITE_COL_LIMIT = 20
_HEURISTIC_COL_LIMIT = 8
_HEURISTIC_COMBO_LIMIT = 30


def count_distinct_combo(
    cursor: Any, schema: str, table: str, combo: tuple[str, ...]
) -> int:
    """COUNT der distinkten Wert-Kombinationen über *combo* (Aggregat-only)."""
    cols = ", ".join(quote_identifier(col) for col in combo)
    cursor.execute(
        f"SELECT COUNT(*) FROM (SELECT DISTINCT {cols} FROM {qualified(schema, table)})"
    )
    return int(cursor.fetchone()[0])


def _single_rank_key(item: dict) -> tuple:
    return (
        0 if item["exact"] else 1,
        -float(item["uniqueness_pct"]),
        float(item["null_pct"]),
        float(item.get("empty_pct") or 0.0),
        -int(item["distinct"]),
        str(item["column"]).lower(),
    )


def rank_single_candidates(stats: list[dict]) -> list[dict]:
    """Rangliste der Einzelspalten-PK-Kandidaten (Decimals werden ausgelassen)."""
    ranked = []
    for item in stats:
        if item.get("decimal_like"):
            continue
        exact = bool(item["pk_candidate"])
        reason = "Distinct = row count, no NULLs"
        if not exact:
            parts = [f"{item['uniqueness_pct']:.2f}% unique"]
            if item["null_pct"] > 0:
                parts.append(f"{item['null_pct']:.2f}% NULL")
            if item.get("empty_pct"):
                parts.append(f"{item['empty_pct']:.2f}% empty")
            reason = ", ".join(parts)
        ranked.append(
            {
                "column": item["column"],
                "data_type": item["data_type"],
                "exact": exact,
                "nulls": item["nulls"],
                "null_pct": item["null_pct"],
                "empty_count": item.get("empty_count"),
                "empty_pct": item.get("empty_pct") or 0.0,
                "distinct": item["distinct"],
                "uniqueness_pct": item["uniqueness_pct"],
                "rank_reason": reason,
            }
        )
    return sorted(ranked, key=_single_rank_key)


def analyze_composite_candidates(
    stats: list[dict],
    ranked_single: list[dict],
    cursor: Any,
    schema: str,
    table: str,
    max_cols: int = 3,
    on_progress: Any | None = None,
) -> tuple[list[tuple[str, ...]], list[dict], dict]:
    """Find exact and promising multi-column PK candidates.

    Liefert ``(exact_candidates, ranked_composites, search_meta)``. Behält die
    Meridian-Budgets bei (siehe Modul-Docstring).
    """
    empty_meta = {
        "max_width": max_cols,
        "eligible_columns": 0,
        "eligible_column_names": [],
        "full_search_skipped": False,
        "skip_reason": "",
        "heuristic_combo_count": 0,
    }
    if not stats:
        if on_progress:
            on_progress("Composite-Key-Suche: keine Spaltenstatistiken vorhanden.")
        return [], [], empty_meta

    total = int(stats[0]["total"])
    if total == 0:
        empty_meta["skip_reason"] = "No rows available."
        if on_progress:
            on_progress("Composite-Key-Suche: keine Zeilen vorhanden.")
        return [], [], empty_meta

    eligible_stats = [
        item
        for item in stats
        if item["nulls"] == 0 and not item["pk_candidate"] and not item.get("decimal_like")
    ]
    eligible_cols = [item["column"] for item in eligible_stats]
    exact_candidates: list[tuple[str, ...]] = []
    exact_seen: set[tuple[str, ...]] = set()
    ranked_composites: list[dict] = []
    distinct_cache: dict[tuple[str, ...], int] = {}
    full_search_skipped = False
    skip_reason = ""

    if len(eligible_cols) > _COMPOSITE_COL_LIMIT:
        full_search_skipped = True
        skip_reason = (
            f"Exact full search skipped: {len(eligible_cols)} null-free columns "
            f"(limit {_COMPOSITE_COL_LIMIT})."
        )
        if on_progress:
            on_progress(f"Composite-Key-Suche: exakte Vollsuche uebersprungen ({len(eligible_cols)} Kandidaten).")
    else:
        if on_progress:
            on_progress(f"Composite-Key-Suche: pruefe {len(eligible_cols)} nullfreie Spalten.")
        for width in range(2, max_cols + 1):
            for combo in combinations(eligible_cols, width):
                distinct = count_distinct_combo(cursor, schema, table, combo)
                distinct_cache[combo] = distinct
                if distinct == total and combo not in exact_seen:
                    exact_seen.add(combo)
                    exact_candidates.append(combo)

    non_exact_nullfree = [item for item in ranked_single if item["column"] in eligible_cols]
    heuristic_cols = [item["column"] for item in non_exact_nullfree[:_HEURISTIC_COL_LIMIT]]
    heuristic_combos: list[tuple[str, ...]] = []
    for width in range(2, max_cols + 1):
        for combo in combinations(heuristic_cols, width):
            heuristic_combos.append(combo)
            if len(heuristic_combos) >= _HEURISTIC_COMBO_LIMIT:
                break
        if len(heuristic_combos) >= _HEURISTIC_COMBO_LIMIT:
            break

    if on_progress:
        on_progress(f"Composite-Key-Suche: bewerte {len(heuristic_combos)} heuristische Kombinationen.")
    for combo in heuristic_combos:
        distinct = distinct_cache.get(combo)
        if distinct is None:
            distinct = count_distinct_combo(cursor, schema, table, combo)
            distinct_cache[combo] = distinct
        uniqueness_pct = round((distinct / total * 100) if total > 0 else 0.0, 2)
        exact = distinct == total
        if exact and combo not in exact_seen:
            exact_seen.add(combo)
            exact_candidates.append(combo)
        ranked_composites.append(
            {
                "columns": list(combo),
                "width": len(combo),
                "exact": exact,
                "distinct": distinct,
                "uniqueness_pct": uniqueness_pct,
                "rank_reason": "Distinct combinations = row count"
                if exact
                else f"{uniqueness_pct:.2f}% unique",
            }
        )

    ranked_composites.sort(
        key=lambda item: (
            0 if item["exact"] else 1,
            -float(item["uniqueness_pct"]),
            int(item["width"]),
            ",".join(item["columns"]).lower(),
        )
    )
    return exact_candidates, ranked_composites, {
        "max_width": max_cols,
        "eligible_columns": len(eligible_cols),
        "eligible_column_names": eligible_cols,
        "full_search_skipped": full_search_skipped,
        "skip_reason": skip_reason,
        "heuristic_combo_count": len(heuristic_combos),
    }
