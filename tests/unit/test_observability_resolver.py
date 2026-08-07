import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "packages"))

from dq_core.engine.models import CheckDef, DatasetConfig
from dq_core.obs.baselines import BaselineManager
from dq_core.obs.resolver import resolve_observability_checks
from dq_core.store.sqlite_store import ResultStore


def _config():
    return DatasetConfig(
        dataset="DS",
        schema="SCH",
        checks=[
            CheckDef(
                name="volume_min_rows",
                sql='SELECT COUNT(*) FROM "SCH"."DS"',
                expect=">= 1",
                severity="fail",
                type="row_count",
                kind="consumer_contract",
            )
        ],
    )


def test_missing_baseline_creates_downgraded_result(tmp_path):
    store = ResultStore(tmp_path / "o.db")
    manager = BaselineManager(store)
    contract = {"observability": {"volume": {"baseline": "rolling", "sensitivity": "medium"}}}

    resolved = resolve_observability_checks(_config(), contract, manager, started_at="2026-06-29T10:00:00+00:00")

    assert [c.name for c in resolved.config.checks] == ["volume_min_rows"]
    assert len(resolved.downgraded_results) == 1
    assert resolved.downgraded_results[0].state == "downgraded"
    assert resolved.downgraded_results[0].passed is False


def test_ready_baseline_adds_numeric_between_check(tmp_path):
    store = ResultStore(tmp_path / "o.db")
    manager = BaselineManager(store)
    manager.update_baseline("DS", "volume_min_rows", [100, 101, 102, 103, 104])
    contract = {"observability": {"volume": {"baseline": "rolling", "sensitivity": "high"}}}

    resolved = resolve_observability_checks(_config(), contract, manager, started_at="2026-06-29T10:00:00+00:00")
    adaptive = resolved.config.checks[-1]

    assert adaptive.name == "volume_adaptive_rows"
    assert adaptive.kind == "internal_gate"
    assert adaptive.expect.startswith("BETWEEN ")
    assert "<BL" not in adaptive.expect
    assert resolved.downgraded_results == []
