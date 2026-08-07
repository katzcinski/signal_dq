# Implementierungsplan — ADR-0003 (BDC/Datasphere-Enforcement) & ADR-0004 (Datenprodukt als Komposition)

**Adressat:** Plattform-Team, Entwicklung, Governance · **Stand:** 2026-06-22
**Status:** *Beschlossen* — Ergebnis einer Grilling-Session gegen ADR-0003/0004 und den Code.
**Zweck:** Einen umsetzbaren Plan festhalten. Begriffe sind in [`/CONTEXT.md`](../CONTEXT.md)
geschärft; die Entscheidungen sind in §D protokolliert.

> Verwandte Dokumente: [`ADR-0003_BDC-Datasphere-DataProductStudio.md`](ADR-0003_BDC-Datasphere-DataProductStudio.md) ·
> [`ADR-0004_DataProduct-als-Komposition.md`](ADR-0004_DataProduct-als-Komposition.md) ·
> [`ADR-0001_Quality-Gates_vs_Contracts.md`](ADR-0001_Quality-Gates_vs_Contracts.md) (`kind`/`boundary`).
> Aktive Phase-2-/Verifikationspunkte sind seit 2026-07-04 in [`OPEN_TASKS.md`](OPEN_TASKS.md) §P konsolidiert.

---

## 0 — Rahmung: zwei asymmetrische Tracks

Die beiden ADRs sind **nicht symmetrisch**, deshalb ein Dokument mit zwei Tracks:

- **Track A — ADR-0004** ist ein **baubares Read-Side-Feature** (neues Aggregat über die
  Lineage). Hängt von nichts Externem ab → vollständiger, phasierter Bauplan.
- **Track B — ADR-0003** ist überwiegend **Verifikation**. Genau **ein** Code-Item ist durch
  die reale Topologie verifiziert und sofort baubar (**G-8**); der Rest bleibt hinter seinem
  Verifikationspunkt **gated**. ADR-0003-Discovery (G-7) wandert in Track A, Phase 2.

Leitprinzip für beide: **additiv, keine Store-Migration, Engine `[ENGINE-FROZEN]`** (Gate G7).

---

## Track A — ADR-0004: Datenprodukt-Aggregat (Read-Side)

### A.1 — Grundprinzipien

1. **Entkoppelt vom `kind`→`boundary`-Rename (ADR-0001 §9).** ADR-0004 benötigt das Rename
   **nicht**. `boundary` ist eine **abgeleitete, read-side** Klassifikation (`internal |
   inbound | outbound`), die **nie persistiert** wird. Das bestehende Gating (G3/Lifecycle)
   läuft unverändert über `kind`. Manifest-Intent (`output_ports`/`inbound`) und das
   bestehende `kind` sind **zwei Intent-Signale**, die die Reconciliation gegeneinander prüft.
2. **Reines Paket `packages/dq_core/product/`** (framework-frei, wie `compiler.py`,
   `inventory.py`, `loader.py`); dünner FastAPI-Router darüber.
3. **Genau ein neues Artefakt** `products/<name>.yaml`. Keine Engine-/Compiler-/Store-Änderung.

### A.2 — Phase 1 (v1): Aggregat + Findings + Health

#### A.2.1 Modell & Laden — `dq_core/product/model.py`
- `Product`-Dataclass: `product`, `owners: list[str]`, `output_ports: [{dataset}]`,
  `inbound: [{depends_on: {product, version}}]`. **Kein** Interieur, **keine** Version,
  **kein** Lifecycle-Feld (beide abgeleitet, ADR-0004 §3/§8).
- **Lenient/struktur-only Laden** (Entscheidung Q3-B): Der Parser prüft nur **strukturelle**
  Gültigkeit (sicherer `product`-Name via bestehendem `^[A-Za-z_]\w*$`; `owners` nicht leer;
  jeder Port hat `dataset`; jedes `inbound` hat `product`+`version`). **Referenzielle** Lücken
  (Port ohne Contract, Objekt fehlt in Lineage) sind **keine** Ladefehler, sondern *Findings*
  (§A.2.3). Das Parsen bleibt **total** (wirft nie auf wohlgeformten, aber referenziell
  unvollständigen Manifesten).
- Neue Setting `products_dir` (Default `products`) in [`settings.py`](../services/api/settings.py).

#### A.2.2 Owner-gegateter Upstream-Walk — `dq_core/product/walk.py`
Reine, **deterministische** Funktion über die `upstream`-Map aus
[`build_lineage_graph`](../packages/dq_core/lineage/inventory.py). Entscheidungen Q4 + Q5:

- **Stopp-Trigger = Deklarierte-Port-Eigenschaft** (nicht der Owner). Der Owner *klassifiziert*
  nur den Stopp.
