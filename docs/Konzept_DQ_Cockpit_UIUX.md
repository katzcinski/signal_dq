# Konzept · UI/UX — DQ & Observability Cockpit

**SAP Datasphere · Data Quality & Observability Cockpit**
Begleitend zum Prototyp `DQCockpit_Prototype.jsx`. Grundlage: Flask-Backend, React-Frontend.

> Status: Konzept zum Bauen. Alle Screens, Rollen und Flows sind aus dem Architekturkonzept
> abgeleitet (zwei Check-Familien, Contract-Lifecycle, Gating, Check-Library, Result-Modell).
> Mock-Daten im Prototyp sind in echten Artefakten geerdet (`S_FF`, `CENTRAL`,
> `gl_account_line_item_view`, `Sales_Orders_View`, LightScreen-/ASM-SBS-Ketten).

-----

## 1 · Zielbild & Designprinzipien

Das Cockpit muss drei Welten in **einer übersichtlichen Oberfläche** vereinen, die heute getrennt
gedacht werden: Observability (kommt Daten an, in erwarteter Form?), Quality (sind Daten korrekt
laut Contract?) und der Contract-Lifecycle (autorisieren, kompilieren, zertifizieren). Die
Leitprinzipien:

- **Dev-Tool-Ethos statt Enterprise-Maske.** Dicht, schnell, tastatur-bedienbar, dunkel. Orientierung
  an Linear/Vercel/Grafana (Chrome ruhig, Daten laut) sowie an Data-Observability (Monte Carlo, Soda:
  Incident-zentriert, Health-Scores, Freshness/Volume-Verläufe) und Data-Contract-Tooling
  (dbt Cloud, GX, Datafold: Contract-as-code, Expectation-Suites, Lineage-DAG, Run-Results). **Kein Fiori.**
- **Farbe ist Bedeutung, nicht Dekoration.** Das bestehende semantische Farbsystem wird durchgezogen:
  Observability = Orange, Quality = Grün, Flow-Monitoring = Teal, Contract = Blau, Feedback = Lila,
  Human-in-the-loop = Pink. Health-Status nutzt eine eigene Achse (OK/Warn/Fail/Critical + Stale).
- **Das Objekt ist die Achse.** Weil `lineage.node.id = inventory.technicalName = dq_object_status.object_name`
  ohne Mapping-Layer zusammenfallen, ist das Datenobjekt der natürliche Verbindungspunkt. Observability,
  Quality, Contract und Lineage konvergieren in der Objekt-Detailansicht.
- **Ein Stil-Signal: die Familien-Spine.** Jede Zeile, Karte und jeder Lineage-Knoten trägt eine 3px
  Farbkante = sofort lesbare Familien-/Domänenzugehörigkeit. Das ist das eine wiedererkennbare Element;
  alles drumherum bleibt monochrom-diszipliniert.
- **Mono = echtes Artefakt.** Alles, was ein reales Systemobjekt ist (Objektname, Spalte, SQL, `expect`,
  `actual_value`, `run_id`, Schema), steht in JetBrains Mono. UI-Sprache in DM Sans. Das spiegelt eure
  bestehende Konvention („Monospace labels = real artifacts”).

-----

## 2 · Rollenmodell (rollenbasierte UI)

Eine UI, drei Sitzpositionen. Die Rolle steuert **Default-Landing, Navigations-Reihenfolge, Dichte und
Schreibrechte** — nicht den Funktionsumfang der einzelnen Screens. Rollenwechsel im Prototyp links oben.

|Rolle             |Primärer Job                                 |Default-Landing      |Nav-Schwerpunkt                                                   |Rechte                                         |
|------------------|---------------------------------------------|---------------------|------------------------------------------------------------------|-----------------------------------------------|
|**Operator**      |Betrieb, Monitoring, Triage                  |Übersicht (Health)   |Übersicht · Incidents · Objekte · Lineage · Runs                  |Lesen; Incidents bestätigen/zuweisen           |
|**Steward**       |Contracts autorisieren, Proposals entscheiden|Contracts (Workbench)|Contracts · Vorschläge · Objekte · Übersicht · Lineage            |Schreiben auf eigene Domänen/Produkte          |
|**Platform Owner**|Multi-Space-Setup, Lineage-Tiefe, Governance |Lineage (Coverage)   |Lineage · Objekte · Contracts · Übersicht · Incidents · Governance|Superset; Policy `owned_by`, Gating, Schema-Map|

