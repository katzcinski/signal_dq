import type { StatusHeatmap } from '@/types';

// DQ-first cockpit: the heatmap already carries object × day worst-status, so we
// can derive a real daily *pass-rate* time-series from it without a new backend
// endpoint. For each day we look at the objects that actually ran and compute
// the share that passed — a day with no runs is null (gap, not zero) so the line
// connects across it instead of crashing to the floor.

export interface PassRatePoint {
  day: string;
  pct: number | null;   // 0..100, null when no object ran that day
  passing: number;
  withRun: number;
}

export function deriveDailyPassRate(hm: StatusHeatmap): PassRatePoint[] {
  return hm.days.map(day => {
    let passing = 0;
    let withRun = 0;
    for (const ds of hm.datasets) {
      const status = hm.matrix[ds]?.[day];
      if (!status) continue;
      withRun += 1;
      if (status === 'pass') passing += 1;
    }
    return {
      day,
      withRun,
      passing,
      pct: withRun > 0 ? Math.round((passing / withRun) * 1000) / 10 : null,
    };
  });
}

// Current value = last day with runs; trend delta = last vs. first valued day in
// the window. Both null when there is no run history at all.
export function passRateSummary(points: PassRatePoint[]): {
  current: number | null;
  delta: number | null;
} {
  const valued = points.filter(p => p.pct !== null) as (PassRatePoint & { pct: number })[];
  if (valued.length === 0) return { current: null, delta: null };
  const current = valued[valued.length - 1].pct;
  const first = valued[0].pct;
  const delta = valued.length >= 2 ? Math.round((current - first) * 10) / 10 : null;
  return { current, delta };
}