- **Multi-Claim** (Q5): jedes Produkt hat einen **eigenen** `visited`-Set; ein Interieur-Objekt
  darf in mehreren Produkten auftauchen (→ Contested-Befund fällt als Query ab).

```text
port_index: object -> (product, owner_set)          # aus ALLEN Manifesten zuerst aufbauen
für jedes Produkt P (sortiert, deterministisch):
    visited = {}; queue = list(P.output_ports)       # Ports sind Rand, kein Interieur
    while queue:
        n = queue.pop(); if n in visited: continue; visited.add(n)
        für up in sorted(upstream.get(n, [])):
            if up in port_index and port_index[up].product != P:
                if port_index[up].owner_set != P.owner_set:
                    record FALL B  inbound-dependency(up)   # depends_on + gepinnte Version
                else:
                    record FALL A  internes hand-off(up)    # kein governter Contract
                # STOPP: nicht in up rekursieren
            elif is_external(up):                            # sourceScope==external_system / ext / S4:*
                record inbound-source(up); # STOPP
            else:
                P.interior.add(up); queue.append(up)         # Interieur → weiter
```
- **Transitive Tiefe = ein Hop** (Stopp am ersten fremden Port; tiefere Kette als separate
  Sicht, nicht eingerechnet — ADR-0004 §4).
- „Layer ≠ Grenze" bleibt strukturell gewahrt: der Layer-Stamp ist **nie** Stopp-Kriterium.

#### A.2.3 Reconciliation — `dq_core/product/reconcile.py`
**Drei** Findings in v1 (Entscheidung Q6); die übrigen drei → Phase 2.

| Finding | Definition (v1) |
|---|---|
| **Dangling-Port** | Manifest-`output_port`, dessen `dataset` **keine** Contract-Datei *oder* **keinen** Lineage-Knoten hat — *oder* dessen Contract `kind: internal_gate` ist (deklarierter Port ohne governten Contract). |
| **Contested-Interieur** | Interieur-Objekt, das von **≥2 Produkten** beansprucht wird (über Produkte hinweg). → Foundation-Product-Kandidat; erzwingt explizite Auflösung (§6). |
| **Boundary-Leak (cross-owner)** | Interieur-Objekt X von P (Owner A) mit Downstream-Kante (`adjacency`) zu einem Objekt eines **anderen** Owner-Sets B, wobei X **kein** deklarierter Port von P ist. → undeklarierter Outbound. Greift, sobald **≥2 Manifeste verschiedener Owner** existieren. |

> **Ehrlich loggen**, dass „estate-leaving"-Leaks in v1 **nicht** erkannt werden (kein
> Consumer-seitiges Signal) — kein Vortäuschen von Vollabdeckung.

#### A.2.4 Zweistufige Gesundheit — `dq_core/product/health.py` (Q7)
- **`own_health(P)` = worst-of** über die `output_ports` von P, die **governance contracts**
  sind (`kind ∈ {consumer_contract, provider_contract}`). Ein `internal_gate` auf einem
  deklarierten Port trägt **nichts** zur Ampel bei → stattdessen Dangling-Port-Finding.
- **`upstream_risk(P)`** je `inbound.depends_on {product=U, version=v}`, **strikt
  nicht-ansteckend** (eigenes Feld, berührt die eigene Ampel nie):
  - `upstream_breach` = `get_compliance(U).compliance == "breached"`,
  - `version_drift` = `get_compliance(U).contract_version != v`.
  Datenquelle: [`store.get_compliance`](../packages/dq_core/store/sqlite_store.py) (liefert
  `compliance` **und** `contract_version`).

#### A.2.5 API — `services/api/routers/products.py` (read-only)
- `GET /api/products` (Liste), `GET /api/products/{product}` (Detail).
- Detail-Shape: `ports[]` (dataset, kind, compliance, version), `interior[]` (id, layer, role,
  coverage_flag), `inbound_dependencies[]` (product, pinned_version, current_version,
  compliance, version_drift), `inbound_sources[]`, `boundary_view` (**abgeleitet**, je Objekt),
  `own_health`, `upstream_risk[]`, `findings[]`. Schemas in `schemas/product_schemas.py`.

#### A.2.6 Cockpit (Entscheidung Q9 — **A+**)
- Neue **Products-Seite** (Liste → Detail), getrieben vom Aggregat-API; wiederverwendet
  bestehende Primitives (`StatusPill`, `CovFlag`, `OwnershipTag`, Tabellen).
