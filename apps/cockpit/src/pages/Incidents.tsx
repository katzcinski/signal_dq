import { useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useIncidents, useIncident, useIncidentTransition, useFailedChecks } from '@/api/incidents';
import { Table, type ColDef } from '@/components/ui/Table';
import { StatusDot } from '@/components/ui/StatusDot';
import { StatusPill } from '@/components/ui/StatusPill';
import { StatePill } from '@/components/ui/StatePill';
import { IncidentSla } from '@/components/ui/IncidentSla';
import { ErrorBanner } from '@/components/ui/ErrorBanner';
import { ReadOnlyBanner } from '@/components/ui/ReadOnlyBanner';
import { TableSkeleton } from '@/components/ui/Skeleton';
import { PageHeader } from '@/components/ui/PageHeader';
import { SidePanel } from '@/components/ui/SidePanel';
import { Button } from '@/components/ui/Button';
import { ActiveFilterChip, FilterChip } from '@/components/ui/FilterChip';
import { relativeTime, absoluteTime } from '@/lib/time';
import { t } from '@/i18n/de';
import { useRoleStore, canActOnIncidents } from '@/store/role';
import type { FailedCheck, Incident, IncidentStatus } from '@/types';

const INCIDENT_STATUS_TABS: IncidentStatus[] = ['open', 'acknowledged', 'investigating', 'resolved'];
// 'active' = alle nicht gelösten Incidents (offen/bestätigt/in Arbeit) in einer
// Liste. Das schließt die Lücke zu Zählern (Cockpit-KPIs, „Meine Arbeit"), die
// über alle offenen Status hinweg zählen — der Sprung landet damit auf genau der
// Menge, die die Zahl meint, statt nur auf dem Default-Tab „Offen".
const TABS = ['active', ...INCIDENT_STATUS_TABS, 'checks'] as const;
const SEVERITY_FILTERS = ['critical', 'fail', 'warn'] as const;

type IncidentTab = typeof TABS[number];
type KindFilter = 'all' | 'contract' | 'internal_gate';
type QueryKey = 'status' | 'kind' | 'severity' | 'assigned' | 'id';

const QUERY_DEFAULTS: Record<QueryKey, string> = {
  status: 'open',
  kind: 'all',
  severity: '',
  assigned: '',
  id: '',
};

function normalizeTab(value: string): IncidentTab {
  return (TABS as readonly string[]).includes(value) ? (value as IncidentTab) : 'open';
}

function isIncidentStatus(value: IncidentTab): value is IncidentStatus {
  return value !== 'checks' && value !== 'active';
}

function matchesKindFilter(incident: Incident, kindFilter: string) {
  if (kindFilter === 'internal_gate') return incident.kind === 'internal_gate';
  if (kindFilter === 'contract') return incident.kind !== 'internal_gate';
  return true;
}

function kindFilterLabel(kindFilter: string) {
  if (kindFilter === 'internal_gate') return t.incidents.kindGate;
  if (kindFilter === 'contract') return t.incidents.kindContract;
  return t.incidents.filterAll;
}

function severityFilterLabel(severity: string) {
  return t.status[severity] ?? severity;
}

function selectedIncidentId(value: string): number | null {
  if (!/^\d+$/.test(value)) return null;
  const id = Number(value);
  return Number.isFinite(id) ? id : null;
}

function IncidentKindBadge({ kind }: { kind?: Incident['kind'] }) {
  const isGate = kind === 'internal_gate';
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', height: 22, padding: '0 var(--s2)',
      borderRadius: 'var(--r-full)', border: `1px solid ${isGate ? 'var(--qual)' : 'var(--cont)'}`,
      color: isGate ? 'var(--qual)' : 'var(--cont)', fontSize: 11, fontWeight: 650,
      whiteSpace: 'nowrap',
    }}>
      {isGate ? t.incidents.kindGate : t.incidents.kindContract}
    </span>
  );
}

