# Marktanalyse DQ / Observability / Data Contracts 2026 — Feature-Gap-Synthese

**Stand:** 2026-06-29 · **Zweck:** Synthese der überzeugendsten Features führender
DQ-/Observability-/Contract-Plattformen, abgeglichen gegen den implementierten Stand von
Signal (siehe [`Tooldokumentation.md`](Tooldokumentation.md)).

Diese Datei ist die **Marktübersicht & Priorisierung**. Der technische Entwurf für die
Tier-1-Features liegt in [`Konzept_Observability_Intelligence_v1.md`](Konzept_Observability_Intelligence_v1.md).

---

## 0 / Verglichene Plattformen

| Kategorie | Vertreter |
|---|---|
| Data Observability | Monte Carlo, Anomalo, Bigeye, Sifflet, Validio, Metaplane (Datadog), Acceldata |
| Data Quality (Checks/OSS) | Soda (SodaCL), Great Expectations, dbt tests, Elementary, Deequ |
| Data Contracts | ODCS 3.1 (Bitol/Linux Foundation), datacontract-cli, Gable.ai |

---

## 1 / Ausgangslage — was Signal bereits abdeckt

Signal ist auf den **Grundlagen nicht im Rückstand**. Bereits implementiert und damit
nicht als Lücke geführt:

- Semantische, SQL-freie Contracts mit SemVer + Breaking-Change-Gate (G3)
- ODCS-3.1-Export, deterministisch kompilierte Checks (G1/G2)
- Rolling-Baselines + `volume_delta`/`column_count`/`recent_volume` (Observability-Quick-Wins)
- Proposal-Miner (datengetriebene Garantie-Vorschläge)
- Compliance-Ampel + SLA-Fenster (7/30/90 d), Incidents mit Timeline
- Lineage-/Coverage-Map (kind-aware), Notification-Routing, einbettbares Badge

Die **Marktstandards (Table Stakes) sind abgedeckt.** Die Lücken konzentrieren sich auf
die **Intelligenz-Schicht** (Wie smart ist Erkennung & Triage?) und einige
**Workflow-Oberflächen**, die die Marktführer zum Standard gemacht haben.

Filter für alle Lücken: Vereinbarkeit mit Signals Invarianten — lesender HANA-Zugriff,
SQL-freie Contracts (G1), Laufzeit-Schema-Bindung (G2), frameworkfreie/eingefrorene Engine
(G7), PII-Gate (G8).

---

## 2 / Tier 1 — Größte und am besten verteidigbare Lücken

> Technischer Entwurf: [`Konzept_Observability_Intelligence_v1.md`](Konzept_Observability_Intelligence_v1.md)

### 1.1 — ML-/adaptive Anomalieerkennung (saisonalitätsbewusst)

**Markt:** Monte Carlo, Anomalo, Bigeye, Validio liefern *gelernte* Schwellwerte —
Modelle, die Saisonalität (Wochentag/Monatsende), Trend und Varianz erfassen und feuern,
wenn ein Wert *für seinen Kontext* anomal ist.

**Signal heute:** `DELTA <op> %` ggü. Vorlauf plus statische `volume.min_rows`.
Feste Bänder erzeugen bei einem monatsende-lastigen SAP-Finanz-/Sales-Workload entweder
False-Positives an ruhigen Tagen oder verpassen langsamen Drift.

**Bewertung:** Das Einzelfeature, das Signal im direkten Vergleich am ehesten „dümmer"
wirken lässt. Fit hoch — neue Baseline-Strategie in `obs/baselines.py` + `anomaly`-Expectation,
ohne den eingefrorenen Ausführungskern zu berühren.

### 1.2 — Segmentierung / dimensionale Anomalieerkennung

**Markt:** „Nulls spiken **nur für region=APAC**" oder „Frische bricht **nur für ein
Quellsystem**". Validio u. a. mit segmentierter Anomalieerkennung.

