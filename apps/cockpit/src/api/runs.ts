import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from './client';
import type { RunSummary, RunListItem, RunEvent, SSEEvent, RunCompare } from '@/types';

export const useRuns = () =>
  useQuery<RunListItem[]>({
    queryKey: ['runs'],
    queryFn: () => api.get('/runs').then(r => r.data),
  });

// UX-N5: server-computed regression diff of two runs (per-check transitions).
export const useRunCompare = (base: string, head: string) =>
  useQuery<RunCompare>({
    queryKey: ['runs', 'compare', base, head],
    queryFn: () => api.get('/runs/compare', { params: { base, head } }).then(r => r.data),
    enabled: !!base && !!head && base !== head,
  });

export const useRun = (id: string) =>
  useQuery<RunSummary>({
    queryKey: ['runs', id],
    queryFn: () => api.get(`/runs/${id}`).then(r => r.data),
    enabled: !!id,
    // Poll while the run is still executing so a triggered run (202) shows up.
    refetchInterval: (query) => query.state.data?.run_state === 'running' ? 2000 : false,
  });

// Polling fallback for live progress lines; used only when the SSE stream below
// is unavailable. Same DB-backed truth as SSE (see services/api/sse.py).
export const useRunEvents = (id: string, active: boolean) =>
  useQuery<RunEvent[]>({
    queryKey: ['runs', id, 'events'],
    queryFn: () => api.get(`/runs/${id}/events`).then(r => r.data),
    enabled: !!id && active,
    refetchInterval: active ? 2000 : false,
  });

// Live progress lines for an in-flight run, streamed from /api/stream (SSE).
// The backend persists every progress line to the store and replays it per
// consumer cursor, so SSE and the polling endpoint return identical content.
// If the stream errors (proxy, no SSE support), we fall back to useRunEvents.
export function useRunStream(id: string, active: boolean): { events: RunEvent[] } {
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [streamFailed, setStreamFailed] = useState(false);
  const [ended, setEnded] = useState(false);

  useEffect(() => {
    if (!id || !active) {
      setEvents([]);
      setStreamFailed(false);
      setEnded(false);
      return;
    }
    setEvents([]);
    setStreamFailed(false);
    setEnded(false);

    // EventSource is same-origin (Vite proxies /api → backend; prod serves both
    // from one origin). It cannot send an Authorization header, so this relies
    // on the same cookie/same-origin auth the rest of the app uses.
    const es = new EventSource(`/api/stream?run_id=${encodeURIComponent(id)}`);

    es.onmessage = (ev) => {
      let msg: SSEEvent;
      try {
        msg = JSON.parse(ev.data);
      } catch {
        return; // keepalive comment or malformed frame
      }
      if (msg.type === 'progress') {
        setEvents(prev => [...prev, { ts: msg.ts, line: msg.line }]);
      } else if (msg.type === 'run_finished' || msg.type === 'run_error') {
        setEnded(true);
        es.close();
      }
    };

    es.onerror = () => {
      // The browser auto-reconnects on transient errors; treat a surfaced error
      // as "stream unavailable" and let the polling fallback take over. If the
      // run already ended we just close quietly.
      es.close();
      setStreamFailed(true);
    };

    return () => es.close();
  }, [id, active]);

  // Fallback poll runs only while the stream has failed and the run is live.
  const fallback = useRunEvents(id, active && streamFailed && !ended);

  return { events: streamFailed ? (fallback.data ?? []) : events };
}
