import { useMemo } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useObjects } from '@/api/objects';
import { useContracts } from '@/api/contracts';
import { useCoverageSummary } from '@/api/coverage';
import { LifecycleStepper } from '@/components/LifecycleStepper';
import { useObjectInspection } from '@/hooks/useObjectInspection';
import { useSearchParamState } from '@/hooks/useSearchParamState';
import { Panel } from '@/components/ui/Panel';
import { PageHeader } from '@/components/ui/PageHeader';
import { ErrorBanner } from '@/components/ui/ErrorBanner';
import { FilterChip } from '@/components/ui/FilterChip';
import { Kpi } from '@/components/ui/Kpi';
import { KpiSkeleton, TableSkeleton } from '@/components/ui/Skeleton';
import { LifecycleTag } from '@/components/ui/LifecycleTag';
import { ControlSelect } from '@/components/ui/ControlPrimitives';
import { StatusPill } from '@/components/ui/StatusPill';
import { DistributionBar, type DistributionSegment } from '@/components/ui/DistributionBar';
import { SlaOverviewPanel } from '@/components/compliance/SlaOverviewPanel';
import { Table, type ColDef } from '@/components/ui/Table';
import { t } from '@/i18n/de';
import type { Contract, Lifecycle, ObjectSummary } from '@/types';

// Governance-Reife als eine Achse: ungebunden (0) < Entwurf < aktiv < veraltet.
const BINDING_ORDER: Record<Lifecycle, number> = { draft: 1, active: 2, deprecated: 3 };

// Ein Filter treibt Tabelle und die Deep-Link-KPIs: 'all' | 'uncovered' |
// 'breached' | 'stale'. Der Klick auf eine KPI setzt (bzw. löst) den passenden
// Modus, damit die Zahl oben immer die Zeilen unten erklärt. Der Modus lebt in
// der URL (?mode=stale), damit Reload/Back/Deep-Links (z. B. das Cockpit-KPI
// „>30d unvalidiert") wie auf jeder anderen Listenseite reproduzierbar sind.
type FilterMode = 'all' | 'uncovered' | 'breached' | 'stale';
const FILTER_MODES: readonly FilterMode[] = ['all', 'uncovered', 'breached', 'stale'];

function normalizeMode(value: string): FilterMode {
  return (FILTER_MODES as readonly string[]).includes(value) ? (value as FilterMode) : 'all';
}

// Contract-Bindung eines Objekts: Lifecycle-Chip + Version, oder ein bewusst
// leiser „leerer Platz"-Chip (gestrichelt, neutral) für ungebundene Objekte —
// Abwesenheit ist kein Breach; den Alarm tragen KPI und Filter, nicht 15 rote
// Chips in der Tabelle. Ein echter Breach bzw. eine überfällige Validierung ist
// hingegen ein Alarm und trägt den kanonischen Status-Pill (Farbtoken statt
// handkopierter Inline-Chips).
function ContractCell({ contract, breached, stale }: { contract?: Contract; breached: boolean; stale: boolean }) {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 'var(--s2)' }}>
      {contract ? (
        <>
          <LifecycleTag lifecycle={contract.lifecycle} />
          {contract.version && (
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--fg-3)' }}>
              v{contract.version}
            </span>
          )}
        </>
      ) : (
        <span style={{
          border: '1px dashed var(--line-2)',
          borderRadius: 'var(--r)', color: 'var(--fg-3)',
          display: 'inline-flex', fontSize: 10, padding: '1px 6px', whiteSpace: 'nowrap',
        }}>
          {t.governance.noContract}
        </span>
      )}
      {breached && <StatusPill status="breached" size="sm" label={t.governance.cellBreached} />}
      {stale && <StatusPill status="stale" size="sm" label={t.governance.cellStale} />}
    </span>
  );
}

// CSV-Export der aktuell gefilterten Governance-Ansicht — Audit-Evidenz ohne
// Server-Roundtrip. RFC-4180-Quoting, damit Namen mit Komma/Anführungszeichen
// nicht die Spalten zerreißen.
function toCsv(rows: string[][]): string {
  const esc = (cell: string) => `"${cell.replace(/"/g, '""')}"`;
  return rows.map(r => r.map(esc).join(',')).join('\r\n');
}

