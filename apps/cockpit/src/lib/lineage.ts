import type {
  ColumnEdgeType,
  ColumnLineageEntry,
  ColumnLineageObjectResponse,
  ColumnLineageStep,
  LineageNode,
} from '@/types';

export const COLUMN_ID_SEPARATOR = '\u241f';

const LAYER_ORDER: Record<string, number> = {
  r: 0,
  raw: 0,
  ic: 1,
  integrated_core: 1,
  bc: 2,
  business_core: 2,
  s: 3,
  serving: 3,
  unknown: 99,
};

export interface LaneInfo {
  key: string;
  label: string;
  code?: string;
  order: number;
}

export function deriveLane(node: Pick<LineageNode, 'layer' | 'layerCode' | 'role'>): LaneInfo {
  const key = node.layerCode || node.layer || node.role || 'unknown';
  const label = node.layer || node.role || node.layerCode || 'unknown';
  const code = node.layerCode && node.layerCode !== label ? node.layerCode : undefined;
  const order = LAYER_ORDER[key] ?? LAYER_ORDER[label] ?? 50;
  return { key, label, code, order };
}

export function lineageNodeLabel(node: Pick<LineageNode, 'id' | 'label'>): string {
  return node.label || node.id;
}

export function columnId(object: string, column: string): string {
  return `${object}${COLUMN_ID_SEPARATOR}${column}`;
}

export function splitColumnId(id: string): { object: string; column: string } {
  const [object, ...rest] = id.split(COLUMN_ID_SEPARATOR);
  return { object, column: rest.join(COLUMN_ID_SEPARATOR) };
}

export function columnEdgeId(
  sourceObject: string,
  sourceColumn: string,
  targetObject: string,
  targetColumn: string,
  edgeType: string,
): string {
  return `col:${columnId(sourceObject, sourceColumn)}->${columnId(targetObject, targetColumn)}:${edgeType || 'direct'}`;
}

export function edgeTypeColor(edgeType: ColumnEdgeType | undefined): string {
  switch (edgeType) {
    case 'direct':
      return '#2da44e';
    case 'computed':
      return '#d97706';
    case 'passthrough':
      return '#7f8c9b';
    default:
      return '#8b949e';
  }
}

export interface ColumnGraphNodeData {
  id: string;
  label: string;
  kind: 'object' | 'column';
  parent?: string;
  object?: string;
  column?: string;
  layer?: string;
  layerCode?: string;
  role?: string;
}

export interface ColumnGraphEdgeData {
  id: string;
  source: string;
  target: string;
  kind: 'column' | 'aggregate';
  edgeType?: string;
  color?: string;
  expression?: string;
  count?: number;
}

export interface ColumnGraphElements {
  nodes: ColumnGraphNodeData[];
  edges: ColumnGraphEdgeData[];
}

export type ColumnIndexByObject = Record<string, Record<string, ColumnLineageEntry>>;

export interface ColumnObjectMeta {
  label?: string;
  layer?: string;
  layerCode?: string;
  role?: string;
}

export type ColumnObjectMetaById = Record<string, ColumnObjectMeta>;

function emptyEntry(): ColumnLineageEntry {
  return { upstream: [], downstream: [] };
}

function addColumn(objectColumns: Map<string, Set<string>>, object: string, column: string) {
  if (!object || !column) return;
  const cols = objectColumns.get(object) ?? new Set<string>();
  cols.add(column);
  objectColumns.set(object, cols);
}