- **`LineageMiniGraph`** — neue **read-only** Komponente, aus [`LineageMap.tsx`](../apps/cockpit/src/pages/LineageMap.tsx)
  herausgelöst (cytoscape + dagre-LR, fit-to-view, Farbe nach Coverage/Role, Click-through).
  **Neue** Komponente; LineageMap bleibt unangetastet (Dedup später). **Ausgeschlossen** in v1:
  Positions-Persistenz, Lane-Filter, Focus-Path-UI, transitive Spur, Workbench-Embed.
- Findings je Produkt auf der Detailseite; globaler Rollup optional.

#### A.2.7 Tests
- Unit (pure): `walk` (Fall A/B, multi-claim, Diamant/Zyklus, Determinismus), `reconcile`
  (drei Findings inkl. cross-owner Leak ab 2 Manifesten), `health` (worst-of, drift, nicht-
  ansteckend). Fixtures = Manifeste + synthetischer Lineage-Graph.
- API-Smoke (list/detail), FE-Komponententests (Products-Seite, MiniGraph-Render).

### A.3 — Phase 2 (Discovery + Anreicherung, gated/deferred)
- **Consumer-seitiges „verlässt-das-Estate"-Signal** (Katalog/ORD/Delta-Share-Metadaten →
  externe *Konsumenten*-Knoten in `build_lineage_graph`). **Gemeinsam mit ADR-0003 G-7.**
- Verbleibende Findings: **estate-leaving Boundary-Leak**, **Over-Declaration**,
  **Orphan-Interieur**.
- Stärke-gerankte **Discovery-Kandidatenliste** (§9-Tabelle) + **`boundary`-Generierung**.
- **ORD/Export: Produkt = Export-Einheit** (§10) — heutiges per-Contract-`/export/*` bleibt.
- Reicheres Cockpit: volles LineageMap-Hüllen-Overlay, transitive Spur, globaler Findings-Rollup.
- **Owner-Vererbung ins Interieur** (§13.1).

### A.4 — Reihenfolge & grober Aufwand (Phase 1)
`model` (1–1,5) → `walk` (2–3) → `reconcile` (2) → `health` (1) → `/api/products` (1,5) →
Products-Seite (2) → `LineageMiniGraph` (1–2). **≈ 10–13 PT.** Read-Side-zuerst (ADR-0004 §13.4).

---

## Track B — ADR-0003: Enforcement an BDC/HDLF (Verifikation-first)

### B.1 — Verifikations-Checkliste (Stand nach Grilling)

| # | Frage | Status |
|---|---|---|
| **V1 [H]** | SQL-on-Files-Adressierung — stabiler zweiteiliger Name? | **GELÖST** für die Topologie „HDLF-Objekt → in dedizierten Monitoring-Space geteilt → **View darüber**": die View ist nativ per `"{schema}"."{view}"` erreichbar → Happy Path. **G-1 = 0 PT.** |
| **V7 [H]** | Katalog-Sichtbarkeit der Spalten-Metadaten | **GELÖST**: Ziel ist eine **View** → Spalten in `SYS.VIEW_COLUMNS`, **nicht** `SYS.TABLE_COLUMNS` → siehe G-8. |
| **V3 [M]** | Freshness-Quelle | `freshness` bleibt **business-recency** auf einer Zeitstempelspalte der View. Wo keine existiert → V3a. |
| **V3a [M]** | Welche `M_*`-Sicht/Spalte liefert eine belastbare *Load-Lag*-Zeit für replizierte Monitoring-Tabellen (`M_TABLE_STATISTICS.LAST_MODIFY_TIME` vs. `M_CS_TABLES.LAST_MERGE_TIME`)? | **OFFEN** (kurze Verifikation). Gate für G-2. |
| V2/V4/V5/V6 | Port-Typen, Delta-Share-Häufigkeit, HDLF-Metadaten, Multi-Port-Äquivalenz | **OFFEN** (Wissen, kein Code-Blocker für v1). |

### B.2 — G-8 (NOW-FIX): view-aware Katalog-Checks
**Befund:** Die Checks `schema` und `type_conformance` fragen **nur** `SYS.TABLE_COLUMNS`
([check_library.json:279,294](../packages/dq_core/library/check_library.json)). Gegen eine
**View** liefert das `COUNT = 0` → bei Closed-Mode (`= N`, **critical**) ein **falscher
Breach**. Der Profiler weiß es bereits besser:
[`query_helpers.get_columns`](../packages/dq_core/connect/query_helpers.py) probiert
`TABLE_COLUMNS` und fällt auf `VIEW_COLUMNS` zurück. In Tests bislang **maskiert** durch die
Mock-Verbindung (`allow_mock_connection=True`).

**Fix (rein, deterministisch, keine Engine-Änderung):**
- `schema`-Template → über **`TABLE_COLUMNS` ∪ `VIEW_COLUMNS`** zählen (Summe der beiden
  Subqueries; `VIEW_NAME` statt `TABLE_NAME` im View-Zweig), analog `get_columns`.
