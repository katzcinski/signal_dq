# Kundendeck — Data Products mit Datasphere: der Lite-Einstieg

> **Format:** Präsentations-Gerüst (eine `##`-Sektion = eine Slide). Sprechernotizen unter _Notiz_. Platzhalter `‹…›` vor dem Termin füllen.
> **Adressat:** Kunde mit SAP Datasphere, Ambition Data-Product-Denken, noch keine Fachbereichs-Ownership.
> **Dauer:** 30–40 Min + Demo. **Quelle:** `docs/Betriebsmodi_Lite_und_Full.md`.

---

## 1 · Titel

**Verbindliche Datenprodukte — ohne auf die Organisation zu warten**
Ein Lite-Einstieg auf SAP Datasphere

‹Kunde / Datum / Vortragende›

_Notiz: Versprechen in einem Satz — messbare Zusagen an Konsumenten in Tagen, Ownership wächst danach organisch nach._

---

## 2 · Wo Sie heute stehen

- SAP Datasphere produktiv — Daten fließen, Konsumenten (SAC, Downstream) hängen dran.
- Ambition: Data-Product-Denken, moderne Architektur.
- **Aber:** keine Ownership aus dem Fachbereich, „Datenprodukt" ist neu.
- Risiko des klassischen Wegs: erst Org-Change & Governance aufbauen → Monate ohne sichtbaren Wert.

_Notiz: Hier nur spiegeln, nicht verkaufen. Der Kunde soll sich wiedererkennen. Die Pointe kommt auf der nächsten Slide._

---

## 3 · Die Kernspannung

> **Verbindlichkeit braucht normalerweise Ownership — Ownership braucht aber erst einen sichtbaren Grund.**

Henne-Ei. Wer zuerst Rollen, Versionen und Approvals fordert, verliert das Momentum.

_Notiz: Das ist der gedankliche Dreh- und Angelpunkt. Lösung: Verbindlichkeit von Ownership entkoppeln._

---

## 4 · Der Vorschlag: Lite zuerst

**Die Plattform gibt die ersten Zusagen — der Fachbereich übernimmt, wenn er den Wert sieht.**

- Garantien zu **Struktur · Qualität · Performance** als geführte Checkliste.
- Sofort **messbar** gegen Datasphere — kein PDF, sondern jeder Lauf geprüft.
- **Konsumenten sehen eine Ampel.** Genau das erzeugt den Pull zur Ownership.
- Technisch entkoppelt: `owned_by: platform` heute → `owned_by: product` später, ohne Rebuild.

_Notiz: „Lite" = derselbe Unterbau wie der Voll-Modus, nur ohne Versions-/Approval-Zeremonie. Kein Wegwerf-Prototyp._

---

## 5 · Was eine Zusage konkret abdeckt

| Dimension | Garantie-Familien | Beispiel |
|---|---|---|
| **Struktur** | schema (closed), keys, referential | „Genau diese Spalten, Schlüssel eindeutig, FKs valide" |
| **Qualität** | not_null, completeness | „Pflichtfelder gefüllt, ≥ 99,5 % Füllgrad" |
| **Performance** | freshness, volume | „Nicht älter als 24 h, ≥ 1.000 Zeilen" |

Rein semantisch — **niemals SQL** im Contract (Sicherheits-Gate). Der Server validiert verbindlich.

