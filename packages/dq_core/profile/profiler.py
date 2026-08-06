"""Spalten-Profiling (framework-free, aggregate-only).

Server-seitiges Profiling einer Tabelle/View über genau zwei aggregierte
Pässe — es verlassen **niemals** Roh-Datenzeilen die DB (kein ``SELECT *``):

  1. Ein breiter Pass: ``COUNT(*)`` + pro Spalte ``COUNT``/``COUNT(DISTINCT)``.
  2. Ein zweiter Pass (nur falls nötig): MIN/MAX/AVG/MEDIAN für numerische und
     Leerstring-Zählung (``LENGTH(TRIM())=0``) für Text-Spalten.

Portiert aus datasphere-tools analyze_view.py — argparse/pandas/licensing
entfernt; nimmt einen DB-Cursor entgegen, öffnet nie selbst Verbindungen.
"""
from __future__ import annotations

from typing import Any

from dq_core.connect.query_helpers import get_columns, jsonable, qualified, quote_identifier

__all__ = [
    "profile_table",
    "build_profiling",
    "build_issues",
]

# Maximale Spaltenzahl pro Profiling-Lauf — schützt vor zu breiten Tabellen
# (Statement-Größe / Round-Trip-Kosten). Caller kann via columns= selbst kürzen.
_MAX_COLUMNS = 500

_SKIP_TYPES = {"BLOB", "CLOB", "NCLOB", "VARBINARY"}
_TEXT_TYPES = {"ALPHANUM", "CHAR", "NCHAR", "NVARCHAR", "SHORTTEXT", "TEXT", "VARCHAR"}
_NUMERIC_TYPES = {
    "BIGINT",
    "DEC",
    "DECIMAL",
    "DOUBLE",
    "FLOAT",
    "FIXED",
    "INT",
    "INTEGER",
    "NUMERIC",
    "REAL",
    "SMALLDECIMAL",
    "SMALLINT",
    "TINYINT",
}
_DECIMAL_TYPES = {"DEC", "DECIMAL", "FIXED", "NUMERIC", "SMALLDECIMAL"}


# ---------------------------------------------------------------------------
# Typ-Klassifizierer
# ---------------------------------------------------------------------------

def _is_text(data_type: str) -> bool:
    kind = str(data_type or "").upper()
    return kind in _TEXT_TYPES or "CHAR" in kind or kind.endswith("TEXT")


def _is_numeric(data_type: str) -> bool:
    kind = str(data_type or "").upper().strip()
    if not kind:
        return False
    base = kind.split("(", 1)[0].strip()
    return base in _NUMERIC_TYPES


def _is_decimal(data_type: str) -> bool:
    kind = str(data_type or "").upper().strip()
    if not kind:
        return False
    base = kind.split("(", 1)[0].strip()
    return base in _DECIMAL_TYPES


def _round_number(value: Any, digits: int = 2) -> Any:
    value = jsonable(value)
    if value is None:
        return None
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return value


# ---------------------------------------------------------------------------
# Spaltenauswahl
# ---------------------------------------------------------------------------

def _resolve_columns(
    cursor: Any, schema: str, table: str, columns: list[dict] | None
) -> list[dict]:
    """Liefert ``[{name, data_type}]`` der profilbaren Spalten.

    Akzeptiert eine vorgegebene Spaltenliste (Keys ``name`` + ``data_type``
    oder Katalog-Form ``COLUMN_NAME``/``DATA_TYPE_NAME``) oder zieht sie aus dem
    SYS-Katalog. BLOB/CLOB & Co. werden ausgelassen, Anzahl wird gekappt.
    """
    if columns is None:
        raw = get_columns(cursor, schema, table)
    else:
        raw = columns

    resolved: list[dict] = []
    for col in raw:
        name = col.get("name") if "name" in col else col.get("COLUMN_NAME")
        data_type = col.get("data_type") if "data_type" in col else col.get("DATA_TYPE_NAME")
        if not name:
            continue
        if str(data_type or "").upper() in _SKIP_TYPES:
            continue
        resolved.append({"name": name, "data_type": data_type or "UNKNOWN"})

    return resolved[:_MAX_COLUMNS]


# ---------------------------------------------------------------------------
# Profiling-Kern
# ---------------------------------------------------------------------------

