"""Ownership-routed breach/incident notifications (R4-2).

A single generic webhook is replaced by ownership-based routing: a contract's
owner decides which channel(s) get paged, and each channel renders the breach
in its own payload shape (Slack / Microsoft Teams / generic webhook). Routing
is configured in an optional YAML file (``notifications_file``); when it is
absent, ``webhook_url`` acts as an implicit default target so existing
deployments keep working unchanged.

Security: every resolved target URL is fired through ``webhook.fire_webhook``,
which enforces the same SSRF guards (https-only, allowlist, private-IP block,
no redirects, timeout). Routing therefore can never become an SSRF bypass — a
target host that is not in ``webhook_allowlist`` is simply dropped.

Config shape (``notifications.yml``)::

    default:
      - { type: webhook, url: "https://hooks.example.com/dq" }
    routes:
      - match: { owned_by: platform }
        targets:
          - { type: slack, url: "https://hooks.slack.example.com/services/T/B/X" }
      - match: { owner: "grp:data-eng" }
        targets:
          - { type: teams, url: "https://outlook.office.example.com/webhook/..." }
"""
from __future__ import annotations

import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from .webhook import fire_webhook

# Teams MessageCard theme colour per severity.
_SEVERITY_COLOR = {"critical": "C0392B", "fail": "E67E22", "warn": "F1C40F"}


def _load_routes(path: str) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {}
    try:
        return yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def _route_matches(match: dict[str, Any], owned_by: str, owners: list[str]) -> bool:
    """A route matches when every key in its ``match`` block matches the
    contract. ``owned_by`` is an equality test; ``owner`` is membership in the
    contract's ``owners`` list."""
    if not match:
        return False
    if "owned_by" in match and match["owned_by"] != owned_by:
        return False
    if "owner" in match and match["owner"] not in (owners or []):
        return False
    return True


def resolve_targets(
    routes: dict[str, Any],
    owned_by: str,
    owners: list[str],
    fallback_url: str,
) -> list[dict[str, Any]]:
    """Targets for a contract: union of matching routes, else ``default``, else
    the implicit ``webhook_url`` fallback. De-duplicated by (type, url)."""
    targets: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    def _add(tgt: dict[str, Any]) -> None:
        url = tgt.get("url")
        key = (tgt.get("type", "webhook"), url or "")
        if url and key not in seen:
            seen.add(key)
            targets.append(tgt)

    for route in routes.get("routes", []) or []:
        if _route_matches(route.get("match", {}), owned_by, owners):
            for tgt in route.get("targets", []) or []:
                _add(tgt)
    if not targets:
        for tgt in routes.get("default", []) or []:
            _add(tgt)
    if not targets and fallback_url:
        _add({"type": "webhook", "url": fallback_url})
    return targets


# ---------------------------------------------------------------------------
# UX-N2: DB-backed routing rules + mute windows (server-authoritative).
# When any rule produces a target the DB wins; otherwise the YAML fallback
# (resolve_targets) keeps existing deployments working unchanged.
# ---------------------------------------------------------------------------

