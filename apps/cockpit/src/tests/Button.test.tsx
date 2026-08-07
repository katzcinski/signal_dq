import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { Button } from '@/components/ui/Button';

describe('Button', () => {
  it('renders a neutral action with the secondary surface', () => {
    const { getByRole } = render(<Button>Los</Button>);
    const btn = getByRole('button') as HTMLButtonElement;
    expect(btn.disabled).toBe(false);
    expect(btn.style.cursor).toBe('pointer');
    expect(btn.style.background).toBe('var(--bg-2)');
    expect(btn.style.color).toBe('var(--fg-2)');
  });

  it('renders a primary action with the container accent', () => {
    render(<Button variant="primary">Start</Button>);
    const btn = screen.getByRole('button') as HTMLButtonElement;
    expect(btn.style.background).toBe('var(--cont)');
    expect(btn.style.color).toBe('rgb(255, 255, 255)');
  });

  it('UX-F8: disabled reads via a tone-shift, not a pure opacity fade', () => {
    const { getByRole } = render(<Button variant="primary" disabled>Los</Button>);
    const btn = getByRole('button') as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
    expect(btn.style.cursor).toBe('not-allowed');
    // no opacity fade — disabled is encoded through colour, not transparency
    expect(btn.style.opacity).toBe('');
    expect(btn.style.background).toBe('var(--bg-2)');
    expect(btn.style.color).toBe('var(--fg-3)');
    expect(btn.style.border).toBe('1px solid var(--line)');
  });

  it('keeps a transition so hover/active animate rather than jump', () => {
    const { getByRole } = render(<Button>Los</Button>);
    expect((getByRole('button') as HTMLButtonElement).style.transition).toContain('filter');
  });

  it('swaps to the pending label and disables interaction while pending', () => {
    render(<Button pending pendingLabel="Speichert">Speichern</Button>);
    const btn = screen.getByRole('button') as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
    expect(btn).toHaveTextContent('Speichert');
    expect(btn).not.toHaveTextContent('Speichern');
    expect(btn.style.cursor).toBe('wait');
    expect(btn).toHaveAttribute('aria-busy', 'true');
  });
});
