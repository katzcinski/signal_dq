import { useSearchParams } from 'react-router-dom';
import { useLibrary } from '@/api/library';
import { t } from '@/i18n/de';
import { FilterChip } from '@/components/ui/FilterChip';
import { Button } from '@/components/ui/Button';
import { Skeleton } from '@/components/ui/Skeleton';
import { PageHeader } from '@/components/ui/PageHeader';
import { useSearchParamState } from '@/hooks/useSearchParamState';
import type { CheckDef, CheckFamily } from '@/types';

function isCheckFamily(value: string): value is CheckFamily {
  return value === 'observability' || value === 'quality';
}

// R6-3: layout-treue Karten-Skeletons statt „Lädt…"-Text — dieselbe Rasterzelle
// wie die echten Check-Karten, damit Laden als „Inhalt kommt hierher" liest.
function LibrarySkeleton() {
  return (
    <div
      aria-hidden
      style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(min(100%, 320px), 1fr))', gap: 'var(--s3)' }}
    >
      {Array.from({ length: 6 }).map((_, i) => (
        <div key={i} style={{
          background: 'var(--bg-1)', border: '1px solid var(--line)', borderRadius: 'var(--r-lg)',
          padding: 14, display: 'flex', flexDirection: 'column', gap: 'var(--s2)',
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 'var(--s2)' }}>
            <Skeleton width={150} height={13} />
            <Skeleton width={64} height={16} radius={6} />
          </div>
          <Skeleton width="80%" height={11} />
          <Skeleton width={110} height={10} />
          <Skeleton width="100%" height={48} radius={6} style={{ marginTop: 4 }} />
        </div>
      ))}
    </div>
  );
}

function CheckCard({ check }: { check: CheckDef }) {
  return (
    <article style={{
      background: 'var(--bg-1)', border: '1px solid var(--line)', borderRadius: 'var(--r-lg)',
      padding: 14, display: 'flex', flexDirection: 'column', gap: 'var(--s2)', minWidth: 0,
      contentVisibility: 'auto', containIntrinsicSize: '280px',
    }}>
      <header style={{ display: 'flex', alignItems: 'flex-start', gap: 'var(--s2)' }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <h2 style={{
            fontFamily: 'var(--font-mono)', fontSize: 13, fontWeight: 600,
            overflowWrap: 'anywhere', textWrap: 'pretty',
          }}>
            {check.label}
          </h2>
          {check.short && (
            <div style={{ fontSize: 12, color: 'var(--fg-2)', marginTop: 4, lineHeight: 1.4 }}>{check.short}</div>
          )}
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 'var(--s1)', flexShrink: 0 }}>
          <span style={{
            fontSize: 10, padding: '2px 6px', borderRadius: 'var(--r)',
            background: 'var(--bg-2)', color: 'var(--fg-3)', border: '1px solid var(--line-2)',
          }}>{check.category}</span>
        </div>
      </header>
      <div style={{ fontSize: 10, color: 'var(--fg-3)' }}>
        {t.library.gating.label}: <span style={{ color: 'var(--fg-2)' }}>{t.library.gating[check.gating]}</span>
      </div>
      {check.help && (
        <div style={{ fontSize: 12, color: 'var(--fg-3)', lineHeight: 1.45 }}>{check.help}</div>
      )}
      {check.sql_template && (
        <div>
          <div style={{ fontSize: 10, color: 'var(--fg-3)', marginBottom: 4 }}>{t.library.templateSql}</div>
          <pre style={{
            background: 'var(--bg-2)', border: '1px solid var(--line-2)', borderRadius: 'var(--r)',
            padding: '6px 8px', fontSize: 11, overflowX: 'auto', margin: 0, color: 'var(--fg-2)',
            whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', maxWidth: '100%',
          }}>{check.sql_template}</pre>
        </div>
      )}
      {check.params.length > 0 && (
        <div>
          <div style={{ fontSize: 10, color: 'var(--fg-3)', marginBottom: 4 }}>{t.library.params}</div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--s1)' }}>
            {check.params.map(param => (
              <span key={param.token} title={param.hint} style={{
                fontSize: 11, fontFamily: 'var(--font-mono)',
                background: 'var(--bg-2)', padding: '2px 6px', borderRadius: 3,
                color: 'var(--fg-2)', border: '1px solid var(--line-2)', maxWidth: '100%',
                overflowWrap: 'anywhere',
              }}>{param.token}: {param.label}</span>
            ))}
          </div>
        </div>
      )}
    </article>
  );
}

