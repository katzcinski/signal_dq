# Implementation Batch 6 — Editor-Modus aus `kind` ableiten

**Adressat:** Entwicklung · **Stand:** 2026-06-19
**Grundlage:** `ADR-0006_Editor-Modus_aus_Kind.md` (Entscheidung R1–R4).
**Zweck:** Den frei togglebaren Lite/Full-Modus durch einen **kind-abgeleiteten Default mit asymmetrisch beschränktem Override** ersetzen, Einstiegspunkte vereinheitlichen und die Begriffe entkoppeln.

> Verwandt: `Betriebsmodi_Lite_und_Full.md` (wird in Schritt 6 nachgezogen) · `ADR-0001_Quality-Gates_vs_Contracts.md` §7 (Orthogonalität Lite/Full ↔ `kind`).

---

## 0 — Geltende Invarianten (NICHT verletzen)

- **Server bleibt autoritativ.** G1/G3 unverändert; alle vier `kind`×Modus-Kombinationen bleiben serverseitig gültig (`contracts.py`). Wir verengen nur die UI-Oberfläche.
- **`/certify` und `/approve` bleiben unverändert.** Keine Endpoint-Semantik wird angefasst — nur ein additives `certified`-Feld an `ContractOut`.
- **R2 ist eine UI-Leitplanke, kein Sicherheits-Gate.** Der Governance-Schutz lebt weiter serverseitig (G3, `contracts.py:705`).

---

## 1 — Backend: `certified`-Flag (additive)

**Datei:** `services/api/schemas/contract_schemas.py`
- `ContractOut`: Feld `certified: bool = False` ergänzen (nach `compliance`).

**Datei:** `services/api/routers/contracts.py`
- In `_contract_out(...)` den Snapshot prüfen und `certified=_active_snapshot_path(product).exists()` setzen.
- `_contract_out` erhält dazu Zugriff auf `product` (bereits vorhanden) — keine Signaturänderung nötig.
- **Bewusst nur am Einzel-GET** (`get_contract`). Die Listen-Route (`list_contracts`) baut `ContractOut` aus dem `contract_index` und bleibt unberührt (`certified` defaultet dort auf `False`); das genügt für die Toggle-Logik, die nur im Editor läuft.

*Aufwand:* 0,25 PT inkl. Test.

---

## 2 — Frontend-Typen & API-Spiegel

**Dateien:** `apps/cockpit/src/types/index.ts`, `apps/cockpit/openapi.json`, `apps/cockpit/src/api/schema.d.ts`
- `ContractOut` (TS): `certified?: boolean;` ergänzen.
- `openapi.json` + `schema.d.ts` regenerieren (bzw. das Feld manuell spiegeln, falls kein Codegen-Lauf vorgesehen ist).

*Aufwand:* 0,25 PT.

---

## 3 — Workbench: Default-Ableitung, Override-Schranke, tote UI (R1/R2)

**Datei:** `apps/cockpit/src/pages/ContractWorkbench.tsx`

3.1 **Default aus `kind` (R1).** In `ContractWorkbench` (Page) die Modus-Bestimmung ändern: statt `const lite = liteParam === '1'` einen aus `kind` abgeleiteten Default verwenden, den ein expliziter URL-Param übersteuert:
```
// Default folgt dem kind; ?lite / ?full ist ein expliziter Override.
const explicit = liteParam === '1' ? true : liteParam === '0' ? false : undefined;
const kindDefaultLite = contract?.kind === 'internal_gate' || !contract; // gate ⇒ Schnell
const lite = explicit ?? kindDefaultLite;
```
Da `contract` erst in `EditorPane` geladen wird, die Ableitung in `EditorPane` ziehen (wo `contract.kind` und `contract.certified` verfügbar sind) und den Modus dort als lokalen State mit kind-Default initialisieren; der Page-Param bleibt nur der Override-Kanal.

3.2 **Override-Schranke (R2).** Den „Schnell"-Toggle-Button nur rendern, wenn:
```
const lockedToFull = draft.kind !== 'internal_gate' && contract?.certified === true;
```
Bei `lockedToFull` den Toggle-Button (`ContractWorkbench.tsx:1116`) ausblenden und einen Modus-Wechsel nach Schnell ignorieren. Gates und noch-nicht-zertifizierte Contracts behalten den Toggle.

3.3 **Tote Governance-UI bei Gates.** `SlaBars` nur rendern, wenn `lifecycle === 'active' && draft.kind !== 'internal_gate'` (`ContractWorkbench.tsx:1114`). Der „Veralten"-Button bleibt — `deprecate` ist auf aktiven Gates funktional.