export function buildColumnGraphElements(
  indexes: ColumnIndexByObject,
  objectMeta: ColumnObjectMetaById = {},
): ColumnGraphElements {
  const objectColumns = new Map<string, Set<string>>();
  const columnEdges = new Map<string, ColumnGraphEdgeData>();

  for (const [object, columns] of Object.entries(indexes)) {
    for (const [column, entry] of Object.entries(columns)) {
      addColumn(objectColumns, object, column);

      for (const step of entry.upstream ?? []) {
        addColumn(objectColumns, step.object, step.column);
        const edgeType = step.edgeType || 'direct';
        const id = columnEdgeId(step.object, step.column, object, column, edgeType);
        columnEdges.set(id, {
          id,
          source: columnId(step.object, step.column),
          target: columnId(object, column),
          kind: 'column',
          edgeType,
          color: edgeTypeColor(edgeType),
          expression: step.expression,
        });
      }

      for (const step of entry.downstream ?? []) {
        addColumn(objectColumns, step.object, step.column);
        const edgeType = step.edgeType || 'direct';
        const id = columnEdgeId(object, column, step.object, step.column, edgeType);
        columnEdges.set(id, {
          id,
          source: columnId(object, column),
          target: columnId(step.object, step.column),
          kind: 'column',
          edgeType,
          color: edgeTypeColor(edgeType),
          expression: step.expression,
        });
      }
    }
  }

  const nodes: ColumnGraphNodeData[] = [];
  for (const object of [...objectColumns.keys()].sort()) {
    const meta = objectMeta[object] ?? {};
    nodes.push({
      id: object,
      label: meta.label || object,
      kind: 'object',
      layer: meta.layer,
      layerCode: meta.layerCode,
      role: meta.role,
    });
    for (const column of [...(objectColumns.get(object) ?? [])].sort()) {
      nodes.push({
        id: columnId(object, column),
        label: column,
        kind: 'column',
        parent: object,
        object,
        column,
      });
    }
  }

  const aggregate = new Map<string, { source: string; target: string; count: number }>();
  for (const edge of columnEdges.values()) {
    const source = splitColumnId(edge.source).object;
    const target = splitColumnId(edge.target).object;
    const aggId = `agg:${source}->${target}`;
    const prev = aggregate.get(aggId);
    aggregate.set(aggId, { source, target, count: (prev?.count ?? 0) + 1 });
  }

  const aggregateEdges = [...aggregate.values()]
    .filter(edge => edge.source !== edge.target)
    .map(edge => ({
      id: `agg:${edge.source}->${edge.target}`,
      source: edge.source,
      target: edge.target,
      kind: 'aggregate' as const,
      count: edge.count,
    }));

  return {
    nodes,
    edges: [...columnEdges.values(), ...aggregateEdges],
  };
}

export interface ColumnRef {
  object: string;
  column: string;
}

export interface ColumnTraceResult {
  indexes: ColumnIndexByObject;
  columnIds: Set<string>;
  edgeIds: Set<string>;
  errors: string[];
}

type FetchColumnIndex = (objectId: string) => Promise<ColumnLineageObjectResponse>;

function cloneIndexes(indexes: ColumnIndexByObject): ColumnIndexByObject {
  return Object.fromEntries(Object.entries(indexes).map(([object, columns]) => [object, { ...columns }]));
}

function stepToEdgeId(ref: ColumnRef, step: ColumnLineageStep, direction: 'upstream' | 'downstream') {
  return direction === 'upstream'
    ? columnEdgeId(step.object, step.column, ref.object, ref.column, step.edgeType || 'direct')
    : columnEdgeId(ref.object, ref.column, step.object, step.column, step.edgeType || 'direct');
}

export async function traceColumnLineage(
  start: ColumnRef,
  indexes: ColumnIndexByObject,
  fetchIndex: FetchColumnIndex,
  maxDepth = 50,
): Promise<ColumnTraceResult> {
  const nextIndexes = cloneIndexes(indexes);
  const columnIds = new Set<string>([columnId(start.object, start.column)]);
  const edgeIds = new Set<string>();
  const errors: string[] = [];
  const visited = new Set<string>([columnId(start.object, start.column)]);
  const queue: Array<{ ref: ColumnRef; depth: number }> = [{ ref: start, depth: 0 }];

  while (queue.length > 0) {
    const { ref, depth } = queue.shift()!;
    if (depth >= maxDepth) continue;

    if (!nextIndexes[ref.object]) {
      try {
        const fetched = await fetchIndex(ref.object);
        nextIndexes[ref.object] = fetched.columns ?? {};
      } catch (err) {
        errors.push(err instanceof Error ? err.message : `Failed to load ${ref.object}`);
        continue;
      }
    }

    const entry = nextIndexes[ref.object]?.[ref.column] ?? emptyEntry();
    const steps: Array<{ step: ColumnLineageStep; direction: 'upstream' | 'downstream' }> = [
      ...(entry.upstream ?? []).map(step => ({ step, direction: 'upstream' as const })),
      ...(entry.downstream ?? []).map(step => ({ step, direction: 'downstream' as const })),
    ];

    for (const { step, direction } of steps) {
      const nextId = columnId(step.object, step.column);
      columnIds.add(nextId);
      edgeIds.add(stepToEdgeId(ref, step, direction));
      if (!visited.has(nextId)) {
        visited.add(nextId);
        queue.push({ ref: { object: step.object, column: step.column }, depth: depth + 1 });
      }
    }
  }

  return { indexes: nextIndexes, columnIds, edgeIds, errors };
}
