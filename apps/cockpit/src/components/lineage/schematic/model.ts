/**
 * Datenadapter: mappt Signals Lineage-API-Shape (`LineageNode` + Column-Edges)
 * auf das Schaltplan-Modell, das Layout (ELK) und SVG-Renderer konsumieren.
 *
 * Framework-frei und rein — bewusst ohne React/DOM, damit es 1:1 unit-testbar
 * ist (siehe schematic-model.test.ts). Die Trace-Berechnung bleibt in
 * lib/lineage.ts (traceColumnLineage); hier geht es nur um die statische
 * Board-Struktur: Chips, Pins, Pin-zu-Pin-Traces.
 */
import type { ColumnEdgeType, ColumnLineageEntry, LineageColumn, LineageNode } from '@/types';
import { columnEdgeId, columnId, deriveLane, edgeTypeColor } from '@/lib/lineage';

/** Eingehende, bereits flachgeklopfte Column-Kante (Form aus lineage.json /
 *  /api/lineage/columns). */
export interface RawColumnEdge {
  source: string;
  sourceColumn: string;
  target: string;
  targetColumn: string;
  edgeType?: ColumnEdgeType;
  expression?: string;
}

/** Ein Pin = eine Spalte am Chip-Rand. */
export interface SchematicPin {
  /** Spaltenname (id innerhalb des Chips). */
  id: string;
  label: string;
  /** Datentyp, falls die API Spalten als Objekte mit data_type liefert. */
  dataType?: string;
  /** Hat eine eingehende Kante → linker Dot. */
  hasIncoming: boolean;
  /** Hat eine ausgehende Kante → rechter Dot. */
  hasOutgoing: boolean;
}

/** Ein Chip = ein Lineage-Objekt. */
export interface SchematicChip {
  id: string;
  label: string;
  /** Anzeige-Layer ("Source", "Harmonization", …). */
  layer: string;
  /** Stabiler Layer-Key fürs x-Banding (ELK layerConstraint). */
  laneKey: string;
  /** Reihenfolge des Layers entlang der Achse. */
  laneOrder: number;
  layerCode?: string;
  role?: string;
  /** Quellsystem ("DEMO", "Datasphere", …) — im Mockup die "Platform". */
  system?: string;
  space?: string;
  dqStatus?: string;
  hasContract: boolean;
  hasBoundaryContract: boolean;
  hasInternalGate: boolean;
  coverageFlag?: string;
  pins: SchematicPin[];
}

/** Eine Trace = eine Pin-zu-Pin-Kante. */
export interface SchematicEdge {
  id: string;
  fromNode: string;
  fromPin: string;
  toNode: string;
  toPin: string;
  /** 'direct' → durchgezogen, 'derived' → gestrichelt (transformiert). */
  kind: 'direct' | 'derived';
  /** Ursprünglicher edgeType (direct|computed|passthrough|…). */
  edgeType: ColumnEdgeType;
  /** Farbe nach edgeType (konsistent mit der bestehenden Map). */
  color: string;
  /** Transformations-Ausdruck für den Inspector-Codeblock. */
  expression?: string;
}

/** Objekt-zu-Objekt-Kante für den Object-Level-Modus. */
export interface ObjectEdge {
  from: string;
  to: string;
}

export interface SchematicModel {
  chips: SchematicChip[];
  edges: SchematicEdge[];
  /**
   * Deduplizierte Objekt-Kanten für den Object-Mode: Vereinigung der echten
   * Objekt-Edges (data.edges) und der aus Column-Edges abgeleiteten Paare —
   * so bleibt der Objekt-Graph auch dort vollständig, wo Spalten-Lineage fehlt.
   */
  objectEdges: ObjectEdge[];
  /** Stabiler Pin-Key (`columnId`) → Pin-Index für Trace-Highlighting. */
  pinKeyOf: (node: string, pin: string) => string;
}

function isDerived(edgeType: ColumnEdgeType): boolean {
  // Alles, was nicht "direct" ist und eine Transformation impliziert, gilt als
  // abgeleitet (gestrichelte Trace). 'direct' ist die einzige 1:1-Abbildung.
  return edgeType !== 'direct';
}

