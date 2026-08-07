import { useState } from 'react';
import { Panel } from '@/components/ui/Panel';
import { Button } from '@/components/ui/Button';
import { Field, Input } from '@/components/ui/Field';
import { ErrorBanner } from '@/components/ui/ErrorBanner';
import { PageHeader } from '@/components/ui/PageHeader';
import { ReadOnlyBanner } from '@/components/ui/ReadOnlyBanner';
import { OperationProgress } from '@/components/OperationProgress';
import { ConnectorPanel } from '@/components/ConnectorPanel';
import {
  useAdminEnvironments, useCreateEnvironment, useUpdateEnvironment, useDeleteEnvironment,
  useStartConnectionTest, useOperationStream, type EnvironmentInput,
} from '@/api/environments';
import { useEntropyConfig } from '@/api/integrations';
import { t } from '@/i18n/de';
import { canManageEnvironments, useRoleStore } from '@/store/role';
import type { AdminEnvironment, ConnectionTestResult } from '@/types';

const row: React.CSSProperties = {
  display: 'flex', alignItems: 'center', gap: 'var(--s3)',
  padding: 'var(--s2) 0', borderBottom: '1px solid var(--line)', flexWrap: 'wrap',
};
const mono: React.CSSProperties = { fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--fg-3)' };
const hint: React.CSSProperties = { fontSize: 11, color: 'var(--fg-3)', marginBottom: 'var(--s3)' };
const empty: React.CSSProperties = { fontSize: 12, color: 'var(--fg-3)' };
const chip = (color: string): React.CSSProperties => ({
  fontSize: 10, textTransform: 'uppercase', color, border: `1px solid ${color}`,
  borderRadius: 'var(--r)', padding: '1px 6px', whiteSpace: 'nowrap',
});

interface FormState {
  name: string; host: string; port: string; user: string;
  schema: string; passwordRef: string; encrypt: boolean; validateCert: boolean;
}

const emptyForm: FormState = {
  name: '', host: '', port: '443', user: '', schema: '', passwordRef: '',
  encrypt: true, validateCert: true,
};

function toForm(env: AdminEnvironment): FormState {
  return {
    name: env.name, host: env.host, port: String(env.port), user: env.user,
    schema: env.schema, passwordRef: '', encrypt: env.encrypt, validateCert: env.validate_cert,
  };
}

// --- Live connection test result, polled from the operations endpoint ---
function ConnectionTest({ name, canTest }: { name: string; canTest: boolean }) {
  const start = useStartConnectionTest();
  const [opId, setOpId] = useState<string | null>(null);
  const { data: op } = useOperationStream<ConnectionTestResult>(opId);

  const running = start.isPending || (!!op && op.state === 'running');
  const result = op?.state === 'finished' || op?.state === 'error' ? op : null;

  const onTest = () => {
    setOpId(null);
    start.mutate(name, { onSuccess: (d) => setOpId(d.op_id) });
  };

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--s2)', flexWrap: 'wrap' }}>
      <Button variant="secondary" size="sm" disabled={!canTest || running} onClick={onTest}>
        {running ? t.settings.testing : t.settings.test}
      </Button>
      {running && op?.progress?.length ? (
        <span style={mono}>{op.progress[op.progress.length - 1].line}</span>
      ) : null}
      {result && result.result && (
        <span style={chip(result.result.ok ? 'var(--status-pass)' : 'var(--status-fail)')}>
          {result.result.ok ? t.settings.testOk : t.settings.testFailed}
        </span>
      )}
      {result?.result?.ok && (
        <span style={mono}>
          {t.settings.latency}: {result.result.latency_ms}ms
          {result.result.server_version ? ` · ${t.settings.serverVersion}: ${result.result.server_version}` : ''}
        </span>
      )}
      {result && !result.result?.ok && (
        <span style={{ ...mono, color: 'var(--status-fail)' }}>
          {result.result?.error || result.error || t.settings.testFailed}
        </span>
      )}
      {opId && (
        <div style={{ flexBasis: '100%', marginTop: 'var(--s2)' }}>
          <OperationProgress operation={op} />
        </div>
      )}
    </div>
  );
}

