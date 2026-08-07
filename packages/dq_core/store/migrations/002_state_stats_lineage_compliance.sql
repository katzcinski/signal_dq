-- Migration 002: gating states, contract linkage, compliance (v2)
-- Idempotent: SQLite ignores "ADD COLUMN IF NOT EXISTS" via try/ignore pattern

-- dq_check_results: gating state (G6 — never silently omit)
ALTER TABLE dq_check_results ADD COLUMN state TEXT NOT NULL DEFAULT 'executed';
-- allowed: executed | skipped_stale | skipped_dependency | downgraded | error

-- dq_runs: link run to contract version/hash/actor (F3/S7)
ALTER TABLE dq_runs ADD COLUMN contract_version TEXT DEFAULT '';
ALTER TABLE dq_runs ADD COLUMN contract_hash    TEXT DEFAULT '';
ALTER TABLE dq_runs ADD COLUMN actor            TEXT DEFAULT '';
ALTER TABLE dq_runs ADD COLUMN run_state        TEXT NOT NULL DEFAULT 'finished';
-- allowed: running | finished | error

-- Stats tuple per check (E6 — only scalars leave HANA)
CREATE TABLE IF NOT EXISTS dq_check_stats (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id     TEXT NOT NULL,
  check_name TEXT NOT NULL,
  n          INTEGER,
  min_v      REAL,
  max_v      REAL,
  p01        REAL,
  p99        REAL,
  mean_v     REAL,
  stddev_v   REAL
);

-- Observability baselines (WS5-1)
CREATE TABLE IF NOT EXISTS dq_baselines (
  dataset          TEXT NOT NULL,
  metric           TEXT NOT NULL,
  n                INTEGER,
  mean_v           REAL,
  stddev_v         REAL,
  p01              REAL,
  p99              REAL,
  mad              REAL,
  updated_at       TEXT,
  warmup_remaining INTEGER DEFAULT 0,
  PRIMARY KEY (dataset, metric)
);

-- Proposals from Anomaly-Miner (WS5-2)
CREATE TABLE IF NOT EXISTS dq_proposals (
  id               TEXT PRIMARY KEY,
  product          TEXT NOT NULL,
  guarantee_patch  TEXT NOT NULL,  -- JSON
  evidence         TEXT,           -- JSON array of run_ids + stats
  status           TEXT NOT NULL DEFAULT 'open',
  -- allowed: open | accepted | rejected | snoozed
  created_at       TEXT,
  snoozed_until    TEXT
);

-- Compliance state separate from Git lifecycle (A1)
CREATE TABLE IF NOT EXISTS dq_compliance (
  product          TEXT PRIMARY KEY,
  contract_version TEXT,
  compliance       TEXT NOT NULL DEFAULT 'unknown',
  -- allowed: compliant | breached | unknown
  since            TEXT,
  last_run_id      TEXT
);

-- Contract index for fast list queries (A3 — Git is not a query DB)
CREATE TABLE IF NOT EXISTS contract_index (
  product      TEXT PRIMARY KEY,
  lifecycle    TEXT,    -- draft | active | deprecated
  owned_by     TEXT,
  version      TEXT,
  head_hash    TEXT,
  updated_at   TEXT
);

-- Run progress for SSE polling fallback (F2)
CREATE TABLE IF NOT EXISTS dq_run_progress (
  id       INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id   TEXT NOT NULL,
  ts       TEXT NOT NULL,
  line     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_run_progress ON dq_run_progress(run_id, id);
