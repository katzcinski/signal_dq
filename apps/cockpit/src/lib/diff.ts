// Pure diff-semantics helpers (UX-N13). No i18n/React here so the logic stays
// unit-testable; components apply the German labels.

export type ExpectDirection = 'loosened' | 'tightened' | 'changed';

export interface ExpectDelta {
  direction: ExpectDirection;
  currentOp: string;
  currentVal: number | null;
  proposedOp: string;
  proposedVal: number | null;
  deltaPct: number | null; // signed % change of the numeric bound, if computable
}

export const OP_SYMBOL: Record<string, string> = {
  '<=': '≤', '>=': '≥', '<': '<', '>': '>', '=': '=', '!=': '≠', '': '',
};

function parseExpect(s: string): { op: string; val: number | null } {
  const m = (s || '').trim().match(/^(<=|>=|!=|=|<|>)?\s*(-?\d+(?:\.\d+)?)/);
  if (!m) return { op: '', val: null };
  return { op: m[1] ?? '=', val: Number(m[2]) };
}

/**
 * Interpret the meaning of a `current_expect → proposed_expect` change:
 * is the threshold being loosened (more rows pass) or tightened?
 */
export function diffExpect(current: string, proposed: string): ExpectDelta {
  const c = parseExpect(current);
  const p = parseExpect(proposed);

  let direction: ExpectDirection = 'changed';
  if (c.val !== null && p.val !== null && p.val !== c.val) {
    const op = p.op || c.op;
    if (op === '<=' || op === '<') direction = p.val > c.val ? 'loosened' : 'tightened';
    else if (op === '>=' || op === '>') direction = p.val < c.val ? 'loosened' : 'tightened';
  }

  const deltaPct =
    c.val !== null && p.val !== null && c.val !== 0
      ? Math.round(((p.val - c.val) / Math.abs(c.val)) * 100)
      : null;

  return {
    direction,
    currentOp: c.op,
    currentVal: c.val,
    proposedOp: p.op,
    proposedVal: p.val,
    deltaPct,
  };
}
