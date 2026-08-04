-- Generic operation and progress channel.
CREATE TABLE IF NOT EXISTS dq_progress (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  stream_id TEXT NOT NULL,
  ts        TEXT NOT NULL,
  line      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_progress_stream ON dq_progress(stream_id, id);

-- Migrate existing run progress into the generic stream once. The legacy table
-- remains as migration input only. New code writes to dq_progress.
INSERT OR IGNORE INTO dq_progress(id, stream_id, ts, line)
SELECT id, run_id, ts, line FROM dq_run_progress;

CREATE TABLE IF NOT EXISTS dq_operations (
  op_id       TEXT PRIMARY KEY,
  kind        TEXT NOT NULL,
  state       TEXT NOT NULL DEFAULT 'running',
  created_by  TEXT NOT NULL DEFAULT '',
  started_at  TEXT NOT NULL,
  finished_at TEXT,
  result_json TEXT,
  error       TEXT
);