export default function CheckLibrary() {
  const { data: library, isLoading } = useLibrary();
  const [, setSearchParams] = useSearchParams();
  const [search, setSearch] = useSearchParamState('q');
  const [category, setCategory] = useSearchParamState('category');
  const [family, setFamily] = useSearchParamState('family');

  const activeFamily = isCheckFamily(family) ? family : '';
  const hasFilters = search !== '' || category !== '' || activeFamily !== '';
  const q = search.toLowerCase();
  const checks = (library?.checks ?? []).filter(c => {
    if (category && c.category !== category) return false;
    if (activeFamily && c.family !== activeFamily) return false;
    const haystack = [c.id, c.label, c.short, c.help, c.example].join(' ').toLowerCase();
    if (q && !haystack.includes(q)) return false;
    return true;
  });
  const resultLabel = checks.length === 1
    ? t.library.resultsOne.replace('{count}', String(checks.length))
    : t.library.resultsMany.replace('{count}', String(checks.length));

  return (
    <section className="page-full" aria-labelledby="check-library-title">
      <PageHeader titleId="check-library-title" title={t.library.title} />

      <div style={{
        display: 'grid',
        gap: 'var(--s4)',
        marginBottom: 16,
        padding: 'var(--s4)',
        background: 'var(--bg-1)',
        border: '1px solid var(--line)',
        borderRadius: 'var(--r-lg)',
      }}>
        <div style={{ display: 'grid', gap: 'var(--s2)' }}>
          <label className="mono-label" htmlFor="library-search">
            {t.library.searchLabel}
          </label>
          <input
            id="library-search"
            name="check-search"
            type="search"
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder={t.library.searchPlaceholder}
            autoComplete="off"
            spellCheck={false}
            style={{
              background: 'var(--bg-2)', border: '1px solid var(--line-2)',
              color: 'var(--fg)', borderRadius: 'var(--r-md)', padding: '8px 10px', fontSize: 12,
              minWidth: 220, maxWidth: 420,
            }}
          />
        </div>

        <fieldset style={{ border: 'none', display: 'grid', gap: 'var(--s2)', minWidth: 0 }}>
          <legend className="mono-label" style={{ marginBottom: 'var(--s1)' }}>
            {t.library.categoryLabel}
          </legend>
          <div style={{ display: 'flex', gap: 'var(--s2)', flexWrap: 'wrap', alignItems: 'center' }}>
            <FilterChip active={category === ''} onClick={() => setCategory('')}>
              {t.library.allCategories}
            </FilterChip>
            {(library?.categories ?? []).map(cat => (
              <FilterChip
                key={cat}
                active={category === cat}
                onClick={() => setCategory(category === cat ? '' : cat)}
              >
                {cat}
              </FilterChip>
            ))}
          </div>
        </fieldset>

        <fieldset style={{ border: 'none', display: 'grid', gap: 'var(--s2)', minWidth: 0 }}>
          <legend className="mono-label" style={{ marginBottom: 'var(--s1)' }}>
            {t.library.familyLabel}
          </legend>
          <div style={{ display: 'flex', gap: 'var(--s2)', flexWrap: 'wrap', alignItems: 'center' }}>
            <FilterChip active={activeFamily === ''} onClick={() => setFamily('')}>
              {t.library.allFamilies}
            </FilterChip>
            {(library?.families ?? []).map(fam => (
              <FilterChip
                key={fam}
                active={activeFamily === fam}
                onClick={() => setFamily(activeFamily === fam ? '' : fam)}
              >
                {t.library.family[fam]}
              </FilterChip>
            ))}
          </div>
        </fieldset>

        <div style={{ display: 'flex', gap: 'var(--s3)', flexWrap: 'wrap', alignItems: 'center' }}>
          <div aria-live="polite" style={{ fontSize: 12, color: 'var(--fg-2)' }}>
            {resultLabel}
          </div>
          {hasFilters && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                setSearchParams(prev => {
                  const params = new URLSearchParams(prev);
                  params.delete('q');
                  params.delete('category');
                  params.delete('family');
                  return params;
                }, { replace: true });
              }}
            >
              {t.library.clearFilters}
            </Button>
          )}
        </div>
      </div>

      {isLoading && <LibrarySkeleton />}

      {!isLoading && checks.length === 0 && (
        <div style={{ color: 'var(--fg-3)', fontSize: 14 }}>{t.library.noResults}</div>
      )}

      {!isLoading && (
        <div
          aria-live="polite"
          style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(min(100%, 320px), 1fr))', gap: 'var(--s3)' }}
        >
          {checks.map(c => <CheckCard key={c.id} check={c} />)}
        </div>
      )}
    </section>
  );
}
