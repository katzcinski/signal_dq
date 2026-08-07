-- Konzept Data-Diff §B.3 — Profil-Snapshots, damit der Distribution-/Key-Diff
-- zwei Zeitpunkte (Versions-/Deploy-Diff) oder zwei Environments vergleichen kann.
-- Nur Aggregat-Profile (kein Sample-Row, G8). Snapshots sind additiv/idempotent.

CREATE TABLE IF NOT EXISTS dq_profile_snapshots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  object_name TEXT NOT NULL,
  environment TEXT DEFAULT '',           -- '' = Default/Mock
  captured_at TEXT NOT NULL,
  stats_json TEXT NOT NULL               -- Aggregat-Profil (profile_table-Result, ohne sample_rows)
);

CREATE INDEX IF NOT EXISTS ix_profile_snap ON dq_profile_snapshots(object_name, environment, captured_at);
