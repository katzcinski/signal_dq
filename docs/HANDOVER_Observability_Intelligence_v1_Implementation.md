# Handover: Observability-Intelligence v1 Implementation

**Stand:** 2026-06-29  
**Status:** implementierungsreifes Konzept / Handover  
**Quellen:** `docs/Konzept_Observability_Intelligence_v1.md`,
`docs/Marktanalyse_DQ_Observability_2026.md`, `docs/Tooldokumentation.md`,
aktueller Code-Stand nach `git pull origin main` auf `main`.

Dieses Dokument ist die handover-faehige Fassung der Grill-Entscheidungen fuer
Observability-Intelligence v1. Bei Widerspruch zum urspruenglichen Konzept gilt
dieses Handover.

## 1. Zielbild

Signal soll in v1 vier Intelligence-Luecken schliessen, ohne die bestehenden
Gates zu verletzen:

1. robuste und spaeter saisonale Baselines fuer Observability-Anomalien,
2. segmentierte Qualitaetsauswertung mit sicherem Detailkanal,
3. persistierte Root-Cause-Analyse und Blast-Radius je Incident,
4. Alert-Clustering als Gruppierung ueber bestehenden Incidents.

Zentrale Invariante: `packages/dq_core/engine/` bleibt `[ENGINE-FROZEN]`.
Keine neue Expectation-Grammatik, keine Engine-Metadaten-Bags, keine multi-row
Engine-Resultsets.

## 2. Festgezurrte Architekturentscheidungen

### 2.1 Adaptive Baselines sind Observability, nicht Contract-Compliance

Adaptive Baselines zaehlen in v1 nicht als semantische Contract-Garantie. Die
Governance-Garantie bleibt der harte Floor:

- `guarantees.volume.min_rows`
- `guarantees.freshness.max_age`

Adaptive Baselines werden als Monitoring-/Observability-Konfiguration modelliert
und duerfen einen Contract nicht automatisch `breached` setzen.

Konsequenz fuer die Implementierung:

- neue adaptive Checks sind nicht Teil des Compiler-Guarantee-Mappings,
- `compute_compliance(...)` darf fuer `consumer_contract`/`provider_contract`
  nur boundary-contract Ergebnisse beruecksichtigen,
- `internal_gate`-Runs koennen weiterhin Engineering-Signals erzeugen.

### 2.2 Keine unresolved Expectation-Tokens

`checks.yml` darf niemals `BETWEEN <BL_LO> AND <BL_HI>` oder aehnliche
ungebundene Expectation-Tokens enthalten. `load_dataset_config()` validiert
Expectations vor Ausfuehrung; solche Tokens waeren heute ungueltig.

V1-Muster:

- Compiler erzeugt nur normale Garantie-Checks.
- Runtime liest `observability` aus dem Contract und synthetisiert optionale
  Observability-Checks mit bereits numerischer Expectation, z. B.
  `BETWEEN 980 AND 1120`.
- Bei fehlender Baseline wird kein gruener Fake-Check erzeugt.

### 2.3 Warmup ist `downgraded`, nicht `executed/pass`

Wenn eine adaptive Baseline fehlt oder noch warm laeuft:

- der harte Floor laeuft normal,
- der adaptive Observability-Check erscheint sichtbar mit `state="downgraded"`,
- `passed=False`,
- keine Compliance-Auswirkung,
- keine Notification.

Das ist G6-konform, weil der Check nicht still verschwindet und nicht als echter
Pass getarnt wird.

### 2.4 Top-level `observability`

Adaptive Baseline-Konfiguration gehoert nicht unter `guarantees`, sondern in
eine neue top-level Sektion:

```yaml
guarantees:
  volume:
    min_rows: 1000
  freshness:
    column: ORDER_DATE
    max_age: PT26H

observability:
  volume:
    baseline: seasonal
    season: [dow, eom]
    sensitivity: medium
  freshness:
    baseline: rolling
    sensitivity: medium
```

Regeln:

- `guarantees.*` nimmt an Breaking-Diff, Compliance und ODCS teil.
- `observability.*` ist operatives Monitoring-Tuning.
- `observability.*` wird validiert und versioniert, aber nicht als G3-Breaking
  Change behandelt.
- ODCS-Export ignoriert `observability`.

Wichtig: `compiler_hash(contract)` darf durch reine `observability`-Aenderungen
nicht zu Check-Churn fuehren. Entweder nur den kompilierten Teil hashen oder
`observability` vor dem Hash entfernen.

