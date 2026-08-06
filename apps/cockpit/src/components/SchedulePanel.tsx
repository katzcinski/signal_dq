import { useEffect, useState } from 'react';
import { useObjectSchedule, useUpsertObjectSchedule, useDeleteObjectSchedule } from '@/api/schedules';
import { useEnvironments } from '@/api/objects';
import { StatusDot } from '@/components/ui/StatusDot';
import { ReadOnlyBanner } from '@/components/ui/ReadOnlyBanner';
import { ScheduleSkeleton } from '@/components/object-detail/ObjectDetailSkeletons';
import { relativeTime, absoluteTime } from '@/lib/time';
import { cadenceLabel, nextRunInfo } from '@/lib/schedule';
import { t } from '@/i18n/de';
import { useRoleStore, canManageSchedules } from '@/store/role';
import type { ScheduleMode } from '@/types';

type Choice = 'manual' | ScheduleMode;

const INTERVALS = [900, 1800, 3600, 21600, 86400];
const EXEC_MODES = ['auto', 'batch', 'isolated'];

const NEXT_COLOR: Record<string, string> = {
  ok: 'var(--fg)', overdue: 'var(--status-fail)',
  external: 'var(--fg-3)', paused: 'var(--status-stale)',
};

function ModeCard({ choice, active, onClick, disabled }: {
  choice: Choice; active: boolean; onClick: () => void; disabled: boolean;
}) {
  const meta = {
    manual:   { c: 'var(--status-stale)', title: t.schedules.modeManual,        desc: t.schedules.modeManualDesc },
    internal: { c: 'var(--qual)',         title: t.schedules.modeInternalTitle,  desc: t.schedules.modeInternalDesc },
    external: { c: 'var(--obs)',          title: t.schedules.modeExternalTitle,  desc: t.schedules.modeExternalDesc },
    on_load:  { c: 'var(--obs)',          title: t.schedules.modeOnLoadTitle,    desc: t.schedules.modeOnLoadDesc },
  }[choice];
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      aria-pressed={active}
      style={{
        flex: 1, textAlign: 'left', cursor: disabled ? 'not-allowed' : 'pointer',
        background: active ? 'var(--bg-2)' : 'transparent',
        border: `1px solid ${active ? meta.c : 'var(--line)'}`,
        boxShadow: active ? `inset 2px 0 0 ${meta.c}` : undefined,
        borderRadius: 'var(--r-lg)', padding: '12px 14px', opacity: disabled ? 0.5 : 1,
        transition: 'background var(--t), border-color var(--t)',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--s2)', marginBottom: 4 }}>
        <span style={{ width: 8, height: 8, borderRadius: '50%', background: meta.c }} />
        <span style={{ fontSize: 13, fontWeight: 650, color: 'var(--fg)' }}>{meta.title}</span>
      </div>
      <div style={{ fontSize: 11.5, color: 'var(--fg-3)', lineHeight: 1.4 }}>{meta.desc}</div>
    </button>
  );
}

