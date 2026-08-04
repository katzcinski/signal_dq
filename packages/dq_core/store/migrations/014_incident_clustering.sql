-- Observability-Intelligence v1: incident clustering for notification dedupe.
CREATE TABLE IF NOT EXISTS dq_incident_clusters (
  cluster_id TEXT PRIMARY KEY,
  correlation_key TEXT NOT NULL,
  representative_incident_id INTEGER,
  opened_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  member_count INTEGER NOT NULL DEFAULT 1
);

ALTER TABLE dq_incidents ADD COLUMN cluster_id TEXT;
ALTER TABLE dq_incidents ADD COLUMN correlation_key TEXT;

CREATE INDEX IF NOT EXISTS ix_incidents_cluster
  ON dq_incidents(cluster_id);

CREATE INDEX IF NOT EXISTS ix_incidents_correlation
  ON dq_incidents(correlation_key);
