import { useEffect, useState } from 'react';
import { Panel } from '@/components/ui/Panel';
import { Button } from '@/components/ui/Button';
import { ConfirmDeleteButton } from '@/components/ui/ControlPrimitives';
import { Field, Input, Select } from '@/components/ui/Field';
import { ErrorBanner } from '@/components/ui/ErrorBanner';
import { PageHeader } from '@/components/ui/PageHeader';
import { ReadOnlyBanner } from '@/components/ui/ReadOnlyBanner';
import {
  useNotificationConfig, useCreateChannel, usePatchChannel, useDeleteChannel,
  useCreateRule, useDeleteRule, useCreateMute, useDeleteMute,
  useDigestPreview, useSendDigest,
} from '@/api/notifications';
import { useRoleStore } from '@/store/role';
import { t } from '@/i18n/de';
import type { NotificationChannel, NotificationRule, NotificationMute } from '@/types';

const row: React.CSSProperties = {
  display: 'flex', alignItems: 'center', gap: 'var(--s3)',
  padding: 'var(--s2) 0', borderBottom: '1px solid var(--line)',
};
const form: React.CSSProperties = {
  display: 'flex', alignItems: 'flex-end', gap: 'var(--s2)', marginTop: 'var(--s3)', flexWrap: 'wrap',
};
const hint: React.CSSProperties = { fontSize: 11, color: 'var(--fg-3)', marginBottom: 'var(--s3)' };
const empty: React.CSSProperties = { fontSize: 12, color: 'var(--fg-3)' };

function muteState(m: NotificationMute): 'active' | 'scheduled' | 'expired' {
  const now = Date.now();
  const s = new Date(m.starts_at).getTime();
  const e = new Date(m.ends_at).getTime();
  if (now < s) return 'scheduled';
  if (now > e) return 'expired';
  return 'active';
}

const STATE_COLOR: Record<string, string> = {
  active: 'var(--status-warn)', scheduled: 'var(--cont)', expired: 'var(--fg-3)',
};

// --- Channels ---
function ChannelsSection({ channels, canEdit }: { channels: NotificationChannel[]; canEdit: boolean }) {
  const create = useCreateChannel();
  const patch = usePatchChannel();
  const del = useDeleteChannel();
  const [name, setName] = useState('');
  const [type, setType] = useState('slack');
  const [url, setUrl] = useState('');

  const canSubmit = Boolean(name.trim() && url.trim());
  const submit = () => {
    if (!canSubmit) return;
    create.mutate({ name: name.trim(), type, url: url.trim() }, {
      onSuccess: () => { setName(''); setUrl(''); },
    });
  };

  return (
    <Panel title={`${t.notifications.channelsTitle} (${channels.length})`}>
      <p style={hint}>{t.notifications.channelsHint}</p>
      {channels.length === 0 && <p style={empty}>{t.notifications.noChannels}</p>}
      {channels.map(c => (
        <div key={c.id} style={row}>
          <span style={{ fontSize: 12, fontWeight: 600, minWidth: 120 }}>{c.name}</span>
          <span style={{ fontSize: 10, textTransform: 'uppercase', color: 'var(--cont)', border: '1px solid var(--line-2)', borderRadius: 'var(--r)', padding: '1px 6px' }}>{c.type}</span>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--fg-3)', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{c.url}</span>
          <label style={{ fontSize: 11, color: 'var(--fg-3)', display: 'inline-flex', alignItems: 'center', gap: 'var(--s1)' }}>
            <input
              type="checkbox" checked={c.enabled} disabled={!canEdit}
              onChange={e => patch.mutate({ id: c.id, enabled: e.target.checked })}
            />
            {c.enabled ? t.notifications.enabled : t.notifications.disabled}
          </label>
          <label style={{ fontSize: 11, color: c.digest_enabled ? 'var(--cont)' : 'var(--fg-3)', display: 'inline-flex', alignItems: 'center', gap: 'var(--s1)' }}>
            <input
              type="checkbox" checked={c.digest_enabled} disabled={!canEdit}
              onChange={e => patch.mutate({ id: c.id, digest_enabled: e.target.checked })}
            />
            {t.notifications.digestSubscribe}
          </label>
          {canEdit && (
            <ConfirmDeleteButton
              label={t.notifications.delete}
              confirmLabel={t.common.confirm}
              cancelLabel={t.common.cancel}
              disabled={del.isPending}
              onConfirm={() => del.mutate(c.id)}
            />
          )}
        </div>
      ))}
      {canEdit && (
        <div style={form}>
          <Field label={t.notifications.name}><Input value={name} onChange={e => setName(e.target.value)} /></Field>
          <Field label={t.notifications.type}>
            <Select value={type} onChange={e => setType(e.target.value)}>
              <option value="slack">slack</option>
              <option value="teams">teams</option>
              <option value="webhook">webhook</option>
            </Select>
          </Field>
          <Field label={t.notifications.url} style={{ flex: 1 }}>
            <Input style={{ width: '100%' }} placeholder="https://…" value={url} onChange={e => setUrl(e.target.value)} />
          </Field>
          <Button variant="primary" disabled={create.isPending || !canSubmit} onClick={submit}>{t.notifications.addChannel}</Button>
        </div>
      )}
    </Panel>
  );
}

