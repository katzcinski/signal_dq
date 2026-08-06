import { useMemo, useState, type CSSProperties } from 'react';
import { t } from '@/i18n/de';
import { Button } from '@/components/ui/Button';
import type { ExtractOperationResult, ExtractStatus } from '@/api/extract';
import type { OperationProgressLine, OperationStatus } from '@/types';

export const EXTRACT_PROGRESS_META_PREFIX = '@@progress ';

type ProgressMode = 'overview' | 'cli';
type ExtractPhase =
  | 'source'
  | 'load_objects'
  | 'build_inventory'
  | 'build_lineage'
  | 'write_snapshots'
  | 'schema_drift'
  | 'complete';

interface ExtractProgressMeta {
  kind?: string;
  phase?: ExtractPhase;
  status?: string;
  source?: string;
  source_space?: string;
  object_type?: string;
  stage?: string;
  current?: number;
  total?: number;
  name?: string;
  inventory_items?: number;
  lineage_nodes?: number;
  lineage_edges?: number;
  column_edges?: number;
  checked?: number;
  drifted?: number;
  breaking?: number;
  error?: string;
}

interface ExtractProgressOverview {
  activePhase: ExtractPhase | null;
  activePhaseLabel: string;
  stepIndex: number;
  currentObject: string | null;
  currentObjectType: string | null;
  source: string | null;
  current: number | null;
  total: number | null;
  summary: string | null;
  driftSummary: ExtractProgressMeta | null;
}

const shell: CSSProperties = {
  border: '1px solid var(--line)',
  borderRadius: 'var(--r-lg)',
  background:
    'linear-gradient(160deg, color-mix(in srgb, var(--bg-2) 88%, white 6%) 0%, var(--bg-1) 100%)',
  padding: 'var(--s4)',
  display: 'flex',
  flexDirection: 'column',
  gap: 'var(--s3)',
};

const subtle: CSSProperties = { color: 'var(--fg-3)', fontSize: 12 };
const mono: CSSProperties = { fontFamily: 'var(--font-mono)', fontSize: 11 };

const PHASE_LABELS: Record<ExtractPhase, string> = {
  source: t.inventoryAdmin.stepSource,
  load_objects: t.inventoryAdmin.stepObjects,
  build_inventory: t.inventoryAdmin.stepObjects,
  build_lineage: t.inventoryAdmin.stepGraph,
  write_snapshots: t.inventoryAdmin.stepSnapshot,
  schema_drift: t.inventoryAdmin.stepDrift,
  complete: t.inventoryAdmin.stepSnapshot,
};

function phaseToStepIndex(phase: ExtractPhase | null): number {
  switch (phase) {
    case 'source':
      return 0;
    case 'load_objects':
    case 'build_inventory':
      return 1;
    case 'build_lineage':
      return 2;
    case 'write_snapshots':
      return 3;
    case 'schema_drift':
    case 'complete':
      return 4;
    default:
      return 0;
  }
}

function currentPhaseFromStatus(status?: ExtractStatus['status'], currentStep?: string): ExtractPhase | null {
  if (status === 'skipped' || status === 'succeeded' || status === 'failed') return 'complete';
  switch (currentStep) {
    case 'starting':
      return 'source';
    case 'extracting_objects':
      return 'load_objects';
    case 'schema_drift':
      return 'schema_drift';
    case 'published_snapshot':
      return 'complete';
    default:
      return null;
  }
}

function parseProgressMeta(line: OperationProgressLine): ExtractProgressMeta | null {
  if (!line.line.startsWith(EXTRACT_PROGRESS_META_PREFIX)) return null;
  try {
    const parsed = JSON.parse(line.line.slice(EXTRACT_PROGRESS_META_PREFIX.length)) as ExtractProgressMeta;
    return parsed.kind === 'extract' ? parsed : null;
  } catch {
    return null;
  }
}

export function extractVisibleProgressLines(lines: OperationProgressLine[] = []): OperationProgressLine[] {
  return lines.filter(line => !line.line.startsWith(EXTRACT_PROGRESS_META_PREFIX));
}

export function buildExtractProgressOverview(
  lines: OperationProgressLine[] = [],
  status?: ExtractStatus | null,
): ExtractProgressOverview {
  const metas = lines.map(parseProgressMeta).filter((meta): meta is ExtractProgressMeta => meta !== null);
  const activePhaseMeta = [...metas].reverse().find(meta => meta.phase);
  const objectMeta = [...metas].reverse().find(meta => (meta.current ?? 0) > 0 && (meta.total ?? 0) > 0);
  const latestWithName = [...metas].reverse().find(meta => !!meta.name);
  const summaryMeta = [...metas].reverse().find(meta => meta.phase === 'complete');
  const driftMeta = [...metas].reverse().find(meta => meta.phase === 'schema_drift' && meta.status === 'finished') ?? null;
  const phase = activePhaseMeta?.phase ?? currentPhaseFromStatus(status?.status, status?.current_step);

  return {
    activePhase: phase,
    activePhaseLabel: phase ? PHASE_LABELS[phase] : t.inventoryAdmin.progressWaiting,
    stepIndex: phaseToStepIndex(phase),
    currentObject: latestWithName?.name ?? null,
    currentObjectType: latestWithName?.object_type ?? null,
    source: activePhaseMeta?.source ?? status?.source ?? null,
    current: objectMeta?.current ?? null,
    total: objectMeta?.total ?? null,
    summary: summaryMeta
      ? [
          summaryMeta.inventory_items,
          summaryMeta.lineage_nodes,
          summaryMeta.lineage_edges,
          summaryMeta.column_edges,
        ]
          .some(item => item != null)
        ? `${summaryMeta.inventory_items ?? 0} / ${summaryMeta.lineage_nodes ?? 0} / ${summaryMeta.lineage_edges ?? 0} / ${summaryMeta.column_edges ?? 0}`
        : null
      : null,
    driftSummary: driftMeta,
  };
}