### 2.5 Segmentierung bleibt scalar-first

Die Engine darf nie ein mehrzeiliges `GROUP BY`-Resultset erhalten.

V1-Muster:

- Primaerer Check gibt genau einen Skalar zurueck:
  Anzahl verletzender Segmente.
- Engine bewertet diesen Skalar mit `expect="= 0"`.
- Segmentdetails werden separat abgefragt und in einem eigenen Store-Kanal
  persistiert.

### 2.6 Segmentwerte brauchen eine explizite Allowlist

`segment_by` darf nicht auf jede gueltige Spalte angewendet werden. Segmentwerte
sind zwar Aggregate, koennen aber trotzdem sensitive IDs oder Namen leaken.

V1 braucht eine explizite Allowlist, z. B.:

- ENV/Settings: `SEGMENT_VALUE_COLUMNS=["REGION","COUNTRY","SOURCE_SYSTEM"]`
- spaeter optional per Objekt/Store konfigurierbar.

`PROFILE_SAMPLE_COLUMNS` darf dafuer nicht wiederverwendet werden, weil es fuer
Rohzeilen-Samples gedacht ist.

### 2.7 RCA wird bei Incident-Oeffnung persistiert

RCA soll nicht bei jedem `GET` neu berechnet werden. Sie wird beim Oeffnen eines
Incidents als abgeleitetes Snapshot-Artefakt persistiert.

V1-Muster:

- Incident wird geoeffnet oder aktualisiert.
- RCA wird fuer neue Incidents berechnet und gespeichert.
- API liest den Snapshot.
- spaeter optional: `POST /api/incidents/{id}/rca/recompute`.

### 2.8 Blast-Radius trennt Consumer-Contracts und interne Gates

RCA soll Downstream-Impact in zwei Buckets ausgeben:

- `affected_contracts`: aktive `consumer_contract`/`provider_contract`
- `affected_internal_gates`: aktive `internal_gate`

`contract_index` hat aktuell keine `kind`-Spalte. Die RCA-Migration muss diese
Spalte ergaenzen oder der Analyzer muss eine valide Kind-Map injiziert bekommen.
Empfohlen: `contract_index.kind` additiv migrieren.

### 2.9 Clustering ist eine Gruppierung ueber Incidents

Alert-Clustering ersetzt keine individuellen Incidents. Es gruppiert sie.

Bestehende Semantik bleibt:

- ein Incident pro Produkt/Gate-Episode,
- eigener Status, Owner, Timeline und Auto-Resolve je Incident,
- Cluster nur fuer Inbox-Gruppierung und Notification-Deduplizierung.

### 2.10 Clustering passiert vor Notification

Wenn Clustering erst nach `notify_breach(...)` passiert, loest es Alert-Fatigue
nicht. Der Flow muss daher werden:

1. Incident oeffnen oder aktualisieren.
2. RCA fuer neue Incidents berechnen.
3. `correlation_key` und `cluster_id` bestimmen.
4. Repraesentanten und Member-Count bestimmen.
5. Nur Repraesentant oder neuer Cluster feuert Notification.

`store.open_incident(...)` sollte daher langfristig mehr als nur `incident_id`
zurueckgeben.

## 3. Migrationsplan

Die aktuelle naechste freie Migration ist `010`. Nach den Grill-Entscheidungen
wird nicht direkt seasonal gestartet, sondern erst robuste globale Baseline.

Empfohlene Nummerierung:

| Migration | Inhalt |
|---|---|
| `010_baseline_median.sql` | `median_v` auf `dq_baselines` |
| `011_baseline_buckets.sql` | neue Bucket-Tabelle fuer saisonale Baselines |
| `012_segment_results.sql` | Segmentdetail-Tabelle |
| `013_incident_rca.sql` | RCA-Snapshot + `contract_index.kind` |
| `014_incident_clustering.sql` | Cluster-Spalten/Cluster-Tabelle |

## 4. Work Package A: Robuste globale Baseline

### Ziel

Kleiner, sofort testbarer Schritt: aktuelle globale Baselines robuster bewerten,
ohne Contract-Schema, Compiler oder Runner gross umzubauen.

### Dateien

- `packages/dq_core/store/migrations/010_baseline_median.sql`
- `packages/dq_core/obs/baselines.py`
- `packages/dq_core/store/sqlite_store.py`
- `tests/unit/test_metric_series.py`
- neue Unit-Tests, z. B. `tests/unit/test_baselines.py`

