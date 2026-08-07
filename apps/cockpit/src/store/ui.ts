import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export type Density = 'comfortable' | 'compact';

// Visual identity. Each theme is a pure token set driven by a data-theme
// attribute on <html> (applied in Shell):
//   classic   — the original blue-graphite cockpit
//   signal    — instrument-grade phosphor lime
//   blueprint — cyanotype / technical drawing (navy + cyan)
//   daylight  — Swiss-editorial light theme (paper + terracotta)
//   amber     — phosphor CRT terminal (monochrome amber + scanlines)
export type Theme = 'classic' | 'signal' | 'blueprint' | 'daylight' | 'amber';

// Display order — also the cycle order for toggleTheme.
export const THEMES: Theme[] = ['classic', 'signal', 'blueprint', 'daylight', 'amber'];

interface UIState {
  density: Density;
  setDensity: (d: Density) => void;
  toggleDensity: () => void;
  theme: Theme;
  setTheme: (t: Theme) => void;
  toggleTheme: () => void;
  // R6-5: Cmd-K recents (most-recent-first, capped).
  recents: string[];
  pushRecent: (path: string) => void;
}

export const useUIStore = create<UIState>()(
  persist(
    (set) => ({
      density: 'comfortable',
      setDensity: (density) => set({ density }),
      toggleDensity: () => set((s) => ({ density: s.density === 'compact' ? 'comfortable' : 'compact' })),
      theme: 'signal',
      setTheme: (theme) => set({ theme }),
      // Advance to the next theme in the cycle (used by the keyboard-less toggle).
      toggleTheme: () => set((s) => ({ theme: THEMES[(THEMES.indexOf(s.theme) + 1) % THEMES.length] })),
      recents: [],
      pushRecent: (path) =>
        set((s) => ({ recents: [path, ...s.recents.filter((p) => p !== path)].slice(0, 6) })),
    }),
    { name: 'signal-ui' },
  ),
);
