import { useQuery } from '@tanstack/react-query';
import { api } from './client';
import type { DataLoad } from '@/types';

export const useDataLoads = (space?: string, top = 50) =>
  useQuery<DataLoad[]>({
    queryKey: ['datasphere', 'data-loads', space, top],
    queryFn: () =>
      api
        .get('/datasphere/data-loads', { params: { space, top } })
        .then(r => r.data),
    staleTime: 60_000,
    retry: false,
  });

export const useObjectDataLoads = (objectId: string, space?: string, top = 20) =>
  useQuery<DataLoad[]>({
    queryKey: ['datasphere', 'data-loads', objectId, space],
    queryFn: () =>
      api
        .get(`/datasphere/data-loads/${encodeURIComponent(objectId)}`, {
          params: { space, top },
        })
        .then(r => r.data),
    enabled: !!objectId,
    staleTime: 60_000,
    retry: false,
  });
