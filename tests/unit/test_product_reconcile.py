from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parents[2] / "packages"))

from dq_core.product.model import OutputPort, Product
from dq_core.product.reconcile import reconcile
from dq_core.product.walk import ProductAggregate


def _product(name: str, owners: list[str], ports: list[str]) -> Product:
    return Product(name, owners, [OutputPort(port) for port in ports], [])


def _agg(product: Product, interior: set[str] | None = None) -> ProductAggregate:
    return ProductAggregate(product, interior or set(), [], [], [], [])


def test_dangling_port_reports_missing_contract_internal_gate_and_missing_node():
    product = _product("p", ["team-a"], ["OUT", "GATE", "MISSING_NODE"])
    findings = reconcile(
        [_agg(product)],
        {"OUT": ["p"], "GATE": ["p"], "MISSING_NODE": ["p"]},
        {},
        [product],
        {"GATE": {"kind": "internal_gate", "dataset": "GATE"}},
        {"OUT", "GATE"},
    )

    by_object = {finding.object_id: finding for finding in findings}
    assert by_object["OUT"].finding_type == "dangling_port"
    assert "no governance contract" in by_object["OUT"].detail
    assert "internal gate" in by_object["GATE"].detail
    assert "no lineage node" in by_object["MISSING_NODE"].detail


def test_contested_port_and_interior_findings_are_reported_per_product():
    p1 = _product("p1", ["team-a"], ["SHARED"])
    p2 = _product("p2", ["team-b"], ["SHARED"])

    findings = reconcile(
        [_agg(p1, {"CORE"}), _agg(p2, {"CORE"})],
        {"SHARED": ["p1", "p2"]},
        {},
        [p1, p2],
        {"SHARED": {"kind": "provider_contract"}},
        {"SHARED", "CORE"},
    )

    contested = [finding for finding in findings if finding.finding_type == "contested"]
    assert {(finding.product, finding.scope, finding.object_id) for finding in contested} == {
        ("p1", "port", "SHARED"),
        ("p2", "port", "SHARED"),
        ("p1", "interior", "CORE"),
        ("p2", "interior", "CORE"),
    }


def test_boundary_leak_is_cross_owner_only_and_ignores_declared_ports():
    p1 = _product("p1", ["team-a"], ["OUT1"])
    p2 = _product("p2", ["team-b"], ["OUT2"])
    p3 = _product("p3", ["team-a"], ["OUT3"])

    findings = reconcile(
        [_agg(p1, {"CORE", "OUT1"}), _agg(p2), _agg(p3)],
        {"OUT1": ["p1"], "OUT2": ["p2"], "OUT3": ["p3"]},
        {"CORE": ["OUT2"], "OUT1": ["OUT2"], "SAFE": ["OUT3"]},
        [p1, p2, p3],
        {"OUT1": {"kind": "provider_contract"}, "OUT2": {"kind": "provider_contract"}},
        {"CORE", "OUT1", "OUT2", "OUT3"},
    )

    leaks = [finding for finding in findings if finding.finding_type == "boundary_leak"]
    assert [(finding.product, finding.object_id) for finding in leaks] == [("p1", "CORE")]
