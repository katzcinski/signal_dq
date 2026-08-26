# docs/ — Index & Status

**Stand:** 2026-07-23 · Vollständiger Index über alle Dokumente in `docs/`, mit
Status-Klassifikation. Kurzfassung/Einstieg: [`../README.md`](../README.md).

**Leseregel bei Konflikten:** Der Code gewinnt. Danach gilt:
[`Tooldokumentation.md`](Tooldokumentation.md) (implementierter Stand) >
[`OPEN_TASKS.md`](OPEN_TASKS.md) (aggregierter Backlog-Status) > Konzepte/Pläne >
historische Handovers/Reviews. Historische Dokumente werden **nicht** mehr
nachgepflegt; wo ein Quelldoc noch „offen"/„nicht implementiert" sagt, gilt der
Status in `OPEN_TASKS.md` bzw. der Banner im Dokumentkopf.

## Referenz (aktiv gepflegt)

| Dokument | Inhalt |
|---|---|
| [`Tooldokumentation.md`](Tooldokumentation.md) | **Vollständige Referenz des implementierten Stands** — Architektur, Datenmodell, API, ENV, CLI, Frontend, Gates, Deployment |
| [`OPEN_TASKS.md`](OPEN_TASKS.md) | Konsolidierter Backlog über alle Bereiche; ersetzt die Backlog-Listen der Einzeldokumente |
| [`Betriebsmodi_Lite_und_Full.md`](Betriebsmodi_Lite_und_Full.md) | Lite vs. Full — Prozess, Personas, Tooling |
| [`Checks_Statuses_Flows.md`](Checks_Statuses_Flows.md) | Wie Signal über Objekte urteilt: Checks, Status-Achsen, Flows |
| [`TOOLTIP_CATALOG.md`](TOOLTIP_CATALOG.md) | Tooltip-/Begriffskatalog fürs Cockpit |
| [`Datenfluesse_Quelle_vs_Signal.md`](Datenfluesse_Quelle_vs_Signal.md) | **Datenfluss-Landkarte** — welche Daten aus der Quelle, welche aus Signals eigenen Tabellen/Views; Zonen-Modell, Quarantäne- und Healing-Pfade (Diagramme) |

## Architektur-Entscheidungen (ADRs)

Nummern sind eindeutig; zwei ADRs wurden 2026-07 wegen Nummern-Kollision
umnummeriert (Hinweis jeweils im Dokumentkopf).

| ADR | Inhalt | Status |
|---|---|---|
| [`ADR-0001_Quality-Gates_vs_Contracts.md`](ADR-0001_Quality-Gates_vs_Contracts.md) | `kind`: internes Quality Gate vs. Contract | umgesetzt (Batch 1–5) |
| [`ADR-0002_Datasphere-DB-Zugriff.md`](ADR-0002_Datasphere-DB-Zugriff.md) | DB-Identität: technischer Space-User, read-only; Amendment (Schreiben nur im Signal-Schema) in `Konzept_Datasphere_Integration_…` §2 | proposed; Amendment implementiert |
| [`ADR-0003_BDC-Datasphere-DataProductStudio.md`](ADR-0003_BDC-Datasphere-DataProductStudio.md) | Signal im BDC/Datasphere-Setup (HDLF vs. SQL-Output-Port) | Konzept/angenommen, Verifikation offen (`OPEN_TASKS` P5) |
| [`ADR-0004_DataProduct-als-Komposition.md`](ADR-0004_DataProduct-als-Komposition.md) | Datenprodukt als Komposition über Lineage | umgesetzt (Phase 1); Phase 2 = `OPEN_TASKS` P |
| [`ADR-0005_Scheduling.md`](ADR-0005_Scheduling.md) | Scheduling extern (Task-Chain/Cron) vs. intern (Poller, Option E) | umgesetzt; Phase 2 = `OPEN_TASKS` N |
| [`ADR-0006_Editor-Modus_aus_Kind.md`](ADR-0006_Editor-Modus_aus_Kind.md) | Editor-Modus (Lite/Full) aus dem `kind` ableiten — **früher „ADR-0002"** | umgesetzt (Batch 6) |
| [`ADR-0007_Generic-Operation-Progress-Channel.md`](ADR-0007_Generic-Operation-Progress-Channel.md) | Generischer Operation-/Progress-Kanal — **früher „ADR-0005"** | umgesetzt (Migration 008, `/api/operations`) |

