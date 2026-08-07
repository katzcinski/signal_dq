"""Tests for ProposalMiner — confidence and warm-up behaviour."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[2] / "packages"))

import pytest
from unittest.mock import MagicMock
from dq_core.obs.miner import ProposalMiner, WARMUP_MIN_SAMPLES, FULL_CONFIDENCE_SAMPLES


def make_store_with_history(n_samples: int, check_name="check_1", dataset="DS"):
    store = MagicMock()
    store.get_runs.return_value = [{"run_id": "r_latest"}]
    store.get_run.return_value = {
        "run_id": "r_latest",
        "results": [{"check_name": check_name}],
    }
    history = [
        {"actual_value": str(float(i * 10)), "passed": True, "state": "executed", "started_at": f"2026-01-{i+1:02d}", "run_id": f"r{i}"}
        for i in range(n_samples)
    ]
    store.get_check_history.return_value = history
    return store


def test_no_proposals_below_warmup():
    store = make_store_with_history(WARMUP_MIN_SAMPLES - 1)
    miner = ProposalMiner(store)
    assert miner.mine("DS") == []


def test_proposals_at_warmup():
    store = make_store_with_history(WARMUP_MIN_SAMPLES)
    miner = ProposalMiner(store)
    proposals = miner.mine("DS")
    assert len(proposals) > 0


def test_confidence_full_at_30():
    store = make_store_with_history(FULL_CONFIDENCE_SAMPLES)
    miner = ProposalMiner(store)
    proposals = miner.mine("DS")
    assert all(p.confidence == 1.0 for p in proposals)


def test_confidence_partial_below_30():
    store = make_store_with_history(15)
    miner = ProposalMiner(store)
    proposals = miner.mine("DS")
    if proposals:
        assert all(p.confidence < 1.0 for p in proposals)


def test_no_runs_returns_empty():
    store = MagicMock()
    store.get_runs.return_value = []
    miner = ProposalMiner(store)
    assert miner.mine("DS") == []


def test_proposal_has_expected_fields():
    store = make_store_with_history(30)
    miner = ProposalMiner(store)
    proposals = miner.mine("DS")
    if proposals:
        p = proposals[0]
        assert p.product == "DS"
        assert p.proposed_expect.startswith("BETWEEN")
        assert p.stats.get("n") == 30
