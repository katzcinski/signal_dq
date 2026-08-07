import { create } from 'zustand';
import { persist } from 'zustand/middleware';

// [AUTHZ] Frontend mirror of the server role model (auth/provider.py:VALID_ROLES).
// The server is authoritative: this store only drives which write affordances the
// UI offers and the X-DQ-Role header sent in dev/noauth mode (api/client.ts). It
// never grants access — a disabled button is a hint, not a gate.
export type Role = 'viewer' | 'steward' | 'owner' | 'admin';

export const ROLES: Role[] = ['viewer', 'steward', 'owner', 'admin'];

export interface RoleMeta {
  label: string;
  hint: string;
  /** Default landing route on role switch (UX-N3). */
  home: string;
}

export const ROLE_META: Record<Role, RoleMeta> = {
  viewer:  { label: 'Viewer',         hint: 'Nur-Lese-Zugriff auf Health, Objekte und Compliance.', home: '/' },
  steward: { label: 'Steward',        hint: 'Pflegt Internal Gates, bearbeitet Incidents und Contracts.', home: '/my' },
  owner:   { label: 'Product-Owner',  hint: 'Gates und Contracts für eigene Produkte.',             home: '/my' },
  admin:   { label: 'Platform-Admin', hint: 'Vollzugriff auf alle Objekte und Aktionen.',           home: '/' },
};

interface RoleState {
  role: Role;
  setRole: (r: Role) => void;
}

export const useRoleStore = create<RoleState>()(
  persist(
    (set) => ({
      role: 'steward',
      setRole: (role) => set({ role }),
    }),
    { name: 'signal-role' },
  ),
);

// ─── Permission mirror (auth/provider.py:Principal) ──────────────────────────
// owner-membership (sub/groups) is not known to the FE in noauth mode, so these
// helpers reflect only the role × owned_by axis. The server still enforces the
// full rule; FE stays permissive-toward-server (shows the action, lets the 403
// surface) only where ownership could grant access it can't see.

/** Mirror of Principal.can_write_contract for the role axis. */
export function canWriteContract(role: Role, ownedBy: string | undefined): boolean {
  if (role === 'admin') return true;
  if (ownedBy === 'platform') return role === 'steward' || role === 'owner';
  if (ownedBy === 'product') return role === 'owner';
  // Unknown ownership: defer to server, keep the affordance for writer roles.
  return role === 'owner' || role === 'steward';
}

/** Incident transitions require steward role or higher (routers/incidents.py:124). */
export function canActOnIncidents(role: Role): boolean {
  return role !== 'viewer';
}

/** Quarantäne-Freigabe/Reprocess erfordert steward+ (routers/quarantine.py). */
export function canActOnQuarantine(role: Role): boolean {
  return role !== 'viewer';
}

/** Enforcement-Apply/Probe = DDL im Tenant-Schema → owner+ (routers/enforcement.py). */
export function canApplyEnforcement(role: Role): boolean {
  return role === 'owner' || role === 'admin';
}

/** UX-N2: notification config is platform-wide → platform-owner (admin) only. */
export function canManageNotifications(role: Role): boolean {
  return role === 'admin';
}

/** HANA/Datasphere connection details may include credentials → admin only. */
export function canManageEnvironments(role: Role): boolean {
  return role === 'admin';
}

/** Accepting a proposal writes a guarantee → same gate as the contract. */
export function canManageInventory(role: Role): boolean {
  return role === 'admin';
}

export function canAcceptProposal(role: Role, ownedBy?: string): boolean {
  return canWriteContract(role, ownedBy);
}

/** Profiling hits live HANA and requires steward role or higher. */
export function canProfileObject(role: Role): boolean {
  return role !== 'viewer';
}

/** Triggering runs loads HANA and requires steward role or higher
 *  (routers/objects.py:trigger_run). */
export function canRunChecks(role: Role): boolean {
  return role !== 'viewer';
}

/** Managing schedules mirrors run-trigger authority — steward role or higher
 *  (routers/schedules.py:_require_steward). */
export function canManageSchedules(role: Role): boolean {
  return role !== 'viewer';
}
