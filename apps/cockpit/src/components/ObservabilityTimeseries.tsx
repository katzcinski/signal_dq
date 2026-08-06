import { useState, useMemo } from 'react';
import { useObjectTimeseries } from '@/api/objects';
import { MetricChart } from '@/components/ui/MetricChart';
import { ErrorBanner } from '@/components/ui/ErrorBanner';
import { TimeseriesSkeleton } from '@/components/object-detail/ObjectDetailSkeletons';
import type { MetricSeries } from '@/types';
import { t } from '@/i18n/de';

// UX-N1 + UX-N11: per-object Freshness & Volume time-series with a single,
// global timeframe picker that applies to every chart on the tab. Turns the
// status board into a monitoring surface.

type Range = '7d' | '30d' | '90d' | 'all';
const RANGE_DAYS: Record<Range, number | null> = { '7d': 7, '30d': 30, '90d': 90, all: null };
const RANGES: Range[] = ['7d', '30d', '90d', 'all'];

function clip(series: MetricSeries, days: number | null): MetricSeries {
  if (days === null) return series;
  const cutoff = Date.now() - days * 86_400_000;
  return { ...series, points: series.points.filter(p => new Date(p.at).getTime() >= cutoff) };
}

export function ObservabilityTimeseries({ objectId, enabled }: { objectId: string; enabled: boolean }) {
  const [range, setRange] = useState<Range>('30d');
  const { data, isLoading, isError, refetch } = useObjectTimeseries(objectId, enabled);

  const series = useMemo(
    () => (data?.series ?? []).map(s => clip(s, RANGE_DAYS[range])),
    [data, range],
  );

  if (isError) return <ErrorBanner onRetry={() => refetch()} />;
  if (isLoading) return <TimeseriesSkeleton />;

  if (!data || data.series.length === 0) {
    return (
      <div style={{ background: 'var(--bg-1)', border: '1px solid var(--line)', borderRadius: 'var(--r-lg)', padding: 'var(--s6)', textAlign: 'center' }}>
        <p style={{ color: 'var(--fg-2)', fontSize: 13, fontWeight: 600 }}>{t.timeseries.emptyTitle}</p>
        <p style={{ color: 'var(--fg-3)', fontSize: 12, marginTop: 6 }}>{t.timeseries.emptyHint}</p>
      </div>
    );
  }

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--s3)', marginBottom: 14 }}>
        <span style={{ fontSize: 12, color: 'var(--fg-3)' }}>{t.timeseries.rangeLabel}</span>
        <div role="group" aria-label={t.timeseries.rangeLabel} style={{ display: 'inline-flex', border: '1px solid var(--line)', borderRadius: 'var(--r-md)', overflow: 'hidden' }}>
          {RANGES.map(r => (
            <button
              key={r}
              onClick={() => setRange(r)}
              aria-pressed={range === r}
              style={{
                padding: '5px 12px', fontSize: 12, border: 'none', cursor: 'pointer',
                background: range === r ? 'var(--cont)' : 'var(--bg-1)',
                color: range === r ? '#fff' : 'var(--fg-3)',
              }}
            >
              {t.timeseries.range[r]}
            </button>
          ))}
        </div>
      </div>
      {series.map(s => <MetricChart key={s.check_name} series={s} />)}
    </div>
  );
}
