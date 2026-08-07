# HANDOVER — Data Quality & Observability Cockpit · Technischer Implementierungsplan

**Adressat:** Coding-Agent · **Modus:** sequentiell, ein Workstream nach dem anderen, Acceptance je Schritt grün halten.
**Stand:** 2026-06-09 · gegründet auf bestehende Engine-Module + Review v0.1 (alle Deltas D1–D14 eingearbeitet).

> **Status (2026-07-23): historisch — Workstreams sind umgesetzt.** Der
> implementierte Stand steht in [`Tooldokumentation.md`](Tooldokumentation.md);
> die verbliebenen Spikes/Entscheidungen (O1–O7, §5) werden in
> [`OPEN_TASKS.md`](OPEN_TASKS.md) **K** geführt. Bei Widerspruch gewinnt der
> Code bzw. die Tooldokumentation.

> **Lies zuerst:** [`REVIEW_Implementierungsplan.md`](REVIEW_Implementierungsplan.md) (Befunde F/A/U/S, Delta-Liste; der dort reviewte ursprüngliche Implementierungsplan ist nicht mehr im Repo). Dieses Dokument ist die ausführbare Synthese. Bei Widerspruch gewinnt dieses Dokument.

## Boundary-Tags (im Code als Kommentar setzen, wo markiert)

- `[ENGINE-FROZEN]` — bestehende `dq_core/engine`-Logik nicht verändern, nur erweitern. Regressionsgate G5.
- `[SCHEMA-MAP]` — Stelle, an der ein `{schema}`-Platzhalter zur Laufzeit gebunden wird. Nie hartkodieren (G2).
- `[CONTRACT-SQL-FREE]` — Pfad, der Contract-Input verarbeitet; hier darf nie SQL durchgereicht werden (G1).
- `[PII-GATE]` — Pfad, der Rohzeilen berühren könnte (Diagnostics). Default off, Allowlist erzwingen (S1).
- `[AUTHZ]` — Autorisierungsentscheidung. Server ist autoritativ, FE spiegelt nur.
- `[DETERMINISM]` — Compiler-Output muss bei gleichem Input byte-identisch sein.

## Goldene Regeln

1. `dq_core` importiert **nie** FastAPI/Flask/Starlette. Lint-Gate G7 erzwingt das.
1. Engine-Dataclasses (`models.py`) bleiben API-frei. Pydantic-Schemas leben in `services/api`.
1. Kein Schritt wird gemerged, dessen Acceptance-Tests rot sind. Gates existieren vor dem ersten Feature.
1. Jede neue Tabelle/Spalte über eine nummerierte Migration, nie per Hand am Schema.

-----

## 0 — Gesetzte Architektur (nicht neu verhandeln)

```
repo/
├─ packages/dq_core/              # frameworkfrei, pip-installierbar (pyproject)
│  ├─ engine/   check_engine.py expectation.py models.py        [ENGINE-FROZEN]
│  ├─ store/    base.py(Protocol) sqlite_store.py hana_store.py migrations/
│  ├─ connect/  db_connection.py                                # hdbcli + Retry
│  ├─ library/  check_library.py check_library.json
│  ├─ contract/ model.py validator.py compiler.py diff.py seed.py   # NEU
│  ├─ lineage/  analyzer_loader.py _column_lineage.py _csn_reconstructor.py _sql_column_parser.py
│  └─ obs/      baselines.py miner.py                           # NEU
├─ services/api/                  # FastAPI (uvicorn)
│  ├─ main.py settings.py deps.py auth/ routers/ schemas/ sse.py git_repo.py
├─ apps/cockpit/                  # Vite + React 18 + TS strict
├─ cli/        dq_check_runner.py                               # importiert dq_core
└─ .github/ (oder .gitlab-ci.yml)                               # Gates G1–G8
```

Persistenz, drei getrennte Orte: **Git** (Contracts + kompilierte `checks/*.yml`) · **Result-Store** (SQLite lokal / `dq_results_lt` in HANA) · **HANA** (geprüfte Daten, nur lesend).
Identitäts-Join mapping-frei: `lineage node.id == inventory.technicalName == dq_object_status.object_name`.

Backend = neues FastAPI-Service (B1). Deployment-Doppelziel über Auth-/Store-Abstraktion, keine Code-Zweige (B2).

-----

## 1 — Datenmodell (Quelle der Wahrheit für alle Schritte)

### 1.1 Engine-Dataclasses — bestehend, eingefroren

