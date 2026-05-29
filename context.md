# PULSE — Session Context
**Last updated:** 2026-05-28  
**Session coverage:** Commands 4, 5, 6

---

## What Has Been Implemented (Commands 1–6)

### ✅ P0 — Foundation
- `start.py` launcher with health-poll before browser open  
- `backend/` + `frontend/` split, `.gitignore`, `requirements.txt`  
- All import `sys.path` wiring (`_BACKEND`, `_ROOT` in every module)

### ✅ P1 — Data Layer
- `fetchers/weather.py` — Open-Meteo HDD/CDD, 5 US cities vs NOAA normals  
- `fetchers/technicals.py` — RSI(14), MACD(12,26,9), BBands(20,2σ), ATR(14)  
- `fetchers/multi_curve.py` — LCO xlsx loader + yfinance dated tickers (CLM26 etc.)  
- `models/term_structure.py` — 5×5 cross-product corr matrix + strip enrichment  
- Signal engine rewritten with asset-specific weight tables  
- `/api/weather`, `/api/technicals`, `/api/term-structure` endpoints  
- ⬡ TERM STRUCTURE tab (p5) in frontend

### ✅ P3 — EIA Seasonality + Rig Count
- `fetchers/seasonality.py` — 5y yfinance monthly avg % returns, bias labels  
- Baker Hughes Rig Count panel live in p3  
- `drawSeasonChart()` reads live `S.fundamentals.seasonality`  

### ✅ Command 4 — FRED Macro Fetcher (2026-05-28)
- **Created:** `backend/fetchers/macro.py`  
  - Series: DGS10 (10Y yield), DCOILWTICO (WTI spot), CPIAUCSL (CPI + YoY), DEXUSEU (EUR/USD)  
  - Stale-value fallback when `FRED_API_KEY` not set  
- **Created:** `.env.example` documenting all optional keys  
- **Modified:** `backend/app.py` — `TTL_MACRO=3600`, `/api/macro`, included in `/api/all`, background warm thread  
- **Modified:** `requirements.txt` — uncommented `fredapi>=0.5`  
- **Modified:** `frontend/index.html` — CPI YoY + EUR/USD rows in p1 Macro Signals panel; `updateMacroFRED()` wired into `updateAll()`  
- **Live sample:** DGS10=4.50%, CPI YoY=3.95%, EUR/USD=1.1603

### ✅ Command 5 — Pattern Recognition (2026-05-28)
- **Created:** `backend/models/patterns.py`  
  - `scipy.signal.find_peaks` on 90-day Brent close → peaks + troughs  
  - Classifies: Double Bottom, Double Top, HH/HL, LH/LL, Ranging  
  - 20-day normalised fingerprint slid across 5-year history → top-3 cosine-similarity analogs with 8-week forward returns  
  - Similarity threshold 0.55; non-overlapping deduplication  
- **Modified:** `backend/app.py` — `TTL_PATTERNS=3600`, `/api/patterns`, in `/api/all`, background warm thread  
- **Modified:** `frontend/index.html` — hardcoded pattern cards replaced with live `updatePatterns()`; condition badges from `S.fundamentals`/`S.curve`  
- **Live sample (2026-05-28):** DOUBLE BOTTOM 86% conf; 2/3 analogs bearish (Q1 2023 −7.7%, Q3 2025 −3.6%, Q4 2024 +6.4%)

### ✅ Command 6 — TradingView Lightweight Charts + Weather Panel (2026-05-28)
**Sub-task A — Candle chart migration:**
- Added LWC CDN to `<head>`: `https://unpkg.com/lightweight-charts/dist/lightweight-charts.standalone.production.js`  
- Replaced `<canvas id="chart-candle">` with `<div id="chart-candle" style="height:160px;">`  
- Rewrote `drawCandleChart()` — creates LWC chart once, calls `resize()` + `setData()` on updates  
- Fair-value price line via `series.createPriceLine()` (dashed gold)  
- Graceful fallback text if CDN fails to load  
- Curve chart and seasonality chart remain on Canvas 2D (not changed)  

**Sub-task B — Weather panel HTML:**
- Added `<div class="panel" style="grid-column:2/4;">` to p3 (spans cols 2-3 beside P&L)  
- All 10 `wx-*` element IDs wired: `wx-hdd`, `wx-hdd-norm`, `wx-cdd`, `wx-cdd-norm`, `wx-hdd-dev`, `wx-cdd-dev`, `wx-season`, `wx-summary`, `wx-net`, `wx-city-tbody`  
- `updateWeather()` was already complete; now it has targets to render into  

---

## Current API Endpoints

