import { useState } from 'react';
import { useEnvironments } from '@/api/objects';
import { useStartConnectionTest, useOperationStream } from '@/api/environments';
import { OperationProgress } from '@/components/OperationProgress';
import { Panel } from '@/components/ui/Panel';
import { Button } from '@/components/ui/Button';
import { ErrorBanner } from '@/components/ui/ErrorBanner';
import { PageHeader } from '@/components/ui/PageHeader';
import { ReadOnlyBanner } from '@/components/ui/ReadOnlyBanner';
import { t } from '@/i18n/de';
import { useRoleStore } from '@/store/role';
import type { ConnectionTestResult, Environment } from '@/types';

const row: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'minmax(120px, 1fr) minmax(120px, 1fr) minmax(120px, 1fr) auto',
  gap: 'var(--s3)',
  alignItems: 'center',
  padding: 'var(--s2) 0',
  borderBottom: '1px solid var(--line)',
};

const mono: React.CSSProperties = {
  color: 'var(--fg-3)',
  fontFamily: 'var(--font-mono)',
  fontSize: 11,
};

const chip = (color: string): React.CSSProperties => ({
  color,
  border: `1px solid ${color}`,
  borderRadius: 'var(--r)',
  fontSize: 10,
  padding: '1px 6px',
  textTransform: 'uppercase',
  whiteSpace: 'nowrap',
});


function ConnectionTest({ env, canTest }: { env: Environment; canTest: boolean }) {
  const start = useStartConnectionTest();
  const [opId, setOpId] = useState<string | null>(null);
  const { data: op } = useOperationStream<ConnectionTestResult>(opId);
  const running = start.isPending || op?.state === 'running';
  const result = op?.state === 'finished' || op?.state === 'error' ? op : null;

  const onStart = () => {
    setOpId(null);
    start.mutate(env.name, { onSuccess: data => setOpId(data.op_id) });
  };

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 'var(--s2)', alignItems: 'center' }}>
        {result?.result && (
          <span style={chip(result.result.ok ? 'var(--status-pass)' : 'var(--status-fail)')}>
            {result.result.ok ? t.settings.testOk : t.settings.testFailed}
          </span>
        )}
        <Button variant="secondary" size="sm" disabled={!canTest || running} onClick={onStart}>
          {running ? t.settings.testing : t.settings.test}
        </Button>
      </div>
      {result?.result?.ok && (
        <div style={{ ...mono, textAlign: 'right', marginTop: 4 }}>
          {t.settings.latency}: {result.result.latency_ms}ms
          {result.result.server_version ? ` | ${t.settings.serverVersion}: ${result.result.server_version}` : ''}
          {result.result.schema_visible ? ` | ${t.settings.schemaVisible}` : ''}
        </div>
      )}
      {result && !result.result?.ok && (
        <div style={{ ...mono, color: 'var(--status-fail)', textAlign: 'right', marginTop: 4 }}>
          {result.result?.error || result.error || t.settings.testFailed}
        </div>
      )}
      {opId && (
        <div style={{ marginTop: 'var(--s2)' }}>
          <OperationProgress operation={op} />
        </div>
      )}
    </div>
  );
}

function EnvironmentRow({ env, canTest }: { env: Environment; canTest: boolean }) {
  return (
    <div style={row}>
      <div>
        <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--fg)' }}>{env.name}</div>
      </div>
      <div style={mono}>{env.host || '-'}</div>
      <div style={{ display: 'flex', gap: 'var(--s2)', flexWrap: 'wrap' }}>
        {env.schema && <span style={chip('var(--cont)')}>{env.schema}</span>}
        <span style={chip(env.secret_status ? 'var(--status-pass)' : 'var(--status-warn)')}>
          {env.secret_status ? t.settings.passwordSet : t.settings.passwordMissing}
        </span>
      </div>
      <div>
        <ConnectionTest env={env} canTest={canTest && !!env.secret_status} />
      </div>
    </div>
  );
}

export default function Environments() {
  const { data, isLoading, isError, refetch } = useEnvironments();
  const role = useRoleStore(s => s.role);
  const canTest = role !== 'viewer';
  const environments = data?.environments ?? [];

  return (
    <div className="page-full">
      <PageHeader title={t.environments.title} subtitle={t.environments.subtitle} />

      {!canTest && <ReadOnlyBanner hint={t.environments.readOnlyHint} />}
      {isError && <ErrorBanner onRetry={() => refetch()} />}
      {isLoading && <p style={{ color: 'var(--fg-3)', fontSize: 12 }}>{t.common.loading}</p>}

      <Panel title={`${t.environments.listTitle} (${environments.length})`}>
        {environments.length === 0 ? (
          <p style={{ color: 'var(--fg-3)', fontSize: 12 }}>{t.environments.noEnvironments}</p>
        ) : (
          <div>
            {environments.map(env => (
              <EnvironmentRow key={env.name} env={env} canTest={canTest} />
            ))}
          </div>
        )}
      </Panel>
    </div>
  );
}