### Datenmodell

```sql
ALTER TABLE dq_baselines ADD COLUMN median_v REAL;
```

SQLite-Migrationen sind idempotent, weil doppelte `ADD COLUMN`-Fehler bereits
ignoriert werden.

### BaselineManager

Aktueller Stand:

- `update_baseline(...)` berechnet `median`, persistiert aber nur `mad`.
- `compute_bounds(...)` nutzt `mean +/- sigma*stddev`.

Soll:

- `median_v` persistieren,
- `robust_zscore(value, baseline)` ergaenzen,
- `compute_bounds(..., method="robust")` oder neue Methode
  `compute_robust_bounds(...)`.

Empfohlene Formel:

```text
robust_z = 0.6745 * (value - median_v) / mad
```

Sonderfaelle:

- `mad is None` oder `mad == 0`: fallback auf IQR/Perzentile, sonst Gleichheit
  gegen `median_v`.
- weniger als `WARMUP_N`: kein Verdikt, state wird spaeter `downgraded`.

### Tests

- Median wird persistiert.
- Ein Ausreisser im Trainingsfenster verschiebt robuste Bounds kaum.
- `mad == 0` erzeugt kein Division-by-zero.
- Bestehende `get_metric_series()`-Tests bleiben gruen.

## 5. Work Package B: Top-level `observability`

### Ziel

Contract-Dateien koennen Monitoring-Konfiguration tragen, ohne diese als
Guarantee zu kompilieren.

### Dateien

- `packages/dq_core/contract/validator.py`
- `packages/dq_core/contract/compiler.py`
- `packages/dq_core/contract/diff.py`
- `packages/dq_core/contract/odcs_export.py`
- `services/api/schemas/contract_schemas.py`
- `services/api/routers/contracts.py`
- Frontend Workbench types/forms:
  `apps/cockpit/src/pages/ContractWorkbench.tsx`,
  `apps/cockpit/src/i18n/de.ts`

### Schema

Additiv:

```yaml
observability:
  volume:
    baseline: rolling|seasonal|trend
    season: [dow|eom|hour]
    sensitivity: low|medium|high
  freshness:
    baseline: rolling|seasonal|trend
    season: [dow|eom|hour]
    sensitivity: low|medium|high
```

V1 kann `trend` validieren, aber als deferred markieren, oder es erst spaeter
zulassen. Konservativer Start: `rolling|seasonal`, `trend` noch nicht aktivieren.

### Compiler

Der Compiler ignoriert `observability` fuer Check-Erzeugung.

Wichtig:

- `compiler_hash(...)` darf nicht durch `observability`-Aenderungen wechseln,
  sofern keine kompilierten Checks entstehen.
- `compile_contract(...)` bleibt deterministisch.

### Diff / ODCS

- `diff.py` ignoriert `observability`.
- `odcs_export.py` ignoriert `observability`.
- API-Diff kann optional eine separate `operational_changes`-Liste zeigen, aber
  sie ist nicht blocking.

### Tests

- Validator akzeptiert top-level `observability`.
- Compiler-Output bleibt byte-identisch bei Aenderung nur unter
  `observability`.
- Breaking-Diff bleibt unveraendert.
- ODCS-Export enthaelt keine Observability-Konfiguration.

## 6. Work Package C: Runtime synthetisierte Observability-Checks

### Ziel

Adaptive Checks werden zur Laufzeit erzeugt oder downgraded, ohne
`checks.yml`-Tokens und ohne Engine-Aenderung.

### Dateien

- neues Modul `packages/dq_core/obs/resolver.py`
- `services/api/routers/objects.py`
- optional `cli/dq_check_runner.py` spaeter, wenn CLI denselben Runtime-Pfad
  bekommen soll
- `packages/dq_core/contract/compliance.py` oder Filterung in
  `services/api/routers/objects.py`

### Laufzeitquelle

`start_object_run(...)` laedt aktuell nur `checks.yml`. Fuer Observability muss
der aktive Contract ebenfalls gelesen werden, z. B. ueber bestehende Helpers
`_active_contract_for(...)` plus neue `_load_active_contract_data(...)`.

### Resolver-Verhalten

Input:

- `DatasetConfig` aus `checks.yml`
- Contract `observability`
- Store/BaselineManager
- `started_at`

Output:

