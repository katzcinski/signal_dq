"""ODCS-3.1-Export (R5-1): kanonisches Contract-Schema v1 → Open Data Contract
Standard (Bitol / LF AI & Data).

Einweg-Export für Interop (OpenMetadata, Collibra, datacontract-cli, Soda) —
ODCS ist NIE ein zweites internes Schema (Lehre aus dem §0-Leitbefund).
Compliance bleibt bewusst draußen: ODCS modelliert keine Laufzeit-Resultate
(bestätigt unsere A1-Trennung).

Mapping:
  schema.columns        → schema[0].properties (+ required/primaryKey/unique)
  keys                  → primaryKey/primaryKeyPosition (+ unique bei Einzelspalte)
  referential           → schema[0].relationships (from/to, v3.1)
  freshness             → slaProperties[property=latency] (+ element)
  volume.min_rows       → schema[0].quality[metric=rowCount]
  completeness          → property.quality[metric=nullValues, unit=percent]
  not_null              → property.required
  lifecycle             → status · Rest → customProperties (lossless escape hatch)
"""
from __future__ import annotations

from typing import Any

from .compiler import parse_iso_duration

ODCS_API_VERSION = "v3.1.0"


def to_odcs(contract: dict[str, Any]) -> dict[str, Any]:
    if contract.get("kind", "internal_gate") == "internal_gate":
        raise ValueError("Internal gates cannot be exported as ODCS data contracts.")

    g = contract.get("guarantees") or {}
    product = str(contract.get("product") or "")
    dataset = str(contract.get("dataset") or product)

    schema_cols = list((g.get("schema") or {}).get("columns") or [])
    not_null_cols = {c for nn in (g.get("not_null") or []) for c in (nn.get("columns") or [])}
    completeness = {c["column"]: c for c in (g.get("completeness") or []) if c.get("column")}

    pk_cols: list[str] = []
    for key in g.get("keys") or []:
        if key.get("unique"):
            pk_cols = list(key.get("columns") or [])
            break

    fresh = g.get("freshness") or {}
    referential = g.get("referential") or []

    # Spalten-Universum in deterministischer Reihenfolge
    ordered: list[str] = []
    for col in [
        *schema_cols,
        *pk_cols,
        *sorted(not_null_cols),
        *completeness.keys(),
        *[fk for r in referential for fk in (r.get("fk") or [])],
        *([fresh["column"]] if fresh.get("column") else []),
    ]:
        if col and col not in ordered:
            ordered.append(col)

    properties: list[dict[str, Any]] = []
    for col in ordered:
        prop: dict[str, Any] = {"name": col}
        if col in not_null_cols:
            prop["required"] = True
        if col in pk_cols:
            prop["primaryKey"] = True
            prop["primaryKeyPosition"] = pk_cols.index(col) + 1
            if len(pk_cols) == 1:
                prop["unique"] = True
        if col in completeness:
            max_null_pct = round(100.0 - float(completeness[col].get("min_pct", 100)), 4)
            prop["quality"] = [{
                "type": "library",
                "metric": "nullValues",
                "unit": "percent",
                "mustBeLessOrEqualTo": max_null_pct,
            }]
        properties.append(prop)

    schema_obj: dict[str, Any] = {
        "name": dataset,
        "physicalName": dataset,
        "logicalType": "object",
        "properties": properties,
    }

    relationships = []
    for r in referential:
        fk = r.get("fk") or []
        pk = r.get("parent_key") or []
        if len(fk) == 1 and len(pk) == 1 and r.get("parent"):
            relationships.append({
                "from": f"{dataset}.{fk[0]}",
                "to": f"{r['parent']}.{pk[0]}",
            })
    if relationships:
        schema_obj["relationships"] = relationships

    vol = g.get("volume") or {}
    if vol.get("min_rows") is not None:
        schema_obj["quality"] = [{
            "type": "library",
            "metric": "rowCount",
            "mustBeGreaterOrEqualTo": int(vol["min_rows"]),
        }]

    odcs: dict[str, Any] = {
        "apiVersion": ODCS_API_VERSION,
        "kind": "DataContract",
        "id": product,
        "name": product,
        "version": str(contract.get("version") or "0.1.0"),
        "status": str(contract.get("lifecycle") or "draft"),
        "schema": [schema_obj],
    }
    if contract.get("description"):
        odcs["description"] = {"purpose": str(contract["description"])}

    if fresh.get("column") and fresh.get("max_age"):
        seconds = parse_iso_duration(fresh["max_age"])
        if seconds % 3600 == 0:
            value, unit = seconds // 3600, "h"
        else:
            value, unit = seconds, "s"
        odcs["slaProperties"] = [{
            "property": "latency",
            "value": value,
            "unit": unit,
            "element": f"{dataset}.{fresh['column']}",
        }]

    custom = [
        {"property": "owned_by", "value": str(contract.get("owned_by", "platform"))},
        {"property": "signal_kind", "value": str(contract.get("kind", ""))},
        {"property": "sourceSpec", "value": "dq-cockpit/contract-v1"},
    ]
    if (g.get("schema") or {}).get("mode"):
        custom.append({"property": "schemaMode", "value": g["schema"]["mode"]})
    if contract.get("owners"):
        custom.append({"property": "owners", "value": ",".join(contract["owners"])})
    odcs["customProperties"] = custom

    return odcs
