import { useNavigate } from 'react-router-dom';
import { useProposals, useProposalAction } from '@/api/proposals';
import { BacktestBadge } from '@/components/BacktestBadge';
import { ErrorBanner } from '@/components/ui/ErrorBanner';
import { ReadOnlyBanner } from '@/components/ui/ReadOnlyBanner';
import { PageHeader } from '@/components/ui/PageHeader';
import { Tooltip } from '@/components/ui/Tooltip';
import { Button } from '@/components/ui/Button';
import { FilterChip, ActiveFilterChip } from '@/components/ui/FilterChip';
import { Skeleton } from '@/components/ui/Skeleton';
import { useSearchParamState } from '@/hooks/useSearchParamState';
import { t } from '@/i18n/de';
import { diffExpect, OP_SYMBOL } from '@/lib/diff';
import { clusterProposals, type ClusterDimension, type ProposalCluster } from '@/lib/proposalClusters';
import { useRoleStore, canAcceptProposal } from '@/store/role';
import type { Proposal } from '@/types';

type ProposalStatusFilter = 'open' | 'reviewed';

const CARD_GRID: React.CSSProperties = {
  display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: 'var(--s4)',
};

const SECTION_HEADING: React.CSSProperties = {
  fontSize: 13, color: 'var(--fg-3)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 12,
};

const GROUP_OPTIONS: ClusterDimension[] = ['product', 'kind', 'confidence', 'status', 'direction', 'none'];
const STATUS_OPTIONS: ProposalStatusFilter[] = ['open', 'reviewed'];
const STAT_KEYS = ['n', 'min', 'max', 'mean'] as const;

function isClusterDimension(value: string): value is ClusterDimension {
  return (GROUP_OPTIONS as string[]).includes(value);
}

function normalizeGroupBy(value: string): ClusterDimension {
  return isClusterDimension(value) ? value : 'product';
}

function normalizeStatusFilter(value: string): ProposalStatusFilter {
  return value === 'reviewed' ? 'reviewed' : 'open';
}

function proposalMatchesStatus(proposal: Proposal, status: ProposalStatusFilter) {
  return status === 'open' ? proposal.status === 'open' : proposal.status !== 'open';
}

// UX-N13: explain the meaning of current -> proposed (loosened/tightened + delta),
// then keep the raw spans below for power users.
function ExpectDiff({ current, proposed }: { current: string; proposed: string }) {
  const d = diffExpect(current, proposed);
  const directionLabel = t.diff[d.direction];
  const dirColor =
    d.direction === 'loosened' ? 'var(--status-warn)'
    : d.direction === 'tightened' ? 'var(--status-fail)'
    : 'var(--fg-3)';

  const opSym = (op: string) => OP_SYMBOL[op] ?? op;
  const bound = d.proposedVal !== null
    ? `${opSym(d.currentOp)} ${d.currentVal} → ${opSym(d.proposedOp)} ${d.proposedVal}`
    : null;

  return (
    <div>
      <div style={{ fontSize: 10, color: 'var(--fg-3)', marginBottom: 4 }}>{t.diff.meaning}</div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--s2)', flexWrap: 'wrap' }}>
        <span style={{
          fontSize: 11, borderRadius: 'var(--r)', padding: '2px 8px',
          background: `color-mix(in srgb, ${dirColor} 15%, transparent)`,
          color: dirColor, border: `1px solid ${dirColor}`,
        }}>
          {directionLabel}
        </span>
        {bound && (
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--fg-2)' }}>{bound}</span>
        )}
        {d.deltaPct !== null && d.deltaPct !== 0 && (
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--fg-3)' }}>
            ({d.deltaPct > 0 ? '+' : ''}{d.deltaPct}%)
          </span>
        )}
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--s2)', marginTop: 8 }}>
        <div>
          <div style={{ fontSize: 10, color: 'var(--fg-3)', marginBottom: 4 }}>{t.proposals.current}</div>
          <code style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--fg-2)' }}>{current || '—'}</code>
        </div>
        <div>
          <div style={{ fontSize: 10, color: 'var(--fg-3)', marginBottom: 4 }}>{t.proposals.proposed}</div>
          <code style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--status-ok)' }}>{proposed}</code>
        </div>
      </div>
    </div>
  );
}

