# Spec · Lineage-UX-Redesign — ruhige Kamera, lesbare Knoten, gedockte Inspektion

> **Status 2026-06-20:** Neu angelegt. Adressiert drei konkrete Beschwerden an der Lineage-Ansicht
> (`apps/cockpit/src/pages/LineageMap.tsx`): **(1)** die Navigation springt und „resized" bei jeder
> Interaktion, **(2)** die Knoten wirken klobig und sind schlecht scanbar, **(3)** Inspektion und
> Bedienung fühlen sich roh statt designt an. Modus wie `OPEN_TASKS.md` / `HANDOVER.md`: jeder
> Schritt mit Acceptance, kein Merge bei rotem Gate. Farbsemantik (Familie ⟂ Status) und
> Mono-für-Artefakte gelten unverändert (`Konzept_DQ_Cockpit_UIUX.md` §1).

**Grundlage:** `apps/cockpit/src/pages/LineageMap.tsx` (Objekt- und Spalten-Graph, Cytoscape +
`cytoscape-dagre`), `apps/cockpit/src/lib/lineage.ts`, Token-System `apps/cockpit/src/index.css`.
**Leitprinzipien (geerbt, nicht neu verhandelt):** Dev-Tool-Ethos · „Farbe ist Bedeutung, nicht
Dekoration" · „Das Objekt ist die Achse" · **die 3px-Familien-Spine als einziges Stil-Signal** —
genau dieses Signal fehlt heute in der Lineage komplett und ist der rote Faden des Redesigns.

> **Leitidee:** Die Daten und die IA stimmen. Was fehlt, ist **Ruhe** — eine Kamera, die nur dann
> bewegt, wenn der Nutzer es auslöst, Knoten, die als Karte statt als Punkt-mit-schwebendem-Text
> lesen, und ein Inspektions-Panel, das nicht über den Graphen klappt. Das ist mehr Choreografie
> als Politur.

> **Umgesetzt 2026-06-20 (Phase 1 + 2)** — Branch `claude/lineage-usability-design-7p9p01`,
> alles in `apps/cockpit/src/pages/LineageMap.tsx`:
> **Phase 1 (Ruhe):** UX-L1 (Spalten-Graph layoutet nur noch bei neu erscheinenden Knoten; Kamera
> wird über Pan/Zoom und über Trace-Rebuilds hinweg erhalten statt refittet — *Einschränkung:*
> bestehende Knoten können beim Trace-Rebuild reflowen, die Kamera bleibt aber stehen), UX-L2
> (Fokus gleitet animiert und nur für Off-Screen-Knoten, respektiert `prefers-reduced-motion`),
> UX-L3 (Canvas füllt die Seite via `clamp(...100dvh...)` + `ResizeObserver`→`cy.resize()` ohne
> Refit), UX-L6 (leere Swimlanes werden bei Filtern ausgeblendet), UX-L7 (`useIsNarrow` per
> `matchMedia`-Listener statt eingefrorenem Snapshot).
> **Phase 2 (Optik):** UX-L8 (Objektknoten = Karte mit 3px-Familien-Spine + *einem* Coverage-Punkt,
> Label im Knoten, Tokens), UX-L9 (Lanes = ruhige solide Swimlane-Bänder), UX-L10 (lesbare
> Spalten-Pills, 11px), UX-L11 (Legenden in eine einklappbare Leiste unter dem Graphen, inkl.
> Familien-Spine-Legende), UX-L12 (`useThemeVersion` baut den Graphen bei `data-theme`-Wechsel neu
> auf → Live-Recolor). Verifiziert: `typecheck`, `lint`, 70 Tests, `build` grün.
> **Offen (Phase 3):** UX-L13 (gedocktes Panel), UX-L4 (geteilte Instanz/Tabs), UX-L5 (Pin-Modus),
> UX-L14 (Graph-Controls/Minimap), UX-L15 (Tastatur/A11y).
> Aktive Nachverfolgung für Phase 3 steht seit 2026-07-04 in [`OPEN_TASKS.md`](OPEN_TASKS.md) §O.

---

## 1 · Befund — was heute warum stört