`CheckDef(name, sql, expect, severity, description, timeout_s, enabled, type, unit)`
`DatasetConfig(dataset, schema, contract_version, checks[])`
`CheckResult(name, sql, expect, severity, passed, actual_value, error, duration_ms, diagnostic_rows[])`
`RunSummary(run_id, dataset, schema, started_at, finished_at, overall_status, total, passed, failed, warnings, results[], triggered_by)`
`VALID_SEVERITIES = {critical, fail, warn}` · Status-Vokabular der Engine: `pass|warn|fail|critical|error`.

### 1.2 Expectation-Grammatik — bestehend, eingefroren

Unterstützt: `IS NULL` · `IS NOT NULL` · `= n` `!= n` `>= <= > < n` · `BETWEEN a AND b` · `= n ±t` · `IN(...)`/`NOT IN(...)` · `DELTA <op> p%` (nutzt `previous_value`) · `MATCHES /regex/`.
**Konsequenz für den Compiler:** jede Garantie muss auf genau einen dieser Ausdrücke abbilden. Keine neuen Operatoren ohne Erweiterung von `expectation.py` **inkl. `validate_expectation`** + Tests.

### 1.3 Result-Store-Schema v1 — bestehend

Tabellen `dq_runs`, `dq_check_results`, `dq_diagnostics` (Auszug der relevanten Spalten):

- `dq_runs(run_id PK, dataset, schema_name, started_at, finished_at, overall_status, total_checks, passed_checks, failed_checks, warning_checks, triggered_by)`
- `dq_check_results(id PK, run_id FK, check_name, sql_text, expect_expr, severity, passed, actual_value, error_message, duration_ms)`
- `dq_diagnostics(id PK, run_id, check_name, row_data)` — **PII-Kanal, siehe WS0-S6.**
  Bestehende Reader: `get_previous_actuals`, `get_diagnostics`, `get_latest_run`, `get_history`, `get_run_detail`.

### 1.4 Migration v2 — NEU (WS0)

Migration `002_state_stats_lineage_compliance.sql`, idempotent (`ADD COLUMN` mit Existenzprüfung; SQLite + HANA-Dialektvariante):

```
-- dq_check_results: Gating-Zustand (E5/G6) — NIE stilles Auslassen
ALTER TABLE dq_check_results ADD COLUMN state TEXT NOT NULL DEFAULT 'executed';
   -- erlaubt: executed | skipped_stale | skipped_dependency | downgraded | error

-- dq_runs: Run ↔ Contract-Version verknüpfen (F3/S7)
ALTER TABLE dq_runs ADD COLUMN contract_version TEXT DEFAULT '';
ALTER TABLE dq_runs ADD COLUMN contract_hash    TEXT DEFAULT '';
ALTER TABLE dq_runs ADD COLUMN actor            TEXT DEFAULT '';
ALTER TABLE dq_runs ADD COLUMN run_state        TEXT NOT NULL DEFAULT 'finished';
   -- erlaubt: running | finished | error  (F2: Run-Zustand persistent, nicht in-memory)

-- NEU: Stats-Tuple je Check (E6 — nur Skalare verlassen HANA)
CREATE TABLE IF NOT EXISTS dq_check_stats (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL, check_name TEXT NOT NULL,
  n INTEGER, min_v REAL, max_v REAL, p01 REAL, p99 REAL, mean_v REAL, stddev_v REAL
);

-- NEU: Obs-Baselines (7.1)
CREATE TABLE IF NOT EXISTS dq_baselines (
  dataset TEXT NOT NULL, metric TEXT NOT NULL,
  n INTEGER, mean_v REAL, stddev_v REAL, p01 REAL, p99 REAL, mad REAL,
  updated_at TEXT, warmup_remaining INTEGER DEFAULT 0,
  PRIMARY KEY (dataset, metric)
);

-- NEU: Proposals (7.2)
CREATE TABLE IF NOT EXISTS dq_proposals (
  id TEXT PRIMARY KEY, product TEXT NOT NULL, guarantee_patch TEXT NOT NULL,
  evidence TEXT, status TEXT NOT NULL DEFAULT 'open', created_at TEXT
);

-- NEU: Compliance-Zustand getrennt vom Git-lifecycle (A1)
CREATE TABLE IF NOT EXISTS dq_compliance (
  product TEXT PRIMARY KEY, contract_version TEXT,
  compliance TEXT NOT NULL DEFAULT 'unknown',  -- compliant | breached | unknown
  since TEXT, last_run_id TEXT
);

-- Read-Index für Contract-Liste (A3) — Git ist keine Query-DB
CREATE TABLE IF NOT EXISTS contract_index (
  product TEXT PRIMARY KEY, lifecycle TEXT, owned_by TEXT, version TEXT,
  head_hash TEXT, updated_at TEXT
);
```

