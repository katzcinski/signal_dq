# Konzept — Manuelles Healing: Datenkorrektur in Signals Custody-Zone

**Stand:** 2026-08-03 · **Status:** **H1 + H3 umgesetzt** (Healing-Workbench
`/healing`, API `/api/healing`, Migrationen store-019 / remote-003);
H2/H4/H5 und die Rest-Mechanik zu evaluieren → [`OPEN_TASKS.md`](OPEN_TASKS.md)
Abschnitt **R**.

> **Konsolidierung (2026-08-03).** Dieses Dokument ist die **maßgebliche**
> Healing-Referenz. Es führt zwei zuvor getrennte Stränge zusammen:
> das Proposal [`Konzept_Quarantaene_Healing.md`](Konzept_Quarantaene_Healing.md)
> (2026-07-11 — Zeilen-Grid, SQL-Healing, Opt-in-Leiter; jetzt **historisch**)
> und die Optionsbewertung H1–H5 vom 2026-08-03. Wo die Umsetzung vom Proposal
> abweicht, steht das in **§5** — samt Begründung und offener Lücke.

**Verwandte Dokumente:** [`ADR-0002`](ADR-0002_Datasphere-DB-Zugriff.md)
(+ Amendment: Schreiben nur im eigenen Schema) ·
[`O10_Datenschutz_Review_Custody_Zone.md`](O10_Datenschutz_Review_Custody_Zone.md) ·
[`Konzept_Datasphere_Integration_Gating_Quarantaene.md`](Konzept_Datasphere_Integration_Gating_Quarantaene.md)
(§5.2 episodische Quarantäne — Voraussetzung) ·
[`Datenfluesse_Quelle_vs_Signal.md`](Datenfluesse_Quelle_vs_Signal.md).

---

## 0 / Kernaussage

Signals Quarantäne-Prozess endete ursprünglich bei „parken, freigeben,
zurückreichen": kaputte Zeilen warten in `DQ_Q_<OBJ>`, bis sie **upstream**
repariert und neu geladen werden. Für viele Fehlerbilder ist das der falsche
Ort — ein fehlendes Länderkürzel, ein verrutschtes Datumsformat, ein
tippfehlerhafter Schlüssel sind in den geparkten Zeilen selbst in Sekunden
korrigierbar, während der Upstream-Fix Tage dauert oder nie kommt (Altsystem,
externer Lieferant).

**Healing** schließt diese Lücke — mit drei unverhandelbaren Invarianten:

1. **Custody-Grenze.** Geheilt wird ausschließlich im Signal-eigenen
   Open-SQL-Schema: `DQ_Q_<OBJ>` (H1) bzw. `DQ_PATCH_<OBJ>` (H3). Signal
   schreibt **nie** in Quellen, Staging oder Ziele des Kunden; die Rückführung
   bleibt der Kunden-Flow über die Release- bzw. Healed-View.
2. **Das Prädikat ist der Abnahmetest.** Es gibt keinen „ist jetzt gut"-Knopf.
   Eine korrigierte Zeile ist freigabefähig, wenn die `WHERE <bad>`-Prädikate
   der verletzten Garantien sie nicht mehr treffen — dieselbe Regel, die sie
   eingesperrt hat, lässt sie frei. Menschliches Urteil entscheidet *was*
   geändert wird, die Maschine entscheidet *ob es reicht*.
3. **Auditiert und rückstellbar.** Jede Änderung landet append-only im Audit
   (Vorher → Nachher, Akteur, Zeit, Grund); der Ursprungswert bleibt
   rekonstruierbar.

---

## 1 / Begriffsrahmen — drei Healing-Achsen

Eine Incident-Triage sollte immer benennen können, **welche** Achse heilt —
sonst wird an Daten „geflickt", was eigentlich ein Regel- oder Quellproblem ist.

