"""Qualitäts-Digest (V4): periodischer Rollup über die Notification-Kanäle.

Aggregiert den Zustand der letzten Periode (Incidents, Läufe/Gate-Verdicts,
Quarantäne, Schema-Drift) aus dem Store — rein lesend — und stellt ihn über
die bestehenden Kanal-Typen zu (Slack/Teams/generischer Webhook, SSRF-Guards
via ``webhook.fire_webhook``). Kanäle abonnieren den Digest explizit
(``digest_enabled``, Opt-in); es gibt bewusst **kein** implizites Fan-out auf
alle Kanäle. Der periodische Versand läuft über den Scheduler-Tick mit
Multi-Worker-Claim (``claim_digest_slot``); manueller Versand über
``POST /api/notifications/digest/send``.
"""
from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from typing import Any

from .webhook import fire_webhook


def _parse_ts(value: Any) -> datetime | None:
    try:
        ts = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)


def build_digest(store: Any, hours: int = 24, now: datetime | None = None) -> dict[str, Any]:
    """Kennzahlen der letzten ``hours`` Stunden — nur Aggregate, keine Rohzeilen (G8)."""
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=hours)

    incidents = store.list_incidents()
    new_incidents = [i for i in incidents if (_parse_ts(i.get("opened_at")) or now) >= cutoff]
    open_incidents = [i for i in incidents if i.get("status") != "resolved"]
    new_by_severity: dict[str, int] = {}
    for i in new_incidents:
        sev = str(i.get("severity") or "fail")
        new_by_severity[sev] = new_by_severity.get(sev, 0) + 1

    runs = [
        r for r in store.get_all_runs(limit=1000)
        if (_parse_ts(r.get("started_at")) or now) >= cutoff
    ]
    failed_runs = [r for r in runs if r.get("overall_status") not in ("pass", "warn")]
    verdicts: dict[str, int] = {}
    for r in runs:
        v = str(r.get("gate_verdict") or "proceed")
        verdicts[v] = verdicts.get(v, 0) + 1

    quarantine_open = store.list_quarantine(status="open", limit=200)

    drift_rows = store.list_schema_drift_objects()
    drift_new = [
        d for d in drift_rows
        if d.get("last_detected_at") and (_parse_ts(d["last_detected_at"]) or now) >= cutoff
    ]

    top = sorted(
        new_incidents,
        key=lambda i: ({"critical": 0, "fail": 1, "warn": 2}.get(str(i.get("severity")), 3),
                       str(i.get("opened_at") or "")),
    )[:5]

    return {
        "period_hours": hours,
        "generated_at": now.isoformat(),
        "incidents_new": len(new_incidents),
        "incidents_new_by_severity": new_by_severity,
        "incidents_open": len(open_incidents),
        "top_incidents": [
            {
                "id": i.get("id"),
                "product": i.get("product", ""),
                "severity": i.get("severity", ""),
                "title": i.get("title", ""),
            }
            for i in top
        ],
        "runs": len(runs),
        "runs_failed": len(failed_runs),
        "gate_verdicts": verdicts,
        "quarantine_open": len(quarantine_open),
        "drift_objects": len(drift_new),
        "drift_breaking_objects": sum(1 for d in drift_new if d.get("breaking")),
    }


def _summary_line(d: dict[str, Any]) -> str:
    return (
        f"Signal-Digest ({d['period_hours']} h): "
        f"{d['incidents_new']} neue Incidents ({d['incidents_open']} offen) · "
        f"{d['runs_failed']}/{d['runs']} Läufe rot · "
        f"{d['quarantine_open']} Quarantäne-Episoden offen · "
        f"{d['drift_objects']} Objekte mit Schema-Drift"
    )


def format_digest_payload(target_type: str, d: dict[str, Any], link: str = "/") -> dict[str, Any]:
    summary = _summary_line(d)
    top = "\n".join(
        f"• [{i['severity']}] {i['product']}: {i['title']}" for i in d["top_incidents"]
    )
    if target_type == "slack":
        text = f":bar_chart: *{summary}*"
        if top:
            text += f"\n{top}"
        text += f"\n<{link}|Cockpit öffnen>"
        return {"text": text}
    if target_type == "teams":
        facts = [
            {"name": "Neue Incidents", "value": str(d["incidents_new"])},
            {"name": "Offene Incidents", "value": str(d["incidents_open"])},
            {"name": "Läufe (rot/gesamt)", "value": f"{d['runs_failed']}/{d['runs']}"},
            {"name": "Quarantäne offen", "value": str(d["quarantine_open"])},
            {"name": "Schema-Drift", "value": str(d["drift_objects"])},
        ]
        return {
            "@type": "MessageCard",
            "@context": "http://schema.org/extensions",
            "summary": summary,
            "themeColor": "2E86C1",
            "title": summary,
            "sections": [{"facts": facts, "text": f"[Cockpit öffnen]({link})"}],
        }
    # Generischer Webhook — vollständige strukturierte Kennzahlen.
    return dict(d)


def digest_targets(store: Any) -> list[dict[str, Any]]:
    """Explizit abonnierte, aktive Kanäle (Opt-in — nie alle Kanäle)."""
    return [
        {"type": c.get("type", "webhook"), "url": c["url"]}
        for c in store.list_notification_channels()
        if c.get("enabled") and c.get("digest_enabled") and c.get("url")
    ]


def send_digest(store: Any, settings: Any, hours: int = 24) -> dict[str, Any]:
    """Digest bauen und an alle abonnierten Kanäle feuern (non-blocking)."""
    digest = build_digest(store, hours=hours)
    targets = digest_targets(store)
    allowlist = settings.webhook_allowlist
    for tgt in targets:
        payload = format_digest_payload(tgt["type"], digest)
        threading.Thread(
            target=fire_webhook, args=(tgt["url"], payload, allowlist), daemon=True,
        ).start()
    return {"digest": digest, "targets": len(targets)}


def digest_tick(store: Any, settings: Any) -> bool:
    """Scheduler-Hook: sendet, wenn aktiviert, Kanäle abonniert sind und der
    Claim gewonnen wird. ``True`` = in diesem Tick versendet."""
    if not settings.digest_enabled:
        return False
    if not digest_targets(store):
        return False  # kein Abonnent → auch keinen Slot verbrauchen
    now_iso = datetime.now(timezone.utc).isoformat()
    if not store.claim_digest_slot(now_iso, settings.digest_interval_hours):
        return False
    send_digest(store, settings, hours=settings.digest_interval_hours)
    return True
