Let me read the remaining models and db layer before writing:

Now I have read every file. Writing the full report now.

---

# PULSE — Complete Technical Reference
**Project:** Price & Uncertainty Live Signal Engine — Energy Trading Dashboard
**Stack:** Python 3.11 · Flask 3 · SQLite · vanilla JS · IBM Plex Mono
**As of:** 2026-05-29

---

## 1. What This Project Is

PULSE is a single-page energy trading dashboard designed for a Futures First internship. It aggregates live market data from a dozen sources, runs quantitative models on top of them, and presents everything in a terminal-aesthetic browser UI. It is **not** a production trading system — it is a research and monitoring tool.

**The three things it does:**
1. **Fetches** live data every N seconds (prices, inventory, positioning, news, weather, tankers, etc.)
2. **Models** that data (fair value, composite signal, patterns, trade idea)
3. **Displays** results in a 5-tab browser dashboard with charts, tables, and alerts

---

## 2. How to Start It

```
cd pulse/
python start.py
```

`start.py` does exactly four things:
1. Checks Python ≥ 3.11 and core package imports
2. Launches `backend/app.py` as a subprocess on port 5000
3. Polls `http://127.0.0.1:5000/api/health` until it gets a 200 (up to 20 seconds)
4. Opens `frontend/index.html` in the default browser using `webbrowser.open()`

The frontend is a **static HTML file opened directly** (`file://` protocol), not served by Flask. Flask only serves the JSON API on `http://127.0.0.1:5000`. The frontend fetches from that URL. CORS is enabled on all Flask routes so the `file://` origin works.

On startup, a background thread runs `warm_cache()` which pre-populates SQLite with fresh data in dependency order (prices → curve → weather → technicals → term structure → fundamentals → fair value → signal → correlations). Slow fetchers (news, macro, patterns, IV, trade idea) are handled by APScheduler which fires them immediately and then on their respective intervals.

---

## 3. Full Directory Layout

```
pulse/
├── start.py                      # one-command launcher
├── requirements.txt              # pinned pip freeze (2026-05-28)
├── CLAUDE.md                     # project state / session handoff file
├── .env                          # API keys (NOT committed)
│
├── backend/
│   ├── app.py                    # Flask server: all routes, TTL cache, scheduler
│   │
│   ├── data/
│   │   └── LCOSettle.xlsx        # ICE Brent M1-M31 daily settlements 2016→2026
│   │                             # (real xlsx saved from ICE, ~2713 rows)
│   │
│   ├── cache/                    # pickle caches (auto-created)
│   │   ├── historical.pkl        # 5-year daily OHLCV for Brent/WTI/HH/DXY/SPX
│   │   └── cot.pkl               # CFTC COT 4-year combined dataset
│   │
│   ├── db/
│   │   ├── __init__.py
│   │   ├── cache.py              # SQLite TTL cache (pulse_cache.db)
│   │   ├── pulse_cache.db        # auto-created SQLite database
│   │   └── signal_history.py     # 500-row rolling signal score log
│   │
│   ├── fetchers/
│   │   ├── prices.py             # live OHLCV for 10 assets via yfinance
│   │   ├── curve.py              # Brent (xlsx) + WTI (basis-adjusted) M1-M12 strip
│   │   ├── historical.py         # 5-year daily OHLCV pickle cache + analytics helpers
│   │   ├── multi_curve.py        # 5-product M1-M12 strips + Brent M1 history from xlsx
│   │   ├── eia.py                # EIA inventory, rig count, OPEC production, STEO, spark/dark
│   │   ├── cot.py                # CFTC COT positioning percentile (4 energy markets)
│   │   ├── opec.py               # OPEC compliance table (static + EIA INTL live)
│   │   ├── geo_risk.py           # 0-100 geopolitical risk index (4-component composite)
│   │   ├── news.py               # energy news (Apify primary, NewsAPI fallback) + clustering
│   │   ├── sentiment.py          # FinBERT batch scorer + recency-weighted aggregate
│   │   ├── weather.py            # Open-Meteo 7-day HDD/CDD for 5 US cities
│   │   ├── technicals.py         # RSI(14) MACD(12,26,9) BBands(20,2σ) ATR(14) — pure numpy
│   │   ├── seasonality.py        # monthly avg % returns for BZ=F + NG=F (5-year yfinance)
│   │   ├── macro.py              # FRED: DGS10, CPI, EUR/USD, FEDFUNDS, INDPRO, MORTGAGE30US
│   │   ├── cracks.py             # crack spreads, VLCC proxy, Saudi OSP
│   │   ├── analyst_watch.py      # Javier Blas + Amena Bakr via Nitter RSS; Trump Truth Social
│   │   └── tanker_watch.py       # live AIS tanker counts at 4 chokepoints via aisstream.io
│   │
│   └── models/
│       ├── fair_value.py         # cost-of-carry fair value with 4 fundamental adjustments
│       ├── correlations.py       # Brent/WTI/DXY/SPX/HH 90-day correlation matrix
│       ├── signal_engine.py      # 9-indicator weighted composite signal [-2, +2]
│       ├── term_structure.py     # 5-product energy heatmap + calendar spread matrix
│       ├── patterns.py           # scipy pattern recognition + top-3 historical analogs
│       ├── trade_idea.py         # rule-based trade idea + Ollama llama3 morning brief
│       └── alerts.py             # PRICE_SHOCK, COT_EXTREME, EIA_SURPRISE, IV_SPIKE
│
└── frontend/
    └── index.html                # entire frontend (~138 KB, single file, vanilla JS)
```

---

## 4. Backend Architecture

### 4.1 Flask App (`app.py`)

The Flask app is the only process users interact with indirectly (the browser calls it). It has three layers:

**Layer 1 — SQLite cache (`db/cache.py`)**
Every piece of data is stored in a single SQLite table:
```
cache(key TEXT PRIMARY KEY, value_json TEXT, updated_at REAL)
```
`get_cached(key, ttl)` returns the value if it's younger than `ttl` seconds, otherwise returns it anyway with `{"stale": True}` merged in. It only returns `None` if the key has never been written. This design means the API **never crashes due to missing data** — it returns stale data with a flag.

**Layer 2 — APScheduler (`BackgroundScheduler`)**
At startup, a scheduler is started with one job per cache key. Each job calls the fetcher and writes to SQLite. Slow jobs (news, macro, patterns, IV, trade idea, alerts, cracks, STEO, analyst watch, tanker watch) are given `next_run_time=_NOW` so they fire immediately on startup.

