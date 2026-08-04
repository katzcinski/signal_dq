-- Compliance-Übergänge als Event-Log (WS2-5: "Übergänge als Events")
CREATE TABLE IF NOT EXISTS dq_compliance_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  product TEXT NOT NULL,
  from_state TEXT NOT NULL,
  to_state TEXT NOT NULL,
  contract_version TEXT DEFAULT '',
  run_id TEXT DEFAULT '',
  at TEXT NOT NULL
);

-- F2: Doppellauf-Schutz auf Store-Ebene — höchstens ein laufender Run je Dataset
CREATE UNIQUE INDEX IF NOT EXISTS idx_dq_runs_one_running
  ON dq_runs(dataset) WHERE run_state = 'running';
