"""Snapshot validation helpers for dq_core (framework-free, aggregate-only).

Ports the Meridian validator core into cursor-in/dict-out functions. The module
never returns raw rows: snapshot and cardinality functions expose aggregates,
and row diffs are counted by wrapping SQL ``EXCEPT`` in ``COUNT(*)``.
"""
from __future__ import annotations

from typing import Any

from dq_core.connect.query_helpers import (
    get_columns,
    jsonable,
    qualified,
    query_one,
    quote_identifier,
)

__all__ = [
    "gather_stats",
    "get_key_cardinality",
    "compare_snapshots",
    "diff_counts",
]

_NUMERIC_TYPES = {
    "BIGINT",
    "DEC",
    "DECIMAL",
    "DOUBLE",
    "FIXED",
    "FLOAT",
    "INT",
    "INTEGER",
    "NUMERIC",
    "REAL",
    "SMALLDECIMAL",
    "SMALLINT",
    "TINYINT",
}


def _is_numeric(data_type: Any) -> bool:
    kind = str(data_type or "").upper().strip()
    if not kind:
        return False
    return kind.split("(", 1)[0].strip() in _NUMERIC_TYPES


def _row_value(row: dict, key: str, default: Any = None) -> Any:
    if key in row:
        return row[key]
    upper = key.upper()
    if upper in row:
        return row[upper]
    lower = key.lower()
    if lower in row:
        return row[lower]
    return default


def _to_int(value: Any, default: int = 0) -> int:
    value = jsonable(value)
    if value is None:
        return default
    return int(value)


def _to_float(value: Any) -> float | None:
    value = jsonable(value)
    if value is None:
        return None
    return float(value)


def _column_name(column: dict) -> str | None:
    return column.get("name") or column.get("COLUMN_NAME") or column.get("column")


def _column_type(column: dict) -> str:
    return str(column.get("data_type") or column.get("DATA_TYPE_NAME") or "UNKNOWN")


def gather_stats(
    cursor: Any,
    schema: str,
    table: str,
    key_columns: list[str] | None = None,
    include_minmax: bool = True,
) -> dict:
    """Collect row and per-column aggregate stats for ``schema.table``.

    The result is snapshot-shaped and contains row count, null counts/rates,
    distinct counts, and numeric min/max values. Top values are deliberately
    omitted because they can expose real data values.
    """
    keys = list(key_columns or [])
    columns = [
        {"name": name, "data_type": _column_type(col)}
        for col in get_columns(cursor, schema, table)
        if (name := _column_name(col))
    ]

    parts = ["COUNT(*) AS ROW_COUNT"]
    metric_aliases: dict[str, dict[str, str]] = {}
    for idx, col in enumerate(columns):
        name = col["name"]
        quoted = quote_identifier(name)
        aliases = {
            "nonnull": f"C{idx}_NONNULL",
            "distinct": f"C{idx}_DISTINCT",
        }
        parts.append(f"COUNT({quoted}) AS {aliases['nonnull']}")
        parts.append(f"COUNT(DISTINCT {quoted}) AS {aliases['distinct']}")
        if include_minmax and _is_numeric(col["data_type"]):
            aliases["min"] = f"C{idx}_MIN"
            aliases["max"] = f"C{idx}_MAX"
            parts.append(f"MIN({quoted}) AS {aliases['min']}")
            parts.append(f"MAX({quoted}) AS {aliases['max']}")
        metric_aliases[name] = aliases

    row = query_one(cursor, f"SELECT {', '.join(parts)} FROM {qualified(schema, table)}") or {}
    row_count = _to_int(_row_value(row, "ROW_COUNT"))

    column_stats: dict[str, dict] = {}
    for col in columns:
        name = col["name"]
        aliases = metric_aliases[name]
        non_null = _to_int(_row_value(row, aliases["nonnull"]))
        distinct = _to_int(_row_value(row, aliases["distinct"]))
        null_count = row_count - non_null
        stat: dict[str, Any] = {
            "data_type": col["data_type"],
            "null_count": null_count,
            "null_rate": round(null_count / row_count, 6) if row_count else 0.0,
            "distinct_count": distinct,
        }
        if "min" in aliases:
            stat["min_value"] = jsonable(_row_value(row, aliases["min"]))
            stat["max_value"] = jsonable(_row_value(row, aliases["max"]))
        column_stats[name] = stat

    return {
        "meta": {"schema": schema, "table": table},
        "row_count": row_count,
        "key_columns": keys,
        "key_stats": get_key_cardinality(cursor, schema, table, keys, row_count) if keys else {},
        "columns": column_stats,
    }


