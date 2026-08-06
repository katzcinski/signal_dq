"""Name-based PK-Scoring-Heuristiken (pure stdlib).

Portiert aus datasphere-tools/toolbox-ui analyzer_heuristics.py: bewertet
PK-Kandidaten nicht nur technisch (Uniqueness/Null-Rate), sondern auch nach
Namensmustern — ein ``*_ID``/``*Key``-Feld schlägt ein ``*Amount``-Feld, und
Measure-Felder (Amount, Quantity, Price …) werden aktiv unterdrückt.

Keine DB, kein Framework — nur ``re``/``copy`` aus der Stdlib.
"""
from __future__ import annotations

import copy
import re
from typing import Any

__all__ = [
    "classify_view_context",
    "score_single_candidate",
    "score_composite_candidate",
    "recompute_overall_scores",
    "heuristic_catalog",
    "enrich_result_with_context",
    "TECHNICAL_WEIGHT",
    "BUSINESS_WEIGHT",
    "MEASURE_TOKENS",
]


TECHNICAL_WEIGHT = 0.65
BUSINESS_WEIGHT = 0.35

DOC_TOKENS = {
    "document",
    "doc",
    "order",
    "salesorder",
    "purchaseorder",
    "invoice",
    "delivery",
    "booking",
    "transaction",
}
ENTITY_TOKENS = {
    "customer",
    "product",
    "material",
    "vendor",
    "supplier",
    "employee",
    "company",
    "account",
    "plant",
    "costcenter",
    "profitcenter",
}
ID_TOKENS = {"id", "key", "guid", "uuid"}
CODE_TOKENS = {"code", "number", "no", "nr"}
LINE_TOKENS = {"item", "itemid", "position", "pos", "line", "linenumber", "sequence", "seq"}
LINE_SUFFIXES = ("item", "items", "line", "lines", "position", "positions", "sequence", "seq")
MEASURE_TOKENS = {
    "amount",
    "quantity",
    "qty",
    "value",
    "price",
    "cost",
    "rate",
    "percent",
    "percentage",
    "weight",
    "volume",
    "tax",
    "discount",
    "net",
    "gross",
    "revenue",
    "margin",
    "score",
}
MEASURE_SUFFIXES = tuple(sorted(MEASURE_TOKENS, key=len, reverse=True))
METRIC_VIEW_TOKENS = {
    "fact",
    "facts",
    "metric",
    "metrics",
    "measure",
    "measures",
    "sales",
    "orders",
    "items",
    "transaction",
    "transactions",
}
DIMENSION_VIEW_TOKENS = {
    "dimension",
    "dim",
    "master",
    "customer",
    "product",
    "material",
    "vendor",
    "employee",
}


def _split_terms(text: str) -> list[str]:
    if not text:
        return []
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
    parts = re.split(r"[^A-Za-z0-9]+", spaced)
    tokens: list[str] = []
    for part in parts:
        token = part.strip().lower()
        if not token:
            continue
        tokens.append(token)
        if token.endswith("s") and len(token) > 4:
            tokens.append(token[:-1])
    compact = re.sub(r"[^a-z0-9]+", "", text.lower())
    if compact:
        tokens.append(compact)
        if compact.endswith("s") and len(compact) > 4:
            tokens.append(compact[:-1])
    return list(dict.fromkeys(tokens))