| ID | Befund | Ort (`LineageMap.tsx`) | Klasse |
|----|--------|------------------------|--------|
| B1 | **Spalten-Graph re-layoutet bei *jeder* Interaktion** mit `fit: true` — expand/collapse/trace/search lösen ein frisches `dagre`-Layout samt Viewport-Refit aus. Das ist die Hauptursache für „springt und resized". | `applyColumnGraphState`, Z. 755–758 | Kamera |
| B2 | **Objekt-Graph zentriert hart bei jedem Fokus** (`cy.center(node)`) — jeder Klick reißt die Kamera ohne Übergang an eine neue Stelle. | Focus-Effekt, Z. 389–403 | Kamera |
| B3 | **Feste Canvas-Höhe 560px** statt viewport-füllend; auf großen Screens ein kleines eingezwängtes Fenster unter `page-full`. | Z. 685, 1186 | Kamera/Layout |
| B4 | **Tab-Wechsel Objects↔Columns unmountet die ganze Cytoscape-Instanz** (zwei getrennte Komponenten) → State + Positionen verloren, Re-Layout-Flash. | Z. 1253–1279 | Kamera/State |
| B5 | **Position-Cache (sessionStorage) + `preset`-Layout + manuelles Node-Dragging** mischen Auto-Layout und Handpositionen → stale/verschobene Knoten nach Daten- oder Filterwechsel. | `cacheKey`, `savePositions`, Z. 74–79, 544–575 | Kamera/State |
| B6 | **Filter setzen nur `display:none` ohne Re-Layout/Refit** → Löcher und leere Lanes im DAG; der Graph „zerfranst" statt sich zu verdichten. | `applyFilters`, Z. 353–383 | Kamera/Layout |
| B7 | **`isNarrow` ist ein einmaliger `window.innerWidth`-Snapshot ohne resize-Listener** → reagiert beim Fenster-Resize nicht, kann mitten in einer Sitzung „falsch" stehen bleiben (trägt zum „resizes"-Eindruck bei). | Z. 1212 | Kamera |
| B8 | **Objektknoten = 28×28-Punkt mit Coverage-Glyph als `background-image` und Label per `text-halign:right` schwebend daneben** → wirkt wie Punkt mit frei fliegendem Text, Labels überlappen bei dichten Graphen, schlecht scanbar. | Node-Style, Z. 474–497 | Knoten |
| B9 | **Coverage doppelt codiert** — `border-color` *und* Glyph-Background. Redundant und unruhig; widerspricht „Farbe sparsam = Bedeutung". | Z. 477–486 | Knoten |
| B10 | **Familien-Spine (3px) fehlt an jedem Knoten** — der zentrale Stil-Anker des Cockpits wird in der Lineage nicht eingelöst; Knoten tragen keine Familien-/Layer-Identität visuell. | gesamter Node-Style | Knoten |
| B11 | **Lanes = gestrichelte, transluzente Compound-Box mit Top-Label** → liest als Platzhalter, nicht als strukturierende Swimlane. | Lane-Style, Z. 518–537 | Knoten |
| B12 | **Spaltenknoten = 16px-Mini-Pill, 9px Font** — kaum lesbar, kein Zustand sichtbar. | Z. 1011–1026 | Knoten |
| B13 | **Drei Legenden (Coverage, Gate/Breach, Edge-Kinds) gequetscht in die Filterzeile**, wrappen unkontrolliert über die Breite. | Z. 662–682 | Knoten/Chrome |
| B14 | **Side-Panel (300/330px) liegt `position:absolute` *über* dem Graphen** und verdeckt die rechten Knoten — gerade die Downstream-Seite, die man beim Inspizieren sehen will. | `ObjectSidePanel` Z. 212–216, `ColumnPanel` Z. 775–779 | Usability |
| B15 | **Keine Zoom-/Fit-/Reset-Controls, keine Minimap, keine Tastaturnavigation** — Orientierung nur per Maus-Pan/Wheel. | — | Usability |
| B16 | **Theme nur einmalig gecacht** (`resolvedTheme` Modul-Singleton) → Laufzeit-Themewechsel (signal/blueprint/daylight/amber) färbt den Graphen nicht um. | `resolveTheme`, Z. 55–72 | Knoten |
| B17 | **Hartkodierte Größen/Fonts statt Tokens** (`--s*`, `--r*`, `--font-*`) in den Inline-Styles → driftet vom Rest des Cockpits ab. | durchgängig | Knoten/Chrome |

---

## 2 · Zielbild

