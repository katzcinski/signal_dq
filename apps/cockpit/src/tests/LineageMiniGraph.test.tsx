import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { LineageMiniGraph } from '@/components/LineageMiniGraph';
import type { LineageGraph } from '@/types';

const cytoscapeMock = vi.hoisted(() => {
  const instance = {
    on: vi.fn(),
    layout: vi.fn(() => ({ run: vi.fn() })),
    fit: vi.fn(),
    resize: vi.fn(),
    destroyed: vi.fn(() => false),
    destroy: vi.fn(),
  };
  const cytoscape = vi.fn(() => instance);
  Object.assign(cytoscape, { use: vi.fn() });
  return { cytoscape, instance };
});

vi.mock('cytoscape', () => ({ default: cytoscapeMock.cytoscape }));
vi.mock('cytoscape-dagre', () => ({ default: {} }));

describe('LineageMiniGraph', () => {
  it('renders without crashing for a minimal graph', async () => {
    const graph: LineageGraph = {
      nodes: [
        { id: 'RAW', layer: 'source', role: 'source' },
        { id: 'OUT', layer: 'serving', role: 'consumption' },
      ],
      edges: [{ id: 'RAW->OUT', source: 'RAW', target: 'OUT' }],
    };

    render(
      <MemoryRouter>
        <LineageMiniGraph subgraph={graph} />
      </MemoryRouter>,
    );

    expect(screen.getByTestId('lineage-mini-graph')).toBeTruthy();
    await waitFor(() => expect(cytoscapeMock.cytoscape).toHaveBeenCalled());
  });

  it('renders a dedicated sparse state for a single-node graph', () => {
    const graph: LineageGraph = {
      nodes: [
        { id: 'OUT', label: 'DEMO_BUS_06', layer: 'Business', role: 'consumption' },
      ],
      edges: [],
    };

    render(
      <MemoryRouter>
        <LineageMiniGraph subgraph={graph} />
      </MemoryRouter>,
    );

    expect(screen.getByTestId('lineage-mini-graph-sparse')).toBeTruthy();
    expect(screen.getByText(/no upstream objects in the current extract/i)).toBeTruthy();
    expect(screen.getByText(/open object detail/i)).toBeTruthy();
  });
});
