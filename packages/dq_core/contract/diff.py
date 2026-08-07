# Contract diff engine (WS2-4) — homegrown, classifies breaking changes.
# Breaking-Klassen: removed_column · key_change · constraint_tightened
# (Freshness/Completeness/Volume/not_null/Severity) · removed_referential ·
# closed-mode schema growth. Type narrowing folgt, sobald die Schema-Garantie
# Typen trägt (v1 kennt nur Spaltennamen).
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

_SEV_RANK = {"warn": 0, "fail": 1, "critical": 2}


@dataclass
class DiffEntry:
    kind: str       # removed_column | key_change | constraint_tightened | removed_referential | severity_escalated
    path: str
    old_value: Any
    new_value: Any
    breaking: bool


def diff_contracts(old: dict[str, Any], new: dict[str, Any]) -> list[DiffEntry]:
    """Compare two contract dicts; return breaking/non-breaking changes."""
    entries: list[DiffEntry] = []
    _diff_guarantees(
        old.get("guarantees") or {},
        new.get("guarantees") or {},
        entries,
    )
    return entries


def is_breaking(entries: list[DiffEntry]) -> bool:
    return any(e.breaking for e in entries)


def _diff_guarantees(
    old_g: dict[str, Any],
    new_g: dict[str, Any],
    out: list[DiffEntry],
) -> None:
    # schema: removed columns = breaking; closed mode + new column = tightened
    old_schema = old_g.get("schema") or {}
    new_schema = new_g.get("schema") or {}
    old_cols = set(old_schema.get("columns") or [])
    new_cols = set(new_schema.get("columns") or [])
    for col in sorted(old_cols - new_cols):
        out.append(DiffEntry("removed_column", "guarantees.schema.columns", col, None, True))
    if (new_schema.get("mode") or "closed") == "closed" and old_cols:
        for col in sorted(new_cols - old_cols):
            out.append(DiffEntry(
                "constraint_tightened", "guarantees.schema.columns",
                None, col, True,
            ))
    if old_schema.get("mode") == "open" and new_schema.get("mode") == "closed":
        out.append(DiffEntry("constraint_tightened", "guarantees.schema.mode", "open", "closed", True))

    # keys: any change = breaking
    old_keys = _normalise_keys(old_g.get("keys") or [])
    new_keys = _normalise_keys(new_g.get("keys") or [])
    if old_keys != new_keys:
        out.append(DiffEntry("key_change", "guarantees.keys", old_keys, new_keys, True))

    # freshness: tightening = breaking
    _diff_freshness(old_g.get("freshness") or {}, new_g.get("freshness") or {}, out)

    # volume: raising min_rows = breaking
    old_min = (old_g.get("volume") or {}).get("min_rows")
    new_min = (new_g.get("volume") or {}).get("min_rows")
    if old_min is not None and new_min is not None and int(new_min) > int(old_min):
        out.append(DiffEntry(
            "constraint_tightened", "guarantees.volume.min_rows",
            old_min, new_min, True,
        ))

    # completeness: raising min_pct or adding a column = breaking
    old_comp = {i["column"]: i for i in (old_g.get("completeness") or []) if i.get("column")}
    for item in new_g.get("completeness") or []:
        col = item.get("column", "")
        old_item = old_comp.get(col)
        if old_item is None:
            if old_comp or old_g:  # neue Constraint auf bestehendem Contract
                out.append(DiffEntry(
                    "constraint_tightened", f"guarantees.completeness[{col}]",
                    None, item.get("min_pct"), True,
                ))
            continue
        if float(item.get("min_pct", 0)) > float(old_item.get("min_pct", 0)):
            out.append(DiffEntry(
                "constraint_tightened", f"guarantees.completeness[{col}].min_pct",
                old_item.get("min_pct"), item.get("min_pct"), True,
            ))

    # not_null: new column under constraint = breaking
    old_nn = {c for nn in (old_g.get("not_null") or []) for c in (nn.get("columns") or [])}
    new_nn = {c for nn in (new_g.get("not_null") or []) for c in (nn.get("columns") or [])}
    for col in sorted(new_nn - old_nn):
        if old_g:
            out.append(DiffEntry(
                "constraint_tightened", f"guarantees.not_null[{col}]", None, col, True,
            ))

    # referential: removed FK = breaking for consumers
    old_refs = {_ref_key(r): r for r in (old_g.get("referential") or [])}
    new_refs = {_ref_key(r): r for r in (new_g.get("referential") or [])}
    for key in old_refs:
        if key not in new_refs:
            out.append(DiffEntry("removed_referential", "guarantees.referential", old_refs[key], None, True))

    # severity escalation on shared guarantee families = breaking (warn→block-Promotion)
    for fam in ("schema", "freshness", "volume"):
        old_sev = _SEV_RANK.get((old_g.get(fam) or {}).get("severity", ""), None)
        new_sev = _SEV_RANK.get((new_g.get(fam) or {}).get("severity", ""), None)
        if old_sev is not None and new_sev is not None and new_sev > old_sev:
            out.append(DiffEntry(
                "severity_escalated", f"guarantees.{fam}.severity",
                (old_g.get(fam) or {}).get("severity"),
                (new_g.get(fam) or {}).get("severity"), True,
            ))


def _normalise_keys(keys: list[dict]) -> list[tuple]:
    return sorted(tuple(sorted(k.get("columns") or [])) for k in keys)


def _ref_key(r: dict) -> str:
    fk = ",".join(sorted(r.get("fk") or []))
    return f"{fk}→{r.get('parent', '')}:{','.join(sorted(r.get('parent_key') or []))}"


def _diff_freshness(
    old_f: dict[str, Any],
    new_f: dict[str, Any],
    out: list[DiffEntry],
) -> None:
    old_age = _freshness_seconds(old_f)
    new_age = _freshness_seconds(new_f)
    if old_age and new_age and new_age < old_age:
        out.append(
            DiffEntry(
                "constraint_tightened",
                "guarantees.freshness.max_age",
                old_f.get("max_age") or old_f.get("max_age_hours"),
                new_f.get("max_age") or new_f.get("max_age_hours"),
                True,
            )
        )


def _freshness_seconds(f: dict[str, Any]) -> int | None:
    """Akzeptiert kanonisches ISO max_age und (für alte Snapshots) max_age_hours."""
    if f.get("max_age_hours") is not None:
        try:
            return int(float(f["max_age_hours"]) * 3600)
        except (TypeError, ValueError):
            return None
    return _parse_duration(f.get("max_age", ""))


def _parse_duration(s: str) -> int | None:
    """Parse ISO 8601 duration string like PT1H, PT24H, P1D → seconds."""
    if not s:
        return None
    m = re.match(r"P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$", str(s))
    if not m:
        return None
    days = int(m.group(1) or 0)
    hours = int(m.group(2) or 0)
    minutes = int(m.group(3) or 0)
    seconds = int(m.group(4) or 0)
    return days * 86400 + hours * 3600 + minutes * 60 + seconds