- erweiterte Check-Liste fuer ausfuehrbare adaptive Checks,
- Liste von `CheckResult(state="downgraded")` fuer Warmup/Missing-Baseline,
- Metadaten fuer spaetere Anzeige optional.

V1 darf simple Scalar-SQL duplizieren:

- Volume: `SELECT COUNT(*) FROM "{schema}"."{dataset}"`
- Freshness: analog zum vorhandenen `freshness`-Template, wenn Column bekannt ist.

Optimierung, dass adaptive Checks vorhandene Row-Count/Freshness-Actuals
wiederverwenden, kann spaeter kommen.

### CheckDef-Eigenschaften

Empfohlen:

- `type="volume_anomaly"` oder `type="freshness_anomaly"`
- `severity="warn"` in v1
- `kind="internal_gate"` oder eigenes Monitoring-Kind ist nicht vorhanden.

Da `compute_compliance(...)` aktuell nicht nach `kind` filtert, muss der
Boundary-Contract-Pfad in `objects.py` vor Compliance-Berechnung filtern:

```python
contract_results = [
    r for r in summary.results
    if r.kind in ("consumer_contract", "provider_contract")
]
new_compliance = compute_compliance(contract_results)
```

Der `internal_gate`-Pfad kann weiterhin interne Ergebnisse auswerten.

### Warmup

Wenn keine Baseline existiert oder `warmup_remaining > 0`:

- keine ausfuehrbare adaptive `CheckDef`,
- sichtbarer `CheckResult` wird nach `run_checks()` an `summary.results`
  angehaengt,
- `state="downgraded"`,
- `passed=False`,
- `error` optional mit kurzer maschinenlesbarer Meldung, z. B.
  `"baseline_warmup"`.

### Tests

- Keine unresolved Tokens in `checks.yml`.
- Warmup erzeugt `downgraded`.
- Boundary-Contract-Compliance ignoriert Observability-Only-Fails.
- Internal-Gate-Verhalten bleibt unveraendert.

## 7. Work Package D: Saisonale Baseline-Buckets

### Ziel

Saisonale Baselines ohne riskante PK-Aenderung an `dq_baselines`.

### Dateien

- `packages/dq_core/store/migrations/011_baseline_buckets.sql`
- `packages/dq_core/obs/baselines.py`
- `packages/dq_core/obs/resolver.py`
- `packages/dq_core/store/sqlite_store.py`

### Datenmodell

Neue Tabelle statt `ALTER PRIMARY KEY`:

```sql
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
```

### Bucket-Key

Empfohlen:

- `dow=0..6`
- `eom=0|1`
- optional `hour=0..23`

Mehrere Achsen werden deterministisch sortiert:

```text
dow=2|eom=0
```

### Sensitivitaet

Mapping:

- `low -> k=4`
- `medium -> k=3`
- `high -> k=2`

Diese Werte duerfen Runtime-Metadaten sein. Sie muessen nicht im Baseline-Row
persistiert werden, wenn sie aus Contract-Observability rekonstruierbar sind.

### Tests

- gleicher Wochentag nutzt gleichen Bucket.
- Monatsende trennt `eom=1` von `eom=0`.
- Warmup gilt je Bucket.
- Global rolling bleibt unveraendert.

## 8. Work Package E: Segmentierung

### Ziel

Segmentierte Qualitaetsauswertung ohne Engine-Multirow und ohne PII-Leak.

### Dateien

- `packages/dq_core/store/migrations/012_segment_results.sql`
- `packages/dq_core/contract/validator.py`
- `packages/dq_core/contract/compiler.py`
- `services/api/settings.py`
- `services/api/routers/objects.py`
- `services/api/routers/runs.py`
- `services/api/schemas/run_schemas.py`
- Frontend:
  `apps/cockpit/src/pages/ObjectDetail.tsx`,
  `apps/cockpit/src/pages/RunDetail.tsx`,
  `apps/cockpit/src/i18n/de.ts`

### Settings

Neu:

```python
segment_value_columns: list[str] = Field(default=[])
```

ENV-Beispiel:

```text
SEGMENT_VALUE_COLUMNS=["REGION","COUNTRY","SOURCE_SYSTEM"]
```

### Contract-Schema

V1 nur fuer `completeness` starten:

```yaml
guarantees:
  completeness:
    - column: NET_AMOUNT
      min_pct: 99.5
      segment_by: REGION
      max_segments: 50
      severity: warn
```

