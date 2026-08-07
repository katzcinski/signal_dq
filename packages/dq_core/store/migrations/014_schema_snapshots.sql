-- Konzept Shift-Left §A.4 — Schema-Drift-Detection der Quelle gegen das
-- Contract-Versprechen. Snapshots tragen die Historie ("seit wann"), Drift-
-- Zeilen die je-Extrakt erkannten Abweichungen. Idempotent neu ableitbar.

-- Snapshot je Objekt × Extrakt.
CREATE TABLE IF NOT EXISTS dq_schema_snapshots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  object_name TEXT NOT NULL,
  captured_at TEXT NOT NULL,
  columns_json TEXT NOT NULL,           -- [{name,type,key,nullable}] aus inventory.json
  inventory_hash TEXT NOT NULL          -- Schnell-Vergleich gleich/ungleich
);

CREATE INDEX IF NOT EXISTS ix_schema_snap ON dq_schema_snapshots(object_name, captured_at);

-- Drift-Befund je Objekt × Kategorie × Spalte (gegen die aktive Garantie bewertet).
CREATE TABLE IF NOT EXISTS dq_schema_drift (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  object_name TEXT NOT NULL,
  detected_at TEXT NOT NULL,
  category TEXT NOT NULL,               -- column_added | column_removed | type_changed | nullable_relaxed | key_changed
  column_name TEXT DEFAULT '',
  before_value TEXT DEFAULT '',
  after_value TEXT DEFAULT '',
  breaking INTEGER NOT NULL DEFAULT 0,
  contract_version TEXT DEFAULT '',
  incident_id INTEGER                   -- gesetzt, wenn ein Incident eröffnet wurde
);

CREATE INDEX IF NOT EXISTS ix_schema_drift_obj ON dq_schema_drift(object_name, detected_at);
