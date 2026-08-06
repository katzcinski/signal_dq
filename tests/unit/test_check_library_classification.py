"""The check library is the single source of truth for the two functional
classification axes — ``family`` (observability/quality, consumed by the store's
family rollup) and ``gating`` (gate/expensive/standard, consumed by the engine's
gating chain). These tests lock the contract so engine/store derivations cannot
drift from the library and so a newly added check cannot omit the fields.
"""
from dq_core.library import checks, families, check_ids_where

VALID_FAMILIES = {"observability", "quality"}
VALID_GATING = {"gate", "expensive", "standard"}


def test_every_check_is_classified():
    for c in checks():
        assert c["family"] in VALID_FAMILIES, c["id"]
        assert c["gating"] in VALID_GATING, c["id"]


def test_families_listed():
    assert families() == ["observability", "quality"]


def test_standard_gap_templates_are_present():
    ids = {c["id"] for c in checks()}

    assert {
        "duplicate_composite",
        "volume_anomaly",
        "cross_field_consistency",
        "type_conformance",
    } <= ids


def test_sap_domain_templates_are_not_in_standard_library():
    ids = {c["id"] for c in checks()}

    assert not {
        "sap_bseg_balance",
        "sap_bkpf_orphan",
        "sap_fiscal_completeness",
        "sap_key_plausibility",
    } & ids


def test_engine_gating_sets_derive_from_library():
    from dq_core.engine.check_engine import GATE_TYPES, EXPENSIVE_TYPES

    assert GATE_TYPES == check_ids_where("gating", "gate")
    assert EXPENSIVE_TYPES == check_ids_where("gating", "expensive")
    # Regression lock: guards against accidental reclassification of a check.
    assert GATE_TYPES == {"freshness", "volume_anomaly"}
    assert EXPENSIVE_TYPES == {
        "reference_integrity", "aggregate_range", "duplicate", "duplicate_composite",
    }


def test_store_obs_types_derive_from_library():
    from dq_core.store.sqlite_store import ResultStore

    assert set(ResultStore._OBS_TYPES) == check_ids_where("family", "observability")
    assert set(ResultStore._OBS_TYPES) == {
        "column_count", "freshness", "recent_volume", "row_count", "schema",
        "type_conformance", "volume_anomaly", "volume_delta",
    }


def test_a_gate_is_never_also_expensive():
    # The gating algorithm runs gates first regardless of cost; modelling a check
    # as both gate and expensive would be contradictory.
    assert not (check_ids_where("gating", "gate") & check_ids_where("gating", "expensive"))
