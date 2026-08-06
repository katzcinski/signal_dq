import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { api } from './client';
import { t } from '@/i18n/de';

// Enforcement-Materialisierung (Slices ③–⑦): Plan (Dry-Run), Apply,
// Capability-Probe. Server erzwingt Rollen (Plan steward+, Apply/Probe owner+).
export interface EnforcementPlanObject {
  name: string;
  kind: 'table' | 'view' | 'procedure';
  manifest_hash: string;
  replaceable: boolean;
  ddl: string;
}

export interface SplitArtifactPlan {
  object_id: string;
  source: string;
  clean_table: string;
  quarantine_table: string;
  released_view: string;
  manifest_hash: string;
  predicates: { check: string; type: string; condition: string }[];
  skipped: { check: string; type: string; reason: string }[];
}

export interface EnforcementPlan {
  enabled: boolean;
  signal_schema: string;
  bridge_enabled: boolean;
  objects: EnforcementPlanObject[];
  split_artifacts: SplitArtifactPlan[];
}

export interface Capability {
  key: string;
  status: 'ok' | 'unavailable' | 'error' | 'manual';
  detail: string;
  environment: string;
  checked_at: string;
}

export const useEnforcementPlan = () =>
  useQuery<EnforcementPlan>({
    queryKey: ['enforcement', 'plan'],
    queryFn: () => api.get('/enforcement/plan').then(r => r.data),
  });

export const useCapabilities = () =>
  useQuery<{ capabilities: Capability[] }>({
    queryKey: ['enforcement', 'capabilities'],
    queryFn: () => api.get('/enforcement/capabilities').then(r => r.data),
  });

export const useEnforcementApply = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (environment: string) =>
      api.post('/enforcement/apply', { environment }).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['enforcement'] });
      toast.success(t.enforcementPanel.applyDone);
    },
    onError: () => toast.error(t.enforcementPanel.applyError),
  });
};

export const useCapabilityProbe = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (environment: string) =>
      api.post('/enforcement/probe', { environment }).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['enforcement', 'capabilities'] });
      toast.success(t.enforcementPanel.probeDone);
    },
    onError: () => toast.error(t.enforcementPanel.probeError),
  });
};