// --- Rules ---
function RulesSection({ rules, channels, canEdit }: { rules: NotificationRule[]; channels: NotificationChannel[]; canEdit: boolean }) {
  const create = useCreateRule();
  const del = useDeleteRule();
  const [name, setName] = useState('');
  const [channelId, setChannelId] = useState<number | ''>(channels[0]?.id ?? '');
  const [severity, setSeverity] = useState('');
  const [kind, setKind] = useState('');
  const [space, setSpace] = useState('');
  const [product, setProduct] = useState('');

  // Der <select> wird erst nach dem ersten Kanal montiert; die initiale
  // useState-Wahl (leer, weil channels noch leer war) bleibt sonst hängen und
  // submit() no-oped stumm. Auf einen gültigen Kanal synchronisieren, sobald
  // sich die Liste ändert (bzw. der gewählte Kanal gelöscht wird).
  useEffect(() => {
    if (channels.length === 0) {
      if (channelId !== '') setChannelId('');
    } else if (!channels.some(c => c.id === channelId)) {
      setChannelId(channels[0].id);
    }
  }, [channels, channelId]);

  const channelName = (id: number) => channels.find(c => c.id === id)?.name ?? `#${id}`;
  const facets = (r: NotificationRule) => {
    const parts = [
      r.match_severity && `${t.notifications.severity}=${r.match_severity}`,
      r.match_space && `${t.notifications.space}=${r.match_space}`,
      r.match_product && `${t.notifications.product}=${r.match_product}`,
      r.match_kind && `${t.notifications.kind}=${r.match_kind}`,
      r.match_owned_by && `${t.notifications.ownedBy}=${r.match_owned_by}`,
      r.match_owner && `${t.notifications.owner}=${r.match_owner}`,
    ].filter(Boolean);
    return parts.length ? parts.join(' · ') : t.notifications.any;
  };

  const canSubmit = Boolean(name.trim()) && channelId !== '';
  const submit = () => {
    if (!canSubmit) return;
    create.mutate(
      {
        name: name.trim(), channel_id: Number(channelId), match_severity: severity,
        match_kind: kind, match_space: space.trim(), match_product: product.trim(),
      },
      { onSuccess: () => { setName(''); setSpace(''); setProduct(''); setSeverity(''); setKind(''); } },
    );
  };

  return (
    <Panel title={`${t.notifications.rulesTitle} (${rules.length})`}>
      <p style={hint}>{t.notifications.rulesHint}</p>
      {rules.length === 0 && <p style={empty}>{t.notifications.noRules}</p>}
      {rules.map(r => (
        <div key={r.id} style={row}>
          <span style={{ fontSize: 12, fontWeight: 600, minWidth: 140 }}>{r.name}</span>
          <span style={{ fontSize: 11, color: 'var(--fg-2)', flex: 1 }}>{facets(r)}</span>
          <span style={{ fontSize: 11, color: 'var(--fg-3)' }}>{t.notifications.routesTo}</span>
          <span style={{ fontSize: 12, color: 'var(--cont)' }}>{channelName(r.channel_id)}</span>
          {canEdit && (
            <ConfirmDeleteButton
              label={t.notifications.delete}
              confirmLabel={t.common.confirm}
              cancelLabel={t.common.cancel}
              disabled={del.isPending}
              onConfirm={() => del.mutate(r.id)}
            />
          )}
        </div>
      ))}
      {canEdit && channels.length > 0 && (
        <div style={form}>
          <Field label={t.notifications.name}><Input value={name} onChange={e => setName(e.target.value)} /></Field>
          <Field label={t.notifications.severity}>
            <Select value={severity} onChange={e => setSeverity(e.target.value)}>
              <option value="">{t.notifications.any}</option>
              <option value="critical">critical</option>
              <option value="fail">fail</option>
              <option value="warn">warn</option>
            </Select>
          </Field>
          <Field label={t.notifications.kind}>
            <Select value={kind} onChange={e => setKind(e.target.value)}>
              <option value="">{t.notifications.any}</option>
              <option value="internal_gate">internal_gate</option>
              <option value="consumer_contract">consumer_contract</option>
              <option value="provider_contract">provider_contract</option>
            </Select>
          </Field>
          <Field label={t.notifications.space}><Input style={{ width: 90 }} value={space} onChange={e => setSpace(e.target.value)} /></Field>
          <Field label={t.notifications.product}><Input style={{ width: 110 }} value={product} onChange={e => setProduct(e.target.value)} /></Field>
          <Field label={t.notifications.channel}>
            <Select value={channelId} onChange={e => setChannelId(Number(e.target.value))}>
              {channels.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
            </Select>
          </Field>
          <Button variant="primary" disabled={create.isPending || !canSubmit} onClick={submit}>{t.notifications.addRule}</Button>
        </div>
      )}
    </Panel>
  );
}

// --- Qualitäts-Digest (V4) ---
function DigestSection() {
  const { data } = useDigestPreview();
  const send = useSendDigest();
  const role = useRoleStore(s => s.role);
  const canSend = role !== 'viewer'; // FE-Spiegel; Server verlangt steward+

  if (!data) return null;
  const kpi: React.CSSProperties = { display: 'flex', flexDirection: 'column', gap: 2, minWidth: 110 };
  const kpiLabel: React.CSSProperties = { fontSize: 10, color: 'var(--fg-3)', textTransform: 'uppercase' };
  const kpiValue: React.CSSProperties = { fontFamily: 'var(--font-mono)', fontSize: 16, fontWeight: 700 };

  return (
    <Panel title={t.notifications.digestTitle}>
      <p style={hint}>{t.notifications.digestHint}</p>
      <div style={{ display: 'flex', gap: 'var(--s5)', flexWrap: 'wrap', alignItems: 'flex-end' }}>
        <div style={kpi}>
          <span style={kpiLabel}>{t.notifications.digestKpiIncidents}</span>
          <span style={{ ...kpiValue, color: data.incidents_new > 0 ? 'var(--status-warn)' : 'var(--fg)' }}>{data.incidents_new}</span>
        </div>
        <div style={kpi}>
          <span style={kpiLabel}>{t.notifications.digestKpiOpen}</span>
          <span style={kpiValue}>{data.incidents_open}</span>
        </div>
        <div style={kpi}>
          <span style={kpiLabel}>{t.notifications.digestKpiRuns}</span>
          <span style={{ ...kpiValue, color: data.runs_failed > 0 ? 'var(--status-fail)' : 'var(--fg)' }}>
            {data.runs_failed}/{data.runs}
          </span>
        </div>
        <div style={kpi}>
          <span style={kpiLabel}>{t.notifications.digestKpiQuarantine}</span>
          <span style={kpiValue}>{data.quarantine_open}</span>
        </div>
        <div style={kpi}>
          <span style={kpiLabel}>{t.notifications.digestKpiDrift}</span>
          <span style={kpiValue}>{data.drift_objects}</span>
        </div>
        <div style={{ flex: 1 }} />
        {canSend && (
          <Button
            variant="primary"
            disabled={send.isPending || data.subscribed_channels === 0}
            onClick={() => send.mutate()}
          >
            {send.isPending ? t.notifications.digestSending : t.notifications.digestSendNow}
          </Button>
        )}
      </div>
      <p style={{ ...empty, marginTop: 'var(--s3)' }}>
        {t.notifications.digestPeriod.replace('{h}', String(data.period_hours))}
        {' · '}
        {t.notifications.digestSubscribed.replace('{n}', String(data.subscribed_channels))}
        {' · '}
        {t.notifications.digestLastSent}: {data.last_sent_at ? new Date(data.last_sent_at).toLocaleString() : t.notifications.digestNeverSent}
        {' · '}
        {data.enabled
          ? t.notifications.digestScheduleOn.replace('{h}', String(data.interval_hours))
          : t.notifications.digestScheduleOff}
      </p>
    </Panel>
  );
}

// --- Mute windows ---
function MutesSection({ mutes, canEdit }: { mutes: NotificationMute[]; canEdit: boolean }) {
  const create = useCreateMute();
  const del = useDeleteMute();
  const [reason, setReason] = useState('');
  const [space, setSpace] = useState('');
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');

  const canSubmit = Boolean(from && to);
  const submit = () => {
    if (!canSubmit) return;
    create.mutate(
      { reason: reason.trim(), match_space: space.trim(), starts_at: new Date(from).toISOString(), ends_at: new Date(to).toISOString() },
      { onSuccess: () => { setReason(''); setSpace(''); setFrom(''); setTo(''); } },
    );
  };

  return (
    <Panel title={`${t.notifications.mutesTitle} (${mutes.length})`}>
      <p style={hint}>{t.notifications.mutesHint}</p>
      {mutes.length === 0 && <p style={empty}>{t.notifications.noMutes}</p>}
      {mutes.map(m => {
        const st = muteState(m);
        return (
          <div key={m.id} style={row}>
            <span style={{ fontSize: 10, textTransform: 'uppercase', color: STATE_COLOR[st], border: `1px solid ${STATE_COLOR[st]}`, borderRadius: 'var(--r)', padding: '1px 6px', minWidth: 64, textAlign: 'center' }}>{t.notifications[st]}</span>
            <span style={{ fontSize: 12, flex: 1 }}>{m.reason || '—'}</span>
            <span style={{ fontSize: 11, color: 'var(--fg-3)' }}>{m.match_space || m.match_product || t.notifications.any}</span>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--fg-3)' }}>
              {new Date(m.starts_at).toLocaleString()} – {new Date(m.ends_at).toLocaleString()}
            </span>
            {canEdit && (
              <ConfirmDeleteButton
                label={t.notifications.delete}
                confirmLabel={t.common.confirm}
                cancelLabel={t.common.cancel}
                disabled={del.isPending}
                onConfirm={() => del.mutate(m.id)}
              />
            )}
          </div>
        );
      })}
      {canEdit && (
        <div style={form}>
          <Field label={t.notifications.reason}><Input value={reason} onChange={e => setReason(e.target.value)} /></Field>
          <Field label={t.notifications.space}><Input style={{ width: 90 }} value={space} onChange={e => setSpace(e.target.value)} /></Field>
          <Field label={t.notifications.from}><Input type="datetime-local" value={from} onChange={e => setFrom(e.target.value)} /></Field>
          <Field label={t.notifications.to}><Input type="datetime-local" value={to} onChange={e => setTo(e.target.value)} /></Field>
          <Button variant="primary" disabled={create.isPending || !canSubmit} onClick={submit}>{t.notifications.addMute}</Button>
        </div>
      )}
    </Panel>
  );
}

export default function Notifications() {
  const { data, isLoading, isError, refetch } = useNotificationConfig();
  const canEdit = data?.can_edit ?? false;

  return (
    <div className="page-full">
      <PageHeader title={t.notifications.title} subtitle={t.notifications.subtitle} />

      {isError && <ErrorBanner onRetry={() => refetch()} />}
      {isLoading && <p style={{ color: 'var(--fg-3)', fontSize: 12 }}>{t.common.loading}</p>}

      {data && (
        <>
          {!canEdit && <ReadOnlyBanner hint={t.notifications.readOnlyHint} />}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--s4)' }}>
            <DigestSection />
            <ChannelsSection channels={data.channels} canEdit={canEdit} />
            <RulesSection rules={data.rules} channels={data.channels} canEdit={canEdit} />
            <MutesSection mutes={data.mutes} canEdit={canEdit} />
          </div>
        </>
      )}
    </div>
  );
}
