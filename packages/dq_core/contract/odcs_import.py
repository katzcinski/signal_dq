"""ODCS-3.1-Import (E1, Source-of-Truth-Modus „Entropy authort → Signal erzwingt"):
Open Data Contract Standard (Bitol / LF AI & Data) → kanonisches Contract-Schema v1.

Gegenstück zu `odcs_export.to_odcs()`. Der Adapter ist die *einzige* fehlende
Naht, um einen Kunden zu bedienen, der bereits auf einem externen Marktplatz
(z. B. Entropy Data) auf ODCS standardisiert hat: Signal konsumiert dessen
ODCS-Dokument als Eingabe, fährt es gegen HANA und erzwingt es.

Leitregeln (unverändert):
  - **SQL-frei (G1).** Es werden ausschließlich *Garantien* rekonstruiert, nie
    SQL. Eine ODCS-`quality`-Regel mit `engine`/`implementation` (SodaCL/SQL)
    wird **nicht** übernommen, sondern verworfen und im Report als `dropped`
    ausgewiesen — Signals Compiler bleibt der einzige SQL-Erzeuger.
  - **Schema erst zur Laufzeit (G2).** `physicalName`/Server werden ignoriert;
    das Contract trägt nur `dataset`, das Environment bindet das Schema.
  - **Verlustfrei-Report.** Alles, was nicht auf eine Garantie-Familie abbildet,
    landet in `dropped`, damit der Aufrufer sieht, was der Marktplatz sagte,
    Signal aber (noch) nicht erzwingt — kein stilles Vortäuschen.

`from_odcs` ist rein (framework-frei, G7) und deterministisch. Der Output ist
ein Contract-*Dict*; die Validierung (G1) übernimmt der Aufrufer über
`validate_contract`, bevor etwas persistiert wird.
"""
from __future__ import annotations

import re
from typing import Any

# Identifier-Sicherheit (S2) — muss zum Validator-Regex passen. Namen, die das
# verletzen (z. B. `order-id`), werden nicht geraten/umgeschrieben, sondern als
# Verlust ausgewiesen.
_SAFE_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# ODCS-`status` → Signal-Lifecycle. Alles Unbekannte fällt konservativ auf
# `draft`, damit ein Import nie versehentlich als zertifiziert gilt.
_STATUS_TO_LIFECYCLE = {
    "draft": "draft",
    "active": "active",
    "deprecated": "deprecated",
    "retired": "deprecated",
}

_VALID_KINDS = {"internal_gate", "consumer_contract", "provider_contract"}


class OdcsImportResult:
    """Ergebnis eines Imports: der rekonstruierte Contract plus ein ehrlicher
    Bericht, was nicht abgebildet werden konnte."""

    __slots__ = ("contract", "dropped", "warnings")

    def __init__(self, contract: dict[str, Any], dropped: list[str], warnings: list[str]):
        self.contract = contract
        self.dropped = dropped
        self.warnings = warnings

    def as_dict(self) -> dict[str, Any]:
        return {"contract": self.contract, "dropped": self.dropped, "warnings": self.warnings}


def _first_schema_object(odcs: dict[str, Any]) -> dict[str, Any]:
    schema = odcs.get("schema")
    if isinstance(schema, list) and schema:
        first = schema[0]
        return first if isinstance(first, dict) else {}
    if isinstance(schema, dict):
        return schema
    return {}


