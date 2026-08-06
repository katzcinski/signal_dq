/**
 * Click-to-trace: vollständige Schaltkreis-Verfolgung über das in-memory
 * Schaltplan-Modell. Reine BFS über die Pin-Adjazenz (upstream + downstream),
 * liefert die Pin-Keys und Kanten-IDs des isolierten Pfads fürs Highlighting.
 *
 * Bewusst synchron: das Board hält den vollen Column-Graphen, daher braucht es
 * nicht die lazy-fetchende traceColumnLineage() aus lib/lineage.ts (die ist für
 * den per-Objekt nachladenden Cytoscape-Pfad gedacht).
 */
import { columnId } from '@/lib/lineage';
import type { SchematicEdge, SchematicModel } from './model';

export interface CircuitTrace {
  /** Pin-Keys (columnId) auf dem Pfad. */
  pins: Set<string>;
  /** Kanten-IDs auf dem Pfad. */
  edges: Set<string>;
}

interface Link {
  edgeId: string;
  other: string;
}

function buildAdjacency(edges: SchematicEdge[]): Map<string, Link[]> {
  const adj = new Map<string, Link[]>();
  const add = (key: string, link: Link) => {
    const list = adj.get(key);
    if (list) list.push(link);
    else adj.set(key, [link]);
  };
  for (const e of edges) {
    const a = columnId(e.fromNode, e.fromPin);
    const b = columnId(e.toNode, e.toPin);
    add(a, { edgeId: e.id, other: b });
    add(b, { edgeId: e.id, other: a });
  }
  return adj;
}

/** Traced den vollen Schaltkreis ab einem Pin (beide Richtungen). */
export function traceCircuit(model: SchematicModel, node: string, pin: string): CircuitTrace {
  const adj = buildAdjacency(model.edges);
  const start = columnId(node, pin);
  const pins = new Set<string>([start]);
  const edges = new Set<string>();
  const queue: string[] = [start];

  while (queue.length) {
    const cur = queue.shift()!;
    for (const link of adj.get(cur) ?? []) {
      edges.add(link.edgeId);
      if (!pins.has(link.other)) {
        pins.add(link.other);
        queue.push(link.other);
      }
    }
  }
  return { pins, edges };
}
