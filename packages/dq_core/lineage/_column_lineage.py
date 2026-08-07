"""Cross-object column lineage built from CSN projection data.

Walks the object-level lineage graph and resolves per-object
``projectionLineage`` entries (output → sourceRef) into fully-qualified
column-to-column edges across object boundaries.

Phase 2 addition: when an object has no CSN projectionLineage but does
have raw SQL text, the ``_sql_column_parser`` module (optional, requires
``sqlglot``) is used to extract column-level lineage from the SQL.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

LOGGER = logging.getLogger(__name__)

# Object types that are expected to carry column-level derivation. Raw/source
# objects (local/remote tables, replicated Data Products, flows) are leaves with
# no upstream to map, so including them dilutes the headline coverage ratio.
DERIVED_TYPES = frozenset({"views", "analytic-models", "transformation-flows"})


@dataclass
class ColumnEdge:
    source_object: str
    source_column: str
    target_object: str
    target_column: str
    edge_type: str  # "direct", "computed", "passthrough"
    expression: str = ""


@dataclass
class ColumnLineageResult:
    edges: list[ColumnEdge]
    coverage: dict[str, Any]
    unmapped_objects: list[str]

    def serialize(self) -> dict[str, Any]:
        return {
            "columnEdges": [
                {
                    "source": e.source_object,
                    "sourceColumn": e.source_column,
                    "target": e.target_object,
                    "targetColumn": e.target_column,
                    "edgeType": e.edge_type,
                    "expression": e.expression,
                }
                for e in self.edges
            ],
            "columnEdgeMeta": {
                "totalEdges": len(self.edges),
                "coverage": self.coverage,
                "unmappedObjects": self.unmapped_objects,
            },
        }


_ALIAS_COL_RE = re.compile(r"^([A-Za-z_][\w.]*)\.([A-Za-z_]\w*)$")
_REF_RE = re.compile(r"\b([A-Za-z_][\w.]*)\.([A-Za-z_]\w*)\b")


def _derive_alias_map(csn: dict[str, Any]) -> dict[str, str]:
    """Reconstruct alias→source from querySources + joinDetails (fallback)."""
    alias_map: dict[str, str] = {}
    query_sources: list[str] = csn.get("querySources") or []
    for qs in query_sources:
        short = qs.rsplit(".", 1)[-1] if "." in qs else qs
        alias_map[short] = qs
    for jd in csn.get("joinDetails") or []:
        source_refs: list[str] = jd.get("sourceRefs") or []
        for alias in jd.get("rightAliases") or []:
            for sr in source_refs:
                short = sr.rsplit(".", 1)[-1] if "." in sr else sr
                if alias == short or len(source_refs) == 1:
                    alias_map[alias] = sr
        for alias in jd.get("leftAliases") or []:
            for sr in source_refs:
                short = sr.rsplit(".", 1)[-1] if "." in sr else sr
                if alias == short:
                    alias_map[alias] = sr
    return alias_map


def _resolve_source_ref(
    source_ref: str,
    alias_map: dict[str, str],
    sole_source: str | None = None,
) -> tuple[str, str] | None:
    """Resolve ``alias.Column`` or bare ``Column`` to ``(object, column)``."""
    ref = source_ref.strip()
    m = _ALIAS_COL_RE.match(ref)
    if m:
        alias, column = m.group(1), m.group(2)
        obj = alias_map.get(alias)
        if obj:
            return obj, column
        return None
    if sole_source and ref and "." not in ref:
        return sole_source, ref
    return None


def _extract_expression_refs(
    expression: str,
    alias_map: dict[str, str],
) -> list[tuple[str, str]]:
    """Extract all ``(object, column)`` references from an expression string."""
    refs: list[tuple[str, str]] = []
    for m in _REF_RE.finditer(expression):
        alias, column = m.group(1), m.group(2)
        obj = alias_map.get(alias)
        if obj:
            refs.append((obj, column))
    return refs


def _try_sql_column_lineage(
    sql: str,
    target_object: str,
    known_sources: list[str],
) -> list[ColumnEdge]:
    """Attempt sqlglot-based column lineage. Returns [] on failure or missing dep."""
    try:
        from ._sql_column_parser import extract_sql_column_lineage
    except ImportError:
        try:
            from _sql_column_parser import extract_sql_column_lineage
        except ImportError:
            return []

    entries = extract_sql_column_lineage(sql, target_object, known_sources)
    result: list[ColumnEdge] = []
    for entry in entries:
        output = entry.get("output") or ""
        if not output or entry.get("unsupported"):
            continue

        source_ref = entry.get("sourceRef") or ""
        expression = entry.get("expression") or ""
        all_refs = entry.get("allSourceRefs") or []
        edge_type = "computed" if expression else "direct"

        # allSourceRefs: for expressions referencing multiple source columns
        # (e.g., CASE, arithmetic), emit an edge per source column.
        if all_refs and expression:
            for ref in all_refs:
                obj, col = _split_qualified_ref(ref, known_sources)
                if obj and col:
                    result.append(ColumnEdge(
                        source_object=obj,
                        source_column=col,
                        target_object=target_object,
                        target_column=output,
                        edge_type="computed",
                        expression=expression,
                    ))
        elif source_ref:
            obj, col = _split_qualified_ref(source_ref, known_sources)
            if obj and col:
                result.append(ColumnEdge(
                    source_object=obj,
                    source_column=col,
                    target_object=target_object,
                    target_column=output,
                    edge_type=edge_type,
                    expression=expression,
                ))

    return result


def _split_qualified_ref(
    ref: str,
    known_sources: list[str],
) -> tuple[str, str]:
    """Split ``object.column`` into ``(object, column)``.

    Handles dotted object names like ``H.H_BOM_V.ColName`` by matching
    against known_sources to find the right split point.
    """
    if not ref or "." not in ref:
        return "", ref

    # Try matching against known sources (longest match wins).
    for src in sorted(known_sources, key=len, reverse=True):
        if ref.startswith(src + "."):
            col = ref[len(src) + 1:]
            if col:
                return src, col

    # Fallback: last dot separates object from column.
    parts = ref.rsplit(".", 1)
    return parts[0], parts[1]


def build_column_lineage(inventory: list[dict[str, Any]]) -> ColumnLineageResult:
    """Build cross-object column edges from inventory projection data."""
    edges: list[ColumnEdge] = []
    mapped_count = 0
    unmapped_count = 0
    unmapped_objects: list[str] = []

    for obj in inventory:
        tech_name = obj.get("technicalName", "")
        csn = obj.get("csnProjection") or {}
        proj_lineage: list[dict[str, Any]] = csn.get("projectionLineage") or []
        alias_map: dict[str, str] = csn.get("aliasMap") or {}
        if not alias_map:
            alias_map = _derive_alias_map(csn)

        if not proj_lineage:
            # Phase 2: try sqlglot-based parsing for SQL views.
            sql_text = obj.get("sql") or ""
            lineage_sources = obj.get("lineageSources") or []
            if sql_text:
                sql_edges = _try_sql_column_lineage(
                    sql_text, tech_name, lineage_sources,
                )
                if sql_edges:
                    edges.extend(sql_edges)
                    mapped_count += len({e.target_column for e in sql_edges})
                    continue

            col_count = obj.get("columnCount") or len(obj.get("columns") or [])
            if col_count > 0:
                unmapped_count += col_count
                unmapped_objects.append(tech_name)
            continue

        query_sources = csn.get("querySources") or []
        sole_source = query_sources[0] if len(query_sources) == 1 else None

        for entry in proj_lineage:
            output_col = entry.get("output") or entry.get("alias") or ""
            source_ref = entry.get("sourceRef") or ""
            expression = entry.get("expression") or ""

            if not output_col:
                continue

            # Structured derived refs from the CSN walker take precedence over
            # the fragile regex-over-rendered-SQL path. One edge per source col.
            all_refs = entry.get("allSourceRefs") or []
            if all_refs:
                emitted = False
                edge_type = "computed" if expression else "direct"
                for ref in all_refs:
                    src_obj, src_col = _split_qualified_ref(ref, query_sources)
                    if src_obj and src_col:
                        edges.append(ColumnEdge(
                            source_object=src_obj,
                            source_column=src_col,
                            target_object=tech_name,
                            target_column=output_col,
                            edge_type=edge_type,
                            expression=expression,
                        ))
                        emitted = True
                if emitted:
                    mapped_count += 1
                    continue

            if source_ref and not expression:
                resolved = _resolve_source_ref(source_ref, alias_map, sole_source)
                if resolved:
                    edges.append(ColumnEdge(
                        source_object=resolved[0],
                        source_column=resolved[1],
                        target_object=tech_name,
                        target_column=output_col,
                        edge_type="direct",
                    ))
                    mapped_count += 1
                else:
                    unmapped_count += 1
            elif expression:
                expr_refs = _extract_expression_refs(expression, alias_map)
                if expr_refs:
                    for src_obj, src_col in expr_refs:
                        edges.append(ColumnEdge(
                            source_object=src_obj,
                            source_column=src_col,
                            target_object=tech_name,
                            target_column=output_col,
                            edge_type="computed",
                            expression=expression,
                        ))
                    mapped_count += 1
                else:
                    if source_ref:
                        resolved = _resolve_source_ref(source_ref, alias_map, sole_source)
                        if resolved:
                            edges.append(ColumnEdge(
                                source_object=resolved[0],
                                source_column=resolved[1],
                                target_object=tech_name,
                                target_column=output_col,
                                edge_type="computed",
                                expression=expression,
                            ))
                            mapped_count += 1
                            continue
                    unmapped_count += 1
            else:
                unmapped_count += 1

    total = mapped_count + unmapped_count

    # Derived-only coverage: for each derived-type object, how many of its
    # columns receive at least one upstream edge. This excludes raw/source
    # leaves whose columns can never be "mapped", giving a fairer headline.
    mapped_cols_by_obj: dict[str, set[str]] = {}
    for e in edges:
        mapped_cols_by_obj.setdefault(e.target_object, set()).add(e.target_column)
    derived_mapped = 0
    derived_unmapped = 0
    for obj in inventory:
        if obj.get("objectType") not in DERIVED_TYPES:
            continue
        name = obj.get("technicalName", "")
        total_cols = obj.get("columnCount") or len(obj.get("columns") or [])
        mapped_here = len(mapped_cols_by_obj.get(name, set()))
        derived_mapped += min(mapped_here, total_cols)
        derived_unmapped += max(0, total_cols - mapped_here)
    derived_total = derived_mapped + derived_unmapped

    return ColumnLineageResult(
        edges=edges,
        coverage={
            "mapped": mapped_count,
            "unmapped": unmapped_count,
            "ratio": round(mapped_count / total, 2) if total else 0.0,
            "derived": {
                "mapped": derived_mapped,
                "unmapped": derived_unmapped,
                "ratio": round(derived_mapped / derived_total, 2) if derived_total else 0.0,
            },
        },
        unmapped_objects=sorted(set(unmapped_objects)),
    )


def build_column_indexes(
    result: ColumnLineageResult,
) -> dict[str, dict[str, list[dict[str, str]]]]:
    """Build per-object column lineage indexes for API lookups.

    Returns ``{object_id: {column_name: {"upstream": [...], "downstream": [...]}}}``
    """
    idx: dict[str, dict[str, dict[str, list[dict[str, str]]]]] = {}

    for e in result.edges:
        tgt = idx.setdefault(e.target_object, {})
        tgt_col = tgt.setdefault(e.target_column, {"upstream": [], "downstream": []})
        tgt_col["upstream"].append({
            "object": e.source_object,
            "column": e.source_column,
            "edgeType": e.edge_type,
            "expression": e.expression,
        })

        src = idx.setdefault(e.source_object, {})
        src_col = src.setdefault(e.source_column, {"upstream": [], "downstream": []})
        src_col["downstream"].append({
            "object": e.target_object,
            "column": e.target_column,
            "edgeType": e.edge_type,
        })

    return idx