**Signal heute:** Prüfung auf Tabellen-/Spalten-Grain. Eine 2-%-Null-Rate, die in einem
Segment 100 % ist, besteht.

**Bewertung:** Häufige Käuferanforderung, sehr im Scope — `group_by`/Segment-Dimension auf
completeness/freshness/volume; der Compiler emittiert Per-Segment-SQL (lesend, Contract bleibt
SQL-frei).

### 1.3 — Automatisierte Root-Cause-Analyse / Blast-Radius auf Incidents

**Markt:** Bei Breach zeigen Monte Carlo & Co. **Upstream-Ursache** (welches Parent-Objekt
gleichzeitig fehlschlug / Schema änderte) und **Downstream-Blast-Radius** (welche
Consumer-Contracts betroffen sind) plus „ist N-mal zuvor passiert".

**Signal heute:** Rohmaterial vorhanden (Lineage + Coverage + Incidents in einem Store),
aber nicht in die Triage verdrahtet.

**Bewertung:** Sehr hoher ROI, geringes Architekturrisiko — überwiegend eine
Korrelationsabfrage über bereits persistierte Daten (`dq_incidents` × `lineage` ×
`dq_check_results` je Run), dargestellt auf der Incident-Timeline.

### 1.4 — Alert-Clustering / Deduplizierung

**Markt:** Jeder 2026er-Report nennt Alert-Fatigue als Adoptions-Killer — „korreliere
verwandte Alerts, damit Engineers nicht zwölfmal denselben Incident jagen".

**Signal heute:** Eine Upstream-Schemaänderung fächert in viele unabhängige Failures/Incidents auf.

**Bewertung:** Notification-/Incident-Schicht-Änderung mit direktem Effekt auf die
tägliche Benutzbarkeit. Korrelierte Failures innerhalb eines Runs (und entlang des
Lineage-Pfads) zu einem Incident bündeln.

---

## 3 / Tier 2 — Überzeugend, guter Fit

### 2.1 — Shift-Left-Enforcement an der Quelle (Schema-Drift-Detection)

Gable fängt Breaking Changes im **Producer-Code** ab. Signal kann keine Producer-Repos lesen,
aber eine leichtere Variante passt: Drift-Detektor, der das **Live-HANA-/Datasphere-Schema**
(Inventar wird bereits extrahiert) je Lauf gegen die `schema`-Garantie des aktiven Contracts
difft und einen Incident öffnet, wenn die Quelle vom Versprechen abweicht. Schließt die
Schleife zwischen „was wir zugesagt haben" und „was die Quelle tatsächlich tat".

### 2.2 — Data-Diff / Environment- & Versions-Vergleich

Datafold-Stil „was änderte sich zwischen zwei Zuständen". Signal hat `runs/compare`
(Status-Diff der Checks), aber keinen *Wert-/Verteilungs-Diff*. Before/After-Vergleich auf
einem Deploy oder zwischen dev/prod. Teilweise im Scope bei lesendem Zugriff (Row-Counts,
Verteilungen, Key-Overlaps zweier Datasets/Environments).

### 2.3 — KI/NL-Copilot für Check- & Contract-Authoring

Anomalo/Monte Carlo generieren Monitore und erklären Incidents in natürlicher Sprache.
Scoped für Signal: **NL → Garantie** in der Contract-Workbench (LLM emittiert *Garantien*,
der deterministische Compiler erzeugt weiterhin sämtliches SQL — G1 bleibt scharf) und
**Incident-Erklärung** auf Deutsch. Der deutschsprachige Erklärer ist ein echter
Differenziator (Codebasis ist German-first).

### 2.4 — Reconciliation / Control-Total gegen eine Source of Truth

Heute explizit aus dem Scope (dokumentiert als separater Integrationspfad). Wird in
2026er-Übersichten wiederholt als *kritisch* genannt, besonders für Finance/SAP. Die eine
Auslassung, die ein Finance-Käufer ansprechen wird — neu zu bewerten als dokumentierter
Integrationspfad statt als Dauerhaftes-Nein.

