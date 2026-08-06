from dq_core.lineage.loader import get_coverage


def test_get_coverage_annotates_kind():
    nodes = [{"id": "ds1"}, {"id": "ds2"}, {"id": "ds3"}]
    statuses = [
        {"dataset": "ds1", "status": "pass"},
        {"dataset": "ds2", "status": "pass"},
    ]
    contracted = ["ds1", "ds2"]

    result = get_coverage(
        nodes,
        statuses,
        contracted,
        gate_products={"ds1"},
        contract_products={"ds2"},
    )
    ds1 = next(n for n in result if n["id"] == "ds1")
    ds2 = next(n for n in result if n["id"] == "ds2")
    ds3 = next(n for n in result if n["id"] == "ds3")

    assert ds1["has_internal_gate"] is True
    assert ds1["has_boundary_contract"] is False
    assert ds2["has_internal_gate"] is False
    assert ds2["has_boundary_contract"] is True
    assert ds3["has_internal_gate"] is False
    assert ds3["coverage_flag"] == "\u25b2"