## Konzepte (fachlich/technisch)

| Dokument | Inhalt | Status |
|---|---|---|
| [`Konzept_MVP_Kundenrollout.md`](Konzept_MVP_Kundenrollout.md) | **Erster Wurf beim Kunden** — MVP-Zuschnitt (Welle 0: DQ-Checks, Contracts Lite, Runs, Cockpit/Coverage), Modul-Gating (`ROLLOUT_WAVE`) und Stufenrollout der übrigen Module | Konzept (zur Umsetzung) |
| [`Konzept_DQ_Observability_Cockpit.md`](Konzept_DQ_Observability_Cockpit.md) | Fachliches Gesamtkonzept | Grundlage, weitgehend umgesetzt |
| [`Konzept_DQ_Cockpit_UIUX.md`](Konzept_DQ_Cockpit_UIUX.md) | UI/UX-Zielbild | Grundlage, weitgehend umgesetzt |
| [`Konzept_Enforcement_Modi_Gate_Quarantine_Monitor.md`](Konzept_Enforcement_Modi_Gate_Quarantine_Monitor.md) | Durchsetzungs-Achse `gate \| quarantine \| monitor` | **umgesetzt** (Slices ①–③) |
| [`Konzept_Datasphere_Integration_Gating_Quarantaene.md`](Konzept_Datasphere_Integration_Gating_Quarantaene.md) | Gating & Quarantäne in Datasphere-Pipelines (Open-SQL-Materialisierung) | in Umsetzung: ①–③ implementiert, ④–⑦ offen |
| [`Konzept_Observability_Intelligence_v1.md`](Konzept_Observability_Intelligence_v1.md) | Baselines, Segmente, RCA, Clustering (Tier 1) | **umgesetzt** (Migrationen 010–015) |
| [`Konzept_ShiftLeft_DataDiff_v1.md`](Konzept_ShiftLeft_DataDiff_v1.md) | Schema-Drift der Quelle + Data-Diff (Tier 2) | **umgesetzt** inkl. Screen `/schema-drift` (A2, 2026-08) |
| [`Konzept_Runs_Freshness.md`](Konzept_Runs_Freshness.md) | Run-/Load-Info als Freshness-Achse | teilweise; Entscheidungen offen (`OPEN_TASKS` J) |
| [`Konzept_Manuelles_Healing.md`](Konzept_Manuelles_Healing.md) | **Maßgebliche Healing-Referenz** — Optionen H1–H5, Umsetzungsstand, Abweichungen vom Proposal 2026-07, Mechanik-Bauplan (Opt-in-Leiter, Allowlist, SQL-Guard) | **H1+H3 umgesetzt** (Workbench `/healing`); Rest = `OPEN_TASKS` R |
| [`Konzept_Managed_Service_Provisioning.md`](Konzept_Managed_Service_Provisioning.md) | Managed Service: Provisionierung, Tenant-Isolation | Konzept (`OPEN_TASKS` D) |
| [`Konzept_MultiPlattform_Executor_BDC.md`](Konzept_MultiPlattform_Executor_BDC.md) | Executor für HANA · HDLF · Databricks | Konzept (`OPEN_TASKS` H) |
| [`Konzept_Meridian_Inventory_Integration.md`](Konzept_Meridian_Inventory_Integration.md) | Meridian-Inventar als Admin-Tool | Konzept |
| [`Scope_OpenLineage_Emitter.md`](Scope_OpenLineage_Emitter.md) | OpenLineage-Emitter | Scope, keine Implementierung (`OPEN_TASKS` G) |
| [`Spec_Lineage_UX_Redesign.md`](Spec_Lineage_UX_Redesign.md) | Lineage-UX (Kamera, Knoten, Inspektion) | Phase 1–2 umgesetzt; Phase 3 = `OPEN_TASKS` O |
| [`TECH_CONCEPT_C2_HanaStore.md`](TECH_CONCEPT_C2_HanaStore.md) | `HanaStore`-Implementierungskonzept | Konzept (`OPEN_TASKS` C2) |
| [`datacontract-cli_Bewertung.md`](datacontract-cli_Bewertung.md) · [`datacontract-cli_Integration.md`](datacontract-cli_Integration.md) · [`datacontract-cli_Hypothese_VollerErsatz.md`](datacontract-cli_Hypothese_VollerErsatz.md) | `datacontract-cli`: Bewertung, Integrationspfad (Second-Opinion-CI-Job umgesetzt), Ersatz-Hypothese (Empfehlung: nicht ersetzen) | Evaluierung |
| [`Zusatz_ContractLifecycle_ORDBDCIntegration.md`](Zusatz_ContractLifecycle_ORDBDCIntegration.md) | ORD/ODCS-Seam, BDC-Catalog | Evaluierung |
| [`Zusatz_EntropyData_Integration_und_Defensibility.md`](Zusatz_EntropyData_Integration_und_Defensibility.md) | Entropy-Data-Abgrenzung/Defensibility | Evaluierung |

