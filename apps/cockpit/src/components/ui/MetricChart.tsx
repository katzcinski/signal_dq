import {
  ComposedChart, Line, ReferenceArea, ReferenceLine, XAxis, YAxis,
  Tooltip, ResponsiveContainer, CartesianGrid,
} from 'recharts';
import type { MetricSeries } from '@/types';
import { t } from '@/i18n/de';

// UX-N1 / UX-N11: a single freshness/volume series rendered with its expected
// band (baseline mean ± 3σ as a shaded ReferenceArea), the mean as a dashed
// reference line, and anomaly points marked in red. Replaces the 80px sparkline
// — answers "since when is this drifting?".

const METRIC_COLOR: Record<string, string> = {
  freshness: 'var(--obs)',
  volume: 'var(--cont)',
  observability: 'var(--fg-2)',
};

interface Row {
  i: number;
  at: string;
  value: number | null;
  anomaly: boolean;
}

// Anomaly-aware dot: red ring for out-of-band/failed points, hidden otherwise.
function makeDot(rows: Row[], color: string) {
  return function Dot(props: { cx?: number; cy?: number; index?: number }) {
    const { cx, cy, index } = props;
    if (cx == null || cy == null || index == null) return <g />;
    const row = rows[index];
    if (!row || row.value === null) return <g />;
    if (row.anomaly) {
      return <circle cx={cx} cy={cy} r={3.5} fill="var(--status-crit)" stroke="var(--bg-1)" strokeWidth={1} />;
    }
    return <circle cx={cx} cy={cy} r={1.6} fill={color} />;
  };
}

function fmtTime(iso: string) {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

export function MetricChart({ series }: { series: MetricSeries }) {
  const color = METRIC_COLOR[series.metric] ?? 'var(--cont)';
  const rows: Row[] = series.points.map((p, i) => ({ i, at: p.at, value: p.value, anomaly: p.anomaly }));
  const numeric = rows.filter(r => r.value !== null);
  const anomalyCount = series.points.filter(p => p.anomaly).length;
  const band = series.baseline;

  const label = t.timeseries.metric[series.metric] ?? series.metric;

  if (numeric.length < 2) {
    return (
      <div style={{ background: 'var(--bg-1)', border: '1px solid var(--line)', borderRadius: 'var(--r-lg)', padding: 'var(--s4)', marginBottom: 12 }}>
        <Header name={series.check_name} label={label} color={color} anomalyCount={anomalyCount} />
        <p style={{ color: 'var(--fg-3)', fontSize: 12, marginTop: 8 }}>{t.timeseries.tooFew}</p>
      </div>
    );
  }

  return (
    <div style={{ background: 'var(--bg-1)', border: '1px solid var(--line)', borderRadius: 'var(--r-lg)', padding: 'var(--s4)', marginBottom: 12 }}>
      <Header name={series.check_name} label={label} color={color} anomalyCount={anomalyCount} />
      <div style={{ height: 180, marginTop: 12 }}>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={rows} margin={{ top: 8, right: 12, bottom: 4, left: 4 }}>
            <CartesianGrid stroke="var(--line)" strokeDasharray="2 4" vertical={false} />
            {band && (
              <ReferenceArea
                y1={band.lower}
                y2={band.upper}
                fill={color}
                fillOpacity={0.08}
                stroke="none"
                ifOverflow="extendDomain"
              />
            )}
            {band && (
              <ReferenceLine
                y={band.mean}
                stroke={color}
                strokeOpacity={0.5}
                strokeDasharray="4 4"
                ifOverflow="extendDomain"
              />
            )}
            <XAxis
              dataKey="at"
              tickFormatter={fmtTime}
              tick={{ fill: 'var(--fg-3)', fontSize: 10 }}
              stroke="var(--line)"
              minTickGap={24}
            />
            <YAxis
              tick={{ fill: 'var(--fg-3)', fontSize: 10 }}
              stroke="var(--line)"
              width={44}
              domain={['auto', 'auto']}
            />
            <Tooltip
              contentStyle={{
                background: 'var(--bg-2)', border: '1px solid var(--line-2)',
                borderRadius: 'var(--r-md)', fontSize: 11, color: 'var(--fg)',
              }}
              labelFormatter={(v: string) => new Date(v).toLocaleString()}
              formatter={(value: number, _n, item: { payload?: Row }) => {
                const anom = item?.payload?.anomaly;
                return [`${value}${anom ? '  ⚠' : ''}`, label];
              }}
            />
            <Line
              type="monotone"
              dataKey="value"
              stroke={color}
              strokeWidth={1.75}
              dot={makeDot(rows, color)}
              activeDot={{ r: 4 }}
              isAnimationActive={false}
              connectNulls
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      {band && (
        <p style={{ color: 'var(--fg-3)', fontSize: 10, marginTop: 6, fontFamily: 'var(--font-mono)' }}>
          {t.timeseries.band}: {round(band.lower)} – {round(band.upper)} · {t.timeseries.mean} {round(band.mean)}
        </p>
      )}
    </div>
  );
}

function round(n: number) {
  return Math.abs(n) >= 100 ? Math.round(n) : Math.round(n * 100) / 100;
}

function Header({ name, label, color, anomalyCount }: {
  name: string; label: string; color: string; anomalyCount: number;
}) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
      <span style={{ width: 8, height: 8, borderRadius: 2, background: color }} />
      <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--fg-2)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>{label}</span>
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--fg-3)' }}>{name}</span>
      <div style={{ flex: 1 }} />
      {anomalyCount > 0 && (
        <span style={{ fontSize: 10, color: 'var(--status-crit)', display: 'inline-flex', alignItems: 'center', gap: 'var(--s1)' }}>
          ⚠ {anomalyCount} {t.timeseries.anomalies}
        </span>
      )}
    </div>
  );
}
