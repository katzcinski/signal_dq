# OPEN TASKS — Konsolidierter Backlog (alle Bereiche) · Signal

> **Stand:** 2026-08-25 (Abschnitt **T** — MVP-Modul-Gating/Stufenrollout —
> ergänzt; übriger Stand 2026-07-23: E/F/N gegen den Code nachgeführt,
> Obs-Intelligence v1 und Enforcement-Achse/Quarantäne sind seit 2026-07 in
> `main`) ·
> **Zweck:** Ein einziger Einstiegspunkt über **alle**
> offenen Punkte, die heute über die `docs/`-Konzepte, Pläne, Reviews und
> Handovers verstreut sind. Diese Datei **ersetzt** die Quelldokumente nicht —
> sie verlinkt sie und hält den aggregierten Status. Detailtiefe (Acceptance,
> Dateipfade, Sequenz) bleibt im jeweiligen Quelldokument.
>
> Die frühere `OPEN_TASKS_UIUX.md` ist in diese Datei **eingegangen** (Status-
> Matrix + Detail + historischer Kontext → Abschnitt **A**).
>
> Historische Review-/Plan-Dokumente führen keine eigene aktive Backlog-Liste
> mehr. Wenn ein Quelldoc noch anders klingt, gilt diese Datei.

**Methode:** Status wurde gegen den Code verifiziert, nicht nur aus den Docs
übernommen — wo Doku und Code abwichen (z. B. O3, HANA WS D), gilt der Code-Stand
und ist vermerkt.

## Legende

| Symbol | Bedeutung |
|--------|-----------|
| ◻ Offen | noch nicht begonnen / nur Konzept |
| ◑ Teilweise | Teile geliefert, Rest offen |
| 🔒 Blockiert | hängt an einer Vorbedingung / Entscheidung / Daten |
| 🧪 Verifikation | Code da, aber unbewiesen (reale HANA/Tenant nötig) |
| ✅ Done | erledigt (hier nur gelistet, wenn ein Quelldoc es noch als offen führt) |

Priorität: **[H]** hoch · **[M]** mittel · **[L]** später/optional.

---

## Übersicht

| ID | Thema | Status | Prio | Quelle |
|----|-------|--------|------|--------|
| **A1** | Teilbarer Quality-Report / Data-Docs-Snapshot (UX-N6) | ◻ Offen | M | Abschnitt A |
| **A2** | Schema-Drift-/Change-Screen (UX-N9) | ✅ Done | M | Abschnitt A |
| **B**  | Spaltenebene-Lineage + Impact (UX-N7 / O3) | ✅ Done | H | `PLAN_UX-N7_Column_Lineage.md` |
| **C**  | `HanaResultStore` (O6) + HANA-Migrationen + Smoke | ◻ Offen | H | `Implementation_HANA_Connection_Progress.md` WS E/F |
| **D**  | Managed Service (Instanz-pro-Tenant) | ◻ Offen | H | `PLAN_Managed_Service_v1.md` |
| **E**  | Observability-Mehrwert (z-Score, Freshness, Impact) | ◑ Teilweise (E1/E3 ✅, E2 offen) | M | `PLAN_Observability_Mehrwert_v1.md` |
| **F**  | Durchsetzungs-Achse `gate \| quarantine \| monitor` | ◑ Teilweise (Slices ①–③ ✅) | M | `Konzept_Datasphere_Integration_Gating_Quarantaene.md` |
| **G**  | OpenLineage-Emitter | ◻ Offen | L | `Scope_OpenLineage_Emitter.md` |
| **H**  | Multi-Plattform-Executor (BDC/Databricks) | ◻ Offen | L | `Konzept_MultiPlattform_Executor_BDC.md` |
| **I**  | Meridian-Port Restpunkte | ◑ Teilweise | M | `HANDOVER-meridian-port.md` |
| **J**  | Freshness als zweite Achse (Run-/Load-Info) | ◑ Teilweise | M | `Konzept_Runs_Freshness.md` |
| **K**  | HANDOVER-Spikes / offene Entscheidungen (O1–O7) | ◑ Teilweise | div. | `HANDOVER.md` §5 |
| **L**  | Verifikation & Nice-to-have (HANA-Smoke, en-Locale, Prometheus, E2E) | 🧪 | L | div. |
| **M**  | Workflow-Audit-Follow-ups (P1/P2/P3, 2026-06-30) | ◻ Offen | H/M | `WORKFLOW_AUDIT_2026-06-30.md` |
| **N**  | Scheduling Phase 2 | ◑ Teilweise (N2 ✅) | M | `ADR-0005_Scheduling.md` |
| **O**  | Lineage UX Phase 3 | ◻ Offen | M/L | `Spec_Lineage_UX_Redesign.md` |
| **P**  | Data-Product/BDC Phase 2 + Verifikationspunkte | ◻ Offen | M/L | `ADR-0003`, `ADR-0004`, `PLAN_ADR-0003-0004_Implementation.md` |
| **Q**  | Tech-Debt: `notify.py`-Dedup (Routing & Dispatch) | ◻ Offen | L | Abschnitt Q |
| **R**  | Healing: Restoptionen H2/H4/H5 + Opt-in-Lücken (R5/R6) | ◻ Offen | H/M/L | `Konzept_Manuelles_Healing.md` |
| **T**  | MVP-Modul-Gating + Stufenrollout (`ROLLOUT_WAVE`) | ◻ Offen | H | `Konzept_MVP_Kundenrollout.md` |

> Der Buchstabe **S** ist bewusst übersprungen: `S1`/`S5`/`S-14` sind im Code
> bereits Sicherheits-Marker (PII-Gate, Bind-Policy, Fehler-Leakage) — eine
> Backlog-ID `S5` wäre doppeldeutig.

> **Bereits geschlossen, obwohl ein Quelldoc es noch offen führt:** Interne
> DQ-Checks-Library im Builder (`handover-iteration-1-internal-checks.md`) ist
> umgesetzt (Compiler-`checks:`-Pfad, `contracts.py`-Persistenz, `GateCheck`-Typ,
> Library v6) ✅. Data-Product-Aggregat (`CODEX_HANDOVER_TrackA_Phase1.md`) ist
> umgesetzt (`packages/dq_core/product/`, `routers/products.py`) ✅. HANA
> WS A/B/C/F5 + der Connections-/Test-Screen (als `pages/Environments.tsx` inkl.
> Test-Button, `secret_status`, `OperationProgress`) sind geliefert ✅ — siehe C.

