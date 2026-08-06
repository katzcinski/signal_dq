# Konzept: Observability-Intelligence v1 (Tier-1-Features)

> **Handover-Hinweis (2026-06-29):** Die implementierungsreife Fassung nach
> Grill-Entscheidungen steht in
> [`HANDOVER_Observability_Intelligence_v1_Implementation.md`](HANDOVER_Observability_Intelligence_v1_Implementation.md).
> Bei Widerspruch gewinnt das Handover.

**Stand:** 2026-06-29 · **Status:** **Umgesetzt** (2026-07: Migrationen 010–015 — robuste/saisonale Baselines, Segment-Details, RCA-Snapshots, Incident-Clustering, Impact-Snapshot) · **Bezug:**
[`Marktanalyse_DQ_Observability_2026.md`](Marktanalyse_DQ_Observability_2026.md) (Tier 1),
[`Tooldokumentation.md`](Tooldokumentation.md) (implementierter Stand)

Technischer Entwurf für die vier Tier-1-Lücken aus der Marktanalyse:

1. **Adaptive, saisonalitätsbewusste Anomalie-Baselines**
2. **Segmentierung / dimensionale Anomalieerkennung**
3. **Automatisierte Root-Cause-Analyse & Blast-Radius**
4. **Alert-Clustering / Deduplizierung**

> **Leitplanke für alle vier:** Kein Gate fällt. Die Engine (`packages/dq_core/engine/`)
> bleibt `[ENGINE-FROZEN]` und frameworkfrei (G7). Contracts bleiben SQL-frei (G1), Schema
> laufzeit-gebunden (G2). Erweitert wird in `obs/`, `compiler.py`, `store/`, der API und dem
> Frontend — **nicht** in `check_engine.py`/`expectation.py`. Neue Store-Objekte ausschließlich
> über nummerierte Migrationen (nächste freie Nummer: **`010`**).

---

## 0 / Architektur-Prinzip: Anomalie als *aufgelöste* Expectation

Der zentrale Trick, der alle vier Features mit der eingefrorenen Engine verträglich macht:

**Die Engine lernt keine neue Grammatik.** Statt einen `ANOMALY`-Operator in
`expectation.py` einzuführen (bräuchte Baseline-Kontext im `evaluate()` → Engine-Änderung),
**materialisiert die `obs/`-Schicht die Baseline zur Laufzeit in eine konkrete numerische
`BETWEEN lo AND hi`-Expectation**, bevor der Check ausgeführt wird. Die Engine sieht eine
gewöhnliche, bereits unterstützte Expectation; die Intelligenz lebt vollständig in `obs/`.

```
Contract (SQL-frei)        Compiler              obs/ Resolver (Laufzeit)        Engine (frozen)
volume:                →   CheckDef mit      →   Baseline laden, Bounds      →   evaluate(actual,
  baseline: rolling        expect_expr =         berechnen, Token ersetzen:      "BETWEEN 980 AND 1120")
  sensitivity: medium      "BETWEEN <BL_LO>      "BETWEEN 980 AND 1120"
                            AND <BL_HI>"
```

`<BL_LO>`/`<BL_HI>` sind ungebundene Tokens (analog zu `{schema}`), die der Runner über die
`BaselineManager`-Bounds bindet. Der **persistierte** `expect_expr` in `dq_check_results`
trägt den aufgelösten numerischen Ausdruck **plus** die Baseline-Referenz (Nachvollziehbarkeit).
Determinismus des Compilers (Header-Hash) bleibt erhalten, weil der kompilierte Output das
*Token* enthält, nicht den volatilen Wert.

---

## 1 / Adaptive, saisonalitätsbewusste Anomalie-Baselines

### 1.1 Problem

`obs/baselines.py` führt heute nur Rolling-Mean/Stddev/MAD/Perzentile über eine flache
Werteliste (`BaselineManager.update_baseline`). `compute_bounds` liefert ein statisches
`mean ± 3σ`. Keine **Saisonalität** (Wochentag, Monatsende), kein **Trend**, keine
**robuste** Schätzung gegen Ausreißer im Trainingsfenster. Auf SAP-Finanz-/Sales-Workloads
(Monatsende-Peaks) erzeugt das False-Positives an ruhigen Tagen und verpasst langsamen Drift.

