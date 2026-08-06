# PLAN — UX-N7: Spaltenebene-Lineage + Impact-Analyse (O3)

**Stand:** 2026-06-26 · **Adressat:** Coding-Agent · **Modus:** wie HANDOVER —
sequentiell, Acceptance je Schritt grün, kein Merge bei rotem Gate.

> **Kernbefund (aktualisiert):** O3 war **kein Parser-Defekt**, sondern ein
> **Datenproblem**. Der CQN-Walker ist implementiert und unit-getestet; der
> Demo-Snapshot trägt inzwischen CSN-`query`/`csnProjection`-Daten und echte
> `columnEdges`. Offen bleibt die Verifikation gegen einen realen Tenant-Extract.

---

## 1 — Ausgangslage (verifiziert)

**Was bereits steht:**

- **Engine/Walker** — `packages/dq_core/lineage/_csn_reconstructor.py`
  (`extract_query_details`, `_collect_expr_refs`) + `_column_lineage.py`
  (`build_column_lineage`, `build_column_indexes`). Klassifiziert `direct` /
  `computed` / `passthrough`, rendert Expressions, sammelt `allSourceRefs`. Zweiter
  Pfad für SQL-Views via `_sql_column_parser.py` (sqlglot, optional).
- **Tests** — der Walker produziert nachweislich `computed`-Kanten mit Expression:
  `tests/unit/test_column_lineage.py` (`:41`, `:86`), `tests/unit/test_inventory_lineage.py`
  (`:169`, `:377`), `tests/api/test_lineage_columns.py` (`:14`, `:25`).
- **API** — `services/api/routers/lineage.py`:
  `GET /api/lineage` (Graph inkl. `columnEdges`) und
  `GET /api/lineage/columns?object=…[&column=…]` (Per-Spalten-Index
  upstream/downstream via `build_column_indexes`).
- **Frontend-Binding** — `apps/cockpit/src/api/lineage.ts`: `fetchColumnLineage`
  + `useColumnLineage`-Hook; Typen `ColumnLineageObjectResponse` /
  `ColumnLineageColumnResponse` in `@/types`.
- **Extract-Pipeline** — `services/api/extraction.py` ruft
  `build_column_lineage(inv_objs).serialize()` und schreibt nach
  `data/lineage.json`.

**Was umgesetzt ist:**

- **Daten** — `data/inventory.json` trägt Demo-Objekte mit `csnProjection`;
  `data/lineage.json` enthält echte `columnEdges` inklusive `computed`-Kanten
  mit Expression statt Seed-Platzhaltern.
- **Backend/API** — `services/api/extraction.py` schreibt
  `build_column_lineage(inv_objs).serialize()`. `/api/lineage` liefert
  `columnEdges`; `/api/lineage/columns` liefert Upstream/Downstream je Spalte;
  `/api/lineage/columns/impact` liefert transitive Downstream-Consumer mit
  Ownership und Coverage.
- **Frontend-View** — `ColumnLineagePanel` ist im Objekt-Detail-Lineage-Tab
  eingebunden und zeigt Spaltenauswahl, Upstream/Downstream und Impact-Liste.
- **Restrisiko** — Live-Tenant-CSN/SQL-Shapes bleiben zu verifizieren; der Demo-
  und Mock-Pfad ist testgedeckt.

**Acceptance (UX-N7, unverändert):** Spalten-DAG + betroffene Downstream-Consumer
mit Ownership aus einem Incident heraus.

---

## 2 — Strategie

Entkoppeln vom harten externen Blocker **O2** (kein offener Datasphere-/DWC_GLOBAL-
Zugang). UX-N7 lässt sich **ohne** Live-Datasphere demonstrierbar machen, indem die
Demo-Daten realistische CSN-`query`-Bäume bekommen — der bestehende Walker erzeugt
daraus echte `computed`-Kanten. Damit ist die gesamte Kette (Engine → API →
Frontend) gegen belastbare Daten baubar und testbar; der spätere Wechsel auf einen
echten Extract ist reine Datenherkunft, kein Code-Wechsel.

