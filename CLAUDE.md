# PULSE — Project State File
**Last updated:** 2026-06-08 · Sprint −1 + 0a shipped (DuckDB + typed API contracts) · Sprint 0b next
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

### ✅ CLASS-DEMO SPRINT — SHIPPED 2026-06-08 (ahead of today's class)

Mom asked in class for a **narrower** scope to discuss today, ahead of the
full Phase 2 brief. Shipped end-to-end in one session:

**Scope she defined:**
- Divide history into **4 regimes** on curve shape only (extreme/mild contango, mild/extreme backwardation)
- For live data, compute fair value only from the **current regime's history**
- Output **the most profitable spread or fly** as a single ranked pick
- Train ≤ 2026-03-31, test on April–May 2026
- Surface it on the Paper Trading tab

**Delivered:**
- `backend/research/regimes.py` — hard-threshold classifier on M1-M12 (≤−5 / −5–0 / 0–+10 / >+10)
- `backend/research/spread_universe.py` — 3 instruments: Brent M1-M2, M3-M6, front fly (M1-2×M2+M3)
- `backend/research/features.py` — point-in-time feature matrix, 2,692 rows × 11 cols, 2016–2026, fully backfillable from /Data + FRED (no EIA/COT calls; can add in Phase 2 full build)
- `backend/research/models.py` — per-(spread, regime) Ridge (CV-tuned α) + Quantile (p10/p50/p90). 12 cells, all saved to `backend/data/research/models/*.pkl`. Backtest report saved to `backend/data/research/backtest_report.json`.
- `backend/research/live_ranker.py` — classify today, predict, rank by `|z| × R²_oos × √(n/100)`, return #1 with full receipts
- API: `/api/regime`, `/api/regime/recommendation`, `/api/regime/backtest`
- `frontend/src/components/panels/RegimePickCard.tsx` — new card on Paper Trading tab above the existing Trade Idea
- **Spread-aware paper trading**: `paper_trading._live_price()` now recognises spread asset keys (`brent_m1_m2`, `brent_m3_m6`, `brent_fly_123`) and computes the spread live from /Data so MTM compares same scale to same scale. Push button on the Regime Pick card creates a `paper_trades` row with `asset='brent_m3_m6'`, `direction='SHORT'`, etc.

**First live recommendation** (2026-06-08, regime = EXTREME_BACKWARDATION, 61 days in regime):
> **SELL Brent M3-M6** · current $7.09 · fair $6.32 · 80% band $4.49–$6.78
> z = +2.56σ · confidence 74% · OOS R² 0.86 · band hit 75%
> Top drivers in this regime: m1_m12 (+1.68), fly_lag1 (-0.45), m1_m2_lag1 (+0.45)
> Models trained on 2,652 rows ≤ 2026-03-31, validated on 40 April-May rows.

**Backtest summary (April-May 2026 test window):**

| spread × regime | n_train | R² in-sample | R² OOS | band hit |
|---|---|---|---|---|
| brent_m1_m2 × EXTREME_BACKWARDATION | 191 | 0.85 | 0.50 | 60% |
| brent_m3_m6 × EXTREME_BACKWARDATION | 191 | 0.97 | **0.86** | **75%** |
| brent_fly_123 × EXTREME_BACKWARDATION | 191 | 0.45 | −0.21 | 57% |

The 40 test rows all fell in EXTREME_BACKWARDATION (M1-M12 ≥ +$10 throughout
April-May), so only that regime's OOS metrics are populated. Other regimes
have training-only stats — they'll get OOS validation when the test window
naturally rolls forward.

**Honest caveats:**
- Fly model is genuinely weak (R²_OOS negative). Reported transparently in the UI rather than hidden.
- M1-M2 model has 60% band hit — usable but not as strong as M3-M6.
- Single-leg paper-trading approximation: spread is recorded as one position with `asset='brent_m3_m6'`, MTM uses the live spread value. True two-leg accounting comes in Phase 2 Sprint 2.
- Features used are tight (curve + macro + seasonal + lagged spreads). Phase 2 full build adds inventory + COT + GDELT tone as features for richer per-regime models.

This narrow-scope work IS Sprint 1 of Phase 2 (the vertical slice). Code lives in `backend/research/` — broadening to more instruments/regimes/axes is now a config change, not a refactor.

---

### ✅ SPRINT −1 · DuckDB + Parquet conversion of /Data — SHIPPED 2026-06-08

