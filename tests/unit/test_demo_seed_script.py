from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parents[2]))
sys.path.insert(0, str(Path(__file__).parents[2] / "packages"))

from dq_core.store.sqlite_store import ResultStore
from scripts.seed import DEMO_PROFILE_ENV, seed_workspace


def test_seed_workspace_populates_demo_products_profiles_and_incidents(tmp_path):
    db_path = tmp_path / "seed.db"
    products_dir = tmp_path / "products"
    contracts_dir = tmp_path / "contracts"

    first = seed_workspace(
        db_path=db_path,
        products_dir=products_dir,
        contracts_dir=contracts_dir,
    )
    second = seed_workspace(
        db_path=db_path,
        products_dir=products_dir,
        contracts_dir=contracts_dir,
    )

    store = ResultStore(db_path)
    incidents = store.list_incidents(limit=20)
    profile_snaps = store.list_profile_snapshots("DEMO_BUS_01", limit=10)

    assert first["runs"] == second["runs"] == 280
    assert first["profile_rows"] == 4
    assert second["profile_rows"] == 0
    assert first["incident_rows"] == 3
    assert second["incident_rows"] == 0
    assert first["proposal_rows"] == second["proposal_rows"] == 2

    assert (products_dir / "commercial_core.yaml").exists()
    assert (products_dir / "revenue_mart.yaml").exists()
    assert (products_dir / "operations_signal.yaml").exists()

    assert (contracts_dir / "DEMO_BUS_01.yaml").exists()
    assert (contracts_dir / "DEMO_BUS_02.yaml").exists()
    assert (contracts_dir / "DEMO_BUS_06.yaml").exists()

    assert len(profile_snaps) == 2
    head = store.get_profile_snapshot(profile_snaps[0]["id"])
    assert head is not None
    assert head["environment"] == DEMO_PROFILE_ENV
    assert head["stats"]["row_count"] > 0

    assert len(incidents) == 3
    assert any(item["kind"] == "internal_gate" for item in incidents)
    assert any(item["kind"] == "consumer_contract" for item in incidents)
    assert any(item["kind"] == "provider_contract" for item in incidents)

    assert store.get_compliance("DEMO_BUS_01")["compliance"] == "compliant"
    assert store.get_compliance("DEMO_BUS_02")["compliance"] == "breached"
    assert store.get_compliance("DEMO_BUS_06")["compliance"] == "warning"
