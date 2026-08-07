import { NavLink, useLocation } from 'react-router-dom';
import { t } from '@/i18n/de';
import { useRoleStore, type Role } from '@/store/role';
import { useUIStore } from '@/store/ui';

// UX-F4: real, self-drawn SVG glyphs instead of platform-dependent Unicode
// symbols (⬡ ⊞ ⟁ …) that rendered inconsistently and carried no label. Each is
// a 16px stroke icon; semantics come from the adjacent aria-label/title, so the
// collapsed rail stays navigable for keyboard and screen-reader users.
type IconKey = 'my' | 'cockpit' | 'objects' | 'products' | 'contracts' | 'lineage' | 'schemaDrift' | 'incidents' | 'quarantine' | 'healing' | 'enforcement' | 'proposals' | 'governance' | 'compliance' | 'library' | 'notifications' | 'settings' | 'schedules' | 'inventoryAdmin' | 'environments';

function Icon({ name }: { name: IconKey }) {
  const common = {
    width: 16, height: 16, viewBox: '0 0 24 24', fill: 'none',
    stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const, 'aria-hidden': true, focusable: false,
  };
  switch (name) {
    case 'my':         return <svg {...common}><circle cx="12" cy="8" r="3.5" /><path d="M5 20a7 7 0 0 1 14 0" /></svg>;
    case 'cockpit':    return <svg {...common}><rect x="3" y="3" width="7" height="9" rx="1" /><rect x="14" y="3" width="7" height="5" rx="1" /><rect x="14" y="12" width="7" height="9" rx="1" /><rect x="3" y="16" width="7" height="5" rx="1" /></svg>;
    case 'objects':    return <svg {...common}><path d="M12 3 4 7l8 4 8-4-8-4Z" /><path d="M4 12l8 4 8-4" /><path d="M4 17l8 4 8-4" /></svg>;
    case 'products':   return <svg {...common}><rect x="4" y="4" width="6" height="6" rx="1" /><rect x="14" y="4" width="6" height="6" rx="1" /><rect x="9" y="14" width="6" height="6" rx="1" /><path d="M10 7h4M12 10v4" /></svg>;
    case 'contracts':  return <svg {...common}><path d="M7 3h7l4 4v14H7z" /><path d="M14 3v4h4" /><path d="M10 13h6M10 17h6" /></svg>;
    case 'lineage':    return <svg {...common}><circle cx="6" cy="6" r="2.5" /><circle cx="18" cy="12" r="2.5" /><circle cx="6" cy="18" r="2.5" /><path d="M8.2 7.3 15.8 11M8.2 16.7 15.8 13" /></svg>;
    case 'schedules':  return <svg {...common}><circle cx="12" cy="12" r="8" /><path d="M12 8v4l3 1.6" /></svg>;
    case 'schemaDrift': return <svg {...common}><rect x="4" y="4" width="6" height="16" rx="1" /><rect x="14" y="4" width="6" height="10" rx="1" /><path d="M17 17v4M15 19l2 2 2-2" /></svg>;
    case 'incidents':  return <svg {...common}><path d="M5 21V4l13 .5L14 8l4 3.5L5 12" /></svg>;
    case 'quarantine': return <svg {...common}><rect x="4" y="4" width="16" height="16" rx="2" /><path d="M4 9h16M4 15h16M9 4v16M15 4v16" /></svg>;
    case 'healing':    return <svg {...common}><path d="M12 5v14M5 12h14" /><circle cx="12" cy="12" r="9" /></svg>;
    case 'enforcement': return <svg {...common}><path d="M6 3v18M6 4h11l-3 3.5L17 11H6" /></svg>;
    case 'proposals':  return <svg {...common}><path d="M12 3v4M12 17v4M3 12h4M17 12h4M5.6 5.6l2.8 2.8M15.6 15.6l2.8 2.8M18.4 5.6l-2.8 2.8M8.4 15.6l-2.8 2.8" /></svg>;
    case 'governance': return <svg {...common}><path d="M12 3 4 6v5c0 5 3.5 8 8 10 4.5-2 8-5 8-10V6Z" /></svg>;
    case 'compliance': return <svg {...common}><path d="M12 3 4 6v5c0 5 3.5 8 8 10 4.5-2 8-5 8-10V6Z" /><path d="M9 12l2 2 4-4" /></svg>;
    case 'library':    return <svg {...common}><rect x="4" y="4" width="4" height="16" rx="1" /><rect x="10" y="4" width="4" height="16" rx="1" /><path d="M17 5l3 .8-3 14-2-.5" /></svg>;
    case 'notifications': return <svg {...common}><path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" /><path d="M13.7 21a2 2 0 0 1-3.4 0" /></svg>;
    case 'environments': return <svg {...common}><path d="M8 7h8M8 17h8" /><rect x="4" y="4" width="16" height="6" rx="1.5" /><rect x="4" y="14" width="16" height="6" rx="1.5" /><path d="M7 10v4M17 10v4" /></svg>;
    case 'settings':   return <svg {...common}><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.9.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.9 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.9l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.9.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.9-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.9V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1Z" /></svg>;
    case 'inventoryAdmin': return <svg {...common}><ellipse cx="12" cy="5" rx="7" ry="3" /><path d="M5 5v7c0 1.7 3.1 3 7 3s7-1.3 7-3V5" /><path d="M5 12v7c0 1.7 3.1 3 7 3s7-1.3 7-3v-7" /><path d="M9 10h6M9 17h6" /></svg>;
  }
}

