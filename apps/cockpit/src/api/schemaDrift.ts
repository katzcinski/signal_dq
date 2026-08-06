import { useQuery } from '@tanstack/react-query';
import { api } from './client';
import type { SchemaDriftObjectRow, SchemaEvolutionOut } from '@/types';

// A2/UX-N9: Schema-Evolution über Zeit — Overview + Detail je Objekt.
export const useSchemaDriftOverview = () =>
  useQuery<SchemaDriftObjectRow[]>({
    queryKey: ['schema-drift'],
    queryFn: () => api.get('/schema-drift').then(r => r.data?.objects ?? []),
  });

export const useSchemaEvolution = (objectName: string) =>
  useQuery<SchemaEvolutionOut>({
    queryKey: ['schema-drift', objectName],
    queryFn: () => api.get(`/schema-drift/${encodeURIComponent(objectName)}`).then(r => r.data),
    enabled: !!objectName,
    retry: false,
  });
