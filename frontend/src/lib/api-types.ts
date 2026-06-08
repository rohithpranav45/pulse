/**
 * AUTO-GENERATED — do not edit by hand.
 * Source: backend/schemas/__init__.py
 * Regenerate: `python scripts/generate_ts_types.py`
 *
 * These types describe PULSE backend responses. Models use Pydantic
 * `extra="allow"`, so every interface ends with an index signature
 * permitting unknown fields — undocumented payload extensions stay
 * accessible without breaking the type check.
 */

// ── Nested models ──────────────────────────────────────
export interface AssetSignal {
  asset: string;
  direction?: number | null;
  score?: number | null;
  signal?: string | null;
  conviction?: string | null;
  bullish_factors?: Array<string>;
  bearish_factors?: Array<string>;
  key_risk?: string | null;
  history?: Array<number>;
  indicators?: Array<SignalIndicator>;
  timestamp?: string | null;
  [key: string]: unknown;
}

export interface CotEntry {
  date?: string | null;
  label?: string | null;
  net?: number | null;
  percentile?: number | null;
  signal?: number | null;
  [key: string]: unknown;
}

export interface CotSection {
  crude_oil?: CotEntry | null;
  gasoline?: CotEntry | null;
  heating_oil?: CotEntry | null;
  natural_gas?: CotEntry | null;
  [key: string]: unknown;
}

export interface EquityPoint {
  closed_at?: string | null;
  cum_pnl?: number | null;
  trade_id?: number | null;
  [key: string]: unknown;
}

export interface FundamentalsData {
  inventory?: Record<string, unknown> | null;
  snapshot?: Record<string, unknown> | null;
  cot?: CotSection | null;
  opec?: Record<string, unknown> | null;
  opec_jodi?: Record<string, unknown> | null;
  opec_eia?: Record<string, unknown> | null;
  geo_risk?: Record<string, unknown> | null;
  rig_count?: RigCount | null;
  seasonality?: Record<string, unknown> | null;
  spark_dark?: Record<string, unknown> | null;
  curve_regime?: Record<string, unknown> | null;
  order_flow?: Record<string, unknown> | null;
  stale?: boolean | null;
  [key: string]: unknown;
}

export interface HealthCounts {
  up?: number;
  stale?: number;
  down?: number;
  [key: string]: unknown;
}

export interface HealthDetailData {
  overall: string;
  counts: HealthCounts;
  total?: number | null;
  streams?: Array<HealthStream>;
  [key: string]: unknown;
}

export interface HealthStream {
  key: string;
  label: string;
  status: string;
  detail?: string | null;
  age_s?: number | null;
  ttl_s?: number | null;
  [key: string]: unknown;
}

export interface NewsArticle {
  title?: string | null;
  headline?: string | null;
  url?: string | null;
  source?: string | null;
  feed?: string | null;
  category?: string | null;
  published?: string | null;
  published_at?: string | null;
  time?: string | null;
  sentiment?: number | null;
  is_negative?: boolean | null;
  [key: string]: unknown;
}

export interface NewsData {
  articles?: Array<NewsArticle>;
  negative_count?: number | null;
  stale?: boolean | null;
  [key: string]: unknown;
}

export interface PaperPerformanceData {
  total_trades?: number | null;
  wins?: number | null;
  losses?: number | null;
  win_rate_pct?: number | null;
  total_pnl?: number | null;
  avg_pnl_per_trade?: number | null;
  avg_win?: number | null;
  avg_loss?: number | null;
  profit_factor?: number | null;
  sharpe_annualised?: number | null;
  max_drawdown?: number | null;
  best_trade?: PaperTradeRef | null;
  worst_trade?: PaperTradeRef | null;
  equity_curve?: Array<EquityPoint>;
  timestamp?: string | null;
  [key: string]: unknown;
}