1. **Daten-Healing** — der Wert ist falsch, jemand korrigiert ihn (H1, H3, H4).
2. **Prozess-Healing** — die Daten kommen erneut richtig; es geht um
   Wiederanlauf und Freigabe (**vorhanden**: Episoden-Lifecycle, Re-Run).
3. **Regel-Healing** — die Daten waren richtig, die Erwartung falsch
   (**vorhanden**: Proposals + Backtesting; H5 macht es zum expliziten
   Triage-Ausgang).

---

## 2 / Leitplanken

- **Quelle bleibt read-only** (ADR-0002). Schreibfläche ist ausschließlich das
  Signal-Schema.
- **Heal → Re-Check → Release.** Jede Korrektur läuft vor der Freigabe erneut
  durch die kompilierten Checks derselben Contract-Version (deterministisch,
  G1). Es gibt keinen Pfad, der korrigierte Zeilen am Gate vorbei freigibt.
- **G8 bleibt scharf.** Rohzeilen verlassen HANA nicht ohne Opt-in. Die heutige
  Workbench zeigt **keine** Zeileninhalte; ein Zeilen-Grid stünde hinter
  demselben Gate wie Diagnostics (per-Objekt-Opt-in + Spalten-Allowlist).
- **Lückenlose Audit-Spur.** Wer, wann, was, warum — als Systemspalten und
  Log-Zeilen, nicht als Konvention. Bei Contract-Kinds zusätzlich Vier-Augen
  (Korrigierender ≠ Freigebender).
- **Episoden-/Generationsbindung.** Korrekturen hängen an Episode × Generation;
  ein neuer Lauf ersetzt (`superseded`) — keine Korrektur „überlebt"
  unkontrolliert in eine neue Episode.
- **Nicht heilbar ist die kontinuierliche Quarantäne** (Split-Views, Slice ④):
  dort existieren keine Kopien, die man editieren könnte. Wer H1 will,
  konfiguriert `quarantine.style: episodic` (oder `both`).

---

## 3 / Optionsraum

### H1 — Korrektur in der Quarantäne-Parkbucht · **umgesetzt**

Geparkte Bad-Rows werden in `DQ_Q_<OBJ>` korrigiert und über den bestehenden
Episoden-Lifecycle freigegeben. Wirkt **episodisch** — bei replizierenden Loads
bringt der nächste Extract den Fehler wieder (dann H3 oder Fix-at-Source).

### H2 — Fix-at-Source-Workflow · **Default-Haltung, nicht gebaut**

Der fachlich sauberste Weg: der Fehler wird im Quellsystem behoben, Signal
orchestriert nur — Incident → Owner → Korrektur → Re-Extract/Re-Run als
Verifikation → Auto-Resolve. Alle Bausteine existieren; es fehlt der **geführte
Flow** (Incident-Aktion „An Quelle beheben" mit Verifikations-Run). ~1–2 PT.

### H3 — Korrektur-Overlay (Patch-Tabelle) · **umgesetzt**

Steward-/Owner-Overrides, die **Reloads überleben**: `DQ_PATCH_<OBJ>` im
Signal-Schema, Konsumenten lesen `V_DQ_HEALED_<OBJ>` = Quelle `LEFT JOIN` Patch
(`COALESCE` je Spalte). Richtig für wiederkehrende, bekannte Quellfehler, deren
Behebung an der Quelle dauert. Dieselbe View-Adoptions-Frage wie `DQ_CLEAN`:
Konsumenten müssen auf die View zeigen.

### H4 — Geführter Reprocess · **nachgelagert**

Korrigierte Zeilen per `INSERT … SELECT` in den Ziel-Flow zurückführen
(Task-Chain-Vorlage, Slice ⑦); gibt dem vorhandenen `confirm-reprocess`-Übergang
seinen technischen Unterbau. Hängt an Slice ⑦ + Live-Spikes O5/O6.

### H5 — Regel-Healing als Triage-Ausgang · **kein Neubau nötig**

Proposals + Backtesting existieren. Fehlend ist die Verdrahtung: im
Incident-Drawer der Ausgang „False Positive → Schwelle prüfen" (Deep-Link in
Workbench/Backtest, Resolve-Kategorie `false_positive`). Liefert nebenbei die
False-Positive-Quote je Garantie als Kalibrier-Feedback. <1 PT.