| Cache key | TTL | What fires it |
|---|---|---|
| prices | 60s | `_refresh_prices()` |
| ohlcv | 60s | `_refresh_ohlcv()` |
| history | 3600s | `_refresh_history()` |
| curve | 600s | `_refresh_curve()` |
| fair_value | 600s | `_refresh_fair_value()` |
| signal | 600s | `_refresh_signal()` |
| technicals | 300s | `_refresh_technicals()` |
| fundamentals | 7200s | `_refresh_fundamentals()` |
| correlations | 7200s | `_refresh_correlations()` |
| term_structure | 3600s | `_refresh_term_structure()` |
| news | 600s | `_refresh_news()` (fires immediately) |
| macro | 3600s | `_refresh_macro()` (fires immediately) |
| patterns | 3600s | `_refresh_patterns()` (fires immediately) |
| iv | 300s | `_refresh_iv()` (fires immediately) |
| trade_idea | 600s | `_refresh_trade()` (fires immediately) |
| alerts | 60s | `_refresh_alerts()` (fires immediately) |
| cracks | 600s | `_refresh_cracks()` (fires immediately) |
| steo | 86400s | `_refresh_steo()` (fires immediately) |
| analyst_watch | 900s | lambda (fires immediately) |
| tanker_watch | 300s | lambda (fires immediately) |

**Layer 3 — Flask routes**
Every route follows the same `_fetch_X()` → cache-hit-or-call-fetcher → `jsonify()` pattern. The critical route is `/api/all` which assembles all 17 datasets in one response — the frontend calls this every 60 seconds and distributes the data to every panel.

**`?nocache=1` bypass:** Any route can be force-refreshed by appending `?nocache=1`. The `get_cached()` wrapper checks `flask.request.args` and returns `None` (cache miss) when that parameter is present.

**`safe_fetch(func, fallback)`:** Every fetcher call is wrapped in this. It catches all exceptions, logs them, and returns the fallback value. This is why the dashboard never shows a blank panel — it always shows something.

### 4.2 The `warm_cache()` Function
Runs in a daemon thread 2 seconds after startup. Populates the SQLite cache in this specific order to respect dependencies:
1. prices, curve, ohlcv, history (no dependencies)
2. weather, technicals, term_structure (depend on historical data)
3. fundamentals (depends on prices for HH price → spark/dark spread)
4. fair_value (depends on fundamentals: inventory, OPEC, geo_risk)
5. signal (depends on fair_value, fundamentals, technicals, curve)
6. correlations (depends on historical)

Slow fetchers are handled by the APScheduler that was already started, not in `warm_cache()`.

---

## 5. Data Sources — Every Fetcher Explained

### `fetchers/prices.py`
**What:** Live prices for 10 assets.
**How:** `yf.Ticker(symbol).history(period="5d", interval="1d")` per ticker. Takes last two closes to compute change. Per-ticker (not batch) to avoid timezone join errors that occur when mixing exchanges (ICE BZ=F vs NYSE DX-Y.NYB).
**Assets:** brent (BZ=F), wti (CL=F), henry_hub (NG=F), dxy (DX-Y.NYB), sp500 (ES=F), gold (GC=F), vix (^VIX), gasoline (RB=F), heating_oil (HO=F), treasury_10y (^TNX)
**Output per asset:** `{price, change_abs, change_pct, high, low, timestamp, stale}`
**Stale fallback:** Module-level `_last_known` dict — if a fetch fails, the last good value is returned with `stale=True`.

### `fetchers/historical.py`
**What:** 5-year daily OHLCV for Brent, WTI, Henry Hub, DXY, S&P 500.
**How:** Downloaded once via `yf.Ticker(symbol).history(period="5y")` and pickled to `cache/historical.pkl`. The pickle is refreshed when it's >24 hours old. An in-process `_session_data` dict prevents repeated disk reads.
**Analytics helpers exposed:**
- `load_historical()` → dict of DataFrames
- `get_returns(asset)` → daily pct-change series
- `get_volatility(asset, window)` → annualised vol = `std(returns[-window:]) × √252 × 100`
- `get_percentile_rank(asset, value, lookback)` → where current value sits vs last N closes (0-100)
- `get_moving_average(asset, window)` → rolling SMA of Close
- `get_seasonality(asset)` → avg monthly return per month (1-12)
**Used by:** geo_risk, fair_value (DXY deviation), technicals (OHLCV), correlations, signal engine (DXY indicator)

### `fetchers/curve.py`
**What:** Brent and WTI M1-M12 futures strip prices.
**How:**
- **Brent:** Reads from `multi_curve.py` which reads the ICE LCO xlsx directly — authoritative daily settlements.
- **WTI:** M1 = live `CL=F` price. M2-M12 = Brent prices minus the live Brent-WTI spread at M1 (basis-adjusted). Yahoo Finance doesn't reliably serve deferred NYMEX individual contracts.
- `get_both_curves()` returns both strips plus a comparison block (correlation between strips, average Brent-WTI spread across tenors, interpretation label).
**Structure detection:** slope = `prices[-1] - prices[0]`. Backwardation if slope > 0.20, contango if < −0.20, flat otherwise.

### `fetchers/multi_curve.py`
**What:** M1-M12 strip prices for 5 products + Brent M1 history from the xlsx.
**How:** Reads `backend/data/LCOSettle.xlsx` via openpyxl. The xlsx has a specific layout: row 1 = contract names (LCOc1…LCOc31), row 2 = (Timestamp, SETTLE) column headers, row 3+ = data newest first. For contract Mi, `SETTLE = row[1 + (i-1)*2]`, `Date = row[0]`.
**Products served:** Brent (from xlsx), WTI/RBOB/HO/HH (from yfinance dated tickers or continuous).
**Critical fix:** `pd.Timestamp.now()` (tz-naive) is used for date comparisons with the xlsx DatetimeIndex which is also tz-naive. Using `pd.Timestamp.utcnow()` (tz-aware) causes a comparison error.

### `fetchers/eia.py`
**What:** Five data products from the EIA v2 API.
1. **Inventory:** Weekly crude/Cushing/gasoline/distillate/natgas stocks vs 5-year seasonal average. `_seasonal_average()` pulls 275 weeks of data and averages the same ISO week number across the prior 5 years (excludes current year). `_deviation_label()` classifies: WELL_ABOVE/ABOVE/NORMAL/BELOW/WELL_BELOW.
2. **Rig Count:** From EIA drill/rig API, week-on-week change.
3. **OPEC Production:** EIA International Data (productId=57), 12 OPEC members, monthly, values >100 are in thousand b/d (divide by 1000 to get Mb/d).
4. **Spark/Dark Spread:** EIA retail electricity price (¢/kWh × 10 = $/MWh). Spark = elec − HH × 6.5. Dark = elec − 65.0/8.0. HH price supplied by caller from cached prices, falls back to live yfinance.
5. **STEO (Short-Term Energy Outlook):** Global liquid fuels supply and demand (18 months), tries multiple series IDs (PAPR_WORLD, COPR_WORLD, etc.) until one succeeds.

