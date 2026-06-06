// Data provenance registry.
// Maps every panel's data to: where it came from, how fresh it is, what kind of
// source it is (live API / cached / model output / hardcoded estimate), and any
// honesty caveats. The dashboard surfaces this via <SourceTag /> so a user can
// audit credibility of any number on screen.
//
// Source kinds drive the dot colour:
//   live      green   — fetched in real time from a public API
//   cached    blue    — stored in SQLite, refreshed on a schedule
//   model     gold    — output of an in-house calc / regression / scoring engine
//   estimate  amber   — derived heuristic, not a real measurement
//   hardcoded red     — values baked into the codebase, manually updated
//   fallback  red     — primary source failed, using degraded backup

export type SourceKind = 'live' | 'cached' | 'model' | 'estimate' | 'hardcoded' | 'fallback';

export interface SourceMeta {
  key: string;
  /** Short display label shown on the chip, e.g. "EIA", "yfinance" */
  label: string;
  /** Full source name shown in the popover */
  fullName: string;
  /** Source kind — drives dot colour */
  kind: SourceKind;
  /** Auth model — None / API key / Scraped / etc. */
  auth: 'none' | 'api-key' | 'scraped' | 'derived';
  /** Refresh / cache TTL in seconds (0 = on-demand / per request) */
  ttlSeconds: number;
  /** Optional canonical URL the user can open to verify */
  url?: string;
  /** Backend file that fetches this */
  backendFile?: string;
  /** Honest notes — known caveats, fallback behaviour, etc. */
  notes?: string;
}

