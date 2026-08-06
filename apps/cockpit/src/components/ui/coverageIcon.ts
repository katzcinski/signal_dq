import { createElement } from 'react';

// Modern, consistent coverage-status icons (R6-8 / Carbon redundancy).
// One SVG vocabulary shared by the lineage canvas nodes, the legend and the
// side panel, so the same mark means the same thing everywhere. Emitted as a
// data-URI (CSP img-src 'self' data:) so it can be both an <img> in React and
// a Cytoscape `background-image` — the canvas renderer can't draw React.
//
// Flags follow the WS4 vocabulary: ● covered · ◐ partial · ▲ gap · ○ out-of-scope.

let _tokens: Record<string, string> | null = null;
function tokens(): Record<string, string> {
  if (_tokens) return _tokens;
  const read = (name: string, fallback: string): string => {
    if (typeof document === 'undefined') return fallback;
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
  };
  _tokens = {
    '●': read('--status-ok', '#3FB07A'),
    '◐': read('--status-warn', '#E0B23E'),
    '▲': read('--status-fail', '#E2783C'),
    '○': read('--fg-3', '#5E6877'),
    cut: read('--bg-0', '#0B0D11'),
  };
  return _tokens;
}

export function coverageColor(flag: string): string {
  const tk = tokens();
  return tk[flag] ?? tk['○'];
}

// Distinct shape per flag (shape redundancy) with a status colour and a dark
// cut-out mark, so each icon reads at 14–18px on a dark node.
function svgMarkup(flag: string, color: string, cut: string): string {
  let inner: string;
  switch (flag) {
    case '●': // covered: filled rounded square + check
      inner = `<rect x="2" y="2" width="20" height="20" rx="5" fill="${color}"/>`
        + `<path d="M7 12.3l3.2 3.2L17 8.5" fill="none" stroke="${cut}" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>`;
      break;
    case '◐': // partial: ring with one half filled
      inner = `<circle cx="12" cy="12" r="9" fill="none" stroke="${color}" stroke-width="2.4"/>`
        + `<path d="M12 3a9 9 0 0 1 0 18Z" fill="${color}"/>`;
      break;
    case '▲': // gap: filled diamond + exclamation
      inner = `<path d="M12 1.5L22.5 12 12 22.5 1.5 12Z" fill="${color}"/>`
        + `<rect x="10.8" y="6.5" width="2.4" height="7.5" rx="1.2" fill="${cut}"/>`
        + `<circle cx="12" cy="17" r="1.5" fill="${cut}"/>`;
      break;
    default: // out-of-scope: dashed outline ring
      inner = `<circle cx="12" cy="12" r="9" fill="none" stroke="${color}" stroke-width="2" stroke-dasharray="3.2 3.2"/>`;
  }
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24">${inner}</svg>`;
}

export function coverageIconDataUri(flag: string, color?: string): string {
  const tk = tokens();
  return `data:image/svg+xml,${encodeURIComponent(svgMarkup(flag, color ?? coverageColor(flag), tk.cut))}`;
}

export function CoverageIcon({ flag, size = 16, label }: { flag: string; size?: number; label?: string }) {
  return createElement('img', {
    src: coverageIconDataUri(flag),
    width: size,
    height: size,
    alt: label ?? '',
    style: { display: 'block' },
  });
}
