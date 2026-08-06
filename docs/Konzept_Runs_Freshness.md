# Konzept: Run-/Load-Informationen als Freshness-Dimension

## Ziel

Signal stellt Informationen ueber ausgefuehrte Datasphere-Runs (Replication
Flows, Transformation Flows, persistierte Views, Task Chains) dar — aber nicht
als eigenes Job-Monitoring, sondern als **Freshness-Dimension**, die jede
Qualitaetsaussage ergaenzt und absichert.

## Leitidee

Datasphere hat bereits einen Task-Monitor. Signal baut den nicht nach. In Signal
beantwortet ein Run genau eine Frage — **"ist dieser Datenstand aktuell?"** — und
das ist die fehlende zweite Achse neben **"ist dieser Datenstand korrekt?"** (den
Checks).

Ein gruenes `PASS` auf Daten, die seit 5 Tagen nicht geladen wurden, ist
irrefuehrend. Runs sind die Evidenz, mit der Signal genau das erkennt. Deshalb
werden Run-Informationen als **Zeit-/Aktualitaetsachse in die bestehenden
Oberflaechen eingewoben** — nicht als separate "Jobs"-Seite.

Diese Idee nutzt ein bereits vorhandenes Primitiv wieder: den Gating-State
`skipped_stale` (G6). Runs liefern die Evidenz, die diesen State steuert.

### Ehrlichkeits-Regel

Fehlt eine Run-Quelle (kein technischer User / kein REST-Connector konfiguriert),
gilt **"unbekannt", nicht "frisch"**. Das ist dieselbe Disziplin wie beim
Extrakt-No-Op: niemals einen unbekannten Zustand als gruen darstellen.

## Connectivity (Kurzentscheidung)

Run-Historie wird ueber die **REST-API mit technischem User**
(OAuth2 Client-Credentials, `services/api/datasphere.py`) bezogen — headless,
monitoring-tauglich, bereits implementiert (R7: `get_task_chain_runs`,
`get_replication_flow_runs`, `get_data_loads` hinter `GET /api/datasphere/data-loads`).
Die CLI bleibt dem vorbehalten, was REST nicht zuverlaessig liefert (volles CSN
fuer Lineage). Begruendung siehe ADR-0002 (Datasphere-DB-Zugriff) bzw.
`datasphere.py`.

## API/Typen — verifizierter Ist-Zustand (Stand der Pruefung)

Damit das Konzept nicht auf nicht vorhandenen Feldern aufbaut, hier der gepruefte
Stand der bestehenden Implementierung. **Wichtig: die hier fehlenden Felder sind
Voraussetzung fuer die Freshness-Evidenz-Hierarchie und muessen erst geschaffen
und an einem echten Payload verifiziert werden.**

- **Modellierte Felder** (`DataLoadOut`, `services/api/routers/data_loads.py`;
  Frontend `DataLoad`, `apps/cockpit/src/types/index.ts`): `object_id`,
  `load_type`, `run_id`, `status`, `started_at`, `finished_at`, `duration_ms`,
  `error_message`, `triggered_by`, `raw`.
- **Nicht modelliert**: **kein** Row-Count / Delta / Load-Modus (initial/delta) /
  `last_delta_at`. Solche Werte ueberleben heute nur ungetypt im `raw`-Blob —
  sofern Datasphere sie ueberhaupt liefert.
- **Feldnamen unbestaetigt**: `_normalise` raet Schluessel per `or`-Ketten
  (`startTime or start_time or startedAt or createdAt` …). Es gibt **keine
  Fixture/keinen Test**, der einen echten Replication-Run-Payload pinnt — die
  Annahme "Delta + Row-Count vorhanden" ist aus diesem Repo **nicht verifizierbar**.
- **Nur zwei Run-Typen abgerufen**: `datasphere.py` holt **Task Chains +
  Replication Flows**; `load_type` ist `task_chain | replication_flow`.
  **Transformation Flows und Persist-Tasks werden derzeit nicht abgerufen** — die
  Abdeckung dieser Typen ist API-seitig aktuell null.
