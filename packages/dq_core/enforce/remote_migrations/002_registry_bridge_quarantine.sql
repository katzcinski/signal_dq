-- Remote-Migration 002 — Registry (Reconciler, Slice ④), Episoden-Spiegel +
-- Quarantäne-Infrastruktur (Slice ⑤) und Run-Requests (SQL-Bridge, Slice ⑥).
-- Reihe analog 001: NIE editieren, nur anhängen. '{signal_schema}' wird zur
-- Laufzeit gebunden (G2) — nur Signals Space-User schreibt diese Tabellen.

-- Desired-State-Registry der von Signal verwalteten Objekte (Konzept §7).
CREATE TABLE "{signal_schema}"."DQ_OBJECTS" (
  "NAME"           NVARCHAR(128) PRIMARY KEY,
  "KIND"           NVARCHAR(16)  NOT NULL,   -- table | view | procedure
  "OBJECT_ID"      NVARCHAR(256),            -- Prüfobjekt (leer für globale Objekte)
  "MANIFEST_HASH"  NVARCHAR(64)  NOT NULL,
  "GENERATION"     INTEGER       NOT NULL,
  "STATUS"         NVARCHAR(16)  NOT NULL,   -- active | invalidated | dropped
  "CREATED_AT"     TIMESTAMP     NOT NULL,
  "UPDATED_AT"     TIMESTAMP     NOT NULL,
  "INVALIDATED_AT" TIMESTAMP                 -- Start der Grace-Period (invalidate-then-drop)
);

-- Episoden-Spiegel: Release-Views brauchen den Episoden-Status SQL-lesbar in
-- HANA. Quelle der Wahrheit bleibt der Result-Store — Signal spiegelt bei
-- jedem Lifecycle-Übergang (Upsert).
CREATE TABLE "{signal_schema}"."DQ_EPISODES" (
  "EPISODE_ID"  INTEGER       PRIMARY KEY,
  "OBJECT_ID"   NVARCHAR(256) NOT NULL,
  "STATUS"      NVARCHAR(16)  NOT NULL,      -- open | reconciled | released | resolved | superseded
  "RUN_ID"      NVARCHAR(64),
  "GENERATION"  INTEGER,
  "ROW_COUNT"   INTEGER,
  "OPENED_AT"   TIMESTAMP,
  "RELEASED_AT" TIMESTAMP,
  "RESOLVED_AT" TIMESTAMP,
  "UPDATED_AT"  TIMESTAMP     NOT NULL
);

-- Lauf-Anforderungen der SQL-Trigger-Bridge (Konzept §6.3). INSERT nur über
-- die DEFINER-Prozedur P_DQ_REQUEST_RUN / P_DQ_GATE, nie per Direkt-Grant.
CREATE TABLE "{signal_schema}"."DQ_RUN_REQUESTS" (
  "REQUEST_ID"   NVARCHAR(64)  PRIMARY KEY,
  "OBJECT_ID"    NVARCHAR(256) NOT NULL,
  "REQUESTED_BY" NVARCHAR(128) NOT NULL,
  "REQUESTED_AT" TIMESTAMP     NOT NULL,
  "STATUS"       NVARCHAR(16)  NOT NULL,     -- requested | claimed | done | error | expired
  "CLAIMED_BY"   NVARCHAR(64),
  "RUN_ID"       NVARCHAR(64),
  "FINISHED_AT"  TIMESTAMP
);
