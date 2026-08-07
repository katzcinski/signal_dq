-- Observability-Intelligence v1: persisted RCA snapshots and contract kind index.
ALTER TABLE contract_index ADD COLUMN kind TEXT NOT NULL DEFAULT 'internal_gate';

CREATE TABLE IF NOT EXISTS dq_incident_rca (
  incident_id INTEGER PRIMARY KEY,
  probable_cause_object TEXT DEFAULT '',
  cause_confidence REAL,
  cause_candidates_json TEXT DEFAULT '[]',
  affected_contracts_json TEXT DEFAULT '[]',
  affected_internal_gates_json TEXT DEFAULT '[]',
  recurrence_count INTEGER DEFAULT 0,
  recurrence_last_at TEXT DEFAULT '',
  computed_at TEXT NOT NULL,
  FOREIGN KEY (incident_id) REFERENCES dq_incidents(id)
);