- **Space-Aufloesung** (gefixt): `_resolve_space` nutzt jetzt `effective_space_id`
  (explizit → env → connector.yml), konsistent zu `get_client`. Vorher env-only,
  wodurch ein per Connector-UI gesetzter Space fuer data-loads nicht griff.

Grounding-Schritt vor jedem Freshness-Build: **einen echten Replication-Flow-Run-
Payload aus einem Tenant aufnehmen**, die tatsaechlichen Schluessel pinnen, dann
getypte Felder (`records_transferred`, `is_delta`, `last_delta_at`) ergaenzen.

## Das Atom: Freshness pro Objekt

Jeder Run bildet auf ein Dataset ab, daher ist die Praesentationseinheit die
**Freshness eines Objekts**, abgeleitet aus seinem letzten Run:

- **Letzter erfolgreicher Load** — absolut + relativ ("vor 3 h") und der Load-Typ
  (replication / transformation / persist view / task chain).
- **Aktueller Zustand** — `success · running · failed · late/overdue · never-run ·
  unknown`.
- **Freshness-Verdikt** gegen ein SLA-Fenster: `fresh · aging · stale · failed ·
  unknown` — eine Freshness-Ampel analog zur Qualitaets-Ampel.
- **Run-History-Sparkline** — die letzten N Runs als farbige Ticks (Outcome /
  Latenz). Ein Blick = "ist dieser Load verlaesslich?".

## Freshness-Evidenz-Hierarchie (Run-Erfolg != Aktualitaet)

Ein erfolgreicher Run beweist nicht, dass sich Daten geaendert haben: ein
Delta-Load kann mit `records = 0` durchlaufen — der Job lief, die Tabelle ist
aber nicht frischer. Deshalb wird Freshness nach **Evidenzguete** abgestuft, nicht
allein aus dem Run-Erfolg:

1. **Daten-Aenderungs-Evidenz (stark)** — Delta-Row-Count + `last delta at` aus dem
   Replication-Flow-Run. `records > 0` = echte Aktualisierung; `records = 0` =
   eigener Zustand `success-no-change` (verschieden von `failed` und von `stale`).
2. **Lauf-Abschluss-Evidenz (schwach)** — nur Run-Endezeit/Status, ohne Counts.
   Gilt als **obere Schranke der Staleness**, nicht als Beweis neuer Daten.
   Sichtbar als solche kennzeichnen.
3. **Keine Quelle** — `volume unknown` / `freshness unknown`. Nie als frisch
   darstellen (Ehrlichkeits-Regel).

Konsequenzen:

- **Volume als Begleiter** — der Delta-Row-Count liefert gratis eine Volumen-Serie
  (Sparkline) und damit Cadence-/Volumen-Anomalien (SOTA: Bigeye/Monte Carlo),
  zumindest fuer Replication-Targets.
- **Metrik-Semantik** — "records transferred" im Delta = *geaenderte Zeilen dieses
  Runs*, nicht *absolute Tabellengroesse*. Gut fuer "hat sich was geaendert?";
  fuer absolute Volumen-Anomalien braucht es eine Initial-Load-Baseline.
- **Ungleiche Abdeckung** — Replication-Flow-Runs liefern Counts gut;
  Transformation-Flows und Persist-Tasks oft nicht. Evidenz ist also getiert:
  reich fuer Replication, duenner sonst → entsprechend kennzeichnen.
- **Per-Target-Fan-out** — ein Replication Flow hat mehrere Ziel-Tables mit je
  eigenem Count; pro Target abbilden (gleiche Run-Gruppen-Nuance wie Task Chains).
- **Payload zuerst verifizieren** — Feldnamen/Verfuegbarkeit variieren je
  DSP-Version und Quelltyp; vor dem Modellieren an einem echten Run pruefen.

