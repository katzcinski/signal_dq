import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { EXTRACT_PROGRESS_META_PREFIX, InventoryExtractProgress } from '@/components/InventoryExtractProgress';
import type { ExtractOperationResult, ExtractStatus } from '@/api/extract';
import type { OperationStatus } from '@/types';

const status: ExtractStatus = {
  op_id: 'op-1',
  job_id: 'op-1',
  status: 'running',
  environment: 'default',
  profile: 'default',
  spaces: [],
  source: 'datasphere-catalog',
  started_at: '2026-06-29T10:00:00Z',
  updated_at: '2026-06-29T10:00:01Z',
  finished_at: null,
  current_step: 'extracting_objects',
  counts: { inventory_items: 0, lineage_nodes: 0, lineage_edges: 0 },
  warnings: [],
  error: null,
  runtime_artifact_paths: { inventory: 'inventory.json', lineage: 'lineage.json' },
  published_snapshot_timestamp: null,
  can_trigger: true,
};

const operation: OperationStatus<ExtractOperationResult> = {
  op_id: 'op-1',
  kind: 'inventory_extract',
  state: 'running',
  created_by: 'admin',
  started_at: '2026-06-29T10:00:00Z',
  finished_at: null,
  error: null,
  result: null,
  progress: [
    {
      ts: '2026-06-29T10:00:00Z',
      line: `${EXTRACT_PROGRESS_META_PREFIX}{"kind":"extract","phase":"source","source":"datasphere-catalog"}`,
    },
    { ts: '2026-06-29T10:00:00Z', line: 'Source   : datasphere-catalog' },
    {
      ts: '2026-06-29T10:00:01Z',
      line: `${EXTRACT_PROGRESS_META_PREFIX}{"kind":"extract","phase":"load_objects","object_type":"views","current":2,"total":5,"name":"V_CUSTOMER","source":"datasphere-catalog"}`,
    },
    { ts: '2026-06-29T10:00:01Z', line: '  [  2/5] V_CUSTOMER' },
  ],
};

const cliRowMatcher = (pattern: RegExp) => (_: string, element: Element | null) =>
  element instanceof HTMLDivElement &&
  element.childElementCount === 1 &&
  pattern.test(element.textContent ?? '');

describe('InventoryExtractProgress', () => {
  it('renders overview cards from structured progress metadata', () => {
    render(<InventoryExtractProgress operation={operation} status={status} />);

    expect(screen.getByText('V_CUSTOMER')).toBeInTheDocument();
    expect(screen.getByText('2 / 5')).toBeInTheDocument();
    expect(screen.getByText('Live-Status')).toBeInTheDocument();
  });

  it('toggles to CLI mode and hides metadata lines', () => {
    render(<InventoryExtractProgress operation={operation} status={status} />);

    fireEvent.click(screen.getByRole('button', { name: 'CLI' }));

    expect(screen.getByText(cliRowMatcher(/^2026-06-29T10:00:00Z Source\s+: datasphere-catalog$/))).toBeInTheDocument();
    expect(screen.getByText(cliRowMatcher(/^2026-06-29T10:00:01Z\s+\[\s+2\/5\] V_CUSTOMER$/))).toBeInTheDocument();
    expect(screen.queryByText(/"phase":"load_objects"/)).not.toBeInTheDocument();
  });
});
