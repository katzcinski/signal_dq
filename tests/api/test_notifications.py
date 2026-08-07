"""UX-N2: notification-routing API — CRUD, platform-owner authz, validation."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "packages"))
sys.path.insert(0, str(Path(__file__).parents[2]))

SLACK = "https://hooks.slack.example.com/services/T/B/X"
VIEWER = {"X-DQ-Role": "viewer"}
STEWARD = {"X-DQ-Role": "steward"}


def _make_channel(api_client, name="ops", type="slack", url=SLACK):
    return api_client.post("/api/notifications/channels",
                           json={"name": name, "type": type, "url": url})


def test_channel_crud_roundtrip(api_client):
    resp = _make_channel(api_client)
    assert resp.status_code == 201, resp.text
    cid = resp.json()["id"]

    cfg = api_client.get("/api/notifications/config").json()
    assert any(c["id"] == cid for c in cfg["channels"])
    assert cfg["can_edit"] is True  # default dev principal is admin

    # toggle enabled
    patched = api_client.patch(f"/api/notifications/channels/{cid}", json={"enabled": False})
    assert patched.status_code == 200
    assert patched.json()["enabled"] is False

    assert api_client.delete(f"/api/notifications/channels/{cid}").status_code == 204
    assert api_client.delete(f"/api/notifications/channels/{cid}").status_code == 404


def test_rule_requires_existing_channel(api_client):
    bad = api_client.post("/api/notifications/rules",
                          json={"name": "r", "channel_id": 99999, "match_severity": "critical"})
    assert bad.status_code == 422


def test_rule_creation_and_facet_validation(api_client):
    cid = _make_channel(api_client).json()["id"]
    ok = api_client.post("/api/notifications/rules", json={
        "name": "Critical on SALES", "channel_id": cid,
        "match_severity": "critical", "match_space": "SALES",
    })
    assert ok.status_code == 201, ok.text
    # bad severity facet rejected
    bad = api_client.post("/api/notifications/rules", json={
        "name": "x", "channel_id": cid, "match_severity": "bogus"})
    assert bad.status_code == 422


def test_mute_window_validation(api_client):
    # end before start → 422
    bad = api_client.post("/api/notifications/mutes", json={
        "starts_at": "2026-06-02T00:00:00Z", "ends_at": "2026-06-01T00:00:00Z"})
    assert bad.status_code == 422
    ok = api_client.post("/api/notifications/mutes", json={
        "reason": "maintenance", "match_space": "SALES",
        "starts_at": "2026-06-01T00:00:00Z", "ends_at": "2026-06-02T00:00:00Z"})
    assert ok.status_code == 201, ok.text
    mid = ok.json()["id"]
    assert api_client.delete(f"/api/notifications/mutes/{mid}").status_code == 204


def test_url_must_be_https(api_client):
    bad = _make_channel(api_client, url="http://insecure.example.com/x")
    assert bad.status_code == 422


def test_writes_require_platform_owner(api_client):
    # viewer and steward cannot mutate notification config (platform-owner only)
    assert _make_channel(api_client).status_code == 201  # admin default works
    for headers in (VIEWER, STEWARD):
        r = api_client.post("/api/notifications/channels",
                            json={"name": "n", "type": "slack", "url": SLACK}, headers=headers)
        assert r.status_code == 403, headers
    # but reads are allowed for non-admins
    assert api_client.get("/api/notifications/config", headers=VIEWER).status_code == 200
    assert api_client.get("/api/notifications/config", headers=VIEWER).json()["can_edit"] is False
