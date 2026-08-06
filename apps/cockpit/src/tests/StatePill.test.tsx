import { render } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { StatePill, CheckStatusCell } from '@/components/ui/StatePill';
import { t } from '@/i18n/de';

describe('StatePill', () => {
  it('renders a neutral pill with glyph, label and tooltip for skipped_stale', () => {
    const { container } = render(<StatePill state="skipped_stale" />);
    expect(container.querySelector('[role="tooltip"]')?.textContent).toBe(t.stateHint.skipped_stale);
    expect(container.textContent).toContain('⏸');
    expect(container.textContent).toContain(t.status.skipped_stale);
  });

  it('uses distinct glyphs for downgraded and error states', () => {
    expect(render(<StatePill state="downgraded" />).container.textContent).toContain('↓');
    expect(render(<StatePill state="error" />).container.textContent).toContain('⚠');
  });
});

describe('CheckStatusCell (G6 gating)', () => {
  it('renders the StatePill — not pass/fail styling — for a skipped_stale result', () => {
    const { container } = render(
      <CheckStatusCell state="skipped_stale" passed={false} severity="fail" />
    );
    // Neutral state pill: dashed border, dim color, no status colors.
    const html = container.innerHTML;
    const pill = container.querySelector('[aria-label]') as HTMLElement;
    expect(pill.textContent).toContain(t.status.skipped_stale);
    expect(html).toContain('dashed');
    expect(html).not.toContain('var(--status-ok)');
    expect(html).not.toContain('var(--status-fail)');
    // No pass/fail label leaks through.
    expect(pill.textContent).not.toMatch(/pass|fail/i);
  });

  it('renders the pass/fail StatusPill for an executed result', () => {
    const { container } = render(
      <CheckStatusCell state="executed" passed={true} severity="fail" />
    );
    expect(container.textContent).toContain('Bestanden');
    expect(container.innerHTML).not.toContain('dashed');
  });
});
