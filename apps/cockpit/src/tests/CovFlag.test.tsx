import { render } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { CovFlag } from '@/components/ui/CovFlag';
import { t } from '@/i18n/de';

describe('CovFlag', () => {
  it('renders the covered symbol with a tooltip', () => {
    const { container } = render(<CovFlag flag="covered" />);
    expect(container.querySelector('[role="tooltip"]')?.textContent).toBe(t.lineage.tooltips.covered);
    const span = container.querySelector('[role="img"]');
    expect(span?.getAttribute('aria-label')).toContain(t.lineage.tooltips.covered);
    expect(span?.textContent).toContain('●');
  });

  it('renders distinct symbols per coverage state', () => {
    const gap = render(<CovFlag flag="gap" />).container.textContent;
    const none = render(<CovFlag flag="out_of_scope" />).container.textContent;
    expect(gap).not.toEqual(none);
  });

  it('shows a label when requested', () => {
    const { container } = render(<CovFlag flag="partial" showLabel />);
    expect(container.textContent).toContain('partial');
  });
});
