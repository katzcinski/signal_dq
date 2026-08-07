from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parents[2] / "packages"))

from dq_core.product.health import own_health, upstream_risk
from dq_core.product.model import InboundDep, OutputPort, Product
from dq_core.product.walk import ProductAggregate


class FakeStore:
    def __init__(self, rows: dict[str, dict]):
        self.rows = rows

    def get_compliance(self, product: str):
        return self.rows.get(product)


def _product(name: str, ports: list[str], inbound: list[InboundDep] | None = None) -> Product:
    return Product(name, ["team-a"], [OutputPort(port) for port in ports], inbound or [])


def _agg(product: Product) -> ProductAggregate:
    return ProductAggregate(product, set(), [], [], [], [])


def _contract(lifecycle: str = "active", kind: str = "provider_contract"):
    return {"kind": kind, "lifecycle": lifecycle, "version": "1.0.0"}


def test_own_health_returns_worst_active_governance_status():
    product = _product("p", ["A", "B", "C"])
    store = FakeStore({
        "A": {"compliance": "pass"},
        "B": {"compliance": "fail"},
        "C": {"compliance": "critical"},
    })

    assert own_health(_agg(product), {"A": _contract(), "B": _contract(), "C": _contract()}, store) == "critical"


def test_own_health_excludes_deprecated_draft_and_internal_gate_ports():
    product = _product("p", ["ACTIVE", "DEPRECATED", "DRAFT", "GATE"])
    store = FakeStore({
        "ACTIVE": {"compliance": "compliant"},
        "DEPRECATED": {"compliance": "critical"},
        "DRAFT": {"compliance": "critical"},
        "GATE": {"compliance": "critical"},
    })
    contracts = {
        "ACTIVE": _contract("active"),
        "DEPRECATED": _contract("deprecated"),
        "DRAFT": _contract("draft"),
        "GATE": _contract("active", "internal_gate"),
    }

    assert own_health(_agg(product), contracts, store) == "pass"


def test_own_health_empty_governance_set_returns_unknown():
    product = _product("p", ["A"])

    assert own_health(_agg(product), {"A": _contract("draft")}, FakeStore({})) == "unknown"


def test_upstream_risk_uses_worst_upstream_port_and_flags_breach():
    upstream = _product("up", ["U1", "U2"])
    consumer = _product("consumer", ["OUT"], [InboundDep("up", "1.2.0")])
    store = FakeStore({
        "U1": {"compliance": "compliant", "contract_version": "1.2.1"},
        "U2": {"compliance": "breached", "contract_version": "1.2.0"},
    })

    [entry] = upstream_risk(_agg(consumer), [consumer, upstream], {}, store)

    assert entry.compliance == "breached"
    assert entry.current_version == "1.2.0"
    assert entry.upstream_breach is True
    assert entry.version_drift is False


def test_upstream_risk_flags_version_drift_without_contaminating_own_health():
    upstream = _product("up", ["U1"])
    consumer = _product("consumer", ["OUT"], [InboundDep("up", "1.2.0")])
    store = FakeStore({
        "OUT": {"compliance": "compliant", "contract_version": "2.0.0"},
        "U1": {"compliance": "compliant", "contract_version": "1.2.1"},
    })

    [entry] = upstream_risk(_agg(consumer), [consumer, upstream], {}, store)

    assert entry.version_drift is True
    assert entry.upstream_breach is False
    assert own_health(_agg(consumer), {"OUT": _contract()}, store) == "pass"


def test_upstream_risk_preserves_known_version_when_worst_port_has_none():
    upstream = _product("up", ["U1", "U2"])
    consumer = _product("consumer", ["OUT"], [InboundDep("up", "1.0.0")])
    store = FakeStore({
        "U1": {"compliance": "breached", "contract_version": "2.0.0"},
        "U2": {"compliance": "critical", "contract_version": None},
    })

    [entry] = upstream_risk(_agg(consumer), [consumer, upstream], {}, store)

    assert entry.compliance == "critical"
    assert entry.current_version == "2.0.0"
    assert entry.version_drift is True