Rollup `dq_object_status` = Store-Query/View (kein Sync-Job), liefert je Objekt × Familie den jüngsten `state`+Status und joint `dq_compliance`.

### 1.5 Contract-YAML-Schema v1 — NEU

**SQL-frei (G1).** `lifecycle` und `compliance` getrennt (A1): nur `lifecycle` steht im YAML, `compliance` kommt aus dem Store.

```yaml
product: sales_orders
dataset: Sales_Orders_View
owned_by: platform            # platform | product_owner
owners: ["grp:data-platform"] # Governance-ACL (S3)
version: 1.0.0                # SemVer
lifecycle: draft              # draft | active | deprecated   (KEIN breached hier!)
guarantees:
  schema:       { columns: [OrderID, ItemNo, Amount, LOAD_TS], mode: closed }
  keys:         [{ columns: [OrderID, ItemNo], unique: true, severity: critical }]
  referential:  [{ fk: [CustomerID], parent: Customers_View, parent_key: [CustomerID], severity: fail }]
  freshness:    { column: LOAD_TS, max_age: PT24H, severity: warn }
  volume:       { baseline: rolling, bounds: auto, severity: warn }
  completeness: [{ column: Amount, min_pct: 99.5, severity: warn }]
```

**Kein** `schema_ref` (A2): Schema wird zur Laufzeit gebunden, nicht im Contract. Datei-Heimat: `contracts/<product>.yml` im Git.

-----

## 2 — Workstreams (sequentiell)

Reihenfolge ist Default. Querschnitte (7.x) starten frühestens nach WS2. Jeder Schritt: Implementieren → Acceptance-Tests grün → mergen.

-----

### WS0 — Fundament (Voraussetzung für alles)

**WS0-1 `dq_core`-Extraktion** `[ENGINE-FROZEN]`
Module unverändert nach `packages/dq_core/{engine,store,connect,library,lineage}` verschieben. Importe auf Paketpfade; `__init__`-Re-Exports für Rückwärtskompatibilität. `pyproject.toml` mit Extras: `core` (yaml), `hana` (hdbcli), `lineage` (sqlglot, optional). CLI `dq_check_runner.py` auf `from dq_core...` umstellen.
*Acceptance:* bestehende pytest-Suite **unverändert grün** (G5). `import dq_core` ohne FastAPI im Environment.

**WS0-2 Lint-Gate G7 (Framework-Isolation)**
CI-Schritt: `grep -rE "import (fastapi|flask|starlette)" packages/dq_core/ && exit 1 || exit 0`.

**WS0-3 Store-Abstraktion + Migration-Runner**
`store/base.py`: `ResultStoreProtocol` aus der bestehenden `ResultStore`-Public-API ableiten (`save_run`, `get_*`). `sqlite_store.py` = bestehende Klasse, an Protocol angepasst. `hana_store.py` = NEU, gleiches Protocol, Ziel `dq_results_lt` (JDBC-Insert via hdbcli). Migration-Runner liest `store/migrations/NNN_*.sql`, führt fehlende aus, trackt in `schema_migrations`. **Migration 002 (§1.4) hier ausführen.**
*Acceptance:* gegen frische SQLite migriert v1→v2 idempotent (zweiter Lauf = no-op). `get_run_detail` liefert neue Felder mit Defaults.

**WS0-4 FastAPI-Skeleton + Settings**
`settings.py` (pydantic-settings, ENV): `AUTH_MODE`, `STORE_BACKEND`, `GIT_REMOTE`, `ENVIRONMENTS_FILE`, `BIND_HOST`. `main.py`, `deps.py` (`get_store`, `get_principal`, `get_environment`). Fehlerformat RFC-7807 `application/problem+json`.
`schemas/` = Pydantic-v2 mit `from_attributes=True`, spiegelt Dataclasses. **Drift-Test** (A6): Snapshot vergleicht Dataclass-Felder ↔ Schema-Felder.

**WS0-5 Auth-Abstraktion** `[AUTHZ]`
`Principal {sub, name, roles[]}`, Rollen `viewer|steward|owner|admin`. `auth/noauth.py` (fixer Admin-Principal) · `auth/oidc.py` (JWT-Validierung, Claims→Rollen-Mapping aus ENV). Provider-Auswahl per `AUTH_MODE`.
**S5 fail-closed:** Default `BIND_HOST=127.0.0.1`. Bind auf `0.0.0.0` nur wenn `AUTH_MODE` explizit ≠ `noauth` gesetzt — sonst Startabbruch mit klarer Meldung.
Zentrale Autz-Funktion `can_write_contract(principal, contract) -> bool = f(roles, owned_by, owners)` (S3).

