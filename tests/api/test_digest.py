"""V4 Qualitäts-Digest: Aggregation, Opt-in-Versand, Claim-Semantik."""
from datetime import datetime, timedelta, timezone

import services.api.digest as digest_mod
from dq_core.engine.models import CheckResult, RunSummary
from services.api.deps import get_store
from services.api.settings import get_settings

NOW = datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc)


class _SyncThread:
    """Versand synchron ausführen, damit Tests deterministisch prüfen können."""

    def __init__(self, target=None, args=(), daemon=None):
        self._target, self._args = target, args

    def start(self):
        self._target(*self._args)


def _seed(store):
    at = (NOW - timedelta(hours=2)).isoformat()
    store.save_run(RunSummary(
        run_id="run-1", dataset="DS_SALES_ORDERS", schema="X",
        started_at=at, finished_at=at, overall_status="fail",
        total=1, passed=0, failed=1, warnings=0,
        results=[CheckResult(name="volume_min_rows", sql="", expect=">= 1",
                             severity="fail", passed=False, actual_value="0")],
    ))
    store.open_incident(
        product="DS_SALES_ORDERS", run_id="run-1", severity="fail",
        title="Volume unter Minimum", failed_checks=["volume_min_rows"],
        contract_version="1.0.0", kind="internal_gate", actor="system",
    )


def test_build_digest_aggregates_period(api_client):
    store = get_store()
    _seed(store)

    d = digest_mod.build_digest(store, hours=24, now=NOW)
    assert d["incidents_new"] == 1
    assert d["incidents_open"] == 1
    assert d["runs"] == 1
    assert d["runs_failed"] == 1
    assert d["top_incidents"][0]["product"] == "DS_SALES_ORDERS"


def test_digest_preview_endpoint(api_client):
    _seed(get_store())
    resp = api_client.get("/api/notifications/digest/preview")
    assert resp.status_code == 200
    body = resp.json()
    assert body["incidents_new"] == 1
    assert body["subscribed_channels"] == 0
    assert body["enabled"] is False


def test_digest_send_requires_subscribed_channel(api_client):
    assert api_client.post(
        "/api/notifications/digest/send", headers={"X-DQ-Role": "steward"},
    ).status_code == 409


def test_digest_send_fires_subscribed_channels(api_client, monkeypatch):
    store = get_store()
    _seed(store)
    ch = store.create_notification_channel(
        name="Ops", type="slack", url="https://hooks.slack.example.com/x", actor="t",
    )
    store.update_notification_channel(ch["id"], digest_enabled=True)

    fired: list[tuple[str, dict]] = []
    monkeypatch.setattr(digest_mod, "fire_webhook", lambda url, payload, allow: fired.append((url, payload)))
    monkeypatch.setattr(digest_mod.threading, "Thread", _SyncThread)

    resp = api_client.post(
        "/api/notifications/digest/send", headers={"X-DQ-Role": "steward"},
    )
    assert resp.status_code == 200
    assert resp.json()["targets"] == 1
    assert len(fired) == 1
    assert "Signal-Digest" in fired[0][1]["text"]  # Slack-Payload
    assert store.get_meta("digest_last_sent") is not None


def test_digest_send_forbidden_for_viewer(api_client):
    assert api_client.post(
        "/api/notifications/digest/send", headers={"X-DQ-Role": "viewer"},
    ).status_code == 403


def test_claim_digest_slot_is_interval_gated(api_client):
    store = get_store()
    assert store.claim_digest_slot(NOW.isoformat(), 24) is True          # erster Claim
    assert store.claim_digest_slot((NOW + timedelta(hours=1)).isoformat(), 24) is False
    assert store.claim_digest_slot((NOW + timedelta(hours=25)).isoformat(), 24) is True


def test_digest_tick_respects_optin_and_flag(api_client, monkeypatch):
    store = get_store()
    settings = get_settings()

    # Flag aus → kein Versand
    assert digest_mod.digest_tick(store, settings) is False

    monkeypatch.setattr(settings, "digest_enabled", True)
    # Kein Abonnent → kein Versand, Slot bleibt unverbraucht
    assert digest_mod.digest_tick(store, settings) is False
    assert store.get_meta("digest_last_sent") is None

    ch = store.create_notification_channel(
        name="Ops", type="webhook", url="https://hooks.example.com/dq", actor="t",
    )
    store.update_notification_channel(ch["id"], digest_enabled=True)
    monkeypatch.setattr(digest_mod, "fire_webhook", lambda *a: None)
    monkeypatch.setattr(digest_mod.threading, "Thread", _SyncThread)
    assert digest_mod.digest_tick(store, settings) is True
    assert digest_mod.digest_tick(store, settings) is False  # Intervall noch nicht um