function KindFilterChips({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  const options: Array<[KindFilter, string]> = [
    ['all', t.incidents.filterAll],
    ['contract', t.incidents.kindContract],
    ['internal_gate', t.incidents.kindGate],
  ];

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--s2)', flexWrap: 'wrap' }}>
      <span style={{ fontSize: 11, color: 'var(--fg-3)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
        {t.incidents.filterKind}
      </span>
      {options.map(([option, label]) => (
        <FilterChip
          key={option}
          active={value === option || (option === 'all' && value !== 'contract' && value !== 'internal_gate')}
          onClick={() => onChange(value === option ? 'all' : option)}
        >
          {label}
        </FilterChip>
      ))}
    </div>
  );
}

function SeverityFilterChips({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--s2)', flexWrap: 'wrap' }}>
      <span style={{ fontSize: 11, color: 'var(--fg-3)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
        {t.common.severity}
      </span>
      <FilterChip active={!value} onClick={() => onChange('')}>
        {t.incidents.allSeverities}
      </FilterChip>
      {SEVERITY_FILTERS.map(severity => (
        <FilterChip
          key={severity}
          active={value === severity}
          onClick={() => onChange(value === severity ? '' : severity)}
        >
          {t.status[severity]}
        </FilterChip>
      ))}
    </div>
  );
}

function ActiveIncidentFilters({
  kindFilter,
  severityFilter,
  assignedFilter,
  onClearKind,
  onClearSeverity,
  onClearAssigned,
}: {
  kindFilter: string;
  severityFilter: string;
  assignedFilter: boolean;
  onClearKind: () => void;
  onClearSeverity: () => void;
  onClearAssigned: () => void;
}) {
  const hasKind = kindFilter === 'contract' || kindFilter === 'internal_gate';
  const hasSeverity = Boolean(severityFilter);
  if (!hasKind && !hasSeverity && !assignedFilter) return null;

  return (
    <div style={{ display: 'flex', gap: 'var(--s2)', flexWrap: 'wrap', marginBottom: 'var(--s3)' }}>
      {hasKind && <ActiveFilterChip label={kindFilterLabel(kindFilter)} onClear={onClearKind} />}
      {hasSeverity && <ActiveFilterChip label={severityFilterLabel(severityFilter)} onClear={onClearSeverity} />}
      {assignedFilter && <ActiveFilterChip label={t.incidents.filterAssigned} onClear={onClearAssigned} />}
    </div>
  );
}

function IncidentDrawer({ id, onClose, onTransitioned }: {
  id: number;
  onClose: () => void;
  onTransitioned: (status: IncidentStatus) => void;
}) {
  const { data: incident, isLoading } = useIncident(id);
  const transition = useIncidentTransition(id);
  const navigate = useNavigate();
  const role = useRoleStore(s => s.role);
  const canAct = canActOnIncidents(role); // server re-checks (incidents.py:124)
  const [ownerInput, setOwnerInput] = useState('');
  const [pendingStatus, setPendingStatus] = useState<string | null>(null);
  const [noteInput, setNoteInput] = useState('');
  const impactedObjects = incident?.impacted_objects ?? [];

  const requestAct = (status: string) => {
    setPendingStatus(status);
    setNoteInput('');
  };

  const confirmAct = () => {
    if (!pendingStatus) return;
    const nextStatus = pendingStatus as IncidentStatus;
    // Nach erfolgreichem Übergang die URL nachziehen (Tab folgt dem Incident),
    // damit der Drawer nicht unter einem Tab stehen bleibt, der ihn nicht mehr
    // listet — sonst zeigt ein Reload/Share einen gelösten Incident unter „Offen".
    transition.mutate(
      { status: nextStatus, note: noteInput.trim() || undefined },
      { onSuccess: () => onTransitioned(nextStatus) },
    );
    setPendingStatus(null);
    setNoteInput('');
  };

  const cancelAct = () => {
    setPendingStatus(null);
    setNoteInput('');
  };

  return (
    <SidePanel title={incident?.title ?? t.incidents.title} onClose={onClose} width={460}>
      {isLoading && <div style={{ color: 'var(--fg-3)' }}>{t.common.loading}</div>}

      {incident && (
        <>
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--s2)', marginBottom: 6, flexWrap: 'wrap' }}>
            <StatusPill status={incident.severity} size="sm" />
            <span style={{ fontSize: 11, color: 'var(--fg-3)' }}>
              {t.incidents.statusLabel[incident.status] ?? incident.status}
            </span>
            <IncidentKindBadge kind={incident.kind} />
            <IncidentSla incident={incident} />
          </div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--fg-2)', marginTop: 4 }}>
            {incident.product}
          </div>
          <div style={{ fontSize: 11, color: 'var(--fg-3)', marginTop: 2, marginBottom: 16 }}>
            {t.incidents.colOpened}: {new Date(incident.opened_at).toLocaleString()} - {t.incidents.contractVersion}: {incident.contract_version || '-'}
          </div>

          {!canAct && <ReadOnlyBanner />}

          <div
            style={{ display: 'flex', gap: 'var(--s2)', flexWrap: 'wrap', marginBottom: pendingStatus ? 8 : 16 }}
            title={canAct ? undefined : t.role.noWriteAction}
          >
            {incident.status === 'open' && (
              <Button
                variant={pendingStatus === 'acknowledged' ? 'primary' : 'secondary'}
                size="sm"
                disabled={!canAct}
                pending={transition.isPending}
                onClick={() => requestAct('acknowledged')}
              >
                {t.incidents.acknowledge}
              </Button>
            )}
            {(incident.status === 'open' || incident.status === 'acknowledged') && (
              <Button
                variant={pendingStatus === 'investigating' ? 'primary' : 'secondary'}
                size="sm"
                disabled={!canAct}
                pending={transition.isPending}
                onClick={() => requestAct('investigating')}
              >
                {t.incidents.investigate}
              </Button>
            )}
            {incident.status !== 'resolved' && (
              <Button
                variant={pendingStatus === 'resolved' ? 'primary' : 'secondary'}
                size="sm"
                disabled={!canAct}
                pending={transition.isPending}
                onClick={() => requestAct('resolved')}
              >
                {t.incidents.resolve}
              </Button>
            )}
            <Button variant="ghost" size="sm" onClick={() => navigate(`/runs/${incident.run_id}`)}>
              {t.incidents.openRun}
            </Button>
            <Button variant="ghost" size="sm" onClick={() => navigate(`/lineage?focus=${encodeURIComponent(incident.product)}`)}>
              {t.incidents.rootCause}
            </Button>
            <Button variant="ghost" size="sm" onClick={() => navigate(`/objects/${encodeURIComponent(incident.product)}?tab=lineage`)}>
              {t.incidents.columnImpact}
            </Button>
          </div>

          {pendingStatus && (
            <div style={{
              background: 'var(--bg-2)', border: '1px solid var(--line-2)',
              borderRadius: 'var(--r-md)', padding: 'var(--s3)', marginBottom: 16,
            }}>
              <div style={{ fontSize: 11, color: 'var(--fg-3)', marginBottom: 6 }}>
                {t.incidents.notePrompt}
              </div>
              <textarea
                value={noteInput}
                onChange={e => setNoteInput(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) confirmAct(); }}
                placeholder={t.incidents.notePlaceholder}
                autoFocus
                rows={2}
                style={{
                  width: '100%', background: 'var(--bg-1)', border: '1px solid var(--line-2)',
                  color: 'var(--fg)', borderRadius: 'var(--r)', padding: '6px 8px', fontSize: 12,
                  resize: 'vertical', boxSizing: 'border-box', display: 'block',
                }}
              />
              <div style={{ display: 'flex', gap: 'var(--s2)', marginTop: 8 }}>
                <Button variant="primary" size="sm" onClick={confirmAct} pending={transition.isPending}>
                  {t.common.confirm}
                </Button>
                <Button variant="ghost" size="sm" onClick={cancelAct}>
                  {t.common.cancel}
                </Button>
              </div>
            </div>
          )}

          <div style={{ marginBottom: 16 }}>
            <div style={{ fontSize: 11, color: 'var(--fg-3)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 6 }}>
              {t.incidents.assignOwner}
            </div>
            <div style={{ fontSize: 12, color: 'var(--fg-2)', marginBottom: 6 }}>
              {t.incidents.colOwner}: {incident.owner || t.incidents.noOwner}
            </div>
            <div style={{ display: 'flex', gap: 'var(--s2)' }}>
              <input
                value={ownerInput}
                onChange={e => setOwnerInput(e.target.value)}
                placeholder={t.incidents.colOwner}
                aria-label={t.incidents.assignOwner}
                style={{
                  flex: 1, background: 'var(--bg-2)', border: '1px solid var(--line-2)',
                  color: 'var(--fg)', borderRadius: 'var(--r-md)', padding: '5px 10px', fontSize: 12,
                }}
              />
              <Button
                variant="primary"
                size="sm"
                disabled={!canAct || !ownerInput.trim()}
                pending={transition.isPending}
                title={canAct ? undefined : t.role.noWriteAction}
                onClick={() => {
                  transition.mutate({ status: incident.status, owner: ownerInput.trim() });
                  setOwnerInput('');
                }}
              >
                {t.incidents.assign}
              </Button>
            </div>
          </div>

          <div style={{ marginBottom: 16 }}>
            <div style={{ fontSize: 11, color: 'var(--fg-3)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 6 }}>
              {t.incidents.failedChecks}
            </div>
            {incident.failed_checks.length === 0 ? (
              <div style={{ fontSize: 12, color: 'var(--fg-3)' }}>-</div>
            ) : incident.failed_checks.map(c => (
              <div key={c} style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--fg-2)', padding: '2px 0' }}>
                - {c}
              </div>
            ))}
          </div>

          <div style={{ marginBottom: 16 }}>
            <div style={{ fontSize: 11, color: 'var(--fg-3)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 6 }}>
              {t.incidents.downstreamImpact}
            </div>
            {impactedObjects.length === 0 ? (
              <div style={{ fontSize: 12, color: 'var(--fg-3)' }}>{t.incidents.noDownstreamImpact}</div>
            ) : impactedObjects.slice(0, 6).map(row => (
              <Button
                key={`${row.product}:${row.distance}`}
                variant="ghost"
                size="sm"
                onClick={() => navigate(`/objects/${encodeURIComponent(row.product)}?tab=lineage`)}
                style={{
                  display: 'grid',
                  gridTemplateColumns: '1fr auto',
                  gap: 8,
                  width: '100%',
                  textAlign: 'left',
                  color: 'var(--fg)',
                  padding: '6px 8px',
                  marginBottom: 6,
                }}
              >
                <span style={{ minWidth: 0 }}>
                  <span style={{ display: 'block', fontFamily: 'var(--font-mono)', fontSize: 12, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {row.product}
                  </span>
                  {(row.object_type || row.space) && (
                    <span style={{ display: 'block', color: 'var(--fg-3)', fontSize: 11, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {[row.object_type, row.space].filter(Boolean).join(' - ')}
                    </span>
                  )}
                </span>
                <span style={{ color: 'var(--fg-3)', fontSize: 11, alignSelf: 'center' }}>
                  d{row.distance}
                </span>
              </Button>
            ))}
            {impactedObjects.length > 6 && (
              <div style={{ fontSize: 11, color: 'var(--fg-3)' }}>
                +{impactedObjects.length - 6} {t.incidents.moreImpacted}
              </div>
            )}
          </div>

          <div>
            <div style={{ fontSize: 11, color: 'var(--fg-3)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 6 }}>
              {t.incidents.timeline}
            </div>
            {(incident.events ?? []).length === 0 ? (
              <div style={{ fontSize: 12, color: 'var(--fg-3)' }}>-</div>
            ) : (incident.events ?? []).map(ev => (
              <div key={ev.id} style={{ borderLeft: '2px solid var(--line-2)', paddingLeft: 10, marginBottom: 10 }}>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--fg-3)' }} title={absoluteTime(ev.at)}>{relativeTime(ev.at)}</div>
                <div style={{ fontSize: 12 }}>
                  <span style={{ color: 'var(--fg)' }}>{ev.actor}</span>
                  {' - '}
                  <span style={{ color: 'var(--fg-2)' }}>{ev.action}</span>
                </div>
                {ev.note && <div style={{ fontSize: 12, color: 'var(--fg-3)', marginTop: 2 }}>{ev.note}</div>}
              </div>
            ))}
          </div>
        </>
      )}
    </SidePanel>
  );
}

function FailedChecksTab({
  severityFilter,
  setSeverityFilter,
}: {
  severityFilter: string;
  setSeverityFilter: (value: string) => void;
}) {
  const { data: checks = [], isLoading, isError, refetch } = useFailedChecks(severityFilter || undefined);
  const navigate = useNavigate();

  const columns = useMemo<ColDef<FailedCheck>[]>(() => [
    { key: 'sev', header: '', render: c => <StatusDot status={c.severity} size={10} />, width: 32 },
    { key: 'check', header: t.incidents.colCheck, mono: true, render: c => c.check_name },
    { key: 'dataset', header: t.incidents.colDataset, mono: true, render: c => c.dataset },
    {
      key: 'state', header: t.incidents.colState,
      render: c => c.state && c.state !== 'executed' ? <StatePill state={c.state} size="sm" /> : null,
    },
    { key: 'actual', header: t.incidents.colActual, mono: true, render: c => c.actual_value ?? '-' },
    { key: 'expected', header: t.incidents.colExpected, mono: true, render: c => c.expect_expr },
    { key: 'when', header: t.incidents.colWhen, mono: true, render: c => new Date(c.started_at).toLocaleString() },
    {
      key: 'actions', header: '',
      render: c => (
        <Button
          variant="ghost"
          size="sm"
          onClick={e => { e.stopPropagation(); navigate(`/runs/${c.run_id}`); }}
        >
          {t.incidents.run}
        </Button>
      ),
    },
  ], [navigate]);

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 10 }}>
        <SeverityFilterChips value={severityFilter} onChange={setSeverityFilter} />
      </div>
      {isError && <ErrorBanner onRetry={() => refetch()} />}
      {isLoading && <TableSkeleton columns={8} />}
      {!isError && !isLoading && (
        <div style={{ background: 'var(--bg-1)', border: '1px solid var(--line)', borderRadius: 'var(--r-lg)', overflow: 'hidden' }}>
          <Table
            columns={columns}
            rows={checks}
            rowKey={c => c.id}
            onRowClick={c => navigate(`/objects/${encodeURIComponent(c.dataset)}`)}
            empty={t.incidents.emptyChecks}
          />
        </div>
      )}
    </div>
  );
}

export default function Incidents() {
  const [searchParams, setSearchParams] = useSearchParams();
  const statusParam = searchParams.get('status') ?? QUERY_DEFAULTS.status;
  const kindFilter = searchParams.get('kind') ?? QUERY_DEFAULTS.kind;
  const severityFilter = searchParams.get('severity') ?? QUERY_DEFAULTS.severity;
  const assignedFilter = (searchParams.get('assigned') ?? QUERY_DEFAULTS.assigned) === '1';
  const idParam = searchParams.get('id') ?? QUERY_DEFAULTS.id;
  const activeTab = normalizeTab(statusParam);
  const isChecksTab = activeTab === 'checks';
  const activeIncidentId = selectedIncidentId(idParam);
  const serverKind = kindFilter === 'internal_gate' ? 'internal_gate' : undefined;

  const { data: incidents = [], isLoading, isError, refetch } =
    useIncidents(undefined, severityFilter || undefined, serverKind);

  const visibleIncidents = useMemo(
    () => incidents.filter(i =>
      matchesKindFilter(i, kindFilter) && (!assignedFilter || Boolean(i.owner)),
    ),
    [incidents, kindFilter, assignedFilter],
  );

  const statusCounts = useMemo(
    () => visibleIncidents.reduce<Record<IncidentStatus, number>>(
      (acc, incident) => {
        acc[incident.status] += 1;
        return acc;
      },
      { open: 0, acknowledged: 0, investigating: 0, resolved: 0 },
    ),
    [visibleIncidents],
  );
  const activeCount = statusCounts.open + statusCounts.acknowledged + statusCounts.investigating;

  const filteredIncidents = useMemo(() => {
    if (activeTab === 'active') return visibleIncidents.filter(i => i.status !== 'resolved');
    if (isIncidentStatus(activeTab)) return visibleIncidents.filter(i => i.status === activeTab);
    return [];
  }, [activeTab, visibleIncidents]);

  const columns = useMemo<ColDef<Incident>[]>(() => [
    {
      key: 'sev', header: t.common.severity, width: 110,
      render: i => <StatusPill status={i.severity} size="sm" />,
    },
    {
      key: 'kind', header: t.incidents.filterKind, width: 120,
      render: i => <IncidentKindBadge kind={i.kind} />,
    },
    { key: 'title', header: t.incidents.colTitle, render: i => i.title },
    { key: 'product', header: t.incidents.colProduct, mono: true, render: i => i.product },
    {
      key: 'owner', header: t.incidents.colOwner,
      render: i => <span style={{ color: i.owner ? 'var(--fg-2)' : 'var(--fg-3)', fontSize: 12 }}>{i.owner || t.incidents.noOwner}</span>,
    },
    {
      key: 'opened', header: t.incidents.colOpened,
      render: i => <span style={{ color: 'var(--fg-3)', fontSize: 12 }} title={absoluteTime(i.opened_at)}>{relativeTime(i.opened_at)}</span>,
    },
    {
      key: 'sla', header: t.incidents.colSla, width: 120,
      render: i => <IncidentSla incident={i} />,
    },
  ], []);

  const setQuery = (next: Partial<Record<QueryKey, string>>) => {
    setSearchParams(prev => {
      const params = new URLSearchParams(prev);
      (Object.entries(next) as Array<[QueryKey, string]>).forEach(([key, value]) => {
        if (!value || value === QUERY_DEFAULTS[key]) params.delete(key);
        else params.set(key, value);
      });
      return params;
    }, { replace: true });
  };

  const closeIncident = () => setQuery({ id: '' });

  // Wenn ein Statuswechsel den Incident aus der aktuellen Tab-Liste entfernt,
  // dem Incident folgen (Status-Tab wechseln), damit der offene Drawer nicht
  // stale gegen die URL steht. Bleibt er sichtbar (z. B. open→acknowledged im
  // „Aktiv"-Tab), keinen unnötigen Tab-Sprung auslösen.
  const followTransition = (status: IncidentStatus) => {
    const stillVisible = activeTab === 'active' ? status !== 'resolved' : activeTab === status;
    if (!stillVisible) setQuery({ status });
  };

  const selectTab = (tab: IncidentTab) => {
    setQuery({ status: tab, id: '' });
  };

  const selectKind = (value: string) => {
    setQuery({ kind: value, id: '' });
  };

  const selectSeverity = (value: string) => {
    setQuery({ severity: value, id: '' });
  };

  const selectAssigned = (value: boolean) => {
    setQuery({ assigned: value ? '1' : '', id: '' });
  };

  return (
    <div className="page-full">
      <PageHeader title={t.incidents.title} />

      <div style={{ display: 'flex', borderBottom: '1px solid var(--line)', marginBottom: 16 }}>
        {TABS.map(tabKey => (
          <button
            key={tabKey}
            onClick={() => selectTab(tabKey)}
            style={{
              padding: 'var(--s2) var(--s4)', border: 'none', background: 'none',
              color: activeTab === tabKey ? 'var(--fg)' : 'var(--fg-3)',
              borderBottom: activeTab === tabKey ? '2px solid var(--cont)' : '2px solid transparent',
              cursor: 'pointer', fontSize: 13,
              marginLeft: tabKey === 'checks' ? 'auto' : undefined,
            }}
          >
            {tabKey === 'active'
              ? `${t.incidents.tabs.active} (${activeCount})`
              : isIncidentStatus(tabKey)
                ? `${t.incidents.tabs[tabKey] ?? tabKey} (${statusCounts[tabKey]})`
                : t.incidents.tabs[tabKey] ?? tabKey}
          </button>
        ))}
      </div>

      {isChecksTab ? (
        <FailedChecksTab severityFilter={severityFilter} setSeverityFilter={selectSeverity} />
      ) : (
        <>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 'var(--s3)', flexWrap: 'wrap', marginBottom: 12 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--s3)', flexWrap: 'wrap' }}>
              <KindFilterChips value={kindFilter} onChange={selectKind} />
              <FilterChip active={assignedFilter} onClick={() => selectAssigned(!assignedFilter)}>
                {t.incidents.filterAssigned}
              </FilterChip>
            </div>
            <SeverityFilterChips value={severityFilter} onChange={selectSeverity} />
          </div>
          <ActiveIncidentFilters
            kindFilter={kindFilter}
            severityFilter={severityFilter}
            assignedFilter={assignedFilter}
            onClearKind={() => selectKind('all')}
            onClearSeverity={() => selectSeverity('')}
            onClearAssigned={() => selectAssigned(false)}
          />
          {isError && <ErrorBanner onRetry={() => refetch()} />}
          {isLoading && <TableSkeleton columns={7} />}
          {!isError && !isLoading && (
            <div style={{ background: 'var(--bg-1)', border: '1px solid var(--line)', borderRadius: 'var(--r-lg)', overflow: 'hidden' }}>
              <Table
                columns={columns}
                rows={filteredIncidents}
                rowKey={i => String(i.id)}
                onRowClick={i => setQuery({ id: String(i.id) })}
                empty={t.incidents.empty}
              />
            </div>
          )}
        </>
      )}

      {!isChecksTab && activeIncidentId != null && (
        <IncidentDrawer id={activeIncidentId} onClose={closeIncident} onTransitioned={followTransition} />
      )}
    </div>
  );
}
