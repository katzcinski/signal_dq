import { useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  useQuarantineEpisodes,
  useQuarantineEpisode,
  useQuarantineRelease,
  useQuarantineConfirmReprocess,
} from '@/api/quarantine';
import { Table, type ColDef } from '@/components/ui/Table';
import { ErrorBanner } from '@/components/ui/ErrorBanner';
import { ReadOnlyBanner } from '@/components/ui/ReadOnlyBanner';
import { TableSkeleton } from '@/components/ui/Skeleton';
import { PageHeader } from '@/components/ui/PageHeader';
import { SidePanel } from '@/components/ui/SidePanel';
import { Button } from '@/components/ui/Button';
import { relativeTime, absoluteTime } from '@/lib/time';
import { t } from '@/i18n/de';
import { useRoleStore, canActOnQuarantine } from '@/store/role';
import type { QuarantineEpisode, QuarantineStatus } from '@/types';

const STATUS_TABS: QuarantineStatus[] = ['open', 'reconciled', 'released', 'resolved', 'superseded'];
// 'active' = alle nicht-terminalen Episoden (offen/isoliert/freigegeben) —
// die Menge, die noch eine Entscheidung oder Rückführung erwartet.
const TABS = ['active', ...STATUS_TABS] as const;
const TERMINAL: QuarantineStatus[] = ['resolved', 'superseded'];

type QuarantineTab = typeof TABS[number];

function normalizeTab(value: string): QuarantineTab {
  return (TABS as readonly string[]).includes(value) ? (value as QuarantineTab) : 'active';
}

function selectedEpisodeId(value: string): number | null {
  if (!/^\d+$/.test(value)) return null;
  const id = Number(value);
  return Number.isFinite(id) ? id : null;
}

// Statusfarbe entlang der Episoden-Reise: aktiv (Handlung nötig) → ok.
function statusColor(status: QuarantineStatus): string {
  if (status === 'open') return 'var(--err, #e5484d)';
  if (status === 'reconciled') return 'var(--warn, #f5a524)';
  if (status === 'released') return 'var(--cont)';
  return 'var(--fg-3)';
}

function QuarantineStatusBadge({ status }: { status: QuarantineStatus }) {
  const color = statusColor(status);
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', height: 22, padding: '0 var(--s2)',
      borderRadius: 'var(--r-full)', border: `1px solid ${color}`,
      color, fontSize: 11, fontWeight: 650, whiteSpace: 'nowrap',
    }}>
      {t.quarantine.statusLabel[status] ?? status}
    </span>
  );
}