Eine Lineage, die sich wie ein Instrument anfühlt, nicht wie ein Whiteboard, das bei jeder Berührung
neu zeichnet:

- **Die Kamera bewegt nur, wenn der Nutzer es will.** Filtern, Expandieren, Tracen, Suchen lassen die
  Sicht stehen; nur ein expliziter „Fokus"/„Fit" bewegt — und dann *animiert*, nicht springend.
- **Ein Knoten ist eine Karte**: Name links-bündig im Knoten, 3px-Familien-Spine an der Führungskante,
  *ein* dezenter Status-Punkt für Coverage. Lesbar bei einem Blick, scanbar in der Spalte.
- **Lanes sind echte Swimlanes**: ruhige, beschriftete Bänder, die die Layer-Achse (Raw → IC → BC →
  Serving) tragen — die räumliche Erzählung des DAG.
- **Inspektion dockt**, sie verdeckt nicht. Der Graph bekommt den Platz neben dem Panel, nicht darunter.
- **Eine persistente Graph-Fläche**: Objects/Columns sind Sichten *einer* Leinwand, kein Remount.

---

## 3 · Workstream A — Ruhige Kamera (löst „springt & resized")

### UX-L1 · Layout entkoppeln von Interaktion *(B1, B6)*
Re-Layout nur bei (a) erstem Render einer Datenmenge und (b) explizitem „Re-Layout/Fit"-Klick. Bei
expand/collapse/trace/search **kein** `fit: true` und kein globales `dagre` mehr. Für neu
hinzukommende Spalten ein *inkrementelles* Layout, das bestehende Positionen respektiert
(`dagre` nur auf dem neuen Sub-Graphen, oder `elk`/`fcose` mit `randomize:false` + Fixierung der
sichtbaren Knoten). Pan/Zoom bleiben über die Interaktion hinweg erhalten.
**Acceptance:** Spalte expandieren/Trace auslösen verändert weder Zoomstufe noch Bildausschnitt der
bereits sichtbaren Knoten (Pixel-Diff der Viewport-Transform = 0 außerhalb des neuen Teilbaums).

### UX-L2 · Fokus animieren statt zentrieren *(B2)*
`cy.center(node)` → `cy.animate({ center: { eles: node }, ... }, { duration: 220, easing: 'ease-out' })`,
und nur wenn der Knoten **außerhalb** des aktuellen Viewports liegt (sonst gar keine Bewegung).
`prefers-reduced-motion` respektieren (duration 0).
**Acceptance:** Klick auf einen bereits sichtbaren Knoten bewegt die Kamera nicht; Klick auf einen
Off-Screen-Knoten gleitet weich heran.

### UX-L3 · Canvas füllt die Seite *(B3)*
Feste `height: 560` ersetzen durch flex-/`min-height:0`-basiertes Füllen des `page-full`-Restraums
(`height: calc(100dvh - <chrome>)` bzw. Flex-Child mit `flex:1`). Cytoscape bei Container-Resize via
`ResizeObserver` → `cy.resize()` ohne Refit.
**Acceptance:** Auf 2560×1440 nutzt der Graph die volle Höhe; Fenster-Resize ändert die Canvas-Größe
ohne Sprung/Zoomverlust.

### UX-L4 · Eine persistente Instanz, Tabs als Sicht *(B4)*
Objects/Columns teilen sich **eine** Cytoscape-Instanz bzw. einen gemeinsamen Container; der
Tab-Wechsel blendet Element-Klassen um statt zu remounten. Mindestziel, falls voll geteilte Instanz
zu groß: Instanzen über `keep-alive`-Muster (gemounted, nur `display:none`) halten, damit Position
und Zoom überleben.
**Acceptance:** Objects→Columns→Objects bewahrt Zoom, Pan und Selektion; kein Layout-Flash.

