# PULSE — Project State

**PULSE** — Energy Intelligence Terminal (Futures First internship). A live energy-trading
dashboard: ingests ~35 data sources, runs quant models (fair value + a regime-conditional
spread engine), and serves a React dashboard with a paper-trading book.

- **Stack:** Flask 3 · React 18 + Vite + Tailwind · SQLite (cache + paper book) ·
  DuckDB/Parquet over a 3.5 GB `/Data` desk feed · sklearn + XGBoost/LightGBM/CatBoost
- **Run (local):** `python start.py` from the repo root → http://127.0.0.1:5000
- **Last updated:** 2026-06-16 (Phase 4 — dashboard rebuild planned · HF regime root-cause found)
- **Live:** https://rohithpranav45-pulse.hf.space (free HF Space, A/B book accumulating 24/7 — **regime endpoints currently failing**, see §1 below)

> 🧭 **Three docs, one per tense:**
> **this file = present** (current state · how to run · architecture · gotchas) ·
> [`docs/ROADMAP.md`](docs/ROADMAP.md) **= future** (pending tasks · timeline · copy-paste session prompts) ·
> [`docs/PHASE_HISTORY.md`](docs/PHASE_HISTORY.md) **= past** (full sprint-by-sprint log) ·
> [`docs/DASHBOARD_REBUILD.md`](docs/DASHBOARD_REBUILD.md) **= active plan** (Phase 4 — 9 tabs → 6 tabs, one phase per session).

---

## 1. Current status

