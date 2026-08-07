"""UX-N15: aggregated activity / audit feed."""
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "packages"))
sys.path.insert(0, str(Path(__file__).parents[2]))


def test_activity_aggregates_incidents_and_proposals(api_client):
    import services.api.deps as deps_mod
    store = deps_mod.get_store()

    # Incident lifecycle: opened by system, resolved by alice.
    iid = store.open_incident(
        product="DS_SALES_ORDERS", run_id="r1", severity="fail",
        title="Breach", failed_checks=["amount_not_null"], actor="system",
    )
    store.transition_incident(iid, status="resolved", actor="alice", note="fixed upstream")

    # A persisted steward proposal decision.
    now = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(store.db_path)
    conn.execute(
        "INSERT OR REPLACE INTO dq_proposals (id, product, guarantee_patch, evidence, status, created_at) "
        "VALUES (?,?,?,?,?,?)",
        ("prop-1", "DS_SALES_ORDERS", "<= 8", "{}", "accepted", now),
    )
    conn.commit()
    conn.close()

    resp = api_client.get("/api/activity")
    assert resp.status_code == 200, resp.text
    items = resp.json()

    kinds = {it["kind"] for it in items}
    assert "incident" in kinds
    assert "proposal" in kinds

    resolved = [it for it in items if it["kind"] == "incident" and it["action"] == "status_changed"]
    assert resolved and resolved[0]["actor"] == "alice"

    proposals = [it for it in items if it["kind"] == "proposal"]
    assert proposals and proposals[0]["action"] == "accepted"


def test_activity_empty_is_ok(api_client):
    # No incidents/proposals/git repo in a fresh tenant → empty list, not 500.
    resp = api_client.get("/api/activity")
    assert resp.status_code == 200
    assert resp.json() == []


def test_activity_respects_limit(api_client):
    import services.api.deps as deps_mod
    store = deps_mod.get_store()
    for i in range(5):
        store.open_incident(
            product=f"P{i}", run_id="r", severity="fail",
            title=f"t{i}", failed_checks=["c"], actor="system",
        )
    resp = api_client.get("/api/activity", params={"limit": 3})
    assert resp.status_code == 200
    assert len(resp.json()) == 3
