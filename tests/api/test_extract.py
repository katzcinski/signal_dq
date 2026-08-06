"""Extract / inventory endpoints (WS1-2, WS2-6).
F5: Extrakt-Aktualität — GET /api/lineage liefert stale-Flag anhand des
konfigurierbaren Schwellwerts (EXTRACT_STALE_DAYS). Ohne konfigurierten
Live-Connector ist POST /api/extract ein ehrlicher No-Op (status=skipped): es
fasst den lokalen/Demo-Snapshot NICHT an und meldet keinen Erfolg."""
import os
import time
from typing import Any


def _wait_for_finished(api_client, op_id: str) -> dict[str, Any]:
    for _ in range(40):
        resp = api_client.get(f"/api/operations/{op_id}")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        if body["state"] in {"finished", "error"}:
            return body
        time.sleep(0.05)
    raise AssertionError("extract operation did not finish")


def _visible_progress(operation: dict[str, Any]) -> list[str]:
    return [row["line"] for row in operation["progress"] if not row["line"].startswith("@@progress ")]


def test_inventory_lists_datasets(api_client):
    resp = api_client.get("/api/inventory")
    assert resp.status_code == 200
    data = resp.json()
    assert "datasets" in data
    assert any(d["id"] == "DS_SALES_ORDERS" for d in data["datasets"])


def test_extract_skipped_without_live_source(api_client):
    """Without a configured CLI/REST source the trigger is an honest no-op.

    It must report status=skipped (never 'succeeded') and source='none' so the
    UI does not present the existing local/demo snapshot as a fresh extraction.
    The on-disk snapshot counts are still echoed for context.
    """
    resp = api_client.post("/api/extract")
    assert resp.status_code == 202
    data = _wait_for_finished(api_client, resp.json()["op_id"])["result"]
    assert data["status"] == "skipped"
    assert data["source"] == "none"
    assert data["extracted_at"] is None
    assert data["inventory_items"] == 1
    assert data["lineage_nodes"] == 1
    assert data["counts"]["inventory_items"] == 1


def test_extract_status_reports_latest_snapshot(api_client):
    resp = api_client.get("/api/extract/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["can_trigger"] is True
    assert data["counts"]["inventory_items"] == 1
    assert data["runtime_artifact_paths"]["inventory"]


def test_extract_trigger_requires_steward(api_client):
    """W-1: Der Lite-Einstieg L1 (Inventar/Lineage extrahieren) ist steward+,
    nicht admin — Extract ist gegenüber Datasphere read-only."""
    assert api_client.post("/api/extract", headers={"X-DQ-Role": "viewer"}).status_code == 403
    assert api_client.post("/api/extract", headers={"X-DQ-Role": "steward"}).status_code == 202


def test_extract_streams_live_object_progress(api_client, monkeypatch):
    import services.api.connector_config as connector_mod
    import services.api.datasphere_catalog as catalog_mod

    class _FakeCatalog:
        def list_objects(self, space):
            return [{
                "technicalName": "v_OrderSummary",
                "objectType": "views",
                "status": "Deployed",
                "businessName": "Order Summary",
            }]

        def read_object_definition(self, space, name):
            return {
                "query": {
                    "SELECT": {
                        "from": {"ref": ["Sales_Orders"], "as": "o"},
                        "columns": [
                            {"ref": ["o", "OrderID"], "as": "OrderID"},
                            {"func": "SUM", "args": [{"ref": ["o", "Amount"]}], "as": "TotalAmount"},
                        ],
                    }
                }
            }

    monkeypatch.setattr(connector_mod, "effective_space_id", lambda settings: "DEMO_SPACE")
    monkeypatch.setattr(catalog_mod, "get_catalog_client", lambda: _FakeCatalog())

    started = api_client.post("/api/extract")
    assert started.status_code == 202

    operation = _wait_for_finished(api_client, started.json()["op_id"])
    assert operation["kind"] == "inventory_extract"
    assert operation["state"] == "finished"
    assert operation["result"]["status"] == "succeeded"
    assert operation["result"]["source"] == "datasphere-catalog"

    progress = _visible_progress(operation)
    assert "Source   : datasphere-catalog" in progress
    assert "[views] listing..." in progress
    assert any("v_OrderSummary" in line for line in progress)


def test_extract_leaves_snapshot_untouched_without_live_source(api_client):
    """Without a live connector POST /api/extract must NOT touch snapshot files.

    Re-stamping the mtime would launder the stale local/demo snapshot into
    looking like a fresh extraction — exactly the behaviour we removed.
    """
    import services.api.settings as sm
    settings = sm.get_settings()
    lineage_path = settings.lineage_file

    # Back-date the lineage file to 10 days ago
    old_ts = time.time() - 10 * 86400
    os.utime(lineage_path, (old_ts, old_ts))
    old_mtime = os.path.getmtime(lineage_path)

    resp = api_client.post("/api/extract")
    assert resp.status_code == 202
    result = _wait_for_finished(api_client, resp.json()["op_id"])["result"]
    assert result["status"] == "skipped"
    assert result["extracted_at"] is None

    new_mtime = os.path.getmtime(lineage_path)
    assert new_mtime == old_mtime, "skipped extract must leave the snapshot mtime untouched"


def test_lineage_stale_flag_when_old(api_client, monkeypatch, tmp_path):
    """F5: GET /api/lineage returns stale=True when extract_age > EXTRACT_STALE_DAYS."""
    import services.api.settings as sm
    settings = sm.get_settings()

    # Back-date the lineage file to well beyond the threshold
    lineage_path = settings.lineage_file
    old_ts = time.time() - (settings.extract_stale_days + 2) * 86400
    os.utime(lineage_path, (old_ts, old_ts))

    resp = api_client.get("/api/lineage")
    assert resp.status_code == 200
    data = resp.json()
    assert data["stale"] is True, f"Expected stale=True but got: {data}"
    assert data["extract_age"] is not None
    assert data["extracted_at"] is not None


def test_lineage_stays_stale_after_skipped_extract(api_client):
    """F5: A skipped (no-source) extract does NOT clear the stale flag.

    Old/demo data is honestly reported as stale; only a real live extraction
    (which rewrites the snapshot) refreshes the staleness clock.
    """
    import services.api.settings as sm
    settings = sm.get_settings()

    # Back-date the lineage file
    lineage_path = settings.lineage_file
    old_ts = time.time() - (settings.extract_stale_days + 5) * 86400
    os.utime(lineage_path, (old_ts, old_ts))

    started = api_client.post("/api/extract")
    assert started.status_code == 202
    assert _wait_for_finished(api_client, started.json()["op_id"])["result"]["status"] == "skipped"

    resp = api_client.get("/api/lineage")
    assert resp.status_code == 200
    data = resp.json()
    assert data["stale"] is True, f"Expected stale=True after skipped extract, got: {data}"
