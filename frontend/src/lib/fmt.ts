export const fmt = {
  price: (n: number | null | undefined, dp = 2): string => {
    if (n === null || n === undefined || Number.isNaN(n)) return '—';
    return n.toLocaleString(undefined, { minimumFractionDigits: dp, maximumFractionDigits: dp });
  },
  pct: (n: number | null | undefined, dp = 2): string => {
    if (n === null || n === undefined || Number.isNaN(n)) return '—';
    const s = n >= 0 ? '+' : '';
    return `${s}${n.toFixed(dp)}%`;
  },
  signed: (n: number | null | undefined, dp = 2): string => {
    if (n === null || n === undefined || Number.isNaN(n)) return '—';
    const s = n >= 0 ? '+' : '';
    return `${s}${n.toFixed(dp)}`;
  },
  int: (n: number | null | undefined): string => {
    if (n === null || n === undefined || Number.isNaN(n)) return '—';
    return Math.round(n).toLocaleString();
  },
  compact: (n: number | null | undefined): string => {
    if (n === null || n === undefined || Number.isNaN(n)) return '—';
    const abs = Math.abs(n);
    if (abs >= 1e9) return `${(n / 1e9).toFixed(1)}B`;
    if (abs >= 1e6) return `${(n / 1e6).toFixed(1)}M`;
    if (abs >= 1e3) return `${(n / 1e3).toFixed(1)}K`;
    return n.toFixed(0);
  },
  ago: (iso: string | number | null | undefined): string => {
    if (!iso) return '—';
    const t = typeof iso === 'number' ? iso : new Date(iso).getTime();
    if (Number.isNaN(t)) return '—';
    const s = Math.max(0, (Date.now() - t) / 1000);
    if (s < 60) return `${Math.round(s)}s ago`;
    if (s < 3600) return `${Math.round(s / 60)}m ago`;
    if (s < 86400) return `${Math.round(s / 3600)}h ago`;
    return `${Math.round(s / 86400)}d ago`;
  },
  time: (d: Date, tz?: string): string =>
    d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false, timeZone: tz }),
};

export function biasClass(n: number | null | undefined): 'bull' | 'bear' | 'neut' {
  if (n === null || n === undefined || Number.isNaN(n)) return 'neut';
  if (n > 0.05) return 'bull';
  if (n < -0.05) return 'bear';
  return 'neut';
}

export function signalLabel(score: number | null | undefined): string {
  // PULSE shows context, never recommends an action. Labels describe the
  // model's read of conditions, not what the trader should do.
  if (score === null || score === undefined) return '—';
  if (score >= 1.2)  return 'STRONGLY BULLISH';
  if (score >= 0.4)  return 'BULLISH';
  if (score <= -1.2) return 'STRONGLY BEARISH';
  if (score <= -0.4) return 'BEARISH';
  return 'NEUTRAL';
}
