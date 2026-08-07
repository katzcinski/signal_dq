import { useNavigate } from 'react-router-dom';
import { Kpi } from '@/components/ui/Kpi';
import { KpiSkeleton, TableSkeleton } from '@/components/ui/Skeleton';
import { PageHeader } from '@/components/ui/PageHeader';
import { Panel } from '@/components/ui/Panel';
import { StatusDot } from '@/components/ui/StatusDot';
import { StatusPill } from '@/components/ui/StatusPill';
import { IncidentSla } from '@/components/ui/IncidentSla';
import { ErrorBanner } from '@/components/ui/ErrorBanner';
import { Table, type ColDef } from '@/components/ui/Table';
import { useSearchParamState } from '@/hooks/useSearchParamState';
import { useObjectInspection } from '@/hooks/useObjectInspection';
import { OnboardingPanel } from '@/components/OnboardingPanel';
import { StatusHeatmap } from '@/components/StatusHeatmap';
import { DqHealthTrend } from '@/components/DqHealthTrend';
import { AttentionPanel } from '@/components/AttentionPanel';
import { useObjects } from '@/api/objects';
import { useIncidents } from '@/api/incidents';
import { useActivity } from '@/api/activity';
import { useCoverageSummary } from '@/api/coverage';
import { useContracts, useContractSla } from '@/api/contracts';
import { relativeTime, absoluteTime } from '@/lib/time';
import { t } from '@/i18n/de';
import type { ActivityItem, Incident, ObjectSummary } from '@/types';

const ACTIVITY_KIND_COLOR: Record<string, string> = {
  incident: 'var(--status-fail)',
  proposal: 'var(--status-warn)',
  contract: 'var(--status-ok)',
};