---

## A — UI/UX (früher `OPEN_TASKS_UIUX.md`)

> Aus `OPEN_TASKS_UIUX.md` übernommen. Modus wie HANDOVER: jeder Schritt mit
> Acceptance, kein Merge bei rotem Gate. Farbsemantik (Familie ⟂ Status),
> Mono-für-Artefakte und Carbon-≥3-von-4-Encoding sind gesetzt und werden nicht
> neu verhandelt.

### Status-Matrix

| ID | Inhalt | Status | Dokumentiert / Beleg |
|----|--------|--------|----------------------|
| UX-F1 | Rollenmodell + Read-only-Zustände (`X-DQ-Role`, Ownership-Lock) | ✅ Done | Tooldoku §9 |
| UX-F2 | Roh-Views/native Dialoge durch designte Oberflächen ersetzt | ✅ Done | — |
| UX-F3 | Incident-Drawer als echter Dialog/Inspector | ✅ Done | Incidents-Inbox (R4-1) |
| UX-F4 | A11y-Härtung (Kontrast `--fg-3`→AA, Nav-Icon-Labels) | ✅ Done | — |
| UX-F5 | Faceted Search/Filter im Objektkatalog (URL-synced) | ✅ Done | Tooldoku §8 (`/objects`) |
| UX-F6 | Token-Disziplin Spacing/Radius + geteilte Primitives | ✅ Done | Primitives + `--r-full` |
| UX-F7 | Restpolitur (Breadcrumbs, Governance Loading/Error, Relativzeit) | ✅ Done | — |
| UX-F8 | Button-Interaktionszustände (Hover/Active/Disabled-Kontrast) | ✅ Done | Globale `button`-Regeln + `Button.test.tsx` |
| UX-F9 | CSS-Micro-polish (::selection, FF-Scrollbar, Header-Shadow, Row-Hover) | ✅ Done | index.css, `Table` Sticky-Header |
| UX-N1 | Freshness-/Volume-Zeitreihen (Band, Anomalie-Marker) | ✅ Done | Tooldoku §8 („Verlauf"-Tab) |
| UX-N2 | Alerting & Notification-Routing | ✅ Done | Tooldoku §5/§8 (`/notifications`, Migration 005/007) |
| UX-N3 | Rollen-Landing „My work" | ✅ Done | Tooldoku §8 (`/my`) |
| UX-N4 | SLA/SLO-Dashboard (Burn-down, Uptime %) | ✅ Done | Tooldoku §5 (`/sla`) |
| UX-N5 | Run-Vergleich / Regressions-Diff | ✅ Done | Tooldoku §5/§8 (`/runs/compare`) |
| UX-N6 | Teilbarer Quality-Report / Data-Docs (Link/PDF) | ◻ Offen | Badge existiert (`/badge/{p}`), Report-Snapshot fehlt → **A1** |
| UX-N7 | Spaltenebene-Lineage + Impact-Analyse | ✅ Done | DAG + Impact-API + UI gegen Demo-Daten; Live-Tenant-CSN bleibt Verifikation unter **I/L** |
| UX-N8 | Check-/Expectation-Library-Browser | ✅ Done | Tooldoku §8 (`/library`) |
| UX-N9 | Schema-Drift-/Change-Screen | ✅ Done | `/schema-drift` (Overview + Evolution je Objekt) → **A2** |
| UX-N10 | Status-Heatmap Objekt × Tag | ✅ Done | Tooldoku §8 (Cockpit) |
| UX-N11 | Echte Charts (Threshold-/Anomalie-Band, Zeitraum-Picker) | ✅ Done | — |
| UX-N12 | Health-Gauge mit Trendrichtung | ✅ Done | Tooldoku §8 (Cockpit) |
| UX-N13 | Diff-Viewer (Contract-Versionen & Proposals) | ✅ Done | Tooldoku §5 (`/diff/active`) |
| UX-N14 | Profiling-/Sample-Row-View hinter `[PII-GATE]` | ✅ Done | Tooldoku §5/§6 (`/profile`, `ALLOW_PROFILE_SAMPLES`) |
| UX-N15 | Activity-/Audit-Feed | ✅ Done | Tooldoku §5 (`/api/activity`) |

**Offen (1):** UX-N6 (teilbarer Report, **A1**).

### Offene Punkte (Detail)

- **A1 · UX-N6 — Teilbarer Quality-Report / Data-Docs.** `[M]` ◻
  `BadgeEmbed` + `GET /api/badge/{p}` existieren als Tile; der vollständige,
  auth-gegatete **Report-Snapshot** (Link/PDF für Nicht-Nutzer, GX-Vorbild) fehlt.
  Kein `/report`-Route im Backend.
  *Acceptance:* öffentlich teilbarer, auth-gegateter Report-Snapshot.
- **A2 · UX-N9 — Schema-Drift-/Change-Screen.** `[M]` ✅ (2026-08-03)
  Eigenständiger Screen unter `/schema-drift`: Overview je Objekt (Snapshots,
  distinct Schemata, Befunde/breaking, Contract-Bindung) + Evolution über Zeit
  (konsekutive Snapshot-Diffs via `diff_snapshots` in
  `dq_core/contract/schema_drift.py`, frameworkfrei) + Drift-Historie gegen den
  Contract mit Incident-Deep-Link. API `GET /api/schema-drift[/{object}]`
  (`routers/schema_drift.py`), Store-Rollups (`get_schema_snapshots`,
  `list_schema_drift_objects`), Page `pages/SchemaDrift.tsx` + Nav + `de.ts`;
  Tests: `tests/unit/test_schema_drift_evolution.py`,
  `tests/api/test_schema_drift_screen.py`, `src/tests/SchemaDrift.test.tsx`.
  `diff.py`-Type-Narrowing (Schema v2) bleibt bewusst außen vor.
  *Acceptance erfüllt:* Spaltenänderungen je Objekt über Zeit, Contract-Bruch markiert.

UX-N7 (Spalten-Lineage) ist erledigt; historische Details und Restrisiken stehen in **B**.

### Historischer Kontext

Quelle: UI/UX-Review vom 2026-06-12 (Senior-Design-Lens) gegen Stand `b300565`,
Marktabgleich Soda/Monte Carlo/GX/dbt/Datafold. Leitidee war, die **zeitliche und
operative Dimension** (Zeitreihen/Alerting — was Soda/MC zum Monitoring statt
Reporting macht) und die **Lücke zwischen Konzept und Implementierung**
(Rollenmodell, eingebettete Lineage, designte statt Roh-Views) zu schließen.
Tier 1 (UX-F1, UX-F2, UX-N1–N4) war der demonstrative Hebel und ist vollständig
ausgeliefert; die Markt-Table-Stakes-Begründung steht in
[`REVIEW_Tool_v1_Befunde.md`](REVIEW_Tool_v1_Befunde.md) §7.

---

## B — Spaltenebene-Lineage + Impact-Analyse (UX-N7 / O3) ✅ [H]

**Quelle:** [`PLAN_UX-N7_Column_Lineage.md`](PLAN_UX-N7_Column_Lineage.md);
querschnittlich auch unter **A** (UX-N7), `REVIEW_Tool_v2_Status.md`
(#1 Column-level coverage), `Scope_OpenLineage_Emitter.md` (OL3),
`Betriebsmodi_Lite_und_Full.md` (Spaltenebene in Coverage), `HANDOVER.md` (O3).

**Korrigierte Diagnose (2026-06-26):** O3 ist **kein Parser-Defekt**, sondern ein
**Datenproblem**. Der CQN-Walker (`_csn_reconstructor.py`,
`_column_lineage.build_column_lineage`) ist implementiert **und** unit-getestet
(`computed`-Kanten inkl. gerenderter Expression; SQL-Pfad via sqlglot). Die API
steht (`GET /api/lineage/columns`). Das FE-Binding (`fetchColumnLineage`) steht.

**Umgesetzt / verifiziert:**
- **Daten:** `data/inventory.json` trägt Demo-Objekte mit `csnProjection`;
  `data/lineage.json` enthält echte `columnEdges` inklusive `computed`-Kanten
  mit Expression.
- **Backend:** Extract-Pipeline schreibt `build_column_lineage(...).serialize()`;
  `GET /api/lineage` liefert `columnEdges`, `GET /api/lineage/columns` liefert
  den Spaltenindex, `GET /api/lineage/columns/impact` liefert transitive
  Downstream-Consumer mit Ownership/Coverage.
- **Frontend:** `ColumnLineagePanel` ist im Objekt-Detail-Lineage-Tab eingebunden
  und zeigt Spaltenauswahl, Upstream/Downstream-DAG und Impact-Liste.

**Restrisiko / spätere Verifikation:**
- Live-Tenant-CSN/SQL-Extrakt bleibt unter **I3/L1** zu verifizieren; der
  Demo- und Mock-Pfad ist grün.

**Acceptance:** Spalten-DAG + betroffene Downstream-Consumer mit Ownership aus
einem Incident heraus. **Folgewirkung:** entsperrt Spalten-Coverage (REVIEW v2 #1)
und OL3.

---

## C — `HanaResultStore` + Full-Deployment (O6) ◻ [H]

**Quelle:** [`Implementation_HANA_Connection_Progress.md`](Implementation_HANA_Connection_Progress.md)
WS D–G; `HANDOVER.md` O6; `REVIEW_Tool_v2_Status.md` (Real-HANA-Pfad).

**Verifizierter Stand:** WS A (Connection-Test + `on_progress`), WS B
(Operation-/Progress-Kanal, Migration 008), WS C1–C4 (Run/Dry-Run/Profile async +
Test-Endpoint), WS F5 (`FileSecretResolver` + `PUT …/secret`) und WS D
(`OperationProgress`-Komponente, `useOperationStream`, Test-/Secret-UI als
`pages/Environments.tsx`) sind **geliefert**. Offen bleibt der HANA-Store selbst:

- **C1 · WS E1 — HANA-Dialekt-Migrationen** `store/migrations/hana/NNN_*.sql`.
  SQLite-Spezifika übersetzen (`AUTOINCREMENT`→Identity/Sequence, `TEXT`→
  `NVARCHAR`, partieller Unique-Index → HANA-Filtered-Index); `CREATE TABLE`
  qualifiziert aufs Open-SQL-Schema (`[SCHEMA-MAP]`, kein Literal).
- **C2 · WS E2 — `HanaStore`** `store/hana_store.py` ist noch **Stub** (17×
  `NotImplementedError`). Alle Protokoll-Methoden via `hdbcli` implementieren;
  reale Store-Fläche ist auf ~48 Methoden gewachsen (Incidents, Schedules,
  Notifications, SLA, Object-Status-Rollups), nicht nur die 17 des veralteten
  `ResultStoreProtocol`. **Deckungsgleich** zu `SqliteStore` (Managed-Entscheid).
- **C3 · WS E3 — `deps.get_store()`** baut bei `STORE_BACKEND=hana` den
  `HanaStore` statt zu werfen; `RESULTS_ENVIRONMENT` in `settings.py` ergänzen.
- **C4 · WS F1–F4 — Verifikation & Härtung:** Smoke-Harness
  (`tests/integration/test_hana_smoke.py` + `make hana-smoke`, env-gated
  `HANA_SMOKE=1`); DB-User-Härtung dokumentieren (`Tooldokumentation.md` §9/§10);
  `scripts/generate_environments.py` + `DatasphereClient.list_db_users()`.
- **C5 · WS G — Quarantäne/Reject-Store** (optional, nach E): zeilen-genaue
  Verstöße per `INSERT … SELECT` direkt in HANA (PK + Allowlist), Rohzeile berührt
  den App-Prozess nie (E6 strikt). Default-off je Garantie. **= F Slices ④–⑤**
  (episodische Zeilen-Tabellen): der `quarantine`-Modus mit Episoden-Lifecycle
  ist geliefert, die Zeilen-Ebene läuft über die Integration-Slices.

**Aufwand (Doc):** ≈ 7,5–10,5 PT (ohne WS G).
**Acceptance:** `STORE_BACKEND=hana` legt Tabellen im konfigurierten Open-SQL-
Schema an, Store-Suite läuft env-gated grün, Result-Tabellen aus dem Space lesbar.

---

## D — Managed Service (Instanz-pro-Tenant) ◻ [H]

**Quelle:** [`PLAN_Managed_Service_v1.md`](PLAN_Managed_Service_v1.md) (Status:
„noch kein Code"); konkretisiert `Konzept_Managed_Service_Provisioning.md` §5.
Scope: **Instanz-pro-Tenant**, `tenant_id`/Row-Level-Pooling bewusst de-scoped.

- **D1 · AP-A — Produktiver `HanaStore`.** **= C2/C1** (der eigentliche Blocker;
  ohne ihn läuft Managed nur auf SQLite-pro-Tenant). Migrationen dialekt-getrennt;
  Doppellauf-Guard via HANA Filtered Index; CI-Verifikation gegen echte HANA im
  nicht-blockierenden Optional-Job.
- **D2 · AP-B — Provisioning-Automation.** „Tenant anlegen" wiederholbar/
  fehlerarm.
- **D3 · AP-C — Pro-Tenant Konfig-/Secret-Härtung.** Saubere Isolation ohne
  App-Umbau (Isolation über Infrastruktur, nicht über Query-Filter).
- **D4 · Offene Entscheidungen** (Doc §„Offene Entscheidungen") vor dem Bau klären.

> **Hinweis:** D1 und C überlappen vollständig — ein `HanaStore` bedient beide
> Spuren. Bei der Umsetzung **nicht doppelt planen.**

---

## E — Observability-Mehrwert ◑ [M]

**Quelle:** [`PLAN_Observability_Mehrwert_v1.md`](PLAN_Observability_Mehrwert_v1.md);
umgesetzt weitgehend über Observability-Intelligence v1
([`HANDOVER_Observability_Intelligence_v1_Implementation.md`](HANDOVER_Observability_Intelligence_v1_Implementation.md),
Migrationen 010–015).

- **E1 · Robuster MAD-z-Score.** `[M]` ✅ — geliefert: `robust_zscore()` +
  `compute_robust_bounds()` in `obs/baselines.py`, `median` in `dq_baselines`
  (Migration `010_baseline_median`), saisonale Buckets (Migration 011).
- **E2 · Freshness via Task-Log.** `[M]` ◻ — schließt „blinde" Objekte; setzt auf
  vorhandenem Scheduling/Task-Chain-Trigger auf. **Überschneidet sich mit J.**
- **E3 · Lineage-Impact am Alert.** `[M]` ✅ — geliefert: Impact-Snapshot je
  Incident (`dq_incidents.impacted_objects`, Migration `015_incident_impact`),
  angezeigt in der Incident-Inbox und in Notifications. Die feinkörnige
  Spalten-Variante bleibt an **B**/Live-CSN (I3) gebunden.

---

## F — Durchsetzungs-Achse `gate | quarantine | monitor` ◑ [M]

**Quelle:** [`Konzept_Datasphere_Integration_Gating_Quarantaene.md`](Konzept_Datasphere_Integration_Gating_Quarantaene.md)
(löst das ursprüngliche
[`Konzept_Enforcement_Modi_Gate_Quarantine_Monitor.md`](Konzept_Enforcement_Modi_Gate_Quarantine_Monitor.md)
als Umsetzungsgrundlage ab).

**Geliefert (2026-07, Slices ①–③):** `enforcement` auf CheckDef/CheckResult/
Guarantee + `enforcement_default` am Contract (Default `monitor`),
`gate_verdict`-Rollup `proceed|quarantine|block` (G6-state-bewusst), Migration
016 (`enforcement_mode`, `gate_verdict`, `dq_quarantine` + Events),
CLI-Exit-Codes 0/1/3 + `--no-enforce`, `GET /api/runs/{id}/status`
(API-Task-Vertrag), `/api/quarantine` (Episoden-Lifecycle, steward+),
Verdict-Materialisierung `packages/dq_core/enforce/` + `/api/enforcement/plan|apply`
(doppelt gegated), Quarantäne-Seite im Cockpit. Siehe `Tooldokumentation.md` §3.8.

**Offen (Slices ④–⑦):** Reconciler/Split-Views, episodische **Zeilen**-Tabellen
(Reject-Store, = **C5/WS G**), SQL-Bridge, Task-Chain-Vorlagen — plus
Live-Tenant-Verifikation der Materialisierung (Spikes O5/O6 im Konzept).

---

## G — OpenLineage-Emitter ◻ [L]

**Quelle:** [`Scope_OpenLineage_Emitter.md`](Scope_OpenLineage_Emitter.md)
(Status: Scope/Plan, keine Implementierung). Phasen P0 (terminal-only RunEvent) →
P3 (Spalten-Lineage, Typen aus CSN). Offene Punkte:

- **OL1 [H]** Graph-Snapshot-Form gegen Marquez **und** DataHub verifizieren.
- **OL2 [H]** Spalten-Typen im Schema-Facet (kommen erst aus CSN, vgl. B/I).
- **OL3 [M]** Spalten-Lineage-Granularität — setzt auf **B** auf; Live-Tenant-
  Datenherkunft bleibt unter **I3/L1** zu verifizieren.
- **OL4 [M]** CLI-Pfad (`cli/dq_check_runner.py`): publizieren Cron-Läufe?
- **OL5 [L]** Dataset-`namespace`-Konvention final festlegen.
- **[P1]** Offizieller OL-Client vs. handgerolltes JSON (Dependency-Entscheidung).

---

## H — Multi-Plattform-Executor (BDC / Databricks) ◻ [L]

**Quelle:** [`Konzept_MultiPlattform_Executor_BDC.md`](Konzept_MultiPlattform_Executor_BDC.md)
(Konzept-/Evaluierungsdoc, keine gesetzten Entscheidungen). Offene Punkte/Risiken:

- **[H]** HDLF-Route A (über HANA) vs. B (Databricks/Delta) je Dataset.
- **[H]** HANA-Engine in `datacontract-cli` existiert nur per Prämisse —
  Upstream-Beitrag (`hdbcli`-Engine) vs. Fork bewerten.
- **[M]** 3-teiliger Namespace im Compiler (`[SCHEMA-MAP]`→`[NAMESPACE-MAP]`,
  optionales `catalog`-Segment ohne G2 zu verwässern).
- **[M]** SAP- vs. native-Databricks-Auth/Unity-Catalog; Capability-Paritätstests
  je Dialekt.
- **[L]** Cross-Platform-Konsistenz-Check als neue Garantie-Familie (Folgekonzept).

---

## I — Meridian-Port Restpunkte ◑ [M]

**Quelle:** [`HANDOVER-meridian-port.md`](HANDOVER-meridian-port.md). Connector,
Extraction, Profiling, Column-Lineage-Chain sind portiert. Offen:

- **I1 · Reicheres Node-Schema im FE adoptieren.** `LineageMap.tsx` hartkodiert
  noch `layer:int` 0–2/`LAYERS[3]` und ignoriert `edge.type`, obwohl das Backend
  `layer:string`/`layerCode`/`role`/`confidence`/`columns[]` emittiert.
  *Offene Entscheidung:* sauberer Cutover vs. Back-Compat-Adapter.
- **I2 · Snapshot/Compare/Diff-Validator (counts-only).** Aus Meridian
  `datasphere_data_validator.py` portieren (`gather_stats`, Compare-Row-Ratio
  >1.05, Diff via SQL `EXCEPT`, Key-Cardinality) → `dq_core/validator/`
  (framework-frei) + API-Route. **PII-Gate:** nur Counts / nicht-sensible Spalten.
  Auch die Fan-out-/Cardinality-Guardrail als `check_library`-Template.
- **I3 · Live-Tenant-Validierung** (🧪): REST-Endpoints nur gegen `respx`-Mocks
  geprüft. `read_object_definition` (`$expand=definition`) liefert evtl. **kein**
  volles CSN → CLI-Pfad für Spalten-Lineage nötig (verifiziert **B** für echte
  Tenants);
  **Pagination** (`@odata.nextLink`) **nicht** behandelt → große Spaces brechen
  nach Seite 1 ab; ggf. zusätzliche OAuth-Scopes.
- **I4 · Extraktion läuft synchron im Threadpool** — keine dauerhafte Job-Queue;
  bei großen Spaces ggf. langsam (revisit).

---

## J — Freshness als zweite Achse ◑ [M]

**Quelle:** [`Konzept_Runs_Freshness.md`](Konzept_Runs_Freshness.md). MVP
(Objekt-Detail-Freshness, Run-Sparkline, „unknown" ohne Connector) ist die
Richtung; offene Designentscheidungen vor dem Verdrahten ins Gating:

- **J1 [H]** `skipped` vs. `downgraded` bei Staleness — Empfehlung `downgraded`
  mit zitiertem Run; **größtes semantisches Risiko**, vor Gate-Integration klären.
- **J2 [M]** Statische Schwellen → Alert-Fatigue: erwartete Cadence pro Objekt aus
  Run-Historie + `schedules.py` lernen, Contract-Wert nur als Obergrenze.
- **J3 [M]** Propagation mit Root-Cause-Dedup (Root + Blast-Radius-Count), sonst
  färbt Downstream-Staleness halbe Landschaften rot.
- **J4 [M]** Partielle Task-Chain-Rollups pro Task modellieren, nicht Chain-Level.
- **J5 [M]** Skalierung: Bulk-Abruf/Caching statt Per-Objekt-Fan-out (N+1).
- **J6 [L]** Optionaler aggregierter Trust-Score (Freshness+Volume+Schema+Quality)
  für Coverage-/Exec-Views — Signals zwei explizite Achsen bleiben transparenter.

---

## K — HANDOVER-Spikes / offene Entscheidungen (O1–O7) ◑

**Quelle:** [`HANDOVER.md`](HANDOVER.md) §5 — vor dem jeweiligen WS klären:

| ID | Punkt | blockiert | Vorgehen |
|----|-------|-----------|----------|
| O1 | Breaking-Diff Stufe 2 (ODCS/`datacontract-cli`) | WS2-4 optional | Stufe 1 homegrown reicht für M2 |
| O2 | Zugriffspfad Katalog-/Lastmetadaten (`DWC_GLOBAL` nicht dok., HDLF-Gap) | WS5-1 | Spike 1–2 PT; Fallback `LOAD_TS` + Row-Count |
| O3 | `columnEdges` ohne echte Derivation | ✅ Done | Als **B** geschlossen; nur Live-Tenant-Verifikation unter **I3/L1** |
| O4 | OIDC beim Kunden (IdP, Claims→Rollen) | WS5/Deploy | Mapping pro Engagement |
| O5 | Parallel Execution | später | deferred; Tenant-Connection-Limit klären |
| O6 | Ergebnisheimat: `HanaResultStore` vs. SQLite-Sync | → **C/D** | Store folgt Deployment, kein Sync |
| O7 | Stats-Tuple-Erhebung: Batch-UNION vs. Profil-Lauf | WS5-2 | separater Profil-Lauf je Dataset; Spike |

---

## L — Verifikation & Nice-to-have 🧪 [L]

**Quelle:** `REVIEW_Tool_v2_Status.md` (Verification-only), querschnittlich.

- **L1 · Reale HANA-Ausführung** 🧪 — `MockConnection` lokal; der `hdbcli`-Pfad ist
  hier nicht ausführbar. Real-Smoke nötig (= **C4/WS F1**).
- **L2 · Multi-Locale** — nur `de.ts` (kein `en`/Switcher). OK, falls Deutsch-only
  gewollt; sonst flaggen.
- **L3 · Prometheus-Exporter** — In-Memory-Metriken + `/api/metrics/health`
  existieren; ein extern scrapebarer Exporter ist Nice-to-have.
- **L4 · Playwright-E2E-Smoke** — optionaler Browser-Ebene-Smoke obendrauf (kein
  Korrektheitsrisiko mehr, `PLAN_Remediation_v2.md`).
- **L5 · Visuelle QA am Datenvolumen** — Tabellendichte >500 Objekte, breite DAGs
  (dagre-Tuning) gegenprüfen (`Konzept_DQ_Cockpit_UIUX.md` §9).

---

## M — Workflow-Audit-Follow-ups (2026-06-30) ◻ [H/M]

**Quelle:** [`WORKFLOW_AUDIT_2026-06-30.md`](WORKFLOW_AUDIT_2026-06-30.md) und
[`PLAN_Workflow_Audit_2026-06-30.md`](PLAN_Workflow_Audit_2026-06-30.md);
überlappt beim Proposal-Banner mit
[`workbench-ux-implementation-handover.md`](workbench-ux-implementation-handover.md).

- **M1 · Stabile Proposal-IDs + Aktionen auf zurückgegebenen IDs.** `[H]` ◻ —
  mined proposals dürfen nach Listen nicht durch neue UUIDs unbedienbar werden;
  Entscheidung `accept/reject/snooze` muss den gelisteten Vorschlag stabil
  filtern.
- **M2 · Contract-Aktivierung/Git-Fehler-Semantik.** `[H]` ◻ — lokale Artefakte,
  Active-Snapshot, Checks, Index und Git-Commit/Push dürfen nicht widersprüchlich
  Erfolg/Fehler melden; Push-Reject braucht einen sichtbaren Recovery-Zustand.
- **M3 · Hermetische Tests und lokale Workflows.** `[M/H]` ◻ — Testläufe dürfen
  nicht von lokaler `.env`/Datasphere-Connector-Konfiguration abhängen; Caches und
  Connector-ENV gezielt isolieren.
- **M4 · Ehrliche Proposal-Accept-Semantik + Pending-Banner.** `[M]` ◻ — solange
  Proposals keinen strukturierten Patch tragen, heißt Accept faktisch „in Draft
  übernehmen"; der Workbench muss die wartende Änderung sichtbar machen.
- **M5 · Contract-Index-Integrität.** `[M]` ◻ — `_update_index` darf Fehler nicht
  schlucken; Schreib-Endpunkte dürfen keinen sauberen Erfolg melden, wenn der
  Read-Model-Index stale bleibt.
- **M6 · OpenAPI/TypeScript-Schema drift + G4 wieder blockierend.** `[M]` ◻ —
  `apps/cockpit/openapi.json` und `schema.d.ts` regenerieren, audit-gelistete
  neue Pfade abdecken, danach CI-G4 wieder als hartes Gate führen.
- **M7 · Legacy `/api/environments` + `/settings` Direktlink.** `[L/M]` ◻ —
  sichere Legacy-Response-Shape finalisieren und Settings unter Nicht-Admin-Rolle
  ohne Admin-403-Network-Request rendern.
- **M8 · Lineage-Bundle messen/optimieren.** `[L]` ◻ — große Lineage-Route erst
  nach M1–M7 messen; entweder reduzieren oder als route-lazy Risiko dokumentieren.

**Explizit nicht mehr offen:** Der frühere MiniGraph-Lint-Fund ist kein eigener
Backlog-Punkt mehr; `sparse` ist in der Hook-Dependency-Liste enthalten und
künftige Regressionen gehören in das normale Lint-Gate.

---

## N — Scheduling Phase 2 ◑ [M]

**Quelle:** [`ADR-0005_Scheduling.md`](ADR-0005_Scheduling.md). Der store-backed
Poller bleibt additiv; externer Scheduler/Task-Chain via CLI bleibt Default.

- **N1 · Cron-Ausdrücke statt fixer Intervalle.** `[M]` ◻ — zusätzlich zum
  Intervallmodell eine verständliche Cron-Repräsentation + Validierung.
- **N2 · Cockpit-Schalter pro Objekt.** `[M]` ✅ — geliefert:
  `SchedulePanel` im Objekt-Detail (Tab „History/Ops") + Ops-Screen
  `pages/Schedules.tsx` (`/schedules`).
- **N3 · HANA-Store-Parität für `dq_schedules`.** `[H]` ◻ — hängt praktisch an
  **C2**; Schedule-Claim, Last-Run-Felder und Doppellauf-Schutz müssen auf HANA
  dieselbe Semantik haben wie SQLite.
- **N4 · Missed-Run-/Catch-up-Telemetrie.** `[L/M]` ◻ — ausgelassene Slots,
  Catch-up-Entscheidung und Scheduler-Trigger im Ops-/Run-Kontext sichtbar machen.

---

## O — Lineage UX Phase 3 ◻ [M/L]

**Quelle:** [`Spec_Lineage_UX_Redesign.md`](Spec_Lineage_UX_Redesign.md). Phase 1
und 2 (ruhige Kamera, Kartenknoten, visuelle Tokens) sind historisch umgesetzt;
Phase 3 gilt sinngemäß für die aktuelle Schematic/SVG-Lineage weiter.

- **O1 · Gedocktes Inspektionspanel.** `[M]` ◻ — Panel darf keine Downstream-Knoten
  überdecken; Graph-Fläche schrumpft kontrolliert, ohne ungefragten Fit.
- **O2 · Persistente Objekt-/Spalten-Sicht.** `[M]` ◻ — Tabwechsel soll Zoom, Pan
  und Selektion behalten; kein Remount-/Layout-Flash.
- **O3 · Pin-Modus statt globalem Positionscache.** `[L/M]` ◻ — manuelle
  Positionen nur explizit gepinnt speichern, Auto-Layout bleibt deterministisch.
- **O4 · Graph-Controls/Orientierung.** `[L]` ◻ — Zoom, Fit, Re-Layout, Reset Pins
  und ggf. Minimap als dezente Instrument-Controls.
- **O5 · Tastatur- und A11y-Pass.** `[L]` ◻ — Suche, Selektion, Panel schließen,
  Fit/Zoom und Fokuszustände per Tastatur erreichbar machen.

---

## P — Data-Product/BDC Phase 2 + Verifikationspunkte ◻ [M/L]

**Quelle:** [`ADR-0003_BDC-Datasphere-DataProductStudio.md`](ADR-0003_BDC-Datasphere-DataProductStudio.md),
[`ADR-0004_DataProduct-als-Komposition.md`](ADR-0004_DataProduct-als-Komposition.md) und
[`PLAN_ADR-0003-0004_Implementation.md`](PLAN_ADR-0003-0004_Implementation.md).
Phase 1 des Data-Product-Aggregats ist geliefert; diese Punkte sind bewusst
nachgelagert.

- **P1 · Product-Discovery + Boundary-Generierung.** `[M]` ◻ — consumer-seitiges
  „verlässt das Estate"-Signal, Discovery-Kandidaten und `boundary` aus Intent ×
  Reality ableiten.
- **P2 · Verbleibende Product-Findings.** `[M]` ◻ — estate-leaving Boundary-Leak,
  Over-Declaration und Orphan-Interieur als Phase-2-Findings modellieren.
- **P3 · Produkt als Export-/Visualisierungseinheit.** `[L/M]` ◻ — ORD/Export auf
  Produkt-Ebene, reicheres Cockpit-Overlay um Lineage-Subgraphen, transitive Spur
  und globaler Findings-Rollup.
- **P4 · Owner-Vererbung ins Interieur.** `[M]` ◻ — Routing/Ownership für
  Interieur-Gates bei Contested-Interieur explizit klären.
- **P5 · BDC/HDLF-Verifikation.** `[M]` ◻ — V3a Load-Lag-Quelle prüfen,
  V2/V4/V5/V6 als Wissens-/Spec-Verifikation schließen; G-8 view-aware
  Katalog-Checks und späterer `load_lag`-Check hängen daran.

---

## Q — Tech-Debt: `notify.py`-Dedup (Routing & Dispatch) ◻ [L]

**Quelle:** Code-Survey 2026-07-04 (`services/api/notify.py`); Verhalten ist
durch `tests/unit/test_notify.py` abgedeckt.

Drei Stellen duplizieren dieselbe Logik und können bei Änderungen auseinander
driften:

- **(type, url)-De-Duplizierung** existiert zweimal: in `resolve_targets()`
  (lokale `_add`-Closure) und in `resolve_db_targets()` (inline `seen`-Set).
- **Dispatch-Schleife** ist in `notify_breach()` und
  `notify_incident_transition()` identisch: `_resolve_with_store` → `ctx`
  bauen → pro Target Payload formen → `fire_webhook` auf Daemon-Thread.
- **Payload-Former** `_format_payload()` / `_format_transition_payload()`
  teilen die Slack-/Teams-Hüllen (MessageCard-Skelett, `_SEVERITY_COLOR`,
  Link-Zeile).

*Refactor:* gemeinsamer Dedup-Helper + ein `_dispatch(targets, ctx, formatter,
settings)`. Reine Strukturänderung — **kein** Verhaltens-/Payload-Unterschied,
der SSRF-Pfad über `fire_webhook` bleibt unangetastet, und `test_notify.py`
bleibt unverändert grün.

---

## R — Healing-Restoptionen (zu evaluieren) ◻ [M/L]

**Quelle:** [`Konzept_Manuelles_Healing.md`](Konzept_Manuelles_Healing.md).
**Umgesetzt (2026-08):** **H1** (Parkbucht-Korrektur mit Schattenspalten,
`P_DQ_CORRECT_ROW`, Episode-Re-Check, Vier-Augen bei Contract-Kinds) und **H3**
(Patch-Overlay `DQ_PATCH_<OBJ>` + `V_DQ_HEALED_<OBJ>`, TTL/Rücknahme) — beide
über die Healing-Workbench (`/healing`, API `/api/healing`). Die folgenden
Optionen sind bewusst **noch nicht gebaut** und vor einer Umsetzung zu bewerten:

- **R1 · H2 — Fix-at-Source als geführter Flow.** `[M]` ◻ — die fachliche
  Default-Haltung, heute nur implizit: Incident → Owner → Korrektur an der
  Quelle → Re-Extract/Re-Run als Verifikation. Zu evaluieren ist die geführte
  Oberfläche (Incident-Aktion „An Quelle beheben" mit Verifikations-Run und
  Status-Rückmeldung), nicht der Mechanismus — Bausteine existieren alle.
  *Aufwand laut Konzept:* ~1–2 PT, reine Workflow-/UI-Schicht.
- **R2 · H4 — Geführter Reprocess (Wiedereinspeisung).** `[M]` ◻ — korrigierte
  Zeilen per `INSERT … SELECT` in den Ziel-Flow zurückführen; gibt dem
  vorhandenen `confirm-reprocess`-Übergang seinen technischen Unterbau.
  **Hängt an F-Slice ⑦** (Task-Chain-Vorlagen) und den Live-Spikes O5/O6 —
  nicht vor deren Klärung planen.
- **R3 · H5 — Regel-Healing als expliziter Triage-Ausgang.** `[L/M]` ◻ —
  Incident-Drawer-Ausgang „False Positive → Schwelle prüfen" mit Deep-Link in
  Workbench/Backtest plus Resolve-Kategorie `false_positive`; liefert die
  False-Positive-Quote je Garantie als Kalibrier-Feedback (ergänzt V1
  Backtesting). Billigster der drei, aber ohne reale Incident-Volumina
  wenig aussagekräftig — deshalb bewusst nachgelagert.
- **R4 · Offene Entscheidungen (Konzept §8 e/f/j).** ◻ — Cockpit-Zeilen-Grid
  hinter dem G8-Gate vs. heutige formularbasierte Korrektur; **Kollisionsregel
  Patch × neue Quell-Lieferung** (Patch gewinnt vs. Lieferung gewinnt +
  Re-Open) und Patch-TTL-/Review-Pflicht — beides **vor produktivem
  H3-Einsatz** zu klären; Live-Verifikation von `P_DQ_CORRECT_ROW`, Re-Check
  und Healed-View am echten Tenant (mit O5/O6 bündeln).

> **Aus der Konzept-Konsolidierung 2026-08-03 (§5):** Die Umsetzung ist die
> *konservative Teilmenge* des Proposals von 2026-07. Zwei Punkte sind echte
> Lücken, kein bewusster Verzicht — sie stehen als R5/R6 hier, nicht im
> Fließtext eines Konzepts.

- **R5 · Opt-in-Leiter für Healing nachziehen.** `[H]` ◻ — **vor produktivem
  Einsatz.** Heute entscheidet allein die Rolle, ob und was korrigiert werden
  darf. Es fehlen: ① eigener Kill-Switch `QUARANTINE_HEALING_ENABLED`
  (Default aus, Muster wie `ENFORCEMENT_MATERIALIZE_ENABLED`) — Healing
  schreibt Nutzdaten und verdient einen eigenen Betriebsschalter neben der
  Materialisierung; ② Contract-Policy `quarantine.healing` mit
  **Spalten-Allowlist** (validator-geprüft, S2-Identifier) statt „jede
  Nicht-Systemspalte korrigierbar"; ③ Vier-Augen als konfigurierbare Policy
  (heute fest an für Contract-Kinds, fest aus für `internal_gate`).
  *Bauplan:* `Konzept_Manuelles_Healing.md` §6.1/§6.2. *Governance:* steht auf
  der O10-Auflagen-Checkliste.
- **R6 · Per-Zeile-Mechanik + SQL-Healing.** `[M]` ◻ — nach Betriebserfahrung
  mit der schlanken Fassung: Per-Zeile-Zustände (`clean`/`discarded`) statt des
  episodenweiten Re-Check-Zählers — erst damit ist „nur die guten Zeilen
  zurück" möglich; Verwerfen mit Pflicht-Grund; Restore-Aktion (heute existiert
  die Schattenspalte `_DQ_ORIGINAL`, aber keine Rückstell-Aktion);
  optimistisches Locking je Zeile (heute Last-Writer-Wins bei parallelen
  Stewards); SQL-Healing für Massenkorrekturen nach dem Guard-Entwurf
  (`Konzept_Manuelles_Healing.md` §6.3).

---

## T — MVP-Modul-Gating + Stufenrollout ◻ [H]

**Quelle:** [`Konzept_MVP_Kundenrollout.md`](Konzept_MVP_Kundenrollout.md).
Voraussetzung dafür, Signal beim Kunden in Betrieb zu nehmen, **bevor** der
volle Funktionsumfang abgenommen ist: ein Codestand, ein Deployment, vier
Freischalt-Wellen. Die Sicherheits-Gates (G1–G8, S5, PII) sind ausdrücklich
**nicht** Teil des Gatings.

- **T1 · Modul-Registry + Settings.** `[H]` ◻ — `services/api/modules.py`
  (Modul→Welle, Kern-Set) plus `rollout_wave` / `modules_enabled_extra` /
  `modules_disabled` in `settings.py`; unbekannter Modulname ⇒ Startabbruch
  (fail-closed).
- **T2 · Server-Gate.** `[H]` ◻ — `require_module(...)` in `deps.py`, als
  Router-Dependency auf den gegateten Routern; Router bleiben registriert
  (OpenAPI über alle Wellen stabil), gegatete Routen antworten 404
  `problem+json`. Contracts-Router pro Route: Lite = Kern, Full-Pfade
  (`PUT` draft, diff, approve, deprecate, sla, export) hinter
  `contracts_full`; ohne dieses Modul akzeptieren Schreibpfade nur
  `kind: internal_gate` (ADR-0006-konform).
- **T3 · `GET /api/system/features` + FE-Spiegel.** `[H]` ◻ — effektives
  Modulset an das Cockpit; Sidebar-Filter, Routen-Platzhalter „Modul nicht
  aktiviert" (i18n), Workbench ohne Full-Pane. Spiegel ist Komfort —
  autoritativ bleibt der Server. **Schwerpunkt ist der Abhängigkeits-Kontrakt**
  (Konzept §2.5): `ObjectDetail` zieht heute Panels aus `profiling`,
  `schedules`, `proposals`, `enforcement`/`monitoring` und `contracts_full`,
  die Workbench aus `proposals` und `schema_drift` — jedes davon braucht einen
  Guard, und `objectDetailTabs.ts` wird modulabhängig. Kein Kern-Screen darf ein
  fehlendes Modul als Fehler zeigen.
- **T4 · Tests + CI.** `[H]` ◻ — `tests/api/test_module_gating.py` (Welle 0 vs.
  Welle 3, Overrides, Startvalidierung, Contracts-Full-Routen einzeln,
  `certify`-G3-Netz bleibt in Welle 0 scharf), Vitest-Matrix
  `navForRole × features` und je ein Welle-0-Render von Cockpit, ObjectDetail
  und Workbench (kein Fehlerbanner, kein toter Tab). Bestehende Suiten laufen
  unter `ROLLOUT_WAVE=3` unverändert.
- **T5 · Kunden-Runbook Welle 0.** `[M]` ◻ — Deployment-Checkliste (OIDC,
  `ALLOW_MOCK_CONNECTION=false`, read-only Space-User, externes Scheduling,
  SQLite-Volume/Backup) und ENV-Referenz in `Tooldokumentation.md` §6.

> **Abhängigkeit:** SQLite trägt die Pilotlast der Welle 0; **C2**
> (`HanaResultStore`) bleibt der Skalierungspfad und ist keine
> Welle-0-Vorbedingung. Welle 1 hängt am Scheduling-Entscheid (**N**), Welle 3
> an den Live-Tenant-Spikes (**F** ④–⑦, O5/O6) und an **R5**.

---

## Querschnitt-Abhängigkeiten (worauf zuerst)

```
echter CSN-Extract (I3) ──► Live-Verifikation von B ──► OL3 / E3
HanaStore (C2) ═ D1 ──────► C (Full-Deploy) + D (Managed) + F-quarantine/C5
HanaStore (C2) ───────────► N3 (Schedule-Store-Parität)
M1-M6 (Workflow-Audit) ───► Branch-/CI-Wahrheit vor weiterer Produktpolitur
J1 (skip/downgrade) ── Entscheidung vor Freshness-Gating (E2/J)
F ④–⑦ (Zeilen-Quarantäne/Reconciler) ═ C5 ──► braucht Live-Tenant-Spikes (O5/O6)
P5 (BDC/HDLF) ────────────► H / Product-Discovery / technische Load-Lag-Achse
```

**Empfohlene Reihenfolge nach Hebel/Aufwand:** M1/M2/M3/M6
(Workflow-Korrektheit + CI-Wahrheit) → C2/D1 (`HanaStore`, entsperrt
Full+Managed und N3) → I3 (Live-Verifikation Spalten-Lineage) →
J1-Entscheidung → A1. O/N/P/F④–⑦/G/H bleiben nachgelagert, bis Demo- oder
Kundenbedarf sie zieht. (E1/E3, F①–③ und N2 sind seit 2026-07 geliefert;
A2 seit 2026-08.)
