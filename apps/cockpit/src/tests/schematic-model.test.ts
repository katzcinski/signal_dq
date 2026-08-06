import { describe, expect, it } from 'vitest';
import {
  buildSchematicModel,
  flattenColumnIndex,
  partitionEdges,
  type RawColumnEdge,
} from '@/components/lineage/schematic/model';
import { columnId } from '@/lib/lineage';
import type { LineageNode } from '@/types';

// Fixture nach dem Vorbild des Schaltplan-Mockups (Source → Harmonized → Output),
// inkl. einer abgeleiteten Kante mit Transformations-Expression.
const NODES: LineageNode[] = [
  {
    id: 'DS_INB', label: 'DS_INB_SALES', layer: 'Source', layerCode: 'r', role: 'source',
    system: 'S/4HANA', space: 'S_SP1', columns: ['VBELN', 'NETWR'], dq_status: 'pass',
  },
  {
    id: 'DS_HRM', label: 'DS_HRM_SALES', layer: 'Harmonization', layerCode: 'ic', role: 'harmonized',
    system: 'Datasphere', space: 'H_SP1', columns: ['SALES_DOC', 'NET_VALUE_USD'], dq_status: 'warn',
    has_contract: true, has_boundary_contract: true,
  },
];

const EDGES: RawColumnEdge[] = [
  { source: 'DS_INB', sourceColumn: 'VBELN', target: 'DS_HRM', targetColumn: 'SALES_DOC', edgeType: 'direct' },
  {
    source: 'DS_INB', sourceColumn: 'NETWR', target: 'DS_HRM', targetColumn: 'NET_VALUE_USD',
    edgeType: 'computed', expression: "CURRENCY_CONVERSION(NETWR, target:'USD')",
  },
];

describe('buildSchematicModel', () => {
  const model = buildSchematicModel(NODES, EDGES);

  it('maps nodes to chips with lane + platform + DQ/contract annotation', () => {
    const hrm = model.chips.find(c => c.id === 'DS_HRM')!;
    expect(hrm.layer).toBe('Harmonization');
    expect(hrm.laneKey).toBe('ic');
    expect(hrm.system).toBe('Datasphere');
    expect(hrm.dqStatus).toBe('warn');
    expect(hrm.hasContract).toBe(true);
    expect(hrm.hasBoundaryContract).toBe(true);
  });

  it('derives pin direction dots from edges', () => {
    const inb = model.chips.find(c => c.id === 'DS_INB')!;
    const vbeln = inb.pins.find(p => p.id === 'VBELN')!;
    expect(vbeln.hasOutgoing).toBe(true);
    expect(vbeln.hasIncoming).toBe(false);

    const hrm = model.chips.find(c => c.id === 'DS_HRM')!;
    const salesDoc = hrm.pins.find(p => p.id === 'SALES_DOC')!;
    expect(salesDoc.hasIncoming).toBe(true);
    expect(salesDoc.hasOutgoing).toBe(false);
  });

  it('classifies direct vs derived and carries the transform expression', () => {
    const direct = model.edges.find(e => e.fromPin === 'VBELN')!;
    expect(direct.kind).toBe('direct');
    expect(direct.expression).toBeUndefined();

    const derived = model.edges.find(e => e.fromPin === 'NETWR')!;
    expect(derived.kind).toBe('derived');
    expect(derived.edgeType).toBe('computed');
    expect(derived.expression).toContain('CURRENCY_CONVERSION');
  });

  it('keeps pins in declared column order', () => {
    const inb = model.chips.find(c => c.id === 'DS_INB')!;
    expect(inb.pins.map(p => p.id)).toEqual(['VBELN', 'NETWR']);
  });

  it('ranks lanes source < harmonization < business by layer name', () => {
    const m = buildSchematicModel(
      [
        { id: 'S', layer: 'Source', layerCode: 'S', columns: [] },
        { id: 'H', layer: 'Harmonization', layerCode: 'H', columns: [] },
        { id: 'B', layer: 'Business', layerCode: 'B', columns: [] },
      ],
      [],
    );
    const order = (id: string) => m.chips.find(c => c.id === id)!.laneOrder;
    expect(order('S')).toBeLessThan(order('H'));
    expect(order('H')).toBeLessThan(order('B'));
  });

  it('unions real object edges with column-derived pairs', () => {
    // BUS hat keine Column-Edges, aber eine echte Objekt-Edge HRM -> BUS.
    const m = buildSchematicModel(
      [
        { id: 'INB', layer: 'Source', layerCode: 'r', columns: ['a'] },
        { id: 'HRM', layer: 'Harmonization', layerCode: 'ic', columns: ['b'] },
        { id: 'BUS', layer: 'Business', layerCode: 'bc', columns: ['c'] },
      ],
      [{ source: 'INB', sourceColumn: 'a', target: 'HRM', targetColumn: 'b', edgeType: 'direct' }],
      [
        { source: 'INB', target: 'HRM' }, // Duplikat zur Column-abgeleiteten Kante
        { source: 'HRM', target: 'BUS' }, // nur als Objekt-Edge vorhanden
        { source: 'BUS', target: 'BUS' }, // Self-Loop -> ignoriert
        { source: 'X', target: 'HRM' },   // unbekannter Knoten -> ignoriert
      ],
    );
    const pairs = m.objectEdges.map(e => `${e.from}>${e.to}`).sort();
    expect(pairs).toEqual(['HRM>BUS', 'INB>HRM']);
  });

  it('exposes a stable pin key matching columnId', () => {
    expect(model.pinKeyOf('DS_INB', 'VBELN')).toBe(columnId('DS_INB', 'VBELN'));
  });
});

