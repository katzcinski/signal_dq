import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useUIStore } from '@/store/ui';
import { useRoleStore } from '@/store/role';
import { t } from '@/i18n/de';

vi.mock('@/api/objects', () => ({
  useObjects: () => ({
    data: [{ id: 'obj-1', name: 'SALES', space: 'CORE' }],
  }),
}));

vi.mock('@/api/contracts', () => ({
  useContracts: () => ({
    data: [{ product: 'Sales Product' }],
  }),
}));

vi.mock('@/api/client', () => ({
  api: { post: vi.fn() },
}));

import { CommandPalette } from '@/components/CommandPalette';

function renderPalette() {
  const onClose = vi.fn();
  render(
    <MemoryRouter>
      <CommandPalette onClose={onClose} />
    </MemoryRouter>,
  );
  return onClose;
}

describe('CommandPalette', () => {
  beforeEach(() => {
    useUIStore.setState({ recents: [] });
    useRoleStore.setState({ role: 'steward' });
  });

  afterEach(() => {
    useRoleStore.setState({ role: 'steward' });
  });

  it('renders as a modal dialog and exposes the library route', () => {
    const onClose = renderPalette();

    const dialog = screen.getByRole('dialog', { name: t.palette.placeholder });
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    expect(screen.getByText(t.nav.library)).toBeInTheDocument();

    fireEvent.keyDown(dialog, { key: 'Escape' });
    expect(onClose).toHaveBeenCalled();
  });

  it('offers run actions and the role landing page for a steward', () => {
    useRoleStore.setState({ role: 'steward' });
    renderPalette();

    // Rollen-Landeseite „Meine Arbeit" ist per Suche erreichbar (navForRole-Spiegel).
    expect(screen.getByText(t.nav.myWork)).toBeInTheDocument();
    // Run-Aktion wird für steward angeboten.
    expect(screen.getByText(t.palette.runChecks)).toBeInTheDocument();
  });

  it('hides run actions for a viewer but keeps navigation', () => {
    useRoleStore.setState({ role: 'viewer' });
    renderPalette();

    // Viewer darf keine Runs triggern (Server 403) → Aktion wird nicht angeboten.
    expect(screen.queryByText(t.palette.runChecks)).not.toBeInTheDocument();
    // Navigation bleibt: das Objekt ist weiterhin auffindbar.
    expect(screen.getByText('SALES')).toBeInTheDocument();
    // Viewer hat keine „Meine Arbeit"-Landeseite.
    expect(screen.queryByText(t.nav.myWork)).not.toBeInTheDocument();
  });

  it('switches the theme via a system action', () => {
    useUIStore.setState({ theme: 'signal' });
    const onClose = renderPalette();

    fireEvent.click(screen.getByText('daylight'));
    expect(useUIStore.getState().theme).toBe('daylight');
    expect(onClose).toHaveBeenCalled();
  });

  it('offers quick filters and the digest action to a steward, not a viewer', () => {
    renderPalette();
    expect(screen.getByText(t.palette.quickOpenIncidents)).toBeInTheDocument();
    expect(screen.getByText(t.palette.quickOverdueSchedules)).toBeInTheDocument();
    expect(screen.getByText(t.palette.sendDigest)).toBeInTheDocument();
  });

  it('hides the digest and schedules actions from viewers', () => {
    useRoleStore.setState({ role: 'viewer' });
    renderPalette();

    expect(screen.queryByText(t.palette.sendDigest)).not.toBeInTheDocument();
    expect(screen.queryByText(t.palette.quickOverdueSchedules)).not.toBeInTheDocument();
    expect(screen.getByText(t.palette.quickOpenIncidents)).toBeInTheDocument();
  });
});
