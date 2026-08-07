import { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useSchemaDriftOverview, useSchemaEvolution } from '@/api/schemaDrift';
import { Table, type ColDef } from '@/components/ui/Table';
import { StatusDot } from '@/components/ui/StatusDot';
import { ErrorBanner } from '@/components/ui/ErrorBanner';
import { PageHeader } from '@/components/ui/PageHeader';
import { TableSkeleton } from '@/components/ui/Skeleton';
import { ObjectSummaryCard } from '@/components/object-detail/ObjectSummaryCard';
import { useSearchParamState } from '@/hooks/useSearchParamState';
import { relativeTime, absoluteTime } from '@/lib/time';
import { t } from '@/i18n/de';
import type {
  SchemaDriftHistoryRow, SchemaDriftObjectRow, SchemaEvolutionChange, SchemaEvolutionStep,
} from '@/types';

// A2/UX-N9: Schema-Evolution je Objekt über Zeit. Datenpfad (Snapshots + Drift-
// Befunde) entsteht beim Extrakt; dieser Screen liest nur.

function driftStatus(r: SchemaDriftObjectRow): string {
  if (r.breaking > 0) return 'fail';
  if (r.findings > 0) return 'warn';
  return 'pass';
}

function BreakingBadge() {
  return (
    <span style={{
      fontSize: 9, textTransform: 'uppercase', letterSpacing: '0.05em',
      color: 'var(--status-fail)', border: '1px solid var(--status-fail)',
      borderRadius: 'var(--r)', padding: '1px 5px', whiteSpace: 'nowrap',
    }}>{t.drift.breakingBadge}</span>
  );
}

function categoryLabel(category: string): string {
  return t.drift.categories[category] ?? category;
}

function ChangeTable({ changes }: { changes: SchemaEvolutionChange[] }) {
  const columns: ColDef<SchemaEvolutionChange>[] = [
    { key: 'category', header: t.drift.colCategory, render: c => categoryLabel(c.category) },
    { key: 'column', header: t.drift.colColumn, mono: true, render: c => c.column },
    { key: 'before', header: t.objectDiff.colBase, mono: true, render: c => c.before || '—' },
    { key: 'after', header: t.objectDiff.colHead, mono: true, render: c => c.after || '—' },
  ];
  return <Table columns={columns} rows={changes} rowKey={c => `${c.category}:${c.column}`} />;
}

function StepCard({ step }: { step: SchemaEvolutionStep }) {
  return (
    <div style={{
      background: 'var(--bg-1)', border: '1px solid var(--line)',
      borderLeft: '3px solid var(--obs)', borderRadius: 'var(--r-lg)',
      padding: 'var(--s3)', display: 'flex', flexDirection: 'column', gap: 'var(--s2)',
    }}>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--fg-2)' }}>
        {t.schemaDrift.stepAt
          .replace('{from}', absoluteTime(step.from_at))
          .replace('{to}', absoluteTime(step.to_at))}
      </div>
      <ChangeTable changes={step.changes} />
    </div>
  );
}

