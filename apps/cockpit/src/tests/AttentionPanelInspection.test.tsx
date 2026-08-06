import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { AttentionPanel } from '@/components/AttentionPanel';
import type { ObjectSummary } from '@/types';

const OBJECT = {
  id: 'obj1',
  name: 'MY_TABLE',
  schema_name: 'S',
  family: 'quality',
  layer: 'reporting',
  status: 'fail',
  family_status: { observability: 'pass', quality: 'fail' },
  contract_status: '',
  cov_flag: 'gap',
  check_count: 7,
  owned_by: 'team',
  last_run: null,
  space: 'SALES',
} as unknown as ObjectSummary;

describe('AttentionPanel inspection wiring', () => {
  it('calls onInspect with the object id when a hotspot is clicked', () => {
    const onInspect = vi.fn();
    render(
      <MemoryRouter>
        <AttentionPanel objects={[OBJECT]} onInspect={onInspect} />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByLabelText('Checks für MY_TABLE anzeigen'));
    expect(onInspect).toHaveBeenCalledTimes(1);
    expect(onInspect.mock.calls[0][0]).toBe('obj1');
  });

  it('falls back to navigation (no inspect label) when onInspect is absent', () => {
    render(
      <MemoryRouter>
        <AttentionPanel objects={[OBJECT]} />
      </MemoryRouter>,
    );

    // Ohne onInspect kein Popover-Trigger — die Zeile bleibt ein reiner Link.
    expect(screen.queryByLabelText('Checks für MY_TABLE anzeigen')).toBeNull();
    expect(screen.getByText('MY_TABLE')).toBeTruthy();
  });
});
