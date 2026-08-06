import axios from 'axios';
import { useRoleStore } from '@/store/role';

// Shared axios instance for all API hooks. Endpoint-specific calls live in the
// `api/*.ts` hook modules; this module only owns the base configuration.
export const api = axios.create({
  baseURL: '/api',
  headers: { 'Content-Type': 'application/json' },
});

// [AUTHZ] Mirror the active UI role to the server via X-DQ-Role. In noauth/dev
// mode the backend honours this header for role simulation (auth/provider.py);
// under real auth it is ignored in favour of the OIDC token. Reading from the
// store at request time keeps the header in sync after a role switch.
api.interceptors.request.use((config) => {
  config.headers.set('X-DQ-Role', useRoleStore.getState().role);
  return config;
});