**WS0-6 Diagnostics-PII-Gate** `[PII-GATE]` (S1)
Default **off**. Aktivierung nur je Check mit Spalten-Allowlist (neues optionales Feld `diagnostics: {enabled, columns[]}` am Check). Retention-TTL (ENV `DIAGNOSTICS_TTL_DAYS`, Cleanup beim Store-Open). Lokal-Modus: zusätzlich ENV-Flag `ALLOW_LOCAL_DIAGNOSTICS=true` nötig, sonst werden `diagnostic_rows` verworfen bevor sie den Store erreichen.
*Acceptance:* ohne Flag landet **keine** Zeile in `dq_diagnostics`; Test mit gesetztem Flag + Allowlist persistiert nur erlaubte Spalten.

**WS0-7 Environments-Konfiguration** (F6/A2) `[SCHEMA-MAP]`
`ENVIRONMENTS_FILE` (YAML): `name → {host, port, schema, secret_ref}`. `get_environment(name)` in deps. Contracts bleiben environment-frei; der Run bekommt `environment` als Parameter, daraus die Schema-Bindung.

**WS0-8 React-Foundation**
Vite + React 18 + TS strict. TanStack Query v5, React Router, Tailwind mit Token-Datei aus dem Design-System (dark, DM Sans, JetBrains Mono). **Token-Regel U1:** semantische Familienfarben (Orange Obs / Grün Quality / Teal Flow / Blau Contract / Violett Feedback / Pink HITL) NUR für Diagramme/Dekor; **Status-Ampel (grün/gelb/rot/grau) exklusiv** — Familien im Grid über Icon+Label+Spaltenposition, nie über Farbe. `openapi-typescript`-Pipeline + fetch-Wrapper. CSP gesetzt, `dangerouslySetInnerHTML` per Lint verboten (S8). Alle Strings zentral in einem `i18n/de.ts`-Modul (U5).

**WS0-9 CI-Gates G1–G8 anlegen** (Definition §4) — bevor das erste Feature merged.

*Acceptance WS0 gesamt:* API liefert Runs/Results aus SQLite; React-Shell läuft mit NoAuth (127.0.0.1) und zeigt leere Statusliste; OpenAPI-Typen-Pipeline grün; alle Gates aktiv.

-----

### WS1 — Cockpit-Dashboard (M1)

**WS1-1 Run-Registry im Store** (F2/A5)
Run-Start schreibt `dq_runs` mit `run_state='running'`; Worker-Thread aktualisiert Progress (eigene `dq_run_progress(run_id, ts, line)`-Tabelle oder Append in `dq_runs`). Store-seitiges „läuft bereits”-Flag verhindert Doppellauf API↔CLI auf demselben Dataset+Environment.

**WS1-2 Endpunkte**

```
GET  /api/objects                          # Rollup je Objekt: Obs/Quality-Status, letzter Run, Trend
GET  /api/objects/{name}                    # Detail: Checks des letzten Runs inkl. state
GET  /api/objects/{name}/checks/{c}/history # actual_value-Zeitreihe (Sparkline + Miner-Quelle)
GET  /api/runs  ·  GET /api/runs/{id}  ·  /results  ·  /diagnostics
POST /api/runs {dataset, environment, execution_mode} -> 202 {run_id}
GET  /api/runs/{id}/events                  # SSE; Adapter um on_progress
GET  /api/runs/{id}                          # Polling-Fallback (run_state + Progress)
GET  /api/library                            # check_library.json
POST /api/extract {environment}              # Analyzer-Kette -> inventory/lineage (F5)
```

SSE-Adapter umhüllt den vorhandenen `on_progress`-Callback; **Polling ist gleichwertiger Pfad** (Proxy/Mobile, A5).

**WS1-3 Frontend** Routen `/`, `/objects/:name`, `/runs/:id`.

