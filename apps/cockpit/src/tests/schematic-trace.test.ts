import { describe, expect, it } from 'vitest';
import { buildSchematicModel, type RawColumnEdge } from '@/components/lineage/schematic/model';
import { traceCircuit } from '@/components/lineage/schematic/trace';
import { columnId } from '@/lib/lineage';
import type { LineageNode } from '@/types';

// Kette A -> B -> C plus ein Seitenzweig D -> C, der NICHT auf dem A-Pfad liegt.
const NODES: LineageNode[] = [
  { id: 'A', layer: 'Source', layerCode: 'r', columns: ['a1'] },
  { id: 'B', layer: 'Harmonization', layerCode: 'ic', columns: ['b1'] },
  { id: 'C', layer: 'Business', layerCode: 'bc', columns: ['c1', 'c2'] },
  { id: 'D', layer: 'Source', layerCode: 'r', columns: ['d1'] },
];
const EDGES: RawColumnEdge[] = [
  { source: 'A', sourceColumn: 'a1', target: 'B', targetColumn: 'b1', edgeType: 'direct' },
  { source: 'B', sourceColumn: 'b1', target: 'C', targetColumn: 'c1', edgeType: 'computed' },
  { source: 'D', sourceColumn: 'd1', target: 'C', targetColumn: 'c2', edgeType: 'direct' },
];
const model = buildSchematicModel(NODES, EDGES);

describe('traceCircuit', () => {
  it('follows the full circuit upstream and downstream from a mid-pin', () => {
    const trace = traceCircuit(model, 'B', 'b1');
    expect(trace.pins).toContain(columnId('A', 'a1'));
    expect(trace.pins).toContain(columnId('B', 'b1'));
    expect(trace.pins).toContain(columnId('C', 'c1'));
    expect(trace.edges.size).toBe(2);
  });

  it('does not pull in disconnected branches', () => {
    const trace = traceCircuit(model, 'A', 'a1');
    // A -> B -> C.c1 ist erreichbar; D -> C.c2 hängt an einer anderen Spalte.
    expect(trace.pins).not.toContain(columnId('D', 'd1'));
    expect(trace.pins).not.toContain(columnId('C', 'c2'));
  });

  it('traces only the connected side branch', () => {
    const trace = traceCircuit(model, 'C', 'c2');
    // c2 hängt nur an D.d1.
    expect(trace.pins).toContain(columnId('D', 'd1'));
    expect(trace.pins).not.toContain(columnId('A', 'a1'));
  });
});