def _column_lookup(inventory_obj: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    if not inventory_obj:
        return lookup
    for col in inventory_obj.get("columns") or []:
        name = str(col.get("name") or col.get("technicalName") or "").strip()
        if name:
            lookup[name] = col
    return lookup


def classify_view_context(inventory_obj: dict[str, Any] | None, view_name: str) -> dict[str, Any]:
    semantic_usage = str((inventory_obj or {}).get("semanticUsage") or "").strip()
    object_type = str((inventory_obj or {}).get("objectType") or "").strip()
    tokens = set(_split_terms(view_name))
    reasons: list[str] = []

    if semantic_usage == "Dimension":
        reasons.append("semanticUsage=Dimension")
        kind = "dimension"
    elif semantic_usage == "Fact":
        reasons.append("semanticUsage=Fact")
        kind = "fact"
    elif any(token in tokens for token in {"item", "items", "line", "position"}):
        reasons.append("view name indicates line items")
        kind = "line_item"
    elif view_name.lower().startswith("i_") and any(token in tokens for token in DIMENSION_VIEW_TOKENS):
        reasons.append("interface-style dimension naming")
        kind = "dimension"
    elif any(token in tokens for token in {"dim", "dimension", "master"}):
        reasons.append("dimension-style naming")
        kind = "dimension"
    elif any(token in tokens for token in METRIC_VIEW_TOKENS):
        reasons.append("fact or metric naming")
        kind = "fact"
    elif object_type == "analytic-models":
        reasons.append("analytic model context")
        kind = "fact"
    else:
        reasons.append("generic inventory context")
        kind = "generic"

    entity_focus = sorted(
        token for token in tokens if token in ENTITY_TOKENS or token in DOC_TOKENS
    )
    return {
        "kind": kind,
        "semantic_usage": semantic_usage,
        "object_type": object_type,
        "tokens": sorted(tokens),
        "entity_focus": entity_focus,
        "reasons": reasons,
    }


def _name_flags(column_name: str, business_name: str) -> dict[str, Any]:
    tokens = set(_split_terms(column_name) + _split_terms(business_name))
    compact = re.sub(r"[^a-z0-9]+", "", f"{column_name} {business_name}".lower())
    name_compact = re.sub(r"[^a-z0-9]+", "", str(column_name).lower())
    exact_id = compact == "id"
    is_measure = any(token in tokens for token in MEASURE_TOKENS) or any(
        compact.endswith(token) or name_compact.endswith(token) for token in MEASURE_SUFFIXES
    )
    return {
        "tokens": tokens,
        "exact_id": exact_id,
        "is_measure": is_measure,
        "is_doc": any(token in tokens for token in DOC_TOKENS),
        "is_entity": any(token in tokens for token in ENTITY_TOKENS),
        "is_id_like": exact_id or any(token in tokens for token in ID_TOKENS),
        "is_code_like": any(token in tokens for token in CODE_TOKENS),
        "is_line_like": any(token in tokens for token in LINE_TOKENS),
        "compact": compact,
        "name_compact": name_compact,
    }


def _dtype_penalty(data_type: str) -> int:
    upper = str(data_type or "").upper()
    if upper in {"DECIMAL", "SMALLDECIMAL", "DOUBLE", "REAL", "FLOAT"}:
        return -18
    return 0


def _view_entity_match(flags: dict[str, Any], context: dict[str, Any]) -> bool:
    context_tokens = set(context.get("tokens") or [])
    entity_focus = set(context.get("entity_focus") or [])
    relevant = flags["tokens"] & (ENTITY_TOKENS | DOC_TOKENS)
    return bool(relevant & (entity_focus or context_tokens))


def _strip_line_suffix(compact: str) -> str:
    for suffix in LINE_SUFFIXES:
        if compact.endswith(suffix) and len(compact) > len(suffix) + 2:
            return compact[: -len(suffix)]
    return ""


def _shared_cds_doc_item_pair(flags: list[dict[str, Any]]) -> bool:
    compacts = [str(flag.get("name_compact") or flag.get("compact") or "") for flag in flags]
    for idx, flag in enumerate(flags):
        compact = compacts[idx]
        base = _strip_line_suffix(compact)
        if not base or not flag.get("is_line_like"):
            continue
        for other_idx, other_flag in enumerate(flags):
            if idx == other_idx:
                continue
            other_compact = compacts[other_idx]
            if not other_compact:
                continue
            if other_compact == base and (
                other_flag.get("is_doc")
                or other_flag.get("is_entity")
                or "document" in other_flag.get("tokens", set())
                or "order" in other_flag.get("tokens", set())
            ):
                return True
    return False


def score_single_candidate(
    candidate: dict[str, Any],
    context: dict[str, Any],
    business_name: str = "",
) -> dict[str, Any]:
    flags = _name_flags(str(candidate.get("column") or ""), business_name)
    technical = float(candidate.get("uniqueness_pct") or 0.0)
    if candidate.get("exact"):
        technical = 100.0
    technical = max(0.0, technical - (float(candidate.get("null_pct") or 0.0) * 1.2))

    business = 40
    reasons: list[str] = []
    suppress = False
    if flags["exact_id"]:
        business += 30
        reasons.append("exact ID field")
    elif flags["is_id_like"]:
        business += 18
        reasons.append("ID-like field")
    if flags["is_code_like"]:
        business += 10
        reasons.append("code/number field")
    if flags["is_doc"]:
        business += 14
        reasons.append("document/header-like field")
    if flags["is_line_like"]:
        business += 6
        reasons.append("line/item-like field")
    if _view_entity_match(flags, context):
        boost = 22 if context["kind"] == "dimension" else 10
        business += boost
        reasons.append("matches view business entity")
    if flags["is_measure"]:
        business -= 70
        reasons.append("measure-like field")
        suppress = True
    business += _dtype_penalty(str(candidate.get("data_type") or ""))

    if context["kind"] == "dimension":
        if flags["is_id_like"] or flags["is_entity"]:
            business += 18
            reasons.append("dimension context boost")
        if flags["is_line_like"]:
            business -= 8
            reasons.append("line-style field in dimension context")
    elif context["kind"] in {"fact", "line_item"}:
        if flags["is_entity"] and not flags["is_doc"]:
            business -= 8
            reasons.append("likely foreign key in fact context")
        if flags["is_line_like"]:
            business += 8
            reasons.append("line-item context boost")

    business = max(0, min(100, business))
    final_score = round((technical * TECHNICAL_WEIGHT) + (business * BUSINESS_WEIGHT), 2)
    enriched = dict(candidate)
    enriched.update(
        {
            "technical_score": round(technical, 2),
            "business_score": business,
            "final_score": final_score,
            "suppressed": suppress,
            "business_name": business_name,
            "reason_tags": reasons,
            "rank_reason": ", ".join(reasons[:3]) if reasons else enriched.get("rank_reason", ""),
            "_flags": flags,
        }
    )
    return enriched


def score_composite_candidate(
    candidate: dict[str, Any],
    context: dict[str, Any],
    scored_singles: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    columns = list(candidate.get("columns") or [])
    members = [scored_singles.get(col) for col in columns if col in scored_singles]
    technical = float(candidate.get("uniqueness_pct") or 0.0)
    if candidate.get("exact"):
        technical = 100.0
    technical = max(0.0, technical - max(0, len(columns) - 2) * 3)

    business = 35
    reasons: list[str] = []
    suppress = False
    flags = [member.get("_flags", {}) for member in members if member]
    if any(flag.get("is_measure") for flag in flags):
        business -= 80
        reasons.append("contains measure-like field")
        suppress = True
    if any(flag.get("exact_id") for flag in flags):
        business += 10
        reasons.append("contains explicit ID")
    if any(flag.get("is_doc") for flag in flags) and any(flag.get("is_line_like") for flag in flags):
        business += 40
        reasons.append("document + item pattern")
    if _shared_cds_doc_item_pair(flags):
        business += 28
        reasons.append("matching CDS document/item pair")
    if context["kind"] == "dimension":
        business -= 12
        reasons.append("compound key less typical for dimensions")
        if any(flag.get("is_entity") and flag.get("is_id_like") for flag in flags):
            business += 8
    elif context["kind"] in {"fact", "line_item"}:
        if any(flag.get("is_entity") or flag.get("is_doc") for flag in flags):
            business += 8
        if any(flag.get("is_line_like") for flag in flags):
            business += 12
            reasons.append("line-item context boost")

    entity_match_count = sum(1 for flag in flags if _view_entity_match(flag, context))
    if entity_match_count:
        business += min(20, entity_match_count * 8)
        reasons.append("aligned with view entity")
    business -= max(0, len(columns) - 2) * 6
    business = max(0, min(100, business))
    final_score = round((technical * TECHNICAL_WEIGHT) + (business * BUSINESS_WEIGHT), 2)

    enriched = dict(candidate)
    enriched.update(
        {
            "technical_score": round(technical, 2),
            "business_score": business,
            "final_score": final_score,
            "suppressed": suppress,
            "reason_tags": reasons,
            "rank_reason": ", ".join(reasons[:3]) if reasons else enriched.get("rank_reason", ""),
        }
    )
    return enriched


def recompute_overall_scores(result: dict[str, Any]) -> dict[str, Any]:
    singles = (result.get("pk_candidates") or {}).get("ranked_single") or []
    composites = (result.get("pk_candidates") or {}).get("ranked_composite") or []
    issues = result.get("issues") or []
    best_single = singles[0] if singles else {}
    best_comp = composites[0] if composites else {}
    completeness = max(
        0.0,
        100.0 - (
            sum(float(col.get("null_pct") or 0.0) + float(col.get("empty_pct") or 0.0) for col in result.get("columns") or [])
            / max(1, len(result.get("columns") or []))
        ),
    )
    business_fit = float(best_single.get("business_score") or best_comp.get("business_score") or 0.0)
    uniqueness = float(best_single.get("technical_score") or 0.0)
    compound_viability = float(best_comp.get("final_score") or 0.0)
    overall = round(
        (uniqueness * 0.30)
        + (completeness * 0.20)
        + (business_fit * 0.25)
        + (compound_viability * 0.15)
        + (max(0.0, 100.0 - len(issues) * 5) * 0.10)
    )
    return {
        "overall_key_confidence": overall,
        "uniqueness": round(uniqueness),
        "completeness": round(completeness),
        "business_fit": round(business_fit),
        "compound_viability": round(compound_viability),
        "weights": {
            "technical": TECHNICAL_WEIGHT,
            "business": BUSINESS_WEIGHT,
            "overall_uniqueness": 0.30,
            "overall_completeness": 0.20,
            "overall_business_fit": 0.25,
            "overall_compound_viability": 0.15,
            "overall_observations": 0.10,
        },
    }


def heuristic_catalog() -> dict[str, Any]:
    return {
        "weights": {
            "technical": TECHNICAL_WEIGHT,
            "business": BUSINESS_WEIGHT,
        },
        "single_rules": {
            "positive": [
                {"signal": "exact ID", "score": "+30"},
                {"signal": "contains ID / KEY / GUID / UUID", "score": "+18"},
                {"signal": "contains CODE / NUMBER / NO / NR", "score": "+10"},
                {"signal": "document/header terms", "score": "+14"},
                {"signal": "matches view entity in dimension context", "score": "+22"},
            ],
            "negative": [
                {"signal": "measure-like field (Amount, Quantity, Price, Value ...)", "score": "-70 and suppress"},
                {"signal": "decimal/float-like datatype", "score": "-18"},
                {"signal": "foreign-key-like field in fact context", "score": "-8"},
            ],
        },
        "compound_rules": [
            {"signal": "document/header + item/line pattern", "score": "+40"},
            {"signal": "matching CDS root pair (SalesOrder + SalesOrderItem)", "score": "+28"},
            {"signal": "line-item context boost", "score": "+12"},
            {"signal": "dimension context", "score": "-12"},
            {"signal": "extra column beyond two", "score": "-6 each"},
            {"signal": "measure-like member", "score": "suppress"},
        ],
    }


def enrich_result_with_context(
    result: dict[str, Any],
    inventory_obj: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Re-score and re-rank a profiler result with name-based heuristics.

    Wendet ``score_single/composite_candidate`` an, unterdrückt Measure-Felder,
    sortiert nach ``final_score`` und hängt ``scores``/``heuristics`` an. Erwartet
    die ``analyze_view``-Result-Form (``columns``, ``pk_candidates``, ``issues``).
    """
    enriched = copy.deepcopy(result)
    column_map = _column_lookup(inventory_obj)
    context = classify_view_context(inventory_obj, str(enriched.get("view") or ""))
    pk = enriched.setdefault("pk_candidates", {})

    scored_single_rows = []
    for row in pk.get("ranked_single") or []:
        inv_col = column_map.get(str(row.get("column") or ""), {})
        business_name = str(inv_col.get("businessName") or "")
        scored_single_rows.append(score_single_candidate(row, context, business_name))
    all_single_lookup = {row["column"]: row for row in scored_single_rows}
    scored_single_rows = [row for row in scored_single_rows if not row.get("suppressed")]
    scored_single_rows.sort(
        key=lambda row: (
            -float(row.get("final_score") or 0.0),
            -float(row.get("technical_score") or 0.0),
            str(row.get("column") or "").lower(),
        )
    )

    scored_comp_rows = []
    for row in pk.get("ranked_composite") or []:
        scored_comp_rows.append(score_composite_candidate(row, context, all_single_lookup))
    scored_comp_rows = [row for row in scored_comp_rows if not row.get("suppressed")]
    scored_comp_rows.sort(
        key=lambda row: (
            -float(row.get("final_score") or 0.0),
            -float(row.get("technical_score") or 0.0),
            len(row.get("columns") or []),
            "+".join(row.get("columns") or []).lower(),
        )
    )

    pk["ranked_single"] = scored_single_rows
    pk["ranked_composite"] = scored_comp_rows
    for row in pk["ranked_single"]:
        row.pop("_flags", None)
    enriched["scores"] = recompute_overall_scores(enriched)
    enriched["heuristics"] = {
        "view_context": context,
        "catalog": heuristic_catalog(),
        "suppressed_terms": sorted(MEASURE_TOKENS),
    }
    return enriched