Converted the 3.5 GB /Data lake to columnar Parquet with DuckDB as the query
engine. Phase 2 historical feature lookups now run ~10× faster cold, ~130×
warm, and the RAM footprint dropped from ~600 MB to ~110 MB per process.

**Delivered:**
- `backend/scripts/convert_data_lake.py` — idempotent mtime-based converter
  (`--check` reports staleness, `--force` rebuilds all). Daily files convert
  via pandas; 1-min files stream via DuckDB `COPY ... TO PARQUET (ZSTD)`.
- `backend/data_lake.py` — every public accessor (`get_brent_settlements`,
  `get_c12_15y`, `get_spread_15y`, `get_brent_ohlcv_multi`, `load_1min_tail`)
  reads parquet via DuckDB with a transparent pandas-CSV fallback. New helper
  `duckdb_conn()` returns a connection with each parquet pre-registered as a
  view named after its source key (`brent_1min`, `wti_1min`, …) so any caller
  can do `SELECT ... FROM brent_1min` directly. `reset_duckdb()` lets callers
  refresh views after a re-conversion. `parquet_path(key)` is exposed.
- `start.py` — calls `ensure_parquet()` during pre-flight; runs the converter
  only when any source CSV/xlsx is newer than its parquet counterpart.
- `requirements.txt` — pinned `duckdb==1.5.3`, `pyarrow==20.0.0`.

**Measured against acceptance criteria:**

| Metric | Target | Achieved |
|---|---|---|
| `load_1min_tail(brent_1min, days=30, c1)` in-process cold | <1 s | 0.87 s |
| Same call warm (subsequent) | — | ~70 ms |
| Equivalent old pandas-CSV column-pruned read | — | 9.4 s |
| Peak RSS for one 1-min file | <100 MB | ~108 MB incl. duckdb+pandas baseline |
| Parquet vs source size (Brent 1-min) | — | 595 MB CSV → 93 MB parquet (zstd) |
| Source CSV preserved | yes | yes — `/Data/parquet/` sits alongside |

**Notes:**
- /Data CSVs are untouched; `FILES[*]` still points at them so legacy paths
  that bypass the loaders (e.g. `realised_vol._load_1min_close_series`) keep
  working. Migrating them to `load_1min_tail` / `duckdb_conn` is opportunistic
  cleanup — pick up when next touching the fetchers.
- Total parquet footprint: ~3.6 GB of 1-min CSVs → ~530 MB on disk (~6.5:1).

---

### ✅ SPRINT 0a · Pydantic response models + auto-generated TS types — SHIPPED 2026-06-08

Pinned the contract for the 8 most-used endpoints to a Pydantic v2 model and
emitted a matching TypeScript file. Phase 2 will add ~15 new endpoints; this
gives them a typed seam so the "frontend reads the wrong shape" bug class can't
sneak through. FastAPI was *not* introduced — we kept Flask and validate on
return via a small `respond()` helper to stay low-risk mid-project.

**Delivered:**
- `backend/schemas/__init__.py` — Pydantic v2 models with `extra="allow"`
  (forward-compatible) for the 8 endpoints. Public `RESPONSE_MODELS` registry
  + `respond(Model, data, timestamp, **envelope)` helper. Validation failures
  log a warning and return the raw payload; set `PULSE_STRICT_SCHEMAS=1` to
  hard-fail in dev.
- `scripts/generate_ts_types.py` — codegen that walks Pydantic JSON schemas
  and emits `frontend/src/lib/api-types.ts` (28 interfaces, ~7 KB). Output is
  pure types, regeneratable, never hand-edited. Includes an `ApiResponseMap`
  for endpoint → type lookups.
- `frontend/src/lib/api.ts` — typed `getJSON<T>` calls on the 8 endpoints,
  re-exports for view code (`PricesData`, `SignalData`, `TradeIdeaData`,
  `FundamentalsData`, `NewsData`, `PaperPosition`, `PaperPerformanceData`,
  `HealthDetailData` and their nested types).
- `requirements.txt` — pinned `pydantic==2.13.4`.

**Endpoints under typed contracts (Sprint 0a):**