- **StatusGrid** (Objekt × Familie; `skipped_stale` darf NIE wie `pass` aussehen — eigenes neutrales Badge mit Tooltip, G6 sichtbar). Filter Space/Layer/Severity/Familie URL-synchron.
- **RunTriggerDialog** (Dataset + Environment + Modus) · **LiveRunPanel** (SSE, Fallback Polling) · **CheckTable** · **ActualValueSparkline** (Recharts) · **DiagnosticsDrawer** (nur wenn aktiviert).
- **Onboarding-Flow** (U4): leerer Tenant → 1 Extrakt → 2 Seed → 3 Dry-Run → 4 erstes Ergebnis.
- **Extrakt-Alter** prominent + Staleness-Warnung (F5).
- Responsive (U3): Dashboard/Detail mobil; Detail-Editoren später Desktop.

*Acceptance WS1 / M1:* Steward sieht je Objekt beide Familien-Status; stale-skipped sichtbar unterscheidbar; Run aus UI startbar mit Live-Log **und** Polling; Zeitreihe je Check abrufbar; Multi-Worker-Deployment zeigt denselben Run-Status (F2 verifiziert mit ≥2 uvicorn-Workern).

-----

### WS2 — Contract-Workbench

**WS2-1 Contract-Modell + Validator** `[CONTRACT-SQL-FREE]` `dq_core/contract/{model.py,validator.py}`
jsonschema für §1.5 + Lint: Reject bei `sql:`-Key irgendwo, bei `SELECT`/Quote-Mustern in String-Werten. **Das ist G1 als Code.**
*Acceptance:* Contract mit eingeschmuggeltem SQL wird abgelehnt (Test).

**WS2-2 Seed** `dq_core/contract/seed.py`
Draft aus `inventory.json`-Snapshot: Schema-Spalten, deklarierte Keys, Measures → Garantien. `Sales_Orders_View` hat **keinen** deklarierten Key → Seed muss `keys: [{columns:[OrderID,ItemNo], unique:true, severity:critical}]` als Pflichtvorschlag erzeugen (erster Pflichtfall).

**WS2-3 Git-Schreibmodell** (F1) `services/api/git_repo.py`
Remote-Repo = Wahrheit (`GIT_REMOTE`). **Writer serialisiert** (ein Prozess-Lock / Commit-Queue). Jeder Commit: Author = Principal, standardisierte Message, genau **ein Commit je Approve**. **Breaking-Prüfung läuft serverseitig blockierend vor jedem Commit** (derselbe `dq_core.contract.diff`-Code wie das CI-Gate G3). Push-Reject → 409 + Rebase-Hinweis. Nach Commit `contract_index` aktualisieren (A3).

**WS2-4 Diff-Engine Stufe 1** `dq_core/contract/diff.py` (homegrown, ~150 LOC, O1)
Erkennt: removed column · type narrowing · key change · verschärfte Constraint → klassifiziert als breaking ⇒ Major-Pflicht. ODCS/`datacontract-cli` (Stufe 2) bewusst zurückgestellt bis R3/R9 geklärt.

**WS2-5 Compliance-Transition** (A1/F4) `dq_core/store`
Regel v1: `breached` bei ≥1 nicht bestandenem Check mit Severity ≥ `fail` der aktiven Version; Auto-Recovery bei vollständig grünem Folgelauf. Übergänge als Events in `dq_compliance` schreiben (since/last_run_id). **`compliance` lebt nur im Store, nie im YAML.**

**WS2-6 Endpunkte**

```
GET  /api/contracts                  # aus contract_index (A3), Filter lifecycle/owned_by/Suche
GET/PUT /api/contracts/{product}     # PUT nur bei lifecycle=draft  [AUTHZ]
POST /api/contracts/{product}/seed
POST /api/contracts/{product}/diff   # gegen aktive Version -> Breaking-Report
POST /api/contracts/{product}/approve   # [AUTHZ] role×owners; -> active, 1 Commit, Compile-Dry-Run
POST /api/contracts/{product}/deprecate
GET  /api/inventory                  # Objekt-/Spalten-Picker (U2/S2)
GET  /api/proposals?status=open  ·  POST /api/proposals/{id}/accept|reject  # Inbox-UI hier, Daten ab 7.2
```

**WS2-7 Frontend** Routen `/contracts`, `/contracts/:product`.

- **ContractEditor**: Formular je Garantie-Familie; **Inventar-Picker** mit Autocomplete gegen `GET /api/inventory` (U2) für referential/keys/columns — kein Freitext. YAML-Vorschau read-only (CodeMirror).
- **Lite-Modus** (N1/D8): Contract als geführte Checkliste (Garantien an/aus + Severity), ohne Version/Approval-Pflicht; Voll-Modus zuschaltbar. Gleicher Unterbau.
- **BreakingDiffPanel** · **ApprovalBar** (sichtbare Statusmaschine, warn→block-Promotion je Garantie als Schalter) · **ProposalInbox** (Evidenz n/p01/p99/mean).

