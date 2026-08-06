import type { CovFlag } from '@/types';
import { t } from '@/i18n/de';
import { Tooltip } from './Tooltip';

const SYMBOLS: Record<CovFlag, string> = {
  covered:      '●',
  partial:      '◐',
  gap:          '▲',
  out_of_scope: '○',
};
const COLORS: Record<CovFlag, string> = {
  covered:      'var(--status-ok)',
  partial:      'var(--status-warn)',
  gap:          'var(--status-fail)',
  out_of_scope: 'var(--fg-3)',
};
const HINTS: Record<CovFlag, string> = {
  covered:      t.lineage.tooltips.covered,
  partial:      t.lineage.tooltips.partial,
  gap:          t.lineage.tooltips.gap,
  out_of_scope: t.lineage.tooltips.outOfScope,
};

interface Props { flag: CovFlag; showLabel?: boolean }

export function CovFlag({ flag, showLabel = false }: Props) {
  const hint = HINTS[flag];
  return (
    <Tooltip content={hint}>
      <span
        role="img"
        aria-label={`${flag}: ${hint}`}
        style={{ color: COLORS[flag], fontFamily: 'inherit', whiteSpace: 'nowrap' }}
      >
        {SYMBOLS[flag]}{showLabel && <span style={{ marginLeft: 4, fontSize: 11, color: 'var(--fg-2)' }}>{flag.replace('_', ' ')}</span>}
      </span>
    </Tooltip>
  );
}
