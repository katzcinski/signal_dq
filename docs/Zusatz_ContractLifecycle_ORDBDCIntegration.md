# Zusatz — Contract-Lifecycle, ORD & BDC-Catalog-Integration

**Zweck:** Festhalten der Erkenntnisse aus der Diskussion zu Data-Contract-Lifecycle, Rollen,
`datacontract-cli`/ODCS und ORD — als Grundlage für die spätere Evaluierung der Integration
von Cockpit/Tool mit dem BDC-Catalog und den ORDs der Datenprodukte.
**Status:** Erkenntnis-/Evaluierungsdokument, *keine* gesetzten Entscheidungen. Offene Punkte
explizit markiert.
**Datum:** 2026-06-09
**Scope:** Seam zwischen (a) unserem semantischen YAML-Contract + Cockpit-Enforcement und
(b) der SAP-nativen Beschreibung/Discovery via ORD/CSN im BDC-Catalog.

-----

## 1 — Kontext & Abgrenzung (die wichtigste Unterscheidung)

Zwei Dinge werden leicht verwechselt und sind sauseinanderzuhalten:

- **Schema-Drift (Obs-Check O3)** — *daten-seitig*. Diff zweier `inventory.json`-Snapshots:
  „hat sich die physische Tabelle seit dem letzten Lauf geändert?” → **vorhanden** im Cockpit.
- **Breaking-Diff** — *vertrags-seitig*. Diff zweier Contract-*Versionen*: „hat sich die Spec
  Version-zu-Version inkompatibel geändert?” → **nicht vorhanden** (nur `contract_version`-Feld,
  keine Versions-Diff, keine SemVer-Policy, kein PR-Gate). **Größte offene Lücke.**

-----

## 2 — Drei-Schichten-Modell (verfeinert)

|Schicht                 |Was sie trägt                                                                                                              |Rolle                                                              |Enforcement?     |
|------------------------|---------------------------------------------------------------------------------------------------------------------------|-------------------------------------------------------------------|-----------------|
|**CSN**                 |Feld-/Strukturebene (das Schema, Feld-Annotations)                                                                         |Feld-Shape                                                         |nein             |
|**ODCS (Data Contract)**|Schema + Quality + SLA + Rollen + Terms                                                                                    |die *Vereinbarung*; Heimat der Breaking-*Erkennung*                |via Cockpit      |
|**ORD**                 |DataProduct: `inputPorts`/`outputPorts`/`entityTypes` + `version`/`releaseStatus`/`successors` + Custom Capabilities/Labels|*strukturell-topologischer* Contract-Surface; Discovery/Publikation|nein (deskriptiv)|

**Korrektur ggü. erster Einschätzung:** ORD ist *nicht nur* „Katalog/wo liegt es”. Über
`inputPorts`/`outputPorts`/`entityTypes` beschreibt ORD die **Interface-Topologie** des
Datenprodukts — welche API-/Event-Resource bzw. welcher Consumption-Endpoint ausliefert, woraus
gespeist wird, um welche fachlichen Entitäten es geht. Das ist der nächstliegende SAP-native
„veröffentlichte Product-Contract”.

**Aber die Grenze bleibt:** Ports tragen Topologie + Zugriff + Schema-*Referenz* + Version/Status.
Sie tragen **nicht** die durchsetzbaren Garantien (Freshness-SLA, Completeness-%,
Verteilungsgrenzen, Retention, Quality-Rules, Terms). Das Schema wird *durch* den Port
referenziert, nicht im Port garantiert.

**Echter Overlap = genau einer: das Schema.** outputPort referenziert ein Schema, der Contract
beschreibt auch ein Schema. → Aufgelöst durch die gesetzte Regel: **YAML-Contract = Source of
Truth; ORD/CSN = einseitige Derivate.** „BDC beschreibt — das Cockpit erzwingt.”

-----

## 3 — Lifecycle-Abdeckung (State-of-the-Art-Referenz: ODCS / Data-Mesh)

|Stufe                                         |Status|Anmerkung                                                             |
|----------------------------------------------|------|----------------------------------------------------------------------|
|Authoring/Definition                          |✓     |Draft-Seed + Workbench                                                |
|Versionierung                                 |◐     |Feld vorhanden, kein Versions-Lifecycle/SemVer-Policy                 |
|Validierung bei Änderung (lint + breaking, CI)|✗     |**die Lücke** — Detektion fehlt                                       |
|Consumer-Sign-off / Negotiation               |✗     |Consumer nur read-only (bekommt Compliance-Status)                    |
|Publikation/Discovery                         |◐     |über einseitige CSN/ORD-Derivate                                      |
|Enforcement/Runtime                           |✓✓    |GX gegen HANA, Gating, Obs+Quality                                    |
|Monitoring/Certification                      |✓✓    |`dq_object_status`, draft/active/breached                             |
|Feedback/Evolution                            |✓     |Proposal-Miner aus wiederkehrenden Anomalien                          |
|Deprecation/Sunset                            |✗ → ◐ |im Cockpit nicht modelliert; **ORD liefert die native Vokabel** (s.u.)|

