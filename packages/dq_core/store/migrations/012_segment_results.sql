-- Observability-Intelligence v1: allowlisted aggregate segment details.
CREATE TABLE IF NOT EXISTS dq_segment_results (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL,
  check_name TEXT NOT NULL,
  segment_column TEXT NOT NULL,
  segment_value TEXT NOT NULL,
  actual_value REAL,
  threshold_value REAL,
  rank INTEGER DEFAULT 0,
  created_at TEXT DEFAULT '',
  FOREIGN KEY (run_id) REFERENCES dq_runs(run_id)
);

CREATE INDEX IF NOT EXISTS ix_segment_results_run_check
  ON dq_segment_results(run_id, check_name);
