# Zusatz — Entropy Data: Integration, Abgrenzung & Defensibility

**Zweck:** Festhalten der Überlegungen zu **Entropy Data** (vormals *Data Mesh
Manager* / *Data Contract Manager*) als möglichem Integrations-/Partner-Ziel —
inkl. der Frage, was mit Signals Burggraben passiert, falls die `datacontract-cli`
(die Entropy für `datacontract test` nutzt) ein **SAP-HANA-Backend** bekommt.
**Status:** Erkenntnis-/Strategiedokument, *keine* gesetzten Entscheidungen.
**Datum:** 2026-06-23
**Leitregel (unverändert):** YAML-Contract = Source of Truth; jeder Marktplatz/
Katalog = einseitiges Derivat. „Signal erzwingt — der Marktplatz beschreibt.”

---

## 1 — Was Entropy Data ist

Ein **Data-Product-Marktplatz + Contract-/Governance-Registry**: Discovery,
semantische Suche, Access-Requests, Lifecycle-Governance. **Plattform-neutral**
(Snowflake, BigQuery, Databricks, Fabric, Athena …), **ODCS-3.1-nativ** und erstes
Tool mit nativer **ODPS-1.0**-Unterstützung (Open Data *Product* Standard).

**Die entscheidende Eigenschaft:** Entropy Data **führt selbst keine Quality-Checks
aus** — es *ingestiert publizierte Ergebnisse*. Der Ausführungspfad ist
`datacontract test --publish <entropy-endpoint>`; `datacontract test` delegiert an
**Soda Core / Great Expectations**, Resultate erscheinen in der „Data Quality”-
Sektion des Contracts im Marktplatz.

Und (aus `docs/datacontract-cli_Integration.md` §F7 bestätigt): **`datacontract
test` hat heute kein SAP-HANA-Backend** (Engines: Snowflake/BigQuery/Databricks/
Postgres/S3/Kafka). Entropys Default-Weg, „grün” zu beweisen, erreicht eine
HANA/Datasphere-Fläche also strukturell nicht.

---

## 2 — Verdikt: komplementär, nicht konkurrierend

Auf die Lifecycle-Tabelle aus `docs/Zusatz_ContractLifecycle_ORDBDCIntegration.md`
§3 gemappt:

| Lifecycle-Hälfte | Owner | Begründung |
|---|---|---|
| **Links** — Marktplatz, Discovery, Access-Requests, Consumer-Sign-off, Versionierung/Lifecycle | **Entropy Data** | Sein Kern — und Signals *dokumentierte schwache Hälfte* (Zusatz-Doc markiert Consumer-Rolle + Deprecation als ✗) |
| **Rechts** — Checks gegen HANA ausführen, erzwingen, zertifizieren | **Signal** | Der HANA-native Executor, den Entropy *wegdelegiert* und für SAP nicht kann |

→ Signal positioniert sich als **„das SAP/HANA-Quality-Backend für euren Entropy-
Data-Marktplatz”**: es erzeugt das verifizierte Grün, das Entropy *anzeigt*, aber
für SAP-Quellen nicht selbst generieren kann.

---

## 3 — Der Integrations-Seam (besteht großteils schon)

- **Contract-Registrierung:** `to_odcs()` emittiert ODCS 3.1 → Entropy ingestiert
  ODCS 3.1 nativ. Einseitiges Derivat, gleiches Muster wie alles andere.
- **Result-Publishing:** Entropy hat eine Result-Ingest-API (der `--publish`-
  Endpoint → „Data Quality”-Sektion). Signal ergänzt einen dünnen Publisher —
  **architektonisch identisch zum OpenLineage-Emitter** (`services/`, konsumiert
  `RunSummary`/`CheckResult`, opt-in, fail-open). Tendenziell **besseres Erst-Ziel
  als generisches OpenLineage**, weil Entropy Signals exakte Vokabel spricht
  (ODCS/ODPS), nicht nur Lineage.
- **Produkt-Ebene:** Signals Product-Manifest (`products/<name>.yaml`) → **ODPS
  1.0** — der produktseitige Analog zum ODCS-Contract-Seam.

---

## 4 — Überlappung (ehrlich)

Beide haben eine Contract-Authoring-UI und eine Quality-Status-Fläche (Signals
Cockpit/Workbench + Compliance-Ampel vs. Entropys Marktplatz + Data-Quality-
Sektion). Adoptiert ein Kunde Entropy als Marktplatz, tritt Signals „Cockpit-als-
Marktplatz”-Ambition zurück. Da diese überlappende Schicht (Authoring,
Versionierung, Consumer-Access, Deprecation) aber genau Signals **anerkannt schwache
Hälfte** ist: **abtreten, nicht bekämpfen** — Entropy = Schaufenster, Signal =
Enforcement-Engine dahinter.

