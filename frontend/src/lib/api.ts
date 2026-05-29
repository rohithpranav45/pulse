// Thin fetch wrapper that unwraps the Flask `{data, timestamp}` envelope.
async function getJSON<T = any>(path: string, timeoutMs = 90000): Promise<T> {
  const ctrl = new AbortController();
  const id = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const res = await fetch(path, { signal: ctrl.signal });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const j = await res.json();
    return (j && typeof j === 'object' && 'data' in j ? j.data : j) as T;
  } finally {
    clearTimeout(id);
  }
}

/**
 * Normalize the `/api/all` response so every view sees a flat structure.
 * Server wraps each section as `{data: ...}` (and fair_value as `{brent, wti}`),
 * which produces deeply nested access paths.
 */
function normalizeAll(raw: any): any {
  if (!raw) return null;
  const unwrap = (v: any) => (v && typeof v === 'object' && 'data' in v ? v.data : v);
  return {
    prices:        unwrap(raw.prices),
    curve:         unwrap(raw.curve),
    fair_value:    raw.fair_value, // {brent, wti} — no data wrapper
    signal:        unwrap(raw.signal),
    correlations:  unwrap(raw.correlations),
    fundamentals:  unwrap(raw.fundamentals),
    news:          unwrap(raw.news),
    weather:       unwrap(raw.weather),
    technicals:    unwrap(raw.technicals),
    term_structure:unwrap(raw.term_structure),
    macro:         unwrap(raw.macro),
    patterns:      unwrap(raw.patterns),
    iv:            unwrap(raw.iv),
    cracks:        unwrap(raw.cracks),
    steo:          unwrap(raw.steo),
    analyst_watch: unwrap(raw.analyst_watch),
    tanker_watch:  unwrap(raw.tanker_watch),
    timestamp:     raw.timestamp,
  };
}

export const api = {
  health:        () => getJSON('/api/health'),
  prices:        () => getJSON('/api/prices'),
  ohlcv:         () => getJSON('/api/ohlcv'),
  history:       () => getJSON('/api/history'),
  curve:         () => getJSON('/api/curve'),
  fairValue:     () => getJSON('/api/fair-value'),
  signal:        () => getJSON('/api/signal'),
  correlations:  () => getJSON('/api/correlations'),
  fundamentals:  () => getJSON('/api/fundamentals'),
  news:          () => getJSON('/api/news'),
  weather:       () => getJSON('/api/weather'),
  technicals:    () => getJSON('/api/technicals'),
  termStructure: () => getJSON('/api/term-structure'),
  macro:         () => getJSON('/api/macro'),
  patterns:      () => getJSON('/api/patterns'),
  tradeIdea:     () => getJSON('/api/trade-idea'),
  alerts:        () => getJSON('/api/alerts'),
  cracks:        () => getJSON('/api/cracks'),
  steo:          () => getJSON('/api/steo'),
  analystWatch:  () => getJSON('/api/analyst-watch'),
  tankerWatch:   () => getJSON('/api/tanker-watch'),
  all:           async () => normalizeAll(await getJSON('/api/all', 120000)),
};

// Canonical asset keys served by the backend (camelCase API: lowercase names)
export const ASSET = {
  brent: 'brent',
  wti: 'wti',
  natgas: 'henry_hub',
} as const;

// Display ticker-tape keys (note legacy uses 'brent', 'wti', etc.)
export const TICKER_KEYS = [
  { key: 'brent',       label: 'BRENT' },
  { key: 'wti',         label: 'WTI' },
  { key: 'henry_hub',   label: 'NAT GAS' },
  { key: 'dxy',         label: 'DXY' },
  { key: 'vix',         label: 'VIX' },
  { key: 'sp500',       label: 'S&P' },
  { key: 'treasury_10y',label: '10Y' },
];

export type Json = Record<string, any>;
