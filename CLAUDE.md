# PULSE — Project State File
**Last updated:** 2026-05-29 (Phase 3 + Phase 4 + Phase 5 + Chart Enhancement + Friend-Dashboard Features complete)  
**Project:** Price & Uncertainty Live Signal Engine — Futures First internship dashboard  
**Stack:** Flask 3 · yfinance · pandas/numpy · vanilla JS · IBM Plex Mono UI  
**Run:** `python start.py` from `pulse/` — opens browser at http://127.0.0.1:5000

---

## How to Start a New Session

1. Open a fresh conversation
2. Say: **"Read `CLAUDE.md` in my pulse folder, then implement Command N"**
3. Read this file + only the specific files that command touches
4. One command per session = minimum context overhead

---

## Directory Layout

```
pulse/
├── start.py
├── requirements.txt
├── CLAUDE.md                       ← this file
│
├── backend/
│   ├── app.py                      # Flask API, all routes, TTL cache, warm_cache()
│   ├── data/
│   │   └── LCOSettle.xlsx          # ICE Brent M1-M31 settlements 2016→2026, 2713 rows
│   ├── fetchers/
│   │   ├── prices.py               # BZ=F CL=F NG=F DXY VIX SPX 10Y live quotes
│   │   ├── curve.py                # Brent + WTI futures strip (yfinance)
│   │   ├── historical.py           # 90-day daily OHLCV cache
│   │   ├── eia.py                  # EIA inventory + rig count + OPEC EIA + spark/dark
│   │   ├── cot.py                  # CFTC COT positioning percentile
│   │   ├── opec.py                 # OPEC static compliance fallback (IEA/Platts estimates)
│   │   ├── geo_risk.py             # geo-risk index from spread/VIX/news
│   │   ├── news.py                 # energy news (Apify primary, NewsAPI fallback)
│   │   ├── sentiment.py            # FinBERT batch scorer + recency-weighted aggregate
│   │   ├── weather.py              # Open-Meteo HDD/CDD 7-day, 5 US cities
│   │   ├── technicals.py           # RSI(14) MACD(12,26,9) BBands(20,2σ) ATR(14)
│   │   ├── multi_curve.py          # 5-product M1-M12 strips + M1 history (LCO xlsx)
│   │   ├── seasonality.py          # monthly avg % returns BZ=F+NG=F, 5y yfinance
│   │   └── macro.py                # FRED: DGS10 CPI EURUSD FEDFUNDS INDPRO MORTGAGE30US
│   └── models/
│       ├── fair_value.py           # regression fair value model
│       ├── correlations.py         # Brent/WTI/DXY/SPX/HH correlation matrix
│       ├── signal_engine.py        # weighted composite signal [-2,+2] per asset
│       ├── term_structure.py       # 5x5 corr matrix + strip enrichment
│       └── patterns.py             # scipy peak/trough: H&S IH&S DblTop/Bot Flag Triangle
│
└── frontend/
    └── index.html                  # single-file dashboard (~138KB)
```

---

## API Endpoints

| Route | TTL | Key data |
|---|---|---|
| GET /api/health | — | liveness |
| GET /api/prices | 60s | live quotes |
| GET /api/ohlcv | 60s | 5-min candles |
| GET /api/history | 3600s | 90-day daily OHLCV |
| GET /api/curve | 600s | Brent + WTI strip |
| GET /api/fair-value | 600s | fair value model |
| GET /api/signal | 600s | composite signal all assets |
| GET /api/correlations | 7200s | cross-asset correlation matrix |
| GET /api/fundamentals | 7200s | inventory + COT + OPEC + geo + rig + spark/dark + seasonality |
| GET /api/news | 600s | headlines + FinBERT scores + composite_sentiment |
| GET /api/weather | 3600s | HDD/CDD 7-day outlook vs normals |
| GET /api/technicals | 300s | RSI/MACD/BBands/ATR Brent/WTI/HH |
| GET /api/term-structure | 3600s | 5x5 corr matrix + M1-M12 strips |
| GET /api/macro | 3600s | FRED macro indicators (stale:true if no key) |
| GET /api/patterns | 3600s | pattern + top-3 historical analogs |
| GET /api/all | — | all above in one call |

---

## Frontend Tabs

