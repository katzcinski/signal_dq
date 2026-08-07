import { useEffect, useId, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Command } from 'cmdk';
import { toast } from 'sonner';
import { useObjects } from '@/api/objects';
import { useContracts } from '@/api/contracts';
import { api } from '@/api/client';
import { THEMES, useUIStore } from '@/store/ui';
import { useRoleStore, canRunChecks } from '@/store/role';
import { navForRole, type NavItem } from '@/components/layout/Sidebar';
import { t } from '@/i18n/de';

interface Props { onClose: () => void }

// R6-5: cmdk-based palette — pages, object/contract open (deep-link), run
// actions, and a persisted Recent group.
export function CommandPalette({ onClose }: Props) {
  const titleId = useId();
  const [query, setQuery] = useState('');
  const dialogRef = useRef<HTMLDivElement>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);
  const navigate = useNavigate();
  const { data: objects = [] } = useObjects();
  const { data: contracts = [] } = useContracts();
  const recents = useUIStore(s => s.recents);
  const pushRecent = useUIStore(s => s.pushRecent);
  const setTheme = useUIStore(s => s.setTheme);
  const role = useRoleStore(s => s.role);

  // Seiten spiegeln die rollenabhängige Sidebar-Navigation (navForRole), damit
  // rollenspezifische Landeseiten wie „Meine Arbeit" auch per Suche erreichbar
  // sind und keine für die Rolle ausgeblendeten Seiten auftauchen.
  const routes = useMemo(
    () => navForRole(role).filter((e): e is NavItem => e !== 'divider'),
    [role],
  );
  const canRun = canRunChecks(role);

  useEffect(() => {
    previousFocusRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    return () => previousFocusRef.current?.focus();
  }, []);

  const trapFocus = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (e.key === 'Escape') {
      e.stopPropagation();
      onClose();
      return;
    }
    if (e.key !== 'Tab') return;

    const dialog = dialogRef.current;
    if (!dialog) return;

    const focusable = dialog.querySelectorAll<HTMLElement>(
      'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
    );
    if (focusable.length === 0) {
      e.preventDefault();
      return;
    }

    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  };

  const go = (path: string, label: string) => { pushRecent(`${path}|${label}`); navigate(path); onClose(); };

  const runChecks = (id: string) => {
    onClose();
    toast.promise(api.post(`/objects/${id}/run`, {}).then(r => r.data), {
      loading: `${t.toast.runStarting} ${id}…`,
      success: `${t.toast.runStarted} ${id}.`,
      error: `${t.toast.runError} ${id}.`,
    });
  };

  const sendDigest = () => {
    onClose();
    toast.promise(api.post('/notifications/digest/send').then(r => r.data), {
      loading: t.notifications.digestSending,
      success: t.palette.digestSent,
      error: t.palette.digestError,
    });
  };

  const recentItems = recents
    .map(r => { const [path, label] = r.split('|'); return { path, label: label || path }; })
    .filter(r => routes.some(x => x.to === r.path)
      || objects.some(o => `/objects/${o.id}` === r.path)
      || contracts.some(c => `/contracts?product=${c.product}` === r.path));

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, zIndex: 1000, background: 'rgba(0,0,0,0.6)',
        display: 'flex', alignItems: 'flex-start', justifyContent: 'center', paddingTop: '12vh',
        overscrollBehavior: 'contain',
      }}
    >
      <div
        id="command-palette-dialog"
        ref={dialogRef}
        onClick={e => e.stopPropagation()}
        onKeyDown={trapFocus}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        style={{
          background: 'var(--bg-2)', border: '1px solid var(--line-2)', borderRadius: 'var(--r-lg)',
          width: 560, maxWidth: 'min(560px, calc(100vw - 24px))', overflow: 'hidden',
          boxShadow: '0 24px 48px rgba(0,0,0,0.5)',
        }}
      >
        <h2 id={titleId} className="sr-only">{t.palette.placeholder}</h2>
        <Command label={t.palette.placeholder} shouldFilter>
          <Command.Input autoFocus value={query} onValueChange={setQuery} placeholder={t.palette.placeholder} />
          <Command.List>
            <Command.Empty>{t.palette.noResults}</Command.Empty>

            {!query && recentItems.length > 0 && (
              <Command.Group heading={t.palette.recent}>
                {recentItems.map(r => (
                  <Command.Item key={`recent:${r.path}`} value={`recent ${r.label}`} onSelect={() => go(r.path, r.label)}>
                    {r.label}
                  </Command.Item>
                ))}
              </Command.Group>
            )}

            <Command.Group heading={t.palette.pages}>
              {routes.map(r => (
                <Command.Item key={r.to} value={`page ${r.label}`} onSelect={() => go(r.to, r.label)}>
                  {r.label}
                </Command.Item>
              ))}
            </Command.Group>

            <Command.Group heading={t.palette.objects}>
              {objects.slice(0, 50).map(o => (
                <Command.Item key={`open:${o.id}`} value={`object ${o.name} ${o.id}`} onSelect={() => go(`/objects/${encodeURIComponent(o.id)}`, o.name)}>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--fg-2)' }}>{o.name}</span>
                  <span style={{ color: 'var(--fg-3)', fontSize: 11 }}>{o.space}</span>
                </Command.Item>
              ))}
            </Command.Group>

            <Command.Group heading={t.palette.actions}>
              {/* Run-Aktionen nur für run-berechtigte Rollen (Server verlangt
                  steward+; Viewer bekämen sonst nur einen 403-Toast). */}
              {canRun && objects.slice(0, 50).map(o => (
                <Command.Item key={`run:${o.id}`} value={`run checks ${o.name} ${o.id}`} onSelect={() => runChecks(o.id)}>
                  {t.palette.runChecks} <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}>{o.name}</span>
                </Command.Item>
              ))}
              {contracts.slice(0, 50).map(c => (
                <Command.Item key={`contract:${c.product}`} value={`contract ${c.product} open`} onSelect={() => go(`/contracts?product=${encodeURIComponent(c.product)}`, c.product)}>
                  {t.palette.openContract} <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}>{c.product}</span>
                </Command.Item>
              ))}
            </Command.Group>

            <Command.Group heading={t.palette.system}>
              {/* Quick-Filter: gängige Triage-Einstiege als ein Tastendruck. */}
              <Command.Item value="quick offene incidents open" onSelect={() => go('/incidents?status=open', t.palette.quickOpenIncidents)}>
                {t.palette.quickOpenIncidents}
              </Command.Item>
              <Command.Item value="quick schema drift" onSelect={() => go('/schema-drift', t.palette.quickSchemaDrift)}>
                {t.palette.quickSchemaDrift}
              </Command.Item>
              {role !== 'viewer' && (
                <Command.Item value="quick überfällige zeitpläne overdue" onSelect={() => go('/schedules?filter=overdue', t.palette.quickOverdueSchedules)}>
                  {t.palette.quickOverdueSchedules}
                </Command.Item>
              )}
              {role !== 'viewer' && (
                <Command.Item value="digest senden quality" onSelect={sendDigest}>
                  {t.palette.sendDigest}
                </Command.Item>
              )}
              {THEMES.map(th => (
                <Command.Item key={`theme:${th}`} value={`theme wechseln ${th}`} onSelect={() => { setTheme(th); onClose(); }}>
                  {t.palette.setTheme} <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}>{th}</span>
                </Command.Item>
              ))}
            </Command.Group>
          </Command.List>
        </Command>
      </div>
    </div>
  );
}
