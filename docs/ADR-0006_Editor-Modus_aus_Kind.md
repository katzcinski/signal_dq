# ADR-0006 — Editor-Modus (Lite/Full) aus dem Artifact-`kind` ableiten

**Adressat:** Beratung, Plattform-Team, Governance, Entwicklung · **Stand:** 2026-06-19
**Status:** *Angenommen* (accepted) — Umsetzung siehe `Implementation_Batch6_Mode_Kind_Defaulting.md`.

> **Hinweis zur Nummerierung (2026-07-23):** Diese ADR hieß ursprünglich „ADR-0002" und kollidierte mit `ADR-0002_Datasphere-DB-Zugriff.md`. Sie wurde auf **ADR-0006** umnummeriert; ältere Dokumente, die „ADR-0002" im Kontext Editor-Modus/Lite-Full zitieren, meinen diese ADR.
**Zweck:** Festhalten, wie der Editor-Modus der Contract Workbench (Lite vs. Full) und die Artifact-Klassifikation (`kind`) zueinander stehen — und die heute inkonsistente, frei togglebare Kopplung in eine klare Regel überführen.

> Verwandte Dokumente: `ADR-0001_Quality-Gates_vs_Contracts.md` (Trennung Gate/Contract via `kind`) · `Betriebsmodi_Lite_und_Full.md` (Lite/Full-Prozesse, wird durch diese ADR aktualisiert) · `Implementation_Batch5_Kind_Gated_Lifecycle_Ceremony.md` (kind-gegateter Lifecycle).

---

## 0 — Kernaussage

`kind` (`internal_gate` vs. `consumer_contract`/`provider_contract`) und der **Editor-Modus** (Lite vs. Full) sind **zwei orthogonale Achsen** — so bereits in ADR-0001 §7 festgehalten und vom Server gewollt: alle vier Kombinationen sind serverseitig implementiert.

- **`kind`** bestimmt das **Governance-Gewicht**: Zeremonie, Compliance-Ampel, SLA, ODCS-Export-Eignung. Gesetzt durch Seed/Promote, **nicht** durch den Editor.
- **Modus** bestimmt die **Zeremonie-Tiefe** beim Speichern: *Schnell zertifizieren* (`/certify`, ein Schritt) vs. *Freigabe-Workflow* (PUT-Draft → `/approve`).

Heute ist der Modus ein **freier Toggle** ohne Bezug zum `kind`. Folge: dasselbe Artefakt öffnet je Einstiegspunkt in unterschiedlichem Modus, und ein governter Contract lässt sich versehentlich an der Freigabe vorbei zertifizieren. Diese ADR ersetzt den freien Toggle durch eine **kind-abgeleitete Default-Regel mit kontrolliertem Override**.

---

## 1 — Kontext: Was Signal heute tut

Der Modus hängt allein am URL-Parameter `?lite=1` (`ContractWorkbench.tsx`). Konkrete Inkonsistenzen (Stand 2026-06-19):

1. **Modus je Einstiegspunkt verschieden** — dasselbe Contract öffnet unterschiedlich:
   - `ObjectDetail.tsx:368` hängt **immer** `&lite=1` an (auch für einen `consumer_contract`).
   - `LineageMap.tsx:283` „Open contract" → kein `lite` → Full.
   - `LineageMap.tsx:289` „Compile" → kein `lite` → Full.
   - Der Toggle selbst kippt frei, unabhängig vom `kind`.

2. **Governance-Bypass möglich** — der freie Toggle + „Speichern & aktivieren" lässt einen **fabrikneuen** `consumer_contract` direkt auf `active` zertifizieren und überspringt den Draft→Approve-Bestätigungsdialog. Der Server erlaubt das (G3 greift erst gegen eine **bereits zertifizierte** Version, `contracts.py:705-720`); auf der Erst-Aktivierung gibt es keine Gegenpartei, die geschützt werden müsste — aber die Zeremonie entfällt unbemerkt.

3. **Gate-Erklärung nur im Full-Modus** — die Texte `gateNoCeremony` / `breakingInfoGate` leben im `BreakingDiffPanel`; der Lite-Modus überspringt den Diff-Fetch (`ContractWorkbench.tsx:970`). Die Aussage „Gates ändern sich frei, Contracts brauchen Zeremonie" erscheint nie in dem Modus, den ein Gate natürlicherweise nutzt.

4. **Tote Governance-UI bei aktivem Gate im Full-Modus** — `SlaBars` rendert drei leere „keine Daten"-Balken (`contracts.py:782` liefert für `internal_gate` Null-Fenster).

5. **Begriffskollision** — das Onboarding koppelt „DQ-First" an das *`kind`* („läuft vollständig über Internal Gates", `de.ts:99`), während der Lite-*Toggle* umgangssprachlich ebenfalls „DQ-First" genannt wird. Drei Konzepte (DQ-First-Philosophie / Lite-UI / `internal_gate`-Kind) verschwimmen.

**Was bereits richtig ist:** Der Server unterstützt bewusst alle vier `kind`×Modus-Kombinationen. `/certify` arbeitet auf jedem `kind` (auch Contracts, `contracts.py:692-720`); der Full-`/approve`-Pfad arbeitet auch auf `internal_gate` (mit gate-spezifischer Diff-Copy). Diese Substanz bleibt **unangetastet** — wir verengen die UI-Oberfläche, nicht die Server-Fähigkeit.