| Route | TTL | Description |
|---|---|---|
| GET /api/health | — | liveness |
| GET /api/prices | 60s | live quotes (yfinance) |
| GET /api/ohlcv | 60s | intraday 5-min candles |
| GET /api/history | 3600s | 90-day daily OHLCV |
| GET /api/curve | 600s | Brent + WTI strip |
| GET /api/fair-value | 600s | regression fair value |
| GET /api/signal | 600s | composite signal all assets |
| GET /api/correlations | 7200s | cross-asset correlation matrix |
| GET /api/fundamentals | 7200s | EIA + COT + OPEC + geo_risk + rig_count + seasonality |
| GET /api/news | 600s | energy news (Apify) |
| GET /api/weather | 3600s | HDD/CDD 7-day outlook |
| GET /api/technicals | 300s | RSI/MACD/BBands/ATR |
| GET /api/term-structure | 3600s | 5×5 corr + M1-M12 strips |
| GET /api/macro | 3600s | FRED: DGS10, CPI, EUR/USD, WTI spot |
| GET /api/patterns | 3600s | scipy pattern + 3 historical analogs |
| GET /api/all | — | all of the above combined |

---

## Key Files Modified in This Session

```
backend/
  fetchers/
    macro.py          ← NEW  (Command 4)
  models/
    patterns.py       ← NEW  (Command 5)
  app.py             ← TTL_MACRO, TTL_PATTERNS, /api/macro, /api/patterns, warm threads

frontend/
  index.html         ← LWC CDN, chart-candle div, drawCandleChart() LWC, wx-* panel,
                        updateMacroFRED(), updatePatterns(), S.macro, S.patterns

.env.example         ← NEW  (Command 4)
requirements.txt     ← fredapi uncommented
```

---

## Environment Variables (pulse/.env)
```
EIA_API_KEY=...
FRED_API_KEY=...      ← used by Command 4 (/api/macro)
NEWSAPI_KEY=...
BLS_API_KEY=...
APIFY_API_KEY=...     ← note: env uses APIFY_API_KEY, not APIFY_API_TOKEN
```

---

## Commands Still Pending (7–12)

| Cmd | Description | Key files |
|---|---|---|
| 7 | Multi-product forward curve chart in p5 | `frontend/index.html` (Chart.js in p5) |
| 8 | Options chain IV fetcher + IV gauge | `fetchers/options_iv.py`, signal_engine, app.py, frontend |
| 9 | Trade idea panel + morning brief (rule-based) | `models/trade_idea.py`, app.py, frontend |
| 10 | SQLite cache + APScheduler | `db/cache.py`, app.py |
| 11 | Alert system + keyboard shortcuts + EIA surprise | `models/alerts.py`, app.py, frontend |
| 12 | Final validation + signal history sparkline | `db/signal_history.py`, requirements audit |

---

## RULE: Always Ask Before Working Around Limitations

**If implementing a feature and the ideal data source is unavailable, inaccessible, or would require a paid API / manual input from the user — STOP and ask before substituting a lower-quality alternative.**

Do not silently:
- Use a proxy dataset (e.g. WTI COT for Brent)
- Hardcode values with ⊘ badges
- Fall back to simulated/demo data
- Use a weaker algorithm when a better one is available if the user can provide a package or key

Instead: **state the blocker, state what the ideal source is, state the workaround, and ask which path to take.** The user may have Bloomberg access, a paid API key, or can provide a data file manually. Always ask first.

---

## Known Gaps / Silent Workarounds (to revisit)

| Gap | Current state | Ideal solution | Needs from user |
|---|---|---|---|
| Options IV (Command 8) | BZ=F has no yfinance options data | CME DataMine or USO ETF proxy | Decision: CME/Bloomberg or USO proxy |
| OPEC compliance | Hardcoded static estimates (Q1 2026) | EIA international series via existing EIA key | Approval to use EIA INTL series |
| Spark/Dark spread | Hardcoded $12.10/$8.30 with ⊘ | EIA electricity price series (EIA key available) | Approval to implement |
| Brent COT | Using WTI CFTC data as proxy | ICE/FCA Brent COT (separate publication) | ICE data access (if available) |
| Morning Brief | Static hardcoded text (Command 9 = rule-based) | Local LLM via Ollama (free, offline) | Ollama installed? Or keep rule-based? |
| Weather normals | Hardcoded monthly averages per city | NOAA Climate Normals CSV (free, daily) | Low priority — current precision adequate |
| FRED WTI ($112.25) | Possibly stale FRED data, displayed in /api/macro | Cross-check vs live yfinance | No action needed, informational only |

---

## Gotchas / Known Issues
- **Windows date formatting:** Use `f"{d.strftime('%b')} {d.day}"` not `"%-d"` (Linux-only)  
- **yfinance multi-level columns:** Always flatten after `yf.download()` with `df.columns.get_level_values(0)`  
- **File truncation:** Write tool silently truncates Python files >~500 lines — use Edit for targeted changes  
- **LWC chart state:** `_lwcChart`, `_lwcSeries`, `_lwcFvLine` are module-level globals; `drawCandleChart()` reuses the instance across calls  
- **APIFY key name:** `.env` uses `APIFY_API_KEY` but CLAUDE.md says `APIFY_API_TOKEN` — check which the fetcher actually reads  