## Wo es sichtbar wird (an bestehende Surfaces andocken, kein Silo)

1. **Objekt-Detail** — primaere Heimat. Freshness-Header + Run-History-Sparkline +
   Last-Load-Fakten. Hook vorhanden: `useObjectDataLoads`.
2. **Status-Grid** — **Freshness-Indikator neben der Qualitaets-Ampel**. Jede Zeile
   zeigt beide Achsen: *korrekt?* (Checks) und *aktuell?* (Loads). Ein gruener
   Check auf veralteten Daten wird sichtbar abgewertet.
3. **Gate-Integration (der Signal-spezifische Hebel)** — ist der letzte Load aelter
   als das Freshness-Fenster des Contracts, wird der Check abgewertet (bevorzugt
   `downgraded`, ausgewertet-aber-konfidenzreduziert; `skipped_stale` nur wenn der
   Check ohne frische Daten bedeutungslos ist — siehe offene Frage 2) und der Run
   als Grund **zitiert**. Das ist die Verbindung, die nur Signal herstellen kann
   (Load-Lineage → Quality-Gating), und sie ist dank G6 fast geschenkt.
4. **Lineage-/Coverage-Map** — Nodes nach Freshness einfaerben und propagieren:
   eine "frische" View, gespeist von einer veralteten Remote-Table, ist
   **effektiv veraltet**. Load-Edges = die Datenbewegungs-Realitaet hinter den
   Lineage-Edges.
5. **Incidents** — ein fehlgeschlagener Run oder chronische Verspaetung wird zum
   Incident auf **derselben** Oberflaeche wie Qualitaetsfehler (ein Posteingang,
   nicht zwei). Timeliness steht neben Correctness.
