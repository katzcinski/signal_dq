-- Enforcement-Achse (Konzept_Enforcement_Modi / Konzept_Datasphere_Integration):
-- Durchsetzungsmodus je Check-Ergebnis, Gate-Verdict je Lauf und
-- Quarantäne-Episoden mit Lifecycle (open → reconciled → released → resolved,
-- + superseded). G6: neue Zustände sind explizit, nie stilles Auslassen.
ALTER TABLE dq_check_results ADD COLUMN enforcement_mode TEXT NOT NULL DEFAULT 'monitor';
ALTER TABLE dq_runs ADD COLUMN gate_verdict TEXT NOT NULL DEFAULT 'proceed';

CREATE TABLE IF NOT EXISTS dq_quarantine (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  product TEXT NOT NULL,
  run_id TEXT DEFAULT '',
  status TEXT NOT NULL DEFAULT 'open',   -- open | reconciled | released | resolved | superseded
  failed_checks TEXT DEFAULT '[]',       -- JSON-Array der Check-Namen (Prädikat-Träger)
  contract_version TEXT DEFAULT '',
  manifest_hash TEXT DEFAULT '',         -- Idempotenz-Anker (Prädikat+Version+Objekt)
  generation INTEGER NOT NULL DEFAULT 1,
  row_count INTEGER,                     -- quarantänisierte Zeilen (NULL = unbekannt/B2)
  opened_at TEXT NOT NULL,
  released_at TEXT,
  released_by TEXT DEFAULT '',
  resolved_at TEXT,
  resolve_reason TEXT DEFAULT ''         -- reprocessed | expired | superseded | manual
);

CREATE INDEX IF NOT EXISTS idx_dq_quarantine_product ON dq_quarantine(product);
CREATE INDEX IF NOT EXISTS idx_dq_quarantine_status ON dq_quarantine(status);

CREATE TABLE IF NOT EXISTS dq_quarantine_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  quarantine_id INTEGER NOT NULL,
  at TEXT NOT NULL,
  actor TEXT DEFAULT '',
  action TEXT NOT NULL,                  -- opened | reconciled | released | resolved | superseded | note
  note TEXT DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_dq_quarantine_events_q ON dq_quarantine_events(quarantine_id);
