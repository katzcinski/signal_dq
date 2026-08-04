-- UX-N2: Alerting & Notification-Routing — server-authoritative channels,
-- routing rules and mute/maintenance windows. These supersede the static
-- notifications.yml, which remains only a fallback default for existing deploys.

-- Delivery channels (Slack / Microsoft Teams / generic webhook).
CREATE TABLE IF NOT EXISTS dq_notification_channels (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  type TEXT NOT NULL,                 -- slack | teams | webhook
  url TEXT NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  created_by TEXT NOT NULL DEFAULT ''
);

-- Routing rules: a breach/incident matching the (severity, space, product,
-- owned_by, owner) facets routes to a channel. Empty facet = wildcard.
CREATE TABLE IF NOT EXISTS dq_notification_rules (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  channel_id INTEGER NOT NULL,
  match_severity TEXT NOT NULL DEFAULT '',   -- critical | fail | warn | ''
  match_space TEXT NOT NULL DEFAULT '',
  match_product TEXT NOT NULL DEFAULT '',
  match_owned_by TEXT NOT NULL DEFAULT '',    -- platform | product | ''
  match_owner TEXT NOT NULL DEFAULT '',
  enabled INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  created_by TEXT NOT NULL DEFAULT '',
  FOREIGN KEY (channel_id) REFERENCES dq_notification_channels(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_dq_notif_rules_channel ON dq_notification_rules(channel_id);

-- Mute / maintenance windows: while active and in scope, all notifications are
-- suppressed (evaluated server-side at notify time). Empty scope = everything.
CREATE TABLE IF NOT EXISTS dq_notification_mutes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  reason TEXT NOT NULL DEFAULT '',
  match_space TEXT NOT NULL DEFAULT '',
  match_product TEXT NOT NULL DEFAULT '',
  starts_at TEXT NOT NULL,            -- ISO-8601 UTC
  ends_at TEXT NOT NULL,              -- ISO-8601 UTC
  created_at TEXT NOT NULL,
  created_by TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_dq_notif_mutes_window ON dq_notification_mutes(starts_at, ends_at);