function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const color = pct >= 80 ? 'var(--status-ok)' : pct >= 50 ? 'var(--status-warn)' : 'var(--status-fail)';
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--s2)' }}>
      <div style={{ flex: 1, height: 4, background: 'var(--line-2)', borderRadius: 2, overflow: 'hidden' }}>
        <div style={{ width: `${pct}%`, height: '100%', background: color, borderRadius: 2 }} />
      </div>
      <span style={{ fontSize: 11, color: 'var(--fg-2)', width: 32, textAlign: 'right' }}>{pct}%</span>
    </div>
  );
}

function ProposalCard({ proposal }: { proposal: Proposal }) {
  const action = useProposalAction();
  const navigate = useNavigate();
  const role = useRoleStore(s => s.role);
  // FE mirror only: the server re-checks role x ownership on accept (S-2).
  const canWrite = canAcceptProposal(role);
  const act = (a: 'accept' | 'reject' | 'snooze') => action.mutate({ id: proposal.id, action: a });

  return (
    <div style={{
      background: 'var(--bg-1)', border: '1px solid var(--line)',
      borderRadius: 'var(--r-lg)', padding: 'var(--s4)', display: 'flex', flexDirection: 'column', gap: 'var(--s3)',
    }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 'var(--s3)' }}>
        <div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--fg)', fontWeight: 500 }}>
            {proposal.check_name}
          </div>
          <div style={{ fontSize: 11, color: 'var(--fg-3)', marginTop: 2 }}>
            {proposal.product}
            <span style={{
              fontSize: 9, borderRadius: 3, padding: '1px 5px', marginLeft: 4,
              background: proposal.kind === 'internal_gate'
                ? 'color-mix(in srgb, var(--qual) 14%, transparent)'
                : 'color-mix(in srgb, var(--cont) 14%, transparent)',
              color: proposal.kind === 'internal_gate' ? 'var(--qual)' : 'var(--cont)',
              border: `1px solid ${proposal.kind === 'internal_gate' ? 'var(--qual)' : 'var(--cont)'}`,
            }}>
              {proposal.kind === 'internal_gate' ? t.proposals.kindLabel.internal_gate : t.proposals.kindLabel.contract}
            </span>
          </div>
        </div>
        <span style={{
          background: 'var(--bg-3)', border: '1px solid var(--line-2)',
          borderRadius: 'var(--r)', padding: '2px 8px', fontSize: 10, color: 'var(--fg-3)',
        }}>
          {t.proposals.statusLabel[proposal.status] ?? proposal.status}
        </span>
      </div>

      <ExpectDiff current={proposal.current_expect} proposed={proposal.proposed_expect} />

      <div>
        <BacktestBadge
          product={proposal.product}
          checkName={proposal.check_name}
          expect={proposal.proposed_expect}
        />
      </div>

      <div>
        <div style={{ fontSize: 10, color: 'var(--fg-3)', marginBottom: 6 }}>{t.proposals.confidence}</div>
        <ConfidenceBar value={proposal.confidence} />
      </div>

      {proposal.stats && (
        <div style={{
          background: 'var(--bg-2)', borderRadius: 'var(--r-md)', padding: 'var(--s2) var(--s3)',
          display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 'var(--s2)',
        }}>
          {STAT_KEYS.map(k => (
            <div key={k}>
              <div style={{ fontSize: 10, color: 'var(--fg-3)', textTransform: 'uppercase' }}>
                {t.proposals.statsLabel[k]}
              </div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--fg-2)' }}>
                {typeof proposal.stats![k] === 'number' ? proposal.stats![k].toFixed(k === 'n' ? 0 : 1) : '—'}
              </div>
            </div>
          ))}
        </div>
      )}

      <div style={{ fontSize: 11, color: 'var(--fg-3)', fontStyle: 'italic' }}>{proposal.rationale}</div>

      {proposal.status === 'open' && (
        <Tooltip content={proposal.kind === 'internal_gate' && !canWrite ? t.role.noWriteAction : undefined} focusable={!canWrite} className="tooltip-full">
          <span style={{ display: 'flex', gap: 'var(--s2)', flexWrap: 'wrap' }}>
            {proposal.kind !== 'internal_gate' ? (
              <Button
                type="button"
                variant="primary"
                size="sm"
                onClick={() => navigate(`/contracts?product=${encodeURIComponent(proposal.product)}`)}
                style={{ flex: '1 1 120px' }}
              >
                {t.proposals.reviewInContract}
              </Button>
            ) : (
              <Button
                type="button"
                variant="primary"
                size="sm"
                onClick={() => act('accept')}
                disabled={!canWrite}
                style={{ flex: '1 1 120px' }}
              >
                {t.proposals.accept}
              </Button>
            )}
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => act('snooze')}
              disabled={!canWrite}
              style={{ flex: '1 1 120px' }}
            >
              {t.proposals.snooze}
            </Button>
            <Button
              type="button"
              variant="danger"
              size="sm"
              onClick={() => act('reject')}
              disabled={!canWrite}
              style={{ flex: '1 1 120px' }}
            >
              {t.proposals.reject}
            </Button>
          </span>
        </Tooltip>
      )}
    </div>
  );
}

