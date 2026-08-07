"""Per-object scheduling toggle API (Option E): manual / internal / external."""


def test_upsert_internal_then_external_then_delete(api_client):
    # No schedule yet → manual.
    assert api_client.get("/api/objects/DS_SALES_ORDERS/schedule").json() is None

    # Turn on internal scheduling.
    resp = api_client.put(
        "/api/objects/DS_SALES_ORDERS/schedule",
        json={"mode": "internal", "interval_seconds": 3600, "environment": ""},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] == "internal"
    assert body["interval_seconds"] == 3600
    assert body["enabled"] is True

    # Switch the same object to external (driven by a Task Chain / CLI).
    resp = api_client.put(
        "/api/objects/DS_SALES_ORDERS/schedule",
        json={"mode": "external", "interval_seconds": 0},
    )
    assert resp.status_code == 200
    assert resp.json()["mode"] == "external"

    # Visible in the ops list.
    listing = api_client.get("/api/schedules").json()
    assert any(s["object_id"] == "DS_SALES_ORDERS" for s in listing)

    # Back to manual.
    assert api_client.delete("/api/objects/DS_SALES_ORDERS/schedule").status_code == 204
    assert api_client.get("/api/objects/DS_SALES_ORDERS/schedule").json() is None


def test_internal_requires_min_interval(api_client):
    resp = api_client.put(
        "/api/objects/DS_SALES_ORDERS/schedule",
        json={"mode": "internal", "interval_seconds": 5},
    )
    assert resp.status_code == 422


def test_unknown_object_404(api_client):
    resp = api_client.put(
        "/api/objects/NOPE/schedule",
        json={"mode": "internal", "interval_seconds": 3600},
    )
    assert resp.status_code == 404


def test_viewer_cannot_manage(api_client):
    resp = api_client.put(
        "/api/objects/DS_SALES_ORDERS/schedule",
        json={"mode": "internal", "interval_seconds": 3600},
        headers={"X-DQ-Role": "viewer"},
    )
    assert resp.status_code == 403


def test_poller_launches_due_internal_run(api_client):
    """End-to-end: a due internal schedule launches a real run via the shared
    start_object_run path (mock connection), and the outcome is stamped back."""
    from datetime import datetime, timezone

    # api_client built the app + store with the test settings active.
    import services.api.deps as deps_mod
    from services.api import scheduler

    store = deps_mod.get_store()
    store.create_schedule(
        schedule_id="obj:DS_SALES_ORDERS",
        object_id="DS_SALES_ORDERS",
        interval_seconds=3600,
        next_due_at=datetime.now(timezone.utc).isoformat(),
    )

    launched = scheduler._launch_due(datetime.now(timezone.utc).isoformat())
    assert launched == 1

    sched = store.get_schedule("obj:DS_SALES_ORDERS")
    assert sched["last_status"] == "started"
    assert sched["last_run_id"]
    # The run is registered against the object and triggered by the scheduler.
    runs = store.get_runs("DS_SALES_ORDERS", limit=5)
    assert any(r["triggered_by"] == "scheduler" for r in runs)
