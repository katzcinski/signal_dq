import { render } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { MetricChart } from '@/components/ui/MetricChart';
import { t } from '@/i18n/de';
import type { MetricSeries, MetricPoint } from '@/types';

function pt(at: string, value: number | null, anomaly = false): MetricPoint {
  return { at, value, raw: value === null ? null : String(value), passed: !anomaly, state: 'executed', run_id: 'r', anomaly };
}

const base: MetricSeries = {
  check_name: 'volume_row_count',
  check_type: 'row_count',
  metric: 'volume',
  baseline: { mean: 100, lower: 90, upper: 110, p01: 92, p99: 108 },
  points: [
    pt('2026-01-01T00:00:00Z', 100),
    pt('2026-01-02T00:00:00Z', 105),
    pt('2026-01-03T00:00:00Z', 500, true),
  ],
};

describe('MetricChart (UX-N1/N11)', () => {
  it('renders the metric label, check name and band summary', () => {
    const { container } = render(<MetricChart series={base} />);
    expect(container.textContent).toContain(t.timeseries.metric.volume);
    expect(container.textContent).toContain('volume_row_count');
    expect(container.textContent).toContain(t.timeseries.band);
  });

  it('surfaces the anomaly count from the series', () => {
    const { container } = render(<MetricChart series={base} />);
    expect(container.textContent).toContain(`1 ${t.timeseries.anomalies}`);
  });

  it('falls back to a notice when there are too few numeric points', () => {
    const sparse: MetricSeries = { ...base, baseline: null, points: [pt('2026-01-01T00:00:00Z', 100)] };
    const { container } = render(<MetricChart series={sparse} />);
    expect(container.textContent).toContain(t.timeseries.tooFew);
  });
});