### UX-L5 · Auto-Layout vs. Handpositionen entwirren *(B5)*
Default ist **immer** das deterministische Auto-Layout. Manuelles Dragging wird zum Opt-in
(„Pin-Modus"); ungepinnte Knoten folgen dem Auto-Layout. Der sessionStorage-Cache speichert nur
explizit gepinnte Positionen, niemals einen kompletten `preset`-Snapshot, der bei Datenänderung
stale wird. `cacheKey` auf Daten-Hash + Layout-Version stützen, bei Miss sauber neu layouten.
**Acceptance:** Nach Re-Extract (geänderte Node-Menge) erscheinen keine Knoten an alten Positionen;
gepinnte Knoten bleiben nur erhalten, wenn sie noch existieren.

### UX-L6 · Filter verdichten statt durchlöchern *(B6)*
Ausgefilterte Knoten werden ausgeblendet *und* das sichtbare Set wird (auf Wunsch / per Re-Layout-
Button) neu verdichtet, sodass keine leeren Lanes/Löcher bleiben. Default: Layout stehen lassen
(Ruhe vor Verdichtung), aber „An Sichtbares anpassen" anbieten.
**Acceptance:** Layer-Filter „Serving" zeigt ein kompaktes Band ohne große Leerflächen, ohne dass
die Kamera ungefragt springt.

### UX-L7 · Responsives Gate korrekt *(B7)*
`isNarrow` aus dem Render-Snapshot in einen `matchMedia('(min-width: 900px)')`-Listener (oder
`ResizeObserver`) überführen, damit der Desktop-Hinweis live auf Resize reagiert statt einzufrieren.
**Acceptance:** Fenster von 1200→800→1200 px schaltet Hinweis/Graph korrekt um, ohne Reload.

---

## 4 · Workstream B — Knoten & Visuelles (löst „klobig")

### UX-L8 · Objektknoten als Karte mit Familien-Spine *(B8, B9, B10, B17)*
Knoten = abgerundetes Rechteck (z. B. ~168×30, dynamisch nach Label) mit:
- **3px-Familien-Spine** an der linken Führungskante (`--obs`/`--qual`/`--cont` nach Familie/Layer) —
  das geerbte Stil-Signal, das die Lineage in den Rest des Cockpits einbindet.
- **Label links-bündig *im* Knoten** (`text-halign: right` mit schwebendem Text entfällt), Mono,
  Token-Größe; Ellipsis bei Überlänge.
- **Ein Coverage-Status-Punkt** rechts im Knoten (eine Achse: covered/partial/gap/out) — die doppelte
  Codierung (Border *und* Glyph) entfällt; Border wird neutral/Hover-reaktiv.
Größen/Radien/Fonts aus Tokens (`--r-md`, `--font-mono`, `--s*`), nicht hartkodiert.
**Acceptance:** Bei 40+ Knoten überlappen keine Labels; Coverage ist über genau ein Element ablesbar;
jeder Knoten trägt eine sichtbare Familien-Spine.

### UX-L9 · Lanes als ruhige Swimlanes *(B11)*
Gestrichelte transluzente Box → durchgehendes, sehr dezent getöntes Band mit klarer
`mono-label`-Beschriftung (uppercase, tracked) an der Oberkante, hairline-getrennt (`--line`).
Reihenfolge fix aus `LAYER_ORDER` (`lib/lineage.ts`). Optional: Lane-Header zeigt #Objekte je Lane.
**Acceptance:** Die Layer-Achse Raw→IC→BC→Serving liest als zusammenhängende Bänder; Lanes wirken
strukturierend, nicht wie Platzhalter.

### UX-L10 · Spaltenknoten lesbar *(B12)*
Spalten-Pill von 16px/9px auf Token-konforme Höhe/Schrift anheben, Padding aus `--s1/--s2`; aktiver
Trace-Pfad klar hervorgehoben (bestehende `trace-hl`/`trace-dim` beibehalten, Kontrast erhöhen).
Aggregat-Kanten-Label (Spaltenzahl) mit lesbarem Hintergrund-Chip.
**Acceptance:** Spaltennamen sind bei Default-Zoom ohne Hineinzoomen lesbar; getracter Pfad ist auf
einen Blick vom gedimmten Rest unterscheidbar.

### UX-L11 · Legenden aus der Filterzeile lösen *(B13)*
Coverage-/Gate-/Edge-Legenden in eine eigene, einklappbare Legenden-Leiste (oder Popover „Legende")
unterhalb des Graphen verschieben; die Filterzeile trägt nur noch Steuerelemente. Konsistente
Chip-Optik mit dem Rest des Cockpits.
**Acceptance:** Die Filterzeile wrappt auf 1280px nicht mehr; Legende ist auffindbar, aber nicht im Weg.

### UX-L12 · Theme live auflösen *(B16)*
`resolvedTheme`-Singleton entfernen oder bei `data-theme`-Wechsel invalidieren (MutationObserver auf
`<html>` oder Re-Read pro Mount). Cytoscape-Styles bei Themewechsel neu anwenden (`cy.style(...)`).
**Acceptance:** Umschalten signal→daylight→blueprint färbt Knoten, Lanes, Kanten sofort um, ohne Reload.

---

## 5 · Workstream C — Inspektion & Controls (Usability)

### UX-L13 · Inspektions-Panel docken statt überlagern *(B14)*
Side-Panel (`ObjectSidePanel`, `ColumnPanel`) aus `position:absolute`-Overlay in ein gedocktes
Split-Layout überführen: Graph schrumpft auf die verbleibende Breite, Panel sitzt rechts daneben
(resizable, Mindestbreiten). Auf engeren Viewports als Off-Canvas-Drawer.
**Acceptance:** Bei geöffnetem Panel ist kein Downstream-Knoten verdeckt; der Graph re-fittet *nicht*
automatisch beim Öffnen (Ruhe-Prinzip), nutzt aber den verfügbaren Platz beim nächsten Fit.

### UX-L14 · Graph-Controls *(B15)*
Dezente Steuerleiste (über dem Canvas, instrument-grade): Zoom +/−, „Fit", „Re-Layout", „Reset
Pins", Zoom-Prozent. Optional Minimap (`cytoscape`-Panzoom/Navigator) für große Graphen.
**Acceptance:** Nutzer kann ohne Mausrad fitten/zoomen; „Fit" ist die *einzige* Aktion, die bewusst die
ganze Kamera bewegt.

### UX-L15 · Tastatur- & A11y-Pass *(B15)*
Pfeiltasten = Pan, `+/−` = Zoom, `f` = Fit, `Esc` = Selektion/Panel schließen, `/` = Suche fokussieren.
Sichtbarer Fokusring (`--focus`) auf Controls; Knoten-Selektion via Tab/Enter erreichbar
(zumindest über die Suchliste/Command-Palette als Fallback).
**Acceptance:** Kernpfade (suchen → Objekt wählen → Panel öffnen/schließen) sind rein per Tastatur bedienbar.

---

## 6 · Sequenzierung

1. **Phase 1 — Ruhe (höchster Hebel gegen die Beschwerde):** UX-L1, UX-L2, UX-L3, UX-L6, UX-L7.
   Danach „springt & resized" gelöst, noch ohne Optik-Umbau.
2. **Phase 2 — Optik:** UX-L8, UX-L9, UX-L10, UX-L11, UX-L12. Knoten lesen als Karten mit Spine.
3. **Phase 3 — Bedienung:** UX-L13, UX-L4, UX-L5, UX-L14, UX-L15. Gedocktes Panel, geteilte Instanz,
   Controls, Tastatur.

Phase 1 ist eigenständig auslieferbar und adressiert die wörtliche Beschwerde am direktesten.

## 7 · Bewusst ausgeklammert

- Kein Wechsel der Graph-Engine (Cytoscape bleibt); `elk`/`fcose` nur falls inkrementelles Layout
  (UX-L1) es erzwingt — dann als isolierter, getesteter Schritt.
- Keine neuen Backend-Endpunkte; Spec ist reine Frontend-/UX-Arbeit auf vorhandenen
  `/api/lineage`-Daten.
- Keine Änderung der Farbsemantik (Familie ⟂ Status) und keine neue Mono-/Token-Politik —
  beides wird nur *konsequenter angewendet*.

## 8 · Risiken & Prüfpunkte

- **Inkrementelles Layout (UX-L1)** ist der technisch heikelste Punkt; vor Vollumbau an einem
  mittelgroßen Spalten-Graphen prototypen. Fallback: Layout stehen lassen + manueller „Re-Layout".
- **Geteilte Instanz (UX-L4)** kann Selektions-/Filter-Zustände koppeln; sauber über
  Element-Klassen trennen, sonst beim keep-alive-Muster bleiben.
- **Bestehende Tests** (`apps/cockpit/src/tests/lineage.test.ts`, `lib/lineage.ts`-Helfer) grün
  halten; reine `lib`-Funktionen bleiben unangetastet, der Umbau ist im View.
</content>
</invoke>
