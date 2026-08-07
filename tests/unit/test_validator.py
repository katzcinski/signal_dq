"""Tests for dq_core.validator counts-only snapshot helpers."""
from __future__ import annotations

from decimal import Decimal

from dq_core.validator import (
    compare_snapshots,
    diff_counts,
    gather_stats,
    get_key_cardinality,
)


class ValidatorCursor:
    def __init__(self):
        self.description: list = []
        self._rows: list = []
        self.executed: list[str] = []

    def execute(self, sql, params=None):
        text = " ".join(str(sql).split())
        upper = text.upper()
        self.executed.append(upper)

        if "SYS.TABLE_COLUMNS" in upper:
            self.description = [
                ("COLUMN_NAME",),
                ("DATA_TYPE_NAME",),
                ("IS_NULLABLE",),
                ("POSITION",),
            ]
            self._rows = [
                ("ID", "INTEGER", "FALSE", 1),
                ("REGION", "NVARCHAR", "TRUE", 2),
                ("AMOUNT", "DECIMAL", "TRUE", 3),
            ]
            return

        if "SYS.VIEW_COLUMNS" in upper:
            self.description = [
                ("COLUMN_NAME",),
                ("DATA_TYPE_NAME",),
                ("IS_NULLABLE",),
                ("POSITION",),
            ]
            self._rows = []
            return

        if "SELECT COUNT(*) AS ROW_COUNT" in upper and "COUNT(DISTINCT" in upper:
            self.description = [
                ("ROW_COUNT",),
                ("C0_NONNULL",),
                ("C0_DISTINCT",),
                ("C0_MIN",),
                ("C0_MAX",),
                ("C1_NONNULL",),
                ("C1_DISTINCT",),
                ("C2_NONNULL",),
                ("C2_DISTINCT",),
                ("C2_MIN",),
                ("C2_MAX",),
            ]
            self._rows = [(100, 100, 100, 1, 100, 90, 30, 95, 50, Decimal("1.50"), Decimal("99.99"))]
            return

        if "SELECT COUNT(*) AS ROW_COUNT" in upper:
            self.description = [("ROW_COUNT",)]
            self._rows = [(100,)]
            return

        if "SELECT COUNT(*) AS DISTINCT_KEYS" in upper:
            self.description = [("DISTINCT_KEYS",)]
            self._rows = [(97,)]
            return

        if "SELECT COUNT(*) AS DIFF_COUNT" in upper:
            self.description = [("DIFF_COUNT",)]
            self._rows = [(3 if '"LEFT_TABLE"' in upper and '"RIGHT_TABLE"' in upper else 4,)]
            return

        raise AssertionError(f"Unexpected SQL: {text}")

    def fetchall(self):
        rows, self._rows = self._rows, []
        return rows


def test_gather_stats_returns_aggregates_without_top_values_or_raw_rows():
    cur = ValidatorCursor()
    stats = gather_stats(cur, "MY_SPACE", "Sales_Orders", key_columns=["ID"])

    assert stats["row_count"] == 100
    assert stats["key_stats"] == {
        "key_columns": ["ID"],
        "distinct_key_count": 97,
        "duplicate_row_count": 3,
        "uniqueness_percent": 97.0,
    }

    columns = stats["columns"]
    assert columns["REGION"]["null_count"] == 10
    assert columns["REGION"]["null_rate"] == 0.1
    assert columns["REGION"]["distinct_count"] == 30
    assert "top_values" not in columns["REGION"]
    assert "min_value" not in columns["REGION"]

    assert columns["AMOUNT"]["min_value"] == 1.5
    assert columns["AMOUNT"]["max_value"] == 99.99
    assert all("SELECT *" not in sql for sql in cur.executed)


def test_get_key_cardinality_fetches_row_count_when_not_supplied():
    cur = ValidatorCursor()
    result = get_key_cardinality(cur, "MY_SPACE", "Sales_Orders", ["ID"])

    assert result["distinct_key_count"] == 97
    assert result["duplicate_row_count"] == 3
    assert result["uniqueness_percent"] == 97.0
    assert "OCCURRENCES" not in result
    assert all("GROUP BY" not in sql for sql in cur.executed)


def test_compare_snapshots_reports_row_column_and_metric_deltas():
    left = {
        "row_count": 100,
        "columns": {
            "ID": {"null_rate": 0.0, "distinct_count": 100},
            "REGION": {"null_rate": 0.1, "distinct_count": 30},
            "LEGACY": {"null_rate": 0.0, "distinct_count": 2},
        },
    }
    right = {
        "row_count": 120,
        "columns": {
            "ID": {"null_rate": 0.0, "distinct_count": 120},
            "REGION": {"null_rate": 0.2, "distinct_count": 31},
            "NEW_COL": {"null_rate": 1.0, "distinct_count": 0},
        },
    }

    result = compare_snapshots(left, right)

    assert result["row_count_left"] == 100
    assert result["row_count_right"] == 120
    assert result["row_delta"] == 20
    assert result["row_ratio"] == 1.2
    assert result["fanout_detected"] is True
    assert result["columns_only_in_left"] == ["LEGACY"]
    assert result["columns_only_in_right"] == ["NEW_COL"]

    by_column = {item["column"]: item for item in result["shared_column_deltas"]}
    assert by_column["REGION"]["null_rate_delta"] == 0.1
    assert by_column["REGION"]["distinct_count_delta"] == 1
    assert {"column": "REGION", "metric": "null_rate", "left": 0.1, "right": 0.2, "delta": 0.1} in result["highlights"]
    assert {"column": "ID", "metric": "distinct_count", "left": 100, "right": 120, "delta": 20} in result["highlights"]


def test_diff_counts_wraps_except_in_count_and_returns_no_rows():
    cur = ValidatorCursor()
    result = diff_counts(
        cur,
        ("MY_SPACE", "LEFT_TABLE"),
        ("MY_SPACE", "RIGHT_TABLE"),
        ["ID", "REGION"],
    )

    assert result == {"left_not_right_count": 3, "right_not_left_count": 3}
    diff_sql = [sql for sql in cur.executed if "EXCEPT" in sql]
    assert len(diff_sql) == 2
    assert all(sql.startswith("SELECT COUNT(*) AS DIFF_COUNT") for sql in diff_sql)
    assert all("FETCH FIRST" not in sql for sql in diff_sql)
