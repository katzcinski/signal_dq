# Investment Case — Warum wir weiter in Signal investieren sollten

**Zweck:** Argumentationsgrundlage für die interne Entscheidung, Signal als
strategisches Asset der Beratung weiterzuentwickeln. Verdichtet die bestehenden
Analysen (Marktanalyse, Entropy-Strategie, BDC/ORD-Integration, Übergabemodelle)
zu einem Pitch mit klarem Ask.
**Adressat:** Geschäftsführung / Partner-Runde · **Stand:** 2026-07-02
**Quellenlage:** Jede Kernaussage ist in einem bestehenden Repo-Dokument
hergeleitet (Verweise je Abschnitt); dieses Dokument fügt die Investment-Logik
hinzu, keine neuen technischen Behauptungen.

---

## 0 — Die Kernthese in drei Sätzen

1. **Es gibt heute kein Data-Quality-/Observability-Produkt für SAP Datasphere /
   HANA Cloud** — weder von SAP selbst noch von den Marktführern (Monte Carlo,
   Anomalo, Soda, Great Expectations, datacontract-cli). Signal besetzt einen
   nachweisbaren Whitespace.
2. Signal ist **kein Prototyp mehr**: Die Marktstandards („Table Stakes") der
   DQ-/Observability-Kategorie sind implementiert, die Lücken zu den Marktführern
   sind identifiziert, priorisiert und technisch entworfen. Weiteres Investment
   kauft Differenzierung, nicht Grundlagen.
3. Mit **SAP Business Data Cloud (BDC)** entsteht gerade ein Data-Product-Ökosystem,
   das **beschreibt, aber nicht erzwingt** — genau die Lücke, für die Signal gebaut
   ist. Das Zeitfenster, sich dort als Enforcement-Schicht zu positionieren, ist
   **jetzt** offen.

---

## 1 — Die Marktlücke: Für Datasphere/HANA Cloud gibt es das schlicht nicht

> Quellen: [`Marktanalyse_DQ_Observability_2026.md`](Marktanalyse_DQ_Observability_2026.md),
> [`Vortrag_Briefing_DataProducts_DataContracts_DSP_BDC.md`](Vortrag_Briefing_DataProducts_DataContracts_DSP_BDC.md) §1.5,
> [`datacontract-cli_Integration.md`](datacontract-cli_Integration.md) §F7

Drei voneinander unabhängige Befunde, die zusammen den Whitespace ergeben:

**a) SAP selbst hat keinen deklarativen Ort für Data Quality in Datasphere.**
Die Fünf-Schichten-Analyse des Vortrags-Briefings zeigt: Schema, Katalog, Sharing
und Access haben in DSP/BDC je einen Ankerpunkt — **Quality/SLA ist die einzige
Schicht, die „nur implementiert" wird** (`DQ_STATUS`-Muster, Task Chains), aber
nirgends deklariert, versioniert oder erzwungen werden kann. Es gibt in Datasphere
kein Contract-Objekt, keine Quality-Rules-Engine, keine Compliance-Sicht. Wer
Datenqualität dort will, baut sie heute pro Projekt handgestrickt in Views — genau
das, was wir in jedem Kundenprojekt aufs Neue sehen.

**b) Die Marktführer erreichen HANA/Datasphere nicht.**
Monte Carlo, Anomalo, Bigeye, Soda, Great Expectations, Elementary — die gesamte
Kategorie verkauft über Warehouse-Konnektoren (Snowflake, BigQuery, Databricks,
Redshift). Ein produktiver HANA-/Datasphere-Connector ist bei keinem der
verglichenen Anbieter Kernangebot. Für sie ist SAP ein Nischenmarkt; für uns ist
es der Heimatmarkt.