**Product-Owner-Variante:** kein eigener Top-Level, sondern ein **Steward mit Scope auf genau ein
Data Product**. Das Policy-Feld `owned_by` (platform vs. product) entscheidet pro Check, wer schreiben
darf — sichtbar als Lock-Icon / Ownership-Tag. Das ist die UI-Form der Dual-Ownership.

Read-only-Zustände werden **nicht versteckt, sondern markiert** (Banner „Nur-Lese-Ansicht — als
Operator angemeldet”, deaktivierte Primäraktionen mit Hinweis). So bleibt das mentale Modell für alle
Rollen identisch.

-----

## 3 · Informationsarchitektur

**Empfehlung (mit Begründung — bewusst gegen die naheliegenden Alternativen):**

Top-Level-Navigation = **Übersicht · Objekte · Contracts · Lineage · Incidents · Vorschläge**,
dazu Utility = **Runs · Governance**. Plus globale **Command Palette (⌘K)** und **Space-Switcher**.

Warum nicht die naheliegenden Modelle:

- **Nicht Lifecycle-orientiert** (Draft → Workbench → Compile → Certify als Nav). Nur der Steward lebt
  im Lifecycle; für alle anderen wären es leere Durchgangsstufen. → Lifecycle wird zum **Stepper
  innerhalb von Contracts**, nicht zur globalen Navigation.
- **Nicht Familien-orientiert** (Observability | Quality als Sektionen). Das zerschneidet das Objekt —
  wer `gl_account_line_item_view` untersucht, will beide Familien an einem Ort. → Familie ist
  **Attribut, Filter und Farbe**, kein Top-Level.
- **Objekt-zentrisch als Rückgrat**, weil die Architektur das Objekt bereits zum mappingfreien
  Universalschlüssel macht. Die Task-Surfaces (Health, Incidents, Vorschläge, Lineage) sind
  Einstiegspunkte für die Primärjobs der drei Rollen und greifen alle auf dieselbe Objekt-Wahrheit zu.

**Route-Map:**

```
/                      → Übersicht (Health-Cockpit)
/objects               → Katalog (Tabelle, Filter nach Layer)
/objects/:id           → Objekt-Detail (Tabs: Checks · Läufe · Contract · Lineage)
/contracts             → Workbench (Liste + Editor + Check Builder als Drawer)
/lineage               → Coverage Map (Signature)
/incidents             → Triage-Inbox (+ Detail)
/proposals             → Feedback-Loop (Proposal Miner)
/runs/:id              → Lauf-Detail (dq_results)
/governance            → Policy owned_by · Gating-Zustände · Acceptance-Gates
```

-----

## 4 · Design-System (Tokens)

**Theme: dark.** Schichtung neutral-kühl (Dev-Tool), nicht reinschwarz.

```
Flächen     bg-0 #0B0D11 (App) · bg-1 #13161C (Panel) · bg-2 #1A1F27 (raised) · bg-3 #222831 (overlay)
Linien      line #222934 (hairline) · line-2 #313945 (stark)
Text        fg #E7EBF2 · fg-2 #98A2B2 (sekundär) · fg-3 #5E6877 (Labels/tertiär)

Familien    Observability #E8973C · Quality #3FB07A · Flow #2FAFC0
            Contract #5E83E6 · Feedback #9E73E0 · Human #E06A9B
Status      OK #3FB07A · Warn #E0B23E · Fail #E2783C · Critical #E5484D · Stale #646E7C · Draft #5E83E6
Coverage    ● Definiert (grün) · ◐ Teilweise (amber) · ▲ Lücke (rot) · ○ Außer Scope (grau)

Primäraktion = near-white (#EEF1F6) auf dunkel — kein bunter Akzent.
Damit ist die einzige Chroma im Chrome das semantische Familien-/Status-System.
```

**Typografie.** Display/Body: **DM Sans** (400/500/600/700). Utility/Daten: **JetBrains Mono**.
Dichte Skala (Dev-Tool läuft klein): 11px Micro-Labels · 12px sekundär · 13px Default · 15px
Section-Titel · 19px Page-Titel · 30px Big-Numbers. Enge Zeilenhöhen.

