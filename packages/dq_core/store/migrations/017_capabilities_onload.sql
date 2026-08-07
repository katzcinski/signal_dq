-- Capability-Probe (Rest-O5/O6): verifizierte Tenant-Fähigkeiten persistieren,
-- damit Enforcement-Features sich an geprüften Fakten gaten statt an Doku.
-- status: ok | unavailable | error | manual (manuell zu verproben, z. B.
-- View-Import im Data Builder) — G6-Disziplin: offene Checks sind sichtbar.
CREATE TABLE IF NOT EXISTS dq_capabilities (
  key TEXT PRIMARY KEY,
  status TEXT NOT NULL,
  detail TEXT DEFAULT '',
  environment TEXT DEFAULT '',
  checked_at TEXT NOT NULL
);

-- on_load-Schedule-Modus (AP-5): Dedupe-Anker — die zuletzt gesehene
-- Datasphere-Run-ID je Schedule, damit derselbe Load nie zwei Läufe auslöst.
ALTER TABLE dq_schedules ADD COLUMN last_external_run_id TEXT NOT NULL DEFAULT '';