export default function Governance() {
  const navigate = useNavigate();
  const { data: objects = [], isLoading, isError, refetch } = useObjects();
  const contractsQuery = useContracts();
  const coverageQuery = useCoverageSummary();
  // Zwei-Ebenen-Inspektion (wie Cockpit/Objekte): der Objekt-Name öffnet das
  // Quick-Checks-Popover, der Zeilenklick bleibt der Sprung ins Objektdetail.
  const { openChecks, overlays } = useObjectInspection();
  const [search, setSearch] = useSearchParamState('q');
  const [space, setSpace] = useSearchParamState('space');
  const [modeParam, setModeParam] = useSearchParamState('mode', 'all');
  const mode = normalizeMode(modeParam);
  // Klick auf eine aktive KPI/Chip löst den Filter wieder — Toggle statt Sackgasse.
  const toggle = (m: FilterMode) => setModeParam(mode === m ? 'all' : m);

  const contracts = contractsQuery.data;
  const { boundaryContracts, contractByProduct, breachedIds } = useMemo(() => {
    const boundary = (contracts ?? []).filter(c => c.kind !== 'internal_gate');
    return {
      boundaryContracts: boundary,
      contractByProduct: new Map(boundary.map(c => [c.product, c])),
      // Identitäts-Join product == object.id; Breach kommt aus dem Store und ist
      // auf jedem Boundary-Contract der Liste annotiert (contracts.py).
      breachedIds: new Set(boundary.filter(c => c.compliance === 'breached').map(c => c.product)),
    };
  }, [contracts]);
  const activeContracts = boundaryContracts.filter(c => c.lifecycle === 'active');
  const uncovered = objects.filter(o => !contractByProduct.has(o.id)).length;
  const coverage = coverageQuery.data;
  const breached = coverage?.contracts_breached ?? 0;
  const staleIds = useMemo(() => new Set(coverage?.unvalidated_30d ?? []), [coverage]);
  // Lifecycle-Verteilung je Objekt (aktiv/Entwurf/veraltet/ungebunden) — zeigt
  // Momentum, das die reine Coverage-Prozentzahl verschluckt.
  const lifecycleSegments: DistributionSegment[] = useMemo(() => {
    const dist = { active: 0, draft: 0, deprecated: 0, none: 0 };
    for (const o of objects) {
      const c = contractByProduct.get(o.id);
      if (!c) dist.none += 1;
      else dist[c.lifecycle] += 1;
    }
    return [
      { key: 'active', label: t.lifecycle.active, count: dist.active, color: 'var(--status-ok)' },
      { key: 'draft', label: t.lifecycle.draft, count: dist.draft, color: 'var(--fg-3)' },
      { key: 'deprecated', label: t.lifecycle.deprecated, count: dist.deprecated, color: 'var(--status-stale)' },
      { key: 'none', label: t.governance.noContract, count: dist.none, color: 'var(--line-2)' },
    ];
  }, [objects, contractByProduct]);
  const spaces = useMemo(() => Array.from(new Set(objects.map(o => o.space))).sort(), [objects]);
  const loading = isLoading || contractsQuery.isLoading;
  const error = isError || contractsQuery.isError;
  const filtered = !!search || mode !== 'all' || !!space;

  const rows = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return objects.filter(o => {
      if (space && o.space !== space) return false;
      if (mode === 'uncovered' && contractByProduct.has(o.id)) return false;
      if (mode === 'breached' && !breachedIds.has(o.id)) return false;
      if (mode === 'stale' && !staleIds.has(o.id)) return false;
      if (!needle) return true;
      return o.name.toLowerCase().includes(needle) || o.space.toLowerCase().includes(needle);
    });
  }, [objects, contractByProduct, breachedIds, staleIds, search, space, mode]);

  const columns: ColDef<ObjectSummary>[] = [
    {
      key: 'object',
      header: t.governance.colObject,
      mono: true,
      sortable: true,
      sortValue: o => o.name,
      // Der Name öffnet das Quick-Checks-Popover ("ist dieses Objekt unter
      // Contract — und gerade gesund?"); der Rest der Zeile führt ins Detail.
      render: o => (
        <button
          type="button"
          aria-label={t.peek.openChecksFor.replace('{name}', o.name)}
          onClick={event => openChecks(o.id, event)}
          onKeyDown={event => event.stopPropagation()}
          style={{ background: 'none', border: 'none', padding: 0, color: 'var(--fg)', cursor: 'pointer', font: 'inherit' }}
        >
          {o.name}
        </button>
      ),
    },
    {
      key: 'space',
      header: t.governance.colSpace,
      sortable: true,
      sortValue: o => o.space,
      render: o => <span style={{ color: 'var(--fg-3)', fontSize: 12 }}>{o.space}</span>,
    },
    {
      key: 'contract',
      header: t.governance.colContract,
      sortable: true,
      sortValue: o => {
        const contract = contractByProduct.get(o.id);
        return contract ? BINDING_ORDER[contract.lifecycle] ?? 1 : 0;
      },
      render: o => (
        <ContractCell
          contract={contractByProduct.get(o.id)}
          breached={breachedIds.has(o.id)}
          stale={staleIds.has(o.id)}
        />
      ),
    },
  ];

  const exportRows = () => {
    const header = [t.governance.colObject, t.governance.colSpace, t.governance.colContract, 'Version', t.governance.cellBreached, t.governance.cellStale];
    const body = rows.map(o => {
      const c = contractByProduct.get(o.id);
      return [
        o.name,
        o.space,
        c ? c.lifecycle : t.governance.noContract,
        c?.version ?? '',
        breachedIds.has(o.id) ? 'x' : '',
        staleIds.has(o.id) ? 'x' : '',
      ];
    });
    // BOM voran, damit Excel UTF-8 (Umlaute) korrekt liest.
    const blob = new Blob(['﻿' + toCsv([header, ...body])], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `governance-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const tableActions = (
    <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--s2)', flexWrap: 'wrap' }}>
      <FilterChip active={mode === 'uncovered'} onClick={() => toggle('uncovered')}>
        {t.governance.onlyUncovered}
      </FilterChip>
      <FilterChip active={mode === 'breached'} onClick={() => toggle('breached')}>
        {t.governance.onlyBreached}
      </FilterChip>
      <FilterChip active={mode === 'stale'} onClick={() => toggle('stale')}>
        {t.governance.onlyStale}
      </FilterChip>
      {spaces.length > 1 && (
        <ControlSelect
          label={t.governance.spaceFilterLabel}
          tone={space ? 'accent' : 'neutral'}
          value={space}
          onChange={e => setSpace(e.target.value)}
        >
          <option value="">{t.governance.spaceAll}</option>
          {spaces.map(s => <option key={s} value={s}>{s}</option>)}
        </ControlSelect>
      )}
      <input
        type="search"
        name="governance-search"
        autoComplete="off"
        spellCheck={false}
        value={search}
        onChange={e => setSearch(e.target.value)}
        placeholder={t.governance.searchPlaceholder}
        aria-label={t.governance.searchPlaceholder}
        style={{
          background: 'var(--bg-2)', border: '1px solid var(--line-2)',
          color: 'var(--fg)', borderRadius: 'var(--r-md)', padding: '5px 10px', fontSize: 12, minWidth: 180,
        }}
      />
      <button
        type="button"
        onClick={exportRows}
        disabled={rows.length === 0}
        style={{
          background: 'var(--bg-2)', border: '1px solid var(--line-2)',
          color: rows.length === 0 ? 'var(--fg-3)' : 'var(--fg-2)',
          borderRadius: 'var(--r-md)', padding: '5px 10px', fontSize: 12,
          cursor: rows.length === 0 ? 'default' : 'pointer', whiteSpace: 'nowrap',
        }}
      >
        {t.governance.exportCsv}
      </button>
    </div>
  );

  return (
    <div className="page-full">
      <PageHeader title={t.governance.title} subtitle={t.governance.subtitle} />

      {/* Antwort zuerst: Wie weit ist der Bestand unter Contract-Governance? */}
      {loading ? <KpiSkeleton count={4} /> : (
        <div className="dash-kpis" style={{ marginBottom: 'var(--s4)' }}>
          <Kpi
            label={t.governance.kpiCoverage}
            value={`${coverage?.contract_coverage_pct ?? 0}%`}
            delta={coverage ? `${coverage.with_active_contract}/${coverage.objects_total} ${t.governance.coverageOf}` : undefined}
            deltaPositive
            accent="var(--cont)"
          />
          <Kpi
            label={t.governance.kpiUncovered}
            value={uncovered}
            accent={uncovered > 0 ? 'var(--status-warn)' : 'var(--qual)'}
            onClick={uncovered > 0 ? () => toggle('uncovered') : undefined}
          />
          <Kpi
            label={t.governance.contractsBreached}
            value={breached}
            accent={breached > 0 ? 'var(--status-fail)' : 'var(--qual)'}
            onClick={breached > 0 ? () => toggle('breached') : undefined}
          />
          <Kpi
            label={t.governance.kpiStale}
            value={staleIds.size}
            delta={staleIds.size > 0 ? t.governance.staleOf : undefined}
            accent={staleIds.size > 0 ? 'var(--status-warn)' : 'var(--qual)'}
            onClick={staleIds.size > 0 ? () => toggle('stale') : undefined}
          />
        </div>
      )}

      {!loading && objects.length > 0 && (
        <div style={{ marginBottom: 'var(--s4)' }}>
          <Panel title={t.governance.distributionTitle} family="contract">
            <DistributionBar segments={lifecycleSegments} />
          </Panel>
        </div>
      )}

      {!loading && activeContracts.length === 0 && (
        <div style={{
          background: 'color-mix(in srgb, var(--cont) 8%, transparent)',
          border: '1px solid var(--cont)',
          borderRadius: 'var(--r-lg)', padding: 'var(--s3) var(--s4)', marginBottom: 16,
          fontSize: 12, color: 'var(--fg-2)',
        }}>
          {t.governance.noActiveContractsPre}
          <strong>{t.governance.noActiveContractsArea}</strong>
          {t.governance.noActiveContractsPost}
          {' '}
          <Link to="/contracts" style={{ color: 'var(--cont)', fontWeight: 600, whiteSpace: 'nowrap' }}>
            {t.governance.noActiveContractsCta} →
          </Link>
        </div>
      )}

      <Panel title={t.governance.objectStatusTitle} family="contract" actions={tableActions}>
        {error ? (
          <ErrorBanner onRetry={() => { refetch(); contractsQuery.refetch(); }} />
        ) : loading ? (
          <TableSkeleton columns={3} />
        ) : (
          <Table
            columns={columns}
            rows={rows}
            rowKey={o => o.id}
            onRowClick={o => navigate(`/objects/${o.id}`)}
            empty={filtered ? t.governance.noMatches : t.governance.noObjects}
          />
        )}
      </Panel>

      {/* SLA-Übersicht je aktivem Boundary-Contract (7/30/90-Tage-Compliance). */}
      {!loading && (
        <div style={{ marginTop: 'var(--s4)' }}>
          <SlaOverviewPanel contracts={activeContracts} />
        </div>
      )}

      {/* Referenz als Disclosure: die Policy bleibt eine Klick entfernt, führt
          aber nicht mehr die Seite an — die handlungsrelevante Tabelle gewinnt Raum. */}
      <details style={{ marginTop: 'var(--s4)' }}>
        <summary style={{
          cursor: 'pointer', fontSize: 12, fontWeight: 600, color: 'var(--fg-2)',
          padding: 'var(--s2) 0', listStyle: 'revert',
        }}>
          {t.governance.rulesDisclosure}
        </summary>
        <div className="dash-2col" style={{ marginTop: 'var(--s3)' }}>
          <Panel title={t.governance.g1Title} family="contract">
            <ul style={{ paddingLeft: 16, margin: 0 }}>
              {t.governance.g1Policy.map((p, i) => (
                <li key={i} style={{ fontSize: 12, color: 'var(--fg-2)', marginBottom: 6, lineHeight: 1.6 }}>{p}</li>
              ))}
            </ul>
          </Panel>
          <Panel title={t.governance.lifecycleTitle} family="contract">
            <p style={{ fontSize: 12, color: 'var(--fg-2)', marginBottom: 12 }}>
              {t.governance.lifecycleDesc1}<strong>{t.governance.lifecycleDescActive}</strong>{t.governance.lifecycleDesc2}
            </p>
            <LifecycleStepper current="active" />
          </Panel>
        </div>
      </details>

      {overlays}
    </div>
  );
}
