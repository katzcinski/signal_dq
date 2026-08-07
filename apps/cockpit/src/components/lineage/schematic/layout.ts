/**
 * ELK-Layout fürs Schaltplan-Board.
 *
 * Hybrid (per-Node): Jeder Chip wird entweder eingeklappt (portlos, objHeight)
 * oder expandiert (ein Port je Pin-Richtung, chipHeight) gelayoutet. ELK rechnet
 * Layered + orthogonales Routing. Ergebnis: positionierte Chips, Pin-Reihen-Y,
 * Polyline-Punkte je Spalten-Trace und je aggregierter Objekt-Kante.
 *
 * Aufgeteilt in pure Funktionen (buildElkGraph / mapElkResult) und den async
 * Runner (layoutSchematic), damit Graph-Aufbau und Ergebnis-Mapping ohne
 * laufende ELK-Engine deterministisch unit-testbar bleiben. Welche Kanten
 * Spalten- bzw. Objekt-Ebene sind, entscheidet die geteilte partitionEdges().
 */
import type { ELK as ElkInstance, ElkNode, ElkPort } from 'elkjs/lib/elk.bundled.js';
import { partitionEdges } from './model';
import type { SchematicChip, SchematicEdge, SchematicModel, SchematicPin } from './model';

/** Geometrie — an das Mockup angelehnt. */
export const GEO = {
  nodeWidth: 240,
  headerH: 58,
  padTop: 10,
  padBottom: 14,
  pinRowH: 26,
  objHeight: 64,
} as const;

export function chipHeight(pinCount: number): number {
  return GEO.headerH + GEO.padTop + pinCount * GEO.pinRowH + GEO.padBottom;
}

/** Y-Mitte einer Pin-Reihe relativ zur Chip-Oberkante. */
export function pinRowY(index: number): number {
  return GEO.headerH + GEO.padTop + index * GEO.pinRowH + GEO.pinRowH / 2;
}

// Stabile ID-Bausteine für ELK-Ports/-Kanten. ':' als Separator (Pin- und
// Objekt-IDs enthalten keine Doppelpunkte).
const SEP = ':';
const westPortId = (node: string, pin: string) => `${node}${SEP}${pin}${SEP}W`;
const eastPortId = (node: string, pin: string) => `${node}${SEP}${pin}${SEP}E`;
const OBJ_EDGE = 'objedge';
const objEdgeId = (from: string, to: string) => `${OBJ_EDGE}${SEP}${from}${SEP}${to}`;

const ROOT_OPTIONS: Record<string, string> = {
  'elk.algorithm': 'layered',
  'elk.direction': 'RIGHT',
  'elk.edgeRouting': 'ORTHOGONAL',
  // Layer-Bänder über laneOrder erzwingen, statt ELK rein topologisch ordnen
  // zu lassen — Source/Harmonization/Business fallen so in stabile x-Spalten.
  'elk.partitioning.activate': 'true',
  'elk.layered.spacing.nodeNodeBetweenLayers': '130',
  'elk.spacing.nodeNode': '36',
  'elk.layered.spacing.edgeNodeBetweenLayers': '24',
  'elk.layered.nodePlacement.strategy': 'NETWORK_SIMPLEX',
  'elk.layered.crossingMinimization.semiInteractive': 'true',
};

/**
 * Baut den ELK-Eingabegraphen. Pure — keine ELK-Ausführung.
 * Expandierte Chips: ein Port je Pin-Richtung, Kanten Port→Port zwischen zwei
 * expandierten Knoten. Alle übrigen Paare: portlose Endknoten, aggregierte
 * Objekt-zu-Objekt-Kante.
 */
export function buildElkGraph(model: SchematicModel, expanded: ReadonlySet<string>): ElkNode {
  const { columnEdges, objectEdges } = partitionEdges(model, expanded);

  const children: ElkNode[] = model.chips.map((chip): ElkNode => {
    if (expanded.has(chip.id)) {
      const ports: ElkPort[] = [];
      chip.pins.forEach((pin, idx) => {
        const y = pinRowY(idx);
        if (pin.hasIncoming) ports.push(port(westPortId(chip.id, pin.id), 'WEST', 0, y));
        if (pin.hasOutgoing) ports.push(port(eastPortId(chip.id, pin.id), 'EAST', GEO.nodeWidth, y));
      });
      return {
        id: chip.id,
        width: GEO.nodeWidth,
        height: chipHeight(chip.pins.length),
        layoutOptions: {
          'elk.portConstraints': 'FIXED_POS',
          'elk.partitioning.partition': String(chip.laneOrder),
        },
        ports,
      };
    }
    return {
      id: chip.id,
      width: GEO.nodeWidth,
      height: GEO.objHeight,
      layoutOptions: { 'elk.partitioning.partition': String(chip.laneOrder) },
    };
  });

  const edges = [
    ...columnEdges.map(e => ({
      id: e.id,
      sources: [eastPortId(e.fromNode, e.fromPin)],
      targets: [westPortId(e.toNode, e.toPin)],
    })),
    // Objekt-Kanten hängen am Knoten selbst (kein Port) — ELK routet sie an den
    // Knotenrand, auch wenn das Ziel als expandierter Chip feste Ports trägt.
    ...objectEdges.map(e => ({
      id: objEdgeId(e.from, e.to),
      sources: [e.from],
      targets: [e.to],
    })),
  ];

  return { id: 'root', layoutOptions: ROOT_OPTIONS, children, edges };
}

