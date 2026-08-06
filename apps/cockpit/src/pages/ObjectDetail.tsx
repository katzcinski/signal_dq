import { useEffect, useRef, useState } from 'react';
import { useParams, useSearchParams, useNavigate, Link } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { useObject, useObjectRuns, useTriggerRun, useCheckHistory } from '@/api/objects';
import { useMonitoringConfig, useMonitoringShares, useRequestMonitoring } from '@/api/monitoring';
import { useRun } from '@/api/runs';
import { useContract, useContractVersionDiff, useSeedContract } from '@/api/contracts';
import { StatusPill } from '@/components/ui/StatusPill';
import { CheckStatusCell } from '@/components/ui/StatePill';
import { ErrorBanner } from '@/components/ui/ErrorBanner';
import { LiveRunPanel } from '@/components/LiveRunPanel';
import { RunTriggerDialog } from '@/components/RunTriggerDialog';
import { BadgeEmbed } from '@/components/BadgeEmbed';
import { MinedProposalsCallout } from '@/components/MinedProposalsCallout';
import { ObservabilityTimeseries } from '@/components/ObservabilityTimeseries';
import { ObjectProfilePanel } from '@/components/ObjectProfilePanel';
import { ObjectDiffPanel } from '@/components/ObjectDiffPanel';
import { SchedulePanel } from '@/components/SchedulePanel';
import { ColumnLineagePanel } from '@/components/lineage/ColumnLineagePanel';
import { Spark } from '@/components/ui/Spark';
import { Table, type ColDef } from '@/components/ui/Table';
import { Breadcrumbs } from '@/components/ui/Breadcrumbs';
import { NotFoundState } from '@/components/ui/NotFoundState';
import { ObjectAttentionBand } from '@/components/object-detail/ObjectAttentionBand';
import { ObjectHero } from '@/components/object-detail/ObjectHero';
import { MiniLineageSection } from '@/components/object-detail/MiniLineageSection';
import { ContractView } from '@/components/object-detail/ContractView';
import { ContractVersionDiffView } from '@/components/object-detail/ContractVersionDiffView';
import { ObjectDetailNavigation } from '@/components/object-detail/ObjectDetailNavigation';
import { ObjectDetailSectionSkeleton, ObjectHeroSkeleton } from '@/components/object-detail/ObjectDetailSkeletons';
import { useRoleStore, canProfileObject, canWriteContract } from '@/store/role';
import { t } from '@/i18n/de';
import type { CheckResult, RunListItem } from '@/types';
import {
  OBJECT_DETAIL_TAB_TARGETS,
  resolveObjectDetailTabTarget,
  type ObjectDetailGroup,
  type ObjectDetailTab as Tab,
} from './objectDetailTabs';

// ---------------------------------------------------------------------------
// Sparkline over the numeric actual_value history of one check (newest-first
// API order is reversed into chronological order). Non-numeric series → dash.
// ---------------------------------------------------------------------------
function HistorySpark({ objectId, checkName, enabled }: {
  objectId: string;
  checkName: string;
  enabled: boolean;
}) {
  const { data } = useCheckHistory(objectId, checkName, enabled);
  if (!data) return <span style={{ color: 'var(--fg-3)' }}>—</span>;
  const values = [...data]
    .reverse()
    .map(p => Number(p.actual_value))
    .filter(v => Number.isFinite(v));
  if (values.length < 2) return <span style={{ color: 'var(--fg-3)' }}>—</span>;
  return <Spark data={values} color="var(--cont)" />;
}

