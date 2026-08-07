"""Notification routing (R4-2): ownership → channels, SSRF-delegated."""
from types import SimpleNamespace

import yaml

from services.api import notify


def _settings(tmp_path, routes=None, webhook_url="", allowlist=None):
    nf = tmp_path / "notifications.yml"
    if routes is not None:
        nf.write_text(yaml.safe_dump(routes), encoding="utf-8")
    return SimpleNamespace(
        notifications_file=str(nf),
        webhook_url=webhook_url,
        webhook_allowlist=allowlist or [],
    )


class _SyncThread:
    """Run the daemon target inline so tests are deterministic."""

    def __init__(self, target=None, args=(), daemon=None):
        self._target, self._args = target, args

    def start(self):
        self._target(*self._args)


def _capture(monkeypatch):
    calls = []
    monkeypatch.setattr(notify, "fire_webhook", lambda url, payload, allow: calls.append((url, payload, allow)))
    monkeypatch.setattr(notify.threading, "Thread", _SyncThread)
    return calls


# ---- resolve_targets ----

def test_owned_by_route_matches():
    routes = {"routes": [{"match": {"owned_by": "platform"},
                          "targets": [{"type": "slack", "url": "https://s/x"}]}]}
    t = notify.resolve_targets(routes, "platform", [], "")
    assert t == [{"type": "slack", "url": "https://s/x"}]


def test_owner_membership_route_matches():
    routes = {"routes": [{"match": {"owner": "grp:data-eng"},
                          "targets": [{"type": "teams", "url": "https://t/x"}]}]}
    assert notify.resolve_targets(routes, "x", ["grp:data-eng"], "")
    assert notify.resolve_targets(routes, "x", ["grp:other"], "") == []


def test_falls_back_to_default_then_webhook_url():
    routes = {"default": [{"type": "webhook", "url": "https://d/x"}]}
    assert notify.resolve_targets(routes, "nobody", [], "")[0]["url"] == "https://d/x"
    # no routes/default → implicit webhook_url
    assert notify.resolve_targets({}, "nobody", [], "https://w/x")[0]["url"] == "https://w/x"
    # nothing configured → no targets
    assert notify.resolve_targets({}, "nobody", [], "") == []


def test_targets_deduplicated():
    routes = {"routes": [
        {"match": {"owned_by": "p"}, "targets": [{"type": "slack", "url": "https://s/x"}]},
        {"match": {"owner": "o"}, "targets": [{"type": "slack", "url": "https://s/x"}]},
    ]}
    assert len(notify.resolve_targets(routes, "p", ["o"], "")) == 1


# ---- payload shapes ----

def _ctx():
    return {
        "product": "DS_X", "compliance": "breached", "run_id": "r1",
        "contract_version": "1.2.0", "failed_checks": ["c1", "c2"],
        "severity": "critical", "title": "Breach", "incident_id": 7,
        "link": "/objects/DS_X?run=r1", "ts": "2026-06-12T00:00:00+00:00",
    }


def test_slack_payload_is_text():
    p = notify._format_payload("slack", _ctx())
    assert "text" in p and "DS_X" in p["text"] and "c1, c2" in p["text"]


def test_teams_payload_is_messagecard():
    p = notify._format_payload("teams", _ctx())
    assert p["@type"] == "MessageCard"
    assert p["themeColor"] == notify._SEVERITY_COLOR["critical"]


def test_webhook_payload_is_structured():
    p = notify._format_payload("webhook", _ctx())
    assert p["product"] == "DS_X" and p["incident_id"] == 7
    assert p["failed_checks"] == ["c1", "c2"]


def test_webhook_payload_carries_cluster_fields():
    p = notify._format_payload("webhook", {
        **_ctx(),
        "cluster_id": "cluster_1",
        "member_count": 3,
        "affected_products": ["A", "B"],
        "probable_cause": "SRC",
        "impacted_objects": [{"product": "B", "distance": 1}],
        "kind": "consumer_contract",
    })
    assert p["cluster_id"] == "cluster_1"
    assert p["member_count"] == 3
    assert p["probable_cause"] == "SRC"
    assert p["impacted_objects"] == [{"product": "B", "distance": 1}]


def test_chat_payloads_include_impact_summary():
    ctx = {**_ctx(), "impacted_objects": [{"product": "B"}, {"product": "C"}]}

    slack = notify._format_payload("slack", ctx)
    teams = notify._format_payload("teams", ctx)

    assert "Impact: B, C" in slack["text"]
    facts = teams["sections"][0]["facts"]
    assert {"name": "Impact", "value": "B, C"} in facts