3.4 **Gate-Erklärung im Schnell-Modus (R aus §1.3 der ADR).** Im Lite-Branch (`ContractWorkbench.tsx:1069-1102`) bei `draft.kind === 'internal_gate'` eine Zeile mit `t.workbench.gateChangeHint` einblenden (heute nur im Full-`BreakingDiffPanel` sichtbar).

*Aufwand:* 1–1,5 PT inkl. Komponententest des Toggle-Renderings.

---

## 4 — Einstiegspunkte vereinheitlichen (R3)

**Datei:** `apps/cockpit/src/pages/ObjectDetail.tsx`
- `openChecksWorkbench` (`:368`): `&lite=1` entfernen → Ziel `/contracts?product=${id}` (Modus folgt dem `kind` des geladenen/geseedeten Contracts).

**Datei:** `apps/cockpit/src/pages/LineageMap.tsx`
- „Open contract" (`:283`) und „Compile" (`:289`): unverändert lassen (kein Modus-Param = Ableitung). Promote-Pfad (`:296`) bleibt — der neu erzeugte `consumer_contract` startet korrekt im Freigabe-Workflow.

*Aufwand:* 0,25 PT.

---

## 5 — Umbenennung (R4)

**Datei:** `apps/cockpit/src/i18n/de.ts`
- `workbench.liteMode`: `'Lite-Modus'` → `'Schnell zertifizieren'`
- `workbench.fullMode`: `'Voll-Modus'` → `'Freigabe-Workflow'`
- `workbench.liteHint` an die neue Benennung angleichen.
- `contracts.onboardingDesc` (`:99`) entkoppeln: „DQ-First" nicht mehr implizit mit dem Schnell-Modus gleichsetzen (DQ-First = Philosophie/`internal_gate`, nicht der Editor-Modus).

*Aufwand:* 0,25 PT. **Keine** Variablen-Umbenennung im Code (`lite`/`liteMode`-Keys bleiben), nur die Anzeigetexte — hält den Diff klein.

---

## 6 — Doku nachziehen

**Datei:** `docs/Betriebsmodi_Lite_und_Full.md`
- §0/§5/§6: ergänzen, dass der Modus-**Default** aus dem `kind` folgt und der Schnell-Override auf zertifizierten Contracts entfällt (R2). Die Lite/Full-Prozesse selbst bleiben gültig.

*Aufwand:* 0,25 PT.

---

## 7 — Tests

| Test | Ort | Inhalt |
|---|---|---|
| `certified`-Flag | `tests/api/test_lite_certify.py` (erweitern) | nach `/certify` liefert `GET /contracts/{p}` `certified=true`; vor erster Zertifizierung `false` |
| Snapshot-Erkennung | `tests/api/test_contract_lifecycle.py` (erweitern) | Draft-Amendment eines aktiven Contracts: `lifecycle=draft`, aber `certified=true` |
| Toggle-Rendering | `apps/cockpit/src/pages/__tests__` (neu/erweitern) | gate ⇒ Default Schnell + Toggle sichtbar; zertifizierter Contract ⇒ kein Schnell-Toggle; `?lite=0` übersteuert Default |
| SLA bei Gate | Komponententest | aktives `internal_gate` rendert keine `SlaBars` |

*Aufwand:* 0,75 PT.

---

## 8 — Sequenz & Aufwand

| Schritt | Inhalt | Aufwand | Abhängig von |
|---|---|---|---|
| 1 | BE `certified`-Flag | 0,25 PT | — |
| 2 | FE-Typen/Spiegel | 0,25 PT | 1 |
| 3 | Workbench R1/R2 + tote UI + Gate-Hint | 1–1,5 PT | 2 |
| 4 | Einstiegspunkte R3 | 0,25 PT | 3 |
| 5 | Umbenennung R4 | 0,25 PT | — (parallel) |
| 6 | Betriebsmodi-Doku | 0,25 PT | 3 |
| 7 | Tests | 0,75 PT | 1–4 |

**Summe:** ~3–3,5 PT. Schritt 5 ist unabhängig und kann parallel laufen.

---

## 9 — Bewusst NICHT in diesem Batch

- Keine Endpoint-Änderung an `/certify` oder `/approve`.
- Kein „zertifiziert"-Badge in der linken Contract-Liste (erst falls gewünscht → `certified` dann auch in `list_contracts` füllen).
- Keine Umbenennung der internen `lite`-Keys/Variablen — nur Anzeigetexte (R4) und Verhaltenslogik (R1–R3).
- Server-Fähigkeit „alle vier `kind`×Modus-Kombinationen" bleibt erhalten.
