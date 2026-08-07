# Konzept: Meridian Inventory als Signal-Admin-Tool

## Ziel

Signal integriert die Meridian-Inventory-Logik als administratives Werkzeug fuer
Platform Admins. Das Werkzeug extrahiert Datasphere/HANA-Metadaten, baut daraus
Inventory- und Lineage-Snapshots, veroeffentlicht verwendbare Ergebnisse auch bei
teilweisen Runs und macht Fortschritt, Warnungen und letzte Snapshots sichtbar.

## Produktform

- Zugang: eigener Sidebar-Eintrag `Inventory`, sichtbar fuer Platform Admins.
- Publish-Verhalten: teilweise erfolgreiche Runs duerfen publiziert werden,
  solange die nutzbaren Snapshots konsistent sind und Warnungen sichtbar bleiben.
- Rohartefakte: Laufzeit-/Debug-Artefakte werden nach erfolgreichem Publish
  bereinigt; langlebig bleiben nur die freigegebenen Snapshot-Artefakte.
- Downloads: keine Steward-/Owner-Downloads von sanitisierten Snapshots in der
  ersten Ausbaustufe.
- Architektur-Findings: zunaechst keine automatische Ueberfuehrung in Proposals,
  Incidents oder einen dritten Signal-Typ.

## Phase 1

Phase 1 liefert einen schmalen, nutzbaren Admin-Einstieg auf dem bestehenden
Extraktpfad:

- Admin-only Backend-Trigger fuer `POST /api/extract`.
- `GET /api/extract/status` fuer Bereitschaft, Fortschritt, Counts, Warnungen,
  Artefaktpfade und letzten Publish-Zeitpunkt.
- Cockpit-Seite `/inventory-admin` mit Readiness, Scope, Status/Progress und
  Snapshot-Ansicht.
- Polling statt Server-Sent Events; echte Live-Schritte folgen mit dem spaeteren
  async Job Runner.
- Der bestehende synchrone Extraktor bleibt die Quelle der Wahrheit. Wenn keine
  Live-Quelle konfiguriert ist, wird das als lokaler Snapshot-Modus angezeigt.

## Naechste Phasen

1. Async Job Runner mit persistierten Run-Schritten, Progress-Events und Cancel.
2. Meridian-Adapter als eigene Inventory-Pipeline mit Space-Auswahl,
   Partial-Publish und Artefakt-Pruning.
3. Live View per SSE/WebSocket fuer Objektfortschritt, Warnungen und Publish.
4. Admin-Historie fuer Snapshots, Diff-Ansicht und Rollback.
5. Spaetere Entscheidung, ob Architektur-Findings als eigener Workflow in Signal
   sichtbar werden.