### `fetchers/cot.py`
**What:** CFTC Commitments of Traders — Managed Money net positions for 4 energy markets.
**How:** Downloads annual Disaggregated Futures XLS zips from CFTC (`fut_disagg_xls_{year}.zip`), combines 4 years, pickles to `cache/cot.pkl` (24-hour TTL). Extracts `M_Money_Positions_Long_ALL` minus `M_Money_Positions_Short_ALL` = net position. Computes 3-year percentile rank of current net vs all prior weeks.
**Contrarian logic:** High percentile (crowded long) → negative signal score (contrarian SELL). Low percentile (crowded short) → positive score (contrarian BUY).
**Markets:** Crude Oil WTI, Nat Gas ICE LD1, Gasoline RBOB, NY Harbor ULSD.

### `fetchers/geo_risk.py`
**What:** 0-100 composite geopolitical risk index.
**How:** 4 equally-weighted components (25 pts each):
1. Brent-WTI spread z-score vs 252-day history — wide spread signals supply-route stress
2. Oil 30-day realised vol percentile vs 252-day history
3. VIX absolute level (threshold bands: <15=5pts, <20=10pts, <25=16pts, <30=21pts, ≥30=25pts)
4. Negative energy headline count (×5 pts each, capped at 25)

Has a module-level in-process TTL cache (300s) so the `get_all_signals()` call that iterates 3 assets doesn't trigger 3 separate Apify calls.

Labels: LOW (0-25), MODERATE (25-45), ELEVATED (45-65), HIGH (65-80), CRITICAL (80-100).

### `fetchers/news.py`
**What:** Energy headlines with FinBERT sentiment scores and topic clustering.
**How:**
- **Primary source:** Apify actor scrapes specific energy news URLs. Requires `APIFY_API_TOKEN` in `.env`.
- **Fallback:** NewsAPI keyword search for "oil gas energy OPEC". Requires `NEWSAPI_KEY`.
- **FinBERT scoring:** Each headline passed to `sentiment.py` which runs ProsusAI/finbert (HuggingFace, ~420MB download on first run). Returns positive/negative/neutral with confidence.
- **Recency weighting:** More recent articles get higher weight in the composite score. Composite = weighted mean of individual scores.
- **Clustering:** `_cluster_articles()` scores each article against 4 theme keyword sets (OPEC+, Supply/Geo, Demand, Macro/Dollar) and assigns to the highest-scoring theme.
**Output:** `{articles: [...], composite_sentiment: {composite, label, bullish, bearish, neutral}, clusters: {theme: [articles]}, negative_count}`

### `fetchers/sentiment.py`
**What:** FinBERT batch sentiment scoring.
**How:** Loads `ProsusAI/finbert` from HuggingFace transformers. Accepts a list of text strings, returns `[{label, score}]`. Batch processes to avoid OOM. Downloads ~420MB to `~/.cache/huggingface/` on first run. Subsequent runs load from cache instantly.

### `fetchers/weather.py`
**What:** 7-day HDD/CDD outlook for 5 US cities.
**How:** Open-Meteo API (free, no key). Gets hourly temp forecasts, converts to daily mean, computes HDD = max(0, 65°F − mean) and CDD = max(0, mean − 65°F). Compares to NOAA 1991-2020 climate normals (hardcoded monthly means per city). Population-weighted aggregate (NYC 25%, Chicago 22%, Dallas 18%, Atlanta 17%, Boston 18%).
**Net demand signal:** In heating season (Nov-Mar), HDD deviation dominates (80%/20%). In cooling season (Jun-Sep), CDD dominates. Shoulder = 50/50.

### `fetchers/technicals.py`
**What:** RSI, MACD, Bollinger Bands, ATR — pure numpy/pandas, no TA-Lib.
**Formulas:**
- RSI(14): Wilder-smoothed via EWM with alpha=1/14
- MACD(12,26,9): Fast EMA − Slow EMA = MACD line; signal = EMA(9) of MACD line; histogram = MACD − signal
- Bollinger %B = (Close − Lower) / (Upper − Lower) where bands = 20-period SMA ± 2σ
- ATR(14): Wilder-smoothed True Range / Close × 100 = % of price
- Composite score: RSI contribution (±0.5 to ±1.0) + MACD histogram direction (±0.5) + MACD crossover (±0.5) + %B extremes (±0.5), clamped to [−2, +2]

Loads data from `historical.py` cache first, falls back to direct yfinance call.

### `fetchers/macro.py`
**What:** 7 FRED macro series.
**How:** `fredapi` Python client with `FRED_API_KEY`. Fetches last 14 observations per series (for YoY calculation). CPI additionally computes `yoy = (latest − 13_periods_ago) / 13_periods_ago × 100`. INDPRO additionally computes `mom` (month-over-month % change). Returns `stale=True` if key is missing.
**Series:** DGS10 (10Y yield), DCOILWTICO (WTI FRED), CPIAUCSL (CPI), DEXUSEU (EUR/USD), FEDFUNDS, INDPRO, MORTGAGE30US.

### `fetchers/seasonality.py`
**What:** Average monthly % return for Brent (BZ=F) and Henry Hub (NG=F) over 5 years.
**How:** Uses `historical.py`'s `get_seasonality()` helper. Groups daily pct-change returns by (year, month), sums within each month, then averages across years for each month number.

### `fetchers/cracks.py`
**What:** Refinery crack spreads, VLCC proxy, Saudi OSP.
**Crack spreads (live yfinance):**
- 3-2-1 = (2×RBOB_bbl + 1×HO_bbl − 3×WTI) / 3 — most-watched US refining margin
- 5-3-2 = (3×RBOB_bbl + 2×HO_bbl − 5×WTI) / 5
- Gasoline crack = RBOB_bbl − WTI
- Heating oil crack = HO_bbl − WTI
- Brent crack = RBOB_bbl − Brent (European proxy)
- RBOB (RB=F) and HO (HO=F) trade in $/gallon → multiply by 42 to get $/barrel
- Each spread has current value, 1-year average, and signal (WIDE/NORMAL/NARROW vs ±20% of avg)

