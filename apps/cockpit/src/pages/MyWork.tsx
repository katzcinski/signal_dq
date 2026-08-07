import { useNavigate } from 'react-router-dom';
import { KpiSkeleton } from '@/components/ui/Skeleton';
import { PageHeader } from '@/components/ui/PageHeader';
import { Panel } from '@/components/ui/Panel';
import { StatusDot } from '@/components/ui/StatusDot';
import { StatusPill } from '@/components/ui/StatusPill';
import { ErrorBanner } from '@/components/ui/ErrorBanner';
import { IncidentSla } from '@/components/ui/IncidentSla';
import { useObjects } from '@/api/objects';
import { useIncidents } from '@/api/incidents';
import { useProposals } from '@/api/proposals';
import { relativeTime, absoluteTime } from '@/lib/time';
import { t } from '@/i18n/de';
import { useRoleStore, ROLE_META } from '@/store/role';
import type { Incident, Proposal } from '@/types';

// UX-N3: role landing "My work". A focused starting point: what is assigned to
// me, what is open in my domains, and the health of those domains.
const SEVERITY_ORDER: Record<string, number> = { critical: 0, fail: 1, warn: 2 };

function RowButton({ onClick, children }: { onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        display: 'flex', alignItems: 'center', gap: 'var(--s3)', width: '100%', textAlign: 'left',
        padding: '7px 0', background: 'none', border: 'none',
        borderBottom: '1px solid var(--line)', borderRadius: 0,
        color: 'var(--fg)', cursor: 'pointer',
      }}
    >
      {children}
    </button>
  );
}

function IncidentKindBadge({ incident }: { incident: Incident }) {
  const isGate = incident.kind === 'internal_gate';
  return (
    <span style={{
      border: `1px solid ${isGate ? 'var(--qual)' : 'var(--cont)'}`,
      borderRadius: 'var(--r-full)', color: isGate ? 'var(--qual)' : 'var(--cont)',
      fontSize: 11, fontWeight: 650, padding: '2px 7px', whiteSpace: 'nowrap',
    }}>
      {isGate ? t.incidents.kindGate : t.incidents.kindContract}
    </span>
  );
}

function incidentHref(incident: Incident) {
  const kind = incident.kind === 'internal_gate' ? 'internal_gate' : 'contract';
  return `/incidents?status=${incident.status}&kind=${kind}&id=${incident.id}`;
}

function AttentionTile({
  label,
  value,
  hint,
  accent,
  onClick,
}: {
  label: string;
  value: number;
  hint: string;
  accent: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        minWidth: 0,
        textAlign: 'left',
        background: 'var(--bg-1)',
        border: '1px solid var(--line)',
        borderBottom: `2px solid ${accent}`,
        borderRadius: 'var(--r-lg)',
        padding: 'var(--s4)',
        cursor: 'pointer',
        display: 'grid',
        gap: 'var(--s2)',
      }}
    >
      <span style={{ color: accent, fontSize: 28, fontWeight: 700, lineHeight: 1 }}>{value}</span>
      <span style={{ color: 'var(--fg)', fontSize: 12, fontWeight: 700 }}>{label}</span>
      <span style={{ color: 'var(--fg-3)', fontSize: 11, lineHeight: 1.35 }}>{hint}</span>
    </button>
  );
}

function AttentionSummary({
  criticalAssigned,
  contractBreaches,
  engineeringSignals,
  openProposals,
  healthPct,
  onNavigate,
}: {
  criticalAssigned: number;
  contractBreaches: number;
  engineeringSignals: number;
  openProposals: number;
  healthPct: number;
  onNavigate: (href: string) => void;
}) {
  return (
    <section
      aria-label={t.myWork.attentionAriaLabel}
      style={{
        border: '1px solid color-mix(in srgb, var(--status-warn) 55%, var(--line))',
        borderRadius: 'var(--r-lg)',
        background: 'color-mix(in srgb, var(--status-warn) 8%, var(--bg-1))',
        padding: 'var(--s4)',
        display: 'grid',
        gap: 'var(--s3)',
      }}
    >
      <div>
        <div style={{ color: 'var(--fg)', fontSize: 'var(--fs-body)', fontWeight: 700 }}>
          {t.myWork.attentionTitle}
        </div>
        <div style={{ color: 'var(--fg-3)', fontSize: 'var(--fs-meta)', marginTop: 4 }}>
          {t.myWork.attentionHint.replace('{health}', `${healthPct}%`)}
        </div>
      </div>
      <div className="dash-kpis">
        <AttentionTile
          label={t.myWork.attentionCriticalAssigned}
          value={criticalAssigned}
          hint={t.myWork.attentionCriticalAssignedHint}
          accent="var(--status-crit)"
          onClick={() => onNavigate('/incidents?status=active&severity=critical&assigned=1')}
        />
        <AttentionTile
          label={t.myWork.attentionContractBreaches}
          value={contractBreaches}
          hint={t.myWork.attentionContractBreachesHint}
          accent="var(--cont)"
          onClick={() => onNavigate('/incidents?status=active&kind=contract')}
        />
        <AttentionTile
          label={t.myWork.attentionEngineeringSignals}
          value={engineeringSignals}
          hint={t.myWork.attentionEngineeringSignalsHint}
          accent="var(--qual)"
          onClick={() => onNavigate('/incidents?status=active&kind=internal_gate')}
        />
        <AttentionTile
          label={t.myWork.attentionOpenProposals}
          value={openProposals}
          hint={t.myWork.attentionOpenProposalsHint}
          accent="var(--obs)"
          onClick={() => onNavigate('/proposals?status=open')}
        />
      </div>
    </section>
  );
}