---

## 5 — Die eine echte Entscheidung: Contract-Source-of-Truth

Beide sind Contract-Registries → Spannung mit Signals Invariante *„YAML = SoT”*.
Zwei saubere Auflösungen, je Kunde wählbar:

1. **Signal authort → Entropy zeigt** (Signal-YAML bleibt SoT, exportiert ODCS +
   Ergebnisse zu Entropy). Default, deckt sich mit der Einweg-Derivat-Regel.
2. **Entropy authort → Signal erzwingt** (Signal konsumiert ODCS als Input, fährt
   es gegen HANA, publiziert Ergebnisse zurück). Für Kunden, die schon auf Entropy
   standardisiert sind.

**Nicht** bidirektional synchronisieren — gleiche Falle, die bei ORD vermieden
wurde.

---

## 6 — Defensibility: „Was, wenn die CLI HANA lesen könnte?”

Realistisches Szenario (kein Hirngespinst): ein HANA-Backend ist im Kern nur ein
SQLAlchemy/`hdbcli`-Dialekt; Soda/GX sind connector-basiert. Angenommen
`datacontract test` bekommt `type: hana`.

### 6a — Was es Signal *wegnimmt*
Genau **eine** Linie: „nur wir können einen Check gegen HANA fahren”. Generische
Checks (not-null, unique, row-count, freshness, custom-SQL) liefen dann direkt
gegen HANA, ohne Signal. **Der Transport würde kommoditisiert.** Wäre Signals Pitch
*nur* „wir führen Checks auf HANA aus”, würde er schwächer.

### 6b — Was *überlebt* (die Substanz)
Der Wert lag nie im Connector, sondern in vier Dingen, die ein CLI-Backend nicht
repliziert:

1. **SQL-freies Garantie→Compiler-Modell (G1).** datacontract test verlangt
   handgeschriebenes SodaCL/SQL in `quality:` — genau das, was G1 verbietet. Signals
   Substanz: *semantische Garantie rein → deterministischer Compiler erzeugt SQL aus
   `check_library.json` → kein SQL im Contract*. Ein HANA-Backend macht die CLI nicht
   zu diesem Modell; sie bleibt „du codierst die Checks selbst” — ein anderes,
   assurance-ärmeres Produkt.
2. **SAP-Domänen-Bibliothek.** `sap_bseg_balance`, `sap_bkpf_orphan`,
   `sap_fiscal_completeness`, `sap_replication_lag`, `sap_key_plausibility` kodieren
   SAP-ERP/Datasphere-Semantik (BSEG/BKPF-Struktur, `M_TABLE_STATISTICS`,
   `SYS.TABLE_COLUMNS`). Ein generisches Backend gibt die *Fähigkeit, SQL zu fahren* —
   nicht *diese Checks*. SAP-Wissen muss weiter jemand autoren/pflegen → Domänen-IP,
   kein Connector.
3. **Read-only + PII-Gate (G8) + Single-Executor-Posture.** Signal fährt lesend,
   Rohzeilen verlassen HANA nie ohne Freigabe, Ergebnisse getrennt. Ein generischer
   Soda/GX-Runner auf HANA hat nichts davon → „externe Test-Engine fragt eure HANA ab”
   ist im SAP-Haus ein **Security-Review-Problem**. Die gegatete, lesende Posture ist
   selbst Moat.
4. **Kontinuierliche Observability.** datacontract test = **punkt-in-zeit CI-Gate**.
   Signal = Laufzeit: Rolling-Baselines, Proposal-Miner, Compliance-Ampel, SLA-Fenster,
   Incident-Timeline, Run-Historie. Auch mit HANA bleibt die CLI ein PR-Pass/Fail, kein
   lebendiges Cockpit (die „rechte Hälfte” aus dem Lifecycle-Doc).

### 6c — Strategische Konsequenz (Leitlinie)
**Signal darf seinen Wert NICHT am HANA-Connector verankern** — der ist
commoditisierbar. Verankerung an: (1) SQL-freies Compiler-Modell, (2)
SAP-Check-Bibliothek, (3) read-only/PII-Governance, (4) kontinuierliche
Observability. Diese vier nimmt ein Backend-Patch nicht weg.

### 6d — Wirkung auf die Entropy-Beziehung
Die komplementäre These **überlebt, die Grenzlinie verschiebt sich nur**: Entropy/CLI
deckt den *einfachen* HANA-Check-Fall in CI ab; Signal besitzt den *SAP-spezifischen,
gegateten, kontinuierlichen* Fall. Der einfache Fall war nie, wo Signals Wert
konzentriert war. Es gibt sogar einen **Embrace-Move**: das HANA-Backend begrüßen
(oder mitbeitragen) — generische Checks via datacontract test im CI, Signal übernimmt
SAP-Spezialitäten + Governance + Runtime. Senkt die Integrationsreibung zu Entropy,
statt sie zu erhöhen.

