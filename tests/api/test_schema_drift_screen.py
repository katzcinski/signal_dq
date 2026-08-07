"""A2/UX-N9: Schema-Evolution-Screen — Overview- + Evolution-Endpoints."""
import yaml

from services.api.deps import get_store


def _write_contract(client, tmp_dir=None):
    """Aktiven Contract mit Schema-Garantie direkt ins Contracts-Verzeichnis legen."""
    from services.api.settings import get_settings
    from pathlib import Path

    contract = {
        "product": "DS_SALES_ORDERS", "dataset": "DS_SALES_ORDERS",
        "version": "2.0.0", "kind": "consumer_contract", "lifecycle": "active",
        "guarantees": {"schema": {"columns": ["A", "B", "C"], "mode": "closed"}},
    }
    path = Path(get_settings().contracts_dir) / "DS_SALES_ORDERS.yaml"
    path.write_text(yaml.safe_dump(contract, sort_keys=False), encoding="utf-8")
    return contract


def _seed_history(store):
    """Zwei Snapshots (B kommt hinzu, C fällt weg) + ein breaking-Befund."""
    store.save_schema_snapshot(
        "DS_SALES_ORDERS",
        [{"name": "A", "type": "string"}, {"name": "C", "type": "integer"}],
        "hash-1",
    )
    store.save_schema_snapshot(
        "DS_SALES_ORDERS",
        [{"name": "A", "type": "string"}, {"name": "B", "type": "string"}],
        "hash-2",
    )
    store.record_schema_drift(
        "DS_SALES_ORDERS",
        [{"category": "column_removed", "column": "C", "before": "C", "after": "", "breaking": True}],
        contract_version="2.0.0",
        incident_id=3,
    )


def test_overview_rolls_up_snapshots_drift_and_contract(api_client):
    _write_contract(api_client)
    _seed_history(get_store())

    resp = api_client.get("/api/schema-drift")
    assert resp.status_code == 200
    objects = resp.json()["objects"]
    assert len(objects) == 1

    row = objects[0]
    assert row["object_name"] == "DS_SALES_ORDERS"
    assert row["snapshots"] == 2
    assert row["distinct_schemas"] == 2
    assert row["findings"] == 1
    assert row["breaking"] == 1
    assert row["last_incident_id"] == 3
    assert row["column_count"] == 2  # jüngster Snapshot: A, B
    # Contract-Bindung angereichert
    assert row["product"] == "DS_SALES_ORDERS"
    assert row["kind"] == "consumer_contract"
    assert row["contract_version"] == "2.0.0"


def test_evolution_diffs_consecutive_snapshots(api_client):
    _write_contract(api_client)
    _seed_history(get_store())

    resp = api_client.get("/api/schema-drift/DS_SALES_ORDERS")
    assert resp.status_code == 200
    body = resp.json()

    assert body["contract"]["kind"] == "consumer_contract"
    assert [s["column_count"] for s in body["snapshots"]] == [2, 2]

    assert len(body["steps"]) == 1
    changes = {(c["category"], c["column"]) for c in body["steps"][0]["changes"]}
    assert changes == {("column_added", "B"), ("column_removed", "C")}

    # Contract-Bruch bleibt markiert: breaking-Befund + Incident-Referenz.
    events = body["drift_events"]
    assert len(events) == 1
    assert events[0]["breaking"] == 1
    assert events[0]["incident_id"] == 3

    assert [c["name"] for c in body["latest_columns"]] == ["A", "B"]


def test_evolution_skips_identical_consecutive_snapshots(api_client):
    store = get_store()
    cols = [{"name": "A", "type": "string"}]
    store.save_schema_snapshot("DS_STABLE", cols, "same-hash")
    store.save_schema_snapshot("DS_STABLE", cols, "same-hash")

    body = api_client.get("/api/schema-drift/DS_STABLE").json()
    assert len(body["snapshots"]) == 2
    assert body["steps"] == []
    assert body["contract"] is None


def test_evolution_unknown_object_404s(api_client):
    assert api_client.get("/api/schema-drift/DS_UNKNOWN").status_code == 404


def test_evolution_invalid_object_name_422s(api_client):
    assert api_client.get("/api/schema-drift/bad%20name!").status_code == 422
