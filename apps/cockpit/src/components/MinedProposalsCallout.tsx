import { useNavigate } from 'react-router-dom';
import { useProposals, useProposalAction } from '@/api/proposals';
import { t } from '@/i18n/de';

// Empty-state nudge (WS5-2 / NN-g): when an object has no guarantees yet, the
// deterministic miner's open suggestions are the most useful call to action —
// "here are N mined suggestions" beats a blank panel. Suggestions can be
// accepted/rejected inline (optimistic via useProposalAction). Renders nothing
// when the object has no open proposals, so callers can drop it into any empty
// state.
export function MinedProposalsCallout({ productId }: { productId: string }) {
  const { data: proposals = [] } = useProposals();
  const action = useProposalAction();
  const navigate = useNavigate();
  const open = proposals.filter(p => p.product === productId && p.status === 'open');
  if (open.length === 0) return null;

  const top = open.slice(0, 3);
  const rowBtn = (variant: 'primary' | 'ghost'): React.CSSProperties => ({
    background: variant === 'primary' ? 'var(--cont)' : 'var(--bg-2)',
    color: variant === 'primary' ? '#fff' : 'var(--fg-2)',
    border: variant === 'primary' ? 'none' : '1px solid var(--line-2)',
    borderRadius: 'var(--r-md)', padding: '4px 10px', fontSize: 11, cursor: 'pointer',
  });

  return (
    <div style={{
      marginBottom: 16, padding: 'var(--s4)', borderRadius: 'var(--r-lg)',
      background: 'var(--bg-1)', border: '1px solid var(--cont)',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--s2)' }}>
        <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--fg)' }}>
          {t.mined.title} ({open.length})
        </span>
        <div style={{ flex: 1 }} />
        <button
          onClick={() => navigate(`/proposals?product=${encodeURIComponent(productId)}`)}
          style={{
            background: 'var(--cont)', color: '#fff', border: 'none',
            borderRadius: 'var(--r-md)', padding: '5px 12px', fontSize: 12, cursor: 'pointer',
          }}
        >
          {t.mined.review} →
        </button>
      </div>
      <p style={{ color: 'var(--fg-3)', fontSize: 12, margin: '4px 0 12px' }}>{t.mined.hint}</p>
      {top.map(p => (
        <div key={p.id} style={{ borderTop: '1px solid var(--line)', padding: 'var(--s2) 0', fontSize: 12 }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 'var(--s2)' }}>
            <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--fg)' }}>{p.check_name}</span>
            <span style={{ marginLeft: 'auto', color: 'var(--fg-3)', fontSize: 11 }}>
              {t.mined.confidence} {Math.round(p.confidence * 100)}%
            </span>
          </div>
          <div style={{ fontFamily: 'var(--font-mono)', color: 'var(--cont)', marginTop: 2 }}>{p.proposed_expect}</div>
          {p.rationale && <div style={{ color: 'var(--fg-3)', marginTop: 2 }}>{p.rationale}</div>}
          <div style={{ display: 'flex', gap: 'var(--s2)', marginTop: 6 }}>
            <button
              style={rowBtn('primary')}
              disabled={action.isPending}
              onClick={() => action.mutate({ id: p.id, action: 'accept' })}
            >
              {t.mined.accept}
            </button>
            <button
              style={rowBtn('ghost')}
              disabled={action.isPending}
              onClick={() => action.mutate({ id: p.id, action: 'reject' })}
            >
              {t.mined.reject}
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}
