import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from './client';
import type { OperationProgressLine, OperationStatus } from '@/types';

export const useOperation = <T = unknown>(opId: string | null) =>
  useQuery<OperationStatus<T>>({
    queryKey: ['operations', opId],
    queryFn: () => api.get(`/operations/${opId}`).then(r => r.data),
    enabled: !!opId,
    refetchInterval: (query) =>
      query.state.data && query.state.data.state !== 'running' ? false : 1000,
  });

type OperationEvent<T> =
  | { type: 'connected'; op_id?: string; stream_id?: string; kind?: string }
  | { type: 'progress'; op_id?: string; stream_id?: string; ts: string; line: string }
  | { type: 'finished'; op_id: string; kind?: string; result: T | null }
  | { type: 'error'; op_id: string; kind?: string; error: string };

function mergeProgress(
  polled: OperationProgressLine[] = [],
  streamed: OperationProgressLine[] = [],
): OperationProgressLine[] {
  const seen = new Set<string>();
  return [...polled, ...streamed].filter(line => {
    const key = line.id != null ? `id:${line.id}` : `${line.ts}:${line.line}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

// Live operation progress via SSE, with the same polling endpoint as fallback.
export function useOperationStream<T = unknown>(opId: string | null) {
  const query = useOperation<T>(opId);
  const [streamed, setStreamed] = useState<OperationProgressLine[]>([]);
  const [streamFailed, setStreamFailed] = useState(false);

  useEffect(() => {
    if (!opId) {
      setStreamed([]);
      setStreamFailed(false);
      return;
    }

    setStreamed([]);
    setStreamFailed(false);
    const es = new EventSource(`/api/operations/${encodeURIComponent(opId)}/events`);

    es.onmessage = (ev) => {
      let msg: OperationEvent<T>;
      try {
        msg = JSON.parse(ev.data);
      } catch {
        return;
      }
      if (msg.type === 'progress') {
        setStreamed(prev => [...prev, { ts: msg.ts, line: msg.line }]);
      } else if (msg.type === 'finished' || msg.type === 'error') {
        es.close();
      }
    };

    es.onerror = () => {
      es.close();
      setStreamFailed(true);
    };

    return () => es.close();
  }, [opId]);

  const data = query.data
    ? {
        ...query.data,
        progress: streamFailed
          ? query.data.progress
          : mergeProgress(query.data.progress, streamed),
      }
    : query.data;

  return { ...query, data, streamFailed };
}
