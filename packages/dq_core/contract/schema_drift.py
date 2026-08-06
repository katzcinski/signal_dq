# [ENGINE-ADJACENT] frameworkfrei (G7) — kein FastAPI/Flask/Starlette-Import.
"""Shift-Left-Schema-Drift-Detektor (Konzept §A).

Vergleicht das **materialisierte Quellschema** (aus dem Extrakt, `inventory.json`,
je Objekt `columns[].{name,type,key,nullable}`) gegen die **`schema`-Garantie des
aktiven Contracts**. Das Versprechen ist die Referenz, nicht der vorige Snapshot.

Reine Metadaten-Diffs — **kein** SQL gegen HANA, kein Datasphere-Write. Die
Severity-/Konsequenz-Zuordnung nach `kind` (Contract-Breach vs. Engineering-Signal)
liegt in der API-Schicht, nicht hier: dieser Modul bleibt kategorie-agnostisch.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any

# Diff-Kategorien (Konzept §A.2).
COLUMN_ADDED = "column_added"
COLUMN_REMOVED = "column_removed"
TYPE_CHANGED = "type_changed"
NULLABLE_RELAXED = "nullable_relaxed"
KEY_CHANGED = "key_changed"


@dataclass
class DriftFinding:
    category: str
    column: str
    before: str = ""   # was der Contract verspricht
    after: str = ""    # was die Quelle tatsächlich tut
    breaking: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# Grobe Typ-Familien — deklarierter Contract-Typ vs. Quelltyp (cds.*/HANA) werden
# auf eine gemeinsame Familie normalisiert, damit z. B. cds.String ↔ string matcht.
_TYPE_FAMILY = {
    # Contract-deklarierte Typen
    "string": "string", "text": "string", "varchar": "string", "nvarchar": "string",
    "char": "string", "nchar": "string", "clob": "string", "nclob": "string",
    "integer": "integer", "int": "integer", "bigint": "integer", "smallint": "integer",
    "tinyint": "integer", "long": "integer",
    "decimal": "decimal", "numeric": "decimal", "double": "decimal", "real": "decimal",
    "float": "decimal", "smalldecimal": "decimal",
    "boolean": "boolean", "bool": "boolean",
    "date": "date",
    "time": "time",
    "timestamp": "timestamp", "datetime": "timestamp", "seconddate": "timestamp",
    "binary": "binary", "varbinary": "binary", "blob": "binary",
}


def _truthy(value: Any) -> bool:
    """Inventar liefert Flags teils als String ('True'/'') — robust coercen."""
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"true", "1", "yes", "y", "x"}


def normalize_type(raw: Any) -> str:
    """cds.String / HANA NVARCHAR(20) / 'integer' → grobe Familie ('string', …)."""
    s = str(raw or "").strip().lower()
    if not s:
        return ""
    if s.startswith("cds."):
        s = s[4:]
    # Längen-/Präzisions-Suffix abschneiden: nvarchar(20) → nvarchar
    s = s.split("(")[0].strip()
    return _TYPE_FAMILY.get(s, s)


def _index_source(source_columns: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Quell-Spalten auf {name: {type, key, nullable}} normalisieren."""
    out: dict[str, dict[str, Any]] = {}
    for col in source_columns or []:
        name = str(col.get("name") or col.get("column") or "").strip()
        if not name:
            continue
        out[name] = {
            "type": normalize_type(col.get("type") or col.get("data_type")),
            "key": _truthy(col.get("key")),
            "nullable": _truthy(col.get("nullable")),
        }
    return out