**VLCC proxy (ESTIMATED badge):** Dubai = Brent × 0.975. Proxy rate = 40 + (Brent−Dubai − 2.0) × 6.0 ($000/day). Baltic Exchange BDTI requires paid subscription; this is directional only.

**Saudi OSP (HARDCODED badge):** Arab Light/Medium/Heavy differentials vs Asia/NWE/USGC benchmarks. Manually updated from Aramco monthly press releases. Last updated May 2026.

### `fetchers/analyst_watch.py`
**What:** Latest posts from Javier Blas, Amena Bakr (via Nitter RSS), and Trump (via Truth Social).
**How (Nitter):** Tries 5 public Nitter instances in order until one returns valid RSS XML. Parses RSS 2.0 and Atom 1.0 format (handles both `<item>` and `<entry>`, both `<pubDate>` and `<updated>/<published>`, both `<link>text</link>` and `<link href="..."/>`). Up to 5 posts per analyst.
**How (Truth Social):** Truth Social blocks unauthenticated API calls (HTTP 403) and serves HTML SPA for all RSS URLs. Returns `ok=False` with a `fallback_note` and `fallback_url`; the frontend shows a "Visit Profile" button instead.

### `fetchers/tanker_watch.py`
**What:** Live tanker counts at 4 oil chokepoints via AIS ship tracking.
**How:**
1. Opens WebSocket to `wss://stream.aisstream.io/v0/stream`
2. Sends subscription with bounding boxes for 4 chokepoints + `FilterMessageTypes: ["PositionReport"]`
3. Collects messages for 12 seconds
4. Filters AIS ship type codes 80-89 (tankers)
5. Assigns vessels to chokepoints by lat/lon containment in bounding boxes
6. Deduplicates by MMSI, counts unique tankers and total vessels

**Risk levels:** Based on tanker count per chokepoint. Hormuz/Bab-el-Mandeb/Suez have elevated baseline (geopolitics).

**Fallback:** If `AISSTREAM_API_KEY` not set, returns `available=False` and the frontend shows the static news-driven Chokepoint panel instead.

**Chokepoints monitored:**
- Strait of Hormuz (bbox: lon 55.5-57.5, lat 22.5-27.5)
- Bab el-Mandeb (lon 42.5-44.0, lat 11.5-13.5)
- Suez Canal (lon 32.0-33.0, lat 29.5-31.5)
- Strait of Malacca (lon 99.0-104.5, lat 1.0-6.5)

---

## 6. Models — Every Model Explained

### `models/fair_value.py`
**What:** Theoretical fair value for Brent or WTI crude.
**Methodology:** Cost-of-carry base + 4 fundamental adjustments:

```
Fair Value = spot × e^((r + c − y) × T)
           + inventory_adjustment
           + opec_adjustment
           + dxy_adjustment
           + geo_premium

Where:
  r = Fed Funds rate (from FRED, 7-day disk cache, fallback 5.3%)
  c = storage cost = 0.6% per annum
  y = convenience yield = 2% base + (−inventory_deviation_pct / 100 × 2%)
      (tight inventory → higher convenience yield → lower carrying cost)
  T = 30/365 (front-month approximation)

Adjustments:
  inventory_adj = −(deviation_pct / 100) × $30
  opec_adj      = (compliance − 1.0) × $7.5
  dxy_adj       = −dxy_deviation_vs_30d × $0.60
  geo_premium   = max(0, (geo_index − 30) × $0.08)
```

**Deviation labels:** EXTREME OVERVALUE (>8%), OVEREXTENDED (4-8%), FAIR (±4%), UNDERVALUED (−4% to −8%), DEEPLY UNDERVALUED (<−8%).

### `models/signal_engine.py`
**What:** Weighted composite directional signal for Brent, WTI, and Henry Hub.
**How:** 9 indicators for crude, 6 for nat gas. Each returns a score in {−2, −1, 0, +1, +2}. Weighted sum gives the composite score.

**Crude weights:**
```
Inventory  28%  | Curve    24%  | COT      19%  | Fair Value 14%
Sentiment   5%  | Technicals 5%| DXY       3%  | IV         2%
Geo Risk    0%  (weight assigned to IV instead — geo alpha decays fast)
```

**Henry Hub weights:**
```
Inventory  30%  | Weather  25%  | Curve    15%  | COT       15%
Fair Value 10%  | Technicals 5%
```

**Conviction:**
- HIGH: agreeing indicators ≥ max(5, n−1)
- MODERATE: agreeing ≥ max(3, n÷2)
- LOW: otherwise

**Signal labels:** STRONG BULLISH (>1.2), MILD BULLISH (>0.4), NEUTRAL (−0.4 to 0.4), MILD BEARISH (<−0.4), STRONG BEARISH (<−1.2)

**History:** Every signal calculation appends to `db/signal_history.py` (500-row rolling SQLite table). The last 24 scores are returned as `history: [...]` — used by frontend sparklines.

### `models/fair_value.py` — already covered above.

### `models/correlations.py`
**What:** 5×5 cross-asset Pearson correlation matrix.
**How:** 90-day daily returns for Brent, WTI, Henry Hub, DXY, S&P 500. Returns matrix plus labels plus `brent_wti_analysis` (beta, spread stats, rolling 30-day correlation series for the spread chart).

### `models/term_structure.py`
**What:** Three things:
1. 5×5 energy product correlation heatmap (Brent/WTI/RBOB/HO/HH at M1)
2. M1-M12 strip enrichment (roll yield, annualised carry, vs-1Y-mean for each contract)
3. Calendar spread matrix (M1-M2 through M11-M12 current values + 11×11 Brent spread Pearson correlation heatmap from 90 days of LCO xlsx data)

### `models/patterns.py`
**What:** Technical pattern recognition using scipy peak/trough detection on Brent 90-day close series.
**Patterns:** Head & Shoulders, Inverse H&S, Double Top, Double Bottom, Bull Flag, Bear Flag, Ascending Triangle, Descending Triangle, Symmetrical Triangle.
**How:** scipy `argrelextrema` finds local peaks and troughs. Pattern-specific geometry checks (head taller than shoulders, second peak within 3% of first, etc.). Historical analogs = top 3 most similar 30-day windows from 5-year history (DTW-like distance on normalised returns).
**Pattern Playbook:** `PATTERN_PLAYBOOK` dict maps each pattern name to {bullish_pct, bearish_pct, median_move_pct, typical_horizon, case_studies[]} drawn from real crude oil history.

