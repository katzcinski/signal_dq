import { describe, expect, it, vi } from 'vitest';
import {
  buildColumnGraphElements,
  columnEdgeId,
  columnId,
  deriveLane,
  traceColumnLineage,
  type ColumnIndexByObject,
} from '@/lib/lineage';

describe('lineage lane derivation', () => {
  it('uses layerCode as the lane key and layer as the label', () => {
    expect(deriveLane({ layer: 'serving', layerCode: 's', role: 'fact' })).toEqual({
      key: 's',
      label: 'serving',
      code: 's',
      order: 3,
    });
  });

  it('falls back to role when layer metadata is absent', () => {
    expect(deriveLane({ layer: '', role: 'flow' })).toEqual({
      key: 'flow',
      label: 'flow',
      code: undefined,
      order: 50,
    });
  });
});

describe('column lineage graph builder', () => {
  it('builds compound object/column nodes and deduped typed edges', () => {
    const indexes: ColumnIndexByObject = {
      Sales: {
        Amount: {
          upstream: [],
          downstream: [{ object: 'Summary', column: 'TotalAmount', edgeType: 'computed' }],
        },
      },
      Summary: {
        TotalAmount: {
          upstream: [{ object: 'Sales', column: 'Amount', edgeType: 'computed', expression: 'SUM(Amount)' }],
          downstream: [],
        },
      },
    };

    const graph = buildColumnGraphElements(indexes, { Sales: { label: 'Sales' }, Summary: { label: 'Summary' } });
    const objectNodes = graph.nodes.filter(n => n.kind === 'object');
    const columnNodes = graph.nodes.filter(n => n.kind === 'column');
    const columnEdges = graph.edges.filter(e => e.kind === 'column');
    const aggregateEdges = graph.edges.filter(e => e.kind === 'aggregate');

    expect(objectNodes.map(n => n.id).sort()).toEqual(['Sales', 'Summary']);
    expect(columnNodes.map(n => n.id).sort()).toEqual([
      columnId('Sales', 'Amount'),
      columnId('Summary', 'TotalAmount'),
    ]);
    expect(columnEdges).toHaveLength(1);
    expect(columnEdges[0]).toMatchObject({
      id: columnEdgeId('Sales', 'Amount', 'Summary', 'TotalAmount', 'computed'),
      edgeType: 'computed',
      expression: 'SUM(Amount)',
    });
    expect(aggregateEdges).toEqual([{ id: 'agg:Sales->Summary', source: 'Sales', target: 'Summary', kind: 'aggregate', count: 1 }]);
  });
});

describe('column lineage tracing', () => {
  it('lazy-loads neighbor indexes and prevents cycles', async () => {
    const seed: ColumnIndexByObject = {
      Summary: {
        TotalAmount: {
          upstream: [{ object: 'Sales', column: 'Amount', edgeType: 'computed' }],
          downstream: [],
        },
      },
    };
    const fetchIndex = vi.fn(async (objectId: string) => ({
      object: objectId,
      columns: objectId === 'Sales'
        ? {
            Amount: {
              upstream: [{ object: 'Raw', column: 'Amount', edgeType: 'direct' }],
              downstream: [{ object: 'Summary', column: 'TotalAmount', edgeType: 'computed' }],
            },
          }
        : {
            Amount: {
              upstream: [],
              downstream: [{ object: 'Sales', column: 'Amount', edgeType: 'direct' }],
            },
          },
    }));

    const result = await traceColumnLineage({ object: 'Summary', column: 'TotalAmount' }, seed, fetchIndex);

    expect(fetchIndex).toHaveBeenCalledTimes(2);
    expect(fetchIndex).toHaveBeenCalledWith('Sales');
    expect(fetchIndex).toHaveBeenCalledWith('Raw');
    expect([...result.columnIds].sort()).toEqual([
      columnId('Raw', 'Amount'),
      columnId('Sales', 'Amount'),
      columnId('Summary', 'TotalAmount'),
    ]);
    expect(result.edgeIds.has(columnEdgeId('Sales', 'Amount', 'Summary', 'TotalAmount', 'computed'))).toBe(true);
    expect(result.edgeIds.has(columnEdgeId('Raw', 'Amount', 'Sales', 'Amount', 'direct'))).toBe(true);
    expect(result.errors).toEqual([]);
  });
});