6. **Contracts** — eine **Freshness-/Timeliness-Guarantee-Familie** ("geladen
   innerhalb 24 h", "taeglich bis 06:00"). Runs sind die Evidenz, die das
   beweist/verletzt — bleibt SQL-frei/semantisch (G1), und die Run-Historie wird
   zum erstklassigen SLA statt nur Status-Anzeige.

## Modell-Nuancen (vorab entscheiden)

- **Task Chains sind Run-*Gruppen*** — ein Chain-Run beruehrt viele Objekte. Den
  Chain-Run als Gruppe darstellen, die auf die Freshness jedes Mitglieds-Objekts
  herunterbricht, nicht als eine opake Zeile.
- **Typ → Objekt-Mapping**: Replication-Flow-Run → Ziel-Table; Transformation-
  Flow-Run → Output-Objekt; Persist-Task → die persistierte View; Task-Chain →
  Fan-out auf alle beruehrten Objekte.
- **Freshness-SLA-Quelle**: zuerst Contract (falls Timeliness-Guarantee
  vorhanden), sonst ein globaler Default pro Environment, sonst "unknown".

## States & visuelle Sprache

- Run-States: `success · running · failed · late · never · unknown`.
- Freshness-Ampel: `fresh · aging · stale · failed · unknown`.
- Zeit: relative Angabe ("vor 3 h") mit absolutem Zeitstempel im Tooltip.
- Konsistenz: dieselbe Ampel-/Badge-Sprache wie bei Qualitaet, damit beide Achsen
  visuell vergleichbar sind.

## Abgrenzung (was Signal NICHT tut)

- Kein Nachbau des Datasphere-Task-Monitors; tiefe Job-Logs werden verlinkt, nicht
  gespiegelt.
- Keine Run-Steuerung (Start/Stop/Retry) — Signal bleibt read-only.
- Keine eigene "Jobs"-Seite als Silo; Run-Info lebt in Objekt/Grid/Lineage/
  Incidents/Contracts.

## Stand der Technik & offene Designfragen

Vergleich mit Daten-Observability-Tools (Monte Carlo, Bigeye, dbt source
freshness, Elementary, Atlan). Das Konzept ist bei **Lineage-Propagation** und
**Gate-Integration** auf bzw. ueber SOTA-Niveau; folgende Punkte sind ungeloest
oder bewusst zu entscheiden:

1. **Run-Erfolg != Freshness** — adressiert durch die Evidenz-Hierarchie oben
   (Delta-Counts > Lauf-Abschluss). SOTA-Pendant: dbt nutzt `loaded_at` in den
   Daten, Monte Carlo nutzt Update-Zeit + Row-Count.
2. **`skipped` vs `downgraded`** — Checks bei Staleness komplett zu ueberspringen,
   kann eine Korrektheits-Regression hinter einem Freshness-Flag verstecken und
   wirft zwei unabhaengige Fakten ("veraltet" / "falsch") zusammen. **Empfehlung:**
   bevorzugt den vorhandenen State `downgraded` (ausgewertet, Konfidenz reduziert,
   "auf veralteten Daten" annotiert) statt `skipped`. `skipped_stale` nur, wenn
   Staleness den Check buchstaeblich bedeutungslos macht (z. B. "heute geladen").
   *Offene Entscheidung — derzeit das groesste semantische Risiko.*
3. **Statische Schwellen → Alert-Fatigue** — ein fixes "24 h" missfeuert bei
   Wochenend-Cadence, Monatsende, Schedule-Wechsel. SOTA: gelernte Cadence/Anomalie
   (Bigeye/Elementary). **Empfehlung:** erwartete Cadence pro Objekt aus
   Run-Historie + `schedules.py` ableiten, statischer Contract-Wert nur als
   Obergrenze.
4. **Propagation ohne Root-Cause-Dedup** — naive Downstream-Staleness faerbt halbe
   Landschaften rot. SOTA (Monte Carlo): Root zeigen, Derivate unterdruecken.
   Propagation muss auf den Root-Stale-Node + Blast-Radius-Count kollabieren.
5. **Partielle Task-Chain-Rollups** — bei Teil-Fehlschlag sind manche Objekte
   frisch, manche stale; Reihenfolge/Abhaengigkeit zaehlt. Pro-Task-Status im
   Chain-Run modellieren, nicht Chain-Level.
6. **"Late" braucht erwartete naechste Ausfuehrung** — Lateness aus Signal-Schedules
   + beobachteter Cadence definieren (siehe 3).
7. **Skalierung** — Run-Historie pro Objekt zu pollen ist N+1 (Rate-Limits). Bulk-
   Abruf/Caching statt Per-Objekt-Fan-out (`useObjectDataLoads`) bei Tenant-Scale.
8. **Zwei Achsen vs. aggregierter Trust-Score** — SOTA rollt Freshness+Volume+
   Schema+Quality zunehmend in einen Asset-Trust-Score (Atlan/MC). Signals zwei
   explizite Achsen sind transparenter; fuer Coverage-/Exec-Views ist ein
   optionaler Aggregat-Rollup zu entscheiden.

## Phasen

- **MVP**: Objekt-Detail-Freshness + Run-Sparkline + Status-Grid-Freshness-
  Indikator (read-only, "unknown" ohne Connector). Wo verfuegbar: Delta-Row-Count
  statt nur Run-Status.
- **High-Value Next**: Freshness ins Gating verdrahten — bevorzugt `downgraded`,
  mit zitiertem Run (siehe offene Frage 2).
- **Spaeter**: Lineage-Propagation (mit Root-Cause-Dedup), Timeliness-Incidents,
  Freshness-Guarantee-Familie, gelernte Cadence.

## Bezug zu bestehenden Invarianten

- **G6** (Gating-States nie still weglassen): `skipped_stale` ist der vorhandene
  Andockpunkt; Runs liefern dessen Evidenz.
- **G1** (keine SQL in Contracts): Timeliness als semantische Guarantee-Familie,
  nie als SQL.
- **Ehrlichkeit bei fehlender Quelle**: "unknown" statt "fresh" — analog zum
  Extrakt-`skipped`-Verhalten.
