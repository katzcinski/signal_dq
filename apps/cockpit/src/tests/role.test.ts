import { describe, it, expect } from 'vitest';
import { canWriteContract, canActOnIncidents, canAcceptProposal, canManageInventory, canProfileObject, ROLE_META } from '@/store/role';
import { navForRole } from '@/components/layout/Sidebar';

// FE permission mirror of auth/provider.py:Principal. The server stays
// authoritative; these guard the affordances the UI offers per role.
describe('canWriteContract', () => {
  it('admin can write anything', () => {
    expect(canWriteContract('admin', 'platform')).toBe(true);
    expect(canWriteContract('admin', 'product')).toBe(true);
    expect(canWriteContract('admin', undefined)).toBe(true);
  });

  it('steward writes platform but not product', () => {
    expect(canWriteContract('steward', 'platform')).toBe(true);
    expect(canWriteContract('steward', 'product')).toBe(false);
  });

  it('owner writes both platform and product', () => {
    expect(canWriteContract('owner', 'platform')).toBe(true);
    expect(canWriteContract('owner', 'product')).toBe(true);
  });

  it('viewer writes nothing', () => {
    expect(canWriteContract('viewer', 'platform')).toBe(false);
    expect(canWriteContract('viewer', 'product')).toBe(false);
    expect(canWriteContract('viewer', undefined)).toBe(false);
  });
});

describe('canActOnIncidents', () => {
  it('requires steward role or higher', () => {
    expect(canActOnIncidents('viewer')).toBe(false);
    expect(canActOnIncidents('steward')).toBe(true);
    expect(canActOnIncidents('owner')).toBe(true);
    expect(canActOnIncidents('admin')).toBe(true);
  });
});

describe('canAcceptProposal', () => {
  it('follows the contract write rule', () => {
    expect(canAcceptProposal('viewer')).toBe(false);
    expect(canAcceptProposal('steward', 'platform')).toBe(true);
    expect(canAcceptProposal('steward', 'product')).toBe(false);
  });
});

describe('canProfileObject', () => {
  it('requires steward role or higher', () => {
    expect(canProfileObject('viewer')).toBe(false);
    expect(canProfileObject('steward')).toBe(true);
    expect(canProfileObject('owner')).toBe(true);
    expect(canProfileObject('admin')).toBe(true);
  });
});

describe('canManageInventory', () => {
  it('requires admin role', () => {
    expect(canManageInventory('viewer')).toBe(false);
    expect(canManageInventory('steward')).toBe(false);
    expect(canManageInventory('owner')).toBe(false);
    expect(canManageInventory('admin')).toBe(true);
  });
});

describe('ROLE_META', () => {
  it('routes writer roles to the My-work landing', () => {
    expect(ROLE_META.steward.home).toBe('/my');
    expect(ROLE_META.owner.home).toBe('/my');
    expect(ROLE_META.viewer.home).toBe('/');
    expect(ROLE_META.admin.home).toBe('/');
  });
});

describe('ROLE_META homes', () => {
  it('viewer lands on Health (/)', () => {
    expect(ROLE_META.viewer.home).toBe('/');
  });

  it('steward lands on My Work (/my)', () => {
    expect(ROLE_META.steward.home).toBe('/my');
  });

  it('owner lands on My Work (/my)', () => {
    expect(ROLE_META.owner.home).toBe('/my');
  });

  it('admin lands on Health (/)', () => {
    expect(ROLE_META.admin.home).toBe('/');
  });
});

describe('navForRole', () => {
  it('groups DQ, governance, and utility entries with dividers', () => {
    const entries = navForRole('viewer').map(entry => entry === 'divider' ? 'divider' : entry.to);

    expect(entries).toEqual([
      '/',
      '/objects',
      '/products',
      '/lineage',
      '/schema-drift',
      '/incidents',
      // Healing/Schedules/Enforcement sind steward+ — für Viewer nicht in der Leiste.
      '/quarantine',
      '/proposals',
      '/library',
      'divider',
      '/contracts',
      '/compliance',
      'divider',
      '/environments',
      '/notifications',
    ]);
  });

  it('keeps role-specific entries around the shared blocks', () => {
    expect(navForRole('steward')[0]).toMatchObject({ to: '/my' });
    expect(navForRole('owner')[0]).toMatchObject({ to: '/my' });
    // Admin schließt mit Inventory-Admin + Settings am Fuß der Leiste ab.
    const adminNav = navForRole('admin');
    expect(adminNav.at(-2)).toMatchObject({ to: '/inventory-admin' });
    expect(adminNav.at(-1)).toMatchObject({ to: '/settings' });
  });
});