Stärke des Cockpits: die *rechte* Hälfte (Definition → Compile → Certify → Evolve).
Schwäche: die *linke* Hälfte (Versions-/Breaking-Governance, Consumer-Rolle, Deprecation).

-----

## 4 — Schlüssel-Erkenntnisse

- **`datacontract-cli` = richtiges Werkzeug, aber nur als statisches CI-Gate.**
  `breaking`/`diff`/`changelog`/`lint` arbeiten rein auf der YAML (kein DB-Zugriff), CI-tauglich
  (Non-Zero-Exit bei Bruch). Internes Modell ist inzwischen **ODCS v3** (Open Data Contract
  Standard); Diff/Breaking operieren auf der `models`-Sektion.
- **Kein Executor-Ersatz: `datacontract test` unterstützt SAP HANA nicht** (Engines:
  Snowflake/BigQuery/Databricks/Postgres/S3/Kafka/… — HANA fehlt). Einsatz als Executor würde
  das „single executor”-Prinzip brechen → strikt auf statische Kommandos beschränken.
  → **Gegenentwurf unter der Annahme, HANA wäre unterstützt:**
  [`Konzept_MultiPlattform_Executor_BDC.md`](Konzept_MultiPlattform_Executor_BDC.md) — Backend-
  Abstraktion (Dialect/Connector), mit der Signal HANA + HDLF + (SAP-/natives) Databricks aus
  *einem* Contract prüft; CLI bleibt dort Parität-Gate, nicht Enforcer.
- **ORD *kodiert* einen Breaking Change, *detektiert* ihn nicht.** ORD-Vokabel: `majorVersion`
  MUSS bei inkompatibler Änderung hochgezählt werden (≙ SemVer-Major); bei Bruch wird die alte
  Ressource nicht ersetzt, sondern ein separater `successor` erzeugt, die alte auf
  `releaseStatus=deprecated`. Detektion bleibt Contract-Layer; ORD ist die Publikation der
  Konsequenz.
- **ORD schließt die Deprecation/Sunset-Lücke (publikationsseitig).** Nativer Lebenszyklus
  `beta → active → deprecated → sunset` (+ `development`), dazu `sunsetDate`, `successors`,
  `Tombstone`. Den Entscheidungs-*Workflow* (wer deprecatet wann) braucht trotzdem einen Owner
  im Cockpit; die *Repräsentation* ist Standard.
- **Wer setzt den Contract: der Producer / Data-Product-Owner** (Commitment wandert upstream).
  Es ist eine *Vereinbarung* → idealerweise mit Consumer ko-designt (producer-driven vs.
  consumer-driven). Platform-Team besitzt das *Meta* (Template/Schema, Tooling, CI-Gates), nicht
  den Inhalt → deckt sich mit unserem `owned_by`-Split. ORD benennt den Owner via `responsible`.
- **Write-back-Grenze:** Nur *committete, stabile* Garantien → ORD (Custom Capabilities/Labels).
  *Live*-Compliance-Status (active/breached) bleibt in `dq_object_status` — fast-changing Status
  nach ORD zurückzuschreiben widerspricht ORDs eigener Intention.

-----

## 5 — Empfehlung im Kern (zur Validierung)

ODCS + ORD als **weitere einseitige Derivate** behandeln — exakt das Muster von CSN/ORD:

1. YAML-Contract bleibt Source of Truth.
1. One-Way-Export YAML → ODCS (`models`) → `datacontract breaking` als **CI-Gate** bei jedem
   Contract-PR. Schließt die Breaking-Lücke + liefert Changelog.
1. Bei echtem Bruch: Publikation in ORD — DataProduct-`majorVersion` bumpen, `successor` anlegen,
   alte Ressource `deprecated` + ggf. `sunsetDate`.
1. Executor bleibt **ausschließlich** GX-on-HANA (kein Fork).

-----

## 6 — Offene Recherche-/Verifikationspunkte

> Priorität grob: **[H]** hoch (blockiert Seam-Festlegung) · **[M]** mittel · **[L]** später.

