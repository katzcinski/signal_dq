# Spike-Kit — Enforcement-Aktivierung am Tenant (Rest-O5 · O6 · O8 · O9)

**Zweck:** Ein halber Tag am echten Datasphere-Tenant, danach sind alle
Aktivierungs-Blocker der Slices ④–⑦ verifiziert. Jeder Check hat hier
fertige Schritte/SQL, ein erwartetes Ergebnis und einen **Capability-Key**,
unter dem das Resultat in Signal eingetragen wird — entweder automatisch
(`POST /api/enforcement/probe`) oder manuell
(`POST /api/enforcement/capabilities`). `GET /api/enforcement/capabilities`
zeigt jederzeit den Stand.

**Voraussetzungen:** Datasphere-Tenant mit einem Space + Open-SQL-Schema
(Database User = Signals Space-User), DB-Client (DBX/hdbsql) mit diesem User,
Data-Builder-Zugriff im Space, ein zweiter Space (für Sharing), optional ein
zweiter Database User (nur für R-D). In Signal: `DATASPHERE_SIGNAL_SCHEMA`
gesetzt, ein Environment mit der Verbindung konfiguriert.

---

## Teil A — Automatisch (ein API-Aufruf)

```bash
curl -X POST "$SIGNAL/api/enforcement/probe" \
  -H "Content-Type: application/json" \
  -d '{"environment": "<env-name>"}'
```

Legt harmlose Probe-Objekte im Signal-Schema an und droppt sie sofort wieder:

| Capability-Key | Prüft | Erwartung |
|---|---|---|
| `open_sql_table_write` | CREATE/INSERT/SELECT/DROP TABLE im eigenen Schema | `ok` (Schema-Owner-Recht) |
| `open_sql_view` | CREATE OR REPLACE VIEW + SELECT | `ok` |
| `sqlscript_sync` | **O6:** Prozedur mit `USING SQLSCRIPT_SYNC` + `SLEEP_SECONDS(1)` | `ok` ⇒ `P_DQ_GATE`-Warte-Schleife nutzbar · `unavailable` ⇒ Fallback: Chain in Request-Schritt + Assert-Schritt teilen (dokumentiert, Konzept §6.3) |
| `catalog_tables_read` | `SYS.TABLES` für das eigene Schema | `ok` (Bootstrap-Existenzprüfung) |

## Teil B — Manuell (Data Builder / zweiter Space / zweiter User)

Ergebnis jeweils eintragen:
```bash
curl -X POST "$SIGNAL/api/enforcement/capabilities" \
  -H "Content-Type: application/json" \
  -d '{"key": "<capability-key>", "status": "ok", "detail": "<Beobachtung>"}'
```

### B1 — `flow_table_import` (Kern-O5, laut Tenant-Erkenntnis bereits bestätigt — gegenprüfen)
1. Im Signal-Schema eine Testtabelle anlegen (Teil A hat `open_sql_table_write`
   bewiesen; für den Import eine bleibende Tabelle nutzen):
   ```sql
   CREATE TABLE "<SIGNAL_SCHEMA>"."DQ_SPIKE_CLEAN" ("ID" INTEGER, "VAL" NVARCHAR(20));
   INSERT INTO "<SIGNAL_SCHEMA>"."DQ_SPIKE_CLEAN" VALUES (1, 'A');
   ```
2. Data Builder → Import → Objekt aus dem Open-SQL-Schema wählen.
3. **Erwartung:** Entität erscheint im Space und zeigt *live* auf die
   hdbtable — nach `INSERT INTO … VALUES (2,'B')` per SQL zeigt die
   Daten-Vorschau im Space sofort 2 Zeilen (kein Kopieren).
4. Die Entität als Quelle in einen Transformation Flow ziehen — validiert der
   Flow? → `ok`.

### B2 — `flow_view_import` (Rest-O5, nur für Split-Variante B relevant)
Wie B1, aber mit einer View:
```sql
CREATE VIEW "<SIGNAL_SCHEMA>"."DQ_SPIKE_V" AS
  SELECT "ID", "VAL" FROM "<SIGNAL_SCHEMA>"."DQ_SPIKE_CLEAN" WHERE "ID" > 0;
```
**Erwartung offen** — genau das ist der Spike. `ok` ⇒ Variante B (Prädikat-
Views) steht als Option; `unavailable` ⇒ Variante A (Tabellen) bleibt der
einzige Split-Pfad (bereits der empfohlene Default).

