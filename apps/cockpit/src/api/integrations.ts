import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from './client';

export interface EntropyConfig {
  enabled: boolean;
  url_set: boolean;
  token_set: boolean;
  allowlist_count: number;
  source_of_truth: 'signal' | 'entropy';
  marketplace_verified: boolean;
  mode: 'off' | 'dry_run' | 'live';
}

export interface EntropyPublishResult {
  status: 'sent' | 'dry_run' | 'skipped' | 'error';
  reason?: string;
  http_status?: number;
  endpoint?: string;
  product?: string;
  run_id?: string;
}

export interface OdcsImportResult {
  product: string;
  persisted: boolean;
  contract: Record<string, unknown>;
  dropped: string[];
  warnings: string[];
}

export const useEntropyConfig = () =>
  useQuery<EntropyConfig>({
    queryKey: ['integrations', 'entropy'],
    queryFn: () => api.get('/integrations/entropy').then(r => r.data),
  });

export const usePublishContract = () =>
  useMutation<EntropyPublishResult, unknown, string>({
    mutationFn: (product) =>
      api.post(`/integrations/entropy/contracts/${encodeURIComponent(product)}`).then(r => r.data),
  });

export const usePublishLatestResult = () =>
  useMutation<EntropyPublishResult, unknown, string>({
    mutationFn: (product) =>
      api.post(`/integrations/entropy/results/${encodeURIComponent(product)}`).then(r => r.data),
  });

export const useImportOdcs = () => {
  const qc = useQueryClient();
  return useMutation<OdcsImportResult, unknown, { odcs: unknown; dry_run?: boolean }>({
    mutationFn: (body) =>
      api.post('/integrations/entropy/import/odcs', body).then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['contracts'] }),
  });
};
