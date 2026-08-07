import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { api } from './client';
import { t } from '@/i18n/de';
import type { QuarantineEpisode, QuarantineEpisodeDetail } from '@/types';

// Quarantäne-Episoden (Enforcement-Achse): GET /api/quarantine?status=&product=
export const useQuarantineEpisodes = (status?: string, product?: string) =>
  useQuery<QuarantineEpisode[]>({
    queryKey: ['quarantine', { status: status ?? '', product: product ?? '' }],
    queryFn: () => api.get('/quarantine', {
      params: {
        ...(status ? { status } : {}),
        ...(product ? { product } : {}),
      },
    }).then(r => r.data),
    refetchInterval: 60_000,
  });

export const useQuarantineEpisode = (id: number | null) =>
  useQuery<QuarantineEpisodeDetail>({
    queryKey: ['quarantine', 'detail', id],
    queryFn: () => api.get(`/quarantine/${id}`).then(r => r.data),
    enabled: id != null,
  });

function useQuarantineAction(id: number | null, action: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { note?: string }) =>
      api.post(`/quarantine/${id}/${action}`, body).then(r => r.data as QuarantineEpisode),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['quarantine'] });
      toast.success(t.toast.quarantineUpdated);
    },
    onError: () => {
      toast.error(t.toast.quarantineUpdateError);
    },
  });
}

/** Steward-Freigabe: Zeilen erscheinen in der Release-View des Kunden-Flows. */
export const useQuarantineRelease = (id: number | null) => useQuarantineAction(id, 'release');

/** Rückführung bestätigt → Episode resolved(reprocessed). */
export const useQuarantineConfirmReprocess = (id: number | null) =>
  useQuarantineAction(id, 'confirm-reprocess');