### 1.2 Design

**Erweiterung von `BaselineManager`, nicht Ersatz.** Neue Strategien hinter einem
gemeinsamen `BaselineStrategy`-Protocol:

| Strategie | Methode | Eignung |
|---|---|---|
| `rolling` (Bestand) | Mean/Stddev/MAD über N | Default, stationäre Metriken |
| `seasonal` | Saison-Buckets (`dow`, `dom`, `dow×hour`) → je Bucket robuste Bounds (Median/MAD) | wochentags-/monatsende-zyklische Volumina |
| `trend` | STL-light: gleitender Median als Level + MAD der Residuen | langsam wachsende Tabellen |

- **Robuste Schätzer als Default:** Bounds aus **Median ± k·MAD** (nicht Mean ± σ), MAD ist
  unempfindlich gegen einzelne Ausreißer im Trainingsfenster.
- **Saison-Bucketing:** Der Trainingswert trägt seinen Zeitstempel; `seasonal` partitioniert
  nach Kalendermerkmal (Default `dow` = Wochentag, `dom_flag` = Monatsende ja/nein) und hält
  je Bucket eine eigene Baseline-Zeile.
- **Sensitivität statt roher Sigma:** Contract deklariert `sensitivity: low|medium|high`
  (→ k ∈ {4, 3, 2}). Kein nacktes σ im YAML (semantisch, nicht numerisch — passt zu G1-Geist).
- **Warmup unverändert** (`WARMUP_N`, default 5 → je Bucket konfigurierbar erhöhen);
  während Warmup gilt die Garantie als `skipped_stale`-nah: der Check läuft, die
  Anomalie-Bewertung wird zur „pass (warm-up)" wie beim heutigen `DELTA` (siehe
  `expectation.py` Zeile 87 f.) — **keine** stille Auslassung (G6).

### 1.3 Datenmodell — Migration `010_seasonal_baselines.sql`

`dq_baselines` erhält eine **Bucket-Achse** (rückwärtskompatibel: `bucket=''` = globale Baseline):

```sql
ALTER TABLE dq_baselines ADD COLUMN strategy   TEXT NOT NULL DEFAULT 'rolling';
ALTER TABLE dq_baselines ADD COLUMN bucket_key TEXT NOT NULL DEFAULT '';   -- z.B. 'dow=2', 'dom=eom'
ALTER TABLE dq_baselines ADD COLUMN k_sigma    REAL;                        -- aufgelöste Sensitivität
-- Primärschlüssel logisch (dataset, metric, bucket_key); via INSERT OR REPLACE wie bisher.
CREATE INDEX IF NOT EXISTS ix_baselines_lookup ON dq_baselines(dataset, metric, bucket_key);
```

### 1.4 Contract-Schema (SQL-frei, additiv)

```yaml
volume:
  min_rows: 1000              # bleibt der harte Floor (Bestand)
  baseline: seasonal          # rolling (default) | seasonal | trend
  season: [dow, eom]          # optionale Saison-Achsen
  sensitivity: medium         # low | high → k
  severity: warn
freshness:
  column: ORDER_DATE
  max_age: PT26H              # harter Floor bleibt
  baseline: seasonal          # adaptiv ZUSÄTZLICH zum Floor
```

Validator (`contract/validator.py`): neue optionale Keys, Enum-geprüft. **Kein** numerischer
Schwellwert außer dem bestehenden harten Floor — die Anomalie-Grenze ist datengetrieben.

### 1.5 Compiler & Resolver

- **Compiler** (`compiler.py`): Bei `baseline != rolling`/`min_rows`-only emittiert er den
  Check mit `expect_expr = "BETWEEN <BL_LO> AND <BL_HI>"` und Metadaten
  (`baseline_strategy`, `season`, `sensitivity`) im `CheckDef`. Das Token zählt für `_UNBOUND_TOKEN`
  (Zeile 33 compiler.py) → der Determinismus-Hash ändert sich nur bei Contract-/Library-Änderung.
