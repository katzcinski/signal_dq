-- Healing-Workbench (Konzept_Manuelles_Healing H1/H3). Der Result-Store ist
-- die Quelle der Wahrheit, HANA die Projektion — analog zu Episoden.

-- H1: Zeilen-Korrekturen in der Quarantäne-Parkbucht. Ein Eintrag je
-- (Episode, Zeilenschlüssel, Spalte); applied=0 heißt im Store auditiert,
-- aber (noch) nicht in HANA materialisiert (Materialisierung ist opt-in).
CREATE TABLE IF NOT EXISTS dq_healing_corrections (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  object_id     TEXT NOT NULL,
  episode_id    INTEGER NOT NULL,
  row_key       TEXT NOT NULL,             -- JSON: {spalte: wert}
  column_name   TEXT NOT NULL,
  before_value  TEXT,
  after_value   TEXT,
  reason        TEXT NOT NULL DEFAULT '',
  actor         TEXT NOT NULL DEFAULT '',
  created_at    TEXT NOT NULL,
  applied       INTEGER NOT NULL DEFAULT 0,
  apply_error   TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_dq_heal_corr_episode ON dq_healing_corrections(episode_id);
CREATE INDEX IF NOT EXISTS idx_dq_heal_corr_object ON dq_healing_corrections(object_id);

-- H3: Patch-Overlay je Objekt. Überlebt Reloads (im Gegensatz zu H1) und
-- wirkt über V_DQ_HEALED_<OBJ>; valid_until = NULL heißt unbefristet.
CREATE TABLE IF NOT EXISTS dq_healing_patches (
  id           TEXT PRIMARY KEY,           -- UUID, = _DQ_PATCH_ID in HANA
  object_id    TEXT NOT NULL,
  key_json     TEXT NOT NULL,              -- JSON: {schlüsselspalte: wert}
  patch_json   TEXT NOT NULL,              -- JSON: {spalte: neuer wert}
  reason       TEXT NOT NULL DEFAULT '',
  actor        TEXT NOT NULL DEFAULT '',
  created_at   TEXT NOT NULL,
  valid_until  TEXT,
  status       TEXT NOT NULL DEFAULT 'active',  -- active | revoked | expired
  revoked_at   TEXT,
  revoked_by   TEXT NOT NULL DEFAULT '',
  applied      INTEGER NOT NULL DEFAULT 0,
  apply_error  TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_dq_heal_patch_object ON dq_healing_patches(object_id, status);