// Layer-Rang fürs x-Banding (links → rechts). deriveLane liefert nur für die
// Lib-Codes (r/ic/bc/s) eine Ordnung; reale Extrakte nutzen aber sprechende
// Layer-Namen bzw. Codes wie S/H/B (Source/Harmonization/Business), die dort auf
// 50 fielen. Hier rangieren wir primär nach Namens-Keywords (eindeutig) und
// fallen sonst auf deriveLane.order zurück.
const LANE_KEYWORDS: Array<[number, string[]]> = [
  [0, ['source', 'raw', 'landing', 'inbound', 'ingest', 'bronze', 'staging']],
  [1, ['harmoniz', 'integrat', 'core', 'cleans', 'silver', 'transform', 'curated']],
  [2, ['business', 'mart', 'serving', 'consum', 'output', 'semantic', 'gold', 'report', 'analyt']],
];

function laneRank(node: LineageNode, fallback: number): number {
  const hay = `${node.layer ?? ''} ${node.role ?? ''}`.toLowerCase();
  for (const [rank, words] of LANE_KEYWORDS) {
    if (words.some(w => hay.includes(w))) return rank;
  }
  return fallback;
}

function columnName(col: string | LineageColumn): string {
  return typeof col === 'string' ? col : col.name || col.label || '';
}

function columnType(col: string | LineageColumn): string | undefined {
  if (typeof col === 'string') return undefined;
  return col.data_type || col.type || undefined;
}

/**
 * Flacht einen per-Objekt-Column-Index (`ColumnIndexByObject`, wie ihn
 * /api/lineage/columns je Objekt liefert) in eine deduplizierte Kantenliste.
 * Erlaubt das Board ohne neuen API-Endpunkt aus den vorhandenen Hooks zu
 * speisen (upstream/downstream beschreiben dieselbe Kante doppelt).
 */
export function flattenColumnIndex(
  index: Record<string, Record<string, ColumnLineageEntry>>,
): RawColumnEdge[] {
  const seen = new Map<string, RawColumnEdge>();
  const put = (e: RawColumnEdge) => {
    const key = columnEdgeId(e.source, e.sourceColumn, e.target, e.targetColumn, e.edgeType || 'direct');
    if (!seen.has(key)) seen.set(key, e);
  };
  for (const [object, columns] of Object.entries(index)) {
    for (const [column, entry] of Object.entries(columns)) {
      for (const step of entry.upstream ?? []) {
        put({
          source: step.object,
          sourceColumn: step.column,
          target: object,
          targetColumn: column,
          edgeType: step.edgeType,
          expression: step.expression,
        });
      }
      for (const step of entry.downstream ?? []) {
        put({
          source: object,
          sourceColumn: column,
          target: step.object,
          targetColumn: step.column,
          edgeType: step.edgeType,
          expression: step.expression,
        });
      }
    }
  }
  return [...seen.values()];
}

/**
 * Baut das Schaltplan-Modell aus annotierten Lineage-Nodes (/api/lineage) und
 * einer flachen Column-Kantenliste. Pins folgen der Spaltenreihenfolge des
 * Nodes; Spalten, die nur in Kanten vorkommen, werden defensiv ergänzt.
 */