export function SchedulePanel({ objectId }: { objectId: string }) {
  const role = useRoleStore(s => s.role);
  const canEdit = canManageSchedules(role);
  const { data: schedule, isLoading } = useObjectSchedule(objectId);
  const { data: envData } = useEnvironments();
  const upsert = useUpsertObjectSchedule(objectId);
  const remove = useDeleteObjectSchedule(objectId);

  // Local edit state, seeded from the server record once it loads.
  const [choice, setChoice] = useState<Choice>('manual');
  const [interval, setInterval] = useState(3600);
  const [environment, setEnvironment] = useState('');
  const [execMode, setExecMode] = useState('auto');
  const [enabled, setEnabled] = useState(true);

  // Seed local edit state from the server record. Depend on the server's actual
  // values (not the query object's identity) so a background refetch returning an
  // equal-but-new object never clobbers in-progress edits.
  useEffect(() => {
    if (schedule) {
      setChoice(schedule.mode);
      setInterval(schedule.interval_seconds || 3600);
      setEnvironment(schedule.environment || '');
      setExecMode(schedule.execution_mode || 'auto');
      setEnabled(schedule.enabled);
    } else {
      setChoice('manual');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    schedule?.schedule_id, schedule?.mode, schedule?.interval_seconds,
    schedule?.environment, schedule?.execution_mode, schedule?.enabled,
  ]);

  if (isLoading) return <ScheduleSkeleton />;

  const next = schedule ? nextRunInfo(schedule) : null;
  const intervalTooLow = choice === 'internal' && interval < 60;

  const onSave = () => {
    if (choice === 'manual') { remove.mutate(); return; }
    upsert.mutate({
      mode: choice,
      interval_seconds: choice === 'internal' ? interval : 0,
      environment: environment || undefined,
      execution_mode: execMode,
      enabled,
    });
  };

  const labelStyle: React.CSSProperties = {
    display: 'flex', flexDirection: 'column', gap: 5, fontSize: 11,
    color: 'var(--fg-3)', textTransform: 'uppercase', letterSpacing: '0.05em',
  };
  const fieldStyle: React.CSSProperties = {
    background: 'var(--bg-2)', border: '1px solid var(--line-2)',
    color: 'var(--fg)', borderRadius: 'var(--r-md)', padding: '7px 10px', fontSize: 13,
  };

  return (
    <div style={{ background: 'var(--bg-1)', border: '1px solid var(--line)', borderRadius: 'var(--r-lg)', padding: 'var(--s5)', maxWidth: 720 }}>
      {!canEdit && <ReadOnlyBanner />}

      {/* status strip when a schedule exists */}
      {schedule && next && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: 'var(--s4)', marginBottom: 18,
          padding: '10px 14px', background: 'var(--bg-2)', borderRadius: 'var(--r-lg)',
          border: '1px solid var(--line)',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
            <StatusDot status={schedule.last_status === 'started' ? 'pass' : (schedule.last_status?.startsWith('error') ? 'fail' : 'unknown')} size={9} />
            <span style={{ fontSize: 12, color: 'var(--fg-2)' }}>
              {t.schedules.lastRun}: {schedule.last_run_at ? relativeTime(schedule.last_run_at) : t.schedules.never}
            </span>
          </div>
          <span style={{ color: 'var(--line-2)' }}>·</span>
          <div style={{ fontSize: 12, color: 'var(--fg-2)' }}>
            {t.schedules.nextRun}:{' '}
            <span style={{ color: NEXT_COLOR[next.kind], fontWeight: 600, fontFamily: 'var(--font-mono)' }} title={schedule.next_due_at ? absoluteTime(schedule.next_due_at) : undefined}>
              {next.label}
            </span>
          </div>
        </div>
      )}

      {/* mode chooser */}
      <div style={{ display: 'flex', gap: 10, marginBottom: 18 }}>
        {(['manual', 'internal', 'external', 'on_load'] as Choice[]).map(c => (
          <ModeCard key={c} choice={c} active={choice === c} disabled={!canEdit} onClick={() => setChoice(c)} />
        ))}
      </div>

      {/* internal: cadence + connection */}
      {choice === 'internal' && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14, marginBottom: 18 }}>
          <label style={labelStyle}>
            {t.schedules.interval}
            <select value={interval} onChange={e => setInterval(Number(e.target.value))} disabled={!canEdit} style={fieldStyle}>
              {INTERVALS.map(s => <option key={s} value={s}>{cadenceLabel(s)}</option>)}
            </select>
          </label>
          <label style={labelStyle}>
            {t.schedules.environment}
            <select value={environment} onChange={e => setEnvironment(e.target.value)} disabled={!canEdit} style={fieldStyle}>
              <option value="">{t.schedules.localMock}</option>
              {(envData?.environments ?? []).map(env => (
                <option key={env.name} value={env.name}>{env.name} ({env.schema})</option>
              ))}
            </select>
          </label>
          <label style={labelStyle}>
            {t.schedules.executionMode}
            <select value={execMode} onChange={e => setExecMode(e.target.value)} disabled={!canEdit} style={fieldStyle}>
              {EXEC_MODES.map(m => <option key={m} value={m}>{m}</option>)}
            </select>
          </label>
          <label style={{ ...labelStyle, justifyContent: 'flex-end' }}>
            {t.schedules.enabled}
            <button
              role="switch" aria-checked={enabled} disabled={!canEdit}
              onClick={() => setEnabled(v => !v)}
              style={{
                width: 44, height: 24, borderRadius: 'var(--r-full)', position: 'relative',
                border: '1px solid var(--line-2)', cursor: canEdit ? 'pointer' : 'not-allowed',
                background: enabled ? 'var(--qual)' : 'var(--bg-3)', transition: 'background var(--t)',
              }}
            >
              <span style={{
                position: 'absolute', top: 2, left: enabled ? 22 : 2, width: 18, height: 18,
                borderRadius: '50%', background: '#0B0D12', transition: 'left var(--t)',
              }} />
            </button>
          </label>
        </div>
      )}

      {choice === 'external' && (
        <div style={{
          marginBottom: 18, padding: '12px 14px', borderRadius: 'var(--r-lg)',
          background: 'color-mix(in srgb, var(--obs) 8%, transparent)',
          border: '1px solid color-mix(in srgb, var(--obs) 40%, var(--line))',
          fontSize: 12.5, color: 'var(--fg-2)', lineHeight: 1.5,
        }}>
          {t.schedules.externalNote}
        </div>
      )}

      {choice === 'manual' && (
        <div style={{ marginBottom: 18, fontSize: 12.5, color: 'var(--fg-3)' }}>
          {t.schedules.panelManualHint}
        </div>
      )}

      {intervalTooLow && (
        <div style={{ marginBottom: 12, fontSize: 12, color: 'var(--status-fail)' }}>{t.schedules.minIntervalHint}</div>
      )}

      {/* actions */}
      <div style={{ display: 'flex', gap: 'var(--s2)' }}>
        <button
          onClick={onSave}
          disabled={!canEdit || upsert.isPending || remove.isPending || intervalTooLow}
          style={{
            background: 'var(--cont)', color: '#fff', border: 'none', borderRadius: 'var(--r-md)',
            padding: 'var(--s2) var(--s4)', fontSize: 13, cursor: canEdit ? 'pointer' : 'not-allowed',
            opacity: canEdit && !intervalTooLow ? 1 : 0.5,
          }}
        >
          {choice === 'manual' ? t.schedules.remove : t.schedules.save}
        </button>
      </div>
    </div>
  );
}
