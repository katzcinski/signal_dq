import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from './client';
import type {
  ObjectSummary, RunListItem, CheckHistoryPoint, EnvironmentsResponse,
  OperationStart,
  ObjectTimeseries,
  ObjectDiffResult,
} from '@/types';

export interface ObjectDiffBody {
  mode?: 'distribution' | 'keys';
  base_snapshot_id?: number;
  head_snapshot_id?: number;
  key_columns?: string[];
}

// §B.2/§B.3: Data-Diff zweier gespeicherter Profil-Snapshots (Distribution/Keys).
export const useObjectDiff = (id: string) =>
  useMutation<ObjectDiffResult, unknown, ObjectDiffBody>({
    mutationFn: (body: ObjectDiffBody = {}) =>
      api.post(`/objects/${id}/diff`, { mode: 'distribution', ...body }).then(r => r.data),
  });

export const useObjects = () =>
  useQuery<ObjectSummary[]>({
    queryKey: ['objects'],
    queryFn: () => api.get('/objects').then(r => r.data),
  });

export const useObject = (id: string) =>
  useQuery<ObjectSummary>({
    queryKey: ['objects', id],
    queryFn: () => api.get(`/objects/${id}`).then(r => r.data),
    enabled: !!id,
  });

export const useObjectRuns = (id: string) =>
  useQuery<RunListItem[]>({
    queryKey: ['objects', id, 'runs'],
    queryFn: () => api.get(`/objects/${id}/runs`).then(r => r.data),
    enabled: !!id,
    // Poll while the latest run is in-flight so the list/status updates live.
    refetchInterval: (query) => query.state.data?.[0]?.run_state === 'running' ? 2000 : false,
  });

export interface TriggerRunBody {
  environment?: string;
  execution_mode?: string;
}

export const useTriggerRun = (id: string) => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: TriggerRunBody = {}) =>
      api.post(`/objects/${id}/run`, body).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['objects', id, 'runs'] });
      qc.invalidateQueries({ queryKey: ['objects', id] });
    },
  });
};

// actual_value time series per check (newest first).
export const useCheckHistory = (objectId: string, checkName: string, enabled = true) =>
  useQuery<CheckHistoryPoint[]>({
    queryKey: ['objects', objectId, 'checks', checkName, 'history'],
    queryFn: () =>
      api.get(`/objects/${objectId}/checks/${encodeURIComponent(checkName)}/history`).then(r => r.data),
    enabled: !!objectId && !!checkName && enabled,
    staleTime: 60_000,
  });

// UX-N1: freshness/volume time-series with baseline band + anomaly markers.
export const useObjectTimeseries = (objectId: string, enabled = true) =>
  useQuery<ObjectTimeseries>({
    queryKey: ['objects', objectId, 'timeseries'],
    queryFn: () => api.get(`/objects/${objectId}/timeseries`).then(r => r.data),
    enabled: !!objectId && enabled,
    staleTime: 60_000,
  });

export const useEnvironments = () =>
  useQuery<EnvironmentsResponse>({
    queryKey: ['environments'],
    queryFn: () => api.get('/environments').then(r => r.data),
    staleTime: 5 * 60_000,
  });

export interface ObjectProfileRequest {
  environment?: string;
  include_composite?: boolean;
  include_samples?: boolean;
  sample_limit?: number;
}

export const useObjectProfile = (id: string) =>
  useMutation<OperationStart, Error, ObjectProfileRequest>({
    mutationFn: (body: ObjectProfileRequest) =>
      api.post(`/objects/${id}/profile`, body).then(r => r.data),
  });

// Analyzer chain: refresh inventory/lineage (onboarding step 1).
export const useExtract = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { environment?: string } = {}) =>
      api.post('/extract', body).then(r => r.data as Record<string, unknown>),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['inventory'] });
      qc.invalidateQueries({ queryKey: ['lineage'] });
      qc.invalidateQueries({ queryKey: ['objects'] });
    },
  });
};