// `aliases`: zusätzliche Pfade, die dieselbe Ansicht rendern (Route-Aliase wie
// /coverage → /lineage). Der Eintrag leuchtet dort mit, sonst hätte der Nutzer
// auf einer aliasierten Route kein „du bist hier".
export interface NavItem { to: string; label: string; icon: IconKey; aliases?: string[]; }
type SidebarEntry = NavItem | 'divider';

const MY_WORK: NavItem = { to: '/my', label: t.nav.myWork, icon: 'my' };
const INVENTORY_ADMIN: NavItem = { to: '/inventory-admin', label: t.nav.inventoryAdmin, icon: 'inventoryAdmin' };

const DQ_BLOCK: NavItem[] = [
  { to: '/',           label: t.nav.cockpit,    icon: 'cockpit' },
  { to: '/objects',    label: t.nav.objects,    icon: 'objects' },
  { to: '/products',   label: t.nav.products,   icon: 'products' },
  { to: '/lineage',    label: t.nav.lineage,    icon: 'lineage', aliases: ['/coverage'] },
  { to: '/schema-drift', label: t.nav.schemaDrift, icon: 'schemaDrift' },
  { to: '/incidents',  label: t.nav.incidents,  icon: 'incidents' },
  { to: '/quarantine', label: t.nav.quarantine, icon: 'quarantine' },
  { to: '/proposals',  label: t.nav.proposals,  icon: 'proposals' },
  { to: '/library',    label: t.nav.library,    icon: 'library' },
];

const GOVERN_BLOCK: NavItem[] = [
  { to: '/contracts',  label: t.nav.contracts,   icon: 'contracts' },
  { to: '/compliance', label: t.nav.compliance,  icon: 'compliance' },
];

const UTILITY: NavItem[] = [
  { to: '/environments', label: t.nav.environments, icon: 'environments' },
  { to: '/notifications', label: t.nav.notifications, icon: 'notifications' },
];

// Platform-administration. The page is server-gated to admin; the nav entry is
// only offered to the admin role (FE mirror — a hidden link is a hint, not a gate).
const SETTINGS: NavItem = { to: '/settings', label: t.nav.settings, icon: 'settings' };

// Scheduling overview is server-gated to steward+ (routers/schedules.py); the
// nav entry is hidden from viewers as an FE mirror (a hint, not a gate). It sits
// right after Incidents in the operational cluster of the rail.
const SCHEDULES: NavItem = { to: '/schedules', label: t.nav.schedules, icon: 'schedules' };
// Healing-Workbench (H1/H3) ist server-gegated (Korrektur steward+, Patch
// owner+); der Nav-Eintrag folgt demselben FE-Spiegel wie Schedules.
const HEALING: NavItem = { to: '/healing', label: t.nav.healing, icon: 'healing' };
// Enforcement-Panel (Plan/Probe/Apply) ist server-gegated (Plan steward+,
// Apply owner+); der Nav-Eintrag folgt demselben FE-Spiegel wie Schedules.
const ENFORCEMENT: NavItem = { to: '/enforcement', label: t.nav.enforcement, icon: 'enforcement' };

function withSchedules(items: NavItem[], role: Role): NavItem[] {
  if (role === 'viewer') return items;
  const i = items.findIndex(n => n.to === '/incidents');
  const extra = [SCHEDULES, HEALING, ENFORCEMENT];
  if (i < 0) return [...items, ...extra];
  return [...items.slice(0, i + 1), ...extra, ...items.slice(i + 1)];
}

