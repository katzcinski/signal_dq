-- R4-1: Incident-Lifecycle — ein Breach erzeugt ein persistentes Incident-Objekt
-- mit Status, Owner und Aktions-Timeline (statt nur einer roten Zelle).
CREATE TABLE IF NOT EXISTS dq_incidents (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  product TEXT NOT NULL,
  run_id TEXT DEFAULT '',
  severity TEXT DEFAULT 'fail',
  status TEXT NOT NULL DEFAULT 'open',   -- open | acknowledged | investigating | resolved
  owner TEXT DEFAULT '',
  title TEXT DEFAULT '',
  failed_checks TEXT DEFAULT '[]',       -- JSON-Array der Check-Namen
  opened_at TEXT NOT NULL,
  resolved_at TEXT,
  contract_version TEXT DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_dq_incidents_status ON dq_incidents(status);
CREATE INDEX IF NOT EXISTS idx_dq_incidents_product ON dq_incidents(product);

CREATE TABLE IF NOT EXISTS dq_incident_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  incident_id INTEGER NOT NULL,
  at TEXT NOT NULL,
  actor TEXT DEFAULT '',
  action TEXT NOT NULL,                  -- opened | status_changed | assigned | note | auto_resolved
  note TEXT DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_dq_incident_events_incident ON dq_incident_events(incident_id);

-- R3-2: Familien-Rollup braucht den Check-Typ am Ergebnis (Garantie↔Check-
-- Rückverfolgbarkeit bis ins Dashboard, HANDOVER WS3-1).
ALTER TABLE dq_check_results ADD COLUMN check_type TEXT NOT NULL DEFAULT '';
