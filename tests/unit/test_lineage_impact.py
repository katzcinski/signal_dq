import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "packages"))

from dq_core.lineage.impact import downstream_impact


def test_downstream_impact_is_transitive_cycle_safe_and_enriched():
    lineage = {
        "nodes": [
            {"id": "B", "label": "Node B", "type": "view", "space": "S1"},
            {"id": "C", "label": "Node C", "type": "analytic-model", "space": "S2"},
        ],
        "edges": [
            {"source": "A", "target": "B"},
            {"source": "B", "target": "C"},
            {"source": "C", "target": "B"},
        ],
    }
    inventory = [
        {
            "technicalName": "B",
            "objectType": "views",
            "owned_by": "platform",
            "owners": ["grp:data-eng"],
            "layer": "Business",
        }
    ]
    contracts = [
        {
            "product": "B",
            "lifecycle": "active",
            "kind": "consumer_contract",
            "version": "1.0.0",
        }
    ]

    impacted = downstream_impact(
        lineage=lineage,
        root="A",
        inventory=inventory,
        contract_index=contracts,
    )

    assert [row["product"] for row in impacted] == ["B", "C"]
    assert impacted[0]["distance"] == 1
    assert impacted[0]["owned_by"] == "platform"
    assert impacted[0]["owners"] == ["grp:data-eng"]
    assert impacted[0]["lifecycle"] == "active"
    assert impacted[1]["distance"] == 2


def test_downstream_impact_respects_depth_limit():
    lineage = {
        "edges": [
            {"source": "A", "target": "B"},
            {"source": "B", "target": "C"},
        ]
    }

    impacted = downstream_impact(lineage=lineage, root="A", max_depth=1)

    assert [row["product"] for row in impacted] == ["B"]
