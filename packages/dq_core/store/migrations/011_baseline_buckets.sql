-- Observability-Intelligence v1: seasonal baseline buckets.
CREATE TABLE IF NOT EXISTS dq_baseline_buckets (
  dataset TEXT NOT NULL,
  metric TEXT NOT NULL,
  strategy TEXT NOT NULL DEFAULT 'seasonal',
  bucket_key TEXT NOT NULL,
  n INTEGER,
  mean_v REAL,
  stddev_v REAL,
  median_v REAL,
  p01 REAL,
  p99 REAL,
  mad REAL,
  updated_at TEXT,
  warmup_remaining INTEGER DEFAULT 0,
  PRIMARY KEY (dataset, metric, strategy, bucket_key)
);

CREATE INDEX IF NOT EXISTS ix_baseline_buckets_lookup
  ON dq_baseline_buckets(dataset, metric, strategy, bucket_key);
