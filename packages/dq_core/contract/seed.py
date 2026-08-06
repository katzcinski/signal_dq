# Contract auto-seeder: inventory snapshot → draft contract guarantees (WS2-2)
from __future__ import annotations

from typing import Any

# Heuristik für Key-Kandidaten, wenn das Inventar keinen Schlüssel deklariert.
_KEY_HINTS = ("ID", "NO", "NR", "KEY", "CODE")
_TS_HINTS = ("TS", "TIME", "DATE", "LOAD", "CHANGE")


def _column_names(obj: dict[str, Any]) -> list[str]:
    return [
        c.get("name") or c.get("technicalName")
        for c in (obj.get("columns") or obj.get("properties") or [])
        if c.get("name") or c.get("technicalName")
    ]


def _key_candidates(columns: list[str]) -> list[str]:
    """Deterministische Key-Heuristik: Spalten mit ID-artigen Suffixen,
    in Inventar-Reihenfolge. WS2-2: ein Dataset ohne deklarierten Schlüssel
    bekommt einen KONKRETEN Pflichtvorschlag, kein Freitext-Hinweisfeld."""
    return [
        col for col in columns
        if any(col.upper().endswith(h) for h in _KEY_HINTS)
    ]


def _assoc_parent_name(target: Any) -> str:
    """Plain entity name from a CSN association target (string or enum-ref dict)."""
    if isinstance(target, dict):
        target = target.get("#") or target.get("=") or target.get("ref") or ""
    name = str(target or "").strip()
    return name.rsplit(".", 1)[-1] if name else ""


def _seed_referential(csn: dict[str, Any], self_name: str) -> list[dict[str, Any]]:
    """Propose referential guarantees from CSN associationManifest.

    Only emits entries where foreignKeyColumns (from @ObjectModel.foreignKey.association)
    and targetKeyColumns (from the ON condition) are both present — avoids speculative
    proposals on associations without explicit FK metadata.
    """
    result = []
    for assoc in (csn.get("associationManifest") or []):
        fk_cols: list[str] = assoc.get("foreignKeyColumns") or []
        target_key: list[str] = assoc.get("targetKeyColumns") or []
        parent = _assoc_parent_name(assoc.get("target"))
        if not fk_cols or not target_key or not parent or parent == self_name:
            continue
        result.append({
            "fk": fk_cols,
            "parent": parent,
            "parent_key": target_key,
            "severity": "warn",
            "proposed": True,
        })
    return result


def seed_from_inventory(obj: dict[str, Any]) -> dict[str, Any]:
    """Generate a draft contract dict from an inventory object.

    A2: kein 'schema:'-Key im Output — Schema-Bindung erfolgt zur Laufzeit.
    """
    name = obj.get("technicalName") or obj.get("id") or obj.get("name") or ""
    owned_by = obj.get("owned_by", "platform")

    guarantees: dict[str, Any] = {}
    csn = obj.get("csnProjection") or {}
    csn_columns: list[dict[str, Any]] = csn.get("columns") or []

    columns = _column_names(obj)
    if columns:
        guarantees["schema"] = {"columns": columns, "mode": "closed"}

    # Keys — three-tier priority:
    # 1. CSN explicit key:true elements (authoritative, no proposed flag)
    # 2. Name heuristic filtered by CSN notNull (stronger signal, proposed)
    # 3. Name heuristic alone (weakest signal, proposed)
    key_cols = csn.get("keyColumns") or obj.get("keyColumns") or []
    if key_cols:
        guarantees["keys"] = [{"columns": key_cols, "unique": True, "severity": "critical"}]
    else:
        not_null_names = {c["name"] for c in csn_columns if c.get("notNull")}
        candidates = _key_candidates(columns)
        confirmed = [c for c in candidates if c in not_null_names] if not_null_names else []
        chosen = confirmed or candidates
        if chosen:
            guarantees["keys"] = [{
                "columns": chosen,
                "unique": True,
                "severity": "critical",
                "proposed": True,
            }]

    ts_cols = [c for c in columns if any(h in c.upper() for h in _TS_HINTS)]
    if ts_cols:
        guarantees["freshness"] = {"column": ts_cols[0], "max_age": "PT24H", "severity": "warn"}

    guarantees["volume"] = {"baseline": "rolling", "bounds": "auto", "severity": "warn"}

    referential = _seed_referential(csn, name)
    if referential:
        guarantees["referential"] = referential

    return {
        "product": name,
        "dataset": name,
        "owned_by": owned_by,
        "kind": "internal_gate",
        "owners": [],
        "version": "0.1.0",
        "lifecycle": "draft",
        "guarantees": guarantees,
    }