def get_key_cardinality(
    cursor: Any,
    schema: str,
    table: str,
    key_columns: list[str],
    row_count: int | None = None,
) -> dict:
    """Return aggregate key cardinality for one or more key columns."""
    keys = list(key_columns or [])
    if not keys:
        raise ValueError("key_columns must contain at least one column")

    table_ref = qualified(schema, table)
    if row_count is None:
        row = query_one(cursor, f"SELECT COUNT(*) AS ROW_COUNT FROM {table_ref}") or {}
        row_count = _to_int(_row_value(row, "ROW_COUNT"))

    key_expr = ", ".join(quote_identifier(key) for key in keys)
    row = query_one(
        cursor,
        f"SELECT COUNT(*) AS DISTINCT_KEYS "
        f"FROM (SELECT DISTINCT {key_expr} FROM {table_ref}) KEY_DISTINCT",
    ) or {}
    distinct = _to_int(_row_value(row, "DISTINCT_KEYS"))
    duplicate_rows = row_count - distinct

    return {
        "key_columns": keys,
        "distinct_key_count": distinct,
        "duplicate_row_count": duplicate_rows,
        "uniqueness_percent": round(distinct / row_count * 100, 2) if row_count else 0.0,
    }


def _snapshot_columns(snapshot: dict) -> dict[str, dict]:
    columns = snapshot.get("columns") or {}
    if isinstance(columns, dict):
        return {str(name): dict(stats or {}) for name, stats in columns.items()}
    if isinstance(columns, list):
        mapped: dict[str, dict] = {}
        for item in columns:
            if not isinstance(item, dict):
                continue
            name = _column_name(item)
            if name:
                mapped[str(name)] = dict(item)
        return mapped
    return {}


def _null_rate(stats: dict, row_count: int) -> float | None:
    value = _to_float(stats.get("null_rate"))
    if value is not None:
        return value
    value = _to_float(stats.get("null_pct"))
    if value is not None:
        return value / 100
    if "null_count" in stats and row_count:
        return _to_int(stats.get("null_count")) / row_count
    if "nulls" in stats and row_count:
        return _to_int(stats.get("nulls")) / row_count
    return None


def _distinct_count(stats: dict) -> int | None:
    if "distinct_count" in stats:
        return _to_int(stats.get("distinct_count"))
    if "distinct" in stats:
        return _to_int(stats.get("distinct"))
    return None


def _metric_delta(left: float | int | None, right: float | int | None) -> float | int | None:
    if left is None or right is None:
        return None
    return right - left


