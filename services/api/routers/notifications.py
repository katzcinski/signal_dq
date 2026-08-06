"""UX-N2: Alerting & Notification-Routing — manage delivery channels, routing
rules and mute/maintenance windows. Routing is server-authoritative (notify.py
reads these tables); the frontend only mirrors. Writes are restricted to the
platform-owner (admin) role; reads are available to any authenticated principal.
"""
from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from ..auth.provider import Principal, PrincipalDep, require_roles
from ..deps import StoreDep

router = APIRouter(prefix="/api/notifications", tags=["notifications"])

# Platform-wide notification config is a platform-owner concern (admin).
require_admin = require_roles("admin")

_CHANNEL_TYPES = {"slack", "teams", "webhook"}
_SEVERITIES = {"", "critical", "fail", "warn"}
_OWNED_BY = {"", "platform", "product"}
_KINDS = {"", "internal_gate", "consumer_contract", "provider_contract"}


def _validate_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise HTTPException(
            status_code=422,
            detail="Channel URL must be an absolute https:// URL.",
        )


# --------------------------------------------------------------------------- #
# Read — full config in one call (FE convenience)
# --------------------------------------------------------------------------- #
@router.get("/config")
def get_config(principal: PrincipalDep, store: StoreDep = ...):
    """Channels, rules and mute windows. ``can_edit`` mirrors the server gate."""
    return {
        "channels": store.list_notification_channels(),
        "rules": store.list_notification_rules(),
        "mutes": store.list_notification_mutes(),
        "can_edit": principal.has_role("admin"),
    }


# --------------------------------------------------------------------------- #
# Channels
# --------------------------------------------------------------------------- #
class ChannelIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    type: str
    url: str = Field(min_length=1, max_length=2000)
    enabled: bool = True


