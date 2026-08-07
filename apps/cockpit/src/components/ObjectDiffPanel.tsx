import { useState } from 'react';
import { useObjectDiff } from '@/api/objects';
import { Table, type ColDef } from '@/components/ui/Table';
import { t } from '@/i18n/de';
import type { ColumnDiff, KeyReconKey } from '@/types';

type Mode = 'distribution' | 'keys';

function fmtNum(v: number | null | undefined): string {
  if (v === null || v === undefined) return '—';
  return Number.isInteger(v) ? String(v) : String(Math.round(v * 100) / 100);
}

function DeltaText({ delta }: { delta: number | null }) {
  if (delta === null || delta === 0) return <span style={{ color: 'var(--fg-3)' }}>{delta === 0 ? '0' : '—'}</span>;
  const up = delta > 0;
  return (
    <span style={{ color: up ? 'var(--status-warn)' : 'var(--cont)', fontFamily: 'var(--font-mono)' }}>
      {up ? '▲' : '▼'} {fmtNum(Math.abs(delta))}
    </span>
  );
}

// §B.4: Data-Diff der zwei jüngsten Profil-Snapshots eines Objekts.
export function ObjectDiffPanel({ objectId }: { objectId: string }) {
  const [mode, setMode] = useState<Mode>('distribution');
  const [onlyChanged, setOnlyChanged] = useState(true);
  const diff = useObjectDiff(objectId);
  const result = diff.data;

  const run = (next: Mode) => { setMode(next); diff.mutate({ mode: next }); };

  const distColumns: ColDef<ColumnDiff>[] = [
    { key: 'column', header: t.objectDiff.colColumn, mono: true, render: c => c.column },
    {
      key: 'metrics', header: '', render: c => (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12 }}>
          {Object.entries(c.metrics)
            .filter(([, m]) => m.base !== null || m.head !== null)
            .map(([name, m]) => (
              <span key={name} style={{ fontSize: 11 }}>
                <span style={{ color: 'var(--fg-3)' }}>{t.objectDiff.metrics[name] ?? name}: </span>
                <span style={{ fontFamily: 'var(--font-mono)' }}>{fmtNum(m.base)} → {fmtNum(m.head)}</span>
                {' '}<DeltaText delta={m.delta} />
              </span>
            ))}
        </div>
      ),
    },
  ];

  const keyColumns: ColDef<KeyReconKey>[] = [
    { key: 'column', header: t.objectDiff.colColumn, mono: true, render: k => k.column },
    { key: 'db', header: t.objectDiff.colDistinctBase, render: k => fmtNum(k.base_distinct) },
    { key: 'dh', header: t.objectDiff.colDistinctHead, render: k => fmtNum(k.head_distinct) },
    { key: 'delta', header: t.objectDiff.colDelta, render: k => <DeltaText delta={k.distinct_delta} /> },
    {
      key: 'dup', header: t.objectDiff.duplicates,
      render: k => (
        <span style={{ fontSize: 11, color: k.head_duplicates ? 'var(--status-fail)' : 'var(--status-ok)' }}>
          {k.head_duplicates ? t.objectDiff.duplicates : t.objectDiff.noDuplicates}
        </span>
      ),
    },
  ];

  const dist = result?.distribution;
  const visibleCols = dist
    ? (onlyChanged ? dist.columns.filter(c => c.changed) : dist.columns)
    : [];

  const toggleStyle = (active: boolean) => ({
    background: active ? 'var(--cont)' : 'var(--bg-2)',
    color: active ? '#fff' : 'var(--fg-2)',
    border: '1px solid var(--line-2)', borderRadius: 'var(--r-md)',
    padding: '6px 12px', fontSize: 12, cursor: 'pointer',
  } as const);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--s4)' }}>
      <div>
        <h2 style={{ fontSize: 14, fontWeight: 600 }}>{t.objectDiff.title}</h2>
        <p style={{ fontSize: 12, color: 'var(--fg-3)', marginTop: 2 }}>{t.objectDiff.subtitle}</p>
      </div>

      <div style={{ display: 'flex', gap: 'var(--s2)', alignItems: 'center', flexWrap: 'wrap' }}>
        <button style={toggleStyle(mode === 'distribution')} onClick={() => setMode('distribution')}>{t.objectDiff.modeDistribution}</button>
        <button style={toggleStyle(mode === 'keys')} onClick={() => setMode('keys')}>{t.objectDiff.modeKeys}</button>
        <div style={{ flex: 1 }} />
        <button
          style={{ ...toggleStyle(false), background: 'var(--cont)', color: '#fff' }}
          onClick={() => run(mode)}
          disabled={diff.isPending}
        >
          {diff.isPending ? t.objectDiff.running : t.objectDiff.run}
        </button>
      </div>

      {diff.isError && (
        <p style={{ fontSize: 13, color: 'var(--fg-3)', padding: 'var(--s4) 0' }}>{t.objectDiff.needTwo}</p>
      )}

      {result && (
        <>
          <div style={{ fontSize: 11, color: 'var(--fg-3)', fontFamily: 'var(--font-mono)' }}>
            {t.objectDiff.snapshotInfo
              .replace('{base}', `#${result.base.snapshot_id}`)
              .replace('{head}', `#${result.head.snapshot_id}`)}
          </div>

          {result.mode === 'distribution' && dist && (
            <>
              <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                <Kpi label={t.objectDiff.rows} base={dist.row_count.base} head={dist.row_count.head} delta={dist.row_count.delta} />
                <Kpi label={t.objectDiff.columns} base={dist.column_count.base} head={dist.column_count.head} delta={dist.column_count.delta} />
                {dist.added_columns.length > 0 && <Tag label={`${t.objectDiff.added}: ${dist.added_columns.join(', ')}`} color="var(--status-warn)" />}
                {dist.removed_columns.length > 0 && <Tag label={`${t.objectDiff.removed}: ${dist.removed_columns.join(', ')}`} color="var(--status-fail)" />}
              </div>
              <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: 'var(--fg-3)', cursor: 'pointer' }}>
                <input type="checkbox" checked={onlyChanged} onChange={e => setOnlyChanged(e.target.checked)} />
                {t.objectDiff.onlyChanged}
              </label>
              <Table columns={distColumns} rows={visibleCols} rowKey={c => c.column} empty={t.objectDiff.noColumnChanges} />
            </>
          )}

          {result.mode === 'keys' && result.reconciliation && (
            <>
              <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                <Kpi label={t.objectDiff.rows} base={result.reconciliation.base_rows} head={result.reconciliation.head_rows} delta={result.reconciliation.row_delta} />
              </div>
              <h3 style={{ fontSize: 12, fontWeight: 600, color: 'var(--fg-2)' }}>{t.objectDiff.keysTitle}</h3>
              <Table columns={keyColumns} rows={result.reconciliation.keys} rowKey={k => k.column} />
            </>
          )}
        </>
      )}
    </div>
  );
}

function Kpi({ label, base, head, delta }: { label: string; base: number | null; head: number | null; delta: number | null }) {
  return (
    <div style={{ background: 'var(--bg-1)', border: '1px solid var(--line)', borderRadius: 'var(--r-md)', padding: '8px 14px' }}>
      <div style={{ fontSize: 10, color: 'var(--fg-3)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>{label}</div>
      <div style={{ fontSize: 14, fontFamily: 'var(--font-mono)' }}>
        {fmtNum(base)} → {fmtNum(head)} <DeltaText delta={delta} />
      </div>
    </div>
  );
}

function Tag({ label, color }: { label: string; color: string }) {
  return (
    <span style={{
      fontSize: 11, color, border: `1px solid ${color}`, borderRadius: 'var(--r-md)',
      padding: '6px 12px', background: `color-mix(in srgb, ${color} 10%, transparent)`,
    }}>{label}</span>
  );
}
