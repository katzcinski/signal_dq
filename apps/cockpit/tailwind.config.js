/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      fontFamily: {
        sans: ['Space Grotesk', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
      // R6-9: single source of truth — the CSS custom properties in index.css.
      // No divergent hex palette here; Tailwind colour utilities resolve to the
      // same vars the inline styles use.
      colors: {
        obs: 'var(--obs)',          // Observability
        quality: 'var(--qual)',     // Quality
        contract: 'var(--cont)',    // Contract
        'status-ok': 'var(--status-ok)',
        'status-warn': 'var(--status-warn)',
        'status-fail': 'var(--status-fail)',
        'status-crit': 'var(--status-crit)',
        line: 'var(--line)',
        'line-2': 'var(--line-2)',
        fg: 'var(--fg)',
        'fg-2': 'var(--fg-2)',
        'fg-3': 'var(--fg-3)',
        bg: 'var(--bg-1)',
      },
    },
  },
  plugins: [],
}