class ChannelPatch(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    type: str | None = None
    url: str | None = Field(default=None, max_length=2000)
    enabled: bool | None = None
    digest_enabled: bool | None = None


@router.post("/channels", status_code=status.HTTP_201_CREATED)
def create_channel(body: ChannelIn, principal: Principal = require_admin, store: StoreDep = ...):
    if body.type not in _CHANNEL_TYPES:
        raise HTTPException(422, detail=f"type must be one of {sorted(_CHANNEL_TYPES)}")
    _validate_url(body.url)
    return store.create_notification_channel(
        name=body.name, type=body.type, url=body.url, enabled=body.enabled,
        actor=principal.sub,
    )


@router.patch("/channels/{channel_id}")
def patch_channel(channel_id: int, body: ChannelPatch, principal: Principal = require_admin, store: StoreDep = ...):
    if body.type is not None and body.type not in _CHANNEL_TYPES:
        raise HTTPException(422, detail=f"type must be one of {sorted(_CHANNEL_TYPES)}")
    if body.url is not None:
        _validate_url(body.url)
    updated = store.update_notification_channel(
        channel_id, name=body.name, type=body.type, url=body.url, enabled=body.enabled,
        digest_enabled=body.digest_enabled,
    )
    if not updated:
        raise HTTPException(404, detail=f"Channel {channel_id} not found")
    return updated


@router.delete("/channels/{channel_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_channel(channel_id: int, principal: Principal = require_admin, store: StoreDep = ...):
    if not store.delete_notification_channel(channel_id):
        raise HTTPException(404, detail=f"Channel {channel_id} not found")


# --------------------------------------------------------------------------- #
# Routing rules
# --------------------------------------------------------------------------- #
class RuleIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    channel_id: int
    match_severity: str = ""
    match_space: str = ""
    match_product: str = ""
    match_owned_by: str = ""
    match_owner: str = ""
    match_kind: str = ""
    enabled: bool = True


@router.post("/rules", status_code=status.HTTP_201_CREATED)
def create_rule(body: RuleIn, principal: Principal = require_admin, store: StoreDep = ...):
    if body.match_severity not in _SEVERITIES:
        raise HTTPException(422, detail=f"match_severity must be one of {sorted(_SEVERITIES)}")
    if body.match_owned_by not in _OWNED_BY:
        raise HTTPException(422, detail=f"match_owned_by must be one of {sorted(_OWNED_BY)}")
    if body.match_kind not in _KINDS:
        raise HTTPException(422, detail=f"match_kind must be one of {sorted(_KINDS)}")
    rule = store.create_notification_rule(
        name=body.name, channel_id=body.channel_id,
        match_severity=body.match_severity, match_space=body.match_space,
        match_product=body.match_product, match_owned_by=body.match_owned_by,
        match_owner=body.match_owner, match_kind=body.match_kind,
        enabled=body.enabled, actor=principal.sub,
    )
    if rule is None:
        raise HTTPException(422, detail=f"Channel {body.channel_id} does not exist")
    return rule


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rule(rule_id: int, principal: Principal = require_admin, store: StoreDep = ...):
    if not store.delete_notification_rule(rule_id):
        raise HTTPException(404, detail=f"Rule {rule_id} not found")


# --------------------------------------------------------------------------- #
# Mute / maintenance windows
# --------------------------------------------------------------------------- #
class MuteIn(BaseModel):
    reason: str = Field(default="", max_length=200)
    match_space: str = ""
    match_product: str = ""
    starts_at: str
    ends_at: str


def _parse_iso(value: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


@router.post("/mutes", status_code=status.HTTP_201_CREATED)
def create_mute(body: MuteIn, principal: Principal = require_admin, store: StoreDep = ...):
    start, end = _parse_iso(body.starts_at), _parse_iso(body.ends_at)
    if not start or not end:
        raise HTTPException(422, detail="starts_at and ends_at must be ISO-8601 timestamps")
    if end <= start:
        raise HTTPException(422, detail="ends_at must be after starts_at")
    return store.create_notification_mute(
        reason=body.reason, match_space=body.match_space, match_product=body.match_product,
        starts_at=start.isoformat(), ends_at=end.isoformat(), actor=principal.sub,
    )


@router.delete("/mutes/{mute_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_mute(mute_id: int, principal: Principal = require_admin, store: StoreDep = ...):
    if not store.delete_notification_mute(mute_id):
        raise HTTPException(404, detail=f"Mute {mute_id} not found")


# --------------------------------------------------------------------------- #
# Qualitäts-Digest (V4) — Vorschau + manueller Versand
# --------------------------------------------------------------------------- #
require_steward = require_roles("steward", "owner", "admin")


@router.get("/digest/preview")
def digest_preview(
    principal: PrincipalDep,
    hours: int | None = None,
    store: StoreDep = ...,
):
    """Digest-Kennzahlen der Periode (nur Aggregate, G8-frei) + Versandstatus."""
    from ..digest import build_digest, digest_targets
    from ..settings import get_settings

    settings = get_settings()
    period = hours or settings.digest_interval_hours
    if not 1 <= period <= 168:
        raise HTTPException(422, detail="hours must be within 1..168")
    return {
        **build_digest(store, hours=period),
        "enabled": settings.digest_enabled,
        "interval_hours": settings.digest_interval_hours,
        "subscribed_channels": len(digest_targets(store)),
        "last_sent_at": store.get_meta("digest_last_sent"),
    }


@router.post("/digest/send")
def digest_send(
    principal: Principal = require_steward,
    store: StoreDep = ...,
):
    """Manueller Versand an alle abonnierten Kanäle (Opt-in via digest_enabled)."""
    from ..digest import send_digest
    from ..settings import get_settings

    settings = get_settings()
    result = send_digest(store, settings, hours=settings.digest_interval_hours)
    if result["targets"] == 0:
        raise HTTPException(
            status_code=409,
            detail="No channel has digest_enabled — subscribe a channel first.",
        )
    store.set_meta("digest_last_sent", datetime.now(timezone.utc).isoformat())
    return {"sent": True, "targets": result["targets"], "digest": result["digest"]}
