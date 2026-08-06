// V1 Garantie-Backtesting: simuliert den Entwurf gegen die gespeicherte
// Messwert-Historie (rein lesend, kein Lauf gegen HANA) — Schwellwerte vor der
// Aktivierung kalibrieren statt Alert-Fatigue ernten.
import { useBacktestContract } from '@/api/contracts';
import { Button } from '@/components/ui/Button';
import { Table, type ColDef } from '@/components/ui/Table';
import { relativeTime, absoluteTime } from '@/lib/time';
import { t } from '@/i18n/de';
import { cardStyle } from './shared';
import type { BacktestCheck, ContractPutBody } from '@/types';

function windowOf(check: BacktestCheck, days: number) {
  return check.windows.find(w => w.days === days);
}

export function BacktestPanel({ product, draft }: { product: string; draft: ContractPutBody }) {
  const backtest = useBacktestContract(product);
  const data = backtest.data;
  const days = data ? data.window_days[data.window_days.length - 1] ?? 90 : 90;
  const summary = data?.summary_windows.find(w => w.days === days);

  const columns: ColDef<BacktestCheck>[] = [
    {
      key: 'check', header: t.backtest.colCheck,
      render: c => <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, fontWeight: 650 }}>{c.check_name}</span>,
    },
    { key: 'expect', header: t.backtest.colExpect, mono: true, render: c => c.expect },
    {
      key: 'points', header: t.backtest.colPoints, width: 80,
      render: c => <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--fg-2)' }}>{c.points}</span>,
    },
    ...(data?.window_days ?? []).map((d): ColDef<BacktestCheck> => ({
      key: `w${d}`, header: t.backtest.windowShort.replace('{days}', String(d)), width: 70,
      render: c => {
        const w = windowOf(c, d);
        const n = w?.breaches ?? 0;
        return (
          <span style={{
            fontFamily: 'var(--font-mono)', fontSize: 12, fontWeight: n > 0 ? 700 : 400,
            color: n > 0 ? 'var(--status-fail)' : 'var(--fg-3)',
          }}>{w ? n : '—'}</span>
        );
      },
    })),
    {
      key: 'rate', header: t.backtest.colRate, width: 70,
      render: c => (
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: c.breaches > 0 ? 'var(--status-warn)' : 'var(--fg-3)' }}>
          {c.evaluated > 0 ? `${Math.round(c.breach_rate * 100)}%` : '—'}
        </span>
      ),
    },
    {
      key: 'last', header: t.backtest.colLastBreach, width: 130,
      render: c => (
        <span
          style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--fg-2)' }}
          title={c.last_breach_at ? absoluteTime(c.last_breach_at) : undefined}
        >
          {c.last_breach_at ? relativeTime(c.last_breach_at) : '—'}
        </span>
      ),
    },
  ];

  return (
    <div style={cardStyle}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12, flexWrap: 'wrap', gap: 'var(--s2)' }}>
        <div>
          <div style={{ fontWeight: 600, fontSize: 14 }}>{t.backtest.title}</div>
          <div style={{ fontSize: 12, color: 'var(--fg-3)', marginTop: 2 }}>{t.backtest.subtitle}</div>
        </div>
        <Button
          type="button"
          size="sm"
          onClick={() => backtest.mutate(draft)}
          disabled={backtest.isPending}
        >
          {backtest.isPending ? t.backtest.running : t.backtest.run}
        </Button>
      </div>

      {backtest.isError && (
        <div style={{ color: 'var(--status-fail)', fontSize: 12 }}>{t.backtest.error}</div>
      )}

      {data && data.checks_with_history === 0 && (
        <div style={{ color: 'var(--fg-3)', fontSize: 12.5 }}>{t.backtest.noHistory}</div>
      )}

      {data && data.checks_with_history > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--s3)' }}>
          <div style={{
            fontSize: 12.5, fontWeight: 600,
            color: (summary?.breaches ?? 0) > 0 ? 'var(--status-warn)' : 'var(--status-ok)',
          }}>
            {(summary?.breaches ?? 0) > 0
              ? t.backtest.summary
                  .replace('{fired}', String(summary?.checks_firing ?? 0))
                  .replace('{total}', String(data.checks_total))
                  .replace('{breaches}', String(summary?.breaches ?? 0))
                  .replace('{days}', String(days))
              : t.backtest.summaryClean.replace('{days}', String(days))}
          </div>
          <Table columns={columns} rows={data.checks} rowKey={c => c.check_name} />
        </div>
      )}
    </div>
  );
}