function EvolutionDetail({ objectName }: { objectName: string }) {
  const { data, isLoading, isError, refetch } = useSchemaEvolution(objectName);
  const navigate = useNavigate();

  if (isError) return <ErrorBanner onRetry={() => refetch()} />;
  if (isLoading || !data) return <TableSkeleton columns={4} />;

  const eventColumns: ColDef<SchemaDriftHistoryRow>[] = [
    {
      key: 'detected', header: t.schemaDrift.colDetected, width: 150,
      render: e => (
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }} title={absoluteTime(e.detected_at)}>
          {relativeTime(e.detected_at)}
        </span>
      ),
    },
    {
      key: 'category', header: t.drift.colCategory,
      render: e => (
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
          {e.breaking === 1 && <BreakingBadge />}
          {categoryLabel(e.category)}
        </span>
      ),
    },
    { key: 'column', header: t.drift.colColumn, mono: true, render: e => e.column_name },
    { key: 'before', header: t.drift.colPromised, mono: true, render: e => e.before_value || '—' },
    { key: 'after', header: t.drift.colActual, mono: true, render: e => e.after_value || '—' },
    { key: 'version', header: t.schemaDrift.colVersion, mono: true, width: 90, render: e => e.contract_version || '—' },
    {
      key: 'incident', header: t.schemaDrift.colIncident, width: 110,
      render: e => e.incident_id == null ? <span style={{ color: 'var(--fg-3)' }}>—</span> : (
        <button
          onClick={ev => { ev.stopPropagation(); navigate(`/incidents?id=${e.incident_id}`); }}
          title={t.schemaDrift.openIncident.replace('{id}', String(e.incident_id))}
          style={{
            background: 'transparent', border: '1px solid var(--line-2)', borderRadius: 'var(--r-md)',
            color: 'var(--status-fail)', fontFamily: 'var(--font-mono)', fontSize: 12,
            padding: '3px 8px', cursor: 'pointer',
          }}
        >#{e.incident_id}</button>
      ),
    },
  ];

  const first = data.snapshots[0];
  return (
    <section aria-label={t.schemaDrift.detailTitle.replace('{object}', data.object_name)}
      style={{ display: 'flex', flexDirection: 'column', gap: 'var(--s4)', marginTop: 'var(--s5)' }}>
      <div>
        <h2 style={{ fontSize: 15, fontWeight: 700, color: 'var(--fg)', margin: 0, fontFamily: 'var(--font-mono)' }}>
          {t.schemaDrift.detailTitle.replace('{object}', data.object_name)}
        </h2>
        <div style={{ fontSize: 12, color: 'var(--fg-3)', marginTop: 2 }}>
          {first && t.schemaDrift.snapshotsLabel
            .replace('{n}', String(data.snapshots.length))
            .replace('{first}', absoluteTime(first.captured_at))}
          {data.contract && (
            <> · {data.contract.product} v{data.contract.version} · {data.contract.kind}</>
          )}
        </div>
      </div>

      <div>
        <h3 style={{ fontSize: 13, fontWeight: 650, color: 'var(--fg-2)', margin: '0 0 8px' }}>
          {t.schemaDrift.stepsTitle}
        </h3>
        {data.steps.length === 0
          ? <div style={{ color: 'var(--fg-3)', fontSize: 12.5 }}>{t.schemaDrift.noSteps}</div>
          : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--s3)' }}>
              {data.steps.map(s => <StepCard key={`${s.from_id}-${s.to_id}`} step={s} />)}
            </div>
          )}
      </div>

      <div>
        <h3 style={{ fontSize: 13, fontWeight: 650, color: 'var(--fg-2)', margin: '0 0 8px' }}>
          {t.schemaDrift.eventsTitle}
        </h3>
        {data.drift_events.length === 0
          ? <div style={{ color: 'var(--fg-3)', fontSize: 12.5 }}>{t.schemaDrift.noEvents}</div>
          : (
            <div style={{ background: 'var(--bg-1)', border: '1px solid var(--line)', borderRadius: 'var(--r-lg)', overflow: 'hidden' }}>
              <Table columns={eventColumns} rows={data.drift_events} rowKey={e => String(e.id)} />
            </div>
          )}
      </div>
    </section>
  );
}