---

## 7 — Offene Punkte

> **Umsetzungsstand (2026-07-23):** Der Seam ist als **opt-in, fail-open**-
> Integration gebaut — architektonisch wie der geplante OpenLineage-Emitter und
> die Enforcement-Materialisierung. Neue Bausteine:
> - **Result-/Contract-Publisher** `services/api/entropy.py` (G7-neutral,
>   SSRF-sicher über die `webhook.py`-Guards, Bearer-Token). Hängt am
>   Run-Abschluss (`routers/objects.py`) und an manuellen Endpunkten.
> - **ODCS→Signal-Import** `packages/dq_core/contract/odcs_import.py`
>   (`from_odcs`, framework-frei, G1: nur Garantien, SQL-Regeln landen in
>   `dropped`). API: `POST /api/integrations/entropy/import/odcs`.
> - **ODPS-1.0-Export** `packages/dq_core/product/odps_export.py`
>   (`to_odps`). API: `GET /api/products/{name}/export/odps`.
> - **Settings** `ENTROPY_PUBLISH_ENABLED/URL/TOKEN/ALLOWLIST`,
>   `ENTROPY_SOURCE_OF_TRUTH` (E1-Routing), `ENTROPY_MARKETPLACE_VERIFIED`
>   (E2/E3-Flag). Status-Panel in den Cockpit-Einstellungen.
>
> **Wichtiger Vorbehalt (Best-Guess-Routing):** Solange
> `ENTROPY_MARKETPLACE_VERIFIED` false ist — d. h. bis die reale Entropy-API in
> Form/Auth gegenverifiziert ist — läuft **jeder Publish als Dry-Run** (Payload
> gebaut, nicht gesendet), und ODPS-Dokumente tragen `x-signal-validation:
> unverified`. So ist die Integration Ende-zu-Ende testbar, ohne gegen einen
> unbestätigten Endpunkt/Standard zu schreiben. Das Wire-Format (`_PAYLOAD_SPEC
> = "signal-entropy/0.1-unverified"`) ist bewusst als vorläufig markiert.

- **E1 [H]** — Source-of-Truth-Modus je Kunde (§5): Signal-authort vs.
  Entropy-authort. **Adapter beidseitig gebaut** (Export via `to_odcs`, Import
  via `from_odcs`, Routing via `ENTROPY_SOURCE_OF_TRUTH`, nie bidirektional);
  mit echtem Kunden noch zu validieren, bevor festgeklopft.
- **E2 [H]** — Entropy Result-Ingest-API: genaue Form/Auth des `--publish`-Endpoints,
  Mapping `RunSummary`/`CheckResult` → Entropy-Quality-Payload. **Mapping gebaut
  (Best-Guess-Payload), Dispatch hinter dem `verified`-Flag als Dry-Run** — die
  echte API/Docs (Architektur-Doc war beim Sichten HTTP 403) bleiben zu verifizieren.
- **E3 [M]** — ODPS-1.0-Mapping: Product-Manifest → ODPS. **Export gebaut,
  flagged `unverified`**; Verlustfreiheit/Custom-Extensions gegen einen realen
  Marktplatz noch offen.
- **E4 [M]** — Überlappungs-Politik: in welchen Deals tritt Signal die Authoring-/
  Marktplatz-Schicht aktiv an Entropy ab (§4) — Messaging/Positionierung festlegen.
- **E5 [L]** — Embrace-Move (§6d): HANA-Backend zur datacontract-cli beitragen? Nur
  generische Checks, Signals SAP-Checks bleiben proprietär.

---

## 8 — Anker-Referenzen

| Baustein | Datei / Stelle |
|---|---|
| ODCS-Export (Registrierungs-Seam) | `packages/dq_core/contract/odcs_export.py` → `to_odcs()` |
| Result-Modell (Quelle Quality-Publish) | `packages/dq_core/engine/models.py` → `RunSummary`, `CheckResult` |
| Emit-Architektur-Vorbild | `docs/Scope_OpenLineage_Emitter.md` (services/, opt-in, fail-open) |
| SAP-Check-Bibliothek (Domänen-IP) | `packages/dq_core/library/check_library.json` |
| G1 (kein SQL im Contract) / G8 (PII-Gate) | `README.md` §Sicherheits-Leitplanken |
| `datacontract test` ohne HANA-Backend | `docs/datacontract-cli_Integration.md` §F7 |
| Lifecycle-Hälften-Modell | `docs/Zusatz_ContractLifecycle_ORDBDCIntegration.md` §3 |