- **R1 [H] — ORD-DataProduct-Port-Sub-Schema.** Referenzieren `inputPorts`/`outputPorts`
  zwingend eine `APIResource`/`EventResource`, oder kann ein Port inline eine
  Delta-Sharing-/ODBC-/HDLF-Quelle tragen? → ORD-DataProduct-JSON-Schema gegenprüfen, *bevor*
  wir die Port→Schema-Referenz als Seam festklopfen. (Nur Existenz der Felder ist verifiziert,
  nicht der Sub-Aufbau.)
- **R2 [H] — ORD-Emission durch Datasphere/BDC heute.** Welche konkrete ORD-Dokumentform
  erzeugt Datasphere für ein Datenprodukt (H1 2026)? Wie läuft die Catalog-Ingestion / der
  ORD-Aggregator-Pfad in BDC? Welche Felder sind setzbar vs. von SAP belegt?
- **R3 [H] — Mapping YAML → ODCS v3 `models`.** Adapter-Design: Was lässt sich verlustfrei
  abbilden, was braucht Custom-Extensions? Wo geht Semantik verloren?
- **R4 [M] — Heimat der Product-Level-DQ-Garantien.** ODCS `servicelevels`/`quality` vs. ORD
  Custom Capabilities/Labels: wo genau leben sie für die Sichtbarkeit im BDC-Catalog?
  Round-trippen sie? Konsistenz-Regel definieren.
- **R5 [M] — Versions-Granularität-Mapping.** ORD `majorVersion` ist *pro Ressource*. Wie
  koppelt das an unsere Contract-Version / SemVer-Policy? Regel: Contract-Breaking →
  DataProduct-`majorVersion`-Bump + `successor`.
- **R6 [M] — Consumer als benannte Gegenpartei.** Kann ORD `IntegrationDependency` /
  `ConsumptionBundle` als Consumer-Registrierungs-Mechanismus dienen (Consumer deklariert
  Abhängigkeit auf unsere DataProduct-ORD-ID)? → Weg, die fehlende Consumer-Rolle zu schließen.
- **R7 [M] — Catalog-/Metadaten-Zugriff programmatisch.** Wie lesen wir DataProduct-/ORD-Metadaten
  aus Datasphere (CLI? OData? Catalog-API?)? Bindet an bekannte Risiken: DWC_GLOBAL nicht
  öffentlich dokumentiert + HDLF-CLI-Permission-Gap.
- **R8 [L] — Deprecation-/Sunset-Workflow-Ownership.** Wer triggert Deprecation, und über
  welchen Cockpit→ORD-Publikationsmechanismus? `Tombstone`-Handhabung.
- **R9 [L] — Homegrown-Diff als Quick-Win-Alternative.** Falls ODCS-Mapping zu früh kommt:
  eigener YAML-Diff (removed field / type narrowing / key change / verschärfte Constraint,
  ~150 LOC). Trade-off: verliert gepflegtes Breaking-Regelwerk + Changelog-Generierung.

-----

## 7 — Mitzudenkende Architektur-Entscheidungen

- ODCS als *kanonisches* Contract-Format adoptieren (großer Schritt, bringt Rollen/SLA/Quality
  nativ + entsperrt die CLI) **oder** Custom-YAML behalten + dünner One-Way-Exporter (geringeres
  Commitment, aber zweite Serialisierung + Mapping-Pflege). → Entscheidung an R3/R4 koppeln.
- Acceptance-Gates erweitern: zusätzlich zu „kein SQL im Contract” / „kein hardcoded `CENTRAL`”
  ein **Breaking-Gate** im CI (lint + `breaking` müssen grün sein).
- Consumer-Rolle im Lifecycle-Modell nachziehen (mind. benannte, konsultierte Gegenpartei) —
  derzeit unter-modelliert.

-----

## 8 — Quellen / Referenzen (zum Nachrecherchieren)

- ODCS v3 / `datacontract-cli` — `breaking`/`diff`/`changelog`, Engine-Liste, ODCS-internes Modell
  (PyPI `datacontract-cli`, `cli.datacontract.com`, DeepWiki `datacontract/datacontract-cli`).
- ORD-Spezifikation v1 — `releaseStatus`/`majorVersion`/`successors`/`sunsetDate`/`Tombstone`,
  DataProduct-Objekt mit `inputPorts`/`outputPorts`/`entityTypes`/`responsible`
  (`open-resource-discovery.org/spec-v1`, GitHub `open-resource-discovery/specification`).
- SAP Community — „Why we created Open Resource Discovery” (ORD als Discovery-Wrapper/Katalog).

> Offen geprüft: ORD-Felder belegt; Port-Sub-Schema und konkrete Datasphere-ORD-Emission **nicht**
> spec-/produktgenau verifiziert (siehe R1, R2).