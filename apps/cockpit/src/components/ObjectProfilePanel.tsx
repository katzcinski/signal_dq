import { useEffect, useMemo, useState } from 'react';
import { useEnvironments, useObjectProfile } from '@/api/objects';
import { useOperationStream } from '@/api/operations';
import { useRoleStore, canProfileObject } from '@/store/role';
import { Button } from '@/components/ui/Button';
import { OperationProgress } from '@/components/OperationProgress';
import { SidePanel } from '@/components/ui/SidePanel';
import { Table, type ColDef } from '@/components/ui/Table';
import type {
  ObjectProfileColumn,
  ObjectProfileResult,
  ProfileSampleRows,
  ProfileCompositeCandidate,
  ProfileSingleCandidate,
} from '@/types';

interface Props {
  objectId: string;
  onClose: () => void;
}

function fmtValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return '-';
  if (typeof value === 'number') return Number.isInteger(value) ? String(value) : value.toFixed(2);
  return String(value);
}

function fmtPct(value: number | null | undefined): string {
  return value == null ? '-' : `${value.toFixed(2)}%`;
}

function profileErrorMessage(err: unknown): string {
  const response = (err as { response?: { status?: number; data?: { detail?: string } } }).response;
  const detail = response?.data?.detail;
  if (detail) return detail;
  switch (response?.status) {
    case 403:
      return 'Profiling requires steward role or higher.';
    case 404:
      return 'Object was not found.';
    case 422:
      return 'Profiling requires a configured live environment.';
    case 503:
      return 'The profiling connection is currently unavailable.';
    default:
      return err instanceof Error ? err.message : 'Profiling failed.';
  }
}

const sectionTitle: React.CSSProperties = {
  fontSize: 11,
  color: 'var(--fg-3)',
  textTransform: 'uppercase',
  letterSpacing: '0.06em',
  marginBottom: 8,
};

function Score({ label, value }: { label: string; value?: number }) {
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 5,
      color: 'var(--fg-3)', fontSize: 11,
    }}>
      {label}
      <strong style={{ color: 'var(--fg-2)', fontFamily: 'var(--font-mono)' }}>
        {value == null ? '-' : Math.round(value)}
      </strong>
    </span>
  );
}

function CandidateRow({ candidate }: {
  candidate: ProfileSingleCandidate | ProfileCompositeCandidate;
}) {
  const cols = 'column' in candidate ? [candidate.column] : candidate.columns;
  return (
    <div style={{
      border: '1px solid var(--line)',
      borderRadius: 'var(--r-md)',
      padding: '9px 11px',
      background: 'var(--bg-2)',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--s2)', flexWrap: 'wrap', marginBottom: 6 }}>
        <code style={{ color: 'var(--fg)', fontSize: 12 }}>{cols.join(' + ')}</code>
        {candidate.exact && (
          <span style={{
            fontSize: 10, color: 'var(--status-ok)',
            border: '1px solid var(--status-ok)', borderRadius: 'var(--r)', padding: '1px 6px',
          }}>
            exact
          </span>
        )}
        <span style={{ color: 'var(--fg-3)', fontSize: 11 }}>{candidate.rank_reason}</span>
      </div>
      <div style={{ display: 'flex', gap: 'var(--s3)', flexWrap: 'wrap' }}>
        <Score label="final" value={candidate.final_score} />
        <Score label="technical" value={candidate.technical_score} />
        <Score label="business" value={candidate.business_score} />
        <Score label="unique" value={candidate.uniqueness_pct} />
      </div>
    </div>
  );
}

function CandidateSection({ title, candidates }: {
  title: string;
  candidates: Array<ProfileSingleCandidate | ProfileCompositeCandidate>;
}) {
  return (
    <section style={{ marginTop: 18 }}>
      <div style={sectionTitle}>{title}</div>
      {candidates.length === 0 ? (
        <div style={{ color: 'var(--fg-3)', fontSize: 12 }}>No candidates found.</div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--s2)' }}>
          {candidates.slice(0, 8).map((candidate, idx) => (
            <CandidateRow
              key={'column' in candidate ? candidate.column : `${candidate.columns.join('|')}-${idx}`}
              candidate={candidate}
            />
          ))}
        </div>
      )}
    </section>
  );
}

