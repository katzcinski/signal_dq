import { useMemo, useState } from 'react';
import { useEnvironments } from '@/api/objects';
import {
  useCapabilities,
  useCapabilityProbe,
  useEnforcementApply,
  useEnforcementPlan,
  type Capability,
  type EnforcementPlanObject,
  type SplitArtifactPlan,
} from '@/api/enforcement';
import { Table, type ColDef } from '@/components/ui/Table';
import { PageHeader } from '@/components/ui/PageHeader';
import { ErrorBanner } from '@/components/ui/ErrorBanner';
import { ReadOnlyBanner } from '@/components/ui/ReadOnlyBanner';
import { TableSkeleton } from '@/components/ui/Skeleton';
import { Button } from '@/components/ui/Button';
import { t } from '@/i18n/de';
import { useRoleStore, canApplyEnforcement } from '@/store/role';

const CAP_COLOR: Record<Capability['status'], string> = {
  ok: 'var(--status-ok)',
  unavailable: 'var(--status-warn)',
  error: 'var(--status-fail)',
  manual: 'var(--fg-3)',
};

function Chip({ on, labelOn, labelOff }: { on: boolean; labelOn: string; labelOff: string }) {
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', height: 22, padding: '0 10px',
      borderRadius: 'var(--r-full)', fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 650,
      border: '1px solid', whiteSpace: 'nowrap',
      borderColor: on ? 'var(--status-ok)' : 'var(--fg-3)',
      color: on ? 'var(--status-ok)' : 'var(--fg-3)',
    }}>
      {on ? labelOn : labelOff}
    </span>
  );
}

function CapabilityBadge({ status }: { status: Capability['status'] }) {
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', height: 20, padding: '0 8px',
      borderRadius: 'var(--r-full)', fontFamily: 'var(--font-mono)', fontSize: 10.5, fontWeight: 650,
      border: `1px solid ${CAP_COLOR[status]}`, color: CAP_COLOR[status], whiteSpace: 'nowrap',
    }}>
      {t.enforcementPanel.capStatus[status] ?? status}
    </span>
  );
}

function SectionTitle({ children }: { children: string }) {
  return (
    <div style={{
      fontFamily: 'var(--font-mono)', fontSize: 11, letterSpacing: '0.08em',
      textTransform: 'uppercase', color: 'var(--fg-3)', margin: '22px 0 8px',
    }}>
      {children}
    </div>
  );
}