// --- Add/edit form ---
function EnvironmentForm({ initial, onDone }: { initial: AdminEnvironment | null; onDone: () => void }) {
  const isEdit = !!initial;
  const create = useCreateEnvironment();
  const update = useUpdateEnvironment();
  const [f, setF] = useState<FormState>(initial ? toForm(initial) : emptyForm);
  const set = <K extends keyof FormState>(k: K, v: FormState[K]) => setF(s => ({ ...s, [k]: v }));

  const pending = create.isPending || update.isPending;
  const valid = f.host.trim() && f.user.trim() && (isEdit || f.name.trim());

  const submit = () => {
    if (!valid) return;
    const body: EnvironmentInput = {
      host: f.host.trim(),
      port: Number(f.port) || 443,
      user: f.user.trim(),
      schema: f.schema.trim(),
      password_ref: f.passwordRef.trim(),
      encrypt: f.encrypt,
      validate_cert: f.validateCert,
    };
    const mut = isEdit ? update : create;
    mut.mutate({ name: isEdit ? initial!.name : f.name.trim(), ...body }, { onSuccess: onDone });
  };

  return (
    <div style={{
      border: '1px solid var(--line-2)', borderRadius: 'var(--r-md)',
      padding: 'var(--s3)', marginTop: 'var(--s3)', background: 'var(--bg-2)',
    }}>
      <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 'var(--s2)' }}>
        {isEdit ? `${t.settings.editEnvironment} — ${initial!.name}` : t.settings.newEnvironment}
      </div>
      <div style={{ display: 'flex', gap: 'var(--s2)', flexWrap: 'wrap', alignItems: 'flex-end' }}>
        {!isEdit && (
          <Field label={t.settings.name}>
            <Input value={f.name} onChange={e => set('name', e.target.value)} placeholder="prod" />
          </Field>
        )}
        <Field label={t.settings.host} style={{ flex: 1, minWidth: 180 }}>
          <Input style={{ width: '100%' }} value={f.host} onChange={e => set('host', e.target.value)}
            placeholder="hana.eu10.hcs.cloud.sap" />
        </Field>
        <Field label={t.settings.port}>
          <Input style={{ width: 80 }} type="number" value={f.port} onChange={e => set('port', e.target.value)} />
        </Field>
        <Field label={t.settings.user}>
          <Input value={f.user} onChange={e => set('user', e.target.value)} placeholder="SIGNAL_RO" />
        </Field>
        <Field label={t.settings.schema}>
          <Input value={f.schema} onChange={e => set('schema', e.target.value)} placeholder="CORE" />
        </Field>
      </div>
      <div style={{ marginTop: 'var(--s2)' }}>
        <Field
          label={t.settings.passwordRef}
          hint={isEdit ? t.settings.passwordRefKeep : t.settings.passwordRefHint}
          style={{ maxWidth: 420 }}
        >
          <Input style={{ width: '100%' }} value={f.passwordRef} autoComplete="off"
            onChange={e => set('passwordRef', e.target.value)} placeholder="env:HANA_PW_PROD" />
        </Field>
      </div>
      <div style={{ display: 'flex', gap: 'var(--s4)', marginTop: 'var(--s2)' }}>
        <label style={{ fontSize: 11, color: 'var(--fg-2)', display: 'inline-flex', alignItems: 'center', gap: 'var(--s1)' }}>
          <input type="checkbox" checked={f.encrypt} onChange={e => set('encrypt', e.target.checked)} />
          {t.settings.encrypt}
        </label>
        <label style={{ fontSize: 11, color: 'var(--fg-2)', display: 'inline-flex', alignItems: 'center', gap: 'var(--s1)' }}>
          <input type="checkbox" checked={f.validateCert} onChange={e => set('validateCert', e.target.checked)} />
          {t.settings.validateCert}
        </label>
      </div>
      {!valid && <p style={{ ...hint, marginTop: 'var(--s2)', marginBottom: 0 }}>{t.settings.requiredHint}</p>}
      <div style={{ display: 'flex', gap: 'var(--s2)', marginTop: 'var(--s3)', justifyContent: 'flex-end' }}>
        <Button variant="ghost" size="sm" onClick={onDone}>{t.settings.cancel}</Button>
        <Button variant="primary" size="sm" disabled={!valid || pending} onClick={submit}>
          {isEdit ? t.settings.save : t.settings.create}
        </Button>
      </div>
    </div>
  );
}

