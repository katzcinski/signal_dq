import { renderHook, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { useRunStream } from '@/api/runs';
import type { ReactNode } from 'react';

// Minimal EventSource stand-in: jsdom has no EventSource, so we record the
// instances the hook opens and drive their handlers by hand.
class MockEventSource {
  static instances: MockEventSource[] = [];
  url: string;
  onmessage: ((ev: { data: string }) => void) | null = null;
  onerror: ((ev: unknown) => void) | null = null;
  closed = false;
  constructor(url: string) {
    this.url = url;
    MockEventSource.instances.push(this);
  }
  emit(obj: unknown) {
    this.onmessage?.({ data: JSON.stringify(obj) });
  }
  fail() {
    this.onerror?.({});
  }
  close() {
    this.closed = true;
  }
}

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

describe('useRunStream', () => {
  beforeEach(() => {
    MockEventSource.instances = [];
    vi.stubGlobal('EventSource', MockEventSource);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('opens an SSE connection to /api/stream for the run', () => {
    renderHook(() => useRunStream('run-123', true), { wrapper });
    expect(MockEventSource.instances).toHaveLength(1);
    expect(MockEventSource.instances[0].url).toBe('/api/stream?run_id=run-123');
  });

  it('does not open a connection when inactive', () => {
    renderHook(() => useRunStream('run-123', false), { wrapper });
    expect(MockEventSource.instances).toHaveLength(0);
  });

  it('accumulates progress lines and ignores non-progress frames', async () => {
    const { result } = renderHook(() => useRunStream('run-1', true), { wrapper });
    const es = MockEventSource.instances[0];

    act(() => {
      es.emit({ type: 'connected', run_id: 'run-1' });
      es.emit({ type: 'run_started', run_id: 'run-1', dataset: 'DS_X' });
      es.emit({ type: 'progress', run_id: 'run-1', ts: 't1', line: 'check A ok' });
      es.emit({ type: 'progress', run_id: 'run-1', ts: 't2', line: 'check B fail' });
    });

    await waitFor(() => expect(result.current.events).toHaveLength(2));
    expect(result.current.events.map(e => e.line)).toEqual(['check A ok', 'check B fail']);
  });

  it('closes the stream on a terminal event', async () => {
    renderHook(() => useRunStream('run-1', true), { wrapper });
    const es = MockEventSource.instances[0];

    act(() => {
      es.emit({ type: 'progress', run_id: 'run-1', ts: 't1', line: 'line' });
      es.emit({ type: 'run_finished', run_id: 'run-1', overall_status: 'pass' });
    });

    await waitFor(() => expect(es.closed).toBe(true));
  });
});