function ProfileSummary({ profile }: { profile: ObjectProfileResult }) {
  const kpiStyle: React.CSSProperties = {
    border: '1px solid var(--line)',
    borderRadius: 'var(--r-md)',
    background: 'var(--bg-2)',
    padding: '9px 11px',
    minWidth: 110,
  };
  const valueStyle: React.CSSProperties = {
    color: 'var(--fg)',
    fontSize: 18,
    fontWeight: 700,
    fontFamily: 'var(--font-mono)',
  };
  const labelStyle: React.CSSProperties = { color: 'var(--fg-3)', fontSize: 11, marginTop: 2 };

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(100px, 1fr))', gap: 'var(--s2)', marginBottom: 18 }}>
      <div style={kpiStyle}>
        <div style={valueStyle}>{profile.row_count.toLocaleString()}</div>
        <div style={labelStyle}>Rows</div>
      </div>
      <div style={kpiStyle}>
        <div style={valueStyle}>{profile.column_count}</div>
        <div style={labelStyle}>Columns</div>
      </div>
      <div style={kpiStyle}>
        <div style={valueStyle}>{profile.scores?.overall_key_confidence ?? '-'}</div>
        <div style={labelStyle}>Key confidence</div>
      </div>
      <div style={kpiStyle}>
        <div style={valueStyle}>{profile.issues?.length ?? 0}</div>
        <div style={labelStyle}>Issues</div>
      </div>
    </div>
  );
}

function ColumnStatsTable({ columns }: { columns: ObjectProfileColumn[] }) {
  const colDefs: ColDef<ObjectProfileColumn>[] = useMemo(() => [
    { key: 'column', header: 'Column', mono: true, sortable: true, sortValue: c => c.column, render: c => c.column },
    { key: 'type', header: 'Type', mono: true, sortable: true, sortValue: c => c.data_type, render: c => c.data_type },
    { key: 'null', header: 'Null %', sortable: true, sortValue: c => c.null_pct, render: c => fmtPct(c.null_pct) },
    { key: 'distinct', header: 'Distinct', sortable: true, sortValue: c => c.distinct, render: c => c.distinct.toLocaleString() },
    { key: 'unique', header: 'Unique %', sortable: true, sortValue: c => c.uniqueness_pct, render: c => fmtPct(c.uniqueness_pct) },
    { key: 'empty', header: 'Empty %', sortable: true, sortValue: c => c.empty_pct ?? -1, render: c => fmtPct(c.empty_pct) },
    { key: 'min', header: 'Min', mono: true, render: c => fmtValue(c.min) },
    { key: 'max', header: 'Max', mono: true, render: c => fmtValue(c.max) },
    { key: 'avg', header: 'Avg', mono: true, render: c => fmtValue(c.avg) },
    {
      key: 'pk',
      header: 'PK',
      sortable: true,
      sortValue: c => c.pk_candidate ? 1 : 0,
      render: c => c.pk_candidate ? (
        <span style={{ color: 'var(--status-ok)', fontWeight: 700 }}>yes</span>
      ) : <span style={{ color: 'var(--fg-3)' }}>-</span>,
    },
  ], []);

  return (
    <section style={{ marginTop: 18 }}>
      <div style={sectionTitle}>Column stats</div>
      <div style={{ border: '1px solid var(--line)', borderRadius: 'var(--r-md)', overflow: 'hidden' }}>
        <Table
          columns={colDefs}
          rows={columns}
          rowKey={c => c.column}
          empty="No column stats returned."
          maxHeight={360}
          virtualizeThreshold={40}
        />
      </div>
    </section>
  );
}

type SampleRow = { __idx: number } & Record<string, unknown>;

function SampleRowsSection({ sample }: { sample?: ProfileSampleRows }) {
  const rows = useMemo<SampleRow[]>(
    () => (sample?.rows ?? []).map((row, idx) => ({ __idx: idx, ...row })),
    [sample?.rows],
  );
  const columns = useMemo(
    () => sample?.columns.length ? sample.columns : Object.keys(sample?.rows[0] ?? {}),
    [sample],
  );
  const colDefs: ColDef<SampleRow>[] = useMemo(() => columns.map(col => ({
    key: col,
    header: col,
    mono: true,
    render: row => fmtValue(row[col]),
  })), [columns]);

  if (!sample) return null;

  return (
    <section style={{ marginTop: 18 }}>
      <div style={sectionTitle}>Sample rows [PII-GATE]</div>
      {!sample.enabled ? (
        <div style={{ color: 'var(--fg-3)', fontSize: 12 }}>{sample.reason || 'Sample rows unavailable.'}</div>
      ) : (
        <div style={{ border: '1px solid var(--line)', borderRadius: 'var(--r-md)', overflow: 'hidden' }}>
          <Table
            columns={colDefs}
            rows={rows}
            rowKey={row => String(row.__idx)}
            empty="No sample rows returned."
            maxHeight={240}
          />
        </div>
      )}
    </section>
  );
}

