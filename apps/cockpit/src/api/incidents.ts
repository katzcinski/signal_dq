import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { api } from './client';
import { t } from '@/i18n/de';
import type { Incident, IncidentDetail, IncidentTransitionBody, FailedCheck, IncidentRca } from '@/types';

// Persistent lifecycle incidents (GET /api/incidents?status=&severity=&kind=)
export const useIncidents = (status?: string, severity?: string, kind?: string) =>
  useQuery<Incident[]>({
    queryKey: ['incidents', { status: status ?? '', severity: severity ?? '', kind: kind ?? '' }],
    queryFn: () => api.get('/incidents', {
      params: {
        ...(status ? { status } : {}),
        ...(severity ? { severity } : {}),
        ...(kind ? { kind } : {}),
      },
    }).then(r => r.data),
    refetchInterval: 60_000,
  });

export const useIncident = (id: number | null) =>
  useQuery<IncidentDetail>({
    queryKey: ['incidents', 'detail', id],
    queryFn: () => api.get(`/incidents/${id}`).then(r => r.data),
    enabled: id != null,
  });

export const useIncidentClusters = (status?: string, severity?: string, kind?: string) =>
  useQuery<Incident[]>({
    queryKey: ['incidents', 'clusters', { status: status ?? '', severity: severity ?? '', kind: kind ?? '' }],
    queryFn: () => api.get('/incidents', {
      params: {
        group: 'cluster',
        ...(status ? { status } : {}),
        ...(severity ? { severity } : {}),
        ...(kind ? { kind } : {}),
      },
    }).then(r => r.data),
    refetchInterval: 60_000,
  });

export const useIncidentRca = (id: number | null) =>
  useQuery<IncidentRca>({
    queryKey: ['incidents', 'rca', id],
    queryFn: () => api.get(`/incidents/${id}/rca`).then(r => r.data),
    enabled: id != null,
    retry: false,
  });

export const useIncidentTransition = (id: number | null) => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: IncidentTransitionBody) =>
      api.post(`/incidents/${id}/transition`, body).then(r => r.data as Incident),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['incidents'] });
      toast.success(t.toast.incidentUpdated);
    },
    onError: () => {
      toast.error(t.toast.incidentUpdateError);
    },
  });
};

// Derived failing-checks view (moved to GET /api/incidents/checks)
export const useFailedChecks = (severity?: string, dataset?: string) =>
  useQuery<FailedCheck[]>({
    queryKey: ['incidents', 'checks', { severity: severity ?? '', dataset: dataset ?? '' }],
    queryFn: () => api.get('/incidents/checks', {
      params: {
        ...(severity ? { severity } : {}),
        ...(dataset ? { dataset } : {}),
      },
    }).then(r => r.data),
    refetchInterval: 60_000,
  });
