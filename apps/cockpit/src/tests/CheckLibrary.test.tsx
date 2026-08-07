import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

vi.mock('@/api/library', () => ({
  useLibrary: () => ({
    data: {
      categories: ['Validity', 'Freshness'],
      families: ['quality', 'observability'],
      checks: [
        {
          id: 'value_range',
          label: 'Value Range',
          short: 'Range check',
          help: 'Ensures a number stays within bounds.',
          example: '',
          category: 'Validity',
          family: 'quality',
          gating: 'standard',
          sql_template: 'SELECT 1',
          params: [],
          default_expect: '= 0',
          default_severity: 'fail',
          unit: '',
        },
        {
          id: 'freshness_lag',
          label: 'Freshness Lag',
          short: 'Lag check',
          help: 'Measures source lag.',
          example: '',
          category: 'Freshness',
          family: 'observability',
          gating: 'gate',
          sql_template: 'SELECT 2',
          params: [],
          default_expect: '< 3600',
          default_severity: 'warn',
          unit: 's',
        },
      ],
    },
    isLoading: false,
  }),
}));

import CheckLibrary from '@/pages/CheckLibrary';

function LocationEcho() {
  const location = useLocation();
  return <div data-testid="location">{location.search}</div>;
}

function renderPage(route = '/library') {
  render(
    <MemoryRouter initialEntries={[route]}>
      <Routes>
        <Route path="/library" element={<><CheckLibrary /><LocationEcho /></>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('CheckLibrary', () => {
  it('hydrates search and filter state from the URL', () => {
    renderPage('/library?q=range&category=Validity&family=quality');

    expect(screen.getByRole('searchbox', { name: 'Checks filtern' })).toHaveValue('range');
    expect(screen.getByRole('button', { name: 'Validity' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: 'Quality' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByText('1 Check')).toBeInTheDocument();
    expect(screen.getByText('Value Range')).toBeInTheDocument();
    expect(screen.queryByText('Freshness Lag')).not.toBeInTheDocument();
  });

  it('syncs filter changes back into the URL and can clear them', () => {
    renderPage();

    fireEvent.click(screen.getByRole('button', { name: 'Validity' }));
    expect(screen.getByTestId('location')).toHaveTextContent('?category=Validity');

    fireEvent.click(screen.getByRole('button', { name: 'Quality' }));
    expect(screen.getByTestId('location')).toHaveTextContent('family=quality');
    expect(screen.getByText('1 Check')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Filter zuruecksetzen' }));
    expect(screen.getByTestId('location')).toHaveTextContent(/^$/);
    expect(screen.getByText('2 Checks')).toBeInTheDocument();
  });
});
