-- Migration 001: initial schema (v1 baseline)
CREATE TABLE IF NOT EXISTS dq_runs (
  run_id         TEXT PRIMARY KEY,
  dataset        TEXT NOT NULL,
  schema_name    TEXT NOT NULL DEFAULT '',
  started_at     TEXT NOT NULL,
  finished_at    TEXT NOT NULL DEFAULT '',
  overall_status TEXT NOT NULL DEFAULT 'pass',
  total_checks   INTEGER NOT NULL DEFAULT 0,
  passed_checks  INTEGER NOT NULL DEFAULT 0,
  failed_checks  INTEGER NOT NULL DEFAULT 0,
  warning_checks INTEGER NOT NULL DEFAULT 0,
  triggered_by   TEXT NOT NULL DEFAULT 'manual'
);

CREATE TABLE IF NOT EXISTS dq_check_results (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id        TEXT NOT NULL REFERENCES dq_runs(run_id),
  check_name    TEXT NOT NULL,
  sql_text      TEXT NOT NULL DEFAULT '',
  expect_expr   TEXT NOT NULL DEFAULT '',
  severity      TEXT NOT NULL DEFAULT 'fail',
  passed        INTEGER NOT NULL DEFAULT 0,
  actual_value  TEXT,
  error_message TEXT,
  duration_ms   INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS dq_diagnostics (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  result_id  INTEGER REFERENCES dq_check_results(id),
  run_id     TEXT NOT NULL,
  check_name TEXT NOT NULL,
  row_data   TEXT NOT NULL  -- JSON-encoded row dict
);

CREATE INDEX IF NOT EXISTS idx_runs_dataset ON dq_runs(dataset, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_results_run  ON dq_check_results(run_id);