## Pitch, Markt & Geschäft

| Dokument | Inhalt |
|---|---|
| [`Investment_Case_Signal.md`](Investment_Case_Signal.md) | Investment Case (Partner-Runde) |
| [`Marktanalyse_DQ_Observability_2026.md`](Marktanalyse_DQ_Observability_2026.md) | Feature-Gap-Synthese Markt 2026 (Quelle der Tier-1/2-Konzepte) |
| [`Kundendeck_DataProducts_Lite.md`](Kundendeck_DataProducts_Lite.md) | Kundenpitch Data Products Lite |
| [`interactive/kundenpitch-datasphere-bdc.html`](interactive/kundenpitch-datasphere-bdc.html) | **Kundenpitch Welle 0** (HTML) — was Signal im ersten Wurf leistet und warum das mit Datasphere/BDC zusammenpasst; Scope aus `Konzept_MVP_Kundenrollout.md` |
| [`Vortrag_Briefing_DataProducts_DataContracts_DSP_BDC.md`](Vortrag_Briefing_DataProducts_DataContracts_DSP_BDC.md) | Vortrags-Briefing |
| [`Uebergabemodelle_und_Lizenz.md`](Uebergabemodelle_und_Lizenz.md) | Übergabemodelle & Lizenz |
| [`DataProduct_Konzept_und_Handling.md`](DataProduct_Konzept_und_Handling.md) | Datenprodukte: Konzept & Workflow (Beratungs-Sicht) |
| [`interactive/`](interactive/) · [`DataProduct_Interaktiv.html`](DataProduct_Interaktiv.html) | Interaktive HTML-Artefakte (Delivery-Offering, Data-Product-Story) |

## Historisch (abgeschlossen oder überholt — nicht mehr nachgepflegt)

Implementierungspläne, Handovers und Reviews. Ihr Backlog-Anteil ist in
`OPEN_TASKS.md` konsolidiert; „offen"-Aussagen in diesen Dateien sind nicht
maßgeblich.

