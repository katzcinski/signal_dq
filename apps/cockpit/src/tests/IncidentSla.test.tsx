import { render } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { IncidentSla } from '@/components/ui/IncidentSla';
import { t } from '@/i18n/de';
import type { Incident } from '@/types';

function incident(over: Partial<Incident>): Incident {
  return {
    id: 1, product: 'DS_X', run_id: 'r1', severity: 'fail', status: 'open',
    owner: '', title: 'T', failed_checks: [], opened_at: new Date().toISOString(),
    resolved_at: null, contract_version: '1', kind: 'consumer_contract', ...over,
  };
}

const minsAgo = (m: number) => new Date(Date.now() - m * 60_000).toISOString();

describe('IncidentSla', () => {
  it('breaches (red) when a critical incident is unacknowledged past its 60m SLA', () => {
    const { container } = render(<IncidentSla incident={incident({ severity: 'critical', status: 'open', opened_at: minsAgo(90) })} />);
    const span = container.querySelector('span[role="img"]')!;
    expect(span.getAttribute('aria-label')).toContain(t.incidents.slaUnacknowledged);
    expect(span.getAttribute('aria-label')).toContain(t.incidents.slaBreached);
    expect(span.getAttribute('style')).toContain('var(--status-fail)');
  });

  it('warns (amber) for a fail incident between warn and breach thresholds', () => {
    const { container } = render(<IncidentSla incident={incident({ severity: 'fail', status: 'open', opened_at: minsAgo(90) })} />);
    const span = container.querySelector('span[role="img"]')!;
    expect(span.getAttribute('style')).toContain('var(--status-warn)');
    expect(span.getAttribute('aria-label')).not.toContain(t.incidents.slaBreached);
  });

  it('stays neutral for a freshly opened incident', () => {
    const { container } = render(<IncidentSla incident={incident({ severity: 'fail', status: 'open', opened_at: minsAgo(2) })} />);
    const span = container.querySelector('span[role="img"]')!;
    expect(span.getAttribute('style')).toContain('var(--fg-3)');
  });

  it('labels acknowledged incidents as open-for, not unacknowledged', () => {
    const { container } = render(<IncidentSla incident={incident({ status: 'acknowledged', opened_at: minsAgo(10) })} />);
    const span = container.querySelector('span[role="img"]')!;
    expect(span.getAttribute('aria-label')).toContain(t.incidents.slaOpenFor);
  });

  it('shows resolution time with no urgency for resolved incidents', () => {
    const opened = minsAgo(180);
    const resolved = minsAgo(60); // resolved after 2h
    const { container } = render(<IncidentSla incident={incident({ severity: 'critical', status: 'resolved', opened_at: opened, resolved_at: resolved })} />);
    const span = container.querySelector('span[role="img"]')!;
    expect(span.getAttribute('aria-label')).toContain(t.incidents.slaResolvedAfter);
    // resolved is always neutral even though severity is critical and >SLA
    expect(span.getAttribute('style')).toContain('var(--fg-3)');
    expect(span.textContent).toContain('2 Std.');
  });
});