`not_null`, `freshness`, `volume` koennen spaeter folgen. Nicht alles in einem
ersten Slice erzwingen.

### Compiler-Muster

Primaerer Check:

```sql
SELECT COUNT(*) FROM (
  SELECT "REGION" AS segment_value,
         ROUND(
           100.0 * COUNT(CASE WHEN "NET_AMOUNT" IS NULL THEN 1 END)
           / NULLIF(COUNT(*), 0),
           2
         ) AS null_pct
  FROM "{schema}"."DS_SALES_ORDERS"
  GROUP BY "REGION"
  HAVING ROUND(
    100.0 * COUNT(CASE WHEN "NET_AMOUNT" IS NULL THEN 1 END)
    / NULLIF(COUNT(*), 0),
    2
  ) > 0.5
) violating_segments
```

Engine sieht:

- `actual_value = Anzahl verletzender Segmente`
- `expect = "= 0"`

Detailquery:

```sql
SELECT "REGION" AS segment_value,
       ROUND(...) AS actual_value
FROM ...
GROUP BY "REGION"
HAVING ...
ORDER BY actual_value DESC
LIMIT <max_segments>
```

Die Detailquery wird nur ausgefuehrt, wenn `segment_by` in der Allowlist steht.

### Datenmodell

```sql
CREATE TABLE IF NOT EXISTS dq_segment_results (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL,
  check_name TEXT NOT NULL,
  segment_column TEXT NOT NULL,
  segment_value TEXT NOT NULL,
  actual_value REAL,
  threshold_value REAL,
  rank INTEGER DEFAULT 0,
  created_at TEXT DEFAULT '',
  FOREIGN KEY (run_id) REFERENCES dq_runs(run_id)
);

CREATE INDEX IF NOT EXISTS ix_segment_results_run_check
  ON dq_segment_results(run_id, check_name);
```

### API

Optionen:

- `GET /api/runs/{id}/results` erweitert jedes Ergebnis um
  `segment_breakdown`.
- oder neuer Endpoint:
  `GET /api/runs/{id}/results/{check_name}/segments`.

Empfehlung: neuer Endpoint zuerst, weil die bestehende Result-Liste schlank
bleibt. Danach kann das FE bei Bedarf lazy laden.

### Tests

- Compiler erzeugt scalar `COUNT(*) FROM (...)`.
- Unsichere Identifier werden abgelehnt.
- Nicht allowlisted `segment_by` verhindert Detailpersistenz.
- API liefert nur aggregierte Segmentwerte.
- Keine Zeilen in `dq_diagnostics`.

## 9. Work Package F: RCA und Blast-Radius

### Ziel

Bei Incident-Oeffnung persistierte RCA mit Ursache, Blast-Radius und Recurrence.

### Dateien

- `packages/dq_core/store/migrations/013_incident_rca.sql`
- neues Modul `packages/dq_core/obs/rca.py`
- `packages/dq_core/store/sqlite_store.py`
- `packages/dq_core/store/base.py`
- `services/api/routers/objects.py`
- `services/api/routers/incidents.py`
- Frontend:
  `apps/cockpit/src/pages/Incidents.tsx`,
  optional `apps/cockpit/src/components/LineageMiniGraph.tsx`

### Migration

```sql
ALTER TABLE contract_index ADD COLUMN kind TEXT NOT NULL DEFAULT 'internal_gate';

CREATE TABLE IF NOT EXISTS dq_incident_rca (
  incident_id INTEGER PRIMARY KEY,
  probable_cause_object TEXT DEFAULT '',
  cause_confidence REAL,
  cause_candidates_json TEXT DEFAULT '[]',
  affected_contracts_json TEXT DEFAULT '[]',
  affected_internal_gates_json TEXT DEFAULT '[]',
  recurrence_count INTEGER DEFAULT 0,
  recurrence_last_at TEXT DEFAULT '',
  computed_at TEXT NOT NULL,
  FOREIGN KEY (incident_id) REFERENCES dq_incidents(id)
);
```

`_update_index(...)` in `contracts.py` muss `kind` setzen.

### Analyzer

`dq_core.obs.rca` bleibt frameworkfrei. Empfohlene Signatur:

```python
def analyze_incident(
    *,
    incident: dict,
    run: dict,
    lineage: dict,
    contract_index: list[dict],
    recent_failures: list[dict],
    prior_incidents: list[dict],
    window_minutes: int = 120,
) -> dict:
    ...
```