| Endpoint | Model | Live response validates? |
|---|---|---|
| GET /api/prices | `PricesResponse` | yes |
| GET /api/fundamentals | `FundamentalsResponse` | yes |
| GET /api/news | `NewsResponse` | yes |
| GET /api/signal | `SignalResponse` | yes |
| GET /api/trade-idea | `TradeIdeaResponse` | yes |
| GET /api/paper/positions | `PaperPositionsResponse` | yes |
| GET /api/paper/performance | `PaperPerformanceResponse` | yes |
| GET /api/health-detail | `HealthDetailResponse` | yes |

**Verification:**
- All 8 endpoints return identical JSON shape as pre-Sprint baseline (byte-for-byte ±15B).
- Zero schema-validation warnings in the API log under live traffic.
- `npx tsc --noEmit` clean (only pre-existing `baseUrl` deprecation).
- `npx vite build` succeeds; dashboard renders with live data in preview.

**For new endpoints (Phase 2 onward):**
1. Add a model in `backend/schemas/__init__.py`.
2. Register it in `RESPONSE_MODELS`.
3. Change `return jsonify(...)` → `return respond(MyModel, data, _now())`.
4. Run `python scripts/generate_ts_types.py`.
5. Import the type from `frontend/src/lib/api.ts`.

---

### 🟢 SPRINT 0b · Sentry + Better Stack observability  ← **next**

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

Things we *know* are suboptimal. Sequencing logic: do what unblocks Phase 2 NOW;
batch the rest into a dedicated **Phase 3 production-hardening sprint** AFTER
Phase 2 ships, with empirical measurements to justify each upgrade.

### NOW — before / during Phase 2 (mentor-independent prep)

| # | Item | Why now | Sprint |
|---|---|---|---|
| 1 | DuckDB + Parquet for /Data | 50× faster historical queries — directly speeds up Phase 2 regressions | **Sprint −1 ✅ shipped 2026-06-08** |
| 2 | Pydantic + TS codegen | Phase 2 adds ~15 new endpoints; type safety prevents the "wrong shape" bug class on each | **Sprint 0a ✅ shipped 2026-06-08** |
| 3 | Sentry observability | Safety net while writing Phase 2 code | **Sprint 0b** |

### PHASE 3 — Production hardening, batched after Phase 2 ships

Sequenced together because they share concerns (deploy needs the whole stack
upgraded simultaneously). Total: ~1 week. To be done with **real Phase 2 data**
flowing, so each upgrade can be justified empirically rather than by guess.

| # | Item | Cost | Why deferred |
|---|---|---|---|
| 4 | **FastAPI migration** (Flask → FastAPI) | 1 day | Phase 2 doesn't need async; risk of breaking the 32 streams while Phase 2 is mid-flight |
| 5 | **Async fetchers** (httpx.AsyncClient for slow I/O) | 1 day | Same — nice to have, not blocking |
| 6 | **Postgres + TimescaleDB** (paper trades, signal/IV history) | 1 day | SQLite handles current scale fine; migration could lose paper-trade history if botched |
| 7 | **Redis cache + dependency tracking** | 1 day | Replaces SQLite cache; gets us auto-invalidation (prices → fair_value) |
| 8 | **WebSocket push** (replace polling for prices/alerts/MTM) | 1 day | UX win but not blocking |
| 9 | **Docker + Fly.io deploy + HTTPS** | 1 day | Only matters once mentor wants to share publicly |
| 10 | **Better Stack log aggregation + uptime monitoring** | 0.5 day | Pairs with deploy |

Phase 3 sprint sequencing rationale documented above (see *"What 'afterwards'
actually means"* in the 2026-06-05 design discussion). The key insight:
**doing #4–#10 BEFORE Phase 2 delays Phase 2 by 3 weeks for invisible benefit;
doing them AFTER lets us measure latency before/after and justify each upgrade.**

### Opportunistic / nice-to-have (no fixed date)

| # | Item | When |
|---|---|---|
| 11 | TanStack Query (replaces homegrown usePolling) | Frontend refactor sprint, eventually |
| 12 | Zustand for cross-tab state | When state passing through props gets painful |
| 13 | Unified charting library (5 libs → 1) | Visual polish refactor |
| 14 | pytest + vcrpy tests | Add coverage as we touch code; don't backfill |
| 15 | MLflow model tracking | Sprint 1 of Phase 2 (per-regime regression experiments) |

### Design principle for this register

**"Defer until measured."** Every item in Phase 3 is an architectural
improvement that's clearly correct in the abstract, but the *magnitude*
of the win depends on real load patterns we don't have data on yet.
Shipping Phase 2 first gives us that data.

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
