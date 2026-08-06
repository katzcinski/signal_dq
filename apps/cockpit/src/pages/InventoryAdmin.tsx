import { useEffect, useMemo, useState, type CSSProperties } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useOperationStream } from '@/api/operations';
import {
  EXTRACT_STATUS_KEY,
  extractStatusIsActive,
  useExtractStatus,
  useStartExtract,
  type ExtractCounts,
  type ExtractOperationResult,
} from '@/api/extract';
import { InventoryExtractProgress } from '@/components/InventoryExtractProgress';
import { Button } from '@/components/ui/Button';
import { ErrorBanner } from '@/components/ui/ErrorBanner';
import { Field, Input } from '@/components/ui/Field';
import { PageHeader } from '@/components/ui/PageHeader';
import { Panel } from '@/components/ui/Panel';
import { ReadOnlyBanner } from '@/components/ui/ReadOnlyBanner';
import { t } from '@/i18n/de';
import { canManageInventory, useRoleStore } from '@/store/role';

const muted: CSSProperties = { color: 'var(--fg-3)', fontSize: 12 };
const valueText: CSSProperties = { color: 'var(--fg)', fontSize: 13, fontWeight: 600 };
const monoText: CSSProperties = { fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--fg-2)' };
const grid = { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))', gap: 'var(--s3)' };
const LOCAL_SOURCE_WARNING = 'No live extraction source configured; nothing was extracted.';

function fmt(value?: string | null): string {
  if (!value) return t.inventoryAdmin.noValue;
  return new Date(value).toLocaleString();
}

function splitSpaces(value: string): string[] {
  return value.split(',').map(part => part.trim()).filter(Boolean);
}

function StatusLine({ ok, label, detail }: { ok: boolean; label: string; detail?: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--s2)', minHeight: 28 }}>
      <span style={{
        width: 8, height: 8, borderRadius: 'var(--r-full)',
        background: ok ? 'var(--status-pass)' : 'var(--status-warn)',
      }} />
      <span style={valueText}>{label}</span>
      {detail && <span style={muted}>{detail}</span>}
    </div>
  );
}

function Metric({ label, value }: { label: string; value?: number }) {
  return (
    <div style={{ borderTop: '1px solid var(--line)', paddingTop: 'var(--s2)' }}>
      <div style={muted}>{label}</div>
      <div style={{ ...valueText, fontSize: 18 }}>{value ?? 0}</div>
    </div>
  );
}

function Counts({ counts }: { counts?: ExtractCounts }) {
  return (
    <div style={grid}>
      <Metric label={t.inventoryAdmin.inventoryItems} value={counts?.inventory_items} />
      <Metric label={t.inventoryAdmin.lineageNodes} value={counts?.lineage_nodes} />
      <Metric label={t.inventoryAdmin.lineageEdges} value={counts?.lineage_edges} />
      <Metric label={t.inventoryAdmin.columnEdges} value={counts?.column_edges} />
    </div>
  );
}