Die Store-Methoden koennen die Listen liefern; der Analyzer bleibt pure Python.

### Ursache

Ranking nach:

- Lineage-Distanz upstream,
- zeitlicher Naehe zum Incident-Run,
- Check-Familie: Schema/Volume/Freshness staerker als einzelne Quality-Regel,
- Severity.

Konservative Confidence:

```text
confidence = distance_score * time_score * severity_score
```

Nie behaupten, dass Ursache sicher ist. UI-Label: "Wahrscheinliche Ursache".

### Blast-Radius

Downstream aus Lineage berechnen, dann mit `contract_index` schneiden:

- `lifecycle == "active"`
- `kind in ("consumer_contract","provider_contract")` ->
  `affected_contracts`
- `kind == "internal_gate"` -> `affected_internal_gates`

### Recurrence

V1:

- gleicher `product`,
- offene/alte Incidents der letzten 90 Tage,
- optional overlap in `failed_checks`.

### API

Neu:

```text
GET /api/incidents/{incident_id}/rca
```

Optional spaeter:

```text
POST /api/incidents/{incident_id}/rca/recompute
```

### Tests

- Upstream-Kandidat mit kurzerer Distanz gewinnt.
- Zeitnaehere Failure gewinnt bei gleicher Distanz.
- Blast-Radius trennt Boundary Contracts und Internal Gates.
- API gibt Snapshot zurueck, nicht live recomputed Drift.

## 10. Work Package G: Incident-Clustering

### Ziel

Notification-Deduplizierung und gruppierte Incident-Inbox, ohne individuelle
Incidents zu verlieren.

### Dateien

- `packages/dq_core/store/migrations/014_incident_clustering.sql`
- `packages/dq_core/store/sqlite_store.py`
- `services/api/routers/objects.py`
- `services/api/routers/incidents.py`
- `services/api/notify.py`
- Frontend:
  `apps/cockpit/src/pages/Incidents.tsx`,
  `apps/cockpit/src/i18n/de.ts`

### Datenmodell

Empfohlen mit eigener Cluster-Tabelle:

```sql
CREATE TABLE IF NOT EXISTS dq_incident_clusters (
  cluster_id TEXT PRIMARY KEY,
  correlation_key TEXT NOT NULL,
  representative_incident_id INTEGER,
  opened_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  member_count INTEGER NOT NULL DEFAULT 1
);

ALTER TABLE dq_incidents ADD COLUMN cluster_id TEXT;
ALTER TABLE dq_incidents ADD COLUMN correlation_key TEXT;

CREATE INDEX IF NOT EXISTS ix_incidents_cluster
  ON dq_incidents(cluster_id);

CREATE INDEX IF NOT EXISTS ix_incidents_correlation
  ON dq_incidents(correlation_key);
```

Wenn man keine neue Tabelle will, kann der Repraesentant per Query berechnet
werden. Die Tabelle macht Notification-Entscheidungen aber einfacher und
stabiler.

### Store-API

Bestehendes `open_incident(...)` gibt nur `int | None` zurueck. Fuer Clustering
besser:

```python
@dataclass
class IncidentOpenResult:
    incident_id: int
    created: bool
    cluster_id: str
    correlation_key: str
    is_representative: bool
    member_count: int
```

Rueckwaertskompatibel:

- neue Methode `open_incident_record(...)`,
- alter `open_incident(...)` Wrapper gibt weiter nur die ID zurueck,
- Aufrufer in `objects.py` werden auf die neue Methode gehoben.

### Correlation-Key

Prioritaet:

1. RCA probable cause: `cause:<object>|window:<bucket>`
2. gleiche Failure-Familie im gleichen Run:
   `run:<run_id>|family:<schema|volume|freshness|quality>`
3. Fallback Zeitfenster:
   `product:<product>|severity:<severity>|window:<15m-bucket>`

Fenster:

- Default 15 Minuten,
- als Setting ergaenzen, z. B. `INCIDENT_CLUSTER_WINDOW_MINUTES=15`.

### Repraesentant

Sortierung:

1. hoechste Severity: `critical > fail > warn`,
2. Boundary Contract vor Internal Gate,
3. fruehester Incident im Cluster.

Nur Repraesentant feuert `notify_breach(...)`.

### Notification-Payload

Bestehende `match_kind`-Regeln greifen auf den Repraesentanten. Payload wird
erweitert:

```json
{
  "cluster_id": "...",
  "member_count": 7,
  "affected_products": ["A", "B"],
  "probable_cause": "SRC_X"
}
```

### API

`GET /api/incidents`:

- Default kann bestehende Liste bleiben.
- Neuer Query-Parameter:

```text
GET /api/incidents?group=cluster
```

Response pro Cluster:

- representative incident fields,
- `cluster_id`,
- `member_count`,
- `members` optional oder lazy endpoint.

### Tests

- Zwei Incidents mit gleicher Ursache landen im gleichen Cluster.
- Produkt-eigene Incident-Timeline bleibt erhalten.
- Nur Repraesentant loest Notification aus.
- `match_kind` bleibt kompatibel.

## 11. Empfohlene Umsetzungsreihenfolge

1. **A: robuste globale Baseline**  
   Kleinster, sofort testbarer Slice. Keine API-/FE-Abhaengigkeit.

2. **B: top-level `observability`**  
   Legt saubere Contract-Semantik fest und verhindert weitere Vermischung mit
   Guarantees.

3. **C: runtime synthetisierte Observability-Checks**  
   Macht adaptive Monitoring-Signale sichtbar, ohne Engine- oder Compiler-Bruch.

4. **D: saisonale Buckets**  
   Baut auf A-C auf.

5. **F: RCA/Blast-Radius**  
   Hoher ROI und relativ isoliert, kann parallel zu A-D laufen.

6. **G: Clustering**  
   Nach RCA, weil Correlation-Key den RCA probable cause nutzen soll.

7. **E: Segmentierung**  
   Eigenstaendig, aber groesserer Compiler/API/UI-Schnitt. Nach den kleineren
   Observability- und RCA-Slices starten.

## 12. CI-/Verification-Matrix

Backend:

```powershell
python -m pytest tests/unit/test_metric_series.py -q
python -m pytest tests/unit/test_contract_validator.py tests/unit/test_compiler.py -q
python -m pytest tests/unit/test_incidents_sla_gating.py tests/unit/test_notify.py -q
python -m pytest tests/api/test_run_subresources.py tests/api/test_notifications.py -q
```

Bei groesseren Slices:

```powershell
python -m pytest tests/ -q
```

Frontend bei UI-Slices:

```powershell
cd apps/cockpit
npm run test
npm run typecheck
```

Gates, die explizit bewiesen werden muessen:

- G1: Contracts bleiben SQL-frei.
- G2: `{schema}` wird nur runtime gebunden.
- G5/G7: Engine-Suite bleibt unveraendert gruen; keine FastAPI-Imports in
  `dq_core`.
- G6: Warmup/Skip/Downgrade sichtbar, nicht als Pass getarnt.
- G8: Segmentdetails sind allowlisted Aggregate, keine Rohzeilen.

## 13. Handover-Hinweise fuer die naechste Agent-Session

Suggested skills:

- `tdd` fuer jeden Work Package Slice.
- `diagnose`, falls bestehende Run-/Incident-Tests durch Status-Semantik brechen.
- `vercel-react-best-practices` bei UI-Erweiterungen im Cockpit.

Wichtige lokale Fakten:

- `main` ist auf `origin/main` fast-forwarded.
- Es gibt untracked lokale `.claude`-Dateien; sie sind nicht Teil dieser Arbeit.
- `HanaStore` ist weiterhin Stub; alle neuen Store-Methoden muessen langfristig
  fuer SQLite und HANA gedacht werden, auch wenn V1 nur SQLite testet.
- `contract_index` enthaelt aktuell keine `kind`-Spalte.
- `CheckDef` hat aktuell keinen Metadata-Container. Fuer V1 keine Engine-
  Dataclass-Erweiterung nur fuer Observability-Metadaten einfuehren, solange ein
  separater Store/API-Kanal reicht.

## 14. Offene, aber nicht blockierende Entscheidungen

- Soll ein fehlgeschlagener adaptive Observability-Check in V1 nur `warn` im Run
  sein oder auch ein eigenes Engineering-Signal oeffnen? Empfehlung fuer V1:
  nur `warn`, kein Alert, bis Clustering/Routing steht.
- Soll Segmentierung nach `completeness` direkt auf `not_null` erweitert werden?
  Empfehlung: erst `completeness`, weil sie prozentuale Segmentmetriken sichtbar
  macht.
- Soll `trend` schon validiert werden? Empfehlung: nein, erst `rolling` und
  `seasonal` stabilisieren.