- **Resolver** (neu, `obs/resolver.py`): Vor `evaluate()` im Runner: Saison-Bucket aus
  `run.started_at` ableiten → `BaselineManager.get_baseline(dataset, metric, bucket)` →
  `compute_bounds(strategy, k)` → Tokens binden. Fehlt die Baseline (Warmup) → `expect_expr`
  wird zu einem immer-wahren Ausdruck mit `state=executed` und Hinweis (G6-konform).

### 1.6 Gate-Konformität

- G1: Contract trägt **Semantik** (`sensitivity`, `season`), kein SQL.
- G7: Engine unverändert — `evaluate()` sieht `BETWEEN`. `obs/`, `compiler.py` sind nicht Teil
  der frozen Engine.
- G6: Warmup/fehlende Baseline ist sichtbar (`executed` + Hinweis), nie als `pass` getarnt.

---

## 2 / Segmentierung / dimensionale Anomalieerkennung

### 2.1 Problem

Checks laufen auf Tabellen-/Spalten-Grain. Eine 2-%-Null-Rate, die in **einem** Segment
(`REGION='APAC'`) 100 % ist, besteht. Marktführer (Validio u. a.) bewerten je Segment.

### 2.2 Design

Eine optionale **Segment-Dimension** auf den dafür sinnvollen Familien
(`completeness`, `not_null`, `freshness`, `volume`). Der Compiler **fächert** eine Garantie
in **N Per-Segment-Checks** auf, indem er ein `GROUP BY <segment>` + `HAVING` erzeugt — alles
lesend, deterministisch, SQL nur im Compiler (G1).

### 2.3 Contract-Schema

```yaml
completeness:
  - column: NET_AMOUNT
    min_pct: 99.5
    segment_by: REGION        # optional: eine validierte Spalte (S2: Inventar-Existenz)
    max_segments: 50          # Sicherheitslimit gegen Kardinalitäts-Explosion
    severity: warn
```

### 2.4 Kompilierung

Statt eines aggregierten Checks erzeugt der Compiler ein Template
`completeness_pct_by_segment`:

```sql
-- Pseudo (im Compiler, {schema} laufzeit-gebunden, Identifier S2-validiert)
SELECT "REGION" AS segment,
       100.0 * COUNT("NET_AMOUNT") / NULLIF(COUNT(*),0) AS pct
FROM {schema}."DS_SALES_ORDERS"
GROUP BY "REGION"
HAVING 100.0 * COUNT("NET_AMOUNT") / NULLIF(COUNT(*),0) < 99.5
```

Der Check **passt**, wenn die Ergebnismenge leer ist (kein verletzendes Segment); jedes
zurückgegebene Segment ist eine Verletzung. `actual_value` wird die **Anzahl verletzender
Segmente**; die **Segment-Liste** geht in einen neuen Detail-Kanal (nicht `dq_diagnostics`,
da Aggregat, kein Rohzeilen-PII — aber Allowlist auf die Segment-Spalte beachten, G8).

### 2.5 Datenmodell — Migration `011_segment_results.sql`

```sql
CREATE TABLE IF NOT EXISTS dq_segment_results (
  id INTEGER PRIMARY KEY,
  run_id TEXT NOT NULL,
  check_name TEXT NOT NULL,
  segment_value TEXT NOT NULL,
  actual_value REAL,
  passed INTEGER NOT NULL,
  FOREIGN KEY (run_id) REFERENCES dq_runs(run_id)
);
CREATE INDEX IF NOT EXISTS ix_segres_run ON dq_segment_results(run_id, check_name);
```

### 2.6 Engine-Verträglichkeit

Die Engine führt den aggregierenden Check normal aus (`actual_value = Anzahl verletzender
Segmente`, `expect_expr = "= 0"`). Das **Auffächern in Segment-Zeilen** macht der Runner/Store
*nach* der Engine-Ausführung aus dem Resultset — Engine bleibt unangetastet (G7). G8:
Segment-Werte sind nur Dimensionsausprägungen; trotzdem an die Profil-/Diagnostics-Allowlist
(`PROFILE_SAMPLE_COLUMNS`-Analog) koppeln, damit keine sensible Spalte ungewollt als Segment leakt.

