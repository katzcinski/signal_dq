import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import LegacyLineageMap from '@/pages/LegacyLineageMap';
import { t } from '@/i18n/de';
import type { LineageGraph } from '@/types';

const apiState = vi.hoisted(() => ({
  scopes: [] as unknown[],
  graph: {
    nodes: [
      { id: 'INB', label: 'INB', layer: 'Source', system: 'S/4HANA' },
      { id: 'HRM', label: 'HRM', layer: 'Harmonization', system: 'Datasphere' },
    ],
    edges: [{ id: 'INB->HRM', source: 'INB', target: 'HRM' }],
  } as LineageGraph,
}));

const cytoscapeMock = vi.hoisted(() => {
  const handlers: Record<string, (event: unknown) => void> = {};
  const selected = { unselect: vi.fn() };
  const elements = { removeClass: vi.fn() };
  const node = {
    addClass: vi.fn(),
    empty: vi.fn(() => false),
    renderedBoundingBox: vi.fn(() => ({ x1: 40, y1: 40, x2: 180, y2: 90 })),
    select: vi.fn(),
  };
  const instance = {
    animate: vi.fn(),
    destroyed: vi.fn(() => false),
    destroy: vi.fn(),
    elements: vi.fn(() => elements),
    fit: vi.fn(),
    getElementById: vi.fn(() => node),
    height: vi.fn(() => 600),
    layout: vi.fn(() => ({ run: vi.fn() })),
    nodes: vi.fn(() => selected),
    on: vi.fn((event: string, selectorOrHandler: string | ((event: unknown) => void), handler?: (event: unknown) => void) => {
      if (typeof selectorOrHandler === 'string' && handler) handlers[`${event}:${selectorOrHandler}`] = handler;
      if (typeof selectorOrHandler === 'function') handlers[event] = selectorOrHandler;
    }),
    resize: vi.fn(),
    width: vi.fn(() => 800),
  };
  const cytoscape = vi.fn(() => instance);
  Object.assign(cytoscape, { use: vi.fn() });
  return { cytoscape, elements, handlers, instance, node, selected };
});

let resizeCallback: ResizeObserverCallback | null = null;

vi.mock('@/api/lineage', () => ({
  useLineage: (scope: unknown) => {
    const effectiveScope = scope ?? {};
    apiState.scopes.push(effectiveScope);
    const enabled = scope === undefined || !!(effectiveScope as { enabled?: boolean }).enabled;
    return { data: enabled ? apiState.graph : undefined, isError: false, isLoading: false };
  },
}));

vi.mock('@/api/objects', () => ({
  useObjects: () => ({
    data: [
      { id: 'INB', name: 'INB', layer: 'Source' },
      { id: 'HRM', name: 'HRM', layer: 'Harmonization' },
    ],
  }),
}));

vi.mock('cytoscape', () => ({ default: cytoscapeMock.cytoscape }));
vi.mock('cytoscape-dagre', () => ({ default: {} }));

function renderMap(initialEntry = '/lineage?renderer=legacy') {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <LegacyLineageMap />
    </MemoryRouter>,
  );
}

async function chooseSeed(label = 'INB') {
  const input = screen.getByPlaceholderText(t.lineage.schematic.seedSearchPlaceholder);
  fireEvent.focus(input);
  fireEvent.change(input, { target: { value: label } });
  fireEvent.mouseDown(await screen.findByRole('button', { name: new RegExp(label) }));
}

describe('LegacyLineageMap', () => {
  beforeEach(() => {
    apiState.scopes = [];
    cytoscapeMock.cytoscape.mockClear();
    cytoscapeMock.instance.animate.mockClear();
    cytoscapeMock.instance.fit.mockClear();
    cytoscapeMock.instance.resize.mockClear();
    cytoscapeMock.node.addClass.mockClear();
    cytoscapeMock.node.select.mockClear();
    Object.keys(cytoscapeMock.handlers).forEach(key => delete cytoscapeMock.handlers[key]);
    resizeCallback = null;
    globalThis.ResizeObserver = class {
      constructor(callback: ResizeObserverCallback) {
        resizeCallback = callback;
      }
      observe() {}
      unobserve() {}
      disconnect() {}
    };
  });

  it('starts empty and does not query the full graph until a seed is chosen', () => {
    renderMap();

    expect(screen.getByText(t.lineage.schematic.seedEmptyTitle)).toBeInTheDocument();
    expect(apiState.scopes.at(-1)).toMatchObject({ enabled: false, seeds: [] });
    expect(cytoscapeMock.cytoscape).not.toHaveBeenCalled();
  });

  it('loads a scoped graph from object search', async () => {
    renderMap();

    await chooseSeed('INB');

    await waitFor(() => {
      expect(apiState.scopes.at(-1)).toMatchObject({ enabled: true, seeds: ['INB'], depth: 2 });
      expect(cytoscapeMock.cytoscape).toHaveBeenCalled();
    });
  });

  it('resizes the Cytoscape canvas without refitting the camera', async () => {
    renderMap();
    await chooseSeed('INB');
    await waitFor(() => expect(cytoscapeMock.cytoscape).toHaveBeenCalled());

    resizeCallback?.([], {} as ResizeObserver);

    expect(cytoscapeMock.instance.resize).toHaveBeenCalled();
    expect(cytoscapeMock.instance.fit).not.toHaveBeenCalled();
  });

  it('does not animate the camera when focusing an already visible node', async () => {
    renderMap();
    await chooseSeed('INB');
    await waitFor(() => expect(cytoscapeMock.handlers['tap:node']).toBeTruthy());

    await act(async () => {
      cytoscapeMock.handlers['tap:node']({ target: { id: () => 'INB' } });
    });

    await waitFor(() => expect(cytoscapeMock.node.select).toHaveBeenCalled());
    expect(cytoscapeMock.instance.animate).not.toHaveBeenCalled();
  });

  it('opens node actions from the Cytoscape context gesture', async () => {
    renderMap();
    await chooseSeed('INB');
    await waitFor(() => expect(cytoscapeMock.handlers['cxttap:node']).toBeTruthy());

    await act(async () => {
      cytoscapeMock.handlers['cxttap:node']({
        originalEvent: { preventDefault: vi.fn() },
        renderedPosition: { x: 42, y: 48 },
        target: { id: () => 'INB' },
      });
    });

    expect(await screen.findByRole('menu')).toHaveTextContent('INB');
    expect(screen.getByRole('menuitem', { name: t.lineage.openObject })).toBeInTheDocument();
  });
});
