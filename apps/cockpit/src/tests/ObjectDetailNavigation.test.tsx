import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ObjectDetailNavigation } from '@/components/object-detail/ObjectDetailNavigation';

describe('ObjectDetailNavigation', () => {
  it('renders group navigation and active subsection state', () => {
    render(
      <ObjectDetailNavigation
        activeGroup="history-ops"
        activeTab="schedule"
        onSelectTab={vi.fn()}
      />,
    );

    const nav = screen.getByLabelText('Objektbereiche');
    expect(nav).toHaveAttribute('data-active-group', 'history-ops');
    expect(nav).toHaveAttribute('data-active-anchor', 'schedule');
    expect(screen.getByRole('button', { name: 'Historie & Betrieb' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: 'Zeitplan' })).toHaveAttribute('aria-pressed', 'true');
  });

  it('selects the default tab when a group is clicked', () => {
    const onSelectTab = vi.fn();
    render(
      <ObjectDetailNavigation
        activeGroup="quality"
        activeTab="checks"
        onSelectTab={onSelectTab}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Struktur & Interface' }));

    expect(onSelectTab).toHaveBeenCalledWith('contract');
  });

  it('selects a subsection inside the active group', () => {
    const onSelectTab = vi.fn();
    render(
      <ObjectDetailNavigation
        activeGroup="structure-interface"
        activeTab="contract"
        onSelectTab={onSelectTab}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Lineage' }));

    expect(onSelectTab).toHaveBeenCalledWith('lineage');
  });
});