- `type_conformance` → Spaltenzeilen beider Kataloge per `UNION ALL` einsammeln, dann die
  bestehende `CASE`-Logik darauf.
- **`version` in `check_library.json` erhöhen** → `compiler_hash` ändert sich → bestehende
  Contracts müssen über `/compile` bzw. `/certify` **neu kompiliert** werden (erwartet,
  determinismus-konform).
- **Tests:** Mock so erweitern, dass er View-Katalog-Ergebnisse liefert; Regressionstest „View-
  Ziel besteht den `schema`-Check". (~1–1,5 PT)

### B.3 — Übrige Code-Items
- **G-1 (Adressierung):** **0 PT** — durch V1 erledigt.
- **G-2 (Load-Lag-Modus):** Neuer Check `load_lag` (Katalog-Modify-Time gegen eine `M_*`-Sicht,
  **explizites Ziel-Tabellen-Param**), **Observability-Familie neben `sap_replication_lag`** —
  **nicht** `freshness` (Q12: business- vs. technical-recency, siehe [`/CONTEXT.md`](../CONTEXT.md)).
  **Gated auf V3a.** Greift nur für **persistierte/replizierte** Tabellen; reine
  Files-via-Virtual brauchen weiterhin Partitions-Metadaten.
- **G-3 (`COUNT(*)`-Kosten):** optionaler Prädikat-Param — koppelt faktisch an V3/Partitions-
  wissen → **deferred** (nicht spekulativ bauen).

### B.4 — Dokumentation (jetzt)
- Regel **G-4**: „Delta-Share-only ohne SQL-Sicht → transitiv prüfen **oder** ehrlich
  out-of-scope" (kein Code).
- Doku „teure Checks" (Full-Scan auf großen Parquet-Beständen).

### B.5 — Wissen / verschoben
- **G-5/G-6** (ORD-Port-Topologie, HDLF-Metadaten/Permission-Gap): Spec-Verifikation, kein Code.
- **G-7 (Discovery der HDLF-Objekte ins Inventar):** → **Track A, Phase 2** (gleicher
  Mechanismus wie das consumer-seitige Signal).

### B.6 — Aufwand (jetzt): **≈ 2 PT** (G-8 + Doku + Checkliste).

---

## C — Querschnitt

- **Determinismus:** Nur G-8 berührt die Library → einmaliger `version`-Bump + Recompile.
  Track A fasst Engine/Compiler/Store **nicht** an.
- **Migration:** **Keine.** Kein Manifest = kein Produkt; bestehende Contracts/Gates laufen
  unverändert (ADR-0004 §12). `boundary` wird nirgends geschrieben.
- **Glossar:** [`/CONTEXT.md`](../CONTEXT.md) (Data Product, Manifest, Interior, boundary vs.
  kind, Reconciliation, Freshness vs. Load-Lag).

---

## D — Entscheidungs-Log (Grilling 2026-06-22)

| # | Frage | Entscheidung |
|---|---|---|
| Q1 | Verhältnis ADR-0003/0004 | Ein Dokument, zwei asymmetrische Tracks. |
| Q2 | `boundary` vs. `kind` | **Entkoppelt**: `boundary` abgeleitet/read-side, nie persistiert; kein Rename als Vorbedingung. |
| Q3 | Artefakt/Laden | Neues `dq_core/product/` + `products_dir`; **lenient/struktur-only** Laden, referenzielle Lücken = Findings. |
| Q4 | Walk-Stopp | **Deklarierte-Port-Eigenschaft** stoppt, Owner-Set klassifiziert (Fall A vs. B). |
| Q5 | Walk-Output | **Multi-Claim** (Contested fällt als Query ab). |
| Q6 | Findings v1 | **Dangling-Port, Contested-Interieur, cross-owner Boundary-Leak**; 3 weitere → Phase 2. `boundary` rein abgeleitet. |
| Q7 | Health | **worst-of** own-health (nur governance ports) + nicht-ansteckendes upstream-risk (breach + drift). |
| Q8 | Discovery | Deferred; cross-owner Leak liefert schwachen Port-Hinweis gratis. |
| Q9 | Cockpit | **A+**: Products-Seite + read-only `LineageMiniGraph`; restliche Graph-Viz deferred. |
| Q10 | Phasenschnitt | Bestätigt; ORD-Export = Phase 2. |
| Q11 | Katalog-Hazard | **V7/G-8** ergänzt; ADR-0003 = Doku + Verifikation + **G-8** Now-Fix. |
| Q12 | Freshness-Semantik | **Freshness = business-recency** (View-Spalte); **Load-Lag = technisch** (eigener Check, gated V3a). |