**Komponenten-Inventar** (im Prototyp implementiert): `StatusPill`, `StatusDot`, `FamilyTag`,
`CovFlag`, `Spark` (Sparkline), `Kpi`, `Panel` (mit Accent-Spine), dichte `Table`, `Command Palette`,
Right-`Drawer` (Check Builder / Lineage-Inspector), `Lifecycle`-Stepper, Segment-Control, Tabs.

**Qualitäts-Boden:** sichtbarer Keyboard-Fokus, `prefers-reduced-motion` respektiert, dezente Motion nur
auf View-Wechsel/Palette/Drawer. Responsiv bis Tablet (darunter: Sidebar kollabiert, Splits stapeln).

-----

## 5 · Screen-Specs

### 5.1 Übersicht — Health-Cockpit (Operator-Default)

**Zweck:** Flotten-Gesundheit auf einen Blick. **Elemente:** 4 KPI-Tiles (Objekte überwacht, Health %,
Contracts aktiv, Freshness-SLO); zwei Familien-Panels (Observability orange / Quality grün) mit je 4–5
Statuszeilen; Pass-Rate-Trend (Area, 20 Läufe, beide Familien); Offene-Incidents-Feed (klickbar →
Incident). **States:** Empty = „Noch keine Läufe — ersten Run starten”. Loading = Skeleton-Tiles.

### 5.2 Objekte — Katalog + Detail

**Katalog:** dichte Tabelle, Filter nach Layer (Landing/Harmonization/Product). Spalten: Objekt
(mono + businessName + Familien-Spine), Layer, Status-Pill, Contract-Status, Coverage-Flag, #Checks,
Owner (`platform`-Lock oder Team), letzter Lauf.
**Detail:** Header (mono-Name, Status, Coverage), Meta (Schema, Layer, Zeilen, Ownership). Tabs:

- **Checks** — gruppiert nach Familie; Spalte/Bezug, `expect`, `actual_value` (rot bei Fail), Severity,
  Trend-Sparkline, Pass/Fail. Read-only **Compile-Peek** zeigt das aus dem Contract generierte SQL.
- **Läufe** — `dq_results`-Lauf (run_id mono, overall, total/passed/failed, schema, `triggered_by`).
- **Contract / Lineage** — Sprung in die jeweilige Surface mit vorausgewähltem Objekt.

### 5.3 Contracts — Workbench (Steward-Default)

**Liste:** Contracts mit Status (Entwurf/aktiv/breached), Owner, Familien-Spine.
**Editor:** oben **Lifecycle-Stepper** in Nutzersprache (Entwurf → Review → Kompilieren → Zertifiziert).
Darunter die **semantischen Garantien** als Sektionen — Identität, Freshness-SLA, Volume-Schranken,
Schema, Keys, Referential, Measures. **Kein SQL.** Inline-Hinweis macht das explizit. Severity-Promotion
(`warn → block`) als Toggle pro Garantie. **Vorgeschlagene Erweiterungen** (aus Feedback-Loop) mit
Übernehmen/Ablehnen. Compile-Bar: Check Builder · Compile-Vorschau · Kompilieren & Zertifizieren.
**Check Builder (Drawer):** Check-Typ aus der Library (Kategorien Vollständigkeit · Konsistenz ·
Verteilung & Aggregate · Aktualität & Sonstiges), Parameter (Spalte, Erwartung), Severity, **Platzierung
via Lineage-Auto-Scope §4.3a** (Layer-Pfad), und read-only **kompilierte SQL-Vorschau**. Der Check
Builder ist der **einzige Compiler** von semantischer Garantie → ausführbarem `checks/*.yml`.

### 5.4 Lineage — Coverage Map (Signature, Platform-Default)

**Das differenzierende Screen.** Ein geschichteter DAG (Landing → Harmonization → Product). Jeder Knoten
trägt **gleichzeitig** Live-Status (Farbkante/Dot) **und** Coverage-Flag (● ◐ ▲ ○). Klick auf Knoten →
**Root-Cause:** Vorfahren-Pfad wird hervorgehoben, Rest gedimmt; ein breachter Knoten zeigt die
wahrscheinliche Upstream-Ursache (z.B. `Sales_Orders_View` ohne Key → Uniqueness propagiert nach
`gl_account_line_item_view`). Inspector (unten rechts): Status, Coverage, Typ, Ursache, „Objekt öffnen” /
„Check hier” (→ Check Builder mit vorausgefüllter Platzierung). Diese Fusion aus Observability (Live-
Status) + Contract (Coverage) + Lineage gibt es bei Monte Carlo (Lineage ohne Coverage-Overlay) und dbt
(Tests ohne Live-Observability) so nicht.

