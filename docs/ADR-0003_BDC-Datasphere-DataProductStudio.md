# ADR-0003 — Signal in einem BDC/Datasphere-Setup mit Data-Product-Studio-Datenprodukten

**Adressat:** Beratung, Plattform-Team, Governance, Entwicklung · **Stand:** 2026-06-22
**Status:** *Beschlossen* (accepted) — bewertet, wie Signals Konzept mit den kommenden Custom Data Products aus dem **Data Product Studio** (BDC) zusammenspielt; betrachtet beide Auslieferungspfade (HDLF-Spaces und SQL-Output-Port). **V1 + V7 sind für die Topologie „HDLF-Objekt → in dedizierten Monitoring-Space geteilt → View darüber" gelöst** (Grilling 2026-06-22); Umsetzung in [`PLAN_ADR-0003-0004_Implementation.md`](PLAN_ADR-0003-0004_Implementation.md).
**Zweck:** Festhalten, **wo** Signals konzeptionelle Ebene (boundary × Lite/Full) und Signals **technische** Ebene (GX-on-HANA-Executor) bei BDC-Custom-Datenprodukten greifen — und wo nicht — abhängig davon, ob ein Datenprodukt auf einem **HDLF-Space** (Object Store, Delta/Parquet) oder über einen **SQL-Output-Port** ausgeliefert wird.

> Verwandte Dokumente: `ADR-0001_Quality-Gates_vs_Contracts.md` (boundary-Diskriminator, Komposition §10, DSP-Taxonomie-Tiering §11) · `ADR-0004_DataProduct-als-Komposition.md` (Manifest + aus Lineage abgeleitetes Interieur, `boundary` = Intent ⋈ Reality — **§12 dieser ADR bewertet ADR-0003 unter dieser Linse neu**) · `Zusatz_ContractLifecycle_ORDBDCIntegration.md` (ORD/ODCS-Seam, Port-Topologie, offene Punkte R1/R2/R7) · `Vortrag_Briefing_DataProducts_DataContracts_DSP_BDC.md` (fünf Schichten, Output-Port = Delta Share **oder** exponierte View, §1.5) · `Betriebsmodi_Lite_und_Full.md` (Prozess-Zeremonie) · `Tooldokumentation.md` (Architektur, Executor).
> Aktive Verifikations-/Phase-2-Punkte sind seit 2026-07-04 in [`OPEN_TASKS.md`](OPEN_TASKS.md) §P konsolidiert.
>
> **Nachtrag (Neubewertung):** §0–§11 behandeln ein Datenprodukt als *eine* SQL-Oberfläche (den Output-Port). Ein Custom Data Product aus dem Studio ist aber ein **Fluss aus mehreren Objekten** (Input → Transformation → Output). **§12** sagt konkret, wie ADR-0004 das umsetzt: Das Manifest deklariert nur Anfang und Ende des Flusses, die Transformationen leitet die Lineage ab — und Signal prüft nur die Stellen, die SQL sprechen (*derive überall, enforce nur an SQL*).

---

## 0 — Kernaussage

Signals **Konzept-Ebene ist speicher-agnostisch** und überträgt sich **unverändert** auf Data-Product-Studio-Produkte: `boundary` (internal | inbound | outbound) klassifiziert eine *Parteigrenze*, nicht einen *Speicherort*; das Tiering aus ADR-0001 §11 (Tier 0/1/2 × Lite/Full) gilt für ein HDLF-Produkt genauso wie für ein HANA-Produkt.

Signals **Enforcement-Ebene ist dagegen nicht speicher-agnostisch.** Der einzige Executor ist **GX-on-HANA** (`hdbcli`, read-only): jeder Check ist ein SQL-Template gegen `"{schema}"."{dataset}"` (`packages/dq_core/library/check_library.json`). Damit gilt der harte Satz dieser ADR:

