import { useMemo, useState } from 'react';
import { useColumnImpact, useColumnLineage } from '@/api/lineage';
import { Table, type ColDef } from '@/components/ui/Table';
import { Field, Select } from '@/components/ui/Field';
import { SectionHeader } from '@/components/ui/SectionHeader';
import { Tooltip } from '@/components/ui/Tooltip';
import { ColumnLineageSkeleton } from '@/components/object-detail/ObjectDetailSkeletons';
import { t } from '@/i18n/de';
import type {
  ColumnEdgeType,
  ColumnImpactRow,
  ColumnLineageObjectResponse,
  ColumnLineageStep,
} from '@/types';

// UX-N7 / WS-D: column-level lineage (upstream/downstream DAG) + transitive
// downstream impact list with ownership. Reads the existing column-lineage API
// (build_column_lineage) plus the new /columns/impact endpoint.

const EDGE_LABEL: Record<string, string> = {
  direct: t.columnLineage.direct,
  computed: t.columnLineage.computed,
  passthrough: t.columnLineage.passthrough,
};

function edgeLabel(type: ColumnEdgeType): string {
  return EDGE_LABEL[type] ?? String(type);
}

function EdgeBadge({ type }: { type: ColumnEdgeType }) {
  // decor only (U1): computed picks up the contract accent, direct stays neutral.
  const accent = type === 'computed' ? 'var(--cont)' : 'var(--fg-3)';
  return (
    <span style={{
      display: 'inline-block', borderRadius: 'var(--r)', padding: '0 var(--s2)',
      fontSize: 10, fontWeight: 600, letterSpacing: '0.04em', textTransform: 'uppercase',
      color: accent, border: `1px solid ${accent}55`, background: `${accent}1a`,
    }}>
      {edgeLabel(type)}
    </span>
  );
}

function StepChip({ step }: { step: ColumnLineageStep }) {
  const chip = (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 'var(--s2)',
      border: '1px solid var(--line-2)', borderRadius: 'var(--r-md)',
      padding: 'var(--s1) var(--s2)', background: 'var(--bg-2)', fontSize: 12,
    }}>
      <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--fg-2)' }}>{step.object}</span>
      <span style={{ color: 'var(--fg-3)' }}>·</span>
      <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--fg)' }}>{step.column}</span>
      <EdgeBadge type={step.edgeType} />
    </span>
  );
  return step.expression ? <Tooltip content={step.expression}>{chip}</Tooltip> : chip;
}

function StepColumn({ title, steps }: { title: string; steps: ColumnLineageStep[] }) {
  return (
    <div style={{ flex: 1, minWidth: 0 }}>
      <div className="mono-label" style={{ marginBottom: 'var(--s2)' }}>{title}</div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--s2)' }}>
        {steps.length === 0
          ? <span style={{ color: 'var(--fg-3)', fontSize: 12 }}>—</span>
          : steps.map((s, i) => <StepChip key={`${s.object}.${s.column}.${i}`} step={s} />)}
      </div>
    </div>
  );
}

export function ColumnLineagePanel({ objectId }: { objectId: string }) {
  const { data, isLoading } = useColumnLineage(objectId);
  const columns = useMemo(
    () => (data as ColumnLineageObjectResponse | undefined)?.columns ?? {},
    [data],
  );
  const columnNames = useMemo(() => Object.keys(columns).sort(), [columns]);
  // Default to the first column that actually carries lineage, not an empty one.
  const defaultCol = useMemo(
    () => columnNames.find(c => columns[c].upstream.length || columns[c].downstream.length)
      ?? columnNames[0] ?? '',
    [columnNames, columns],
  );

  const [selected, setSelected] = useState<string>('');
  const active = selected && columns[selected] ? selected : defaultCol;

  const { data: impact } = useColumnImpact(objectId, active || undefined);

  const impactColumns: ColDef<ColumnImpactRow>[] = [
    { key: 'object', header: t.columnLineage.colObject, mono: true, render: r => r.object,
      sortable: true, sortValue: r => r.object },
    { key: 'column', header: t.columnLineage.colColumn, mono: true, render: r => r.column },
    { key: 'depth', header: t.columnLineage.colDepth, render: r => r.depth,
      sortable: true, sortValue: r => r.depth },
    { key: 'type', header: t.columnLineage.colType, render: r => <EdgeBadge type={r.edgeType} /> },
    { key: 'owner', header: t.columnLineage.colOwner, render: r => (
      <span title={(r.owners ?? []).join(', ')}>
        {r.coverageFlag ? <span style={{ marginRight: 6 }}>{r.coverageFlag}</span> : null}
        {r.ownedBy || '—'}
      </span>
    ) },
  ];

  if (isLoading) {
    return <ColumnLineageSkeleton />;
  }
  if (columnNames.length === 0) {
    return <p style={{ color: 'var(--fg-3)', fontSize: 12 }}>{t.columnLineage.noEdges}</p>;
  }

  const entry = active ? columns[active] : undefined;

  return (
    <div>
      <SectionHeader title={t.columnLineage.title} />
      <Field label={t.columnLineage.pickColumn} style={{ maxWidth: 280, marginBottom: 'var(--s4)' }}>
        <Select value={active} onChange={e => setSelected(e.target.value)} style={{ width: '100%' }}>
          {columnNames.map(c => <option key={c} value={c}>{c}</option>)}
        </Select>
      </Field>

      {entry && (entry.upstream.length || entry.downstream.length) ? (
        <div style={{ display: 'flex', gap: 'var(--s4)', alignItems: 'flex-start' }}>
          <StepColumn title={t.columnLineage.upstream} steps={entry.upstream} />
          <div style={{ flex: 1, minWidth: 0 }}>
            <div className="mono-label" style={{ marginBottom: 'var(--s2)' }}>{objectId}</div>
            <span style={{
              display: 'inline-flex', alignItems: 'center', gap: 'var(--s2)',
              border: '1px solid var(--cont)', borderRadius: 'var(--r-md)',
              padding: 'var(--s1) var(--s2)', background: 'var(--bg-1)', fontSize: 12,
              fontFamily: 'var(--font-mono)', color: 'var(--fg)',
            }}>{active}</span>
          </div>
          <StepColumn title={t.columnLineage.downstream} steps={entry.downstream} />
        </div>
      ) : (
        <p style={{ color: 'var(--fg-3)', fontSize: 12 }}>{t.columnLineage.noColumnEdges}</p>
      )}

      <div style={{ marginTop: 'var(--s6)' }}>
        <SectionHeader
          title={t.columnLineage.impactTitle}
          count={impact?.totalImpacted}
          hint={t.columnLineage.impactHint}
        />
        {impact && impact.impacted.length > 0 ? (
          <>
            <Table
              columns={impactColumns}
              rows={impact.impacted}
              rowKey={r => `${r.object}.${r.column}`}
            />
            {impact.truncated && (
              <p style={{ color: 'var(--status-warn)', fontSize: 11, marginTop: 'var(--s2)' }}>
                {t.columnLineage.impactTruncated}
              </p>
            )}
          </>
        ) : (
          <p style={{ color: 'var(--fg-3)', fontSize: 12 }}>{t.columnLineage.impactNone}</p>
        )}
      </div>
    </div>
  );
}