export const SOURCES: Record<string, SourceMeta> = {
  // ── Market data ─────────────────────────────────────────────────────────
  yfinance: {
    key: 'yfinance',
    label: 'yfinance',
    fullName: 'Yahoo Finance (unofficial scrape via yfinance lib)',
    kind: 'live',
    auth: 'none',
    ttlSeconds: 60,
    url: 'https://finance.yahoo.com/',
    backendFile: 'backend/fetchers/prices.py',
    notes: 'Unofficial. Subject to Yahoo throttling / schema breaks. Per-ticker Ticker.history() calls — batched download disabled due to tz bug.',
  },
  yfinance_ohlcv: {
    key: 'yfinance_ohlcv',
    label: 'yfinance · 5m',
    fullName: 'Yahoo Finance — 5-minute intraday OHLCV',
    kind: 'live',
    auth: 'none',
    ttlSeconds: 60,
    url: 'https://finance.yahoo.com/quote/BZ%3DF',
    backendFile: 'backend/app.py (/api/ohlcv)',
    notes: 'BZ=F / CL=F continuous contracts. Volume can be sparse on Brent.',
  },
  yfinance_daily: {
    key: 'yfinance_daily',
    label: 'yfinance · 1d',
    fullName: 'Yahoo Finance — 90-day daily OHLCV cache',
    kind: 'cached',
    auth: 'none',
    ttlSeconds: 3600,
    backendFile: 'backend/fetchers/historical.py',
  },
  yfinance_5y: {
    key: 'yfinance_5y',
    label: 'yfinance · 5y',
    fullName: 'Yahoo Finance — 5-year daily history for seasonality / patterns',
    kind: 'cached',
    auth: 'none',
    ttlSeconds: 86400,
    backendFile: 'backend/fetchers/seasonality.py',
  },

  // ── Curves & term structure ─────────────────────────────────────────────
  lco_xlsx: {
    key: 'lco_xlsx',
    label: 'ICE LCO · xlsx',
    fullName: 'ICE Brent LCO M1–M31 settlements (local xlsx, 2016→2026)',
    kind: 'cached',
    auth: 'none',
    ttlSeconds: 86400,
    backendFile: 'backend/data/LCOSettle.xlsx',
    notes: 'Static file on disk — not auto-refreshed. Settlements lag real-time pricing.',
  },
  curve_blend: {
    key: 'curve_blend',
    label: 'ICE + yfinance',
    fullName: 'Brent strip from local xlsx, WTI M1 live + basis-adjusted M2–M12',
    kind: 'cached',
    auth: 'none',
    ttlSeconds: 600,
    backendFile: 'backend/fetchers/curve.py',
  },
  multi_curve: {
    key: 'multi_curve',
    label: 'yfinance · strips',
    fullName: '5-product M1–M12 strips (Brent / WTI / RBOB / HO / NG)',
    kind: 'cached',
    auth: 'none',
    ttlSeconds: 3600,
    backendFile: 'backend/fetchers/multi_curve.py',
  },

  // ── EIA family ──────────────────────────────────────────────────────────
  eia_inv: {
    key: 'eia_inv',
    label: 'EIA · WPSR',
    fullName: 'EIA Weekly Petroleum Status Report (PET.WCESTUS1 etc.)',
    kind: 'live',
    auth: 'api-key',
    ttlSeconds: 7200,
    url: 'https://www.eia.gov/petroleum/weekly/',
    backendFile: 'backend/fetchers/eia.py',
    notes: 'Released Wed 10:30 ET. Requires EIA_API_KEY in .env.',
  },
  eia_rigs: {
    key: 'eia_rigs',
    label: 'EIA · rigs',
    fullName: 'EIA — U.S. crude oil rotary rigs in operation',
    kind: 'live',
    auth: 'api-key',
    ttlSeconds: 86400,
    backendFile: 'backend/fetchers/eia.py',
    notes: 'Currently returning null in diagnostics — endpoint or series may be offline.',
  },
  eia_steo: {
    key: 'eia_steo',
    label: 'EIA · STEO',
    fullName: 'EIA Short-Term Energy Outlook — global oil supply/demand/balance',
    kind: 'live',
    auth: 'api-key',
    ttlSeconds: 86400,
    url: 'https://www.eia.gov/outlooks/steo/',
    backendFile: 'backend/fetchers/eia.py',
    notes: 'Updated monthly. 18-month outlook (history + forecast).',
  },
  eia_intl: {
    key: 'eia_intl',
    label: 'EIA · INTL',
    fullName: 'EIA International — OPEC production by member',
    kind: 'live',
    auth: 'api-key',
    ttlSeconds: 86400,
    backendFile: 'backend/fetchers/eia.py',
    notes: 'Currently returning "No data returned from EIA INTL" — dashboard falls back to static OPEC estimates.',
  },
  eia_spark: {
    key: 'eia_spark',
    label: 'EIA · power',
    fullName: 'EIA electricity wholesale price → spark/dark spread derivation',
    kind: 'model',
    auth: 'api-key',
    ttlSeconds: 7200,
    backendFile: 'backend/fetchers/eia.py',
    notes: 'Spark = electricity − 7×Henry Hub; dark = electricity − coal heat-rate. Derived inside the EIA fetcher.',
  },

  // ── Positioning / OPEC ──────────────────────────────────────────────────
  cftc_cot: {
    key: 'cftc_cot',
    label: 'CFTC · COT',
    fullName: 'CFTC Commitments of Traders (legacy disaggregated futures)',
    kind: 'live',
    auth: 'none',
    ttlSeconds: 86400,
    url: 'https://www.cftc.gov/MarketReports/CommitmentsofTraders/',
    backendFile: 'backend/fetchers/cot.py',
    notes: 'Published Fri 15:30 ET, reflects Tue. Percentile calculated over rolling 3y window.',
  },
  opec_static: {
    key: 'opec_static',
    label: 'OPEC · static',
    fullName: 'OPEC member quotas + production (HARDCODED IEA / Platts estimates)',
    kind: 'hardcoded',
    auth: 'none',
    ttlSeconds: 0,
    backendFile: 'backend/fetchers/opec.py',
    notes: 'Aramco / OPEC do not publish a machine-readable feed. Numbers are manually entered from public press releases. Update interval: ad-hoc.',
  },

  // ── News / sentiment ────────────────────────────────────────────────────
  news_apify: {
    key: 'news_apify',
    label: 'Apify · scrape',
    fullName: 'Apify scraper (primary) → NewsAPI / direct RSS (fallbacks)',
    kind: 'live',
    auth: 'api-key',
    ttlSeconds: 600,
    backendFile: 'backend/fetchers/news.py',
    notes: 'Apify primary. If quota/auth fails: falls back to NewsAPI, then to direct RSS pulls. Look at `source_used` in response.',
  },
  finbert: {
    key: 'finbert',
    label: 'FinBERT · local',
    fullName: 'ProsusAI/finbert — local HuggingFace inference for headline sentiment',
    kind: 'model',
    auth: 'none',
    ttlSeconds: 600,
    url: 'https://huggingface.co/ProsusAI/finbert',
    backendFile: 'backend/fetchers/sentiment.py',
    notes: 'Runs offline once model cached (~420MB). Falls back to 0.0 scores if model fails to load.',
  },

  // ── Weather ─────────────────────────────────────────────────────────────
  open_meteo: {
    key: 'open_meteo',
    label: 'Open-Meteo',
    fullName: 'Open-Meteo — 7-day HDD/CDD outlook, 5 US population centres',
    kind: 'live',
    auth: 'none',
    ttlSeconds: 3600,
    url: 'https://open-meteo.com/',
    backendFile: 'backend/fetchers/weather.py',
    notes: 'Free, no key. Normals approximated from NOAA climatology.',
  },

  // ── Macro ───────────────────────────────────────────────────────────────
  fred: {
    key: 'fred',
    label: 'FRED · series',
    fullName: 'St. Louis Fed FRED — DGS10, CPIAUCSL, EURUSD, FEDFUNDS, INDPRO, MORTGAGE30US',
    kind: 'live',
    auth: 'api-key',
    ttlSeconds: 3600,
    url: 'https://fred.stlouisfed.org/',
    backendFile: 'backend/fetchers/macro.py',
    notes: 'Requires FRED_API_KEY. If absent, response is marked stale=true. CPI/INDPRO release monthly; DGS10 daily.',
  },

  // ── Models / in-house ───────────────────────────────────────────────────
  fair_value_model: {
    key: 'fair_value_model',
    label: 'PULSE · model',
    fullName: 'Multi-factor fair-value regression (inventory, curve, COT, DXY, geo)',
    kind: 'model',
    auth: 'derived',
    ttlSeconds: 600,
    backendFile: 'backend/models/fair_value.py',
    notes: 'Currently returning empty {} in diagnostics — model requires upstream fundamentals to populate component dict.',
  },
  signal_engine: {
    key: 'signal_engine',
    label: 'PULSE · signal',
    fullName: 'Composite signal — weighted blend of inventory/curve/COT/FV/tech/DXY/geo',
    kind: 'model',
    auth: 'derived',
    ttlSeconds: 600,
    backendFile: 'backend/models/signal_engine.py',
    notes: 'Score range [−2, +2]. Conviction = HIGH when ≥ max(5, n−1) factors agree.',
  },
  trade_idea_rule: {
    key: 'trade_idea_rule',
    label: 'PULSE + Ollama',
    fullName: 'Rule-based trade idea + Ollama llama3 morning brief',
    kind: 'model',
    auth: 'derived',
    ttlSeconds: 600,
    backendFile: 'backend/models/trade_idea.py',
    notes: 'If Ollama daemon not running, brief falls back to deterministic 5-sentence template.',
  },
  pattern_scipy: {
    key: 'pattern_scipy',
    label: 'scipy · peaks',
    fullName: 'scipy peak/trough detection — H&S, IH&S, Dbl Top/Bot, Flag, Triangle + analog lookup',
    kind: 'model',
    auth: 'derived',
    ttlSeconds: 3600,
    backendFile: 'backend/models/patterns.py',
  },
  correlations_calc: {
    key: 'correlations_calc',
    label: 'PULSE · corr',
    fullName: 'Rolling 30d + 252d correlation matrix (Brent / WTI / DXY / SPX / HH)',
    kind: 'model',
    auth: 'derived',
    ttlSeconds: 7200,
    backendFile: 'backend/models/correlations.py',
  },
  term_structure_calc: {
    key: 'term_structure_calc',
    label: 'PULSE · ts',
    fullName: '5×5 cross-product correlation matrix + strip enrichment from LCO + yfinance',
    kind: 'model',
    auth: 'derived',
    ttlSeconds: 3600,
    backendFile: 'backend/models/term_structure.py',
  },
  technicals_calc: {
    key: 'technicals_calc',
    label: 'PULSE · ta',
    fullName: 'RSI(14) · MACD(12,26,9) · BBands(20,2σ) · ATR(14) on yfinance daily',
    kind: 'model',
    auth: 'derived',
    ttlSeconds: 300,
    backendFile: 'backend/fetchers/technicals.py',
  },
  geo_risk_calc: {
    key: 'geo_risk_calc',
    label: 'PULSE · geo',
    fullName: 'Geo-risk index — Brent-WTI spread anomaly + VIX level + negative news count',
    kind: 'model',
    auth: 'derived',
    ttlSeconds: 7200,
    backendFile: 'backend/fetchers/geo_risk.py',
  },
  alerts_calc: {
    key: 'alerts_calc',
    label: 'PULSE · alerts',
    fullName: 'PRICE_SHOCK / COT_EXTREME / EIA_SURPRISE / IV_SPIKE detector',
    kind: 'model',
    auth: 'derived',
    ttlSeconds: 60,
    backendFile: 'backend/models/alerts.py',
  },

  // ── Institutional desk feed (paid Refinitiv/ICE-grade, supplied via /Data) ─
  data_lake_settlements: {
    key: 'data_lake_settlements',
    label: 'ICE LCO · desk',
    fullName: 'ICE Brent C1-C31 daily settlements (institutional desk feed, /Data CSV)',
    kind: 'cached',
    auth: 'derived',
    ttlSeconds: 86400,
    backendFile: 'Data/LCO_Brent_daily_settlement_c1_to_c31_2016_2026.csv',
    notes: '2,713 trading days, 2016 → present. Refresh by replacing the file in /Data.',
  },
  data_lake_15y_spread: {
    key: 'data_lake_15y_spread',
    label: 'ICE · 15y',
    fullName: 'ICE Brent M1-M12 spread, 14.6-year history (3,693 obs)',
    kind: 'cached',
    auth: 'derived',
    ttlSeconds: 86400,
    backendFile: 'Data/LCO_Brent_daily_close_c1_c12_spread_2011_2026.xlsx',
    notes: 'Drives the 15-year percentile rank shown in the Curve Regime panel.',
  },
  data_lake_1min: {
    key: 'data_lake_1min',
    label: '1-min mids · desk',
    fullName: 'Brent / WTI / HO / Gasoil 1-minute mid prices (5 years, ~3 GB total)',
    kind: 'cached',
    auth: 'derived',
    ttlSeconds: 21600,
    backendFile: 'Data/LCO_Brent_1min_outrights_midprice_*.csv',
    notes: 'Underlies the real realised-vol calc. Tail loaded on demand to stay in low-MB memory footprint.',
  },
  data_lake_orderflow: {
    key: 'data_lake_orderflow',
    label: 'Buy/Sell · desk',
    fullName: 'Per-contract daily buy/sell volume from institutional desk feed',
    kind: 'cached',
    auth: 'derived',
    ttlSeconds: 3600,
    backendFile: 'Data/LCO_Brent_daily_OHLCV_buysell_volume_multi_contract.xlsx',
    notes: 'Genuine order-flow imbalance — not available from any free public API.',
  },

  // ── New free authoritative sources (Phase A additions) ─────────────────
  ovx_fred: {
    key: 'ovx_fred',
    label: 'CBOE OVX',
    fullName: 'CBOE Crude Oil ETF Volatility Index (OVXCLS) via FRED',
    kind: 'live',
    auth: 'api-key',
    ttlSeconds: 3600,
    url: 'https://fred.stlouisfed.org/series/OVXCLS',
    backendFile: 'backend/fetchers/ovx.py',
    notes: 'Real institutional 30-day implied vol on USO options — the benchmark traders quote. Replaces the realised-vol-as-IV-proxy hack.',
  },
  jodi_oil: {
    key: 'jodi_oil',
    label: 'JODI-Oil',
    fullName: 'JODI-Oil World Database — monthly crude production by country',
    kind: 'live',
    auth: 'none',
    ttlSeconds: 86400 * 7,
    url: 'https://www.jodidata.org/oil/',
    backendFile: 'backend/fetchers/jodi.py',
    notes: 'Free, no auth, 100+ countries report monthly. Replaces the HARDCODED OPEC static table. Lag is one month vs current date.',
  },
  gdelt_doc: {
    key: 'gdelt_doc',
    label: 'GDELT 2.0',
    fullName: 'GDELT Project DOC 2.0 API — global news + theme + tone',
    kind: 'live',
    auth: 'none',
    ttlSeconds: 600,
    url: 'https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/',
    backendFile: 'backend/fetchers/gdelt.py',
    notes: 'Free, no auth, 15-min news cadence, 100+ languages. 5s rate limit per IP — we throttle internally. Replaces Apify/NewsAPI primary path.',
  },
  baker_hughes_rig: {
    key: 'baker_hughes_rig',
    label: 'Baker Hughes',
    fullName: 'Baker Hughes weekly US rig count (homepage scrape + EIA STEO backup)',
    kind: 'live',
    auth: 'none',
    ttlSeconds: 86400,
    url: 'https://rigcount.bakerhughes.com/',
    backendFile: 'backend/fetchers/rig_count.py',
    notes: 'Replaces the dead EIA endpoint. Will fall back to EIA STEO monthly if the homepage scrape returns 403.',
  },
  stooq_fallback: {
    key: 'stooq_fallback',
    label: 'Stooq',
    fullName: 'Stooq.com daily CSV (free, no auth) — price fallback when yfinance breaks',
    kind: 'live',
    auth: 'none',
    ttlSeconds: 60,
    url: 'https://stooq.com/db/',
    backendFile: 'backend/fetchers/stooq.py',
    notes: 'Triggered automatically when yfinance returns insufficient data for a symbol.',
  },
  ecb_fx: {
    key: 'ecb_fx',
    label: 'ECB FX',
    fullName: 'ECB euro foreign exchange reference rates (daily XML, no auth)',
    kind: 'live',
    auth: 'none',
    ttlSeconds: 3600,
    url: 'https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml',
    backendFile: 'backend/fetchers/ecb_fx.py',
    notes: 'Published 16:00 CET every working day. Second-source EUR/USD alongside FRED DEXUSEU.',
  },
  curve_regime_15y: {
    key: 'curve_regime_15y',
    label: 'PULSE · 15y',
    fullName: '15-year Brent M1-M12 percentile rank + regime classifier',
    kind: 'model',
    auth: 'derived',
    ttlSeconds: 3600,
    backendFile: 'backend/fetchers/curve_regime.py',
    notes: 'Computes z-score / percentile / regime label from /Data 15-year spread file. Provides context the bare M1-M2 spread lacks.',
  },
  order_flow_model: {
    key: 'order_flow_model',
    label: 'PULSE · OF',
    fullName: 'Per-contract order-flow imbalance from institutional buy/sell volume',
    kind: 'model',
    auth: 'derived',
    ttlSeconds: 3600,
    backendFile: 'backend/fetchers/order_flow.py',
    notes: 'imbalance = (buy − sell) / (buy + sell). Rolling 20-day average per contract.',
  },
  marketaux: {
    key: 'marketaux',
    label: 'MarketAux',
    fullName: 'MarketAux financial news API (Energy industry filter, sentiment-scored)',
    kind: 'live',
    auth: 'api-key',
    ttlSeconds: 900,
    url: 'https://www.marketaux.com/',
    backendFile: 'backend/fetchers/marketaux.py',
    notes: 'Secondary news source layered between GDELT and the legacy aggregator. Free tier = 100 requests/day; we use ~96/day at the 15-min cadence.',
  },
  groq_brief: {
    key: 'groq_brief',
    label: 'Groq · llama3',
    fullName: 'Groq cloud llama-3.3-70b — morning brief generator',
    kind: 'live',
    auth: 'api-key',
    ttlSeconds: 600,
    url: 'https://console.groq.com/',
    backendFile: 'backend/models/trade_idea.py (_groq_brief)',
    notes: 'Generates the 120-word morning brief in <2s using Groq\'s free tier. Falls back to local Ollama, then to deterministic template.',
  },
  analogs_stumpy: {
    key: 'analogs_stumpy',
    label: 'stumpy · MP',
    fullName: 'stumpy matrix-profile similarity search over 10-year Brent C1 history',
    kind: 'model',
    auth: 'derived',
    ttlSeconds: 21600,
    backendFile: 'backend/fetchers/analogs.py',
    notes: 'Finds the most similar historical 60-day windows by z-normalised Euclidean distance. Forward-return averaged across top-K gives a backtested bias.',
  },
  realised_vol_5y: {
    key: 'realised_vol_5y',
    label: 'RV · desk',
    fullName: '30-day annualised realised vol from /Data 1-min mids, ranked vs 5-year history',
    kind: 'model',
    auth: 'derived',
    ttlSeconds: 21600,
    backendFile: 'backend/fetchers/realised_vol.py',
    notes: 'Computed once every 6h (loading the 4 big CSVs takes ~30s). Cross-validates OVX.',
  },

  // ── Honest "we don't really have this" sources ──────────────────────────
  saudi_osp_hc: {
    key: 'saudi_osp_hc',
    label: 'Saudi OSP · hard',
    fullName: 'Saudi Aramco Official Selling Prices (HARDCODED from monthly press release)',
    kind: 'hardcoded',
    auth: 'none',
    ttlSeconds: 0,
    backendFile: 'backend/fetchers/cracks.py',
    notes: 'Aramco publishes a PDF on the first of each month. Numbers are hand-copied. Currently showing May 2026 values.',
  },
  vlcc_estimate: {
    key: 'vlcc_estimate',
    label: 'VLCC · proxy',
    fullName: 'VLCC freight rate proxy — Dubai ≈ Brent × 0.975 (ESTIMATED)',
    kind: 'estimate',
    auth: 'derived',
    ttlSeconds: 600,
    backendFile: 'backend/fetchers/cracks.py',
    notes: 'Baltic Exchange BDTI requires a paid feed ($500+/mo). This is a crude heuristic, not a real shipping rate.',
  },
  iv_synthetic: {
    key: 'iv_synthetic',
    label: 'IV · realised',
    fullName: 'Realised volatility used as an IV proxy (no options chain feed)',
    kind: 'estimate',
    auth: 'derived',
    ttlSeconds: 3600,
    backendFile: 'backend/fetchers/options_iv.py',
    notes: 'A real ATM IV would require CME / Refinitiv. We compute 20-day realised vol and rank against a 30-row history persisted in SQLite.',
  },

  // ── External live feeds ─────────────────────────────────────────────────
  nitter_rss: {
    key: 'nitter_rss',
    label: 'Nitter RSS',
    fullName: 'Nitter (X.com mirror) — Javier Blas + Amena Bakr posts via RSS',
    kind: 'live',
    auth: 'scraped',
    ttlSeconds: 900,
    backendFile: 'backend/fetchers/analyst_watch.py',
    notes: 'Falls through a list of public Nitter instances. Often degraded — instances go offline regularly. Trump → Truth Social direct link (X API blocked).',
  },
  static_reference: {
    key: 'static_reference',
    label: 'static · ref',
    fullName: 'Static reference content (contract specs, case studies, curriculum)',
    kind: 'hardcoded',
    auth: 'none',
    ttlSeconds: 0,
    backendFile: 'frontend/src/lib/contracts.ts · caseStudies.ts',
    notes: 'Reference material from the Futures First curriculum and exchange contract specs. Not market data — does not refresh.',
  },
  aisstream: {
    key: 'aisstream',
    label: 'aisstream.io',
    fullName: 'aisstream.io WebSocket — live AIS tanker positions',
    kind: 'live',
    auth: 'api-key',
    ttlSeconds: 300,
    url: 'https://aisstream.io/',
    backendFile: 'backend/fetchers/tanker_watch.py',
    notes: 'Requires AISSTREAM_API_KEY. 30-second snapshot near Hormuz / Suez / Bab-el-Mandeb / Malacca. If key missing, panel shows news-driven chokepoint risk instead.',
  },
};

