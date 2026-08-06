import { fireEvent, render, screen, within } from '@testing-library/react';
import { beforeEach, describe, it, expect, vi } from 'vitest';
import { t } from '@/i18n/de';
import type { DigestPreview, NotificationConfig } from '@/types';

const h = vi.hoisted(() => ({
  cfg: { current: null as NotificationConfig | null },
  digest: { current: undefined as DigestPreview | undefined },
  deleteChannel: vi.fn(),
  createRule: vi.fn(),
  sendDigest: vi.fn(),
}));

// Mock the API layer so the page renders without react-query/axios.
vi.mock('@/api/notifications', () => {
  const noopMut = () => ({ mutate: () => {}, isPending: false });
  return {
    useNotificationConfig: () => ({ data: h.cfg.current, isLoading: false, isError: false, refetch: () => {} }),
    useCreateChannel: noopMut, usePatchChannel: noopMut,
    useDeleteChannel: () => ({ mutate: h.deleteChannel, isPending: false }),
    useCreateRule: () => ({ mutate: h.createRule, isPending: false }), useDeleteRule: noopMut,
    useCreateMute: noopMut, useDeleteMute: noopMut,
    useDigestPreview: () => ({ data: h.digest.current }),
    useSendDigest: () => ({ mutate: h.sendDigest, isPending: false }),
  };
});

vi.mock('@/store/role', () => ({
  useRoleStore: (selector: (state: { role: string }) => unknown) => selector({ role: 'admin' }),
}));

import Notifications from '@/pages/Notifications';

const baseConfig = (overrides: Partial<NotificationConfig> = {}): NotificationConfig => ({
  channels: [{ id: 1, name: 'Ops Slack', type: 'slack', url: 'https://hooks.slack.example.com/x', enabled: true, digest_enabled: false, created_at: '', created_by: '' }],
  rules: [{ id: 1, name: 'Critical SALES', channel_id: 1, match_severity: 'critical', match_space: 'SALES', match_product: '', match_owned_by: '', match_owner: '', match_kind: '', enabled: true, created_at: '', created_by: '' }],
  mutes: [],
  can_edit: true,
  ...overrides,
});

const digestPreview = (over: Partial<DigestPreview> = {}): DigestPreview => ({
  period_hours: 24, generated_at: '2026-08-03T12:00:00Z',
  incidents_new: 2, incidents_new_by_severity: { fail: 2 }, incidents_open: 3,
  top_incidents: [], runs: 10, runs_failed: 1, gate_verdicts: { proceed: 10 },
  quarantine_open: 1, drift_objects: 1, drift_breaking_objects: 0,
  enabled: false, interval_hours: 24, subscribed_channels: 1, last_sent_at: null,
  ...over,
});

describe('Notifications page (UX-N2)', () => {
  beforeEach(() => {
    h.digest.current = undefined;
    h.deleteChannel.mockClear();
    h.createRule.mockClear();
    h.sendDigest.mockClear();
  });

  it('renders channels and rule facets routing to the channel', () => {
    h.cfg.current = baseConfig();
    render(<Notifications />);
    expect(screen.getAllByText('Ops Slack').length).toBeGreaterThan(0);
    expect(screen.getByText('Critical SALES')).toBeInTheDocument();
    // combined facet summary (unique): "Severity=critical · Space=SALES"
    expect(screen.getByText(/Severity=critical.*Space=SALES/)).toBeInTheDocument();
    expect(screen.getByText(t.notifications.addChannel)).toBeInTheDocument();
    expect(screen.getByText(t.notifications.addRule)).toBeInTheDocument();
  });

  it('shows the read-only banner and hides add forms for non-admins', () => {
    h.cfg.current = baseConfig({ can_edit: false });
    render(<Notifications />);
    expect(screen.getByText(t.role.readOnlyBanner)).toBeInTheDocument();
    expect(screen.queryByText(t.notifications.addChannel)).not.toBeInTheDocument();
    expect(screen.queryByText(t.notifications.addMute)).not.toBeInTheDocument();
  });

  it('submits a rule with the synced channel once the first channel exists', () => {
    // Start ohne Kanäle: das Regelformular ist noch nicht montiert.
    h.cfg.current = baseConfig({ channels: [], rules: [] });
    const { rerender } = render(<Notifications />);
    expect(screen.queryByText(t.notifications.addRule)).not.toBeInTheDocument();

    // Erster Kanal wird angelegt → Regelformular erscheint, channelId synchronisiert.
    h.cfg.current = baseConfig({ rules: [] });
    rerender(<Notifications />);

    const ruleForm = screen.getByText(t.notifications.addRule).closest('div') as HTMLElement;
    fireEvent.change(within(ruleForm).getByLabelText(t.notifications.name), { target: { value: 'My Rule' } });
    fireEvent.click(screen.getByText(t.notifications.addRule));

    // submit() no-opt nicht mehr stumm: createRule wird mit dem sichtbaren Kanal aufgerufen.
    expect(h.createRule).toHaveBeenCalledTimes(1);
    expect(h.createRule.mock.calls[0][0]).toMatchObject({ name: 'My Rule', channel_id: 1 });
  });

  it('requires confirmation before deleting a channel', () => {
    h.cfg.current = baseConfig();
    render(<Notifications />);

    fireEvent.click(screen.getAllByText(t.notifications.delete)[0]);
    expect(h.deleteChannel).not.toHaveBeenCalled();

    fireEvent.click(screen.getByText(t.common.confirm));
    expect(h.deleteChannel).toHaveBeenCalledWith(1);
  });

  it('renders the digest preview and sends on demand (V4)', () => {
    h.cfg.current = baseConfig();
    h.digest.current = digestPreview();
    render(<Notifications />);

    expect(screen.getByText(t.notifications.digestTitle)).toBeInTheDocument();
    expect(screen.getByText('1/10')).toBeInTheDocument(); // Läufe rot/gesamt
    fireEvent.click(screen.getByText(t.notifications.digestSendNow));
    expect(h.sendDigest).toHaveBeenCalledTimes(1);
  });

  it('disables sending when no channel subscribed', () => {
    h.cfg.current = baseConfig();
    h.digest.current = digestPreview({ subscribed_channels: 0 });
    render(<Notifications />);

    expect(screen.getByText(t.notifications.digestSendNow).closest('button')).toBeDisabled();
  });
});
