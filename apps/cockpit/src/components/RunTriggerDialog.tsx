import { useState } from 'react';
import { useEnvironments } from '@/api/objects';
import { t } from '@/i18n/de';

interface Props {
  onStart: (body: { environment?: string; execution_mode: string }) => void;
  onClose: () => void;
  pending: boolean;
}

const EXECUTION_MODES = ['auto', 'batch', 'isolated'];

const selectStyle: React.CSSProperties = {
  background: 'var(--bg-2)', border: '1px solid var(--line-2)',
  color: 'var(--fg)', borderRadius: 'var(--r-md)', padding: '6px 10px', fontSize: 13, width: '100%',
};

export function RunTriggerDialog({ onStart, onClose, pending }: Props) {
  const { data } = useEnvironments();
  const [environment, setEnvironment] = useState('');
  const [executionMode, setExecutionMode] = useState('auto');

  return (
    <div
      style={{
        position: 'fixed', inset: 0, zIndex: 900, background: 'rgba(0,0,0,0.5)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={t.objectDetail.runDialogTitle}
        onClick={e => e.stopPropagation()}
        onKeyDown={e => { if (e.key === 'Escape') onClose(); }}
        style={{
          background: 'var(--bg-1)', border: '1px solid var(--line-2)', borderRadius: 'var(--r-lg)',
          padding: 'var(--s5)', width: 360, display: 'flex', flexDirection: 'column', gap: 14,
        }}
      >
        <div style={{ fontWeight: 700, fontSize: 14 }}>{t.objectDetail.runDialogTitle}</div>

        <label style={{ display: 'flex', flexDirection: 'column', gap: 'var(--s1)', fontSize: 12, color: 'var(--fg-2)' }}>
          {t.objectDetail.environment}
          <select value={environment} onChange={e => setEnvironment(e.target.value)} style={selectStyle}>
            <option value="">{t.objectDetail.localMock}</option>
            {(data?.environments ?? []).map(env => (
              <option key={env.name} value={env.name}>{env.name} ({env.schema})</option>
            ))}
          </select>
        </label>

        <label style={{ display: 'flex', flexDirection: 'column', gap: 'var(--s1)', fontSize: 12, color: 'var(--fg-2)' }}>
          {t.objectDetail.executionMode}
          <select value={executionMode} onChange={e => setExecutionMode(e.target.value)} style={selectStyle}>
            {EXECUTION_MODES.map(m => <option key={m} value={m}>{m}</option>)}
          </select>
        </label>

        <div style={{ display: 'flex', gap: 'var(--s2)', justifyContent: 'flex-end' }}>
          <button
            onClick={onClose}
            style={{
              background: 'var(--bg-2)', color: 'var(--fg)', border: '1px solid var(--line-2)',
              borderRadius: 'var(--r-md)', padding: '7px 14px', fontSize: 13,
            }}
          >
            {t.common.cancel}
          </button>
          <button
            onClick={() => onStart({ environment: environment || undefined, execution_mode: executionMode })}
            disabled={pending}
            style={{
              background: 'var(--cont)', color: '#fff', border: 'none',
              borderRadius: 'var(--r-md)', padding: '7px 14px', fontSize: 13,
            }}
          >
            {pending ? t.objectDetail.running : t.common.start}
          </button>
        </div>
      </div>
    </div>
  );
}