def _parse_iso(value: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def is_muted(
    mutes: list[dict[str, Any]],
    *,
    product: str,
    space: str,
    at: datetime | None = None,
) -> bool:
    """True when an active mute window covers this product/space at time ``at``.
    A mute with empty space/product scope matches everything; a non-empty facet
    must equal the breach's. Evaluated server-side at notify time (UX-N2)."""
    now = at or datetime.now(timezone.utc)
    for mute in mutes or []:
        if mute.get("match_space") and mute["match_space"] != space:
            continue
        if mute.get("match_product") and mute["match_product"] != product:
            continue
        start = _parse_iso(mute.get("starts_at", ""))
        end = _parse_iso(mute.get("ends_at", ""))
        if start and end and start <= now <= end:
            return True
    return False


def _rule_matches(
    rule: dict[str, Any], *, severity: str, space: str, product: str,
    owned_by: str, owners: list[str], kind: str = "consumer_contract",
) -> bool:
    """A rule matches when every non-empty facet equals the breach's. Empty
    facet = wildcard. ``match_owner`` is membership in the contract owners."""
    if not rule.get("enabled", True):
        return False
    if rule.get("match_severity") and rule["match_severity"] != severity:
        return False
    if rule.get("match_space") and rule["match_space"] != space:
        return False
    if rule.get("match_product") and rule["match_product"] != product:
        return False
    if rule.get("match_owned_by") and rule["match_owned_by"] != owned_by:
        return False
    if rule.get("match_owner") and rule["match_owner"] not in (owners or []):
        return False
    if rule.get("match_kind") and rule["match_kind"] != kind:
        return False
    return True


def resolve_db_targets(
    channels: list[dict[str, Any]],
    rules: list[dict[str, Any]],
    *,
    severity: str,
    space: str,
    product: str,
    owned_by: str,
    owners: list[str],
    kind: str = "consumer_contract",
) -> list[dict[str, Any]]:
    """Targets from DB rules: every enabled rule whose facets match routes to
    its (enabled) channel. De-duplicated by (type, url)."""
    by_id = {c["id"]: c for c in channels if c.get("enabled", True)}
    targets: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for rule in rules or []:
        if not _rule_matches(rule, severity=severity, space=space, product=product,
                             owned_by=owned_by, owners=owners, kind=kind):
            continue
        channel = by_id.get(rule.get("channel_id"))
        if not channel:
            continue
        key = (channel.get("type", "webhook"), channel.get("url", ""))
        if channel.get("url") and key not in seen:
            seen.add(key)
            targets.append({"type": channel.get("type", "webhook"), "url": channel["url"]})
    return targets


def _resolve_with_store(
    store: Any, settings: Any, *, severity: str, space: str, product: str,
    owned_by: str, owners: list[str], kind: str = "consumer_contract",
) -> tuple[list[dict[str, Any]], bool]:
    """Return (targets, muted). DB rules take precedence; YAML/webhook_url is the
    fallback. ``muted`` short-circuits delivery regardless of targets."""
    if store is not None:
        try:
            if is_muted(store.list_notification_mutes(), product=product, space=space):
                return [], True
            db_targets = resolve_db_targets(
                store.list_notification_channels(),
                store.list_notification_rules(),
                severity=severity, space=space, product=product,
                owned_by=owned_by, owners=owners, kind=kind,
            )
            if db_targets:
                return db_targets, False
        except Exception:
            pass  # DB unavailable → fall through to YAML default
    routes = _load_routes(settings.notifications_file)
    return resolve_targets(routes, owned_by, owners or [], settings.webhook_url), False


def _format_payload(target_type: str, ctx: dict[str, Any]) -> dict[str, Any]:
    summary = f"DQ breach: {ctx['product']} v{ctx['contract_version'] or '?'} ({ctx['severity']})"
    failed = ", ".join(ctx["failed_checks"]) or "—"
    impact = _impact_summary(ctx.get("impacted_objects") or [])
    impact_line = f"\nImpact: {impact}" if impact else ""
    if target_type == "slack":
        return {
            "text": (
                f":rotating_light: *{summary}*\n"
                f"Failed checks: {failed}{impact_line}\n"
                f"<{ctx['link']}|Open in cockpit>"
            )
        }
    if target_type == "teams":
        facts = [
            {"name": "Product", "value": ctx["product"]},
            {"name": "Version", "value": ctx["contract_version"] or "?"},
            {"name": "Severity", "value": ctx["severity"]},
            {"name": "Failed checks", "value": failed},
            {"name": "Run", "value": ctx["run_id"]},
        ]
        if impact:
            facts.append({"name": "Impact", "value": impact})
        return {
            "@type": "MessageCard",
            "@context": "http://schema.org/extensions",
            "summary": summary,
            "themeColor": _SEVERITY_COLOR.get(ctx["severity"], "999999"),
            "title": summary,
            "sections": [
                {
                    "facts": facts,
                    "text": f"[Open in cockpit]({ctx['link']})",
                }
            ],
        }
    # Generic webhook — full structured context (machine-routable downstream).
    return {
        k: ctx.get(k)
        for k in (
            "product", "compliance", "run_id", "contract_version",
            "failed_checks", "severity", "title", "incident_id", "kind",
            "cluster_id", "member_count", "affected_products", "probable_cause",
            "impacted_objects", "link", "ts",
        )
    }


def _impact_summary(impacted_objects: list[dict[str, Any]]) -> str:
    labels = [
        str(item.get("product") or item.get("object") or "")
        for item in impacted_objects
        if isinstance(item, dict) and (item.get("product") or item.get("object"))
    ]
    if not labels:
        return ""
    shown = ", ".join(labels[:3])
    if len(labels) > 3:
        shown = f"{shown} (+{len(labels) - 3})"
    return shown


def _format_transition_payload(target_type: str, ctx: dict[str, Any]) -> dict[str, Any]:
    action_label = {
        "status_changed": f"Status → {ctx['new_status']}",
        "assigned": f"Assigned to {ctx['new_owner']}",
    }.get(ctx["action"], ctx["action"])
    summary = f"Incident update: {ctx['product']} — {action_label}"
    note_part = f"\nNote: {ctx['note']}" if ctx.get("note") else ""
    if target_type == "slack":
        return {
            "text": (
                f":bell: *{summary}*\n"
                f"Actor: {ctx['actor']}{note_part}\n"
                f"<{ctx['link']}|Open incident>"
            )
        }
    if target_type == "teams":
        facts = [
            {"name": "Product", "value": ctx["product"]},
            {"name": "Action", "value": action_label},
            {"name": "Actor", "value": ctx["actor"]},
        ]
        if ctx.get("note"):
            facts.append({"name": "Note", "value": ctx["note"]})
        return {
            "@type": "MessageCard",
            "@context": "http://schema.org/extensions",
            "summary": summary,
            "themeColor": _SEVERITY_COLOR.get(ctx["severity"], "999999"),
            "title": summary,
            "sections": [{"facts": facts, "text": f"[Open incident]({ctx['link']})"}],
        }
    # Generic webhook — structured context.
    return {
        k: ctx.get(k)
        for k in (
            "product", "incident_id", "severity", "title",
            "action", "actor", "note", "new_status", "new_owner", "kind", "link", "ts",
        )
    }


def notify_incident_transition(
    *,
    product: str,
    incident_id: int,
    severity: str,
    title: str,
    action: str,
    actor: str,
    note: str,
    new_status: str | None,
    new_owner: str | None,
    owned_by: str,
    owners: list[str],
    settings: Any,
    store: Any = None,
    space: str = "",
    kind: str = "consumer_contract",
    cluster_id: str = "",
    member_count: int = 1,
    affected_products: list[str] | None = None,
    probable_cause: str = "",
) -> None:
    """Fire incident-transition notifications on status changes and owner assignment.

    Non-blocking: each target is dispatched on a daemon thread. SSRF-safe via
    ``fire_webhook``. A misconfigured target never breaks the API response.
    Routing/mute is server-authoritative via ``store`` (UX-N2), YAML is fallback.
    """
    targets, muted = _resolve_with_store(
        store, settings, severity=severity, space=space, product=product,
        owned_by=owned_by, owners=owners or [], kind=kind,
    )
    if muted or not targets:
        return
    ctx = {
        "product": product,
        "incident_id": incident_id,
        "severity": severity,
        "title": title,
        "action": action,
        "actor": actor,
        "note": note,
        "new_status": new_status,
        "new_owner": new_owner,
        "kind": kind,
        "link": f"/incidents/{incident_id}",
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    allowlist = settings.webhook_allowlist
    for tgt in targets:
        payload = _format_transition_payload(tgt.get("type", "webhook"), ctx)
        threading.Thread(
            target=fire_webhook,
            args=(tgt["url"], payload, allowlist),
            daemon=True,
        ).start()


def notify_breach(
    *,
    product: str,
    compliance: str,
    run_id: str,
    contract_version: str,
    failed_checks: list[str],
    severity: str,
    title: str,
    incident_id: int | None,
    owned_by: str,
    owners: list[str],
    settings: Any,
    store: Any = None,
    space: str = "",
    kind: str = "consumer_contract",
    cluster_id: str = "",
    member_count: int = 1,
    affected_products: list[str] | None = None,
    probable_cause: str = "",
    impacted_objects: list[dict[str, Any]] | None = None,
) -> None:
    """Fire breach/incident-open notifications to all routed channels.

    Non-blocking: each target is dispatched on a daemon thread. SSRF-safe via
    ``fire_webhook``. A misconfigured target never breaks the run. Routing/mute
    is server-authoritative via ``store`` (UX-N2), YAML is fallback.
    """
    targets, muted = _resolve_with_store(
        store, settings, severity=severity, space=space, product=product,
        owned_by=owned_by, owners=owners or [], kind=kind,
    )
    if muted or not targets:
        return
    ctx = {
        "product": product,
        "compliance": compliance,
        "run_id": run_id,
        "contract_version": contract_version,
        "failed_checks": failed_checks or [],
        "severity": severity,
        "title": title,
        "incident_id": incident_id,
        "kind": kind,
        "cluster_id": cluster_id,
        "member_count": member_count,
        "affected_products": affected_products or [],
        "probable_cause": probable_cause,
        "impacted_objects": impacted_objects or [],
        "link": f"/objects/{product}?run={run_id}",
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    allowlist = settings.webhook_allowlist
    for tgt in targets:
        payload = _format_payload(tgt.get("type", "webhook"), ctx)
        threading.Thread(
            target=fire_webhook,
            args=(tgt["url"], payload, allowlist),
            daemon=True,
        ).start()
