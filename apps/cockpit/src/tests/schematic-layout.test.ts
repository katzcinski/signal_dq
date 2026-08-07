import { describe, expect, it } from 'vitest';
import { buildSchematicModel, type RawColumnEdge } from '@/components/lineage/schematic/model';
import {
  buildElkGraph,
  chipHeight,
  GEO,
  layoutSchematic,
  mapElkResult,
  pinRowY,
} from '@/components/lineage/schematic/layout';
import type { ElkNode } from 'elkjs/lib/elk.bundled.js';
import type { LineageNode } from '@/types';

const NODES: LineageNode[] = [
  { id: 'INB', layer: 'Source', layerCode: 'r', columns: ['VBELN', 'NETWR'] },
  { id: 'HRM', layer: 'Harmonization', layerCode: 'ic', columns: ['SALES_DOC', 'NET_VALUE_USD'] },
];
const EDGES: RawColumnEdge[] = [
  { source: 'INB', sourceColumn: 'VBELN', target: 'HRM', targetColumn: 'SALES_DOC', edgeType: 'direct' },
  {
    source: 'INB', sourceColumn: 'NETWR', target: 'HRM', targetColumn: 'NET_VALUE_USD',
    edgeType: 'computed', expression: 'CONV(NETWR)',
  },
];
const model = buildSchematicModel(NODES, EDGES);
const ALL = new Set(['INB', 'HRM']);
const NONE = new Set<string>();

describe('geometry', () => {
  it('stacks pin rows below the header', () => {
    expect(pinRowY(0)).toBe(GEO.headerH + GEO.padTop + GEO.pinRowH / 2);
    expect(pinRowY(1) - pinRowY(0)).toBe(GEO.pinRowH);
    expect(chipHeight(2)).toBe(GEO.headerH + GEO.padTop + 2 * GEO.pinRowH + GEO.padBottom);
  });
});

describe('buildElkGraph (both expanded)', () => {
  const graph = buildElkGraph(model, ALL);

  it('emits a WEST port for incoming and EAST for outgoing pins', () => {
    const inb = graph.children!.find(c => c.id === 'INB')!;
    // INB.VBELN only feeds downstream -> EAST port, no WEST.
    expect(inb.ports!.some(p => p.id === 'INB:VBELN:E')).toBe(true);
    expect(inb.ports!.some(p => p.id === 'INB:VBELN:W')).toBe(false);

    const hrm = graph.children!.find(c => c.id === 'HRM')!;
    expect(hrm.ports!.some(p => p.id === 'HRM:SALES_DOC:W')).toBe(true);
  });

  it('pins ports at fixed positions and the chip into its lane partition', () => {
    const inb = graph.children!.find(c => c.id === 'INB')!;
    expect(inb.layoutOptions!['elk.portConstraints']).toBe('FIXED_POS');
    expect(inb.layoutOptions!['elk.partitioning.partition']).toBe('0'); // raw -> order 0
    const eastPort = inb.ports!.find(p => p.id === 'INB:VBELN:E')!;
    expect(eastPort.x).toBe(GEO.nodeWidth);
    expect(eastPort.y).toBe(pinRowY(0));
  });

  it('routes edges port-to-port', () => {
    const e = graph.edges!.find(x => x.id === model.edges[0].id)!;
    expect(e.sources).toEqual(['INB:VBELN:E']);
    expect(e.targets).toEqual(['HRM:SALES_DOC:W']);
  });
});

describe('buildElkGraph (none expanded)', () => {
  it('drops ports and aggregates column traces to one object edge', () => {
    const graph = buildElkGraph(model, NONE);
    const hrm = graph.children!.find(c => c.id === 'HRM')!;
    expect(hrm.ports).toBeUndefined();
    expect(graph.edges).toHaveLength(1);
    expect(graph.edges![0].id).toBe('objedge:INB:HRM');
    expect(graph.edges![0].sources).toEqual(['INB']);
  });
});

describe('buildElkGraph (hybrid — one side expanded)', () => {
  it('routes a mixed pair as a single aggregated object edge, not pin-to-pin', () => {
    // Nur INB expandiert: HRM bleibt portlos → das Paar aggregiert.
    const graph = buildElkGraph(model, new Set(['INB']));
    const inb = graph.children!.find(c => c.id === 'INB')!;
    const hrm = graph.children!.find(c => c.id === 'HRM')!;
    // INB hat Ports (für eigene Spalten-Lineage-Dots), HRM nicht.
    expect(inb.ports!.length).toBeGreaterThan(0);
    expect(hrm.ports).toBeUndefined();
    // Keine Pin-zu-Pin-Kante, sondern eine aggregierte Objekt-Kante.
    expect(graph.edges).toHaveLength(1);
    expect(graph.edges![0].id).toBe('objedge:INB:HRM');
    expect(graph.edges![0].sources).toEqual(['INB']);
    expect(graph.edges![0].targets).toEqual(['HRM']);
  });
});

describe('mapElkResult', () => {
  it('lifts chip positions, pin rowY and edge polyline points', () => {
    // Synthetisches ELK-Ergebnis ohne echte Engine.
    const result: ElkNode = {
      id: 'root',
      width: 600,
      height: 200,
      children: [
        { id: 'INB', x: 0, y: 0, width: GEO.nodeWidth, height: chipHeight(2) },
        { id: 'HRM', x: 360, y: 20, width: GEO.nodeWidth, height: chipHeight(2) },
      ],
      edges: [
        {
          id: model.edges[0].id,
          sources: ['INB VBELN E'],
          targets: ['HRM SALES_DOC W'],
          sections: [{ id: 's', startPoint: { x: 240, y: 81 }, bendPoints: [{ x: 300, y: 81 }], endPoint: { x: 360, y: 101 } }],
        },
      ],
    };
    const layout = mapElkResult(model, ALL, result);
    expect(layout.width).toBe(600);
    const hrm = layout.chips.find(c => c.id === 'HRM')!;
    expect(hrm.x).toBe(360);
    expect(hrm.expanded).toBe(true);
    expect(hrm.pins[0].rowY).toBe(pinRowY(0));
    const edge = layout.edges.find(e => e.id === model.edges[0].id)!;
    expect(edge.points).toEqual([
      { x: 240, y: 81 },
      { x: 300, y: 81 },
      { x: 360, y: 101 },
    ]);
    expect(edge.kind).toBe('direct');
  });
});

describe('layoutSchematic (ELK integration)', () => {
  it('lays Source left of Harmonization and routes every trace', async () => {
    const layout = await layoutSchematic(model, ALL);
    const inb = layout.chips.find(c => c.id === 'INB')!;
    const hrm = layout.chips.find(c => c.id === 'HRM')!;
    expect(inb.x).toBeLessThan(hrm.x); // RIGHT direction, source partition first
    expect(layout.width).toBeGreaterThan(0);
    for (const e of layout.edges) {
      expect(e.points.length).toBeGreaterThanOrEqual(2);
    }
  });

  it('routes an aggregated object edge into a one-sided-expanded pair', async () => {
    // Nur INB expandiert → das Paar INB→HRM aggregiert; ELK muss die Objekt-
    // Kante trotz fester Ports an INB an den HRM-Rand routen.
    const layout = await layoutSchematic(model, new Set(['INB']));
    expect(layout.edges).toHaveLength(0);
    expect(layout.objectEdges).toHaveLength(1);
    expect(layout.objectEdges[0].points.length).toBeGreaterThanOrEqual(2);
    expect(layout.chips.find(c => c.id === 'INB')!.expanded).toBe(true);
    expect(layout.chips.find(c => c.id === 'HRM')!.expanded).toBe(false);
  });
});
