import { fireEvent, render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Combobox } from '@/components/ui/Combobox';
import { Field, Input, Select } from '@/components/ui/Field';
import { SectionHeader } from '@/components/ui/SectionHeader';
import { Tooltip } from '@/components/ui/Tooltip';
import { PageHeader } from '@/components/ui/PageHeader';
import { FilterChip, ActiveFilterChip } from '@/components/ui/FilterChip';

describe('UI primitives (UX-F6)', () => {
  it('Button pulls radius from the token and reflects disabled state', () => {
    const { rerender } = render(<Button>Go</Button>);
    const btn = screen.getByRole('button', { name: 'Go' });
    expect(btn.style.borderRadius).toBe('var(--r-md)');
    expect(btn.style.cursor).toBe('pointer');
    rerender(<Button disabled>Go</Button>);
    expect(screen.getByRole('button', { name: 'Go' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Go' }).style.cursor).toBe('not-allowed');
  });

  it('Button variant sets the primary accent', () => {
    render(<Button variant="primary">Save</Button>);
    expect(screen.getByRole('button', { name: 'Save' }).style.background).toBe('var(--cont)');
  });

  it('Card spacing comes from the token scale', () => {
    const { container } = render(<Card pad="md">x</Card>);
    const el = container.firstElementChild as HTMLElement;
    expect(el.style.padding).toBe('var(--s4)');
    expect(el.style.borderRadius).toBe('var(--r-lg)');
  });

  it('Field wraps a control with its label', () => {
    render(<Field label="Name"><Input value="" onChange={() => {}} /></Field>);
    expect(screen.getByText('Name')).toBeInTheDocument();
    expect(screen.getByRole('textbox')).toBeInTheDocument();
  });

  it('Select renders options from the shared control style', () => {
    render(<Select aria-label="pick"><option value="a">a</option></Select>);
    const sel = screen.getByLabelText('pick');
    expect(sel.style.borderRadius).toBe('var(--r-md)');
  });

  it('SectionHeader shows the title and count', () => {
    render(<SectionHeader title="Channels" count={3} />);
    expect(screen.getByText('Channels (3)')).toBeInTheDocument();
  });

  it('Tooltip renders hover content without replacing the trigger', () => {
    render(<Tooltip content="More context"><button>Info</button></Tooltip>);
    expect(screen.getByRole('button', { name: 'Info' })).toBeInTheDocument();
    expect(screen.getByRole('tooltip')).toHaveTextContent('More context');
  });

  it('PageHeader renders the title from the token and an optional subtitle + actions slot', () => {
    render(
      <PageHeader
        title="Objekte"
        subtitle="Steward · offen"
        actions={<button>Neu</button>}
      />,
    );
    const heading = screen.getByRole('heading', { name: 'Objekte' });
    expect(heading.style.fontSize).toBe('var(--fs-page-title)');
    expect(screen.getByText('Steward · offen')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Neu' })).toBeInTheDocument();
  });

  it('FilterChip reflects the active tone and fires onClick', () => {
    const onClick = vi.fn();
    const { rerender } = render(<FilterChip active={false} onClick={onClick}>Quality</FilterChip>);
    const chip = screen.getByRole('button', { name: 'Quality' });
    expect(chip).toHaveAttribute('aria-pressed', 'false');
    expect(chip.style.background).toBe('var(--bg-2)');
    fireEvent.click(chip);
    expect(onClick).toHaveBeenCalledOnce();
    rerender(<FilterChip active onClick={onClick}>Quality</FilterChip>);
    expect(screen.getByRole('button', { name: 'Quality' }).style.background).toBe('var(--cont)');
  });

  it('ActiveFilterChip clears its single filter', () => {
    const onClear = vi.fn();
    render(<ActiveFilterChip label="pass" onClear={onClear} />);
    fireEvent.click(screen.getByRole('button'));
    expect(onClear).toHaveBeenCalledOnce();
  });

  it('Combobox listbox escapes clipping containers', () => {
    render(
      <div data-testid="clip" style={{ overflow: 'hidden' }}>
        <Combobox options={['alpha', 'beta']} value="" onChange={() => {}} placeholder="Pick" />
      </div>,
    );

    const combobox = screen.getByRole('combobox', { name: 'Pick' });
    expect(combobox).toHaveAttribute('aria-autocomplete', 'list');
    expect((combobox as HTMLInputElement).style.outline).toBe('');

    fireEvent.focus(combobox);

    const listbox = screen.getByRole('listbox');
    expect(screen.getByTestId('clip')).not.toContainElement(listbox);
    expect(listbox.parentElement).toBe(document.body);
    expect(listbox.style.position).toBe('fixed');
    expect(combobox).toHaveAttribute('aria-controls', listbox.id);
  });
});
