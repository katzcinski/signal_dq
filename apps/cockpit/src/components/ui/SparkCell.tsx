import { Spark } from './Spark';

// R6-2: a metric cell = latest value + delta vs. previous + a 14-point
// sparkline. `series` is oldest→newest.
interface Props {
  series: number[];
  unit?: string;
  width?: number;
}

const N = 14;

export function SparkCell({ series, unit = '', width = 64 }: Props) {
  const points = series.slice(-N);
  if (points.length === 0) return <span style={{ color: 'var(--fg-3)', fontSize: 11 }}>—</span>;

  const latest = points[points.length - 1];
  const prev = points.length > 1 ? points[points.length - 2] : latest;
  const delta = latest - prev;
  const deltaPct = prev !== 0 ? (delta / Math.abs(prev)) * 100 : 0;
  const dir = delta > 0 ? '▲' : delta < 0 ? '▼' : '·';
  // Neutral colour: a metric moving is not inherently good/bad.
  const fmt = (n: number) => (Number.isInteger(n) ? String(n) : n.toFixed(2));

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--s2)' }}>
      <div style={{ minWidth: 56 }}>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--fg)' }}>{fmt(latest)}{unit}</div>
        {points.length > 1 && (
          <div style={{ fontSize: 10, color: 'var(--fg-3)' }}>{dir} {fmt(Math.abs(delta))}{prev !== 0 ? ` (${Math.abs(deltaPct).toFixed(0)}%)` : ''}</div>
        )}
      </div>
      {points.length > 1 && <Spark data={points} width={width} color="var(--fg-2)" />}
    </div>
  );
}