function port(id: string, side: 'WEST' | 'EAST', x: number, y: number): ElkPort {
  return { id, x, y, width: 1, height: 1, layoutOptions: { 'elk.port.side': side } };
}

// ---- Ergebnis-Mapping ----

export interface PositionedPin extends SchematicPin {
  /** Reihen-Y relativ zur Chip-Oberkante. */
  rowY: number;
}

export interface PositionedChip extends Omit<SchematicChip, 'pins'> {
  x: number;
  y: number;
  width: number;
  height: number;
  /** Spalten ausgeklappt (Ports/Pin-Reihen) oder eingeklappt (Objekt-Karte). */
  expanded: boolean;
  pins: PositionedPin[];
}

export interface RoutedEdge extends SchematicEdge {
  /** Absolute Polyline-Punkte (orthogonal) für den <path>. */
  points: Array<{ x: number; y: number }>;
}

/** Aggregierte Objekt-zu-Objekt-Kante. */
export interface RoutedObjectEdge {
  id: string;
  fromNode: string;
  toNode: string;
  points: Array<{ x: number; y: number }>;
}

export interface SchematicLayout {
  chips: PositionedChip[];
  /** Pin-zu-Pin-Traces zwischen expandierten Chips. */
  edges: RoutedEdge[];
  /** Aggregierte Objekt-Kanten für alle übrigen Paare. */
  objectEdges: RoutedObjectEdge[];
  width: number;
  height: number;
}

function sectionPoints(node: ElkNode, edgeId: string): Array<{ x: number; y: number }> {
  const edge = (node.edges ?? []).find(e => e.id === edgeId);
  const section = edge?.sections?.[0];
  if (!section) return [];
  return [section.startPoint, ...(section.bendPoints ?? []), section.endPoint].map(p => ({
    x: p.x,
    y: p.y,
  }));
}

/**
 * Mappt das ELK-Ergebnis zurück aufs Schaltplan-Modell. Pure — nimmt den von
 * ELK befüllten Graphen, das Quellmodell und denselben Expansions-Zustand wie
 * buildElkGraph, damit die Kanten-Partition identisch ist.
 */
export function mapElkResult(
  model: SchematicModel,
  expanded: ReadonlySet<string>,
  result: ElkNode,
): SchematicLayout {
  const posById = new Map<string, ElkNode>();
  for (const c of result.children ?? []) posById.set(c.id, c);

  const chips: PositionedChip[] = model.chips.map(chip => {
    const p = posById.get(chip.id);
    const { pins, ...rest } = chip;
    const isExpanded = expanded.has(chip.id);
    return {
      ...rest,
      expanded: isExpanded,
      x: p?.x ?? 0,
      y: p?.y ?? 0,
      width: p?.width ?? GEO.nodeWidth,
      height: p?.height ?? (isExpanded ? chipHeight(chip.pins.length) : GEO.objHeight),
      pins: pins.map((pin, idx) => ({ ...pin, rowY: pinRowY(idx) })),
    };
  });

  const { columnEdges, objectEdges: objPairs } = partitionEdges(model, expanded);

  const edges: RoutedEdge[] = columnEdges.map(e => ({
    ...e,
    points: sectionPoints(result, e.id),
  }));

  const objectEdges: RoutedObjectEdge[] = objPairs.map(o => ({
    id: objEdgeId(o.from, o.to),
    fromNode: o.from,
    toNode: o.to,
    points: sectionPoints(result, objEdgeId(o.from, o.to)),
  }));

  return {
    chips,
    edges,
    objectEdges,
    width: result.width ?? 0,
    height: result.height ?? 0,
  };
}

let elkInstance: ElkInstance | null = null;
async function getElk(): Promise<ElkInstance> {
  if (!elkInstance) {
    const { default: ELK } = await import('elkjs/lib/elk.bundled.js');
    elkInstance = new ELK();
  }
  return elkInstance;
}

/** Async Layout-Runner: baut den Graphen, lässt ELK rechnen, mappt zurück. */
export async function layoutSchematic(
  model: SchematicModel,
  expanded: ReadonlySet<string>,
): Promise<SchematicLayout> {
  const graph = buildElkGraph(model, expanded);
  const result = await (await getElk()).layout(graph);
  return mapElkResult(model, expanded, result);
}
