import { useMemo, useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { useObject, useObjectRuns, useTriggerRun, useCheckHistory, useObjectTimeseries } from '@/api/objects';
import { useObjectSchedule } from '@/api/schedules';
import { useRun } from '@/api/runs';
import { SidePanel } from '@/components/ui/SidePanel';
import { Button } from '@/components/ui/Button';
import { StatusPill } from '@/components/ui/StatusPill';
import { StatusDot } from '@/components/ui/StatusDot';
import { CheckStatusCell } from '@/components/ui/StatePill';
import { Spark } from '@/components/ui/Spark';
import { SparkCell } from '@/components/ui/SparkCell';
import { cadenceLabel, nextRunInfo } from '@/lib/schedule';
import { absoluteTime, relativeTime } from '@/lib/time';
import { t } from '@/i18n/de';
import type { CheckResult, MetricSeries, RunListItem } from '@/types';

const STATUS_RANGES = [7, 14, 30] as const;
const MAX_PANEL_CHECKS = 12;
const MAX_FAILURE_LINES = 5;
const MAX_TREND_SERIES = 4;
const EMPTY_CHECK_RESULTS: CheckResult[] = [];

const NEXT_COLOR = {
  ok: 'var(--fg)',
  overdue: 'var(--status-fail)',
  external: 'var(--fg-3)',
  paused: 'var(--status-stale)',
};

function checkRank(check: CheckResult) {
  if (!check.passed && check.severity === 'critical') return 0;
  if (!check.passed) return 1;
  if (check.state !== 'executed') return 2;
  return 3;
}

function orderedChecks(results: CheckResult[]) {
  return [...results].sort((a, b) => checkRank(a) - checkRank(b) || a.name.localeCompare(b.name));
}

function formatValue(value: number | null, raw?: string | null) {
  if (value === null) return raw || '-';
  if (Math.abs(value) >= 100) return String(Math.round(value));
  return Number.isInteger(value) ? String(value) : value.toFixed(2);
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section style={{ marginBottom: 18 }}>
      <h3 style={{
        margin: '0 0 8px',
        fontSize: 11,
        color: 'var(--fg-3)',
        textTransform: 'uppercase',
        letterSpacing: '0.05em',
      }}>
        {title}
      </h3>
      {children}
    </section>
  );
}

function FamilyChip({ family }: { family: string }) {
  return (
    <span style={{
      color: family === 'observability' ? 'var(--obs)' : family === 'quality' ? 'var(--qual)' : 'var(--cont)',
      fontFamily: 'var(--font-mono)',
      fontSize: 10,
      fontWeight: 700,
      textTransform: 'uppercase',
    }}>
      {family.slice(0, 4)}
    </span>
  );
}

function CheckRow({ objectId, check }: { objectId: string; check: CheckResult }) {
  const { data: history = [] } = useCheckHistory(objectId, check.name);
  const series = useMemo(
    () => [...history]
      .reverse()
      .map(h => Number(h.actual_value))
      .filter(n => Number.isFinite(n)),
    [history],
  );

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: 'var(--s2) 0', borderBottom: '1px solid var(--line)' }}>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--fg)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{check.name}</div>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--fg-3)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{check.expect || '-'}</div>
      </div>
      <SparkCell series={series} />
      <CheckStatusCell state={check.state} passed={check.passed} severity={check.severity} />
    </div>
  );
}