**c) Der Open-Source-Standardweg hatte die Lücke ebenfalls — bis wir sie selbst
geschlossen haben.** `datacontract test` — der De-facto-Standard, um
ODCS-Contracts gegen eine Datenbank zu prüfen — hatte historisch **kein
SAP-HANA-Backend** (Engines: Snowflake/BigQuery/Databricks/Postgres/S3/Kafka).
Der strukturelle Effekt: Plattformen wie Entropy Data, die Quality-Ergebnisse nur
*anzeigen* und die Ausführung an diese CLI delegieren, konnten für SAP-Quellen
kein verifiziertes Grün erzeugen. **Das inzwischen existierende HANA-Backend
stammt aus unserem Haus** — von uns an das Entropy-Ökosystem beigesteuert (der
im Strategie-Doc als „Embrace-Move" beschriebene Zug, bewusst vollzogen: der
generische Transport wird kommoditisiert, Signals SAP-Checks und Governance
bleiben proprietär). Das belegt zweierlei: Die Lücke war real genug, dass *wir*
sie füllen mussten — und wir sind im relevanten Ökosystem bereits als Contributor
sichtbar, nicht als Zaungast.

**Investment-Logik:** Ein Markt, in dem weder der Plattformhersteller noch die
Kategorie-Marktführer noch das OSS-Ökosystem liefern, während die Nachfrage
(Datenqualität in SAP-Landschaften) in jedem unserer Projekte auftaucht, ist die
seltene Konstellation *nachgewiesener Bedarf ohne Wettbewerb im Segment*.
Datasphere/HANA-only ist dabei keine Schwäche, sondern eine dokumentierte
**Positionierungsentscheidung** (Marktanalyse §3.4): Wir konkurrieren nicht über
Connector-Breite, sondern über SAP-Tiefe.

---

## 2 — Kein Insellösungs-Risiko: Signal vereint DQ, Observability und Contracts nach State of the Art

> Quellen: [`Marktanalyse_DQ_Observability_2026.md`](Marktanalyse_DQ_Observability_2026.md),
> [`Tooldokumentation.md`](Tooldokumentation.md),
> [`Konzept_Observability_Intelligence_v1.md`](Konzept_Observability_Intelligence_v1.md)

Der Markt konvergiert seit 2024 auf die Kombination aus drei früher getrennten
Kategorien: **Data Contracts** (Versprechen), **Data Quality** (Checks) und
**Data Observability** (Baselines, Anomalien, Incidents). Signal ist von Anfang an
als diese Kombination gebaut — nicht als DQ-Tool mit angeflanschtem Monitoring:

- **Contracts:** semantische, SQL-freie YAML-Contracts mit SemVer,
  Breaking-Change-Gate in CI (G3) und ODCS-3.1-Export — anschlussfähig an den
  Industriestandard (Bitol / Linux Foundation).
- **Quality:** deterministisch kompilierte, ausschließlich lesende Checks gegen
  HANA, inkl. einer **SAP-Domänen-Bibliothek** (BSEG/BKPF-Konsistenz,
  Replikations-Lag, Fiscal-Completeness), die es in keinem generischen Tool gibt.
- **Observability:** Rolling-Baselines, Volumen-/Schema-Drift, Compliance-Ampel
  mit SLA-Fenstern (7/30/90 Tage), Incidents mit Timeline, Lineage-/Coverage-Map,
  Proposal-Miner (datengetriebene Garantie-Vorschläge).

Die Marktanalyse 2026 kommt zum Befund: **„Signal ist auf den Grundlagen nicht im
Rückstand"** — die Table Stakes der Kategorie sind abgedeckt. Die verbleibenden
Lücken zu Monte Carlo & Co. liegen in der *Intelligenz-Schicht* (saisonalitäts-
bewusste Anomalieerkennung, Segmentierung, Root-Cause/Blast-Radius,
Alert-Clustering) — und für genau diese vier Features existiert bereits ein
technischer Entwurf, der die Architektur-Invarianten nicht verletzt.

**Investment-Logik:** Das teure Fundament (Engine, Compiler, Store, Cockpit,
CI-Gates) ist bezahlt. Das nächste Investment fließt zu 100 % in die Features,
die im Verkaufsgespräch den Unterschied machen — „fühlt sich so smart an wie
Monte Carlo, spricht aber SAP".

---

## 3 — Der BDC-Hebel: Data Products semantisch ergänzen und Contracts überhaupt erst einführen

