# Handover — SLA-Übersichts-Panel (Compliance-Seite)

> **Status: umgesetzt (Option A).** Das Panel rendert auf der Compliance-Seite
> je aktivem Boundary-Contract eine Zeile (aktueller Compliance-Status +
> 7/30/90-Tage-Fenster). Neu: `components/compliance/SlaOverviewPanel.tsx` und
> das geteilte Primitiv `components/ui/SlaWindowValue.tsx` (Schwellwerte/Farben,
> nun auch von `SlaBars` genutzt). Entscheidungen zu den offenen Fragen unten:
> **(1)** Option A (N Einzelabfragen je Zeile). **(2)** Zeile klickbar →
> Objektdetail (`/objects/{product}`). **(3)** nur `active`. **(4)** stabile
> Sortierung nach Produktname (worst-first ist unter Option A nicht möglich, da
> die Fensterwerte erst pro Zeile geladen werden). Tests:
> `src/tests/SlaOverviewPanel.test.tsx`. Die zuvor toten `governance.sla*`-Strings
> werden jetzt gelesen.

**Status:** offen · **Bereich:** Frontend (Compliance/Governance), optional Backend
**Kontext:** Bei der Governance-UI-Überarbeitung (`claude/governance-ui-improvements-pgvzem`)
fiel auf, dass die Compliance-Seite i18n-Strings für ein SLA-Panel besitzt, dieses
Panel aber **nie gerendert** wird. Dieses Dokument übergibt Design und Umsetzung.

## Problem in einem Satz

`src/i18n/de.ts` definiert unter `governance.*` die Schlüssel `slaTitle`,
`slaProduct`, `slaCurrent`, `sla7d`, `sla30d`, `sla90d`, `slaEmpty` — eine
„SLA-Übersicht (aktive Contracts)". Kein Code liest sie. Entweder das Panel
bauen (dieses Handover) **oder** die toten Strings entfernen.

## Zielbild

Ein Panel auf der Compliance-Seite (`src/pages/Compliance.tsx`), das je **aktivem
Boundary-Contract** eine Zeile zeigt:

```
SLA-Übersicht (aktive Contracts)
┌───────────────┬──────────┬─────────┬─────────┬─────────┐
│ Produkt       │ Aktuell  │ 7 Tage  │ 30 Tage │ 90 Tage │
├───────────────┼──────────┼─────────┼─────────┼─────────┤
│ SALES_ORDERS  │ ● Konform│ 99,8 %  │ 99,1 %  │ 98,4 %  │
│ FIN_LEDGER    │ ● Verletzt│ 94,2 % │ 96,0 %  │ 97,3 %  │
└───────────────┴──────────┴─────────┴─────────┴─────────┘
```

- **Nur aktive Contracts** (Titel sagt es; `activeContracts` ist in
  `Compliance.tsx` bereits berechnet).
- Leerzustand `slaEmpty` = „Keine aktiven Contracts", wenn die Liste leer ist.
- Platzierung: als weiteres `<Panel family="contract">` nach der Objekt-Tabelle,
  vor der `<details>`-Regel-Disclosure.

## Was bereits existiert (wiederverwenden, nicht neu bauen)

| Baustein | Ort | Zweck |
|---|---|---|
| `GET /api/contracts/{product}/sla` | `services/api/routers/contracts.py:824` | Liefert `{ product, kind, current, windows:{7d,30d,90d} }` je Produkt |
| `SlaResponse` | `apps/cockpit/src/types/index.ts:569` | Typ dazu; `windows` sind `number \| null` (%-compliant) |
| `useContractSla(product)` | `apps/cockpit/src/api/contracts.ts:105` | react-query-Hook auf obigen Endpoint |
| `store.get_sla(product, days)` | `packages/dq_core/store/sqlite_store.py:1080` | %-Zeit im Zustand `compliant` aus `dq_compliance_events`; `None` ohne Events |
| `SlaBars` | `apps/cockpit/src/components/workbench/SlaBars.tsx` | **Kanonisches Rendering** einer einzelnen 7/30/90-Reihe als Balken |
| `StatusPill` | `apps/cockpit/src/components/ui/StatusPill.tsx` | Für die `current`-Spalte (`compliant`/`breached`); nimmt `label`-Prop |
| `Table`/`ColDef` | `apps/cockpit/src/components/ui/Table.tsx` | Tabellenlayout wie die Objekt-Tabelle |