export default function Enforcement() {
  const { data: plan, isLoading, isError, refetch } = useEnforcementPlan();
  const { data: caps } = useCapabilities();
  const { data: envs } = useEnvironments();
  const apply = useEnforcementApply();
  const probe = useCapabilityProbe();
  const role = useRoleStore(s => s.role);
  const canApply = canApplyEnforcement(role); // Server prüft verbindlich (owner+)
  const [environment, setEnvironment] = useState('');
  const [openArtifact, setOpenArtifact] = useState<string | null>(null);

  const envOptions = envs?.environments?.map(e => e.name) ?? [];

  const objectColumns = useMemo<ColDef<EnforcementPlanObject>[]>(() => [
    { key: 'name', header: t.enforcementPanel.colName, mono: true, render: o => o.name },
    { key: 'kind', header: t.enforcementPanel.colKind, width: 110, render: o => o.kind },
    { key: 'hash', header: 'manifest_hash', mono: true, width: 150, render: o => o.manifest_hash },
    {
      key: 'repl', header: t.enforcementPanel.colReplaceable, width: 130,
      render: o => (
        <span style={{ color: 'var(--fg-3)', fontSize: 12 }}>
          {o.replaceable ? t.enforcementPanel.replaceable : t.enforcementPanel.stateful}
        </span>
      ),
    },
  ], []);

  const capColumns = useMemo<ColDef<Capability>[]>(() => [
    { key: 'status', header: t.enforcementPanel.colStatus, width: 130, render: c => <CapabilityBadge status={c.status} /> },
    { key: 'key', header: t.enforcementPanel.colCapability, mono: true, render: c => c.key },
    {
      key: 'detail', header: t.enforcementPanel.colDetail,
      render: c => <span style={{ color: 'var(--fg-3)', fontSize: 12 }}>{c.detail || '—'}</span>,
    },
    {
      key: 'checked', header: t.enforcementPanel.colChecked, width: 170,
      render: c => (
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--fg-3)' }}>
          {c.checked_at ? new Date(c.checked_at).toLocaleString() : '—'}
        </span>
      ),
    },
  ], []);

  return (
    <div className="page-full">
      <PageHeader title={t.enforcementPanel.title} />
      <p style={{ color: 'var(--fg-2)', fontSize: 13, maxWidth: 760, marginBottom: 12 }}>
        {t.enforcementPanel.intro}
      </p>

      {isError && <ErrorBanner onRetry={() => refetch()} />}
      {isLoading && <TableSkeleton columns={4} />}

      {plan && (
        <>
          <div style={{ display: 'flex', gap: 'var(--s2)', flexWrap: 'wrap', alignItems: 'center', marginBottom: 6 }}>
            <Chip on={plan.enabled} labelOn={t.enforcementPanel.enabled} labelOff={t.enforcementPanel.disabled} />
            <Chip on={plan.bridge_enabled} labelOn={t.enforcementPanel.bridgeOn} labelOff={t.enforcementPanel.bridgeOff} />
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--fg-3)' }}>
              {t.enforcementPanel.schemaLabel}: {plan.signal_schema || '—'}
            </span>
          </div>

          {!canApply && <ReadOnlyBanner />}

          <div style={{ display: 'flex', gap: 'var(--s2)', alignItems: 'center', flexWrap: 'wrap', margin: '10px 0 4px' }}>
            <select
              value={environment}
              onChange={e => setEnvironment(e.target.value)}
              aria-label={t.enforcementPanel.environment}
              style={{
                background: 'var(--bg-2)', color: 'var(--fg)', border: '1px solid var(--line-2)',
                borderRadius: 'var(--r-md)', padding: '5px 10px', fontSize: 12,
              }}
            >
              <option value="">{t.enforcementPanel.pickEnvironment}</option>
              {envOptions.map(name => <option key={name} value={name}>{name}</option>)}
            </select>
            <Button
              variant="secondary" size="sm"
              disabled={!canApply || !environment}
              pending={probe.isPending}
              title={canApply ? undefined : t.role.noWriteAction}
              onClick={() => probe.mutate(environment)}
            >
              {t.enforcementPanel.runProbe}
            </Button>
            <Button
              variant="primary" size="sm"
              disabled={!canApply || !environment || !plan.enabled}
              pending={apply.isPending}
              title={!plan.enabled ? t.enforcementPanel.applyNeedsOptIn : canApply ? undefined : t.role.noWriteAction}
              onClick={() => apply.mutate(environment)}
            >
              {t.enforcementPanel.applyPlan}
            </Button>
          </div>

          <SectionTitle>{t.enforcementPanel.capabilitiesTitle}</SectionTitle>
          <div style={{ background: 'var(--bg-1)', border: '1px solid var(--line)', borderRadius: 'var(--r-lg)', overflow: 'hidden' }}>
            <Table
              columns={capColumns}
              rows={caps?.capabilities ?? []}
              rowKey={c => c.key}
              empty={t.enforcementPanel.capabilitiesEmpty}
            />
          </div>

          <SectionTitle>{t.enforcementPanel.infrastructureTitle}</SectionTitle>
          <div style={{ background: 'var(--bg-1)', border: '1px solid var(--line)', borderRadius: 'var(--r-lg)', overflow: 'hidden' }}>
            <Table columns={objectColumns} rows={plan.objects} rowKey={o => o.name} />
          </div>

          <SectionTitle>{t.enforcementPanel.splitTitle}</SectionTitle>
          {plan.split_artifacts.length === 0 && (
            <div style={{ color: 'var(--fg-3)', fontSize: 13 }}>{t.enforcementPanel.splitEmpty}</div>
          )}
          {plan.split_artifacts.map((art: SplitArtifactPlan) => (
            <div
              key={art.object_id}
              style={{ background: 'var(--bg-1)', border: '1px solid var(--line)', borderRadius: 'var(--r-lg)', padding: '12px 16px', marginBottom: 10 }}
            >
              <button
                onClick={() => setOpenArtifact(openArtifact === art.object_id ? null : art.object_id)}
                style={{
                  display: 'flex', gap: 12, alignItems: 'baseline', width: '100%', textAlign: 'left',
                  background: 'none', border: 'none', cursor: 'pointer', color: 'var(--fg)', padding: 0,
                }}
              >
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: 13, fontWeight: 650 }}>{art.object_id}</span>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--fg-3)' }}>
                  {art.predicates.length} {t.enforcementPanel.predicates}
                  {art.skipped.length > 0 && ` · ${art.skipped.length} ${t.enforcementPanel.skipped}`}
                </span>
                <span style={{ marginLeft: 'auto', color: 'var(--fg-3)' }}>{openArtifact === art.object_id ? '▾' : '▸'}</span>
              </button>
              {openArtifact === art.object_id && (
                <div style={{ marginTop: 10, fontSize: 12, color: 'var(--fg-2)' }}>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--fg-3)', marginBottom: 6 }}>
                    {art.source} → {art.clean_table} · {art.quarantine_table} · {art.released_view}
                  </div>
                  {art.predicates.map(p => (
                    <div key={p.check} style={{ fontFamily: 'var(--font-mono)', fontSize: 11.5, padding: '2px 0' }}>
                      <span style={{ color: 'var(--qual)' }}>{p.check}</span>
                      {' — '}
                      <span style={{ color: 'var(--fg-3)' }}>{p.condition}</span>
                    </div>
                  ))}
                  {art.skipped.map(sk => (
                    <div key={sk.check} style={{ fontSize: 11.5, padding: '2px 0', color: 'var(--fg-3)' }}>
                      ⊘ {sk.check} — {sk.reason}
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </>
      )}
    </div>
  );
}
