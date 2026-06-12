import type {
  PricesData,
  SignalData,
  TradeIdeaData,
  FundamentalsData,
  NewsData,
  PaperPosition,
  PaperPerformanceData,
  HealthDetailData,
  ABReportData,
} from './api-types';

// Re-export the generated types so views can import them from a single place.
export type {
  PricesData,
  PriceQuote,
  SignalData,
  AssetSignal,
  SignalIndicator,
  TradeIdeaData,
  FundamentalsData,
  CotSection,
  CotEntry,
  RigCount,
  NewsData,
  NewsArticle,
  PaperPosition,
  PaperPerformanceData,
  PaperTradeRef,
  EquityPoint,
  HealthDetailData,
  HealthStream,
  HealthCounts,
  ABReportData,
  ABArmMetrics,
  ABArms,
  ABDiff,
  ABWelch,
  ABPaired,
  ABStopCriteria,
  ABArmEquityPoint,
} from './api-types';

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

async function postJSON<T = any>(path: string, body: any = {}, timeoutMs = 30000): Promise<T> {
  const ctrl = new AbortController();
  const id = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const res = await fetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body ?? {}),
      signal: ctrl.signal,
    });
    const j = await res.json().catch(() => ({}));
    if (!res.ok) {
      const err = (j && (j.error || (j.data && j.data.error))) || `HTTP ${res.status}`;
      throw new Error(String(err));
    }
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
    prices:          unwrap(raw.prices),
    curve:           unwrap(raw.curve),
    fair_value:      raw.fair_value, // {brent, wti} — no data wrapper
    signal:          unwrap(raw.signal),
    correlations:    unwrap(raw.correlations),
    fundamentals:    unwrap(raw.fundamentals),
    news:            unwrap(raw.news),
    weather:         unwrap(raw.weather),
    technicals:      unwrap(raw.technicals),
    term_structure:  unwrap(raw.term_structure),
    macro:           unwrap(raw.macro),
    patterns:        unwrap(raw.patterns),
    iv:              unwrap(raw.iv),
    cracks:          unwrap(raw.cracks),
    steo:            unwrap(raw.steo),
    analyst_watch:   unwrap(raw.analyst_watch),
    tanker_watch:    unwrap(raw.tanker_watch),
    spreads_history: unwrap(raw.spreads_history),
    seasonality:     unwrap(raw.seasonality),
    eia_surprise:    unwrap(raw.eia_surprise),
    forward_cover:   unwrap(raw.forward_cover),
    // Phase A additions
    ovx:             unwrap(raw.ovx),
    curve_regime:    unwrap(raw.curve_regime),
    order_flow:      unwrap(raw.order_flow),
    jodi:            unwrap(raw.jodi),
    gdelt_tone:      unwrap(raw.gdelt_tone),
    // Phase B additions
    marketaux:       unwrap(raw.marketaux),
    analogs:         unwrap(raw.analogs),
    timestamp:       raw.timestamp,
  };
}

export const api = {
  health:        () => getJSON('/api/health'),
  healthDetail:  () => getJSON<HealthDetailData>('/api/health-detail'),
  prices:        () => getJSON<PricesData>('/api/prices'),
  ohlcv:         () => getJSON('/api/ohlcv'),
  history:       () => getJSON('/api/history'),
  curve:         () => getJSON('/api/curve'),
  fairValue:     () => getJSON('/api/fair-value'),
  signal:        () => getJSON<SignalData>('/api/signal'),
  correlations:  () => getJSON('/api/correlations'),
  fundamentals:  () => getJSON<FundamentalsData>('/api/fundamentals'),
  news:          () => getJSON<NewsData>('/api/news'),
  weather:       () => getJSON('/api/weather'),
  technicals:    () => getJSON('/api/technicals'),
  termStructure: () => getJSON('/api/term-structure'),
  macro:         () => getJSON('/api/macro'),
  patterns:      () => getJSON('/api/patterns'),
  tradeIdea:     () => getJSON<TradeIdeaData>('/api/trade-idea'),
  alerts:        () => getJSON('/api/alerts'),
  cracks:        () => getJSON('/api/cracks'),
  steo:          () => getJSON('/api/steo'),
  analystWatch:  () => getJSON('/api/analyst-watch'),
  tankerWatch:   () => getJSON('/api/tanker-watch'),
  spreadsHistory:() => getJSON('/api/spreads-history'),
  seasonality:   () => getJSON('/api/seasonality'),
  eiaSurprise:   () => getJSON('/api/eia-surprise'),
  forwardCover:  () => getJSON('/api/forward-cover'),
  ovx:           () => getJSON('/api/ovx'),
  curveRegime:   () => getJSON('/api/curve-regime'),
  orderFlow:     () => getJSON('/api/order-flow'),
  jodi:          () => getJSON('/api/jodi'),
  gdeltTone:     () => getJSON('/api/gdelt-tone'),
  marketaux:     () => getJSON('/api/marketaux'),
  analogs:       () => getJSON('/api/analogs'),
  // Phase 2 — regime engine
  regime:                 () => getJSON('/api/regime'),
  regimeRecommendation:   () => getJSON('/api/regime/recommendation'),
  regimeBacktest:         () => getJSON('/api/regime/backtest'),
  regimeDrill:            (spread: string) => getJSON(`/api/regime/drill/${spread}`),
  regimeAB:               () => getJSON<ABReportData>('/api/regime/ab'),
  regimeABTick:           (body: any = {}) => postJSON('/api/regime/ab/tick', body),
  regimeABReset:          (scope: 'all' | 'closed' = 'all') => postJSON('/api/regime/ab/reset', { scope }),
  // Paper trading
  paperPositions:  () => getJSON<PaperPosition[]>('/api/paper/positions'),
  paperPerformance:() => getJSON<PaperPerformanceData>('/api/paper/performance'),
  paperPush:       (body: any = {}) => postJSON('/api/paper/push', body),
  paperClose:      (id: number, body: any = {}) => postJSON(`/api/paper/close/${id}`, body),
  paperClear:      (scope: 'all' | 'closed' = 'closed') => postJSON('/api/paper/clear', { scope }),
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