export default function InventoryAdmin() {
  const role = useRoleStore(s => s.role);
  const canTrigger = canManageInventory(role);
  const qc = useQueryClient();
  const { data, isLoading, isError, refetch } = useExtractStatus();
  const startExtract = useStartExtract();
  const [environment, setEnvironment] = useState('default');
  const [profile, setProfile] = useState('default');
  const [spaces, setSpaces] = useState('');
  const [includeSql, setIncludeSql] = useState(true);
  const [force, setForce] = useState(false);
  const [opId, setOpId] = useState<string | null>(null);
  const { data: operation } = useOperationStream<ExtractOperationResult>(opId);

  useEffect(() => {
    if (extractStatusIsActive(data?.status) && data?.op_id) {
      setOpId(prev => prev === data.op_id ? prev : data.op_id);
    }
  }, [data?.op_id, data?.status]);

  useEffect(() => {
    if (operation?.state === 'finished') {
      void qc.invalidateQueries({ queryKey: EXTRACT_STATUS_KEY });
      void qc.invalidateQueries({ queryKey: ['objects'] });
      void qc.invalidateQueries({ queryKey: ['lineage'] });
      void qc.invalidateQueries({ queryKey: ['inventory'] });
    }
  }, [operation?.state, qc]);

  const backendReady = !isError && !isLoading;
  const snapshotReady = Boolean(data?.published_snapshot_timestamp);
  const effectiveCanTrigger = canTrigger && Boolean(data?.can_trigger);
  const displayData = operation?.result ?? data;
  const warnings = useMemo(
    () => (displayData?.warnings ?? []).map(item => item === LOCAL_SOURCE_WARNING ? t.inventoryAdmin.localWarning : item),
    [displayData?.warnings],
  );
  const running = startExtract.isPending || extractStatusIsActive(data?.status) || operation?.state === 'running';

  const trigger = () => {
    setOpId(null);
    startExtract.mutate(
      {
        environment: environment.trim() || 'default',
        profile: profile.trim() || undefined,
        spaces: splitSpaces(spaces),
        include_sql: includeSql,
        force,
      },
      { onSuccess: payload => setOpId(payload.op_id) },
    );
  };

  return (
    <div className="page-full">
      <PageHeader title={t.inventoryAdmin.title} subtitle={t.inventoryAdmin.subtitle} />

      {!canTrigger && <ReadOnlyBanner hint={t.inventoryAdmin.readOnlyHint} />}
      {isError && <ErrorBanner onRetry={() => refetch()} />}
      {isLoading && <p style={muted}>{t.common.loading}</p>}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 'var(--s4)', alignItems: 'start' }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--s4)' }}>
          <Panel title={t.inventoryAdmin.readiness} family="observability">
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--s2)' }}>
              <StatusLine ok={canTrigger} label={canTrigger ? t.inventoryAdmin.roleReady : t.inventoryAdmin.roleBlocked} detail={role} />
              <StatusLine ok={backendReady} label={t.inventoryAdmin.apiReady} detail={displayData?.current_step} />
              <StatusLine ok={snapshotReady} label={snapshotReady ? t.inventoryAdmin.snapshotReady : t.inventoryAdmin.snapshotMissing} detail={fmt(displayData?.published_snapshot_timestamp)} />
            </div>
          </Panel>

          <Panel title={t.inventoryAdmin.scope} family="contract">
            <div style={{ display: 'grid', gap: 'var(--s3)' }}>
              <Field label={t.inventoryAdmin.environment}>
                <Input value={environment} disabled={!effectiveCanTrigger} onChange={e => setEnvironment(e.target.value)} style={{ width: '100%' }} />
              </Field>
              <Field label={t.inventoryAdmin.profile}>
                <Input value={profile} disabled={!effectiveCanTrigger} onChange={e => setProfile(e.target.value)} style={{ width: '100%' }} />
              </Field>
              <Field label={t.inventoryAdmin.spaces} hint={t.inventoryAdmin.spacesHint}>
                <Input value={spaces} disabled={!effectiveCanTrigger} onChange={e => setSpaces(e.target.value)} style={{ width: '100%' }} />
              </Field>
              <label style={{ display: 'flex', alignItems: 'center', gap: 'var(--s2)', fontSize: 12, color: 'var(--fg-2)' }}>
                <input type="checkbox" checked={includeSql} disabled={!effectiveCanTrigger} onChange={e => setIncludeSql(e.target.checked)} />
                {t.inventoryAdmin.includeSql}
              </label>
              <label style={{ display: 'flex', alignItems: 'center', gap: 'var(--s2)', fontSize: 12, color: 'var(--fg-2)' }}>
                <input type="checkbox" checked={force} disabled={!effectiveCanTrigger} onChange={e => setForce(e.target.checked)} />
                {t.inventoryAdmin.force}
              </label>
              <Button variant="primary" disabled={!effectiveCanTrigger || running} onClick={trigger}>
                {running ? t.liveRun : t.inventoryAdmin.startExtract}
              </Button>
            </div>
          </Panel>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--s4)' }}>
          <Panel title={t.inventoryAdmin.progress} family="quality">
            <div style={{ ...grid, marginBottom: 'var(--s4)' }}>
              <div><div style={muted}>{t.inventoryAdmin.status}</div><div style={valueText}>{displayData?.status ?? t.inventoryAdmin.noValue}</div></div>
              <div><div style={muted}>{t.inventoryAdmin.step}</div><div style={valueText}>{displayData?.current_step ?? t.inventoryAdmin.noValue}</div></div>
              <div><div style={muted}>{t.inventoryAdmin.source}</div><div style={valueText}>{displayData?.source ?? t.inventoryAdmin.noValue}</div></div>
              <div><div style={muted}>{t.inventoryAdmin.jobId}</div><div style={monoText}>{displayData?.op_id ?? displayData?.job_id ?? t.inventoryAdmin.noValue}</div></div>
              <div><div style={muted}>{t.inventoryAdmin.started}</div><div style={valueText}>{fmt(displayData?.started_at)}</div></div>
              <div><div style={muted}>{t.inventoryAdmin.updated}</div><div style={valueText}>{fmt(displayData?.updated_at)}</div></div>
              <div><div style={muted}>{t.inventoryAdmin.finished}</div><div style={valueText}>{fmt(displayData?.finished_at)}</div></div>
            </div>
            <InventoryExtractProgress operation={operation} status={data} />
            <div style={{ marginTop: 'var(--s4)' }}>
              <Counts counts={displayData?.counts} />
            </div>
            {warnings.length > 0 && (
              <div style={{ marginTop: 'var(--s4)', color: 'var(--status-warn)', fontSize: 12 }}>
                {t.inventoryAdmin.warning}: {warnings.join(' ')}
              </div>
            )}
            {displayData?.error && <div style={{ marginTop: 'var(--s4)', color: 'var(--status-fail)', fontSize: 12 }}>{displayData.error}</div>}
          </Panel>

          <Panel title={t.inventoryAdmin.snapshot} family="observability">
            <div style={{ marginBottom: 'var(--s3)' }}>
              <div style={muted}>{t.inventoryAdmin.publishedAt}</div>
              <div style={valueText}>{fmt(displayData?.published_snapshot_timestamp)}</div>
            </div>
            <div style={{ display: 'grid', gap: 'var(--s2)' }}>
              {Object.entries(displayData?.runtime_artifact_paths ?? {}).map(([key, value]) => (
                <div key={key} style={{ display: 'grid', gridTemplateColumns: '90px minmax(0, 1fr)', gap: 'var(--s2)' }}>
                  <span style={muted}>{key}</span>
                  <span style={{ ...monoText, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{value}</span>
                </div>
              ))}
            </div>
          </Panel>
        </div>
      </div>
    </div>
  );
}
