import { useId, useState } from 'react';
import {
  AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer,
  CartesianGrid, ReferenceLine,
} from 'recharts';
import { useStatusHeatmap } from '@/api/coverage';
import { deriveDailyPassRate, passRateSummary } from '@/lib/healthSeries';
import { t } from '@/i18n/de';

// DQ-first centerpiece: the daily share of objects passing their checks, over a
// selectable window. Answers "is our data quality trending up or down?" at a
// glance — the number tells you where you are, the curve tells you where you're
// heading. Target line at 95% gives the eye an instant pass/fail reference.

const TARGET = 95;
const WINDOWS = [30, 90] as const;

function healthColor(pct: number | null): string {
  if (pct == null) return 'var(--fg-3)';
  if (pct >= 95) return 'var(--status-ok)';
  if (pct >= 80) return 'var(--status-warn)';
  return 'var(--status-fail)';
}

function fmtDay(iso: string) {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

function chip(active: boolean): React.CSSProperties {
  return {
    fontSize: 11, padding: '3px 10px', borderRadius: 'var(--r-full)', cursor: 'pointer',
    border: `1px solid ${active ? 'var(--cont)' : 'var(--line-2)'}`,
    background: active ? 'color-mix(in srgb, var(--cont) 16%, transparent)' : 'transparent',
    color: active ? 'var(--fg)' : 'var(--fg-3)',
    transition: 'background var(--t), border-color var(--t), color var(--t)',
  };
}

export function DqHealthTrend() {
  const [days, setDays] = useState<number>(30);
  const { data, isLoading, isSuccess } = useStatusHeatmap(days);
  const gradientId = useId();

  const points = data ? deriveDailyPassRate(data) : [];
  const { current, delta } = passRateSummary(points);
  const accent = healthColor(current);
  const hasData = points.some(p => p.pct !== null);

  const trend = delta == null ? 'flat' : delta > 0.5 ? 'up' : delta < -0.5 ? 'down' : 'flat';
  const trendColor = trend === 'up' ? 'var(--status-ok)' : trend === 'down' ? 'var(--status-fail)' : 'var(--fg-3)';
  const trendGlyph = trend === 'up' ? '▲' : trend === 'down' ? '▼' : '▬';

  return (
    <div style={{
      background: 'var(--bg-1)', border: '1px solid var(--line)',
      borderLeft: `3px solid ${accent}`, borderRadius: 'var(--r-lg)', overflow: 'hidden',
      display: 'flex', flexDirection: 'column',
    }}>
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        gap: 'var(--s3)', padding: 'var(--s3) var(--s4)', borderBottom: '1px solid var(--line)',
      }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 14, minWidth: 0 }}>
          <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--fg-2)', textTransform: 'uppercase', letterSpacing: '0.05em', whiteSpace: 'nowrap' }}>
            {t.cockpit.trendTitle}
          </span>
          {current != null && (
            <span style={{ display: 'inline-flex', alignItems: 'baseline', gap: 'var(--s3)' }}>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 28, fontWeight: 700, color: 'var(--fg)', lineHeight: 1 }}>{current} %</span>
              {delta != null && (
                // Delta als Chip statt loser Text — liest sich als Zustand, nicht als Rauschen.
                <span style={{
                  fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 700, color: trendColor,
                  display: 'inline-flex', alignItems: 'center', gap: 4,
                  padding: '2px 8px', borderRadius: 'var(--r-md)',
                  background: `color-mix(in srgb, ${trendColor} 12%, transparent)`,
                  border: `1px solid color-mix(in srgb, ${trendColor} 45%, transparent)`,
                }}>
                  <span aria-hidden>{trendGlyph}</span>{delta > 0 ? '+' : ''}{String(delta).replace('.', ',')}
                </span>
              )}
            </span>
          )}
        </div>
        <div role="group" aria-label={t.timeseries.rangeLabel} style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
          {WINDOWS.map(w => (
            <button key={w} style={chip(days === w)} onClick={() => setDays(w)}>
              {t.timeseries.range[`${w}d`] ?? `${w} T`}
            </button>
          ))}
        </div>
      </div>

      <div style={{ padding: 'var(--s3) var(--s3) var(--s1)' }}>
        {isLoading && !data ? (
          <div style={{ height: 200 }} className="skeleton" />
        ) : !hasData ? (
          <p style={{ color: 'var(--fg-3)', fontSize: 12, padding: '72px 8px', textAlign: 'center' }}>
            {isSuccess ? t.cockpit.trendEmpty : '—'}
          </p>
        ) : (
          <div style={{ height: 200 }}>
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={points} margin={{ top: 8, right: 12, bottom: 4, left: -8 }}>
                <defs>
                  <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={accent} stopOpacity={0.28} />
                    <stop offset="100%" stopColor={accent} stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="var(--line)" strokeDasharray="2 4" vertical={false} />
                <ReferenceLine
                  y={TARGET}
                  stroke="var(--status-ok)"
                  strokeOpacity={0.5}
                  strokeDasharray="4 4"
                  label={{ value: `${t.cockpit.trendTarget} ${TARGET}%`, position: 'insideTopRight', fill: 'var(--fg-3)', fontSize: 10 }}
                />
                <XAxis
                  dataKey="day"
                  tickFormatter={fmtDay}
                  tick={{ fill: 'var(--fg-3)', fontSize: 10 }}
                  stroke="var(--line)"
                  minTickGap={32}
                />
                <YAxis
                  domain={[0, 100]}
                  ticks={[0, 50, 100]}
                  tickFormatter={(v: number) => `${v}%`}
                  tick={{ fill: 'var(--fg-3)', fontSize: 10 }}
                  stroke="var(--line)"
                  width={44}
                />
                <Tooltip
                  contentStyle={{ background: 'var(--bg-2)', border: '1px solid var(--line-2)', borderRadius: 'var(--r-md)', fontSize: 11, color: 'var(--fg)' }}
                  labelFormatter={(v: string) => new Date(v).toLocaleDateString()}
                  formatter={(value: number, _n, item: { payload?: { passing: number; withRun: number } }) => {
                    const p = item?.payload;
                    const detail = p ? `  (${p.passing}/${p.withRun})` : '';
                    return [`${value}%${detail}`, t.cockpit.trendPassRate];
                  }}
                />
                <Area
                  type="monotone"
                  dataKey="pct"
                  stroke={accent}
                  strokeWidth={2}
                  fill={`url(#${gradientId})`}
                  dot={false}
                  activeDot={{ r: 4 }}
                  isAnimationActive={false}
                  connectNulls
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>
      {/* Legende statt Fließtext: Linien-Swatches erklären Kurve und Zielband. */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 'var(--s5)', flexWrap: 'wrap',
        color: 'var(--fg-3)', fontSize: 11, padding: '0 var(--s4) var(--s3)',
      }}>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
          <span aria-hidden style={{ width: 12, height: 2, background: accent, display: 'inline-block' }} />
          {t.cockpit.trendHint}
        </span>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
          <span aria-hidden style={{ width: 12, borderTop: '2px dashed color-mix(in srgb, var(--status-ok) 60%, transparent)', display: 'inline-block' }} />
          {t.cockpit.trendTarget} ≥ {TARGET} %
        </span>
      </div>
    </div>
  );
}
