import { useQuery } from '@tanstack/react-query';
import { api } from './client';
import type { ActivityItem } from '@/types';

// UX-N15: merged audit feed (incidents · proposals · contract approvals).
export const useActivity = (limit = 30) =>
  useQuery<ActivityItem[]>({
    queryKey: ['activity', limit],
    queryFn: () => api.get('/activity', { params: { limit } }).then(r => r.data),
    refetchInterval: 60_000,
  });