/* ─────────────────────────────────────────────────────────────────────────
   Helpers
   ───────────────────────────────────────────────────────────────────────── */

/** Format an ISO timestamp as "12s / 4m / 3h / 2d ago", or "—" if absent. */
export function ageString(iso?: string | number | null): string {
  if (!iso) return '—';
  let t: number;
  if (typeof iso === 'number') t = iso;
  else t = new Date(iso).getTime();
  if (!Number.isFinite(t)) return '—';
  const sec = Math.max(0, Math.floor((Date.now() - t) / 1000));
  if (sec < 60) return `${sec}s ago`;
  if (sec < 3600) return `${Math.floor(sec / 60)}m ago`;
  if (sec < 86400) return `${Math.floor(sec / 3600)}h ago`;
  return `${Math.floor(sec / 86400)}d ago`;
}

/** Classify freshness vs TTL — used to override dot colour when data goes stale. */
export function freshness(iso: string | number | null | undefined, ttlSeconds: number):
  'fresh' | 'aging' | 'stale' | 'unknown' {
  if (!iso) return 'unknown';
  const t = typeof iso === 'number' ? iso : new Date(iso).getTime();
  if (!Number.isFinite(t)) return 'unknown';
  const ageSec = (Date.now() - t) / 1000;
  if (ttlSeconds <= 0) return 'fresh';
  if (ageSec <= ttlSeconds) return 'fresh';
  if (ageSec <= ttlSeconds * 3) return 'aging';
  return 'stale';
}

