import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { AxiosError } from 'axios';
import { api } from './client';
import { t } from '@/i18n/de';

// „Für Monitoring verfügbar machen" — Hybrid (ADR-0002). Das Cockpit merkt ein
// Objekt nur im Soll-Zustand vor; ein externes Skript provisioniert Share+View
// und meldet den Status zurück. Signal schreibt selbst nicht nach Datasphere.

export type ShareStatus = 'requested' | 'provisioned' | 'error';

export interface MonitoringConfig {
  enabled: boolean;
  monitoring_space: string;
}

export interface ShareEntry {
  object_id: string;
  status: ShareStatus;
  view: string | null;
  error: string | null;
}

export const useMonitoringConfig = () =>
  useQuery<MonitoringConfig>({
    queryKey: ['monitoring', 'config'],
    queryFn: () => api.get('/monitoring/config').then(r => r.data),
    staleTime: 60_000,
  });

export const useMonitoringShares = () =>
  useQuery<ShareEntry[]>({
    queryKey: ['monitoring', 'shares'],
    queryFn: () => api.get('/monitoring/shares').then(r => r.data.shares ?? []),
    // Poll while anything is still being provisioned by the external script.
    refetchInterval: (query) =>
      (query.state.data ?? []).some(s => s.status === 'requested') ? 5000 : false,
  });

export const useRequestMonitoring = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (objectId: string) =>
      api.post(`/monitoring/shares/${objectId}`).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['monitoring', 'shares'] });
      toast.success(t.monitoring.requestedToast);
    },
    onError: (err: AxiosError<{ detail?: string }>) => {
      toast.error(err.response?.data?.detail ?? t.monitoring.requestError);
    },
  });
};
