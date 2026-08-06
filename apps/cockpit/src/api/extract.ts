import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { t } from '@/i18n/de';
import type { OperationStart } from '@/types';
import { api } from './client';

export type ExtractStatusValue = 'idle' | 'queued' | 'running' | 'succeeded' | 'partial' | 'skipped' | 'failed';

export interface ExtractCounts {
  inventory_items?: number;
  lineage_nodes?: number;
  lineage_edges?: number;
  column_edges?: number;
}

export interface ExtractStatus {
  op_id: string | null;
  job_id: string | null;
  status: ExtractStatusValue;
  environment: string;
  profile: string;
  spaces: string[];
  source: string;
  started_at: string | null;
  updated_at: string | null;
  finished_at: string | null;
  current_step: string;
  counts: ExtractCounts;
  warnings: string[];
  error: string | null;
  runtime_artifact_paths: Record<string, string>;
  published_snapshot_timestamp: string | null;
  can_trigger: boolean;
}

export interface ExtractSchemaDriftSummary {
  checked: number;
  drifted: number;
  breaking: number;
  errors: number;
}

export interface ExtractOperationResult extends Omit<ExtractStatus, 'can_trigger'> {
  can_trigger?: boolean;
  extracted_at: string | null;
  schema_drift?: ExtractSchemaDriftSummary;
}

export interface ExtractTriggerBody {
  environment?: string;
  profile?: string;
  spaces?: string[];
  include_sql?: boolean;
  force?: boolean;
}

export const EXTRACT_STATUS_KEY = ['extract', 'status'] as const;

export function extractStatusIsActive(status?: ExtractStatusValue): boolean {
  return status === 'queued' || status === 'running';
}

export function useExtractStatus() {
  return useQuery({
    queryKey: EXTRACT_STATUS_KEY,
    queryFn: async () => (await api.get<ExtractStatus>('/extract/status')).data,
    refetchInterval: query => extractStatusIsActive(query.state.data?.status) ? 2_000 : false,
  });
}

export function useStartExtract() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: ExtractTriggerBody) => (await api.post<OperationStart>('/extract', body)).data,
    onSuccess: () => {
      toast.success(t.inventoryAdmin.triggerStarted);
      void qc.invalidateQueries({ queryKey: EXTRACT_STATUS_KEY });
    },
    onError: () => {
      toast.error(t.inventoryAdmin.triggerError);
    },
  });
}