### `models/trade_idea.py`
**What:** A structured directional trade recommendation for Brent crude.
**How:**
1. Reads Brent signal score and conviction from signal_engine output
2. Checks if `score > 0.5 AND live_price < fair_value` → LONG; `score < -0.5 AND live_price > fair_value` → SHORT; else NEUTRAL
3. Stop = live_price − 1.5 × ATR (long) or + 1.5 × ATR (short)
4. Target = midpoint between live and fair value
5. Generates 3-bullet entry thesis from top weighted agreeing indicators
6. Tries Ollama llama3 at `http://localhost:11434` for morning brief (120-140 word prose). Falls back to `_rule_based_brief()` (deterministic 5-sentence template using curve structure, inventory, COT, crack spread data).

### `models/alerts.py`
**What:** 4 real-time alert types.
- **PRICE_SHOCK:** Brent session change > 2× ATR (warning) or > 3× ATR (critical)
- **COT_EXTREME:** COT crude percentile >85 (crowded long warning) or <15 (crowded short warning)
- **EIA_SURPRISE:** Current week crude change vs 4-week prior average — surprise >2Mb/d = warning, >4Mb/d = critical
- **IV_SPIKE:** Crude IV percentile >80% = warning, >90% = critical

Each alert has a daily-deduplicated ID (`md5(type:YYYY-MM-DD)`), severity, message string, and timestamp.

### `db/cache.py`
**What:** Thread-safe SQLite TTL cache.
**How:** Thread-local connections (avoids SQLite threading issues). Single table. Write lock via `threading.Lock`. `get_cached()` returns stale data (with `stale=True` merged) rather than raising — this is the key resilience pattern. `set_cache()` uses `INSERT OR REPLACE` (upsert).

---

## 7. All API Endpoints

| Route | TTL | Returns |
|---|---|---|
| `GET /api/health` | — | `{status, timestamp}` |
| `GET /api/prices` | 60s | live OHLCV for 10 assets |
| `GET /api/ohlcv` | 60s | 5-min intraday candles (Brent + WTI) |
| `GET /api/history` | 3600s | 90-day daily OHLCV (Brent + WTI) |
| `GET /api/curve` | 600s | Brent + WTI M1-M12 strip + comparison |
| `GET /api/fair-value` | 600s | `{brent: {fair_value, live_price, deviation_pct, components}, wti: ...}` |
| `GET /api/signal` | 600s | `{brent, wti, henry_hub}` each with `{score, signal, conviction, indicators[], history[]}` |
| `GET /api/correlations` | 7200s | `{matrix, curve, brent_wti}` |
| `GET /api/fundamentals` | 7200s | `{inventory, snapshot, cot, opec, geo_risk, rig_count, seasonality, opec_eia, spark_dark}` |
| `GET /api/news` | 600s | `{articles[], composite_sentiment, clusters, negative_count}` |
| `GET /api/weather` | 3600s | `{hdd_7day, cdd_7day, hdd_deviation_pct, net_demand_signal, cities[]}` |
| `GET /api/technicals` | 300s | `{brent, wti, henry_hub}` each with RSI/MACD/BBands/ATR |
| `GET /api/term-structure` | 3600s | `{correlation_matrix, strips, calendar_spreads}` |
| `GET /api/macro` | 3600s | `{dgs10, cpi, eurusd, fedfunds, indpro, mortgage, stale}` |
| `GET /api/patterns` | 3600s | `{pattern, analogs[], playbook, summary}` |
| `GET /api/iv` | 300s | `{crude_iv, crude_iv_pctile, hh_iv, hh_iv_pctile, signal}` |
| `GET /api/trade-idea` | 600s | `{direction, score, conviction, entry_thesis[], stop_level, target_level, key_risk, morning_brief}` |
| `GET /api/alerts` | 60s | `{alerts[], eia_change, eia_4wk_avg}` |
| `GET /api/cracks` | 600s | `{crack_spreads, vlcc_proxy, saudi_osp}` |
| `GET /api/steo` | 86400s | `{months[], current_supply, current_demand, current_balance}` |
| `GET /api/analyst-watch` | 900s | `{analysts: [{name, posts[], ok, error}]}` |
| `GET /api/tanker-watch` | 300s | `{available, chokepoints: [{name, tankers, vessels, risk_level, tanker_list[]}]}` |
| `GET /api/all` | — | all above in one response |

---

## 8. Frontend Architecture

The entire frontend is a single file: `frontend/index.html` (~138 KB). It uses:
- **Lightweight Charts (LWC)** v4 for the candlestick chart (loaded from CDN)
- **Chart.js** v4 for all canvas-based charts (CDN)
- **TradingView Advanced Chart Widget** (embedded iframes, CDN script)
- **Vanilla JS** — no React, no Vue, no build step
- **IBM Plex Mono** from Google Fonts
- **CSS variables** for the dark terminal colour scheme

### 8.1 Global State Object `S`

All API data is stored in a single global object `S`:
```javascript
const S = {
  prices: null, curve: null, signal: null, fv: null,
  fundamentals: null, news: null, weather: null, technicals: null,
  term_structure: null, macro: null, patterns: null, iv: null,
  cracks: null, history: null, steo: null,
  analyst_watch: null, tanker_watch: null,
  lastUpdate: null
};
```

`fetchAll()` calls `/api/all`, distributes the response into `S`, then calls `updateAll()`.

### 8.2 Polling and Data Flow

```
On load:
  fetchAll()              → every 60s
  fetchTradeIdea()        → every 600s (separate, slow)
  fetchHistory()          → every 3600s (90-day spread chart)
  fetchAnalystWatch()     → every 900s (separate, Nitter RSS)
  fetchTankerWatch()      → every 300s (separate, AIS)
  updateMarketStatus()    → every 60s
  updateStatusBar()       → every 5s

updateAll() calls in sequence:
  updateTopbar()
  updateSignalCards()
  updateFairValue()
  updateMacroPanel()
  updateCandlestickChart()   → LWC redraw
  updateCurveChart()         → Chart.js redraw
  updateSpreadChart()        → canvas redraw
  updateEIA()
  updateCOT()
  updateOPEC()
  updateGeoRisk()
  updateWeather()
  updateRigCount()
  updateSparkDark()
  updateForwardCover()
  updateChokepoints()
  updateTechnicals()
  updateCorrelationMatrix()
  updateNewsPanel()
  updatePatterns()
  updateSeasonality()
  updateTermStructure()
  updateCalendarSpreads()
  updateSTEO()
  updateAnalystWatch()
  updateTankerWatch()
  updateProvenance()         → 100ms delayed
```