Reihenfolge: **A (Daten) → B (Walker-Härtung) → C (API-Impact) → D (Frontend)**.
A schaltet B–D frei; C/D können nach A parallel laufen.

---

## 3 — Workstreams

### WS-A — Realistische Spalten-Lineage-Daten (entsperrt alles)
**Ziel:** echte `columnEdges` mit `computed`/`direct` + Expression statt Seed-Platzhalter.

- **A1** `data/inventory.json` für ausgewählte Views (mind. `Sales_Orders_View`
  + 2–3 Downstream-Views) um `query` (CSN-AST im von `extract_query_details`
  erwarteten Format: `SELECT.from`/`columns` mit `ref`/`func`/`xpr`) **oder**
  `sql` anreichern. Quelle: bestehende Test-Fixtures in
  `tests/unit/test_inventory_lineage.py` als Vorlage.
- **A2** Extraktion neu erzeugen (`services/api/extraction.py` /
  `scripts/seed.py`), sodass `data/lineage.json` echte `columnEdges` enthält.
  Seed-Platzhalter entfernen.
- **A3** Regressionstest: `build_column_lineage` über das angereicherte Inventar
  liefert ≥1 `computed`-Kante mit nicht-leerer Expression und korrekte
  upstream/downstream-Indizes.

*Acceptance:* `GET /api/lineage/columns?object=Sales_Orders_View` liefert reale
upstream/downstream-Kanten inkl. mind. einer `computed`-Kante mit Expression.

### WS-B — Walker gegen reale CSN-Shapes härten
**Ziel:** keine stillen `direct`/leer-Degradierungen bei komplexer CSN.

- **B1** Fixture-Set realer Shapes: Assoziationen/`$self`, verschachtelte `xpr`
  (CASE/Arithmetik), `SET`/Union-Branches, Calculated Columns, Aliase mit Punkten.
- **B2** Lücken in `_render_expr` / `_collect_expr_refs` / `_render_column`
  schließen; jede Korrektur mit Unit-Test. **`[ENGINE-FROZEN]`/G5 wahren:**
  bestehende Tests unverändert grün, nur erweitern.
- **B3** Coverage-Kennzahl (`columnEdgeMeta.coverage.derived.ratio`) als
  Sichtbarkeitsanker — degradierte/ungemappte Objekte explizit ausweisen (G6-Geist:
  nie still auslassen).

*Acceptance:* neue Shape-Fixtures ergeben erwartete `computed`-Kanten; `ratio`
spiegelt ungemappte Objekte wider.

### WS-C — API: Impact-Endpunkt ✅ (2026-06-26)
**Ziel:** „Welche Downstream-Consumer-Spalten brechen, wenn Spalte X sich ändert?"

> **Umgesetzt:** `GET /api/lineage/columns/impact?object=…&column=…[&max_depth=]`
> (BFS über `columnEdges`, zyklensicher, `truncated`-Flag), angereichert mit
> Ownership (`ownedBy`/`owners`) und Coverage-Flag je betroffenem Consumer.
> Contract-Scan in `_scan_contracts` faktorisiert (geteilt mit `/lineage`).
> Tests in `tests/api/test_lineage_columns.py` (transitiv+Ownership, max_depth/
> truncation, Zyklus). *Erledigt.*

- **C1** `GET /api/lineage/columns` deckt 1-Hop ab. **Neu:** transitive
  Downstream-Hülle je Spalte (BFS über `columnEdges`) + Anreicherung mit
  **Ownership** (`owned_by`/`owners` aus `inventory`) und Contract-/Coverage-Status
  je betroffenem Consumer. Endpoint-Vorschlag:
  `GET /api/lineage/columns/impact?object=…&column=…`.
