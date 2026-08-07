# O10 — Datenschutz-Review: Signals Custody-Zone (Dossier für den Governance-Termin)

**Adressat:** Datenschutz/Governance, Plattform-Team · **Stand:** 2026-07-11
**Status:** Entscheidungsvorlage — der Review-Termin ist der Blocker, dieses
Dossier macht ihn zu **einem** Termin.
**Gegenstand:** Die episodische Quarantäne (Slice ⑤) parkt **vollständige
Rohzeilen — potenziell inkl. personenbezogener Daten** — in Tabellen im
Signal-eigenen Open-SQL-Schema. Das Healing-Konzept würde zusätzlich das
**Anzeigen und Ändern** dieser Zeilen erlauben. Beides ist implementiert bzw.
konzipiert, aber **dormant**; dieser Review gibt die Aktivierung frei (oder
verlangt Auflagen).

---

## 1 — Was genau gespeichert wird (Datenflüsse)

```
Quelle (Kunden-Space) ──SELECT──► Signal-Engine (flüchtig, nur Zählwerte)
                                        │ verdict = quarantine
                                        ▼
                       INSERT…SELECT WHERE <bad>  (innerhalb HANA!)
                                        ▼
              "<SIGNAL_SCHEMA>"."DQ_Q_<OBJ>"  ← vollständige Bad-Zeilen
                                        │ Steward-Freigabe
                                        ▼
              V_DQ_RELEASED_<OBJ> ──SELECT── Kunden-Re-Load-Flow → Ziel
```

Zentrale Eigenschaften:

1. **Die Zeilen verlassen HANA nie.** Der Snapshot ist ein `INSERT…SELECT`
   innerhalb der Datenbank; Signals Service, Store (SQLite) und Cockpit
   speichern nur **Zählwerte, Check-Namen, Zeitstempel, Episoden-Status** —
   nie Zeileninhalte. (Gate G8 unverändert.)
2. **Anzeige nur gegated:** Ein Drilldown in Zeileninhalte existiert
   ausschließlich über den bestehenden Diagnostics-Pfad — je Check explizit
   aktiviert (`diagnostics_enabled`) **und** spalten-allowlisted; Rolle
   mindestens steward. Ohne Opt-in sieht auch das Cockpit nur Zahlen.
3. **Zweck:** Isolation fehlerhafter Datensätze bis zur Behebung/Rückführung —
   kein Reporting, keine Auswertung, keine Weitergabe.

## 2 — Speicherbegrenzung & Löschkonzept

| Mechanismus | Regel | Implementierung |
|---|---|---|
| **Pflicht-TTL** | Quarantäne-Zeilen leben maximal `QUARANTINE_TTL_DAYS` (Default **30 Tage**) | automatischer Purge im Lauf-Pfad; Episode wird explizit `resolved(expired)` — nie stilles Verschwinden |
| **Rückführung** | Nach bestätigter Rückführung (`confirm-reprocess`) fallen die Zeilen aus der Release-View; der nächste TTL-Purge entfernt sie physisch | Lifecycle `released → resolved(reprocessed)` |
| **Kein Reconciler-Drop** | Quarantäne-Tabellen werden nie durch Schema-Abgleich gelöscht — nur TTL/Abschluss | vom invalidate-then-drop ausgenommen |
| **Betroffenenrechte** | Löschung auf Zuruf: `DELETE` auf `DQ_Q_<OBJ>` durch den Schema-Owner ist jederzeit möglich; Episode manuell schließen | Runbook-Punkt, siehe §5 |

**Zu entscheiden im Review:** ① Ist 30 Tage der richtige Default (bzw. je
Datenklasse abweichend)? ② Muss der Purge zusätzlich zeitgesteuert laufen
(heute: opportunistisch je Lauf des Objekts — ein Objekt ohne weitere Läufe
purgt erst beim nächsten Lauf)?

## 3 — Zugriff, Rollen, Audit

- **Schreiben:** ausschließlich Signals technischer Space-User, ausschließlich
  im eigenen Open-SQL-Schema (ADR-0002-Amendment). Pipeline-/Fremd-User
  erhalten höchstens SELECT auf Views bzw. EXECUTE auf Prozeduren.
- **Freigabe:** steward+ (Server-seitig erzwungen), jede Aktion mit Akteur,
  Zeitstempel und Notiz in der Episoden-Timeline; zusätzlich als Operation
  auditiert.
