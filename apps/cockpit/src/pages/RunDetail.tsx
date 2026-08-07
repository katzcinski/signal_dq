import { useParams, useNavigate, Link } from 'react-router-dom';
import { useRun } from '@/api/runs';
import { StatusPill } from '@/components/ui/StatusPill';
import { CheckStatusCell } from '@/components/ui/StatePill';
import { ErrorBanner } from '@/components/ui/ErrorBanner';
import { Table, type ColDef } from '@/components/ui/Table';
import { Breadcrumbs } from '@/components/ui/Breadcrumbs';
import { NotFoundState } from '@/components/ui/NotFoundState';
import { Button } from '@/components/ui/Button';
import { FilterChip } from '@/components/ui/FilterChip';
import { ObjectSummaryCard } from '@/components/object-detail/ObjectSummaryCard';
import { Skeleton, TableSkeleton } from '@/components/ui/Skeleton';
import { useSearchParamState } from '@/hooks/useSearchParamState';
import { t } from '@/i18n/de';
import type { CheckResult } from '@/types';

// CSV field escaping: double inner quotes, wrap in quotes, and neutralize
// formula injection by prefixing =, +, -, @ with a single quote.
function csvField(value: unknown): string {
  let s = String(value ?? '').replace(/"/g, '""');
  if (/^[=+\-@]/.test(s)) s = `'${s}`;
  return `"${s}"`;
}

// R6-3: layout-treues Skeleton statt „Lädt…"-Text — Hero-Zeile, Summary-Karten
// und Tabelle als Platzhalter, damit Laden als „Inhalt kommt hierher" liest.
function RunDetailSkeleton() {
  return (
    <div className="page-full">
      <div style={{ marginBottom: 20 }}>
        <Skeleton width={200} height={14} style={{ marginBottom: 16 }} />
        <div style={{ display: 'flex', gap: 'var(--s4)', alignItems: 'center', flexWrap: 'wrap' }}>
          <Skeleton width={260} height={16} />
          <Skeleton width={70} height={20} radius={999} />
        </div>
        <div className="object-detail-summary-grid" style={{ marginTop: 16 }}>
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="object-summary-card">
              <Skeleton width={70} height={10} />
              <div style={{ marginTop: 12 }}><Skeleton width={48} height={22} /></div>
            </div>
          ))}
        </div>
      </div>
      <TableSkeleton columns={6} />
    </div>
  );
}