export function ObjectProfilePanel({ objectId, onClose }: Props) {
  const role = useRoleStore(s => s.role);
  const allowed = canProfileObject(role);
  const profile = useObjectProfile(objectId);
  const { data: envData, isLoading: envLoading } = useEnvironments();
  const environments = useMemo(() => envData?.environments ?? [], [envData]);
  const [environment, setEnvironment] = useState('');
  const [includeSamples, setIncludeSamples] = useState(false);
  const [opId, setOpId] = useState<string | null>(null);
  const { data: operation } = useOperationStream<ObjectProfileResult>(opId);

  useEffect(() => {
    if (!environment && environments[0]) setEnvironment(environments[0].name);
  }, [environment, environments]);

  const runProfile = () => {
    setOpId(null);
    profile.mutate({
      environment,
      include_composite: true,
      include_samples: includeSamples,
      sample_limit: 20,
    }, {
      onSuccess: data => setOpId(data.op_id),
    });
  };

  const error = profile.isError ? profileErrorMessage(profile.error) : '';
  const running = profile.isPending || operation?.state === 'running';
  const profileResult = operation?.state === 'finished' ? operation.result : null;
  const operationError = operation?.state === 'error' ? operation.error : '';
  const canRun = allowed && !!environment && !running;

  return (
    <SidePanel
      title={`Profile ${objectId}`}
      onClose={onClose}
      width={720}
      footer={(
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <Button variant="primary" onClick={runProfile} disabled={!canRun}>
            {running ? 'Profiling...' : 'Run profile'}
          </Button>
          {!allowed && <span style={{ color: 'var(--fg-3)', fontSize: 12 }}>Steward role or higher required.</span>}
          {allowed && !environment && !envLoading && (
            <span style={{ color: 'var(--fg-3)', fontSize: 12 }}>Select a live environment first.</span>
          )}
        </div>
      )}
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <label style={{ display: 'flex', flexDirection: 'column', gap: 6, maxWidth: 280 }}>
          <span style={{ color: 'var(--fg-3)', fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
            Environment
          </span>
          <select
            value={environment}
            onChange={e => setEnvironment(e.target.value)}
            disabled={!allowed || envLoading}
            style={{
              background: 'var(--bg-2)',
              border: '1px solid var(--line)',
              borderRadius: 'var(--r-md)',
              color: 'var(--fg)',
              padding: '7px 10px',
              fontSize: 12,
            }}
          >
            <option value="">{envLoading ? 'Loading environments...' : 'Select environment'}</option>
            {environments.map(env => (
              <option key={env.name} value={env.name}>{env.name} ({env.schema})</option>
            ))}
          </select>
        </label>

        <label style={{ display: 'flex', alignItems: 'center', gap: 'var(--s2)', color: 'var(--fg-2)', fontSize: 12 }}>
          <input
            type="checkbox"
            checked={includeSamples}
            onChange={e => setIncludeSamples(e.target.checked)}
            disabled={!allowed || running}
          />
          Sample rows [PII-GATE]
        </label>

        {(error || operationError) && (
          <div style={{
            border: '1px solid var(--status-crit)',
            borderRadius: 'var(--r-md)',
            background: 'rgba(229, 72, 77, 0.08)',
            color: 'var(--status-crit)',
            padding: '10px 12px',
            fontSize: 12,
          }}>
            {error || operationError}
          </div>
        )}

        {operation && <OperationProgress operation={operation} />}

        {!profileResult && !running && !error && !operationError && (
          <div style={{ color: 'var(--fg-3)', fontSize: 12, lineHeight: 1.6 }}>
            Profiling runs aggregate-only queries against the selected live environment.
          </div>
        )}

        {running && !operation && <div style={{ color: 'var(--fg-3)', fontSize: 12 }}>Profiling columns...</div>}

        {profileResult && (
          <div>
            <ProfileSummary profile={profileResult} />
            <CandidateSection title="Single-column key candidates" candidates={profileResult.pk_candidates.ranked_single ?? []} />
            <CandidateSection title="Composite key candidates" candidates={profileResult.pk_candidates.ranked_composite ?? []} />
            <ColumnStatsTable columns={profileResult.columns} />
            <SampleRowsSection sample={profileResult.sample_rows} />
          </div>
        )}
      </div>
    </SidePanel>
  );
}
