"""Healing-Workbench (H1/H3): Gates, Audit, Vier-Augen, Re-Check-Vorbedingung."""
import json
from pathlib import Path

import yaml

from services.api.deps import get_store
from services.api.settings import get_settings

STEWARD = {"X-DQ-Role": "steward"}
OWNER = {"X-DQ-Role": "owner"}
VIEWER = {"X-DQ-Role": "viewer"}


def _inventory_with_columns():
    """Inventar-Objekt mit Schlüssel-/Datenspalten (Grundlage für H3-Zuschnitt)."""
    settings = get_settings()
    inv_path = Path(settings.inventory_file)
    data = json.loads(inv_path.read_text(encoding="utf-8"))
    data["objects"][0]["columns"] = [
        {"name": "ID", "type": "cds.String", "key": "true"},
        {"name": "AMOUNT", "type": "cds.Decimal"},
        {"name": "CURRENCY", "type": "cds.String"},
    ]
    inv_path.write_text(json.dumps(data), encoding="utf-8")
    import services.api.deps as deps_mod
    deps_mod.get_inventory.cache_clear() if hasattr(deps_mod.get_inventory, "cache_clear") else None


def _contract(kind="consumer_contract"):
    settings = get_settings()
    path = Path(settings.contracts_dir) / "DS_SALES_ORDERS.yaml"
    path.write_text(yaml.safe_dump({
        "product": "DS_SALES_ORDERS", "dataset": "DS_SALES_ORDERS",
        "version": "1.0.0", "kind": kind, "lifecycle": "active",
        "guarantees": {"volume": {"min_rows": 1}},
    }, sort_keys=False), encoding="utf-8")


def _open_episode(store, product="DS_SALES_ORDERS"):
    return store.open_quarantine(
        product=product, run_id="run-1", failed_checks=["amount_not_null"],
        contract_version="1.0.0", actor="system",
    )


# ------------------------------------------------------------------- Rollen

def test_overview_requires_steward(api_client):
    assert api_client.get("/api/healing/overview", headers=VIEWER).status_code == 403
    assert api_client.get("/api/healing/overview", headers=STEWARD).status_code == 200


def test_patch_creation_requires_owner(api_client):
    _inventory_with_columns()
    body = {"object_id": "DS_SALES_ORDERS", "keys": {"ID": "42"}, "values": {"AMOUNT": "100"}}
    assert api_client.post("/api/healing/patches", json=body, headers=STEWARD).status_code == 403
    assert api_client.post("/api/healing/patches", json=body, headers=OWNER).status_code == 201


# ---------------------------------------------------------------- H1 Korrektur

def test_correction_is_audited_even_without_materialization(api_client):
    _inventory_with_columns()
    store = get_store()
    episode_id = _open_episode(store)

    # Ohne kompilierte Checks gibt es keine Zeilen-Spezifikation → 409 statt
    # stillem Erfolg (G6: der Nutzer erfährt, dass H1 hier nicht greift).
    resp = api_client.post(
        f"/api/healing/episodes/{episode_id}/corrections",
        json={"keys": {"ID": "42"}, "column": "AMOUNT", "new_value": "100", "reason": "Tippfehler"},
        headers=STEWARD,
    )
    assert resp.status_code == 409
    assert "row-level" in resp.json()["detail"]


