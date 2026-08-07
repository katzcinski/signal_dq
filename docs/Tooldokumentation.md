# Signal — Tooldokumentation (vollständige Referenz)

**Stand:** 2026-07-23 · **Komponente:** Data Quality & Observability Cockpit für SAP Datasphere

Diese Datei ist die zusammenhängende technische Referenz und beschreibt den **implementierten Stand**. Einstieg und Schnellstart: [`../README.md`](../README.md). Betriebsmodi/Personas: [`Betriebsmodi_Lite_und_Full.md`](Betriebsmodi_Lite_und_Full.md). Gate-vs-Contract-Klassifikation (`kind`): [`ADR-0001_Quality-Gates_vs_Contracts.md`](ADR-0001_Quality-Gates_vs_Contracts.md). Fachliches Konzept: [`Konzept_DQ_Observability_Cockpit.md`](Konzept_DQ_Observability_Cockpit.md). Implementierungs-/Planungshistorie & Gates: [`HANDOVER.md`](HANDOVER.md), [`PLAN_Remediation_v2.md`](PLAN_Remediation_v2.md).

## Inhalt

1. [Was Signal ist](#1--was-signal-ist)
2. [Architektur](#2--architektur)
3. [Kernkonzepte](#3--kernkonzepte)
4. [Datenmodell & Persistenz](#4--datenmodell--persistenz)
5. [API-Referenz](#5--api-referenz)
6. [Konfiguration (ENV)](#6--konfiguration-env)
7. [CLI](#7--cli)
8. [Frontend (Cockpit)](#8--frontend-cockpit)
9. [Sicherheit & Gates](#9--sicherheit--gates)
10. [Deployment](#10--deployment)
11. [Entwicklung & Tests](#11--entwicklung--tests)
12. [Glossar](#12--glossar)

---

## 1 — Was Signal ist

Signal verwandelt **semantische Garantien** über Datasphere-Objekte in **deterministisch kompilierte, ausführbare Quality-Checks**, fährt sie lesend gegen HANA und macht den Zustand als Cockpit, Compliance-Ampel und Coverage-Map sichtbar.

**Leitprinzipien:**

- **Contracts tragen Garantien, nie SQL** (Gate G1). Der einzige Ort, an dem SQL entsteht, ist der Compiler.
- **Engine ist eingefroren & frameworkfrei** (`dq_core` importiert nie FastAPI). Erweitern statt ändern.
- **Vier Zustands-Achsen sind getrennt**: Lifecycle (Erstellung) · Compliance (Halten der Zusage) · Coverage (Abdeckung) · Enforcement (Konsequenz eines Breaches: `gate | quarantine | monitor`).
- **`kind` trennt Quality Gate von Contract** (ADR-0001): „Checks überall, Contracts nur an den Parteigrenzen." Gleiche Engine/Regel, unterschiedliche Konsequenz — ein `internal_gate`-Fehler ist ein Engineering-Signal, ein `*_contract`-Fehler ein governance-relevanter Compliance-Breach.
- **Ein Code, zwei Deployments**: lokal (SQLite/NoAuth) und Kunde (HANA/OIDC) über Auth-/Store-Abstraktion, ohne Code-Zweige.

---

## 2 — Architektur

![Signal — Architekturdiagramm](assets/architektur.svg)

**Drei getrennte Persistenzorte (HANDOVER §0):**

- **Git** — Contracts (`contracts/<product>.yaml`), zertifizierte Snapshots (`<product>.active.yml`), kompilierte Checks (`checks/<product>/checks.yml`).
- **Result-Store** — Läufe, Check-Ergebnisse, Diagnostics, Baselines, Compliance, Incidents (SQLite lokal / `dq_results_lt` in HANA).
- **HANA/Datasphere** — die geprüften Daten, ausschließlich lesend.

**Identitäts-Join mapping-frei:** `lineage node.id == inventory.technicalName == dq_object_status.object_name == product`.

**`dq_core`-Module:**

| Modul | Inhalt |
|---|---|
| `engine/` | `check_engine.py` (run_checks), `expectation.py` (Grammatik), `models.py` (Dataclasses) — `[ENGINE-FROZEN]` |
| `contract/` | `model.py` (inkl. `kind`), `validator.py` (G1, `VALID_KINDS`), `compiler.py` (G1/G2/S2), `diff.py` (Breaking), `gate_g3.py` (CI-Shim, kind-gegated), `compliance.py` (pass/fail-Orakel), `seed.py`, `odcs_export.py` (nur `*_contract`) |
| `validator/` | `core.py` — eigenständige Validierungsbausteine (geteilt von Contract-Validator und API) |
| `store/` | `base.py` (Protocol), `sqlite_store.py`, `hana_store.py`, `migrations/NNN_*.sql` |
| `connect/` | `db_connection.py` (hdbcli + Retry, `MockConnection`) |
| `library/` | `check_library.py` + `check_library.json` (versionierter `sql_template`-Katalog) |
| `lineage/` | Analyzer-Loader, Spalten-Lineage, CSN-Rekonstruktor, kind-aware `get_coverage` |
| `obs/` | `baselines.py` (Rolling-Stats), `miner.py` (Proposal-Mining, inkl. `kind`) |
| `profile/` | `profiler.py`, `heuristics.py`, `pk_detection.py` — Spaltenstatistik, PK-Kandidaten, optionale Sample Rows `[PII-GATE]` |

---

## 3 — Kernkonzepte

### 3.1 Contract (Schema v1, SQL-frei)

```yaml
product: DS_SALES_ORDERS         # Identifier, = Dateiname & Join-Key
kind: consumer_contract          # internal_gate | consumer_contract | provider_contract (default: internal_gate)
dataset: DS_SALES_ORDERS         # Datasphere-Objekt; Schema wird NICHT hier gebunden
owned_by: product                # platform | product
owners: ["grp:data-platform"]    # optionale ACL (sub oder grp:)
version: "1.0.0"                 # SemVer
lifecycle: active                # draft | active | deprecated  (NIE compliance!)
guarantees:
  schema:       { columns: [ORDER_ID, CUSTOMER_ID, NET_AMOUNT], mode: closed }
  keys:         [{ columns: [ORDER_ID], unique: true, severity: critical }]
  referential:  [{ fk: [CUSTOMER_ID], parent: Customers_View, parent_key: [CUSTOMER_ID], severity: fail }]
  not_null:     [{ columns: [ORDER_ID, NET_AMOUNT], severity: fail }]
  completeness: [{ column: NET_AMOUNT, min_pct: 99.5, severity: warn }]
  freshness:    { column: ORDER_DATE, max_age: PT26H, severity: warn }
  volume:       { min_rows: 1000, severity: warn }
```

`compliance` und `schema_ref` stehen **nicht** im YAML: Compliance lebt im Store (A1), das Schema wird zur Laufzeit aus dem Environment gebunden (A2/G2). `kind` fehlt → Default `internal_gate` (der ehrliche Default: ohne zugestimmte Gegenpartei ist ein Set ein internes Gate, kein Contract).

### 3.2 Garantie-Familien → Checks (Compiler)

| Familie | Template | Expectation | Severity-Default |
|---|---|---|---|
| `schema` (closed/open) | `schema` | `= N` / `>= N` Spalten | critical |
| `keys` | `duplicate` / `duplicate_composite` | `= 0` | critical |
| `referential` | `reference_integrity` | `= 0` Orphans | fail |
| `not_null` | `missing` | `= 0` | fail |
| `completeness` | `completeness_pct` | `<= (100 − min_pct)%` | warn |
| `freshness` | `freshness` | `< max_age` (Sekunden) | warn |
| `volume.min_rows` | `row_count` | `>= min_rows` | warn |

Die Check-Library stellt zusätzlich generische Templates für Standard-Lücken bereit. Sie sind aber nicht automatisch Contract-Garantien:

| Template | Status | Begründung |
|---|---|---|
| `duplicate_composite` | Contract-Garantie über `keys.columns` | Der deklarierte Grain/Key ist eine konsumierbare Zusage. |
| `volume_anomaly` | Internal Observability-Check | Baseline-Drift ist laufzeit- und historienabhängig; Contract bleibt `volume.min_rows`. |
| `cross_field_consistency` | Internal/manueller Check | Fachliche Mehrspaltenregeln brauchen erst eine SQL-freie DSL, bevor sie Contract-Garantien werden. |
| `type_conformance` | später Contract-Garantie | Erst wenn das Contract-Schema deklarierte Spaltentypen trägt. |

`volume.baseline: rolling` bleibt Observability-Konfiguration; die Runtime-Zeitreihe und Baseline-Pflege liefern die Historie, auf die `volume_anomaly` zielt.

Bewusst **nicht** in der Runtime-Library: Reconciliation / Control-Total gegen eine externe Quelle. Das ist ein Accuracy-Check mit Cross-System-Runtime und gehört als eigener Integrationspfad dokumentiert, nicht als generisches HANA-Template.

Der Compiler ist **deterministisch**: Header-Hash = f(Contract-Hash, Library-Version); gleicher Input ⇒ byte-identische `checks.yml`. Merge mit handgepflegten Suiten ist **existing-wins**.

### 3.3 Expectation-Grammatik (eingefroren)

`IS NULL` · `IS NOT NULL` · `= != >= <= > < n` · `BETWEEN a AND b` · `= n ±t` · `IN(...)` / `NOT IN(...)` · `DELTA <op> p%` (nutzt `previous_value`) · `MATCHES /regex/`. Neue Operatoren nur über `expectation.py` + `validate_expectation` + Tests.

### 3.4 Lifecycle, Compliance, Coverage

- **Lifecycle** (YAML): `draft → active → deprecated`. PUT erzeugt immer einen Draft; `approve`/`certify` aktivieren.
- **Compliance** (Store, **nur `*_contract`**): `unknown → compliant | breached`. `breached` bei ≥1 nicht bestandenem Check ≥ `fail` der aktiven Version; Auto-Recovery bei grünem Folgelauf. Übergänge sind Events (`since`, `last_run_id`); Neu-Breach öffnet ein **Contract-Breach**-Incident. Ein `internal_gate` schreibt **keine** Compliance/SLA, sondern öffnet bei Fehler ein **Engineering-Signal**-Incident (Team-Routing).
- **Coverage** (abgeleitet, kind-aware): `covered` (active + kompilierte Checks) · `partial` (active, keine Checks) · `gap` (Set, nicht active) · `out_of_scope` (kein Set). Die Coverage-Map unterscheidet zusätzlich `has_internal_gate` vs. `has_boundary_contract`.

### 3.5 `kind` — Quality Gate vs. Contract (ADR-0001)

`kind` ist der Klassifikations-Diskriminator je Set/File (validiert in `dq_core/contract/validator.py`, `VALID_KINDS`):

| `kind` | Bedeutung | Konsequenz bei Verletzung | Lifecycle-Zeremonie | ODCS-Export |
|---|---|---|---|---|
| `internal_gate` | internes Quality Gate, keine Gegenpartei (**Default**) | Engineering-Signal (Team-intern), **keine** Ampel/SLA | frei änderbar, zeremonielos | nie (409) |
| `consumer_contract` | Versprechen an den Consumer | Contract-Breach, Compliance-Ampel + SLA | SemVer, Approval, Breaking-Schutz (G3) | ja |
| `provider_contract` | Versprechen der Quelle/des Providers | wie consumer | wie consumer | ja |

**„Gleiche Regel, zwei Artefakte"** — Engine, Compiler, Store und Check-Library bleiben kategorie-agnostisch; nur der Governance-Mantel folgt dem `kind`. Die **Promotion** `internal_gate → consumer_contract` (`POST …/promote`, Copy-Semantik) ist der explizite Governance-Akt, an dem aus interner Kontrolle ein Versprechen wird. Gates G1/G2/G6/G7/G8 bleiben für alle `kind` scharf. Vollständige Begründung und Komposition über Produktgrenzen: [`ADR-0001_Quality-Gates_vs_Contracts.md`](ADR-0001_Quality-Gates_vs_Contracts.md).

### 3.6 Lite vs. Full

| | Lite | Full |
|---|---|---|
| Aktivierung | `POST …/certify` (ein Schritt) | `PUT` → `approve` → `compile` |
| Versionierung | keine Pflicht | SemVer, Breaking ⇒ Major (G3) |
| Breaking-Gate | nur für bereits zertifizierte `*_contract` | immer blockierend (nur `*_contract`) |

Lite/Full beschreibt die **Prozess-Zeremonie** und ist **orthogonal** zu `kind` (Grenz-Klassifikation). Der Editor-**Default**-Modus wird aus dem `kind` abgeleitet (`internal_gate` → Lite/„Schnell zertifizieren", `*_contract` → Full/„Freigabe-Workflow"); der Override entfällt auf bereits zertifizierten Contracts (ADR-0006). Vollständig in [`Betriebsmodi_Lite_und_Full.md`](Betriebsmodi_Lite_und_Full.md) und [`ADR-0006_Editor-Modus_aus_Kind.md`](ADR-0006_Editor-Modus_aus_Kind.md).

### 3.7 Check-Bibliothek & Familien-Rollup

`packages/dq_core/library/check_library.json` ist die einzige Quelle für Engine-Defaults **und** UI-Picker: **24 Templates in 4 Kategorien** (Vollständigkeit · Konsistenz · Verteilung & Aggregate · Aktualität & Sonstiges). Der Cockpit-Rollup klassifiziert je **Check-Typ** (`ResultStore._OBS_TYPES`): **Observability** = `freshness, row_count, schema, volume_delta, column_count, recent_volume`; alles andere = **Quality**.

- **Observability** (Pipeline/Form/Menge): `row_count`, `freshness`, `schema` plus die Quick-Wins `volume_delta` (`DELTA <op> %` ggü. Vorlauf), `column_count` (Spaltenzahl-Stabilität, `DELTA = 0%`), `recent_volume` (frische Zeilen im Fenster). `recent_volume` wird wie `row_count` als Volume-Zeitreihe gebaselined.
- **Quality** (Inhalt): u. a. `missing`, `completeness_pct`, `empty_string`, `duplicate(_composite/_approx)`, `invalid`, `value_range`, `allowed_values`, `pattern_match`, `string_length`, `reference_integrity`, `cross_column_compare`, `future_dates`, `aggregate_range`, `distinct_count`, `row_count_match`, `custom_sql`.
- SAP/BDC-spezifische Templates wurden zugunsten allgemein gebräuchlicher, Soda-/GX-naher Checks entfernt.

Der **Compiler** (§3.2) bildet Garantie-Familien auf eine feste Template-Teilmenge ab; die übrige Bibliothek steht dem manuellen Check Builder zur Verfügung.

### 3.8 Enforcement-Achse — `gate | quarantine | monitor`

`enforcement` ist die vierte Zustands-Achse je Check/Garantie (Default **`monitor`** — keine grüne Pipeline wird zum Überraschungs-Stopp), plus `enforcement_default` am Contract. Sie beschreibt, *welche Konsequenz* ein Breach hat, orthogonal zu `severity` und Lite/Full:

- **`monitor`** — nur beobachten (Compliance/Incident wie bisher).
- **`gate`** — der Lauf erhält das Verdict `block`; die konsumierende Task-Chain stoppt.
- **`quarantine`** — Verdict `quarantine`; im Lauf-Pfad wird eine **Quarantäne-Episode** geöffnet (Lifecycle `open → reconciled → released → resolved`, `+ superseded`, Migration 016).

Aus den Check-Ergebnissen rollt ein state-bewusstes (G6) **`gate_verdict`** je Lauf auf: `proceed | quarantine | block`. Konsum-Pfade: CLI-Exit-Codes 0/1/3 (`--no-enforce` schaltet ab), `GET /api/runs/{id}/status` (API-Task-Vertrag mit `fail_on`-Mapping) und — opt-in, doppelt gegated über `ENFORCEMENT_MATERIALIZE_ENABLED` + `DATASPHERE_SIGNAL_SCHEMA` — die **Verdict-Materialisierung** ins Signal-eigene Open-SQL-Schema (`packages/dq_core/enforce/`, `V_DQ_GATE_STATUS`, `P_DQ_ASSERT_GATE`), damit Datasphere-Task-Chains das Gate SQL-seitig abfragen können. Signal bleibt dabei read-only gegenüber **Kundendaten** (ADR-0002-Amendment: Schreiben nur im eigenen Schema). Konzepte: [`Konzept_Enforcement_Modi_Gate_Quarantine_Monitor.md`](Konzept_Enforcement_Modi_Gate_Quarantine_Monitor.md), [`Konzept_Datasphere_Integration_Gating_Quarantaene.md`](Konzept_Datasphere_Integration_Gating_Quarantaene.md).

---

## 4 — Datenmodell & Persistenz

Result-Store-Schema über nummerierte, idempotente Migrationen (`packages/dq_core/store/migrations/`):

| Migration | Inhalt |
|---|---|
| `001_initial_schema` | `dq_runs`, `dq_check_results`, `dq_diagnostics` |
| `002_state_stats_lineage_compliance` | `state`-Spalte, `contract_version/hash/actor/run_state`, `dq_check_stats`, `dq_baselines`, `dq_proposals`, `dq_compliance`, `contract_index` |
| `003_compliance_events_run_guard` | Compliance-Event-Log + Doppellauf-Guard |
| `004_incident_lifecycle` | Incident-Tabellen + Timeline |
| `005_notification_routing` | Notification-Kanäle/Regeln/Mutes |
| `006_artifact_kind` | `dq_check_results.kind` (ADR-0001-Diskriminator, Default `internal_gate`) |
| `007_incident_kind` | `dq_incidents.kind` (Engineering-Signal vs. Contract-Breach, Backfill `consumer_contract`) + `dq_notification_rules.match_kind` (Wildcard wenn leer) |
| `008_operations` | Generischer Operation-/Progress-Kanal (ADR-0007) |
| `009_schedules` | `dq_schedules` + Due-Run-Claim-Queue (ADR-0005, Option E) |
| `010_baseline_median` | Observability-Intelligence v1: robuste globale Baselines (`median`/`mad`) |
| `011_baseline_buckets` | Observability-Intelligence v1: saisonale Baseline-Buckets |
| `012_segment_results` | Observability-Intelligence v1: allowlisted Aggregat-Segment-Details |
| `013_incident_rca` | Observability-Intelligence v1: persistierte RCA-Snapshots + Contract-Kind-Index |
| `014_incident_clustering` | Observability-Intelligence v1: Incident-Clustering für Notification-Dedupe |
| `014_schema_snapshots` | Shift-Left-Schema-Drift: `dq_schema_snapshots` (Quellschema-Historie) + `dq_schema_drift` (Drift-Befunde gegen das Contract-Versprechen) |
| `015_incident_impact` | Observability-Intelligence v1: `dq_incidents.impacted_objects` (Downstream-Impact-Snapshot) |
| `015_profile_snapshots` | Data-Diff: `dq_profile_snapshots` (Aggregat-Profile als Snapshots für Distribution-/Key-Diff, ohne Sample-Rows) |
| `016_enforcement` | Enforcement-Achse: `dq_check_results.enforcement_mode`, `dq_runs.gate_verdict`, `dq_quarantine` + `dq_quarantine_events` (Episoden-Lifecycle) |

> Die Nummern **014** und **015** sind doppelt belegt (je zwei Dateien aus parallelen Feature-Strängen). Das ist unschön, aber unkritisch und bleibt so: Der Runner trackt Migrationen per **Dateiname** in `schema_migrations`, nicht per Nummer, und ausgelieferte Migrationen werden nie umbenannt. Neue Migrationen beginnen bei `017_…`.

**Zentrale Tabellen (Auszug):**

- `dq_runs(run_id PK, dataset, schema_name, started_at, finished_at, overall_status, total/passed/failed/warning_checks, run_state, contract_version, contract_hash, actor, triggered_by, gate_verdict)` — `gate_verdict ∈ {proceed, quarantine, block}`
- `dq_check_results(id PK, run_id FK, check_name, sql_text, expect_expr, severity, passed, actual_value, error_message, duration_ms, state, kind, enforcement_mode)` — `state ∈ {executed, skipped_stale, skipped_dependency, downgraded, error}`
- `dq_quarantine` + `dq_quarantine_events` — Quarantäne-Episoden (`open → reconciled → released → resolved`, `+ superseded`), Dedupe je Produkt über `manifest_hash`
- `dq_diagnostics(id PK, run_id, check_name, row_data)` — **PII-Kanal**, default leer
- `dq_compliance(product PK, contract_version, compliance, since, last_run_id)`
- `contract_index(product PK, lifecycle, owned_by, version, head_hash, updated_at)` — Lese-Index (Git ist keine Query-DB)
- `dq_baselines`, `dq_check_stats`, `dq_proposals`

`dq_object_status` ist eine Store-Query/View (kein Sync-Job): je Objekt × Familie der jüngste `state`+Status, gejoint mit `dq_compliance`.

Migrationen laufen idempotent beim Store-Open (Runner trackt `schema_migrations`). Neue Tabellen/Spalten **immer** über eine nummerierte Migration.

---

## 5 — API-Referenz

FastAPI, Basis `/api`. Interaktive Docs zur Laufzeit: `/api/docs` (Swagger), `/api/redoc`, Schema `/api/openapi.json`. Fehlerformat: RFC-7807 `application/problem+json`. Health: `GET /api/health`.

### Objekte & Läufe

| Methode | Pfad | Zweck |
|---|---|---|
| GET | `/api/objects` | Rollup je Objekt (Status, Familien, Coverage, letzter Lauf) |
| GET | `/api/objects/{id}` | Objekt-Detail inkl. Checks des letzten Laufs |
| GET | `/api/objects/{id}/runs` | Lauf-Historie des Objekts |
| GET | `/api/objects/{id}/checks/{name}/history` | `actual_value`-Zeitreihe (Sparkline) |
| GET | `/api/objects/{id}/timeseries` | aggregierte Zeitreihen |
| POST | `/api/objects/{id}/run` | Lauf auslösen → `202 {run_id}` `[AUTHZ]` |
| POST | `/api/objects/{id}/profile` | Profil-Lauf (Stats-Tuple) |
| GET | `/api/runs` · `/api/runs/{id}` | Läufe (paginiert `limit/offset`) / Detail |
| GET | `/api/runs/{id}/status` | API-Task-Vertrag: `RUNNING/COMPLETED/FAILED` + `gate_verdict` (`fail_on`-Mapping für Task-Chains) |
| GET | `/api/runs/{id}/results` · `/diagnostics` · `/events` | Ergebnisse · PII-gated Rohzeilen · SSE |
| GET | `/api/runs/compare?base=&head=` | Lauf-/Versions-Vergleich (Statuswechsel je Check, inkl. `value_delta` vorher→nachher — B-1 Data-Diff) |
| POST | `/api/objects/{id}/diff` | Data-Diff zweier Profil-Snapshots: `distribution` (Verteilungs-Diff) bzw. `keys` (Key-Reconciliation) `[AUTHZ steward+]` |

### Contracts

| Methode | Pfad | Zweck |
|---|---|---|
| GET | `/api/contracts` | Liste aus `contract_index` (Filter lifecycle) |
| GET/PUT | `/api/contracts/{product}` | Lesen / Draft schreiben (G1) `[AUTHZ]` |
| POST | `/api/contracts/{product}/seed` | Draft aus Inventar erzeugen |
| POST | `/api/contracts/{product}/promote` | `internal_gate` → `consumer_contract`-Draft (Copy-Semantik) `[AUTHZ]` |
| POST | `/api/contracts/{product}/diff` · GET `/diff/active` · `/version-diff` | Breaking-Report (liefert `kind`, `ceremony_required`, `blocking`) |
| GET | `/api/contracts/{product}/drift` | Shift-Left-Report: weicht die **Quelle** vom Schema-Versprechen ab (read-only; Persistenz + kind-aware Incident laufen beim Extrakt) |
| POST | `/api/contracts/{product}/backtest` | Garantie-Backtesting (V1): Entwurf (`contract`) oder Einzel-Expectations (`checks`) gegen die persistierte Messwert-Historie simulieren — „hätte N× in 30/90 d gefeuert", rein lesend |
| POST | `/api/contracts/{product}/approve` | Full-Modus: Draft → active (G3 nur `*_contract` + 1 Commit) `[AUTHZ]` |
| POST | `/api/contracts/{product}/certify` | **Lite-Modus: save → active → compile in einem Schritt** `[AUTHZ]` |
| POST | `/api/contracts/{product}/compile?dry_run=` | Garantien → Checks (persistiert nur `active`) |
| POST | `/api/contracts/{product}/deprecate` | active → deprecated |
| GET | `/api/contracts/{product}/sla` | SLA-%-Fenster (7/30/90 d); für `internal_gate` leer (`null`) |
| GET | `/api/contracts/{product}/observed` | Beobachtete Realität je Garantie: letzter Messwert, Sparkline-Reihe, PASS/FAIL (read-only-Rollup) |
| GET | `/api/contracts/{product}/export/odcs` · POST `/export/bdc` | ODCS-3.1 (nur `*_contract`, sonst 409) · CSN/ORD-Fragmente |
| POST | `/api/contracts/reindex` | Index-Rebuild nach externem `git pull` `[AUTHZ]` |

### Checks, Extrakt, Inventar

| Methode | Pfad | Zweck |
|---|---|---|
| POST | `/api/checks/{dataset}/dry-run` | Kompilieren + gegen HANA laufen, **nicht** persistiert `[AUTHZ]` |
| POST | `/api/checks/{dataset}/revert` | Git-Revert der kompilierten `checks.yml` `[AUTHZ]` |
| POST | `/api/extract` | Analyzer-Kette → inventory/lineage |
| GET | `/api/inventory` · `/api/environments` · `/api/library` | Objekt-Picker · Environments · Check-Bibliothek |
| POST | `/api/environments/{name}/test` | Live-Verbindungstest (Operation + SSE) `[AUTHZ steward+]` |
| GET/POST/PUT/DELETE | `/api/admin/environments[...]` | HANA-Verbindungen pflegen (Cockpit-Einstellungen) `[AUTHZ admin]` — nie Klartext-Passwort, nur `password_ref` |

### Lineage / Coverage / Incidents / Proposals / Observability

| Methode | Pfad | Zweck |
|---|---|---|
| GET | `/api/lineage/graph` · `/coverage/summary` · `/coverage/heatmap` · `/coverage/health` | Graph & Coverage-Aggregate; `summary` enthält `with_internal_gate`/`with_contract_checks`/`contracts_breached`/`gates_failing` |
| GET | `/api/incidents` · `/{id}` · POST `/{id}/transition` | Incidents (Filter `status/severity/kind`, paginiert) + Timeline; `kind` trennt Engineering-Signal von Contract-Breach |
| GET | `/api/proposals` · POST `/{id}/accept|reject|snooze` | Miner-Vorschläge (mit `kind`) |
| GET | `/api/activity` | Activity-/Audit-Feed (Approvals, Incident-Transitions, Läufe) |
| POST | `/api/objects/{id}/profile` | Profil-Lauf: Spaltenstatistik, PK-Kandidaten, optionale Sample Rows `[PII-GATE]` |
| GET | `/api/metrics/health` · `/api/datasphere/*` · `/api/data-loads` | Betriebs-/Lastmetadaten |
| GET | `/api/notifications/...` · POST/PATCH/DELETE `channels|rules|mutes` | Notification-Routing (Regeln optional kind-gefiltert via `match_kind`) |
| GET/POST | `/api/notifications/digest/preview` · `/send` | Qualitäts-Digest (V4): Kennzahlen-Rollup der Periode · manueller Versand an abonnierte Kanäle (`digest_enabled`, `steward+`); Automatik über den Scheduler-Tick (claim-basiert, Migration 018) |
| GET | `/api/badge/{product}` | einbettbares Status-Badge |

### Data Products, Quarantäne, Enforcement, Operations, Schedules

| Methode | Pfad | Zweck |
|---|---|---|
| GET | `/api/products` · `/api/products/{product}` | Data-Product-Aggregat (ADR-0004): Komposition, Boundary, Findings-Rollup |
| GET | `/api/quarantine` · `/{id}` | Quarantäne-Episoden (Filter Status), Detail + Event-Timeline |
| POST | `/api/quarantine/{id}/release` · `/confirm-reprocess` · `/reconcile` | Episoden-Übergänge (`steward+`, 409 bei unzulässigem Übergang); Freigabe zusätzlich 409 bei offenen Verstößen bzw. Vier-Augen-Verletzung, sobald an der Episode geheilt wurde |
| GET/POST | `/api/healing/overview` · `/episodes/{id}` · `/episodes/{id}/corrections` · `/recheck` | Healing H1 (`steward+`): Parkbucht-Korrektur mit Schattenspalte `_DQ_ORIGINAL`, Re-Check gegen das Bad-Prädikat |
| GET/POST | `/api/healing/patches` · `/patches/{id}/revoke` · `/plan` | Healing H3 (`owner+` für Schreiben): Patch-Overlay `DQ_PATCH_<OBJ>` + `V_DQ_HEALED_<OBJ>`, Rücknahme mit Audit; `plan` = DDL-Vorschau |
| GET | `/api/enforcement/plan` · POST `/apply` | Materialisierungs-Plan (DDL/DML-Vorschau) · Apply ins Signal-Schema (`owner/admin`, Operations-Audit, doppelt gegated §3.8) |
| GET | `/api/operations/{op_id}` · `/events` | Generischer Operation-/Progress-Kanal (ADR-0007): Poll + SSE |
| GET/PUT/DELETE | `/api/objects/{id}/schedule` · GET `/api/schedules` | Pro-Objekt-Scheduling `manual/internal/external` (ADR-0005) + Ops-Sicht (`steward+`) |
| GET/PUT | `/api/admin/connector` · POST `/login` | Datasphere-Connector-Konfiguration + OAuth-Login `[AUTHZ admin]` |
| GET | `/api/schema-drift` · `/{object}` | Schema-Evolution (A2/UX-N9): Rollup je Objekt (Snapshots × Drift × Contract) · Snapshot-Diffs über Zeit + Drift-Historie mit Incident-Referenz |

### Monitoring (Hub-Sharing, Hybrid)

„Für Monitoring vormerken" nach dem **Hybrid-Modell** (ADR-0002 §7): Signal hält nur den **Soll-Zustand**, ein externes, privilegiertes Skript reconciled Share + Projektions-View im Monitoring-Hub und meldet Status zurück. **Signal schreibt nie nach Datasphere.**

| Methode | Pfad | Zweck |
|---|---|---|
| GET | `/api/monitoring/config` | `enabled` + Hub-Space (steuert UI-Sichtbarkeit) |
| GET | `/api/monitoring/shares` | Status je vorgemerktem Objekt (`requested → provisioned \| error`) |
| GET | `/api/monitoring/manifest` | Soll-Zustand fürs Skript: Identität + View-Name (`<SPACE>__<OBJEKT>`) + Spalten + vorgeschlagenes Projektions-SQL (explizite Spaltenliste) |
| POST | `/api/monitoring/shares/{id}` | Objekt vormerken (nur Registry-Write, kein Datasphere-Zugriff) |
| PUT | `/api/monitoring/shares/{id}/status` | Skript-Callback: `provisioned` / `error` |
| DELETE | `/api/monitoring/shares/{id}` | aus Soll-Zustand entfernen → Skript droppt die verwaiste View beim Reconcile |

> Die vollständige, immer aktuelle Liste ist die generierte OpenAPI unter `/api/openapi.json`; das Frontend bezieht daraus seine Typen (`openapi-typescript`, Gate G4).

---

## 6 — Konfiguration (ENV)

Settings über `pydantic-settings` (`services/api/settings.py`). Auszug:

| Variable | Default | Zweck |
|---|---|---|
| `BIND_HOST` / `BIND_PORT` | `127.0.0.1` / `8000` | S5 fail-closed: `0.0.0.0` nur mit echtem Auth |
| `AUTH_MODE` | `noauth` | `noauth` \| `oidc` |
| `OIDC_ISSUER` / `OIDC_AUDIENCE` / `OIDC_JWKS_URL` | — | OIDC-Validierung |
| `OIDC_ROLE_CLAIM` / `OIDC_GROUPS_CLAIM` / `OIDC_ROLE_MAPPING` | `roles` / `groups` / `{}` | Claims → Rollen |
| `STORE_BACKEND` | `sqlite` | `sqlite` \| `hana` |
| `SQLITE_DB` | `signal.db` | lokaler Store-Pfad |
| `GIT_REMOTE` | `""` | Contract-Repo-Remote (leer = lokal, kein Push) |
| `CONTRACTS_DIR` / `CHECKS_DIR` | `contracts` / `checks` | Artefakt-Verzeichnisse |
| `DATA_DIR` / `INVENTORY_FILE` / `LINEAGE_FILE` | `data` / `data/inventory.json` / `data/lineage.json` | Extrakt-Snapshots |
| `ENVIRONMENTS_FILE` | `environments.yml` | `name → {host, port, schema, secret_ref}` |
| `ALLOW_LOCAL_DIAGNOSTICS` | `false` | PII-Gate: Rohzeilen lokal zulassen |
| `DIAGNOSTICS_TTL_DAYS` | `7` | Retention der Diagnostics |
| `ALLOW_PROFILE_SAMPLES` | `false` | PII-Gate für den Profiler: Sample Rows nur mit Flag |
| `PROFILE_SAMPLE_COLUMNS` | `[]` | Allowlist der im Profil zulässigen Sample-Spalten |
| `EXTRACT_STALE_DAYS` | `7` | Staleness-Schwelle für Extrakt-Alter |
| `ALLOW_MOCK_CONNECTION` | `true` | Läufe ohne Environment via MockConnection |
| `SCHEDULER_ENABLED` | `false` | Interner Schedule-Poller (ADR-0005, Option E) — opt-in |
| `SCHEDULER_TICK_SECONDS` | `30` | Poll-Kadenz des Pollers (nicht das Lauf-Intervall) |
| `CORS_ORIGINS` | localhost:5173/3000 | erlaubte Frontends |
| `WEBHOOK_URL` / `WEBHOOK_ALLOWLIST` | — | Breach-Webhook (SSRF-Allowlist) |
| `NOTIFICATIONS_FILE` | `notifications.yml` | YAML-Fallback für Kanäle/Regeln (DB schlägt YAML) |
| `DIGEST_ENABLED` | `false` | Qualitäts-Digest-Automatik (V4) — opt-in; Versand nur an Kanäle mit `digest_enabled` |
| `DIGEST_INTERVAL_HOURS` | `24` | Digest-Periode (1–168 h); Slot-Claim verhindert Doppel-Versand bei mehreren Workern |
| `DATASPHERE_*` / `DATASPHERE_USE_CLI` | — / `false` | Datasphere-API/CLI-Zugang (Lastmetadaten) |
| `DATASPHERE_MONITORING_SPACE` | `""` | Hub-Space für „Für Monitoring vormerken"; leer = Feature aus. Signal schreibt **nicht** in Datasphere — das Provisioning übernimmt ein externes Skript. |
| `MONITORING_SERVICE_TOKEN` | `""` | Token für den Skript-Callback (`PUT /api/monitoring/shares/{id}/status`) |
| `SECRETS_FILE` | `secrets.local.yml` | lokaler Secret-Store für `password_ref`/`secret_ref` |
| `PRODUCTS_DIR` | `products` | Data-Product-Definitionen (ADR-0004) |
| `CONNECTOR_FILE` | `datasphere.yml` | persistierte Connector-Konfiguration (`/api/admin/connector`) |
| `SEGMENT_VALUE_COLUMNS` | `[]` | Allowlist der Segment-Wertspalten (Obs-Intelligence, Migration 012) |
| `INCIDENT_CLUSTER_WINDOW_MINUTES` | `15` | Zeitfenster fürs Incident-Clustering (Notification-Dedupe) |
| `ENFORCEMENT_MATERIALIZE_ENABLED` | `false` | Kill-Switch der Verdict-Materialisierung (§3.8); nur zusammen mit `DATASPHERE_SIGNAL_SCHEMA` aktiv |
| `DATASPHERE_SIGNAL_SCHEMA` | `""` | Signal-eigenes Open-SQL-Schema für `V_DQ_GATE_STATUS`/`P_DQ_ASSERT_GATE` (zur Laufzeit gebunden, G2) |
| `ENFORCEMENT_VERDICT_TTL_SECONDS` | `0` | Verdict-Verfallszeit in der materialisierten Gate-Sicht (`0` = kein TTL) |

Environments-Datei bindet das `{schema}` zur Laufzeit — Contracts bleiben environment-frei.

---

## 7 — CLI

`cli/dq_check_runner.py` fährt die Engine ohne API (für Cron/Task-Chain-Scheduling):

```bash
python cli/dq_check_runner.py \
  --schema CORE_DWH \
  --checks checks/DS_SALES_ORDERS/checks.yml \
  --db dq_results.db \
  [--dry-run] [--mock] \
  [--host HOST --port 443 --user U --password P] \
  [--execution-mode auto|batch|isolated] \
  [--output text|json] [--no-enforce]
```

`--mock` läuft gegen die `MockConnection` (kein HANA). `--dry-run` persistiert nicht. Credentials kommen alternativ aus `HANA_USER`/`HANA_PASSWORD`. `--schema` bindet den `{schema}`-Platzhalter `[SCHEMA-MAP]`.

**Exit-Codes folgen dem `gate_verdict`** (§3.8): `0` = proceed, `1` = block, `3` = quarantine (bewusst nicht 2 — das bleibt der Usage-/Config-Fehler). `--no-enforce` schaltet das Verdict-Mapping ab (immer 0 bei erfolgreichem Lauf); Task-Chains/Cron nutzen den Exit-Code als Gate.

---

## 8 — Frontend (Cockpit)

Vite + React 18 + TS strict, TanStack Query v5, React Router, Tailwind (Design-Tokens). Routen:

| Route | Screen | Zweck |
|---|---|---|
| `/` | Cockpit | DQ-Health-Verlauf (Trend-Graph), Familien-Rollups (Observability/Quality), Brennpunkte, Status-Grid (Objekt × Familie), Reliability-Heatmap, SLA-Panel, Activity-Feed; stale sichtbar (G6) |
| `/my` | MyWork | Rollen-Landing; Incidents nach `kind` getrennt (Contract-Breach vs. Engineering-Signal) |
| `/objects`, `/objects/:id` | Katalog/Detail | Faceted Search; Checks, Sparkline, „Verlauf"-Tab (Zeitreihen), Profiling-Drawer, Run-Trigger, „Für Monitoring vormerken" |
| `/products`, `/products/:name` | Data Products | Produkt-Aggregat (ADR-0004): Komposition, Boundary, Findings |
| `/contracts` | Contract-Workbench | Garantie-Editor (Modus aus `kind`), Compile, Breaking-Diff, Promotion-Flow, Govern-Onboarding |
| `/lineage`, `/coverage` | Lineage-/Coverage-Map | Schematic-SVG-Lineage (Legacy-Cytoscape-Map als Fallback-Ansicht); Coverage-Status je Node, Dimension-Switcher (Internal\|Contract\|All), Gate = gestrichelt; `/coverage` ist Route-Alias derselben Ansicht |
| `/incidents` | Incidents | Incident-Inbox + Timeline; `kind`-Badge & -Filter (Engineering-Signal vs. Contract-Breach) |
| `/quarantine` | Quarantäne | Episoden-Inbox (Tabs nach Status), Drawer mit Event-Timeline, Freigabe-/Reprocess-Aktionen (§3.8) |
| `/healing` | Healing-Workbench | Manuelle Datenkorrektur (`Konzept_Manuelles_Healing` H1/H3): Parkbucht-Korrektur je Episode mit Re-Check-Zähler, Patch-Overlay mit Gültigkeit/Rücknahme; schreibt nur im Signal-Schema, Quelle bleibt read-only |
| `/proposals` | Proposals | Miner-Vorschläge (Inbox), kind-Badge |
| `/runs/:id`, `/runs/compare` | Run-Detail/-Vergleich | Live-Log (SSE) + Polling; Regressions-Diff zweier Runs; `gate_verdict`-Anzeige |
| `/schedules` | Schedules | Ops-Sicht der pro-Objekt-Zeitpläne (`manual/internal/external`, ADR-0005) |
| `/schema-drift` | Schema-Drift | Schema-Evolution je Objekt über Zeit (A2/UX-N9): Snapshot-Diffs (Spalten hinzu/entfernt/Typ), Contract-Brüche mit Incident-Deep-Link |
| `/compliance`, `/library`, `/notifications` | Verwaltung | ACLs/Compliance-Ampel (nur Contracts; `/governance` leitet hierher um), Check-Library-Browser, Routing (inkl. `match_kind`) |
| `/settings`, `/environments`, `/inventory-admin` | Administration | Einstellungen (inkl. Datasphere-Connector), HANA-Verbindungen + Test (Operation/SSE), Inventar-Pflege |

UI-Regeln: Status-Ampel (grün/gelb/rot/grau) ist **exklusiv**; Familienfarben nur für Dekor/Diagramme. Status-Encoding ≥3-von-4 (Farbe + Form/Glyph + Label, Carbon). Alle Strings zentral in `i18n/de.ts` (de-only). CSP gesetzt, ESLint mit `react/no-danger`; `dangerouslySetInnerHTML` verboten (S8).

---

## 9 — Sicherheit & Gates

| Gate | Prüfung | Mechanik |
|---|---|---|
| G1 | Kein SQL im Contract | jsonschema + Lint auf `contracts/*.yml` |
| G2 | Kein hartkodiertes Schema | `{schema}`-Platzhalter, Bind erst zur Laufzeit |
| G3 | Breaking ⇒ Major | `dq_core.contract.diff` server- **und** CI-seitig |
| G4 | Kein FE/BE-Typ-Drift | `openapi-typescript` + `git diff --exit-code` |
| G5 | Engine-Regress | bestehende pytest-Suite unverändert grün |
| G6 | Gating sichtbar | `skipped_stale` nie wie `pass` |
| G7 | Framework-Isolation | kein `import fastapi/flask/starlette` in `dq_core/` |
| G8 | PII-Gate | ohne `ALLOW_LOCAL_DIAGNOSTICS` keine Rohzeile; mit Flag nur Allowlist-Spalten |

**Weitere Leitplanken:** Auth fail-closed (S5); Autorisierung serverseitig autoritativ, Schreibrecht = `Rolle × owned_by × owners` (S3); Identifier-Validierung im Compiler (Regex → Inventar-Existenz → Quote-Escaping, S2); Webhook-SSRF-Allowlist (S6); Interna nie in HTTP-Responses (S-14, RFC-7807). HANA wird ausschließlich lesend angesprochen.

**Rollen:** `viewer | steward | owner | admin`. Schreibrecht: admin alles; steward/owner platform-owned; owner zusätzlich product-owned; `owners`-ACL (`sub`/`grp:`) ergänzend, fail-closed.

---

## 10 — Deployment

| Profil | Berater-lokal | Kunde |
|---|---|---|
| Store | SQLite | HANA (`dq_results_lt`) |
| Auth | NoAuth (Admin-Principal) | OIDC |
| Bind | `127.0.0.1` | `0.0.0.0` (nur mit Auth) |
| Worker | 1 (uvicorn --reload) | ≥2 (Run-Registry im Store schützt vor Doppellauf) |
| Scheduling | manuell/Cron · optional interner Poller | Cron/Task-Chain → CLI · optional interner Poller |

Beide Profile laufen aus **demselben Code** über die Auth-/Store-Abstraktion — kein Code-Zweig. Die API triggert Läufe ad hoc; regelmäßige Läufe plant entweder ein **externer** Scheduler über die CLI **oder** — opt-in via `SCHEDULER_ENABLED` — Signals **interner Poller** (ADR-0005, Option E). Multi-Worker-Korrektheit (gemeinsamer Run-Status) ist mit ≥2 uvicorn-Workern verifiziert (F2); der Poller stützt sich auf denselben Guard, sodass je Worker ein eigener Poller laufen darf, ohne Doppelläufe zu erzeugen.

**Scheduling als pro-Objekt-Schalter (ADR-0005):** Jedes Objekt ist `manual` (kein Eintrag), `internal` (Poller fährt die Kadenz `interval_seconds`) oder `external` (Task-Chain/Cron→CLI fährt sie; der Poller rührt es nie an). Verwaltung über `PUT/GET/DELETE /api/objects/{id}/schedule` und die Ops-Sicht `GET /api/schedules` (steward+). Konfiguration liegt in der Store-Tabelle `dq_schedules`, **nicht** im Contract (operativ, nicht semantisch — G1). Tick-Kadenz des Pollers: `SCHEDULER_TICK_SECONDS` (Default 30 s).

---

## 11 — Entwicklung & Tests

```bash
make install        # Backend (pip) + Frontend (npm)
make dev-backend    # uvicorn services.api.main:app --reload
make dev-frontend   # vite
make test           # python -m pytest tests/ -v
make seed           # Demo-Läufe in den Store
make lint           # py_compile + tsc --noEmit
```

**Teststrategie:** `dq_core` pytest (Engine + contract/compiler/diff/baselines, inkl. Compiler-Determinismus per Hash) · API mit FastAPI-`TestClient` gegen SQLite (Fixture `api_client`, isolierter Temp-Store je Test) · Frontend Vitest + Testing Library · Gates G1–G8 in CI (`.github/workflows/ci.yml`).

**Goldene Regeln:** `dq_core` bleibt frameworkfrei (G7); Engine-Dataclasses API-frei, Pydantic-Schemas in `services/api`; kein Merge mit roten Acceptance-Tests; jede Schema-Änderung über eine nummerierte Migration.

---

## 12 — Glossar

| Begriff | Bedeutung |
|---|---|
| **Contract** | SQL-freies YAML mit Garantien über ein Datasphere-Objekt |
| **`kind`** | Klassifikation des Sets: `internal_gate` (Quality Gate) · `consumer_contract`/`provider_contract` (Versprechen an einer Parteigrenze) |
| **Quality Gate** | interner Check ohne Gegenpartei (`internal_gate`); Fehler = Engineering-Signal, keine Governance-Ampel |
| **Engineering-Signal** | Team-internes Incident aus einem fehlgeschlagenen `internal_gate` (kein Compliance-/SLA-Effekt) |
| **Promotion** | Governance-Akt `internal_gate → consumer_contract` (Copy-Semantik, neues Artefakt) |
| **Garantie** | semantische Zusage (Familie: schema/keys/referential/not_null/completeness/freshness/volume) |
| **Compiler** | übersetzt Garantien deterministisch in `CheckDef`s (`{schema}`-Platzhalter) |
| **Check** | ausführbarer SQL-Ausdruck + Expectation, gegen HANA gefahren |
| **Lifecycle** | `draft \| active \| deprecated` — Erstellungszustand |
| **Compliance** | `compliant \| breached \| unknown` — ob die aktive Zusage gehalten wird (nur Store) |
| **Coverage** | `covered \| partial \| gap \| out_of_scope` — Abdeckungsgrad eines Objekts |
| **Lite / Full** | Betriebsmodi: ohne / mit Versions-Approval-Zeremonie |
| **Enforcement** | `gate \| quarantine \| monitor` — welche Konsequenz ein Breach hat (Default `monitor`) |
| **Gate-Verdict** | `proceed \| quarantine \| block` — state-bewusster Rollup je Lauf; konsumiert via CLI-Exit-Code, `/api/runs/{id}/status` oder materialisierte Gate-Sicht |
| **Quarantäne-Episode** | persistenter Quarantäne-Zustand je Produkt (`open → reconciled → released → resolved`, `+ superseded`) |
| **Run / RunSummary** | ein Ausführungslauf einer Check-Suite + dessen Ergebnis |
| **Proposal** | datengetriebener Garantie-Vorschlag aus dem Miner |
| **Incident** | persistente Breach-Episode mit Timeline |
| **Result-Store** | Persistenz für Läufe/Ergebnisse/Compliance (SQLite/HANA) |
| **Gate (G1–G8)** | erzwungene Invariante in CI + Server |

---

*Diese Referenz beschreibt den implementierten Stand. Bei Konflikt mit Planungsdokumenten (`HANDOVER.md`, `PLAN_*`) gewinnt der Code; melde Abweichungen als Issue.*