export default function SchemaDrift() {
  const { data: rows = [], isLoading, isError, refetch } = useSchemaDriftOverview();
  const [selected, setSelected] = useSearchParamState('object');

  const stats = useMemo(() => {
    let drifted = 0, breaking = 0;
    let last: string | null = null;
    for (const r of rows) {
      if (r.findings > 0) drifted++;
      if (r.breaking > 0) breaking++;
      if (r.last_detected_at && (!last || r.last_detected_at > last)) last = r.last_detected_at;
    }
    return { drifted, breaking, last };
  }, [rows]);

  const columns: ColDef<SchemaDriftObjectRow>[] = [
    { key: 'dot', header: '', width: 28, render: r => <StatusDot status={driftStatus(r)} size={9} /> },
    {
      key: 'object', header: t.schemaDrift.colObject, sortable: true, sortValue: r => r.object_name,
      render: r => (
        <div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 13, fontWeight: 650, color: 'var(--fg)' }}>{r.object_name}</div>
          <div style={{ fontSize: 11, color: 'var(--fg-3)' }}>
            {r.product ? `${r.product} v${r.contract_version} · ${r.kind}` : t.schemaDrift.contractless}
          </div>
        </div>
      ),
    },
    {
      key: 'snapshots', header: t.schemaDrift.colSnapshots, width: 100, sortable: true, sortValue: r => r.snapshots,
      render: r => <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}>{r.snapshots}</span>,
    },
    {
      key: 'schemas', header: t.schemaDrift.colSchemas, width: 100, sortable: true, sortValue: r => r.distinct_schemas,
      render: r => (
        <span style={{
          fontFamily: 'var(--font-mono)', fontSize: 12,
          color: r.distinct_schemas > 1 ? 'var(--status-warn)' : 'var(--fg-2)',
          fontWeight: r.distinct_schemas > 1 ? 700 : 400,
        }}>{r.distinct_schemas}</span>
      ),
    },
    {
      key: 'columns', header: t.schemaDrift.colColumns, width: 90,
      render: r => <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--fg-2)' }}>{r.column_count ?? '—'}</span>,
    },
    {
      key: 'findings', header: t.schemaDrift.colFindings, width: 130, sortable: true, sortValue: r => r.findings,
      render: r => r.findings === 0 ? <span style={{ color: 'var(--fg-3)' }}>—</span> : (
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontFamily: 'var(--font-mono)', fontSize: 12 }}>
          {r.findings}
          {r.breaking > 0 && <BreakingBadge />}
        </span>
      ),
    },
    {
      key: 'last', header: t.schemaDrift.colLastDrift, width: 140, sortable: true,
      sortValue: r => r.last_detected_at ?? '',
      render: r => (
        <span
          style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: r.breaking > 0 ? 'var(--status-fail)' : 'var(--fg-2)' }}
          title={r.last_detected_at ? absoluteTime(r.last_detected_at) : undefined}
        >
          {r.last_detected_at ? relativeTime(r.last_detected_at) : '—'}
        </span>
      ),
    },
  ];

  return (
    <div className="page-full">
      <PageHeader title={t.schemaDrift.title} subtitle={t.schemaDrift.subtitle} />

      <div className="dash-kpis" style={{ marginBottom: 22 }}>
        <ObjectSummaryCard
          label={t.schemaDrift.kpiObjects}
          value={rows.length}
          hint={t.schemaDrift.kpiObjectsSub}
        />
        <ObjectSummaryCard
          label={t.schemaDrift.kpiDrifted}
          tone={stats.drifted ? 'var(--status-warn)' : undefined}
          value={stats.drifted}
        />
        <ObjectSummaryCard
          label={t.schemaDrift.kpiBreaking}
          tone={stats.breaking ? 'var(--status-fail)' : 'var(--cont)'}
          value={stats.breaking}
          hint={t.schemaDrift.kpiBreakingSub}
        />
        <ObjectSummaryCard
          label={t.schemaDrift.kpiLastDetected}
          value={stats.last ? relativeTime(stats.last) : '—'}
          hint={stats.last ? absoluteTime(stats.last) : undefined}
        />
      </div>

      {isError && <ErrorBanner onRetry={() => refetch()} />}
      {isLoading && <TableSkeleton columns={7} />}
      {!isError && !isLoading && (
        <div style={{ background: 'var(--bg-1)', border: '1px solid var(--line)', borderRadius: 'var(--r-lg)', overflow: 'hidden' }}>
          <Table
            columns={columns}
            rows={rows}
            rowKey={r => r.object_name}
            onRowClick={r => setSelected(r.object_name === selected ? '' : r.object_name)}
            empty={t.schemaDrift.empty}
          />
        </div>
      )}

      {!isError && !isLoading && rows.length > 0 && !selected && (
        <div style={{ color: 'var(--fg-3)', fontSize: 12.5, marginTop: 'var(--s3)' }}>
          {t.schemaDrift.selectHint}
        </div>
      )}
      {selected && <EvolutionDetail objectName={selected} />}
    </div>
  );
}
