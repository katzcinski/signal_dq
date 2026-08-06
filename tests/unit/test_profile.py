"""Tests für dq_core.profile (framework-free profiling/PK/heuristics).

Keine Live-DB: ein kleiner Fake-Cursor liefert kanonische Aggregat-Zeilen,
oder es wird db_connection.MockCursor genutzt. Alle Fixtures sind SYNTHETISCH
(erfundene Namen wie Sales_Orders / v_Demo) — keine Kundendaten.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from dq_core.connect import query_helpers as qh
from dq_core.connect.db_connection import MockCursor
from dq_core.profile import heuristics
from dq_core.profile.heuristics import (
    classify_view_context,
    score_single_candidate,
)
from dq_core.profile.pk_detection import (
    analyze_composite_candidates,
    rank_single_candidates,
)
from dq_core.profile.profiler import (
    _is_decimal,
    _is_numeric,
    _is_text,
    build_issues,
    build_profiling,
    profile_table,
)


# ---------------------------------------------------------------------------
# Fake-Cursor: kanonische Aggregat-Antworten je nach SQL-Form
# ---------------------------------------------------------------------------

class FakeCursor:
    """Minimaler Cursor-Stub.

    Erkennt die vom Profiler/PK-Detection erzeugten SQL-Formen anhand von
    Substrings und liefert vorbereitete Tuple-Zeilen zurück. ``description``
    wird passend gesetzt, damit query_helpers.query() dict rows bauen kann.
    """

    def __init__(self, columns, agg_row, profile_row=None, combo_distinct=None):
        self._columns = columns  # list[(COLUMN_NAME, DATA_TYPE_NAME, IS_NULLABLE, POSITION)]
        self._agg_row = agg_row
        self._profile_row = profile_row
        self._combo_distinct = combo_distinct or {}
        self.description: list = []
        self._rows: list = []
        self._scalar = None

    def execute(self, sql, params=None):
        text = " ".join(str(sql).split())
        upper = text.upper()
        if "SYS.TABLE_COLUMNS" in upper or "SYS.VIEW_COLUMNS" in upper:
            self.description = [
                ("COLUMN_NAME",),
                ("DATA_TYPE_NAME",),
                ("IS_NULLABLE",),
                ("POSITION",),
            ]
            self._rows = list(self._columns)
            self._scalar = None
        elif "SELECT DISTINCT" in upper:
            # COUNT(*) FROM (SELECT DISTINCT col, col FROM ...) — Composite-Probe
            inner = text.split("SELECT DISTINCT", 1)[1].split("FROM", 1)[0]
            combo = frozenset(
                c.strip().strip('"') for c in inner.split(",") if c.strip()
            )
            self._scalar = (self._combo_distinct.get(combo, 0),)
            self._rows = []
        elif upper.startswith("SELECT COUNT(*) AS R0") or " AS R0" in upper:
            # Pass 1: breite COUNT / COUNT(DISTINCT)-Aggregation
            self._scalar = self._agg_row
            self._rows = []
        else:
            # Pass 2: MIN/MAX/AVG/MEDIAN/empty-string
            self._scalar = self._profile_row
            self._rows = []

    def fetchone(self):
        if self._scalar is not None:
            row, self._scalar = self._scalar, None
            return row
        return self._rows.pop(0) if self._rows else None

    def fetchall(self):
        rows, self._rows = self._rows, []
        return rows

    def close(self):
        pass


# Synthetische Tabelle "v_Demo": ID (unique, no nulls), CUSTOMER_NAME (text,
# some nulls + empty), AMOUNT (decimal measure).
_DEMO_COLUMNS = [
    ("ID", "INTEGER", "FALSE", 1),
    ("CUSTOMER_NAME", "NVARCHAR", "TRUE", 2),
    ("AMOUNT", "DECIMAL", "TRUE", 3),
]
# Pass-1 row: r0=COUNT(*), then per column (COUNT, COUNT DISTINCT)
#   ID:            100 non-null, 100 distinct  -> unique, no nulls
#   CUSTOMER_NAME:  90 non-null,  80 distinct  -> 10 nulls
#   AMOUNT:        100 non-null,  55 distinct
_DEMO_AGG_ROW = (100, 100, 100, 90, 80, 100, 55)
# Pass-2 row order follows column order: numeric columns emit MIN/MAX/AVG/MEDIAN,
# text columns emit empty_count. ID is INTEGER (numeric) -> 4 values;
# CUSTOMER_NAME (text) -> empty_count; AMOUNT (numeric) -> 4 values.
_DEMO_PROFILE_ROW = (
    1, 100, Decimal("50.5"), Decimal("50.5"),   # ID min/max/avg/median
    5,                                           # CUSTOMER_NAME empty_count
    Decimal("1.50"), Decimal("999.00"),          # AMOUNT min/max
    Decimal("250.25"), Decimal("200.00"),        # AMOUNT avg/median
)


def _demo_cursor():
    return FakeCursor(_DEMO_COLUMNS, _DEMO_AGG_ROW, _DEMO_PROFILE_ROW)


# ---------------------------------------------------------------------------
# query_helpers
# ---------------------------------------------------------------------------

def test_jsonable_normalises_decimal_and_temporal():
    assert qh.jsonable(Decimal("5")) == 5
    assert isinstance(qh.jsonable(Decimal("5")), int)
    assert qh.jsonable(Decimal("2.5")) == 2.5
    assert qh.jsonable(date(2026, 6, 14)) == "2026-06-14"
    assert qh.jsonable(None) is None
    assert qh.jsonable(True) is True


def test_quote_identifier_escapes_and_qualifies():
    assert qh.quote_identifier("Sales_Orders") == '"Sales_Orders"'
    assert qh.quote_identifier('we"ird') == '"we""ird"'
    assert qh.qualified("MY_SPACE", "v_Demo") == '"MY_SPACE"."v_Demo"'
    with pytest.raises(ValueError):
        qh.quote_identifier("  ")


def test_query_zips_description_into_dict_rows():
    cur = MockCursor()
    rows = qh.query(cur, "SELECT 1 AS result FROM DUMMY")
    assert rows == [{"result": 0}]
    assert qh.query_one(MockCursor(), "SELECT 1 AS result FROM DUMMY") == {"result": 0}


def test_get_columns_uses_table_columns_then_view_fallback():
    cur = _demo_cursor()
    cols = qh.get_columns(cur, "MY_SPACE", "v_Demo")
    names = [c["name"] for c in cols]
    assert names == ["ID", "CUSTOMER_NAME", "AMOUNT"]
    assert cols[0]["data_type"] == "INTEGER"


# ---------------------------------------------------------------------------
# type classifiers
# ---------------------------------------------------------------------------

def test_type_classifiers():
    assert _is_text("NVARCHAR")
    assert _is_text("SHORTTEXT")
    assert not _is_text("INTEGER")
    assert _is_numeric("DECIMAL(15,2)")
    assert _is_numeric("BIGINT")
    assert not _is_numeric("NVARCHAR")
    assert _is_decimal("DECIMAL")
    assert _is_decimal("SMALLDECIMAL")
    assert not _is_decimal("INTEGER")


# ---------------------------------------------------------------------------
# profile_table
# ---------------------------------------------------------------------------

def test_profile_table_returns_null_distinct_uniqueness_stats():
    result = profile_table(_demo_cursor(), "MY_SPACE", "v_Demo")
    assert result["row_count"] == 100
    assert result["column_count"] == 3
    by_col = {c["column"]: c for c in result["columns"]}

    id_col = by_col["ID"]
    assert id_col["nulls"] == 0
    assert id_col["distinct"] == 100
    assert id_col["uniqueness_pct"] == 100.0
    assert id_col["pk_candidate"] is True

    name_col = by_col["CUSTOMER_NAME"]
    assert name_col["nulls"] == 10
    assert name_col["null_pct"] == 10.0
    assert name_col["distinct"] == 80
    assert name_col["pk_candidate"] is False
    assert name_col["empty_count"] == 5  # from pass-2

    amount_col = by_col["AMOUNT"]
    # decimal/measure column must never be flagged as a single PK candidate
    assert amount_col["pk_candidate"] is False
    assert amount_col["decimal_like"] is True
    assert amount_col["min"] == 1.5
    assert amount_col["max"] == 999.0


def test_profile_table_never_selects_raw_rows():
    """Sicherheitsposture: keine SELECT *-Statements; nur Aggregate."""
    executed: list[str] = []
    base = _demo_cursor()
    orig_execute = base.execute

    def recording(sql, params=None):
        executed.append(" ".join(str(sql).split()).upper())
        return orig_execute(sql, params)

    base.execute = recording  # type: ignore[assignment]
    profile_table(base, "MY_SPACE", "v_Demo")
    aggregate_scans = [s for s in executed if " FROM " in s and "SYS." not in s]
    assert aggregate_scans  # there were data-touching queries
    for sql in aggregate_scans:
        assert "SELECT *" not in sql
        assert "COUNT" in sql or "MIN" in sql or "DISTINCT" in sql


def test_build_issues_and_profiling():
    stats = profile_table(_demo_cursor(), "MY_SPACE", "v_Demo")["columns"]
    issues = build_issues(stats)
    assert any(i["column"] == "CUSTOMER_NAME" and i["type"] == "completeness" for i in issues)
    prof = build_profiling(stats)
    assert any(c["column"] == "CUSTOMER_NAME" for c in prof["empty_string_columns"])
    assert any(c["column"] == "AMOUNT" for c in prof["numeric_stats"])


# ---------------------------------------------------------------------------
# pk detection
# ---------------------------------------------------------------------------

def test_rank_single_flags_unique_non_null_column():
    stats = profile_table(_demo_cursor(), "MY_SPACE", "v_Demo")["columns"]
    ranked = rank_single_candidates(stats)
    # decimal AMOUNT must be excluded entirely
    assert all(r["column"] != "AMOUNT" for r in ranked)
    # the unique, null-free ID column ranks first and is flagged exact
    assert ranked[0]["column"] == "ID"
    assert ranked[0]["exact"] is True


def test_analyze_composite_candidates_finds_exact_combo():
    # Two non-unique, null-free text columns that are unique together.
    columns = [
        ("REGION", "NVARCHAR", "FALSE", 1),
        ("CITY", "NVARCHAR", "FALSE", 2),
    ]
    # 10 rows; REGION: 3 distinct, CITY: 6 distinct; (REGION,CITY) combo unique.
    agg_row = (10, 10, 3, 10, 6)
    profile_row = (0, 0)  # empty_count for both text cols
    combo_distinct = {frozenset(("REGION", "CITY")): 10}  # order-insensitive
    cur = FakeCursor(columns, agg_row, profile_row, combo_distinct)
    stats = profile_table(cur, "MY_SPACE", "Sales_Orders")["columns"]

    cur2 = FakeCursor(columns, agg_row, profile_row, combo_distinct)
    ranked_single = rank_single_candidates(stats)
    exact, ranked_comp, meta = analyze_composite_candidates(
        stats, ranked_single, cur2, "MY_SPACE", "Sales_Orders", max_cols=2
    )
    assert ("REGION", "CITY") in exact
    assert any(
        rc["exact"] and set(rc["columns"]) == {"REGION", "CITY"} for rc in ranked_comp
    )
    assert meta["eligible_columns"] == 2


# ---------------------------------------------------------------------------
# heuristics
# ---------------------------------------------------------------------------

def test_heuristics_score_id_above_amount():
    context = classify_view_context({"objectType": "views"}, "Sales_Orders")
    id_cand = {"column": "ORDER_ID", "data_type": "INTEGER", "exact": True,
               "uniqueness_pct": 100.0, "null_pct": 0.0}
    amount_cand = {"column": "NET_AMOUNT", "data_type": "DECIMAL", "exact": False,
                   "uniqueness_pct": 95.0, "null_pct": 0.0}
    scored_id = score_single_candidate(id_cand, context)
    scored_amount = score_single_candidate(amount_cand, context)
    assert scored_id["final_score"] > scored_amount["final_score"]
    # measure-like field is actively suppressed
    assert scored_amount["suppressed"] is True
    assert scored_id["suppressed"] is False


def test_enrich_result_with_context_reranks_and_suppresses_measures():
    result = {
        "view": "Sales_Orders",
        "columns": [
            {"column": "ORDER_ID", "null_pct": 0.0},
            {"column": "NET_AMOUNT", "null_pct": 0.0},
        ],
        "pk_candidates": {
            "ranked_single": [
                {"column": "NET_AMOUNT", "data_type": "DECIMAL", "exact": False,
                 "uniqueness_pct": 99.0, "null_pct": 0.0},
                {"column": "ORDER_ID", "data_type": "INTEGER", "exact": True,
                 "uniqueness_pct": 100.0, "null_pct": 0.0},
            ],
            "ranked_composite": [],
        },
        "issues": [],
    }
    enriched = heuristics.enrich_result_with_context(result)
    singles = enriched["pk_candidates"]["ranked_single"]
    # AMOUNT suppressed -> only ORDER_ID survives and leads
    assert [s["column"] for s in singles] == ["ORDER_ID"]
    assert enriched["scores"]["overall_key_confidence"] > 0