### 5.5 Incidents — Triage

Inbox-Stil (Linear-artig): Severity-Dot, Titel, Objekt (mono), Zeit, Status (offen/bestätigt/gelöst).
**Detail:** failing Check (mono: `expect` vs `actual_value`), **Blast Radius** (Downstream-Consumer),
Aktionen Bestätigen · Root-Cause im Lineage · Objekt öffnen. Incidents sind kein eigener Store, sondern
abgeleitet aus breachten `dq_results`-Zeilen.

### 5.6 Vorschläge — Feedback-Loop

Karten aus dem **Proposal Miner**: pro Vorschlag Objekt, Check, `from → to` (alte → neue Schranke),
Konfidenz, Begründung aus dem **Statistik-Tupel** (min/max/p01/p99/mean/stddev), Warm-up-Status.
Aktionen Übernehmen (→ Contract-Amendment) · Ablehnen · Snooze. Auto-Apply **erst nach Steward-
Bestätigung**. Banner stellt klar: keine Rohdaten verlassen HANA (privacy-safe).

### 5.7 Governance (Platform Owner)

Dual-Ownership `owned_by` (welche Checks platform- vs. product-owned), Gating-Zustände als **first-class
states** (stale-skipped, volume-anomaly hold, schema-drift → regen, key-unverified → downgrade), und die
zwei **Acceptance-Gates** (kein SQL im Contract; keine hartcodierten `CENTRAL`-Referenzen im Compiler).

### 5.8 Command Palette (⌘K), global

Springt zu Objekt / Ansicht / Aktion, wechselt Rolle. Pfeiltasten + Enter, Esc schließt. Zentrales
Dev-Tool-Signal für Tempo.

-----

## 6 · Schlüssel-Flows

1. **Contract autorisieren → kompilieren → zertifizieren** (Steward). Auto-Seed-Entwurf öffnen →
   semantische Garantien schärfen (SLA, Schranken, `warn → block`) → Check Builder kompiliert nach
   `checks/*.yml` → Compile-Vorschau prüfen → Kompilieren & Zertifizieren → Lifecycle springt auf aktiv.
1. **Incident triagieren → Root-Cause → fixen** (Operator → Steward). Incident öffnen → Blast Radius
   sehen → „Root-Cause im Lineage” → Upstream-Ursache erkennen → „Check hier” am verursachenden Knoten.
1. **Proposal minen → übernehmen → Contract erweitern** (Steward). Vorschlag prüfen (Statistik-Begründung,
   Warm-up) → Übernehmen → erscheint als Amendment im Contract → nächster Run erzwingt die neue Schranke.
1. **Check platzieren via Lineage** (§4.3a). Im Lineage-Inspector „Check hier” → Check Builder mit
   vorausgewähltem Layer/Objekt → Typ + Parameter → in Contract übernehmen.

-----

## 7 · Architektur-Treue — verbindliche UI-Regeln

Diese Punkte sind keine Stilfragen, sondern setzen Architekturentscheidungen in der UI durch:

- **Kein SQL im Contract.** Der Editor zeigt ausschließlich semantische Garantien. SQL erscheint nur als
  read-only **Compile-Vorschau**. Der Check Builder ist der einzige Compiler — Voraussetzung für
  Dual-Ownership.
- **Ein Executor.** Alle Checks laufen gegen die HANA-Repräsentation. Die UI bietet keinen alternativen
  Run-Target (kein Delta-Sharing-Run) an.
- **Dual-Ownership = `owned_by` sichtbar.** Lock-Icon/Ownership-Tag pro Check; Schreibrechte folgen der
  Policy, nicht der Rolle allein.
- **Gating-Zustände sind first-class UI-Zustände**, keine stillen Auslassungen: `stale-skipped`,
  `volume-anomaly hold`, `schema-drift → regen`, `key-unverified → downgrade` erscheinen als eigener
  Status (grau/amber), nicht als „kein Ergebnis”.
- **Coverage zunächst auf Objekt-Granularität.** `columnEdges` sind aktuell leer (bekannter Parser-Defekt,
  690 Kanten als `direct` ohne Expression). Die Coverage-Flags arbeiten daher heute auf Objektebene;
  Spalten-Level-Coverage ist Roadmap (siehe §9) — die UI ist darauf vorbereitet (Flag-Modell skaliert auf
  Spalten), behauptet aber keine Spalten-Coverage, die es noch nicht gibt.