def profile_table(
    cursor: Any,
    schema: str,
    table: str,
    columns: list[dict] | None = None,
    on_progress: Any | None = None,
) -> dict:
    """Profile *schema.table* in zwei Aggregat-Pässen und liefere ein Result-Dict.

    Result-Form (analyze_view-kompatibel)::

        {schema, table, row_count, column_count, columns:[...],
         pk_candidates:{single,...}, profiling:{...}, issues:[...]}

    Jede Spalte: ``column, data_type, total, nulls, null_pct, distinct,
    uniqueness_pct, pk_candidate, text_like, numeric_like, decimal_like,
    empty_count, empty_pct, min, max, avg, median``.

    Es wird nie ``SELECT *`` ausgeführt — ausschließlich Aggregate.
    """
    if on_progress:
        on_progress("Profiling: Spalten werden aufgeloest ...")
    cols = _resolve_columns(cursor, schema, table, columns)

    if not cols:
        if on_progress:
            on_progress("Profiling: keine profilierbaren Spalten gefunden.")
        return {
            "schema": schema,
            "table": table,
            "row_count": 0,
            "column_count": 0,
            "columns": [],
            "pk_candidates": {"single": []},
            "profiling": {"empty_string_columns": [], "numeric_stats": []},
            "issues": [],
        }

    qt = qualified(schema, table)

    # --- Pass 1: COUNT(*) + pro Spalte COUNT / COUNT(DISTINCT) ---------------
    if on_progress:
        on_progress(f"Profiling: Pass 1/2 fuer {len(cols)} Spalten ...")
    parts = ["COUNT(*) AS r0"]
    for i, col in enumerate(cols):
        qc = quote_identifier(col["name"])
        parts.append(f"COUNT({qc}) AS r{1 + i * 2}")
        parts.append(f"COUNT(DISTINCT {qc}) AS r{2 + i * 2}")
    cursor.execute(f"SELECT {', '.join(parts)} FROM {qt}")
    row = cursor.fetchone() or []

    total = int(row[0]) if row else 0
    results: list[dict] = []
    for i, col in enumerate(cols):
        non_null = int(row[1 + i * 2]) if row else 0
        distinct = int(row[2 + i * 2]) if row else 0
        nulls = total - non_null
        null_pct = round((nulls / total * 100) if total > 0 else 0.0, 2)
        uniq_pct = round((distinct / total * 100) if total > 0 else 0.0, 2)
        data_type = col["data_type"]
        results.append(
            {
                "column": col["name"],
                "data_type": data_type,
                "total": total,
                "nulls": nulls,
                "null_pct": null_pct,
                "distinct": distinct,
                "uniqueness_pct": uniq_pct,
                "pk_candidate": nulls == 0
                and distinct == total
                and total > 0
                and not _is_decimal(data_type),
                "text_like": _is_text(data_type),
                "numeric_like": _is_numeric(data_type),
                "decimal_like": _is_decimal(data_type),
            }
        )

    # --- Pass 2: MIN/MAX/AVG/MEDIAN (numerisch) + Leerstring (Text) ---------
    if on_progress:
        on_progress("Profiling: Pass 2/2 fuer Detailstatistiken ...")
    profile_parts: list[str] = []
    profile_map: list[tuple[str, str]] = []
    for col in cols:
        qc = quote_identifier(col["name"])
        data_type = col["data_type"]
        if _is_text(data_type):
            profile_parts.append(
                f"SUM(CASE WHEN {qc} IS NOT NULL AND LENGTH(TRIM({qc})) = 0 THEN 1 ELSE 0 END)"
            )
            profile_map.append((col["name"], "empty_count"))
        if _is_numeric(data_type):
            profile_parts.extend([f"MIN({qc})", f"MAX({qc})", f"AVG({qc})", f"MEDIAN({qc})"])
            profile_map.extend(
                [
                    (col["name"], "min"),
                    (col["name"], "max"),
                    (col["name"], "avg"),
                    (col["name"], "median"),
                ]
            )

    extras_by_column: dict[str, dict] = {}
    if profile_parts and total > 0:
        cursor.execute(f"SELECT {', '.join(profile_parts)} FROM {qt}")
        extra_row = cursor.fetchone() or []
        for idx, (column_name, metric_name) in enumerate(profile_map):
            extras_by_column.setdefault(column_name, {})[metric_name] = jsonable(
                extra_row[idx] if idx < len(extra_row) else None
            )

    for item in results:
        extras = extras_by_column.get(item["column"], {})
        if item["text_like"]:
            empty_count = int(extras.get("empty_count") or 0)
            item["empty_count"] = empty_count
            item["empty_pct"] = round((empty_count / total * 100) if total > 0 else 0.0, 2)
        else:
            item["empty_count"] = None
            item["empty_pct"] = None
        item["min"] = _round_number(extras.get("min"))
        item["max"] = _round_number(extras.get("max"))
        item["avg"] = _round_number(extras.get("avg"))
        item["median"] = _round_number(extras.get("median"))

    if on_progress:
        on_progress("Profiling: Statistiken berechnet.")
    return {
        "schema": schema,
        "table": table,
        "row_count": total,
        "column_count": len(results),
        "columns": results,
        "pk_candidates": {"single": [it["column"] for it in results if it["pk_candidate"]]},
        "profiling": build_profiling(results),
        "issues": build_issues(results),
    }


# ---------------------------------------------------------------------------
# Abgeleitete Sichten
# ---------------------------------------------------------------------------

def build_issues(stats: list[dict]) -> list[dict]:
    """Completeness-Issues: Spalten mit NULL-Anteil > 0."""
    issues = []
    for item in stats:
        total = int(item["total"])
        if item["null_pct"] > 0:
            issues.append(
                {
                    "column": item["column"],
                    "type": "completeness",
                    "detail": f"{item['null_pct']:.1f}% NULLs ({item['nulls']}/{total} rows)",
                }
            )
    return issues


def build_profiling(stats: list[dict]) -> dict:
    """Aggregiere Leerstring-Spalten + numerische Statistiken für die UI."""
    empty_string_columns = []
    numeric_stats = []
    for item in stats:
        if item.get("text_like"):
            empty_string_columns.append(
                {
                    "column": item["column"],
                    "empty_count": item.get("empty_count") or 0,
                    "empty_pct": item.get("empty_pct") or 0.0,
                }
            )
        if item.get("numeric_like"):
            numeric_stats.append(
                {
                    "column": item["column"],
                    "min": item.get("min"),
                    "max": item.get("max"),
                    "avg": item.get("avg"),
                    "median": item.get("median"),
                }
            )
    return {
        "empty_string_columns": sorted(
            empty_string_columns,
            key=lambda item: (-float(item["empty_pct"]), item["column"].lower()),
        ),
        "numeric_stats": numeric_stats,
    }
