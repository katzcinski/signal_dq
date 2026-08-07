"""Reichert den Demo-Snapshot um echte Spalten-Lineage an (WS-A / O3).

Hintergrund: Der CQN-Walker (``dq_core.lineage._csn_reconstructor`` +
``_column_lineage``) ist implementiert und unit-getestet, aber der ausgelieferte
Demo-Snapshot trug bisher keinen CSN-``query``-AST — daher nur Seed-Platzhalter
(alle ``direct``, leere Expression) in ``data/lineage.json``.

Dieses Skript definiert realistische CSN-Query-Bäume für ausgewählte Demo-Views
(deckungsgleich zu den vorhandenen Objekt-Kanten), schickt sie durch den **echten**
Walker und schreibt:

* ``data/inventory.json`` — die betroffenen Objekte erhalten ``query`` (roher CSN-
  AST) + ``csnProjection`` (assembliert, exakt das, was ein echter Extract trüge).
* ``data/lineage.json`` — ``columnEdges`` + ``columnEdgeMeta`` neu erzeugt aus
  ``build_column_lineage``; die Objekt-Knoten/-Kanten bleiben unverändert.

Idempotent: erneuter Lauf ergibt byte-identische Ausgabe.

Aufruf:  ``python scripts/seed_column_lineage.py``
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packages"))

from dq_core.lineage._csn_reconstructor import extract_query_details  # noqa: E402
from dq_core.lineage._column_lineage import build_column_lineage  # noqa: E402

INVENTORY = ROOT / "data" / "inventory.json"
LINEAGE = ROOT / "data" / "lineage.json"


# --- CSN helpers ------------------------------------------------------------

def col(source_alias: str, column: str, out: str) -> dict:
    """Direkter Passthrough: ``alias.column AS out``."""
    return {"ref": [source_alias, column], "as": out}


def func(name: str, refs: list[tuple[str, str]], out: str) -> dict:
    """Berechnete Spalte über eine Funktion, z. B. ``SUM(b5.BUS_COL_03)``."""
    return {"func": name, "args": [{"ref": [a, c]} for a, c in refs], "as": out}


def arith(a: tuple[str, str], op: str, b: tuple[str, str], out: str) -> dict:
    """Berechnete Spalte über Arithmetik, z. B. ``b3.X + b4.Y``."""
    return {"xpr": [{"ref": list(a)}, op, {"ref": list(b)}], "as": out}


def from_one(obj: str, alias: str) -> dict:
    return {"ref": [obj], "as": alias}


def from_join(kind: str, sources: list[tuple[str, str]], on: list) -> dict:
    return {
        "join": kind,
        "args": [from_one(obj, alias) for obj, alias in sources],
        "on": on,
    }


def select(from_node: dict, columns: list[dict]) -> dict:
    return {"query": {"SELECT": {"from": from_node, "columns": columns}}}


# --- CSN-Query-Definitionen je View ----------------------------------------
# Deckungsgleich zu den Objekt-Kanten in data/lineage.json. Mix aus direct +
# computed; die BUS-Kette (BUS_03/04/05 → BUS_01 → BUS_02) liefert die 2-Hop-
# Impact-Strecke für UX-N7.

CSN_QUERIES: dict[str, dict] = {
    # SRC_01 → SRC_02 / SRC_03
    "DEMO_SRC_02": select(
        from_one("DEMO_SRC_01", "s"),
        [
            col("s", "SRC_COL_01", "SRC_COL_01"),
            col("s", "SRC_COL_02", "SRC_COL_02"),
            func("UPPER", [("s", "SRC_COL_03")], "SRC_COL_03"),
            col("s", "SRC_COL_04", "SRC_COL_04"),
        ],
    ),
    "DEMO_SRC_03": select(
        from_one("DEMO_SRC_01", "s"),
        [
            col("s", "SRC_COL_01", "SRC_COL_01"),
            func("TRIM", [("s", "SRC_COL_02")], "SRC_COL_02"),
            col("s", "SRC_COL_05", "SRC_COL_03"),
        ],
    ),
    # HARM_01 → HARM_02
    "DEMO_HARM_02": select(
        from_one("DEMO_HARM_01", "h"),
        [
            col("h", "HARM_COL_01", "HARM_COL_01"),
            {"xpr": [{"ref": ["h", "HARM_COL_02"]}, "*", {"val": 100}], "as": "HARM_COL_02"},
            col("h", "HARM_COL_03", "HARM_COL_03"),
            func("COALESCE", [("h", "HARM_COL_04")], "HARM_COL_04"),
        ],
    ),
    # BUS_03/04/05 → BUS_01  (Join + Aggregat)
    "DEMO_BUS_01": select(
        from_join(
            "inner",
            [("DEMO_BUS_03", "b3"), ("DEMO_BUS_04", "b4"), ("DEMO_BUS_05", "b5")],
            [{"ref": ["b3", "BUS_COL_01"]}, "=", {"ref": ["b4", "BUS_COL_01"]}],
        ),
        [
            col("b3", "BUS_COL_01", "BUS_COL_01"),
            col("b4", "BUS_COL_02", "BUS_COL_02"),
            func("SUM", [("b5", "BUS_COL_03")], "BUS_COL_03"),
            arith(("b3", "BUS_COL_02"), "+", ("b4", "BUS_COL_03"), "BUS_COL_04"),
        ],
    ),
    # BUS_01 → BUS_02  (2. Hop: hängt an den BUS_01-Spalten oben)
    "DEMO_BUS_02": select(
        from_one("DEMO_BUS_01", "b1"),
        [
            col("b1", "BUS_COL_01", "BUS_COL_01"),
            func("ROUND", [("b1", "BUS_COL_03")], "BUS_COL_03"),
            col("b1", "BUS_COL_04", "BUS_COL_04"),
        ],
    ),
}


def _query_sources(alias_map: dict[str, str]) -> list[str]:
    return list(dict.fromkeys(alias_map.values()))


def _assemble_projection(obj_def: dict) -> dict:
    details = extract_query_details(obj_def)
    return {
        "projectionLineage": details.get("projectionLineage", []),
        "aliasMap": details.get("aliasMap", {}),
        "joinDetails": details.get("joinDetails", []),
        "querySources": _query_sources(details.get("aliasMap", {})),
    }


def main() -> int:
    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    lineage = json.loads(LINEAGE.read_text(encoding="utf-8"))

    enriched = 0
    for obj in inventory["objects"]:
        name = obj.get("technicalName", "")
        csn = CSN_QUERIES.get(name)
        if not csn:
            continue
        obj["query"] = csn["query"]
        obj["csnProjection"] = _assemble_projection(csn)
        enriched += 1

    result = build_column_lineage(inventory["objects"]).serialize()
    lineage["columnEdges"] = result["columnEdges"]
    lineage["columnEdgeMeta"] = result["columnEdgeMeta"]

    # deterministische, lesbare Ausgabe
    INVENTORY.write_text(
        json.dumps(inventory, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    LINEAGE.write_text(
        json.dumps(lineage, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    edges = result["columnEdges"]
    computed = [e for e in edges if e["edgeType"] == "computed"]
    direct = [e for e in edges if e["edgeType"] == "direct"]
    print(
        f"enriched views: {enriched} | columnEdges: {len(edges)} "
        f"(direct={len(direct)}, computed={len(computed)})"
    )
    print("coverage:", json.dumps(result["columnEdgeMeta"]["coverage"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