/** Format a TTL in seconds as a short human label. */
export function ttlLabel(seconds: number): string {
  if (seconds <= 0) return 'on-demand';
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
  if (seconds < 86400) return `${Math.round(seconds / 3600)}h`;
  return `${Math.round(seconds / 86400)}d`;
}

/** Tailwind colour class for each kind (border + bg) */
export function kindColour(kind: SourceKind): { dot: string; text: string } {
  switch (kind) {
    case 'live':      return { dot: 'bg-bull',         text: 'text-bull' };
    case 'cached':    return { dot: 'bg-[#4d8eff]',    text: 'text-[#7fb0ff]' };
    case 'model':     return { dot: 'bg-gold',         text: 'text-gold' };
    case 'estimate':  return { dot: 'bg-neut',         text: 'text-neut' };
    case 'hardcoded': return { dot: 'bg-bear',         text: 'text-bear' };
    case 'fallback':  return { dot: 'bg-bear animate-pulse', text: 'text-bear' };
  }
}

export function kindLabel(kind: SourceKind): string {
  return ({
    live: 'LIVE',
    cached: 'CACHED',
    model: 'MODEL',
    estimate: 'ESTIMATE',
    hardcoded: 'HARDCODED',
    fallback: 'FALLBACK',
  } as const)[kind];
}

export function resolveSource(key: string | SourceMeta | undefined | null): SourceMeta | null {
  if (!key) return null;
  if (typeof key === 'object') return key;
  return SOURCES[key] ?? null;
}
