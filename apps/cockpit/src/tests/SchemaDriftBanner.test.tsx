import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { SchemaDriftBanner } from '@/components/SchemaDriftBanner';
import type { SchemaDriftReport } from '@/types';

const state = vi.hoisted(() => ({ report: undefined as SchemaDriftReport | undefined }));

vi.mock('@/api/contracts', () => ({
  useSchemaDrift: () => ({ data: state.report, isLoading: false, isError: false }),
}));

function report(over: Partial<SchemaDriftReport>): SchemaDriftReport {
  return {
    product: 'DS_SALES_ORDERS', dataset: 'DS_SALES_ORDERS',
    object_found: true, kind: 'consumer_contract',
    findings: [], summary: { total: 0, breaking: 0, has_breaking: false, by_category: {} },
    history: [], ...over,
  };
}

describe('SchemaDriftBanner', () => {
  it('renders nothing when the source matches the promise', () => {
    state.report = report({ findings: [] });
    const { container } = render(<SchemaDriftBanner product="DS_SALES_ORDERS" />);
    expect(container.firstChild).toBeNull();
  });

  it('renders nothing when the object is not in the inventory', () => {
    state.report = report({ object_found: false });
    const { container } = render(<SchemaDriftBanner product="DS_SALES_ORDERS" />);
    expect(container.firstChild).toBeNull();
  });

  it('surfaces breaking drift findings with the breaking badge', () => {
    state.report = report({
      findings: [{ category: 'column_removed', column: 'C', before: 'C', after: '', breaking: true }],
      summary: { total: 1, breaking: 1, has_breaking: true, by_category: { column_removed: 1 } },
    });
    render(<SchemaDriftBanner product="DS_SALES_ORDERS" />);
    expect(screen.getByText(/weicht vom Versprechen ab/i)).toBeTruthy();
    expect(screen.getAllByText('C').length).toBeGreaterThan(0);
    expect(screen.getByText(/Spalte entfernt/i)).toBeTruthy();
  });
});
