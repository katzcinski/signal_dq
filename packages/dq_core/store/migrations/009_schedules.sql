-- Scheduling (Option E) -- durable schedule definitions plus a due-run claim
-- queue. A schedule says "run object X against environment Y every N seconds".
-- The API never runs on a timer itself. A poller (services/api/scheduler.py)
-- claims due schedules and launches runs via the shared start_object_run path.
-- Multi-worker correctness -- claiming advances next_due_at optimistically, and
-- the existing partial unique index idx_dq_runs_one_running (003) remains the
-- hard guarantee against duplicate concurrent runs per dataset.
--
-- mode=internal -- Signal's poller drives this object on its cadence.
-- mode=external -- a Task Chain or cron to CLI drives it, the poller never
--   claims it (the row documents intent and stamps last_run for the UI).
-- A per-object toggle -- no row (manual), mode=internal, or mode=external.
CREATE TABLE IF NOT EXISTS dq_schedules (
  schedule_id     TEXT PRIMARY KEY,
  object_id       TEXT NOT NULL,
  mode            TEXT NOT NULL DEFAULT 'internal',
  environment     TEXT NOT NULL DEFAULT '',
  execution_mode  TEXT NOT NULL DEFAULT 'auto',
  interval_seconds INTEGER NOT NULL DEFAULT 0,
  enabled         INTEGER NOT NULL DEFAULT 1,
  next_due_at     TEXT NOT NULL,
  last_run_at     TEXT,
  last_run_id     TEXT,
  last_status     TEXT,
  created_by      TEXT NOT NULL DEFAULT '',
  created_at      TEXT NOT NULL,
  updated_at      TEXT
);

-- The poller scans enabled internal schedules ordered by next_due_at.
CREATE INDEX IF NOT EXISTS idx_dq_schedules_due
  ON dq_schedules(mode, enabled, next_due_at);