### 2.7 API & UI

- `GET /api/runs/{id}/results` erweitert um `segment_breakdown` je Check (Top-N verletzende
  Segmente).
- Objekt-Detail (`/objects/:id`): unter dem Check ein aufklappbares Segment-Panel
  (Heatmap „Segment × pass/fail"). Strings nach `i18n/de.ts`.

---

## 3 / Automatisierte Root-Cause-Analyse & Blast-Radius

### 3.1 Problem

Rohmaterial liegt vor (Lineage-Graph + Coverage + Incidents in **einem** Store), ist aber
nicht in die Triage verdrahtet. Bei einem Breach fehlt: „welches Upstream-Objekt ist
gleichzeitig/zuvor gekippt" und „welche Consumer sind betroffen".

### 3.2 Design — reine Korrelation, keine neue Erfassung

Ein **`obs/rca.py`**-Analyzer, der bei Incident-Öffnung (Hook in der bestehenden
Incident-Lifecycle-Logik) drei Abfragen gegen bereits persistierte Daten fährt:

1. **Upstream-Ursache:** Lineage-`upstream(object)` (aus `lineage.json`/`adjacency`) →
   für jedes Parent-Objekt: gab es im **selben Zeitfenster** einen fehlgeschlagenen Lauf oder
   eine Schema-/Volume-Anomalie (`dq_check_results.passed=0`)? → Ranking nach Lineage-Distanz
   + Zeitnähe.
2. **Blast-Radius:** Lineage-`downstream(object)` → Schnittmenge mit `contract_index`
   (welche **Consumer-Contracts** hängen daran) → Liste betroffener Produkte + deren `kind`.
3. **Recurrence:** `dq_incidents` desselben Objekts/Familie in den letzten 90 d → „N-mal zuvor,
   zuletzt am …".

### 3.3 Datenmodell — Migration `012_incident_rca.sql`

```sql
CREATE TABLE IF NOT EXISTS dq_incident_rca (
  incident_id TEXT NOT NULL,
  probable_cause_object TEXT,     -- Upstream-Verdächtiger (höchster Rang)
  cause_confidence REAL,          -- 0..1 aus Distanz + Zeitnähe
  blast_radius_json TEXT,         -- [{product, kind, distance}]
  recurrence_count INTEGER,
  computed_at TEXT NOT NULL,
  PRIMARY KEY (incident_id)
);
```

RCA ist ein **abgeleitetes, neu berechenbares Artefakt** (kein Single Source of Truth) —
idempotent neu berechenbar aus Store + Lineage.

### 3.4 API & UI

- `GET /api/incidents/{id}/rca` → `{probable_cause, blast_radius[], recurrence}`.
- Incident-Timeline (`/incidents`): Kopf-Panel „Wahrscheinliche Ursache" (Lineage-Pfad als
  Mini-Graph), „Betroffene Consumer" (klickbar zu deren Contracts), „Schon gesehen: N×".
- Coverage-/Lineage-Map: betroffene Knoten beim Öffnen eines Incidents hervorheben
  (Blast-Radius einfärben).

### 3.5 Gate-Konformität

Nur lesende Store-/Lineage-Abfragen; keine Engine-Berührung; keine HANA-Schreibvorgänge.
Keine Rohzeilen → G8 unberührt.

---

## 4 / Alert-Clustering / Deduplizierung

### 4.1 Problem

Eine Upstream-Schemaänderung fächert in viele unabhängige Failures auf — und damit in viele
Incidents/Notifications. Alert-Fatigue.

### 4.2 Design — Korrelations-Schlüssel + Fenster

Beim Anlegen eines Incidents (bestehende Lifecycle-Logik, Migration 004/007) wird ein
**Correlation-Key** berechnet und gleichartige offene Incidents im Zeitfenster zu einem
**Cluster** gruppiert, **bevor** Notifications feuern (Routing aus 005).

**Correlation-Heuristik (in Reihenfolge):**