// UX-N15: recent audit feed — who approved / resolved / decided what.
function ActivityFeed() {
  const { data: items = [], isSuccess } = useActivity(12);
  if (items.length === 0) {
    return <p style={{ color: 'var(--fg-3)', fontSize: 12 }}>{isSuccess ? t.activity.empty : '—'}</p>;
  }
  return (
    <div>
      {items.map((it: ActivityItem, i) => {
        const color = ACTIVITY_KIND_COLOR[it.kind] ?? 'var(--fg-3)';
        return (
          <div key={`${it.kind}-${it.ref}-${i}`} style={{
            display: 'flex', alignItems: 'center', gap: 10,
            padding: '7px 0', borderBottom: '1px solid var(--line)',
          }}>
            <span style={{
              fontSize: 10, borderRadius: 'var(--r)', padding: '2px 6px', minWidth: 64, textAlign: 'center',
              background: `color-mix(in srgb, ${color} 14%, transparent)`,
              color, border: `1px solid ${color}`,
            }}>
              {t.activity.kind[it.kind] ?? it.kind}
            </span>
            <span style={{ fontSize: 12, color: 'var(--fg)' }}>{it.actor}</span>
            <span style={{ fontSize: 12, color: 'var(--fg-3)' }}>{t.activity.action[it.action] ?? it.action}</span>
            {it.product && <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--fg-3)' }}>{it.product}</span>}
            <span style={{ flex: 1, fontSize: 11, color: 'var(--fg-3)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {it.summary}
            </span>
            <span title={absoluteTime(it.at)} style={{ fontSize: 11, color: 'var(--fg-3)', whiteSpace: 'nowrap' }}>
              {relativeTime(it.at)}
            </span>
          </div>
        );
      })}
    </div>
  );
}

const SEVERITY_ORDER: Record<string, number> = { critical: 0, fail: 1, warn: 2 };

function SlaBar({ pct }: { pct: number | null }) {
  if (pct === null) return <span style={{ fontSize: 10, color: 'var(--fg-3)' }}>—</span>;
  const color = pct >= 99 ? 'var(--qual)' : pct >= 90 ? 'var(--status-warn)' : 'var(--status-crit)';
  return (
    <div title={`${pct}%`} style={{ display: 'flex', alignItems: 'center', gap: 'var(--s1)', width: 84 }}>
      <div style={{ width: 52, height: 5, background: 'var(--bg-2)', borderRadius: 3, overflow: 'hidden' }}>
        <div style={{ width: `${Math.min(pct, 100)}%`, height: '100%', background: color, borderRadius: 3 }} />
      </div>
      <span style={{ fontSize: 10, color: 'var(--fg-3)', fontFamily: 'var(--font-mono)' }}>{pct}%</span>
    </div>
  );
}

// UX-Konsistenz §2.9: SLA-Panel als echte Tabelle (Zeilen-Hover über `.tbl-row`,
// Dichte-Tokens `--row-pad-*`, konsistente Header) statt handgerollter Flex-Zeile.
// Der SLA-Wert wird pro Produkt geladen, daher bleibt eine Zeile = eine Komponente.
const SLA_CELL: React.CSSProperties = { padding: 'var(--row-pad-y) var(--row-pad-x)', fontSize: 'var(--cell-fs)' };

function SlaRow({ product }: { product: string }) {
  const { data: sla } = useContractSla(product);
  const w = sla?.windows;
  const cur = sla?.current ?? 'unknown';
  const curColor = cur === 'compliant' ? 'var(--qual)' : cur === 'breached' ? 'var(--status-crit)' : 'var(--fg-3)';
  return (
    <tr className="tbl-row" style={{ borderBottom: '1px solid var(--line)' }}>
      <td style={{ ...SLA_CELL, fontFamily: 'var(--font-mono)', color: 'var(--fg-2)', maxWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{product}</td>
      <td style={{ ...SLA_CELL, color: curColor }}>{t.compliance[cur] ?? cur}</td>
      <td style={SLA_CELL}><SlaBar pct={w?.['7d'] ?? null} /></td>
      <td style={SLA_CELL}><SlaBar pct={w?.['30d'] ?? null} /></td>
      <td style={SLA_CELL}><SlaBar pct={w?.['90d'] ?? null} /></td>
    </tr>
  );
}

// Befund-Schweregrad je Objekt: schlechtester Familien- bzw. Gesamtstatus.
// 9 = kein Befund ("Unbekannt") — steuert Sortierung und den Befunde-Filter.
const STATUS_RANK: Record<string, number> = { critical: 0, fail: 1, error: 2, warn: 3, pass: 4 };
const rankOf = (s?: string) => (s && s in STATUS_RANK ? STATUS_RANK[s] : 9);
const worstRank = (o: ObjectSummary) => Math.min(
  rankOf(o.family_status?.observability),
  rankOf(o.family_status?.quality),
  rankOf(o.status),
);

const FAMILY_TEXT_COLOR: Record<string, string> = {
  critical: 'var(--status-crit)',
  fail: 'var(--status-fail)',
  error: 'var(--status-stale)',
  warn: 'var(--status-warn)',
  pass: 'var(--status-ok)',
};

// Status cell: dot + text label — never color-only (U1). Befunde färben auch
// den Text, "Unbekannt" bleibt gedimmt, damit das Grid nicht rauscht.
function FamilyStatusCell({ status }: { status: string }) {
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 12,
      color: FAMILY_TEXT_COLOR[status] ?? 'var(--fg-3)',
    }}>
      <StatusDot status={status} />
      <span>{t.status[status] ?? status}</span>
    </span>
  );
}

function incidentHref(incident: Incident) {
  const kind = incident.kind === 'internal_gate' ? 'internal_gate' : 'contract';
  return `/incidents?status=${incident.status}&kind=${kind}&id=${incident.id}`;
}

const segBtn = (active: boolean): React.CSSProperties => ({
  background: active ? 'var(--bg-1)' : 'transparent',
  border: active ? '1px solid var(--line-2)' : '1px solid transparent',
  color: active ? 'var(--fg)' : 'var(--fg-3)',
  borderRadius: 'var(--r)', padding: '3px 10px', fontSize: 11,
  cursor: 'pointer', fontWeight: active ? 600 : 400, whiteSpace: 'nowrap',
});

export default function Cockpit() {
  const objectsQuery = useObjects();
  const incidentsQuery = useIncidents();
  const coverageQuery = useCoverageSummary();
  const contractsQuery = useContracts();
  const { data: objects = [] } = objectsQuery;
  const { data: incidents = [] } = incidentsQuery;
  const { data: contracts = [] } = contractsQuery;
  const activeContracts = contracts.filter(c =>
    c.lifecycle === 'active' && c.kind !== 'internal_gate',
  );
  const coverage = coverageQuery.data;
  const navigate = useNavigate();
  const [gridMode, setGridMode] = useSearchParamState('grid');
  // Two-level inspection (wie auf der Objekte-Seite): Checks-Zelle/Hotspots öffnen
  // das kompakte Popover, der Zeilenklick das rechte Betriebs-Panel. Eine Instanz
  // für die ganze Seite — Grid, Hotspots und Heatmap teilen sie sich, damit nie
  // zwei Panels übereinander liegen.
  const { openChecks, openPeek, overlays } = useObjectInspection();

  const totalObjects = objects.length;
  const unvalidated = coverage?.unvalidated_30d ?? [];
  const spaceCount = new Set(objects.map(o => o.space)).size;
  const layerCount = new Set(objects.map(o => o.layer)).size;

  const openIncidents = incidents.filter(i => i.status !== 'resolved');
  const criticalIncidents = openIncidents.filter(i => i.severity === 'critical').length;
  // Gate-Signale = offene Engineering-Signal-Incidents (internal_gate). Zählung
  // und Sprungziel teilen sich dieselbe Quelle, damit die Zahl die Landeliste
  // erklärt (statt der abweichenden coverage.gates_failing-Check-Zählung).
  const gateIncidents = openIncidents.filter(i => i.kind === 'internal_gate').length;
  const topIncidents = [...openIncidents]
    .sort((a, b) => (SEVERITY_ORDER[a.severity] ?? 9) - (SEVERITY_ORDER[b.severity] ?? 9))
    .slice(0, 5);
  const oldestOpen = openIncidents.reduce<string | null>(
    (min, i) => (!min || i.opened_at < min ? i.opened_at : min), null,
  );
  const incidentsDelta = openIncidents.length === 0 ? undefined : [
    criticalIncidents > 0 ? `${criticalIncidents} ${t.cockpit.critical}` : null,
    oldestOpen ? t.cockpit.kpiOldestSince.replace('{time}', relativeTime(oldestOpen)) : null,
  ].filter(Boolean).join(' · ');

  // Status-Grid: Befunde zuerst (nach Schweregrad), das befundlose Rauschen
  // kollabiert in eine Summenzeile. Der Filter lebt in der URL (?grid=all).
  const sortedObjects = [...objects].sort(
    (a, b) => worstRank(a) - worstRank(b) || a.name.localeCompare(b.name),
  );
  const findingRows = sortedObjects.filter(o => worstRank(o) < 9);
  const showAll = gridMode === 'all' || findingRows.length === 0;
  const gridRows = showAll ? sortedObjects : findingRows;
  const hiddenCount = sortedObjects.length - findingRows.length;
  const activeByProduct = new Map(activeContracts.map(c => [c.product, c]));

  // U4: empty tenant → guided onboarding instead of the grid.
  if (objectsQuery.isSuccess && !objectsQuery.isError && objects.length === 0) {
    return <OnboardingPanel />;
  }

  // Objekt × Familie matrix — both family statuses per row (WS1-3 StatusGrid),
  // ergänzt um Contract-Bindung und letzten Lauf.
  const gridColumns: ColDef<ObjectSummary>[] = [
    {
      key: 'name', header: t.cockpit.colObject, mono: true,
      // Der Name führt zur Vollansicht; der Rest der Zeile öffnet das Betriebs-Panel.
      render: o => (
        <button
          onClick={e => { e.stopPropagation(); navigate(`/objects/${o.id}`); }}
          onKeyDown={e => e.stopPropagation()}
          style={{ background: 'none', border: 'none', padding: 0, color: 'var(--fg-2)', cursor: 'pointer', font: 'inherit' }}
        >
          {o.name}
        </button>
      ),
    },
    { key: 'space', header: t.cockpit.colSpace, render: o => <span style={{ color: 'var(--fg-3)', fontSize: 12 }}>{o.space}</span> },
    { key: 'layer', header: t.cockpit.colLayer, render: o => <span style={{ color: 'var(--fg-3)', fontSize: 12 }}>{o.layer}</span> },
    {
      key: 'obs', header: t.cockpit.colObservability,
      render: o => <FamilyStatusCell status={o.family_status?.observability ?? 'unknown'} />,
    },
    {
      key: 'qual', header: t.cockpit.colQuality,
      render: o => <FamilyStatusCell status={o.family_status?.quality ?? 'unknown'} />,
    },
    {
      key: 'checks', header: t.objects.colChecks,
      // Checks-Zelle: öffnet das kompakte Quick-Checks-Popover am Zeiger.
      render: o => (
        <button
          type="button"
          aria-label={t.peek.openChecksFor.replace('{name}', o.name)}
          onClick={event => openChecks(o.id, event)}
          onKeyDown={event => event.stopPropagation()}
          style={{
            background: 'var(--bg-2)',
            border: '1px solid var(--line-2)',
            borderRadius: 'var(--r-md)',
            color: 'var(--fg-2)',
            cursor: 'pointer',
            fontSize: 12,
            minWidth: 32,
            padding: '2px 8px',
          }}
        >
          {o.check_count ?? '-'}
        </button>
      ),
    },
    {
      key: 'contract', header: t.cockpit.colContract,
      render: o => {
        const c = activeByProduct.get(o.id);
        return c ? (
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 12, color: 'var(--status-ok)' }}>
            <StatusDot status="pass" />
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11 }}>v{c.version}</span>
          </span>
        ) : <span style={{ color: 'var(--fg-3)' }}>—</span>;
      },
    },
    {
      key: 'last_run', header: t.objects.colLastRun,
      render: o => (
        <span title={o.last_run ? absoluteTime(o.last_run) : undefined} style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--fg-3)' }}>
          {o.last_run ? relativeTime(o.last_run) : '—'}
        </span>
      ),
    },
  ];

  return (
    <div className="page-full" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--s4)' }}>
      <PageHeader
        title={t.cockpit.title}
        subtitle={t.cockpit.subtitle}
        style={{ marginBottom: 0 }}
        actions={(
          <div style={{ display: 'flex', gap: 'var(--s2)', alignItems: 'center', flexWrap: 'wrap' }}>
            {objectsQuery.dataUpdatedAt > 0 && (
              <span style={{
                fontFamily: 'var(--font-mono)', fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.08em',
                color: 'var(--fg-2)', padding: 'var(--s1) var(--s3)', borderRadius: 'var(--r-full)',
                border: '1px solid var(--line-2)', background: 'var(--bg-1)',
                display: 'inline-flex', alignItems: 'center', gap: 'var(--s2)', whiteSpace: 'nowrap',
              }}>
                <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--signal)', boxShadow: '0 0 0 3px var(--signal-dim)' }} />
                {t.cockpit.liveUpdated.replace('{time}', new Date(objectsQuery.dataUpdatedAt).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' }))}
              </span>
            )}
            <span style={{
              fontSize: 11, color: 'var(--fg-2)', padding: 'var(--s1) var(--s3)', borderRadius: 'var(--r-full)',
              border: '1px solid var(--line-2)', background: 'var(--bg-1)',
              display: 'inline-flex', alignItems: 'center', gap: 'var(--s2)', whiteSpace: 'nowrap',
            }}>
              <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--qual)' }} />
              {t.cockpit.dqFirst}
            </span>
          </div>
        )}
      />

      {objectsQuery.isError && <ErrorBanner onRetry={() => objectsQuery.refetch()} />}
      {incidentsQuery.isError && <ErrorBanner onRetry={() => incidentsQuery.refetch()} />}

      {/* Hero: DQ-health trend (left) + hotspots (right). */}
      <div className="dash-hero">
        <DqHealthTrend />
        <AttentionPanel objects={objects} onInspect={openChecks} />
      </div>

      {/* KPI strip — the at-a-glance numbers. */}
      {objectsQuery.isLoading ? <KpiSkeleton count={5} /> : (
      <div className="dash-kpis">
        <Kpi
          label={t.cockpit.kpiObjects}
          value={totalObjects}
          delta={totalObjects > 0
            ? t.cockpit.kpiContext.replace('{spaces}', String(spaceCount)).replace('{layers}', String(layerCount))
            : undefined}
          accent="var(--cont)"
          onClick={() => navigate('/objects')}
        />
        <Kpi
          label={t.cockpit.kpiCoverage}
          value={`${String(coverage?.contract_coverage_pct ?? 0).replace('.', ',')} %`}
          delta={coverage ? `${coverage.with_active_contract}/${coverage.objects_total} ${t.cockpit.coverageOf}` : undefined}
          accent="var(--qual)"
          onClick={() => navigate('/compliance')}
        />
        <Kpi
          label={t.cockpit.kpiOpenIncidents}
          value={openIncidents.length}
          delta={incidentsDelta}
          deltaPositive={criticalIncidents > 0 ? false : undefined}
          accent={openIncidents.length > 0 ? 'var(--status-fail)' : 'var(--qual)'}
          onClick={() => navigate('/incidents?status=active')}
        />
        <Kpi
          label={t.cockpit.kpiGateSignals}
          value={gateIncidents}
          accent={gateIncidents > 0 ? 'var(--status-warn)' : 'var(--qual)'}
          onClick={() => navigate('/incidents?status=active&kind=internal_gate')}
        />
        <Kpi
          label={t.cockpit.kpiUnvalidated}
          value={unvalidated.length}
          accent={unvalidated.length > 0 ? 'var(--status-warn)' : 'var(--qual)'}
          onClick={() => navigate('/compliance?mode=stale')}
        />
      </div>
      )}

      {/* Primary drill-down: Objekt × Familie — Befunde zuerst, Rauschen kollabiert. */}
      <div style={{ background: 'var(--bg-1)', border: '1px solid var(--line)', borderRadius: 'var(--r-lg)', overflow: 'hidden', boxShadow: 'var(--shadow-1)' }}>
        <div style={{
          display: 'flex', alignItems: 'center', gap: 'var(--s4)', flexWrap: 'wrap',
          padding: '8px 16px', borderBottom: '1px solid var(--line)',
        }}>
          <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--fg-2)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            {t.cockpit.statusGrid}
          </span>
          {findingRows.length > 0 && (
            <div role="group" aria-label={t.cockpit.statusGrid} style={{
              display: 'inline-flex', background: 'var(--bg-2)', border: '1px solid var(--line)',
              borderRadius: 'var(--r-md)', padding: 2,
            }}>
              <button aria-pressed={!showAll} style={segBtn(!showAll)} onClick={() => setGridMode('')}>
                {t.cockpit.gridFindings} · {findingRows.length}
              </button>
              <button aria-pressed={showAll} style={segBtn(showAll)} onClick={() => setGridMode('all')}>
                {t.cockpit.gridAll} · {sortedObjects.length}
              </button>
            </div>
          )}
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--fg-3)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
            {t.cockpit.gridSortHint}
          </span>
          <button
            onClick={() => navigate('/objects')}
            style={{ marginLeft: 'auto', background: 'none', border: 'none', color: 'var(--cont)', fontSize: 11, cursor: 'pointer', padding: 0 }}
          >
            {t.cockpit.gridToCatalog}
          </button>
        </div>
        {objectsQuery.isLoading ? (
          <TableSkeleton columns={8} />
        ) : (
          <>
            <Table
              columns={gridColumns}
              rows={gridRows}
              rowKey={o => o.id}
              onRowClick={o => openPeek(o.id)}
              rowStyle={o => worstRank(o) === 0
                ? { background: 'color-mix(in srgb, var(--status-crit) 4%, transparent)' }
                : undefined}
              empty={t.cockpit.noObjects}
            />
            {!showAll && hiddenCount > 0 && (
              <button
                onClick={() => setGridMode('all')}
                style={{
                  display: 'block', width: '100%', textAlign: 'left',
                  padding: '9px 16px', background: 'none', border: 'none',
                  borderTop: '1px solid var(--line)', color: 'var(--fg-3)', fontSize: 11.5, cursor: 'pointer',
                }}
              >
                {t.cockpit.gridHidden.replace('{n}', String(hiddenCount))}{' '}
                — <span style={{ color: 'var(--cont)' }}>{t.cockpit.gridShow} ▾</span>
              </button>
            )}
          </>
        )}
      </div>

      <StatusHeatmap onInspect={openChecks} />

      {/* Operational pair: open incidents + SLA compliance. */}
      <div className="dash-2col">
        <Panel title={t.cockpit.openIncidents}>
          {topIncidents.length === 0 ? (
            <p style={{ color: 'var(--fg-3)', fontSize: 12 }}>
              {incidentsQuery.isSuccess ? t.cockpit.noIncidents : '—'}
            </p>
          ) : topIncidents.map((i: Incident) => (
            <button
              key={i.id}
              onClick={() => navigate(incidentHref(i))}
              style={{
                display: 'flex', alignItems: 'center', gap: 'var(--s3)', width: '100%', textAlign: 'left',
                padding: '6px 0', background: 'none', border: 'none',
                borderBottom: '1px solid var(--line)', borderRadius: 0,
                color: 'var(--fg)', cursor: 'pointer',
              }}
            >
              <StatusPill status={i.severity} size="sm" />
              <span style={{ fontSize: 12, flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{i.title}</span>
              <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--fg-3)', fontSize: 11 }}>{i.product}</span>
              <IncidentSla incident={i} />
            </button>
          ))}
        </Panel>

        {activeContracts.length > 0 ? (
          <Panel title={t.cockpit.slaTitle}>
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', tableLayout: 'fixed' }}>
                <thead>
                  <tr style={{ background: 'var(--bg-2)' }}>
                    {[t.cockpit.slaProduct, t.cockpit.slaCurrent, t.cockpit.sla7d, t.cockpit.sla30d, t.cockpit.sla90d].map((h, i) => (
                      <th key={h} style={{
                        padding: 'var(--row-pad-y) var(--row-pad-x)', textAlign: 'left',
                        fontSize: 10, fontWeight: 600, color: 'var(--fg-3)', textTransform: 'uppercase',
                        letterSpacing: '0.06em', borderBottom: '1px solid var(--line)',
                        width: i === 0 ? 'auto' : 92, whiteSpace: 'nowrap',
                      }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {activeContracts.map(c => <SlaRow key={c.product} product={c.product} />)}
                </tbody>
              </table>
            </div>
          </Panel>
        ) : (
          <Panel title={t.cockpit.slaTitle}>
            <p style={{ color: 'var(--fg-3)', fontSize: 12 }}>{t.cockpit.slaEmpty}</p>
          </Panel>
        )}
      </div>

      {/* Audit + neglected objects. */}
      <div className="dash-2col">
        <Panel title={t.activity.title}>
          <ActivityFeed />
        </Panel>

        <Panel title={`${t.cockpit.unvalidatedTitle}${unvalidated.length ? ` (${unvalidated.length})` : ''}`}>
          {unvalidated.length === 0 ? (
            <p style={{ color: 'var(--fg-3)', fontSize: 12 }}>
              {coverageQuery.isSuccess ? t.cockpit.unvalidatedEmpty : '—'}
            </p>
          ) : (
            <>
              <p style={{ color: 'var(--fg-3)', fontSize: 11, marginBottom: 8 }}>{t.cockpit.unvalidatedHint}</p>
              {unvalidated.map(objId => (
                <button
                  key={objId}
                  onClick={() => navigate(`/objects/${encodeURIComponent(objId)}`)}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 'var(--s3)', width: '100%', textAlign: 'left',
                    padding: '6px 0', background: 'none', border: 'none',
                    borderBottom: '1px solid var(--line)', borderRadius: 0,
                    color: 'var(--fg)', cursor: 'pointer',
                  }}
                >
                  <StatusDot status="unknown" />
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{objId}</span>
                  <span style={{ color: 'var(--fg-3)', fontSize: 11 }}>{t.common.open} →</span>
                </button>
              ))}
            </>
          )}
        </Panel>
      </div>

      {overlays}
    </div>
  );
}