---

## 2 — Entscheidung

**Der Modus wird aus dem `kind` *vorbelegt*, bleibt aber ein echter Override — asymmetrisch beschränkt auf der gefährlichen Richtung.** Vier Regeln:

### R1 — `kind` setzt den Default-Modus
- `internal_gate` → Default **Schnell zertifizieren**.
- `consumer_contract` / `provider_contract` → Default **Freigabe-Workflow**.

Der Modus bleibt ein sichtbarer Toggle; nur der **Startwert** folgt dem `kind`.

### R2 — Override asymmetrisch beschränkt (Governance-Schutz)
Der Schnell-Modus wird auf einem Contract **nur angeboten, solange keine zertifizierte Version existiert** (kein `.active.yml`-Snapshot). Die Erst-Aktivierung ist konsequenzfrei (noch keine Gegenpartei). **Nach** der ersten Zertifizierung wird der Schnell-Toggle ausgeblendet — jede weitere Änderung läuft über den Freigabe-Workflow. Gates behalten beide Modi jederzeit.

> Spiegelt die serverseitige G3-Logik (`contracts.py:705`) als UI-Leitplanke. G3 bleibt **serverautoritativ**; R2 ist eine zusätzliche FE-Sicherung, kein Ersatz.

### R3 — Einstiegspunkte wählen den Modus nicht mehr
Einstiegspunkte entfernen hartkodierte `lite=1`/Full-Vorgaben. Die Workbench leitet den Default aus dem `kind` ab; `?lite` / `?full` in der URL gilt nur noch als **expliziter Override**.

### R4 — Umbenennung weg von „Lite/Voll"
Die Labels werden zeremonie-basiert benannt — entkoppelt von „DQ-First" und vom `kind`:
- `Lite-Modus` → **„Schnell zertifizieren"**
- `Voll-Modus` → **„Freigabe-Workflow"**

---

## 3 — Wie das Frontend „bereits zertifiziert" erkennt

`lifecycle === 'draft'` ist **kein** verlässliches Signal für „noch nie zertifiziert": ein PUT auf einen aktiven Contract erzwingt `lifecycle = draft` (Draft-Amendment), während der `.active.yml`-Snapshot bestehen bleibt (`contracts.py:185-188`).

**Entscheidung:** Ein explizites Feld **`certified: bool`** an `ContractOut` (true, wenn `.active.yml` existiert). Es treibt R2 eindeutig. Alternativ ließe sich `version-diff.available` wiederverwenden — verworfen, weil das einen zweiten Fetch nur fürs Toggle-Rendering erzwingt. Das Feld wird zunächst nur am Einzel-GET (`GET /contracts/{product}`) geführt; die Liste (linke Spalte) braucht es erst, falls dort ein „zertifiziert"-Badge gewünscht wird.

---

## 4 — Konsequenzen

**Positiv**
- Eine Regel überall: dasselbe Artefakt öffnet konsistent, unabhängig vom Einstiegspunkt.
- Governance-Bypass geschlossen: ein einmal zertifizierter Contract lässt sich nicht mehr per Schnell-Modus an der Freigabe vorbei ändern.
- Ehrliche, kind-passende Oberfläche: Gate-Erklärung im Schnell-Modus, keine toten SLA-Balken bei Gates.
- Begriffe entwirrt: Modus (Zeremonie) ≠ `kind` (Grenze) ≠ DQ-First (Philosophie).

**Negativ / Risiken**
- Der schnelle Erst-Aktivierungspfad für Contracts bleibt erhalten, ist aber jetzt zeitlich begrenzt (vor erster Zertifizierung) — Anwender, die ihn gewohnt sind, müssen spätere Änderungen über die Freigabe führen. **Gegenmittel:** klare Toggle-Beschriftung + einmaliger Hinweis.
- `Betriebsmodi_Lite_und_Full.md` und die i18n-Copy müssen nachgezogen werden (siehe Implementierungsplan).

**Neutral**
- Server-Fähigkeit unverändert: alle vier `kind`×Modus-Kombinationen bleiben serverseitig gültig; nur die UI verengt die Oberfläche.
- G3 bleibt serverautoritativ; R2 ist reine UI-Leitplanke.

---

## 5 — Status & nächste Schritte

Umsetzung in `Implementation_Batch6_Mode_Kind_Defaulting.md`. Vor Abschluss zu prüfen:

1. Finale deutsche Labels für R4 bestätigen („Schnell zertifizieren" / „Freigabe-Workflow" vs. „Ohne Freigabe" / „Mit Freigabe").
2. Onboarding-Copy (`de.ts:99`) entkoppeln, sodass „DQ-First" nicht mehr mit dem Lite-Modus gleichgesetzt wird.
3. `Betriebsmodi_Lite_und_Full.md` §0/§5/§6 an die kind-abgeleitete Default-Regel angleichen.

> **Faustregel:** Der `kind` bestimmt, *ob* Zeremonie nötig ist; der Modus bestimmt nur, *wie viel* davon der Editor zeigt. Der Default folgt dem `kind`; der Override ist nur erlaubt, solange er keine Zusage aushebelt.