*Acceptance WS2:* Draft aus inventory seedbar; `Sales_Orders_View` erhält den Key-Pflichtfall; Breaking-Diff blockiert Approve bei Major ohne Versionssprung (server- UND CI-seitig); jede aktive Version = genau ein Commit mit Principal als Author; SQL-im-Contract wird abgewiesen.

-----

### WS3 — Check Builder / Compiler (M2)

**WS3-1 Compiler** `[DETERMINISM]` `[SCHEMA-MAP]` `dq_core/contract/compiler.py`
Garantie → `check_library`-Template (`sql_template`+`params`) → `CheckDef`. Schema bleibt als `{schema}`-Platzhalter im Output (A2) — **nie `CENTRAL` hartkodieren (G2)**. Identifier-Validator (S2): Regex `^[A-Za-z_][A-Za-z0-9_]*$` + Existenzprüfung gegen Inventar-Snapshot + Quote-Escaping. `severity`/`enabled` aus Contract; `type` trägt Garantie-Typ (Rückverfolgbarkeit Check↔Garantie bis ins Dashboard).
**Determinismus:** Header-Hash = f(Contract-Hash, **Library-Version** aus `check_library.json:"version"` — A4). Gleicher Input ⇒ byte-identische `checks.yml`.
**Merge** mit handgepflegten Suiten: **existing-wins**, Konflikte als Report, nie stilles Überschreiben.

**WS3-2 Endpunkte**

```
POST /api/contracts/{product}/compile?dry_run=true  -> {checks_yaml, diff_to_current, conflicts}
POST /api/contracts/{product}/compile               # Commit checks/<dataset>.yml; nur aus lifecycle=active
POST /api/checks/{dataset}/dry-run {environment}     # batch-Lauf gegen HANA, NICHT persistiert
POST /api/checks/{dataset}/revert                    # Git-Revert auf Vorversion (F7)
```

**WS3-3 Frontend** Route `/contracts/:product/compile`.
**CompilePreview** (Garantie-Herkunft je Zeile) · **YamlDiffView** (CodeMirror-Merge) · **ConflictList** (existing-wins markiert) · **DryRunPanel** (Live wie WS1) · **Revert-Aktion** (F7).

*Acceptance WS3 / M2:* G1/G2-Tests schlagen bei Verstoß fehl; Determinismus-Test (zweimal kompilieren = identische Bytes, inkl. Library-Version im Hash); Roundtrip Contract→Compile→Run→Status ohne Handarbeit; handgepflegte Suite überlebt Merge unverändert; Revert stellt Vorversion her.

-----

### WS4 — Lineage Coverage Map

**WS4-1 Daten** `GET /api/lineage/graph` — Nodes/Edges aus `lineage.json` (`analyzer_loader`), Layer (Landing/Harmonization/Product) + Coverage je Node: aktiver Contract? kompilierte Checks? Familien? ⇒ `✓`/`◐`/`⚠`/`○`.
**Stufe 1 = Objektebene.** Spaltenebene erst nach `columnEdges`-Fix (O3: 690 Kanten `direct`/leer). Objektebene davon unabhängig.

**WS4-2 Frontend** Route `/coverage`. Cytoscape.js + dagre (LR), Node-Styling nach Coverage-Status, Familie als Badge-Ring (nicht Fill — U1). Klick → SidePanel (Check-Scope, letzter Status, „Contract öffnen”/„Compile”). Filter Layer/Status, Suche `technicalName`. Performance: Positions-Cache (sessionStorage) ab ~300 Nodes, Labels ab Zoomstufe. Cytoscape-Labels per Text-Sanitizing (S8). Desktop-only mit Hinweis (U3).

*Acceptance WS4:* `Sales_Orders_View` erscheint vor dem WS2-Key-Pflichtfall als `⚠`, danach als `✓`; jede `⚠`-Node hat klickbaren Pfad in die Workbench; Map zeigt Extrakt-Alter (F5).

-----

### WS5 — Querschnitte (ab WS2 parallelisierbar)

**WS5-1 Observability-Familie** `dq_core/obs/baselines.py` (7.1)
Obs-Config ist **Teil des Contracts** (Freshness/Volume-Garantien), kein zweites Artefakt (E1/E3). `dq_baselines`: Warm-up über N Läufe, robuste Statistik (Perzentile/MAD), Rolling Bounds. **Spike zuerst (O2):** Zugriffspfad auf Katalog-/Lastmetadaten klären (DWC_GLOBAL nicht öffentlich dokumentiert, HDLF-CLI-Gap); Fallback `LOAD_TS`-Spalten + Row-Count-Snapshots. Scheduling extern (Cron/Task-Chain→CLI); API triggert nur ad hoc.

