"""Best-effort SQL reconstruction from Datasphere graphical-view CSN.

The generated SQL is intentionally a readable skeleton. It is not a
Datasphere-native deployable artifact and does not try to encode labels,
associations, DACs, release state, or analytic semantics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


WarningDict = dict[str, str]


def _warning(code: str, message: str, context: str) -> WarningDict:
    return {"code": code, "message": message, "context": context}


def _enum_value(value: Any) -> str:
    if isinstance(value, dict) and value.get("#"):
        return str(value["#"])
    return str(value) if value is not None else ""


def quote_identifier(value: str) -> str:
    return '"' + str(value).replace('"', '""') + '"'


def _quote_ref(ref: Any, *, source_context: bool = False) -> str:
    if not isinstance(ref, list) or not ref:
        return ""
    parts = [str(part) for part in ref if str(part)]
    if source_context and len(parts) == 1 and "." in parts[0]:
        parts = [part for part in parts[0].split(".") if part]
    return ".".join(quote_identifier(part) for part in parts)


def _ref_name(ref: Any) -> str:
    if not isinstance(ref, list) or not ref:
        return ""
    return ".".join(str(part) for part in ref if str(part))


def _alias_of(node: Any) -> str:
    if isinstance(node, dict):
        alias = node.get("as")
        if alias:
            return str(alias)
        ref = node.get("ref")
        if isinstance(ref, list) and ref:
            return str(ref[-1]).split(".")[-1]
    return ""


def _literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


@dataclass
class _RenderContext:
    warnings: list[WarningDict] = field(default_factory=list)
    join_details: list[dict[str, Any]] = field(default_factory=list)
    projection_lineage: list[dict[str, Any]] = field(default_factory=list)
    alias_nullable: dict[str, bool] = field(default_factory=dict)
    alias_source_map: dict[str, str] = field(default_factory=dict)
    warned_nullable_keys: set[str] = field(default_factory=set)

    def warn(self, code: str, message: str, context: str) -> None:
        self.warnings.append(_warning(code, message, context))


def _render_expr(expr: Any, ctx: _RenderContext, context: str) -> tuple[str, bool, str | None, bool]:
    """Return (sql, unsupported, source_ref, nullable_source)."""
    if isinstance(expr, str):
        return expr.upper() if expr.lower() in {"and", "or", "not"} else expr, False, None, False
    if isinstance(expr, (int, float, bool)) or expr is None:
        return _literal(expr), False, None, False
    if isinstance(expr, list):
        chunks: list[str] = []
        unsupported = False
        source_ref: str | None = None
        nullable = False
        for idx, item in enumerate(expr):
            rendered, item_unsupported, item_source, item_nullable = _render_expr(
                item, ctx, f"{context}[{idx}]"
            )
            chunks.append(rendered)
            unsupported = unsupported or item_unsupported
            source_ref = source_ref or item_source
            nullable = nullable or item_nullable
        return " ".join(part for part in chunks if part), unsupported, source_ref, nullable
    if not isinstance(expr, dict):
        ctx.warn("UNSUPPORTED_EXPR", f"Unsupported expression type: {type(expr).__name__}", context)
        return "/* unsupported */ NULL", True, None, False

    if isinstance(expr.get("ref"), list):
        ref = expr["ref"]
        source = _ref_name(ref)
        alias = str(ref[0]) if ref else ""
        return _quote_ref(ref), False, source, bool(ctx.alias_nullable.get(alias))
    if "val" in expr:
        return _literal(expr.get("val")), False, None, False
    if isinstance(expr.get("xpr"), list):
        return _render_expr(expr["xpr"], ctx, f"{context}.xpr")
    if isinstance(expr.get("SELECT"), dict):
        sql, _aliases = _render_select(expr["SELECT"], ctx, context)
        return f"({sql})", False, None, False
    if isinstance(expr.get("func"), str):
        rendered_args: list[str] = []
        unsupported = False
        nullable = False
        for idx, arg in enumerate(expr.get("args") or []):
            rendered, item_unsupported, _item_source, item_nullable = _render_expr(
                arg, ctx, f"{context}.args[{idx}]"
            )
            rendered_args.append(rendered)
            unsupported = unsupported or item_unsupported
            nullable = nullable or item_nullable
        return f"{expr['func']}({', '.join(rendered_args)})", unsupported, None, nullable

    ctx.warn(
        "UNSUPPORTED_EXPR",
        "Unsupported CSN expression; rendered as NULL placeholder.",
        context,
    )
    return "/* unsupported */ NULL", True, None, False


def _collect_aliases(node: Any) -> set[str]:
    aliases: set[str] = set()
    if not isinstance(node, dict):
        return aliases
    alias = _alias_of(node)
    if alias:
        aliases.add(alias)
    if isinstance(node.get("SELECT"), dict):
        aliases.update(_collect_aliases(node["SELECT"].get("from")))
    if isinstance(node.get("args"), list):
        for arg in node["args"]:
            aliases.update(_collect_aliases(arg))
    return aliases


def _collect_source_refs(node: Any) -> list[str]:
    refs: list[str] = []
    if not isinstance(node, dict):
        return refs
    if isinstance(node.get("ref"), list):
        refs.append(_ref_name(node["ref"]))
    if isinstance(node.get("SELECT"), dict):
        refs.extend(_collect_source_refs(node["SELECT"].get("from")))
    if isinstance(node.get("args"), list):
        for arg in node["args"]:
            refs.extend(_collect_source_refs(arg))
    return list(dict.fromkeys(ref for ref in refs if ref))


def _collect_expr_refs(node: Any) -> list[list[str]]:
    """Collect every ``{"ref": [...]}`` leaf inside a column expression tree."""
    refs: list[list[str]] = []

    def walk(n: Any) -> None:
        if isinstance(n, dict):
            if isinstance(n.get("ref"), list):
                refs.append(n["ref"])
                return
            for key, value in n.items():
                if key not in ("as", "key") and isinstance(value, (dict, list)):
                    walk(value)
        elif isinstance(n, list):
            for item in n:
                walk(item)

    walk(node)
    return refs


def _flatten_on_tokens(node: Any) -> list[Any]:
    """Flatten a CSN ON / boolean expression into a flat token list.

    Refs stay as ``{"ref": [...]}`` dicts, operators/keywords as strings,
    literals as ``{"val": ...}`` dicts. ``xpr`` wrappers are unwrapped so
    ``a = b AND c = d`` becomes ``[ref, "=", ref, "and", ref, "=", ref]``.
    """
    if isinstance(node, dict):
        if isinstance(node.get("xpr"), list):
            return _flatten_on_tokens(node["xpr"])
        return [node]
    if isinstance(node, list):
        tokens: list[Any] = []
        for item in node:
            tokens.extend(_flatten_on_tokens(item))
        return tokens
    if node is None:
        return []
    return [node]


def extract_key_pairs(on_node: Any) -> list[dict[str, str]]:
    """Extract column-to-column equality pairs from a CSN ON expression.

    Returns ``[{"left": "alias.col", "right": "alias.col"}, ...]`` for each
    ``ref = ref`` equality (conjuncts joined by AND). Only column-to-column
    equalities are emitted — literal comparisons and inequalities are ignored
    because they carry no key-coverage information for grain analysis.
    """
    tokens = _flatten_on_tokens(on_node)
    pairs: list[dict[str, str]] = []
    for idx, tok in enumerate(tokens):
        if not (isinstance(tok, str) and tok.strip() == "="):
            continue
        left = tokens[idx - 1] if idx - 1 >= 0 else None
        right = tokens[idx + 1] if idx + 1 < len(tokens) else None
        left_ref = (
            _ref_name(left.get("ref"))
            if isinstance(left, dict) and isinstance(left.get("ref"), list)
            else ""
        )
        right_ref = (
            _ref_name(right.get("ref"))
            if isinstance(right, dict) and isinstance(right.get("ref"), list)
            else ""
        )
        if left_ref and right_ref:
            pairs.append({"left": left_ref, "right": right_ref})
    return pairs


def _render_from(node: Any, ctx: _RenderContext, context: str) -> tuple[str, set[str]]:
    if not isinstance(node, dict):
        ctx.warn("UNSUPPORTED_FROM", "Unsupported or missing FROM clause.", context)
        return "/* unsupported source */", set()

    if isinstance(node.get("ref"), list):
        sql = _quote_ref(node["ref"], source_context=True)
        ref_name = _ref_name(node["ref"])
        alias = _alias_of(node)
        aliases = {alias} if alias else set()
        if alias:
            sql += f" AS {quote_identifier(alias)}"
            ctx.alias_nullable.setdefault(alias, False)
            ctx.alias_source_map[alias] = ref_name
        return sql, aliases

    if isinstance(node.get("SELECT"), dict):
        sql, inner_aliases = _render_select(node["SELECT"], ctx, context)
        alias = _alias_of(node)
        if alias:
            ctx.alias_nullable.setdefault(alias, any(ctx.alias_nullable.get(a, False) for a in inner_aliases))
            return f"(\n{_indent(sql)}\n) AS {quote_identifier(alias)}", {alias}
        return f"(\n{_indent(sql)}\n)", inner_aliases

    if node.get("join"):
        args = [arg for arg in node.get("args", []) if isinstance(arg, dict)]
        if not args:
            ctx.warn("UNSUPPORTED_FROM", "Join node has no usable arguments.", context)
            return "/* unsupported join */", set()

        current_sql, current_aliases = _render_from(args[0], ctx, f"{context}.args[0]")
        all_aliases = set(current_aliases)
        join_kind = str(node.get("join") or "inner").lower()
        join_sql = {
            "left": "LEFT JOIN",
            "right": "RIGHT JOIN",
            "full": "FULL OUTER JOIN",
            "inner": "INNER JOIN",
            "cross": "CROSS JOIN",
        }.get(join_kind, f"{join_kind.upper()} JOIN")

        for idx, arg in enumerate(args[1:], 1):
            right_sql, right_aliases = _render_from(arg, ctx, f"{context}.args[{idx}]")
            if join_kind == "left":
                for alias in right_aliases:
                    ctx.alias_nullable[alias] = True
            elif join_kind == "right":
                for alias in current_aliases:
                    ctx.alias_nullable[alias] = True
            elif join_kind == "full":
                for alias in set(current_aliases) | set(right_aliases):
                    ctx.alias_nullable[alias] = True

            condition = ""
            if join_kind != "cross":
                rendered, _unsupported, _source, _nullable = _render_expr(
                    node.get("on") or [], ctx, f"{context}.on"
                )
                condition = f"\n    ON {rendered}" if rendered else ""

            ctx.join_details.append({
                "joinType": join_kind,
                "leftAliases": sorted(current_aliases),
                "rightAliases": sorted(right_aliases),
                "cardinality": node.get("cardinality") or {},
                "condition": condition.strip().removeprefix("ON ").strip(),
                "keyPairs": extract_key_pairs(node.get("on")),
                "sourceRefs": _collect_source_refs(node),
            })
            current_sql = f"{current_sql}\n  {join_sql} {right_sql}{condition}"
            current_aliases = set(current_aliases) | set(right_aliases)
            all_aliases.update(right_aliases)
        return current_sql, all_aliases

    if isinstance(node.get("SET"), dict):
        sql, inner_aliases = _render_query(node, ctx, context)
        alias = _alias_of(node)
        if alias:
            return f"(\n{_indent(sql)}\n) AS {quote_identifier(alias)}", {alias}
        return f"(\n{_indent(sql)}\n)", inner_aliases

    ctx.warn("UNSUPPORTED_FROM", "Unsupported FROM node shape.", context)
    return "/* unsupported source */", set()


def _column_alias(column: dict[str, Any]) -> str:
    if column.get("as"):
        return str(column["as"])
    ref = column.get("ref")
    if isinstance(ref, list) and ref:
        return str(ref[-1]).split(".")[-1]
    return ""


def _render_column(column: Any, ctx: _RenderContext, context: str) -> str | None:
    if isinstance(column, str):
        return quote_identifier(column)
    if not isinstance(column, dict):
        ctx.warn("UNSUPPORTED_EXPR", "Unsupported SELECT column shape.", context)
        return None
    alias = _column_alias(column)
    rendered, unsupported, expr_source_ref, nullable = _render_expr(column, ctx, context)
    # Classify by the column's own shape, not by what _render_expr surfaced:
    # a bare {"ref": [...]} (possibly carrying as/key) is a passthrough; anything
    # with func/xpr/val/SELECT is an expression. This stops xpr columns from
    # being mislabelled as direct via their first nested ref.
    is_direct = (set(column.keys()) - {"as", "key"}) == {"ref"}
    source_ref = expr_source_ref if is_direct else None
    all_source_refs: list[str] = []
    sole = (
        next(iter(ctx.alias_source_map.values()))
        if len(ctx.alias_source_map) == 1 else None
    )
    for ref in _collect_expr_refs(column):
        parts = [str(part) for part in ref if str(part)]
        if len(parts) >= 2:
            obj = ctx.alias_source_map.get(parts[0], parts[0])
            all_source_refs.append(f"{obj}.{parts[-1]}")
        elif len(parts) == 1 and sole:
            all_source_refs.append(f"{sole}.{parts[0]}")
    all_source_refs = list(dict.fromkeys(all_source_refs))
    ctx.projection_lineage.append({
        "output": alias,
        "sourceRef": source_ref or "",
        "expression": "" if is_direct else rendered,
        "alias": alias,
        "unsupported": unsupported,
        "nullableSource": nullable,
        "allSourceRefs": all_source_refs,
    })
    if alias and rendered != quote_identifier(alias):
        return f"{rendered} AS {quote_identifier(alias)}"
    return rendered


def _render_select(select: dict[str, Any], ctx: _RenderContext, context: str) -> tuple[str, set[str]]:
    from_sql, aliases = _render_from(select.get("from"), ctx, f"{context}.from")
    columns = select.get("columns") or []
    if isinstance(columns, list) and columns:
        rendered_columns = [
            col for idx, column in enumerate(columns)
            if (col := _render_column(column, ctx, f"{context}.columns[{idx}]"))
        ]
    else:
        rendered_columns = ["*"]

    select_list = ",\n    ".join(rendered_columns)
    sql = f"SELECT\n    {select_list}\nFROM {from_sql}"
    return sql, aliases


def _render_query(query: Any, ctx: _RenderContext, context: str) -> tuple[str, set[str]]:
    """Render a query node, descending through SET union/intersect/except shapes."""
    if isinstance(query, dict) and isinstance(query.get("SELECT"), dict):
        return _render_select(query["SELECT"], ctx, f"{context}.SELECT")
    if isinstance(query, dict) and isinstance(query.get("SET"), dict):
        sset = query["SET"]
        op = str(sset.get("op") or "union").upper()
        keyword = f"{op} ALL" if (op == "UNION" and sset.get("all")) else op
        parts: list[str] = []
        aliases: set[str] = set()
        for idx, arg in enumerate(sset.get("args") or []):
            branch_sql, branch_aliases = _render_query(arg, ctx, f"{context}.SET.args[{idx}]")
            parts.append(branch_sql)
            aliases |= branch_aliases
        return f"\n{keyword}\n".join(parts), aliases
    ctx.warn("UNSUPPORTED_FROM", "Unsupported or missing query shape.", context)
    return "/* unsupported source */", set()


def _indent(sql: str) -> str:
    return "\n".join(f"  {line}" for line in sql.splitlines())


def _warn_nullable_key_outputs(obj_def: dict[str, Any], ctx: _RenderContext) -> None:
    elements = obj_def.get("elements") or {}
    if not isinstance(elements, dict):
        return
    for lineage in ctx.projection_lineage:
        output = lineage.get("output") or ""
        if not output or not lineage.get("nullableSource"):
            continue
        element = elements.get(output)
        if not isinstance(element, dict):
            continue
        if not (element.get("key") or element.get("notNull")):
            continue
        if output in ctx.warned_nullable_keys:
            continue
        ctx.warned_nullable_keys.add(output)
        ctx.warn(
            "LEFT_JOIN_NULLABLE_KEY",
            "Output column is key/not-null but is projected from the nullable side of an outer join.",
            output,
        )


def extract_query_details(obj_def: dict[str, Any]) -> dict[str, Any]:
    """Return lightweight join/projection facts from the primary CSN query."""
    query = (obj_def or {}).get("query") or {}
    if not (isinstance(query.get("SELECT"), dict) or isinstance(query.get("SET"), dict)):
        return {"joinDetails": [], "projectionLineage": [], "aliasMap": {}}
    ctx = _RenderContext()
    _render_query(query, ctx, "query")
    return {
        "joinDetails": ctx.join_details,
        "projectionLineage": ctx.projection_lineage,
        "aliasMap": ctx.alias_source_map,
    }


def build_sql_reconstruction(def_name: str, obj_def: dict[str, Any]) -> dict[str, Any]:
    """Build a readable SQL skeleton from a graphical view's CSN query tree."""
    base = {
        "available": False,
        "status": "not_applicable",
        "sql": "",
        "warnings": [],
        "source": "csn.query.SELECT",
    }
    query = (obj_def or {}).get("query") or {}
    if not (isinstance(query.get("SELECT"), dict) or isinstance(query.get("SET"), dict)):
        return base
    source_path = "csn.query.SET" if isinstance(query.get("SET"), dict) else "csn.query.SELECT"

    ctx = _RenderContext()
    try:
        sql, _aliases = _render_query(query, ctx, "query")
        _warn_nullable_key_outputs(obj_def, ctx)
    except Exception as exc:  # noqa: BLE001 - inventory must survive odd CSN
        return {
            **base,
            "status": "failed",
            "warnings": [_warning("RECONSTRUCTION_FAILED", str(exc), def_name)],
            "source": source_path,
        }

    status = "partial" if ctx.warnings else "ok"
    return {
        "available": True,
        "status": status,
        "sql": f"CREATE VIEW {quote_identifier(def_name)} AS\n{sql};",
        "warnings": ctx.warnings,
        "source": source_path,
    }
