import { useMemo, useState } from 'react';
import {
  useHealingOverview, useHealingEpisode, useCreateCorrection, useRecheckEpisode,
  useCreatePatch, useRevokePatch,
} from '@/api/healing';
import { Table, type ColDef } from '@/components/ui/Table';
import { Button } from '@/components/ui/Button';
import { Field, Input } from '@/components/ui/Field';
import { ErrorBanner } from '@/components/ui/ErrorBanner';
import { PageHeader } from '@/components/ui/PageHeader';
import { TableSkeleton } from '@/components/ui/Skeleton';
import { ObjectSummaryCard } from '@/components/object-detail/ObjectSummaryCard';
import { useSearchParamState } from '@/hooks/useSearchParamState';
import { relativeTime, absoluteTime } from '@/lib/time';
import { useRoleStore } from '@/store/role';
import { t } from '@/i18n/de';
import type { HealingCorrection, HealingEpisodeRow, HealingPatch } from '@/types';

// Healing-Workbench (Konzept_Manuelles_Healing): H1 korrigiert geparkte Zeilen
// episodisch, H3 legt ein dauerhaftes Overlay über die Quelle. Beide schreiben
// ausschließlich im Signal-Schema — die Quelle bleibt read-only (ADR-0002).

type Tab = 'episodes' | 'patches';

function KeyValueList({ data }: { data: Record<string, string> }) {
  const entries = Object.entries(data ?? {});
  if (entries.length === 0) return <span style={{ color: 'var(--fg-3)' }}>—</span>;
  return (
    <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11.5 }}>
      {entries.map(([k, v]) => `${k}=${v}`).join(', ')}
    </span>
  );
}

function AppliedFlag({ applied }: { applied: boolean }) {
  return (
    <span style={{
      fontSize: 10, borderRadius: 'var(--r)', padding: '1px 6px', whiteSpace: 'nowrap',
      color: applied ? 'var(--status-ok)' : 'var(--fg-3)',
      border: `1px solid ${applied ? 'var(--status-ok)' : 'var(--line-2)'}`,
    }}>
      {applied ? t.healing.appliedYes : t.healing.appliedNo}
    </span>
  );
}

// ─── H1: Episode-Detail mit Korrekturformular ────────────────────────────────