def compare_snapshots(left: dict, right: dict, fanout_threshold: float = 1.05) -> dict:
    """Compare two aggregate snapshots without touching the database."""
    left_rows = _to_int(left.get("row_count"))
    right_rows = _to_int(right.get("row_count"))
    row_ratio = (right_rows / left_rows) if left_rows else None
    fanout_detected = right_rows > 0 if row_ratio is None else row_ratio > fanout_threshold

    left_columns = _snapshot_columns(left)
    right_columns = _snapshot_columns(right)
    only_left = sorted(set(left_columns) - set(right_columns))
    only_right = sorted(set(right_columns) - set(left_columns))

    shared_column_deltas: list[dict] = []
    highlights: list[dict] = []
    for column in sorted(set(left_columns) & set(right_columns)):
        left_stats = left_columns[column]
        right_stats = right_columns[column]
        left_null_rate = _null_rate(left_stats, left_rows)
        right_null_rate = _null_rate(right_stats, right_rows)
        null_delta = _metric_delta(left_null_rate, right_null_rate)
        if isinstance(null_delta, float):
            null_delta = round(null_delta, 6)

        left_distinct = _distinct_count(left_stats)
        right_distinct = _distinct_count(right_stats)
        distinct_delta = _metric_delta(left_distinct, right_distinct)

        null_changed = null_delta not in (None, 0)
        distinct_changed = distinct_delta not in (None, 0)
        delta = {
            "column": column,
            "null_rate_left": left_null_rate,
            "null_rate_right": right_null_rate,
            "null_rate_delta": null_delta,
            "distinct_count_left": left_distinct,
            "distinct_count_right": right_distinct,
            "distinct_count_delta": distinct_delta,
            "null_rate_changed": null_changed,
            "distinct_count_changed": distinct_changed,
        }
        shared_column_deltas.append(delta)

        if null_changed:
            highlights.append(
                {
                    "column": column,
                    "metric": "null_rate",
                    "left": left_null_rate,
                    "right": right_null_rate,
                    "delta": null_delta,
                }
            )
        if distinct_changed:
            highlights.append(
                {
                    "column": column,
                    "metric": "distinct_count",
                    "left": left_distinct,
                    "right": right_distinct,
                    "delta": distinct_delta,
                }
            )

    return {
        "row_count_left": left_rows,
        "row_count_right": right_rows,
        "row_delta": right_rows - left_rows,
        "row_ratio": round(row_ratio, 6) if row_ratio is not None else None,
        "fanout_threshold": fanout_threshold,
        "fanout_detected": fanout_detected,
        "columns_only_in_left": only_left,
        "columns_only_in_right": only_right,
        "shared_column_deltas": shared_column_deltas,
        "highlights": highlights,
    }


def _strip_identifier_quotes(value: str) -> str:
    text = value.strip()
    if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
        return text[1:-1].replace('""', '"')
    return text


def _resolve_table_ref(ref: Any) -> str:
    if isinstance(ref, dict):
        schema = ref.get("schema") or ref.get("space")
        table = ref.get("table") or ref.get("name")
        if schema and table:
            return qualified(str(schema), str(table))
    if isinstance(ref, (tuple, list)) and len(ref) == 2:
        return qualified(str(ref[0]), str(ref[1]))
    if isinstance(ref, str):
        parts = ref.split(".", 1)
        if len(parts) == 2 and all(part.strip() for part in parts):
            return qualified(
                _strip_identifier_quotes(parts[0]),
                _strip_identifier_quotes(parts[1]),
            )
    raise ValueError(
        "table refs must be (schema, table), {'schema','table'}, or 'SCHEMA.TABLE'"
    )


def _direction_flags(direction: str) -> tuple[bool, bool]:
    normalised = str(direction or "").strip().lower().replace("_", "-")
    left = normalised in {"both", "left", "left-not-right", "a-not-b"}
    right = normalised in {"both", "right", "right-not-left", "b-not-a"}
    if not left and not right:
        raise ValueError("direction must be 'both', 'left-not-right', or 'right-not-left'")
    return left, right


def _except_count(cursor: Any, source: str, target: str, columns: list[str]) -> int:
    col_expr = ", ".join(quote_identifier(column) for column in columns)
    sql = (
        "SELECT COUNT(*) AS DIFF_COUNT "
        f"FROM (SELECT {col_expr} FROM {source} "
        f"EXCEPT SELECT {col_expr} FROM {target}) DIFF_ROWS"
    )
    row = query_one(cursor, sql) or {}
    return _to_int(_row_value(row, "DIFF_COUNT"))


def diff_counts(
    cursor: Any,
    left_ref: Any,
    right_ref: Any,
    columns: list[str],
    direction: str = "both",
) -> dict:
    """Count set differences between two table refs using SQL ``EXCEPT``.

    The function returns counts only; it never selects or returns the differing
    rows themselves.
    """
    selected_columns = [
        str(column).strip()
        for column in (columns or [])
        if str(column).strip()
    ]
    if not selected_columns:
        raise ValueError("columns must contain at least one column")

    left_table = _resolve_table_ref(left_ref)
    right_table = _resolve_table_ref(right_ref)
    run_left, run_right = _direction_flags(direction)

    return {
        "left_not_right_count": _except_count(cursor, left_table, right_table, selected_columns)
        if run_left
        else None,
        "right_not_left_count": _except_count(cursor, right_table, left_table, selected_columns)
        if run_right
        else None,
    }
