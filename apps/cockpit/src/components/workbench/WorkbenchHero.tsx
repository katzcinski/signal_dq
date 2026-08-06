// Hero-Karte der Contract-Workbench (Objekte-Detail-Muster): Titel, Kind-/
// Versions-Badges, Meta-Zeile und Fakten-Zeile links; Ungespeichert-Indikator
// und Aktionen rechts. Rein präsentational — die Wiring-Logik lebt im EditorPane.
import type { ReactNode } from 'react';
import { t } from '@/i18n/de';

export interface HeroChip { label: string; tone: string; subtle?: boolean }
export interface HeroFact { label: string; value: ReactNode; tone?: string }

function Chip({ label, tone, subtle }: HeroChip) {
  return (
    <span style={{
      fontSize: 11, fontWeight: 650, padding: '2px 9px', borderRadius: 'var(--r-full)',
      whiteSpace: 'nowrap', color: tone,
      background: subtle ? 'transparent' : `color-mix(in srgb, ${tone} 15%, transparent)`,
      border: `1px solid ${subtle ? `color-mix(in srgb, ${tone} 55%, var(--line))` : 'transparent'}`,
    }}>
      {label}
    </span>
  );
}

export function WorkbenchHero({ title, chips, meta, facts, unsaved, actions }: {
  title: string;
  chips: HeroChip[];
  meta: string[];
  facts: HeroFact[];
  unsaved: boolean;
  actions: ReactNode;
}) {
  return (
    <div className="object-detail-hero" style={{
      background: 'var(--bg-1)', border: '1px solid var(--line)', borderRadius: 'var(--r-lg)',
      padding: 'var(--s5)', boxShadow: 'var(--shadow-1)',
    }}>
      <div className="object-detail-hero-head" style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 'var(--s4)', flexWrap: 'wrap' }}>
        <div style={{ minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--s3)', flexWrap: 'wrap' }}>
            <h1 style={{ fontSize: 'var(--fs-h1)', fontWeight: 700, lineHeight: 'var(--lh-tight)', margin: 0, fontFamily: 'var(--font-mono)' }}>{title}</h1>
            {chips.map((c, i) => <Chip key={i} {...c} />)}
          </div>
          {meta.length > 0 && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--s2)', flexWrap: 'wrap', marginTop: 'var(--s2)', color: 'var(--fg-3)', fontSize: 'var(--fs-meta)' }}>
              {meta.map((m, i) => (
                <span key={i} style={{ display: 'inline-flex', alignItems: 'center', gap: 'var(--s2)' }}>
                  {i > 0 && <span aria-hidden style={{ color: 'var(--line-2)' }}>·</span>}
                  {m}
                </span>
              ))}
            </div>
          )}
        </div>
        <div className="object-detail-actions" style={{ display: 'flex', alignItems: 'center', gap: 'var(--s3)', flexWrap: 'wrap' }}>
          {unsaved && (
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 'var(--s2)', fontSize: 12, color: 'var(--status-warn)', whiteSpace: 'nowrap' }}>
              <span style={{ width: 7, height: 7, borderRadius: '50%', background: 'var(--status-warn)' }} />
              {t.workbench.hero.unsaved}
            </span>
          )}
          {actions}
        </div>
      </div>

      {facts.length > 0 && (
        <div style={{
          display: 'flex', gap: 'var(--s5)', flexWrap: 'wrap', marginTop: 'var(--s4)',
          paddingTop: 'var(--s4)', borderTop: '1px solid var(--line)',
        }}>
          {facts.map((f, i) => (
            <div key={i} style={{ minWidth: 0 }}>
              <div style={{ fontSize: 'var(--fs-eyebrow)', color: 'var(--fg-3)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4 }}>{f.label}</div>
              <div style={{ fontSize: 14, fontWeight: 650, color: f.tone ?? 'var(--fg)' }}>{f.value}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