export default function RunDetail() {
  const { id = '' } = useParams();
  const { data: run, isLoading, isError, refetch } = useRun(id);
  const navigate = useNavigate();
  const [failuresParam, setFailuresParam] = useSearchParamState('failures');
  const onlyFailures = failuresParam === '1';

  if (isLoading) return <RunDetailSkeleton />;
  if (isError) return <div className="page-full"><ErrorBanner onRetry={() => refetch()} /></div>;
  if (!run) {
    return (
      <div className="page-full">
        <Breadcrumbs items={[
          { label: t.breadcrumb.home, to: '/' },
          { label: t.breadcrumb.objects, to: '/objects' },
          { label: `${t.breadcrumb.runs} ${id.slice(0, 12)}…` },
        ]} />
        <NotFoundState
          title={t.runDetail.notFound}
          message={t.notFound.runMessage}
          actions={[
            { label: t.notFound.objects, to: '/objects', primary: true },
            { label: t.notFound.home, to: '/' },
          ]}
        />
      </div>
    );
  }

  const durationMs = run.started_at && run.finished_at
    ? new Date(run.finished_at).getTime() - new Date(run.started_at).getTime()
    : null;

  // „Nur Fehlschläge": alles außer bestanden — dafür kommt man auf die Seite.
  const failedResults = run.results.filter(r => !r.passed);
  const visibleResults = onlyFailures ? failedResults : run.results;

  const columns: ColDef<CheckResult>[] = [
    { key: 'name', header: t.runDetail.colCheck, mono: true, render: c => c.name },
    { key: 'status', header: t.runDetail.colStatus, render: c => <CheckStatusCell state={c.state} passed={c.passed} severity={c.severity} /> },
    { key: 'expect', header: t.runDetail.colExpect, mono: true, render: c => c.expect },
    { key: 'actual', header: t.runDetail.colActual, mono: true, render: c => c.actual_value ?? '—' },
    { key: 'error', header: t.runDetail.colError, render: c => c.error ? <span style={{ color: 'var(--status-fail)', fontSize: 11 }}>{c.error}</span> : null },
    { key: 'ms', header: t.runDetail.colMs, mono: true, render: c => String(c.duration_ms) },
  ];

  const downloadCSV = () => {
    const header = 'name,state,passed,expect,actual_value,severity,duration_ms,error\n';
    const rows = run.results.map(r =>
      [r.name, r.state, r.passed, r.expect, r.actual_value ?? '', r.severity, r.duration_ms, r.error ?? '']
        .map(csvField)
        .join(',')
    ).join('\n');
    const blob = new Blob([header + rows], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = `run_${run.run_id}.csv`; a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="page-full">
      <Breadcrumbs items={[
        { label: t.breadcrumb.home, to: '/' },
        { label: t.breadcrumb.objects, to: '/objects' },
        { label: run.dataset, to: `/objects/${encodeURIComponent(run.dataset)}` },
        { label: `${t.breadcrumb.runs} ${run.run_id.slice(0, 12)}…` },
      ]} />
      <div style={{ marginBottom: 20 }}>
        <Button variant="ghost" size="sm" onClick={() => navigate(`/objects/${encodeURIComponent(run.dataset)}`)} style={{ marginBottom: 12 }}>{t.runDetail.back}</Button>
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--s4)', flexWrap: 'wrap' }}>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--fg-2)' }}>{run.run_id}</span>
          <StatusPill status={run.overall_status} />
          {run.gate_verdict && (
            <span style={{
              display: 'inline-flex', alignItems: 'center', height: 22, padding: '0 10px',
              borderRadius: 'var(--r-full)', fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 650,
              border: '1px solid',
              borderColor: run.gate_verdict === 'block' ? 'var(--status-fail)' : run.gate_verdict === 'quarantine' ? 'var(--status-warn)' : 'var(--status-ok)',
              color: run.gate_verdict === 'block' ? 'var(--status-fail)' : run.gate_verdict === 'quarantine' ? 'var(--status-warn)' : 'var(--status-ok)',
            }} title={t.quarantine.verdictLabel[run.gate_verdict] ?? run.gate_verdict}>
              {t.quarantine.verdictLabel[run.gate_verdict] ?? run.gate_verdict}
            </span>
          )}
          <span style={{ color: 'var(--fg-3)', fontSize: 12 }}>{t.runDetail.dataset}: {run.dataset}</span>
          <span style={{ color: 'var(--fg-3)', fontSize: 12 }}>{t.runDetail.triggeredBy}: {run.triggered_by}</span>
          {durationMs !== null && <span style={{ color: 'var(--fg-3)', fontSize: 12 }}>{durationMs}ms</span>}
          <div style={{ flex: 1 }} />
          <Link
            to={`/runs/compare?head=${encodeURIComponent(run.run_id)}`}
            style={{ background: 'var(--bg-2)', border: '1px solid var(--line-2)', color: 'var(--fg-2)', borderRadius: 'var(--r-md)', padding: 'var(--s2) var(--s4)', fontSize: 12, textDecoration: 'none' }}
          >
            {t.compare.compareTo}
          </Link>
          <Button variant="secondary" onClick={downloadCSV}>{t.runDetail.downloadCsv}</Button>
        </div>
        <div className="object-detail-summary-grid" style={{ marginTop: 16 }}>
          <ObjectSummaryCard label={t.runDetail.total} value={run.total} />
          <ObjectSummaryCard label={t.runDetail.passed} value={run.passed} tone="var(--status-ok)" />
          <ObjectSummaryCard label={t.runDetail.failed} value={run.failed} tone="var(--status-fail)" />
          <ObjectSummaryCard label={t.runDetail.warnings} value={run.warnings} tone="var(--status-warn)" />
        </div>
      </div>
      <div style={{ display: 'flex', gap: 'var(--s2)', marginBottom: 12, flexWrap: 'wrap' }}>
        <FilterChip active={!onlyFailures} onClick={() => setFailuresParam('')}>
          {t.runDetail.allChecks}
        </FilterChip>
        <FilterChip active={onlyFailures} onClick={() => setFailuresParam('1')}>
          {`${t.runDetail.onlyFailures} (${failedResults.length})`}
        </FilterChip>
      </div>
      <div style={{ background: 'var(--bg-1)', border: '1px solid var(--line)', borderRadius: 'var(--r-lg)', overflow: 'hidden' }}>
        <Table columns={columns} rows={visibleResults} rowKey={c => c.name} empty={t.runDetail.noResults} />
      </div>
    </div>
  );
}
