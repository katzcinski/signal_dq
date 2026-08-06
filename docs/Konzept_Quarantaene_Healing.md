# Konzept — Quarantäne-Healing: Stewards heilen geparkte Zeilen in Signal

> ## ⚠ Historisch — abgelöst am 2026-08-03
>
> Dieses Proposal ist in
> [`Konzept_Manuelles_Healing.md`](Konzept_Manuelles_Healing.md) **aufgegangen**
> und wird nicht mehr nachgepflegt. Maßgeblich ist dort:
> §3 (Optionsraum H1–H5) · §4 (Umsetzungsstand) · **§5 (Abweichungen dieser
> Vorlage von der Umsetzung — samt offener Lücken)** · §6 (Mechanik als Bauplan:
> Opt-in-Leiter, Spalten-Allowlist, SQL-Guard).
>
> **Umgesetzt wurde die konservative Teilmenge** dieses Proposals: Korrektur je
> Zeile über ein Formular (kein Zeilen-Grid), episodenweiter Re-Check statt
> Per-Zeile-`clean`, `DQ_HEAL_LOG` statt `DQ_Q_AUDIT`, kein SQL-Healing.
> **Nicht** umgesetzt und weiterhin offen: eigener Kill-Switch
> `QUARANTINE_HEALING_ENABLED`, Contract-Policy mit Spalten-Allowlist,
> Per-Zeile-Zustände, optimistisches Locking → `OPEN_TASKS.md` **R5/R6**.
>
> Der Text unten bleibt als **Bauplan und Begründungsquelle** erhalten — die
> Guard-Regeln, die Allowlist-Matrix und das UI-Konzept sind die Vorlage für den
> Ausbau.

**Adressat:** Plattform-Team, Governance, Fachbereich · **Stand:** 2026-07-11
**Status:** historisch — abgelöst durch `Konzept_Manuelles_Healing.md`
**Zweck:** Festlegen, wie ein Steward quarantänisierte Zeilen **in Signal
selbst korrigiert** — per manueller Zellen-Bearbeitung im Grid oder per
SQL-Statement — bevor sie über die Release-View zurückfließen. Beides ist ein
**bewusstes Opt-in** (Kill-Switch + Contract-Policy); der bisherige Grundsatz
„Signal fasst Nutzdaten nie an" wird dafür kontrolliert, auditiert und nur
innerhalb der eigenen Custody-Zone gelockert.

> Verwandte Dokumente:
> `Konzept_Datasphere_Integration_Gating_Quarantaene.md` (§5.2 episodische
> Quarantäne, Release-View, TTL — **Voraussetzung: Slice ⑤**) ·
> `Konzept_Enforcement_Modi_Gate_Quarantine_Monitor.md` (Episoden-Lifecycle) ·
> `ADR-0002_Datasphere-DB-Zugriff.md` (+ Amendment: Schreiben nur im eigenen
> Schema) · `docs/interactive/enforcement-gating-quarantaene.html`.

---

## 0 — Kernaussage

Bisher endet Signals Quarantäne-Prozess bei „parken, freigeben, zurückreichen":
kaputte Zeilen warten in `DQ_Q_<OBJ>`, bis sie **upstream** repariert und neu
geladen werden. Das ist für viele Fehlerbilder der falsche Ort — ein fehlendes
Länderkürzel, ein verrutschtes Datumsformat, ein tippfehlerhafter Schlüssel
sind **in den geparkten Zeilen selbst** in Sekunden korrigierbar, während der
Upstream-Fix Tage dauert oder nie kommt (Altsystem, externer Lieferant).

**Healing** schließt diese Lücke:

> Der Steward korrigiert quarantänisierte Zeilen **direkt in Signals
> Quarantäne-Tabelle** — manuell im Grid oder per gescopetem SQL-Statement.
> Signal validiert die Korrektur **gegen dieselben Prädikate, die die Zeilen
> quarantänisiert haben**: erst wenn eine Zeile die verletzten Garantien
> besteht, ist sie `clean` und darf in die Release-View. Jede Änderung ist
> zellgenau auditiert und rückstellbar.

Drei Invarianten bleiben unverhandelbar:

1. **Custody-Grenze.** Geheilt wird ausschließlich in `DQ_Q_<OBJ>` im
   Signal-eigenen Open-SQL-Schema. Signal schreibt **nie** in Staging,
   Quellen oder Ziele des Kunden — die Rückführung geheilter Zeilen bleibt
   der Kunden-Flow über die Release-View (harte Grenze aus dem
   Integrations-Konzept §0, unverändert).