function StatusHistory({ runs }: { runs: RunListItem[] }) {
  const [range, setRange] = useState<(typeof STATUS_RANGES)[number]>(14);
  const runsInRange = useMemo(() => {
    const cutoff = Date.now() - range * 86_400_000;
    return runs
      .filter(run => {
        const time = new Date(run.started_at).getTime();
        return Number.isFinite(time) && time >= cutoff;
      })
      .reverse();
  }, [runs, range]);

  const total = runsInRange.length;
  const pass = runsInRange.filter(run => run.overall_status === 'pass').length;

  return (
    <Section title={t.peek.statusHistory}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--s2)', justifyContent: 'space-between', marginBottom: 8 }}>
        <div role="group" aria-label={t.timeseries.rangeLabel} style={{ display: 'inline-flex', border: '1px solid var(--line)', borderRadius: 'var(--r-md)', overflow: 'hidden' }}>
          {STATUS_RANGES.map(days => (
            <button
              key={days}
              type="button"
              onClick={() => setRange(days)}
              aria-pressed={range === days}
              style={{
                padding: '4px 9px',
                fontSize: 11,
                border: 'none',
                cursor: 'pointer',
                background: range === days ? 'var(--cont)' : 'var(--bg-1)',
                color: range === days ? '#fff' : 'var(--fg-3)',
              }}
            >
              {t.peek.rangeDays.replace('{days}', String(days))}
            </button>
          ))}
        </div>
        <span style={{ color: 'var(--fg-3)', fontSize: 11 }}>
          {total
            ? t.peek.statusSummary.replace('{pass}', String(pass)).replace('{total}', String(total))
            : t.peek.statusNoRuns}
        </span>
      </div>
      {total ? (
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: 4,
          minHeight: 22,
          padding: '7px 8px',
          background: 'var(--bg-2)',
          border: '1px solid var(--line-2)',
          borderRadius: 'var(--r-md)',
          overflowX: 'auto',
        }}>
          {runsInRange.map(run => (
            <span key={run.run_id} title={`${run.overall_status} - ${absoluteTime(run.started_at)}`} style={{ display: 'inline-flex' }}>
              <StatusDot status={run.overall_status} size={9} />
            </span>
          ))}
        </div>
      ) : null}
    </Section>
  );
}

function FailureLine({ objectId, check }: { objectId: string; check: CheckResult }) {
  const { data: history = [] } = useCheckHistory(objectId, check.name);
  const text = useMemo(() => {
    let streak = 0;
    while (history[streak]?.passed === 0) streak += 1;
    if (streak > 1) {
      const since = history[streak - 1];
      return `${t.peek.failingSinceRun} ${since.run_id.slice(0, 8)} (${streak} ${t.peek.runsInRow})`;
    }
    return t.peek.failedLatestRun;
  }, [history]);

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--s2)', padding: '6px 0', borderBottom: '1px solid var(--line)' }}>
      <CheckStatusCell state={check.state} passed={check.passed} severity={check.severity} />
      <div style={{ minWidth: 0 }}>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--fg)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{check.name}</div>
        <div style={{ fontSize: 11, color: 'var(--fg-3)' }}>{text}</div>
      </div>
    </div>
  );
}

function RecoveredLine({ check }: { check: CheckResult }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--s2)', padding: '6px 0', borderBottom: '1px solid var(--line)' }}>
      <StatusDot status="pass" size={9} />
      <div style={{ minWidth: 0 }}>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--fg)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{check.name}</div>
        <div style={{ fontSize: 11, color: 'var(--fg-3)' }}>{t.peek.recoveredLastRun}</div>
      </div>
    </div>
  );
}

function FailureHistory({ objectId, results, previousResults }: {
  objectId: string;
  results: CheckResult[];
  previousResults: CheckResult[];
}) {
  const previousByName = useMemo(
    () => new Map(previousResults.map(check => [check.name, check])),
    [previousResults],
  );
  const failed = useMemo(
    () => orderedChecks(results)
      .filter(check => !check.passed && (check.state === 'executed' || check.state === 'error'))
      .slice(0, MAX_FAILURE_LINES),
    [results],
  );
  const recovered = useMemo(
    () => results
      .filter(check => check.passed && previousByName.get(check.name)?.passed === false)
      .sort((a, b) => a.name.localeCompare(b.name))
      .slice(0, 3),
    [results, previousByName],
  );
  const extraFailureCount = Math.max(
    0,
    results.filter(check => !check.passed && (check.state === 'executed' || check.state === 'error')).length - failed.length,
  );

  return (
    <Section title={t.peek.failureHistory}>
      {failed.length === 0 && recovered.length === 0 ? (
        <div style={{ color: 'var(--fg-3)', fontSize: 12 }}>{t.peek.failureNone}</div>
      ) : (
        <>
          {failed.map(check => <FailureLine key={check.name} objectId={objectId} check={check} />)}
          {recovered.map(check => <RecoveredLine key={check.name} check={check} />)}
          {extraFailureCount > 0 ? (
            <div style={{ color: 'var(--fg-3)', fontSize: 11, paddingTop: 6 }}>
              + {extraFailureCount} {t.peek.moreFailures}
            </div>
          ) : null}
        </>
      )}
    </Section>
  );
}

