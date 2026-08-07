"""WS-A regression: der ausgelieferte Demo-Snapshot trägt echte Spalten-Lineage.

Sichert ab, dass ``data/inventory.json`` CSN-``csnProjection`` enthält, sodass
``build_column_lineage`` echte ``computed``-Kanten (inkl. Expression) und die
2-Hop-Impact-Kette in der BUS-Schicht erzeugt — nicht mehr die alten
``direct``/leer-Platzhalter (O3). Erzeugt von ``scripts/seed_column_lineage.py``.
"""

from __future__ import annotations

import json
from pathlib import Path

from dq_core.lineage._column_lineage import build_column_indexes, build_column_lineage

REPO_ROOT = Path(__file__).resolve().parents[2]
INVENTORY = REPO_ROOT / "data" / "inventory.json"


def _objects() -> list[dict]:
    return json.loads(INVENTORY.read_text(encoding="utf-8"))["objects"]


def test_demo_inventory_carries_csn_projection() -> None:
    enriched = [o for o in _objects() if o.get("csnProjection", {}).get("projectionLineage")]
    assert enriched, "kein Objekt mit csnProjection.projectionLineage — Seed-Skript laufen lassen"


def test_demo_yields_computed_edges_with_expression() -> None:
    result = build_column_lineage(_objects())
    computed = [e for e in result.edges if e.edge_type == "computed"]
    assert computed, "keine computed-Kanten — Walker bekam keinen CSN-query-AST"
    assert all(e.expression for e in computed), "computed-Kante ohne Expression"


def test_demo_bus_two_hop_impact_chain() -> None:
    """BUS_05.BUS_COL_03 → BUS_01.BUS_COL_03 → BUS_02.BUS_COL_03 (transitiv)."""
    idx = build_column_indexes(build_column_lineage(_objects()))

    bus01 = idx["DEMO_BUS_01"]["BUS_COL_03"]
    up = {(u["object"], u["column"]) for u in bus01["upstream"]}
    down = {(d["object"], d["column"]) for d in bus01["downstream"]}
    assert ("DEMO_BUS_05", "BUS_COL_03") in up
    assert ("DEMO_BUS_02", "BUS_COL_03") in down


def test_demo_arithmetic_emits_edge_per_source_column() -> None:
    """``b3.BUS_COL_02 + b4.BUS_COL_03`` → je eine Kante pro Quellspalte."""
    result = build_column_lineage(_objects())
    sources = {
        (e.source_object, e.source_column)
        for e in result.edges
        if e.target_object == "DEMO_BUS_01" and e.target_column == "BUS_COL_04"
    }
    assert ("DEMO_BUS_03", "BUS_COL_02") in sources
    assert ("DEMO_BUS_04", "BUS_COL_03") in sources
