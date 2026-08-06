import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { api } from './client';
import { t } from '@/i18n/de';
import type {
  HealingCorrection, HealingEpisodeDetail, HealingOverview, HealingPatch, HealingPlan,
} from '@/types';

const OVERVIEW = ['healing', 'overview'];

// Healing-Workbench (Konzept_Manuelles_Healing H1/H3).
export const useHealingOverview = () =>
  useQuery<HealingOverview>({
    queryKey: OVERVIEW,
    queryFn: () => api.get('/healing/overview').then(r => r.data),
    retry: false,
  });

export const useHealingEpisode = (episodeId: number | null) =>
  useQuery<HealingEpisodeDetail>({
    queryKey: ['healing', 'episode', episodeId],
    queryFn: () => api.get(`/healing/episodes/${episodeId}`).then(r => r.data),
    enabled: episodeId != null,
    retry: false,
  });

export interface CorrectionInput {
  keys: Record<string, string>;
  column: string;
  new_value: string;
  before_value?: string;
  reason?: string;
}

export const useCreateCorrection = (episodeId: number) => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: CorrectionInput) =>
      api.post(`/healing/episodes/${episodeId}/corrections`, body)
        .then(r => r.data as { correction: HealingCorrection; remaining_bad_rows: number | null; release_ready: boolean }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['healing'] });
      toast.success(t.healing.correctionSaved);
    },
    onError: () => toast.error(t.healing.correctionError),
  });
};

export const useRecheckEpisode = (episodeId: number) => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.post(`/healing/episodes/${episodeId}/recheck`).then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['healing'] }),
    onError: () => toast.error(t.healing.recheckError),
  });
};

export interface PatchInput {
  object_id: string;
  keys: Record<string, string>;
  values: Record<string, string>;
  reason?: string;
  valid_until?: string | null;
}

export const useCreatePatch = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: PatchInput) => api.post('/healing/patches', body).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['healing'] });
      toast.success(t.healing.patchSaved);
    },
    onError: () => toast.error(t.healing.patchError),
  });
};

export const useRevokePatch = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (patchId: string) =>
      api.post(`/healing/patches/${patchId}/revoke`).then(r => r.data as { patch: HealingPatch }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['healing'] });
      toast.success(t.healing.patchRevoked);
    },
    onError: () => toast.error(t.healing.patchError),
  });
};

export const useHealingPlan = (objectId: string) =>
  useQuery<HealingPlan>({
    queryKey: ['healing', 'plan', objectId],
    queryFn: () => api.get(`/healing/plan?object_id=${encodeURIComponent(objectId)}`).then(r => r.data),
    enabled: !!objectId,
    retry: false,
  });
