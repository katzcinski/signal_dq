import { useEffect, useMemo, useState } from 'react';
import { useSearchParams, Link } from 'react-router-dom';
import { useRuns, useRunCompare } from '@/api/runs';
import { Table, type ColDef } from '@/components/ui/Table';
import { Breadcrumbs } from '@/components/ui/Breadcrumbs';
import { ErrorBanner } from '@/components/ui/ErrorBanner';
import { PageHeader } from '@/components/ui/PageHeader';
import { t } from '@/i18n/de';
import type { CheckChange, CheckCompareStatus, CheckTransition, RunListItem } from '@/types';

const STATUS_COLOR: Record<string, string> = {
  pass: 'var(--status-ok)',
  fail: 'var(--status-fail)',
  error: 'var(--status-fail)',
  warn: 'var(--status-warn)',
  skipped: 'var(--fg-3)',
};

const TRANSITION_COLOR: Record<CheckTransition, string> = {
  regressed: 'var(--status-fail)',
  recovered: 'var(--status-ok)',
  added: 'var(--cont)',
  removed: 'var(--fg-3)',
  changed: 'var(--status-warn)',
  unchanged: 'var(--fg-3)',
};

// Sort so the meaningful transitions surface first.
const TRANSITION_ORDER: Record<CheckTransition, number> = {
  regressed: 0, recovered: 1, added: 2, removed: 3, changed: 4, unchanged: 5,
};

function StatusBadge({ status }: { status: CheckCompareStatus | null }) {
  if (!status) return <span style={{ color: 'var(--fg-3)' }}>{t.compare.absent}</span>;
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 12 }}>
      <span style={{ width: 7, height: 7, borderRadius: '50%', background: STATUS_COLOR[status] ?? 'var(--fg-3)' }} />
      {t.status[status] ?? status}
    </span>
  );
}

function TransitionBadge({ transition }: { transition: CheckTransition }) {
  const color = TRANSITION_COLOR[transition];
  return (
    <span style={{
      fontSize: 10, borderRadius: 'var(--r)', padding: '2px 8px',
      background: `color-mix(in srgb, ${color} 15%, transparent)`,
      color, border: `1px solid ${color}`,
    }}>
      {t.compare.transition[transition] ?? transition}
    </span>
  );
}

// B-1 Value-Diff (§B.2): vorher → nachher je Check, mit Richtung & Δ%.
function ValueCell({ change }: { change: CheckChange }) {
  const vd = change.value_delta;
  if (!vd || (vd.base == null && vd.head == null)) return <span style={{ color: 'var(--fg-3)' }}>—</span>;
  const hasPct = vd.pct_delta != null && vd.pct_delta !== 0;
  const up = (vd.abs_delta ?? 0) > 0;
  return (
    <span style={{ fontSize: 12, fontFamily: 'var(--font-mono)' }}>
      <span style={{ color: 'var(--fg-2)' }}>{vd.base ?? '—'} → {vd.head ?? '—'}</span>
      {hasPct && (
        <span style={{ color: up ? 'var(--status-warn)' : 'var(--cont)', marginLeft: 6 }}>
          {up ? '▲' : '▼'} {Math.abs(vd.pct_delta as number)}%
        </span>
      )}
    </span>
  );
}

function RunOption(r: RunListItem) {
  const when = r.started_at ? new Date(r.started_at).toLocaleString() : r.run_id.slice(0, 8);
  return `${r.dataset} · ${r.run_id.slice(0, 8)} · ${when} · ${r.overall_status}`;
}