function ProposalCardSkeleton() {
  return (
    <div
      data-testid="proposal-card-skeleton"
      style={{
        background: 'var(--bg-1)',
        border: '1px solid var(--line)',
        borderRadius: 'var(--r-lg)',
        padding: 'var(--s4)',
        display: 'grid',
        gap: 'var(--s3)',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 'var(--s3)' }}>
        <div style={{ display: 'grid', gap: 8, flex: 1 }}>
          <Skeleton width="55%" height={13} />
          <Skeleton width="38%" height={10} />
        </div>
        <Skeleton width={72} height={18} radius={6} />
      </div>
      <Skeleton width="100%" height={62} radius={6} />
      <Skeleton width="72%" height={10} />
      <Skeleton width="100%" height={42} radius={6} />
      <div style={{ display: 'flex', gap: 'var(--s2)' }}>
        <Skeleton width="33%" height={28} radius={6} />
        <Skeleton width="33%" height={28} radius={6} />
        <Skeleton width="33%" height={28} radius={6} />
      </div>
    </div>
  );
}

function ProposalSkeletonGrid() {
  return (
    <div style={CARD_GRID}>
      {Array.from({ length: 6 }).map((_, i) => <ProposalCardSkeleton key={i} />)}
    </div>
  );
}

// Resolve the German header label for a cluster key along the active dimension.
function clusterLabel(dim: ClusterDimension, key: string): string {
  switch (dim) {
    case 'product': return key;
    case 'kind': return t.proposals.kindLabel[key] ?? key;
    case 'confidence': return t.proposals.confidenceLabel[key] ?? key;
    case 'status': return t.proposals.statusLabel[key] ?? key;
    case 'direction': return t.proposals.directionLabel[key] ?? key;
    case 'none': return '';
  }
}

function GroupByControl({ value, onChange }: { value: ClusterDimension; onChange: (d: ClusterDimension) => void }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--s2)', flexWrap: 'wrap' }}>
      <span style={{ fontSize: 11, color: 'var(--fg-3)' }}>{t.proposals.groupByLabel}</span>
      <div style={{ display: 'flex', gap: 'var(--s1)', flexWrap: 'wrap' }}>
        {GROUP_OPTIONS.map(opt => (
          <FilterChip key={opt} active={opt === value} onClick={() => onChange(opt)}>
            {t.proposals.groupBy[opt]}
          </FilterChip>
        ))}
      </div>
    </div>
  );
}

function StatusFilterChips({ value, onChange }: { value: ProposalStatusFilter; onChange: (status: ProposalStatusFilter) => void }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--s2)', flexWrap: 'wrap' }}>
      <span style={{ fontSize: 11, color: 'var(--fg-3)' }}>{t.proposals.statusFilterLabel}</span>
      <div style={{ display: 'flex', gap: 'var(--s1)', flexWrap: 'wrap' }}>
        {STATUS_OPTIONS.map(opt => (
          <FilterChip key={opt} active={opt === value} onClick={() => onChange(opt)}>
            {t.proposals.statusFilter[opt]}
          </FilterChip>
        ))}
      </div>
    </div>
  );
}

function ProposalControls({
  groupBy,
  onGroupBy,
  status,
  onStatus,
}: {
  groupBy: ClusterDimension;
  onGroupBy: (d: ClusterDimension) => void;
  status: ProposalStatusFilter;
  onStatus: (status: ProposalStatusFilter) => void;
}) {
  return (
    <>
      <StatusFilterChips value={status} onChange={onStatus} />
      <GroupByControl value={groupBy} onChange={onGroupBy} />
    </>
  );
}

