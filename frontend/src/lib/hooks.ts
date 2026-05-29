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

  const refetch = useCallback(async () => {
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
    tick.current = window.setInterval(refetch, intervalMs);
    return () => {
      mounted.current = false;
      if (tick.current) window.clearInterval(tick.current);
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

export function useLocalStorage<T>(key: string, initial: T): [T, (v: T) => void] {
  const [v, setV] = useState<T>(() => {
    try {
      const raw = localStorage.getItem(key);
      return raw ? (JSON.parse(raw) as T) : initial;
    } catch {
      return initial;
    }
  });
  const set = (val: T) => {
    setV(val);
    try { localStorage.setItem(key, JSON.stringify(val)); } catch {}
  };
  return [v, set];
}
