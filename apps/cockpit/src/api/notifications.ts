import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { api } from './client';
import { t } from '@/i18n/de';
import type {
  DigestPreview, NotificationConfig, NotificationChannel, NotificationRule, NotificationMute,
} from '@/types';

const KEY = ['notifications', 'config'];

// UX-N2: channels + routing rules + mute windows in one read (server-authoritative).
export const useNotificationConfig = () =>
  useQuery<NotificationConfig>({
    queryKey: KEY,
    queryFn: () => api.get('/notifications/config').then(r => r.data),
  });

function useInvalidate() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: KEY });
}

export interface ChannelInput {
  name: string; type: string; url: string; enabled?: boolean; digest_enabled?: boolean;
}

export const useCreateChannel = () => {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (body: ChannelInput) =>
      api.post('/notifications/channels', body).then(r => r.data as NotificationChannel),
    onSuccess: () => { invalidate(); toast.success(t.toast.saved); },
    onError: () => toast.error(t.toast.saveError),
  });
};

export const usePatchChannel = () => {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: ({ id, ...body }: Partial<ChannelInput> & { id: number }) =>
      api.patch(`/notifications/channels/${id}`, body).then(r => r.data as NotificationChannel),
    onSuccess: () => invalidate(),
    onError: () => toast.error(t.toast.saveError),
  });
};

export const useDeleteChannel = () => {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (id: number) => api.delete(`/notifications/channels/${id}`),
    onSuccess: () => { invalidate(); toast.success(t.toast.deleted); },
    onError: () => toast.error(t.toast.saveError),
  });
};

export interface RuleInput {
  name: string; channel_id: number;
  match_severity?: string; match_space?: string; match_product?: string;
  match_owned_by?: string; match_owner?: string; match_kind?: string; enabled?: boolean;
}

export const useCreateRule = () => {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (body: RuleInput) =>
      api.post('/notifications/rules', body).then(r => r.data as NotificationRule),
    onSuccess: () => { invalidate(); toast.success(t.toast.saved); },
    onError: () => toast.error(t.toast.saveError),
  });
};

export const useDeleteRule = () => {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (id: number) => api.delete(`/notifications/rules/${id}`),
    onSuccess: () => { invalidate(); toast.success(t.toast.deleted); },
    onError: () => toast.error(t.toast.saveError),
  });
};

// V4 Qualitäts-Digest: Kennzahlen-Vorschau + manueller Versand.
export const useDigestPreview = () =>
  useQuery<DigestPreview>({
    queryKey: ['notifications', 'digest'],
    queryFn: () => api.get('/notifications/digest/preview').then(r => r.data),
  });

export const useSendDigest = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.post('/notifications/digest/send').then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['notifications', 'digest'] });
      toast.success(t.notifications.digestSent);
    },
    onError: () => toast.error(t.notifications.digestSendError),
  });
};

export interface MuteInput {
  reason?: string; match_space?: string; match_product?: string;
  starts_at: string; ends_at: string;
}

export const useCreateMute = () => {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (body: MuteInput) =>
      api.post('/notifications/mutes', body).then(r => r.data as NotificationMute),
    onSuccess: () => { invalidate(); toast.success(t.toast.saved); },
    onError: () => toast.error(t.toast.saveError),
  });
};

export const useDeleteMute = () => {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (id: number) => api.delete(`/notifications/mutes/${id}`),
    onSuccess: () => { invalidate(); toast.success(t.toast.deleted); },
    onError: () => toast.error(t.toast.saveError),
  });
};
