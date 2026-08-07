"""B-2/B-3 (§B): POST /api/objects/{id}/diff über gespeicherte Profil-Snapshots."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "packages"))
sys.path.insert(0, str(Path(__file__).parents[2]))


def _profile(row_count, columns):
    return {"row_count": row_count, "column_count": len(columns), "columns": columns,
            "pk_candidates": {"single": [c["column"] for c in columns if c.get("pk")]}}


def _seed_two_snapshots(store):
    base = _profile(1000, [
        {"column": "ID", "null_pct": 0.0, "distinct": 1000, "pk": True},
        {"column": "AMT", "null_pct": 0.1, "distinct": 500},
    ])
    head = _profile(900, [
        {"column": "ID", "null_pct": 0.0, "distinct": 890, "pk": True},
        {"column": "AMT", "null_pct": 5.0, "distinct": 480},
    ])
    bid = store.save_profile_snapshot("DS_SALES_ORDERS", base)
    hid = store.save_profile_snapshot("DS_SALES_ORDERS", head)
    return bid, hid


def test_distribution_diff_latest_two(api_client):
    import services.api.deps as deps_mod
    store = deps_mod.get_store()
    _seed_two_snapshots(store)

    resp = api_client.post("/api/objects/DS_SALES_ORDERS/diff", json={"mode": "distribution"})
    assert resp.status_code == 200, resp.text
    dist = resp.json()["distribution"]
    assert dist["row_count"]["delta"] == -100
    amt = next(c for c in dist["columns"] if c["column"] == "AMT")
    assert amt["changed"] is True
    assert amt["metrics"]["null_pct"]["delta"] == 4.9


def test_keys_reconciliation_flags_duplicates(api_client):
    import services.api.deps as deps_mod
    store = deps_mod.get_store()
    bid, hid = _seed_two_snapshots(store)

    resp = api_client.post(
        "/api/objects/DS_SALES_ORDERS/diff",
        json={"mode": "keys", "base_snapshot_id": bid, "head_snapshot_id": hid},
    )
    assert resp.status_code == 200, resp.text
    rec = resp.json()["reconciliation"]
    key = next(k for k in rec["keys"] if k["column"] == "ID")
    # base: 1000 rows / 1000 distinct = unique; head: 900 rows / 890 distinct → Duplikate
    assert key["base_duplicates"] is False
    assert key["head_duplicates"] is True


def test_diff_requires_two_snapshots(api_client):
    import services.api.deps as deps_mod
    store = deps_mod.get_store()
    store.save_profile_snapshot("DS_SALES_ORDERS", _profile(10, [{"column": "A", "distinct": 10}]))
    resp = api_client.post("/api/objects/DS_SALES_ORDERS/diff", json={"mode": "distribution"})
    assert resp.status_code == 422
