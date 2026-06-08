# PULSE — Project State File
**Last updated:** 2026-06-05 · Phase 1 shipped (PR #2), Phase 2 starting
**Project:** PULSE — Energy Intelligence Terminal (Futures First internship)
**Stack:** Flask 3 · React 18 + Vite + Tailwind · SQLite (cache + paper book) · /Data desk feed · 35 named data sources
**Run:** `python start.py` from `pulse/` root — opens http://127.0.0.1:5000

---

## How to start a new session

1. Read this file **end-to-end**. It is the single source of truth.
2. Check **"Current sprint"** below.
3. Execute that sprint's tasks in order.
4. Update this file when each sprint ships.
5. If something is unclear, the relevant code or design doc is referenced inline.

**Rule:** one sprint per session. Don't multi-task across sprints in one chat — the context overhead defeats the purpose.

---

## Where we are right now

### ✅ Phase 1 — SHIPPED + MERGED to main (PR #2, 5,699 lines)

A working energy-intelligence dashboard with:

- **32 live data streams** (prices, curve, fundamentals, news, weather, technicals, term structure, macro, patterns, IV, OVX, JODI, etc.)
- **Health monitoring** — `/api/health-detail` + top-bar pill + drill modal
- **Source provenance** — 35-entry registry surfaced via per-panel SourceTag chips + shield-icon ledger
- **Trade Idea card** powered by 9-indicator weighted signal engine (hand-set "expert prior" weights)
- **Groq llama-3.3-70b morning brief** (5-bullet format) with Ollama + rule-based fallbacks
- **Paper Trading sandbox** (tab 9) — SQLite-backed single-leg book, MTM every minute, auto-close on TP/SL, full performance panel (PnL · Win% · Sharpe · Profit factor · Max DD · equity curve)
- **News audio replay** — 3-tier source picker (NEWS_BREAKING alert → most-negative FinBERT article → latest), spoken via Web Speech API
- **Stumpy pattern analogs** over 14.6y Brent C1 history
- **Curve regime panel** — M1-M12 percentile + z-score vs 15-year history
- **Order-flow imbalance** per Brent contract from /Data buy/sell volume

Mentor presented this and was satisfied with Phase 1.

### 🔄 Phase 2 — IN PROGRESS

**Mentor's ask** (paraphrasing her message of 2026-06-05): build a **regime-based market analysis engine** that:

1. Classifies markets into regimes using inventory + seasonality + vol + curve + macro
2. Builds a regime-wise historical dataset of spread/butterfly behaviour
3. Applies regressions (Linear / Ridge / Lasso / Rolling / Regime-specific / Feature selection)
4. Generates ranked analytical opportunities when spreads/butterflies deviate from their regime-conditional expectation
5. Integrates into the dashboard — current regime, drivers, regression output, ranked opportunities

**Status:** Methodology brainstormed. **7 alignment questions sent to mentor 2026-06-05**, awaiting reply (see below).

While waiting, executing the prep sprints below.

---

## Pending decisions (waiting on mentor's reply)

The exact build depends on her answers. While she replies, infrastructure work is mentor-independent and proceeds.

1. **Instrument scope** — 15 spreads + 3 butterflies proposed (Brent + WTI calendars, Brent-WTI tenors, 4 cracks, 3 flies). She picks the universe.
2. **Regime axes** — default proposed: curve × inventory × volatility (27 grid, ~9-12 with usable n). She may add seasonal axis or change.
3. **Time horizon** — default 20-day mean reversion. May want 5d swing or 60d position.
4. **Paper trading integration** — extend to 2-leg spread positions (recommended) or convert spreads to single-asset approximations.
5. **WTI deferred data gap** — /Data has Brent C1-C31 but not WTI equivalent. Request the file, or restrict scope to Brent-led.
6. **Auto-push behaviour** — opportunities display only / auto-stage for approval / auto-push above threshold.
7. **Phase 1 coexistence** — replace existing signal engine, run alongside, or split (Phase 1 = directional, Phase 2 = spreads/butterflies).

---

## Current sprint

### 🔴 SPRINT −1 · DuckDB + Parquet conversion of /Data

**Goal:** convert the 3.5 GB /Data lake from CSV/xlsx to Parquet, with DuckDB as the query engine. Phase 2 will run thousands of historical feature lookups — pandas + CSV is ~50× too slow.

**Acceptance criteria:**
- One-time converter script `backend/scripts/convert_data_lake.py` produces `/Data/parquet/*.parquet`
- `backend/data_lake.py` public API unchanged (functions still return pandas) but uses DuckDB under the hood
- First call to any loader: <1s (was 30s for the 1-min files)
- RAM footprint: <100MB (was 600MB for one 1-min file)
- New helper: `data_lake.duckdb_conn()` returns a connection for direct SQL on the lake
- /Data CSVs are not deleted — Parquet sits alongside, so source-of-truth is preserved

**Files to create / change:**
- NEW: `backend/scripts/convert_data_lake.py` — idempotent, checks file mtimes, only re-converts when source changed
- MODIFY: `backend/data_lake.py` — DuckDB-backed loaders, same return shapes
- MODIFY: `start.py` — run converter at boot if Parquet is older than source CSVs
- ADD to `requirements.txt`: `duckdb==1.1.x`, `pyarrow==18.x`

**Validation:**
- `python -m backend.data_lake` still prints same output as today
- `python -c "from backend.data_lake import load_1min_tail; t = load_1min_tail('brent_1min', days=30, contract='c1'); print(len(t))"` — should complete in <500ms

---

### 🟡 SPRINT 0a · Pydantic response models + auto-generated TS types

**Goal:** kill the recurring bug class where frontend reads the wrong shape. Phase 2 will add ~15 new endpoints — typed contracts make this safe.

**Acceptance criteria:**
- Every API route returns a typed Pydantic model (`@app.route("/api/foo") def foo() -> FooResponse`)
- FastAPI is NOT introduced yet (too risky mid-project) — instead, Pydantic models live in `backend/schemas/` and routes manually validate on return
- `scripts/generate_ts_types.py` reads the Pydantic schema, emits `frontend/src/lib/api-types.ts`
- TypeScript code imports these types instead of redefining them
- Start with the 8 most-used endpoints first (prices, fundamentals, news, signal, trade-idea, paper/positions, paper/performance, health-detail)

**Files to create:**
- NEW: `backend/schemas/__init__.py` — Pydantic models
- NEW: `scripts/generate_ts_types.py` — codegen script
- MODIFY: `frontend/src/lib/api.ts` — import from generated types

---

### 🟢 SPRINT 0b · Sentry + Better Stack observability

**Goal:** safety net before adding a lot of new code. 30-minute setup with infinite future value.

**Tasks:**
- `pip install sentry-sdk[flask]`, init in `backend/app.py`
- `npm i @sentry/react`, init in `frontend/src/main.tsx`
- Sign up for Better Stack free tier (you'll need to do this — I'll guide), get a logtail token
- Add structured logging to all error paths

**Action user must take:**
- Register at sentry.io (free), create a "PULSE" project, paste DSN into `.env` as `SENTRY_DSN`
- Register at betterstack.com (free), paste source token as `BETTER_STACK_TOKEN`

---

### 🟢 SPRINT 0c · Historical feature matrix + regime classifier scaffold

**Goal:** Phase 2 foundation. Mentor-independent — works for any regime axes she chooses.

**Acceptance criteria:**
- `backend/research/features.py` builds a daily feature matrix for 2011-2026 (point-in-time, no future leakage)
  - Features: inventory %dev + 4wk change · COT pct · OVX · DXY level + 30d change · curve M1-M2 · curve M1-M12 · days-to-expiry · sin/cos month · realised vol · cross-product proxies · GDELT tone
  - Stored as `backend/data/features_pit.parquet` (3,693 rows × ~15 cols)
- `backend/research/regimes.py` — pluggable classifier
  - `classify(features_df, axes=["curve", "inventory", "vol"]) → regime_labels`
  - Default: 3 axes × 3 buckets each = 27 grid, ~9-12 with usable n
  - Stored as `backend/data/regime_history.parquet`
- Diagnostic notebook `notebooks/phase2_sprint0_diagnostics.ipynb`:
  - Distribution of regimes over 15 years
  - Sample-size table per regime
  - Transition matrix
  - F-test: do regimes produce statistically distinct M1-M12 spread distributions?

**Once mentor replies** with her axis preferences, this is a one-line change in the call site.

---

## Phase 2 sprints (after mentor confirms scope)

| Sprint | Days | Output |
|---|---|---|
| **1** — Vertical slice on Brent M1-M12 | 3–5 | Per-regime regression suite (Linear/Ridge/Lasso/Robust/Quantile), walk-forward CV, winner selected per regime, live inference endpoint with full receipts |
| **2** — Dashboard REGIME tab + paper trading 2-leg | 5 | New tab visible with regime banner, opportunity board (M1-M12 only initially), drill panel. Paper book schema migrated to multi-leg. |
| **3** — Broaden to full instrument universe | 5–7 | All 15 spreads + 3 butterflies modelled. UI fills in. Mentor's Q1, Q2, Q3, Q5 answers applied. |
| **4** — Validation + backtest | 3–5 | Walk-forward backtest of acting on top-ranked opportunities. Compare vs Phase 1 signal. Two-page methodology PDF for mentor. |

---

## Directory layout

```
pulse/
├── start.py                          # one-command launcher
├── CLAUDE.md                         # THIS FILE
├── .env                              # API keys (gitignored)
├── .env.example                      # template
├── requirements.txt                  # pinned Python deps
├── Data/                             # 3.5 GB institutional desk feed (gitignored)
│   ├── LCO_Brent_daily_settlement_c1_to_c31_2016_2026.csv
│   ├── LCO_Brent_daily_close_c1_c12_spread_2011_2026.xlsx
│   ├── LCO_Brent_daily_OHLCV_buysell_volume_multi_contract.xlsx
│   ├── LCO_Brent_1min_outrights_midprice_*.csv
│   ├── CL_WTI_1min_outrights_midprice_*.csv
│   ├── HO_HeatingOil_1min_outrights_midprice_2021_2026.csv
│   ├── LGO_Gasoil_1min_outrights_midprice_2021_2026.csv
│   ├── WTCL_LCO_Spread_1min_outrights_2021_2026.csv
│   └── parquet/                      # SPRINT −1 deliverable
│
├── backend/
│   ├── app.py                        # Flask API, ~1400 lines, all routes + scheduler
│   ├── data_lake.py                  # /Data loaders (becomes DuckDB-backed in Sprint −1)
│   ├── paper_trading.py              # SQLite trade book + MTM service
│   ├── db/
│   │   ├── cache.py                  # SQLite TTL cache
│   │   └── pulse_cache.db            # SQLite file (gitignored)
│   ├── data/
│   │   ├── LCOSettle.xlsx            # legacy fallback (data_lake.py prefers /Data CSV)
│   │   └── cache/                    # JODI raw zip + sundry caches (gitignored)
│   ├── fetchers/                     # 22 modules — one per data source
│   │   ├── prices.py · ohlcv handled in app.py · historical.py
│   │   ├── curve.py · multi_curve.py · curve_regime.py · order_flow.py
│   │   ├── eia.py · cot.py · opec.py · jodi.py · rig_count.py
│   │   ├── weather.py · technicals.py · cracks.py · seasonality.py
│   │   ├── macro.py · ovx.py · ecb_fx.py
│   │   ├── news.py · gdelt.py · marketaux.py · sentiment.py · rss_news.py
│   │   ├── geo_risk.py · analyst_watch.py · tanker_watch.py
│   │   ├── realised_vol.py · options_iv.py · stooq.py · analogs.py
│   │   ├── eia_surprise.py · forward_cover.py · spreads_history.py
│   ├── models/
│   │   ├── fair_value.py             # cost-of-carry + 4-component adjustments
│   │   ├── signal_engine.py          # 9-indicator weighted composite [-2,+2]
│   │   ├── trade_idea.py             # rule-based idea + Groq morning brief
│   │   ├── correlations.py · term_structure.py · patterns.py · alerts.py
│   └── research/                     # NEW in Sprint 0c
│       ├── features.py               # historical feature matrix builder
│       └── regimes.py                # pluggable regime classifier
│
└── frontend/
    ├── index.html · vite.config.ts · package.json
    ├── src/
    │   ├── App.tsx                   # root, 9 tabs
    │   ├── main.tsx
    │   ├── views/                    # one file per tab
    │   │   ├── SignalView · ChartsView · FundamentalsView · IntelligenceView
    │   │   ├── TermStructureView · SpreadsView · ContractsView · PlaybookView
    │   │   ├── PaperView             # paper trading sandbox
    │   │   └── (FUTURE) RegimeView   # Phase 2 sprint 2
    │   ├── components/
    │   │   ├── shell/                # TopBar · Sidebar · StatusBar · HealthPill · ProvenanceLegend
    │   │   ├── ui/                   # Panel · Chip · Stat · ScoreBar · Sparkline · SourceTag · Modal · ErrorBoundary
    │   │   ├── panels/               # specialised analysis panels
    │   │   ├── charts/               # chart components
    │   │   ├── alerts/               # ToastStack (with squawk + news replay)
    │   │   ├── chat/                 # ChatDock
    │   │   └── onboarding/           # OnboardingTour
    │   └── lib/
    │       ├── api.ts                # HTTP client + endpoint registry
    │       ├── hooks.ts              # usePolling, useClock, useLocalStorage
    │       ├── fmt.ts                # number/date/signal formatting
    │       ├── provenance.ts         # 35-entry source registry
    │       ├── caseStudies.ts · contracts.ts · geoRisk.ts
```

---

## API endpoints (32 active in Phase 1)

| Group | Routes |
|---|---|
| **Health** | GET /api/health · GET /api/health-detail |
| **Prices/charts** | GET /api/prices · /api/ohlcv · /api/history · /api/curve |
| **Models** | GET /api/fair-value · /api/signal · /api/correlations · /api/term-structure |
| **Fundamentals** | GET /api/fundamentals · /api/eia-surprise · /api/forward-cover · /api/jodi |
| **News/intel** | GET /api/news · /api/marketaux · /api/gdelt-tone · /api/analyst-watch · /api/tanker-watch · /api/patterns · /api/analogs |
| **Risk/structure** | GET /api/cracks · /api/steo · /api/ovx · /api/curve-regime · /api/order-flow |
| **Other** | GET /api/weather · /api/technicals · /api/macro · /api/iv · /api/trade-idea · /api/alerts · /api/spreads-history · /api/seasonality |
| **All-in-one** | GET /api/all |
| **Paper trading** | POST /api/paper/push · POST /api/paper/close/:id · GET /api/paper/positions · GET /api/paper/performance · POST /api/paper/clear |
| **RAG** | POST /api/ask · GET /api/ask/stats |

---

## Environment keys (`backend/.env`)

```
EIA_API_KEY=...           # EIA v2 — free at api.eia.gov
FRED_API_KEY=...          # FRED — free at fred.stlouisfed.org
NEWSAPI_KEY=...           # legacy news fallback
BLS_API_KEY=...           # Bureau of Labor Statistics
APIFY_API_TOKEN=...       # Apify news scrape (paid)
AISSTREAM_API_KEY=...     # live AIS tankers
MARKETAUX_KEY=...         # MarketAux news (free 100/day, currently quota-exhausted)
GROQ_API_KEY=...          # Groq llama-3.3-70b for morning brief
OLLAMA_MODEL=llama3.2:1b  # local LLM fallback
OLLAMA_TIMEOUT=120
# After Sprint 0b:
SENTRY_DSN=...            # error tracking
BETTER_STACK_TOKEN=...    # log aggregation
```

---

## Data sources — what powers what

35 named sources in `frontend/src/lib/provenance.ts`. Key tiers:

**LIVE (green dot):** yfinance · EIA v2 · CFTC · FRED OVX · FRED macro · GDELT 2.0 · MarketAux · Open-Meteo · aisstream · ECB FX · Stooq · Nitter
**CACHED (blue dot):** ICE LCO 15y · multi_curve · /Data Brent settlements · /Data 1-min mids · daily yfinance · 5y yfinance
**MODEL (gold dot):** PULSE signal engine · fair value · correlations · curve regime 15y · order flow · realised vol · pattern scipy · stumpy MP · geo risk · alerts · trade idea + Groq
**ESTIMATE (amber dot):** VLCC freight proxy · IV synthetic (legacy, replaced by OVX)
**HARDCODED (red dot):** Saudi OSP · OPEC static · contract reference · case studies

Every panel header shows its source as a chip. Click the **shield icon** top-right → full ledger with search.

---

## /Data lake — what's in it and where it's used

The institutional desk feed in `/Data/` (~3.5 GB, gitignored, supplied by mentor). Consumed by:

| File | Used by | What it powers |
|---|---|---|
| `LCO_Brent_daily_settlement_c1_to_c31_2016_2026.csv` (1.2 MB) | `multi_curve.load_lco_history()` via `data_lake.get_brent_settlements()` | Forward curve, calendar spreads, term structure |
| `LCO_Brent_daily_close_c1_c12_spread_2011_2026.xlsx` (146 KB) | `curve_regime.py` via `data_lake.get_spread_15y()` | M1-M12 percentile + z-score over 14.6y |
| `LCO_Brent_daily_OHLCV_buysell_volume_multi_contract.xlsx` (140 KB) | `order_flow.py` via `data_lake.get_brent_ohlcv_multi()` | Per-contract daily buy/sell imbalance |
| `LCO_Brent_1min_outrights_midprice_*.csv` (1.1 GB) | `realised_vol.py` + Phase 2 features | 30-day annualised RV + intraday Phase 2 work |
| `CL_WTI_1min_outrights_midprice_*.csv` (1.1 GB) | `realised_vol.py` | WTI RV (HH proxy) |
| `HO_HeatingOil_1min_outrights_midprice_*.csv` (495 MB) | reserved for Phase 2 cracks | Refined product RV |
| `LGO_Gasoil_1min_outrights_midprice_*.csv` (509 MB) | reserved | European distillate analytics |
| `WTCL_LCO_Spread_1min_outrights_*.csv` (550 MB) | reserved for Phase 2 | True 1-min WTI-Brent calendar spread |

**Gap (mentor question Q5):** no WTI equivalent of the daily C1-C31 settlement file. Needed for WTI calendar spread analysis in Phase 2.

After Sprint −1: each of these has a `parquet` companion in `Data/parquet/` accessed via DuckDB.

---

## Signal engine weights — current (hand-set "expert prior")

**Crude (Brent / WTI):**
```
inventory 28% · curve 24% · cot 19% · fair_value 14%
sentiment 5% · technicals 5% · dxy 3% · iv 2% · geo 0%
```
**Nat Gas:**
```
inventory 30% · weather 25% · curve 15% · cot 15%
fair_value 10% · technicals 5%
```

Score range [−2, +2]. Conviction: HIGH if ≥5/9 indicators agree, MODERATE if ≥3/9, else LOW.

**Phase 2 will train data-driven weights** per regime per spread and compare against these. See "Phase 2 sprint 4" — validation report.

---

## Trade Idea pipeline

```
signal_engine.score
        ↓
direction = LONG if score>0.5 AND spot < fair_value
          | SHORT if score<-0.5 AND spot > fair_value
          | NEUTRAL otherwise
        ↓
target = spot ± 0.5 × (fair_value − spot)
stop   = spot ∓ 1.5 × ATR
        ↓
thesis_bullets = top 3 indicators (by |weight × score|) agreeing with direction
key_risk      = strongest contradicting indicator
        ↓
morning_brief: Groq llama-3.3-70b → local Ollama → rule-based template
        ↓
trader sees on Signal tab. "Push to Paper" button stages in paper book (tab 9).
```

---

## Paper trading

- **Table:** `paper_trades` in `pulse_cache.db`. Single-leg currently. **Sprint 2 of Phase 2 migrates to multi-leg** (for spread trades).
- **MTM job:** APScheduler every 60s. Checks live price vs TP/SL; auto-closes on hit.
- **Performance:** total PnL · win rate · annualised Sharpe (√252) · profit factor · max drawdown · best/worst trade · equity curve.

---

## Tech debt register (consciously deferred)

Things we *know* are suboptimal, ranked by when we should address them:

| # | Item | Severity | When to fix |
|---|---|---|---|
| 1 | DuckDB + Parquet for /Data | HIGH | **Sprint −1 (now)** |
| 2 | Pydantic + TS codegen | HIGH | **Sprint 0a (now)** |
| 3 | Sentry + Better Stack | MEDIUM | **Sprint 0b (now)** |
| 4 | FastAPI migration | MEDIUM | After Phase 2 (Sprint 6) |
| 5 | Redis cache + TimescaleDB | MEDIUM | After Phase 2 |
| 6 | WebSocket push for live prices | MEDIUM | After Phase 2 |
| 7 | TanStack Query on frontend | LOW | Opportunistic |
| 8 | Zustand for shared state | LOW | When cross-tab state grows |
| 9 | Unified charting (currently 5 libs) | LOW | Refactor sprint |
| 10 | pytest + vcrpy tests | MEDIUM | Add as we go, don't backfill |
| 11 | MLflow for Phase 2 model tracking | MEDIUM | Sprint 1 of Phase 2 |
| 12 | Docker + Fly.io deploy | LOW | When mentor wants to share with her boss |

The architecture review I did 2026-06-05 is logged here too — see `docs/ARCHITECTURE_REVIEW.md` if it exists, otherwise it's in the chat history.

---

## Gotchas / non-obvious behaviour

These bite a fresh session if not flagged:

1. **`python start.py` serves the React build from `backend/static/`**. Frontend changes won't show until you run `cd frontend && npm run build`. For live HMR: `npm run dev` on port 5173 instead.
2. **Two python processes on :5000 = stale code running**. Always `taskkill /F /PID` both before restarting.
3. **SQLite cache poisoning** — when an upstream API fails during a fetch, the fallback dict gets cached. Bust with `DELETE FROM cache WHERE key='...'` to force a fresh fetch.
4. **GDELT rate limit is 1 req/5s per IP**. Multiple GDELT calls in scheduler stagger themselves via a process-wide lock. If you add a new GDELT caller, respect the lock.
5. **MarketAux free tier = 3 articles/request, 100 req/day total**. Paginate carefully; we cap at 3 pages. Currently quota-exhausted on the latest key.
6. **FinBERT model is 420 MB**, downloads on first call to `~/.cache/huggingface/`. First sentiment call is slow.
7. **`backend/static/index.html` is regenerated on every `npm run build`**. Don't hand-edit it.
8. **`Data/` is gitignored**. If you `git clone` on a new machine, the dashboard runs but Phase 2 features will be empty until /Data is restored.
9. **APScheduler `next_run_time=_NOW` only on slow jobs**. The fast ones (prices, ohlcv) wait for their first interval.
10. **PowerShell encoding** — never use PowerShell to read/write `frontend/src/**/*.tsx`. Use the `Read`/`Edit` tools. PowerShell mangles multi-byte chars.

---

## Mentor communication log

| Date | Event |
|---|---|
| 2026-05-29 | Phase 1 mid-review: "trade signals too strong (BUY/SELL), too much glare. Need bullish/bearish labels, replay button, morning brief always visible, fix news bugs." → ALL ADDRESSED in PR #2. |
| 2026-06-05 (AM) | Phase 1 final demo. Approved. Mentor asks for **regime-based market analysis engine**. |
| 2026-06-05 (PM) | 7 alignment questions sent (see "Pending decisions"). Awaiting reply. |

---

## Repo + branch hygiene

- **Main branch:** `main` — always green, always shippable
- **Working pattern:** branch off `main`, PR back, squash-merge, delete branch
- **Last shipped PR:** #2 (2026-06-05) — Phase A+B data overhaul + Paper Trading + Health monitoring
- **Backup branch:** `backup/pre-merge-20260602-175531` — leftover from PR #1, retained out of caution
- **Commit style:** body explains WHY not WHAT. Use `Co-Authored-By: Claude` trailer when AI-paired.

---

## How to resume in a fresh chat — checklist

```
1. Open new chat
2. Paste:
   "Read CLAUDE.md in pulse/, then start [Sprint X].
    Don't multi-task. When the sprint ships, update CLAUDE.md and stop."

3. The agent:
   a. Reads this file
   b. Reads only the files the sprint touches
   c. Implements
   d. Tests
   e. Updates the "Current sprint" section to mark complete + advance to next
   f. Stops
```

That's the contract. One sprint per session. Maximum focus, minimum context overhead.

---

## What "top-notch" means for this project — decision principles

Use these as the tie-breaker when multiple paths are viable:

1. **Honesty over polish.** Every number on the screen traces to a named source. Stale data is shown as stale. Fallback paths are labelled.
2. **Interpretability over R².** Mentor's mandate. A 65% R² Ridge with named drivers beats an 80% R² GBM the trader can't explain.
3. **Type safety on the seams.** Schema drift between backend and frontend is the #1 source of bugs in this project. Sprint 0a addresses this.
4. **Show your receipts.** Every model output ships with its training-data window, sample size, OOS metrics, and historical analogs. Especially in Phase 2.
5. **Ship narrow, then broaden.** One spread fully end-to-end before five spreads half-done.
6. **Mentor-facing always.** Every sprint ends with an artifact she could open and understand.

---

**End of CLAUDE.md.**
A fresh session should now have everything needed to resume. Start with "Current sprint."
