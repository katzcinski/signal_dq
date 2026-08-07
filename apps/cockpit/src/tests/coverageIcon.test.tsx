import { render } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { coverageIconDataUri, coverageColor, CoverageIcon } from '@/components/ui/coverageIcon';

const FLAGS = ['●', '◐', '▲', '○'];

describe('coverageIcon', () => {
  it('emits a decodable SVG data URI per flag', () => {
    for (const flag of FLAGS) {
      const uri = coverageIconDataUri(flag);
      expect(uri.startsWith('data:image/svg+xml,')).toBe(true);
      const svg = decodeURIComponent(uri.slice('data:image/svg+xml,'.length));
      expect(svg).toContain('<svg');
      expect(svg).toContain('viewBox="0 0 24 24"');
    }
  });

  it('uses a distinct mark for each flag (no two icons identical)', () => {
    const uris = FLAGS.map(f => coverageIconDataUri(f));
    expect(new Set(uris).size).toBe(FLAGS.length);
  });

  it('maps status colours to the design tokens (fallbacks in jsdom)', () => {
    expect(coverageColor('●')).toBe('#3FB07A');
    expect(coverageColor('▲')).toBe('#E2783C');
    // unknown flag falls back to the out-of-scope (grey) colour
    expect(coverageColor('???')).toBe(coverageColor('○'));
  });

  it('CoverageIcon renders an img with the flag data URI and alt label', () => {
    const { getByAltText } = render(<CoverageIcon flag="▲" size={14} label="Lücke" />);
    const img = getByAltText('Lücke') as HTMLImageElement;
    expect(img.getAttribute('src')).toBe(coverageIconDataUri('▲'));
    expect(img.getAttribute('width')).toBe('14');
  });
});