| Tab | Label | Key panels |
|---|---|---|
| p1 | ▲ SIGNAL | Brent/WTI/HH signal cards, fair value, indicator breakdown, macro panel |
| p2 | ◎ PRICE & CURVES | LWC candlestick (Brent/WTI toggle, volume, SMA20, FV line), futures curve chart |
| p3 | ◈ FUNDAMENTALS | EIA inventory, COT, OPEC (EIA live), geo risk, rig count, weather, spark/dark |
| p4 | ◆ INTELLIGENCE | Correlation matrix, news (FinBERT badges + sentiment bar), patterns + analogs, seasonality |
| p5 | ⬡ TERM STRUCTURE | 5x5 energy heatmap, M1-M12 strip table, spread chain, 5-product normalized curve chart |

---

## Signal Engine Weights

**Crude (Brent/WTI):**
```
inventory 30% | curve 25% | cot 20% | fair_value 15% | technicals 5% | dxy 3% | geo 2%
```
**Nat Gas (Henry Hub):**
```
inventory 30% | weather 25% | curve 15% | cot 15% | fair_value 10% | technicals 5%
```
Score: **-2.0 (strong sell) → +2.0 (strong buy)**  
Conviction: HIGH if agreeing >= max(5, n-1) | MODERATE if >= max(3, n//2)

---

## Key Data Sources

| Source | What | Auth |
|---|---|---|
| yfinance | Prices, OHLCV, strips | None |
| ICE LCO xlsx | Brent M1-M31 settlements | `backend/data/LCOSettle.xlsx` |
| EIA API | Inventory + OPEC INTL + electricity price | `EIA_API_KEY` in `.env` |
| CFTC | COT positioning | None (public) |
| Open-Meteo | 7-day weather | None |
| Apify | Energy news scraping | `APIFY_API_TOKEN` in `.env` |
| FRED | Macro indicators | `FRED_API_KEY` in `.env` (optional) |
| HuggingFace | FinBERT sentiment (ProsusAI/finbert) | None (~420MB cached to ~/.cache/huggingface) |

**LCO xlsx:** Row1=contract names (LCOc1…LCOc31), Row2=(Timestamp,SETTLE) headers, Row3+=data newest-first. SETTLE for Mi = `row[1+(i-1)*2]`, Date=`row[0]`.

---

## Environment Variables (`backend/.env`)

```
EIA_API_KEY=...         # EIA v2 API — register free at api.eia.gov
APIFY_API_TOKEN=...     # news scraping — free tier at apify.com
FRED_API_KEY=...        # macro data — free at fred.stlouisfed.org
NEWSAPI_KEY=...         # fallback news — free at newsapi.org
```

---

## Completion Status

### ✅ Commands 1-10 — DONE

| What | Key files |
|---|---|
| Foundation, project structure, start.py | `start.py`, `requirements.txt` |
| Prices, OHLCV, curve, history, fair value, signal, correlations | `fetchers/prices.py`, `fetchers/curve.py`, `models/` |
| EIA inventory + seasonal deviation + rig count | `fetchers/eia.py` |
| COT positioning percentile | `fetchers/cot.py` |
| OPEC static compliance table + EIA INTL live production | `fetchers/opec.py`, `fetchers/eia.py` |
| Geo risk index | `fetchers/geo_risk.py` |
| Weather HDD/CDD 5 cities | `fetchers/weather.py` |
| Technicals RSI/MACD/BBands/ATR | `fetchers/technicals.py` |
| Multi-curve LCO xlsx + yfinance dated tickers | `fetchers/multi_curve.py` |
| Term structure 5x5 corr + strip enrichment | `models/term_structure.py` |
| Seasonality monthly avg returns + bias label | `fetchers/seasonality.py` |
| FRED macro fetcher (7 series, MoM for INDPRO, YoY for CPI) | `fetchers/macro.py` |
| Pattern recognition (scipy): H&S IH&S DblTop/Bot BullBearFlag Triangles + analogs | `models/patterns.py` |
| LWC candlestick + volume histogram + SMA20 + Brent/WTI toggle | `frontend/index.html` |
| FinBERT news sentiment (batch, recency-weighted aggregate) | `fetchers/sentiment.py`, `fetchers/news.py` |
| EIA INTL OPEC production + EIA electricity spark/dark spread | `fetchers/eia.py`, `app.py`, `index.html` |
| 5-product normalized forward curve chart (Chart.js, p5) | `frontend/index.html` |

### ✅ Commands 1-15 — ALL DONE

| What | Key files |
|---|---|
| *(Commands 1-11 as above)* | |
| Rule-based trade idea (direction, thesis, stop, target, horizon, key risk) | `models/trade_idea.py` |
| Ollama llama3 morning brief with rule-based fallback (ConnectionError safe) | `models/trade_idea.py` — `_ollama_brief()` |
| `/api/trade-idea` route + TTL_TRADE=600 + background warm-up | `backend/app.py` |
| Trade idea card in p1 row 3 (full width, direction badge + levels + thesis) | `frontend/index.html` — `updateTradeIdea()` |
| `<details>` collapsible morning brief below trade card | `frontend/index.html` |
| Static Morning Brief panel replaced; Macro Signals promoted to row 2 panel | `frontend/index.html` |
| `fetchTradeIdea()` polled every 600s independently of `/api/all` | `frontend/index.html` |
| SQLite-backed TTL cache (drop-in, stale=True on expired reads) | `backend/db/__init__.py`, `backend/db/cache.py` |
| APScheduler BackgroundScheduler replaces manual warm threads | `backend/app.py` — `_scheduler`, `_refresh_*` jobs |
| Slow jobs (news/macro/patterns/iv/trade) fire immediately at scheduler start | `backend/app.py` — `next_run_time=_NOW` |
| Alert system (PRICE_SHOCK, COT_EXTREME, EIA_SURPRISE, IV_SPIKE) | `backend/models/alerts.py` |
| `/api/alerts` route + TTL_ALERTS=60 + APScheduler job | `backend/app.py` |
| `get_cached` nocache bypass via Flask request context (`?nocache=1`) | `backend/app.py` — `get_cached()` wrapper |
| Alert tray (fixed top-right, pills auto-dismiss 8s, critical stays) | `frontend/index.html` — `showAlert()`, `#alert-tray` |
| Keyboard shortcuts: 1-5 tabs, R=force refresh, F=fullscreen, Esc=exit | `frontend/index.html` — `keydown` listener |
| EIA crude actual + surprise wired to live data (vs 4wk avg) | `frontend/index.html` — `updateEIA()` |
| Signal history SQLite table (500-row cap, per-asset score log) | `backend/db/signal_history.py` |
| `calculate_signal()` appends to history; returns `history: [24 scores]` | `backend/models/signal_engine.py` |
| SVG sparklines (60×20px, green above 0 / red below 0, dual clipPath) | `frontend/index.html` — `buildSparkline()` |
| All ⊘/DEMO badges removed from frontend | `frontend/index.html` |
| All backend modules pass `py_compile` | `backend/**/*.py` |
| `requirements.txt` pinned to exact pip freeze versions (2026-05-28) | `requirements.txt` |

---

## Chart Enhancement Pass (2026-05-29)

### EMA20 / MA50 / VWAP Overlays
| What | Where | Detail |
|---|---|---|
| `_calcEMA(data, period)` | `index.html` | Exponential MA — proper EMA formula with seed from SMA |
| `_calcVWAP(data)` | `index.html` | Session VWAP = cumSum(TP×Vol)/cumSum(Vol), TP=(H+L+C)/3 |
| `toggleOverlay(key)` | `index.html` | Toggle EMA20/MA50/VWAP visibility; dims button to 35% opacity when off |
| `_lwcEma20Series` / `_lwcMa50Series` / `_lwcVwapSeries` | `index.html` | Three new LWC line series: cyan/purple/orange |
| EMA20/MA50/VWAP toggle buttons | `index.html` candlestick header | `.ov-btn` class; next to WTI/Brent toggle; color-coded |
| Legend updated | `index.html` | Added EMA20 (cyan), MA50 (purple), VWAP (dashed orange) swatch rows |

### Brent-WTI Historical Spread Chart
| What | Where | Detail |
|---|---|---|
| `fetchHistory()` | `index.html` | Fetches `/api/history` (90-day daily OHLCV); 1h interval; sets `S.history` |
| `drawSpreadChart()` | `index.html` | Canvas chart: 90-day Brent−WTI spread, ±1σ amber band, mean dashed line, cyan area fill |
| `<canvas id="chart-spread">` | `index.html` Brent-WTI panel | Added above interpretation box; redraws on P2 tab switch |
| Startup call | `index.html` | `fetchHistory()` on load; `setInterval(fetchHistory, 3600000)` |

### TradingView Live Charts Panel
| What | Where | Detail |
|---|---|---|
| TradingView panel (grid-column:1/3) | `index.html` P2 bottom | Two side-by-side Advanced Chart widgets: WTI (NYMEX:CL1!) + Brent (NYMEX:BZ1!) |
| EMA/SMA/VWAP built-in | TradingView | Studies: `["STD;EMA","STD;SMA","STD;VWAP"]` — real-time CFD data |
| Dark theme, 3M default, symbol changeable | TradingView | `theme:"dark"`, `withdateranges:true`, `allow_symbol_change:true` |
| embed-widget-advanced-chart.js | CDN | Async-loaded; creates isolated iframes; no JS conflict with LWC/Chart.js |

## All Commands Complete

---

## Friend-Dashboard Feature Pass (2026-05-29)

### Features Implemented
| Feature | Files | Detail |
|---|---|---|
| EMA20 / MA50 / VWAP overlays | `index.html` | Toggle buttons on candlestick; EMA (proper k=2/(n+1)), VWAP cumulative; cyan/purple/orange LWC series |
| Brent-WTI 90-day spread chart | `index.html` | Canvas: ±1σ amber band, cyan area fill, date labels; `fetchHistory()` hourly |
| TradingView live widgets | `index.html` | P2 bottom: WTI (NYMEX:CL1!) + Brent (NYMEX:BZ1!), dark theme, 3M, EMA/SMA/VWAP studies |
| EIA STEO Global Oil Balance | `fetchers/eia.py`, `app.py`, `index.html` | `/api/steo` TTL=24h; Chart.js combo bar/line chart; supply/demand/balance; near-term vs forecast bars |
| Calendar Spread Matrix | `models/term_structure.py`, `index.html` | M1-M2…M11-M12 ladder for Brent+WTI; green=backwardation, red=contango; 11×11 Brent spread correlation heatmap from LCO xlsx 90-day history |
| Analyst Watch (Nitter RSS) | `fetchers/analyst_watch.py`, `app.py`, `index.html` | `/api/analyst-watch` TTL=15min; Javier Blas + Amena Bakr via Nitter (multiple instance fallback); Trump → Truth Social CTA (API blocked) |
| Tanker Watch (AIS) | `fetchers/tanker_watch.py`, `app.py`, `index.html` | `/api/tanker-watch` TTL=5min; aisstream.io WebSocket; Hormuz/Bab-el-Mandeb/Suez/Malacca; fallback to news-driven Chokepoint panel + setup instructions when key missing |

### Bug Fixes
| Bug | File | Fix |
|---|---|---|
| `get_brent_m1_history` tz mismatch | `fetchers/multi_curve.py` | `pd.Timestamp.utcnow()` → `pd.Timestamp.now()` (tz-naive to match LCO df.index) |
| Multiple Flask processes blocking routes | — | Documented: always kill ALL python processes before restart |

### New Env Variable
```
AISSTREAM_API_KEY=...   # live AIS tanker tracking — free at aisstream.io
```

### New API Endpoints
| Route | TTL | Key data |
|---|---|---|
| GET /api/steo | 86400s | EIA STEO global supply/demand/balance (18 months) |
| GET /api/analyst-watch | 900s | Javier Blas + Amena Bakr tweets (Nitter RSS) + Trump profile link |
| GET /api/tanker-watch | 300s | Live AIS: tanker counts near Hormuz/Suez/Bab-el-Mandeb/Malacca |

---

## Phase 3 — Analytical Features (2026-05-28)

### New Backend
| What | File | Notes |
|---|---|---|
| Crack spread fetcher | `fetchers/cracks.py` | Live yfinance — 3-2-1, 5-3-2, gasoline, HO, Brent crack vs 1Y avg |
| VLCC freight proxy | `fetchers/cracks.py` | Dubai est. = Brent×0.975; rate proxy heuristic; **ESTIMATED** badge |
| Saudi OSP | `fetchers/cracks.py` | Hardcoded May 2026 Aramco differentials; **HARDCODED** badge |
| `/api/cracks` route | `app.py` | TTL_CRACKS=600s; APScheduler job fires immediately on start |
| `/api/all` updated | `app.py` | `cracks` key now included |

### New Frontend
| What | Where | Notes |
|---|---|---|
| Key Spreads dashboard | p1 row 3 (full-width) | Brent-WTI, M1-M2, WTI M1-M6, 3-2-1 crack, gas crack, HO crack |
| Crack Spreads panel | p3 (2-col) | Live table: value/1Y avg/vs avg/signal pill per spread |
| VLCC Proxy panel | p3 (1-col) | **ESTIMATED** badge, rate proxy gauge, Brent-Dubai components |
| Saudi OSP panel | p3 (2-col) | **HARDCODED** badge + date, Arab Light/Med/Heavy × Asia/NWE/USGC |
| CSS additions | `index.html` | `.crack-row`, `.sig-pill`, `.badge-est`, `.badge-hc`, `.spread-dash` etc. |

### Phase 3C / 3D
Already complete (Forward Demand Cover gauge + Chokepoint Risk Monitor — both in p3).

### Free Data Research (confirmed)
- **VLCC / BDTI**: No free API. Baltic Exchange = paid ($500+/mo). Proxy: Brent-Dubai spread (estimated).
- **Saudi OSP**: Aramco = no machine-readable API. Manually sourced from public monthly press releases. Hardcoded with badge.
- **Crack spreads**: RBOB (RB=F) + Heating Oil (HO=F) on yfinance — fully live, no key required.

---

## Post-Command Polish Pass (2026-05-28)

### Bug Fixes
| Bug | File | Fix |
|---|---|---|
| `APIFY_API_KEY` → `APIFY_API_TOKEN` | `fetchers/news.py:246` | 1-line fix — Apify now works |
| Duplicate `const crackEl` (SyntaxError) | `frontend/index.html` | Removed dead first declaration |
| IV history resets on restart | `fetchers/options_iv.py` | Replaced in-memory deque with SQLite iv_history table |
| `transformers` not in requirements | `requirements.txt` | Uncommented, FinBERT now installable |

### Frontend Enhancements
- **Deep panel shadows** — `box-shadow` system on all `.panel` and `.sig-card` with hover lift
- **Signal card glow** — `text-shadow` on `.sig-verdict` by bull/bear/neut class
- **Body background** — radial gradient + scan-line texture overlay (terminal feel)
- **Price flash animation** — `flash-up`/`flash-dn` keyframes triggered on every topbar price update
- **Tab transitions** — fade + translateY(6px) → 0 on tab switch (220ms ease)
- **Count-up animation** — `animateNum()` utility (ease-out cubic, 350ms) for animated numbers
- **Conviction badges** — pulsing green ring for HIGH, static amber dot for MODERATE in signal cards
- **Status bar** — fixed 26px bottom bar: LIVE dot, M1-M2 spread, crack spread, BRT-WTI, INV %, COT %ile, GEO index, last refresh time
- **Keyboard shortcut overlay** — `?` key toggles full-screen shortcut guide (glassmorphism panel)
- **News item hover** — subtle background transition on hover
- **Stat/spread card hover** — background darkens on hover
- **Improved score bar** — 8px height, rounded, animated width transition (1.2s ease)

### New Panels
- **Days of Forward Demand Cover** (p3) — gauge with 54-day critical threshold marker, color-coded
- **Chokepoint Risk Monitor** (p3) — Hormuz/Bab el-Mandeb/Suez/Malacca with news-driven risk levels

### Architecture
- `options_iv.py` — `iv_history` SQLite table (30-row rolling window, survives restart)
- `options_iv.py` — `reliable: bool` flag (True when ≥10 observations accumulated)
- `updateStatusBar()` — periodic 5s updater for the status bar
- `updateForwardCover()` — EIA crude stocks → days of cover calculation
- `updateChokepoints()` — keyword scan of recent headlines → risk level per chokepoint

---

## Phase 1 + Phase 2 Pass (2026-05-28)

### Phase 1 — All 4 bug fixes complete
| Fix | File | Detail |
|---|---|---|
| 1A. Apify env var | `fetchers/news.py:246` | `APIFY_API_KEY` → `APIFY_API_TOKEN` |
| 1B. transformers | `requirements.txt` | Uncommented; FinBERT 5.9.0 installed |
| 1C. IV SQLite persistence | `fetchers/options_iv.py` | Rolling 30-row `iv_history` table replaces in-memory deque |
| 1D. Live OPEC → fair value | `fetchers/opec.py` | `get_opec_production()` tries EIA INTL live data first, falls back to static estimates |

### yfinance tz-fix pass
| File | Fix |
|---|---|
| `fetchers/prices.py` | Replaced batch `yf.download()` with per-ticker `Ticker.history()` — 10/10 assets now live |
| `fetchers/curve.py` | Rewrote `fetch_curve()` — Brent from ICE LCO xlsx (M1-M12), WTI M1 live + basis-adjusted M2-M12 |
| `fetchers/multi_curve.py` | Fixed ticker format (`=F` suffix), M1 uses continuous contract, `Ticker.history()` throughout |
| `fetchers/historical.py` | Per-ticker `Ticker.history()` replaces batch download in `_download()` |
| `fetchers/technicals.py` | `Ticker.history()` in fallback path |

### Phase 2 — All frontend items complete
| Item | Detail |
|---|---|
| Loading skeletons | `initSkeletons()` — shimmer placeholders for news list (5 rows) + correlation grid (25 cells) before first data load |
| Click-to-expand overlays | `#drill-modal` + `openDrill(title, html)` / `closeDrill()` — signal cards clickable; shows full indicator breakdown, IV gauge, key risk |
| Correlation matrix tooltip | `#corr-tooltip` floating div; mousemove delegation on `.corr-cell[data-a]`; shows asset pair, correlation value, strength label, brief interpretation |
| News: hover description + click URL | `updateNewsPanel()` — adds `.news-link` class + `onclick=window.open(url)` when URL present; `.news-desc` shown on `:hover` |
| Alert countdown drain | `.alert-drain` — absolute 2px bar at pill bottom, `drain-bar` keyframe depletes left→0 over 8s; smooth `alert-out` on dismiss |
| Escape closes drill modal | Keyboard handler updated |

---

## Known Patterns / Gotchas

**File truncation:** The Write tool silently truncates Python files >~500 lines. Always use `Edit` for targeted changes. Run `python -m py_compile <file>` after every write.

**PowerShell encoding hazard:** PowerShell 5.1 `Get-Content` reads files as Windows-1252 by default. `Set-Content -Encoding utf8` adds a BOM. Both corrupt multi-byte UTF-8 characters in index.html. **Never use PowerShell to read/write index.html.** Use the `Read` and `Edit` tools exclusively.

**sys.path:** Both `backend/` and project root must be on `sys.path`. `app.py` inserts both `_BACKEND` and `_ROOT`. All fetchers do the same.

**yfinance multi-level columns:** After `yf.download()`, flatten: `if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)`.

**LCO xlsx:** Real xlsx saved as .csv. Already copied to `backend/data/LCOSettle.xlsx`. Open with openpyxl directly.

**FinBERT first run:** Downloads ~420MB to `~/.cache/huggingface/` on first call. Subsequent calls use cache. Wrap pipeline init in try/except — falls back to 0.0 scores gracefully.

**EIA INTL unit:** Production values >100 are in thousand barrels/day (Tb/d). Divide by 1000 to get Mb/d. Check `unit` field or value magnitude.

**LWC chart resize:** Call `_lwcChart.resize(container.offsetWidth, height)` inside the `else` branch (chart already exists) to handle tab-switch redraws.

**APScheduler (Command 13):** Use `BackgroundScheduler` not `BlockingScheduler`. Set `daemon=True` on the scheduler thread. Import `from apscheduler.schedulers.background import BackgroundScheduler`.

---

## Phase 4 — AI Enhancement (2026-05-28)

### 4A — Real-time Narrative Generation
| What | File | Detail |
|---|---|---|
| `_rule_based_brief(ctx)` | `models/trade_idea.py` | 5-sentence analyst brief: curve structure, inventory, COT, cracks, bias |
| Enhanced `_ollama_brief(ctx)` | `models/trade_idea.py` | Richer prompt with M1-M2, crack spread, inventory %; 80-word sanity check; falls back to rule-based |
| `generate_trade_idea()` extended | `models/trade_idea.py` | Adds `cracks=None` param; extracts `m1m2_spread`, `curve_struct`, `inv_pct`, `crack_321`, `crack_avg`, `crack_signal` into `brief_ctx` |
| `_trade_idea()` wired | `app.py` | Passes `cracks=_fetch_cracks()` to `generate_trade_idea()` |

### 4B — News Clustering
| What | File | Detail |
|---|---|---|
| `_CLUSTER_KEYWORDS` | `fetchers/news.py` | 4 themes × ~24 keywords each: OPEC+, Supply/Geo, Demand, Macro/Dollar |
| `_cluster_articles()` | `fetchers/news.py` | Score articles against each theme; assign to highest; returns `{theme: [articles]}` |
| `clusters` key | `fetchers/news.py` | Added to `get_energy_news()` return dict |
| CSS cluster headers | `frontend/index.html` | `.news-cluster-hdr`, `.cluster-dot`, `.cluster-lbl`, colour-coded by theme |
| `updateNewsPanel()` | `frontend/index.html` | Renders clustered sections (max 3/theme) with section headers; flat fallback |

### 4C — Pattern Playbook
| What | File | Detail |
|---|---|---|
| `PATTERN_PLAYBOOK` dict | `models/patterns.py` | 12 patterns × {bias, description, bullish_pct, bearish_pct, median_move_pct, typical_horizon, case_studies[]} |
| Case studies | `models/patterns.py` | 2-3 per pattern from real crude oil history (2008, 2014, 2016, 2020, 2022, 2023) |
| `playbook` key | `models/patterns.py` | Added to `get_patterns()` return dict; `None` if pattern not in playbook |
| CSS playbook | `frontend/index.html` | `.playbook-box`, `.playbook-res-bar`, `.playbook-case`, `.playbook-case-detail`, etc. |
| `updatePatterns()` | `frontend/index.html` | Renders resolution stats bar (bull%/bear%), median move, horizon, case studies |
| `#pat-playbook` container | `frontend/index.html` | Inserted between `pat-detail` and `pattern-list` |

---

## Phase 5 — Professional Polish (2026-05-28)

### 5A — Data Provenance Labels
| What | Where | Detail |
|---|---|---|
| `.prov-label` CSS | `index.html` | `prov-dot` (colour-coded), `prov-src`, `prov-age` — 7.5px mono footer on each panel |
| `_PROV_MAP` | `index.html` | 15-entry map: panel CSS selector → {source label, timestamp getter fn} |
| `_agoStr(isoTs)` | `index.html` | Converts ISO timestamp to "Xm ago" / "Xh ago" / "just now" |
| `updateProvenance()` | `index.html` | Appends/updates `.prov-label` divs programmatically; no HTML changes to panels needed |
| Wired into `updateAll` | `index.html` | Patched via `_origUpdateAll` wrapper; fires 100ms after every update |

### 5B — Export / Share
| What | Where | Detail |
|---|---|---|
| `#export-btn` | `index.html` topbar | `📊 EXPORT` button; hover: gold tint |
| `exportReport()` | `index.html` | Generates full-fidelity HTML report in new window: prices grid, signal table, trade idea + morning brief, key fundamentals; includes "⎙ Print / Save as PDF" button |
| `@media print` CSS | `index.html` | Hides dashboard UI when printing; shows only `#print-report` wrapper |

### 5C — Fullscreen Chart Mode
| What | Where | Detail |
|---|---|---|
| `#chart-modal` overlay | `index.html` | 95vw × 90vh backdrop blur modal; `⤢` expand buttons on 4 chart panel headers |
| `openChartModal(type)` | `index.html` | 4 modes: `candle` (new LWC chart), `curve` (canvas redraw), `season` (canvas copy/redraw), `multicurve` (new Chart.js instance) |
| `closeChartModal()` | `index.html` | Destroys LWC instance, clears body, hides modal |
| `_drawCurveOnCanvas(canvas)` | `index.html` | Shared curve drawing logic at arbitrary canvas size |
| `_drawSeasonOnCanvas(canvas)` | `index.html` | Copies seasonality canvas or shows placeholder |
| `drawMultiCurveChartOn(canvas)` | `index.html` | Creates new Chart.js multi-curve at modal size |
| Esc key updated | `index.html` | Now also calls `closeChartModal()` |

### 5D — Market Hours Awareness
| What | Where | Detail |
|---|---|---|
| `#mkt-status` chip | `index.html` topbar | `● OPEN` (green) / `● CLOSED` (amber) / `● WEEKEND` (red) |
| `getMarketStatus()` | `index.html` | Returns OPEN/CLOSED/WEEKEND based on UTC day + ICE Brent hours (01:00–23:00 UTC Mon-Fri) |
| `updateMarketStatus()` | `index.html` | Updates chip class/text; adds `.ticker-stale` to dim topbar prices when closed/weekend; shows `● WEEKEND` stale dot |
| `.ticker-stale` CSS | `index.html` | `t-price` dims to `var(--white3)`; `t-chg` drops to 45% opacity |
| Runs on load + 60s interval | `index.html` | `updateMarketStatus()` called immediately + `setInterval(60000)` |
