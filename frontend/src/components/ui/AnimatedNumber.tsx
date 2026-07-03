import { useEffect, useRef, useState } from 'react';

/**
 * Numeric value that rolls smoothly to its new value when it changes.
 * First render snaps (no 0→value count-up on every tab visit); subsequent
 * changes tween over `duration` ms with an ease-out cubic. Respects
 * prefers-reduced-motion.
 */
export function AnimatedNumber({
  value,
  format = (n: number) => n.toFixed(2),
  duration = 600,
}: {
  value: number;
  format?: (n: number) => string;
  duration?: number;
}) {
  const [display, setDisplay] = useState(value);
  const prev = useRef(value);
  const raf = useRef<number | null>(null);

  useEffect(() => {
    const from = prev.current;
    const to = value;
    prev.current = value;
    if (from === to || !Number.isFinite(from) || !Number.isFinite(to)) {
      setDisplay(to);
      return;
    }
    if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) {
      setDisplay(to);
      return;
    }
    const t0 = performance.now();
    const step = (t: number) => {
      const p = Math.min((t - t0) / duration, 1);
      const eased = 1 - Math.pow(1 - p, 3);
      setDisplay(from + (to - from) * eased);
      if (p < 1) raf.current = requestAnimationFrame(step);
    };
    raf.current = requestAnimationFrame(step);
    return () => {
      if (raf.current) cancelAnimationFrame(raf.current);
    };
  }, [value, duration]);

  return <>{format(display)}</>;
}