function ScheduleSummary({ objectId }: { objectId: string }) {
  const { data: schedule, isLoading } = useObjectSchedule(objectId);
  if (isLoading) {
    return (
      <Section title={t.peek.scheduleTitle}>
        <div style={{ color: 'var(--fg-3)', fontSize: 12 }}>{t.peek.scheduleLoading}</div>
      </Section>
    );
  }

  if (!schedule) {
    return (
      <Section title={t.peek.scheduleTitle}>
        <div style={{ color: 'var(--fg-3)', fontSize: 12 }}>{t.peek.scheduleManual}</div>
      </Section>
    );
  }

  const next = nextRunInfo(schedule);
  const lastStatus = schedule.last_status === 'started'
    ? 'pass'
    : schedule.last_status?.startsWith('error') ? 'fail' : 'unknown';

  return (
    <Section title={t.peek.scheduleTitle}>
      <div style={{
        display: 'grid',
        gap: 6,
        padding: 'var(--s3)',
        background: 'var(--bg-2)',
        border: '1px solid var(--line-2)',
        borderRadius: 'var(--r-md)',
        fontSize: 12,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 'var(--s2)' }}>
          <span style={{ color: 'var(--fg-3)' }}>{t.schedules.colMode}</span>
          <span style={{ color: 'var(--fg)', fontWeight: 650 }}>{schedule.mode === 'internal' ? t.schedules.modeInternal : t.schedules.modeExternal}</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 'var(--s2)' }}>
          <span style={{ color: 'var(--fg-3)' }}>{t.schedules.colCadence}</span>
          <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--fg-2)' }}>{cadenceLabel(schedule.interval_seconds)}</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 'var(--s2)' }}>
          <span style={{ color: 'var(--fg-3)' }}>{t.schedules.nextRun}</span>
          <span style={{ color: NEXT_COLOR[next.kind], fontFamily: 'var(--font-mono)', fontWeight: 650 }} title={absoluteTime(schedule.next_due_at)}>
            {next.label}
          </span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 'var(--s2)' }}>
          <span style={{ color: 'var(--fg-3)' }}>{t.schedules.lastRun}</span>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 'var(--s1)', color: 'var(--fg-2)' }}>
            <StatusDot status={lastStatus} size={8} />
            <span title={absoluteTime(schedule.last_run_at)}>{schedule.last_run_at ? relativeTime(schedule.last_run_at) : t.schedules.never}</span>
          </span>
        </div>
      </div>
    </Section>
  );
}

function MiniMetricTrend({ series }: { series: MetricSeries }) {
  const values = series.points
    .map(point => point.value)
    .filter((value): value is number => value !== null && Number.isFinite(value));
  const latest = [...series.points].reverse().find(point => point.value !== null || point.raw);
  const anomalyCount = series.points.filter(point => point.anomaly).length;
  const label = t.timeseries.metric[series.metric] ?? series.metric;
  const color = series.metric === 'freshness'
    ? 'var(--obs)'
    : series.metric === 'volume' ? 'var(--cont)' : 'var(--fg-2)';

  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: 'minmax(0, 1fr) 110px',
      alignItems: 'center',
      gap: 'var(--s3)',
      padding: '8px 0',
      borderBottom: '1px solid var(--line)',
    }}>
      <div style={{ minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--s2)' }}>
          <span style={{ width: 8, height: 8, borderRadius: 2, background: color, flexShrink: 0 }} />
          <span style={{ fontSize: 11, fontWeight: 650, color: 'var(--fg-2)' }}>{label}</span>
          {anomalyCount > 0 ? <span style={{ color: 'var(--status-crit)', fontSize: 10 }}>{anomalyCount} {t.timeseries.anomalies}</span> : null}
        </div>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--fg-3)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', marginTop: 3 }}>
          {series.check_name}
        </div>
        <div style={{ fontSize: 11, color: 'var(--fg-3)', marginTop: 3 }}>
          {t.peek.latestValue}: <span style={{ color: 'var(--fg)', fontFamily: 'var(--font-mono)' }}>{latest ? formatValue(latest.value, latest.raw) : '-'}</span>
        </div>
      </div>
      {values.length > 1 ? <Spark data={values.slice(-30)} width={104} height={34} color={color} /> : <span style={{ color: 'var(--fg-3)', fontSize: 11 }}>-</span>}
    </div>
  );
}