### 8.3 Tab System

```javascript
function showTab(id) {
  document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.getElementById(id).classList.add('active');
  // triggers LWC resize if switching to P2
}
```

Tabs: `p1` (Signal), `p2` (Price & Curves), `p3` (Fundamentals), `p4` (Intelligence), `p5` (Term Structure).

Keyboard shortcuts: keys 1-5 switch tabs, R = force refresh, F = fullscreen, `?` = shortcut overlay, Esc = close modals.

---

## 9. Tab Features — Complete Technical Breakdown

### TAB P1 — ▲ SIGNAL

**Signal Cards (Brent / WTI / Henry Hub)**
- Source: `/api/signal` → `S.signal.brent / .wti / .henry_hub`
- Each card shows: score (−2 to +2), signal label, conviction (HIGH/MODERATE/LOW), 24-point SVG sparkline of historical scores
- SVG sparklines: `buildSparkline(data)` draws a 60×20px path. Green fill above zero / red fill below zero using dual `clipPath` regions. Points are `(i/(n-1)×60, 10 − score/2×10)`.
- Conviction badge: HIGH = pulsing green ring CSS animation, MODERATE = static amber dot
- Click-to-expand: opens `#drill-modal` with full indicator breakdown table (name, score bar, weight, reason), IV gauge, key risk. `openDrill(title, html)` builds the HTML dynamically.

**Fair Value Panel**
- Source: `S.fv.brent` and `S.fv.wti`
- Shows: live price vs fair value, deviation %, 5-component breakdown (cost-of-carry base, inventory adj, OPEC adj, DXY adj, geo premium)
- Fair value line also drawn on the candlestick chart as a dashed horizontal line

**Indicator Breakdown (Score Bars)**
- 8 rows per asset, each with: indicator name, score (coloured pill), weight, reason text
- Score bar: 8px height, CSS transition `width: 1.2s ease`, green/red depending on sign

**Macro Signals Panel**
- Source: `S.macro`
- Shows 7 FRED series with value, date, MoM/YoY change

**Key Spreads Dashboard (P1 row 3, full width)**
- Source: `S.cracks`
- Shows: Brent-WTI, M1-M2, WTI M1-M6, 3-2-1 crack, gasoline crack, HO crack as a horizontal spread strip

**Trade Idea Card**
- Source: `/api/trade-idea` (polled separately every 600s)
- Shows: direction badge (LONG=green/SHORT=red/NEUTRAL=amber), live price, stop, target, entry thesis bullets, key risk, time horizon
- Collapsible `<details>` element below holds the morning brief prose (150-word Ollama output or rule-based fallback)

---

### TAB P2 — ◎ PRICE & CURVES

**Candlestick Chart (Lightweight Charts)**
- Library: LWC v4 from CDN, created once as `_lwcChart` global
- Data: `/api/ohlcv` → 5-min Brent or WTI candles
- Toggle: Brent/WTI buttons call `switchAsset()` which re-fetches and redraws
- Overlays (toggle buttons):
  - EMA20: `_calcEMA(closes, 20)` — proper EWM with `k = 2/(n+1) = 2/21`
  - MA50: simple rolling mean of 50 closes
  - VWAP: `_calcVWAP(data)` — cumulative `Σ(TP×Vol)/Σ(Vol)` where `TP = (H+L+C)/3`
  - Each overlay is a separate LWC `addLineSeries()` instance
- Volume: separate histogram series (LWC `addHistogramSeries()`)
- Fair Value line: `addLineSeries()` with dashed style, horizontal price line at `S.fv.brent.fair_value`

**Brent-WTI Spread Chart**
- Source: `S.history` (90-day daily OHLCV, fetched hourly)
- Rendered on `<canvas id="chart-spread">` using Chart.js
- Shows: daily Brent−WTI spread, ±1σ amber band, mean dashed line, cyan area fill below spread line
- `drawSpreadChart()` rebuilds on every `/api/history` refresh and on P2 tab switch

**Futures Curve Chart**
- Source: `S.curve`
- Chart.js line chart on `<canvas id="chart-curve">`: Brent strip (blue) and WTI strip (orange), M1-M12
- Expand button (`⤢`) opens `openChartModal('curve')` which redraws the chart at 95vw×90vh

**TradingView Live Charts (bottom of P2)**
- Two embedded TradingView Advanced Chart widgets: WTI (NYMEX:CL1!) and Brent (NYMEX:BZ1!)
- Script injected dynamically: `embed-widget-advanced-chart.js` from CDN
- Settings: dark theme, 3-month default, EMA/SMA/VWAP studies pre-loaded, `allow_symbol_change: true`
- Each rendered in a dedicated `<div>` at 50% width

---

### TAB P3 — ◈ FUNDAMENTALS

**EIA Inventory Panel**
- Source: `S.fundamentals.snapshot` and `S.fundamentals.inventory`
- 5 series: Crude Stocks, Cushing Stocks, Gasoline, Distillate, Nat Gas Storage
- Each row: current, 5-year avg, deviation (abs + %), label (WELL_ABOVE/ABOVE/NORMAL/BELOW/WELL_BELOW), date
- Alert threshold: EIA crude change vs 4-week average shown prominently

**COT Positioning Panel**
- Source: `S.fundamentals.cot`
- 4 markets: Crude Oil, Nat Gas, Gasoline, Heating Oil
- Each: percentile bar (0-100), label, net contracts, date
- Contrarian interpretation displayed

**OPEC Panel**
- Source: `S.fundamentals.opec_eia`
- 12 OPEC members: name, actual production (Mb/d), prior year, % change
- Total actual shown prominently
- Data source badge: "EIA INTL" live data

**Geo Risk Panel**
- Source: `S.fundamentals.geo_risk`
- 0-100 index, label, primary driver
- 4 component breakdown with sub-scores

**Rig Count**
- Source: `S.fundamentals.rig_count`
- Current US rig count, week-on-week change, date

**Weather Panel**
- Source: `S.weather`
- HDD and CDD 7-day totals vs normal
- % deviation from normal, net demand signal
- Per-city breakdown table

**Spark/Dark Spread Panel**
- Source: `S.fundamentals.spark_dark`
- Spark spread (gas power plant margin), dark spread (coal plant margin)
- Components: electricity price $/MWh, HH price $/MMBtu, heat rate

**Days of Forward Demand Cover**
- Calculated client-side: `crude_stocks / (daily_consumption_estimate)`
- Gauge with 54-day critical threshold marker

