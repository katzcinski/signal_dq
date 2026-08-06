"""Column-level lineage extraction from SQL text via sqlglot.

Parses SQL view definitions to produce ``projectionLineage``-compatible
entries — the same format ``_csn_reconstructor.extract_query_details``
produces for graphical views. This lets ``_column_lineage.py`` treat
SQL views identically to CSN-based views.

Optional dependency — degrades gracefully when sqlglot is not installed.
Install: ``pip install sqlglot>=25.0``
"""

from __future__ import annotations

import logging
from typing import Any

LOGGER = logging.getLogger(__name__)

try:
    import sqlglot
    from sqlglot import exp

    HAS_SQLGLOT = True
except ImportError:
    HAS_SQLGLOT = False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_sql_column_lineage(
    sql: str,
    target_object: str,
    known_sources: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Parse SQL and return projectionLineage-compatible entries.

    Args:
        sql:             Raw SQL text of the view.
        target_object:   Technical name of the view being parsed.
        known_sources:   Optional list of already-known source objects
                         (from lineageSources) — helps disambiguate bare
                         table names vs aliases.

    Returns:
        List of dicts matching CSN projectionLineage format::

            [{"output": str, "sourceRef": str, "expression": str,
              "alias": str, "unsupported": bool, "nullableSource": False}]

        Empty list if parsing fails or sqlglot is unavailable.
    """
    if not HAS_SQLGLOT or not sql or not sql.strip():
        return []
    try:
        return _parse(sql, target_object, known_sources or [])
    except Exception:
        LOGGER.debug("sqlglot parse failed for %s", target_object, exc_info=True)
        return []


# ---------------------------------------------------------------------------
# Internal parsing
# ---------------------------------------------------------------------------

def _parse(
    sql: str,
    target_object: str,
    known_sources: list[str],
) -> list[dict[str, Any]]:
    """Core parse routine — may raise on malformed SQL."""
    # Generic dialect — sqlglot has no HANA dialect but standard SQL
    # parsing covers the patterns found in Datasphere SQL views.
    parsed = sqlglot.parse_one(sql)

    # For UNION, parse only the first branch's columns (pragmatic).
    is_union = isinstance(parsed, exp.Union)
    select = parsed.find(exp.Select)
    if select is None:
        return []

    if is_union:
        # Use tables from the first branch for column resolution,
        # but collect all tables for the alias map (multi-source lineage).
        first_tables = list(select.find_all(exp.Table))
        all_tables = list(parsed.find_all(exp.Table))
        alias_map = _build_alias_map(all_tables, known_sources)
        # For bare columns in a UNION's first branch, prefer the first
        # branch's sole source if it has exactly one table.
        union_sole = (
            _table_full_name(first_tables[0])
            if len(first_tables) == 1 else None
        )
    else:
        all_tables = list(parsed.find_all(exp.Table))
        alias_map = _build_alias_map(all_tables, known_sources)
        union_sole = None

    results: list[dict[str, Any]] = []
    effective_sources = known_sources if not union_sole else [union_sole]

    for col_expr in select.expressions:
        entry = _resolve_column_expr(col_expr, alias_map, effective_sources)
        results.append(entry)

    return results


def _build_alias_map(
    tables: list[Any],
    known_sources: list[str],
) -> dict[str, str]:
    """Map SQL aliases to fully-qualified source object names.

    Datasphere SQL uses dotted table names like ``"H.H_BOM_V"`` which
    sqlglot parses as a single identifier (not schema.table). We keep
    the full dotted name as the source identifier.
    """
    alias_map: dict[str, str] = {}
    bare_names: list[str] = []

    for table in tables:
        full_name = _table_full_name(table)
        if not full_name:
            continue
        alias = table.alias or full_name
        alias_map[alias] = full_name
        if not table.alias:
            bare_names.append(full_name)

    # Cross-reference known_sources for tables that might appear with a
    # schema prefix in the inventory but without one in SQL (or vice versa).
    known_short = {s.rsplit(".", 1)[-1]: s for s in known_sources}
    for alias, full in list(alias_map.items()):
        short = full.rsplit(".", 1)[-1]
        if short in known_short and full != known_short[short]:
            alias_map[alias] = known_short[short]

    return alias_map


def _table_full_name(table: Any) -> str:
    """Extract the full table name, preserving dots."""
    # sqlglot may split "H.H_BOM_V" into db="H" name="H_BOM_V"
    # or keep it as one identifier depending on quoting.
    parts: list[str] = []
    if table.catalog:
        parts.append(table.catalog)
    if table.db:
        parts.append(table.db)
    if table.name:
        parts.append(table.name)
    return ".".join(parts) if parts else ""


def _resolve_column_expr(
    col_expr: Any,
    alias_map: dict[str, str],
    known_sources: list[str],
) -> dict[str, Any]:
    """Resolve one SELECT expression into a projectionLineage entry."""
    # Determine output name (alias or inferred column name).
    output_name = _infer_output_name(col_expr)

    # Unwrap Alias to get the actual expression.
    inner = col_expr.this if isinstance(col_expr, exp.Alias) else col_expr

    # Case 1: Simple column reference — direct mapping.
    if isinstance(inner, exp.Column):
        source_ref = _resolve_column_ref(inner, alias_map, known_sources)
        return _entry(output_name, source_ref, expression="", unsupported=not source_ref)

    # Case 2: Star — can't resolve column-level lineage.
    if isinstance(inner, exp.Star):
        return _entry(output_name or "*", "", expression="", unsupported=True)

    # Case 3: Literal value — no source dependency.
    if isinstance(inner, exp.Literal):
        return _entry(output_name, "", expression=inner.sql(), unsupported=False)

    # Case 4: Expression (function, CASE, arithmetic, etc.)
    # Find all column references in the expression tree.
    col_refs = _extract_all_column_refs(inner, alias_map, known_sources)
    expression_sql = inner.sql()

    if col_refs:
        # Use the first column as the primary sourceRef; all are tracked
        # via the expression text. For CASE/COALESCE/arithmetic, all
        # referenced columns contribute to the output.
        primary_ref = col_refs[0]
        return _entry(
            output_name,
            primary_ref,
            expression=expression_sql,
            unsupported=False,
            all_source_refs=col_refs,
        )

    # Expression with no column refs (e.g., CURRENT_TIMESTAMP).
    return _entry(output_name, "", expression=expression_sql, unsupported=False)


def _infer_output_name(col_expr: Any) -> str:
    """Get the output column name from an expression."""
    if isinstance(col_expr, exp.Alias):
        return col_expr.alias
    if isinstance(col_expr, exp.Column):
        return col_expr.name
    return ""


def _resolve_column_ref(
    column: Any,
    alias_map: dict[str, str],
    known_sources: list[str],
) -> str:
    """Resolve a single Column node to ``fully_qualified_object.column``."""
    col_name = column.name
    table_alias = column.table or ""

    if table_alias and table_alias in alias_map:
        return f"{alias_map[table_alias]}.{col_name}"

    # Bare column, no table qualifier — resolve via sole source.
    if not table_alias:
        if len(alias_map) == 1:
            sole_source = next(iter(alias_map.values()))
            return f"{sole_source}.{col_name}"
        if len(known_sources) == 1:
            return f"{known_sources[0]}.{col_name}"

    # Table alias that didn't resolve — keep as-is for downstream fallback.
    if table_alias:
        return f"{table_alias}.{col_name}"

    return col_name


def _extract_all_column_refs(
    node: Any,
    alias_map: dict[str, str],
    known_sources: list[str],
) -> list[str]:
    """Extract all resolved column references from an expression tree.

    Handles CASE, arithmetic, functions, COALESCE, etc. — any nested
    Column node gets resolved.  Returns deduplicated list preserving order.
    """
    refs: list[str] = []
    seen: set[str] = set()
    for col in node.find_all(exp.Column):
        ref = _resolve_column_ref(col, alias_map, known_sources)
        if ref and ref not in seen:
            refs.append(ref)
            seen.add(ref)
    return refs


# ---------------------------------------------------------------------------
# Entry builder
# ---------------------------------------------------------------------------

def _entry(
    output: str,
    source_ref: str,
    *,
    expression: str = "",
    unsupported: bool = False,
    all_source_refs: list[str] | None = None,
) -> dict[str, Any]:
    """Build a projectionLineage-compatible dict."""
    d: dict[str, Any] = {
        "output": output,
        "sourceRef": source_ref,
        "expression": expression,
        "alias": output,
        "unsupported": unsupported,
        "nullableSource": False,
    }
    if all_source_refs and len(all_source_refs) > 1:
        d["allSourceRefs"] = all_source_refs
    return d


__all__ = ["HAS_SQLGLOT", "extract_sql_column_lineage"]
