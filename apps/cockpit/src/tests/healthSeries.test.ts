import { describe, it, expect } from 'vitest';
import { deriveDailyPassRate, passRateSummary } from '@/lib/healthSeries';
import type { StatusHeatmap } from '@/types';

const hm: StatusHeatmap = {
  days: ['2026-06-01', '2026-06-02', '2026-06-03'],
  datasets: ['A', 'B'],
  matrix: {
    // day1: both ran, both pass → 100%
    // day2: A fails, B passes → 50%
    // day3: no runs → null gap
    A: { '2026-06-01': 'pass', '2026-06-02': 'fail' },
    B: { '2026-06-01': 'pass', '2026-06-02': 'pass' },
  },
};

describe('deriveDailyPassRate', () => {
  it('computes per-day pass-rate over objects that ran', () => {
    const pts = deriveDailyPassRate(hm);
    expect(pts.map(p => p.pct)).toEqual([100, 50, null]);
    expect(pts[1]).toMatchObject({ passing: 1, withRun: 2 });
  });

  it('marks days with no runs as a null gap, not zero', () => {
    const pts = deriveDailyPassRate(hm);
    expect(pts[2].pct).toBeNull();
    expect(pts[2].withRun).toBe(0);
  });
});

describe('passRateSummary', () => {
  it('reports the latest valued day and the window delta', () => {
    const s = passRateSummary(deriveDailyPassRate(hm));
    expect(s.current).toBe(50);   // last day with runs
    expect(s.delta).toBe(-50);    // 50 - 100
  });

  it('returns nulls when there is no run history', () => {
    const s = passRateSummary(deriveDailyPassRate({ days: ['x'], datasets: [], matrix: {} }));
    expect(s).toEqual({ current: null, delta: null });
  });
});