**Schwellwerte (aus `SlaBars` übernehmen, damit die Farben konsistent sind):**
`≥ 99 %` → `--status-ok`, `≥ 95 %` → `--status-warn`, sonst `--status-fail`;
`null` → „keine Daten" (`t.workbench.slaNoData`).

## Datenlücke — die eine echte Entscheidung

Es gibt **keinen Aggregat-Endpoint**, der die SLA-Fenster aller aktiven
Contracts in einem Response liefert. Zwei Wege:

**Option A — Frontend, N Einzelabfragen (empfohlen für die erste Version).**
Über `activeContracts` iterieren und pro Zeile `useContractSla(product)` rufen.
react-query parallelisiert und cacht die Abrufe; bei der realistischen Größe
(Dutzende Contracts) unkritisch. Kein Backend-Change, keine neuen Gates. Umsetzung
als kleine `<SlaRow product=…>`-Komponente, die ihren eigenen Hook hält — analog
zu `SlaBars`.

**Option B — Aggregat-Endpoint (Skalierungspfad).**
`GET /api/coverage/sla` in `services/api/routers/metrics.py` (neben
`coverage_summary`), das über die aktiven Boundary-Contracts läuft und
`[{ product, current, windows }]` zurückgibt (`store.get_sla` je Fenster). Ein
Request. Erfordert laut `CLAUDE.md` → „When adding features": Router registrieren,
Response-Schema unter `services/api/schemas/`, Tests unter `tests/api/`.

> Empfehlung: **A jetzt**, B erst, wenn die Contract-Zahl das rechtfertigt. Die
> Zeilenkomponente kapselt den Unterschied — ein späterer Umstieg auf B tauscht
> nur die Datenquelle, nicht das Rendering.

## Umsetzungsskizze (Option A)

1. **Kleines Wert-Rendering extrahieren.** Die Balken-/Schwellwertlogik aus
   `SlaBars` in ein wiederverwendbares `ui/`-Primitiv ziehen (z. B.
   `SlaWindowValue({ pct })` → gefärbter Prozentwert oder Mini-Balken), damit
   Workbench und Governance dieselbe Darstellung teilen. (Optional, aber vermeidet
   eine dritte Kopie der 99/95-Schwellen.)
2. **`SlaRow`-Komponente** in `Compliance.tsx` (oder daneben): nimmt `product`,
   ruft `useContractSla(product)`, rendert `<tr>` mit Produkt, `current` als
   `StatusPill` und drei `SlaWindowValue`.
3. **Panel** mit `t.governance.slaTitle`; Body = `Table` über `activeContracts`
   oder eine schlichte `<table>`; Leerzustand `t.governance.slaEmpty`.
4. **i18n** ist vollständig vorhanden — keine neuen Strings nötig
   (`slaTitle/slaProduct/slaCurrent/sla7d/sla30d/sla90d/slaEmpty`).
5. **Test** `src/tests/Governance.test.tsx` bzw. neue Datei: `useContractSla`
   mocken (wie in `ContractWorkbenchMode.test.tsx:56`), Zeilen + Prozentwerte +
   Leerzustand prüfen.

## Offene Fragen an den/die Umsetzer:in

1. **A oder B?** (Empfehlung: A.)
2. **Zeilen-Klick** — soll eine Zeile ins Objekt-/Contract-Detail führen, oder
   ist das Panel rein informativ? (Rest der Seite ist klickbar → konsistenterweise
   Sprung ins Objektdetail.)
3. **Nur aktiv** oder auch `deprecated`? (Titel sagt „aktive Contracts".)
4. **Sortierung** — nach Produktname (stabil) oder nach schlechtestem Fenster
   zuerst (setzt Verstöße nach oben, wie die KPI-Logik der Seite)?

## Referenzen

- Aktueller Seitencode: `apps/cockpit/src/pages/Compliance.tsx`
- Toter i18n-Block: `apps/cockpit/src/i18n/de.ts` → `governance.sla*`
- SLA-Mechanik: `docs/Tooldokumentation.md` (Compliance/SLA-Fenster)