export default function ObjectDetail() {
  const { id = '' } = useParams();
  const [sp, setSp] = useSearchParams();
  const tabTarget = resolveObjectDetailTabTarget(sp.get('tab'));
  const activeGroup = tabTarget.group;
  const tab = tabTarget.anchor;
  // Tab-Wechsel spiegelt den Rest der Query (kein Wipe künftiger Parameter) und
  // ersetzt den History-Eintrag statt zu pushen — konsistent mit allen anderen
  // Tab-/Filter-Views (useSearchParamState), damit der Zurück-Button nicht durch
  // jeden angetippten Tab läuft.
  const setTab = (next: Tab) => setSp(prev => {
    const params = new URLSearchParams(prev);
    params.set('tab', OBJECT_DETAIL_TAB_TARGETS[next].anchor);
    return params;
  }, { replace: true });
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const role = useRoleStore(s => s.role);

  // All hooks run unconditionally — no early return may come before them.
  const { data: obj, isLoading, isError, refetch } = useObject(id);
  const { data: runs = [] } = useObjectRuns(id);
  const { data: contract } = useContract(id);
  const { data: contractVersionDiff } = useContractVersionDiff(id, !!contract);
  const trigger = useTriggerRun(id);
  const seedContract = useSeedContract();
  const { data: monCfg } = useMonitoringConfig();
  const { data: monShares = [] } = useMonitoringShares();
  const requestMonitoring = useRequestMonitoring();
  const monEntry = monShares.find(s => s.object_id === id);

  const latestRun: RunListItem | undefined = runs[0];
  const { data: latestRunDetail } = useRun(latestRun?.run_id ?? '');
  const results: CheckResult[] = latestRunDetail?.results ?? [];
  const failedChecks = results.filter(result => !result.passed).length;

  const isRunning = latestRun?.run_state === 'running' || latestRunDetail?.run_state === 'running';
  const canProfile = canProfileObject(role);

  // When the in-flight run completes, refresh object status + run list.
  const runState = latestRunDetail?.run_state;
  const prevRunState = useRef(runState);
  useEffect(() => {
    if (prevRunState.current === 'running' && runState && runState !== 'running') {
      qc.invalidateQueries({ queryKey: ['objects', id] });
      qc.invalidateQueries({ queryKey: ['objects', id, 'runs'] });
    }
    prevRunState.current = runState;
  }, [runState, id, qc]);

  if (isLoading) {
    return (
      <div className="page-full">
        <ObjectHeroSkeleton />
        <ObjectDetailNavigation
          activeGroup={activeGroup}
          activeTab={tab}
          onSelectTab={setTab}
        />
        <ObjectDetailSectionSkeleton tab={tab} />
      </div>
    );
  }
  if (isError) return <div className="page-full"><ErrorBanner onRetry={() => refetch()} /></div>;
  if (!obj) {
    return (
      <div className="page-full">
        <Breadcrumbs items={[
          { label: t.breadcrumb.home, to: '/' },
          { label: t.breadcrumb.objects, to: '/objects' },
          { label: id },
        ]} />
        <NotFoundState
          title={t.objectDetail.notFound}
          message={t.notFound.objectMessage}
          actions={[
            { label: t.notFound.objects, to: '/objects', primary: true },
            { label: t.notFound.home, to: '/' },
          ]}
        />
      </div>
    );
  }

  const canCreateChecks = canWriteContract(role, obj.owned_by);
  const openChecksWorkbench = () => {
    const target = `/contracts?product=${encodeURIComponent(id)}`;
    if (contract) {
      navigate(target);
      return;
    }
    seedContract.mutate(id, { onSuccess: () => navigate(target) });
  };

  const isActiveSection = (group: ObjectDetailGroup, anchor: Tab) => (
    activeGroup === group && tab === anchor
  );

  const runColumns: ColDef<RunListItem>[] = [
    { key: 'run_id', header: t.objectDetail.colRunId, mono: true, render: r => (
      <Link to={`/runs/${r.run_id}`} style={{ color: 'var(--cont)', fontFamily: 'var(--font-mono)', fontSize: 11 }}>
        {r.run_id.slice(0, 12)}…
      </Link>
    )},
    { key: 'status', header: t.objectDetail.colStatus, render: r => <StatusPill status={r.overall_status} size="sm" /> },
    { key: 'total', header: t.objectDetail.colChecks, render: r => `${r.passed}/${r.total}` },
    { key: 'started_at', header: t.objectDetail.colStarted, mono: true, render: r => new Date(r.started_at).toLocaleString() },
    { key: 'triggered_by', header: t.objectDetail.colTrigger, render: r => <span style={{ color: 'var(--fg-3)', fontSize: 11 }}>{r.triggered_by}</span> },
  ];

  // E: trend sparkline — fetch history for the first ~20 checks of the latest run.
  const sparkBudget = new Set(results.slice(0, 20).map(c => c.name));

  const checkColumns: ColDef<CheckResult>[] = [
    { key: 'name', header: t.objectDetail.colCheck, mono: true, render: c => c.name },
    { key: 'status', header: t.objectDetail.colStatus, render: c => <CheckStatusCell state={c.state} passed={c.passed} severity={c.severity} /> },
    { key: 'expect', header: t.objectDetail.colExpect, mono: true, render: c => c.expect },
    { key: 'actual', header: t.objectDetail.colActual, mono: true, render: c => c.actual_value ?? '—' },
    {
      key: 'trend', header: t.objectDetail.colTrend, width: 80,
      render: c => <HistorySpark objectId={id} checkName={c.name} enabled={sparkBudget.has(c.name)} />,
    },
    { key: 'ms', header: t.objectDetail.colMs, mono: true, render: c => String(c.duration_ms) },
  ];

  return (
    <div className="page-full">
      <Breadcrumbs items={[
        { label: t.breadcrumb.home, to: '/' },
        { label: t.breadcrumb.objects, to: '/objects' },
        { label: obj.name },
      ]} />
      <ObjectHero
        object={obj}
        contract={contract}
        latestRun={latestRun}
        results={results}
        monitoringEnabled={!!monCfg?.enabled}
        monitoringEntry={monEntry}
        monitoringSpace={monCfg?.monitoring_space}
        monitoringPending={requestMonitoring.isPending}
        canProfile={canProfile}
        canCreateChecks={canCreateChecks}
        checksActionPending={seedContract.isPending}
        runPending={trigger.isPending || isRunning}
        onBack={() => navigate('/objects')}
        onRequestMonitoring={() => requestMonitoring.mutate(id)}
        onOpenProfile={() => setProfileOpen(true)}
        onOpenChecksWorkbench={openChecksWorkbench}
        onStartRun={() => setDialogOpen(true)}
      />

      <ObjectAttentionBand
        failedChecks={failedChecks}
        hasContract={!!contract}
        monitoringEnabled={!!monCfg?.enabled}
        monitoringEntry={monEntry}
        hasBreakingContractDiff={contractVersionDiff?.breaking === true}
      />

      {dialogOpen && (
        <RunTriggerDialog
          pending={trigger.isPending}
          onClose={() => setDialogOpen(false)}
          onStart={body => trigger.mutate(body, { onSettled: () => setDialogOpen(false) })}
        />
      )}

      {profileOpen && (
        <ObjectProfilePanel objectId={obj.id} onClose={() => setProfileOpen(false)} />
      )}

      <ObjectDetailNavigation
        activeGroup={activeGroup}
        activeTab={tab}
        onSelectTab={setTab}
      />

      {isActiveSection('quality', 'checks') && (
        <div className="object-detail-section">
          {results.length === 0 && <MinedProposalsCallout productId={obj.id} />}
          <div style={{ background: 'var(--bg-1)', border: '1px solid var(--line)', borderRadius: 'var(--r-lg)', overflow: 'hidden' }}>
            <Table columns={checkColumns} rows={results} rowKey={c => c.name} empty={t.objectDetail.noResults} />
          </div>
        </div>
      )}

      {isActiveSection('history-ops', 'runs') && (
        <div className="object-detail-section">
          {runs.length >= 2 && (
            <div style={{ marginBottom: 12, textAlign: 'right' }}>
              <Link
                to={`/runs/compare?base=${encodeURIComponent(runs[1].run_id)}&head=${encodeURIComponent(runs[0].run_id)}`}
                style={{ color: 'var(--cont)', fontSize: 12 }}
              >
                {t.compare.compareLatest} →
              </Link>
            </div>
          )}
          <div style={{ background: 'var(--bg-1)', border: '1px solid var(--line)', borderRadius: 'var(--r-lg)', overflow: 'hidden' }}>
            <Table columns={runColumns} rows={runs} rowKey={r => r.run_id} empty={t.objectDetail.noRuns} />
          </div>
        </div>
      )}

      {isActiveSection('history-ops', 'timeseries') && (
        <div className="object-detail-section">
          <ObservabilityTimeseries objectId={obj.id} enabled={tab === 'timeseries'} />
        </div>
      )}

      {isActiveSection('structure-interface', 'contract') && (
        <div className="object-detail-section">
          {!contract && <MinedProposalsCallout productId={obj.id} />}
          <div style={{ background: 'var(--bg-1)', border: '1px solid var(--line)', borderRadius: 'var(--r-lg)', padding: 'var(--s5)' }}>
            {contract ? (
              <ContractView contract={contract} />
            ) : (
              <p style={{ color: 'var(--fg-3)' }}>
                {t.objectDetail.noContractPrefix}{' '}
                <Link to="/contracts" style={{ color: 'var(--cont)' }}>{t.objectDetail.noContractLink}</Link>{' '}
                {t.objectDetail.noContractSuffix}
              </p>
            )}
          </div>
          {contract && <ContractVersionDiffView product={obj.id} enabled={tab === 'contract'} />}
          <BadgeEmbed product={obj.id} />
        </div>
      )}

      {isActiveSection('structure-interface', 'lineage') && (
        <div className="object-detail-section">
          <div style={{ background: 'var(--bg-1)', border: '1px solid var(--line)', borderRadius: 'var(--r-lg)', padding: 'var(--s6)' }}>
            <MiniLineageSection focusId={obj.id} />
          </div>
          <div style={{ background: 'var(--bg-1)', border: '1px solid var(--line)', borderRadius: 'var(--r-lg)', padding: 'var(--s6)', marginTop: 'var(--s4)' }}>
            <ColumnLineagePanel objectId={obj.id} />
          </div>
        </div>
      )}

      {isActiveSection('history-ops', 'schedule') && (
        <div className="object-detail-section">
          <SchedulePanel objectId={obj.id} />
        </div>
      )}

      {isActiveSection('history-ops', 'diff') && (
        <div className="object-detail-section">
          <ObjectDiffPanel objectId={obj.id} />
        </div>
      )}

      {latestRun && (
        <LiveRunPanel runId={latestRun.run_id} dataset={latestRun.dataset} running={isRunning} />
      )}
    </div>
  );
}
