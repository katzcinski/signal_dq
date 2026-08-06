import { useQuery } from '@tanstack/react-query';
import { api } from './client';
import type { CoverageSummary, HealthTrend, StatusHeatmap } from '@/types';

export const useCoverageSummary = () =>
  useQuery<CoverageSummary>({
    queryKey: ['coverage', 'summary'],
    queryFn: () => api.get('/coverage/summary').then(r => r.data),
  });

// UX-N12: data-health trend (latest vs. prior run) for the cockpit gauge.
export const useHealthTrend = () =>
  useQuery<HealthTrend>({
    queryKey: ['coverage', 'health'],
    queryFn: () => api.get('/coverage/health').then(r => r.data),
    staleTime: 60_000,
  });

// UX-N10: object × day reliability heatmap.
export const useStatusHeatmap = (days = 30) =>
  useQuery<StatusHeatmap>({
    queryKey: ['coverage', 'heatmap', days],
    queryFn: () => api.get(`/coverage/heatmap?days=${days}`).then(r => r.data),
    staleTime: 60_000,
  });