> Quellen: [`ADR-0003_BDC-Datasphere-DataProductStudio.md`](ADR-0003_BDC-Datasphere-DataProductStudio.md),
> [`ADR-0004_DataProduct-als-Komposition.md`](ADR-0004_DataProduct-als-Komposition.md),
> [`Zusatz_ContractLifecycle_ORDBDCIntegration.md`](Zusatz_ContractLifecycle_ORDBDCIntegration.md),
> [`Vortrag_Briefing_DataProducts_DataContracts_DSP_BDC.md`](Vortrag_Briefing_DataProducts_DataContracts_DSP_BDC.md)

SAP rollt mit BDC und dem **Data Product Studio** gerade ein Data-Product-Ökosystem
aus: Jedes Produkt bekommt einen **ORD-Descriptor**, wird im Katalog auffindbar und
über Delta Share / SQL-Output-Ports konsumierbar. Was dabei strukturell fehlt:

> **ORD beschreibt — es erzwingt nicht.** Ports tragen Topologie, Zugriff und
> Schema-*Referenz*. Sie tragen **nicht** die durchsetzbaren Garantien:
> Freshness-SLA, Completeness, Verteilungsgrenzen, Quality-Rules, Terms.
> (Zusatz ORD/BDC §2)

Das heißt konkret: BDC-Kunden bekommen einen Marktplatz voller Datenprodukte,
denen man **nicht ansehen kann, ob sie halten, was sie versprechen** — und es gibt
kein SAP-Werkzeug, das dieses Versprechen formuliert oder prüft. Signals Rolle ist
präzise definiert und bereits architektonisch entschieden (ADR-0003, accepted):

1. **Semantische Ergänzung:** Signal legt über jedes BDC-Datenprodukt einen
   maschinenlesbaren Contract (Schema, Keys, Freshness, Volumen, Completeness,
   referenzielle Integrität) — die Quality/SLA-Schicht, die ORD nicht hat. Export
   als ODCS 3.1 und Rückschreibung stabiler Garantien in den ORD-Descriptor sind
   als Einweg-Derivate konzipiert: **„BDC beschreibt — Signal erzwingt."**
