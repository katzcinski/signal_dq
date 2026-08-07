# REVIEW: UI-Konsistenz der Hauptseiten (Referenz: Objekte-Seiten)

Stand: 2026-07 · Branch `claude/tool-ui-design-review-8qsy67` · Nur Befund, keine Code-Änderungen.

Die Objekte-Seiten (`ObjectCatalog.tsx`, `ObjectDetail.tsx` mit den
`components/object-detail/*`-Bausteinen) wurden zuletzt gezielt optimiert und
dienen hier als Referenzstandard. Dieses Review vergleicht die übrigen
Hauptfenster gegen diesen Standard und schlägt konkrete Angleichungen vor.

## 1. Was die Objekte-Seiten zum Maßstab macht

**Objekt-Detail** (`/objects/:id`):

- Breadcrumbs → **Hero-Karte** (Titel, Tags, Meta-Zeile, Fakten, rechtsbündige
  Aktionen mit Pending-/Disabled-Zuständen) → **Summary-Card-Grid**
  (`label / value / hint / tone`) → **Attention-Band** mit Deep-Links in den
  passenden Tab → zweistufige, gruppierte Navigation — alles URL-getrieben
  (`?tab=`).
- Layout-treue Skeletons (`ObjectHeroSkeleton`, Sektions-Skeletons) statt
  „Laden…“-Text; Sektions-Reveal-Animation mit `prefers-reduced-motion`-Fallback.
- Responsive über echte CSS-Klassen mit Media-Queries
  (`.object-detail-hero`, `.object-detail-actions`, …).

**Objekt-Katalog** (`/objects`):

- Alle Filter URL-synchronisiert (`useSearchParamState`), Filter-Chips plus
  Aktiv-Filter-Zeile mit Einzel-Clear, entprellte Suche (`useDeferredValue`),
  sortierbare Spalten, `TableSkeleton`, `ErrorBanner` mit Retry.
- Peek-Panel: Name navigiert zur Vollseite, Zeile öffnet den Peek (R6-1).
- Konsequente Token-Nutzung (`--fs-*`, `--lh-*`, `--s*`, `color-mix`-Tints)
  statt Magic Numbers.

## 2. Querschnittsbefunde (größter Hebel)

Diese Punkte betreffen mehrere Seiten gleichzeitig; sie zuerst zu lösen macht
jede spätere Seitenangleichung billig.

1. **Kein gemeinsamer Seitenkopf.** Titelgrößen schwanken zwischen 18px
   (`Objekte`, `Incidents`, `Workbench`), 20px (`Cockpit`, `My Work`) und
   Margins 10/14/16/20 — während der Hero das Token `--fs-h1` nutzt.
   → `PageHeader`-Primitive (Titel, Untertitel, rechter Slot für
   Suche/Aktionen) unter `components/ui/`.
2. **Duplizierte Mikro-Komponenten.** Der identische `chipBtn`-Stil ist in
   `ObjectCatalog.tsx`, `CheckLibrary.tsx` und inline in `Incidents.tsx`
   handkopiert; Proposals' `GroupByControl` ist eine vierte Variante.
   Ebenso bauen `Incidents` (`drawerBtn`), `Proposals`, `RunDetail` und
   `ContractWorkbench` (`btnStyle`) eigene Buttons, obwohl `ui/Button`
   Pending-/Disabled-/Variant-Support mitbringt.
   → `FilterChip`-Primitive extrahieren, `Button` flächig adoptieren.
3. **Ladezustände uneinheitlich.** Objekte: layout-treue Skeletons.
   `Proposals`, `CheckLibrary`, `RunDetail`: nur „Laden…“-Text. Das
   Status-Grid im `Cockpit` hat gar keinen Skeleton (nur der KPI-Streifen).
4. **URL-Synchronisierung lückenhaft.** `Schedules` hält Filter+Suche in
   `useState` (nicht teil-/refreshbar), Proposals' Gruppierung steht nicht in
   der URL, und der Incident-Drawer hat keinen `?id=`-Deep-Link — deshalb
   können Cockpit-/My-Work-Zeilen nur auf eine *gefilterte Liste* verlinken
   statt den konkreten Incident zu öffnen.
