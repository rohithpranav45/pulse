import { useEffect, useRef, useState, useCallback } from 'react';

export function usePolling<T>(
  fn: () => Promise<T>,
  intervalMs: number,
  deps: any[] = [],
) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);
  const [lastUpdated, setLastUpdated] = useState<number | null>(null);
  const mounted = useRef(true);
  const tick = useRef<number | null>(null);
  const lastFetch = useRef<number>(0);

  const refetch = useCallback(async () => {
    lastFetch.current = Date.now();
    try {
      const result = await fn();
      if (!mounted.current) return;
      setData(result);
      setError(null);
      setLastUpdated(Date.now());
    } catch (e: any) {
      if (!mounted.current) return;
      setError(e);
    } finally {
      if (mounted.current) setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => {
    mounted.current = true;
    refetch();
    // Skip polls while the tab is hidden (saves backend load on a dashboard
    // that's often left open in a background tab)…
    tick.current = window.setInterval(() => {
      if (!document.hidden) refetch();
    }, intervalMs);
    // …and catch up immediately when the user comes back, if the data has
    // gone stale past its own polling cadence.
    const onVisible = () => {
      if (document.hidden) return;
      if (Date.now() - lastFetch.current >= intervalMs) refetch();
    };
    document.addEventListener('visibilitychange', onVisible);
    window.addEventListener('focus', onVisible);
    return () => {
      mounted.current = false;
      if (tick.current) window.clearInterval(tick.current);
      document.removeEventListener('visibilitychange', onVisible);
      window.removeEventListener('focus', onVisible);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refetch, intervalMs]);

  return { data, loading, error, lastUpdated, refetch };
}

export function useClock() {
  const [now, setNow] = useState(new Date());
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);
  return now;
}

export type Theme = 'dark' | 'light';

/** Theme toggle backed by localStorage. Applies `data-theme` (and the legacy
 *  `dark` class) to <html> so the CSS-variable palette in index.css flips the
 *  whole app. The initial paint is handled by the inline script in index.html
 *  (no flash of the wrong theme on load). */
export function useTheme(): [Theme, () => void] {
  const [theme, setTheme] = useLocalStorage<Theme>('pulse.theme', 'dark');
  useEffect(() => {
    const root = document.documentElement;
    root.setAttribute('data-theme', theme);
    root.classList.toggle('dark', theme === 'dark');
  }, [theme]);
  const toggle = useCallback(
    () => setTheme(theme === 'dark' ? 'light' : 'dark'),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [theme],
  );
  return [theme, toggle];
}

export function useLocalStorage<T>(key: string, initial: T): [T, (v: T) => void] {
  const [v, setV] = useState<T>(() => {
    try {
      const raw = localStorage.getItem(key);
      return raw ? (JSON.parse(raw) as T) : initial;
    } catch {
      return initial;
    }
  });
  // Keep every hook instance for the same key in sync (e.g. the theme is
  // toggled from both the TopBar button and the command palette).
  useEffect(() => {
    const onSync = (e: Event) => {
      const d = (e as CustomEvent).detail;
      if (d?.key === key) setV(d.value as T);
    };
    window.addEventListener('pulse-ls', onSync);
    return () => window.removeEventListener('pulse-ls', onSync);
  }, [key]);
  const set = (val: T) => {
    setV(val);
    try { localStorage.setItem(key, JSON.stringify(val)); } catch {}
    window.dispatchEvent(new CustomEvent('pulse-ls', { detail: { key, value: val } }));
  };
  return [v, set];
}