**Chokepoint Risk Monitor**
- If `S.tanker_watch.available = true`: shows live AIS tanker counts, risk level badges, tanker name pills
- If `S.tanker_watch.available = false`: shows news-driven risk levels derived from negative headline keyword scan + setup instructions for `AISSTREAM_API_KEY`

**Crack Spreads Panel**
- Source: `S.cracks.crack_spreads`
- Table: 3-2-1, 5-3-2, gasoline, HO, Brent crack — value/1Y avg/vs avg/signal pill

**VLCC Proxy Panel**
- Source: `S.cracks.vlcc_proxy`
- ESTIMATED badge, Brent-Dubai spread, proxy VLCC rate (rough directional only)

**Saudi OSP Panel**
- Source: `S.cracks.saudi_osp`
- HARDCODED badge with date
- Arab Light/Medium/Heavy × Asia/NWE/USGC differentials grid

**EIA STEO Global Oil Balance**
- Source: `S.steo`
- Chart.js combo chart (bar = supply/demand, line = balance)
- 18 months, solid bars = near-term, hatched/lighter = forecast
- Current supply, demand, balance shown as KPIs

---

### TAB P4 — ◆ INTELLIGENCE

**Correlation Matrix**
- Source: `S.correlations.matrix`
- 5×5 grid: Brent / WTI / HH / DXY / SPX
- Each cell: Pearson correlation value, colour-coded (green=positive, red=negative, intensity = |r|)
- Tooltip on hover: `#corr-tooltip` shows asset pair, correlation, strength label, interpretation

**News Panel**
- Source: `S.news`
- Clustered into 4 sections by theme (OPEC+, Supply/Geo, Demand, Macro/Dollar)
- Each article: FinBERT badge (POSITIVE/NEGATIVE/NEUTRAL with confidence %), headline, source, time ago
- Hover: shows description/summary. Click (when URL present): opens article in new tab
- Composite sentiment bar above the list: green/red split showing bullish vs bearish article count

**Pattern Recognition Panel**
- Source: `S.patterns`
- Current detected pattern name + confidence
- Pattern Playbook: historical resolution stats (bullish % / bearish %) as a coloured bar, median move, typical horizon, 2-3 case studies from real crude history
- Top-3 historical analogs: date range, similarity score, what happened next

**Seasonality Panel**
- Source: `S.fundamentals.seasonality`
- Monthly bar chart (Chart.js): avg % return per month for Brent and Henry Hub
- Current month highlighted

**Analyst Watch Panel**
- Source: `S.analyst_watch`
- 3 analyst cards side-by-side: Javier Blas (Bloomberg Opinion), Amena Bakr (Energy Intelligence), Trump (Truth Social)
- Blas + Bakr: up to 5 posts each with timestamp, text (capped at 400 chars), link to original tweet on X.com
- Trump: styled "Visit Profile" button (Truth Social API blocked for unauthenticated users)
- Source badges: "NITTER" (blue-green) or "TRUTH" (red)

---

### TAB P5 — ⬡ TERM STRUCTURE

**5×5 Energy Correlation Heatmap**
- Source: `S.term_structure.correlation_matrix`
- Products: Brent M1, WTI M1, RBOB M1, HO M1, HH M1
- 90-day daily return Pearson correlations
- Same colour scheme as P4 matrix but for energy products

**M1-M12 Strip Table**
- Source: `S.term_structure.strips`
- For each product: M1 through M12 prices, roll yield (M1−M2), annualised carry
- Backwardation cells highlighted green, contango cells highlighted red

**Calendar Spread Matrix (Brent)**
- Source: `S.term_structure.calendar_spreads.brent`
- Row per spread: M1-M2, M2-M3, … M11-M12
- Each cell coloured: green = backwardation (spread > 0.10), red = contango (< −0.10), grey = flat
- 11×11 Brent spread-pair Pearson correlation heatmap below: computed from 90 days of LCO xlsx daily spread series

**Spread Chain**
- A linear display of the M1-M2 through M11-M12 ladder showing how the term structure is shaped through the curve

**5-Product Normalised Curve Chart**
- Chart.js line chart: all 5 products normalised to 100 at M1 to show relative curve shapes side-by-side

---

## 10. UI Infrastructure

**Status Bar (bottom, fixed)**
- `updateStatusBar()` runs every 5 seconds
- Shows: LIVE dot, M1-M2 spread, 3-2-1 crack, Brent-WTI, inventory %, COT %ile, GEO index, last refresh time

**Market Hours Awareness**
- `getMarketStatus()`: OPEN (Mon-Fri 01:00-23:00 UTC, ICE Brent hours) / CLOSED / WEEKEND
- `#mkt-status` chip in topbar
- `.ticker-stale` CSS class dims topbar prices when market is closed/weekend

**Alert Tray**
- `#alert-tray` fixed top-right
- `showAlert(alert)` appends a pill. Non-critical pills auto-dismiss after 8s with a draining CSS animation bar. CRITICAL pills stay until dismissed.

**Data Provenance Labels**
- `updateProvenance()` runs 100ms after every `updateAll()`
- `_PROV_MAP` maps panel CSS selectors → `{source label, timestamp getter fn}`
- Appends/updates a `.prov-label` `<div>` at the bottom of each panel showing source name + "Xm ago"

**Export Report**
- `exportReport()` generates a complete HTML report in a new browser window
- Includes: price grid, signal table, trade idea + morning brief, key fundamentals
- Includes a "⎙ Print / Save as PDF" button

**Fullscreen Chart Mode**
- `#chart-modal` overlay (95vw × 90vh)
- 4 modes: `candle` (new LWC instance), `curve` (Chart.js at modal size), `season` (canvas copy), `multicurve` (new Chart.js)
- Esc closes modal

**Keyboard Shortcut Overlay**
- `?` key toggles `#shortcut-overlay` (glassmorphism panel listing all shortcuts)

---

## 11. Environment Variables

File location: `pulse/.env` (project root)

```
EIA_API_KEY=...          # EIA v2 API — register free at api.eia.gov
APIFY_API_TOKEN=...      # Apify news scraping — free tier at apify.com
FRED_API_KEY=...         # FRED macro — free at fred.stlouisfed.org
NEWSAPI_KEY=...          # fallback news — free at newsapi.org
AISSTREAM_API_KEY=...    # live AIS tanker tracking — free at aisstream.io
```

**Critical note:** The code uses `APIFY_API_TOKEN` (not `APIFY_API_KEY`). Make sure the `.env` key name matches exactly.

