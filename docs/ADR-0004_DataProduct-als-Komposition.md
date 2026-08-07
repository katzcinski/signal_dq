# ADR-0004 — Datenprodukt als Komposition über Lineage (Manifest + abgeleitetes Interieur)

**Adressat:** Beratung, Plattform-Team, Governance, Entwicklung · **Stand:** 2026-06-22
**Status:** *Beschlossen* (accepted) — gegen den Code gegrillt (2026-06-22); Umsetzung in [`PLAN_ADR-0003-0004_Implementation.md`](PLAN_ADR-0003-0004_Implementation.md).
> **Umsetzungs-Schärfungen aus dem Grilling:** (1) `boundary` bleibt **entkoppelt** vom `kind`→`boundary`-Rename — abgeleitet/read-side, **nie persistiert**; `kind` und Manifest-Intent werden gegeneinander reconciliert. (2) Manifest-Laden **lenient/struktur-only**; referenzielle Lücken sind Findings, keine Ladefehler. (3) Walk: **Deklarierte-Port-Eigenschaft stoppt, Owner-Set klassifiziert**; **Multi-Claim** des Interieurs. (4) v1-Findings: **Dangling-Port, Contested-Interieur, cross-owner Boundary-Leak**; estate-leaving Leak/Over-Declaration/Orphan + Discovery + ORD-Export → **Phase 2**.
**Zweck:** Festhalten, wie Signal das **Datenprodukt als Aggregat über mehrere Layer** modelliert — ein Produkt ist die Kombination aus Objekten des Raw-, Integrated-Core- und Business-Core-Layers mit den Serving-/Business-Layer-Objekten als Output. Bisher kennt das Modell dieses „Ganze" nicht; Contracts sind dataset-zentriert.

