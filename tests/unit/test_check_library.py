"""Catalog integrity + observability classification for the check library.

Guards the contract between the catalog (check_library.json) and the engine:
every template's default expectation must be evaluatable, the SAP/BDC templates
are gone, and the observability quick-win checks are both present and classified
as observability by the result store.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "packages"))

from dq_core.engine.expectation import validate_expectation
from dq_core.library.check_library import checks, categories, check_by_id
from dq_core.store.sqlite_store import ResultStore

OBS_QUICK_WINS = ("volume_delta", "column_count", "recent_volume")


def test_every_default_expectation_is_valid():
    """A typo'd default_expect would silently ship a non-evaluatable check."""
    for chk in checks():
        validate_expectation(chk["default_expect"])


def test_categories_are_declared():
    declared = set(categories())
    used = {c["category"] for c in checks()}
    assert used <= declared, used - declared


def test_sap_bdc_templates_removed():
    assert not any(c["id"].startswith("sap_") for c in checks())
    assert "SAP / BDC" not in categories()


def test_observability_quick_wins_present():
    for cid in OBS_QUICK_WINS:
        chk = check_by_id(cid)
        assert chk is not None, cid
        assert chk["category"] == "Aktualität & Sonstiges"


def test_quick_wins_classified_as_observability():
    """The whole point of the additions: they must roll up to the
    observability family, not quality."""
    for cid in OBS_QUICK_WINS:
        assert cid in ResultStore._OBS_TYPES


def test_volume_delta_uses_run_over_run_delta():
    """volume_delta leans on the existing DELTA grammar (no engine change)."""
    assert check_by_id("volume_delta")["default_expect"].startswith("DELTA")