export default function MyWork() {
  const role = useRoleStore(s => s.role);
  const navigate = useNavigate();

  const objectsQuery = useObjects();
  const incidentsQuery = useIncidents();
  const proposalsQuery = useProposals();

  const objects = objectsQuery.data ?? [];
  const incidents = incidentsQuery.data ?? [];
  const proposals = proposalsQuery.data ?? [];

  const openIncidents = incidents
    .filter(i => i.status !== 'resolved')
    .sort((a, b) => (SEVERITY_ORDER[a.severity] ?? 9) - (SEVERITY_ORDER[b.severity] ?? 9));
  const contractBreaches = openIncidents.filter(i => i.kind !== 'internal_gate');
  const engineeringSignals = openIncidents.filter(i => i.kind === 'internal_gate');
  const assigned = openIncidents.filter(i => i.owner);
  const criticalAssigned = assigned.filter(i => i.severity === 'critical');
  const openProposals = proposals.filter(p => p.status === 'open');

  const totalObjects = objects.length;
  const healthy = objects.filter(o => o.status === 'pass').length;
  const healthPct = totalObjects > 0 ? Math.round((healthy / totalObjects) * 100) : 0;

  const subtitle = role === 'viewer'
    ? t.myWork.subtitleViewer
    : t.myWork.subtitleSteward;

  const isLoading = objectsQuery.isLoading || incidentsQuery.isLoading || proposalsQuery.isLoading;

  return (
    <div className="page-full">
      <PageHeader title={t.myWork.title} subtitle={`${ROLE_META[role].label} · ${subtitle}`} />

      {(objectsQuery.isError || incidentsQuery.isError || proposalsQuery.isError) && (
        <ErrorBanner onRetry={() => { objectsQuery.refetch(); incidentsQuery.refetch(); proposalsQuery.refetch(); }} />
      )}

      {isLoading ? <KpiSkeleton count={4} /> : (
        <AttentionSummary
          criticalAssigned={criticalAssigned.length}
          contractBreaches={contractBreaches.length}
          engineeringSignals={engineeringSignals.length}
          openProposals={openProposals.length}
          healthPct={healthPct}
          onNavigate={navigate}
        />
      )}

      <div style={{ display: 'grid', gap: 'var(--s4)', marginTop: 'var(--s4)' }}>
        <Panel title={t.myWork.assignedIncidents}>
          {assigned.length === 0 ? (
            <p style={{ color: 'var(--fg-3)', fontSize: 12 }}>{t.myWork.noAssigned}</p>
          ) : assigned.map((i: Incident) => (
            <RowButton key={i.id} onClick={() => navigate(incidentHref(i))}>
              <StatusDot status={i.severity} />
              <IncidentKindBadge incident={i} />
              <span style={{ fontSize: 12, flex: 1 }}>{i.title}</span>
              <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--fg-3)', fontSize: 11 }}>{i.owner}</span>
              <IncidentSla incident={i} />
            </RowButton>
          ))}
        </Panel>

        <Panel title={t.myWork.contractBreaches}>
          {contractBreaches.length === 0 ? (
            <p style={{ color: 'var(--fg-3)', fontSize: 12 }}>{t.myWork.noOpenIncidents}</p>
          ) : contractBreaches.slice(0, 8).map((i: Incident) => (
            <RowButton key={i.id} onClick={() => navigate(incidentHref(i))}>
              <StatusPill status={i.severity} size="sm" />
              <span style={{ fontSize: 12, flex: 1 }}>{i.title}</span>
              <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--fg-3)', fontSize: 11 }}>{i.product}</span>
              <span style={{ color: 'var(--fg-3)', fontSize: 11 }} title={absoluteTime(i.opened_at)}>{relativeTime(i.opened_at)}</span>
            </RowButton>
          ))}
        </Panel>

        <Panel title={t.myWork.engineeringSignals}>
          {engineeringSignals.length === 0 ? (
            <p style={{ color: 'var(--fg-3)', fontSize: 12 }}>{t.myWork.noOpenIncidents}</p>
          ) : engineeringSignals.slice(0, 8).map((i: Incident) => (
            <RowButton key={i.id} onClick={() => navigate(incidentHref(i))}>
              <StatusPill status={i.severity} size="sm" />
              <span style={{ fontSize: 12, flex: 1 }}>{i.title}</span>
              <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--fg-3)', fontSize: 11 }}>{i.product}</span>
              <span style={{ color: 'var(--fg-3)', fontSize: 11 }} title={absoluteTime(i.opened_at)}>{relativeTime(i.opened_at)}</span>
            </RowButton>
          ))}
        </Panel>

        <Panel title={t.myWork.openProposals}>
          {openProposals.length === 0 ? (
            <p style={{ color: 'var(--fg-3)', fontSize: 12 }}>{t.myWork.noProposals}</p>
          ) : openProposals.slice(0, 8).map((p: Proposal) => (
            <RowButton key={p.id} onClick={() => navigate(`/proposals?status=open&product=${encodeURIComponent(p.product)}`)}>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, flex: 1 }}>{p.check_name}</span>
              <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--fg-3)', fontSize: 11 }}>{p.product}</span>
              <span style={{ color: 'var(--cont)', fontSize: 11 }}>{t.myWork.review}</span>
            </RowButton>
          ))}
        </Panel>
      </div>
    </div>
  );
}