# ---- notify_breach delegates to SSRF-safe sender ----

def test_notify_breach_fires_each_target_with_allowlist(tmp_path, monkeypatch):
    calls = _capture(monkeypatch)
    routes = {"routes": [{"match": {"owned_by": "platform"}, "targets": [
        {"type": "slack", "url": "https://hooks.slack/x"},
        {"type": "webhook", "url": "https://hooks.dq/x"},
    ]}]}
    s = _settings(tmp_path, routes=routes, allowlist=[r".*\.slack", r".*\.dq"])
    notify.notify_breach(
        product="DS_X", compliance="breached", run_id="r1", contract_version="1",
        failed_checks=["c1"], severity="fail", title="T", incident_id=3,
        owned_by="platform", owners=[], settings=s,
    )
    urls = {c[0] for c in calls}
    assert urls == {"https://hooks.slack/x", "https://hooks.dq/x"}
    # every dispatch carries the allowlist → SSRF enforcement stays in fire_webhook
    assert all(c[2] == s.webhook_allowlist for c in calls)


def test_notify_breach_noop_without_targets(tmp_path, monkeypatch):
    calls = _capture(monkeypatch)
    s = _settings(tmp_path, routes={}, webhook_url="")
    notify.notify_breach(
        product="DS_X", compliance="breached", run_id="r1", contract_version="1",
        failed_checks=[], severity="fail", title="T", incident_id=None,
        owned_by="x", owners=[], settings=s,
    )
    assert calls == []


# ---- UX-N2: DB-backed routing rules + mute windows ----

def _store(tmp_path):
    import sys
    sys.path.insert(0, str(tmp_path))  # noop; ensure import side-effect-free
    from dq_core.store.sqlite_store import ResultStore
    return ResultStore(tmp_path / "n.db")


def test_is_muted_scoping():
    mutes = [{"match_space": "SALES", "match_product": "",
              "starts_at": "2026-01-01T00:00:00+00:00", "ends_at": "2030-01-01T00:00:00+00:00"}]
    assert notify.is_muted(mutes, product="DS", space="SALES") is True
    assert notify.is_muted(mutes, product="DS", space="HR") is False


def test_resolve_db_targets_matches_facets():
    channels = [{"id": 1, "type": "slack", "url": "https://s/x", "enabled": True},
                {"id": 2, "type": "webhook", "url": "https://w/y", "enabled": True}]
    rules = [{"channel_id": 1, "enabled": True, "match_severity": "critical",
              "match_space": "SALES", "match_product": "", "match_owned_by": "", "match_owner": ""}]
    hit = notify.resolve_db_targets(channels, rules, severity="critical", space="SALES",
                                    product="DS", owned_by="platform", owners=[])
    assert hit == [{"type": "slack", "url": "https://s/x"}]
    # facet mismatch → no target
    miss = notify.resolve_db_targets(channels, rules, severity="warn", space="SALES",
                                     product="DS", owned_by="platform", owners=[])
    assert miss == []


def test_resolve_db_targets_matches_kind():
    channels = [{"id": 1, "type": "slack", "url": "https://s/x", "enabled": True}]
    rules = [{"channel_id": 1, "enabled": True, "match_kind": "internal_gate"}]
    hit = notify.resolve_db_targets(
        channels, rules, severity="critical", space="", product="DS",
        owned_by="platform", owners=[], kind="internal_gate",
    )
    miss = notify.resolve_db_targets(
        channels, rules, severity="critical", space="", product="DS",
        owned_by="platform", owners=[], kind="consumer_contract",
    )
    assert hit == [{"type": "slack", "url": "https://s/x"}]
    assert miss == []


def test_notify_breach_uses_db_rules_over_yaml(tmp_path, monkeypatch):
    calls = _capture(monkeypatch)
    store = _store(tmp_path)
    ch = store.create_notification_channel(name="ops", type="slack", url="https://db.slack/x")
    store.create_notification_rule(name="crit-sales", channel_id=ch["id"],
                                   match_severity="critical", match_space="SALES",
                                   match_kind="consumer_contract")
    # YAML default also present — DB must win.
    s = _settings(tmp_path, routes={"default": [{"type": "webhook", "url": "https://yaml/x"}]},
                  allowlist=[r".*"])
    notify.notify_breach(
        product="DS_X", compliance="breached", run_id="r1", contract_version="1",
        failed_checks=["c1"], severity="critical", title="T", incident_id=3,
        owned_by="platform", owners=[], settings=s, store=store, space="SALES",
        kind="consumer_contract",
    )
    assert {c[0] for c in calls} == {"https://db.slack/x"}