export interface PaperPosition {
  id: number;
  asset?: string | null;
  direction?: string | null;
  status?: string | null;
  source?: string | null;
  conviction?: string | null;
  size?: number | null;
  entry_price?: number | null;
  target_price?: number | null;
  stop_price?: number | null;
  exit_price?: number | null;
  mtm_price?: number | null;
  mtm_at?: string | null;
  opened_at?: string | null;
  closed_at?: string | null;
  close_reason?: string | null;
  realised?: number | null;
  realised_pct?: number | null;
  unrealised?: number | null;
  thesis?: string | null;
  metadata?: Record<string, unknown> | null;
  [key: string]: unknown;
}

export interface PaperTradeRef {
  id?: number | null;
  asset?: string | null;
  pnl?: number | null;
  [key: string]: unknown;
}

export interface PriceQuote {
  price?: number | null;
  change_abs?: number | null;
  change_pct?: number | null;
  high?: number | null;
  low?: number | null;
  stale?: boolean | null;
  timestamp?: string | null;
  [key: string]: unknown;
}

export interface PricesData {
  brent?: PriceQuote | null;
  wti?: PriceQuote | null;
  henry_hub?: PriceQuote | null;
  gasoline?: PriceQuote | null;
  heating_oil?: PriceQuote | null;
  dxy?: PriceQuote | null;
  sp500?: PriceQuote | null;
  vix?: PriceQuote | null;
  treasury_10y?: PriceQuote | null;
  gold?: PriceQuote | null;
  stale?: boolean | null;
  [key: string]: unknown;
}

export interface RigCount {
  current?: number | null;
  previous?: number | null;
  change?: number | null;
  date?: string | null;
  source?: string | null;
  note?: string | null;
  stale?: boolean | null;
  timestamp?: string | null;
  [key: string]: unknown;
}

export interface SignalData {
  brent?: AssetSignal | null;
  wti?: AssetSignal | null;
  henry_hub?: AssetSignal | null;
  [key: string]: unknown;
}

export interface SignalIndicator {
  name: string;
  raw_value?: unknown;
  reason?: string | null;
  score?: number | null;
  weight?: number | null;
  [key: string]: unknown;
}

export interface TradeIdeaData {
  direction?: string | null;
  signal?: string | null;
  conviction?: string | null;
  score?: number | null;
  live_price?: number | null;
  fair_value?: number | null;
  target_level?: number | null;
  stop_level?: number | null;
  time_horizon?: string | null;
  entry_thesis?: Array<string>;
  key_risk?: string | null;
  morning_brief?: string | null;
  stale?: boolean | null;
  timestamp?: string | null;
  [key: string]: unknown;
}

// ── Top-level responses ────────────────────────────────
export interface FundamentalsResponse {
  data: FundamentalsData;
  timestamp: string;
  [key: string]: unknown;
}

export interface HealthDetailResponse {
  data: HealthDetailData;
  timestamp: string;
  [key: string]: unknown;
}

export interface NewsResponse {
  data: NewsData;
  timestamp: string;
  [key: string]: unknown;
}

export interface PaperPerformanceResponse {
  data: PaperPerformanceData;
  timestamp: string;
  [key: string]: unknown;
}

export interface PaperPositionsResponse {
  data: Array<PaperPosition>;
  timestamp: string;
  [key: string]: unknown;
}

export interface PricesResponse {
  data: PricesData;
  timestamp: string;
  stale?: boolean | null;
  [key: string]: unknown;
}

export interface SignalResponse {
  data: SignalData;
  timestamp: string;
  [key: string]: unknown;
}

export interface TradeIdeaResponse {
  data: TradeIdeaData;
  timestamp: string;
  [key: string]: unknown;
}

// ── Endpoint → response type ───────────────────────────
export interface ApiResponseMap {
  "/api/fundamentals": FundamentalsResponse;
  "/api/health-detail": HealthDetailResponse;
  "/api/news": NewsResponse;
  "/api/paper/performance": PaperPerformanceResponse;
  "/api/paper/positions": PaperPositionsResponse;
  "/api/prices": PricesResponse;
  "/api/signal": SignalResponse;
  "/api/trade-idea": TradeIdeaResponse;
}
