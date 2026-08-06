import { render, fireEvent, screen } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { BadgeEmbed } from '@/components/BadgeEmbed';
import { t } from '@/i18n/de';

// sonner's toast is a side-effect we don't assert on here.
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

describe('BadgeEmbed', () => {
  beforeEach(() => {
    Object.assign(navigator, {
      clipboard: { writeText: vi.fn().mockResolvedValue(undefined) },
    });
  });

  it('renders a same-origin preview image for the product', () => {
    render(<BadgeEmbed product="DS_SALES_ORDERS" />);
    const img = screen.getByAltText('DQ DS_SALES_ORDERS') as HTMLImageElement;
    // Preview uses the relative path so the dev proxy serves it.
    expect(img.getAttribute('src')).toBe('/api/badge/DS_SALES_ORDERS');
  });

  it('copies an absolute Markdown snippet to the clipboard', () => {
    render(<BadgeEmbed product="DS_X" />);
    fireEvent.click(screen.getByText(t.badge.copyMarkdown));
    const written = (navigator.clipboard.writeText as ReturnType<typeof vi.fn>).mock.calls[0][0];
    expect(written).toBe(`![DQ DS_X](${window.location.origin}/api/badge/DS_X)`);
  });

  it('url-encodes the product in the badge path', () => {
    render(<BadgeEmbed product="A B" />);
    const img = screen.getByAltText('DQ A B') as HTMLImageElement;
    expect(img.getAttribute('src')).toBe('/api/badge/A%20B');
  });
});