function TrendSummary({ objectId }: { objectId: string }) {
  const { data, isLoading, isError } = useObjectTimeseries(objectId, true);
  const series = useMemo(
    () => (data?.series ?? [])
      .filter(item => item.metric === 'freshness' || item.metric === 'volume')
      .slice(0, MAX_TREND_SERIES),
    [data],
  );

  return (
    <Section title={t.peek.trendTitle}>
      {isLoading ? (
        <div style={{ color: 'var(--fg-3)', fontSize: 12 }}>{t.peek.trendLoading}</div>
      ) : isError ? (
        <div style={{ color: 'var(--status-fail)', fontSize: 12 }}>{t.peek.trendError}</div>
      ) : series.length === 0 ? (
        <div style={{ color: 'var(--fg-3)', fontSize: 12 }}>{t.peek.trendEmpty}</div>
      ) : (
        <div style={{ background: 'var(--bg-2)', border: '1px solid var(--line-2)', borderRadius: 'var(--r-md)', padding: '2px var(--s3)' }}>
          {series.map(item => <MiniMetricTrend key={item.check_name} series={item} />)}
        </div>
      )}
    </Section>
  );
}

export function ObjectPeek({ objectId, onClose }: { objectId: string; onClose: () => void }) {
  const { data: obj } = useObject(objectId);
  const { data: runs = [] } = useObjectRuns(objectId);
  const latest = runs[0];
  const previous = runs[1];
  const { data: runDetail } = useRun(latest?.run_id ?? '');
  const { data: previousRunDetail } = useRun(previous?.run_id ?? '');
  const trigger = useTriggerRun(objectId);
  const results = runDetail?.results ?? EMPTY_CHECK_RESULTS;
  const previousResults = previousRunDetail?.results ?? EMPTY_CHECK_RESULTS;
  const isRunning = latest?.run_state === 'running' || runDetail?.run_state === 'running';
  const visibleChecks = useMemo(() => orderedChecks(results).slice(0, MAX_PANEL_CHECKS), [results]);
  const hiddenCheckCount = Math.max(0, results.length - visibleChecks.length);

  return (
    <SidePanel
      width={520}
      title={
        <span style={{ display: 'flex', alignItems: 'center', gap: 'var(--s2)', minWidth: 0 }}>
          <span style={{ color: 'var(--fg-3)', fontSize: 12, fontWeight: 600 }}>{t.peek.operationsTitle}</span>
          <span style={{ fontFamily: 'var(--font-mono)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{obj?.name ?? objectId}</span>
          {obj && <FamilyChip family={obj.family} />}
          {obj && <StatusPill status={obj.status ?? 'unknown'} size="sm" />}
        </span>
      }
      onClose={onClose}
      footer={
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
          <Button
            variant="primary"
            size="sm"
            onClick={() => trigger.mutate({})}
            disabled={trigger.isPending || isRunning}
          >
            {trigger.isPending || isRunning ? t.peek.running : t.peek.runChecks}
          </Button>
          <Link to={`/objects/${encodeURIComponent(objectId)}`} onClick={onClose} style={{ color: 'var(--cont)', fontSize: 13 }}>{t.peek.openFull}</Link>
        </div>
      }
    >
      {obj && (
        <div style={{ fontSize: 12, color: 'var(--fg-3)', marginBottom: 16 }}>
          {obj.space} / {obj.layer} / {t.peek.contract} {obj.contract_status || '-'}
        </div>
      )}

      <StatusHistory runs={runs} />
      <FailureHistory objectId={objectId} results={results} previousResults={previousResults} />
      <ScheduleSummary objectId={objectId} />
      <TrendSummary objectId={objectId} />

      <Section title={t.peek.checksLatestRun}>
        {results.length === 0 ? (
          <div style={{ color: 'var(--fg-3)', fontSize: 13 }}>{t.peek.noChecks}</div>
        ) : (
          <>
            {visibleChecks.map(check => <CheckRow key={check.name} objectId={objectId} check={check} />)}
            {hiddenCheckCount > 0 ? (
              <div style={{ color: 'var(--fg-3)', fontSize: 11, paddingTop: 6 }}>
                + {hiddenCheckCount} {t.peek.moreChecks}
              </div>
            ) : null}
          </>
        )}
      </Section>
    </SidePanel>
  );
}
