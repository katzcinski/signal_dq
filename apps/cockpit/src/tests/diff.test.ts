import { describe, it, expect } from 'vitest';
import { diffExpect } from '@/lib/diff';

describe('diffExpect (UX-N13)', () => {
  it('detects a loosened upper bound', () => {
    const d = diffExpect('<= 5', '<= 8');
    expect(d.direction).toBe('loosened');
    expect(d.deltaPct).toBe(60);
  });

  it('detects a tightened upper bound', () => {
    const d = diffExpect('<= 8', '<= 4');
    expect(d.direction).toBe('tightened');
    expect(d.deltaPct).toBe(-50);
  });

  it('treats a raised lower bound as tightened', () => {
    const d = diffExpect('>= 0.90', '>= 0.95');
    expect(d.direction).toBe('tightened');
  });

  it('treats a lowered lower bound as loosened', () => {
    const d = diffExpect('>= 0.95', '>= 0.80');
    expect(d.direction).toBe('loosened');
  });

  it('falls back to "changed" for non-numeric or equality expectations', () => {
    expect(diffExpect('IN (a,b)', 'IN (a,b,c)').direction).toBe('changed');
    expect(diffExpect('= 0', '= 1').direction).toBe('changed');
  });
});