function tone(operation?: OperationStatus['state'], extractStatus?: ExtractStatus['status']) {
  if (operation === 'error' || extractStatus === 'failed') return 'var(--status-fail)';
  if (extractStatus === 'skipped') return 'var(--status-warn)';
  if (operation === 'finished' || extractStatus === 'succeeded') return 'var(--status-pass)';
  return 'var(--cont)';
}

interface Props {
  operation?: OperationStatus<ExtractOperationResult> | null;
  status?: ExtractStatus | null;
}

export function InventoryExtractProgress({ operation, status }: Props) {
  const [mode, setMode] = useState<ProgressMode>('overview');
  const visibleLines = useMemo(() => extractVisibleProgressLines(operation?.progress ?? []), [operation?.progress]);
  const overview = useMemo(
    () => buildExtractProgressOverview(operation?.progress ?? [], status),
    [operation?.progress, status],
  );
  const snapshot = operation?.result ?? status ?? null;
  const color = tone(operation?.state, snapshot?.status);
  const running = operation?.state === 'running' || snapshot?.status === 'running' || snapshot?.status === 'queued';
  const progressPct = overview.current && overview.total ? Math.max(6, Math.round((overview.current / overview.total) * 100)) : 0;
  const summaryCounts = snapshot?.counts;

  const steps = [
    t.inventoryAdmin.stepSource,
    t.inventoryAdmin.stepObjects,
    t.inventoryAdmin.stepGraph,
    t.inventoryAdmin.stepSnapshot,
    t.inventoryAdmin.stepDrift,
  ];

  return (
    <div style={shell}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 'var(--s3)', flexWrap: 'wrap', alignItems: 'center' }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--s2)', flexWrap: 'wrap' }}>
            <span style={{ width: 10, height: 10, borderRadius: '50%', background: color, flexShrink: 0 }} />
            <strong style={{ color: 'var(--fg)', fontSize: 14 }}>{t.inventoryAdmin.liveStatus}</strong>
            <span style={{
              color,
              border: `1px solid ${color}`,
              borderRadius: 'var(--r-full)',
              padding: '2px 8px',
              fontSize: 11,
              fontWeight: 700,
              textTransform: 'uppercase',
            }}>
              {snapshot?.status ?? operation?.state ?? t.inventoryAdmin.noValue}
            </span>
          </div>
          <div style={subtle}>
            {overview.activePhaseLabel}
            {overview.source ? ` · ${overview.source}` : ''}
          </div>
        </div>

        <div style={{ display: 'flex', gap: 'var(--s2)' }}>
          <Button variant={mode === 'overview' ? 'secondary' : 'ghost'} size="sm" onClick={() => setMode('overview')}>
            {t.inventoryAdmin.modeOverview}
          </Button>
          <Button variant={mode === 'cli' ? 'secondary' : 'ghost'} size="sm" onClick={() => setMode('cli')}>
            {t.inventoryAdmin.modeCli}
          </Button>
        </div>
      </div>

      {mode === 'overview' ? (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 'var(--s3)' }}>
            <div style={{ border: '1px solid var(--line)', borderRadius: 'var(--r-md)', background: 'var(--bg-2)', padding: 'var(--s3)' }}>
              <div style={subtle}>{t.inventoryAdmin.currentObject}</div>
              <div style={{ color: 'var(--fg)', fontWeight: 700, marginTop: 4 }}>
                {overview.currentObject ?? t.inventoryAdmin.noValue}
              </div>
              {overview.currentObjectType && <div style={{ ...subtle, marginTop: 4 }}>{overview.currentObjectType}</div>}
            </div>
            <div style={{ border: '1px solid var(--line)', borderRadius: 'var(--r-md)', background: 'var(--bg-2)', padding: 'var(--s3)' }}>
              <div style={subtle}>{t.inventoryAdmin.objectsLoaded}</div>
              <div style={{ color: 'var(--fg)', fontWeight: 700, marginTop: 4 }}>
                {overview.current != null && overview.total != null
                  ? `${overview.current} / ${overview.total}`
                  : t.inventoryAdmin.progressWaiting}
              </div>
            </div>
            <div style={{ border: '1px solid var(--line)', borderRadius: 'var(--r-md)', background: 'var(--bg-2)', padding: 'var(--s3)' }}>
              <div style={subtle}>{t.inventoryAdmin.inventoryItems}</div>
              <div style={{ color: 'var(--fg)', fontWeight: 700, marginTop: 4 }}>{summaryCounts?.inventory_items ?? 0}</div>
            </div>
            <div style={{ border: '1px solid var(--line)', borderRadius: 'var(--r-md)', background: 'var(--bg-2)', padding: 'var(--s3)' }}>
              <div style={subtle}>{t.inventoryAdmin.schemaDrift}</div>
              <div style={{ color: 'var(--fg)', fontWeight: 700, marginTop: 4 }}>
                {snapshot && 'schema_drift' in snapshot && snapshot.schema_drift
                  ? `${snapshot.schema_drift.drifted}/${snapshot.schema_drift.checked}`
                  : overview.driftSummary
                    ? `${overview.driftSummary.drifted ?? 0}/${overview.driftSummary.checked ?? 0}`
                    : t.inventoryAdmin.noValue}
              </div>
            </div>
          </div>

          <div style={{ display: 'grid', gap: 'var(--s2)' }}>
            <div style={{ display: 'grid', gridTemplateColumns: `repeat(${steps.length}, minmax(0, 1fr))`, gap: 'var(--s2)' }}>
              {steps.map((step, idx) => {
                const complete = idx < overview.stepIndex || (!running && idx === overview.stepIndex && snapshot?.status !== 'failed');
                const active = idx === overview.stepIndex && running;
                const border = active ? color : complete ? 'var(--status-pass)' : 'var(--line)';
                const background = active
                  ? `color-mix(in srgb, ${color} 12%, var(--bg-2))`
                  : complete
                    ? 'color-mix(in srgb, var(--status-pass) 10%, var(--bg-2))'
                    : 'var(--bg-2)';
                return (
                  <div key={step} style={{ border: `1px solid ${border}`, borderRadius: 'var(--r-md)', background, padding: 'var(--s2)' }}>
                    <div style={{ fontSize: 11, color: active || complete ? 'var(--fg)' : 'var(--fg-3)', fontWeight: 700 }}>
                      {step}
                    </div>
                  </div>
                );
              })}
            </div>

            <div style={{ height: 8, borderRadius: 'var(--r-full)', background: 'var(--bg-3)', overflow: 'hidden' }}>
              <div
                style={{
                  height: '100%',
                  width: overview.total ? `${progressPct}%` : running ? '32%' : '100%',
                  background: color,
                  transition: 'width var(--t)',
                }}
              />
            </div>
          </div>

          <div>
            <div style={{ ...subtle, marginBottom: 'var(--s2)' }}>{t.inventoryAdmin.activity}</div>
            <div style={{
              border: '1px solid var(--line)',
              borderRadius: 'var(--r-md)',
              background: 'var(--bg-2)',
              padding: 'var(--s3)',
              display: 'flex',
              flexDirection: 'column',
              gap: 6,
              minHeight: 120,
            }}>
              {visibleLines.length === 0 ? (
                <div style={subtle}>
                  {running ? t.inventoryAdmin.progressWaiting : t.inventoryAdmin.progressIdle}
                </div>
              ) : (
                visibleLines.slice(-6).map((line, idx) => (
                  <div key={`${line.ts}-${idx}`} style={{ display: 'grid', gridTemplateColumns: 'auto minmax(0, 1fr)', gap: 'var(--s2)' }}>
                    <span style={{ ...mono, color: 'var(--fg-3)' }}>{line.ts}</span>
                    <span style={{ ...mono, color: 'var(--fg-2)' }}>{line.line}</span>
                  </div>
                ))
              )}
            </div>
          </div>
        </>
      ) : (
        <div>
          <div style={{ ...subtle, marginBottom: 'var(--s2)' }}>{t.inventoryAdmin.cliHint}</div>
          <div style={{
            border: '1px solid var(--line)',
            borderRadius: 'var(--r-md)',
            background: '#0f1720',
            color: '#d8e4ef',
            padding: 'var(--s3)',
            minHeight: 220,
            maxHeight: 320,
            overflowY: 'auto',
          }}>
            {visibleLines.length === 0 ? (
              <div style={{ ...mono, color: '#91a3b5' }}>
                {running ? t.inventoryAdmin.progressWaiting : t.inventoryAdmin.progressIdle}
              </div>
            ) : (
              visibleLines.map((line, idx) => (
                <div key={`${line.ts}-${idx}`} style={{ ...mono, marginBottom: 4 }}>
                  <span style={{ color: '#8eb7d6' }}>{line.ts}</span> {line.line}
                </div>
              ))
            )}
          </div>
        </div>
      )}

      {(operation?.error || snapshot?.error) && (
        <div style={{ color: 'var(--status-fail)', fontSize: 12 }}>
          {operation?.error || snapshot?.error}
        </div>
      )}
    </div>
  );
}