> Verwandte Dokumente: `ADR-0001_Quality-Gates_vs_Contracts.md` (`boundary`-Diskriminator, Komposition §10, DSP-Tiering §11 — die direkte Grundlage) · `ADR-0006_Editor-Modus_aus_Kind.md` (Lite/Full ⊥ kind) · `ADR-0003_BDC-Datasphere-DataProductStudio.md` (**§12 wendet dieses Kompositions-Modell auf das BDC/HDLF-Setup an** — Owner-Walk über File-Knoten, `output_ports` = SQL-Enforcement-Naht, „derive überall, enforce nur an SQL") · `Vortrag_Briefing_DataProducts_DataContracts_DSP_BDC.md` (Konzept-Gerüst, §2 Data Product vs. Contract) · `Zusatz_ContractLifecycle_ORDBDCIntegration.md` (ORD/ODCS-Seam) · `Konzept_DQ_Observability_Cockpit.md` (fachliches Konzept).

---

## 0 — Kernaussage

Ein **Datenprodukt** ist nach eurer eigenen Doktrin (ADR-0001 §10, Briefing §2) *das Ganze über alle Layer in einer Ownership*; ein **Contract** beschreibt nur die *Ränder*. Im Code existiert dieses „Ganze" bisher nicht: `Contract(product, dataset)` ist faktisch **1 Contract = 1 Dataset = 1 „Produkt"**, und die Layer-Information lebt isoliert im Lineage-Graphen.

Diese ADR führt das **Datenprodukt als Read-Side-Aggregat** ein:

> **Ein dünnes Manifest deklariert nur Identität, Owner-Hülle und Ports (die Ränder). Das Interieur — alle Raw-/Core-/Business-Core-Objekte — wird aus der Lineage abgeleitet, begrenzt durch die Owner-Hülle. `boundary` wird nicht länger handgesetzt und quergeprüft, sondern aus dem Abgleich von Intent (Manifest) und Reality (Lineage) abgeleitet.**

Engine, Compiler und Store bleiben **unangetastet** (additiv, Read-Side, keine Migration) — konsistent mit ADR-0001 §4.

---

## 1 — Kontext: Was Signal heute tut (und was fehlt)

| Baustein | Heute | Lücke |
|---|---|---|
| Contract-Modell | `Contract(product, dataset, …)`; `product` fällt auf `dataset` zurück (`model.py:31`) | keine Klammer „diese Objekte sind zusammen Produkt X" |
| Layer/Role | pro Objekt gestampt in `inventory.py:496` (`layer`, `layerCode`, `role`) | nur im Lineage-Graphen; Contract-Welt weiß davon nichts |
| `boundary` | `internal`/`inbound`/`outbound` pro Set (ADR-0001, Batch 1–5) | pro Set, nicht im Rahmen eines komponierten Produkts; handgesetzt |
| Produkt-Schlüssel | `Contract.product` (degeneriert) | echte 1:N-Gruppierung fehlt |
| Compliance-Split | Batch 4 (Gate vs. Contract) | kein Ort, um *pro Produkt* zu aggregieren |
| Cross-Produkt-Kette | `depends_on`-Idee (ADR-0001 §10.6) | kein Träger-Artefakt |

Die zwei Welten — **Lineage-Graph** (kennt Layer) und **Contracts** (kennen Versprechen) — sind heute nur lose über `dataset == technicalName` verbunden. Es fehlt das Aggregat, das beide zusammenführt.

---

## 2 — Entscheidung

**Hybrid: dünnes Manifest + aus Lineage abgeleitetes Interieur.** Verworfen wurden:

- **A — rein abgeleitet (kein Artefakt):** Produkt = Lineage-Subgraph ab Output-Port. Null Migration, ehrt „Layer ≠ Grenze" maximal — aber braucht eine verlässlich kodierte Ownership-Grenze und ist unscharf, wo Ownership nicht kodiert ist.
- **B — explizites Manifest (alle Mitglieder gelistet):** maximal auditierbar, aber zweite Quelle der Wahrheit neben der realen Lineage → garantierter Drift.

**Gewählt: C.** Das Manifest deklariert nur das, was die Theorie als *real* bezeichnet (Identität, Owner-Hülle, Ränder); das technische Dazwischen ist nur Lineage und wird **nicht** von Hand erklärt. Das recycelt die Engine, die Layer ohnehin stampt, und folgt der Doktrin „nur die Ränder deklarieren".

**Hülle = expliziter Owner-Set** (nicht Space). Begründung: Teams schneiden oft *nicht* entlang der DSP-Spaces; der wertvollste Befund (Boundary-Leak, §6) braucht die *Verantwortungs*grenze, nicht die technische.

---

## 3 — Manifest-Schema (Sketch)

Ein neues Artefakt `products/<name>.yaml`. Es trägt **nur** Identität, Hülle und Ränder — nichts Zustandsbehaftetes, kein Interieur:

```yaml
product: sales_overview
owners: [team-sales]              # die Hülle (Owner-Set) — wirkt als Stopp-Bedingung
output_ports:                     # 1:N → je Port ein Outbound-Contract (1:1:1:1 pro Port)
  - dataset: DS_REVENUE_SUMMARY   #   verweist auf bestehende Contract-YAML
inbound:                          # nur deklarieren, wo eine echte Gegenpartei existiert
  - depends_on: { product: kunde, version: "1.2.0" }   # Fall B (gekettete Contracts)
# interieur: NICHT gelistet — wird aus Lineage abgeleitet (§4)
```

- **Produkt wird nicht versioniert.** Identität ist stabil (Eigentums-Hülle); SemVer lebt am Outbound-Contract *pro Port* (Briefing: „SemVer lebt beim Produzenten"). Darum `output_ports` als **Liste** (1:N), nicht *eine* Produkt-Version.
- **`inbound` nur bei echter Gegenpartei.** Eigener CSV-Dump/selbst geownt → kein Contract (Briefing §1.4).

---

## 4 — Ableitungsregel: der Owner-gegatete Upstream-Walk

**Owner-Set wirkt *negativ*.** Die Interieur-Objekte (Core, Raw) tragen heute keinen Owner (`owners` hängt nur am `Contract`, `model.py:21`); ein internes Core-Objekt hat oft gar keinen Contract. Mitgliedschaft lässt sich also **nicht** positiv über Owner-Tags einsammeln. Owner-Set ist deshalb keine Mitgliedschafts-Eigenschaft, sondern eine **Stopp-Bedingung**: Mitgliedschaft kommt aus der Lineage; der Owner entscheidet nur, *wo der Walk aufhört* — an der Port eines *anderen* Owners.

```
1. Alle Manifeste einlesen → Map: Output-Port-Objekt → (Produkt, Owner-Set)
2. Pro Produkt: Upstream-Walk durch den Lineage-Graphen ab Output-Port.
   Ein Ast stoppt bei:
   (a) Output-Port eines ANDEREN Produkts  → Inbound-Dependency (Fall B, depends_on + gepinnte Version)
   (b) externer Source-Node (S4:*, ext)    → Inbound-Source (Kandidat für Inbound-Contract)
   (c) bereits besucht
3. Alles dazwischen = Interieur → interne Gates (Miner-vorschlagbar)
```

Das ist exakt Fall A / Fall B (ADR-0001 §10.3/§10.4), jetzt **berechenbar**: Bleibt `kunde` im selben Owner-Set, läuft der Walk hindurch → internes Gate (Fall A). Ist `kunde` der Output-Port eines fremden Owner-Sets, stoppt der Walk dort → Inbound-Dependency (Fall B). **Derselbe Lineage-Graph, der Owner-Set entscheidet die Klassifikation** — „Layer ≠ Grenze" bleibt strukturell gewahrt: der Layer-Stamp aus `inventory.py:496` ist nur *Beschreibung* der Knoten, nie Stopp-Kriterium.

**Tiefe Ketten:** Der Walk stoppt am **ersten** fremden Port. Die transitive Abhängigkeit bleibt implizit (ADR-0001 §3.2: „Contracts mergen nicht") und wird separat als transitive Sicht gerendert, nicht ins Produkt eingerechnet.

---

## 5 — Intent vs. Reality: `boundary` wird abgeleitet, nicht quergeprüft

Manifest und `boundary` dürfen **nicht** „übereinstimmen müssen" — zwei handgepflegte Quellen für denselben Fakt wären genau die Drift, die wir abschaffen wollen. Stattdessen beantworten drei Ebenen *unterschiedliche* Fragen und **vergleichen** sich:

| Ebene | Quelle | Frage |
|---|---|---|
| **Intent** | Manifest (`output_ports`, `inbound`) | „Was *will* ich exponieren?" |
| **Reality** | Lineage + Owner-Set (der Walk, §4) | „Was wird *tatsächlich* über eine Grenze konsumiert?" |
| **`boundary`** | **abgeleitet** aus Intent ⋈ Reality, auf das Set materialisiert | Klassifikation fürs Lifecycle-Gating (Batch 5) |

`boundary` ist damit das **Resultat** des Abgleichs — auf das Set materialisiert, damit das bestehende Gating (SemVer/Approval/Breaking, Batch 5) unverändert weiterläuft. Es ist kein dritter Handeingabe-Kandidat mehr. Engine/Store bleiben unangetastet.

**Misch-Fall ist kein Konflikt:** Ein Port-Objekt, das zugleich interne Garantien trägt (z. B. exponierte Fact View mit internem Ref-Integritäts-Gate), ist der dokumentierte Sonderfall `boundary` *je Garantie* (ADR-0001 OP-2) — nicht ein Widerspruch.

---

## 6 — Reconciliation-Befunde (der eigentliche Gewinn)

Sobald das Aggregat existiert, fallen die Befunde als **Deltas zwischen Intent und Reality** automatisch ab. Zwei davon automatisieren den §10.2-Test des Briefings („datengetrieben, nicht label-getrieben"):

| Befund | Bedeutung | Konsequenz |
|---|---|---|
| **Boundary-Leak** | Reality hat grenzüberschreitenden Konsumenten, Intent hat **keinen** Port | **= undeklarierter Outbound-Contract** (§10.2 automatisiert) → Port/Contract anlegen |
| **Over-Declaration** | Intent sagt Port, Reality hat **keinen** grenzüberschreitenden Konsumenten | Versprechen ohne Konsument → Tier-0-Verdacht (Over-Governance, §11.4) |
| **Contested-Interieur** | Zwei Produkte beanspruchen dasselbe Interieur-Objekt | **= Foundation-Product-Kandidat** (§10.2) → zum eigenen Port erheben |
| **Orphan-Interieur** | Objekt speist einen Output-Port, aber kein Produkt beansprucht es | Hülle zu eng → Manifest erweitern |
| **Dangling-Port** | Manifest deklariert Output-Port ohne existierendes Objekt / ohne Outbound-Contract | Drift Manifest ↔ Realität |

**Contested-Interieur erzwingt eine *explizite* Auflösung.** Das Tool verweigert die stille Vermischung konkurrierender Owner: entweder eigener Port (= Foundation Product, wird Fall-B-Dependency für beide) oder ein Produkt deklariert es als geteiltes Interieur mit benanntem Owner. Das ist die auditierbare Promotion aus §10.2.

---

## 7 — Zweistufige Gesundheit (eigenes vs. transitives Versprechen)

Weil der Walk am ersten fremden Port stoppt und Contracts nicht mergen (§10.4), braucht ein Produkt **zwei** getrennte Status-Spuren:

| Spur | Quelle | Semantik |
|---|---|---|
| **Eigenes Versprechen** | Outbound-Contracts der eigenen Ports | DAS ist die Produkt-Ampel (governance-relevant) |
| **Upstream-Risiko** | Compliance der `depends_on`-Produkte (gepinnte Version) | „eine Zusage stromaufwärts ist gebrochen" — *Risiko*, nicht eigener Breach |

Bricht `kunde`, wird `sales_overview` **nicht automatisch rot** — es bekommt ein Upstream-Risiko-Signal. Ob daraus ein eigener Breach wird, zeigt erst der eigene Outbound-Check. Das hält die Ampel ehrlich (Batch-4-Doktrin) und macht die transitive Kette dort sichtbar, wo sie hingehört — als separate Spur, nicht vermischt.

---

## 8 — Lifecycle wird abgeleitet, nicht gepflegt

Konsequenz aus „Produkt nicht versionieren": auch der Lifecycle bekommt **kein** handgepflegtes Feld, sondern ergibt sich aus den Ports:

- mind. ein Port `active` → Produkt `active`
- alle Ports `deprecated` → Produkt `deprecated`
- nur `draft`-Ports → Produkt `draft`

Das vermeidet eine dritte Stelle, die mit `Contract.lifecycle` (`model.py:23`) driften könnte. Das Manifest trägt nur **Identität + Hülle + Ports**, sonst nichts Zustandsbehaftetes.

---

## 9 — Discovery & Bootstrapping: aus Konsum-Evidenz, nicht Topologie

Damit das nicht nur Greenfield bedient, braucht es einen Discovery-Pfad — analog zu ADR-0001s „ehrlichem Default".

**Verworfen: „Sink = Port-Kandidat".** Ein Objekt ohne Downstream in der *erfassten* Lineage ist kein Output-Port, sondern eins von zwei Dingen: **Konsum außerhalb des Graphen** (Delta Share, exponierte View, BI-Layer, nicht erfasster Space) — sieht terminal aus, ist es nicht — **oder tatsächlich tot** (verwaist/deprecated/Scratch). „Sink" wirft genau diese beiden zusammen und reproduziert die Over-Governance-Flut (§11.3: von hunderten Objekten sind real nur 10–20 Produkte). Außerdem ist ein Port durch *grenzüberschreitenden Konsum* definiert (§5), nicht durch Terminalität.

**Richtig: Vorschläge aus Konsum-Evidenz, nach Stärke gerankt:**

| Stärke | Signal | → |
|---|---|---|
| **stark** | Konsum verlässt das eigene Estate (Delta Share / exponierte Share-View) **oder** Kante zu bekanntem fremdem Produkt | Port-Kandidat |
| **mittel** | konsumiert von out-of-inventory / unbekanntem Downstream | Port-Kandidat (zu verifizieren) |
| **schwach** | im Katalog als Foundation Product publiziert, aber *kein* beobachteter Konsum | Tier-0-Verdacht (§11: Katalog ≠ Contract) |
| **kein Kandidat** | Sink ganz ohne Konsum | separater Befund: Orphan/Dead-End (Cleanup / Out-of-Graph-Warnung) — *kein* Port-Vorschlag |

Infrastruktur teilweise vorhanden: `build_lineage_graph` erzeugt bereits **externe Knoten** für out-of-inventory-Quellen (`inventory.py`, `sourceScope == "external_system"`). Dasselbe Konzept downstream — exponierte Shares/Views als externe *Konsumenten* — ist das stärkste Cold-Start-Signal.

**Cold-Start ist iterativ, nicht Big-Bang:** „fremder Owner" setzt Owner-Attribution voraus, die es vor dem ersten Manifest kaum gibt.

1. **Phase 0 (keine Manifeste):** einziges verlässliches „crosses-a-boundary"-Signal ist Konsum, der das Estate *verlässt* (externe Shares, exponierte Views, Katalog-Publikation). Wenige, hochsignalige Vorschläge.
2. **Phase 1 (erste Manifeste bestätigt):** Owner-Attribution propagiert → cross-owner-Kanten zwischen Produkten werden sichtbar → nächste Runde Kandidaten + Fall-B-Dependencies.
3. Jedes bestätigte Manifest schärft die Owner-Karte → konvergent.

**Authoring-Flow (output-first):**

1. **Discovery** schlägt aus Konsum-Evidenz Kandidat-Ports vor.
2. **Confirm:** Mensch bestätigt Output-Port(s) + Owner-Set → Manifest entsteht. Auditierbarer Promotion-Akt (§10.2), zweite Achse neben Gate→Contract (Batch 3).
3. **Ableiten:** Interieur, Inbound-Sources, Cross-Produkt-Dependencies fallen automatisch ab; der **Miner** (`obs/miner.py`) schlägt fürs Interieur interne Gates, für die Ports Contract-Klauseln vor.
4. **Reconciliation** läuft kontinuierlich → treibt weitere Promotion-Entscheidungen.

**Pointe: Discovery und Boundary-Leak sind *derselbe* Mechanismus** — „grenzüberschreitender Konsum" in verschiedenen Lebensphasen: **vor** dem Manifest → *Discovery-Vorschlag*; **nach** dem Manifest → *Boundary-Leak-Befund*. Eine Engine, kein Doppelbau.

---

## 10 — Katalog/ORD: das Produkt ist die Export-Einheit

`odcs_export.py` exportiert heute pro Contract. Produktweise gebündelt fällt die Katalog-Sicht praktisch von selbst ab: **Produkt = Katalog-/Marketplace-Präsenz (ORD-Descriptor), Port = governter Contract** (Briefing §1.5, §11). Das deckt sich mit der DSP-Realität „alles ist ein Foundation Product im Katalog" (§11.1): das Produkt-Label bleibt, die vertragliche Verbindlichkeit liegt pro Port und wird getiert (`boundary` × Lite/Full).

---

## 11 — Konsequenzen

**Positiv**

- Das „Ganze" wird zum erstklassigen, aber **abgeleiteten** Aggregat — ohne dritte Wahrheit, ohne Store-Migration.
- Fall A / Fall B werden **berechenbar** statt manuell klassifiziert.
- Boundary-Leak automatisiert den §10.2-Test: fehlende Contracts und Foundation-Kandidaten werden zur Query, nicht zum Workshop.
- `boundary` kippt von „handgesetzt + querprüfen" zu „abgeleitet + bestätigen" → weniger Pflege, kein Drift-Pflaster.
- Ehrliche, zweistufige Produkt-Ampel (eigenes Versprechen ⊥ Upstream-Risiko).
- Genau ein neues Artefakt (`products/*.yaml`), additiv und Read-Side.

**Negativ / Risiken**

- Discovery braucht ein verlässliches „Konsum verlässt das Estate"-Signal; ist die Lineage lückenhaft, sind Cold-Start-Vorschläge schwach (Gegenmittel: Katalog-/Share-Metadaten als zusätzliche Evidenz).
- Owner-Set muss gepflegt werden; ohne Owner-Attribution bleibt der Walk grob (mildert sich iterativ, §9).
- Contested-Interieur erzwingt Entscheidungen — gewollt, aber Onboarding-/Doku-Aufwand.
- `boundary` materialisieren statt deklarieren: bestehende handgesetzte Werte werden zum *Intent* umgedeutet (Migration, §12) — muss kommuniziert werden, sonst ändert sich Ampel-Semantik unbemerkt.

**Neutral**

- Lite/Full bleibt orthogonal (ADR-0006): das Produkt-Aggregat berührt die Prozess-Zeremonie nicht.
- Engine/Compiler/Store unverändert (`[ENGINE-FROZEN]`, Gate G7).

---

## 12 — Migration (nicht-brechend)

1. **Kein Manifest = kein Produkt.** Bestehende Contracts/Gates bleiben gültig und funktionieren unverändert weiter; das Produkt-Aggregat ist rein additiv.
2. **`boundary` bleibt vorerst authorbar** und wird als *Intent* gelesen; die abgeleitete Reality läuft dagegen. Discovery (§9) kann `boundary` später aus entdeckten Produkten **generieren** → schrittweiser Übergang von „handgesetzt" zu „abgeleitet + bestätigt".
3. **Keine Store-Migration.** Runs/Results bleiben dataset-zentriert; optional `product` im `contract_index` spiegeln, nur für Cockpit-Filter.
4. **Discovery-getriebenes Bootstrapping** statt Big-Bang (§9, Phasen 0→1).

---

## 13 — Offene Punkte / nächste Schritte

> Aktive Phase-2-Backlog-Punkte sind seit 2026-07-04 in [`OPEN_TASKS.md`](OPEN_TASKS.md) §P konsolidiert.

1. **Owner-Vererbung ins Interieur:** Interieur-Gates erben den Owner vom Manifest (Routing, Batch 4); bei Contested-Interieur erzwingt das Tool explizite Auflösung (§6). Mechanik der Vererbung im Detail festlegen.
2. **Reality-Signal-Quellen:** Welche Metadaten zählen verlässlich als „Konsum verlässt das Estate" (Delta-Share-Registry? exponierte Views? Katalog/ORD)? Priorisieren.
3. **Cockpit-Rendering:** Produkt als Hülle um den Lineage-Subgraphen, IN/OUT-Badges (vorhanden) an den Randknoten, GATE-Badges im Inneren, transitive Kette als separate Spur.
4. **Reihenfolge:** Modell + Manifest-Schema + Walk + Reconciliation zuerst (Read-Side); Discovery-Ranking und `boundary`-Generierung danach.

> **Faustregel (ADR-0004):** Das Produkt deklariert nur seine Ränder und seine Owner-Hülle; das Interieur leitet die Lineage ab. Ports sind durch grenzüberschreitenden Konsum definiert, nicht durch Layer oder Topologie. `boundary` ist das Ergebnis von Intent ⋈ Reality — keine zweite Handeingabe.