### ✅ Shipped
- **Phase 1 — dashboard** (PR #2): 32 live data streams, health monitoring, source provenance,
  directional Brent signal engine, Groq morning brief, paper-trading sandbox, pattern analogs.
- **Phase 2 — regime engine** (PR #3 + follow-ups): regime-conditional spread/butterfly engine over
  **6 instruments** (Brent + WTI {M1-M2, M3-M6, fly}) × a **3-axis regime grid** (curve × inventory × vol).
  **7-model per-cell competition** (Ridge/Lasso/ElasticNet/Huber + XGB/LGBM/CatBoost). Walk-forward
  backtest + methodology PDF. Dedicated Regime tab, 2-leg paper trading, drill/evidence modal.
- **Tuned exit rule (Phase 2.9.x):** the live book closes on **TP = halfway-to-fair · SL = 2.5σ ·
  30-trading-day time-stop**, trading **4 spreads** (drops brent/wti M3-M6). Backtest win rate 82.9%;
  robustness-checked → win-rate robust OOS (~74-75%), but quote NET Sharpe/PF as *in-sample-optimistic*.
- **A/B paper harness:** a daily tick dual-pushes a `pooled` arm and a `gated` arm; `/api/regime/ab`
  reports per-arm NET win rate + Welch/paired t-tests + a verdict. This is the live forward-validation.
- **Phase 3.D deploy artifacts:** multi-stage `Dockerfile`, `docker-compose.yml` (app + Caddy reverse
  proxy w/ basic-auth + auto-HTTPS), `backend/wsgi.py` (gunicorn entry, single worker), SQLite WAL.
- **Phase 3.0 — invariants test:** `tests/test_invariants.py` (pytest, 9 tests green) asserts the gate /
  tuned-exit / A/B-cost mirrors stay in sync (§5 gotchas 7-9). Run `python -m pytest tests/`.
- **Phase 2.8.8 — full 2018-2026 walk-forward** (34 quarterly refits, `walkforward_report.json` 2026-06-15):
  **the regime-unaware baseline beats every regime variant on NET Sharpe.**
  baseline `+0.372` · gated_blend `+0.298` · pooled `+0.293` · sized_half `+0.282` · sized_kelly `+0.281`.
  Per-spread: baseline wins 4/6 outright — including reversing the Phase-2.7 brent_fly_123 win
  (baseline 1.521 vs sized_half 1.433). 2018-2020 contango is a **Brent-only** story (WTI synth starts
  2021, pre-2021 WTI cells auto-skip per `MIN_SAMPLES`); deep contango is a clean rolling-z play that
  doesn't need regime conditioning. **Phase 2.8 acceptance bar** (gated NET ≥ +0.65) **missed by ~2×.**
  Live A/B `/api/regime/ab` still arbitrates pooled-vs-gated in production — this doesn't change the live
  default, but it strongly reframes the Phase 2.8.x backlog (regime-as-feature / soft probabilities /
  HMM regimes vs simply shipping baseline-led on long history). Methodology PDF regenerated. Bug fix
  same sprint: `_by_curve_axis` now tolerates `regime=None` on gated baseline-fallback rows
  (latent crash exposed by 2018-2020 WTI rows that have no pooled cell — never triggered in the 2024+ window).
- **Phase 2.8.5 — soft regime probabilities** (`walkforward_report.json["pooled_soft"]`, 2026-06-15):
  **softening the hard −$2 / +$5 curve cuts into a logistic membership function ties hard pooled
  and still trails baseline.** New `backend/research/softprob.py` replaces the indicator-function
  regime classifier with per-axis logistic transitions (bandwidth $1/bbl on curve & inventory,
  2.5pp on vol). Each day's prediction is the posterior-weighted blend across all trained pooled
  cells for that spread (point / quantiles / residual variance all blended). Reuses the per-cell
  competition; same 34 refits 2018-2026; same NET cost model. **pooled_soft NET Sharpe +0.297**
  vs baseline `+0.372` · global `+0.380` · gated_blend `+0.298` · hard pooled `+0.293` — soft pooled
  matches hard pooled within noise (Δ +0.004), so the *discontinuity* at the trader thresholds
  was **not** the binding constraint. Mean modal posterior weight 0.86 over ~2.5 cells blended per
  fire — softening did kick in, but the blended prediction landed where the dominant-cell prediction
  already was. Per-spread: pooled_soft tracks hard pooled almost exactly; baseline still wins 4/6
  outright. **Phase 2.8 acceptance bar (gated NET ≥ +0.65) still unmet by ~2×.** Reframes the
  Phase 2.8 backlog: with split (2.8.4 global) and softening (2.8.5) both failing to lift the
  headline, the credible remaining routes are 2.8.9 HMM/change-point (are the trader thresholds even
  the right regimes?), 2.8.7 multi-horizon, and 2.8.10 portfolio vol-targeting. Composite-soft is
  available behind `python -m backend.research.walkforward --soft-only --composite` (heavier,
  not run this sprint) but the pooled finding makes it unlikely to flip the verdict — flat-prior
  composite ≈ global, and 2.8.4 global already gave us that answer. Methodology PDF regenerated.
  Raw trades persisted to `pooled_soft_trades.json` (10,587 rows); re-run alone via
  `python -m backend.research.walkforward --soft-only` (~6 min) without retraining the heavy
  composite leg.
- **Phase 2.8.4 — global model with regime-as-feature** (`walkforward_report.json["global"]`, 2026-06-15):
  **collapsing the per-cell grid lifts NET Sharpe from ~+0.30 (gated/pooled) to +0.380 — a hair above
  baseline +0.372 (within noise), and a clear improvement over every per-cell regime variant.** One
  model per spread trained on **all** rows with the composite regime fed as 9 one-hot axis columns
  (curve/inv/vol — 3+3+3); same 7-model competition; same 34 refits 2018-2026; same NET cost model.
  6,263 signals (60.3% hit rate), Huber wins 5/6 latest cells. Per-spread NET Sharpe: brent_m1_m2
  `+0.24` (base `+0.67`), brent_m3_m6 `+0.25` (base `−0.04`), brent_fly_123 `+0.92` (base `+1.26`),
  wti_m1_m2 `+0.46` (base `+0.26`), wti_m3_m6 `+0.32` (base `+0.31`), wti_fly_123 `+0.59` (base `+0.80`).
  Honest verdict: **regime-as-feature ties baseline** (per-spread baseline still wins 3/6 outright,
  global wins 2/6, 1 tied) — the per-cell *split* was the binding constraint vs the regime *information*,
  but on this 6-spread universe the information itself isn't lifting the headline. Phase 2.8 acceptance
  bar (gated NET ≥ +0.65) still unmet. Methodology PDF regenerated. Raw trades persisted to
  `global_trades.json` (10,587 rows); re-run alone via `python -m backend.research.walkforward --global-only`
  (~8 min) without retraining the per-cell harness.
- **Phase 3.E — LIVE on Hugging Face Spaces (free, no card, 24/7):** public dashboard at
  **https://rohithpranav45-pulse.hf.space** — the A/B paper book now accumulates round-the-clock.
  A Docker Space builds from this repo's `main` (shallow clone) and **bakes the 534 MB parquet lake**
  from a private HF Dataset (`rohithpranav45/pulse-data`); `backend/hf_persist.py` syncs
  `pulse_cache.db` to/from that Dataset (pull on boot before the app opens it, push every 2h + atexit)
  so the book survives HF's **ephemeral** storage. A GitHub Action (`.github/workflows/keepalive.yml`)
  pings `/api/health` every 6h to beat the 48h idle-sleep. All `.env` keys live as Space secrets.
  Build files + runbook: `deploy/hf_space/` + `deploy/HF_DEPLOY.md`. (Supersedes the Oracle-ARM plan,
  which stayed capacity-blocked after 400+ retries.)

### 🔄 In progress — **Phase 4: dashboard rebuild (9 tabs → 6 tabs)** (planning, 2026-06-16)
Full plan: [`docs/DASHBOARD_REBUILD.md`](docs/DASHBOARD_REBUILD.md). Target structure: **DESK · CHARTS · REGIME ·
PAPER · SIGNAL LOG · MARKETS**. Charts tab kept as-is per user. Cutting Signal / Intelligence /
Fundamentals / Playbook / Spreads tabs (their useful panels relocate). One phase per session, additive
before deletive. Local-only first; HF deploy frozen until mentor verdict on strategy direction is in.
Next session = Phase 4.A (new DESK landing view + risk panel). Strategy + architecture changes
deliberately deferred (mentor decision pending + demo-risk).

### 🚨 HF Spaces regime endpoints broken (root cause found, 2026-06-16)
- `https://rohithpranav45-pulse.hf.space/api/regime/recommendation` and `/api/regime/backtest` return
  `{"available": false}` silently. `/api/regime/drill/<spread>` surfaces the real error:
  **`No module named 'joblib'`**.
- Root cause: `requirements.txt` shipped without `scikit-learn` pinned, so the HF image installed
  neither sklearn nor its transitive `joblib`. Every `pkl` load via `joblib.load` raises ImportError,
  caught by `safe_fetch`, masked as "available: false". `/api/regime` (current regime, no pkls) and
  `/api/regime/walkforward` + `/api/regime/ab` (cached JSON / SQLite) still work — that's why the
  failure looked partial.
- **Fix already in local working tree** (this session): added `scikit-learn==1.7.0` to `requirements.txt`.
  When the user is ready, push to `main` → HF auto-rebuilds with sklearn + joblib → all regime
  endpoints recover. Until then, the dashboard's Regime tab shows partial data only.
- User-deferred: pushing was held back so the HF Space stays stable as a presentation backup
  (today, 2026-06-16). Local desk version is what's being demoed.

### 🔄 In progress — **Phase 3.1: live analysis engine + signal log** (mentor directive, 2026-06-15)
Mentor asked everyone past the historical-validation phase to **run the framework on live market
data** and **add a dashboard signal log** (timestamp · regime · instrument · rationale · confidence ·
subsequent performance) — "move from historical validation to a live analysis engine." Data feed:
per-day SQLite files of **15-min OHLCV bars per contract** (`CO_*`=ICE Brent, `CL_*`=CME WTI) on the
office share `I:\Public\Summer Interns Energy\DB\` (the shared path; override with `PULSE_LIVE_FEED_DIR`).
- **✅ Backend shipped + verified headless (Brent first):**
  - `research/live_feed.py` — reads the share, orders contracts by expiry → c1..c12, builds **real**
    Brent/WTI spreads (m1_m2/m3_m6/fly) + curve m1_m12 at contemporaneous timestamps. (WTI front=N26,
    Brent front=Q26 — different start months, hence ordinal mapping.)
  - `research/live_engine.py` — overlays the live snapshot onto the engine (`get_recommendation` gained
    **additive** `live_actuals` / `live_curve_m1m12` kwargs — daily/A-B paths bit-for-bit unchanged) and
    returns the ranking the framework would trade NOW. Honours PULSE_GATED_BLEND/REGIME_MODE/GATED_SIZE.
  - `research/signal_log.py` — `signal_log` table in `pulse_cache.db`; logs every non-NEUTRAL opportunity
    with all mentor fields + tracks subsequent performance (MTM + tuned TP/SL/30d time-stop). Idempotent
    dedup on (instrument, direction, feed_as_of, cadence).
  - API: `/api/regime/live`, `/api/regime/signals[?status=open|closed]`, `POST /api/regime/signals/generate`.
    Scheduler: `_live_signal_daily` (24h) + `_live_signal_intraday` (15min gen + perf sweep); both gated by
    `PULSE_LIVE_SIGNALS_DISABLED=1`.
  - Verified end-to-end on the captured weekend file: live curve M1-M12 +7.35 → **BACK** regime, top live
    signal Brent fly BUY (z −4.33, XGBoost, conf 0.96). 9 invariants still green; daily path unaffected.
  - **✅ 2026-06-16 — now running on the ACTUAL live feed from this office desk** (both laptop-era blockers
    gone: this desk sees `I:\`, and the recorder is streaming again — `bars_15min_*.db` advancing, latest
    bar within the hour). Live read on 06-16: curve M1-M12 +7.25 → **BACK/LOW/STRESSED**, top live signal
    **Brent fly BUY (z −3.73, XGBoost, conf 0.96)**; 4 signals logged + served by the API. **The fix that
    made it live (gotcha 14):** reading the recorder's WAL db *in place over the SMB share* raises
    `database disk image is malformed` (WAL/`-shm` semantics don't work over a network filesystem). New
    `live_feed._snapshot_feed_locally` / `_open_feed_local` copy the `.db` (+ best-effort `-wal`, never the
    stale `-shm`) to a local temp dir and read the copy — integrity-guarded, memoised per sweep. Replaces
    the old `_connect_ro_wal` (which also *hung* a thread uninterruptibly on certain SMB/WAL states).
  - **✅ Dashboard Signal Log tab** (`views/SignalLogView.tsx` + `panels/SignalLogPanel.tsx`, sidebar key 9) —
    columns timestamp · instrument · dir · regime · confidence · entry→fair(z) · subsequent perf, with ALL/
    OPEN/CLOSED filter + GENERATE button. `api.regimeSignals/regimeLive/regimeSignalsGenerate`. Built +
    browser-verified (2 live Brent signals render; GENERATE round-trips). Phase 3.1 functionally complete.
- **⚠️ Operational notes (2026-06-16):** (1) The live engine **must run on a machine that sees `I:\`** —
  this office desk does; HF/Oracle don't. So "live analysis engine" = a **desk-hosted** process; HF stays
  the public A/B book. (2) The recorder writes one file `bars_15min_20260612.db` and keeps appending to it
  (filename date is stale, data is live — `latest_feed_file` picks it by name-date so this is fine while
  there's one file). The *other* path `I:\Public\Siddharth Raj\lightstreamer_data\` is the **dead** old
  recorder (frozen 06-12) — ignore it; the code default `I:\Public\Summer Interns Energy\DB` is correct.
  (3) **sklearn version skew:** model pkls were trained on sklearn 1.7.0; this desk runs 1.9.0
  (`InconsistentVersionWarning` on every unpickle). Outputs look sane but pin sklearn or retrain to be
  rigorous. (4) **Port-5000 zombie:** the earlier restart churn (under the OLD hanging code) left one
  unkillable python process squatting `:5000` (stuck thread, `TerminateProcess` can't reap it). A
  **reboot reclaims 5000**; until then run on another port (`PORT=5050 python backend/app.py`). The new
  local-snapshot ingestion won't reproduce that hang.

### 🔄 In progress — **always-on deployment** (details in memory `pulse-deployment-pending`)
Goal: a public link so the A/B book accumulates 24/7. Host = **Oracle Cloud Always Free (ARM)**,
region `ap-hyderabad-1`; network ready (VCN `pulse-vcn` + public subnet). The free ARM shape is
**out of capacity**, so an **auto-retry loop runs on this PC** (`~/.oci/pulse_launch.py`, hidden via a
Startup-folder launcher, 90s loop; logs to `~/.oci/pulse_launch.log`). On success it writes
`~/.oci/pulse_instance.txt`. **Next:** when it lands → SSH in (`ssh -i ~/.ssh/oracle_pulse ubuntu@<ip>`),
open 80/443 (security list + iptables), `docker compose up -d --build`, hand over the link.

### ⬜ Next / backlog
> **Full backlog + timeline + per-task copy-paste prompts → [`docs/ROADMAP.md`](docs/ROADMAP.md).** Highlights:
- **Read the A/B verdict** once ≥30 closed trades/arm (or 14 days) → keep gated default or flip to pooled.
- **Phase 2.8 model backlog** (now reframed by the 2.8.8 + 2.8.4 + 2.8.5 verdicts above — both
  *splitting* and *softening* fail to lift the headline; baseline still wins): ~~2.8.4 global
  model w/ regime-as-feature~~ ✅ *(ties baseline at NET +0.380)* · ~~2.8.5 soft regime
  probabilities~~ ✅ *(ties hard pooled at NET +0.297; the threshold discontinuity wasn't the
  binding constraint)* · 2.8.7 multi-horizon sweep · ~~2.8.8 extend walk-forward to 2018-2026~~
  ✅ · 2.8.9 HMM/change-point regimes · 2.8.10 portfolio vol targeting.

---

## 2. How to run

| Task | Command |
|---|---|
| Local dev (serves built React from `backend/static`) | `python start.py` → http://127.0.0.1:5000 |
| Frontend hot-reload | `cd frontend && npm run dev` → :5173 (proxies `/api` to :5000) |
| Rebuild frontend after UI edits | `cd frontend && npm run build` |
| Retrain regime models | `python -m backend.research.models --mode composite` (also `--mode pooled`) |
| Walk-forward backtest (~3 h) | `python -u -m backend.research.walkforward` |
| Walk-forward, **global leg only** (~8 min) | `python -u -m backend.research.walkforward --global-only` |
| Walk-forward, **soft pooled leg only** (~6 min) | `python -u -m backend.research.walkforward --soft-only` |
| Live snapshot from feed (Phase 3.1) | `python -m backend.research.live_feed` (set `PULSE_LIVE_FEED_DIR`) |
| Live recommendation on current market | `python -m backend.research.live_engine` |
| Generate + list live signals | `python -m backend.research.signal_log` · `--update --list` |
| Regenerate methodology PDF | `python -m backend.research.methodology_pdf` |
| Production container | `docker compose up -d --build` (full runbook: `deploy/README.md`) |

> Fresh machine? `/Data`, the model pkls, and `.env` are all gitignored — restore or rebuild them (§5).

---

## 3. Architecture

```
pulse/
├── start.py                         local launcher
├── Dockerfile · docker-compose.yml · .dockerignore · deploy/   Phase 3.D deployment
├── Data/                            3.5 GB desk feed (gitignored) + parquet/ (DuckDB)
├── backend/
│   ├── app.py                       Flask API: routes + APScheduler (scheduler.start only in __main__)
│   ├── wsgi.py                      gunicorn entry — starts scheduler + warm-up (MUST be --workers 1)
│   ├── data_lake.py                 /Data loaders via DuckDB/parquet
│   ├── paper_trading.py             SQLite paper book + 60s MTM (WAL pragmas)
│   ├── db/cache.py                  SQLite TTL cache (WAL pragmas) → pulse_cache.db
│   ├── fetchers/                    ~30 data-source modules
│   ├── models/                      fair value · signal engine · trade idea · patterns
│   ├── research/                    Phase 2 regime engine (table below)
│   └── schemas/                     Pydantic response models → generated frontend types
└── frontend/                        React + Vite (builds into backend/static)
```

**`backend/research/` — the regime engine:**

| File | Role |
|---|---|
| `regimes.py` | composite 27-cell + pooled 3-cell curve grids (hard thresholds) |
| `softprob.py` | Phase 2.8.5 logistic-bandwidth soft posteriors per axis + composite/pooled composition |
| `spread_universe.py` | 6 instruments + outright-leg decomposition |
| `features.py` | point-in-time feature matrix (22 features: curve, COT, cracks, macro, …) |
| `models.py` | 7-model per-cell competition + quantile bands |
| `live_ranker.py` | classify → predict → rank; **applies the tuned exit rule** (TP/SL/time-stop). Phase 3.1: additive `live_actuals`/`live_curve_m1m12` overrides |
| `live_feed.py` | Phase 3.1 — reads the live 15-min bar share, builds real spreads + curve by expiry ordering |
| `live_engine.py` | Phase 3.1 — overlays the live snapshot onto the ranker → "what would it trade now" |
| `signal_log.py` | Phase 3.1 — persists every live opportunity + subsequent-performance MTM (`signal_log` table) |
| `walkforward.py` | expanding-window backtest; writes trade tapes + `walkforward_report.json` |
| `exit_sim.py` · `exit_tuning.py` · `exit_robustness.py` | TP/SL simulator · tuning sweep · OOS robustness |
| `ab_test.py` | pooled-vs-gated live A/B harness |
| `methodology_pdf.py` | mentor-facing PDF |

---

## 4. API · Env · Data

**API (37 endpoints).** Groups: health · prices/charts · models · fundamentals · news/intel ·
risk/structure · paper trading (`/api/paper/*`) · **regime engine** (`/api/regime`,
`/api/regime/recommendation`, `/api/regime/backtest`, `/api/regime/drill/<spread>`,
`/api/regime/walkforward`, `/api/regime/ab[/tick|/reset]`) · RAG (`/api/ask`).
*New endpoint pattern:* add a Pydantic model in `backend/schemas/` → register it → return via
`respond(...)` → run `python scripts/generate_ts_types.py`.

**Env keys (`.env`, gitignored).** `EIA_API_KEY`, `FRED_API_KEY`, `GROQ_API_KEY`, `NEWSAPI_KEY`,
`MARKETAUX_KEY`, `APIFY_API_TOKEN`, `AISSTREAM_API_KEY`, `SENTRY_DSN`/`VITE_SENTRY_DSN`,
`BETTER_STACK_TOKEN`. Optional regime flags: `PULSE_REGIME_MODE=pooled`, `PULSE_GATED_BLEND=1`,
`PULSE_GATED_SIZE=full|half|kelly`, `PULSE_AB_TEST_DISABLED=1`.

**/Data lake.** Brent C1-C31 daily settlements (real); WTI C1-C6 (synth from 1-min mids → flagged
ESTIMATE via `data_lake.get_wti_settlements()`); 1-min mids (Brent/WTI/HO/Gasoil); spread/OHLCV xlsx.
Converted to `Data/parquet/` for DuckDB. Research caches (COT, FRED/external, crude stocks) live in
`backend/data/research/`.

---

## 5. Gotchas (load-bearing)

**Dev loop**
1. Frontend edits don't show until `npm run build` (app serves `backend/static/`). Use `npm run dev` for HMR.
2. Two python processes on :5000 = stale code running — `taskkill /F /PID` both before restarting.
3. Never edit `frontend/src/**/*.tsx` via PowerShell (mangles multibyte chars) — use the Read/Edit tools.
4. Run the walk-forward with `python -u`; it writes the report *before* the final summary print, which
   trips cp1252 on the `μ` glyph (cosmetic only).

**Fresh-machine setup** (everything below is gitignored — restore or rebuild)
5. `.env` must be named `.env` (not `env`). Needs `xlrd` for COT `.xls`; if `external_history.parquet`
   is missing FRED columns, rebuild with `python -m backend.research.external_history`.
6. Model pkls (`backend/data/research/models*/`) — copy from another machine or rebuild via
   `python -m backend.research.models --mode composite|pooled`.

**Regime-engine invariants** (asserted by `tests/test_invariants.py` — run `python -m pytest tests/`)
7. **Gate rule** is mirrored: `live_ranker._pooled_passes_gate` ↔ `walkforward._pooled_passes_gate`
   (`GATED_WINNERS`, `GATED_Z_THRESHOLD`, `ROLLING_WIN` must match bit-for-bit).
8. **Tuned exit rule** lives in `live_ranker.py` (TP/SL frac + excluded spreads) **and** `paper_trading.py`
   (`TUNED_MAX_HOLD_TRADING_DAYS` mirrors `live_ranker.TUNED_MAX_HOLD_DAYS`). The walk-forward deliberately
   still trades all 6 spreads at p50/1.5σ/20d — **do not** fold the exit rule into it (separate layers).
9. A/B cost table `ab_test.COST_PER_SPREAD_RT` mirrors `walkforward.COST_PER_SPREAD_RT`.
10. Composite regime labels contain `/` → `models._safe()` maps it to `-` for pkl filenames.
11. WTI settlements are synth/ESTIMATE — swap in a real daily file inside `data_lake.get_wti_settlements()`.

**Live feed (Phase 3.1)**
14. **Reading the live SQLite WAL feed over a share → read a LOCAL snapshot, never the share file in place.**
    The recorder writes `.db` + a live `-wal`; opening that over the SMB share raises `database disk image is
    malformed` (WAL relies on a memory-mapped `-shm` index that doesn't work over network filesystems; the
    on-share `-shm` is also stale vs the `-wal`). Worse, the old in-place `mode=ro` open could *hang a thread
    uninterruptibly* (→ an unkillable process squatting the port). Fix (2026-06-16): `live_feed._open_feed_local`
    → `_snapshot_feed_locally` copies the `.db` (+ **best-effort** fresh `-wal`, **never** the stale `-shm`,
    clearing any stale local sidecars) to a temp dir and reads the copy, integrity-guarded + memoised per sweep.
    db-only is a checkpointed image (≤1 checkpoint-interval stale); db+wal recovers the freshest bars and SQLite
    rebuilds the `-shm`. Don't reintroduce a direct share read.
15. **`PULSE_LIVE_FEED_DIR`** overrides the default share path. The Oracle deploy can't see `I:\` — set it
    to a synced local dir there, or run the live engine on an office PC. `PULSE_LIVE_SIGNALS_DISABLED=1`
    turns off the scheduler jobs.
16. **Contract ordinal mapping is by expiry, not month code** — Brent front is Q26, WTI front is N26 in the
    current feed (earlier months rolled off). `live_feed.list_contracts` sorts by decoded expiry so c1=front.

**Deployment (Phase 3.D)**
12. gunicorn MUST stay `--workers 1` (scheduler must be singular) and **no `--preload`** (APScheduler
    threads don't survive `fork()`); the scheduler starts in `wsgi.py`, not app.py's `__main__`.
13. `backend/db` bind-mount must be writable by the container uid (`PULSE_UID=$(id -u)` or chown 10001).
    The app is internal-only behind Caddy; basic auth gates everything except `/api/health`.

---

## 6. Conventions

- **One sprint per session** — read this file, do the sprint, update §1, stop. Don't multitask sprints.
  *(Full session rules + a copy-paste prompt for every pending task live in [`docs/ROADMAP.md`](docs/ROADMAP.md).)*
- **Honesty over polish** — every number traces to a named source; stale data shown as stale; report
  failures plainly (the walk-forward & robustness verdicts are deliberately graded, not spun).
- **Interpretability over R²** (mentor mandate) · **type safety on the backend↔frontend seam**
  (Pydantic → generated TS) · **ship narrow, then broaden**.
- **Git:** branch off `main`, PR back. Last shipped: PR #3 (Phase 2 engine). `main` is the default branch.
- **End-of-turn footer** (when a sprint ships): one line recommending *continue here* vs *new chat*, plus a
  ready-to-paste prompt for the next task.

---

*Deep-cleaned 2026-06-14: history moved to `docs/PHASE_HISTORY.md`; dead docs removed; tree committed on a clean branch.*