def test_correction_on_healable_episode_audits_and_rechecks(api_client, monkeypatch):
    _inventory_with_columns()
    store = get_store()
    episode_id = _open_episode(store)

    # Zeilenfähige Spezifikation vortäuschen (ohne kompilierte Checks-Datei).
    import services.api.routers.healing as healing_router
    from dq_core.enforce.split import RowPredicate, SplitSpec

    spec = SplitSpec(
        object_id="DS_SALES_ORDERS", source='"CORE"."DS_SALES_ORDERS"',
        predicates=[RowPredicate("amount_not_null", "missing", 'DQ_SRC."AMOUNT" IS NULL')],
        columns=["ID", "AMOUNT", "CURRENCY"],
    )
    monkeypatch.setattr(healing_router, "split_spec_for", lambda *a, **k: spec)
    monkeypatch.setattr(healing_router, "run_recheck", lambda *a, **k: 0)

    resp = api_client.post(
        f"/api/healing/episodes/{episode_id}/corrections",
        json={"keys": {"ID": "42"}, "column": "AMOUNT", "new_value": "100",
              "before_value": "", "reason": "Tippfehler"},
        headers=STEWARD,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["correction"]["column_name"] == "AMOUNT"
    assert body["correction"]["row_key"] == {"ID": "42"}
    # Ohne Materialisierung ist die Korrektur auditiert, aber nicht projiziert.
    assert body["correction"]["applied"] is False
    assert body["release_ready"] is True

    stored = store.list_healing_corrections(episode_id=episode_id)
    assert len(stored) == 1
    assert stored[0]["actor"]


def test_correction_rejects_unknown_column(api_client, monkeypatch):
    _inventory_with_columns()
    store = get_store()
    episode_id = _open_episode(store)

    import services.api.routers.healing as healing_router
    from dq_core.enforce.split import RowPredicate, SplitSpec

    spec = SplitSpec(
        object_id="DS_SALES_ORDERS", source='"CORE"."DS_SALES_ORDERS"',
        predicates=[RowPredicate("c", "missing", "1=1")],
        columns=["ID", "AMOUNT"],
    )
    monkeypatch.setattr(healing_router, "split_spec_for", lambda *a, **k: spec)

    def _raise(*a, **k):
        from dq_core.enforce.healing import HealingError
        raise HealingError("Unbekannte Spalte 'NICHT_DA' für dieses Objekt")

    monkeypatch.setattr(healing_router, "apply_correction", _raise)
    resp = api_client.post(
        f"/api/healing/episodes/{episode_id}/corrections",
        json={"keys": {"ID": "1"}, "column": "NICHT_DA", "new_value": "x"},
        headers=STEWARD,
    )
    assert resp.status_code == 422
    # Nichts auditiert, wenn die Eingabe ungültig war.
    assert store.list_healing_corrections(episode_id=episode_id) == []


def test_correction_rejected_on_terminal_episode(api_client):
    store = get_store()
    episode_id = _open_episode(store)
    store.resolve_quarantine(episode_id, "system", reason="expired")

    resp = api_client.post(
        f"/api/healing/episodes/{episode_id}/corrections",
        json={"keys": {"ID": "1"}, "column": "AMOUNT", "new_value": "1"},
        headers=STEWARD,
    )
    assert resp.status_code == 409


# ------------------------------------------------------- Freigabe-Vorbedingungen

def test_release_blocked_for_the_corrector_on_contract_episodes(api_client):
    _contract("consumer_contract")
    store = get_store()
    episode_id = _open_episode(store)
    store.add_healing_correction(
        object_id="DS_SALES_ORDERS", episode_id=episode_id, row_key={"ID": "1"},
        column_name="AMOUNT", before_value=None, after_value="1", actor="Dev User",
    )
    # In NoAuth heißt der rollen-simulierte Principal 'Dev User' — derselbe Akteur.
    resp = api_client.post(f"/api/quarantine/{episode_id}/release", json={}, headers=STEWARD)
    assert resp.status_code == 409
    assert "Four-eyes" in resp.json()["detail"]


def test_release_allowed_for_a_different_actor(api_client):
    _contract("consumer_contract")
    store = get_store()
    episode_id = _open_episode(store)
    store.add_healing_correction(
        object_id="DS_SALES_ORDERS", episode_id=episode_id, row_key={"ID": "1"},
        column_name="AMOUNT", before_value=None, after_value="1", actor="jemand-anderes",
    )
    resp = api_client.post(f"/api/quarantine/{episode_id}/release", json={}, headers=STEWARD)
    assert resp.status_code == 200
    assert resp.json()["status"] == "released"


def test_internal_gate_episode_has_no_four_eyes_rule(api_client):
    _contract("internal_gate")
    store = get_store()
    episode_id = _open_episode(store)
    store.add_healing_correction(
        object_id="DS_SALES_ORDERS", episode_id=episode_id, row_key={"ID": "1"},
        column_name="AMOUNT", before_value=None, after_value="1", actor="Dev User",
    )
    assert api_client.post(f"/api/quarantine/{episode_id}/release", json={}, headers=STEWARD).status_code == 200


def test_release_without_corrections_is_unchanged(api_client):
    _contract("consumer_contract")
    store = get_store()
    episode_id = _open_episode(store)
    assert api_client.post(f"/api/quarantine/{episode_id}/release", json={}, headers=STEWARD).status_code == 200


def test_release_blocked_while_rows_still_violate(api_client, monkeypatch):
    _contract("internal_gate")
    store = get_store()
    episode_id = _open_episode(store)
    store.add_healing_correction(
        object_id="DS_SALES_ORDERS", episode_id=episode_id, row_key={"ID": "1"},
        column_name="AMOUNT", before_value=None, after_value="1", actor="jemand",
    )
    import services.api.healing as healing_service
    from dq_core.enforce.split import RowPredicate, SplitSpec

    spec = SplitSpec(
        object_id="DS_SALES_ORDERS", source='"C"."DS_SALES_ORDERS"',
        predicates=[RowPredicate("c", "missing", "1=1")], columns=["ID"],
    )
    monkeypatch.setattr(healing_service, "split_spec_for", lambda *a, **k: spec)
    monkeypatch.setattr(healing_service, "run_recheck", lambda *a, **k: 3)

    resp = api_client.post(f"/api/quarantine/{episode_id}/release", json={}, headers=STEWARD)
    assert resp.status_code == 409
    assert "3 row(s)" in resp.json()["detail"]


# ------------------------------------------------------------- H3 Patch-Overlay

def test_patch_lifecycle_create_replace_revoke(api_client):
    _inventory_with_columns()
    store = get_store()

    created = api_client.post("/api/healing/patches", headers=OWNER, json={
        "object_id": "DS_SALES_ORDERS", "keys": {"ID": "42"},
        "values": {"AMOUNT": "100"}, "reason": "Quellfehler",
    })
    assert created.status_code == 201
    body = created.json()
    assert body["patch_table"] == "DQ_PATCH_DS_SALES_ORDERS"
    assert body["healed_view"] == "V_DQ_HEALED_DS_SALES_ORDERS"
    first_id = body["patch"]["id"]
    assert body["patch"]["status"] == "active"
    assert body["patch"]["applied"] is False       # keine Materialisierung im Test

    # Zweiter Patch auf denselben Schlüssel ersetzt den ersten.
    second = api_client.post("/api/healing/patches", headers=OWNER, json={
        "object_id": "DS_SALES_ORDERS", "keys": {"ID": "42"}, "values": {"AMOUNT": "200"},
    })
    assert second.status_code == 201
    states = {p["id"]: p["status"] for p in store.list_healing_patches(object_id="DS_SALES_ORDERS")}
    assert states[first_id] == "revoked"
    assert states[second.json()["patch"]["id"]] == "active"

    # Rücknahme behält die Zeile als Audit.
    revoked = api_client.post(
        f"/api/healing/patches/{second.json()['patch']['id']}/revoke", headers=OWNER,
    )
    assert revoked.status_code == 200
    assert revoked.json()["patch"]["status"] == "revoked"
    assert len(store.list_healing_patches(object_id="DS_SALES_ORDERS")) == 2


def test_patch_rejects_key_column_as_patch_target(api_client):
    _inventory_with_columns()
    resp = api_client.post("/api/healing/patches", headers=OWNER, json={
        "object_id": "DS_SALES_ORDERS", "keys": {"ID": "42"}, "values": {"ID": "43"},
        "patch_columns": ["ID"],
    })
    assert resp.status_code == 422


def test_patch_rejects_invalid_valid_until(api_client):
    _inventory_with_columns()
    resp = api_client.post("/api/healing/patches", headers=OWNER, json={
        "object_id": "DS_SALES_ORDERS", "keys": {"ID": "42"},
        "values": {"AMOUNT": "1"}, "valid_until": "irgendwann",
    })
    assert resp.status_code == 422


def test_expired_patch_is_reported_as_expired(api_client):
    _inventory_with_columns()
    store = get_store()
    store.upsert_healing_patch(
        patch_id="p-old", object_id="DS_SALES_ORDERS", keys={"ID": "1"},
        values={"AMOUNT": "1"}, valid_until="2020-01-01T00:00:00+00:00", actor="o",
    )
    patches = api_client.get("/api/healing/patches?object_id=DS_SALES_ORDERS", headers=STEWARD).json()["patches"]
    assert patches[0]["status"] == "expired"


def test_double_revoke_conflicts(api_client):
    _inventory_with_columns()
    store = get_store()
    store.upsert_healing_patch(
        patch_id="p-1", object_id="DS_SALES_ORDERS", keys={"ID": "1"},
        values={"AMOUNT": "1"}, actor="o",
    )
    assert api_client.post("/api/healing/patches/p-1/revoke", headers=OWNER).status_code == 200
    assert api_client.post("/api/healing/patches/p-1/revoke", headers=OWNER).status_code == 409
    assert api_client.post("/api/healing/patches/unbekannt/revoke", headers=OWNER).status_code == 404


# ----------------------------------------------------------------------- Plan

def test_plan_shows_both_healing_paths(api_client):
    _inventory_with_columns()
    plan = api_client.get("/api/healing/plan?object_id=DS_SALES_ORDERS", headers=STEWARD)
    assert plan.status_code == 200
    body = plan.json()
    assert body["enabled"] is False                 # Materialisierung im Test aus
    # H3 ist ohne kompilierte Checks planbar (nur Inventar nötig)
    assert body["h3"]["patch_table"] == "DQ_PATCH_DS_SALES_ORDERS"
    assert body["h3"]["key_columns"] == ["ID"]
    assert any("V_DQ_HEALED_DS_SALES_ORDERS" in d for d in body["h3"]["ddl"])
    # Die Quelle wird nur gelesen — kein schreibendes Statement auf ihr
    assert all("UPDATE \"CORE\"" not in d for d in body["h3"]["ddl"])


def test_overview_lists_healable_episodes(api_client):
    _contract("consumer_contract")
    store = get_store()
    episode_id = _open_episode(store)
    store.add_healing_correction(
        object_id="DS_SALES_ORDERS", episode_id=episode_id, row_key={"ID": "1"},
        column_name="AMOUNT", before_value=None, after_value="1", actor="a",
    )
    body = api_client.get("/api/healing/overview", headers=STEWARD).json()
    assert body["corrections_total"] == 1
    row = next(e for e in body["episodes"] if e["episode_id"] == episode_id)
    assert row["corrections"] == 1
    assert row["four_eyes"] is True
    assert row["kind"] == "consumer_contract"