- **`Sales_Orders_View` ohne Key** ist im Prototyp als konkreter Erstfall sichtbar: Coverage = Lücke (▲),
  Vorschlag `duplicate(OrderID, ItemNo) = 0` · critical.

-----

## 8 · Technische Umsetzung (Flask + React)

### Flask-API-Oberfläche (was das React-Frontend braucht)

|Endpoint                                                              |Quelle / Komponente                                                   |
|----------------------------------------------------------------------|----------------------------------------------------------------------|
|`GET /api/objects?space=`                                             |`inventory.json` + `dq_object_status`-Rollup                          |
|`GET /api/objects/:id`                                                |Inventar + letzter Lauf aus `result_store.py`                         |
|`GET /api/objects/:id/runs`, `GET /api/runs/:run_id`                  |`dq_results` (`ResultStore`)                                          |
|`GET /api/lineage?space=`                                             |`lineage.json` (nodes/edges; `columnEdges` leer → Objekt-Granularität)|
|`GET / PUT /api/contracts/:id`                                        |semantischer YAML-Contract in Git; PUT prüft No-SQL-Gate              |
|`POST /api/contracts/:id/compile`                                     |Check-Builder-Compiler → `checks/*.yml` (einziger Compiler)           |
|`POST /api/objects/:id/run`                                           |`gx_runner.py` / `dq_check_runner.py`                                 |
|`GET /api/proposals`, `POST /api/proposals/:id/{accept,reject,snooze}`|Proposal Miner (Zeitreihen `actual_value` + Statistik-Tupel)          |
|`GET /api/incidents`                                                  |abgeleitet aus breachten `dq_results`-Zeilen                          |
|`GET /api/check-library`                                              |`check_library.json`                                                  |
|`GET /api/stream` (SSE/WebSocket)                                     |Live-Run-Status für die Run-Indicator-Pille                           |

### React-Struktur

Routen spiegeln die Navigation (§3). Server-State über React Query/SWR (Cache + Revalidate);
leichter Context für **Rolle** und **Space** (session-scoped). Geteilte Komponenten exakt wie im
Prototyp. Charts: recharts. Lineage in Produktion: **Cytoscape.js + dagre** (im Prototyp als SVG-DAG
nachgebildet, damit klick-/root-cause-fähig ohne externe Lib).

### Prototyp → reale Komponenten

Die Mock-Konstanten (`OBJECTS`, `INCIDENTS`, `PROPOSALS`, `LIN_NODES/EDGES`, `CHECK_LIB`) sind 1:1 die
Form der obigen API-Antworten. `gl_account_line_item_view` mit 818 Dubletten, Lauf `c74831dd`,
`triggered_by: ui` stammen direkt aus `dq_results.json`; die Check-Typen aus `check_library.json`;
die Objektnamen/Ketten aus `inventory_2.json` / `lineage_2.json`.

-----

## 9 · Roadmap & offene Punkte

- **Spalten-Level-Coverage** sobald `_column_lineage` / `_sql_column_parser` echte `columnEdges` liefert
  (CQN-Walker-Fix). Flag-Modell skaliert dann von Objekt auf Spalte.
- **Authoring-Home** für `product_owner`-Contracts: Ausrichtung auf Data Product Studio (H1 2026 GA) —
  beeinflusst, ob der Workbench-Editor eigenständig bleibt oder andockt.
- **BDC additiv.** ORD-Capability- und Fiscal-Completeness-Checks sind in der Library als zusätzliche
  Blätter angelegt, nicht als Voraussetzung.
- **Was im Prototyp gemockt ist:** Live-Streaming, Auth/Rollen-Backing, Persistenz von Actions
  (Übernehmen/Bestätigen sind UI-Stubs). Editor-Schreibpfad und Compiler-Aufruf sind als Buttons
  vorhanden, aber nicht verdrahtet.
- **Visuelle QA:** Screens am echten Datenvolumen gegenprüfen (Tabellendichte bei >500 Objekten;
  Lineage-Layout bei breiten DAGs — dagre-Tuning).

-----

*Begleitdateien: `DQCockpit_Prototype.jsx` (lauffähiger Prototyp der Kern-Screens).
Farbsystem und Konventionen anschlussfähig an die bestehenden Konzept- und HTML-Deliverables.*