def detect_schema_drift(
    contract: dict[str, Any],
    source_columns: list[dict[str, Any]],
) -> list[DriftFinding]:
    """Diff der `schema`-Garantie gegen das materialisierte Quellschema.

    `source_columns` ist die `columns`-Liste des Inventar-Objekts. Liefert eine
    deterministisch sortierte Liste von `DriftFinding`. Trägt der Contract keine
    `schema`-Garantie, gibt es nichts zu prüfen (leere Liste).
    """
    schema_g = ((contract or {}).get("guarantees") or {}).get("schema") or {}
    expected: list[str] = list(schema_g.get("columns") or [])
    if not expected:
        return []
    closed = (schema_g.get("mode") or "closed") == "closed"
    types: dict[str, Any] = schema_g.get("types") or {}

    source = _index_source(source_columns)
    expected_set = set(expected)
    findings: list[DriftFinding] = []

    # Entfernte Spalten — immer breaking (Versprechen nicht erfüllbar).
    for col in expected:
        if col not in source:
            findings.append(DriftFinding(COLUMN_REMOVED, col, before=col, after="", breaking=True))

    # Zusätzliche Spalten — breaking nur im closed-mode.
    for col in sorted(source.keys()):
        if col not in expected_set:
            findings.append(
                DriftFinding(COLUMN_ADDED, col, before="", after=col, breaking=closed)
            )

    # Typ-/Nullability-/Key-Drift — nur für deklarierte (typisierte) Spalten,
    # die in der Quelle vorhanden sind.
    for col, spec in types.items():
        if col not in source:
            continue  # bereits als column_removed erfasst
        src = source[col]
        spec = spec or {}

        declared_type = normalize_type(spec.get("type"))
        if declared_type and src["type"] and declared_type != src["type"]:
            findings.append(
                DriftFinding(TYPE_CHANGED, col, before=declared_type, after=src["type"], breaking=True)
            )

        if "nullable" in spec and not _truthy(spec.get("nullable")) and src["nullable"]:
            # NOT NULL versprochen, Quelle erlaubt NULL → Aufweichung, breaking.
            findings.append(
                DriftFinding(NULLABLE_RELAXED, col, before="NOT NULL", after="NULLABLE", breaking=True)
            )

        if "key" in spec and _truthy(spec.get("key")) != src["key"]:
            findings.append(
                DriftFinding(
                    KEY_CHANGED, col,
                    before="key" if _truthy(spec.get("key")) else "non-key",
                    after="key" if src["key"] else "non-key",
                    breaking=True,
                )
            )

    findings.sort(key=lambda f: (f.category, f.column))
    return findings


def diff_snapshots(
    before_columns: list[dict[str, Any]],
    after_columns: list[dict[str, Any]],
) -> list[DriftFinding]:
    """Diff zweier materialisierter Quellschemata (Snapshot → Snapshot).

    Grundlage des Schema-Evolution-Screens (A2/UX-N9): welche Spalten kamen
    zwischen zwei Extrakten hinzu, fielen weg oder wechselten Typ/Key. Im
    Gegensatz zu `detect_schema_drift` gibt es hier **keine** Contract-Referenz —
    `breaking` bleibt daher immer ``False``; die Contract-Bewertung liefert die
    parallel persistierte Drift-Historie (`dq_schema_drift`).
    """
    before = _index_source(before_columns)
    after = _index_source(after_columns)
    findings: list[DriftFinding] = []

    for col in sorted(before.keys()):
        if col not in after:
            findings.append(DriftFinding(COLUMN_REMOVED, col, before=col, after=""))

    for col in sorted(after.keys()):
        if col not in before:
            findings.append(DriftFinding(COLUMN_ADDED, col, before="", after=col))

    for col in sorted(before.keys() & after.keys()):
        b, a = before[col], after[col]
        if b["type"] and a["type"] and b["type"] != a["type"]:
            findings.append(DriftFinding(TYPE_CHANGED, col, before=b["type"], after=a["type"]))
        if not b["nullable"] and a["nullable"]:
            findings.append(
                DriftFinding(NULLABLE_RELAXED, col, before="NOT NULL", after="NULLABLE")
            )
        if b["key"] != a["key"]:
            findings.append(
                DriftFinding(
                    KEY_CHANGED, col,
                    before="key" if b["key"] else "non-key",
                    after="key" if a["key"] else "non-key",
                )
            )

    findings.sort(key=lambda f: (f.category, f.column))
    return findings


def summarize_drift(findings: list[DriftFinding]) -> dict[str, Any]:
    """Report-Kopf: Zähler + breaking-Flag für die API/UI."""
    breaking = [f for f in findings if f.breaking]
    by_category: dict[str, int] = {}
    for f in findings:
        by_category[f.category] = by_category.get(f.category, 0) + 1
    return {
        "total": len(findings),
        "breaking": len(breaking),
        "has_breaking": bool(breaking),
        "by_category": by_category,
    }


def columns_hash(source_columns: list[dict[str, Any]]) -> str:
    """Stabiler Hash des Quellschemas für den Schnell-Vergleich gleich/ungleich."""
    norm = sorted(
        (name, spec["type"], spec["key"], spec["nullable"])
        for name, spec in _index_source(source_columns).items()
    )
    payload = json.dumps(norm, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
