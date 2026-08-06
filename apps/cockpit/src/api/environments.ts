import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { api } from './client';
export { useOperation } from './operations';
export { useOperationStream } from './operations';
import { t } from '@/i18n/de';
import type { AdminEnvironmentsResponse } from '@/types';

const KEY = ['admin', 'environments'];

// Admin-only: full connection targets, secret values hidden server-side.
export const useAdminEnvironments = () =>
  useQuery<AdminEnvironmentsResponse>({
    queryKey: KEY,
    queryFn: () => api.get('/admin/environments').then(r => r.data),
  });

function useInvalidate() {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: KEY });
    // The run dialog reads the non-secret name+schema list from a separate key.
    qc.invalidateQueries({ queryKey: ['environments'] });
  };
}

export interface EnvironmentInput {
  host: string;
  port: number;
  user: string;
  schema: string;
  // Secret reference (e.g. "env:HANA_PW_PROD"), never the password itself.
  // Empty on update keeps the existing credential unchanged.
  password_ref?: string;
  encrypt?: boolean;
  validate_cert?: boolean;
}

export const useCreateEnvironment = () => {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: ({ name, ...body }: EnvironmentInput & { name: string }) =>
      api.post('/admin/environments', body, { params: { name } }).then(r => r.data),
    onSuccess: () => { invalidate(); toast.success(t.toast.saved); },
    onError: () => toast.error(t.toast.saveError),
  });
};

export const useUpdateEnvironment = () => {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: ({ name, ...body }: EnvironmentInput & { name: string }) =>
      api.put(`/admin/environments/${encodeURIComponent(name)}`, body).then(r => r.data),
    onSuccess: () => { invalidate(); toast.success(t.toast.saved); },
    onError: () => toast.error(t.toast.saveError),
  });
};

export const useDeleteEnvironment = () => {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (name: string) => api.delete(`/admin/environments/${encodeURIComponent(name)}`),
    onSuccess: () => { invalidate(); toast.success(t.toast.deleted); },
    onError: () => toast.error(t.toast.saveError),
  });
};

// Live connection test: POST starts a background operation (op_id); the result
// and progress lines are then polled from the operations endpoint until done.
export const useStartConnectionTest = () =>
  useMutation({
    mutationFn: (name: string) =>
      api.post(`/environments/${encodeURIComponent(name)}/test`).then(r => r.data as { op_id: string }),
    onError: () => toast.error(t.settings.testStartError),
  });

// Store the password for an environment in secrets.local.yml (server-side).
// The password is sent once and never returned or logged (S-1).
export const useSetEnvironmentSecret = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ name, password }: { name: string; password: string }) =>
      api.put(`/admin/environments/${encodeURIComponent(name)}/secret`, { password }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['environments'] });
      toast.success(t.environments.secretSaved);
    },
    onError: () => toast.error(t.environments.secretSaveError),
  });
};