function ClusterMeta({ cluster }: { cluster: ProposalCluster }) {
  const parts = [
    cluster.openCount > 0 ? t.proposals.clusterMeta.open.replace('{n}', String(cluster.openCount)) : null,
    t.proposals.clusterMeta.total.replace('{n}', String(cluster.count)),
    t.proposals.clusterMeta.avgConfidence.replace('{n}', String(Math.round(cluster.avgConfidence * 100))),
  ].filter(Boolean) as string[];
  return (
    <span style={{ display: 'flex', gap: 'var(--s2)', alignItems: 'center', flexWrap: 'wrap' }}>
      {parts.map((p, i) => (
        <span key={i} style={{
          fontSize: 10, color: 'var(--fg-3)', background: 'var(--bg-3)',
          border: '1px solid var(--line-2)', borderRadius: 'var(--r)', padding: '1px 7px',
        }}>{p}</span>
      ))}
    </span>
  );
}

function ClusterSection({ dim, cluster }: { dim: ClusterDimension; cluster: ProposalCluster }) {
  return (
    <details open style={{ marginBottom: 'var(--s4)' }}>
      <summary style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 'var(--s3)',
        cursor: 'pointer', listStyle: 'none', padding: 'var(--s2) 0', marginBottom: 12,
        borderBottom: '1px solid var(--line)',
      }}>
        <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--fg)' }}>
          {clusterLabel(dim, cluster.key)}
        </span>
        <ClusterMeta cluster={cluster} />
      </summary>
      <div style={CARD_GRID}>
        {cluster.proposals.map(p => <ProposalCard key={p.id} proposal={p} />)}
      </div>
    </details>
  );
}

export default function Proposals() {
  const { data: proposals = [], isLoading, isError, refetch } = useProposals();
  const role = useRoleStore(s => s.role);
  const [groupByParam, setGroupBy] = useSearchParamState('groupBy', 'product');
  const [statusParam, setStatusFilter] = useSearchParamState('status', 'open');
  // ?product= grenzt auf ein Objekt ein — der Sprung „N Vorschläge für dieses
  // Objekt" (MinedProposalsCallout, „Meine Arbeit") landet damit auf genau
  // dessen Vorschlägen statt in der ungefilterten Gesamtliste.
  const [productFilter, setProductFilter] = useSearchParamState('product');
  const groupBy = normalizeGroupBy(groupByParam);
  const statusFilter = normalizeStatusFilter(statusParam);
  const visibleProposals = proposals.filter(p =>
    proposalMatchesStatus(p, statusFilter) && (!productFilter || p.product === productFilter),
  );
  const clusters = groupBy === 'none' ? [] : clusterProposals(visibleProposals, groupBy);

  return (
    <div className="page-full">
      <PageHeader
        title={t.proposals.title}
        actions={(
          <ProposalControls
            groupBy={groupBy}
            onGroupBy={setGroupBy}
            status={statusFilter}
            onStatus={setStatusFilter}
          />
        )}
      />
      {!canAcceptProposal(role) && <ReadOnlyBanner />}
      {productFilter && (
        <div style={{ display: 'flex', gap: 'var(--s2)', flexWrap: 'wrap', marginBottom: 'var(--s3)' }}>
          <ActiveFilterChip
            label={`${t.proposals.productFilterLabel}: ${productFilter}`}
            onClear={() => setProductFilter('')}
          />
        </div>
      )}
      {isError && <ErrorBanner onRetry={() => refetch()} />}

      {isLoading ? (
        <ProposalSkeletonGrid />
      ) : (
        <>
          {!isError && proposals.length === 0 && (
            <div style={{ color: 'var(--fg-3)', padding: 40, textAlign: 'center' }}>
              {t.proposals.empty}
            </div>
          )}
          {!isError && proposals.length > 0 && visibleProposals.length === 0 && (
            <div style={{ color: 'var(--fg-3)', padding: 40, textAlign: 'center' }}>
              {t.proposals.emptyFiltered}
            </div>
          )}

          {/* Clustered view: group by object (default) or another property. */}
          {groupBy !== 'none' && clusters.map(c => (
            <ClusterSection key={c.key || 'all'} dim={groupBy} cluster={c} />
          ))}

          {/* Flat view ("Keine"): the status chip decides which set is visible. */}
          {groupBy === 'none' && visibleProposals.length > 0 && (
            <>
              <h2 style={SECTION_HEADING}>{t.proposals.statusFilter[statusFilter]} ({visibleProposals.length})</h2>
              <div style={CARD_GRID}>
                {visibleProposals.map(p => <ProposalCard key={p.id} proposal={p} />)}
              </div>
            </>
          )}
        </>
      )}
    </div>
  );
}
