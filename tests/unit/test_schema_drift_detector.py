"""Shift-Left-Schema-Drift-Detektor (Konzept §A) — reine Diff-Mechanik (G7)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "packages"))
sys.path.insert(0, str(Path(__file__).parents[2]))

from dq_core.contract.schema_drift import (
    COLUMN_ADDED,
    COLUMN_REMOVED,
    KEY_CHANGED,
    NULLABLE_RELAXED,
    TYPE_CHANGED,
    detect_schema_drift,
    normalize_type,
    summarize_drift,
)
from dq_core.contract.validator import validate_contract


def _contract(mode="closed", types=None):
    schema = {"columns": ["A", "B", "C"], "mode": mode}
    if types:
        schema["types"] = types
    return {"product": "P", "dataset": "P", "version": "1.0.0",
            "guarantees": {"schema": schema}}


def test_no_schema_guarantee_means_no_drift():
    c = {"product": "P", "dataset": "P", "version": "1.0.0", "guarantees": {}}
    assert detect_schema_drift(c, [{"name": "X"}]) == []


def test_column_removed_is_breaking():
    src = [{"name": "A"}, {"name": "B"}]  # C fehlt
    findings = detect_schema_drift(_contract(), src)
    cats = {(f.category, f.column): f for f in findings}
    assert (COLUMN_REMOVED, "C") in cats
    assert cats[(COLUMN_REMOVED, "C")].breaking is True


def test_added_column_breaking_only_in_closed_mode():
    src = [{"name": "A"}, {"name": "B"}, {"name": "C"}, {"name": "D"}]
    closed = {f.column: f for f in detect_schema_drift(_contract("closed"), src)}
    assert closed["D"].category == COLUMN_ADDED and closed["D"].breaking is True

    opened = {f.column: f for f in detect_schema_drift(_contract("open"), src)}
    assert opened["D"].category == COLUMN_ADDED and opened["D"].breaking is False


def test_type_nullable_key_drift():
    types = {"B": {"type": "integer", "nullable": False, "key": True}}
    # Quelle: B ist String, nullable, kein Key → drei breaking-Befunde.
    src = [
        {"name": "A"}, {"name": "C"},
        {"name": "B", "type": "cds.String", "nullable": "True", "key": ""},
    ]
    findings = detect_schema_drift(_contract(types=types), src)
    cats = {f.category for f in findings if f.column == "B"}
    assert TYPE_CHANGED in cats
    assert NULLABLE_RELAXED in cats
    assert KEY_CHANGED in cats
    assert all(f.breaking for f in findings if f.column == "B")


def test_matching_typed_column_has_no_drift():
    types = {"B": {"type": "string", "nullable": True, "key": False}}
    src = [
        {"name": "A"}, {"name": "C"},
        {"name": "B", "type": "cds.String", "nullable": "True", "key": ""},
    ]
    findings = [f for f in detect_schema_drift(_contract(types=types), src) if f.column == "B"]
    assert findings == []


def test_normalize_type_families():
    assert normalize_type("cds.String") == "string"
    assert normalize_type("NVARCHAR(20)") == "string"
    assert normalize_type("cds.Integer") == "integer"
    assert normalize_type("DECIMAL(10,2)") == "decimal"


def test_summary_counts_breaking():
    src = [{"name": "A"}, {"name": "B"}]  # C entfernt
    summary = summarize_drift(detect_schema_drift(_contract(), src))
    assert summary["has_breaking"] is True
    assert summary["breaking"] == 1
    assert summary["by_category"][COLUMN_REMOVED] == 1


def test_findings_are_deterministically_sorted():
    src = [{"name": "B"}, {"name": "Z"}, {"name": "A"}]  # C entfernt, Z hinzu
    a = [(f.category, f.column) for f in detect_schema_drift(_contract(), src)]
    b = [(f.category, f.column) for f in detect_schema_drift(_contract(), src)]
    assert a == b == sorted(a)


def test_validator_accepts_schema_types():
    """§A.5: Die optionale Typ-Deklaration ist gültig (kein SQL → G1 ok)."""
    c = _contract(types={"B": {"type": "integer", "nullable": False, "key": True}})
    assert validate_contract(c) == []


def test_validator_rejects_unknown_type_enum():
    c = _contract(types={"B": {"type": "geography"}})
    assert validate_contract(c) != []
