/**
 * Pure Helfer für den Schaltplan-Renderer: Farb-Mapping (DQ/Lane) auf
 * Theme-Vars und Polyline → SVG-Pfad mit gerundeten Ecken. Bewusst ohne
 * React/DOM, damit unit-testbar.
 */

/** DQ-Status (pass|warn|fail|critical|…) → Theme-Statusfarbe als CSS-Var. */
export function dqStatusColor(status: string | undefined): string {
  switch ((status || '').toLowerCase()) {
    case 'pass':
    case 'ok':
      return 'var(--status-ok)';
    case 'warn':
    case 'warning':
      return 'var(--status-warn)';
    case 'fail':
    case 'failing':
    case 'error':
      return 'var(--status-fail)';
    case 'critical':
    case 'crit':
      return 'var(--status-crit)';
    default:
      return 'var(--status-unknown)';
  }
}

// Theme-Akzente im Wechsel fürs Layer-Strip — stabil über laneOrder, damit
// dasselbe Layer immer dieselbe Farbe bekommt.
const LANE_ACCENTS = ['var(--obs)', 'var(--qual)', 'var(--cont)', 'var(--status-ok)', 'var(--status-warn)'];

export function laneColor(laneOrder: number): string {
  const i = Number.isFinite(laneOrder) ? Math.abs(Math.trunc(laneOrder)) : 0;
  return LANE_ACCENTS[i % LANE_ACCENTS.length];
}

export interface Point {
  x: number;
  y: number;
}

/**
 * Orthogonale Polyline → SVG-Pfad. Rundet Ecken mit kleinen Quadrant-Arcs
 * (radius), damit die Traces wie saubere Leiterbahnen wirken statt harter
 * 90°-Knicke. Fällt bei <2 Punkten / kollinearen Segmenten auf gerade
 * Linien zurück.
 */
export function orthogonalPath(points: Point[], radius = 6): string {
  if (!points.length) return '';
  if (points.length === 1) return `M ${points[0].x} ${points[0].y}`;
  if (points.length === 2) {
    return `M ${points[0].x} ${points[0].y} L ${points[1].x} ${points[1].y}`;
  }

  let d = `M ${points[0].x} ${points[0].y}`;
  for (let i = 1; i < points.length - 1; i++) {
    const prev = points[i - 1];
    const curr = points[i];
    const next = points[i + 1];
    const r = Math.min(
      radius,
      dist(prev, curr) / 2,
      dist(curr, next) / 2,
    );
    if (r < 0.5) {
      d += ` L ${curr.x} ${curr.y}`;
      continue;
    }
    const entry = towards(curr, prev, r);
    const exit = towards(curr, next, r);
    d += ` L ${entry.x} ${entry.y} Q ${curr.x} ${curr.y} ${exit.x} ${exit.y}`;
  }
  const last = points[points.length - 1];
  d += ` L ${last.x} ${last.y}`;
  return d;
}

function dist(a: Point, b: Point): number {
  return Math.hypot(b.x - a.x, b.y - a.y);
}

// Punkt, der `r` von `from` Richtung `to` liegt.
function towards(from: Point, to: Point, r: number): Point {
  const d = dist(from, to) || 1;
  return { x: from.x + ((to.x - from.x) / d) * r, y: from.y + ((to.y - from.y) / d) * r };
}
