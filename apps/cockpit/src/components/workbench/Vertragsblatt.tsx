// „Vertragsblatt": sticky rechte Spalte mit Versionssprung, YAML-Vorschau und
// Freigabepfad (Speichern → G1 → Kompilieren/Dry-Run → G3 → Aktivieren) als
// Leiterbahn mit Pins. Rein präsentational; Status + Aktionen kommen vom EditorPane.
import type { ReactNode } from 'react';
import { t } from '@/i18n/de';
import { monoStyle } from './shared';

export type PathStatus = 'done' | 'current' | 'pending' | 'blocked';
export interface PathStep { key: string; label: string; hint?: ReactNode; status: PathStatus; badge?: string }

const PIN: Record<PathStatus, { color: string; glyph: string }> = {
  done: { color: 'var(--status-ok)', glyph: '✓' },
  current: { color: 'var(--cont)', glyph: '◐' },
  blocked: { color: 'var(--status-warn)', glyph: '!' },
  pending: { color: 'var(--line-2)', glyph: '○' },
};

export function Vertragsblatt({ versionFrom, versionTo, majorRequired, yaml, steps, footer }: {
  versionFrom: string;
  versionTo: string;
  majorRequired: boolean;
  yaml: string;
  steps: PathStep[];
  footer?: ReactNode;
}) {
  return (
    <aside
      aria-label={t.workbench.sheet.title}
      style={{
        position: 'sticky', top: 'var(--s4)', alignSelf: 'start',
        background: 'var(--bg-1)', border: '1px solid var(--line)', borderRadius: 'var(--r-lg)',
        display: 'flex', flexDirection: 'column', gap: 'var(--s4)', padding: 'var(--s4)', minWidth: 0,
      }}
    >
      <div style={{ fontSize: 'var(--fs-eyebrow)', color: 'var(--fg-3)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
        {t.workbench.sheet.title}
      </div>

      {/* Versionssprung */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--s2)', flexWrap: 'wrap' }}>
        <span style={{ ...monoStyle, fontSize: 13, color: 'var(--fg-2)' }}>{versionFrom}</span>
        <span aria-hidden style={{ color: 'var(--fg-3)' }}>→</span>
        <span style={{ ...monoStyle, fontSize: 13, fontWeight: 700, color: 'var(--fg)' }}>{versionTo}</span>
        {majorRequired && (
          <span style={{
            fontSize: 10, fontWeight: 650, padding: '1px 7px', borderRadius: 'var(--r-full)',
            color: 'var(--status-warn)', border: '1px solid var(--status-warn)',
            background: 'color-mix(in srgb, var(--status-warn) 14%, transparent)', whiteSpace: 'nowrap',
          }}>
            {t.workbench.sheet.majorRequired}
          </span>
        )}
      </div>

      {/* YAML-Vorschau */}
      <pre style={{
        ...monoStyle, fontSize: 11, color: 'var(--fg-2)', background: 'var(--bg-2)',
        border: '1px solid var(--line)', borderRadius: 'var(--r-md)', padding: 'var(--s3)',
        margin: 0, overflow: 'auto', maxHeight: 260, whiteSpace: 'pre',
      }}>
        {yaml || '—'}
      </pre>

      {/* Freigabepfad */}
      <div>
        <div style={{ fontSize: 'var(--fs-eyebrow)', color: 'var(--fg-3)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 'var(--s3)' }}>
          {t.workbench.sheet.pathTitle}
        </div>
        <ol style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column' }}>
          {steps.map((s, i) => {
            const pin = PIN[s.status];
            const last = i === steps.length - 1;
            return (
              <li key={s.key} style={{ display: 'flex', gap: 'var(--s3)', minHeight: last ? undefined : 44 }}>
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
                  <span style={{
                    width: 20, height: 20, borderRadius: '50%', flexShrink: 0,
                    display: 'grid', placeItems: 'center', fontSize: 11, fontWeight: 700,
                    color: s.status === 'pending' ? 'var(--fg-3)' : '#0B0D12',
                    background: s.status === 'pending' ? 'transparent' : pin.color,
                    border: `2px solid ${pin.color}`,
                  }}>
                    {pin.glyph}
                  </span>
                  {!last && <span style={{ flex: 1, width: 2, background: 'var(--line)', marginTop: 2 }} />}
                </div>
                <div style={{ paddingBottom: last ? 0 : 'var(--s3)', minWidth: 0 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--s2)', flexWrap: 'wrap' }}>
                    <span style={{ fontSize: 13, fontWeight: 600, color: s.status === 'pending' ? 'var(--fg-3)' : 'var(--fg)' }}>{s.label}</span>
                    {s.badge && (
                      <span style={{ ...monoStyle, fontSize: 9, padding: '0 5px', borderRadius: 3, background: 'var(--bg-3)', border: '1px solid var(--line-2)', color: 'var(--fg-3)' }}>{s.badge}</span>
                    )}
                  </div>
                  {s.hint && <div style={{ fontSize: 11, color: 'var(--fg-3)', marginTop: 2, lineHeight: 'var(--lh-meta)' }}>{s.hint}</div>}
                </div>
              </li>
            );
          })}
        </ol>
      </div>

      {footer}
    </aside>
  );
}