> **Signal erzwingt an der SQL-erreichbaren Oberfläche eines Datenprodukts.** Hat das Produkt einen SQL-Output-Port (HANA-Space-Produkt **oder** HDLF-Produkt via SQL-on-Files), wendet der vorhandene Executor **unverändert** an. Ist das Produkt ein *reiner* Object-Store-/Delta-Share-Auslieferung **ohne** SQL-Oberfläche, liegt es **außerhalb** der heutigen Executor-Reichweite — und das soll **nicht** durch einen zweiten Executor geheilt werden (Verstoß gegen das „single executor"-Prinzip und Gate G7).

Die Begriffsunsicherheit des Auftraggebers („SQL-Output-Port — keine Ahnung was das heißt") löst sich genau hier auf: Für Signal kollabieren *„Produkt auf HANA-Space"* und *„HDLF-Produkt via SQL-on-Files konsumierbar"* auf **dieselbe** Sache — eine relationale, per SQL adressierbare Oberfläche = Signals Enforcement-Naht. Nur der dritte Fall (Delta-Share-only, keine SQL-Sicht) ist der harte Fall.

---

## 1 — Kontext: Was sich mit Data Product Studio ändert

**Data Product Studio** (BDC) ist das Werkzeug, mit dem Kunden **eigene** (custom) Datenprodukte bauen — über die von SAP gelieferten Standard-Produkte hinaus. Für Signal sind drei Fakten relevant:

1. **Auslieferungspfad „HDLF-Spaces" ist der erste Weg, den SAP geht.** Die physischen Daten eines solchen Produkts sind **Dateien** in einem Object Store (HANA Data Lake Files, Delta/Parquet) — **keine** HANA-Tabellen. Das ist der für Signal entscheidende Unterschied gegenüber dem klassischen Datasphere-Bild (Fact View / Analytic Model auf HANA), das den Signal-Docs bisher zugrunde liegt.
2. **Ein Datenprodukt kann (auch) einen SQL-Output-Port haben.** Was das genau bedeutet, ist offen (siehe §3). Klar ist nur: Es existiert ein Konsumweg, der **SQL** spricht.
3. **Jedes Studio-Produkt ist ein Katalog-/ORD-Produkt.** Das ändert nichts an ADR-0001 §11: „Katalog-Produkt ≠ governter Contract." Studio erzeugt Produkte tool-getrieben; ob ein *governter Outbound-Contract* nötig ist, bleibt eine Tier-Entscheidung entlang der Lineage.

Die bisherigen Signal-Docs gehen implizit von HANA-erreichbaren Objekten aus: Das Briefing nennt als Output-Port den **Delta Share oder die exponierte Consumption-View** (`Briefing §1.5`), und der Zusatz-Doc fragt bereits in **R1** explizit, ob ein ORD-Port „inline eine Delta-Sharing-/ODBC-/**HDLF**-Quelle tragen" kann, sowie in **R7** nach dem „HDLF-CLI-Permission-Gap". Diese ADR zieht die HDLF-Frage aus dem Anhang in den Vordergrund und entscheidet die Enforcement-Seite.

---

## 2 — Signals technische Realität (der harte Constraint)

| Schicht | Heutige Bindung | Folge für BDC |
|---|---|---|
| Verbindung | `hdbcli.dbapi.connect(...)` (`connect/db_connection.py`) — **nur HANA** | erreicht nur, was über das **HANA-SQL-Interface** sichtbar ist |
| Check-Form | SQL-Template `SELECT … FROM "{schema}"."{dataset}"` (`library/check_library.json`, 20 Checks) | braucht einen **zweiteiligen, SQL-auflösbaren Objektnamen** |
| Bindung | Schema erst zur Laufzeit gebunden (Gate G2, `[SCHEMA-MAP]`) | adressiert über `{schema}`/`{dataset}`, kein Hardcoding |
| Prinzip | **ein** Executor (GX-on-HANA), Engine framework-frei (Gate G7) | ein zweiter (Spark/Delta-)Executor ist explizit unerwünscht (`Zusatz §4/§5`) |

Daraus folgt die Reichweiten-Regel: **Signal sieht ein Datenprodukt genau dann, wenn das HANA-SQL-Interface es als (virtuelle) Relation `schema.dataset` ausliefern kann.** Alles andere ist für den Executor unsichtbar — unabhängig davon, wie gut die Konzept-Ebene passt.

---

## 3 — Auflösung der Begriffsunsicherheit „SQL-Output-Port"

Der Auftraggeber nennt drei Hypothesen. Bewertung jeder einzelnen aus Signal-Sicht:

| # | Hypothese des Auftraggebers | Bewertung | Für Signal heißt das |
|---|---|---|---|
| (a) | Produkte werden **auf HDLF-Spaces** gebaut (SAPs erster Weg) | zutreffend als *Speicher*-Aussage; sagt für sich genommen **nichts** über die Konsum-Schnittstelle | Daten = Dateien; Executor-Reichweite **erst** über eine SQL-Sicht |
| (b) | SQL-Output-Port heißt vielleicht: man kann Produkte **auf HANA-Spaces** bauen | plausibel; ein HANA-Space-Produkt hat naturgemäß eine SQL-Oberfläche | **Happy Path** — Executor greift unverändert |
| (c) | Produkte im HDLF-Space sind vielleicht einfach **per SQL-on-Files** konsumierbar | technisch die wahrscheinlichste Bedeutung des „SQL-Output-Ports" für ein HDLF-Produkt | **Happy Path** — sobald die SQL-on-Files-Relation steht |

**Schlussfolgerung:** (b) und (c) **kollabieren für Signal auf dasselbe** — eine relationale, per SQL adressierbare Oberfläche. Ob diese Oberfläche eine native HANA-Tabelle/-View (b) oder eine SQL-on-Files-Virtual-Table über Parquet/Delta im HDLF (c) ist, ist dem SQL-Template **gleichgültig**, solange ein stabiler zweiteiliger Name `"{schema}"."{dataset}"` auflöst. Der „SQL-Output-Port" ist damit aus Signal-Sicht **die kanonische Enforcement-Naht** — und zugleich exakt der „Output Port" der Briefing-§1.5 / des 1:1:1:1-Prinzips (Data Contract → Output Port → Schema → Read Role).

> **Verifikationspunkt V1 [H]:** SQL-on-Files / HDLF-Virtual-Table — liefert das HANA-SQL-Interface den Produkt-Inhalt unter einem **stabilen, zweiteiligen** Namen (`schema.object`), oder braucht es eine andere Adressierung (Catalog-präfix, Virtual-Table-Wrapper, Remote-Table)? Das entscheidet, ob die Template-Anpassung in §8 *null* oder *gering* ist.

### 3.1 — Entscheidungsbaum: Wo enforced Signal bei einem Studio-Produkt?

Die ganze ADR lässt sich auf **eine** operative Frage je Datenprodukt verdichten: *Gibt es eine SQL-erreichbare Oberfläche desselben Inhalts?* Daran hängt, ob Signal direkt, transitiv oder gar nicht prüft.

```mermaid
flowchart TD
    A["Studio-Datenprodukt<br/>(Custom, BDC)"] --> B{"Output-Port<br/>spricht SQL?"}
    B -- "ja: HANA-View / SQL-on-Files / ODBC" --> C["Direktes Enforcement<br/>GX-on-HANA gegen schema.object"]
    B -- "nein: nur Delta Share / Object Store" --> D{"SQL-erreichbare<br/>Repräsentation<br/>desselben Inhalts?"}
    D -- "ja: SQL-on-Files-Projektion<br/>oder HANA-Upstream" --> E["Transitives Enforcement<br/>an der SQL-Repräsentation<br/>(Deklaration != Enforcement)"]
    D -- "nein" --> F["Out-of-scope für den Executor<br/>KEIN zweiter Executor (G7)"]

    C --> G{"boundary?"}
    E --> G
    G -- "outbound (Konsum-Grenze)" --> H["Outbound-Contract<br/>Lite/Full nach Tier (ADR-0001 §11)"]
    G -- "internal (kein externer Consumer)" --> I["Internes Quality Gate<br/>keine Contract-Zeremonie"]

    classDef ok fill:#dfe,stroke:#3a3,stroke-width:1px;
    classDef warn fill:#fee,stroke:#c33,stroke-width:1px;
    classDef seam fill:#fde,stroke:#c39,stroke-width:2px;
    class C,E ok;
    class F warn;
    class H,I seam;
```

Lesehilfe: Die **obere** Hälfte (B/D) ist die **technische** Reichweiten-Entscheidung (Executor-Naht, §4/§5); die **untere** Hälfte (G) ist die **governance**-seitige Klassifikation, die unverändert aus ADR-0001 stammt (§6 dieser ADR). Beide sind orthogonal: Ein out-of-scope-Produkt (F) kann governance-seitig sehr wohl ein Tier-2-Outbound-Contract *sein* — nur kann Signal ihn dann nicht *erzwingen*. Das ist der Punkt, an dem das Kunden-Framing greift: „Tier-2 ⇒ gib dem Produkt einen SQL-Output-Port."

### 3.2 — Durchgespielt: ein HDLF-Custom-Produkt

Beispiel `sales_orders_curated`, im Data Product Studio auf einem **HDLF-Space** als Delta-Tabelle gebaut, von einem anderen Team (FIN-Reporting) konsumiert.

| Schritt | Frage | Ergebnis |
|---|---|---|
| 1 | Output-Port spricht SQL? | Studio exponiert eine **SQL-on-Files-Sicht** `SALES."ORDERS_CURATED"` → **ja** (Zweig C) |
| 2 | boundary? | Konsum durch **anderes Team** über Grenze → `outbound` (Zweig H) |
| 3 | Tier? | mehrere abhängige FIN-Reports → **Tier 2 / Full** (SemVer, Approval) |
| 4 | Enforcement | 20 Bibliotheks-Checks gegen `SALES.ORDERS_CURATED` — `row_count`, `freshness` (über Lade-/Partitionsspalte, V3), `schema`-Closed-Mode, Ref-Integrität — **ohne Engine-Änderung** |
| 5 | Deklaration | Outbound-Contract-YAML (Source of Truth); ORD/CSN als einseitige Derivate (Zusatz §5) |

**Gegenprobe — derselbe Inhalt nur als Delta Share, ohne SQL-Sicht:** Schritt 1 → Zweig D. Existiert eine HANA-Upstream-Tabelle, aus der der Share gespeist wird → transitives Enforcement dort (Zweig E). Existiert sie nicht → Zweig F: governance-seitig bleibt es ein Outbound-Contract, aber Signal kann ihn nicht erzwingen → ehrlich als „nicht überwacht" in der Coverage-Map ausweisen, **nicht** grün vortäuschen.

---

## 4 — Fall 1: Datenprodukt auf HDLF-Space (SAPs erster Weg)

**Physik:** Dateien (Delta/Parquet) im Object Store. **Konzept-Ebene:** vollständig anwendbar — das HDLF-Produkt ist ein Data Product im Sinne von ADR-0001 (das Ganze, in einer Ownership), sein Output-Port ist die Outbound-Grenze, das Tiering (§11) entscheidet über Contract-Aufwand. **Enforcement-Ebene:** hängt allein daran, **ob eine SQL-Sicht existiert**:

| Konsum-Schnittstelle des HDLF-Produkts | Signal-Executor | Vorgehen |
|---|---|---|
| **SQL-on-Files-Sicht** vorhanden (Fall 3c) | ✅ erreichbar | Checks gegen die Virtual-Table wie gegen eine HANA-Tabelle — Happy Path |
| **Delta Share / nur Object-Store-Zugriff**, keine SQL-Sicht | ❌ nicht erreichbar | **transitiv** an der SQL-erreichbaren Upstream-Oberfläche prüfen (s. u.) **oder** out-of-scope |

**Wichtig — Delta Share ist kein SQL-Endpoint.** Ein Delta Share wird von Spark-/Databricks-Clients konsumiert, nicht über SQL. Signal kann einen Delta Share **nicht direkt** testen. Die saubere Auflösung folgt dem schon gesetzten Muster *Deklaration ≠ Enforcement* (ADR-0001 §10.5): Der Delta Share ist die **Deklaration** (Output-Port-Versprechen); das **Enforcement** setzt Signal an der SQL-erreichbaren Repräsentation **desselben** Inhalts an — der SQL-on-Files-Projektion bzw. dem HANA-Objekt, aus dem der Share gespeist wird. Existiert **gar keine** solche Repräsentation, ist das Produkt für den GX-on-HANA-Executor schlicht unsichtbar; dann ist die ehrliche Antwort „out-of-scope für den Executor", **nicht** „wir bauen einen Spark-Executor".

**Datenseitige Feinheiten bei Files (kleinere Param-Anpassung, keine Architektur):**

- `row_count`/`volume_anomaly` = `COUNT(*)` über die Virtual-Table → korrekt, aber bei großen Parquet-Beständen ggf. **teuer** (Full-Scan). Pruning/Partition-Prädikate als Check-Param vorsehen.
- `freshness` erwartet heute eine **Daten-Spalte** (`column: ORDER_DATE`). Bei Files lebt Frische oft in **Partitionspfaden/Datei-Timestamps**, nicht in einer Spalte. Entweder eine konventionelle Lade-/Partitionsspalte verlangen oder Freshness über Datei-/Partitions-Metadaten modellieren (Folge-Workstream, nicht Teil dieser ADR).
- Schema-/Closed-Mode-Checks (Gate G2, Laufzeit-Bindung) funktionieren über die Virtual-Table-Spaltenliste unverändert.

---

## 5 — Fall 2: Datenprodukt mit SQL-Output-Port

Das ist der **empfohlene Integrationszielzustand** und der technisch einfachste Fall — unabhängig davon, ob der SQL-Port ein HANA-Space-Produkt (3b) oder eine SQL-on-Files-Sicht über HDLF (3c) ist:

- Der Executor braucht nur **Verbindungs-Koordinaten** (gibt es) und einen **auflösbaren Objektnamen** (= der Port liefert ihn). `{schema}.{dataset}` bindet auf genau das, was der Output-Port exponiert.
- Alle 20 Bibliotheks-Checks, die Compliance-Ampel, Coverage-/Lineage-Map, Incidents und der Proposal-Miner greifen **ohne Code-Änderung**.
- Der SQL-Output-Port ist 1:1 die **Outbound-Grenze** (`boundary: outbound`). Das 1:1:1:1-Prinzip (Briefing §1.5) wird konkret: **ein** Contract pro Output-Port, gegen das Signal an genau diesem Port enforced.

→ Wo der Kunde die Wahl hat, ist ein **SQL-Output-Port die für Signal-Governance bevorzugte Auslieferung**. Das ist auch das ehrliche Kunden-Framing: „Gib dem Produkt einen SQL-Output-Port, dann ist es ohne Zusatzaufwand contract-überwachbar."

---

## 6 — Konzept-Ebene: überträgt sich unverändert (der Teil, der *nicht* wackelt)

Unabhängig von HDLF vs. SQL-Port bleibt **alles aus ADR-0001 / dem Briefing gültig**, weil `boundary` eine Grenze klassifiziert, keinen Speicher:

| Konzept | Gilt bei BDC-Studio-Produkten? | Begründung |
|---|---|---|
| `boundary` (internal/inbound/outbound) | **ja, 1:1** | Output-Port = Outbound-Grenze; interne Studio-Transformationsschritte = `internal` Gates |
| Data Product = das Ganze, Contract = nur die Ränder | **ja** | Studio-Produkt umfasst Inbound→Transformation→Output; Contract beschreibt nur den/die Port(s) |
| Tiering Tier 0/1/2 (§11) | **ja** | „alle Dims sind Foundation Products" gilt in BDC *erst recht* (ORD je Objekt); Tier datengetrieben aus Lineage |
| Layer ≠ Grenze, Objekt ≠ Produkt | **ja** | ein HDLF-Zwischen-File ist so wenig ein Contract wie eine Core-Tabelle |
| Gekettete Contracts (Fall B, §10.4) | **ja** | Studio-Produkt kann Upstream-Produkt konsumieren → `inbound`-Referenz + eigener `outbound` |
| ORD/ODCS als einseitige Derivate (Zusatz §5) | **ja** | Studio emittiert ORD; YAML-Contract bleibt Source of Truth, ORD/CSN = Derivate |

**Einzige konzeptionelle Schärfung:** Der Begriff „Output Port" wird in BDC **konkreter und potenziell mehrfach** — ein Produkt kann mehrere Ports haben (z. B. Delta Share **und** SQL-on-Files **derselben** Daten). Regel: Pro *governter* Grenze **ein** Outbound-Contract; mehrere physische Ports auf **denselben** Inhalt sind verschiedene *Transporte* einer Zusage, nicht mehrere Verträge. Signal enforced an dem Port, der SQL spricht; die Zusage gilt für alle Ports desselben Inhalts (Transport-Äquivalenz).

---

## 7 — Entscheidung

1. **Konzept-Ebene unverändert übernehmen.** `boundary` × Lite/Full und das §11-Tiering gelten für BDC-Studio-Produkte ohne Anpassung. Kein Schema-, kein Modell-Eingriff auf der Governance-Seite.
2. **Den SQL-Output-Port als Signals kanonische Enforcement-Naht festlegen.** Signal erzwingt an der SQL-erreichbaren Oberfläche des Output-Ports. „HANA-Space-Produkt" und „HDLF-Produkt via SQL-on-Files" werden vom Executor **identisch** behandelt.
3. **Fall 2 (SQL-Output-Port) ist der unterstützte Happy Path** und der empfohlene Auslieferungs-Zielzustand für contract-governte Produkte — voraussichtlich **null bis triviale** Code-Änderung (abhängig von V1).
4. **Fall 1 (HDLF-Space) wird unterstützt, *sofern* eine SQL-on-Files-Sicht existiert.** Ohne SQL-Sicht: **transitive** Prüfung an der Upstream-SQL-Oberfläche; existiert auch die nicht, ist das Produkt **explizit out-of-scope** für den Executor.
5. **Keinen zweiten Executor bauen.** Ein Spark-/Delta-/Object-Store-Executor wird **abgelehnt** — er bricht „single executor", dupliziert Regeln und verletzt G7 (Frameworkfreiheit der Engine). Die Engine bleibt `[ENGINE-FROZEN]`.
6. **Eine dünne Adressierungs-Abstraktion vorsehen** (nur falls V1 es verlangt): `{schema}.{dataset}` so kapseln, dass eine SQL-on-Files-/HDLF-Virtual-Table identisch zu einer nativen HANA-Tabelle aufgelöst wird. Erwarteter Aufwand gering (s. §8).

**Bewusst NICHT entschieden** (folgt späterer Verifikation): die genaue ORD-Port-Sub-Schema-Frage für HDLF (R1), die konkrete Datasphere-ORD-Emission (R2), der programmatische Catalog-/Metadaten-Zugriff inkl. HDLF-Permission-Gap (R7) — diese bleiben im Zusatz-Doc verortet und werden durch diese ADR nur **geschärft**, nicht abgeschlossen.

---

## 8 — Lücken & benötigte Anpassungen (technisch, nicht konzeptionell)

| # | Gap | Schwere | Maßnahme | Aufwand (PT) |
|---|---|---|---|---|
| G-1 | Adressierung `{schema}.{dataset}` auf SQL-on-Files-/HDLF-Objekt | — | **Durch V1 erledigt:** die Monitoring-Space-**View** ist nativ `"{schema}"."{view}"` erreichbar | **0** |
| G-2 | Frische/Load-Recency, wo keine Business-Zeitstempelspalte existiert | mittel | **Load-Lag**-Check (Katalog-Modify-Time, `M_*`-Sicht, eigener Check in der Observability-Familie — **nicht** `freshness`); gated auf **V3a**. Nur für persistierte/replizierte Tabellen. | 1–1,5 |
| **G-8** | **`schema`/`type_conformance` fragen nur `SYS.TABLE_COLUMNS`** → gegen eine **View** `COUNT=0` → **falscher critical-Breach** | **hoch** | View-aware machen (`TABLE_COLUMNS` ∪ `VIEW_COLUMNS`), analog `query_helpers.get_columns`; Library-`version`-Bump + Recompile. **Now-Fix, durch V7 verifiziert.** | 1–1,5 |
| G-3 | `COUNT(*)`-Kosten bei großen Parquet-Beständen | gering | Partition-/Prädikat-Param im Check; Doku „teure Checks" | 0,5 |
| G-4 | Delta-Share-only-Produkte (keine SQL-Sicht) | mittel | Doku-Regel „transitiv prüfen oder out-of-scope"; **kein** Code | 0,25 |
| G-5 | ORD-Port-Topologie für HDLF (R1/R2) verifizieren | hoch (Wissen) | Spec-/Produkt-Verifikation, nicht Code | — |
| G-6 | Catalog-/HDLF-Metadaten programmatisch lesen (R7) | mittel (Wissen) | an bekannte Risiken gekoppelt (DWC_GLOBAL, HDLF-CLI-Permission-Gap) | — |
| G-7 | **Discovery**: Signals Inventar (`data/inventory.json`-Snapshot, Schema-Drift-Check O3) erfasst heute HANA-Kataloge — HDLF-Produkte/Virtual-Tables müssen erst hineinfinden | mittel | Inventar-Extrakt um die SQL-on-Files-/Studio-Objekte erweitern (welche Virtual-Tables sind „Produkte"?); koppelt an V5 | 1–2 |

Kernbotschaft der Tabelle: **Der teuerste Posten ist Wissen (G-5/G-6), nicht Code.** Auf der Code-Seite ist der wahrscheinliche Gesamteingriff klein und additiv — die Engine bleibt unangetastet. G-7 (Discovery) ist die stillste Lücke: Erreichbar zu *sein* genügt nicht, Signal muss das Produkt im Inventar auch *finden*.

---

## 9 — Konsequenzen

**Positiv**

- Signals Governance-Konzept ist **zukunftssicher** gegenüber dem BDC-Speichermodell-Wechsel: die wertvolle Ebene (boundary, Tiering, Komposition) überträgt sich ohne Bruch.
- Klare, ehrliche Reichweiten-Aussage gegenüber Kunde/SAP: „Signal überwacht an SQL-Output-Ports" — kein Versprechen, das der Executor nicht halten kann.
- Der SQL-Output-Port als Naht macht Fall (b) und (c) zu **einem** Integrationspfad statt zweier.
- Keine Architektur-Erosion: „single executor", G2, G7 und `[ENGINE-FROZEN]` bleiben intakt.

**Negativ / Risiken**

- Reine Delta-Share-/Object-Store-Produkte ohne SQL-Sicht sind **nicht** überwachbar — falls SAPs erster Weg (HDLF) in der Praxis *häufig* ohne SQL-on-Files auskommt, schrumpft Signals adressierbare Fläche. **Gegenmittel:** Kunden-Framing „SQL-Output-Port = überwachbar"; Tier-2-Produkte sollten ohnehin einen SQL-Port bekommen.
- V1 (Adressierung) ist noch nicht produktgenau verifiziert; falls SQL-on-Files **keinen** stabilen zweiteiligen Namen liefert, steigt G-1 von „trivial" auf „mittel".
- Frische-/Volumen-Semantik auf Files braucht eine durchdachte Param-Erweiterung, sonst entstehen falsch-grüne oder teure Checks.

**Neutral**

- Lite/Full bleibt orthogonal (ADR-0006): Speicherort und Zeremonie-Tiefe sind unabhängig. Ein HDLF-Produkt kann Tier-2/Full sein, ein HANA-Produkt Tier-0/internal.
- ORD/ODCS-Seam (Zusatz-Doc) bleibt die offene Baustelle; diese ADR verschiebt sie nicht, schärft aber die HDLF-spezifischen Fragen.

---

## 10 — Offene Verifikationspunkte (Schärfung von R1/R2/R7)

> Priorität: **[H]** blockiert die Enforcement-Festlegung · **[M]** mittel · **[L]** später.

- **V1 [H] — SQL-on-Files-Adressierung. ✅ GELÖST** für die Topologie „HDLF → Monitoring-Space-Share → View darüber": die View ist nativ `"{schema}"."{view}"` erreichbar → G-1 = 0 PT.
- **V7 [H] — Katalog-Sichtbarkeit der Spalten-Metadaten. ✅ GELÖST:** das Enforcement-Ziel ist eine **View**, deren Spalten in `SYS.VIEW_COLUMNS` (nicht `SYS.TABLE_COLUMNS`) liegen → die Checks `schema`/`type_conformance` sind heute view-blind (falscher Breach) → **G-8**.
- **V3a [M] — Load-Lag-Quelle.** Welche `M_*`-Sicht/Spalte liefert eine belastbare Load-/Merge-Zeit für replizierte Monitoring-Tabellen (`M_TABLE_STATISTICS.LAST_MODIFY_TIME` vs. `M_CS_TABLES.LAST_MERGE_TIME`)? — Gate für G-2. **OFFEN.**
- **V2 [H] — Output-Port-Typen je Studio-Produkt.** Welche Port-Typen bietet Data Product Studio konkret an (Delta Share, SQL-on-Files, HANA-View, ODBC), und sind sie pro Produkt **wählbar/kombinierbar**? Klärt, wie oft Fall 2 real verfügbar ist — verschärft R2.
- **V3 [M] — Freshness-Quelle bei Files.** Existiert eine konventionelle Lade-/Partitionsspalte, oder muss Frische aus Partitions-/Datei-Metadaten kommen? (entscheidet G-2)
- **V4 [M] — Delta-Share-only-Häufigkeit.** Wie verbreitet sind in SAPs erstem HDLF-Weg Produkte **ohne** SQL-Sicht? Bestimmt das Risiko aus §9.
- **V5 [M] — Metadaten-/Catalog-Zugriff für HDLF.** Programmatischer Lesepfad auf HDLF-Produkt-/ORD-Metadaten inkl. des bekannten HDLF-CLI-Permission-Gaps — verschärft R7.
- **V6 [L] — Multi-Port-Transport-Äquivalenz.** Wenn ein Produkt Delta Share **und** SQL-on-Files auf denselben Inhalt bietet: Garantiert SAP Inhaltsgleichheit, sodass die SQL-seitige Prüfung den Share mit-abdeckt (transitives Enforcement, §4)?

---

## 11 — Faustregeln (als Merksätze)

1. **Konzept transferiert, Executor nicht.** `boundary` × Lite/Full gilt überall; GX-on-HANA erreicht nur SQL-Oberflächen.
2. **Signal erzwingt am SQL-Output-Port.** Der Port ist die Outbound-Grenze und die Enforcement-Naht in einem.
3. **HANA-Space-Produkt = HDLF-via-SQL-on-Files** — für den Executor dasselbe: eine relationale Oberfläche `schema.object`.
4. **Delta Share ist kein SQL-Endpoint.** Direkt nicht prüfbar; transitiv an der SQL-Repräsentation desselben Inhalts enforcen — oder ehrlich out-of-scope.
5. **Kein zweiter Executor.** Object-Store-/Spark-Enforcement wird abgelehnt; single executor, G7, `[ENGINE-FROZEN]` bleiben.
6. **Der teure Posten ist Wissen, nicht Code.** Die Code-Anpassung ist klein und additiv; die Verifikationspunkte V1–V6 sind der eigentliche kritische Pfad.
7. **„SQL-Output-Port = überwachbar."** Das ehrliche Kunden-Framing: Wo Governance zählt (Tier 2), gib dem Produkt einen SQL-Port.

---

## 12 — Neubewertung im Licht von ADR-0004 (Datenprodukt als Komposition)

> Nachtrag. §0–§11 behandeln ein Datenprodukt als *eine* SQL-Oberfläche (den Output-Port). ADR-0004 sagt: ein Datenprodukt ist ein **Fluss aus mehreren Objekten** — Input → Transformation(en) → Output. Diese Sektion sagt konkret, wie ADR-0004 für die Custom Data Products aus dem Data Product Studio umgesetzt wird, und was das für ADR-0003 ändert.

### 12.1 — Ein Custom Data Product ist ein Fluss, kein einzelnes Objekt

Ein im Data Product Studio gebautes Produkt hat mehrere Objekte im Fluss:

```
 Input                Transformation(en)            Output
 (inbound)            (Interieur)                   (output port)
 SAP-Standard-     →  join / clean / aggregate   →  SALES.ORDERS_CURATED
 produkt oder         Zwischen-Files / -Views        (SQL-on-Files oder
 HDLF-Roh-File                                       HANA-View)
```

ADR-0004 bildet genau diesen Fluss ab — aber **ohne alle Objekte aufzuzählen**.

### 12.2 — So wird ADR-0004 umgesetzt: nur Anfang und Ende deklarieren

Man schreibt **ein dünnes Manifest** (`products/<name>.yaml`) und listet darin **nur die Ränder des Flusses** — den Output und (falls eine fremde Partei die Quelle besitzt) den Input:

```yaml
product: sales_orders_curated
owners: [team-fin]
output_ports:                 # das Ende des Flusses: der SQL-Port
  - dataset: ORDERS_CURATED
inbound:                      # der Anfang: nur wenn ein fremdes Team die Quelle besitzt
  - depends_on: { product: kunde, version: "1.2.0" }
# die Transformationen dazwischen werden NICHT gelistet
```

Die **Transformationen dazwischen** schreibt niemand auf. Signal **leitet sie aus der Lineage ab**: vom Output-Port rückwärts laufen, bis ein Ast bei einem fremden Produkt-Port oder einer externen Quelle endet. Alles dazwischen = Interieur.

Daraus fällt automatisch:

- **`boundary`** je Objekt — Output = `outbound`, Input vom fremden Team = `inbound`, Rest = `internal`. Abgeleitet, nicht handgesetzt.
- **Befunde** (ADR-0004 §6) — z. B.: ein Transform-Zwischenobjekt wird heimlich von einem anderen Team konsumiert → undeklarierter Output-Port.

### 12.3 — Was Signal davon prüfen kann: nur die SQL-Stellen im Fluss

Hier greift ADR-0003. Merksatz: **abgeleitet wird der ganze Fluss, geprüft nur, wo SQL erreichbar ist.**

| Stelle im Fluss | abgeleitet (sichtbar)? | geprüft (Checks laufen)? |
|---|---|---|
| Output-Port mit SQL (SQL-on-Files oder HANA-View) | ja | **ja** — 20 Checks unverändert |
| Transform-Zwischenobjekt als HANA-View | ja | ja |
| Transform-Zwischenobjekt als reines HDLF-File | ja | **nein** — sichtbar, aber kein SQL |
| Output nur als Delta Share (keine SQL-Sicht) | ja (stärkstes Discovery-Signal) | **nein** — out-of-scope für den Executor |

Ein File-Zwischenschritt oder ein Delta-Share-Output ist also **nicht „unsichtbar"** — er ist deklariert/entdeckt und wird mit „monitored = no" geführt, aber Signal fährt keinen Check darauf. Kein zweiter (Spark-)Executor (§7.5).

### 12.4 — Konkret für die zwei Fälle dieser ADR

- **Fall 1 (HDLF-Space):** Input und Transform-Schritte sind oft Files. Das Manifest deklariert den Output-Port; Signal prüft ihn, sobald er eine SQL-on-Files-Sicht hat; die File-Zwischenschritte sind sichtbar, aber nicht prüfbar. Greifen zwei Produkte auf dasselbe Roh-File zu, meldet ADR-0004 es als Foundation-Product-Kandidat (§6, Contested-Interieur).
- **Fall 2 (SQL-Output-Port):** Happy Path. Der `output_ports`-Eintrag ist genau die SQL-Stelle, an der Signal prüft. Konsumiert das Produkt ein SAP-Standard-Produkt als Input, trägt das Manifest ein `inbound: depends_on` — und die Ampel trennt **eigenes Versprechen** (eigene Checks am Port) vom **Upstream-Risiko** (gepinntes SAP-Produkt bricht → nicht automatisch rot, ADR-0004 §7).

### 12.5 — Voraussetzung: wie die Objekte überhaupt in den Graph kommen (CLI-Permission-Gap)

Damit der Rückwärts-Lauf etwas zu laufen hat, müssen die HDLF-/Studio-Objekte **im Lineage-Graph stehen**. Es gibt zwei Extraktionspfade (`services/api/extraction.py`); `build_lineage_graph(objects)` baut die Lineage aus den **extrahierten** Objekten, nicht aus einem direkten HANA-SYS-Read:

| Pfad | liefert | CLI nötig? |
|---|---|---|
| **Datasphere Catalog REST API** (`datasphere_catalog.py`, OAuth2-Tech-User) | Objekt-**Listing + Metadaten** (`technicalName`, `objectType`, `status`) | **nein** — headless, **Default-Pfad** |
| **Datasphere CLI** | zusätzlich volles **CSN** (Voraussetzung für **Spalten**-Lineage) | ja — nur als *Aufwertung* bevorzugt |

Der REST-Pfad nimmt der CLI also die **Knoten-Beschaffung** ab — aber er **holt nicht „alles".** Vier code-belegte Grenzen, die genau im HDLF-Fall beißen:

| Grenze | Beleg | Folge |
|---|---|---|
| **Ein Space pro Lauf** | `run_extraction` liest `datasphere_space_id` (Singular); `_gather_via_catalog` ruft `list_objects(space)` für genau diesen Space — iteriert **nicht** über `list_spaces()` | Cross-Space-Produkte (HDLF-Interieur + HANA-Port) brauchen mehrere Läufe; nicht automatisch das ganze Estate |
| **Typ-Filter auf 5 Enums** | `OBJECT_TYPES = views, local-tables, remote-tables, analytic-models, transformation-flows`; `_normalize_object_type` mappt Unbekanntes **best-effort auf `views`** | **keine** Kategorie für „HDLF-File" oder „SQL-on-Files-Virtual-Table" — solche Objekte fehlen oder werden fehlverbucht; explizit out-of-scope: replication-flows, task-chains, data-access-controls |
| **Sichtbarkeit = Tech-User-Rechte** | `list_spaces`/`list_objects` liefern nur, was der OAuth-Tech-User sehen darf | Permission-Gap ist nicht weg, sondern **verlagert** (CLI → REST-Tech-User); ob er die HDLF-Spaces grantet, ist offen |
| **Definition oft leer** | `read_object_definition` → häufig `None`/`{}` | kein CSN → keine **Spalten**-Lineage (der Owner-Walk arbeitet objekt-granular und kommt damit aus) |

> **Ehrlicher Stand:** Der REST-Katalog beschafft *Listing + Metadaten der Repository-Objekte **eines** konfigurierten Space, gefiltert auf 5 bekannte Typen, im Rahmen der Tech-User-Rechte* — das ist deutlich weniger als „alles". Für HDLF bleibt der **eigentliche Verifikationspunkt (V5):** Erscheint ein HDLF-Roh-File / eine SQL-on-Files-Virtual-Table überhaupt als Catalog-Repository-Objekt — und falls ja, braucht der Typ-Filter eine neue Kategorie? Der CLI-Permission-Gap blockiert die Knoten zwar nicht prinzipiell (REST umgeht ihn), aber „REST holt die HDLF-Objekte" ist **nicht verifiziert**, nicht gelöst.

Zusätzlich braucht der Walk eine **Owner-Attribution** als Stopp-Bedingung (V8) — die Owner-Hülle schneidet in BDC quer durch HDLF- und HANA-Spaces (ADR-0004 §2, „Hülle ≠ Space"). Code-seitig ist die Umsetzung klein und additiv (Read-Side, Engine `[ENGINE-FROZEN]`); der teuerste Posten bleibt die **HDLF-Discovery-Verifikation**, nicht Code.

### 12.6 — Faustregeln (Ergänzung zu §11)

8. **Derive überall, enforce nur an SQL.** Der ganze Fluss wird abgeleitet; geprüft wird nur, wo ein Objekt SQL spricht — am Output-Port und an jedem Zwischenschritt.
9. **Out-of-scope für den Executor ≠ out-of-scope für Governance.** Ein Delta-Share-Output ist nicht prüfbar, aber das stärkste Discovery-Signal — deklariert, entdeckt, „monitored = no", nicht weiß.
10. **Das Manifest deklariert nur Anfang und Ende.** Output-Port(s) und (bei fremder Quelle) Input; die Transformationen leitet die Lineage ab.
11. **Der REST-Katalog umgeht die CLI, holt aber nicht „alles".** Headless-Listing nur pro *einem* Space, auf 5 Objekt-Typen gefiltert, im Rahmen der Tech-User-Rechte; keine Kategorie für HDLF-Files/Virtual-Tables; CSN oft fehlend. Ob HDLF-Objekte überhaupt als Catalog-Objekt erscheinen, ist **unverifiziert (V5)** — der teuerste Posten bleibt Wissen, nicht Code.
