import { useNavigate } from 'react-router-dom';
import { t } from '@/i18n/de';
import { Tooltip } from '@/components/ui/Tooltip';
import { ControlSelect, IconButton, ToolbarButton } from '@/components/ui/ControlPrimitives';
import { useUIStore, THEMES, type Theme } from '@/store/ui';
import { useRoleStore, ROLES, ROLE_META, type Role } from '@/store/role';

interface Props {
  onToggleSidebar: () => void;
  onOpenPalette: () => void;
  paletteOpen: boolean;
}

function MenuIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="1.8" strokeLinecap="round" aria-hidden="true" focusable="false">
      <path d="M4 6h16M4 12h16M4 18h16" />
    </svg>
  );
}

function SearchIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
      <circle cx="11" cy="11" r="7" />
      <path d="m16 16 4 4" />
    </svg>
  );
}

function DensityIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="1.8" strokeLinecap="round" aria-hidden="true" focusable="false">
      <path d="M5 7h14M5 12h14M5 17h14" />
    </svg>
  );
}

function ThemeDot({ theme }: { theme: Theme }) {
  return (
    <span style={{
      width: 9,
      height: 9,
      borderRadius: 'var(--r-full)',
      flexShrink: 0,
      background: 'var(--signal)',
      boxShadow: theme === 'classic' ? '0 0 0 1px var(--line-2)' : '0 0 0 3px var(--signal-dim)',
    }}
    />
  );
}

function ThemeSwitcher() {
  const theme = useUIStore(s => s.theme);
  const setTheme = useUIStore(s => s.setTheme);

  return (
    <ControlSelect
      label={t.theme.label}
      title={t.theme.toggle}
      value={theme}
      onChange={e => setTheme(e.target.value as Theme)}
      prefix={<ThemeDot theme={theme} />}
    >
      {THEMES.map(th => (
        <option key={th} value={th} style={{ background: 'var(--bg-2)', color: 'var(--fg)' }}>
          {t.theme[th]}
        </option>
      ))}
    </ControlSelect>
  );
}

// UX-F1: role switcher. Changing role updates the X-DQ-Role header (api/client.ts)
// and lands the user on that role's default home (UX-N3). The server stays
// authoritative; this only changes which write affordances the UI offers.
function RoleSwitcher() {
  const role = useRoleStore(s => s.role);
  const setRole = useRoleStore(s => s.setRole);
  const navigate = useNavigate();

  const onChange = (next: Role) => {
    setRole(next);
    navigate(ROLE_META[next].home);
  };

  return (
    <Tooltip content={t.role.tooltips[role] ?? ROLE_META[role].hint}>
      <ControlSelect
        label={t.role.switchLabel}
        value={role}
        onChange={e => onChange(e.target.value as Role)}
        tone="accent"
        prefix={<span className="topbar-control-text mono-label">{t.role.switchLabel}</span>}
        shellStyle={{ borderColor: 'color-mix(in srgb, var(--cont) 46%, var(--line-2))' }}
      >
        {ROLES.map(r => (
          <option key={r} value={r} style={{ background: 'var(--bg-2)', color: 'var(--fg)' }}>
            {ROLE_META[r].label}
          </option>
        ))}
      </ControlSelect>
    </Tooltip>
  );
}

export function Topbar({ onToggleSidebar, onOpenPalette, paletteOpen }: Props) {
  const density = useUIStore(s => s.density);
  const toggleDensity = useUIStore(s => s.toggleDensity);
  const densityLabel = density === 'compact' ? t.density.compact : t.density.comfortable;

  return (
    <header className="topbar">
      <IconButton label="Toggle sidebar" onClick={onToggleSidebar}>
        <MenuIcon />
      </IconButton>

      <ToolbarButton
        className="topbar-command"
        onClick={onOpenPalette}
        aria-label={t.palette.placeholder}
        aria-haspopup="dialog"
        aria-expanded={paletteOpen}
        aria-controls="command-palette-dialog"
        style={{ justifyContent: 'space-between', width: 'min(36vw, 340px)', minWidth: 220 }}
      >
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 'var(--s2)', minWidth: 0 }}>
          <SearchIcon />
          <span className="topbar-command-label">{t.palette.placeholder}</span>
        </span>
        <kbd className="topbar-kbd">Ctrl K</kbd>
      </ToolbarButton>

      <div style={{ flex: 1, minWidth: 'var(--s3)' }} />

      <div className="topbar-control-group" role="group" aria-label="View controls">
        <ThemeSwitcher />
        <ToolbarButton
          onClick={toggleDensity}
          active={density === 'compact'}
          aria-label={t.density.toggle}
          title={t.density.toggle}
        >
          <DensityIcon />
          <span className="topbar-control-text">{densityLabel}</span>
        </ToolbarButton>
      </div>

      <RoleSwitcher />
    </header>
  );
}