- **Secrets/Transport:** hdbcli mit TLS + Zertifikatsvalidierung; Credentials
  im Secret-Store, Rotation benannt (ADR-0002).
- **Mandantentrennung:** eine Custody-Zone je Signal-Schema; Blast-Radius =
  genau die unter Quarantäne-Enforcement stehenden Objekte.

## 4 — Healing-Erweiterung (separat freizugeben)

> **Stand 2026-08-03:** Healing ist inzwischen **teilweise implementiert** —
> maßgeblich ist [`Konzept_Manuelles_Healing.md`](Konzept_Manuelles_Healing.md)
> (das frühere `Konzept_Quarantaene_Healing.md` ist darin aufgegangen).
> Gebaut wurde die **konservative Teilmenge**: Korrektur einzelner Zellen über
> ein Formular — das Cockpit zeigt **keine** Zeileninhalte, es gibt also
> vorerst **kein** Anzeige-Grid und **kein** SQL-Healing. Für den Review
> relevant: der im Konzept geforderte **eigene Kill-Switch** und die
> **Spalten-Allowlist im Contract** sind **noch nicht umgesetzt**
> (`OPEN_TASKS.md` R5) — heute entscheidet allein die Rolle (`steward+`
> korrigiert, Vier-Augen bei Contract-Kinds). Das gehört auf die
> Auflagen-Checkliste (§5).

Das ursprüngliche Healing-Konzept sah zusätzlich vor:
**Anzeigen** (Grid, spalten-maskiert nach Allowlist) und **Ändern**
(zellgenau bzw. gescopetes SQL) geparkter Zeilen durch Stewards.

Datenschutz-relevante Zusicherungen des Konzepts:

- Opt-in-Leiter: globaler Kill-Switch → Contract-Policy (`manual` /
  `manual+sql`) → optional Vier-Augen-Freigabe.
- Editierbar nur allowlisted Spalten; nicht allowlistete sind maskiert
  (`•••`) und gesperrt; „editieren ohne sehen" ist als Konfiguration verboten.
- Append-only-Audit je Zelle (alt→neu, Akteur, Methode, Statement verbatim);
  Original wiederherstellbar; Audit-Aufbewahrung = Episoden-TTL
  (**Review-Frage:** länger aufbewahren? → dann getrennte Audit-Retention).

**Empfehlung:** Slice ⑤ (Parken/Freigeben) und Healing (Ändern) **getrennt**
freigeben — Healing erst nach Slice-⑤-Betriebserfahrung.

## 5 — Auflagen-Kandidaten & offene Punkte (Checkliste für den Termin)

- [ ] TTL-Default bestätigen oder je Datenklasse festlegen (§2)
- [ ] Zeitgesteuerter Purge als Auflage? (§2)
- [ ] Datenklassen ausschließen? (z. B. besondere Kategorien Art. 9 DSGVO →
      `enforcement: quarantine` für diese Objekte untersagen — Contract-Review)
- [ ] Diagnostics-Allowlists je Objekt abnehmen (wer sieht welche Spalten)
- [ ] Runbook Betroffenenrechte (Auskunft/Löschung) — Zuständigkeit benennen
- [ ] AV-Vertrag/TOMs: Custody-Zone als Verarbeitungstätigkeit aufnehmen
- [ ] Healing: jetzt mitentscheiden oder auf Folge-Termin nach ⑤-Erfahrung
- [ ] Audit-Retention für Healing-Änderungen (falls freigegeben)
- [ ] **Neu (2026-08):** eigener Healing-Kill-Switch + Spalten-Allowlist im
      Contract als Auflage setzen? (heute nicht implementiert — R5)
- [ ] **Neu (2026-08):** H3-Patch-Overlay mitentscheiden — dauerhafte
      Korrektur über `V_DQ_HEALED_<OBJ>`, Aufbewahrung/Verfall der Patches

## 6 — Referenzen

`Konzept_Datasphere_Integration_Gating_Quarantaene.md` §5.2/§9 ·
`Konzept_Manuelles_Healing.md` §5/§7 (maßgeblich) ·
`Konzept_Quarantaene_Healing.md` §7 (historisch) ·
`Datenfluesse_Quelle_vs_Signal.md` · `ADR-0002` + Amendment ·
Spike-Kit: `docs/spikes/Spike_Kit_Enforcement_Aktivierung.md` ·
Interaktiv: `docs/interactive/enforcement-logik-landkarte.html`