2. **Contracts überhaupt erst einführen:** BDC erzeugt Produkte tool-getrieben
   („alles ist ein Foundation Product"). Das erzeugt beim Kunden entweder
   Governance-Vakuum oder Over-Governance. Signals Tiering-Modell
   (`boundary` × Lite/Full, datengetrieben über die Lineage) ist die
   Beratungsantwort darauf — und zugleich das Feature, das kein Wettbewerber hat,
   weil es aus echter SAP-Projektarbeit stammt.
3. **Technische Naht ist geklärt:** ADR-0003 hat entschieden, dass Signal an der
   **SQL-erreichbaren Oberfläche** eines Datenprodukts erzwingt (HANA-View oder
   SQL-on-Files über HDLF) — der vorhandene Executor greift dort **ohne
   Engine-Änderung**. Das ist kein Forschungsprojekt, sondern Konfiguration.

**Investment-Logik (Timing):** BDC-Adoption beginnt bei unseren Kunden gerade
erst. Wer in den ersten Rollout-Wellen die Contract-/Quality-Schicht stellt,
definiert den Standard beim Kunden. In 18 Monaten ist dieses Fenster entweder
von uns besetzt — oder von einem Wettbewerber, der unsere Analyse nachvollzogen
hat.

---

## 4 — Entropy Data: Partnerschaft statt Konkurrenz — und ein fertig gedachter Integrationspfad

> Quelle: [`Zusatz_EntropyData_Integration_und_Defensibility.md`](Zusatz_EntropyData_Integration_und_Defensibility.md)

**Entropy Data** (vormals Data Mesh Manager) ist der führende plattformneutrale
Data-Product-Marktplatz (ODCS-3.1-nativ, erstes Tool mit ODPS-1.0-Support). Die
strategische Analyse liegt vor und ist eindeutig: **komplementär, nicht
konkurrierend.** Und die Beziehung ist keine Hypothese mehr — **wir haben das
HANA-Backend für Entropys Ausführungspfad selbst beigesteuert, und es besteht
ein loser, direkter Austausch zwischen unserem Haus und Entropy.**

Der naheliegende Einwand — *„Entropy hat doch auch Contracts und Data Quality,
sind wir dann nicht Konkurrent?"* — löst sich an der Unterscheidung
*verwalten/anzeigen* vs. *ausführen/erzwingen* auf:

- Entropy **führt selbst keine Quality-Checks aus** — es ist Registry und
  Anzeigefläche. Sein Ausführungspfad ist `datacontract test --publish`, also
  eine externe CLI, die an Soda/GX delegiert. Für SAP-Quellen war dieser Pfad
  bis zu unserer Backend-Contribution strukturell leer (§1c).
- Die Arbeitsteilung mappt exakt auf Signals Stärken-/Schwächenprofil: Entropy
  besitzt die *linke* Lifecycle-Hälfte (Marktplatz, Discovery, Access-Requests,
  Consumer-Sign-off) — Signals dokumentiert schwache Hälfte, die wir bewusst
  abtreten statt bekämpfen. Signal besitzt die *rechte* (Checks gegen HANA
  ausführen, erzwingen, kontinuierlich beobachten, zertifizieren) — die Hälfte,
  die Entropy per Architektur wegdelegiert. Bild für den Pitch: **Entropy ist
  das Schaufenster, Signal die Enforcement-Engine dahinter.**
- Die verbleibende Überlappung (beide haben Authoring-UI und
  Quality-Status-Fläche) ist im Strategie-Doc ehrlich benannt und über die
  Source-of-Truth-Frage je Kunde auflösbar: *Signal authort → Entropy zeigt*
  (Default) oder *Entropy authort → Signal erzwingt* — nie bidirektional.
- **Der Integrations-Seam existiert großteils schon:** ODCS-Export (`to_odcs()`)
  → Entropy ingestiert nativ; Result-Publishing ist ein dünner Publisher nach dem
  bereits entworfenen OpenLineage-Emitter-Muster; das Product-Manifest mappt auf
  ODPS 1.0.

Die Backend-Contribution verändert die Qualität dieser Beziehung: Aus „möglichem
Partner-Ziel" wird ein **angewärmter Kanal** — wir sind dort als Contributor
bekannt, die Grenzziehung ist von uns selbst gesetzt (generische CI-Checks laufen
über die CLI, die *wir* HANA-fähig gemacht haben; SAP-Spezialitäten, Governance
und Runtime gehören Signal), und die Integrationsreibung ist gesenkt statt erhöht
— exakt das im Strategie-Doc als „Embrace-Move" beschriebene Zielbild.

Die Positionierung ist damit formuliert: **„Signal ist das SAP/HANA-Quality-Backend
für euren Entropy-Data-Marktplatz."** Für die Beratung heißt das: Wir müssen keinen
Marktplatz bauen und nicht gegen ein finanziertes Produkt antreten — wir docken an
dessen Ökosystem an und besetzen das Segment, das wir dort selbst am besten kennen.
Eine formalisierte Partnerschaft gibt uns zusätzlich Sichtbarkeit außerhalb der
eigenen Kundenbasis; der lose Austausch ist der Startpunkt, kein Kaltkontakt.

---

## 5 — Verteidigbarkeit: Warum uns das nicht weggenommen wird

> Quelle: [`Zusatz_EntropyData_Integration_und_Defensibility.md`](Zusatz_EntropyData_Integration_und_Defensibility.md) §6

Die härteste Frage im Pitch ist: *„Was, wenn jemand einen generischen
HANA-Connector baut?"* Unsere Antwort ist die stärkste, die es gibt: **Wir haben
ihn selbst gebaut und beigesteuert.** Das war kein Kontrollverlust, sondern der
im Strategie-Doc durchgerechnete Zug — der Connector/Transport ist
kommoditisierbar, also kommoditisieren *wir* ihn zu unseren Bedingungen und
verankern Signals Wert an den vier Dingen, die ein Connector-Patch nicht
repliziert:

1. **Das SQL-freie Garantie→Compiler-Modell (G1).** Wettbewerbstools verlangen
   handgeschriebenes SQL/SodaCL im Contract. Signal: semantische Garantie rein,
   deterministischer Compiler erzeugt das SQL. Das ist ein anderes, assurance-
   stärkeres Produkt — und CI-erzwungen (die Gates G1–G8 sind Build-brechend).
2. **Die SAP-Domänen-Bibliothek.** BSEG/BKPF-Balance, Replication-Lag,
   Fiscal-Completeness — kodiertes SAP-ERP-Wissen. Ein generisches Backend gibt
   die Fähigkeit, SQL zu fahren, nicht *diese Checks*. Das ist Beratungs-IP in
   Produktform.
3. **Die Security-Posture als Feature.** Ausschließlich lesend, PII-Gate (G8,
   Rohzeilen verlassen HANA nie ohne explizite Freigabe), fail-closed Auth.
   „Externe Test-Engine fragt eure produktive HANA ab" ist im SAP-Haus ein
   Security-Review-Problem — Signals gegatete Posture ist selbst der Moat, der
   Deals durch die Security bringt (inkl. Hybrid-Executor im Kundennetz).
4. **Kontinuierliche Observability statt CI-Momentaufnahme.** Alle CLI-basierten
   Ansätze sind Punkt-in-Zeit-Gates. Signal ist Laufzeit: Baselines, Ampel,
   SLA-Fenster, Incidents, Run-Historie, Proposals — ein lebendes Cockpit.

Dazu zwei weiche, aber real verkaufsrelevante Differenzierer: **German-first**
(gesamte UI und künftige Incident-Erklärungen auf Deutsch — im DACH-Mittelstand
ein echtes Argument) und **Determinismus** (kein Black-Box-ML entscheidet, was
geprüft wird; auditierbar, was Governance- und Wirtschaftsprüfer-Gespräche
drastisch verkürzt).

---

## 6 — Der Business Case für die Beratung: drei Erlös-Hebel aus einem Asset

> Quellen: [`Uebergabemodelle_und_Lizenz.md`](Uebergabemodelle_und_Lizenz.md),
> [`Konzept_Managed_Service_Provisioning.md`](Konzept_Managed_Service_Provisioning.md),
> [`Betriebsmodi_Lite_und_Full.md`](Betriebsmodi_Lite_und_Full.md)

Signal ist bewusst als **Beratungs-Delivery-Tool** konzipiert, nicht als
Lizenzprodukt — die Übergabemodelle sind juristisch vorgedacht:

| Hebel | Modell | Wirkung |
|---|---|---|
| **Delivery-Beschleuniger** | Lite-Modus im Projekt | DQ-/Contract-Arbeit, die sonst je Projekt handgebaut wird, kommt aus dem Werkzeugkasten → höhere Marge auf bestehenden Engagements, differenzierendes Angebot in Ausschreibungen |
| **Wiederkehrender Umsatz** | Managed Service (Modell A1: wir betreiben technisch, Kunde governt fachlich; Hybrid-Executor für strenge Security) | Monatliches Betriebs-Entgelt + Rollout-/Härtungs-Engagements — Recurring Revenue ohne Kippen ins Produktgeschäft |
| **Marktpositionierung** | Vortrag/Kundendeck (liegen fertig im Repo), Entropy-Partnerschaft, BDC-Frühphase | Thought Leadership „Data Contracts in SAP-Landschaften" — zieht Projekte an, die es ohne das Asset nicht gäbe |

Wichtig für die Partner-Runde: Der Managed-Service-Pfad ist so geschnitten, dass
die **Softwareüberlassungs-Schwelle nicht erreicht wird** (keine Lizenz-, Gewähr-
leistungs- und Steuerthematik als Nebenwirkung). Ein späterer bewusster Schritt
ins Produktgeschäft (Modell C) bleibt als Option offen — die Checkliste dafür
existiert.

---

## 7 — Warum das Investment jetzt klein und das Risiko begrenzt ist

- **Das Fundament steht und ist abgesichert.** Engine, Compiler, Store, Cockpit,
  CI mit acht build-brechenden Sicherheits-Gates, Tests, vollständige Doku. Wir
  investieren nicht in einen Neubau, sondern in die letzte Meile.
- **Die Roadmap ist priorisiert, nicht spekulativ.** Vier Tier-1-Features
  (Anomalie-Baselines, Root-Cause/Blast-Radius, Segmentierung, Schema-Drift an
  der Quelle) sind marktvalidiert (aus dem Vergleich mit Monte Carlo/Anomalo
  abgeleitet), technisch entworfen und verletzen keine Architektur-Invariante.
- **Die strategischen Fragen sind schriftlich durchgearbeitet.** BDC-Anschluss
  (ADR-0003/0004: beschlossen), Entropy (Strategie-Doc mit offenen Punkten E1–E5),
  Lizenz/Übergabe (Modell-Doc), Wettbewerb (Marktanalyse mit Quellen). Das
  Investment-Risiko ist kein „wissen wir nicht", sondern eine Liste konkreter,
  benannter Verifikationspunkte.
- **Ehrlich benannte Restrisiken:** (a) SAP könnte mittelfristig native DQ in
  Datasphere/BDC bauen — dann bleibt Signals Contract-/Governance- und
  SAP-Domänen-Schicht relevant, aber das Fenster für die Positionierung schrumpft:
  ein Argument *für* Tempo, nicht dagegen. (b) Das frühere Risiko „die CLI könnte
  ein HANA-Backend bekommen" ist entschärft, weil wir diesen Zug selbst gemacht
  haben (§5) — Restrisiko ist nur, dass Dritte auf dem von uns gelegten Transport
  generische Angebote bauen; die vier Wert-Anker (§5) adressieren genau das.
  (c) Zwei technische Annahmen am BDC-Seam sind noch zu verifizieren
  (SQL-on-Files-Adressierung V1, konkrete ORD-Emission R2) — beides Gegenstand
  des vorgeschlagenen nächsten Schritts, nicht des Gesamtinvestments.

---

## 8 — Der Ask: drei konkrete Schritte

1. **Intelligenz-Schicht bauen (Entwicklung).** Die vier priorisierten
   Tier-1-Features aus der Marktanalyse umsetzen (Reihenfolge dort festgelegt:
   Anomalie-Baselines → Root-Cause/Blast-Radius → Segmentierung → Schema-Drift).
   Ergebnis: Signal ist im Feature-Vergleich mit den Kategorie-Marktführern
   nicht mehr unterscheidbar „dümmer" — bei vollem SAP-Vorsprung.
2. **Erster Referenzkunde als Managed Service (Vertrieb + Delivery).** Ein
   bestehender Datasphere-Kunde, Modell A1, Lite-Modus, 10–20 reale Contracts
   entlang der Lineage. Validiert Security-Pfad (Hybrid-Executor), Preismodell
   und den Tiering-Ansatz am lebenden Objekt.
3. **Ökosystem-Andockpunkte formalisieren (geringer Aufwand, hoher Optionswert).**
   Den bestehenden losen Austausch mit Entropy Data — angewärmt durch unsere
   HANA-Backend-Contribution — in eine konkrete Integrationsvereinbarung
   überführen (Result-Ingest-API, Source-of-Truth-Modus — offene Punkte E1/E2)
   und die zwei BDC-Annahmen verifizieren (V1: SQL-on-Files-Naming, R2:
   ORD-Emission durch Datasphere) am Test-Tenant.

**Schluss-Satz für den Pitch:**

> Wir besitzen heute das einzige Werkzeug, das Data Contracts in SAP-Landschaften
> nicht nur beschreibt, sondern erzwingt — in einem Markt, den SAP offen lässt
> und die Observability-Anbieter nicht erreichen. Wo das OSS-Ökosystem SAP
> inzwischen erreicht, tut es das über einen Baustein aus unserem Haus. Das
> Fundament ist bezahlt, die Roadmap ist marktvalidiert, das BDC-Zeitfenster ist
> offen, der Draht zu Entropy liegt. Die Frage ist nicht, ob diese Lücke gefüllt
> wird — sondern ob von uns.
