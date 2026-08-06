import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { api } from './client';
import { t } from '@/i18n/de';
import type { Proposal } from '@/types';

export const useProposals = () =>
  useQuery<Proposal[]>({
    queryKey: ['proposals'],
    queryFn: () => api.get('/proposals').then(r => r.data),
  });

type ProposalActionKind = 'accept' | 'reject' | 'snooze';

const proposalAction = (id: string, action: ProposalActionKind) =>
  api.post(`/proposals/${id}/${action}`).then(r => r.data);

const STATUS_FOR: Record<ProposalActionKind, Proposal['status']> = {
  accept: 'accepted', reject: 'rejected', snooze: 'snoozed',
};
const TOAST_FOR: Record<ProposalActionKind, string> = {
  accept: t.toast.proposalAccepted, reject: t.toast.proposalRejected, snooze: t.toast.proposalSnoozed,
};

// R6-4: optimistic status change on the open list + toast with rollback on error.
export const useProposalAction = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, action }: { id: string; action: ProposalActionKind }) => proposalAction(id, action),
    onMutate: async ({ id, action }) => {
      await qc.cancelQueries({ queryKey: ['proposals'] });
      const previous = qc.getQueryData<Proposal[]>(['proposals']);
      qc.setQueryData<Proposal[]>(['proposals'], (old) =>
        (old ?? []).map(p => p.id === id ? { ...p, status: STATUS_FOR[action] } : p));
      return { previous };
    },
    onError: (_e, _vars, ctx) => {
      if (ctx?.previous) qc.setQueryData(['proposals'], ctx.previous);
      toast.error(t.toast.proposalError);
    },
    onSuccess: (_d, { action }) => { toast.success(TOAST_FOR[action]); },
    onSettled: () => qc.invalidateQueries({ queryKey: ['proposals'] }),
  });
};
