import { useState, type CSSProperties } from 'react';
import { useConnectorStatus, useSaveConnector, useStartConnectorLogin } from '@/api/connector';
import { Button } from '@/components/ui/Button';
import { Field, Input, Select } from '@/components/ui/Field';
import { Panel } from '@/components/ui/Panel';
import { Tooltip } from '@/components/ui/Tooltip';
import { t } from '@/i18n/de';

const muted: CSSProperties = { color: 'var(--fg-3)', fontSize: 12 };
const valueText: CSSProperties = { color: 'var(--fg)', fontSize: 13, fontWeight: 600 };
const infoBadge: CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  width: 18,
  height: 18,
  borderRadius: 'var(--r-full)',
  border: '1px solid var(--line-2)',
  color: 'var(--fg-3)',
  fontSize: 11,
  cursor: 'help',
};

function StatusLine({ ok, label, detail }: { ok: boolean; label: string; detail?: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--s2)', minHeight: 28 }}>
      <span style={{
        width: 8, height: 8, borderRadius: 'var(--r-full)',
        background: ok ? 'var(--status-pass)' : 'var(--status-warn)',
      }} />
      <span style={valueText}>{label}</span>
      {detail && <span style={muted}>{detail}</span>}
    </div>
  );
}

type PersistTarget = 'file' | 'env';

function SectionTitle({ title, tooltip }: { title: string; tooltip: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--s2)' }}>
      <p style={{ ...valueText, fontSize: 12, margin: 0 }}>{title}</p>
      <Tooltip content={tooltip}>
        <span aria-label={tooltip} style={infoBadge}>i</span>
      </Tooltip>
    </div>
  );
}

/** Datasphere connector config (space, CLI, REST OAuth) — shared by the Inventory
 *  Admin page and Settings. Self-contained: owns its own status/save queries. */