`load_dotenv()` is called in `app.py` with no path argument — it loads from whatever directory Flask is started in, which is `pulse/` when launched via `start.py`. Each individual fetcher also calls `load_dotenv()` at module level for standalone testing. `tanker_watch.py` specifically uses `_ROOT / ".env"` (going up two directories from `fetchers/` to `pulse/`).

---

## 12. Database Layer

**`db/cache.py`** — SQLite TTL cache
- DB file: `backend/db/pulse_cache.db` (auto-created)
- Thread-local connections avoid SQLite threading issues
- Write lock: `threading.Lock()` for safe concurrent scheduler writes
- Never raises: all reads/writes are in try/except, failures are logged and ignored

**`db/signal_history.py`** — Signal score history
- Table: `signal_history(asset TEXT, score REAL, conviction TEXT, top_driver TEXT, ts TEXT)`
- 500-row rolling cap per asset (deletes oldest when exceeded)
- `append_history(asset, score, conviction, driver)` — called by signal engine on every calculation
- `get_history(asset, n=24)` — returns last 24 scores as `[float, ...]` for sparklines

---

## 13. Caching Strategy (Two Layers)

**Layer 1: pickle files** (disk, process-level)
- `cache/historical.pkl` — 5-year OHLCV, 24-hour TTL
- `cache/cot.pkl` — CFTC COT 4-year data, 24-hour TTL
- These survive process restarts

**Layer 2: SQLite** (disk, request-level)
- `db/pulse_cache.db` — all API responses
- Every TTL in `app.py` maps to one row in this DB
- Stale data is returned with `stale=True` rather than error
- APScheduler writes to this DB in the background on fixed intervals
- This survives process restarts too — the scheduler repopulates within one TTL interval after startup

---

## 14. Known Quirks and Gotchas

**File truncation:** The `Write` tool silently truncates Python files >~500 lines. Always use `Edit` for targeted changes. Run `python -m py_compile <file>` after every write.

**PowerShell encoding:** PowerShell 5.1 `Get-Content` reads files as Windows-1252. Never use PowerShell to read/write `index.html`. Use the `Read` and `Edit` tools only.

**yfinance per-ticker:** Always use `yf.Ticker(sym).history(...)` not `yf.download([sym1, sym2])`. Batch download causes tz-aware/tz-naive join errors when mixing exchanges (ICE futures vs NYSE).

**LCO xlsx tz-naive:** The xlsx DatetimeIndex is tz-naive. All date comparisons must use `pd.Timestamp.now()` (tz-naive), not `pd.Timestamp.utcnow()` (tz-aware with UTC tzinfo).

**Multiple Flask processes:** If you restart the server without killing all Python processes, old processes keep port 5000. New routes return 404 from the old process. Kill all Python processes before restarting: `Stop-Process -Name python -Force`.

**FinBERT first run:** Downloads ~420MB to `~/.cache/huggingface/`. Wrap in try/except — falls back to 0.0 scores gracefully.

**EIA INTL units:** OPEC production values >100 are in thousand barrels/day (Tb/d). Divide by 1000 to get Mb/d. The code checks `raw_val > 100` as the unit detection heuristic.

**LWC resize on tab switch:** Call `_lwcChart.resize(container.offsetWidth, height)` inside the tab-switch handler (the `else` branch where chart already exists) to fix blank chart when switching back to P2.

**Truth Social:** RSS URLs return HTML SPA. Mastodon API returns HTTP 403 for unauthenticated requests. No free workaround exists. The Trump card shows a "Visit Profile" CTA by design.

**Nitter instances:** Public Nitter instances go offline frequently. The code tries 5 in order. If all fail, the analyst cards show an error state — this is expected occasionally.

**COT data latency:** CFTC releases COT data on Fridays for the prior Tuesday's positioning. There is always a ~3-4 day lag in the data.

---

## 15. React Migration

**Should you migrate?** Yes, and the backend needs zero changes — it's a pure JSON API. The migration is entirely frontend (`index.html` → React app).

**What it gets you:**
- Component-level re-renders (currently `updateAll()` re-renders everything even if only prices changed)
- Proper state management (currently one giant `S` object)
- TypeScript safety for API response shapes
- Cleaner separation between chart initialisation and data updates
- Hot module replacement during development

**Recommended stack:**
- **Vite + React + TypeScript** (fast build, great DX)
- **TanStack Query** for data fetching + cache invalidation (replaces all the `setInterval` polling)
- **Recharts or Visx** for canvas charts (replaces Chart.js)
- Keep **TradingView widgets** as-is (embedded iframes, no change needed)
- Keep **Lightweight Charts** via `lightweight-charts` npm package (already has React adapter)

**Migration approach:** Keep the Flask backend 100% as-is. Create a new `frontend-react/` directory. Port tab by tab — start with P1 (Signal) since it's the most data-rich. The API contract is stable; just fetch from `http://127.0.0.1:5000/api/all` same as before.

**Key components to create:**
```
<Topbar />               prices + market status + alert tray
<SignalCard asset="brent" />   score, sparkline, conviction badge
<FairValuePanel />
<CandlestickChart />     LWC wrapper
<CurveChart />           Recharts line
<SpreadChart />          Recharts area
<EIAPanel />
<COTPanel />
<NewsPanel />            clustered, with FinBERT badges
<CorrelationMatrix />    SVG heatmap
<PatternPanel />
<TermStructurePanel />
<AnalystWatch />
<TankerWatch />
```

**State management:** TanStack Query with a single `useAllData()` hook polling `/api/all` every 60 seconds. Individual endpoints (`/api/trade-idea`, `/api/analyst-watch`, `/api/tanker-watch`) get their own queries with their respective intervals.

**The biggest win from React:** Currently when data arrives, `updateAll()` serially calls 25+ DOM-manipulation functions. In React, only the components whose props actually changed re-render. This will make the UI feel significantly more responsive.

---

## 16. What Each Tab Is Supposed to Tell You

| Tab | Core question answered |
|---|---|
| **P1 Signal** | Should I be long or short Brent/WTI/HH right now, and why? |
| **P2 Price & Curves** | What is the price doing intraday and what does the futures curve look like? |
| **P3 Fundamentals** | What is the physical market doing? (stocks, production, refining, shipping) |
| **P4 Intelligence** | What is the market narrative? (news, positioning, patterns, analyst views) |
| **P5 Term Structure** | How are the forward curves shaped and how do the monthly spreads correlate? |

---

This document covers every file, every algorithm, every data source, every UI panel, and every technical decision in the PULSE codebase. A developer reading this should be able to navigate the codebase cold, understand why each piece exists, and extend or replace any part of it without breaking the others.