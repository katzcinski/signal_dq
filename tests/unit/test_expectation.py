"""Tests for expectation.py — [ENGINE-FROZEN] (G5)."""
import pytest

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[2] / "packages"))

from dq_core.engine.expectation import evaluate, validate_expectation


# --- validate_expectation ---

def test_validate_accepts_comparison():
    validate_expectation("= 0")
    validate_expectation(">= 100")
    validate_expectation("< 50.5")
    validate_expectation("!= 0")


def test_validate_accepts_between():
    validate_expectation("BETWEEN 0 AND 100")


def test_validate_accepts_delta():
    validate_expectation("DELTA < 10%")
    validate_expectation("DELTA <= 5%")


def test_validate_accepts_null_forms():
    validate_expectation("IS NULL")
    validate_expectation("IS NOT NULL")


def test_validate_accepts_in_forms():
    validate_expectation("IN('A','B')")
    validate_expectation("NOT IN('X')")


def test_validate_rejects_empty():
    with pytest.raises(ValueError, match="empty"):
        validate_expectation("")


def test_validate_rejects_unsupported():
    with pytest.raises(ValueError):
        validate_expectation("LIKE '%foo%'")


# --- evaluate ---

@pytest.mark.parametrize("actual,expr,expected", [
    (0, "= 0", True),
    (1, "= 0", False),
    (5, "> 3", True),
    (5, "> 5", False),
    (5, ">= 5", True),
    (5, "<= 4", False),
    (3, "!= 3", False),
    (4, "!= 3", True),
    (50, "BETWEEN 0 AND 100", True),
    (-1, "BETWEEN 0 AND 100", False),
])
def test_evaluate_numeric(actual, expr, expected):
    assert evaluate(actual, expr) == expected


def test_evaluate_delta_no_previous():
    # No baseline → pass (warm-up)
    assert evaluate(999, "DELTA < 10%", previous_value=None) is True


def test_evaluate_delta_within():
    assert evaluate(105, "DELTA < 10%", previous_value=100) is True


def test_evaluate_delta_exceeds():
    assert evaluate(120, "DELTA < 10%", previous_value=100) is False


def test_evaluate_delta_prev_zero():
    # Previous value zero → pass (no division by zero)
    assert evaluate(5, "DELTA < 10%", previous_value=0) is True


def test_evaluate_is_null():
    assert evaluate(None, "IS NULL") is True
    assert evaluate(0, "IS NULL") is False


def test_evaluate_is_not_null():
    assert evaluate(0, "IS NOT NULL") is True
    assert evaluate(None, "IS NOT NULL") is False


def test_evaluate_between():
    assert evaluate(10, "BETWEEN 10 AND 20") is True
    assert evaluate(21, "BETWEEN 10 AND 20") is False