| Dokument | Inhalt / Ausgang |
|---|---|
| [`HANDOVER.md`](HANDOVER.md) | Ursprünglicher technischer Implementierungsplan (Workstreams, Gates) — umgesetzt; Rest-Spikes O1–O7 in `OPEN_TASKS` K |
| [`PLAN_Remediation_v2.md`](PLAN_Remediation_v2.md) | Remediation R0–R6 — umgesetzt |
| [`Implementation_Batch1_Nav_Restructure.md`](Implementation_Batch1_Nav_Restructure.md) … [`Batch6`](Implementation_Batch6_Mode_Kind_Defaulting.md) | Batches 1–6 zum `kind`-Diskriminator — umgesetzt |
| [`Implementation_HANA_Connection_Progress.md`](Implementation_HANA_Connection_Progress.md) | HANA-Connection-Pfad: WS A–D/F5 geliefert; WS E/F (HanaStore) offen → `OPEN_TASKS` C |
| [`HANDOVER_Observability_Intelligence_v1_Implementation.md`](HANDOVER_Observability_Intelligence_v1_Implementation.md) | Grill-Entscheidungen Obs-Intelligence v1 — umgesetzt |
| [`HANDOVER_Observability_Quarantaene_Orchestrierung.md`](HANDOVER_Observability_Quarantaene_Orchestrierung.md) | Quarantäne/Orchestrierung — Gating-Teil umgesetzt (Slices ①–③); Rest offen |
| [`HANDOVER_SLA_Panel.md`](HANDOVER_SLA_Panel.md) | SLA-Panel — umgesetzt |
| [`HANDOVER-meridian-port.md`](HANDOVER-meridian-port.md) | Meridian-Port — Restpunkte in `OPEN_TASKS` I |
| [`CODEX_HANDOVER_TrackA_Phase1.md`](CODEX_HANDOVER_TrackA_Phase1.md) | Data-Product-Aggregat Phase 1 — umgesetzt |
| [`handover-iteration-1-internal-checks.md`](handover-iteration-1-internal-checks.md) | Interne Check-Library im Builder — umgesetzt |
| [`workbench-ux-implementation-handover.md`](workbench-ux-implementation-handover.md) · [`workbench-ux-proposal.html`](workbench-ux-proposal.html) · [`workbench-redesign-proposal.html`](workbench-redesign-proposal.html) | Workbench-UX-Redesign — umgesetzt; Proposal-Banner-Rest in `OPEN_TASKS` M4 |
| [`PLAN_UX-N7_Column_Lineage.md`](PLAN_UX-N7_Column_Lineage.md) | Spalten-Lineage — umgesetzt (`OPEN_TASKS` B) |
| [`PLAN_Observability_Mehrwert_v1.md`](PLAN_Observability_Mehrwert_v1.md) | Obs-Mehrwert — teilweise umgesetzt (`OPEN_TASKS` E) |
| [`PLAN_Managed_Service_v1.md`](PLAN_Managed_Service_v1.md) | Managed Service v1 — offen (`OPEN_TASKS` D) |
| [`PLAN_ADR-0003-0004_Implementation.md`](PLAN_ADR-0003-0004_Implementation.md) | ADR-0003/0004-Umsetzung — Phase 1 geliefert; Phase 2 = `OPEN_TASKS` P |
| [`PLAN_Workflow_Audit_2026-06-30.md`](PLAN_Workflow_Audit_2026-06-30.md) · [`WORKFLOW_AUDIT_2026-06-30.md`](WORKFLOW_AUDIT_2026-06-30.md) | Workflow-Audit + Plan — Follow-ups = `OPEN_TASKS` M |
| [`REVIEW_Implementierungsplan.md`](REVIEW_Implementierungsplan.md) · [`REVIEW_Tool_v1_Befunde.md`](REVIEW_Tool_v1_Befunde.md) · [`REVIEW_Tool_v2_Status.md`](REVIEW_Tool_v2_Status.md) | Plan-/Tool-Reviews v0.1–v2 — historisch |
| [`REVIEW_Observability_Quarantaene_Orchestrierung_2026-07-08.md`](REVIEW_Observability_Quarantaene_Orchestrierung_2026-07-08.md) | Review Obs/Quarantäne/Orchestrierung — Grundlage der Slices |
| [`Konzept_Quarantaene_Healing.md`](Konzept_Quarantaene_Healing.md) | Healing-Proposal 2026-07 (Zeilen-Grid, SQL-Healing, Opt-in-Leiter) — **aufgegangen in** `Konzept_Manuelles_Healing.md`; bleibt als Bauplan für `OPEN_TASKS` R5/R6 |
| [`REVIEW_UI_Konsistenz_Hauptseiten_2026-07.md`](REVIEW_UI_Konsistenz_Hauptseiten_2026-07.md) | UI-Konsistenz-Befund 2026-07 |
| [`cockpit-vision-d-statusquo-perfektioniert.html`](cockpit-vision-d-statusquo-perfektioniert.html) · [`theme-previews/`](theme-previews/) | Design-Explorationen (HTML) |
