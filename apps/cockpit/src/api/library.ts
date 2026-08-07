import { useQuery } from '@tanstack/react-query';
import { api } from './client';
import type { CheckLibrary } from '@/types';

export const useLibrary = () =>
  useQuery<CheckLibrary>({
    queryKey: ['library'],
    queryFn: () => api.get('/library').then(r => r.data),
    staleTime: Infinity,
  });