**WS5-2 Proposal-Miner** `dq_core/obs/miner.py` (7.2)
Batch über `actual_value`-Zeitreihen + `dq_check_stats`. Kandidaten: stabile Wertebereiche, stabile NULL-Quoten, garantielose Spalten mit auffälliger Verteilung. Output → `dq_proposals`. **Kein Auto-Apply** — Accept (WS2-6) erzeugt Draft-Amendment über den normalen Approve-Weg.
*Voraussetzung:* Stats-Tuple-Erhebung — Entscheidung O7 (separater Profil-Lauf je Dataset, ein Statement). Default-Spalten-Set, **kein** PII-Roh-Read (E6).

**WS5-3 Webhook** (7.3) bei Übergang → `breached`. **SSRF-Schutz (S6):** URL-Allowlist (Host-Pattern), kein Redirect-Follow, Timeout, interne IP-Ranges blocken.

**WS5-4 CSN/ORD-Minimal-Export** (B2/D11) — hebt BDC-Story von „vorgesehen” auf „zeigbar”.
`POST /api/contracts/{product}/export/bdc` → erzeugt **Artefakt-Dateien** (CSN-Custom-Namespace-Annotations für Feld-Garantien + ORD-Custom-Label-Fragment für Produkt-Garantien), manuell deploybar. **Einseitig** (E1), nie zurückgelesen. Greift R1/R2 nicht vor — nur Datei-Generierung, kein Catalog-Write.

-----

## 3 — Sequenzierung, Abhängigkeiten, Aufwand

|WS   |Inhalt                                                                                  |hängt ab von                     |Aufwand brutto (PT)|Meilenstein|
|-----|----------------------------------------------------------------------------------------|---------------------------------|-------------------|-----------|
|WS0  |Fundament (dq_core, Store v2, FastAPI, Auth, PII-Gate, Environments, React-Shell, Gates)|—                                |8–12               |—          |
|WS1  |Cockpit-Dashboard                                                                       |WS0                              |10–14              |**M1**     |
|WS2  |Contract-Workbench (+ Lite-Modus, Git-Modell, Diff, Compliance)                         |WS0                              |13–18              |—          |
|WS3  |Check Builder / Compiler                                                                |WS2                              |7–11               |**M2**     |
|WS4  |Coverage Map                                                                            |WS1 (Status), WS3 (Coverage-Join)|6–9                |—          |
|WS5-1|Observability-Familie                                                                   |WS2 + O2-Spike                   |6–9                |—          |
|WS5-2|Proposal-Miner                                                                          |WS0 (Stats), WS2 (Inbox)         |4–6                |—          |
|WS5-3|Webhook                                                                                 |WS1                              |1–2                |—          |
|WS5-4|CSN/ORD-Minimal-Export                                                                  |WS3                              |2–3                |—          |

**Brutto-Gesamt ≈ 60–95 PT** (inkl. Review-Deltas, Edge-Cases, Doku, Stabilisierung). Netto-Implementierung ohne Kundenspezifika ±30 %.

**M1** (nach WS1): lesendes Cockpit produktiv — Status, Historie, Run-Trigger mit Live-Log + Polling.
**M2** (nach WS3): Contract→Compile→Certify geschlossen; erster Pflichtfall (`Sales_Orders_View`-Key) durchlaufen.
**M3** (nach WS4 + WS5): Konzeptumfang v1 inkl. Coverage Map, Feedback-Loop, BDC-Export.

**Entscheidungs-Gate vor M2 (N3, kein Bau):** Betriebsmodell festlegen — Berater-lokal (kein Dauerbetrieb) vs. Container beim Kunden (Updates/Secrets/IdP-Zuständigkeit). Bepreisen, bevor WS3 fertig ist.

-----

## 4 — CI-Gates (anlegen in WS0-9, müssen vor erstem Feature-Merge laufen)

