import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { api } from './client';
import { t } from '@/i18n/de';
import type { Schedule, ScheduleUpsert } from '@/types';

const LIST_KEY = ['schedules'];
const objKey = (id: string) => ['objects', id, 'schedule'];

// Cross-object ops view (GET /api/schedules). steward+ server-side.
export const useSchedules = () =>
  useQuery<Schedule[]>({
    queryKey: LIST_KEY,
    queryFn: () => api.get('/schedules').then(r => r.data),
    // The overview is operational — keep the next-run countdowns lively.
    refetchInterval: 15_000,
  });

// A single object's schedule, or null when scheduling is manual.
export const useObjectSchedule = (id: string) =>
  useQuery<Schedule | null>({
    queryKey: objKey(id),
    queryFn: () => api.get(`/objects/${encodeURIComponent(id)}/schedule`).then(r => r.data),
    enabled: !!id,
  });

function useInvalidate(id?: string) {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: LIST_KEY });
    if (id) qc.invalidateQueries({ queryKey: objKey(id) });
  };
}

export const useUpsertObjectSchedule = (id: string) => {
  const invalidate = useInvalidate(id);
  return useMutation({
    mutationFn: (body: ScheduleUpsert) =>
      api.put(`/objects/${encodeURIComponent(id)}/schedule`, body).then(r => r.data as Schedule),
    onSuccess: () => { invalidate(); toast.success(t.toast.saved); },
    onError: () => toast.error(t.toast.saveError),
  });
};

export const useDeleteObjectSchedule = (id: string) => {
  const invalidate = useInvalidate(id);
  return useMutation({
    mutationFn: () => api.delete(`/objects/${encodeURIComponent(id)}/schedule`),
    onSuccess: () => { invalidate(); toast.success(t.toast.deleted); },
    onError: () => toast.error(t.toast.saveError),
  });
};

// List-level upsert (pause/resume/edit a row from the overview without a
// per-object hook instance). Takes the full upsert body the PUT expects.
export const useUpdateScheduleRow = () => {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: ScheduleUpsert }) =>
      api.put(`/objects/${encodeURIComponent(id)}/schedule`, body).then(r => r.data as Schedule),
    onSuccess: () => invalidate(),
    onError: () => toast.error(t.toast.saveError),
  });
};

// Run-now from the overview: same trigger the object page uses. Invalidates the
// list so last_run/status refresh once the run is registered.
export const useRunObjectNow = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      api.post(`/objects/${encodeURIComponent(id)}/run`, {}).then(r => r.data),
    onSuccess: (_d, id) => {
      qc.invalidateQueries({ queryKey: LIST_KEY });
      qc.invalidateQueries({ queryKey: ['objects', id, 'runs'] });
      toast.success(t.schedules.runStarted);
    },
    onError: () => toast.error(t.schedules.runError),
  });
};
