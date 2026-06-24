# PULSE — Project State

**PULSE** — Energy Intelligence Terminal (Futures First internship). A live energy-trading
dashboard: ingests ~35 data sources, runs quant models (fair value + a regime-conditional
spread engine), and serves a React dashboard with a paper-trading book.

- **Stack:** Flask 3 · React 18 + Vite + Tailwind · SQLite (cache + paper book) ·
  DuckDB/Parquet over a 3.5 GB `/Data` desk feed · sklearn + XGBoost/LightGBM/CatBoost
- **Run (local):** `python start.py` from the repo root → http://127.0.0.1:5000
- **Last updated:** 2026-06-24 (**News Impact Sprint 3 — GEOPOLITICAL earns a measured beta.** Re-classified
  ~1/3 of the NOISE corpus with Groq 8b (70b's daily token cap was exhausted), cutting NOISE 80%→72% and
  growing GEOPOLITICAL 317→520 headlines → at the 1d horizon it goes **t=1.54 (prior) → t=3.05, β=+0.87 %/unit
  (MEASURED)**; t rose with n, so 8b recovered real geo-oil headlines (not noise). `impact.score_headline` now
  serves a measured % move for geopolitical headlines instead of a prior. Also fixed a recurring
  `pulse_cache.db` corruption at root (`.gitattributes` marks binaries `binary`) + tightened backfill themes to
  oil-only (`OIL_CORPUS_THEMES`). Still open: corpus span 2021-only (GDELT coverage backfill 429s from the
  office IP), remaining NOISE best re-done with 70b once its cap resets. Prior: **Sprint 2: event study + the %
  move.** Turns the Sprint-1
  GDELT headline corpus into an empirical headline → expected Brent % move: `event_study.py` fits a per-factor,
  curve-regime-gated beta from the +1h/+4h/+1d forward return regressed on a signed crude-sentiment lexicon;
  `impact.py` serves it through a **prior-then-learn gate** (measured beta only when |t|≥2 on ≥12 headlines,
  else a labelled prior). New **News Impact tab (hotkey 8)** + `/api/news/impact` & `/api/news/factors`.
  **Graded verdict:** on the corpus we could pull — **2,999 headlines, 2021-01→09 only** (GDELT IP-soft-banned
  the historical backfill mid-pull; Groq 70b's daily token cap forced a fall to 8b + keyword, 80% NOISE) — **no
  factor clears |t|≥2 at the 1d horizon, so every factor falls to its prior.** Signs are economically sensible
  (GEOPOLITICAL +0.47 %/unit) but the thin/noisy tape doesn't earn a measured beta yet; the pipeline is the
  deliverable, a broader/better-timestamped corpus is the unlock. 168 pytest pass (+16 hermetic). Prior: Phase 8
  — per-spread gate lifted the regime book +0.298 → +0.374 NET Sharpe to baseline parity (+0.372) by enabling
  regime on exactly {wti_m1_m2, wti_fly_123})
- **Live:** https://rohithpranav45-pulse.hf.space (free HF Space, A/B book accumulating 24/7 — **Phase 8 deployed + verified live 2026-06-22**; regime endpoints healthy, `/api/regime/perspread_gate` serving, `PULSE_GATED_BLEND=1` set so the live per-spread gate is active. Runs on the baked parquet lake, so `as_of` = latest baked settle, not the desk `I:\` live feed)

> 🧭 **Three docs, one per tense:**
> **this file = present** (current state · how to run · architecture · gotchas) ·
> [`docs/ROADMAP.md`](docs/ROADMAP.md) **= future** (pending tasks · timeline · copy-paste session prompts) ·
> [`docs/PHASE_HISTORY.md`](docs/PHASE_HISTORY.md) **= past** (full sprint-by-sprint log) ·
> [`docs/DASHBOARD_REBUILD.md`](docs/DASHBOARD_REBUILD.md) **= active plan** (Phase 4 — 9 tabs → 6 tabs, one phase per session).

---

## 1. Current status

> 📌 **Latest session handoff:** [`docs/SESSION_HANDOFF_2026-06-22.md`](docs/SESSION_HANDOFF_2026-06-22.md)
> — Phase 8 per-spread gate + GARCH risk-layer study + A/B backtest-verdict panel (all merged to `main`
> = `e6b15c4`). Read it for the detailed continuation context + the open next-steps.

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

### ✅ Phase 4 — dashboard rebuild (9 tabs → 6 tabs) (4.A–4.H shipped, 2026-06-17)
Full plan: [`docs/DASHBOARD_REBUILD.md`](docs/DASHBOARD_REBUILD.md). Final structure: **DESK · CHARTS ·
MARKETS · PAPER · REGIME · SIGNAL LOG**, hotkeys `1`–`6` contiguous (plus `Cmd/Ctrl+1..6` that
fires even inside text inputs). Charts kept as-is per user; HF deploy frozen until mentor verdict
on strategy direction is in.
- **4.A** ✅ DESK landing + RiskPanel.
- **4.B** ✅ Relocated PriceDecomposition / IndicatorDrillDown / GeoRiskCalculator → DESK; Signal tab deleted.
- **4.C** ✅ MARKETS tab folds in Spreads & Fundamentals via lazy `<details>` sections.
- **4.D** ✅ Playbook tab folded into the existing Regime drill modal's `AnalogsTable`; sidebar 8 → 7.
- **4.E** ✅ (this session) Intelligence tab cut entirely. `frontend/src/views/IntelligenceView.tsx`
  deleted (366 LOC gone — the view was self-contained, no shared panels to mop up); `Sidebar.tsx`
  drops the `intelligence` `NAV_ITEMS` entry + `ViewKey` member + `Brain` icon import → 7 → 6
  sidebar entries; `App.tsx` drops the import + switch case, hotkey map renumbered 1-6, coalesce
  catches legacy `pulse.view='intelligence'` → `'desk'`. `DeskView.tsx` local `ViewKey` type
  drops `intelligence`. `OnboardingTour.tsx` "Seven workspaces" copy → "Six workspaces" with the
  new tab list. Bundle: 1,172 → 1,157 kB JS (–15 kB). Preview confirmed legacy redirect.
- **4.F** ✅ (this session) Polish layer. **Cmd/Ctrl+1..6** added to the keyboard `useEffect` —
  the modifier variant fires anywhere (including inside `<input>` / `<textarea>`), bare `1..6`
  still only fires outside form inputs. **`?` opens a help overlay** (new `HelpOverlay` component
  in `App.tsx`) listing every shortcut + the Cmd/Ctrl variant (auto-shows `⌘` on Mac, `Ctrl`
  elsewhere); **`Esc` closes it**; the existing `/` ChatDock binding still intact. **Error chips
  + live freshness chip on `Panel.tsx`**: new `lastSuccess?: number | null` + `fetchError?:
  unknown` props render a `● N s ago` pill (or `◌` after 90s = stale) and a red `⚠ ERR` pill on
  fetch failure; backwards-compatible — every existing Panel call still works without touching
  the new props. Wired through the highest-traffic panels first: `HeroPick` and
  `OpenPositionsStrip` on DESK (each now exposes `lastSuccess`/`fetchError` from `usePolling`),
  `SignalLogPanel`. Each of those also gained an **explicit empty-state card** ("Regime endpoint
  unreachable: …" / "Paper book endpoint failed: …" / "No signals logged yet for filter X") in
  place of the infinite skeleton. Panel `staticMount` already gates per-panel framer-motion mount
  animations from re-firing on poll-refresh; DeskView already opts in across the board, so the
  "no animation on poll refresh" acceptance was already met. Theme persistence
  (`useTheme` → `useLocalStorage('pulse.theme')` → `data-theme` on `<html>`) is unchanged.
- **4.G** ✅ (this session) Signal Log session dedup. Schema migrated v1 → v2: dropped the per-bar
  UNIQUE `(instrument, direction, feed_as_of, cadence)`; added `opened_at_session TEXT NOT NULL`
  + `last_seen_at TEXT` + `bar_count INTEGER NOT NULL DEFAULT 1`; new UNIQUE
  `(instrument, direction, opened_at_session)`. Migration `_migrate_to_v2` is the
  create-new → copy → drop-old → rename dance wrapped in `BEGIN IMMEDIATE`/`COMMIT` so the
  WAL-shared `pulse_cache.db` never sees a half-migrated state; backfills `opened_at_session =
  signal_at`, `last_seen_at = COALESCE(mtm_at, signal_at)`, `bar_count = 1` for the 48 existing
  rows. Idempotent (`ensure_schema` is safe to re-run). DB pre-migration backup at
  `backend/db/_corrupt_backup_<ts>_pre4G/`. New `_record_signal` helper drives the insert path:
  if an OPEN session for `(instrument, direction)` exists → `UPDATE` (bump `bar_count`, refresh
  `last_seen_at`); if the same `feed_as_of` already drove this session → `noop` (daily +
  intraday jobs over the same bar are safe); if an OPEN session in the *opposite* direction
  exists → close it with `close_reason='flip'` and open a new row. `generate_live_signals`
  return shape gained `extended` / `flipped` / `noop` counters alongside `logged`.
  Frontend: `SignalLogPanel.tsx` `SignalRow` interface gained `opened_at_session`, `last_seen_at`,
  `bar_count`, `realised_move`; the Time cell now shows `× N bars` when `bar_count > 1` (tooltip:
  `last seen <ts>`); `closeReasonTone` handles the new `flip` reason → neut. Tests: `test_invariants.py`
  gained `test_signal_log_dedup_keys` (asserts the v2 UNIQUE + the new columns; runs against a
  temp DB, never touches the live cache). New `tests/test_signal_log_session.py` has three
  behavioral tests — same-direction across 3 bars = 1 row with `bar_count=3`; same `feed_as_of`
  repeated = `noop`; direction flip = 2 rows with the first row CLOSED/`flip`. **13 tests green
  total** (10 invariants + 3 session tests), `npm run build` clean (1,162 kB JS / 40.3 kB CSS).
  Preview SIGNAL LOG shows 6-entry sidebar + table with the new error-pill chip lit (the dev
  Flask endpoint is offline in this preview), backfilled rows render at `bar_count=1` (badge
  hidden) — the badge will start showing once the live engine re-fires post-migration.
- **4.H** ✅ (this session) Calibration plot on REGIME tab. New backend endpoint
  `GET /api/regime/calibration?include=pass|all` reads `backend/data/research/gated_trades.json`,
  bins by `|z|` (cutoffs `0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, ∞`), and returns per-bin
  `{z_lo, z_hi, n, reverted_frac, mean_fwd_pnl}` where reverted = `fwd_pnl > 0` over the
  20-day walk-forward window. `include=pass` (default) restricts to trades the live engine
  would actually have fired (`gate=pass` rows, 1,527 trades vs the 9,946 total); `all`
  exposes the full baseline tape. Overall reverted = 60.7% across pass rows; bins are
  monotonic 52.8% → 71% as |z| climbs, which is the well-calibrated story we want the
  mentor to read at a glance. New `frontend/src/components/panels/CalibrationPanel.tsx`
  renders each bin as a labelled bar with a centered 50% reference line, tone-coded
  (bull ≥ 60% / neut 50-60% / bear < 50%) and a faint sample-size chip on the right edge;
  hover tooltip on each bar reads exactly: `"When the model said z=X, the spread reverted
  Y% of the time in 20 days (n trades)."` per the mentor's acceptance criterion.
  `regimeCalibration(include)` added to `api.ts`; panel wired into `RegimeView.tsx` between
  `RegimePickCard` and `ABComparePanel`. Panel uses the 4.F freshness/error chip props
  (verified in preview — offline state correctly renders `⚠ ERR` + "Calibration endpoint
  unreachable: HTTP 502" copy). Test-client hit returns `200` with the populated bins.
  13 pytest green, `npm run build` clean (1,166 kB JS / 40.7 kB CSS).
- **Next session** — Phase 4 fully complete locally (4.A → 4.H). Hold for mentor strategy
  verdict before any HF redeploy; architecture changes still deferred.

### ✅ Live feature overlay — fixes stale-feature blow-up (2026-06-18)
The live engine scored the global model on `df.iloc[-1]` — the latest *daily* feature row,
frozen at **2026-05-26** (the /Data daily file stopped advancing). Only the z-score numerator
(live spread) + regime one-hot were live; the **feature vector predicting fair value was 3 weeks
stale**, so fair value reflected late-May while `actual` was today → z-scores blew out to **−11σ /
−7σ** and tripped the `|z|>8` sanity gate. Root symptom, not a model bug.
- **New `backend/research/live_features.py`** — `build_overlay(snap_co, snap_cl=None)` recomputes
  today's **fast** features from the live snapshots: `brent_close, m1_m12, m1_m12_sq, curvature,
  m1_m2_lag1/m3_m6_lag1/fly_lag1, wti_close, wti_m1_m12, wti_brent_spread (=wti_c1−brent_c1, matches
  features.py sign), wti_*_lag1, sin_doy, cos_doy, days_to_expiry`. **Slow** features (inv/COT/cracks/
  real_rate/ovx_vix/realised_vol_20d/brent_ret_5d) stay carried-stale and are reported honestly in a
  `feature_overlay` meta block — no live source on this feed, and a 3-week carry on a weekly series is
  a far smaller error than on the front price. `*_lag1` cols map to the freshest live spread level.
- **Wiring:** `live_ranker.get_recommendation` gained an additive `live_feature_overlay` kwarg —
  default `None` reproduces the daily/A-B path **bit-for-bit**; when present it merges the overlay onto
  a copy of `latest_features` before `predict()`. `live_engine.get_live_recommendation` builds the
  overlay and passes it; the overlay propagates automatically to `/api/regime/live`,
  `signal_log.generate_live_signals`, and `intraday_replay` (all call `get_live_recommendation`).
  Response carries `overlaid_features` + `live_feed.feature_overlay`.
- **Verified on the live 06-18 feed (laptop sees `I:\`):** brent_m1_m2 fair **$2.91 → $0.24**
  (live spread $0.20), z **−11.29 → −0.16**; wti_m1_m2 z **−6.89 → +0.48**. All four spreads now
  in-distribution; top credible signal = **wti_fly_123 SELL z=+2.10 (LightGBM)** instead of the absurd
  −11σ. The `|z|>8` gate no longer fires spuriously.
- **Tests:** new `tests/test_live_features.py` (6 tests — overlay correctness, lag mapping, WTI sign,
  calendar formula, unavailable-snapshot no-op, describe_overlay). **23 pytest green** (17 + 6).

### ✅ Adaptive per-spread sanity cap (2026-06-18)
The signal-log sanity gate was a flat `|z|>8` — one-size-fits-all. New
`signal_log.adaptive_z_caps()` derives a **per-spread** cap from each spread's own |z| distribution
across the full walk-forward OOS tape (`global_trades.json`):
`cap = clip(quantile(|z|, 0.995) × 1.5, floor 4.0, ceil 10.0)`, where `z = (actual−fair)/std(resid)`
— the same resid_std the live z is normalised by, so the cap is directly comparable to a live z_score.
Cached per process; falls back to the flat `_SANITY_Z_CAP` when the tape is absent. Computed caps:
brent_m1_m2 **8.02** · brent_m3_m6/fly **7.35** · wti_m1_m2 **10.0** (synth-offset headroom) ·
wti_m3_m6 **7.33** · wti_fly_123 **6.27** (tighter — that spread never exceeds ~4σ OOS). The flat 8
both over-suppressed wti_fly_123 and under-suppressed wti_m1_m2; the adaptive cap fixes both.
`generate_live_signals` uses `z_caps.get(spread, _SANITY_Z_CAP)` per row and returns the applied
`z_caps`. **Tests:** 3 added to `tests/test_signal_log_session.py` (per-spread + bounded, tight<wide,
missing-tape fallback). **26 pytest green** (23 + 3).

### ✅ Phase 2 — gated decorrelated selection (2026-06-19)
Mentor directive: take the top-conviction trades but **never double up on correlated/similar bets**
(no risk concentration). New **`backend/research/gated_select.py`** turns the ranker's conviction-sorted
`ranked` list into the desk's actual book via a greedy correlation filter:
- `instrument_corr_matrix(window=504)` — trailing ~2y daily-change Pearson corr across the spread
  universe, cached per-process. The tradeable universe (after the tuned M3-M6 exclusion) is **bimodal**:
  `{brent_m1_m2, brent_fly_123}` ρ≈**0.87** and `{wti_m1_m2, wti_fly_123}` ρ≈**0.76**, everything
  cross-product ≤0.30. So ρ_max=**0.70** admits at most one trade per front-curve cluster.
- `select_decorrelated(ranked, rho_max=0.70)` — greedy: take the highest-conviction actionable
  (BUY/SELL) row, then skip any candidate whose **signed-P&L correlation** with an already-held position
  is ≥ ρ_max. Sign matters: concentration is `Var(pnl_i+pnl_j)=Var_i+Var_j+2·Cov`, so **positive**
  signed-corr = redundant → skip, **negative** = a hedge (lowers book variance) → keep. Opposite-direction
  correlated pairs are therefore retained, same-direction ones dropped. Threshold tunable via
  `PULSE_DECORREL_RHO`.
- **Wiring:** additive `portfolio` block on `get_recommendation()` (`{selected, skipped[{spread,
  correlated_with,rho,reason}], rho_max, window, n_actionable, n_selected}`). `top`/`ranked` untouched →
  the A/B harness, signal_log, dashboard cards are bit-for-bit unaffected; propagates automatically to
  `/api/regime/recommendation` + `/api/regime/live`. Defensive: selection failure logs a warning and
  leaves `portfolio=None` rather than breaking the recommendation.
- **Verified live (06-19 feed):** daily-settle path selects `brent_m1_m2` (only actionable row); live-overlay
  path holds 0 (no spread crosses the z-gate after re-scoring on today's market — correct, not a bug).
- **Tests:** new `tests/test_gated_select.py` (12 — greedy order, same-dir skip, opposite-dir hedge kept,
  cross-cluster both kept, all-4-fire→2 selected, NEUTRAL excluded, unsorted input, max_positions cap,
  env override, inclusive threshold, real-universe bimodal skip-if-no-/Data). **38 pytest green** (26 + 12).
- **Dashboard (REGIME tab, `DecorrelatedBookPanel.tsx`, 2026-06-22).** Surfaces the directive as its own
  first-class panel (under the pick card): the **selected book** (kept positions in conviction order — label,
  direction, z, conviction) + every candidate **dropped for correlation** (struck through, with the signed
  ρ and which held position knocked it out), a `ρ_max` + `N/M kept` header, and a footer explaining
  signed-corr (redundant→skip, hedge→keep) + the bimodal cluster structure. Reads the existing
  `/api/regime/recommendation` `portfolio` block (no backend change) — distinct from the AutoDeskPanel,
  which frames the same book around live market-hours/breaker execution.
### ✅ Phase 3 — live auto-trade desk (2026-06-19)
Mentor directive: "tune on live data so the dashboard auto-takes/closes trades like a desk analyst, 5d/wk
during market hours." New **`backend/research/auto_desk.py`** reconciles the paper book to the gated,
decorrelated live recommendation — reusing every existing layer, no exit logic duplicated:
- `run_auto_desk(*, dry_run=False)` reads `live_engine.get_live_recommendation(include_wti=True)` (so the
  `portfolio` block matches `ranked` — the Brent-only filter that strips `portfolio` is skipped) and treats
  **`portfolio.selected`** as the day's intended book.
- **Two entry gates:** (1) `is_market_open(feed_as_of)` = weekday **AND** feed bar ≤ 90 min fresh
  (freshness is the real gate — holidays/after-hours/frozen-recorder safe; the weekday check is the explicit
  "5d/wk"). (2) `shock_engine.live_stress_state()["breaker_active"]` — on a shock **onset** new entries pause;
  open trades keep running under their 2.5σ stops (the validated 2026-06-19 onset-only behaviour).
- **Reconciliation per tick:** selected + no auto position → **OPEN** (BUY→LONG/SELL→SHORT via
  `paper_trading.push_trade(source="auto_desk")`); selected + same dir → **HOLD** (dedup, one position/spread);
  selected + opposite dir → **FLIP** (`close_trade('flip')` then re-open if entries allowed); held but no
  longer selected → **LEFT** running under its stop. **Exits stay with the existing 60s `mark_to_market`
  sweep** (TP halfway-to-fair / 2.5σ SL / 30-trading-day time-stop) — never re-implemented here.
- **Wiring:** `_auto_desk_tick` scheduler job (15-min, bar-aligned, kicked +8 min after boot), gated by
  `PULSE_LIVE_SIGNALS_DISABLED` (no feed → off) + own opt-out `PULSE_AUTO_DESK_DISABLED=1`. Endpoints
  `GET /api/regime/autodesk` (dry-run preview of the open/flip/hold plan) + `POST /api/regime/autodesk/run`
  (force a real tick).
- **Verified live (06-19 feed):** market_open=true (Fri, fresh 06:45 bar), **breaker_active=true** so entries
  paused, `selected=[]` (live-overlay path holds 0 — correct). ⚠️ **Caveat (carried from §5):** the breaker
  reads `live_stress_state()` which is still as-of the **last daily settle (2026-05-26)** — the GMM needs 20d
  vol the 15-min feed can't yet supply, so the breaker is currently latched on that day's STRESS read
  (conservative: it pauses entries). A live-feed-driven stress read is the remaining Phase-3 polish.
- **Tests:** new `tests/test_auto_desk.py` (14 — market-hours weekday/weekend/stale/no-ts, opens-only-selected,
  BUY→LONG + SELL→SHORT mapping, dedup-holds, breaker-pauses-entries, market-closed-no-entries, flip closes
  'flip' + opens new side, de-selected-left-running, disabled-env short-circuit, feed-unavailable, dry-run
  takes-no-action; hermetic — temp DB + monkeypatched rec/stress, no feed/`/Data`). **52 pytest green** (38 + 14).
- **Next (Phase 4 / 5):** ~~dashboard surfaces + live-feed stress read~~ ✅ (below); then 2.8.7 multi-horizon + feature selection.

### ✅ Phase 4 — auto-desk dashboard surfaces + live-feed stress read (2026-06-19)
Surfaced the Phase 3 live auto-desk on the dashboard and made the shock breaker react intraday:
- **REGIME tab — `AutoDeskPanel.tsx`** (between the shock monitor and the pick card): consumes
  `GET /api/regime/autodesk` (dry-run preview, 60 s poll). Shows the two **entry gates** (market hours
  OK/BLOCK + reason; shock circuit-breaker OK/BLOCK + live P(stress)), the **ALLOWED/PAUSED** verdict +
  open-desk-position count, the **stress-read provenance** (LIVE feed vs daily-settle fallback + reason —
  honest about which is live), the **selected decorrelated book**, and the **open/flip/left-running/skipped
  plan**. A **"Run desk now"** button fires `POST /api/regime/autodesk/run`. `api.regimeAutodesk` /
  `regimeAutodeskRun` added.
- **PAPER tab — auto-desk provenance.** `Position.source` already carried `auto_desk`; added an **`⚙ auto`
  badge** on every desk-opened row (open + closed tables) and a **source filter** (All / Auto-desk / Manual)
  scoping both tables. Hero KPIs stay on the whole book (filter only scopes the tables).
- **Live-feed-driven stress read.** New `live_feed.recent_daily_frame("CO")` resamples the 15-min feed to a
  daily c1/c12 close frame; `shock_engine.live_stress_state(use_live_feed=True)` scores the fitted detector
  on those **consecutive live daily closes** so the breaker reacts intraday. It **only engages once the
  recorder has ≥ `MIN_LIVE_STRESS_ROWS` (6) usable feature rows** (~26 raw daily closes for a clean 20-day
  vol window); otherwise it **falls back to the daily-settle read** with an explicit `live_fallback_reason`
  (a naive splice of today's price onto the weeks-stale settle would count the gap as one return and
  spuriously spike vol). `auto_desk` now calls it with `use_live_feed=True`. **Verified live (06-19):** feed
  has 6 daily closes → falls back honestly (`source=daily_settle`, breaker off the 2026-05-26 read); the
  live path is unit-tested with a synthetic 45-row feed and **auto-upgrades** as the recorder accumulates.
- **Tests:** new `tests/test_live_stress.py` (5 — `recent_daily_frame` resample + no-feed, live-engages /
  thin-history-fallback / feed-absent-fallback; stress-state tests skipif no `/Data`). **57 pytest green**
  (52 + 5). **Frontend `npm run build` (vite) ✓ + `tsc --noEmit` ✓ — both clean (exit 0)** via the portable
  Node at `~/nodejs` (3044 modules → `backend/static`, 1,204 kB JS). The new AutoDeskPanel + PaperView
  additions add zero type errors, AND the 8 pre-existing baseline `tsc` errors were fixed this session:
  `motion.ts` (framer-motion v11 dropped `Transition['ease']` → typed the curves as `Easing`),
  `SpreadChart.tsx` (dead `?? .t` fallback removed), `ChartsView.tsx` (`width: 1 as const` for the strict
  `LineWidth` union), `HealthPill.tsx` + `PaperView.tsx` (fetcher return types adapted to the local
  row/perf shapes the views use vs the looser generated API types). Build script is still `vite build` only
  (no `tsc` gate), but the tree now type-checks clean.
- **Next (Phase 5):** 2.8.7 multi-horizon sweep + feature selection (robustness polish). ✅ shipped below.

### ✅ Phase 5 — robustness: multi-horizon sweep + feature selection (2026-06-19)
Two **additive research legs** on the walk-forward (same standalone-merge pattern as `--global-only`/
`--soft-only` — no 3 h full re-run, no touch to the gate/exit invariants in `tests/test_invariants.py`).
Both write to `walkforward_report.json` + persist a trade tape. Methodology PDF regenerated (Phase 5 section
added, +3.4 kB → 23.3 kB).
- **2.8.7 multi-horizon sweep** (`python -m backend.research.walkforward --horizon-only`, ~5 s).
  The walk-forward fixes a 20-day forward horizon, but the models predict the **contemporaneous fair value**
  → the entry signal (z→direction) is horizon-independent; only the hold/exit horizon changes realised PnL.
  So the sweep is **pure post-processing** over the persisted `baseline_trades.json` + `global_trades.json`
  tapes: recompute `fwd_pnl = sign × (spread[d+H] − spread[d])` at **H ∈ {5,10,20,30}d** from the rebuilt
  spread series, NET of the same per-spread RT cost (horizon-independent — one round trip), Sharpe annualised
  √(252/H). Validates against the headline: recomputed 20d NET = baseline **+0.372** / global **+0.380**,
  bit-for-bit the documented numbers. **Finding — the two engines' edges live at different horizons:** the
  regime-unaware **baseline reverts slowly**, NET Sharpe climbing monotonically to a peak at **30d**
  (overall **+0.530** vs +0.372 at 20d; *every* spread peaks at the 30d bound). The **global regime model
  carries a faster signal**, peaking around **10d** (overall **+0.451** vs +0.380 at 20d) with the front
  spreads (brent_m1_m2) peaking at **5d** (+0.756) and decaying after. Corroborates the live 30-day time-stop
  on the baseline-led book; says the regime overlay should be harvested faster where used. **Honest caveat:**
  daily fills overlap and *longer* horizons overlap more, so the 30d Sharpe is the most overlap-inflated —
  read the **ranking** across H, not the level; it does **not** overturn the headline (baseline still wins at
  every common horizon). Block: `report["horizon_sweep"]` (per-source `overall_by_horizon` + `by_spread` +
  `best_horizon_by_spread`); tape `horizon_trades.json`.
- **Feature selection — Lasso stability selection** (`--featsel-only`, ~14 min, retrains the global leg).
  The global leg trains on all 22 (Brent) / 24 (WTI) base features + 9 regime one-hots. Lean set picked by
  **Meinshausen-Bühlmann stability selection**: a scaled Lasso is fit per spread at every refit cutoff; a base
  feature is kept if its non-zero-coef **selection frequency** across the 34 refits ≥ **50%** (floor: top-6 by
  mean |coef|); the 9 regime one-hots are always retained. Lean per-spread sets re-run through the global
  walk-forward → `global_lean`. **Verdict (graded, in the Phase 2.8.x tradition): a leaner set does NOT hold
  the NET headline.** Lean-global NET Sharpe **+0.308** trails both full-global **+0.380** and baseline
  **+0.372** (cost ~0.07, driven by the WTI M-spreads where the dropped features were load-bearing —
  wti_m3_m6 +0.32→−0.05, wti_m1_m2 +0.46→+0.31). It **is** a real **interpretability** win where the edge
  concentrates: the butterflies prune hardest (**brent_fly_123 keeps just 8/19** — curvature, calendar, lags,
  COT, cracks) and lean even **beats** full-global on both flys + brent_m1_m2 (+0.24→+0.43). Stability
  selection at the 50% threshold trades a small NET loss for interpretability rather than a free lunch — **the
  full feature set stays the recommended default.** Blocks: `report["global_lean"]` + `report["feature_selection"]`
  (per-spread `selected`/`freq`/`mean_abs_coef`) + `costs.global_lean_net` + lifts vs baseline/full-global;
  tape `featsel_trades.json`.
- **Plumbing:** `_train_global_through`/`_produce_global_trades` gained an additive `base_feats_by_spread`
  kwarg (default `None` reproduces the Phase 2.8.4 global leg bit-for-bit). New CLI flags `--horizon-only` /
  `--featsel-only`. **Tests:** new `tests/test_phase5_research.py` (9 — horizon recompute directions/edges,
  annualisation + cost, best-horizon eligibility gate; Lasso stability keeps the dominant feature, floor when
  nothing stable, lean-feature override threading + default-None full set). **66 pytest green** (57 + 9).
- **Next (Phase 6):** ~~2.8.9 HMM / change-point regimes~~ ✅ (below) + 2.8.10 portfolio vol-targeting.

### ✅ Phase 6 — data-driven HMM / change-point regimes (2.8.9) (2026-06-19)
Mentor question: **are the hard trader thresholds even the right regimes?** The Phase 2 grid splits the
curve axis on hard cuts (CONTANGO ≤ −$2 < NEUTRAL ≤ +$5 < BACK). This leg replaces them with a **fitted**
detector and tests whether data-driven regimes beat baseline + the hard-threshold variants on NET Sharpe.
Additive leg, same standalone-merge pattern as Phase 5's `--horizon-only`/`--featsel-only` — no 3 h full
re-run, no touch to the gate/exit invariants in `tests/test_invariants.py`.
- **New `backend/research/regime_hmm.py` — `CurveRegimeHMM`.** GMM + **causal sticky-HMM forward filter**
  over `[m1_m12, curve_chg_5d]` (curve level + its 5-day change = the change-point/momentum signal a static
  threshold is blind to). Mirrors `shock_engine.StressDetector` exactly (sklearn.mixture only, no new dep).
  States relabelled **ordinally by curve level** (R0 = deepest contango) so cells are stable across refits;
  forward filter at day d uses only data ≤ d (look-ahead-free). `state_summary()` exposes the data-driven
  boundaries vs the hard −$2/+$5 cuts. Standalone: `python -m backend.research.regime_hmm`.
- **Wiring (`--hmm-only`, ~30 min for the K-sweep).** `_train_cells_through` / `_evaluate_window` gained
  additive `regime_col` / `regime_list` / `enable_boosters` overrides (default `None` reproduces
  composite/pooled **bit-for-bit**). `_produce_hmm_trades` fits the detector per refit on ≤cutoff, labels the
  window causally, runs the **same 7-model per-cell competition** (boosters on, like pooled) over the
  discovered R-states — same 20-day horizon, same NET cost model, same 34 refits. Headline **K=3** (matched
  to the 3 hard buckets) drives the costs/lift wiring; **K∈{2,3,4}** sweep stored under `hmm["state_sweep"]`.
  Blocks: `report["hmm"]` (+ `detector.mean_boundaries`, `state_sweep`, `by_regime`) + `costs.hmm_net` +
  lifts vs baseline / **pooled** / **global**; tape `hmm_trades.json` (10,485 rows, headline K).
- **Verdict (graded, Phase 2.8.x tradition): data-driven regimes do NOT unseat the headline.** HMM K=3 NET
  Sharpe **+0.289** trails baseline **+0.372** and global **+0.380**, and ~ties hard pooled **+0.293** /
  gated_blend **+0.298**. State sweep: K=2 +0.279 · **K=3 +0.289** · K=4 +0.201 (more states overfit). So
  *learning* the boundary from data doesn't beat the hard cuts either — consistent with 2.8.4 (global ties
  baseline) and 2.8.5 (soft ties hard pooled): on this 6-spread universe the regime **partition is not the
  binding constraint**. **But two honest positives:** (1) the detector **relocates the contango cut from the
  trader's −$2 toward zero** (mean K=3 boundaries **−$0.81 / +$3.34** vs −$2 / +$5) — a defensible
  interpretability result; (2) it's a **front-curve win** — beats both baseline and pooled on brent_m1_m2
  (**0.83** vs 0.67 / 0.52) and wti_m1_m2 (**0.45** vs 0.26 / 0.26), but loses on the deferred carries
  (brent/wti M3-M6) and trails baseline on both flys, which is why the headline nets out below baseline.
- **Tests:** new `tests/test_phase6_research.py` (9 — ordinal relabel by curve level, state count,
  causal labelling [prefix-stable under future appends], burn-in→UNKNOWN, too-few-rows guard, regime-source
  override threads through `_train_cells_through`/`_evaluate_window`, default-args unchanged, `_aggregate_hmm`
  shape + detector block). **75 pytest green** (66 + 9). Methodology PDF regenerated (Phase 6 section,
  +2 kB → 25.3 kB).
- **Next (Phase 7):** ~~2.8.10 portfolio vol-targeting~~ ✅ (below).

### ✅ Phase 7 — portfolio vol-targeting (2.8.10) (2026-06-22)
Mentor directive (last open Phase 2.8.x model leg): **scale the book's per-spread notionals to a target
portfolio vol.** Additive **post-processing** leg over the persisted gated tape (same standalone-merge
pattern as Phase 5/6 — no retrain, no touch to the gate/exit invariants in `tests/test_invariants.py`).
New **`backend/research/vol_target.py`** reweights notionals by reusing the two shipped risk primitives:
- **`shock_engine.risk_scale`** — per-position **vol-target × stress de-risk**: `vol_scale = clip(target_pos_vol
  / forecast_vol_i, floor, cap)` (equalises each spread's $/bbl risk so a $-vol fly stops dominating a tight
  front spread) `× (1 − derisk·P(stress))` (cuts size INTO a shock). `forecast_vol_i` = trailing 20d realised
  $/bbl vol of the spread (causal); `P(stress)` from the GMM+sticky-HMM detector fit 2016→2019.
- **`gated_select.select_decorrelated`** — the desk's decorrelated book (conviction = |z|; signed-corr filter).
- **Portfolio overlay** — one factor `k = clip(target_book_vol / book_vol, 0.25, 2.0)` where `book_vol` is the
  ex-ante vol from the kept positions' risks + the trailing corr matrix (signed by direction, so a hedge lowers
  it). Adds exposure to a thin/hedged book, trims a full/correlated one → targets *portfolio* vol.
- **Wiring (`--voltarget-only`, ~5 s).** `run_voltarget_only` runs four **ablation variants** (decorrelated →
  +risk_parity → +parity_stress → +vol_target[full]) on the gated tape, each normalised to **mean notional 1.0**
  (matched avg exposure → max-DD comparable; Sharpe/Calmar leverage-invariant). Blocks: `report["vol_target"]`
  (+ `variants`, `config`) + `costs.vol_target_net` + lifts vs gated/baseline; tape `voltarget_trades.json`
  (4,834 held positions, headline variant). Standalone: `python -m backend.research.vol_target`.
- **Verdict (graded): vol-targeting is a drawdown-management tool, not an alpha tool.** On the gated tape
  (NET, matched exposure): gated_raw Sharpe **+0.298** / maxDD **−281** / Calmar **2.55** → full vol_target
  Sharpe **+0.198** / maxDD **−112** (**~60% DD cut**) / Calmar **2.01**. The drawdown reduction does **not**
  pay for the return given up — on risk-adjusted return it trails the un-targeted gated book, and the
  regime-unaware **baseline** (Calmar **4.99**, Sharpe +0.372) stays the headline. Ablation localises it:
  **risk parity** is the biggest single DD-reducer (−215 → −141, caps the high-$-vol fly); the **portfolio
  overlay** is the only layer that *improves* Calmar at the margin (1.52 → 2.01). Per-spread, the reweighting
  lifts the deferred carries/flys (brent_fly 1.02→1.53, wti_m3_m6 0.02→0.62) but craters brent_m1_m2
  (0.61→0.05 — parity up-sizes the low-$-vol front spread, whose small moves get eaten by RT cost).
  For a **DD-constrained** mandate the overlay earns its Sharpe; for a **Sharpe-max** mandate the baseline wins.
- **Tests:** new `tests/test_phase7_research.py` (12 — vol annualisation, book_vol quadrature + hedge-lowers-vol,
  size_day drops NEUTRAL/missing-pnl, risk-parity equalises risk, stress de-risk, decorrelation drops correlated
  same-dir, portfolio overlay levers thin book, apply_vol_target normalises to mean-notional-1 + feeds the cost
  model via sizing_scale, variant-flag config, Calmar/summary; hermetic — synthetic tapes/vol/stress/corr, no
  `/Data`). **87 pytest green** (75 + 12). Methodology PDF regenerated (Phase 7 section, +2.5 kB → 27.8 kB).
- **Phase 2.8.x model backlog now complete** — splitting (2.8.4), softening (2.8.5), long history (2.8.8),
  data-driven regimes (2.8.9), and vol-targeting (2.8.10) all shipped; **baseline remains the NET-Sharpe
  headline across every variant.** Open routes: ~~per-spread gate thresholds where the per-spread lift table
  justifies them~~ ✅ (Phase 8 below); read the live A/B verdict once ≥30 closed trades/arm accumulate.

### ✅ Phase 8 — per-spread gate (2026-06-22)
Mentor directive: the per-spread lift table shows regime conditioning helps **unevenly** across the 6
spreads — replace the single global gate (`regime_pooled==BACK × winner∈GATED_WINNERS × |z|≥0.5`, applied
uniformly) with **per-spread thresholds** where the lift table justifies them, walk-forward validated.
- **The uneven signal (walk-forward `gated_blend_net.by_spread_source`, NET Sharpe regime-leg vs baseline-leg
  per spread):** the regime leg **beats** baseline on the WTI fronts — wti_m1_m2 **+1.22 vs +0.71**,
  wti_fly_123 **+0.97 vs +0.54** — but **loses** on every Brent spread (brent_m1_m2 +0.46 vs +0.72,
  brent_fly_123 +0.75 vs +1.17) and both M3-M6 carries. Firing regime uniformly drags the gated book to NET
  Sharpe +0.298, below the +0.372 baseline.
- **New `backend/research/gate_config.py` — the single source of truth.** `decide_enabled(reg_pnls,
  base_pnls)` = "is regime's annualised NET Sharpe > baseline's by `GATE_MARGIN` (0.0), on ≥ `GATE_MIN_N`
  (20) regime trades?"; `enabled_at_cutoff()` resolves the enabled-spread set from per-spread close-date
  histories (only trades closed < cutoff → no look-ahead); `per_spread_gate_passes(spread, enabled,
  global_gate_pass)` composes the (still-mirrored) global predicate with the per-spread enable set
  (`enabled=None` ⇒ degrades to the Phase 2.6 global gate, so a pre-Phase-8 report stays safe);
  `latest_enabled_from_report()` reads `per_spread_gate.enabled_latest` for live inference. **The global-gate
  predicate stays mirrored as constants in `live_ranker` ↔ `walkforward` (asserted by `test_invariants`); the
  per-spread layer lives ONLY here and is imported by both, so they cannot drift.**
- **Walk-forward leg (`--perspread-gate-only`, ~5 s, no retrain).** `run_perspread_gate_only()` mirrors
  `--voltarget-only`'s standalone-merge: builds per-spread regime/baseline close-date histories from the
  persisted `pooled_trades.json` + `baseline_trades.json`, resolves the enabled set **per refit cutoff**
  (decision uses only trades closed before that cutoff — the `_compute_kelly_by_cutoff` pattern, genuinely
  OOS), re-routes the blend per spread, aggregates NET. Blocks: `per_spread_gate` (+ `enabled_latest`,
  `enabled_by_cutoff`, `by_spread_source`) + `costs.per_spread_gate_net` + lifts vs gated / baseline; tape
  `gated_perspread_trades.json` (9,926 rows).
- **Verdict (graded): per-spread gating closes the gap to baseline.** NET Sharpe **+0.298 (global gate) →
  +0.374 (per-spread)** — parity with baseline **+0.372**. The final-cutoff config enables regime on exactly
  **{wti_m1_m2, wti_fly_123}** (wti_m1_m2 since 2025, wti_fly_123 just crossed at the 2026-04-01 cutoff) and
  routes the other four spreads to the rolling-z baseline. **Insensitive to both knobs** (NET 0.374–0.376
  across margin 0–0.25 × min_n 10–30 → not a fitted edge). It does **not** beat baseline (consistent with the
  whole 2.8.x arc — baseline is still the headline) but finally makes the **regime book competitive** by only
  deploying regime conditioning where the per-spread lift table earned it.
- **Live wiring.** `live_ranker` splits the gate into the global predicate + the per-spread enable layer:
  reads `enabled_latest` fresh per call (regenerated report takes effect without restart, like Kelly), default
  **on** (`PULSE_PERSPREAD_GATE=0/off` reverts to the uniform gate). New `gate="spread_disabled"` reason on
  baseline-fallback rows where the global gate *would* have passed but the spread isn't enabled; `gated_summary`
  surfaces `per_spread_gate` (the enabled set) + a human method blurb. Propagates automatically to
  `/api/regime/recommendation` + `/api/regime/live` + signal_log + auto_desk (all call `get_recommendation`).
- **Dashboard (REGIME tab).** Two surfaces: (1) `RegimePickCard.tsx` live indicator — a
  `PER-SPREAD: WTI M1-M2 · WTI FLY` header chip shows the enabled set (tooltip = the method blurb; falls
  back to a `UNIFORM GATE` chip when off/no config), and baseline-fallback rows whose `gate=="spread_disabled"`
  get a distinct **`⊘ SPREAD OFF`** badge (blue) next to `BASELINE`, separate from `fail`/`health_fail`, each
  with a reason-specific tooltip; the gated provenance note explains the layer. (2) **New
  `PerSpreadGatePanel.tsx`** (between the pick card + calibration) — the full verdict: a 3-stat strip
  (baseline +0.372 → global gate +0.298 → per-spread +0.374) + a per-spread decision table (each spread's
  regime-leg vs baseline-leg NET Sharpe as comparison bars, `REGIME ON`/`baseline` chip, Δ). New endpoint
  `GET /api/regime/perspread_gate` (reads the `per_spread_gate` block + `gated_blend_net.by_spread_source`)
  + `api.regimePerspreadGate`. Test-client 200; `npm run build` + `tsc` clean (only pre-existing TS5101
  `baseUrl` deprecation).
- **Tests:** new `tests/test_perspread_gate.py` (14 — Sharpe comparison, sample floor, margin block, no-baseline
  no-block, no-look-ahead cutoff filter, predicate composition incl. None-degrades-to-global, report reader +
  missing-block None, env default-on/opt-out, end-to-end per-spread routing on a synthetic tape; hermetic) +
  2 invariants (`test_perspread_gate_is_single_source`, `test_perspread_gate_degrades_to_global_gate`).
  **103 pytest green** (87 + 16). Methodology PDF regenerated (Phase 8 section, +1.7 kB → 29.5 kB).

### ✅ GARCH conditional-vol — risk-layer study (2026-06-22)
Question from the user: does **GARCH** add value here? Tested it as a graded leg (same standalone-merge
pattern as Phase 7). New **`backend/research/garch_vol.py`** — causal one-step-ahead conditional-vol
forecast (plain GARCH(1,1) + asymmetric GJR-GARCH, Student-t, fit on daily $/bbl spread *changes* via the
`arch` package), refit every 21d with the variance recursion rolled daily between refits, annualised √252 →
a **drop-in for `vol_target.spread_vol_frame`**. Leg: `python -m backend.research.walkforward --garch-only`
(post-processing on the gated tape, no retrain) → `garch` report block + `costs.garch_vol_target_net` +
lifts. **Two questions, two answers:**
- **(1) As a 1-step forecast — no.** On QLIKE (lower=better, next-day variance), the trailing-20d window
  *wins* on the mean (−0.91 vs GARCH −0.70 / GJR −0.64) and on **3/6 spreads**; GARCH/GJR only edge it on
  the two front spreads. Calendar spreads are low-and-stable-vol, where GARCH's clustering edge (strong on
  outright prices) is muted.
- **(2) As the sizing input to Phase 7 vol-targeting — yes, materially.** Feeding GARCH vol into the full
  vol-target overlay lifts the book **NET Sharpe +0.198 → +0.285, Calmar 2.01 → 3.21, max-DD −112 → −93**
  (GJR; plain GARCH +0.277 / 3.03 / −96 — **robust across both specs**). The `decorrelated` (no-vol-scaling)
  variant is identical across all three inputs (+0.251) — clean sanity check. This turns Phase 7 from a
  *Sharpe-losing* DD tool into a *Calmar-improving* one: vol-targeting doesn't need the best point forecast,
  it needs reactivity to vol onset (GARCH leads the lagging window) + sensible cross-sectional risk.
- **Verdict (graded): a real risk-layer refinement, not alpha.** Still **below the baseline headline**
  (+0.372 / Calmar 4.99), so it doesn't change the conclusion — but it's the first lever that makes the
  vol-targeted regime book competitive on risk-adjusted terms. Research-only: the live app never imports
  `garch_vol`; vol-targeting isn't the live default book (the desk trades the decorrelated gated selection),
  so nothing in the live path changes. **`arch==8.0.0`** added to `requirements.txt` (research-only dep).
- **Tests:** new `tests/test_garch_vol.py` (8 — QLIKE loss, frame shape + NaN-prefix, **causal
  prefix-stability** [σ at day t unchanged when future data is appended], annualisation, GJR≠plain,
  accuracy-table shape, degenerate-series no-crash; hermetic, synthetic series, `importorskip('arch')`).
  **111 pytest green** (103 + 8). Methodology PDF regenerated (GARCH section, +1.8 kB → 31.3 kB). Also
  fixed gotcha 4 at the source — `walkforward.__main__` now forces UTF-8 stdout so the →/—/μ summary
  glyphs never crash a cp1252 console.

### ✅ A/B panel — lead with the backtest verdict (2026-06-22)
The A/B panel looked "broken / always blank" — because the **live forward book can't reach a verdict
fast**: the run times out at `MAX_DAYS=14` but a trade holds up to 30 *trading* days (~6 weeks), and it
needs ≥30 *closed*/arm — jointly unreachable, and on the sleepy free HF Space the daily tick barely fires
(2 sessions in 7 days; the keep-alive only pings `/api/health`). So both arms sat at `n_closed=0` → null
metrics → empty cards. **Not a bug; a cadence mismatch.** Fix = surface the answer that already exists.
- **New `ab_test.backtest_verdict()`** — computes the pooled-vs-gated comparison **instantly from the
  walk-forward tapes** (`pooled_trades.json` / `gated_trades.json` / `baseline_trades.json`, NET via
  `walkforward._cost_for`), reusing the existing `_welch_t`. Verdict on **13,758 closed trades**: pooled
  **+0.293** vs gated **+0.298** NET Sharpe, **Welch p=0.74 → statistically tied**; baseline **+0.372**
  is the headline. Conclusion: keep the `gated` default. Cached per process; embedded in `get_report()`
  so `/api/regime/ab` carries `backtest_verdict`.
- **`ABComparePanel.tsx`** now **leads with a Backtest-verdict block** (pooled/gated/baseline NET Sharpe
  tiles + the TIED/winner chip + Welch p + 13.8k-trade count), then shows the live forward book below
  under a "slow confirmation" divider — with an honest **accumulating banner** (opened/closed counts +
  why it's slow) instead of empty dashes. So the panel always shows a real, defensible answer on open.
- **Tests:** new `tests/test_ab_backtest_verdict.py` (5 — verdict shape, verdict↔(welch,sharpe) consistency,
  `get_report` embeds it, Welch helper basics; tape-gated skipif). **114 pytest green** (111 + 3 active).
  `npm run build` + `tsc` clean. **Takeaway for the user/mentor: the pooled-vs-gated question is already
  answered (tied; keep gated; baseline wins) — the live A/B was only ever slow confirmation of that.**

### ✅ HF Spaces — Phase 8 deployed + verified live (2026-06-22)
- **Deployed.** PR #5 (Phase 7+8) merged to `main`; user triggered a Factory rebuild (HF does NOT
  auto-rebuild on GitHub push — it needs Settings → *Factory rebuild*, which shallow-clones the latest
  `main`; deploy/HF_DEPLOY.md §6). Verified live post-rebuild: `/api/regime/perspread_gate` → **200** with
  `{baseline 0.372, global_gate 0.298, perspread 0.374}`, `enabled_latest:[wti_fly_123, wti_m1_m2]`;
  `/api/regime/recommendation` → `available:true, gated_blend:true` (Space var `PULSE_GATED_BLEND=1` set →
  live per-spread gate + decorrelated `portfolio` + `gated_summary` all active); dashboard HTML + the new
  Decorrelated-book / Per-spread-gate panels render.
- **The earlier "broken" state is fully resolved.** The `scikit-learn==1.7.0` + transitive `joblib` fix has
  been in the running image (pkls load fine; `/api/regime/drill/<spread>` returns real analogs). The
  `No module named 'joblib'` symptom is gone.
- **`as_of` = latest baked settle (2026-05-26), by design** — the HF Space runs on the **baked parquet
  lake**, not the office `I:\` 15-min live feed (only the desk process sees `I:\`). So the public Space is
  the A/B book + framework on baked daily settles; the live-feed `as_of` advancing is a desk-only behaviour.
- **Updating going forward:** merge to `main` → **Factory rebuild** the Space (no token on this desk; the
  keep-alive Action only pings `/api/health`, it does not rebuild).

### ✅ News Impact Model — Sprint 3: GEOPOLITICAL earns a measured beta + infra fixes (2026-06-24)
Sprint 3's goal — **broaden/clean the corpus so a factor earns out of its prior** — was **achieved**:
GEOPOLITICAL now clears |t|≥2 at the 1d headline horizon, so the prior-then-learn gate serves a **measured**
beta for it. The coverage lever (more years) stayed blocked, but the **classification-quality lever** (Groq
re-classification) was unblocked mid-session by a user-supplied key and did the job.
- **🩹 Fixed a recurring DB-corruption blocker.** Pulling the Sprint-2 branch onto the desk gave
  `database disk image is malformed` on `pulse_cache.db` — **no `.gitattributes`**, so git's autocrlf smudge
  filter mangled the binary on checkout (blob stayed valid — 2,277,376 B, `integrity ok`, 2,999 rows — but the
  working file came out 1,556,480 B; `git status` showed it *clean* as the clean/smudge filters are
  self-consistent). New **`.gitattributes`** marks `*.db` + all binary assets `binary`; restored from the clean
  blob; a blob-vs-working size scan confirmed only `pulse_cache.db` was hit. Root-caused the chronic corruption.
- **Corpus de-risk:** new **`OIL_CORPUS_THEMES`** (`gdelt.py`) drops `MILITARY` + `WB_MENA_ENERGY` from the
  backfill theme set (generic war/regional news the classifier mislabels GEOPOLITICAL — the Kabul-drone-strike
  problem). `corpus.backfill_gdelt` defaults to the oil-only set (via `functools.partial`, hermetic test
  untouched). Improves the next backfill.
- **Classifier robustness + re-classify path:** `_groq_classify_batch` gained **429 backoff** (honours
  `retry-after`, capped) + **daily-cap detection** (terminal, no pointless retries); new
  **`classify.reclassify_factor(target)`** re-runs Groq over rows *currently* labelled a factor and overwrites
  (Groq-only — skips on failure rather than re-confirming NOISE via keywords; naturally resumable).
- **Re-classification (8b, since 70b's 100k daily token cap was exhausted — `Used 99932/100000`):** 8b-instant
  has a separate budget but a tight **6,000 TPM**, so bulk runs are paced ~5 batches/min. Re-classified ~1/3 of
  NOISE (958 headlines, 32 batches): **NOISE 2,407 → 2,147 (80%→72%)**, GEOPOLITICAL **317 → 520**.
- **Verdict (graded): GEOPOLITICAL earns a measured beta.** At the 1d horizon GEOPOLITICAL goes
  **n=317 t=1.54 (prior) → n=520 β=+0.865 %/unit t=3.05 (MEASURED)**. Critically **t rose as n grew** — random
  NOISE→GEOPOLITICAL relabels would have diluted t toward 0, so 8b is recovering *real* geo-oil headlines the
  keyword fallback had buried, not manufacturing signal. Right sign (bullish-for-crude geo → Brent up). `impact.score_headline`
  now returns e.g. *"Drone strike on Saudi oil pipeline → GEOPOLITICAL, LONG, +0.78% Brent, basis=measured
  (t=3.05, n=520)"* instead of the prior. Other factors stay on priors (still thin). `news_impact_betas.json`
  re-cached; `.env` GROQ key set (gitignored, **not committed**).
- **Still open / honest caveats:** corpus span still 2021-only (the GDELT coverage backfill **429s from the
  office shared IP** — resume from a clean network: `python -m backend.research.news_impact --backfill --start
  2021-09-01 --classify`); remaining ~2,147 NOISE not yet re-done (better to finish with **70b once its daily
  cap resets** — cleaner than 8b); some GEOPOLITICAL growth may include non-oil military news, a known limit of
  the broad-theme 2021 pull (the oil-only theme set fixes it going forward).
- **Tests:** +1 (`test_corpus_theme_set_is_oil_only`); **170 pytest green**. Branch stays
  `phase4-live-feature-overlay` (feature branch, not merged to main).

### ✅ News Impact Model — Sprint 2: event study + the % move (2026-06-23)
Sprint 1 (merged `cf3fbd3`) shipped the timestamped GDELT headline corpus (`news_history` table) + the
8-factor Groq/keyword classifier. Sprint 2 turns that tape into an empirical **headline → expected Brent %
move**, the same conditional-reaction thesis as the inventory framework but the event is a headline.
- **`event_study.py`** — for each classified, timestamped headline, align the Brent/WTI tape and measure the
  **forward return at +1h / +4h / +1d** (intraday 5-min lake for 1h/4h, daily settle close-to-close for 1d,
  asof-matched with a 90-min staleness guard so overnight/weekend headlines drop out). Each headline gets a
  **signed crude-polarity sentiment** ∈ [−1,+1] from a deterministic lexicon (auditable; +1 = bullish for
  crude — draws/outages/sanctions/strong demand). Regress forward return on sentiment **per factor, gated by
  curve regime** (BACK/CONTANGO) → the per-factor beta (% Brent move per +1 unit sentiment) with t/R²/N, plus
  a vol-normalised column (move ÷ horizon-scaled trailing-20d Brent vol). `_ols` cloned from
  `inventory_impact`; `MIN_N=12`, `T_MIN=2`. Caches `news_impact_betas.json`.
- **`impact.py`** — headline → `{factor, direction, expected_%_move, t_stat, regime_context}`. **Prior-then-
  learn gate** (the `gate_config` per-spread pattern): show a **measured** beta only when |t|≥2 on ≥12
  headlines, else a labelled, economically-reasoned **prior** (GEOPOLITICAL 0.90 %/unit … NOISE 0.0) — the
  desk never sees a fabricated-precise number. `impact_feed` ranks recent headlines by |expected move|.
- **API + frontend:** `GET /api/news/impact` (ranked feed) + `/api/news/factors` (per-factor beta table) via
  Pydantic `NewsImpactResponse`/`NewsFactorsResponse` → regen TS. New **News Impact tab (hotkey 8)** +
  `NewsImpactPanel` (feed) + `NewsFactorPanel` (beta table); sidebar 7→8, App hotkey map + help overlay +
  `ViewKey` updated. **Also fixed a latent main bug the TS regen surfaced:** `ABBacktestVerdict` /
  `ABBacktestArm` were hand-patched into `api-types.ts` but never modeled in `schemas/__init__.py`, so the
  codegen would drop them (breaking `tsc`); now properly modeled (`backtest_verdict` on `ABReportData`).
- **Corpus (honest):** **2,999 headlines, 2021-01 → 2021-09** (~8 months). The historical GDELT backfill
  **IP-soft-banned mid-pull** (persistent 429s that session cooldowns wouldn't clear) so coverage capped at
  2021; it's idempotent/resumable to extend later (+ live persistence grows it continuously). All classified:
  **Groq-8b 870 / keyword 2,129** — the 70b model's free-tier **100k daily-token cap was exhausted**, so
  classification fell to `llama-3.1-8b-instant` (separate quota; less reliable at batch JSON → keyword filled
  ~70%). by_factor is NOISE-heavy (2,407/2,999, **80%**) — GDELT's broad MILITARY+energy theme pulls in
  non-oil military news (the Kabul-drone-strike headline classifies GEOPOLITICAL).
- **Verdict (graded, Phase-2.8.x tradition): on this thin/noisy 8-month corpus NO factor clears |t|≥2 at the
  1d headline horizon → every factor falls back to its labelled prior.** Signs are mostly economically
  sensible (GEOPOLITICAL **+0.47 %/unit**, WEATHER +0.43, both right-signed; aligned hit 57% for WEATHER) but
  the t-stats don't clear. 1h flickers significant for DEMAND_MACRO (t=3.16, n=13) and INVENTORY (t=−2.98,
  n=20) — too fragile, and **GDELT seendate lags true publication** so a +1h window can miss the reaction.
  The prior-then-learn gate correctly keeps the desk on priors: **the pipeline is the deliverable; a broader,
  better-timestamped corpus is what's needed before measured betas replace priors.** Endpoints verified via
  Flask test client (`available=True`, n=2999, regime BACK; feed ranks GEOPOLITICAL LONG via prior; 0/9
  measured at 1d).
- **Tests:** new `tests/test_news_impact_event_study.py` (16 hermetic — sentiment lexicon, asof staleness,
  intraday/daily forward returns, curve regime, panel build + no-coverage drop, OLS recovery + min-N,
  factor-table significance flag, prior-then-learn measured↔prior switch, NOISE→NEUTRAL, taxonomy coverage,
  impact_feed ranking, regime-graceful-without-tape). **168 pytest pass** (+16); the 1 failure
  (`test_holiday_shifts_release_to_thursday`) is **pre-existing & unrelated** (a Memorial-Day-2026 holidays
  calendar assertion in `inventory_impact`, untouched by this sprint). Frontend `npm run build` ✓ +
  `tsc --noEmit` ✓ (clean).

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
  binding constraint)* · ~~2.8.7 multi-horizon sweep~~ ✅ · ~~2.8.8 extend walk-forward to 2018-2026~~
  ✅ · ~~2.8.9 HMM/change-point regimes~~ ✅ *(data-driven curve regimes NET +0.289 trail baseline /
  global, tie hard pooled — regime partition isn't the binding constraint; relocates contango cut −$2 →
  −$0.81)* · ~~2.8.10 portfolio vol targeting~~ ✅ *(halves gated max-DD −281 → −112 but trades away NET
  Sharpe +0.298 → +0.198 / Calmar 2.55 → 2.01 — DD-management, not alpha; baseline still wins)*. **Phase
  2.8.x model backlog complete — baseline +0.372 remains the NET-Sharpe headline across every variant.**

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
| Walk-forward, **multi-horizon sweep** (Phase 5, ~5 s, no retrain) | `python -u -m backend.research.walkforward --horizon-only` |
| Walk-forward, **feature-selection leg** (Phase 5, ~14 min) | `python -u -m backend.research.walkforward --featsel-only` |
| Walk-forward, **HMM regime leg** (Phase 6, ~15 min) | `python -u -m backend.research.walkforward --hmm-only` |
| HMM curve-regime detector (standalone) | `python -m backend.research.regime_hmm` |
| Walk-forward, **vol-target leg** (Phase 7, ~5 s, no retrain) | `python -u -m backend.research.walkforward --voltarget-only` |
| Walk-forward, **per-spread gate leg** (Phase 8, ~5 s, no retrain) | `python -u -m backend.research.walkforward --perspread-gate-only` |
| Walk-forward, **GARCH risk-layer study** (~2 min, no retrain) | `python -u -m backend.research.walkforward --garch-only` |
| GARCH conditional-vol forecast accuracy (standalone) | `python -m backend.research.garch_vol` |
| Portfolio vol-target sizing (standalone) | `python -m backend.research.vol_target` |
| Live snapshot from feed (Phase 3.1) | `python -m backend.research.live_feed` (set `PULSE_LIVE_FEED_DIR`) |
| Live recommendation on current market | `python -m backend.research.live_engine` |
| Generate + list live signals | `python -m backend.research.signal_log` · `--update --list` |
| Auto-desk dry-run (plan only) | `python -m backend.research.auto_desk` (`--live` to execute · `--wti`) |
| News corpus backfill + classify (Sprint 1, one-off) | `python -m backend.research.news_impact --backfill --start 2021-01-01 --classify` |
| Fit + cache news-impact event-study betas (Sprint 2) | `python -m backend.research.news_impact.event_study` |
| Score the live news-impact feed (Sprint 2, standalone) | `python -m backend.research.news_impact.impact` |
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
| `live_feed.py` | Phase 3.1 — reads the live 15-min bar share, builds real spreads + curve by expiry ordering. Phase 4: `recent_daily_frame` resamples to a daily c1/c12 frame for the live stress read |
| `live_features.py` | Phase 4 (06-18) — overlays today's fast features (price/curve/lags/calendar) onto the stale daily row so the model scores on the live market; slow features carried-stale + reported |
| `live_engine.py` | Phase 3.1 — overlays the live snapshot onto the ranker → "what would it trade now" |
| `signal_log.py` | Phase 3.1 — persists every live opportunity + subsequent-performance MTM (`signal_log` table) |
| `gated_select.py` | Phase 2 (06-19) — greedy signed-P&L-corr filter → the decorrelated `portfolio` block |
| `gate_config.py` | Phase 8 (2026-06-22) — per-spread gate: shared decision logic (regime fires per spread only where its OOS NET Sharpe beat baseline) imported by both `live_ranker` + `walkforward` so the live gate and the backtested gate can't drift |
| `regime_hmm.py` | Phase 6 (2.8.9) — data-driven curve regime detector (GMM + causal sticky-HMM over curve level + 5d change); replaces the hard −$2/+$5 thresholds for the `--hmm-only` walk-forward leg |
| `vol_target.py` | Phase 7 (2.8.10) — portfolio vol-targeting: reweights the gated tape via `shock_engine.risk_scale` (per-position vol-target × stress de-risk) + `gated_select` decorrelation + a corr-based book overlay; feeds the `--voltarget-only` walk-forward leg |
| `garch_vol.py` | GARCH study (2026-06-22) — causal conditional-vol forecast (plain GARCH + GJR-GARCH via `arch`); drop-in for `vol_target.spread_vol_frame`. Feeds `--garch-only`: improves the vol-target risk layer (Calmar 2.01→3.21) but stays below baseline — risk refinement, not alpha. Research-only (live app never imports it) |
| `shock_engine.py` | Phase 2.8.9/10 — GMM stress detector + causal HMM + circuit-breaker (`breaker_active`) |
| `auto_desk.py` | Phase 3 (06-19) — reconciles the paper book to `portfolio.selected` on the live feed during market hours; gates entries with the shock breaker; exits owned by `paper_trading.mark_to_market` |
| `walkforward.py` | expanding-window backtest; writes trade tapes + `walkforward_report.json`. Phase 5: `--horizon-only` (5/10/20/30d exit-horizon sweep, post-processing) + `--featsel-only` (Lasso stability-selection lean global leg) |
| `exit_sim.py` · `exit_tuning.py` · `exit_robustness.py` | TP/SL simulator · tuning sweep · OOS robustness |
| `ab_test.py` | pooled-vs-gated live A/B harness |
| `methodology_pdf.py` | mentor-facing PDF |

---

## 4. API · Env · Data

**API (40 endpoints).** Groups: health · prices/charts · models · fundamentals · news/intel ·
risk/structure · paper trading (`/api/paper/*`) · **regime engine** (`/api/regime`,
`/api/regime/recommendation`, `/api/regime/backtest`, `/api/regime/drill/<spread>`,
`/api/regime/walkforward`, `/api/regime/calibration`, `/api/regime/perspread_gate` (Phase 8),
`/api/regime/ab[/tick|/reset]`) · RAG (`/api/ask`).
*New endpoint pattern:* add a Pydantic model in `backend/schemas/` → register it → return via
`respond(...)` → run `python scripts/generate_ts_types.py`.

**Env keys (`.env`, gitignored).** `EIA_API_KEY`, `FRED_API_KEY`, `GROQ_API_KEY`, `NEWSAPI_KEY`,
`MARKETAUX_KEY`, `APIFY_API_TOKEN`, `AISSTREAM_API_KEY`, `SENTRY_DSN`/`VITE_SENTRY_DSN`,
`BETTER_STACK_TOKEN`. Optional regime flags: `PULSE_REGIME_MODE=pooled`, `PULSE_GATED_BLEND=1`,
`PULSE_GATED_SIZE=full|half|kelly`, `PULSE_AB_TEST_DISABLED=1`, `PULSE_PERSPREAD_GATE=0` (Phase 8 — revert
the per-spread gate to the uniform Phase 2.6 global gate; default on).

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
4b. **Node is installed PORTABLY at `~/nodejs`** (`C:\Users\<user>\nodejs` — node.exe + npm.cmd, node_modules
   present), not via the system installer. An interactive shell has it on PATH, but a **non-interactive shell
   (the agent's PowerShell tool) does NOT** — so `npm`/`node` read as "not found." Prepend it first:
   `$env:Path = "$env:USERPROFILE\nodejs;" + $env:Path` then `& "$env:USERPROFILE\nodejs\npm.cmd" run build`
   (from `frontend/`). Don't conclude Node is missing.

**Fresh-machine setup** (everything below is gitignored — restore or rebuild)
5. `.env` must be named `.env` (not `env`). Needs `xlrd` for COT `.xls`; if `external_history.parquet`
   is missing FRED columns, rebuild with `python -m backend.research.external_history`.
6. Model pkls (`backend/data/research/models*/`) — copy from another machine or rebuild via
   `python -m backend.research.models --mode composite|pooled`.

**Regime-engine invariants** (asserted by `tests/test_invariants.py` — run `python -m pytest tests/`)
7. **Gate rule** is mirrored: `live_ranker._pooled_passes_gate` ↔ `walkforward._pooled_passes_gate`
   (`GATED_WINNERS`, `GATED_Z_THRESHOLD`, `ROLLING_WIN` must match bit-for-bit). **Phase 8: the per-spread
   *layer* on top is NOT duplicated** — both sides import `gate_config.per_spread_gate_passes` /
   `decide_enabled` / `latest_enabled_from_report`, so the live per-spread gate and the backtested one can't
   drift (asserted by `test_perspread_gate_is_single_source`). Keep the per-spread logic in `gate_config.py`
   only; don't re-implement it in `live_ranker` or `walkforward`.
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
