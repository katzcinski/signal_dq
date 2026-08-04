-- Qualitäts-Digest (V4): periodischer Rollup über die bestehenden
-- Notification-Kanäle. Kanäle abonnieren den Digest explizit (Opt-in,
-- kein implizites Fan-out). dq_meta trägt den Claim-Anker für den
-- Multi-Worker-sicheren Versand (analog claim_due_schedules).
ALTER TABLE dq_notification_channels ADD COLUMN digest_enabled INTEGER NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS dq_meta (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL DEFAULT ''
);
