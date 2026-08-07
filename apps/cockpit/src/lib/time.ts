// Shared time formatting (UX-F7): one relative-time source so tables, drawers
// and timelines speak the same language instead of each re-deriving it.

/** "vor 3 Std." style relative time, German. Empty/invalid input → "—". */
export function relativeTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  const ts = new Date(iso).getTime();
  if (Number.isNaN(ts)) return '—';
  const min = Math.round((Date.now() - ts) / 60_000);
  if (min < 1) return 'gerade eben';
  if (min < 60) return `vor ${min} Min.`;
  const h = Math.round(min / 60);
  if (h < 24) return `vor ${h} Std.`;
  return `vor ${Math.round(h / 24)} Tagen`;
}

/** Full localized timestamp for tooltips. Empty/invalid input → "—". */
export function absoluteTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleString();
}