describe('partitionEdges', () => {
  const model = buildSchematicModel(NODES, EDGES);

  it('draws pin-to-pin only when both ends are expanded', () => {
    const { columnEdges, objectEdges } = partitionEdges(model, new Set(['DS_INB', 'DS_HRM']));
    expect(columnEdges).toHaveLength(2);
    // Das Paar ist voll über Spalten-Kanten abgebildet → keine Objekt-Kante.
    expect(objectEdges).toHaveLength(0);
  });

  it('aggregates to a single object edge when only one side is expanded', () => {
    const { columnEdges, objectEdges } = partitionEdges(model, new Set(['DS_INB']));
    expect(columnEdges).toHaveLength(0);
    expect(objectEdges.map(o => `${o.from}>${o.to}`)).toEqual(['DS_INB>DS_HRM']);
  });

  it('aggregates everything when nothing is expanded', () => {
    const { columnEdges, objectEdges } = partitionEdges(model, new Set());
    expect(columnEdges).toHaveLength(0);
    expect(objectEdges).toHaveLength(1);
  });

  it('keeps a coarse object edge between two expanded nodes that lack column lineage', () => {
    // HRM -> BUS existiert nur als grobe Objekt-Edge (keine Column-Edges).
    const m = buildSchematicModel(
      [
        { id: 'HRM', layer: 'Harmonization', layerCode: 'ic', columns: ['b'] },
        { id: 'BUS', layer: 'Business', layerCode: 'bc', columns: ['c'] },
      ],
      [],
      [{ source: 'HRM', target: 'BUS' }],
    );
    const { columnEdges, objectEdges } = partitionEdges(m, new Set(['HRM', 'BUS']));
    expect(columnEdges).toHaveLength(0);
    expect(objectEdges.map(o => `${o.from}>${o.to}`)).toEqual(['HRM>BUS']);
  });
});

describe('flattenColumnIndex', () => {
  it('dedupes upstream/downstream into a single edge list', () => {
    // Dieselbe Kante taucht als downstream von INB und upstream von HRM auf.
    const index = {
      DS_INB: {
        NETWR: {
          upstream: [],
          downstream: [{ object: 'DS_HRM', column: 'NET_VALUE_USD', edgeType: 'computed' as const, expression: 'X' }],
        },
      },
      DS_HRM: {
        NET_VALUE_USD: {
          upstream: [{ object: 'DS_INB', column: 'NETWR', edgeType: 'computed' as const, expression: 'X' }],
          downstream: [],
        },
      },
    };
    const edges = flattenColumnIndex(index);
    expect(edges).toHaveLength(1);
    expect(edges[0]).toMatchObject({
      source: 'DS_INB', sourceColumn: 'NETWR', target: 'DS_HRM', targetColumn: 'NET_VALUE_USD',
    });
  });
});
