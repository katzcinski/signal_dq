import { describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import SchematicLineage from '@/components/lineage/schematic/SchematicLineage';
import type { LineageGraph } from '@/types';

const GRAPH: LineageGraph = {
  nodes: [
    { id: 'INB', layer: 'Source', layerCode: 'r', system: 'S/4HANA', columns: ['VBELN', 'NETWR'], dq_status: 'pass' },
    {
      id: 'HRM', layer: 'Harmonization', layerCode: 'ic', system: 'Datasphere',
      columns: ['SALES_DOC', 'NET_VALUE_USD'], dq_status: 'warn', has_contract: true,
    },
  ],
  edges: [],
  columnEdges: [
    { source: 'INB', sourceColumn: 'VBELN', target: 'HRM', targetColumn: 'SALES_DOC', edgeType: 'direct' },
    {
      source: 'INB', sourceColumn: 'NETWR', target: 'HRM', targetColumn: 'NET_VALUE_USD',
      edgeType: 'computed', expression: "CURRENCY_CONVERSION(NETWR, 'USD')",
    },
  ],
};

// Der Container ist seed-gated: ohne Seed wird nichts geladen. Der Mock liefert
// den Graphen unabhängig vom Scope; die Tests wählen zuerst ein Seed.
vi.mock('@/api/lineage', () => ({
  useLineage: () => ({ data: GRAPH, isLoading: false }),
}));

vi.mock('@/api/objects', () => ({
  useObjects: () => ({
    data: [
      { id: 'INB', name: 'INB', layer: 'Source' },
      { id: 'HRM', name: 'HRM', layer: 'Harmonization' },
    ],
  }),
}));

function renderLineage(initialEntry = '/lineage') {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Routes>
        <Route path="/lineage" element={<SchematicLineage />} />
      </Routes>
    </MemoryRouter>,
  );
}

/** Seed über das Suchfeld wählen, damit der Graph geladen/gerendert wird. */
async function pickSeed(label = 'INB') {
  const input = screen.getByPlaceholderText('Seed-Objekt hinzufügen…');
  fireEvent.focus(input);
  fireEvent.change(input, { target: { value: label } });
  const option = await screen.findByRole('button', { name: new RegExp(label) });
  fireEvent.mouseDown(option);
}

/** Spalten eines Chips über den Kopf-Chevron ausklappen. */
async function expandColumns(label: string) {
  const toggle = await screen.findByRole('button', {
    name: new RegExp(`Spalten anzeigen.*${label}`),
  });
  fireEvent.click(toggle);
}

describe('SchematicLineage container', () => {
  it('gates on a seed and renders the board once one is chosen', async () => {
    renderLineage();
    // Vor der Seed-Auswahl: Empty-State, kein Board.
    expect(screen.getByText('Lineage gezielt laden')).toBeInTheDocument();
    expect(screen.queryByText('S/4HANA')).not.toBeInTheDocument();

    await pickSeed('INB');

    // Default: alles eingeklappt (Objekt-Ebene) — Spaltenanzahl statt Pin-Labels.
    await waitFor(() => {
      expect(screen.getAllByText('2 cols').length).toBeGreaterThan(0);
    });
    expect(screen.queryByText('VBELN')).not.toBeInTheDocument();
    // Layer-Sidebar + System-Chips aus den Daten.
    expect(screen.getAllByText('S/4HANA').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Datasphere').length).toBeGreaterThan(0);
  });

  it('traces a column and surfaces its transformation in the inspector', async () => {
    renderLineage();
    await pickSeed('INB');
    // Spalten müssen erst ausgeklappt werden, bevor ein Pin tracebar ist.
    await expandColumns('HRM');
    const pin = await screen.findByText('NET_VALUE_USD');
    fireEvent.click(pin);
    // Inspector zeigt den Transformations-Codeblock (pre), nicht nur den SVG-Tooltip.
    await waitFor(() => {
      expect(screen.getByText(/CURRENCY_CONVERSION/, { selector: 'pre' })).toBeInTheDocument();
    });
  });

  it('expands a single node\'s columns on the chevron click', async () => {
    renderLineage();
    await pickSeed('INB');
    // Eingeklappt: keine Spalten-Pins sichtbar.
    await waitFor(() => {
      expect(screen.getAllByText('2 cols').length).toBeGreaterThan(0);
    });
    expect(screen.queryByText('SALES_DOC')).not.toBeInTheDocument();

    await expandColumns('HRM');

    // Nur HRM ausgeklappt → dessen Pins erscheinen, INB bleibt eingeklappt.
    expect(await screen.findByText('SALES_DOC')).toBeInTheDocument();
    expect(screen.queryByText('VBELN')).not.toBeInTheDocument();
    expect(screen.getByText('Alle Spalten einklappen')).toBeInTheDocument();
  });

  it('hydrates the focus query as the initial seed', async () => {
    renderLineage('/lineage?focus=INB');
    expect(screen.queryByText('Lineage gezielt laden')).not.toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getAllByText('2 cols').length).toBeGreaterThan(0);
    });
    expect(screen.getAllByText('INB').length).toBeGreaterThan(0);
  });

  it('does not promote selected chips to seeds', async () => {
    renderLineage('/lineage?focus=INB');
    await waitFor(() => {
      expect(screen.getAllByText('2 cols').length).toBeGreaterThan(0);
    });
    expect(screen.getAllByLabelText('Seed entfernen')).toHaveLength(1);

    const hrmTitle = screen.getAllByText('HRM').find(el => el.classList.contains('schem-title'));
    expect(hrmTitle).toBeTruthy();
    fireEvent.click(hrmTitle!);

    expect(screen.getAllByLabelText('Seed entfernen')).toHaveLength(1);
  });
});
