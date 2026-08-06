import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { t } from '@/i18n/de';
import { SavedViewsBar, loadViews } from '@/components/SavedViewsBar';

const KEY = 'signal.catalog.views';

describe('loadViews', () => {
  beforeEach(() => localStorage.clear());

  it('returns [] for missing or broken storage payloads', () => {
    expect(loadViews()).toEqual([]);
    localStorage.setItem(KEY, 'kaputt{');
    expect(loadViews()).toEqual([]);
    localStorage.setItem(KEY, JSON.stringify({ nicht: 'liste' }));
    expect(loadViews()).toEqual([]);
  });

  it('filters malformed entries', () => {
    localStorage.setItem(KEY, JSON.stringify([
      { name: 'Gültig', params: { q: 'sales' } },
      { name: '', params: {} },
      { params: { q: 'x' } },
      null,
    ]));
    expect(loadViews()).toEqual([{ name: 'Gültig', params: { q: 'sales' } }]);
  });
});

describe('SavedViewsBar', () => {
  beforeEach(() => localStorage.clear());

  it('renders nothing without views and without active filter', () => {
    const { container } = render(
      <SavedViewsBar current={{}} hasActiveFilter={false} onApply={() => {}} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('saves the current filters under a name and applies them on click', () => {
    const onApply = vi.fn();
    render(
      <SavedViewsBar
        current={{ q: 'sales', family: 'quality', dqstatus: 'fail', space: '' }}
        hasActiveFilter
        onApply={onApply}
      />,
    );

    fireEvent.click(screen.getByText(`+ ${t.objects.savedViewSave}`));
    fireEvent.change(screen.getByLabelText(t.objects.savedViewNamePlaceholder), {
      target: { value: 'Meine roten Finance-Objekte' },
    });
    fireEvent.click(screen.getByText(t.common.confirm));

    expect(loadViews()).toEqual([
      { name: 'Meine roten Finance-Objekte', params: { q: 'sales', family: 'quality', dqstatus: 'fail', space: '' } },
    ]);

    fireEvent.click(screen.getByText('Meine roten Finance-Objekte'));
    expect(onApply).toHaveBeenCalledWith({ q: 'sales', family: 'quality', dqstatus: 'fail', space: '' });
  });

  it('deletes a view via its ✕ affordance', () => {
    localStorage.setItem(KEY, JSON.stringify([{ name: 'Alt', params: {} }]));
    render(<SavedViewsBar current={{}} hasActiveFilter={false} onApply={() => {}} />);

    fireEvent.click(screen.getByLabelText(t.objects.savedViewDelete.replace('{name}', 'Alt')));
    expect(loadViews()).toEqual([]);
    expect(screen.queryByText('Alt')).not.toBeInTheDocument();
  });

  it('overwrites an existing view with the same name', () => {
    localStorage.setItem(KEY, JSON.stringify([{ name: 'V', params: { q: 'alt' } }]));
    render(<SavedViewsBar current={{ q: 'neu' }} hasActiveFilter onApply={() => {}} />);

    fireEvent.click(screen.getByText(`+ ${t.objects.savedViewSave}`));
    fireEvent.change(screen.getByLabelText(t.objects.savedViewNamePlaceholder), { target: { value: 'V' } });
    fireEvent.keyDown(screen.getByLabelText(t.objects.savedViewNamePlaceholder), { key: 'Enter' });

    expect(loadViews()).toEqual([{ name: 'V', params: { q: 'neu' } }]);
  });
});