|Gate|Prüfung                                 |Mechanik                                                                                              |
|----|----------------------------------------|------------------------------------------------------------------------------------------------------|
|G1  |Kein SQL im Contract                    |jsonschema + Lint-Test auf `contracts/*.yml` (`[CONTRACT-SQL-FREE]`)                                  |
|G2  |Kein hartkodiertes `CENTRAL` im Compiler|Unit-Test + `grep`-Gate auf `dq_core/contract` (`[SCHEMA-MAP]`)                                       |
|G3  |Breaking ⇒ Major-Sprung                 |`dq_core.contract.diff`-Tests + CI-Gate auf Contract-PRs (derselbe Code wie serverseitige Prüfung, F1)|
|G4  |Kein FE/BE-Typ-Drift                    |`openapi-typescript` generieren, `git diff --exit-code`                                               |
|G5  |Engine-Regress                          |bestehende pytest-Suite nach Extraktion unverändert grün (`[ENGINE-FROZEN]`)                          |
|G6  |Gating sichtbar                         |Test: `skipped_stale` landet als expliziter `state`, nie stilles Auslassen                            |
|G7  |Framework-Isolation                     |`grep` auf `import fastapi/flask/starlette` in `dq_core/` → fail                                      |
|G8  |PII-Gate                                |Test: ohne `ALLOW_LOCAL_DIAGNOSTICS` keine Zeile in `dq_diagnostics`; mit Flag nur Allowlist-Spalten  |

**Teststrategie:** `dq_core` pytest (bestehend + contract/compiler/diff/baselines, inkl. Compiler-Determinismus per Hash) · API httpx-TestClient gegen SQLite · Frontend Vitest + Testing Library (StatusGrid-, Editor-Logik) · Playwright-Smoke für M1/M2-Pfade + Multi-Worker-Run (F2).

-----

## 5 — Offene Punkte (vor dem jeweiligen WS klären, nicht raten)

|# |Punkt                                                                               |blockiert       |Vorgehen                                                                                     |
|--|------------------------------------------------------------------------------------|----------------|---------------------------------------------------------------------------------------------|
|O2|Zugriffspfad Katalog-/Lastmetadaten (DWC_GLOBAL nicht öffentlich dok., HDLF-CLI-Gap)|WS5-1           |Spike 1–2 PT vor WS5-1; Fallback `LOAD_TS` + Row-Count-Snapshot                              |
|O1|Breaking-Diff Stufe 2 (ODCS/`datacontract-cli`)                                     |WS2-4 optional  |Stufe 1 homegrown reicht für M2; Stufe 2 erst nach R3/R9                                     |
|O3|`columnEdges` ohne echte Derivation (Daten-, **kein** Parser-Defekt — Stand 2026-06-26)|WS4/UX-N7 Spaltenebene|CQN-Walker ist implementiert **und** unit-getestet (`computed`+Expression). Realer Blocker: Extract liefert in den Snapshots keinen CSN-`query`-AST/`sql`, daher nur Seed-Platzhalter. Plan: `docs/PLAN_UX-N7_Column_Lineage.md`|
|O4|OIDC beim Kunden (IdP, Claims→Rollen)                                               |WS5/Deployment  |Abstraktion steht ab WS0; Mapping pro Engagement                                             |
|O5|Parallel Execution (`SCOPE-parallel-execution.md`)                                  |später          |deferred; Tenant-Connection-Limit klären, dann 1–2 PT (Registry erlaubt es ohne API-Änderung)|
|O6|Ergebnisheimat Kunde: `HanaResultStore` vs. SQLite-Sync                             |WS0-3/Deployment|Empfehlung: Store folgt Deployment, kein Sync; HANA = `dq_results_lt`                        |
|O7|Stats-Tuple-Erhebung: Batch-UNION vs. Profil-Lauf                                   |WS5-2           |separater Profil-Lauf je Dataset (ein Statement); Spike                                      |

**Bewusst außerhalb v1:** SAC konsumiert weiter Released Interface Views; BDC-Anbindung nur einseitiger Export (WS5-4); kein Engine-Fork für Object-Store (E2 — Object-Store-Produkte erst nach HANA-Repräsentation prüfbar, in Kundenpräsentation explizit nennen, B3).

-----

## 6 — Definition of Done (gesamt)

- Alle Gates G1–G8 grün in CI.
- M1, M2, M3 Acceptance erfüllt.
- Engine-Suite unverändert (G5), `dq_core` frameworkfrei (G7).
- Lokal-Deployment (NoAuth, 127.0.0.1, SQLite) **und** Kunden-Deployment (OIDC, ≥2 Worker, HANA-Store) aus demselben Code lauffähig — verifiziert mit Multi-Worker-Run.
- Keine Rohzeile verlässt HANA ohne explizite Freigabe + Allowlist (E6/S1).
- `Sales_Orders_View`-Key-Pflichtfall durchlaufen: ⚠ → Garantie → Compile → Run → ✓.