export function buildSchematicModel(
  nodes: LineageNode[],
  columnEdges: RawColumnEdge[],
  objectEdges: ReadonlyArray<{ source: string; target: string }> = [],
): SchematicModel {
  const incoming = new Set<string>();
  const outgoing = new Set<string>();
  const extraColumns = new Map<string, Set<string>>();
  const nodeIds = new Set(nodes.map(n => n.id));

  // Objekt-Kanten: echte data.edges ∪ aus Column-Edges abgeleitete Paare,
  // dedupliziert, ohne Self-Loops, beide Enden bekannt.
  const objSeen = new Set<string>();
  const objectPairs: ObjectEdge[] = [];
  const addObjectPair = (from: string, to: string) => {
    if (!from || !to || from === to) return;
    if (!nodeIds.has(from) || !nodeIds.has(to)) return;
    const key = `${from}${to}`;
    if (objSeen.has(key)) return;
    objSeen.add(key);
    objectPairs.push({ from, to });
  };
  for (const e of objectEdges) addObjectPair(e.source, e.target);

  const edges: SchematicEdge[] = [];
  const edgeSeen = new Set<string>();
  for (const e of columnEdges) {
    if (!e.source || !e.target || !e.sourceColumn || !e.targetColumn) continue;
    const edgeType = (e.edgeType || 'direct') as ColumnEdgeType;
    const id = columnEdgeId(e.source, e.sourceColumn, e.target, e.targetColumn, edgeType);
    if (edgeSeen.has(id)) continue;
    edgeSeen.add(id);

    outgoing.add(columnId(e.source, e.sourceColumn));
    incoming.add(columnId(e.target, e.targetColumn));
    addObjectPair(e.source, e.target);

    // Spalten, die im Node nicht gelistet sind, trotzdem als Pin zeigen.
    if (nodeIds.has(e.source)) addExtra(extraColumns, e.source, e.sourceColumn);
    if (nodeIds.has(e.target)) addExtra(extraColumns, e.target, e.targetColumn);

    edges.push({
      id,
      fromNode: e.source,
      fromPin: e.sourceColumn,
      toNode: e.target,
      toPin: e.targetColumn,
      kind: isDerived(edgeType) ? 'derived' : 'direct',
      edgeType,
      color: edgeTypeColor(edgeType),
      expression: e.expression,
    });
  }

  const chips: SchematicChip[] = nodes.map(n => {
    const lane = deriveLane(n);
    const declared = (n.columns ?? []).map(columnName).filter(Boolean);
    const types = new Map<string, string | undefined>();
    for (const col of n.columns ?? []) {
      const name = columnName(col);
      if (name) types.set(name, columnType(col));
    }
    // Reihenfolge: deklarierte Spalten zuerst, dann nur-in-Kanten-Spalten.
    const ordered = [...declared];
    for (const extra of extraColumns.get(n.id) ?? []) {
      if (!types.has(extra)) ordered.push(extra);
    }
    const pins: SchematicPin[] = ordered.map(name => ({
      id: name,
      label: name,
      dataType: types.get(name),
      hasIncoming: incoming.has(columnId(n.id, name)),
      hasOutgoing: outgoing.has(columnId(n.id, name)),
    }));

    return {
      id: n.id,
      label: n.label || n.id,
      layer: lane.label,
      laneKey: lane.key,
      laneOrder: laneRank(n, lane.order),
      layerCode: n.layerCode,
      role: n.role,
      system: n.system,
      space: n.space,
      dqStatus: n.dq_status,
      hasContract: Boolean(n.has_contract),
      hasBoundaryContract: Boolean(n.has_boundary_contract),
      hasInternalGate: Boolean(n.has_internal_gate),
      coverageFlag: n.coverage_flag,
      pins,
    };
  });

  return {
    chips,
    edges,
    objectEdges: objectPairs,
    pinKeyOf: columnId,
  };
}

function addExtra(map: Map<string, Set<string>>, object: string, column: string) {
  const set = map.get(object) ?? new Set<string>();
  set.add(column);
  map.set(object, set);
}

/** Ergebnis der Kanten-Partitionierung für den hybriden (per-Node) Modus. */
export interface PartitionedEdges {
  /** Pin-zu-Pin-Kanten — nur zwischen zwei expandierten Chips. */
  columnEdges: SchematicEdge[];
  /** Aggregierte Objekt-zu-Objekt-Kanten für alle übrigen Paare. */
  objectEdges: ObjectEdge[];
}

// ' ' als Separator: kommt in Objekt-IDs nicht vor.
const pairKey = (from: string, to: string) => `${from} ${to}`;

/**
 * Partitioniert die Kanten des Modells nach dem hybriden Expansions-Zustand:
 * Ein Knotenpaar wird genau dann auf Spalten-Ebene (Pin-zu-Pin) gezeichnet,
 * wenn **beide** Enden expandiert sind und mindestens eine Column-Edge tragen;
 * sonst aggregiert es zu einer einzigen Objekt-Kante.
 *
 * Bewusst rein und an **einer** Stelle, damit Graph-Aufbau (buildElkGraph) und
 * Ergebnis-Mapping (mapElkResult) dieselbe Aufteilung sehen und nie driften.
 */
export function partitionEdges(
  model: SchematicModel,
  expanded: ReadonlySet<string>,
): PartitionedEdges {
  const bothExpanded = (a: string, b: string) => expanded.has(a) && expanded.has(b);

  const columnEdges = model.edges.filter(e => bothExpanded(e.fromNode, e.toNode));
  // Paare, die tatsächlich als Spalten-Kanten gezeichnet werden. Nur diese
  // werden aus den Objekt-Kanten entfernt — ein voll expandiertes Paar ohne
  // Column-Edges (nur grobe Objekt-Edge) bleibt sichtbar.
  const columnPairs = new Set(columnEdges.map(e => pairKey(e.fromNode, e.toNode)));

  const objectEdges = model.objectEdges.filter(o => !columnPairs.has(pairKey(o.from, o.to)));

  return { columnEdges, objectEdges };
}