### Bewertung

| Option | Quelle bleibt wahr? | Überlebt Reload | Audit | G8-Belastung | Aufwand | Stand |
|---|---|---|---|---|---|---|
| H1 Parkbucht | ja (Signal-Schema) | ✗ episodisch | Prozedur + Store | keine (Korrektur in HANA) | ~3–4 PT | ✅ |
| H2 Fix-at-Source | ja (Quelle korrigiert) | ✓ | Quellsystem + Incident | keine | ~1–2 PT | ◻ |
| H3 Patch-Overlay | ja (Overlay) | ✓ | Patch-Tabelle, pro Feld | keine | ~4–6 PT | ✅ |
| H4 Reprocess | ja | ✓ | Episode-Events | keine | mit Slice ⑦ | ◻ |
| H5 Regel-Ausgang | ja | ✓ | Incident/Proposal | keine | <1 PT | ◻ |

---

## 4 / Umsetzungsstand (2026-08)

| Baustein | Umsetzung |
|---|---|
| H1 Korrektur | `dq_core/enforce/healing.py` — `correction_statement`, Schattenspalte `_DQ_ORIGINAL` (JSON je Spalte), Stempel `_DQ_CORRECTED_BY/_AT/_REASON`, Heal-Zustand |
| H1 Prozedur-Tür | `P_DQ_CORRECT_ROW` (SECURITY DEFINER) im Soll-Zustand — Korrektur **ohne** UPDATE-Grant auf `DQ_Q_*`; zwei Guards: Registry-Lookup (`DQ_OBJECTS`, nur aktive `DQ_Q_*`) und Katalog-Prüfung (`SYS.TABLE_COLUMNS`, keine `_DQ_*`-Systemspalten) |
| H1 Audit | `DQ_HEAL_LOG` (remote-003, append-only, `SOURCE = api \| procedure`) + `dq_healing_corrections` im Result-Store |
| H1 Re-Check | `recheck_statement` — `COUNT(*)` der Episode-Zeilen, die das Bad-Prädikat weiterhin erfüllen |
| Heal→Re-Check→Release | Freigabe-Guard in `routers/quarantine.py`: offene Verstöße blocken die Freigabe (409), **sobald** an der Episode korrigiert wurde |
| Vier-Augen | Contract-Kinds: Korrigierender ≠ Freigebender (409); `internal_gate` bleibt frei |
| H3 Overlay | `PatchSpec`, `patch_table_ddl`, `healed_view_ddl` (LEFT JOIN + `COALESCE`, Gültigkeitsfenster), Patch-CRUD im Store (store-019), Ersetzen/Rücknahme als Audit |
| API | `/api/healing` — `overview`, `episodes/{id}`, `corrections`, `recheck`, `patches`, `patches/{id}/revoke`, `plan`; Korrektur `steward+`, Patch `owner+` |
| Oberfläche | Healing-Workbench `/healing` (Tab H1 Episoden, Tab H3 Patches), rollen-gespiegelt |

**Architektur-Entscheid:** Der Result-Store ist die Wahrheit, die
HANA-Materialisierung ist opt-in (`ENFORCEMENT_MATERIALIZE_ENABLED`) und wird je
Eintrag über `applied` ausgewiesen — ein nicht projizierter Eintrag ist sichtbar,
nicht stillschweigend verschwunden (G6).

**Verifikation offen (🧪):** Der `hdbcli`-Pfad ist lokal nicht ausführbar —
`P_DQ_CORRECT_ROW`, Re-Check und Healed-View gehören in dieselben Live-Spikes
wie die übrige Materialisierung (O5/O6).