def test_notify_breach_suppressed_by_active_mute(tmp_path, monkeypatch):
    calls = _capture(monkeypatch)
    store = _store(tmp_path)
    ch = store.create_notification_channel(name="ops", type="slack", url="https://db.slack/x")
    store.create_notification_rule(name="all", channel_id=ch["id"], match_severity="critical")
    store.create_notification_mute(starts_at="2026-01-01T00:00:00+00:00",
                                   ends_at="2030-01-01T00:00:00+00:00", match_space="SALES")
    s = _settings(tmp_path, routes={}, allowlist=[r".*"])
    notify.notify_breach(
        product="DS_X", compliance="breached", run_id="r1", contract_version="1",
        failed_checks=["c1"], severity="critical", title="T", incident_id=3,
        owned_by="platform", owners=[], settings=s, store=store, space="SALES",
    )
    assert calls == []  # mute window suppressed delivery


# ---- notify_incident_transition ----

def _transition_ctx():
    return dict(
        product="DS_X", incident_id=7, severity="critical", title="Breach",
        action="status_changed", actor="alice", note="urgent",
        new_status="acknowledged", new_owner=None,
    )


def test_transition_slack_payload():
    p = notify._format_transition_payload("slack", {**_transition_ctx(), "link": "/incidents/7", "ts": "t"})
    assert "text" in p
    assert "DS_X" in p["text"]
    assert "acknowledged" in p["text"]
    assert "alice" in p["text"]


def test_transition_teams_payload():
    p = notify._format_transition_payload("teams", {**_transition_ctx(), "link": "/incidents/7", "ts": "t"})
    assert p["@type"] == "MessageCard"
    assert p["themeColor"] == notify._SEVERITY_COLOR["critical"]
    facts_names = [f["name"] for f in p["sections"][0]["facts"]]
    assert "Action" in facts_names and "Actor" in facts_names


def test_transition_webhook_payload():
    p = notify._format_transition_payload("webhook", {**_transition_ctx(), "link": "/incidents/7", "ts": "t"})
    assert p["product"] == "DS_X"
    assert p["incident_id"] == 7
    assert p["action"] == "status_changed"
    assert p["new_status"] == "acknowledged"


def test_notify_incident_transition_fires_on_status_change(tmp_path, monkeypatch):
    calls = _capture(monkeypatch)
    routes = {"routes": [{"match": {"owned_by": "platform"},
                          "targets": [{"type": "webhook", "url": "https://hooks.dq/x"}]}]}
    s = _settings(tmp_path, routes=routes, allowlist=[r".*\.dq"])
    notify.notify_incident_transition(
        product="DS_X", incident_id=5, severity="fail", title="T",
        action="status_changed", actor="alice", note="", new_status="resolved",
        new_owner=None, owned_by="platform", owners=[], settings=s,
    )
    assert len(calls) == 1
    assert calls[0][0] == "https://hooks.dq/x"


def test_notify_incident_transition_fires_on_owner_assignment(tmp_path, monkeypatch):
    calls = _capture(monkeypatch)
    routes = {"default": [{"type": "webhook", "url": "https://hooks.dq/x"}]}
    s = _settings(tmp_path, routes=routes, allowlist=[r".*\.dq"])
    notify.notify_incident_transition(
        product="DS_X", incident_id=5, severity="fail", title="T",
        action="assigned", actor="bob", note="", new_status=None,
        new_owner="carol", owned_by="x", owners=[], settings=s,
    )
    assert len(calls) == 1
    payload = calls[0][1]
    assert payload["new_owner"] == "carol"


def test_notify_incident_transition_noop_without_targets(tmp_path, monkeypatch):
    calls = _capture(monkeypatch)
    s = _settings(tmp_path, routes={}, webhook_url="")
    notify.notify_incident_transition(
        product="DS_X", incident_id=5, severity="fail", title="T",
        action="status_changed", actor="alice", note="", new_status="resolved",
        new_owner=None, owned_by="x", owners=[], settings=s,
    )
    assert calls == []