def _custom_props(odcs: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for entry in odcs.get("customProperties") or []:
        if isinstance(entry, dict) and entry.get("property") is not None:
            out[str(entry["property"])] = entry.get("value")
    return out


def _iso_duration_from_sla(value: Any, unit: str) -> str | None:
    """SLA-Latenz (value+unit) → ISO-8601-Duration, wie der Validator sie erwartet."""
    try:
        n = int(value)
    except (TypeError, ValueError):
        return None
    if n < 0:
        return None
    unit = (unit or "").lower()
    if unit in ("d", "day", "days"):
        return f"P{n}D"
    if unit in ("h", "hour", "hours"):
        return f"PT{n}H"
    if unit in ("m", "min", "minute", "minutes"):
        return f"PT{n}M"
    if unit in ("s", "sec", "second", "seconds", ""):
        return f"PT{n}S"
    return None


def from_odcs(odcs: dict[str, Any], *, default_kind: str = "consumer_contract") -> OdcsImportResult:
    """Rekonstruiere ein Signal-Contract-Dict aus einem ODCS-3.1-Dokument.

    `default_kind` greift, wenn das Dokument keine `signal_kind`-customProperty
    trägt; da ODCS eine *Vereinbarung an einer Parteigrenze* ist, ist
    `consumer_contract` der ehrliche Default (nie `internal_gate`).
    """
    if not isinstance(odcs, dict):
        raise ValueError("ODCS document must be a mapping.")

    dropped: list[str] = []
    warnings: list[str] = []
    custom = _custom_props(odcs)

    schema_obj = _first_schema_object(odcs)
    dataset_raw = (
        odcs.get("id")
        or schema_obj.get("name")
        or schema_obj.get("physicalName")
        or odcs.get("name")
        or ""
    )
    product_raw = odcs.get("id") or odcs.get("name") or dataset_raw

    product = str(product_raw or "").strip()
    dataset = str(schema_obj.get("name") or dataset_raw or product).strip()
    if not _SAFE_IDENT.match(product):
        raise ValueError(
            f"ODCS id/name {product!r} is not a safe Signal identifier "
            r"(^[A-Za-z_][A-Za-z0-9_]*$) — rename before import."
        )
    if not _SAFE_IDENT.match(dataset):
        # Dataset muss ein SQL-Identifier sein; kein Raten.
        warnings.append(f"dataset {dataset!r} not identifier-safe; falling back to product name.")
        dataset = product

    # ── Spalten & Property-Metadaten ──────────────────────────────────────────
    properties = schema_obj.get("properties") or []
    columns: list[str] = []
    not_null_cols: list[str] = []
    pk_positions: list[tuple[int, str]] = []
    completeness: list[dict[str, Any]] = []

    for prop in properties:
        if not isinstance(prop, dict):
            continue
        name = str(prop.get("name") or "").strip()
        if not name:
            continue
        if not _SAFE_IDENT.match(name):
            dropped.append(f"property {name!r}: not identifier-safe (S2), column skipped.")
            continue
        columns.append(name)
        if prop.get("required") is True:
            not_null_cols.append(name)
        if prop.get("primaryKey") is True:
            pos = prop.get("primaryKeyPosition")
            try:
                pos_i = int(pos)
            except (TypeError, ValueError):
                pos_i = len(pk_positions) + 1
            pk_positions.append((pos_i, name))
        # Property-level quality → completeness (nullValues ≤ x %)
        for q in prop.get("quality") or []:
            if not isinstance(q, dict):
                continue
            metric = str(q.get("metric") or "").lower()
            if metric in ("nullvalues", "null_values") and str(q.get("unit", "")).lower() == "percent":
                bound = q.get("mustBeLessOrEqualTo")
                try:
                    min_pct = round(100.0 - float(bound), 4)
                    completeness.append({"column": name, "min_pct": min_pct})
                except (TypeError, ValueError):
                    dropped.append(f"property {name!r} quality/nullValues: unparseable bound {bound!r}.")
            else:
                dropped.append(
                    f"property {name!r} quality[{metric or '?'}]: no SQL-free guarantee mapping — dropped (G1)."
                )

    guarantees: dict[str, Any] = {}
    if columns:
        schema_mode = custom.get("schemaMode")
        schema_g: dict[str, Any] = {"columns": columns}
        if schema_mode in ("closed", "open"):
            schema_g["mode"] = schema_mode
        guarantees["schema"] = schema_g

    # ── Keys (primaryKey → keys[unique]) ──────────────────────────────────────
    if pk_positions:
        pk_cols = [name for _, name in sorted(pk_positions, key=lambda t: t[0])]
        guarantees["keys"] = [{"columns": pk_cols, "unique": True}]

    # ── not_null ──────────────────────────────────────────────────────────────
    if not_null_cols:
        guarantees["not_null"] = [{"columns": not_null_cols}]

    # ── completeness ──────────────────────────────────────────────────────────
    if completeness:
        guarantees["completeness"] = completeness

    # ── referential (schema.relationships) ────────────────────────────────────
    referential: list[dict[str, Any]] = []
    for rel in schema_obj.get("relationships") or []:
        if not isinstance(rel, dict):
            continue
        frm = str(rel.get("from") or "")
        to = str(rel.get("to") or "")
        # Format: "<dataset>.<col>" → "<parent>.<parent_key>"
        fk = frm.split(".")[-1] if "." in frm else frm
        parent = to.split(".")[0] if "." in to else ""
        parent_key = to.split(".")[-1] if "." in to else ""
        if fk and parent and parent_key and all(_SAFE_IDENT.match(x) for x in (fk, parent, parent_key)):
            referential.append({"fk": [fk], "parent": parent, "parent_key": [parent_key]})
        else:
            dropped.append(f"relationship {frm!r}→{to!r}: not identifier-safe or incomplete — dropped.")
    if referential:
        guarantees["referential"] = referential

    # ── volume (schema-level quality rowCount) ────────────────────────────────
    for q in schema_obj.get("quality") or []:
        if not isinstance(q, dict):
            continue
        metric = str(q.get("metric") or "").lower()
        if metric == "rowcount" and q.get("mustBeGreaterOrEqualTo") is not None:
            try:
                guarantees["volume"] = {"min_rows": int(q["mustBeGreaterOrEqualTo"])}
            except (TypeError, ValueError):
                dropped.append(f"schema quality/rowCount: unparseable bound {q.get('mustBeGreaterOrEqualTo')!r}.")
        elif metric and metric != "rowcount":
            dropped.append(f"schema quality[{metric}]: no SQL-free guarantee mapping — dropped (G1).")

    # ── freshness (slaProperties latency) ─────────────────────────────────────
    for sla in odcs.get("slaProperties") or []:
        if not isinstance(sla, dict):
            continue
        if str(sla.get("property") or "").lower() != "latency":
            dropped.append(f"slaProperty {sla.get('property')!r}: no freshness mapping — dropped.")
            continue
        element = str(sla.get("element") or "")
        col = element.split(".")[-1] if "." in element else element
        max_age = _iso_duration_from_sla(sla.get("value"), str(sla.get("unit", "")))
        if col and _SAFE_IDENT.match(col) and max_age:
            guarantees["freshness"] = {"column": col, "max_age": max_age}
        else:
            dropped.append(f"slaProperty latency on {element!r}: no identifier-safe column/duration — dropped.")

    # ── Contract-Mantel ───────────────────────────────────────────────────────
    kind = custom.get("signal_kind") or default_kind
    # ODCS ist per Definition eine Parteigrenze — nie ein internes Gate; ein
    # unbekannter Wert fällt ebenfalls konservativ auf consumer_contract.
    if kind == "internal_gate":
        warnings.append("signal_kind=internal_gate on an ODCS import is contradictory; using consumer_contract.")
        kind = "consumer_contract"
    elif kind not in _VALID_KINDS:
        kind = "consumer_contract"

    owned_by = custom.get("owned_by")
    if owned_by not in ("platform", "product"):
        owned_by = "platform"

    owners_raw = custom.get("owners")
    owners = [o.strip() for o in str(owners_raw).split(",") if o.strip()] if owners_raw else []

    version = str(odcs.get("version") or "").strip()
    if not re.match(r"^\d+\.\d+\.\d+$", version):
        warnings.append(f"version {version or '(none)'} not SemVer; defaulting to 1.0.0.")
        version = "1.0.0"

    lifecycle = _STATUS_TO_LIFECYCLE.get(str(odcs.get("status") or "").lower(), "draft")

    contract: dict[str, Any] = {
        "product": product,
        "kind": kind,
        "dataset": dataset,
        "owned_by": owned_by,
        "version": version,
        # Import ergibt IMMER einen Draft — Zertifizierung ist ein bewusster Akt
        # im Cockpit, kein Nebeneffekt des Imports (spiegelt PUT-Semantik).
        "lifecycle": "draft",
        "guarantees": guarantees,
    }
    if owners:
        contract["owners"] = owners
    desc = odcs.get("description")
    if isinstance(desc, dict) and desc.get("purpose"):
        contract["description"] = str(desc["purpose"])
    elif isinstance(desc, str) and desc:
        contract["description"] = desc

    if lifecycle != "draft":
        warnings.append(
            f"ODCS status implied lifecycle={lifecycle!r}; import is stored as draft — "
            "certify explicitly to activate."
        )
    if not guarantees:
        warnings.append("No mappable guarantees found — the imported draft compiles to zero checks.")

    return OdcsImportResult(contract=contract, dropped=dropped, warnings=warnings)