export default function RunCompare() {
  const [sp, setSp] = useSearchParams();
  const base = sp.get('base') ?? '';
  const head = sp.get('head') ?? '';
  const [onlyChanges, setOnlyChanges] = useState(true);

  const { data: runs = [] } = useRuns();
  const { data: cmp, isLoading, isError, refetch } = useRunCompare(base, head);

  // Scope the pickers to the dataset of whichever run is already chosen.
  const dataset = useMemo(() => {
    const byId = new Map(runs.map(r => [r.run_id, r]));
    return byId.get(base)?.dataset ?? byId.get(head)?.dataset ?? '';
  }, [runs, base, head]);
  const pickerRuns = dataset ? runs.filter(r => r.dataset === dataset) : runs;

  const setRun = (which: 'base' | 'head', value: string) => {
    const next = new URLSearchParams(sp);
    if (value) next.set(which, value); else next.delete(which);
    setSp(next);
  };

  // Entry from RunDetail sets only ?head — auto-pick the immediately prior run
  // of the same dataset as the baseline so the diff is one click away.
  useEffect(() => {
    if (!head || base || pickerRuns.length < 2) return;
    const ordered = [...pickerRuns].sort((a, b) => b.started_at.localeCompare(a.started_at));
    const idx = ordered.findIndex(r => r.run_id === head);
    const prior = idx >= 0 ? ordered[idx + 1] : undefined;
    if (prior) {
      const next = new URLSearchParams(sp);
      next.set('base', prior.run_id);
      setSp(next, { replace: true });
    }
  }, [head, base, pickerRuns, sp, setSp]);

  const sortedChanges = useMemo(() => {
    const rows = [...(cmp?.changes ?? [])];
    rows.sort((a, b) =>
      (TRANSITION_ORDER[a.transition] - TRANSITION_ORDER[b.transition]) ||
      a.check_name.localeCompare(b.check_name));
    return onlyChanges ? rows.filter(r => r.transition !== 'unchanged') : rows;
  }, [cmp, onlyChanges]);

  const columns: ColDef<CheckChange>[] = [
    { key: 'check_name', header: t.compare.colCheck, mono: true, render: c => c.check_name },
    { key: 'base', header: t.compare.colBase, render: c => <StatusBadge status={c.base_status} /> },
    { key: 'head', header: t.compare.colHead, render: c => <StatusBadge status={c.head_status} /> },
    { key: 'value', header: t.compare.colValue, render: c => <ValueCell change={c} /> },
    { key: 'change', header: t.compare.colChange, render: c => <TransitionBadge transition={c.transition} /> },
  ];

  const selectStyle = {
    background: 'var(--bg-2)', border: '1px solid var(--line-2)', color: 'var(--fg)',
    borderRadius: 'var(--r-md)', padding: '7px 10px', fontSize: 12, minWidth: 280, maxWidth: '100%',
  } as const;

  return (
    <div className="page-full">
      <Breadcrumbs items={[
        { label: t.breadcrumb.home, to: '/' },
        { label: t.breadcrumb.objects, to: '/objects' },
        { label: t.compare.title },
      ]} />
      <PageHeader title={t.compare.title} subtitle={t.compare.subtitle} />

      <div style={{ display: 'flex', gap: 'var(--s4)', flexWrap: 'wrap', marginBottom: 20 }}>
        <label style={{ display: 'flex', flexDirection: 'column', gap: 'var(--s1)' }}>
          <span style={{ fontSize: 10, color: 'var(--fg-3)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>{t.compare.base}</span>
          <select style={selectStyle} value={base} onChange={e => setRun('base', e.target.value)}>
            <option value="">{t.compare.pickRun}</option>
            {pickerRuns.map(r => <option key={r.run_id} value={r.run_id}>{RunOption(r)}</option>)}
          </select>
        </label>
        <label style={{ display: 'flex', flexDirection: 'column', gap: 'var(--s1)' }}>
          <span style={{ fontSize: 10, color: 'var(--fg-3)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>{t.compare.head}</span>
          <select style={selectStyle} value={head} onChange={e => setRun('head', e.target.value)}>
            <option value="">{t.compare.pickRun}</option>
            {pickerRuns.map(r => <option key={r.run_id} value={r.run_id}>{RunOption(r)}</option>)}
          </select>
        </label>
      </div>

      {isError && <ErrorBanner onRetry={() => refetch()} />}
      {(!base || !head || base === head) && (
        <p style={{ color: 'var(--fg-3)', fontSize: 13, padding: 'var(--s6) 0' }}>{t.compare.needTwo}</p>
      )}
      {base && head && base !== head && isLoading && (
        <p style={{ color: 'var(--fg-3)', padding: 'var(--s6)' }}>{t.common.loading}</p>
      )}

      {cmp && (
        <>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginBottom: 16 }}>
            {(['regressed', 'recovered', 'added', 'removed', 'changed'] as CheckTransition[]).map(k => (
              <div key={k} style={{
                display: 'flex', alignItems: 'center', gap: 'var(--s2)',
                background: 'var(--bg-1)', border: '1px solid var(--line)',
                borderRadius: 'var(--r-md)', padding: '6px 12px',
              }}>
                <span style={{ width: 8, height: 8, borderRadius: '50%', background: TRANSITION_COLOR[k] }} />
                <span style={{ fontSize: 12, color: 'var(--fg-2)' }}>{t.compare.transition[k]}</span>
                <span style={{ fontSize: 14, fontWeight: 700, fontFamily: 'var(--font-mono)' }}>{cmp.summary[k] ?? 0}</span>
              </div>
            ))}
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--s4)', marginBottom: 8 }}>
            <span style={{ fontSize: 11, color: 'var(--fg-3)', fontFamily: 'var(--font-mono)' }}>
              <Link to={`/runs/${cmp.base.run_id}`} style={{ color: 'var(--cont)' }}>{cmp.base.run_id.slice(0, 10)}…</Link>
              {' → '}
              <Link to={`/runs/${cmp.head.run_id}`} style={{ color: 'var(--cont)' }}>{cmp.head.run_id.slice(0, 10)}…</Link>
            </span>
            <div style={{ flex: 1 }} />
            <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: 'var(--fg-3)', cursor: 'pointer' }}>
              <input type="checkbox" checked={onlyChanges} onChange={e => setOnlyChanges(e.target.checked)} />
              {t.compare.onlyChanges}
            </label>
          </div>

          <div style={{ background: 'var(--bg-1)', border: '1px solid var(--line)', borderRadius: 'var(--r-lg)', overflow: 'hidden' }}>
            <Table columns={columns} rows={sortedChanges} rowKey={c => c.check_name} empty={t.compare.noChanges} />
          </div>
        </>
      )}
    </div>
  );
}