2. **Das Prädikat ist der Abnahmetest.** Es gibt keinen „ist jetzt gut"-Knopf.
   Eine editierte Zeile wird `clean`, wenn die `WHERE <bad>`-Prädikate der
   verletzten Garantien sie nicht mehr treffen — dieselbe Regel, die sie
   eingesperrt hat, lässt sie frei. Menschliches Urteil entscheidet *was*
   geändert wird, die Maschine entscheidet *ob es reicht*.
3. **Opt-in, auditiert, rückstellbar.** Default ist **aus** (globaler
   Kill-Switch + Policy je Contract). Jede Zelländerung und jedes Statement
   landet append-only im Audit (alt → neu, Akteur, Methode, Zeit); das
   Original ist jederzeit wiederherstellbar.

---

## 1 — Einordnung & Voraussetzungen

| Voraussetzung | Status |
|---|---|
| Episodische Quarantäne: physische Zeilen in `DQ_Q_<OBJ>` (Slice ⑤) | Konzept — **Healing setzt Slice ⑤ voraus** |
| Episoden-Lifecycle + Release-/Confirm-API (Slice ①) | ✅ implementiert (PR #98) |
| Materialisierungs-Infrastruktur, Schreib-Connection, Kill-Switch-Muster (Slice ③) | ✅ implementiert (PR #98) |
| Datenschutz-Review Custody-Zone (Spike O10) | offen — Healing **verschärft** O10 (siehe §7) |

**Nicht heilbar** ist die kontinuierliche Quarantäne (Split-Views, Slice ④):
dort existieren keine Kopien, die man editieren könnte — die Views filtern das
Original. Wer Healing will, konfiguriert `quarantine_style: episodic` (oder
`both`). Das Konzept macht Healing damit auch zum **Entscheidungsargument**
zwischen den beiden Quarantäne-Semantiken.

Der Lifecycle wird um einen Arbeitszustand erweitert:

```
open ──► reconciled ──► [ healing ]* ──► released ──► resolved
                          ▲     │
                          └─────┘  (iterativ: editieren → validieren)
```

`healing` ist **kein** neuer Episoden-Status (der Lifecycle bleibt stabil),
sondern ein **Zeilen-Zustandsmodell innerhalb** einer `reconciled`-Episode —
siehe §3. Die Episode selbst bleibt `reconciled`, bis der Steward freigibt.

---

## 2 — Die zwei Healing-Methoden

### 2.1 Manuelles Zeilen-Editieren (Grid)

Der Standardweg für kleine Mengen und Einzelfälle: der Steward öffnet die
**Healing-Workbench** (§6), sieht die geparkten Zeilen als editierbares Grid
und korrigiert Zellwerte inline. Merkmale:

- **Zellgenau:** jede Änderung ist ein Delta (Spalte, alt, neu) — kein
  Zeilen-Ersatz. Batch-Save fasst mehrere Zellen einer Sitzung zusammen.
- **Typ-geführt:** die Eingabe wird gegen den Inventar-/CSN-Typ der Spalte
  validiert (Datum bleibt Datum, Zahl bleibt Zahl) — Fehler werden vor dem
  Schreiben abgefangen, nicht erst vom HANA-Typfehler.
- **Spalten-Gating:** editierbar sind nur Spalten der Healing-Allowlist
  (§5.3); alle anderen sind sichtbar-gesperrt oder maskiert (PII, §7).
- **Verwerfen statt Löschen:** Zeilen, die nicht heilbar sind (Datenmüll,
  Dubletten), markiert der Steward als `discarded` mit Pflicht-Grund — sie
  verlassen die Release-Menge, bleiben aber bis zum TTL-Ablauf auditierbar
  erhalten. Physisches Löschen gibt es im Healing nicht.

### 2.2 SQL-Healing (gescopete Statements)

Der Weg für Massen-Korrekturen („alle 4 200 Zeilen mit `country IS NULL` auf
`'DE'`"): der Steward formuliert die Korrektur als SQL. **Aber:** freies SQL
gegen den Tenant ist genau das, was Signal nie zulässt. Deshalb schreibt der
Steward kein vollständiges Statement, sondern nur **SET- und WHERE-Klausel** —
Signal baut, prüft und scoped das Statement selbst:

```
Steward-Eingabe:            SET  "COUNTRY" = 'DE'
                            WHERE "COUNTRY" IS NULL AND "REGION" = 'EU'

Signal erzeugt & führt aus: UPDATE "<SIGNAL_SCHEMA>"."DQ_Q_<OBJ>"
                            SET   "COUNTRY" = 'DE',
                                  "_DQ_HEAL_STATE" = 'edited',
                                  "_DQ_EDITED_BY" = :actor,
                                  "_DQ_EDITED_AT" = CURRENT_UTCTIMESTAMP
                            WHERE ("COUNTRY" IS NULL AND "REGION" = 'EU')
                              AND "_DQ_EPISODE_ID" = :episode      -- erzwungen
                              AND "_DQ_HEAL_STATE" <> 'discarded'  -- erzwungen
```

**SQL-Guard** (frameworkfrei in `dq_core`, §5.2) — fail-closed:

| Regel | Begründung |
|---|---|
| Nur `SET`/`WHERE`-Fragmente, nie ein ganzes Statement | Verb, Zielobjekt und Scope bestimmt Signal — nicht der Nutzer |
| Genau **eine** Zieltabelle: die `DQ_Q_<OBJ>` der Episode | kein Join, kein Subselect auf Kundenschemata, kein Cross-Episode-Update |
| `SET` nur auf Spalten der Healing-Allowlist; `_DQ_*`-Systemspalten sind tabu | Schutzspalten (Zustand, Audit-Anker) bleiben Signals Hoheit |
| `WHERE` ist Pflicht; Episode-/Discard-Scope wird **angehängt**, nie ersetzt | kein versehentliches Voll-Update; Discards bleiben unangetastet |
| Verbotene Tokens: `;`, `--`, `/*`, DDL/DML-Verben, `SELECT` in `SET` | dieselbe Lint-Disziplin wie der G1-Contract-Linter, hier als Laufzeit-Gate |
| **Dry-Run zuerst:** `SELECT COUNT(*)` mit identischem Scope, Anzeige „trifft N Zeilen" — Ausführen erst nach Bestätigung | Massen-Wirkung sichtbar machen, bevor sie passiert |
| Statement + Treffer-Zahl + `statement_hash` wandern verbatim ins Audit | Reproduzierbarkeit; das Audit erzählt die ganze Heilungs-Geschichte |

SQL-Healing ist eine **eigene Berechtigungsstufe** (§5.1): mächtiger als
Zellen-Editieren, daher enger vergeben.

### 2.3 Was bewusst NICHT geht

- **Zeilen hinzufügen.** Healing repariert Vorhandenes; neue Zeilen entstehen
  nur upstream. (Sonst würde Signal zur Dateneingabe-Oberfläche.)
- **Schema ändern.** Spalten/Typen der Quarantäne-Tabelle sind vom Reconciler
  verwaltet.
- **Nach der Freigabe heilen.** `released`-Zeilen sind eingefroren — wer nach
  der Freigabe einen Fehler findet, stößt eine neue Episode an (der nächste
  Lauf quarantänisiert erneut). Kein stilles Umschreiben bereits
  zurückgereichter Daten.
- **Contract-Prädikate „weich stellen".** Wenn der Steward findet, dass die
  Garantie falsch ist, ändert er den **Contract** (G3-Pfad) — nicht die Daten.
  Die Workbench verlinkt dafür direkt in den Contract-Workbench.

---

## 3 — Zeilen-Zustandsmodell & Validierung

Jede geparkte Zeile trägt einen Heal-Zustand (`_DQ_HEAL_STATE`):

```
quarantined ──(Edit/SQL)──► edited ──(Validieren)──► clean
     ▲                        │  ▲                     │
     │                        │  └──(erneut editieren)─┤
     └──(Original wiederherstellen)◄──────────────────┘
     │
     └──(Verwerfen + Grund)──► discarded          (terminal je Zeile)
```

| Zustand | Bedeutung | In Release-View? |
|---|---|---|
| `quarantined` | unverändert geparkt | nur wenn Episode ohne Healing freigegeben wird (heutiges Verhalten) |
| `edited` | geändert, noch nicht validiert | **nie** |
| `clean` | Prädikat-Validierung bestanden | ✓ nach Freigabe |
| `discarded` | bewusst verworfen (Pflicht-Grund) | nie; TTL räumt ab |

**Validierung = Prädikat-Wiederholung.** „Validieren" führt die
`WHERE <bad>`-Prädikate der **verletzten Garantien der Episode** gegen die
Quarantäne-Tabelle aus — dieselben Fragmente, die der Compiler erzeugt hat
(`_diagnostic_sql`), nur mit gebundenem Ziel `DQ_Q_<OBJ>` statt des
Quellobjekts:

```sql
UPDATE "…"."DQ_Q_<OBJ>"
SET "_DQ_HEAL_STATE" = CASE WHEN ( <bad₁> OR <bad₂> … ) THEN 'edited' ELSE 'clean' END
WHERE "_DQ_EPISODE_ID" = :episode AND "_DQ_HEAL_STATE" IN ('edited','clean')
```

Konsequenzen dieser Konstruktion:

- **Kein zweites Regelwerk.** Es gibt keine „Healing-Regeln", die vom Contract
  divergieren könnten — G1 bleibt intakt, das SQL stammt weiter ausschließlich
  aus dem Compiler.
- **Grenzen ehrlich benennen:** `referential`-Prädikate brauchen den Parent —
  die Validierung liest dafür (read-only, wie jeder Check) das Parent-Objekt.
  `keys`-Duplikate werden **innerhalb der Quarantäne-Menge plus** gegen den
  aktuellen Quellbestand geprüft (sonst wäre ein „geheiltes" Duplikat beim
  Re-Import sofort wieder eins). Objekt-Garantien (`freshness`, `volume`,
  `schema`) sind nie zeilen-quarantänisiert und damit auch nie heilbar.
- **Ein `clean` ist eine Momentaufnahme.** Zwischen Validierung und Freigabe
  kann sich der Quellbestand ändern (Duplikat-Fall). Die Freigabe zeigt
  deshalb den Validierungs-Zeitstempel; optional (Policy) erzwingt sie eine
  frische Validierung, wenn er älter als N Minuten ist.

**Audit & Wiederherstellen.** Jede Änderung erzeugt append-only-Einträge:

```
DQ_Q_AUDIT (Signal-Schema, global für alle Quarantäne-Tabellen)
  AUDIT_ID · EPISODE_ID · ROW_ID (_DQ_ROW_ID) · COLUMN_NAME
  OLD_VALUE · NEW_VALUE (NVARCHAR-normalisiert)
  METHOD ('manual' | 'sql' | 'restore' | 'discard' | 'validate')
  STATEMENT_HASH (bei sql) · ACTOR · AT
```

„Original wiederherstellen" spielt die Audit-Kette einer Zeile rückwärts ab
(jede Wiederherstellung ist selbst ein Audit-Eintrag — die Geschichte wird
nie gelöscht, nur fortgeschrieben). Die Original-Werte sind damit ohne
Schattenkopie rekonstruierbar; der TTL-Purge der Episode räumt Audit-Zeilen
mit ab (Löschkonzept O10).

---

## 4 — Logik-Fluss Ende-zu-Ende

```
1  Lauf: verdict=quarantine ──► Episode open ──► Snapshot ──► reconciled (N Zeilen)
2  Steward öffnet Healing-Workbench (eigenes Fenster, §6)
3  Iterieren:  Grid-Edits / SQL-Statements  ──►  Zeilen 'edited'
4  Validieren: Prädikate laufen gegen DQ_Q  ──►  'clean' | zurück auf 'edited'
5  Nicht Heilbares verwerfen (Grund)        ──►  'discarded'
6  Freigabe (steward+, optional Vier-Augen) ──►  Episode released
      Release-View zeigt NUR 'clean'-Zeilen (+ 'quarantined', falls Healing
      für die Episode gar nicht genutzt wurde — Abwärtskompatibilität)
7  Kunden-Flow liest Release-View, lädt zurück, CALL P_DQ_CONFIRM_REPROCESS
8  Episode resolved(reprocessed) · Audit + Statements bleiben bis TTL
```

Schritt 4 und die Freigabe-Regel sind der Kern: **die Release-View wird durch
Healing strenger, nie laxer.** Ohne Healing gibt sie (wie bisher) die ganze
freigegebene Episode zurück; sobald in einer Episode geheilt wurde, gibt sie
ausschließlich validierte Zeilen zurück. Ein halb geheilter Zustand kann nie
versehentlich zurückfließen.

### API-Oberfläche (Service-Layer, RFC-7807, alle Aktionen als Episode-Events)

| Endpoint | Rolle | Zweck |
|---|---|---|
| `GET  /api/quarantine/{id}/rows?state=&check=&offset=&limit=` | steward+ ¹ | geparkte Zeilen, paginiert, Spalten PII-gefiltert (§7) |
| `PATCH /api/quarantine/{id}/rows` | steward+ ² | Batch von Zell-Deltas `[{row_id, column, value}]` → UPDATE + Audit |
| `POST /api/quarantine/{id}/rows/discard` | steward+ ² | `{row_ids, reason}` → `discarded` |
| `POST /api/quarantine/{id}/rows/restore` | steward+ ² | `{row_ids}` → Audit rückwärts, Zustand `quarantined` |
| `POST /api/quarantine/{id}/sql/preview` | owner+ ² ³ | SET/WHERE validieren, Dry-Run-Count zurück |
| `POST /api/quarantine/{id}/sql/execute` | owner+ ² ³ | gescopetes UPDATE ausführen, `{affected, statement}` |
| `POST /api/quarantine/{id}/validate` | steward+ ² | Prädikat-Lauf, Zustands-Zusammenfassung zurück |
| `GET  /api/quarantine/{id}/audit?row_id=` | steward+ | Audit-Trail (Zeile oder Episode) |

¹ Zeilen-Sicht = Rohdaten-Sicht → nie `viewer` (Defense-in-depth wie beim
Diagnostics-Pfad). ² Nur wenn Healing aktiv (Kill-Switch + Policy), sonst 409.
³ SQL-Stufe gemäß Policy (§5.1), Default `owner`+.

Alle Schreib-Endpoints prüfen den Episoden-Status: Healing nur in
`open`/`reconciled` — `released`/terminal ⇒ 409.

---

## 5 — Opt-in, Rollen & Konfiguration

### 5.1 Drei Schalter, aufsteigend

```
Stufe 0  QUARANTINE_HEALING_ENABLED=false            → Feature existiert nicht
         (globaler Kill-Switch, Setting, Default)      (keine Endpoints, kein UI)

Stufe 1  Contract-Policy  quarantine:                → Grid-Editing für diesen
           healing:                                     Contract, steward+
             mode: manual
             columns: [COUNTRY, DELIVERY_DATE, …]    → Allowlist editierbarer Spalten

Stufe 2      mode: manual+sql                        → zusätzlich SQL-Healing,
             sql_role: owner        # oder steward     Rolle konfigurierbar,
             four_eyes: true        # Default false     optional Vier-Augen-Freigabe
```

- **Kill-Switch** folgt exakt dem Muster von
  `ENFORCEMENT_MATERIALIZE_ENABLED`: global, env-getrieben, Default aus —
  ein Betriebsentscheid, kein UI-Toggle.
- **Policy lebt im Contract** (validator-geprüft, G1-gelintet — `columns`
  sind S2-Identifier). Damit ist pro Datenprodukt nachvollziehbar und
  versioniert, *ob* und *wie tief* geheilt werden darf; eine Policy-Änderung
  ist ein normaler Contract-Diff.
- **Vier-Augen** (`four_eyes: true`): Freigabe einer Episode mit Healing-
  Änderungen muss durch einen **anderen** Principal erfolgen als den, der
  editiert hat (Server prüft gegen die Audit-Akteure). Empfohlen als Default
  im Full-Modus, aus im Lite-Modus.

### 5.2 Wo die Logik lebt (Gates)

| Baustein | Ort | Gate |
|---|---|---|
| SQL-Guard (Fragment-Parser, Scope-Injektion, Token-Lint) | `packages/dq_core/enforce/heal_guard.py` | G7 frameworkfrei; reine Text→Text-Funktionen, golden-testbar |
| Prädikat-Rebinding (`<bad>` → Ziel `DQ_Q_<OBJ>`) | `dq_core/enforce` (nutzt Compiler-Fragmente) | G1: kein neues SQL-Regelwerk |
| Healing-Executor (UPDATE/Audit über Schreib-Connection) | `services/api/enforcement/healing.py` | Kill-Switch + Policy + Rolle, jede Aktion Episode-Event |
| Remote-Migration `002_healing.sql` (Systemspalten `_DQ_ROW_ID`, `_DQ_HEAL_STATE`, `_DQ_EDITED_BY/AT`, Tabelle `DQ_Q_AUDIT`, Discard-Grund) | `dq_core/enforce/remote_migrations/` | nummeriert, nie editieren |
| Release-View-Definition „nur clean" | Reconciler (Slice ④/⑤) | Registry + manifest_hash wie alle materialisierten Objekte |

### 5.3 Spalten-Allowlist — eine Liste, zwei Wirkungen

`healing.columns` steuert **Editierbarkeit**; die Sichtbarkeit im Grid steuert
die bestehende **Diagnostics-Allowlist** (G8). Beide zusammen:

| Spalte ist … | im Grid | editierbar |
|---|---|---|
| in Diagnostics- UND Healing-Allowlist | Klartext | ✓ |
| nur in Diagnostics-Allowlist | Klartext | gesperrt (Schloss-Icon) |
| nur in Healing-Allowlist | **Konflikt → Validator-Fehler** — editieren ohne sehen ist absurd und gefährlich | — |
| in keiner | maskiert (`•••`) | ✗ |
| Schlüsselspalten der Garantie (`keys`, FK) | Klartext (Identifikation nötig) — implizit zur Diagnostics-Menge | Default gesperrt, explizit freischaltbar |

---

## 6 — UI-Konzept: die Healing-Workbench (eigenes Fenster)

Healing ist **kein Drawer** an der Quarantäne-Liste — es ist konzentrierte
Arbeit an Daten. Die Workbench ist eine eigene, voll-breite Route
`/quarantine/:id/heal` (lazy Page, öffnet aus dem Episode-Drawer per Button
**„Heilen"**; optional `target="_blank"` als echtes Browser-Fenster für
Zwei-Monitor-Arbeit — die Route ist selbsttragend).

```
┌────────────────────────────────────────────────────────────────────────────┐
│ ← Quarantäne   DS_SALES_ORDERS · Episode #42 · Generation 3    [reconciled]│
│ Garantien: ⛔ A_not_null · ⛔ ref_COUNTRY_DIM_COUNTRY   Contract v1.4.0 ↗   │
│ ┌────────┬────────┬────────┬───────────┐                                   │
│ │ 4 180  │  312   │ 3 851  │    17     │   [ Validieren ▷ ]  [ SQL-Modus ] │
│ │geparkt │ edited │ clean  │ verworfen │   zuletzt validiert: vor 4 min    │
│ └────────┴────────┴────────┴───────────┘                                   │
├────────────────────────────────────────────────────────────────────────────┤
│ Filter: [Zustand ▾] [Garantie ▾] [Spalte durchsuchen…]        1–50 / 4 180 │
│ ┌─┬──────────┬───────────┬──────────┬───────────┬─────────────┬──────────┐ │
│ │▌│ ORDER_ID │ COUNTRY ✎ │ REGION 🔒│ AMOUNT ••• │ DELIV_DATE ✎│ Zustand  │ │
│ ├─┼──────────┼───────────┼──────────┼───────────┼─────────────┼──────────┤ │
│ │█│ 10041    │ ⟨NULL⟩ ✎  │ EU       │ •••       │ 2026-07-02  │ geparkt  │ │
│ │▓│ 10057    │ DE *      │ EU       │ •••       │ 2026-07-03  │ edited   │ │
│ │░│ 10063    │ DE        │ EU       │ •••       │ 2026-07-03  │ clean ✓  │ │
│ └─┴──────────┴───────────┴──────────┴───────────┴─────────────┴──────────┘ │
│  ▌Zustands-Stripe: rot geparkt · gelb edited · grün clean · grau verworfen │
│  [Auswahl verwerfen…] [Original wiederherstellen] [Änderungen speichern n] │
├────────────────────────────────────────────────────────────────────────────┤
│ ▸ Zeile 10057 — Audit: COUNTRY ⟨NULL⟩→'DE' · manual · t.mueller · 14:02    │
├────────────────────────────────────────────────────────────────────────────┤
│                       [ Freigeben (nur 3 851 clean) ]  Vier-Augen: b.weber │
└────────────────────────────────────────────────────────────────────────────┘
```

**Aufbau & Verhalten:**

- **Kopf = Kontext + Abnahmetest.** Objekt, Episode, Generation, Status-Pill;
  die **verletzten Garantien als Chips** — Klick zeigt das Prädikat
  (die „Prüfungsfrage", gegen die geheilt wird) und filtert das Grid auf die
  Zeilen, die genau diese Garantie verletzen. Link in den Contract-Workbench
  („Garantie falsch? → Contract ändern, nicht Daten").
- **Zähler-Leiste** (geparkt / edited / clean / verworfen) ist zugleich
  Filter; **Validieren** ist die prominenteste Aktion und aktualisiert die
  Zähler live (Operation-Progress-Kanal, wie Läufe).
- **Grid:** Zustands-Stripe links je Zeile; editierbare Spalten mit ✎,
  gesperrte mit 🔒, maskierte mit `•••` (Tooltip nennt den Grund: PII-Gate
  bzw. Policy). Inline-Edit typ-geführt (Datepicker für Datum, numerisches
  Feld für Zahlen); geänderte Zellen bis zum Speichern mit `*` und
  Dirty-Rahmen. Ursprungswert per Hover sichtbar. Batch-Save
  („Änderungen speichern (n)"), Mehrfachauswahl für Verwerfen/Wiederherstellen.
  Pagination serverseitig (Episoden können groß sein) — Sortierung/Filter
  ebenfalls.
- **SQL-Modus** (Tab, nur sichtbar bei `mode: manual+sql` und passender
  Rolle): zweigeteilt — links Editor mit festem Rahmen
  (`UPDATE DQ_Q_DS_SALES_ORDERS` vorgegeben und nicht editierbar, darunter
  freie `SET`-/`WHERE`-Felder), rechts **Vorschau-Pflicht**: „trifft 4 180
  Zeilen" + Beispiel-Zeilen (5, PII-gefiltert). Ausführen erst nach Vorschau;
  darunter die **Statement-Historie** der Episode (verbatim, Akteur, Treffer,
  wiederholbar). Fehlversuche des Guards zeigen die verletzte Regel im
  Klartext („SET auf REGION ist nicht in der Healing-Allowlist").
- **Audit-Leiste** (aufklappbar, unten): Timeline der Episode inkl. aller
  Healing-Events; je Zeile per Klick der zellgenaue Trail.
- **Freigabe-Fuß:** der Release-Button trägt die Wahrheit im Label —
  „Freigeben (nur 3 851 clean)". Bei `four_eyes` zeigt er, wer freigeben darf
  (nicht der Editierende); bei veralteter Validierung fordert er erst
  „Erneut validieren". Rollen ohne Schreibrecht sehen die gesamte Workbench
  read-only mit `ReadOnlyBanner` (FE spiegelt, Server entscheidet).
- **i18n:** alle Labels in `de.ts` (`healing.*`): „Heilen", „Validieren",
  „Verwerfen", „Original wiederherstellen", „Änderungen speichern",
  „Freigeben (nur n bereinigt)", Zustands-Labels „geparkt / bearbeitet /
  bereinigt / verworfen".

---

## 7 — Sicherheit, PII & Gates

| Gate/Prinzip | Wirkung dieses Konzepts |
|---|---|
| **G1** | unverändert: Contracts bleiben SQL-frei. Steward-SQL ist **operatives Handeln**, nie Contract-Inhalt; es wird nie persistiert außer im Audit, nie kompiliert, nie wiederverwendet als Regel. Der Fragment-Guard nutzt dieselbe Token-Lint-Disziplin wie der G1-Linter. |
| **G2** | Tabellen-/Schema-Namen ausschließlich zur Laufzeit gebunden (`{signal_schema}`, Episode → Tabellenname aus der Registry); Nutzereingaben können das Ziel nicht wählen. |
| **G6** | Heal-Zustände sind explizit und vollständig (`quarantined/edited/clean/discarded`); die Validierung setzt Zustände immer beidseitig (auch zurück auf `edited`), nie stilles Auslassen. |
| **G7** | Guard + Prädikat-Rebinding frameworkfrei in `dq_core/enforce`; Ausführung/AuthZ in `services/`. |
| **G8** | Rohzeilen verlassen HANA weiterhin nur über gegatete Pfade: das Grid IST ein Rohzeilen-Pfad → nie `viewer`, Spalten-Maskierung nach Diagnostics-Allowlist, Sample-Vorschau im SQL-Dry-Run gleich gefiltert. **Neu und ehrlich benannt:** Healing zeigt und ändert Nutzdaten — der O10-Datenschutz-Review muss Healing explizit mit abdecken (Zweckbindung, Rollenkonzept, Audit-Aufbewahrung = Episoden-TTL). |
| **ADR-0002-Amendment** | unverändert tragfähig: alle Writes bleiben im Signal-Schema. Healing erweitert *was* dort geschrieben wird (Nutzdaten-Zellen statt nur Metadaten) — deshalb der eigene Kill-Switch zusätzlich zum Materialisierungs-Switch. |
| **Auditierbarkeit** | append-only, zellgenau, Statements verbatim; Vier-Augen optional erzwungen; jede Aktion zusätzlich als Episode-Event (Timeline) und Operation (ADR-0005-Kanal) sichtbar. |
| **Nebenläufigkeit** | optimistisches Locking je Zeile (`_DQ_EDITED_AT` als Version): kollidierende Edits zweier Stewards ⇒ 409 mit aktuellem Wert, kein Last-Writer-Wins im Stillen. |

---

## 8 — Implementierungs-Slice

**Layer 1 — `dq_core/enforce` (frameworkfrei)**
`heal_guard.py`: `parse_fragments(set_clause, where_clause, allowlist) → GuardedUpdate`
(Fehler mit Regel-Referenz); `rebind_predicates(checks, table) → Validierungs-SQL`;
Remote-Migration `002_healing.sql`. Golden-Tests: Guard-Matrix (jede Regel je
ein Positiv-/Negativ-Fall), Rebinding je Garantie-Familie, Determinismus.

**Layer 2 — Store**
Migration `017_healing.sql`: Episode-Zähler (`rows_edited`, `rows_clean`,
`rows_discarded`), `validated_at`; Events erweitert um Healing-Aktionen.

**Layer 3 — Services**
`enforcement/healing.py`: Row-Reader (paginiert, PII-Projektion), Batch-Update
+ Audit, Discard/Restore, SQL-Preview/Execute (Guard → Dry-Run → Execute),
Validate (Rebinding → UPDATE → Zähler). Settings:
`QUARANTINE_HEALING_ENABLED` (Default `false`). Policy-Parsing im Validator
(`quarantine.healing`-Block, S2-Identifier, Konflikt-Regel §5.3).

**Layer 4 — API**
Router-Erweiterung `routers/quarantine.py` (§4-Tabelle), 409-Semantik
(Feature aus / falscher Episoden-Status / Lock-Konflikt / Vier-Augen),
RFC-7807. `tests/api`: Rollenmatrix, Guard-Ablehnungen, Validieren-Zyklus,
Vier-Augen, Lock-Konflikt.

**Layer 5 — Frontend**
`pages/QuarantineHealing.tsx` (lazy, Route `/quarantine/:id/heal`), Grid mit
Inline-Edit + Zustands-Stripes, SQL-Tab, Audit-Leiste, Freigabe-Fuß;
`api/quarantineHealing.ts`; `de.ts`-Block `healing`; vitest (Edit-Flow,
Maskierung, Read-only-Spiegel, Freigabe-Label).

**Reihenfolge:** nach Slice ⑤ (physische Tabellen — ohne sie gibt es nichts
zu heilen) und **nach erweitertem O10-Review**. Innerhalb: Guard + Migration →
Row-API + Grid → Validieren → SQL-Modus → Vier-Augen.

## 9 — Offene Punkte

| # | Punkt | Behandlung |
|---|---|---|
| H1 | `keys`-Validierung gegen den lebenden Quellbestand: Kosten & Semantik (Snapshot vs. live) | Spike mit O7 kombinieren |
| H2 | Maximale Episoden-Größe fürs Grid; ab wann SQL-only empfehlen (z. B. > 50 k Zeilen) | im UI als Hinweis, Grenze als Setting |
| H3 | Audit-Aufbewahrung nach `resolved` — mit TTL purgen oder länger (Compliance)? | Teil des O10-Reviews |
| H4 | „Heilungs-Vorschläge": Signal schlägt SET/WHERE aus Fehlermuster vor (Proposal-Miner-Analogie, L2 der Self-Healing-Leiter) | bewusst v2 — erst manuelle Mechanik härten |
| H5 | Browser-Fenster-Variante: Session-/Auth-Verhalten von `target="_blank"` im OIDC-Modus | beim FE-Bau verifizieren |
