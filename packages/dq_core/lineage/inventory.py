"""Inventory-object assembly + object-level lineage graph (pure, framework-free).

Ported from the Meridian (datasphere-tools) inventory engine, keeping ONLY the
pure transforms Signal needs:

  * :func:`build_inventory_object` — assemble one ``INVOBJ`` (per the locked
    output schema) from a raw CSN object definition. Reuses
    :func:`extract_query_details` / :func:`build_sql_reconstruction` from
    ``_csn_reconstructor`` for the projection lineage / SQL reconstruction, and
    stamps layer / layerCode / role / confidence via a :class:`NamingModel`.
  * :func:`build_lineage_graph` — build the object-level ``{nodes, edges,
    adjacency, upstream}`` graph (including external out-of-inventory source
    nodes), matching the locked lineage schema.

No I/O, no CLI, no third-party imports (stdlib + the already-ported pure
lineage helpers only). Column-level edges are NOT produced here — the
integrator merges ``build_column_lineage(objects).serialize()`` separately.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

try:  # package mode
    from ._csn_reconstructor import (
        build_sql_reconstruction,
        extract_key_pairs,
        extract_query_details,
    )
    from ._semantics import (
        SCHEMA_VERSION,
        QUNIS_DEFAULT,
        NamingModel,
        parse_external_source,
        sql_fingerprint,
    )
except ImportError:  # script mode (no package context)
    from _csn_reconstructor import (  # type: ignore[no-redef]
        build_sql_reconstruction,
        extract_key_pairs,
        extract_query_details,
    )
    from _semantics import (  # type: ignore[no-redef]
        SCHEMA_VERSION,
        QUNIS_DEFAULT,
        NamingModel,
        parse_external_source,
        sql_fingerprint,
    )

# Object types where we expect a query/SQL definition → reconstruct + project.
SQL_BEARING_TYPES = frozenset({"views", "analytic-models", "transformation-flows"})

# Object types treated as graphical when no raw SQL is present.
_GRAPHICAL_VIEW_TYPES = frozenset({"views"})


# ---------------------------------------------------------------------------
# CSN navigation helpers (pure)
# ---------------------------------------------------------------------------

def _primary_definition(
    raw_def: dict[str, Any],
    technical_name: str | None = None,
) -> tuple[str | None, dict[str, Any] | None]:
    """Return ``(definition_name, definition_dict)`` for the primary CSN entity.

    Accepts either a full ``{"definitions": {...}}`` payload or a bare
    definition dict (already unwrapped). Tolerant of missing keys.
    """
    if not isinstance(raw_def, dict):
        return None, None

    definitions = raw_def.get("definitions")
    if not isinstance(definitions, dict):
        # Already a bare definition (has elements/query/kind) — use as-is.
        if any(k in raw_def for k in ("elements", "query", "kind")):
            return technical_name, raw_def
        return None, None

    if technical_name:
        exact = definitions.get(technical_name)
        if isinstance(exact, dict):
            return technical_name, exact
        upper = definitions.get(technical_name.upper())
        if isinstance(upper, dict):
            return technical_name.upper(), upper
        wanted = technical_name.casefold()
        for name, obj_def in definitions.items():
            if str(name).casefold() == wanted and isinstance(obj_def, dict):
                return str(name), obj_def
    for name, obj_def in definitions.items():
        if isinstance(obj_def, dict) and obj_def.get("kind") == "entity":
            return str(name), obj_def
    for name, obj_def in definitions.items():
        if isinstance(obj_def, dict):
            return str(name), obj_def
    return None, None


def _annotation_value(value: Any) -> str:
    if isinstance(value, dict):
        if value.get("#"):
            return str(value["#"])
        if value.get("="):
            return str(value["="])
    return str(value) if value is not None else ""


def _ref_name(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, dict):
        ref = value.get("ref")
        if isinstance(ref, list) and ref:
            parts: list[str] = []
            for part in ref:
                if isinstance(part, dict):
                    seg = part.get("id") or part.get("name") or part.get("target")
                    if seg:
                        parts.append(str(seg))
                elif str(part):
                    parts.append(str(part))
            if parts:
                return ".".join(parts)
        for key in ("name", "technicalName", "id", "target"):
            if value.get(key):
                return str(value[key])
    return None


def _format_association_ref(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        if isinstance(value.get("ref"), list):
            return ".".join(str(part) for part in value["ref"])
        for key in ("name", "id", "targetElement", "foreignKey", "sourceElement"):
            if value.get(key):
                return str(value[key])
    return str(value)


def _format_association_condition(elem: dict[str, Any]) -> str:
    """Best-effort rendering of an association ON/key condition from CSN."""
    for key in ("on", "onCondition", "condition"):
        value = elem.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, list) and value:
            return " ".join(_format_association_ref(part) for part in value)

    keys = elem.get("keys") or elem.get("foreignKeys")
    if isinstance(keys, list) and keys:
        return ", ".join(_format_association_ref(key) for key in keys)
    if isinstance(keys, dict) and keys:
        return ", ".join(f"{k} -> {_format_association_ref(v)}" for k, v in keys.items())
    return ""


def _association_key_pairs(
    name: str,
    elem: dict[str, Any],
    target: str | None = None,
) -> tuple[list[dict[str, str]], list[str]]:
    """Return ``(keyPairs, targetKeyColumns)`` for an association element."""
    on = elem.get("on") or elem.get("onCondition") or elem.get("condition")
    pairs: list[dict[str, str]] = []
    target_cols: list[str] = []
    target_short = (target or "").rsplit(".", 1)[-1]
    prefixes = {p for p in (name, target_short) if p}

    if isinstance(on, (list, dict)):
        pairs = extract_key_pairs(on)
        for pair in pairs:
            for side in (pair.get("left", ""), pair.get("right", "")):
                parts = side.split(".")
                if len(parts) >= 2 and parts[0] in prefixes:
                    target_cols.append(parts[-1])

    if not target_cols:
        keys = elem.get("keys") or elem.get("foreignKeys")
        if isinstance(keys, list):
            for key in keys:
                if isinstance(key, dict):
                    ref = key.get("ref") or key.get("targetElement")
                    if isinstance(ref, list) and ref:
                        target_cols.append(str(ref[-1]))
                    elif isinstance(ref, str) and ref:
                        target_cols.append(ref.split(".")[-1])
                elif isinstance(key, str) and key:
                    target_cols.append(key.split(".")[-1])
        elif isinstance(keys, dict):
            for value in keys.values():
                target_cols.append(_format_association_ref(value).split(".")[-1])

    return pairs, list(dict.fromkeys(col for col in target_cols if col))


# ---------------------------------------------------------------------------
# Column / CSN-projection extraction
# ---------------------------------------------------------------------------

def _extract_columns(obj_def: dict[str, Any]) -> list[dict[str, Any]]:
    """Flat ``columns`` list (INVOBJ top-level shape) from CSN ``elements``."""
    elements = (obj_def or {}).get("elements") or {}
    columns: list[dict[str, Any]] = []
    if isinstance(elements, dict):
        for name, meta in elements.items():
            if not isinstance(meta, dict):
                continue
            if meta.get("type") in ("cds.Association", "cds.Composition"):
                continue
            columns.append({
                "name": str(name),
                "type": str(meta.get("type") or ""),
                "key": str(meta.get("key", "")) if meta.get("key") is not None else "",
                "nullable": "",
                "businessName": str(meta.get("@EndUserText.label", "")),
            })
    return columns


def _build_csn_projection(
    obj_def: dict[str, Any] | None,
    definition_name: str | None,
    sql_text: str,
    reconstruction: dict[str, Any] | None,
) -> dict[str, Any]:
    """Assemble ``csnProjection`` exactly per the locked schema.

    Reuses :func:`extract_query_details` for projectionLineage / aliasMap /
    joinDetails / querySources; everything else is derived from the CSN
    ``elements`` and entity-level annotations.
    """
    obj_def = obj_def if isinstance(obj_def, dict) else {}
    elements = obj_def.get("elements") or {}
    columns: list[dict[str, Any]] = []
    associations: list[dict[str, Any]] = []
    association_roles: dict[str, dict[str, list[str]]] = defaultdict(
        lambda: {"foreignKeyColumns": [], "textColumns": []}
    )
    if isinstance(elements, dict):
        for name, meta in elements.items():
            if not isinstance(meta, dict):
                continue
            if meta.get("type") in ("cds.Association", "cds.Composition"):
                assoc_pairs, assoc_target_cols = _association_key_pairs(
                    str(name), meta, _ref_name(meta.get("target")),
                )
                associations.append({
                    "name": name,
                    "target": meta.get("target"),
                    "condition": _format_association_condition(meta),
                    "keyPairs": assoc_pairs,
                    "targetKeyColumns": assoc_target_cols,
                })
                continue
            fk_assoc = _annotation_value(meta.get("@ObjectModel.foreignKey.association"))
            text_assoc = _annotation_value(meta.get("@ObjectModel.text.association"))
            if fk_assoc:
                association_roles[fk_assoc]["foreignKeyColumns"].append(str(name))
            if text_assoc:
                association_roles[text_assoc]["textColumns"].append(str(name))
            columns.append({
                "name": name,
                "type": meta.get("type"),
                "length": meta.get("length"),
                "precision": meta.get("precision"),
                "scale": meta.get("scale"),
                "key": bool(meta.get("key")),
                "notNull": bool(meta.get("notNull")),
                "label": meta.get("@EndUserText.label", ""),
                "defaultAggregation": _annotation_value(meta.get("@Aggregation.default")),
                "measureType": _annotation_value(meta.get("@AnalyticsDetails.measureType")),
                "foreignKeyAssociation": fk_assoc,
                "textAssociation": text_assoc,
            })

    select = ((obj_def.get("query") or {}).get("SELECT") or {})
    query_source = _ref_name(select.get("from")) if isinstance(select, dict) else None
    query_details = extract_query_details(obj_def)
    query_sources = list(dict.fromkeys(
        source
        for detail in query_details.get("joinDetails", [])
        for source in (detail.get("sourceRefs") or [])
    ))
    if query_source:
        query_sources = list(dict.fromkeys([query_source, *query_sources]))

    mixin_targets: list[str] = []
    if isinstance(select, dict) and isinstance(select.get("mixin"), dict):
        for mixin_def in select["mixin"].values():
            if isinstance(mixin_def, dict):
                target = _ref_name(mixin_def.get("target"))
                if target:
                    mixin_targets.append(target)

    modeling_pattern = _annotation_value(obj_def.get("@ObjectModel.modelingPattern"))
    data_category = (
        _annotation_value(obj_def.get("@Semantics.dataCategory"))
        or _annotation_value(obj_def.get("@Analytics.dataCategory"))
        or _annotation_value(obj_def.get("@DataWarehouse.dataCategory"))
        or _annotation_value(obj_def.get("dataCategory"))
        or ("FACT" if modeling_pattern == "ANALYTICAL_FACT" else "")
    )

    association_manifest: list[dict[str, Any]] = []
    for assoc in associations:
        roles = association_roles.get(str(assoc.get("name") or ""), {})
        association_manifest.append({
            **assoc,
            "foreignKeyColumns": roles.get("foreignKeyColumns", []),
            "textColumns": roles.get("textColumns", []),
        })

    return {
        "definition": definition_name,
        "kind": obj_def.get("kind"),
        "dataCategory": data_category,
        "modelingPattern": modeling_pattern,
        "keyColumns": [c["name"] for c in columns if c.get("key")],
        "columns": columns,
        "associations": associations,
        "associationManifest": association_manifest,
        "querySource": query_source,
        "querySources": query_sources,
        "joinDetails": query_details.get("joinDetails", []),
        "projectionLineage": query_details.get("projectionLineage", []),
        "aliasMap": query_details.get("aliasMap", {}),
        "mixinTargets": list(dict.fromkeys(mixin_targets)),
        "sqlSize": len(sql_text or ""),
        "sqlFingerprint": sql_fingerprint(sql_text),
        "sqlReconstructionStatus": (reconstruction or {}).get("status", "not_applicable"),
    }


# ---------------------------------------------------------------------------
# Object-level lineage-edge extraction from CSN (pure)
# ---------------------------------------------------------------------------

def _extract_csn_query_lineage(obj_def: dict[str, Any], self_name: str) -> list[dict[str, str]]:
    """Structured CSN SELECT/mixin references (FROM / JOIN / association mixins)."""
    refs: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    if not isinstance(obj_def, dict):
        return refs

    def add_ref(name: str | None, conn_type: str) -> None:
        if not name or name == self_name:
            return
        key = (name, conn_type)
        if key in seen:
            return
        seen.add(key)
        refs.append({"name": name, "type": conn_type})

    def walk_from(value: Any, conn_type: str) -> None:
        if not isinstance(value, dict):
            return
        if isinstance(value.get("ref"), list):
            add_ref(_ref_name(value), conn_type)
            return
        nested = ((value.get("SELECT") or {}).get("from") or None)
        if isinstance(nested, dict):
            walk_from(nested, conn_type)
        args = value.get("args") or []
        if isinstance(args, list):
            for idx, arg in enumerate(args):
                walk_from(arg, "select" if idx == 0 else "join")

    select = ((obj_def.get("query") or {}).get("SELECT") or {})
    if not isinstance(select, dict):
        return refs
    walk_from(select.get("from"), "select")
    mixin = select.get("mixin") or {}
    if isinstance(mixin, dict):
        for mixin_name, mixin_def in mixin.items():
            if not isinstance(mixin_def, dict):
                continue
            target = _ref_name(mixin_def.get("target"))
            if target and target != self_name:
                refs.append({
                    "name": target,
                    "type": "association",
                    "associationName": str(mixin_name),
                    "targetEntity": target,
                    "joinCondition": _format_association_condition(mixin_def),
                })
    return refs


def _extract_csn_associations(obj_def: dict[str, Any], self_name: str) -> list[dict[str, str]]:
    """cds.Association / cds.Composition targets declared on entity elements."""
    refs: list[dict[str, str]] = []
    seen: set[str] = set()
    if not isinstance(obj_def, dict):
        return refs
    elements = obj_def.get("elements") or {}
    if not isinstance(elements, dict):
        return refs
    for assoc_name, elem in elements.items():
        if not isinstance(elem, dict):
            continue
        if elem.get("type") in ("cds.Association", "cds.Composition"):
            target = str(elem.get("target") or "").strip()
            condition = _format_association_condition(elem)
            seen_key = f"{assoc_name}|{target}|{condition}"
            if target and target != self_name and seen_key not in seen:
                seen.add(seen_key)
                refs.append({
                    "name": target,
                    "type": "association",
                    "associationName": str(assoc_name),
                    "targetEntity": target,
                    "joinCondition": condition,
                })
    return refs


def _dedupe_lineage_edges(edges: list[dict[str, str]]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for edge in edges:
        key = (
            str(edge.get("name") or ""),
            str(edge.get("type") or "select"),
            str(edge.get("associationName") or ""),
        )
        if not key[0] or key in seen:
            continue
        seen.add(key)
        out.append(edge)
    return out


# ---------------------------------------------------------------------------
# Public: per-object assembly
# ---------------------------------------------------------------------------

def build_inventory_object(
    raw_def: dict[str, Any],
    *,
    technical_name: str,
    object_type: str,
    status: str,
    space: str,
    sql: str = "",
    business_name: str = "",
    semantic_usage: str = "",
    naming: NamingModel | None = None,
) -> dict[str, Any]:
    """Assemble ONE ``INVOBJ`` from a raw CSN object definition.

    ``raw_def`` may be a full ``{"definitions": {...}}`` payload or a bare
    definition dict. Missing keys yield safe defaults — this never raises on
    odd CSN. Reuses ``extract_query_details`` (csnProjection lineage) and
    ``build_sql_reconstruction`` (sqlReconstruction); stamps layer / layerCode
    / role / confidence via the naming model (defaults to QUNIS_DEFAULT).
    """
    model = naming or QUNIS_DEFAULT
    raw_def = raw_def if isinstance(raw_def, dict) else {}
    sql = sql or ""

    definition_name, obj_def = _primary_definition(raw_def, technical_name)
    obj_def = obj_def if isinstance(obj_def, dict) else {}

    columns = _extract_columns(obj_def)

    # --- SQL reconstruction (only meaningful for query-bearing objects). ---
    sql_reconstruction: dict[str, Any] = {
        "available": False,
        "status": "not_applicable",
        "sql": "",
        "warnings": [],
        "source": "csn.query.SELECT",
    }
    if object_type in SQL_BEARING_TYPES and not sql:
        sql_reconstruction = build_sql_reconstruction(
            definition_name or technical_name, obj_def,
        )

    csn_projection = _build_csn_projection(
        obj_def, definition_name, sql, sql_reconstruction,
    )

    # --- Object-level lineage edges from CSN. ---
    lineage_edges: list[dict[str, str]] = []
    if object_type in SQL_BEARING_TYPES:
        lineage_edges += _extract_csn_query_lineage(obj_def, technical_name)
    lineage_edges += _extract_csn_associations(obj_def, technical_name)
    lineage_edges = _dedupe_lineage_edges(lineage_edges)

    # --- Semantics stamp. ---
    layer, layer_code = model.match_layer(technical_name)
    role = model.derive_role(technical_name, object_type, semantic_usage or None)
    confidence = model.derive_confidence(
        technical_name, object_type, semantic_usage or None, layer, role,
    )

    sql_found = bool(sql)
    is_graphical = object_type in _GRAPHICAL_VIEW_TYPES and not sql_found

    record: dict[str, Any] = {
        "space": space,
        "objectType": object_type,
        "kind": str(raw_def.get("kind") or obj_def.get("kind") or object_type),
        "technicalName": technical_name,
        "businessName": business_name,
        "semanticUsage": semantic_usage,
        "status": status,
        "columnCount": len(columns),
        "columns": columns,
        "sqlFound": sql_found,
        "sqlPath": "",
        "sql": sql,
        "sqlReconstruction": sql_reconstruction,
        "sqlReconstructionAvailable": bool(sql_reconstruction.get("available")),
        "sqlReconstructionStatus": str(sql_reconstruction.get("status") or "not_applicable"),
        "sqlReconstructionWarningCount": len(sql_reconstruction.get("warnings") or []),
        "csnProjection": csn_projection,
        "analyticModel": {},
        "dataAccessControl": {},
        "appliedDataAccessControls": [],
        "flowLineage": {},
        "lineageEdges": lineage_edges,
        "lineageSources": [e["name"] for e in lineage_edges],
        "error": None,
        "layer": layer,
        "layerCode": layer_code,
        "role": role,
        "isGraphical": is_graphical,
        "sqlSize": len(sql),
        "sqlFingerprintExact": sql_fingerprint(sql),
        "confidence": confidence,
    }
    return record


# ---------------------------------------------------------------------------
# Public: object-level lineage graph
# ---------------------------------------------------------------------------

def _split_qualified_source(source: str) -> tuple[str | None, str]:
    """Return ``(qualifier, leaf_name)`` for a simple ``schema.object`` ref."""
    if "." not in source:
        return None, source
    qualifier, leaf = source.rsplit(".", 1)
    if not qualifier or not leaf:
        return None, source
    return qualifier, leaf


def _resolve_graph_source(
    source: str,
    target_obj: dict[str, Any],
    known: set[str],
) -> tuple[str, dict[str, str]]:
    """Map local space-qualified refs (``SPACE.name``) back to technical names."""
    if source in known:
        return source, {}
    qualifier, leaf = _split_qualified_source(source)
    space = str(target_obj.get("space") or "").strip()
    if qualifier and space and qualifier.casefold() == space.casefold() and leaf in known:
        return leaf, {"sourceReference": source, "sourceQualifier": qualifier}
    return source, {}


def build_lineage_graph(objects: list[dict[str, Any]]) -> dict[str, Any]:
    """Build the object-level lineage graph from assembled INVOBJ records.

    Returns ``{meta, nodes, edges, adjacency, upstream}`` matching the locked
    lineage schema. External (out-of-inventory) source nodes are added for
    ``external_system`` references the way Meridian does. Column-level edges are
    NOT added here — the integrator merges ``build_column_lineage().serialize()``.
    """
    known = {obj["technicalName"] for obj in objects}
    edges: list[dict[str, Any]] = []
    adjacency: dict[str, list[str]] = defaultdict(list)
    upstream: dict[str, list[str]] = defaultdict(list)
    external_nodes: dict[str, dict[str, Any]] = {}

    def add_edge(edge: dict[str, Any]) -> None:
        source = str(edge.get("source") or "")
        target = str(edge.get("target") or "")
        if not source or not target:
            return
        edges.append(edge)
        adjacency[source].append(target)
        upstream[target].append(source)

    def add_external_node(
        node_id: str,
        *,
        system: str,
        external_key: str,
        source_reference: str = "",
    ) -> None:
        if node_id in known or node_id in external_nodes:
            return
        external_nodes[node_id] = {
            "id": node_id,
            "businessName": source_reference or external_key or node_id,
            "technicalName": source_reference or external_key or node_id,
            "type": "external",
            "status": "External",
            "layer": "external",
            "layerCode": "ext",
            "role": "source",
            "confidence": 0.9,
            "columns": [],
            "columnCount": 0,
            "system": system,
            "externalKey": external_key,
        }

    for obj in objects:
        target = obj["technicalName"]
        raw_edges: list[dict[str, str]] = obj.get("lineageEdges") or []
        if not raw_edges:
            raw_edges = [
                {"name": s, "type": "select"}
                for s in (obj.get("lineageSources") or [])
            ]
        for edge in raw_edges:
            name = edge.get("name")
            if not name:
                continue
            source, source_meta = _resolve_graph_source(name, obj, known)
            conn_type = edge.get("type", "select")
            scope_info = parse_external_source(source, in_space=source in known)
            graph_edge: dict[str, Any] = {
                "source": source,
                "target": target,
                "connectionType": conn_type,
                "sourceInSpace": source in known,
                "sourceScope": scope_info["sourceScope"],
                "confidence": scope_info["confidence"],
            }
            graph_edge.update(source_meta)
            for key in (
                "sourceScope",
                "sourceSystem",
                "externalKey",
                "connectionName",
                "sourceReference",
                "targetReference",
                "rawPath",
                "confidence",
            ):
                if edge.get(key) not in (None, ""):
                    graph_edge[key] = edge[key]
            if "externalSpace" in scope_info:
                graph_edge["externalSpace"] = scope_info["externalSpace"]
            if scope_info.get("sourceKind"):
                graph_edge["sourceKind"] = scope_info["sourceKind"]
            # parse_external_source classifies S4:* refs and supplies the system
            # / key; surface them on the edge (unless the producer already did).
            for key in ("sourceSystem", "externalKey"):
                if scope_info.get(key) and key not in graph_edge:
                    graph_edge[key] = scope_info[key]
            for key in ("associationName", "targetEntity", "joinCondition"):
                if edge.get(key):
                    graph_edge[key] = edge[key]
            if graph_edge.get("sourceScope") == "external_system":
                add_external_node(
                    source,
                    system=str(graph_edge.get("sourceSystem") or "UNKNOWN"),
                    external_key=str(graph_edge.get("externalKey") or source),
                    source_reference=str(graph_edge.get("sourceReference") or ""),
                )
            add_edge(graph_edge)

    nodes = [
        {
            "id": obj["technicalName"],
            "businessName": obj.get("businessName", ""),
            "type": obj.get("objectType", ""),
            "status": obj.get("status", ""),
            "space": obj.get("space", ""),
            "system": obj.get("system", "DSP"),
            "layer": obj.get("layer", "unknown"),
            "layerCode": obj.get("layerCode", "?"),
            "role": obj.get("role", "other"),
            "confidence": obj.get("confidence", 0.5),
            "columns": [c.get("name", "") for c in (obj.get("columns") or [])],
            "columnCount": obj.get("columnCount", 0),
        }
        for obj in objects
    ]
    nodes.extend(external_nodes.values())

    return {
        "meta": {"schemaVersion": SCHEMA_VERSION},
        "nodes": nodes,
        "edges": edges,
        "adjacency": dict(adjacency),
        "upstream": dict(upstream),
    }


__all__ = [
    "SQL_BEARING_TYPES",
    "build_inventory_object",
    "build_lineage_graph",
]