function ConnectionsSection({ environments, canEdit }: { environments: AdminEnvironment[]; canEdit: boolean }) {
  const del = useDeleteEnvironment();
  const [editing, setEditing] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);

  return (
    <Panel
      title={`${t.settings.connectionsTitle} (${environments.length})`}
      actions={canEdit && !adding ? (
        <Button variant="secondary" size="sm" onClick={() => { setAdding(true); setEditing(null); }}>
          {t.settings.addEnvironment}
        </Button>
      ) : undefined}
    >
      <p style={hint}>{t.settings.connectionsHint}</p>
      {environments.length === 0 && !adding && <p style={empty}>{t.settings.noEnvironments}</p>}

      {environments.map(env => (
        <div key={env.name}>
          <div style={row}>
            <span style={{ fontSize: 12, fontWeight: 600, minWidth: 90 }}>{env.name}</span>
            <span style={mono}>{env.user}@{env.host}:{env.port}</span>
            {env.schema && <span style={chip('var(--cont)')}>{env.schema}</span>}
            <span style={chip(env.password_set ? 'var(--status-pass)' : 'var(--status-warn)')}>
              {env.password_set ? t.settings.passwordSet : t.settings.passwordMissing}
            </span>
            {!env.encrypt && <span style={chip('var(--status-warn)')}>no-tls</span>}
            <div style={{ flex: 1 }} />
            {canEdit && (
              <>
                <Button variant="ghost" size="sm" onClick={() => {
                  setEditing(env.name); setAdding(false);
                }}>
                  {t.settings.edit}
                </Button>
                <Button variant="danger" size="sm"
                  onClick={() => { if (confirm(t.settings.deleteConfirm)) del.mutate(env.name); }}>
                  {t.settings.delete}
                </Button>
              </>
            )}
          </div>
          {canEdit && (
            <ConnectionTest name={env.name} canTest={env.password_set} />
          )}
          {editing === env.name && (
            <EnvironmentForm initial={env} onDone={() => setEditing(null)} />
          )}
        </div>
      ))}

      {adding && <EnvironmentForm initial={null} onDone={() => setAdding(false)} />}
    </Panel>
  );
}

function EntropySection() {
  const { data, isLoading } = useEntropyConfig();

  const modeColor =
    data?.mode === 'live' ? 'var(--status-pass)'
      : data?.mode === 'dry_run' ? 'var(--status-warn)'
        : 'var(--fg-3)';
  const modeLabel =
    data?.mode === 'live' ? t.entropy.modeLive
      : data?.mode === 'dry_run' ? t.entropy.modeDryRun
        : t.entropy.modeOff;
  const modeHint =
    data?.mode === 'live' ? t.entropy.modeLiveHint
      : data?.mode === 'dry_run' ? t.entropy.modeDryRunHint
        : t.entropy.modeOffHint;

  return (
    <Panel title={t.entropy.title}>
      <p style={hint}>{t.entropy.hint}</p>
      {isLoading && <p style={empty}>{t.common.loading}</p>}
      {data && (
        <>
          <div style={row}>
            <span style={{ fontSize: 12, fontWeight: 600, minWidth: 90 }}>{t.entropy.status}</span>
            <span style={chip(modeColor)}>{modeLabel}</span>
            <span style={chip(data.url_set ? 'var(--status-pass)' : 'var(--status-warn)')}>
              {data.url_set ? t.entropy.urlSet : t.entropy.urlMissing}
            </span>
            <span style={chip(data.token_set ? 'var(--status-pass)' : 'var(--status-warn)')}>
              {data.token_set ? t.entropy.tokenSet : t.entropy.tokenMissing}
            </span>
            <span style={chip('var(--cont)')}>{t.entropy.allowlist}: {data.allowlist_count}</span>
          </div>
          <div style={row}>
            <span style={{ fontSize: 12, fontWeight: 600, minWidth: 90 }}>{t.entropy.sourceOfTruth}</span>
            <span style={chip('var(--cont)')}>
              {data.source_of_truth === 'signal' ? t.entropy.sotSignal : t.entropy.sotEntropy}
            </span>
            <span style={chip(data.marketplace_verified ? 'var(--status-pass)' : 'var(--status-warn)')}>
              {data.marketplace_verified ? t.entropy.verified : t.entropy.unverified}
            </span>
          </div>
          <p style={{ ...hint, marginTop: 'var(--s2)', marginBottom: 0 }}>{modeHint}</p>
          {!data.marketplace_verified && (
            <p style={{ ...hint, marginBottom: 0, color: 'var(--status-warn)' }}>
              {t.entropy.validationPending}
            </p>
          )}
          <p style={{ ...hint, marginBottom: 0 }}>{t.entropy.envOnlyHint}</p>
        </>
      )}
    </Panel>
  );
}

export default function Settings() {
  const { data, isLoading, isError, refetch } = useAdminEnvironments();
  const role = useRoleStore(s => s.role);
  const canEdit = data?.can_edit ?? false;
  const canEditConnector = canManageEnvironments(role);

  return (
    <div className="page-full">
      <PageHeader title={t.settings.title} subtitle={t.settings.subtitle} />

      {isError && <ErrorBanner onRetry={() => refetch()} />}
      {isLoading && <p style={{ color: 'var(--fg-3)', fontSize: 12 }}>{t.common.loading}</p>}

      {data && (
        <>
          {!canEdit && <ReadOnlyBanner hint={t.settings.readOnlyHint} />}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--s4)' }}>
            <ConnectionsSection environments={data.environments} canEdit={canEdit} />
            <ConnectorPanel canEdit={canEditConnector} />
            <EntropySection />
          </div>
        </>
      )}
    </div>
  );
}