5. **i18n-Verstöße.** Hartkodierte deutsche Strings außerhalb `i18n/de.ts`,
   teils ohne Umlaute: `Proposals.tsx` („Im Contract pruefen ->“,
   „Gate“/„Contract“-Badges), `Compliance.tsx` (Banner „Noch keine aktiven
   Contracts … unabhaengig“), `ContractWorkbench.tsx`
   („Promotion fehlgeschlagen.“). Verstößt gegen die Repo-Konvention, dass
   alle Nutzertexte in `de.ts` leben.
6. **`IncidentDrawer` reimplementiert `SidePanel` — schlechter.** Die
   vorhandene `SidePanel`-Primitive hat eine echte Fokus-Falle; der
   handgebaute Drawer behandelt nur Escape + Initialfokus. Portierung
   behebt zugleich visuelle Drift (Schatten, Kopf, Close-Button).
7. **Attention-Band- und Summary-Card-Muster werden nicht wiederverwendet.**
   Genau das fehlt `My Work` („was braucht heute meine Aufmerksamkeit“),
   dem `Cockpit` und `RunDetail` (handgebaute Statistikzeile).
8. **Responsive-Regressionen.** `My Work`: KPI-Zeile fix `repeat(3, 1fr)`;
   `Compliance`: Panel-Grid fix `1fr 1fr` — beides bricht auf schmalen
   Screens, obwohl `.dash-kpis`/`.dash-2col` mit Media-Queries existieren.
9. **`Compliance` rendert eine rohe `<table>`** statt der `Table`-Komponente —
   verliert Row-Hover, Dichte-Tokens (`--row-pad-*`, `--cell-fs`),
   Sortierung und konsistente Header.

## 3. Befunde je Seite

Priorität gemäß Abstimmung: **(1) Incidents → (2) My Work + Proposals →
(3) Products + Compliance**; RunDetail/Schedules danach; Workbench siehe §4.

### Incidents (`/incidents`) — Priorität 1

- Drawer auf `SidePanel` + `Button` umstellen (Fokus-Falle, konsistenter Kopf).
- `?id=`-Deep-Link für den Drawer; damit können Cockpit/My Work direkt den
  konkreten Incident öffnen.
- Zählwerte an den Status-Tabs (`Offen (3)` …), wie es der Nutzer aus dem
  Attention-Band kennt.
- Kind-Filter-Chips auf die gemeinsame Chip-Primitive; Aktiv-Filter-Zeile
  wie im Objekt-Katalog ergänzen.
- Severity-Filter existiert nur im Checks-Tab — auf die Incident-Tabs ausweiten.

### My Work (`/my`) — Priorität 2

- Attention-Band-artige Zusammenfassung oben statt vier gleichwertiger Panels;
  die wichtigste Information („2 kritische Incidents mir zugewiesen“) muss
  vor dem Scrollen sichtbar sein.
- Zeilen sollen den konkreten Incident öffnen (setzt den `?id=`-Deep-Link
  voraus), nicht nur die gefilterte Liste.
- KPI-Grid auf `.dash-kpis` (auto-fit) statt fix `repeat(3, 1fr)`.
- Panel-Skeletons; fehlendes `ErrorBanner` für die Objects-Query ergänzen;
  Panels über `gap` statt `marginTop`-Wrapper stapeln.

### Proposals (`/proposals`) — Priorität 2

- i18n-Fixes (§2.5) inkl. korrekter Umlaute und `→` statt `->`.
- Karten-Skeletons statt „Laden…“; `Button`-Adoption in den Karten.
- `groupBy` per `useSearchParamState` in die URL.
- Status-Filter (offen/bewertet) als Chips analog Objekt-Katalog; die
  Cluster-Ansicht bleibt Default.

### Products (`/products`) — Priorität 3

- Geringste Filter-Parität aller Listen: keine Suche, keine Chips, kein
  URL-State. Die Toolbar aus `ObjectCatalog` (Suche + Lifecycle-/Health-Chips
  + Aktiv-Filter-Zeile) direkt übertragen.