function EpisodeDetail({ episodeId }: { episodeId: number }) {
  const { data, isLoading, isError, refetch } = useHealingEpisode(episodeId);
  const createCorrection = useCreateCorrection(episodeId);
  const recheck = useRecheckEpisode(episodeId);

  const [keyColumn, setKeyColumn] = useState('');
  const [keyValue, setKeyValue] = useState('');
  const [column, setColumn] = useState('');
  const [newValue, setNewValue] = useState('');
  const [reason, setReason] = useState('');

  if (isError) return <ErrorBanner onRetry={() => refetch()} />;
  if (isLoading || !data) return <TableSkeleton columns={4} />;

  const effectiveKeyColumn = keyColumn || data.key_columns[0] || '';
  const canSubmit = Boolean(effectiveKeyColumn && keyValue.trim() && column && newValue.trim());

  const submit = () => {
    if (!canSubmit) return;
    createCorrection.mutate(
      {
        keys: { [effectiveKeyColumn]: keyValue.trim() },
        column,
        new_value: newValue.trim(),
        reason: reason.trim(),
      },
      { onSuccess: () => { setKeyValue(''); setNewValue(''); setReason(''); } },
    );
  };

  const correctionColumns: ColDef<HealingCorrection>[] = [
    { key: 'key', header: t.healing.colKeys, render: c => <KeyValueList data={c.row_key} /> },
    { key: 'column', header: t.healing.colColumn, mono: true, render: c => c.column_name },
    { key: 'before', header: t.healing.colBefore, mono: true, render: c => c.before_value || '—' },
    { key: 'after', header: t.healing.colAfter, mono: true, render: c => c.after_value || '—' },
    { key: 'actor', header: t.healing.colActor, render: c => c.actor || '—' },
    {
      key: 'at', header: t.healing.colOpened, width: 120,
      render: c => (
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }} title={absoluteTime(c.created_at)}>
          {relativeTime(c.created_at)}
        </span>
      ),
    },
    { key: 'applied', header: t.healing.colApplied, width: 110, render: c => <AppliedFlag applied={c.applied} /> },
  ];

  const remaining = data.remaining_bad_rows;

  return (
    <section style={{ display: 'flex', flexDirection: 'column', gap: 'var(--s4)', marginTop: 'var(--s5)' }}>
      <div>
        <h2 style={{ fontSize: 15, fontWeight: 700, color: 'var(--fg)', margin: 0 }}>
          {t.healing.detailTitle.replace('{id}', String(episodeId)).replace('{object}', data.object_id)}
        </h2>
        <div style={{ fontSize: 12, color: 'var(--fg-3)', marginTop: 2 }}>
          {data.kind}
          {data.four_eyes && <> · {t.healing.fourEyesHint}</>}
        </div>
      </div>

      {!data.row_capable && (
        <div style={{
          background: 'color-mix(in srgb, var(--status-warn) 8%, transparent)',
          border: '1px solid var(--status-warn)', borderRadius: 'var(--r-lg)',
          padding: 'var(--s3)', fontSize: 12.5, color: 'var(--fg-2)',
        }}>
          {t.healing.notRowCapable}
        </div>
      )}

      {/* Heal → Re-Check → Release: der Zähler entscheidet über die Freigabe. */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--s4)', flexWrap: 'wrap' }}>
        <div>
          <div style={{ fontSize: 10, color: 'var(--fg-3)', textTransform: 'uppercase' }}>
            {t.healing.remainingRows}
          </div>
          <div style={{
            fontFamily: 'var(--font-mono)', fontSize: 18, fontWeight: 700,
            color: remaining === 0 ? 'var(--status-ok)' : remaining == null ? 'var(--fg-3)' : 'var(--status-fail)',
          }}>
            {remaining == null ? t.healing.remainingUnknown : remaining}
          </div>
        </div>
        <span style={{
          fontSize: 12, fontWeight: 600,
          color: data.release_ready ? 'var(--status-ok)' : 'var(--fg-3)',
        }}>
          {data.release_ready ? t.healing.releaseReady : t.healing.releaseBlocked}
        </span>
        <Button
          type="button" size="sm"
          onClick={() => recheck.mutate()}
          disabled={recheck.isPending || !data.row_capable}
        >
          {recheck.isPending ? t.healing.rechecking : t.healing.recheck}
        </Button>
      </div>

      {data.row_capable && (
        <div style={{
          background: 'var(--bg-1)', border: '1px solid var(--line)',
          borderRadius: 'var(--r-lg)', padding: 'var(--s4)',
        }}>
          <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 'var(--s3)' }}>
            {t.healing.correctionFormTitle}
          </div>
          <div style={{ display: 'flex', gap: 'var(--s2)', flexWrap: 'wrap', alignItems: 'flex-end' }}>
            <Field label={t.healing.keyColumn}>
              <select
                value={effectiveKeyColumn}
                onChange={e => setKeyColumn(e.target.value)}
                aria-label={t.healing.keyColumn}
                style={{
                  background: 'var(--bg-2)', border: '1px solid var(--line-2)', color: 'var(--fg)',
                  borderRadius: 'var(--r-md)', padding: '6px 10px', fontSize: 12.5,
                }}
              >
                {(data.key_columns.length ? data.key_columns : data.columns).map(c => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </Field>
            <Field label={t.healing.keyValue}>
              <Input value={keyValue} onChange={e => setKeyValue(e.target.value)} />
            </Field>
            <Field label={t.healing.column}>
              <select
                value={column}
                onChange={e => setColumn(e.target.value)}
                aria-label={t.healing.column}
                style={{
                  background: 'var(--bg-2)', border: '1px solid var(--line-2)', color: 'var(--fg)',
                  borderRadius: 'var(--r-md)', padding: '6px 10px', fontSize: 12.5,
                }}
              >
                <option value="">—</option>
                {data.columns.filter(c => c !== effectiveKeyColumn).map(c => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </Field>
            <Field label={t.healing.newValue}>
              <Input value={newValue} onChange={e => setNewValue(e.target.value)} />
            </Field>
            <Field label={t.healing.reason} style={{ flex: 1 }}>
              <Input style={{ width: '100%' }} value={reason} onChange={e => setReason(e.target.value)} />
            </Field>
            <Button
              variant="primary"
              disabled={!canSubmit || createCorrection.isPending}
              onClick={submit}
            >
              {t.healing.submitCorrection}
            </Button>
          </div>
        </div>
      )}

      <div>
        <h3 style={{ fontSize: 13, fontWeight: 650, color: 'var(--fg-2)', margin: '0 0 8px' }}>
          {t.healing.correctionsTitle}
        </h3>
        {data.corrections.length === 0
          ? <div style={{ color: 'var(--fg-3)', fontSize: 12.5 }}>{t.healing.noCorrections}</div>
          : (
            <div style={{ background: 'var(--bg-1)', border: '1px solid var(--line)', borderRadius: 'var(--r-lg)', overflow: 'hidden' }}>
              <Table columns={correctionColumns} rows={data.corrections} rowKey={c => String(c.id)} />
            </div>
          )}
      </div>
    </section>
  );
}

// ─── H3: Patch-Overlay ───────────────────────────────────────────────────────

function PatchesTab({ patches, canManage }: { patches: HealingPatch[]; canManage: boolean }) {
  const createPatch = useCreatePatch();
  const revoke = useRevokePatch();
  const [objectId, setObjectId] = useState('');
  const [keyColumn, setKeyColumn] = useState('');
  const [keyValue, setKeyValue] = useState('');
  const [column, setColumn] = useState('');
  const [value, setValue] = useState('');
  const [reason, setReason] = useState('');
  const [validUntil, setValidUntil] = useState('');

  const canSubmit = Boolean(
    objectId.trim() && keyColumn.trim() && keyValue.trim() && column.trim() && value.trim(),
  );

  const submit = () => {
    if (!canSubmit) return;
    createPatch.mutate(
      {
        object_id: objectId.trim(),
        keys: { [keyColumn.trim()]: keyValue.trim() },
        values: { [column.trim()]: value.trim() },
        reason: reason.trim(),
        valid_until: validUntil ? new Date(validUntil).toISOString() : null,
      },
      { onSuccess: () => { setKeyValue(''); setValue(''); setReason(''); } },
    );
  };

  const columns: ColDef<HealingPatch>[] = [
    { key: 'object', header: t.healing.colObject, mono: true, render: p => p.object_id },
    { key: 'keys', header: t.healing.colKeys, render: p => <KeyValueList data={p.keys} /> },
    { key: 'values', header: t.healing.colValues, render: p => <KeyValueList data={p.values} /> },
    {
      key: 'status', header: t.healing.colStatus, width: 130,
      render: p => (
        <span style={{
          fontSize: 11, fontWeight: 650,
          color: p.status === 'active' ? 'var(--status-ok)' : 'var(--fg-3)',
        }}>
          {t.healing.statusLabel[p.status] ?? p.status}
        </span>
      ),
    },
    {
      key: 'valid', header: t.healing.colValidUntil, width: 140,
      render: p => (
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--fg-2)' }}>
          {p.valid_until ? absoluteTime(p.valid_until) : t.healing.unlimited}
        </span>
      ),
    },
    { key: 'actor', header: t.healing.colActor, render: p => p.actor || '—' },
    { key: 'applied', header: t.healing.colApplied, width: 110, render: p => <AppliedFlag applied={p.applied} /> },
    ...(canManage ? [{
      key: 'actions', header: '', width: 130,
      render: (p: HealingPatch) => p.status === 'active' ? (
        <Button type="button" size="sm" onClick={() => revoke.mutate(p.id)} disabled={revoke.isPending}>
          {t.healing.revoke}
        </Button>
      ) : <span style={{ color: 'var(--fg-3)' }}>—</span>,
    } as ColDef<HealingPatch>] : []),
  ];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--s4)' }}>
      {!canManage && (
        <div style={{ fontSize: 12.5, color: 'var(--fg-3)' }}>{t.healing.patchOwnerOnly}</div>
      )}
      {canManage && (
        <div style={{
          background: 'var(--bg-1)', border: '1px solid var(--line)',
          borderRadius: 'var(--r-lg)', padding: 'var(--s4)',
        }}>
          <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 'var(--s3)' }}>
            {t.healing.patchFormTitle}
          </div>
          <div style={{ display: 'flex', gap: 'var(--s2)', flexWrap: 'wrap', alignItems: 'flex-end' }}>
            <Field label={t.healing.patchObject}>
              <Input value={objectId} onChange={e => setObjectId(e.target.value)} />
            </Field>
            <Field label={t.healing.keyColumn}>
              <Input style={{ width: 110 }} value={keyColumn} onChange={e => setKeyColumn(e.target.value)} />
            </Field>
            <Field label={t.healing.keyValue}>
              <Input style={{ width: 110 }} value={keyValue} onChange={e => setKeyValue(e.target.value)} />
            </Field>
            <Field label={t.healing.column}>
              <Input style={{ width: 110 }} value={column} onChange={e => setColumn(e.target.value)} />
            </Field>
            <Field label={t.healing.newValue}>
              <Input style={{ width: 110 }} value={value} onChange={e => setValue(e.target.value)} />
            </Field>
            <Field label={t.healing.patchValidUntil}>
              <Input type="datetime-local" value={validUntil} onChange={e => setValidUntil(e.target.value)} />
            </Field>
            <Field label={t.healing.reason} style={{ flex: 1 }}>
              <Input style={{ width: '100%' }} value={reason} onChange={e => setReason(e.target.value)} />
            </Field>
            <Button variant="primary" disabled={!canSubmit || createPatch.isPending} onClick={submit}>
              {t.healing.submitPatch}
            </Button>
          </div>
        </div>
      )}

      <div>
        <h3 style={{ fontSize: 13, fontWeight: 650, color: 'var(--fg-2)', margin: '0 0 8px' }}>
          {t.healing.patchesTitle}
        </h3>
        <div style={{ background: 'var(--bg-1)', border: '1px solid var(--line)', borderRadius: 'var(--r-lg)', overflow: 'hidden' }}>
          <Table columns={columns} rows={patches} rowKey={p => p.id} empty={t.healing.noPatches} />
        </div>
      </div>
    </div>
  );
}