function QuarantineDrawer({ id, onClose, onTransitioned }: {
  id: number;
  onClose: () => void;
  onTransitioned: (status: QuarantineStatus) => void;
}) {
  const { data: episode, isLoading } = useQuarantineEpisode(id);
  const release = useQuarantineRelease(id);
  const confirm = useQuarantineConfirmReprocess(id);
  const navigate = useNavigate();
  const role = useRoleStore(s => s.role);
  const canAct = canActOnQuarantine(role); // server re-checks (quarantine.py)
  const [pendingAction, setPendingAction] = useState<'release' | 'confirm' | null>(null);
  const [noteInput, setNoteInput] = useState('');

  const confirmAct = () => {
    if (!pendingAction) return;
    const mutation = pendingAction === 'release' ? release : confirm;
    const nextStatus: QuarantineStatus = pendingAction === 'release' ? 'released' : 'resolved';
    mutation.mutate(
      { note: noteInput.trim() || undefined },
      { onSuccess: () => onTransitioned(nextStatus) },
    );
    setPendingAction(null);
    setNoteInput('');
  };

  const pending = release.isPending || confirm.isPending;

  return (
    <SidePanel title={episode ? episode.product : t.quarantine.title} onClose={onClose} width={460}>
      {isLoading && <div style={{ color: 'var(--fg-3)' }}>{t.common.loading}</div>}

      {episode && (
        <>
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--s2)', marginBottom: 6, flexWrap: 'wrap' }}>
            <QuarantineStatusBadge status={episode.status} />
            <span style={{ fontSize: 11, color: 'var(--fg-3)' }}>
              {t.quarantine.colGeneration}: {episode.generation}
            </span>
            <span style={{ fontSize: 11, color: 'var(--fg-3)' }}>
              {t.quarantine.colRows}: {episode.row_count ?? t.quarantine.rowCountUnknown}
            </span>
          </div>
          <div style={{ fontSize: 11, color: 'var(--fg-3)', marginTop: 2, marginBottom: 16 }}>
            {t.quarantine.colOpened}: {new Date(episode.opened_at).toLocaleString()}
            {' - '}
            {t.quarantine.contractVersion}: {episode.contract_version || '-'}
          </div>

          {!canAct && <ReadOnlyBanner />}

          <div
            style={{ display: 'flex', gap: 'var(--s2)', flexWrap: 'wrap', marginBottom: pendingAction ? 8 : 16 }}
            title={canAct ? undefined : t.role.noWriteAction}
          >
            {(episode.status === 'open' || episode.status === 'reconciled') && (
              <Button
                variant={pendingAction === 'release' ? 'primary' : 'secondary'}
                size="sm"
                disabled={!canAct}
                pending={pending}
                onClick={() => { setPendingAction('release'); setNoteInput(''); }}
              >
                {t.quarantine.release}
              </Button>
            )}
            {episode.status === 'released' && (
              <Button
                variant={pendingAction === 'confirm' ? 'primary' : 'secondary'}
                size="sm"
                disabled={!canAct}
                pending={pending}
                onClick={() => { setPendingAction('confirm'); setNoteInput(''); }}
              >
                {t.quarantine.confirmReprocess}
              </Button>
            )}
            {episode.run_id && (
              <Button variant="ghost" size="sm" onClick={() => navigate(`/runs/${episode.run_id}`)}>
                {t.quarantine.openRun}
              </Button>
            )}
          </div>

          {pendingAction && (
            <div style={{
              background: 'var(--bg-2)', border: '1px solid var(--line-2)',
              borderRadius: 'var(--r-md)', padding: 'var(--s3)', marginBottom: 16,
            }}>
              {pendingAction === 'release' && (
                <div style={{ fontSize: 12, color: 'var(--fg-2)', marginBottom: 6 }}>
                  {t.quarantine.releaseHint}
                </div>
              )}
              <div style={{ fontSize: 11, color: 'var(--fg-3)', marginBottom: 6 }}>
                {t.quarantine.notePrompt}
              </div>
              <textarea
                value={noteInput}
                onChange={e => setNoteInput(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) confirmAct(); }}
                placeholder={t.quarantine.notePlaceholder}
                autoFocus
                rows={2}
                style={{
                  width: '100%', background: 'var(--bg-1)', border: '1px solid var(--line-2)',
                  color: 'var(--fg)', borderRadius: 'var(--r)', padding: '6px 8px', fontSize: 12,
                  resize: 'vertical', boxSizing: 'border-box', display: 'block',
                }}
              />
              <div style={{ display: 'flex', gap: 'var(--s2)', marginTop: 8 }}>
                <Button variant="primary" size="sm" onClick={confirmAct} pending={pending}>
                  {t.common.confirm}
                </Button>
                <Button variant="ghost" size="sm" onClick={() => { setPendingAction(null); setNoteInput(''); }}>
                  {t.common.cancel}
                </Button>
              </div>
            </div>
          )}

          {(episode.released_by || episode.resolve_reason) && (
            <div style={{ fontSize: 12, color: 'var(--fg-2)', marginBottom: 16 }}>
              {episode.released_by && (
                <div>{t.quarantine.releasedBy}: {episode.released_by}</div>
              )}
              {episode.resolve_reason && (
                <div>{t.quarantine.resolveReason}: {episode.resolve_reason}</div>
              )}
            </div>
          )}

          <div style={{ marginBottom: 16 }}>
            <div style={{ fontSize: 11, color: 'var(--fg-3)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 6 }}>
              {t.quarantine.colChecks}
            </div>
            {episode.failed_checks.length === 0 ? (
              <div style={{ fontSize: 12, color: 'var(--fg-3)' }}>-</div>
            ) : episode.failed_checks.map(c => (
              <div key={c} style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--fg-2)', padding: '2px 0' }}>
                - {c}
              </div>
            ))}
          </div>

          <div>
            <div style={{ fontSize: 11, color: 'var(--fg-3)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 6 }}>
              {t.quarantine.timeline}
            </div>
            {(episode.events ?? []).length === 0 ? (
              <div style={{ fontSize: 12, color: 'var(--fg-3)' }}>-</div>
            ) : (episode.events ?? []).map(ev => (
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

export default function Quarantine() {
  const [searchParams, setSearchParams] = useSearchParams();
  const activeTab = normalizeTab(searchParams.get('status') ?? 'active');
  const idParam = searchParams.get('id') ?? '';
  const activeEpisodeId = selectedEpisodeId(idParam);

  const { data: episodes = [], isLoading, isError, refetch } = useQuarantineEpisodes();

  const statusCounts = useMemo(
    () => episodes.reduce<Record<QuarantineStatus, number>>(
      (acc, e) => { acc[e.status] += 1; return acc; },
      { open: 0, reconciled: 0, released: 0, resolved: 0, superseded: 0 },
    ),
    [episodes],
  );
  const activeCount = statusCounts.open + statusCounts.reconciled + statusCounts.released;

  const filtered = useMemo(() => {
    if (activeTab === 'active') return episodes.filter(e => !TERMINAL.includes(e.status));
    return episodes.filter(e => e.status === activeTab);
  }, [activeTab, episodes]);

  const columns = useMemo<ColDef<QuarantineEpisode>[]>(() => [
    {
      key: 'status', header: t.quarantine.colStatus, width: 130,
      render: e => <QuarantineStatusBadge status={e.status} />,
    },
    { key: 'product', header: t.quarantine.colProduct, mono: true, render: e => e.product },
    {
      key: 'checks', header: t.quarantine.colChecks, mono: true,
      render: e => e.failed_checks.join(', ') || '-',
    },
    {
      key: 'rows', header: t.quarantine.colRows, mono: true, width: 90,
      render: e => e.row_count ?? '-',
    },
    { key: 'generation', header: t.quarantine.colGeneration, mono: true, width: 100, render: e => e.generation },
    {
      key: 'opened', header: t.quarantine.colOpened,
      render: e => <span style={{ color: 'var(--fg-3)', fontSize: 12 }} title={absoluteTime(e.opened_at)}>{relativeTime(e.opened_at)}</span>,
    },
  ], []);

  const setQuery = (next: Partial<Record<'status' | 'id', string>>) => {
    setSearchParams(prev => {
      const params = new URLSearchParams(prev);
      (Object.entries(next) as Array<['status' | 'id', string]>).forEach(([key, value]) => {
        if (!value || (key === 'status' && value === 'active')) params.delete(key);
        else params.set(key, value);
      });
      return params;
    }, { replace: true });
  };

  // Nach Freigabe/Bestätigung dem Status der Episode folgen, wenn der aktive
  // Tab sie nicht mehr listet — der offene Drawer bleibt sonst stale zur URL.
  const followTransition = (status: QuarantineStatus) => {
    const stillVisible = activeTab === 'active' ? !TERMINAL.includes(status) : activeTab === status;
    if (!stillVisible) setQuery({ status });
  };

  return (
    <div className="page-full">
      <PageHeader title={t.quarantine.title} />

      <div style={{ display: 'flex', borderBottom: '1px solid var(--line)', marginBottom: 16 }}>
        {TABS.map(tabKey => (
          <button
            key={tabKey}
            onClick={() => setQuery({ status: tabKey, id: '' })}
            style={{
              padding: 'var(--s2) var(--s4)', border: 'none', background: 'none',
              color: activeTab === tabKey ? 'var(--fg)' : 'var(--fg-3)',
              borderBottom: activeTab === tabKey ? '2px solid var(--cont)' : '2px solid transparent',
              cursor: 'pointer', fontSize: 13,
            }}
          >
            {tabKey === 'active'
              ? `${t.quarantine.tabs.active} (${activeCount})`
              : `${t.quarantine.tabs[tabKey] ?? tabKey} (${statusCounts[tabKey as QuarantineStatus]})`}
          </button>
        ))}
      </div>

      {isError && <ErrorBanner onRetry={() => refetch()} />}
      {isLoading && <TableSkeleton columns={6} />}
      {!isError && !isLoading && (
        <div style={{ background: 'var(--bg-1)', border: '1px solid var(--line)', borderRadius: 'var(--r-lg)', overflow: 'hidden' }}>
          <Table
            columns={columns}
            rows={filtered}
            rowKey={e => String(e.id)}
            onRowClick={e => setQuery({ id: String(e.id) })}
            empty={t.quarantine.empty}
          />
        </div>
      )}

      {activeEpisodeId != null && (
        <QuarantineDrawer
          id={activeEpisodeId}
          onClose={() => setQuery({ id: '' })}
          onTransitioned={followTransition}
        />
      )}
    </div>
  );
}