---

## 5 / Abweichungen vom Proposal 2026-07 — und was daraus folgt

Das Proposal beschrieb eine **reichere** H1-Mechanik als das, was gebaut wurde.
Die Unterschiede sind hier vollständig aufgeführt: teils bewusste Vereinfachung,
teils **echte offene Lücke**.

| Thema | Proposal 2026-07 | Umsetzung 2026-08 | Bewertung |
|---|---|---|---|
| **Eigener Kill-Switch** | `QUARANTINE_HEALING_ENABLED`, Default aus — Healing existiert sonst nicht | fehlt; es greifen nur Materialisierungs-Switch + Rollen-Gates | **Lücke** → R5. Healing schreibt Nutzdaten und verdient den eigenen Betriebsschalter |
| **Spalten-Allowlist** | Contract-Policy `quarantine.healing.columns`; „editieren ohne sehen" ist Validator-Fehler | fehlt; korrigierbar ist jede Nicht-Systemspalte des Objekts | **Lücke** → R5. Governance-relevant: heute entscheidet allein die Rolle, nicht der Contract |
| **Zeilen-Zustände** | `quarantined / edited / clean / discarded` — je Zeile | `quarantined / corrected / released` — kein `clean` je Zeile, kein `discarded` | bewusst vereinfacht: Freigabereife wird **episodenweit** über den Re-Check-Zähler entschieden. Verwerfen einzelner Zeilen fehlt → R6 |
| **Validierung** | `UPDATE … SET state = CASE WHEN <bad> THEN 'edited' ELSE 'clean' END` je Zeile | `COUNT(*) WHERE <bad>` je Episode | gröber, aber gleiche Semantik an der Freigabe. Per-Zeile-Freigabe („nur die guten zurück") ist damit **nicht** möglich → R6 |
| **Original-Wiederherstellung** | Replay der Audit-Kette, keine Schattenkopie | `_DQ_ORIGINAL` als JSON-Schattenspalte (erster Vorher-Wert je Spalte) | bewusst: einfacher und ohne Replay-Logik. Restore-Aktion selbst fehlt → R6 |
| **Audit-Tabelle** | `DQ_Q_AUDIT` zellgenau mit `METHOD`, `STATEMENT_HASH` | `DQ_HEAL_LOG` mit `SOURCE`; kein Statement-Hash (kein SQL-Modus) | konsistent zum reduzierten Funktionsumfang |
| **SQL-Healing** | SET/WHERE-Fragmente + Guard + Dry-Run für Massenkorrekturen | nicht gebaut | bewusst nachgelagert → R6. Der Guard-Entwurf des Proposals bleibt die Vorlage |
| **Zeilen-Grid** | editierbares Grid mit PII-Maskierung | Formular ohne Zeileninhalte | bewusst **G8-konservativer**: kein neuer Rohzeilen-Pfad ins Cockpit |
| **Vier-Augen** | Contract-Policy `four_eyes`, Default aus | immer aktiv für Contract-Kinds, nie für `internal_gate` | strenger als das Proposal, dafür ohne Schalter → R5 (Konfigurierbarkeit prüfen) |
| **Nebenläufigkeit** | optimistisches Locking je Zeile (409 statt Last-Writer-Wins) | nicht gebaut | **Lücke** → R6, relevant sobald mehrere Stewards gleichzeitig arbeiten |

**Kurzfassung für den Governance-Termin:** Was gebaut wurde, ist die
*konservative Teilmenge* des Proposals — weniger Fläche, dieselben Invarianten.
Die zwei Punkte, die vor einem produktiven Einsatz nachzuziehen sind, sind der
**eigene Kill-Switch** und die **Spalten-Allowlist im Contract** (R5).

---

## 6 / Mechanik im Detail (Vorlage für den Ausbau)

Dieser Abschnitt bewahrt die Substanz des Proposals als Bauplan für R5/R6.

### 6.1 Opt-in-Leiter (Zielbild)

```
Stufe 0  QUARANTINE_HEALING_ENABLED=false   → Feature existiert nicht
         (globaler Kill-Switch, Default)      (keine Endpoints, kein UI)

Stufe 1  Contract-Policy quarantine.healing: → Korrektur für diesen Contract
           mode: manual                        steward+
           columns: [COUNTRY, DELIVERY_DATE]  → Allowlist korrigierbarer Spalten

Stufe 2    mode: manual+sql                   → zusätzlich SQL-Healing,
           sql_role: owner                      Rolle konfigurierbar,
           four_eyes: true                      Vier-Augen erzwingbar
```

Der Kill-Switch folgt dem Muster von `ENFORCEMENT_MATERIALIZE_ENABLED`:
global, env-getrieben, Default aus — ein Betriebsentscheid, kein UI-Toggle.
Die Policy lebt **im Contract** (validator-geprüft, `columns` als
S2-Identifier): damit ist pro Datenprodukt versioniert nachvollziehbar, *ob*
und *wie tief* geheilt werden darf; eine Policy-Änderung ist ein Contract-Diff.

### 6.2 Spalten-Allowlist — eine Liste, zwei Wirkungen

`healing.columns` steuert **Korrigierbarkeit**, die bestehende
Diagnostics-Allowlist (G8) die **Sichtbarkeit**:

| Spalte ist … | sichtbar | korrigierbar |
|---|---|---|
| in Diagnostics- **und** Healing-Allowlist | Klartext | ✓ |
| nur in Diagnostics-Allowlist | Klartext | gesperrt |
| nur in Healing-Allowlist | **Validator-Fehler** — korrigieren ohne sehen ist unzulässig | — |
| in keiner | maskiert | ✗ |
| Schlüsselspalten der Garantie | Klartext (Identifikation nötig) | Default gesperrt, explizit freischaltbar |

### 6.3 SQL-Healing — Guard-Regeln (fail-closed)

Der Steward schreibt **kein** vollständiges Statement, sondern nur SET- und
WHERE-Fragment; Verb, Zielobjekt und Scope bestimmt Signal:

| Regel | Begründung |
|---|---|
| Nur `SET`/`WHERE`-Fragmente | Ziel und Scope gehören Signal, nicht dem Nutzer |
| Genau **eine** Zieltabelle: `DQ_Q_<OBJ>` der Episode | kein Join, kein Subselect auf Kundenschemata |
| `SET` nur auf Allowlist-Spalten; `_DQ_*` tabu | Schutzspalten bleiben Signals Hoheit |
| `WHERE` ist Pflicht; Episoden-Scope wird **angehängt**, nie ersetzt | kein versehentliches Voll-Update |
| Verbotene Tokens: `;`, `--`, `/*`, DDL/DML-Verben, `SELECT` in `SET` | dieselbe Lint-Disziplin wie der G1-Linter, hier als Laufzeit-Gate |
| **Dry-Run zuerst** („trifft N Zeilen"), Ausführen erst nach Bestätigung | Massenwirkung sichtbar machen, bevor sie passiert |
| Statement + Trefferzahl + Hash verbatim ins Audit | Reproduzierbarkeit |

### 6.4 Was bewusst NICHT geht

- **Zeilen hinzufügen** — Healing repariert Vorhandenes; neue Zeilen entstehen
  upstream. Sonst würde Signal zur Dateneingabe-Oberfläche.
- **Schema ändern** — Spalten/Typen der Quarantäne-Tabelle verwaltet der
  Reconciler.
- **Nach der Freigabe heilen** — freigegebene Zeilen sind eingefroren; ein
  später gefundener Fehler erzeugt eine neue Episode.
- **Contract-Prädikate „weich stellen"** — wenn die Garantie falsch ist, ändert
  man den **Contract** (G3-Pfad), nicht die Daten. Das ist H5.

---

## 7 / Sicherheit, PII & Gates

| Gate | Wirkung |
|---|---|
| **G1** | unverändert: Contracts bleiben SQL-frei. Steward-Korrekturen sind **operatives Handeln**, nie Contract-Inhalt — nie kompiliert, nie als Regel wiederverwendet. |
| **G2** | Schema- und Tabellennamen ausschließlich zur Laufzeit gebunden (`{signal_schema}`); Nutzereingaben können das Ziel nicht wählen. Spaltennamen durchlaufen die Identifier-Allowlist (S2). |
| **G6** | Heal-Zustände sind explizit; `applied=0` weist eine nicht materialisierte Korrektur aus, statt sie zu verschweigen. |
| **G7** | SQL-Erzeugung frameworkfrei in `dq_core/enforce/healing.py`; Ausführung und AuthZ in `services/`. |
| **G8** | Die Workbench zeigt **keine** Rohzeilen — der Nutzer benennt Zeilenschlüssel und Zielwert. Ein Zeilen-Grid wäre ein neuer Rohzeilen-Pfad und bräuchte Diagnostics-Gating + Maskierung. |
| **ADR-0002-Amendment** | tragfähig: alle Writes bleiben im Signal-Schema. Healing erweitert *was* dort geschrieben wird (Nutzdaten-Zellen statt nur Metadaten) — daher der geforderte eigene Kill-Switch (R5). |

---

## 8 / Offene Punkte

Konsolidiert aus beiden Dokumenten; die Backlog-IDs stehen in
[`OPEN_TASKS.md`](OPEN_TASKS.md) Abschnitt **R**.

| # | Punkt | Behandlung |
|---|---|---|
| a | Eigener Kill-Switch + Contract-Policy `quarantine.healing` (Modus, Spalten-Allowlist, Vier-Augen-Schalter) | **R5** — vor produktivem Einsatz |
| b | Per-Zeile-Zustände (`clean`/`discarded`), Verwerfen, Restore, optimistisches Locking | **R6** |
| c | SQL-Healing für Massenkorrekturen (Guard nach §6.3) | **R6**, nach a |
| d | Rollen: `steward+` korrigiert, `owner+` gibt frei? (heute: steward+ korrigiert, Vier-Augen nur bei Contract-Kinds) | R5 |
| e | Cockpit-Zeilen-Grid hinter G8-Gate vs. heutige formularbasierte Korrektur | R4 — erst bei Kundenbedarf |
| f | Patch-Verfall (H3): TTL/Review-Pflicht, Kollisionsregel Patch × neue Quell-Lieferung | R4 — **vor produktivem H3-Einsatz klären** |
| g | `keys`-Validierung gegen den lebenden Quellbestand (Snapshot vs. live) | Spike mit O7 bündeln |
| h | Maximale Episodengröße; ab wann SQL-only empfehlen | mit c |
| i | Audit-Aufbewahrung nach `resolved` — TTL oder länger (Compliance)? | O10-Review |
| j | Live-Verifikation `P_DQ_CORRECT_ROW`, Re-Check, Healed-View am Tenant | R4, mit O5/O6 |
| k | „Heilungs-Vorschläge" (Signal schlägt Korrekturen aus Fehlermustern vor) | bewusst v2 — erst die manuelle Mechanik härten |

---

## 9 / Empfehlung

1. **Haltung:** H2 ist der Default — manuelles Daten-Healing ist die begründete
   Ausnahme, nie der Normalweg. **H5 sofort verdrahten** (billigster Baustein,
   verhindert Daten-Flickerei bei Regelfehlern).
2. **Vor produktivem H1/H3-Einsatz:** R5 (Kill-Switch + Spalten-Allowlist) und
   Punkt f (Patch-Kollisionsregel) schließen.
3. **H4 mit Slice ⑦**, nicht früher. **R6** (per-Zeile-Mechanik, SQL-Healing)
   erst nach Betriebserfahrung mit der schlanken Fassung.