---

## 4 / Tier 3 — Beobachten, geringere Dringlichkeit

### 3.1 — KI/LLM-Datenobservability
RAG-Korpus-Qualität, Validierung KI-generierter Felder. Echte Branchendynamik, aber erst
relevant, wenn Datasphere-Kunden GenAI auf diesen Daten fahren — für Signal aktuell verfrüht.

### 3.2 — Prädiktive / proaktive Frische-SLAs
Vorhersage „diese Tabelle wird ihre SLA verfehlen" aus Job-Timing-Historie. Natürliche
Erweiterung, sobald Zeitreihe + ML-Baseline (1.1) stehen.

### 3.3 — Cost/FinOps & Pipeline-Job-Observability
Acceldata-/Datadog-Terrain. Stark orchestrator-gekoppelt (Airflow/dbt), außerhalb von
Signals lesender Datasphere-Spur — geringer Fit.

### 3.4 — Connector-Breite
Marktführer verkaufen über N Warehouse-Integrationen. Signal ist bewusst
Datasphere/HANA-only — keine Lücke, eine Positionierungsentscheidung. Nicht verfolgen.

---

## 5 / Empfehlung — priorisierte Reihenfolge

Sortiert nach *Wert × Fit × geringes Architekturrisiko*:

1. **Saisonalitätsbewusste Anomalie-Baselines (1.1)** — schließt die sichtbarste
   Intelligenz-Lücke, fügt sich in `obs/` ein.
2. **Incident Root-Cause + Blast-Radius (1.3)** — reine Hebelwirkung auf bereits
   gespeicherte Daten; keine neue Erfassung.
3. **Segmentierung auf Checks (1.2)** — häufige Käuferanforderung, passt in den Compiler.
4. **Schema-Drift-Detection an der Quelle (2.1)** — schließt die Contract-Schleife, günstig
   dank vorhandenem Extrakt.

Diese vier bewegen Signal von „solider deterministischer Contract-Engine" zu „fühlt sich so
smart an wie Monte Carlo/Anomalo", ohne ein Gate zu verletzen (G1/G2/G7 überleben: Engine
bleibt eingefroren, Contracts SQL-frei, Schema laufzeit-gebunden). **Alert-Clustering (1.4)**
und **NL-/DE-Copilot (2.3)** sind die nächste Stufe und überwiegend UX-/Notification-Schicht.

---

## 6 / Quellen

- [Monte Carlo Review (2026) — ML-Driven Data Observability](https://www.modern-datatools.com/tools/monte-carlo)
- [Monte Carlo vs. Anomalo — Broad Observability vs. Deep Anomaly Detection](https://www.anomalo.com/blog/monte-carlo-vs-anomalo/)
- [Anomalo Review (2026) — Data Quality + Unstructured Data](https://tooldirectory.ai/tools/anomalo)
- [Gable — The Shift Left Data Manifesto](https://www.gable.ai/blog/shift-left-data-manifesto)
- [Most Data Contract Tools Don't Enforce Contracts (zircote, Apr 2026)](https://zircote.com/blog/2026/04/most-data-contract-tools-dont-enforce-contracts/)
- [DataKitchen — The 2026 DQ & Observability Commercial Software Landscape](https://datakitchen.io/blog/the-2026-data-quality-and-data-observability-commercial-software-landscape/)
- [Dagster — Data Observability Tools 2026 (Bigeye/Soda)](https://dagster.io/learn/data-observability-tools)
- [Revefi — Data Observability in 2026](https://www.revefi.com/blog/what-is-data-observability)
- [Monte Carlo — What the 2026 Gartner Market Guide Means](https://montecarlo.ai/blog-what-2026-gartner-market-guide-for-data-observability-tools-means-for-your-data-and-ai-team-my-take)