1. **Lineage-Nähe:** teilen sich zwei Failures im selben Run einen Upstream aus §3 → ein Cluster.
2. **Gleiche Familie + gleicher Run** (z. B. Schema-Bruch trifft viele Spalten) → ein Cluster.
3. **Zeitfenster:** Default 15 min (konfigurierbar via Settings, analog `SCHEDULER_TICK_SECONDS`).

Ein **Cluster** bekommt einen Repräsentanten (höchste Severity / `*_contract` vor
`internal_gate`); Folge-Incidents hängen als `correlated_with` daran. **Notification feuert
einmal pro Cluster** mit Rollup („1 Ursache, 7 betroffene Checks, 3 Consumer").

### 4.3 Datenmodell — Migration `013_incident_clustering.sql`

```sql
ALTER TABLE dq_incidents ADD COLUMN cluster_id TEXT;          -- NULL = Einzel-Incident
ALTER TABLE dq_incidents ADD COLUMN correlation_key TEXT;     -- berechneter Schlüssel
CREATE INDEX IF NOT EXISTS ix_incident_cluster ON dq_incidents(cluster_id);
```

### 4.4 API & UI

- `GET /api/incidents` gruppiert optional (`?group=cluster`); Repräsentant + `member_count`.
- Notification-Payload trägt das Rollup; bestehende `match_kind`-Regeln (007) bleiben gültig
  und greifen auf den Repräsentanten.
- `/incidents`-Inbox: Cluster als aufklappbare Gruppe (ein Eintrag statt sieben).

### 4.5 Gate-Konformität

Reine Store-/Routing-Schicht. Kein neuer Compliance-Zustand (G6 unberührt — die einzelnen
Check-States bleiben unverändert sichtbar, nur die *Benachrichtigung* wird gebündelt).

---

## 5 / Umsetzungsreihenfolge & Abhängigkeiten

```
①  RCA/Blast-Radius (§3)        ── keine Abhängigkeit, reine Korrelation ── höchster ROI/Risiko-Quotient
②  Seasonal Baselines (§1)      ── Resolver-Muster (§0); fundiert spätere Predictive-SLAs
③  Segmentierung (§2)           ── eigenständig; größter Compiler-Anteil
④  Alert-Clustering (§4)        ── nutzt RCA-Lineage-Korrelation aus ① als Eingabe
```

**Empfehlung:** ① und ② parallel (verschiedene Schichten — Store/Lineage vs. obs/compiler),
danach ③, zuletzt ④ (baut auf ①).

| Feature | Migrationen | Engine berührt? | Neue Contract-Keys | Hauptaufwand |
|---|---|---|---|---|
| §1 Seasonal Baselines | `010` | nein | `baseline/season/sensitivity` | obs/, compiler, resolver |
| §2 Segmentierung | `011` | nein | `segment_by/max_segments` | compiler, store, UI |
| §3 RCA/Blast-Radius | `012` | nein | — | obs/rca, API, UI |
| §4 Alert-Clustering | `013` | nein | — | store, notifications, UI |

---

## 6 / Tests (mirror CI: tests/unit + tests/api)

- **§1:** `tests/unit` — Saison-Bucketing (Monatsende vs. Wochentag), MAD-Robustheit gegen
  injizierte Ausreißer, Warmup-Verhalten = G6-konform; Compiler-Determinismus-Hash unverändert
  bei gleichem Contract (Token, nicht Wert).
- **§2:** `tests/unit` — Auffächerung Garantie→Per-Segment-SQL, `max_segments`-Cap, S2 auf
  `segment_by`; `tests/api` — `segment_breakdown` im Result-Response, G8-Allowlist.
- **§3:** `tests/unit` — Upstream-Ranking nach Distanz/Zeit, Blast-Radius ∩ `contract_index`,
  Recurrence-Zählung; `tests/api` — `/incidents/{id}/rca`.
- **§4:** `tests/unit` — Correlation-Key-Gruppierung, Repräsentanten-Wahl
  (`*_contract` vor `internal_gate`); `tests/api` — eine Notification pro Cluster.

Alle vier: bestehende Engine-Suite (G5) muss **unverändert grün** bleiben — der Beweis, dass
`[ENGINE-FROZEN]` gehalten wurde.