- Optional Peek-Panel (Zeile peekt, Name navigiert) analog R6-1.
- `ProductDetail` ist bereits weitgehend angeglichen (Breadcrumbs,
  `product-hero`-Klassen) — nur Feinschliff nötig.

### Compliance (`/compliance`) — Priorität 3

- Objektstatus-Tabelle auf die `Table`-Komponente umstellen (§2.9),
  Zeilenklick → Objekt-Detail.
- Panel-Grid auf `.dash-2col`; handgerollte KPI-Chips auf `Kpi`/Summary-Cards.
- Inline-Banner-Text nach `de.ts` (§2.5).

### RunDetail (`/runs/:id`) — nach Priorität 1–3

- Statistikzeile (Total/Passed/Failed/Warnings) auf das
  `ObjectSummaryCard`-Grid; Kopf Richtung Hero-Muster.
- „Nur Fehlschläge“-Filterchip bzw. Failures-first-Sortierung — dafür kommt
  man auf die Seite.
- `Button`-Adoption (CSV, Vergleich), Skeleton statt „Laden…“.

### Schedules (`/schedules`) — nach Priorität 1–3

- Filter + Suche per `useSearchParamState` in die URL.
- Lokale `Tile`-Komponente durch das Summary-Card-Muster ersetzen.

### Cockpit (`/`) — Feinschliff

- Bereits nah am Standard. Titel auf Token; Skeleton fürs Status-Grid;
  SLA-Panel auf `Table`; KPI-Kacheln als Deep-Links auf die jeweils
  gefilterte Ansicht (z. B. „Offene Incidents“ → `/incidents?status=open`).

### CheckLibrary (`/library`) — Feinschliff

- Guter Stand (URL-Filter, Fieldsets). Karten-Skeletons statt Text;
  `chipBtn` auf die gemeinsame Primitive.

## 4. Contract-Workbench (`/contracts`) — Vorschläge (eigener Umbau-Pass)

Der Workbench-Umbau ist bewusst **nicht** Teil der Prioritäten 1–3, sondern
ein eigener Pass. Vorschläge:

- **Gruppierte Navigation wie im Objekt-Detail**: Der `EditorPane` mischt
  heute Garantien-Editor, Check-Builder, Compile/Dry-Run, Breaking-Diff, SLA
  und YAML-Vorschau in einer Scroll-Säule. Eine zweistufige Navigation
  (Gruppen: *Definition* / *Prüfung & Diff* / *Betrieb*) mit `?tab=`-URL-State
  würde die Seite strukturieren, ohne Funktionen zu verschieben.
- **Datei aufteilen**: 1 666 Zeilen mit ~20 lokalen Komponenten →
  `components/workbench/` (GuaranteeEditor, CheckBuilder, CompilePanel,
  BreakingDiffPanel, ContractList sind bereits sauber geschnitten und nur
  auszulagern).
- **Primitive adoptieren**: lokales `btnStyle` → `ui/Button`; Skeletons für
  Liste + Editor; `minHeight: 600` durch flexible Höhe ersetzen.
- **Kurzfristig (risikolos, kann mit Priorität 1–3 mitlaufen)**: i18n-Fix
  („Promotion fehlgeschlagen.“ nach `de.ts`), Button-Adoption.

## 5. Empfohlene Umsetzungsreihenfolge

1. **Gemeinsame Primitives** (macht alles Folgende billig):
   `PageHeader`, `FilterChip`, `Button`-/`SidePanel`-Adoption, i18n-Fixes,
   Skeleton-Vereinheitlichung, Responsive-Fixes (§2).
2. **Incidents** (§3, Priorität 1).
3. **My Work + Proposals** (Priorität 2).
4. **Products + Compliance** (Priorität 3).
5. **RunDetail, Schedules, Cockpit-/Library-Feinschliff.**
6. **Workbench-Umbau als eigener Pass** (§4).

Jeder Schritt ist unabhängig shippbar; CI-relevante Gates (G4 advisory,
Lint 0 Warnings, vitest) bleiben von reinen UI-Angleichungen unberührt,
solange keine API-Typen angefasst werden.