### B3 — `cross_space_sharing`
Die in B1 importierte Entität im Quell-Space teilen → im zweiten Space als
Quelle nutzen. **Erwartung:** Standard-Sharing funktioniert; keine DB-Grants
nötig. → `ok`.

### B4 — `execute_grant_foreign_user` (nur Rezept R-D — Kunden-Prozeduren unter fremder Identität)
Voraussetzung: Slice ③ ist per `POST /api/enforcement/apply` materialisiert
(Prozeduren existieren). Dann als Signal-User:
```sql
GRANT EXECUTE ON "<SIGNAL_SCHEMA>"."P_DQ_ASSERT_GATE" TO <ZWEITER_DB_USER>;
```
Als zweiter User:
```sql
CALL "<SIGNAL_SCHEMA>"."P_DQ_ASSERT_GATE"('DQ_SPIKE_OBJ', 3600, NULL, 'block_and_quarantine');
```
**Erwartung:** Grant gelingt; der Aufruf wirft `SQL_ERROR_CODE 10050`
(kein Verdict — fail-closed, das ist das korrekte Verhalten!). → `ok`.
Schlägt schon der GRANT fehl → `unavailable` + Meldung notieren; R-D braucht
dann den Umweg über den eigenen Space-Kontext.

### B5 — `invalidate_drop_loud` (O9 — Grace-Mechanik der Waisen)
1. Flow aus B1 laufen lassen (grün).
2. Die Quelle droppen: `DROP TABLE "<SIGNAL_SCHEMA>"."DQ_SPIKE_CLEAN";`
3. Flow erneut ausführen. **Erwartung:** Der Flow schlägt **laut** fehl
   (Fehler am Task, nicht 0 Zeilen still verarbeitet). → `ok`.
   Verarbeitet er still leer weiter → `error` + genaue Beobachtung — dann
   braucht die Grace-Mechanik einen anderen Bruch-Mechanismus (z. B.
   Spalten-Umbenennung), bitte notieren.

### B6 — `api_task_status_codes` (O8 — Feinschliff Slice ②/⑦)
1. HTTP-Connection auf Signal anlegen (Host, technischer Principal steward+;
   S5: kein noauth über Loopback hinaus).
2. Task Chain mit API-Task: `POST /api/objects/<id>/run`, Async-Modus,
   Status-URL aus dem `Location`-Header.
3. **Erwartung:** Task pollt `/api/runs/{id}/status`, akzeptiert die
   RUNNING/COMPLETED/FAILED-Antworten, Chain verzweigt korrekt. Abweichende
   Statuscode-Erwartungen (z. B. HTTP-Code statt Body-Feld) exakt notieren
   → ggf. kleine Endpoint-Anpassung.

## Aufräumen

```sql
DROP TABLE "<SIGNAL_SCHEMA>"."DQ_SPIKE_CLEAN";  -- falls nicht in B5 gedroppt
DROP VIEW  "<SIGNAL_SCHEMA>"."DQ_SPIKE_V";
```
Importierte Spike-Entitäten und Test-Flows im Data Builder löschen.

## Ergebnis-Matrix → Aktivierungs-Entscheidung

| Alle `ok` bei … | dann aktivierbar |
|---|---|
| A + B1 + B3 (+B5) | Slice ④ Variante A + Slice ⑤ (`ENFORCEMENT_MATERIALIZE_ENABLED`) — B5 gehört zur Betriebs-, nicht zur Startbedingung |
| zusätzlich B2 | Slice ④ Variante B als Option |
| zusätzlich `sqlscript_sync` | Slice ⑥ komplett (`ENFORCEMENT_SQL_BRIDGE_ENABLED`); sonst Fallback-Muster |
| zusätzlich B4 | Rezept R-D (Kunden-Prozeduren fremder Identität) |
| zusätzlich B6 | API-Task-Gate produktiv + Slice ⑦ (`DATASPHERE_ALLOW_TRIGGER`) |

Slice ⑤ produktiv zusätzlich: **O10-Review abgeschlossen**
(`docs/O10_Datenschutz_Review_Custody_Zone.md`).
