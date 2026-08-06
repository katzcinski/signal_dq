import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "packages"))

from dq_core.obs.rca import analyze_incident


def test_upstream_candidate_with_shorter_distance_wins():
    lineage = {
        "edges": [
            {"source": "SRC_A", "target": "MID"},
            {"source": "MID", "target": "TARGET"},
            {"source": "SRC_B", "target": "TARGET"},
        ]
    }
    failures = [
        {"dataset": "SRC_A", "started_at": "2026-06-29T09:55:00+00:00", "severity": "critical", "check_type": "schema"},
        {"dataset": "SRC_B", "started_at": "2026-06-29T09:55:00+00:00", "severity": "critical", "check_type": "schema"},
    ]

    out = analyze_incident(
        incident={"product": "TARGET", "opened_at": "2026-06-29T10:00:00+00:00"},
        run={"dataset": "TARGET", "started_at": "2026-06-29T10:00:00+00:00"},
        lineage=lineage,
        contract_index=[],
        recent_failures=failures,
        prior_incidents=[],
    )

    assert out["probable_cause_object"] == "SRC_B"


def test_blast_radius_splits_contracts_and_internal_gates():
    lineage = {"edges": [{"source": "SRC", "target": "A"}, {"source": "A", "target": "B"}]}
    index = [
        {"product": "A", "lifecycle": "active", "kind": "consumer_contract", "version": "1.0.0"},
        {"product": "B", "lifecycle": "active", "kind": "internal_gate", "version": "0.1.0"},
    ]

    out = analyze_incident(
        incident={"product": "SRC", "opened_at": "2026-06-29T10:00:00+00:00"},
        run={"dataset": "SRC", "started_at": "2026-06-29T10:00:00+00:00"},
        lineage=lineage,
        contract_index=index,
        recent_failures=[],
        prior_incidents=[],
    )

    assert [x["product"] for x in out["affected_contracts"]] == ["A"]
    assert [x["product"] for x in out["affected_internal_gates"]] == ["B"]