export function ConnectorPanel({ canEdit }: { canEdit: boolean }) {
  const { data, isLoading } = useConnectorStatus();
  const save = useSaveConnector();
  const startLogin = useStartConnectorLogin();
  const [persistTarget, setPersistTarget] = useState<PersistTarget | null>(null);
  const [spaceId, setSpaceId] = useState<string | null>(null);
  const [useCli, setUseCli] = useState<boolean | null>(null);
  const [cliHost, setCliHost] = useState<string | null>(null);
  const [baseUrl, setBaseUrl] = useState<string | null>(null);
  const [clientId, setClientId] = useState<string | null>(null);
  const [tokenUrl, setTokenUrl] = useState<string | null>(null);
  const [clientSecret, setClientSecret] = useState('');
  const [cliClientId, setCliClientId] = useState<string | null>(null);
  const [cliAuthorizationUrl, setCliAuthorizationUrl] = useState<string | null>(null);
  const [cliTokenUrl, setCliTokenUrl] = useState<string | null>(null);
  const [cliOauthSecretsFile, setCliOauthSecretsFile] = useState<string | null>(null);
  const [cliClientSecret, setCliClientSecret] = useState('');
  const [savedMsg, setSavedMsg] = useState('');

  const hasEnvConfig = Boolean(
    data?.env_space_id || data?.env_cli_host || data?.env_base_url || data?.env_client_id
    || data?.env_token_url || data?.env_cli_client_id || data?.env_cli_authorization_url
    || data?.env_cli_token_url || data?.env_cli_oauth_secrets_file || data?.env_use_cli,
  );
  const activeTarget: PersistTarget = persistTarget ?? (hasEnvConfig ? 'env' : 'file');
  const targetValue = (fileValue: string, envValue: string, localValue: string | null) => {
    if (localValue !== null) return localValue;
    return activeTarget === 'env' ? envValue : fileValue;
  };
  const targetBool = (fileValue: boolean, envValue: boolean, localValue: boolean | null) => {
    if (localValue !== null) return localValue;
    return activeTarget === 'env' ? envValue : fileValue;
  };

  const effectiveSpace = targetValue(data?.file_space_id ?? '', data?.env_space_id ?? '', spaceId);
  const effectiveUseCli = targetBool(data?.file_use_cli ?? false, data?.env_use_cli ?? false, useCli);
  const effectiveCliHost = targetValue(data?.file_cli_host ?? '', data?.env_cli_host ?? '', cliHost);
  const effectiveBaseUrl = targetValue(data?.file_base_url ?? '', data?.env_base_url ?? '', baseUrl);
  const effectiveClientId = targetValue(data?.file_client_id ?? '', data?.env_client_id ?? '', clientId);
  const effectiveTokenUrl = targetValue(data?.file_token_url ?? '', data?.env_token_url ?? '', tokenUrl);
  const effectiveCliClientId = targetValue(data?.file_cli_client_id ?? '', data?.env_cli_client_id ?? '', cliClientId);
  const effectiveCliAuthorizationUrl = targetValue(
    data?.file_cli_authorization_url ?? '',
    data?.env_cli_authorization_url ?? '',
    cliAuthorizationUrl,
  );
  const effectiveCliTokenUrl = targetValue(data?.file_cli_token_url ?? '', data?.env_cli_token_url ?? '', cliTokenUrl);
  const effectiveCliOauthSecretsFile = targetValue(
    data?.file_cli_oauth_secrets_file ?? '',
    data?.env_cli_oauth_secrets_file ?? '',
    cliOauthSecretsFile,
  );

  const envOverride = Boolean(
    data?.env_has_space_id || data?.env_has_use_cli || data?.env_has_cli_host
    || data?.env_has_base_url || data?.env_has_client_id || data?.env_has_client_secret
    || data?.env_has_token_url || data?.env_has_cli_client_id || data?.env_has_cli_client_secret
    || data?.env_has_cli_authorization_url || data?.env_has_cli_token_url || data?.env_has_cli_oauth_secrets_file,
  );

  const handleSave = () => {
    save.mutate(
      {
        persist_target: activeTarget,
        space_id: effectiveSpace,
        use_cli: effectiveUseCli,
        cli_host: effectiveCliHost,
        base_url: effectiveBaseUrl,
        client_id: effectiveClientId,
        token_url: effectiveTokenUrl,
        client_secret: clientSecret || undefined,
        cli_client_id: effectiveCliClientId,
        cli_authorization_url: effectiveCliAuthorizationUrl,
        cli_token_url: effectiveCliTokenUrl,
        cli_oauth_secrets_file: effectiveCliOauthSecretsFile,
        cli_client_secret: cliClientSecret || undefined,
      },
      {
        onSuccess: () => {
          setSavedMsg(t.connector.saved);
          setSpaceId(null); setUseCli(null); setCliHost(null);
          setBaseUrl(null); setClientId(null); setTokenUrl(null);
          setCliClientId(null); setCliAuthorizationUrl(null);
          setCliTokenUrl(null); setCliOauthSecretsFile(null);
          setClientSecret(''); setCliClientSecret('');
        },
        onError: () => setSavedMsg(t.connector.saveError),
      },
    );
  };

  const sourceDot = (mode: string | undefined) => {
    if (mode === 'cli' || mode === 'catalog') return 'var(--status-pass)';
    return 'var(--status-warn)';
  };

  const handleStartLogin = () => {
    startLogin.mutate(undefined, {
      onSuccess: () => setSavedMsg(t.connector.loginStarted),
      onError: () => setSavedMsg(t.connector.loginStartError),
    });
  };

  return (
    <Panel title={t.connector.title} family="observability">
      {isLoading && <p style={muted}>{t.common.loading}</p>}
      {data && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--s3)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--s2)' }}>
            <span style={{ width: 8, height: 8, borderRadius: 'var(--r-full)', background: sourceDot(data.source_mode), flexShrink: 0 }} />
            <span style={valueText}>
              {data.source_mode === 'cli' ? t.connector.sourceCli
                : data.source_mode === 'catalog' ? t.connector.sourceCatalog
                : t.connector.sourceNone}
            </span>
          </div>

          {data.cli_available && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--s1)' }}>
              <StatusLine ok={data.cli_available} label={t.connector.cliAvailable} />
              <StatusLine ok={data.cli_logged_in} label={data.cli_logged_in ? t.connector.cliLoggedIn : t.connector.cliNotLoggedIn}
                detail={data.cli_host ?? undefined} />
              {!data.cli_logged_in && (
                <>
                  <pre style={{ ...muted, fontSize: 11, margin: 0, whiteSpace: 'pre-wrap' }}>
                    {data.login_command || t.connector.loginHint}
                  </pre>
                  {canEdit && (
                    <Button size="sm" disabled={startLogin.isPending} onClick={handleStartLogin}>
                      {t.connector.openLogin}
                    </Button>
                  )}
                </>
              )}
            </div>
          )}
          {!data.cli_available && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--s1)' }}>
              <StatusLine ok={false} label={t.connector.cliMissing} />
              <pre style={{ ...muted, fontSize: 11, margin: 0, whiteSpace: 'pre-wrap' }}>{t.connector.installHint}</pre>
            </div>
          )}

          <div style={{ borderTop: '1px solid var(--line)', paddingTop: 'var(--s3)', display: 'grid', gap: 'var(--s3)' }}>
            {envOverride && <p style={{ ...muted, fontSize: 11 }}>{t.connector.envOverride}</p>}
            {canEdit && (
              <Field label={t.connector.persistTarget} hint={t.connector.persistTargetHint}>
                <Select
                  value={activeTarget}
                  onChange={e => setPersistTarget(e.target.value as PersistTarget)}
                  style={{ width: '100%' }}
                >
                  <option value="file">{t.connector.persistFile.replace('{path}', data.config_file)}</option>
                  <option value="env">{t.connector.persistEnv.replace('{path}', data.env_file)}</option>
                </Select>
              </Field>
            )}
            <Field label={t.connector.spaceId} hint={t.connector.spaceIdHint}>
              <Input
                value={effectiveSpace}
                disabled={!canEdit || Boolean(data.env_has_space_id)}
                onChange={e => setSpaceId(e.target.value)}
                style={{ width: '100%' }}
              />
            </Field>
            <label style={{ display: 'flex', alignItems: 'center', gap: 'var(--s2)', fontSize: 12, color: 'var(--fg-2)' }}>
              <input
                type="checkbox"
                checked={effectiveUseCli}
                disabled={!canEdit || data.env_has_use_cli}
                onChange={e => setUseCli(e.target.checked)}
              />
              {t.connector.useCli}
            </label>
            <Field label={t.connector.cliHost} hint={t.connector.cliHostHint}>
              <Input
                value={effectiveCliHost}
                disabled={!canEdit || data.env_has_cli_host}
                onChange={e => setCliHost(e.target.value)}
                placeholder="my-tenant.eu10.hcs.cloud.sap"
                style={{ width: '100%' }}
              />
            </Field>

            <div style={{ borderTop: '1px solid var(--line)', paddingTop: 'var(--s3)', display: 'grid', gap: 'var(--s3)' }}>
              <SectionTitle title={t.connector.restTitle} tooltip={t.connector.restUsageTooltip} />
              <p style={{ ...muted, fontSize: 11, margin: 0 }}>{t.connector.restHint}</p>
              <Field label={t.connector.baseUrl}>
                <Input
                  value={effectiveBaseUrl}
                  disabled={!canEdit || Boolean(data.env_has_base_url)}
                  onChange={e => setBaseUrl(e.target.value)}
                  placeholder="https://my-tenant.eu10.hcs.cloud.sap"
                  style={{ width: '100%' }}
                />
              </Field>
              <Field label={t.connector.clientId}>
                <Input
                  value={effectiveClientId}
                  disabled={!canEdit || Boolean(data.env_has_client_id)}
                  onChange={e => setClientId(e.target.value)}
                  autoComplete="off"
                  style={{ width: '100%' }}
                />
              </Field>
              <Field label={t.connector.tokenUrl} hint={t.connector.tokenUrlHint}>
                <Input
                  value={effectiveTokenUrl}
                  disabled={!canEdit || Boolean(data.env_has_token_url)}
                  onChange={e => setTokenUrl(e.target.value)}
                  placeholder="https://my-tenant.authentication.eu10.hana.ondemand.com/oauth/token"
                  style={{ width: '100%' }}
                />
              </Field>
              <Field
                label={t.connector.clientSecret}
                hint={data.secret_configured ? t.connector.secretKeepHint : t.connector.secretHint}
              >
                <Input
                  type="password"
                  value={clientSecret}
                  disabled={!canEdit || Boolean(data.env_has_client_secret)}
                  onChange={e => setClientSecret(e.target.value)}
                  autoComplete="new-password"
                  placeholder={data.secret_configured ? '••••••••' : ''}
                  style={{ width: '100%' }}
                />
              </Field>
              <StatusLine ok={data.secret_configured} label={data.secret_configured ? t.connector.secretSet : t.connector.secretMissing} />
            </div>

            <div style={{ borderTop: '1px solid var(--line)', paddingTop: 'var(--s3)', display: 'grid', gap: 'var(--s3)' }}>
              <SectionTitle title={t.connector.cliAuthTitle} tooltip={t.connector.cliUsageTooltip} />
              <p style={{ ...muted, fontSize: 11, margin: 0 }}>{t.connector.cliAuthHint}</p>
              <Field label={t.connector.cliClientId}>
                <Input
                  value={effectiveCliClientId}
                  disabled={!canEdit || Boolean(data.env_has_cli_client_id)}
                  onChange={e => setCliClientId(e.target.value)}
                  autoComplete="off"
                  style={{ width: '100%' }}
                />
              </Field>
              <Field
                label={t.connector.cliClientSecret}
                hint={data.cli_secret_configured ? t.connector.secretKeepHint : t.connector.cliSecretHint}
              >
                <Input
                  type="password"
                  value={cliClientSecret}
                  disabled={!canEdit || Boolean(data.env_has_cli_client_secret)}
                  onChange={e => setCliClientSecret(e.target.value)}
                  autoComplete="new-password"
                  placeholder={data.cli_secret_configured ? '••••••••' : ''}
                  style={{ width: '100%' }}
                />
              </Field>
              <Field label={t.connector.authorizationUrl} hint={t.connector.authorizationUrlHint}>
                <Input
                  value={effectiveCliAuthorizationUrl}
                  disabled={!canEdit || Boolean(data.env_has_cli_authorization_url)}
                  onChange={e => setCliAuthorizationUrl(e.target.value)}
                  placeholder="https://my-tenant.authentication.eu10.hana.ondemand.com/oauth/authorize"
                  style={{ width: '100%' }}
                />
              </Field>
              <Field label={t.connector.cliTokenUrl} hint={t.connector.cliTokenUrlHint}>
                <Input
                  value={effectiveCliTokenUrl}
                  disabled={!canEdit || Boolean(data.env_has_cli_token_url)}
                  onChange={e => setCliTokenUrl(e.target.value)}
                  placeholder="https://my-tenant.authentication.eu10.hana.ondemand.com/oauth/token"
                  style={{ width: '100%' }}
                />
              </Field>
              <Field label={t.connector.oauthSecretsFile} hint={t.connector.oauthSecretsFileHint}>
                <Input
                  value={effectiveCliOauthSecretsFile}
                  disabled={!canEdit || Boolean(data.env_has_cli_oauth_secrets_file)}
                  onChange={e => setCliOauthSecretsFile(e.target.value)}
                  placeholder="C:\\...\\datasphere-secrets.json"
                  style={{ width: '100%' }}
                />
              </Field>
              <StatusLine
                ok={data.cli_secret_configured}
                label={data.cli_secret_configured ? t.connector.cliSecretSet : t.connector.cliSecretMissing}
              />
            </div>

            {canEdit && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--s3)' }}>
                <Button variant="primary" disabled={save.isPending} onClick={handleSave}>{t.connector.save}</Button>
                {savedMsg && <span style={{ fontSize: 12, color: save.isError ? 'var(--status-fail)' : 'var(--fg-3)' }}>{savedMsg}</span>}
              </div>
            )}
          </div>
        </div>
      )}
    </Panel>
  );
}