_Notiz: Familien an konkrete Konsumenten-Schmerzen knüpfen („sind die Daten von heute?"). Performance/Freshness ist meist der emotionalste Hebel._

---

## 6 · Was der Konsument sieht

- **Status-Cockpit:** je Objekt grün / gelb / rot, mit Historie.
- **Compliance-Ampel:** `compliant` / `breached` — automatisch, pro Produkt.
- **Coverage-Map:** welche Objekte schon eine Zusage tragen (`✓`) und welche nackt sind (`○`).

> Die Coverage-Map ist das Gesprächswerkzeug: „Dieses Objekt, von dem Ihr Report lebt, hat heute null Garantien."

_Notiz: Hier später live in die Demo überleiten. Die nackte vs. abgedeckte Map ist der stärkste visuelle Moment._

---

## 7 · Der Lite-Prozess in 6 Schritten

```
Extrakt ─▶ Seed ─▶ Garantien (Checkliste) ─▶ Speichern & aktivieren ─▶ Run ─▶ Ampel
```

1. **Extrakt** des Datasphere-Inventars & Lineage.
2. **Seed** — Tool schlägt Garantien aus dem Inventar vor (kein leeres Blatt).
3. **Garantien** per An/Aus + Severity setzen.
4. **Ein Klick** „Speichern & aktivieren" → Checks kompiliert.
5. **Lauf** gegen Datasphere.
6. **Ampel** im Cockpit — für Plattform und Konsument.

_Notiz: Betonen: Schritt 4 ist ein Klick, keine Approval-Runde. In Tagen, nicht Wochen._

---

## 8 · Live-Demo

1. Leerer Tenant → **Extrakt** → Objekte erscheinen, Coverage `○`.
2. `‹Beispielobjekt›` **seeden** → Garantie-Vorschläge.
3. Im **Lite-Modus** freshness + not_null + keys aktivieren → **Speichern & aktivieren**.
4. **Dry-Run / Run** → pass/fail je Garantie.
5. Coverage springt auf `✓`, **Compliance-Ampel** leuchtet.

_Notiz: Vorab im lokalen Modus (SQLite, NoAuth) aufgesetzt. Fallback-Screenshots bereithalten. 3–5 echte Konsum-Objekte des Kunden vorbereiten, wenn Daten verfügbar._

---

## 9 · Vom Lite-Einstieg zum governten Data Product

| Reifegrad | Modus | Was hinzukommt |
|---|---|---|
| **Heute** | Lite, `owned_by: platform` | Messbare Zusagen, Ampel |
| **Fachbereich sieht Wert** | Ownership-Shift → `product` | Verantwortung wandert |
| **Verbindlich versioniert** | Voll-Modus | SemVer, Approval, Breaking-Schutz, SLA-Fenster |

**Kein Rebuild** — gleiches Werkzeug, nur mehr Zeremonie, wenn die Reife da ist.

_Notiz: Dem Kunden die Sicherheit geben, dass Lite keine Sackgasse ist. Der Voll-Modus ist ein Toggle, kein neues Projekt._

---

## 10 · Was governter Voll-Modus zusätzlich bringt

- **Versionierung** (SemVer) und nachvollziehbare Änderungshistorie (1 Commit je Freigabe).
- **Breaking-Schutz:** inkompatible Änderung erzwingt Major-Sprung — Server **und** CI.
- **SLA-Fenster** (7/30/90 Tage), Incident-Timeline bei Breaches.
- **Datengetriebene Vorschläge** (Miner) und **BDC/ODCS-Export** für Katalog-Interop.

_Notiz: Nicht überfrachten — das ist das „Wohin", nicht der heutige Scope. Nur antippen._

---

## 11 · Betrieb & Aufsatz

| Variante | Profil | Wofür |
|---|---|---|
| **Berater-lokal** | SQLite, NoAuth, kein Dauerbetrieb | **PoC / Lite-Phase** |
| **Container beim Kunden** | OIDC, HANA-Store, ≥2 Worker | **Regelbetrieb / Voll-Modus** |

Beides aus demselben Code. Läufe planbar via Cron/Task-Chain.
**Zu entscheiden:** Betriebsmodell & Zuständigkeit (Updates/Secrets/IdP) vor dem Skalieren.

_Notiz: Ehrlich sein — das ist die eine echte Entscheidung. Für den Einstieg reicht lokal vollständig._

---

## 12 · Ehrliche Grenzen (Vertrauens-Slide)

- **Volume-Baselines** (Anomalie-Erkennung) brauchen Lauf-Historie; Einstieg über simples `min_rows`.
- **Scheduling** ist extern (Cron) — für Dauer-Verbindlichkeit einzurichten.
- **Spalten-genaue** Coverage folgt; Objektebene ist sofort da.

_Notiz: Bewusst zeigen — Offenheit über Grenzen baut mehr Vertrauen auf als ein lückenloser Pitch. Diese Slide nicht weglassen._

---

## 13 · Vorgeschlagene nächsten Schritte

1. **Scoping-Workshop** (½ Tag): 3–5 wichtigste Konsum-Objekte auswählen.
2. **Lite-PoC** (‹X Tage›, lokal): Extrakt → Garantien → Ampel auf echten Objekten.
3. **Review mit Fachbereich:** Coverage-Map als Ownership-Gespräch.
4. **Entscheidung:** Betriebsmodell & Übergang Lite → Full.

_Notiz: Mit einer kleinen, konkreten Zusage abschließen — der PoC ist der natürliche nächste Schritt, niedrige Schwelle._

---

## 14 · Backup — Häufige Fragen

- **„Ist Lite ein Wegwerf-Prototyp?"** Nein — identischer Unterbau, Voll-Modus ist ein Toggle.
- **„Schreibt das Tool in Datasphere?"** Nein — nur lesend; Ergebnisse liegen getrennt (Store).
- **„Was, wenn niemand Ownership übernimmt?"** Die Plattform-Zusage bleibt gültig und messbar; die Ampel hält den Druck.
- **„Wie sicher sind die Garantien?"** Kein SQL im Contract, Identifier-Validierung, PII-Gate (keine Rohzeile ohne Freigabe).

_Notiz: Nur bei Bedarf ziehen. Die SQL-/PII-Antwort ist für technische Stakeholder wichtig._