- **C2** Schemas unter `services/api/schemas/`, Test unter `tests/api/`.
  Zyklen-Schutz (besuchte Knoten), Tiefenlimit.

*Acceptance:* Impact-Response listet alle transitiven Downstream-Spalten mit
Objekt, Ownership und Coverage; Zyklus terminiert.

### WS-D — Frontend: Spalten-DAG + Impact-Liste ✅ (2026-06-26)
**Ziel:** UX-N7-Acceptance im Cockpit.

> **Umgesetzt:** `useColumnImpact`-Hook (`api/lineage.ts`) + Typen
> (`ColumnImpactResponse`). Neue Komponente
> `components/lineage/ColumnLineagePanel.tsx`: Spalten-Picker → Upstream/
> Downstream-DAG (Chips, `direct`/`computed` als Decor-Badge, Expression im
> Tooltip) + Impact-Tabelle (Objekt/Spalte/Ebene/Typ/Owner inkl. Coverage-Flag,
> Truncation-Hinweis). Eingebunden im `lineage`-Tab von `ObjectDetail`. Leerer/
> degradierter Zustand explizit (G6-Geist). Strings in `i18n/de.ts`, vitest
> `tests/ColumnLineagePanel.test.tsx`. **Offen (klein):** dedizierter Einstieg
> direkt aus einem Incident-Drawer (aktuell Einstieg über Objekt-Detail). *Erledigt.*

- **D1** `useColumnLineage` (vorhanden) + neuer `useColumnImpact`-Hook in
  `api/lineage.ts`; ggf. `npm run gen:api` für Typen.
- **D2** **ColumnLineagePanel** im Objekt-Detail / als Drill-down aus
  `SchematicInspector`: Spalten-DAG (Reuse Cytoscape/dagre wie objektebene; Familie
  als Ring nicht Fill — U1), `direct` vs. `computed` visuell unterschieden,
  Expression im Tooltip (Text-Sanitizing, S8).
- **D3** **ImpactList**: aus einer Spalte heraus betroffene Downstream-Consumer mit
  Ownership; Einstieg aus einem Incident (UX-N7-Wortlaut). Deutsche Strings in
  `i18n/de.ts`, vitest-Test.
- **D4** Leerer/degradierter Zustand: wenn keine echten Spalten-Kanten vorliegen,
  klaren Hinweis zeigen (nicht so tun, als sei vollständig) — G6-Geist im UI.

*Acceptance:* aus einem Incident/Objekt → Spalte → DAG + Liste betroffener
Downstream-Consumer mit Ownership; vitest grün, `typecheck`/`lint` sauber.

---

## 4 — Sequenzierung & Aufwand (grob)

| WS | Inhalt | hängt ab von | Aufwand |
|----|--------|--------------|---------|
| A | Realistische Daten | — | klein–mittel |
| B | Walker-Härtung | A (zum Verifizieren) | mittel |
| C | Impact-API | A | klein–mittel |
| D | Frontend DAG + Impact | A, C | mittel |

**Reale Daten (O2):** für den Produktivbetrieb bleibt ein echter Extract mit
CSN-`query`/`sql` nötig — das ist Datenherkunft (Datasphere-Zugang), **kein**
zusätzlicher Code. Der hier gebaute Stand funktioniert mit echten Daten ohne
Änderung.

## 5 — Gates / DoD

- G5/`[ENGINE-FROZEN]`: bestehende Engine-Tests unverändert grün; Walker nur
  erweitert.
- G7: `dq_core` bleibt frameworkfrei.
- Neue API unter `tests/api/`, Walker-Shapes unter `tests/unit/`.
- Frontend: `typecheck` + `lint --max-warnings 0` + vitest grün; Build grün.
- G6-Geist: degradierte/ungemappte Spalten sichtbar, nie still als „vollständig".
- Acceptance UX-N7 erfüllt: Spalten-DAG + Downstream-Impact mit Ownership aus
  Incident.
