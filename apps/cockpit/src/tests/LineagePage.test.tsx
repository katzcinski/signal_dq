import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import LineagePage from '@/pages/LineagePage';

vi.mock('@/components/lineage/schematic/SchematicLineage', () => ({
  default: () => <div data-testid="schematic-lineage">schematic</div>,
}));

vi.mock('@/pages/LegacyLineageMap', () => ({
  default: () => <div data-testid="legacy-lineage">legacy</div>,
}));

function renderPage(initialEntry = '/lineage') {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Routes>
        <Route path="/lineage" element={<LineagePage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('LineagePage', () => {
  it('defaults to the schematic renderer and can switch to legacy', async () => {
    renderPage();

    expect(await screen.findByTestId('schematic-lineage')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Legacy' }));

    await waitFor(() => {
      expect(screen.getByTestId('legacy-lineage')).toBeInTheDocument();
    });
  });

  it('can deep-link directly to the legacy renderer', async () => {
    renderPage('/lineage?renderer=legacy');

    expect(await screen.findByTestId('legacy-lineage')).toBeInTheDocument();
  });
});