// UX-N3 / UX-F1: nav order follows the role. Stewards/owners lead with "My work"
// (their default landing); viewers/admins lead with the global cockpit. The
// admin additionally gets the platform-settings entry at the foot of the rail.
export function navForRole(role: Role): SidebarEntry[] {
  const dqBlock = withSchedules(DQ_BLOCK, role);
  const base: SidebarEntry[] = [
    ...dqBlock,
    'divider',
    ...GOVERN_BLOCK,
    'divider',
    ...UTILITY,
  ];
  if (role === 'admin') return [...base, INVENTORY_ADMIN, SETTINGS];
  if (role === 'steward' || role === 'owner') return [MY_WORK, ...base];
  return base;
}

interface Props { collapsed: boolean }

export function Sidebar({ collapsed }: Props) {
  const role = useRoleStore(s => s.role);
  const theme = useUIStore(s => s.theme);
  const nav = navForRole(role);
  const { pathname } = useLocation();

  const matchesAlias = (aliases?: string[]) =>
    aliases?.some(a => pathname === a || pathname.startsWith(`${a}/`)) ?? false;

  return (
    <aside style={{
      width: collapsed ? 48 : 200,
      background: 'var(--bg-1)',
      borderRight: '1px solid var(--line)',
      display: 'flex', flexDirection: 'column',
      transition: 'width var(--t)',
      flexShrink: 0, overflow: 'hidden',
    }}>
      {theme !== 'classic' ? (
        <div style={{
          padding: '14px 14px', borderBottom: '1px solid var(--line)', overflow: 'hidden',
          display: 'flex', alignItems: 'center', gap: 9,
        }}>
          {/* Live "signal" dot — a phosphor pulse that reads as "instrument online". */}
          <span style={{
            width: 7, height: 7, borderRadius: '50%', flexShrink: 0,
            background: 'var(--signal)', boxShadow: '0 0 0 3px var(--signal-dim)',
          }} />
          {!collapsed && (
            <span style={{
              fontFamily: 'var(--font-mono)', fontWeight: 600, fontSize: 13,
              letterSpacing: '0.22em', color: 'var(--fg)', whiteSpace: 'nowrap',
              textTransform: 'uppercase',
            }}>
              Signal
            </span>
          )}
        </div>
      ) : (
        <div style={{ padding: 'var(--s4) var(--s3)', borderBottom: '1px solid var(--line)', overflow: 'hidden' }}>
          <span style={{ fontWeight: 700, fontSize: 14, color: 'var(--fg)', whiteSpace: 'nowrap' }}>
            {collapsed ? 'S' : 'Signal'}
          </span>
        </div>
      )}
      <nav style={{ flex: 1, padding: 'var(--s2) 0' }}>
        {nav.map((entry, idx) => {
          if (entry === 'divider') {
            return (
              <div
                key={`div-${idx}`}
                style={{ height: 1, background: 'var(--line)', margin: '6px 12px' }}
              />
            );
          }
          const { to, label, icon, aliases } = entry;
          const aliasActive = matchesAlias(aliases);
          return (
            <NavLink
              key={to} to={to} end={to === '/'}
              title={label}
              aria-label={label}
              style={({ isActive }) => {
                const active = isActive || aliasActive;
                return {
                  position: 'relative',
                  display: 'flex', alignItems: 'center', gap: 10,
                  padding: 'var(--s2) var(--s3)', margin: '1px 6px', borderRadius: 'var(--r-md)',
                  justifyContent: collapsed ? 'center' : 'flex-start',
                  color: active ? 'var(--fg)' : 'var(--fg-2)',
                  background: active ? 'var(--bg-2)' : 'transparent',
                  boxShadow: active ? 'inset 2px 0 0 var(--nav-active-bar)' : undefined,
                  fontSize: 13, whiteSpace: 'nowrap', overflow: 'hidden',
                  transition: 'color var(--t), background var(--t)',
                };
              }}
            >
              {({ isActive }) => (
                <>
                  <span style={{
                    display: 'inline-flex', flexShrink: 0,
                    color: isActive || aliasActive ? 'var(--nav-active-icon)' : 'inherit',
                    transition: 'color var(--t)',
                  }}>
                    <Icon name={icon} />
                  </span>
                  {!collapsed && <span>{label}</span>}
                </>
              )}
            </NavLink>
          );
        })}
      </nav>
    </aside>
  );
}
