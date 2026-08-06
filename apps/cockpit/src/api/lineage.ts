import { useQuery } from '@tanstack/react-query';
import { api } from './client';
import type {
  ColumnImpactResponse,
  ColumnLineageColumnResponse,
  ColumnLineageObjectResponse,
  LineageGraph,
} from '@/types';

export interface LineageScope {
  /** Seed-Objekte: ohne Seeds wird der volle Graph geladen. */
  seeds?: string[];
  /** BFS-Tiefe um die Seeds (Hops in beide Richtungen). */
  depth?: number;
  /** Abfrage gezielt aussetzen (z. B. solange kein Seed gewählt ist). */
  enabled?: boolean;
}

export const useLineage = (scope: LineageScope = {}) => {
  const seeds = scope.seeds ?? [];
  const depth = scope.depth ?? 2;
  return useQuery<LineageGraph>({
    // Seeds stabil sortiert in den Key, damit identische Auswahl gecacht wird.
    queryKey: ['lineage', [...seeds].sort(), seeds.length ? depth : null],
    queryFn: () => {
      const params = new URLSearchParams();
      for (const s of seeds) params.append('seed', s);
      if (seeds.length) params.set('depth', String(depth));
      const qs = params.toString();
      return api.get(`/lineage${qs ? `?${qs}` : ''}`).then(r => r.data);
    },
    enabled: scope.enabled ?? true,
  });
};

export function fetchColumnLineage(objectId: string): Promise<ColumnLineageObjectResponse>;
export function fetchColumnLineage(objectId: string, column: string): Promise<ColumnLineageColumnResponse>;
export function fetchColumnLineage(objectId: string, column?: string) {
  return api.get('/lineage/columns', {
    params: column ? { object: objectId, column } : { object: objectId },
  }).then(r => r.data);
}

export const useColumnLineage = (objectId: string, column?: string) =>
  useQuery<ColumnLineageObjectResponse | ColumnLineageColumnResponse>({
    queryKey: ['lineage', 'columns', objectId, column ?? 'all'],
    queryFn: () => fetchColumnLineage(objectId, column as string),
    enabled: !!objectId,
  });

export const useColumnImpact = (objectId: string, column: string | undefined) =>
  useQuery<ColumnImpactResponse>({
    queryKey: ['lineage', 'columns', 'impact', objectId, column ?? ''],
    queryFn: () =>
      api
        .get('/lineage/columns/impact', { params: { object: objectId, column } })
        .then(r => r.data),
    enabled: !!objectId && !!column,
  });
