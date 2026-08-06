import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { EXTRACT_STATUS_KEY } from './extract';

export interface ConnectorStatus {
  space_id: string;
  use_cli: boolean;
  cli_available: boolean;
  cli_logged_in: boolean;
  cli_host: string | null;
  catalog_configured: boolean;
  source_mode: 'cli' | 'catalog' | 'none';
  config_file: string;
  env_file: string;
  base_url: string;
  client_id: string;
  token_url: string;
  secret_configured: boolean;
  cli_client_id: string;
  cli_authorization_url: string;
  cli_token_url: string;
  cli_oauth_secrets_file: string;
  cli_secret_configured: boolean;
  login_command: string;
  file_space_id: string;
  file_use_cli: boolean;
  file_cli_host: string;
  file_base_url: string;
  file_client_id: string;
  file_token_url: string;
  file_cli_client_id: string;
  file_cli_authorization_url: string;
  file_cli_token_url: string;
  file_cli_oauth_secrets_file: string;
  env_space_id: string;
  env_use_cli: boolean;
  env_cli_host: string;
  env_base_url: string;
  env_client_id: string;
  env_token_url: string;
  env_cli_client_id: string;
  env_cli_authorization_url: string;
  env_cli_token_url: string;
  env_cli_oauth_secrets_file: string;
  env_has_space_id: boolean;
  env_has_use_cli: boolean;
  env_has_cli_host: boolean;
  env_has_base_url: boolean;
  env_has_client_id: boolean;
  env_has_client_secret: boolean;
  env_has_token_url: boolean;
  env_has_cli_client_id: boolean;
  env_has_cli_client_secret: boolean;
  env_has_cli_authorization_url: boolean;
  env_has_cli_token_url: boolean;
  env_has_cli_oauth_secrets_file: boolean;
}

export interface ConnectorSave {
  persist_target?: 'file' | 'env';
  space_id: string;
  use_cli: boolean;
  cli_host?: string;
  base_url?: string;
  client_id?: string;
  token_url?: string;
  client_secret?: string;
  clear_secret?: boolean;
  cli_client_id?: string;
  cli_authorization_url?: string;
  cli_token_url?: string;
  cli_oauth_secrets_file?: string;
  cli_client_secret?: string;
  clear_cli_secret?: boolean;
}

export interface ConnectorLoginStart {
  ok: boolean;
  command: string;
}

export function useConnectorStatus() {
  return useQuery<ConnectorStatus>({
    queryKey: ['connector-status'],
    queryFn: async () => {
      const resp = await fetch('/api/admin/connector');
      if (!resp.ok) throw new Error(`${resp.status}`);
      return resp.json();
    },
    staleTime: 30_000,
  });
}

export function useSaveConnector() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: ConnectorSave) => {
      const resp = await fetch('/api/admin/connector', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!resp.ok) throw new Error(`${resp.status}`);
      return resp.json() as Promise<ConnectorStatus>;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['connector-status'] });
      qc.invalidateQueries({ queryKey: EXTRACT_STATUS_KEY });
    },
  });
}

export function useStartConnectorLogin() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      const resp = await fetch('/api/admin/connector/login', { method: 'POST' });
      if (!resp.ok) throw new Error(`${resp.status}`);
      return resp.json() as Promise<ConnectorLoginStart>;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['connector-status'] });
    },
  });
}