// ─── Seite ───────────────────────────────────────────────────────────────────

export default function Healing() {
  const { data, isLoading, isError, refetch } = useHealingOverview();
  const [tabParam, setTab] = useSearchParamState('tab', 'episodes');
  const [selected, setSelected] = useSearchParamState('episode');
  const role = useRoleStore(s => s.role);
  const canManagePatches = role === 'owner' || role === 'admin';
  const tab: Tab = tabParam === 'patches' ? 'patches' : 'episodes';

  const selectedId = useMemo(() => {
    const id = Number(selected);
    return Number.isFinite(id) && id > 0 ? id : null;
  }, [selected]);

  const episodeColumns: ColDef<HealingEpisodeRow>[] = [
    {
      key: 'episode', header: t.healing.colEpisode, width: 90,
      render: e => <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}>#{e.episode_id}</span>,
    },
    {
      key: 'object', header: t.healing.colObject,
      render: e => (
        <div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 13, fontWeight: 650 }}>{e.object_id}</div>
          <div style={{ fontSize: 11, color: 'var(--fg-3)' }}>
            {e.kind}
            {e.four_eyes && <> · {t.healing.fourEyes}</>}
          </div>
        </div>
      ),
    },
    { key: 'status', header: t.healing.colStatus, width: 110, render: e => e.status },
    {
      key: 'rows', header: t.healing.colRows, width: 90,
      render: e => <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}>{e.row_count ?? '—'}</span>,
    },
    {
      key: 'corrections', header: t.healing.colCorrections, width: 120,
      render: e => (
        <span style={{
          fontFamily: 'var(--font-mono)', fontSize: 12,
          color: e.corrections > 0 ? 'var(--cont)' : 'var(--fg-3)',
        }}>{e.corrections}</span>
      ),
    },
    {
      key: 'opened', header: t.healing.colOpened, width: 130,
      render: e => (
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }} title={absoluteTime(e.opened_at)}>
          {relativeTime(e.opened_at)}
        </span>
      ),
    },
  ];

  return (
    <div className="page-full">
      <PageHeader title={t.healing.title} subtitle={t.healing.subtitle} />

      {isError && <ErrorBanner onRetry={() => refetch()} />}
      {isLoading && <TableSkeleton columns={6} />}

      {data && (
        <>
          {!data.materialization_enabled && (
            <div style={{
              background: 'color-mix(in srgb, var(--status-warn) 8%, transparent)',
              border: '1px solid var(--status-warn)', borderRadius: 'var(--r-lg)',
              padding: 'var(--s3)', marginBottom: 'var(--s4)', fontSize: 12.5, color: 'var(--fg-2)',
            }}>
              {t.healing.materializationOff}
            </div>
          )}

          <div className="dash-kpis" style={{ marginBottom: 22 }}>
            <ObjectSummaryCard label={t.healing.kpiEpisodes} value={data.episodes.length} />
            <ObjectSummaryCard label={t.healing.kpiCorrections} value={data.corrections_total} />
            <ObjectSummaryCard
              label={t.healing.kpiPatches}
              tone={data.patches.length ? 'var(--cont)' : undefined}
              value={data.patches.length}
            />
          </div>

          <div style={{ display: 'flex', gap: 'var(--s2)', marginBottom: 14 }}>
            {(['episodes', 'patches'] as Tab[]).map(key => (
              <button
                key={key}
                onClick={() => setTab(key)}
                style={{
                  padding: '6px 14px', borderRadius: 'var(--r-lg)', fontSize: 12.5, cursor: 'pointer',
                  background: tab === key ? 'color-mix(in srgb, var(--cont) 16%, transparent)' : 'var(--bg-2)',
                  border: `1px solid ${tab === key ? 'var(--cont)' : 'var(--line)'}`,
                  color: tab === key ? 'var(--fg)' : 'var(--fg-2)',
                  fontWeight: tab === key ? 650 : 400,
                }}
              >
                {key === 'episodes' ? t.healing.tabEpisodes : t.healing.tabPatches}
              </button>
            ))}
          </div>

          {tab === 'episodes' ? (
            <>
              <div style={{ background: 'var(--bg-1)', border: '1px solid var(--line)', borderRadius: 'var(--r-lg)', overflow: 'hidden' }}>
                <Table
                  columns={episodeColumns}
                  rows={data.episodes}
                  rowKey={e => String(e.episode_id)}
                  onRowClick={e => setSelected(
                    selectedId === e.episode_id ? '' : String(e.episode_id),
                  )}
                  empty={t.healing.noEpisodes}
                />
              </div>
              {selectedId != null && <EpisodeDetail episodeId={selectedId} />}
            </>
          ) : (
            <PatchesTab patches={data.patches} canManage={canManagePatches} />
          )}
        </>
      )}
    </div>
  );
}
