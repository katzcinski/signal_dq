import { useExpectationBacktest } from '@/api/contracts';
import { t } from '@/i18n/de';

// V1: „hätte N× in 90 d gefeuert" — Evidenz für Proposal-Entscheidungen aus der
// gespeicherten Messwert-Historie (rein lesend, react-query dedupliziert).
export function BacktestBadge({ product, checkName, expect }: {
  product: string; checkName: string; expect: string;
}) {
  const { data, isError } = useExpectationBacktest(product, checkName, expect);
  if (isError || !data) return null;

  const check = data.checks[0];
  if (!check || check.points === 0) {
    return (
      <span style={{
        fontSize: 10, borderRadius: 'var(--r)', padding: '2px 8px',
        background: 'var(--bg-3)', color: 'var(--fg-3)', border: '1px solid var(--line-2)',
      }}>{t.backtest.badgeNoData}</span>
    );
  }

  const days = data.window_days[data.window_days.length - 1] ?? 90;
  const w = check.windows.find(x => x.days === days);
  const n = w?.breaches ?? 0;
  const color = n > 0 ? 'var(--status-warn)' : 'var(--status-ok)';
  return (
    <span style={{
      fontSize: 10, borderRadius: 'var(--r)', padding: '2px 8px', whiteSpace: 'nowrap',
      background: `color-mix(in srgb, ${color} 12%, transparent)`,
      color, border: `1px solid ${color}`,
    }}>
      {n > 0
        ? t.backtest.badge.replace('{n}', String(n)).replace('{days}', String(days))
        : t.backtest.badgeClean.replace('{days}', String(days))}
    </span>
  );
}
