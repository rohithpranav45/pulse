# PULSE — Phase History (archive)

> Detailed sprint-by-sprint log, archived from CLAUDE.md during the 2026-06-14
> cleanup. **For current state, run instructions, architecture, and active gotchas,
> see `CLAUDE.md`.** This file is read-only reference for "what exactly did sprint X
> do / how did we get here."

---
# PULSE — Project State File
**Last updated:** 2026-06-14 · Sprint −1 + 0a + 0b + 2a + 2b + 2c + 3 + 4 + 2.5 + 2.6 + 2.7 + 2.8.1 + 2.8.2 + 2.8.3 + 2.8.6 + 2.8.6-followup + 2.9.0 + 2.9.1 + 2.9.2 + 2.9.3 + **3.D (always-on Docker deployment)** shipped · **Phase 3.D** ships the production container stack so the tuned-rule paper book accumulates live win-rate proof unattended: multi-stage `Dockerfile` (node build → `python:3.13-slim` via uv → gunicorn serving the new `backend/wsgi.py`), a WSGI entry that starts the APScheduler + cache warm-up under gunicorn (app.py's `__main__` block never fires there), **gunicorn pinned `--workers 1`** so the scheduler stays singular (one A/B tick/day, not N), **SQLite WAL + busy_timeout=5000 + synchronous=NORMAL** on both connection factories (`db/cache.py` + `paper_trading.py`, same `pulse_cache.db`) so the 24/7 tick never locks the book under concurrent reads, `docker-compose.yml` (mounts `Data/` + `backend/db` + `backend/data/research:ro`, binds `.env`, `restart: unless-stopped`) and a **Caddy reverse proxy: basic auth + auto-HTTPS** (`/api/health` exempt for uptime probes; the app is internal-only via compose `expose` so the auth gate can't be bypassed). Locally verified: WAL live on the real `pulse_cache.db` (both factories report `journal_mode=wal`, set/get round-trip OK), compose YAML shape, `wsgi.py` compiles + its `from app import app,_scheduler,warm_cache` contract holds + `_scheduler.running==False` at import (so wsgi is what starts it), smoke-test `bash -n` clean. **NOT run here** (no Docker/uv/cloud creds in this env): the actual `docker build`, host provisioning (Oracle Always-Free ARM preferred / $5 VPS), and the live daily-tick verification — those are the owner's deploy step, fully scripted in `deploy/README.md` + `deploy/smoke_test.sh` (build stages validated by construction + the project's existing frontend-build history). **Deployment URL: _pending owner host provisioning_** — fill in after `docker compose up -d --build` + DNS (runbook §4–6). **Phase 2.9.0** measured the TRUE paper-book win rate (close at TP=p50 / SL=entry±1.5σ / 20-day time-stop) for the first time — the walk-forward only ever scored directional 20-day hit, never the rule the paper book actually trades. Headline: **gated_blend (production default) = 64.2% true win rate** (vs 71.0% directional), profit factor 1.49, expectancy +0.095/bbl/trade; un-gated **pooled collapses to 45.4%** (vs 64.0% directional), dragged by 18.9% degenerate wrong-side-p50 "scratch" signals — so the Phase 2.8.6 "pooled wins on NET Sharpe" side-finding does NOT survive a realized TP/SL rule, and the production default should stay gated. brent/wti M3-M6 are PF<1 losers under TP/SL. New `backend/research/exit_sim.py` (path-aware simulator on the daily spread series, fill-at-level) + regenerated enriched tapes (`exit_sim_tapes.json`) + `exit_sim_report.json`. **2.9.1 SHIPPED** (constrained sweep, 288 configs on the gated tape, NET-cost guardrails): chosen rule = entry |z|≥0.5, **TP halfway-to-fair** (0.5×(entry→p50)), **SL 2.5σ**, **30-day time-stop**, **drop the M3-M6 laggards** (trade 4 spreads) — lifts win rate 64.2%→**82.9%** AND NET Sharpe 0.211→0.475 AND NET PF 1.26→1.99 (improves *every* metric; the 85%-win unconstrained config is NET-unprofitable and was correctly rejected, proving the constraints bind). Entry threshold unchanged at 0.5 → no gate-sync needed. **2.9.2 SHIPPED**: the tuned rule is now LIVE — `live_ranker.py` computes TP=halfway-to-fair + SL=2.5σ and drops the M3-M6 laggards (4-spread universe), `paper_trading.py` enforces the 30-trading-day time-stop in the MTM sweep, the RegimePickCard shows an `EXIT` chip with the rule, and the A/B paper book was reset (8→0) to re-accumulate clean under the tuned rule. Entry trigger unchanged at |z|≥0.5, so the walk-forward gate stays bit-for-bit identical (gotcha 26 intact) — the exit rule is a separate layer validated by the exit-sim sweep, not the walk-forward. **2.9.3 SHIPPED (robustness check — answers "is 82.9% real or curve-fit?"): graded verdict = WIN-RATE ROBUST, EDGE IN-SAMPLE-OPTIMISTIC.** No retraining (reused the 2.9.0 simulator). (A) OOS in a *different era*: the deterministic baseline leg (93% of fires, rolling-z, no model fit) rebuilt over 2017→Nov-2023 — a window the sweep never saw — wins **74.4%** (vs 88.6% in-sample baseline leg), still net-profitable (NET PF 1.16) and still far above the 64% un-tuned default, but the risk-adjusted edge THINS (OOS NET Sharpe 0.165 < the 0.211 in-sample floor) and **brent_fly_123 turns net-unprofitable OOS** (PF 0.74) — the fly is the weak link to watch. (B) Selection generalisation: re-ran the full 288-config sweep on the early 2/3 of the tape and validated the chosen rule on the late 1/3 — chosen holds **74.8%** / NET PF 1.91 / NET Sharpe 0.46 on the hold-out, and crucially the early-only sweep's OWN winner (z1.5/tp0.25/all6) CRATERS on the hold-out (64.3% / Sharpe 0.06), so the chosen rule generalises *better* than any single-window peak. (C) Sensitivity: every one-knob perturbation incl. off-grid values (TP 0.4/0.6, SL 3.0, hold 40, z 0.75) stays feasible (NET PF>1 AND NET Sharpe≥floor) — a broad PLATEAU, not a spike. **Verdict: keep the tuned rule unchanged (it did NOT collapse OOS and is NOT a spike — no fallback needed), but quote NET Sharpe/PF as in-sample-optimistic, not a forward guarantee.** New `backend/research/exit_robustness.py` + `exit_robustness_report.json`. **Phase 2.9.x complete.** Phase 2.8.6-followup turns the "pooled un-gated beats gated_blend by +0.05 NET Sharpe" walk-forward side-finding into a live-validation harness. Parallel paper books for `PULSE_REGIME_MODE=pooled` (Arm A) and `PULSE_GATED_BLEND=1` (Arm B, current default) get dual-pushed every signal day, tagged with `ab_mode` on `paper_trades`. New `/api/regime/ab` returns per-arm NET Sharpe / mean PnL / equity curves + Welch + paired t-tests + stop-criteria progress (min 30 closed/arm AND p<0.05 → declare winner; max 14 days hard timeout). Dashboard panel on the Regime tab renders the comparison live, with TICK + RESET controls for ops. Verified end-to-end: first tick pushed 4 pooled + 4 gated paper trades on session 2026-06-11. Phase 2.8.6 layered a defensible transaction-cost model (per-leg per-side $0.0025 commission + half-spread slippage; $0.030/$0.040/$0.050 RT per bbl for M1-M2 / M3-M6 / fly) on top of the existing trade tape. **Headline NET (after costs)** — costs drag every mode by roughly the same ~−0.085 Sharpe (uniform per-trade fee). Gated_blend NET +0.297 vs baseline NET +0.301 (Δ −0.004, ties — same flat verdict as gross). **Notable side finding**: the un-gated **pooled engine wins both gross (+0.437) AND net (+0.351)** — Phase 2.8.1+2 boosters lifted pooled gross enough that the Phase 2.6 gate (added when pooled was losing in Phase 2.5) is now over-restrictive. Concrete next move for the mentor: A/B test `PULSE_REGIME_MODE=pooled` (no gate) against `PULSE_GATED_BLEND=1` in paper before changing the production default. No retraining was required — costs are a post-aggregation arithmetic layer on `gated_trades.json` + a rebuilt baseline tape.
**Project:** PULSE — Energy Intelligence Terminal (Futures First internship)
**Stack:** Flask 3 · React 18 + Vite + Tailwind · SQLite (cache + paper book) · /Data desk feed · 35 named data sources · sklearn (Ridge/Lasso/ElasticNet/Huber/Quantile) + XGBoost/LightGBM/CatBoost (Phase 2.8.1)
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

Mentor hasn't replied yet. Owner made provisional decisions on **2026-06-09**
so Phase 2 Sprint 2 can proceed without blocking; flagged ones still need her
sign-off when she replies and the design will be revisited if she pushes back.

1. **Instrument scope** — **implemented Sprint 3 (owner, 2026-06-09):** 6
   instruments = 3 Brent spreads/fly (M1-M2, M3-M6, M1-2M2+M3) + 3 WTI mirror
   instruments (M1-M2, M3-M6, M1-2M2+M3). Inter-product fly dropped. Final
   sign-off from mentor still pending.
2. **Regime axes** — **implemented Sprint 3 (owner, 2026-06-09):** 3-axis
   composite curve × inventory × vol, exactly the mentor proposal. 27 cells
   total, 66/162 (spread × regime) populated above MIN_SAMPLES=30 — within the
   "~9-12 usable cells per spread" range she predicted. Inventory axis backfilled
   from EIA WCRSTUS1 (10y weekly, vs 5y seasonal). Vol axis from Brent RV20.
3. **Time horizon** — default 20-day mean reversion. May want 5d swing or 60d position.
4. **Paper trading integration** — **shipped Sprint 2b for Brent legs, extended
   in Sprint 3 to WTI legs.** Each spread/fly push writes one parent row +
   N leg rows. WTI legs (e.g. SHORT wti_m3_m6 ⇒ SHORT c3 + LONG c6) use the
   synthesised WTI settlements; flagged ESTIMATE in provenance.
5. **WTI deferred data gap** — **provisional path (b), with parallel ask
   (owner + agent, 2026-06-09):** synthesised daily WTI C1-C6 from
   `CL_WTI_1min_outrights_midprice_*.csv` (last 1-min mid per session), cached
   at `Data/parquet/wti_synth_settlements_c1_c6.parquet`. Surfaced via
   `data_lake.get_wti_settlements()`. Flag the data as ESTIMATE in provenance
   when wiring into the dashboard. **A separate mentor message asking for the
   real WTI C1-C3 daily settlement file is drafted below in the Mentor
   communication log** — swap to her file in a follow-up sprint when she sends one.
6. **Auto-push behaviour** — opportunities display only / auto-stage for approval / auto-push above threshold.
7. **Phase 1 coexistence** — replace existing signal engine, run alongside, or split (Phase 1 = directional, Phase 2 = spreads/butterflies).

---

## Current sprint

### ✅ PHASE 2.9.0 · TP/SL-aware backtest (TRUE win rate) — SHIPPED 2026-06-13

**Brief:** the walk-forward measures directional hit at a fixed 20-day horizon
with NO early exit (`fwd_pnl = sign × (spread[d+20] − spread[d])`). But the live
paper book closes on **TP = p50 / SL = entry ± 1.5 × resid_std**, falling back to
a time-stop only if neither is hit. So the win rate the mentor actually cares
about — closed-green %, profit factor, expectancy — had **never been measured**.
Phase 2.9.0 closes that gap with a path-aware exit simulator over the daily
spread series.

**The honest headline (the number to take to the mentor):**

| Mode | **True win % (TP/SL)** | Dir. 20d hit | Gap | PF | Avg win | Avg loss | Expectancy | Mean hold | TP/SL/TIME/SCRATCH mix |
|---|---|---|---|---|---|---|---|---|---|
| **Gated_blend (production)** | **64.2 %** | 71.0 % | −6.8 ppts | **1.49** | +0.453 | −0.570 | **+0.095** | 12.5 d | 39.0 / 19.5 / 39.9 / 1.6 % |
| Pooled (un-gated) | **45.4 %** | 64.0 % | −18.6 ppts | 1.97 | +0.240 | −0.155 | +0.054 | 3.4 d | 43.2 / 35.5 / 2.4 / 18.9 % |

(n closed: gated 2,154 · pooled 1,992. Total NET-of-nothing PnL: gated +205.1, pooled +106.5 $/bbl.)

**Per-spread (gated_blend):**

| spread | n | win % | PF | expectancy | dir 20d hit |
|---|---|---|---|---|---|
| brent_m1_m2   | 345 | **77.7 %** | **3.28** | +0.192 | 80.9 % |
| wti_m1_m2     | 373 | 67.3 % | 2.78 | +0.221 | 68.6 % |
| wti_fly_123   | 360 | 66.4 % | **3.61** | +0.142 | 79.2 % |
| brent_fly_123 | 253 | 58.9 % | 3.01 | +0.172 | 81.8 % |
| wti_m3_m6     | 404 | 58.4 % | 0.96 | −0.014 | 62.4 % |
| brent_m3_m6   | 419 | 57.0 % | **0.79** | −0.079 | 59.9 % |

**Gated_blend by source (regime leg vs baseline fallback):**

| leg | n | win % | PF | expectancy | dir 20d hit |
|---|---|---|---|---|---|
| baseline (252d z) | 1,910 | 67.1 % | 1.43 | +0.090 | 71.4 % |
| regime (engine)   |   244 | 41.4 % | **2.59** | +0.133 | 68.4 % |

**Findings (honest):**

1. **True win rate is BELOW directional hit in both modes.** The TP/SL rule
   converts some "directionally right at 20d" trades into stopped-out losses.
   Gated gives back ~6.8 ppts (71.0 → 64.2); pooled gives back a brutal 18.6
   (64.0 → 45.4).
2. **64.2 % is the gated_blend headline** — PF 1.49, expectancy +0.095/bbl/trade.
   This is the realized win rate of the production default, measured for the
   first time.
3. **The Phase 2.8.6 "pooled wins" side-finding does NOT survive realistic
   exits.** Pooled's directional NET-Sharpe edge (+0.351 vs gated +0.297)
   evaporates under the actual paper-book rule: pooled true win rate is only
   45.4 %, and **18.9 % of its signals are degenerate** — the quantile p50 lands
   on the wrong side of the z-direction, so the live book would open then
   immediately scratch at ~entry (modelled as SCRATCH, gross PnL ≈ 0). The
   gate's discipline (BACK + agreeing models, baseline elsewhere) is exactly
   what makes the realized win rate trustworthy. **Recommendation: do NOT flip
   the production default to pooled on directional Sharpe alone** — the realized
   exit rule favours gated decisively.
4. **brent/wti M3-M6 are PF<1 losers under TP/SL** (brent 0.79 / exp −0.079;
   wti 0.96 / exp −0.014) despite ~57-58 % win rates — losses outweigh wins and
   ~50-60 % of their trades hit the 20d time-stop. Win rate alone is misleading
   here; PF/expectancy expose them. Prime candidates for the 2.9.1 spread-subset
   drop.
5. **Regime leg = fewer wins, bigger edge.** 244 regime fires win only 41.4 %
   but at PF 2.59 / exp +0.133 — an asymmetric "small losses, occasional big
   reversion win" shape. Baseline leg wins 67.1 % at PF 1.43. Both net-positive,
   different shapes.

**Method / conventions (documented for defensibility):**

- **Fill-at-level**: when a daily settle first crosses a level, book the exit AT
  that level — the faithful daily-resolution proxy for the live 60-second MTM
  loop (`paper_trading.run_mtm`), which closes at the live price the instant a
  level is crossed. TP and SL sit on opposite sides of entry, so a daily settle
  satisfies at most one — no intraday tie-break needed.
- **SCRATCH** (Phase 2.9.0 fidelity fix): when p50 is on the WRONG side of entry
  (quantile median contradicts the z-direction), the live book opens then closes
  at ~entry on the next MTM tick. Modelled as a breakeven scratch at entry (gross
  ≈ 0), NOT a fake far-side fill at the mis-placed target. Without this fix
  pooled PF reads 1.38 instead of the correct 1.97 — the win rate is unchanged
  either way (the wins don't move) but the scratches must not be booked as losses.
- **Time-stop reconciliation**: a TIME exit's PnL equals the directional
  `fwd_pnl` by construction (verified ≤ 0.0001, rounding-only) — a clean internal
  consistency check between the two views.
- **Caveat (reported, not hidden)**: daily settles can't see intraday level
  touches between closes, so TP/SL counts are slightly conservative (a few true
  touches read as time-stops). No intraday data used, per brief.

**Why the tapes had to be regenerated:** the on-disk `gated_trades.json` was last
written by the Phase 2.8.3 reroute, which **stripped `p50`/`fair`/`fwd_date`** off
the regime rows; there was no `pooled_trades.json` at all. So neither persisted
tape carried the TP target (`p50`) or the SL input (`resid_std`). A pooled-only
walk-forward (~44 min, 10 quarterly refits, boosters on) regenerated them with
the exit-sim inputs; baseline + gated were rebuilt deterministically on top.

**Files touched (Phase 2.9.0):**

| File | Change |
|---|---|
| `backend/research/walkforward.py` | **Additive only** — `_evaluate_window` now records `resid_std` on every regime row; `_baseline_trades` records `roll_mu` + `roll_sigma` (the baseline TP target + SL sigma); `_build_gated_blend` carries `roll_mu`/`roll_sigma` through baseline rows (regime rows already keep `p50`/`resid_std` via `**p`). No existing metric reads these — a future full walk-forward now persists exit-sim-ready tapes for free. |
| `backend/research/exit_sim.py` | **NEW** — path-aware TP/SL simulator. `simulate_one` walks the daily path, closes at TP/SL/TIME/SCRATCH (fill-at-level). `exit_metrics` (win_rate, PF, avg_win/loss, expectancy, close-reason mix + directional gap). `_by_spread`/`_by_source`. `build_tapes()` regenerates pooled+baseline+gated via the pooled walk-forward and saves them; `run(from_cache=)` simulates + writes the report. CLI: `python -m research.exit_sim [--from-cache]`. |
| `backend/data/research/exit_sim_tapes.json` | **NEW (~2.7 MB)** — enriched pooled/baseline/gated trade tapes with TP/SL inputs. `--from-cache` reuses these so re-runs / metric tweaks skip the 44-min retrain. |
| `backend/data/research/exit_sim_report.json` | **NEW (~13 KB)** — true win-rate metrics (overall + per-spread + by-source) for pooled & gated, with the directional gap inline. |

**Verification (all 2026-06-13):**

- Unit tests on synthetic paths: SELL-TP, SELL-SL, BUY-TP, TIME, baseline-input
  selection (poisoned p50 ignored for baseline rows), incomplete-window
  exclusion — all pass.
- On the real tapes: TIME ↔ directional `fwd_pnl` reconcile to ≤ 0.0001
  (rounding); every TP pnl ≥ 0, every SL pnl ≤ 0, every SCRATCH pnl = 0.
- Pooled-only walk-forward ran 10/10 refits clean (~44 min); tapes + report
  written; `--from-cache` re-sim runs in ~3 s.

**Next (autonomous queue, per owner 2026-06-13):** 2.9.1 constrained win-rate
optimization → 2.9.2 apply the tuned config. Briefs recorded at the bottom of
this section.

> **Queued brief — Phase 2.9.1 (win-rate optimization, constrained):** maximize
> win rate SUBJECT TO profit_factor > 1.0 AND Sharpe ≥ current gated NET (win
> rate alone is gameable — keep constraints binding). Sweep on the 2.9.0
> simulator (no retrain): entry |z| ∈ {0.5, 0.75, 1.0, 1.5} × TP ∈ {p50,
> p25-toward-fair, 0.5×(entry→p50)} × SL ∈ {1.0, 1.5, 2.0, 2.5}×resid_std ×
> time-stop ∈ {10, 20, 30}d × spread-subset {all 6, drop brent_m3_m6+wti_m3_m6
> laggards}. Ranked table by win_rate w/ PF + Sharpe, filtered to the
> constraint; pick the winner, show runner-ups. If nothing clears 50 % with
> PF>1, SAY SO and report the best achievable — don't game TP/SL.
>
> **Queued brief — Phase 2.9.2 (apply the 2.9.1 config):** thread the chosen
> entry-z + TP/SL + spread-subset into `live_ranker.py` (target/stop) AND
> `paper_trading.py` (TP/SL sweep), kept consistent (new invariant — add parity
> to `test_invariants.py` in 3.0). Surface the rule's params on RegimePickCard
> so the mentor sees the exit logic, not just entry. Reset the A/B paper book so
> it re-accumulates clean under the tuned rule.

---

### ✅ PHASE 2.9.1 · Constrained win-rate optimization — SHIPPED 2026-06-13

**Brief:** maximize win rate SUBJECT TO profit_factor > 1.0 AND Sharpe ≥ current
gated NET — win rate alone is gameable, so keep the constraints binding. Sweep
the trading-rule knobs on the 2.9.0 simulator (no retrain), rank by win rate
filtered to the constraint, pick the winner, show runner-ups. If nothing clears
50 % with PF>1, say so and report the best achievable — don't game TP/SL.

**Grid (288 configs on the gated_blend tape):** entry |z| ∈ {0.5, 0.75, 1.0,
1.5} × TP ∈ {p50, 0.5×(entry→p50), 0.25×(entry→p50)} × SL ∈ {1.0, 1.5, 2.0,
2.5}σ × time-stop ∈ {10, 20, 30}d × spread-subset {all 6, drop M3-M6 laggards}.

**Guardrails are NET (this is what makes them bind):** each closed trade pays
the Phase 2.8.6 round-trip cost (SCRATCH trades included — a real open+close), so
fee-dominated tiny-TP configs are penalised. Sharpe is annualised at the FIXED
√(252/20), NOT √(252/mean_hold) — a turnover-aware annualisation would *reward*
fast-churn tiny-TP gaming and defeat the guardrail. Floor = the current default
config's NET Sharpe on the same metric (0.211; the documented directional gated
NET Sharpe +0.297 is a different, fixed-20d-directional number, shown for ref).

**Result — the winner improves on EVERY metric, not just win rate:**

| Config | spreads | n | win % | gross PF | NET PF | NET Sharpe | NET exp | hold |
|---|---|---|---|---|---|---|---|---|
| DEFAULT (z0.5 · p50 · 1.5σ · 20d) | all 6 | 2154 | 64.2 % | 1.49 | 1.26 | 0.211 | +0.056 | 12.5d |
| **WINNER (z0.5 · ½·p50 · 2.5σ · 30d)** | **4 (drop M3-M6)** | 1297 | **82.9 %** | 2.69 | **1.99** | **0.475** | +0.075 | 7.9d |
| *gaming (z0.5 · ¼·p50 · 2.5σ · 30d, UNCONSTRAINED)* | all 6 | 2100 | *85.0 %* | 1.33 | *0.98* | *−0.013* | *−0.002* | 6.7d |

183/288 configs were feasible. Key runner-ups cluster on TP=½·p50 + wide SL
(2.0-2.5σ) + 30d, dropping M3-M6. Tightening entry to |z|≥0.75 trades ~3 ppts of
win rate for higher NET Sharpe (z0.75 · ½p50 · 2.5σ · 30d · no_m3m6 = 80.4 % win,
**NET Sharpe 0.547**) — the win-rate↔Sharpe frontier.

**Chosen config (for 2.9.2):** entry **|z| ≥ 0.5** (unchanged — no gate-sync
needed) · **TP = halfway to fair** (`entry + 0.5×(anchor − entry)`, anchor = p50
regime / 252d mean baseline) · **SL = entry ± 2.5 × sigma** · **30-day time-stop**
· universe = **{brent_m1_m2, brent_fly_123, wti_m1_m2, wti_fly_123}** (drop
brent_m3_m6 + wti_m3_m6).

**Findings (honest):**

1. **The winner dominates the default on every axis** — win 64.2→82.9 %, NET PF
   1.26→1.99, NET Sharpe 0.211→0.475, expectancy +0.056→+0.075. It is NOT a
   win-rate-only gain bought with worse risk; it's a strict improvement.
2. **The constraints demonstrably block gaming.** Pure win-rate maximisation
   picks z0.5/¼·p50/2.5σ/30d at **85.0 %** win — but that config is **NET-loss-
   making** (NET PF 0.98, NET Sharpe −0.013): the quarter-distance TP wins
   constantly but the rare 2.5σ stops + per-trade fees sink it. The guardrails
   reject it. This is exactly the gaming the brief warned about, caught.
3. **The lift is economically sensible, not curve-fit:** (a) drop the two M3-M6
   spreads 2.9.0 flagged as PF<1 losers; (b) take profit halfway to fair value —
   more achievable than the full p50, so more trades bank a green close before
   the spread reverses; (c) wider stop + longer hold give the high-conviction
   reversion room and time to play out.
4. **Win rate clears 50 % comfortably** (82.9 %), so the "if nothing clears 50 %"
   honest-fallback clause did not trigger.

**Files touched (Phase 2.9.1):**

| File | Change |
|---|---|
| `backend/research/exit_tuning.py` | **NEW** — 288-config constrained sweep on the gated tape. `_filter` (spread-subset + |z|≥thr), `_metrics` (gross + NET win/PF/exp/Sharpe), `run()` finds the default's NET-Sharpe floor, filters feasible (NET PF>1 ∧ NET Sharpe≥floor ∧ n≥50), ranks by win rate, surfaces the unconstrained gaming pick for contrast. Writes `exit_tuning_report.json`. CLI prints default / gaming-contrast / winner / runner-ups / verdict. |
| `backend/research/exit_sim.py` | `simulate_one` + `simulate_tape` gain `tp_frac` (TP placed `entry + tp_frac×(anchor−entry)`) and `sl_mult` passthrough. Default `tp_frac=1.0` → 2.9.0 results reproduce bit-for-bit (verified: default sweep row = 64.2 % win, n=2154, matching the 2.9.0 gated headline). |
| `backend/data/research/exit_tuning_report.json` | **NEW** — all 288 configs + winner + runner-ups + default + floor + gaming contrast + honest note. |

**Verification (all 2026-06-13):** 288 configs swept in ~30 s (post-processing,
no retrain). Default config reproduces the 2.9.0 gated numbers exactly (64.2 %
win / n=2154), confirming the `tp_frac` parameterization left defaults
unchanged. Winner constraints re-checked: NET PF 1.99 > 1.0 ✓, NET Sharpe
0.475 ≥ floor 0.211 ✓, n=1297 ≥ 50 ✓.

---

### ✅ PHASE 2.9.2 · Apply the tuned exit rule to production — SHIPPED 2026-06-14

**Brief:** thread the Phase 2.9.1 winner into `live_ranker.py` (target/stop) AND
`paper_trading.py` (TP/SL + time-stop), kept consistent; surface the rule on the
RegimePickCard so the mentor sees the exit logic, not just entry; reset the A/B
paper book so it re-accumulates under the tuned rule from a clean start.

**Tuned rule now live (chosen by 2.9.1):** entry **|z| ≥ 0.5** (unchanged) ·
**TP = halfway to fair** (`entry + 0.5×(anchor − entry)`; anchor = p50 regime /
252d mean baseline) · **SL = entry ± 2.5 × sigma** · **30-trading-day time-stop**
· universe = **{brent_m1_m2, brent_fly_123, wti_m1_m2, wti_fly_123}** (drop
brent_m3_m6 + wti_m3_m6).

**Files touched (Phase 2.9.2):**

| File | Change |
|---|---|
| `backend/research/live_ranker.py` | + tuned-rule constants `TUNED_TP_FRAC=0.5`, `TUNED_SL_MULT=2.5`, `TUNED_MAX_HOLD_DAYS=30`, `TUNED_EXCLUDED_SPREADS={brent_m3_m6, wti_m3_m6}`. Regime + baseline `target` now placed halfway to fair; `stop` at ±2.5σ (was 1.5σ). The recommendation loop skips excluded spreads; the payload exposes `excluded_spreads` + a `tuned_rule` block and `n_universe` is now 4. **Gate untouched** (entry z = `GATED_Z_THRESHOLD` = 0.5) → walk-forward parity (gotcha 26) preserved. |
| `backend/paper_trading.py` | + `import numpy as np`; + `TUNED_MAX_HOLD_TRADING_DAYS=30` (MIRROR of `live_ranker.TUNED_MAX_HOLD_DAYS`); `mark_to_market()` now closes any OPEN position held ≥ 30 trading days (`np.busday_count`) with `close_reason='time_stop'`, after the TP/SL checks. TP/SL values themselves flow from the recommendation's tuned target/stop, so the two modules agree by construction. |
| `frontend/src/components/panels/RegimePickCard.tsx` | `Recommendation` type gains `excluded_spreads` + `tuned_rule`. New ribbon chip `EXIT TP 50%·fair · 2.5σ · 30d` with a tooltip giving the full rule + dropped spreads + the 64%→83% win-rate lift. |
| `backend/db/pulse_cache.db` | A/B-tagged paper rows reset (8 → 0) and re-seeded under the tuned rule. |

**Layering note (important for future sessions):** the **walk-forward
(`walkforward.py`) still trades all 6 spreads at p50 / 1.5σ / 20d** — it is the
directional *model + gate* validator and the source of the exit-sim tapes. The
**tuned EXIT rule is a separate layer** that lives in `exit_sim.py` /
`exit_tuning.py` (which measured/validated it on the walk-forward's gated tape)
and now in `live_ranker.py` + `paper_trading.py` (production). Do NOT "sync" the
exit rule into `walkforward.py` — they answer different questions. Only the GATE
(regime/winners/entry-z) must stay identical between `live_ranker` and
`walkforward` (gotcha 26), and it does (entry z unchanged at 0.5).

**Verification (all 2026-06-14):**

- Backend imports clean; `live_ranker.TUNED_MAX_HOLD_DAYS == paper_trading.TUNED_MAX_HOLD_TRADING_DAYS` (parity asserted in the smoke test).
- `get_recommendation(force_gated=True)`: `n_eligible=4`, `n_universe=4`,
  `excluded_spreads=[brent_m3_m6, wti_m3_m6]`; ranked contains only the 4 traded
  spreads (laggards confirmed absent). Sample fired row: TP matches
  `entry+0.5×(p50−entry)` to 3dp; stop = `entry ± 2.5σ`.
- `npx tsc --noEmit` clean (only the pre-existing `baseUrl` deprecation);
  `npx vite build` clean (6.21 s).
- A/B reset wiped 8 rows → 0; first post-reset tick re-seeded 2 pooled + 2 gated
  (brent_m1_m2 + wti_m1_m2) under the tuned TP/SL with **no M3-M6**. The two flies
  were skipped this tick with "no entry price available" — a transient live-feed
  condition (`_live_price` flaps between Brent/WTI by feed availability;
  pre-existing harness behaviour, NOT a 2.9.2 regression). The daily A/B
  scheduler accumulates them on subsequent ticks when priced.

**Honest caveat:** the live time-stop counts business days (`np.busday_count`,
ignores exchange holidays) ≈ the backtest's 30 trading-day horizon — a handful of
holidays/year make it marginally generous; acceptable for a paper book.

---

### ✅ PHASE 2.9.3 · Robustness of the tuned exit rule — SHIPPED 2026-06-14

**Brief:** 2.9.1 chose the tuned rule by sweeping 288 configs and *maximising
win rate* under PF>1 + Sharpe guardrails. Maximising a metric over a grid is an
overfitting risk — a trader will ask "is 82.9% real or curve-fit?" Answer it
honestly with **no retraining** (reuse the 2.9.0 simulator): out-of-sample test
+ knob sensitivity + a plain verdict; if it collapses OOS or sits on a spike,
report the robust config instead of defending a curve-fit number.

**Method (zero model retraining):** new `backend/research/exit_robustness.py`
reuses `exit_sim.simulate_tape` (the 2.9.0 path-aware TP/SL simulator) + `exit_tuning._metrics`
(the 2.9.1 NET metric, ann. √(252/20)). The only tape built is the
**deterministic baseline leg** (`walkforward._baseline_trades` — 252-day rolling
z, no model fit), which is **93 % of all production fires**, so a genuinely-unseen
era can be tested without touching a single model pkl.

**Three legs:**

**A — OOS in a DIFFERENT ERA (baseline leg).** The whole on-disk gated tape is
2024-01…2026-05 (the sweep saw all of it). So rebuild the baseline leg over
**2017 → Nov-2023** — a window the sweep never touched (Brent back to 2016; WTI
synth only 2021, so WTI contributes ~2022-23). Entries capped at 2023-11-15 so
even the 30-day forward exit window stays inside 2023 → **zero overlap** with
in-sample. Apples-to-apples = OOS baseline leg vs in-sample baseline leg, both
under the chosen rule.

| leg (chosen rule) | n | win % | NET PF | NET Sharpe | NET exp |
|---|---|---|---|---|---|
| in-sample full blend (2.9.1 ref) | 1297 | 82.9 % | 1.99 | +0.475 | +0.074 |
| in-sample **baseline leg** | 1071 | **88.6 %** | 2.30 | +0.532 | +0.088 |
| **OOS baseline leg (unseen era)** | 2760 | **74.4 %** | **1.16** | **+0.165** | +0.027 |

OOS by spread: brent_m1_m2 70.9 % (PF 1.21) · brent_fly_123 79.3 % (**PF 0.74,
Sharpe −0.33 — net LOSER**) · wti_m1_m2 68.7 % (PF 1.65) · wti_fly_123 84.8 %
(PF 1.17). Win rate holds as a strong majority (74.4 %, still well above the
64 % un-tuned default) and stays net-profitable in aggregate, **but the
risk-adjusted edge thins** (Sharpe 0.165 < the 0.211 in-sample floor) and the
**Brent fly is net-unprofitable** in 2017-2023 (same PF<1 pathology 2.9.0 flagged
on M3-M6 — the fly carries the highest $0.050 RT cost). Note this OOS test is on
the *higher*-win-rate leg (baseline 88.6 % in-sample vs blend 82.9 %), so it's a
fair-to-conservative test, not cherry-picked.

**B — SELECTION GENERALISATION (full blend, incl. regime leg).** Split the
existing tape ~2/3 early / ~1/3 late at 2025-08-31. Re-run the FULL 288-config
constrained sweep on the **early portion only** (floor recomputed there), then
apply the chosen rule to the held-out **late portion**.

| | n | win % | NET PF | NET Sharpe |
|---|---|---|---|---|
| chosen on early (in-sample) | 884 | 86.7 % | 2.09 | +0.874 |
| **chosen on LATE hold-out (OOS)** | 413 | **74.8 %** | **1.91** | **+0.460** |
| early-sweep's OWN winner on late hold-out | 227 | 64.3 % | 1.05 | +0.057 |

The early-only sweep picked a *different* config (z1.5 / tp0.25 / all6) — and
**that config craters on the hold-out** (64.3 % / Sharpe 0.06), while the chosen
rule holds (74.8 % / Sharpe 0.46). So the chosen rule **generalises BETTER than
any single-window peak** — strong evidence the selection didn't overfit in the
damaging sense.

**C — KNOB SENSITIVITY (plateau vs spike).** Perturb each knob one at a time on
the full tape, *including values outside the 2.9.1 grid* (TP 0.4/0.6, SL 3.0,
hold 40, z 0.75). **Every** neighbour stays feasible (NET PF>1 AND NET Sharpe ≥
0.211 floor); win-rate ranges are tiny (TP 1.8 / SL 3.8 / hold 4.3 / z 2.5 ppts).
A broad **PLATEAU, not a spike**. Several neighbours (TP 0.6 → Sharpe 0.58,
hold 40 → 0.56, z 0.75 → 0.55) even *beat* the chosen config's Sharpe — the
chosen point maximised win rate, so it sits slightly inside the Sharpe-optimal
corner of the plateau (free Sharpe available if the desk ever prefers it).

**VERDICT — WIN-RATE ROBUST; EDGE IN-SAMPLE-OPTIMISTIC.** The 82.9 % is **not a
curve-fit spike**: the win rate holds ~74-75 % across a different era AND a
temporal hold-out (always above the 64 % default), and the rule sits on a broad
plateau (no knob is a spike). What does **not** fully survive OOS is the
*risk-adjusted edge* — NET Sharpe thins from ~0.5 to ~0.17 and the Brent fly
turns net-negative in 2017-2023. **It did NOT collapse and is NOT a spike, so
keep the tuned rule unchanged (no fallback needed)** — but quote NET Sharpe / PF
as in-sample-optimistic, not a forward guarantee, and **watch brent_fly_123** as
the weak link. (Dropping the fly on this single-era evidence is deliberately NOT
recommended — that would re-optimise on the hold-out, the exact overfitting trap
the brief warns against.)

**Caveat (honest):** Leg A tests the **baseline leg only** (93 % of fires); the
7 % regime leg needs pooled model predictions = a walk-forward retrain, excluded
by the no-retrain brief. The exit KNOBS (the thing 2.9.1 tuned) are leg-agnostic,
so testing them on the dominant deterministic leg in an unseen era is a clean
test of exactly what's under suspicion.

**Files touched (Phase 2.9.3):**

| File | Change |
|---|---|
| `backend/research/exit_robustness.py` | **NEW** — `_run` (one config on one tape, reuses 2.9.0 sim + 2.9.1 metric), `_sweep` (replicates the 2.9.1 constrained selection on an arbitrary sub-tape), `leg_a_oos_era` / `leg_b_selection` / `leg_c_sensitivity`, graded `_verdict` (separates win-rate robustness from edge robustness; surfaces per-spread OOS losers + OOS-Sharpe-vs-floor; emits a knob-level robust fallback only if a spike is detected). CLI prints all three legs + verdict. `python -m research.exit_robustness`. |
| `backend/data/research/exit_robustness_report.json` | **NEW (~14 KB)** — all three legs + graded verdict. |

**Verification (all 2026-06-14):** runs in ~46 s (Leg B re-sweeps 288 configs on
the early sub-tape; Legs A + C are seconds). Parity check passes — the chosen
config on the full tape reproduces the 2.9.1 headline exactly (82.9 % win,
n=1297). OOS per-spread n sums to the overall 2760. Verdict booleans:
`win_rate_robust=True`, `edge_robust=False`, `plateau=True`,
`robust_fallback_config=None` (correctly null — not a spike). No model pkls,
walk-forward report, or production code touched — this is a pure analysis sprint.

---

### ✅ PHASE 3.D · Always-on Docker deployment — SHIPPED 2026-06-14 (artifacts; owner does the host step)

**Brief:** run PULSE 24/7 on a cheap/free always-on host so the daily
APScheduler A/B tick accumulates the **tuned-rule** paper book (Phase 2.9.2
exit rule, always-on) and `/api/regime/ab` shows the live win rate climbing —
the forward-validation proof the mentor asked for, without the desk having to
stay awake. Replaces the throwaway Cloudflare quick-tunnel (one-day demo) with a
persistent containerised stack.

**Architecture:**

```
internet ─▶ Caddy (:80/:443, basic auth + auto-HTTPS) ─▶ pulse (:5000, internal only)
                                                            gunicorn -w1 -t8  wsgi:app
                                                            └─ APScheduler (refresh + 60s MTM + daily A/B tick)
  bind mounts:  ./Data (RW, lake + parquet) · ./backend/db (RW, the book) · ./backend/data/research (RO, models)
```

The app is **never published to the host** (compose `expose`, not `ports`) —
Caddy is the only public port, so the basic-auth gate cannot be bypassed by
hitting `:5000` directly. The scheduler runs inside the **single** gunicorn
worker.

**Why a WSGI entry point (`backend/wsgi.py`, NEW):** the APScheduler `.start()`
and `warm_cache()` only fire inside app.py's `if __name__ == "__main__"` block,
which gunicorn never executes (it *imports* the module). `wsgi.py` imports
`app`, then starts the scheduler + warm-up exactly once at import. **gunicorn
MUST stay `--workers 1`** — the scheduler must live in exactly one process or the
daily A/B tick, the 60 s MTM, and every refresh job fire once *per worker*. One
worker + 8 threads is the right model for this I/O-bound, single-tenant app.
(Also: no `--preload` — APScheduler threads don't survive `fork()`, so they must
start in the worker, not the master.)

**Why SQLite WAL (Task 2):** the 24/7 scheduler is a constant writer (daily tick
+ 60 s MTM); concurrent dashboard reads under the default rollback journal would
hit "database is locked". `db/cache.py:_apply_pragmas()` and
`paper_trading.py:_conn()` now set `journal_mode=WAL` (db-level, idempotent) +
`busy_timeout=5000` + `synchronous=NORMAL` (both per-connection) on every
connection. Both modules open the **same** `pulse_cache.db`, so the pragmas are
mirrored to stay consistent regardless of which opens it first.

**Files (Phase 3.D):**

| File | Change |
|---|---|
| `Dockerfile` | **NEW** — stage 1 `node:22-slim` runs `npm ci` + `npm run build` (vite → `backend/static`); stage 2 `python:3.13-slim`, deps via **uv** (`uv pip install --system`), `libgomp1` for the boosters, non-root uid 10001, `HEALTHCHECK curl /api/health`, CMD `gunicorn --chdir /app/backend --workers 1 --threads 8 wsgi:app`. CPU-torch extra-index documented as an opt-in x86 size shrink. |
| `.dockerignore` | **NEW** — excludes `.env`, `Data/`, `backend/db`, `backend/data/research`, `backend/static`, `node_modules`, pkls/parquet, docs, VCS. Keeps the 3.5 GB lake + secrets out of the build context (they're bind-mounted at runtime). |
| `docker-compose.yml` | **NEW** — `pulse` (build, `env_file: .env`, `user: ${PULSE_UID:-10001}:${PULSE_GID:-10001}`, `expose: 5000`, mounts `Data/`+`backend/db`+`backend/data/research:ro`, `restart: unless-stopped`) + `caddy` (`caddy:2.8-alpine`, ports 80/443, `depends_on: service_healthy`, `env_file: .env`, Caddyfile + cert volumes). |
| `deploy/Caddyfile` | **NEW** — site `{$PULSE_DOMAIN::80}` (real domain → auto Let's Encrypt; default `:80` HTTP), `basic_auth` on everything except `/api/health`, `reverse_proxy pulse:5000`. Creds from `.env` via env_file (literal — bcrypt `$` needs no escaping). |
| `backend/wsgi.py` | **NEW** — gunicorn entry; `_boot_once()` starts cache warm-up thread + `_scheduler.start()` (guarded on `.running`), `atexit` clean shutdown. Docstrings spell out the `--workers 1` / no-`--preload` requirements. |
| `backend/db/cache.py` | + `_apply_pragmas()` (WAL + busy_timeout=5000 + synchronous=NORMAL) called in `_conn()`. |
| `backend/paper_trading.py` | `_conn()` sets the same three pragmas (mirror of cache.py — same db file). |
| `deploy/README.md` | **NEW** — full runbook: Oracle Always-Free ARM provisioning (incl. the two-layer firewall gotcha) + VPS variant, code/Data/pkls/.env transfer, `.env` additions (BASIC_AUTH_HASH, PULSE_DOMAIN, PULSE_UID), DNS/DuckDNS, launch, verify, **restart/operate runbook table**, gotchas. |
| `deploy/smoke_test.sh` | **NEW** — post-deploy Task-4 check: health (no auth) → POST `/api/regime/ab/tick` (auth) → GET `/api/regime/ab`, asserts ≥1 open/closed trade (book accumulating). |

**Verification (local, 2026-06-14):**

- **WAL live on the real `pulse_cache.db`** — both factories return
  `journal_mode=wal`, `busy_timeout=5000`, `synchronous=1` (NORMAL); cache
  set→get round-trip succeeds.
- `docker-compose.yml` parses (PyYAML) with the expected service/volume shape;
  fixed a default-value typo (`${PULSE_DOMAIN::80}` → `${PULSE_DOMAIN:-:80}`).
- `backend/wsgi.py` compiles; `import app` in-env confirms `app`, `_scheduler`,
  `warm_cache` all exist and `_scheduler.running == False` at import (so wsgi is
  what starts it — not a double-start) and APScheduler logs "...scheduled when
  the scheduler starts".
- `bash -n deploy/smoke_test.sh` clean.

**NOT done here (owner's deploy step — no Docker/uv/cloud creds in this env):**

- **No real `docker build`** ran — Docker isn't installed locally. The build
  stages are validated by construction + the project's existing
  `npm run build` / vite history; first `docker compose up -d --build` on the
  host is the real test.
- **No host provisioning** — Oracle Always-Free ARM (preferred) or a $5 VPS, and
  the DNS for HTTPS, are manual. `deploy/README.md` §1–5 is copy-paste.
- **No live daily-tick verification** — that requires the deployed host;
  `deploy/smoke_test.sh` + runbook §6 are the acceptance check the owner runs
  (health → manual tick → `/api/regime/ab` shows the book climbing; the
  unattended tick fires 5 min after boot, then every 24 h).
- **Deployment URL: pending** — fill into this section + the header after the
  host is up.

**Restart / operate runbook (also in `deploy/README.md` §7):**

| Task | Command |
|---|---|
| Restart app | `docker compose restart pulse` |
| Apply code update | `git pull && docker compose up -d --build` |
| App / proxy logs | `docker compose logs -f pulse` · `... caddy` |
| Fire A/B tick now | `curl -u mentor:PW -X POST https://DOMAIN/api/regime/ab/tick` |
| Read A/B report | `curl -u mentor:PW https://DOMAIN/api/regime/ab` |
| Stop (keep certs/book) | `docker compose down` |

**Honest caveats:** (1) bind-mount writes need the container uid to own
`backend/db` — set `PULSE_UID=$(id -u)` in `.env` (runs as the host user) or
`chown -R 10001:10001 backend/db`; documented as the #1 runbook gotcha. (2) The
image is large (torch + 3 boosters, ~3–4 GB on x86; smaller on ARM CPU-only) —
fine for Oracle's 50 GB volume; CPU-torch index documented to shrink x86. (3)
WAL assumes local disk (ext4/xfs), which Oracle/VPS block storage is — not NFS.

---

### ✅ PHASE 2.8.6-FOLLOWUP · A/B paper-test harness (pooled vs gated) — SHIPPED 2026-06-11

**Brief:** Phase 2.8.6 surfaced that un-gated pooled NET Sharpe (+0.351) beats
the current default gated_blend (+0.297) and baseline (+0.301) in walk-forward.
Goal: validate this under live paper execution before flipping the production
default. Don't ship the change in production blind — let the market run for
~2 weeks against both arms in parallel and only switch if the data agrees.

**Design decision — parallel paper books, dual-push per signal day.**

Considered three split strategies:

| split          | upside | rejected because |
|---             |---     |---               |
| alternate days | simple | confounds market regime with arm; halves the data each arm sees |
| split by spread | clean attribution per spread | confounds spread-mean-reversion strength with mode effect |
| **parallel books** | both arms see SAME market → matched-pair statistical power, clean attribution | minor risk of stacking when arms emit same signal — fixed with dedup on `(asset, direction, ab_mode)` |

Chose parallel books. Each tick generates BOTH `pooled` and `gated`
recommendations via the new `live_ranker.get_recommendation(force_mode=,
force_gated=)` override path (no env-var swap, no process-wide side
effect), iterates every spread that emits BUY/SELL, and writes one paper
trade per arm tagged with `ab_mode ∈ {'pooled', 'gated'}` on
`paper_trades`. The dedup helper `open_position_exists(asset, direction,
ab_mode)` prevents the daily tick from stacking multiple positions on a
persistent signal — matches what a live book would do (it doesn't double
down on a position it already holds).

**Stop criteria (when to declare a winner):**

1. **Minimum n_closed ≥ 30 per arm** — small-sample t-statistics aren't
   trustworthy below ~30 observations per group.
2. **Welch's t-test on per-trade NET PnL with p < 0.05** — Welch
   (unequal-variance) two-sample t-test is robust to per-arm variance
   asymmetry. Scipy used when available; normal-approx erfc fallback when
   not. Side note: we ALSO compute a paired t-test on
   `(session, asset, direction)`-matched closed trades — usually tighter
   p-value because matched-pair removes market-day noise.
3. **Hard timeout at 14 calendar days** — brief says "~2 weeks"; this is
   the operationalised version.

Verdict logic: if (1) AND (2) → declare winner = arm with higher NET mean
PnL. If only (3) elapses → `undecided_timeout` with the current numbers.
Otherwise `undecided` with a per-criterion explainer.

**NET headline (Phase 2.8.6 cost-aware):** per-trade NET PnL subtracts
the Phase 2.8.6 round-trip cost from the closed-trade realised PnL,
scaled by trade size. Sharpe annualised √252 on the NET series. Mirrors
the methodology PDF exactly so paper headline numbers are directly
comparable to the walk-forward report. `COST_PER_SPREAD_RT` is
duplicated in `ab_test.py` and kept in sync with `walkforward.py`
(gotcha 37 / 41 pattern — costs are a reporting layer, not a model
param, but the two must agree).

**Files touched (Phase 2.8.6-followup):**

| File | Change |
|---|---|
| `backend/research/live_ranker.py` | + `force_mode`, `force_gated` kwargs on `get_recommendation()` so callers can override env-var-driven mode resolution at call-time without process-wide side effects (the A/B harness uses this to generate both arms in one tick). Default behaviour unchanged — when both kwargs are None, the existing `_active_mode()` + `_gated_blend_enabled()` paths fire as before. |
| `backend/paper_trading.py` | + `ab_mode TEXT DEFAULT NULL` and `ab_session TEXT DEFAULT NULL` columns on `paper_trades` (added via `ALTER TABLE` for backward-compat with existing DBs; legacy non-A/B rows have ab_mode=NULL). `push_trade()` accepts `ab_mode` + `ab_session` kwargs. New `open_position_exists(asset, direction, ab_mode)` dedup helper. New `list_ab_trades(ab_mode=, status=)` query helper. |
| `backend/research/ab_test.py` | **NEW** — full harness. `tick(ab_session=)` runs one daily generation step. `get_report()` builds the per-arm metrics + Welch + paired t-test + stop-criteria progress + verdict. `_arm_metrics()`, `_welch_t()`, `_paired_t()`, `_net_pnl()`, `_cost_for()` helpers. `reset(scope=)` wipes A/B-tagged paper rows only. `COST_PER_SPREAD_RT` mirror of `walkforward.py`. |
| `backend/app.py` | + `/api/regime/ab` (GET) returns the report via `respond(ABReportResponse, …)`. + `/api/regime/ab/tick` (POST) fires one manual generation step. + `/api/regime/ab/reset` (POST) wipes A/B rows. + APScheduler job `_ab_tick` scheduled every 24h (starts 5 min after boot), gated by `PULSE_AB_TEST_DISABLED=1`. + `timedelta` added to existing `datetime` import. |
| `backend/schemas/__init__.py` | + `ABReportData` + `ABArms` + `ABArmMetrics` + `ABDiff` + `ABWelch` + `ABPaired` + `ABStopCriteria` + `ABArmEquityPoint` + `ABReportResponse`. Registered `/api/regime/ab` → `ABReportResponse` in `RESPONSE_MODELS`. |
| `frontend/src/lib/api-types.ts` | Regenerated by `python scripts/generate_ts_types.py` — 38 interfaces (was 29 after Phase 2.7). |
| `frontend/src/lib/api.ts` | Re-exports the new AB types. + `api.regimeAB()`, `api.regimeABTick(body)`, `api.regimeABReset(scope)`. |
| `frontend/src/components/panels/ABComparePanel.tsx` | **NEW** — verdict ribbon, two ARM cards (pooled gold / gated blue) with per-arm KPIs (n_closed, n_open, hit, sharpe NET, mean PnL NET, max DD NET, sharpe gross, total NET, mean cost), inline-SVG cumulative-NET equity chart with two-line legend, difference panel (Δ Sharpe / Δ mean PnL / Welch t / Welch p / paired n / paired p), stop-criteria progress with TrendingUp/Down icons. Manual TICK + RESET buttons with confirm. Polls `/api/regime/ab` every 30 s. |
| `frontend/src/views/RegimeView.tsx` | Mounts `<ABComparePanel />` below `<RegimePickCard />`. |
| `backend/db/pulse_cache.db` | Schema migrated in-place — `paper_trades.ab_mode`/`ab_session` columns added by `_ensure_table()` on first import after the change. Existing paper rows unaffected (ab_mode=NULL). |

**Verification (all 2026-06-11):**

- Smoke test `python -c "from research.ab_test import tick, get_report; print(tick(), get_report())"` from backend/: first tick pushed **4 pooled + 4 gated** paper trades on session 2026-06-11, 2 each skipped (NEUTRAL spreads), 0 errors. `get_report()` returns `verdict='undecided'` with `verdict_note` explaining `need >=30 closed/arm`.
- `python scripts/generate_ts_types.py` regenerated `api-types.ts` cleanly (9,567 bytes / 38 interfaces).
- `npx tsc --noEmit` clean (only pre-existing `baseUrl` deprecation).
- `npx vite build` clean — 6.92 s, 1.18 MB bundle (was 1.07 MB; +110 KB for the AB types + panel).
- Backend imports clean: `from research import ab_test, live_ranker; from paper_trading import push_trade, open_position_exists, list_ab_trades; print('OK')`.
- Dedup verified: a second `tick()` call within the same session re-fires every arm but every spread is skipped with reason `already_open` (because the first tick's positions are still OPEN). Matches design.
- Dashboard verified live (preview server): RegimeView shows the existing RegimePickCard with the new ABComparePanel mounted below. Verdict ribbon shows `UNDECIDED` with `need >=30 closed/arm (have 4/4); p_value unavailable (n too small)`. Both arm cards render with 4 opened / 0 closed and equity chart shows placeholder text ("equity curve appears once trades close"). TICK + RESET buttons functional.

**Operational guidance for the mentor:**

1. **Run for ≥ 14 calendar days** OR until 30 closed trades land per arm
   (whichever comes first). The TICK button on the dashboard lets her fire
   manually; the APScheduler will also run it once per 24 h.
2. **The verdict ribbon is the headline**. `pooled_wins` or `gated_wins`
   with `verdict_note` quoting `n_closed` + Welch `p_value` is the
   trigger to switch. `undecided_timeout` means run was inconclusive at
   14 days — extend the window or accept that the walk-forward signal
   was a sampling artifact.
3. **Don't conflate this with the regular paper book.** The legacy paper
   trades the trader manually pushes from the RegimePickCard still flow
   into the original Paper tab analytics; they have `ab_mode=NULL` and
   are excluded from the A/B aggregation. RESET on the AB panel only
   wipes `ab_mode IS NOT NULL` rows.
4. **Costs are subtracted, sizing is honoured.** Pooled arm uses
   `notional_scale=1.0` always (un-gated, no Phase 2.7 sizing applies).
   Gated arm respects whatever `PULSE_GATED_SIZE` is set (default `full`
   = 1.0). Cost scales with size on both arms.

**What this sprint did NOT do** (intentionally):

- Did not change the default production mode. `PULSE_GATED_BLEND=1`
  stays the default; the A/B harness pushes BOTH arms in parallel and
  observes. The default flip is a separate one-line change pending the
  A/B verdict.
- Did not modify the walk-forward report. Phase 2.8.6 NET numbers are
  unchanged; they're what the A/B is trying to live-validate.
- Did not retrain anything. Both arms use the same Phase 2.8.1+2 pooled
  models on disk; only the routing rule differs.
- Did not write a methodology PDF section yet. After the A/B verdict
  lands we'll regenerate the PDF with whichever arm won.

**Next session — followup to the followup:**

The harness needs ≥14 calendar days OR 30 closed trades/arm to declare
a verdict. Until then this CLAUDE.md current-sprint section stays open
as "live A/B in progress." The next mentor-facing milestone is reading
the verdict and writing the production-mode-flip PR (if pooled wins) or
keeping the gated default (if gated wins or undecided).

---

### ✅ EVENT-TO-DISTRIBUTION ASSIGNMENT — SHIPPED 2026-06-12

**Mentor's class assignment (2026-06-12):** convert the headline *"Israel
launches strikes on Iranian energy infrastructure. Iran threatens closure of
the Strait of Hormuz."* into 1-week probability distributions for Brent
M1-M2, M2-M4, M1-M6 — EV, 50 % range, 90 % range, scenario probabilities.
Deliverable: ≤10 slides + supporting code. Presented end of day.

**Framework (4 steps):**

1. **Event study** — 13 Middle-East / supply-threat events 2018-2025, 5-trading-day
   spread deltas from last close before each event, severity-tiered (1 = verbal/proxy,
   2 = shipping, 3 = energy infrastructure, 4 = supply war). **The June 2025
   Israel-Iran 12-day war is in our settle data and is the direct analog**:
   D+5 deltas +0.61 / +1.19 / +2.48, with the spike→ceasefire-collapse path
   visible daily (M1-M2 gave back 0.57 in one session on the ceasefire).
2. **Scenario tree** — 4 exhaustive outcomes with arguable priors:
   de-escalation 30 % (mean tilted NEGATIVE — base is stretched, M1-M2 2.91 vs
   10-yr p99 5.22) · sustained-conflict-Hormuz-open 40 % (= June-2025 D+5
   verbatim) · partial disruption 22 % (2.5× Abqaiq — note Abqaiq's M1-M2
   barely moved (+0.07) because SPR-release expectations cap the prompt; the
   belly carries infra shocks) · closure attempt 8 % (1.2× Russia-2022 +
   lognormal right tail; never observed in 40 yrs, Iran self-deterred — its own
   1.5-1.7 mb/d transits Hormuz).
3. **Conditional (μ, σ) per scenario per spread** — σ floored at BACK-regime
   weekly vol (1.02 / 1.23 / 2.71 — current regime BACK/LOW/STRESSED, ~2×
   unconditional vol; PULSE classifier reused).
4. **Monte Carlo mixture** — 200k draws, one-factor correlation ρ=0.84
   (measured from 5-day spread-change co-movement).

**The answer (as of 2026-05-26 data):**

| spread | now | EV (1 wk) | 50 % range | 90 % range | P(widen) |
|---|---|---|---|---|---|
| M1-M2 | 2.91 | **3.24** (+0.33) | 2.15-4.13 | 0.78-6.04 | 55 % |
| M2-M4 | 5.77 | **6.85** (+1.08) | 5.26-8.01 | 3.66-11.05 | 65 % |
| M1-M6 | 12.98 | **15.09** (+2.11) | 11.73-17.54 | 8.22-23.91 | 64 % |

Headline insight: the front spread is the coin-flip (stretched base unwinds
hardest on de-escalation); the belly carries the cleanest widening signal
(the Abqaiq lesson — no SPR offset 2-4 months out).

**Files:**

| File | What |
|---|---|
| `backend/research/event_study.py` | Full pipeline: event study → scenario params → MC mixture → 6 dark-theme charts + results.json + event_deltas.csv. `python -m backend.research.event_study` (~20 s, needs `PYTHONIOENCODING=utf-8` per gotcha 19). |
| `backend/data/research/event_study/` | results.json, event_deltas.csv, 6 chart PNGs (gitignored dir). |
| `scripts/deck/build_event_deck.js` | pptxgenjs deck builder (`node scripts/deck/build_event_deck.js`). Local npm install in scripts/deck/. |
| `docs/PULSE_event_to_distribution.pptx` | **The deliverable** — 10 slides, PULSE dark theme, QA'd via PowerPoint COM export. |

**Verification:** MC seed=42 reproducible; slides exported to PNG via
PowerPoint COM and visually inspected (footer collision + label overlap
fixed in one QA cycle); all scenario means traceable to event_deltas.csv rows.

---

### 🟡 DEPLOYMENT — Cloudflare Tunnel (mentor demo, 2026-06-12)

Dashboard exposed to the public internet via Cloudflare Tunnel so the
mentor can hit it from her phone / home without a VPN. Decision rationale
documented up-front so a future session doesn't redo the comparison:

| Option | Why rejected / picked |
|---|---|
| Oracle Cloud free tier | 1 week to provision + ATO friction; mentor demo is today |
| Hetzner / Render | Real money, real infra setup, real DNS hassle |
| **Cloudflare Tunnel (quick)** | **PICKED for today** — zero infra, working in 10 min, URL is `*.trycloudflare.com` |
| Cloudflare Tunnel (named) + Access | Picked for after admin access lands — stable URL + email-gated auth |

**Current state (2026-06-12) — quick tunnel.**

- **URL**: `https://jacket-army-appointed-racing.trycloudflare.com` (changes if cloudflared restarts)
- **Architecture**: cloudflared (foreground PowerShell on the office desk) → tunnel → http://localhost:5000 → Flask + React build
- **No auth in front yet** — quick tunnel has no Access integration. Acceptable risk for a 1-day demo with a non-guessable URL the mentor was sent directly. **Do NOT post this URL publicly.**
- **Why no Windows service install**: needs admin password (Windows 11 Enterprise office machine). User has filed an IT request; until granted, cloudflared runs in a foreground PowerShell window.
- **Sleep prevention**: `powercfg /change standby-timeout-ac 0 / monitor-timeout-ac 0 / disk-timeout-ac 0 / hibernate-timeout-ac 0` — desk never sleeps while plugged in. Screen lock auto-suspend may still kick in via office GPO; not blocking the tunnel.
- **Binary**: `cloudflared.exe` lives at the repo root (gitignored). Downloaded from `https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe`, version 2026.6.0 verified.

**How to start the tunnel from a cold desk (~3 commands):**

```powershell
# 1. Make sure Flask is running
cd C:\Users\peruka.pranav\Downloads\pulse
.\.venv\Scripts\python.exe start.py
# (wait ~15s for boot, http://127.0.0.1:5000/api/health → status: ok)

# 2. New PowerShell window — start the tunnel
cd C:\Users\peruka.pranav\Downloads\pulse
.\cloudflared.exe tunnel --url http://localhost:5000

# 3. Copy the *.trycloudflare.com URL from the cloudflared output
#    Mentor URL goes stale on every restart — update memo + PPT slide 10
```

**How to restart Flask cleanly** (if it crashes or you need a fresh boot):

```powershell
# Find the python process owning port 5000
netstat -ano | findstr ":5000"
Stop-Process -Id <PID> -Force
# Then start.py again as above
```

**Pre-flight gotchas that bit this session — DO NOT REPEAT:**

1. **`.env` vs `env`** — `load_dotenv()` (in `backend/app.py`) looks for the file named `.env`. If the file was copied from another machine as `env` (no dot), API keys silently don't load and `cot_history` / `external_history` / `inventory_history` all fall back to empty caches and `build_features()` returns shape `(0, 0)`. **Always verify `Test-Path .env`** before troubleshooting empty regime data.
2. **`xlrd` missing** — `cot_history._build_history()` downloads CFTC `.xls` (legacy format, not `.xlsx`). Without `xlrd>=2.0.1` installed, every year fails silently with `Missing optional dependency 'xlrd'`. `requirements.txt` should pin it; if a fresh venv ever skips installing it, `pip install xlrd` and re-run `python -m backend.research.cot_history`.
3. **Stale `external_history.parquet`** — pre-Phase-2.8.2 caches only have yfinance columns (`crack_321`, `wti_brent_spread`). Phase 2.8.2 added FRED-sourced `real_rate` and `ovx_vix_ratio`. If those columns are missing, `build_features().dropna(subset=BRENT_FEATURES)` wipes every row. **Fix**: `python -m backend.research.external_history` to force-rebuild from FRED API. (Detect: count `external_history.parquet` columns — should be ≥ 14, not 9.)
4. **Model PKLs are gitignored** — `backend/data/research/models/`, `models_pooled/`, `*.json`, `*.parquet` are all in the gitignore. When migrating to a new machine, either copy them from the old machine OR rebuild: `python -m backend.research.models --mode composite && python -m backend.research.models --mode pooled` (~2 min total on a modern desk).
5. **Background `&` in PS5.1** — PowerShell 5.1 (Windows default) does NOT support bash-style `command &` for backgrounding. Use `Start-Process` or the harness's `run_in_background: true`. Trying to write a one-liner with `& python ... &` is a parse error.

**Upgrade path — once admin access lands:**

| Step | Command | Notes |
|---|---|---|
| 1. Cloudflare account login | `cloudflared tunnel login` | Opens browser; pick `peruka.pranav@...` zone. No admin needed yet. |
| 2. Pick domain | Either own a domain (cheapest: ~$10/yr Namecheap → set NS to Cloudflare) OR use Cloudflare Workers `*.workers.dev` proxying OR use free `*.duckdns.org` (won't get Cloudflare Access; would need a third-party gate) | Cloudflare Access needs a real domain on Cloudflare DNS. |
| 3. Create named tunnel | `cloudflared tunnel create pulse` | Outputs `<UUID>` + writes credentials JSON to `%USERPROFILE%\.cloudflared\<UUID>.json` |
| 4. Config | Write `%USERPROFILE%\.cloudflared\config.yml`: `tunnel: <UUID>` + `credentials-file: ...` + `ingress: [{hostname: pulse.<domain>, service: http://localhost:5000}, {service: http_status:404}]` | |
| 5. DNS route | `cloudflared tunnel route dns <UUID> pulse.<domain>` | Creates a CNAME at Cloudflare DNS |
| 6. Install as Windows service | `cloudflared service install` (admin PowerShell) → starts on boot, survives logoff | **This is the step that needs admin.** Until then run `cloudflared tunnel run pulse` in a foreground window. |
| 7. Cloudflare Access | Zero Trust dashboard → Access → Applications → Add → self-hosted → app domain `pulse.<domain>` → policy "Emails: mentor@..., owner@..." | Free tier covers up to 50 users. Mentor gets a one-time email code on first visit; session stickies for 24 h. |

After upgrade, update slide 10 + the memo with the stable URL and re-run the phone smoke test (must hit Cloudflare Access login wall, then dashboard).

**Files touched (Deployment, 2026-06-12):**

| File | Change |
|---|---|
| `cloudflared.exe` | **NEW (gitignored)** — Cloudflare tunnel binary v2026.6.0 at repo root. Run as `.\cloudflared.exe tunnel --url http://localhost:5000`. |
| `.gitignore` | + `cloudflared.exe` |
| `.env` | **NEW (gitignored)** — copy of pre-existing `env` (no dot) so `load_dotenv()` finds the API keys. `env` is kept on disk for backward compat but `.env` is authoritative. |
| `backend/data/research/external_history.parquet` | Rebuilt with Phase 2.8.2 FRED columns (`dgs10`, `t5yie`, `real_rate`, `ovx`, `vix`, `ovx_vix_ratio`) — 9 cols → 15 cols. Old cache was from pre-2.8.2 desk. |
| `backend/data/research/cot_history.parquet` | **NEW** — rebuilt from CFTC zips (`xlrd` was missing on this venv). 636 weekly rows. |
| `backend/data/research/crude_stocks_history.parquet` | **NEW** — built from EIA v2 API. 600 weekly rows. |
| `backend/data/research/models/*.pkl` | **NEW** — 264 composite-mode pkls. Retrained on this desk. |
| `backend/data/research/models_pooled/*.pkl` | **NEW** — 60 pooled-mode pkls. |
| `backend/data/research/backtest_report.json` + `backtest_report_pooled.json` | **NEW** — regenerated as side effects of the retrain. |
| `docs/PULSE_demo_slides.md` | **NEW** — 10-slide outline for the mentor walkthrough. Copy/paste into PowerPoint. |
| `docs/mentor_memo_draft.md` | **NEW** — draft message to send the mentor pointing at the demo URL + A/B panel. Not sent yet. |

**Verification (all 2026-06-12):**

- `GET https://jacket-army-appointed-racing.trycloudflare.com/api/health` returns `status: ok`.
- Mentor-phone smoke test: dashboard loads on mobile data (off office WiFi), Regime tab renders `BACK/LOW/STRESSED`, top-pick `BUY Brent front fly (XGBoost, conf 0.96)`, A/B panel shows verdict `UNDECIDED` with `4/4 trades opened, 0 closed`.
- `powercfg /query SCHEME_CURRENT SUB_SLEEP` confirms STANDBYIDLE=0, hibernate=0, monitor=0 on AC.
- All 6 spreads eligible in `/api/regime/recommendation`; competition grid shows all 7 candidates per cell.

**What this section did NOT do (intentionally):**

- Did not run a walk-forward on this desk. The previous walk-forward report on the laptop is the authoritative `walkforward_report.json` for the mentor demo. Re-running here would take ~3 h with no expected change in numbers (same data, same code).
- Did not set up named tunnel + Access. Waiting on admin access.
- Did not migrate any paper trade history. `pulse_cache.db` is fresh on this desk — A/B harness has its first session as 2026-06-11 (4 + 4 trades open, none closed). Mentor will see this honest "harness running, awaiting data" state, which is the correct mentor-facing message anyway.

**Next session — once admin access lands:**

Follow the "Upgrade path" table above. Estimated 20 min including DNS propagation. After that, update slide 10 + memo with the stable URL and re-run the phone smoke test.

---

### ✅ PHASE 2.8.6 · Transaction costs in the walk-forward — SHIPPED 2026-06-11

**Brief:** Phase 2.8.3 widened the gate but the gated_blend headline stayed
flat at +0.384 because the booster alpha was already leaking into baseline
attribution. The honest next-credible lever for a credibility lift was
**modelling per-trade transaction cost** so the gated/sized NET Sharpe
reflects what a live book would actually experience. Phase 2.8.6 layers a
defensible cost model on top of the existing trade tapes; no retraining
needed because cost-aware Sharpe is a post-aggregation arithmetic operation.

**Cost model (defensible, exchange-published-fee anchored):**

Per leg, per side:
- Commission + clearing + brokerage: **$0.0025/bbl** (~$2.45 per 1,000-bbl
  contract; ICE Brent ~$1.45/side + clearing ~$0.30 + brokerage ~$0.70)
- Half bid-ask slippage: **$0.0050/bbl** front (M1/M2), **$0.0075/bbl** deferred (M3-M6)

Round-trip cost = N legs × 2 sides × (commission + half-spread). Yields:

| spread | RT cost $/bbl |
|---|---|
| brent_m1_m2 / wti_m1_m2     | **$0.030** |
| brent_m3_m6 / wti_m3_m6     | **$0.040** |
| brent_fly_123 / wti_fly_123 | **$0.050** |

Cost scales with `sizing_scale` on regime rows (half-sized regime trade =
half the contracts = half the fees). NEUTRAL trades incur zero cost (no
fill). Applied at the AGGREGATION step only — model training/CV is
unaffected, so no retraining required when the cost model changes.

**Headline (gross vs net Sharpe, 2026-06-11):**

| Mode             | Gross Sharpe | Net Sharpe | Δ (cost drag) | Mean cost/fire | n fired |
|---               |---           |---         |---            |---             |---      |
| baseline 252d z  | +0.385       | **+0.301** | −0.084        | $0.0392        | 2,082   |
| pooled (un-gated) | +0.437      | **+0.351** | −0.086        | $0.0404        | 1,996   |
| gated_blend (2.8.3) | +0.384    | **+0.297** | −0.087        | $0.0395        | 2,154   |
| sized_half       | +0.346       | +0.259     | −0.087        | $0.0370        | 2,154   |
| sized_kelly      | +0.332       | +0.246     | −0.086        | $0.0365        | 2,154   |

**Per-spread NET (gated_blend, vs baseline NET):**

| spread          | gated gross Shp | gated NET Shp | baseline NET Shp | Δ NET vs base |
|---              |---              |---            |---               |---            |
| brent_fly_123   | +1.534          | +1.320        | +1.555           | **−0.235** (baseline wins) |
| brent_m1_m2     | +0.934          | +0.859        | +0.860           | −0.001 (tie) |
| brent_m3_m6     | −0.268          | −0.339        | −0.339           | 0.000 (tie, both bad) |
| wti_fly_123     | +0.884          | +0.744        | +0.762           | −0.018 |
| wti_m1_m2       | +0.259          | +0.206        | +0.199           | **+0.007** |
| wti_m3_m6       | +0.298          | +0.207        | +0.195           | **+0.012** |

**Gated_blend NET by source (which leg of the gate carries which slice):**

| source   | n_fired | Net Sharpe | Net mean PnL | Mean cost/fire |
|---       |---      |---         |---           |---             |
| regime   | 244     | **+0.806** | +0.4447      | $0.0451 (highest — fly-heavy mix) |
| baseline | 1,910   | +0.218     | +0.0971      | $0.0388        |

**Findings:**

1. **Costs drag every mode by roughly the same ~−0.085 Sharpe** because the
   per-trade cost (~$0.040 mean) is mostly determined by spread mix, not by
   which strategy fires. The relative rankings between modes are preserved.

2. **gated_blend NET (+0.297) is essentially TIED with baseline NET (+0.301)**
   — Δ −0.004. Costs do NOT flip the Phase 2.8.3 "flat headline" verdict.
   They erode both modes equally; the engine is no better or worse against
   baseline under realistic friction.

3. **Pooled (un-gated) is the surprise headline winner under NET costs too.**
   Pooled gross Sharpe is +0.437 (lifted from +0.195 in Phase 2.5 by the
   booster + alpha-feature expansion). Under costs it lands at +0.351 NET
   — **+0.05 above baseline NET, +0.05 above gated_blend NET**. The Phase
   2.6 gate was added when pooled was losing badly; Phase 2.8.1+2 made
   pooled strong on its own, and the gate is now over-restrictive (rejects
   too many fires that would have been profitable).

4. **Regime leg of gated_blend still earns alpha NET** — 244 fires at NET
   Sharpe **+0.806** (vs gross +0.888). The engine works on the slice it
   speaks on; it's just that the slice is small and the gated_blend headline
   is baseline-dominated under the production rule.

5. **The mean cost on regime fires ($0.0451) is higher than baseline fires
   ($0.0388)** because boosters concentrate on the fly (the most expensive
   spread class at $0.050/RT). This was the brief's hypothesis — "boosters
   fire ~3.4× more often, so net Sharpe differential may shift" — and the
   answer is qualitatively yes (regime mean cost is ~16 % higher) but
   quantitatively small enough that it doesn't move the headline.

**Concrete production recommendation (updated for Phase 2.8.6):**

- **A/B test `PULSE_REGIME_MODE=pooled` (no gate) against
  `PULSE_GATED_BLEND=1` in paper trading** for ~2 weeks. The walk-forward
  says pooled un-gated wins by +0.05 net Sharpe; paper validation will
  confirm or refute under live execution drag.
- **Keep `PULSE_GATED_BLEND=1` as today's default** until the A/B has data
  — the gated blend has been the production rule since Phase 2.6 and the
  paper book reflects that.
- **If pooled wins the A/B, switch defaults**; the gated blend can stay
  available as a defensive mode for traders who want the regime leg
  attribution badge on the dashboard.

**Files touched (Phase 2.8.6):**

| File | Change |
|---|---|
| `backend/research/walkforward.py` | + `COST_PER_SPREAD_RT` dict + `COST_DEFAULT_RT` + `_cost_for(trade)` helper. Extended `_metrics`, `_by`, `_by_curve_axis`, `_by_source`, `_by_spread_source` to accept an optional `cost_fn`. New `_net_block(trades, include_source)` helper. `run_walkforward()` now writes a top-level `costs` block to the report containing per-spread RT table + NET metrics for composite/pooled/baseline/gated_blend/sized_* + lift tables. Also persists `composite_trades.json`, `pooled_trades.json`, `baseline_trades.json` alongside the existing `gated_trades.json` so future cost-model tweaks can re-aggregate without the ~3h walk-forward. CLI summary prints gross vs net Sharpe + mean cost per fire per mode. |
| `backend/research/reroute_gated.py` | + sys.path bootstrap (so `python -m backend.research.reroute_gated` works without setting `PYTHONPATH`). + Phase 2.8.6 NET section: rebuilds the baseline tape from `build_spread_series()` (deterministic), computes NET blocks for baseline/pooled (reconstructed)/gated_blend/sized_*, writes into `report["costs"]`. Composite NET skipped here because pre-2.8.6 walk-forward didn't persist `composite_trades.json`; a fresh walk-forward will populate it. CLI summary at the end prints the same gross-vs-net headline + per-spread NET breakdown. |
| `backend/research/methodology_pdf.py` | + §11 on page 1 documenting the cost model (per-leg per-side breakdown + RT cost per spread). + Phase 2.8.6 NET headline table on page 2 (gross / net Sharpe + mean cost + n fired per mode) + per-spread NET Sharpe table (gross gated / net gated / net baseline / Δ) + Phase 2.8.6 finding callout (adapts text based on measured Δ between gated NET and baseline NET; surfaces the "pooled wins" side finding when warranted). Caveats updated — "costs not modelled" replaced with the Phase 2.8.6 cost model description. |
| `backend/data/research/walkforward_report.json` | Regenerated via reroute. New top-level `costs` block (~50 KB). Report size 111 KB → 164 KB. |
| `backend/data/research/PULSE_methodology.pdf` | Regenerated. 14.8 KB → 18.3 KB. 2 pages → 5 pages (extra content). |
| `backend/data/research/composite_trades.json` etc. | **NOT yet on disk** — will be written when next full walk-forward runs. Reroute can't materialise composite trades from `gated_trades.json` alone. |

**Verification (all 2026-06-11):**

- `PYTHONIOENCODING=utf-8 python -m backend.research.reroute_gated` runs in
  ~12 s end-to-end (includes the ~10 s `build_spread_series()` warmup for
  the rebuilt baseline tape). Prints OLD-vs-NEW gated headline (unchanged
  by Phase 2.8.6), the per-spread Δ (unchanged), then the new Phase 2.8.6
  NET headline + per-spread NET breakdown.
- `python -m backend.research.methodology_pdf` regenerates the 5-page PDF
  in <1 s. Verified via `pdfplumber` extraction: §11 cost model on page 2,
  NET headline table + per-spread NET table on page 4, finding callout
  with the "pooled un-gated beats both" side finding rendered correctly.
- `PYTHONIOENCODING=utf-8 python -c "from backend.research import
  walkforward, reroute_gated, methodology_pdf, live_ranker, models;
  print('imports OK')"` clean.
- `_cost_for` smoke test confirms:
  - Brent fly fired regime trade → $0.050 (full notional)
  - NEUTRAL trade → $0.000 (no fill)
  - Half-sized regime fly → $0.025 (sizing-scale applied)

**What this sprint did NOT do** (intentionally — out of scope):

- Did not retrain any models. Cost is a reporting layer, not a CV input.
- Did not change live inference paths. `live_ranker.py` continues to surface
  gross fair value + z + bands; cost-awareness lives in the methodology PDF
  + walk-forward report only. If we A/B test pooled vs gated and pooled
  wins, the live_ranker change is just flipping the default `PULSE_REGIME_MODE`
  — already implemented in Phase 2.5.
- Did not estimate slippage from /Data 1-min mids. The brief mentioned this
  as an option; chose exchange-published-fee anchored numbers instead because
  they're more defensible to the mentor and don't require a multi-day
  microstructure study. The numbers are configurable in `COST_PER_SPREAD_RT`
  if mentor wants to override.
- Did not write `composite_trades.json` yet — that requires a full walk-forward
  run, deferred until a sprint needs to retrain anyway.

**Phase 2.8 remaining tasks — sequencing after 2.8.6:**

| # | Task | Status |
|---|---|---|
| **2.8.4** | Pool to one global model with regime-as-feature. | pending |
| **2.8.5** | Soft regime probabilities — replace hard thresholds. | pending |
| **2.8.7** | Multi-horizon sweep (5/20/60d) and pick per spread. | pending |
| **2.8.8** | Extend walk-forward to 2018-2026 (contango coverage). | **promoted to next-credible candidate** — Phase 2.8.6 showed costs don't lift the headline, but extending to 8 years (including 2018-2020 contango) is the largest remaining structural change. Would also need a fresh walk-forward run which persists `composite_trades.json` for full Phase 2.8.6 NET coverage. |
| **2.8.9** | HMM or change-point regime detection. | pending |
| **2.8.10** | Portfolio-level vol targeting. | pending |
| **2.8.11** | Methodology PDF + CLAUDE.md update — done for 2.8.6; will redo end-of-phase. | partial |

**Acceptance for Phase 2.8 as a whole** (revised after 2.8.6): the original
+0.65 gated Sharpe target hasn't moved (gated NET +0.297). But Phase 2.8.6
surfaced a credible alternative — **un-gated pooled NET +0.351** — that
beats baseline NET by +0.05 and beats gated_blend NET by +0.05. If the
A/B paper test confirms this, the mentor recommendation pivots from "ship
the gate" to "ship pooled un-gated" and the Phase 2.8 acceptance target
becomes "NET Sharpe ≥ baseline NET + 0.05" which is currently MET on
pooled. Worth raising with mentor before committing more sprint cycles to
2.8.4–2.8.10.

---

### ✅ PHASE 2.8.3 · Widen GATED_WINNERS to admit boosters — SHIPPED 2026-06-11

**Brief:** the Phase 2.6 gated-blend production rule was hard-coded to
`winner_model ∈ {Lasso, Huber}`. Phase 2.8.1 added three boosters
(XGBoost / LightGBM / CatBoost) that now legitimately win BACK cells in
the pooled walk-forward. The narrow gate rejected them, regressing the
gated_blend Sharpe from +0.456 to +0.389 between Phase 2.7 and Phase
2.8.2. Phase 2.8.3 widens `GATED_WINNERS` to the full booster + linear
union and re-aggregates the gated leg.

**Files touched (Phase 2.8.3):**

| File | Change |
|---|---|
| `backend/research/walkforward.py` | `GATED_WINNERS` extended from `{Lasso, Huber}` → `{Lasso, Huber, XGBoost, LightGBM, CatBoost}` |
| `backend/research/live_ranker.py` | Mirror change to the live-inference gate (per gotcha 26, must stay bit-for-bit identical) |
| `backend/research/reroute_gated.py` | **NEW** — one-shot re-aggregation script. Reconstructs `pooled_trades` + `baseline_trades` from the existing `gated_trades.json` (Phase 2.8.2 walk-forward already trained the full 7-candidate competition; the gate change only affects ROUTING, not training), runs `_build_gated_blend` + `_apply_sizing` + `_aggregate_mode` under the widened gate, and rewrites the gated_blend + sized_blend + lift blocks of `walkforward_report.json`. Composite + pooled + baseline blocks are untouched. Runs in <2 s vs the full ~3h walk-forward. |
| `backend/data/research/walkforward_report.json` | Regenerated: gated_blend + sized_blend blocks reflect the widened gate. |
| `backend/data/research/gated_trades.json` | Regenerated under the widened gate. |
| `backend/data/research/PULSE_methodology.pdf` | Regenerated from the updated report. |

**Headline (Phase 2.8.2 narrow gate → Phase 2.8.3 widened gate):**

| Metric                       | OLD (2.8.2) | NEW (2.8.3) | Δ |
|---                           |---          |---          |---|
| gated_blend overall sharpe   | +0.389      | **+0.384**  | −0.005 (flat) |
| gated_blend overall hit_rate | 0.7165      | 0.7103      | −0.006 |
| gated_blend overall mean_pnl | +0.1809     | +0.1759     | −0.0050 |
| gated_blend overall n_signals| 2,092       | 2,154       | +62 |
| gated_blend overall max_dd   | −257.71     | −255.50     | +2.21 |
| **regime leg sharpe**        | +0.369      | **+0.888**  | **+0.519** |
| **regime leg n_signals**     | 71          | **244**     | **+173** |
| baseline leg sharpe          | +0.393      | +0.306      | −0.087 |
| baseline leg n_signals       | 2,021       | 1,910       | −111 |

**Per-spread gated Sharpe vs baseline (Phase 2.8.3):**

| spread          | gated (new) | baseline | Δ vs base |
|---              |---          |---       |---        |
| brent_fly_123   | +1.534      | +1.763   | −0.229    |
| brent_m1_m2     | +0.934      | +0.935   | −0.001    |
| brent_m3_m6     | −0.268      | −0.268   |  0.000    |
| wti_fly_123     | +0.884      | +0.895   | −0.011    |
| wti_m1_m2       | +0.259      | +0.251   | +0.008    |
| wti_m3_m6       | +0.298      | +0.286   | +0.012    |

**Per-spread regime-leg Sharpe (NEW, the slice the engine truly owns):**

| spread          | regime leg sharpe | n_signals | hit |
|---              |---                |---        |---  |
| brent_fly_123   | +0.956            | 85        | 61.2% |
| brent_m1_m2     | +0.292            | 51        | 62.7% |
| wti_fly_123     | **+1.499**        | 95        | 75.8% |
| wti_m3_m6       | **+1.610**        | 9         | 77.8% |
| wti_m1_m2       | +9.869            | 4         | 100% (n too small to read) |

**Acceptance verdict: NOT MET.** The brief predicted gated_blend Sharpe
≥ +0.60. Measured: +0.384. The prediction was based on the by-cohort
pooled walk-forward Sharpe of the boosters (LightGBM +1.294 / CatBoost
+1.248) — a slice-level number that doesn't translate to blended
headline lift.

**Honest interpretation of what happened — methodologically clean, no
new alpha at the blended level:**

The widened gate operates correctly. The 173 booster-winner BACK-regime
trades that were previously routed to baseline now route to regime
(244 = 71 original + 173 newly admitted; baseline drops by 111 fires
because 62 of the 173 were NEUTRAL under baseline z but non-NEUTRAL
under pooled z, so they're new fires not removals).

The regime leg's Sharpe jumps to **+0.888** across 244 trades —
material and presentable. The booster trades genuinely contribute
when treated as regime signals. The 9 wti_m3_m6 regime fires at
Sharpe +1.610 and the 95 wti_fly_123 fires at +1.499 are real.

**But the gated_blend HEADLINE doesn't move** because:

1. Most of the 173 re-routed trades had baseline-z direction matching
   pooled-z direction. Their realized PnL is the same regardless of
   which leg owns them; only the attribution label changes.
2. The 62 truly-new fires (pooled-z agrees with regime, baseline-z
   said NEUTRAL) contribute Sharpe ≈ +0.49 mean PnL — strong, but
   62 trades in a 2,154 trade blend doesn't shift the headline.
3. Removing the booster trades from baseline drops the baseline leg's
   Sharpe from +0.393 to +0.306 — those trades were *carrying* the
   baseline leg's headline under the narrow gate. The widening
   redistributes credit; it doesn't print new money.

**Why this still ships:**

- The widened gate is methodologically more correct. Under the narrow
  gate the regime engine's Sharpe was understated (booster alpha was
  being attributed to baseline). Under the widened gate the engine
  reports its honest Sharpe of **+0.888**.
- Live inference now routes booster-win BACK signals through the
  regime engine (the `live_ranker.GATED_WINNERS` mirror change) — the
  dashboard shows a REGIME source badge on trades where boosters won,
  rather than falsely labelling them BASELINE.
- The per-spread regime-leg breakdown (wti_fly +1.499, wti_m3_m6
  +1.610) becomes presentable evidence for the mentor that the engine
  earns alpha when conditions are right.
- No retraining was required — the on-disk pooled models from Phase
  2.8.1 are unchanged. Only the routing rule changed.

**What the brief got wrong:** it assumed the booster trades' alpha
under cohort-aggregation (Sharpe +1.294 etc.) implied a +0.20 headline
lift. That arithmetic is wrong because the alpha was *already* flowing
through the baseline-source attribution — the boosters' directional
calls happen to agree with the baseline z-score on most of these
trades. Phase 2.8.6 (transaction costs) is the next-credible
headline-mover: boosters fire more often than the narrow gate, so they
pay more cost per cohort — that's a real differentiator.

**Sized blend (Phase 2.7) under widened gate, unchanged finding:**

| mode  | sharpe | mean_pnl | max_dd  |
|---    |---     |---       |---      |
| full  | +0.384 | +0.176   | −255.50 |
| half  | +0.346 | +0.148   | −264.68 |
| kelly | +0.332 | +0.140   | −269.52 |

Sizing still doesn't help the headline (Phase 2.7's DD-compression
hypothesis remains disproved). The per-spread story under sizing is
unchanged from Phase 2.7 — `PULSE_GATED_SIZE=half` remains an opt-in
flag for Brent fly variance reduction, not a default.

**Verification (all 2026-06-11):**

- `python -m backend.research.reroute_gated` runs in <2 s. Loads
  3,638 gated trades, reconstructs 3,638 pooled + 3,553 baseline
  candidates, re-routes under widened gate, rewrites the report.
  Final state confirmed: `gate.winners = ['CatBoost', 'Huber',
  'Lasso', 'LightGBM', 'XGBoost']`.
- `python -m backend.research.methodology_pdf` regenerates the
  2-page PDF in <1 s. Headline + per-spread tables reflect new
  numbers automatically.
- `walkforward_report.json` size: 111 KB (was 107 KB) — extra rows
  in lift tables.
- The full ~3h walk-forward was attempted earlier at 06:56 but the
  process died at ~08:22 mid-pooled-refit-3 (laptop sleep). The
  reroute shortcut delivers an *identical* result because the wider
  gate is a strict superset of the narrow one and no per-cell winner
  changed — only the routing rule did. See `reroute_gated.py`
  docstring for the mathematical argument.

**Files NOT regenerated** (no change needed):

- `backend/data/research/models/`, `models_pooled/` — pkls unchanged.
  Gate widening doesn't retrain anything.
- `backend/data/research/backtest_report.json`,
  `backtest_report_pooled.json` — single-cutoff training reports;
  unaffected by gate.
- `backend/data/research/cot_history.parquet`,
  `external_history.parquet`, `crude_stocks_history.parquet` —
  feature caches; unaffected.
- Composite / pooled / baseline blocks of `walkforward_report.json` —
  re-aggregation only touches the gated_blend, sized_blend, and
  lift_* sections.

**Phase 2.8 remaining tasks — sequencing after 2.8.3:**

| # | Task | Status |
|---|---|---|
| **2.8.6** | Transaction costs in the walk-forward. | ✅ **shipped 2026-06-11** (see Phase 2.8.6 section above). |
| **2.8.4** | Pool to one global model with regime-as-feature. | pending |
| **2.8.5** | Soft regime probabilities — replace hard thresholds. | pending |
| **2.8.7** | Multi-horizon sweep (5/20/60d) and pick per spread. | pending |
| **2.8.8** | Extend walk-forward to 2018-2026 (contango coverage). | pending |
| **2.8.9** | HMM or change-point regime detection. | pending |
| **2.8.10** | Portfolio-level vol targeting. | pending |
| **2.8.11** | Methodology PDF + CLAUDE.md update — done for 2.8.3 and 2.8.6; will redo end-of-phase. | partial |

**Acceptance for Phase 2.8 as a whole** (revised after 2.8.6): Phase
2.8.6 confirmed the gate widening alone (2.8.3) and costs (2.8.6) do
not lift the gated_blend headline to the original +0.65 target. **But
Phase 2.8.6 surfaced a credible alternative**: un-gated pooled engine
NET Sharpe +0.351 (vs baseline NET +0.301, vs gated NET +0.297). If
mentor accepts "NET Sharpe ≥ baseline NET + 0.05" as the revised
acceptance bar, pooled un-gated currently MEETS it. Worth raising
before committing more sprint cycles to 2.8.4–2.8.10.

---

### ✅ PHASE 2.8.1 + 2.8.2 · 7-model competition + alpha features — SHIPPED 2026-06-11

**Brief:** lift gated_blend Sharpe by attacking the two structural weaknesses
honest Phase 2.7 reporting surfaced — linear models leaving non-linear
interactions on the table, and a feature set that was missing the
alpha-bearing predictors. Walk-forward end-to-end before/after; methodology
PDF and CLAUDE.md updated.

**Headline (10 quarterly refits, 2024-2026, regenerated 2026-06-11):**

| Mode             | Before (2.7) | After (2.8.1+2)  | Δ Sharpe | Verdict |
|---               |---           |---               |---       |---      |
| composite (27)   | +0.245       | **+0.431**       | **+0.186 (+76 %)** | **HUGE WIN** |
| pooled (3 curve) | +0.195       | **+0.437**       | **+0.242 (+124 %)** | **HUGE WIN** |
| gated_blend      | +0.456       | +0.389           | **−0.067 (−15 %)**  | **REGRESSION** ⚠️ |
| sized_half       | +0.434       | +0.392           | −0.042 | regressed with gated |
| sized_kelly      | +0.426       | +0.391           | −0.035 | regressed with gated |
| baseline 252d z  | +0.385       | +0.385           | flat | (sanity check; unchanged spread definition) |

**Why gated_blend regressed:** Phase 2.8.1 boosters (XGB / LGBM / CatBoost)
stole BACK-regime cells the Phase 2.6 gate's narrow `winner_model ∈ {Lasso,
Huber}` criterion locks out. Boosters in pooled mode deliver Sharpe **+1.294
(LightGBM)** and **+1.248 (CatBoost)** — stronger than the gate-eligible
Huber +1.107 and Lasso +0.781. But the gate currently rejects them, so the
85 fires it does allow (down from 97) are concentrated on the weaker
remaining slice. Result: gate Sharpe drops, baseline weight rises, headline
slips.

**Phase 2.8.3 is now a one-line gate widening** — change `GATED_WINNERS` to
include the booster families and re-run walk-forward. The 327 pooled BOOSTER
trades (LightGBM + CatBoost + XGBoost combined, all with Sharpe > +0.85)
that the current gate excludes are the obvious headline lift. **Predicted
gated Sharpe under widened gate: ≥ +0.60.**

**Where the composite + pooled lifts came from (per-spread, post-2.8):**

| spread          | composite (Δ vs 2.7) | pooled (Δ vs 2.7) | baseline |
|---              |---                   |---                |---       |
| brent_m1_m2     | **+1.467** (was +0.013, +1.45 lift!) | **+0.855** (was −0.144, +1.00 lift) | +0.935 |
| brent_m3_m6     | −0.283 (was −0.268, flat)            | −0.166 (was −0.246, +0.08 lift)     | −0.268 |
| brent_fly_123   | +0.980 (was +1.032, ~flat)           | +0.878 (was +0.848, slight lift)     | +1.763 |
| wti_m1_m2       | +0.242 (was +0.109, +0.13 lift)      | +0.454 (was +0.135, +0.32 lift)      | +0.251 |
| wti_m3_m6       | +0.306 (was +0.537, regression)      | +0.334 (was +0.451, regression)      | +0.286 |
| wti_fly_123     | +0.893 (was +0.778, +0.12 lift)      | +0.929 (was +0.912, ~flat)           | +0.895 |

**Composite mode now beats baseline on 4/6 spreads** (was 1/6 in Phase 2.7).
The headline win is **Brent M1-M2 composite Sharpe lifting from +0.013 to
+1.467 (+1.45 lift)** — a spread that was previously losing to baseline now
crushes it. Brent M3-M6 still loses to baseline (the structural finding
since Phase 2.5 — that spread's mean reversion is dominated by the rolling
z-baseline and per-cell models keep adding noise).

**Composite winner distribution (10 refits × ~65 fit cells/refit = ~660
cell-refits):**

| winner | n cell-refits | n signals (fired in walk-forward) | Sharpe |
|---|---|---|---|
| ElasticNet | 1137 | 1137 | +0.513 |
| Lasso      |  489 |  489 | +0.320 |
| Ridge      |  464 |  464 | +0.289 |
| Huber      |  191 |  191 | +0.739 (small slice but strong) |

For the per-cell BACKTEST_REPORT (single-cutoff at TRAIN_END=2026-03-31, 66
fit cells), the winner mix is more booster-friendly:

| winner     | cells won (of 66) | Phase 2.7 winners |
|---         |---                |---                |
| ElasticNet | 22                | 18                |
| Lasso      | 19                | 16                |
| Ridge      |  9                | 20                |
| XGBoost    |  6                | n/a (new)         |
| LightGBM   |  5                | n/a (new)         |
| CatBoost   |  4                | n/a (new)         |
| Huber      |  1                | 12                |

**Boosters won 15/66 composite cells (23%)** + 3/15 pooled cells (20%) on
the single-cutoff training run. They're disabled in walk-forward composite
mode by design (booster fits dominate refit wall-time and the gate excludes
them anyway), but they DO compete in walk-forward pooled mode where the
gated_blend lives.

**Phase 2.8.2 feature expansion — 11 → 22 Brent features:**

| feature | source | role |
|---|---|---|
| `curvature` = M1 − 2·M6 + M12 | Brent settle | fly-specific curve information |
| `inv_surprise` | EIA WCRSTUS1 weekly Δ − 4w MA | alpha is in the SURPRISE, not the level |
| `cot_mm_pct_156w` | CFTC disaggregated COT (NEW `cot_history.py`, 2014-2026 backfill) | managed-money crowding, contrarian |
| `crack_321` | yfinance RB/HO/CL daily history (NEW `external_history.py`) | refining-margin pressure on the front |
| `gasoline_crack` | yfinance RB/CL | gasoline-side of the same |
| `wti_brent_spread` | yfinance CL/BZ | Atlantic-basin arb width |
| `real_rate` | FRED DGS10 − T5YIE | storage-economics carry driver |
| `ovx_vix_ratio` | FRED OVXCLS / VIXCLS | crude-IV vs equity-IV risk-premium |
| `days_to_expiry` | calendar | front-month roll proxy |

Drivers list in `backtest_report.json` confirms the new features earn
non-zero weight: e.g. the latest top-pick (BUY Brent fly_123 under
BACK/LOW/STRESSED) is now an XGBoost winner whose top drivers are
`cos_doy` (0.193), `m1_m2_lag1` (0.142), `m1_m12_sq` (0.093) — XGBoost's
feature_importances_ now flow through `_extract_coefs` as proxy
coefficients so the dashboard's driver list stays informative even when the
winner isn't linear.

**Files touched (Phase 2.8.1 + 2.8.2):**

| File | Change |
|---|---|
| `backend/research/models.py` | + `_fit_xgb`, `_fit_lgbm`, `_fit_catboost`; lazy imports + `_HAS_XGB/_HAS_LGBM/_HAS_CATBOOST` flags; `_TIEBREAK_RANK` extended with boosters at the bottom (linear preferred on ties); `_extract_coefs` + `_active_features` handle `feature_importances_` for trees; `_BOOSTER_MIN_ROWS=80` skips boosters on small cells; tuned hyperparams (150 trees, depth 3-4, lr 0.05) for speed + regularisation |
| `backend/research/features.py` | + 9 alpha features (`curvature`, `inv_surprise`, `cot_mm_pct_156w`, `crack_321`, `gasoline_crack`, `wti_brent_spread`, `real_rate`, `ovx_vix_ratio`, `days_to_expiry`); BRENT_FEATURES 11 → 20; NaN audit clean (2,694 rows × 22+5 cols) |
| `backend/research/cot_history.py` | **NEW** — downloads ~12 years of CFTC disaggregated futures zips for Crude Oil WTI, caches a clean weekly history to `cot_history.parquet`. Surfaces `cot_mm_long`, `cot_mm_short`, `cot_mm_net`, `cot_mm_pct_156w`. Refreshes when older than 14 days |
| `backend/research/external_history.py` | **NEW** — fetches FRED (DGS10, T5YIE, OVX, VIX) + yfinance (CL=F, BZ=F, RB=F, HO=F) daily series back to 2014; computes `real_rate`, `ovx_vix_ratio`, `crack_321`, `gasoline_crack`, `wti_brent_spread`; caches to `external_history.parquet`. Refreshes when older than 7 days |
| `backend/research/walkforward.py` | + booster imports; **boosters compete in walk-forward only in pooled mode** (composite would 10x refit wall-time and the gated_blend can't consume them under the current gate anyway) |
| `backend/research/live_ranker.py` | `method` blurb now names the 7-model competition |
| `backend/research/methodology_pdf.py` | §4 documents 20-feature set + Phase 2.8.2 alphas; §5 documents 7-model competition; new §10 documents Phase 2.8 changes + the gate-broken finding |
| `frontend/src/components/panels/RegimePickCard.tsx` | `winner_model` union extended with `XGBoost`, `LightGBM`, `CatBoost`; competition grid now renders all 7 candidates dynamically when `competition` has > 4 keys |
| `requirements.txt` | + `xgboost==2.1.3`, `lightgbm==4.5.0`, `catboost==1.2.10` (CatBoost needs `--only-binary :all:` on Windows) |
| `backend/data/research/cot_history.parquet` | **NEW** — 636 weekly rows, 2014-04-01 → 2026-06-02 |
| `backend/data/research/external_history.parquet` | **NEW** — 3,245 daily rows, 2014-01-02 → 2026-06-10 |
| `backend/data/research/models/*.pkl`, `models_pooled/*.pkl` | retrained 324 pkls total (66 composite cells × 4 + 15 pooled cells × 4) |
| `backend/data/research/backtest_report.json` | regenerated — 7-candidate competition results, winner distribution incl. 15 booster wins |
| `backend/data/research/walkforward_report.json` | regenerated — composite/pooled/gated/sized headline tables |
| `backend/data/research/PULSE_methodology.pdf` | regenerated — 14.8 KB (was 13 KB), Phase 2.8 sections added |

**Verification:**
- `python -u -m backend.research.models --mode composite` completes in ~17 min (Phase 2.5 was ~2 min — boosters are the cost). Winner mix matches the brief's prediction: linear wins ties, boosters win when CV R² edge > 0.005.
- `python -u -m backend.research.models --mode pooled` completes in ~10 min.
- `python -u -m backend.research.walkforward` completes in ~3 hours (composite linear-only ~2h, pooled with boosters ~1h, baseline + aggregation < 1 min). With composite boosters disabled in walk-forward this is the steady-state cost. Re-enabling for ablation would 5x the cost.
- `python -m backend.research.methodology_pdf` regenerates the 2-page PDF in <1 s.
- Live dashboard (`http://127.0.0.1:5000`) serves the new Phase 2.8 models — `/api/regime/recommendation` returns the top pick **BUY Brent front fly with XGBoost as winner** (active_features=19/19), full 7-cell competition grid visible on the RegimePickCard.
- `npx tsc --noEmit` clean. `npx vite build` clean.

**Honest finding for the mentor:**

Phase 2.8.1 + 2.8.2 delivered the predicted lift in composite + pooled mode
— composite Sharpe lifted +76 %, pooled +124 %, and four of six spreads now
beat baseline under composite mode (was one of six). **But the Phase 2.6
gated_blend production rule was tightly bound to the Phase 2.5 finding that
specifically Lasso + Huber were the strong winners under the BACK regime,
and that binding is now obsolete.** When boosters earn the right to win
BACK cells via the CV competition, the gate keeps rejecting them, and the
gated_blend Sharpe regresses from +0.456 to +0.389.

The fix is one line: widen `GATED_WINNERS` to include the boosters. The
data already proves this works — in the new pooled walk-forward, the
booster cohorts deliver Sharpe **+1.294 (LightGBM, 113 fires) / +1.248
(CatBoost, 147 fires) / +0.853 (XGBoost, 67 fires)** — all stronger than
the currently-eligible Huber (+1.107) or Lasso (+0.781). Phase 2.8.3 is
just rewriting the gate and rerunning walk-forward to confirm a
predicted lift to gated Sharpe ≥ +0.60.

**Remaining Phase 2.8 tasks (3-11) — unchanged from the original plan**
unless redirected by mentor feedback:

| # | Task | Status |
|---|---|---|
| **2.8.3** | **Widen `GATED_WINNERS` to include boosters; re-run walk-forward.** Promoted from "conformal prediction" to "fix the gate that 2.8.1 broke." Predicted lift: +0.20 Sharpe (gated 0.389 → ~0.60). Conformal prediction deferred to a later slot. | next session |
| **2.8.4** | Pool to one global model with regime-as-feature. | pending |
| **2.8.5** | Soft regime probabilities — replace hard thresholds. | pending |
| **2.8.6** | Transaction costs in the walk-forward. | pending — required for credibility headline |
| **2.8.7** | Multi-horizon sweep (5/20/60d) and pick per spread. | pending |
| **2.8.8** | Extend walk-forward to 2018-2026 (contango coverage). | pending |
| **2.8.9** | HMM or change-point regime detection. | pending |
| **2.8.10** | Portfolio-level vol targeting. | pending |
| **2.8.11** | Methodology PDF + CLAUDE.md update — done for 2.8.1+2; will redo end-of-phase. | partial |
**Acceptance for Phase 2.8 as a whole** (unchanged): gated_blend NET Sharpe ≥ +0.65 over the full 2018-2026 walk-forward, with methodology PDF + walk-forward report regenerated and CLAUDE.md updated. After 2.8.1+2.8.2 we are at gated +0.389 GROSS — fix the gate (2.8.3), then transaction costs (2.8.6) + 2018-2026 walk-forward (2.8.8) are the remaining must-haves for credibility.

---

### ✅ CLASS-DEMO SPRINT + 4-MODEL COMPETITION — SHIPPED 2026-06-08

Mom asked in class for a **narrower** scope to discuss today, ahead of the
full Phase 2 brief. Shipped end-to-end in one session, then upgraded
the model selection from "Ridge default" to a real 4-way competition.

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
- `backend/research/models.py` — **4-model competition** per (spread, regime). Each cell fits Ridge / Lasso / ElasticNet / Huber via 5-fold TimeSeriesSplit CV. Winner picked by max mean CV R² (sparsity tiebreak: ElasticNet > Lasso > Ridge > Huber within 0.005). Plus Quantile p10/p50/p90 for confidence bands, fit separately. 12 cells × (winner + 3 quantile) = 48 fitted models saved to `backend/data/research/models/*.pkl`. Backtest report saved to `backend/data/research/backtest_report.json`.
- `backend/research/live_ranker.py` — classify today, predict, rank by `|z| × R²_oos × √(n/100)`, return #1 with full receipts including `winner_model`, `active_features`, full competition table.
- API: `/api/regime`, `/api/regime/recommendation`, `/api/regime/backtest`
- `frontend/src/components/panels/RegimePickCard.tsx` — new card on Paper Trading tab. Shows winner-model badge + 4-candidate competition grid with winner highlighted in gold + active features count + driver coefficients from the actual winning model.
- **Spread-aware paper trading**: `paper_trading._live_price()` now recognises spread asset keys (`brent_m1_m2`, `brent_m3_m6`, `brent_fly_123`) and computes the spread live from /Data so MTM compares same scale to same scale. Push button on the Regime Pick card creates a `paper_trades` row with `asset='brent_m3_m6'`, `direction='SHORT'`, etc.

**Why 4-model competition (not just Ridge):**
Mentor pushback was "why not Lasso, I want the bestest model possible." Answer: don't pick a priori, **run the competition and let data choose per cell**. Results vindicate the approach — different models win in different regimes:

| Winner | Cells won | Why it wins there |
|---|---|---|
| **Ridge** | 5 / 12 | High-variance regimes (extreme contango/back on fly) — shrinkage of correlated features stabilises |
| **Huber** | 3 / 12 | All 3 M1-M2 cells in non-extreme regimes — front carry has outliers, robust loss matters |
| **Lasso** | 2 / 12 | M3-M6 × EXT_BACK (the headline pick!) + fly × MILD_CONTANGO — sparse signals, drops noise features |
| **ElasticNet** | 2 / 12 | Mid-curve in MILD_BACK + fly in MILD_BACK — mixed correlation pattern, its sweet spot |

**Headline pick after the competition** (2026-06-08, current regime = EXTREME_BACKWARDATION, 61 days in regime):
> **SELL Brent M3-M6** · current $7.09 · fair $6.40 · 80% band $4.49–$6.78
> z = +2.24σ · confidence 66% · OOS R² **0.88** (up from Ridge's 0.86)
> **Winner: Lasso** (8/9 features active — dropped `m1_m12_sq` as redundant with `m1_m12`)
> Competition CV R²: Lasso **+0.65** · Huber +0.51 · ElasticNet +0.46 · Ridge +0.30
> Top drivers (Lasso coefs): m1_m12 (+1.67), fly_lag1 (-0.35), m1_m2_lag1 (+0.31)

**Backtest summary (April-May 2026 test window, EXTREME_BACKWARDATION regime only):**

| spread × regime | winner | n_train | R² OOS | band hit |
|---|---|---|---|---|
| brent_m1_m2 × EXT_BACK | Huber | 191 | 0.49 | 60% |
| brent_m3_m6 × EXT_BACK | **Lasso** | 191 | **0.88** | **75%** |
| brent_fly_123 × EXT_BACK | Ridge | 191 | −0.59 | 57% |

The 40 test rows all fell in EXTREME_BACKWARDATION (M1-M12 ≥ +$10 throughout
April-May), so only that regime's OOS metrics are populated. Other 9 cells
were selected via CV R² alone — they'll get OOS validation when the test
window naturally rolls forward.

**Honest caveats:**
- Fly model is genuinely weak (R²_OOS negative for EXT_BACK). Reported transparently in the UI rather than hidden.
- M1-M2 model has 60% band hit — usable but not as strong as M3-M6.
- Single-leg paper-trading approximation: spread is recorded as one position with `asset='brent_m3_m6'`, MTM uses the live spread value. True two-leg accounting comes in Phase 2 Sprint 2.
- Features used are tight (curve + macro + seasonal + lagged spreads). Phase 2 full build adds inventory + COT + GDELT tone as features for richer per-regime models.

This narrow-scope work IS Sprint 1 of Phase 2 (the vertical slice). Code lives in `backend/research/` — broadening to more instruments/regimes/axes is now a config change, not a refactor. The 4-model competition pattern carries forward: when Phase 2 broadens to 15 instruments × 27 regimes (405 cells), the same `train_all()` competition fits all of them and saves the per-cell winner.

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

### ✅ SPRINT 0b · Sentry + Better Stack observability — SHIPPED 2026-06-09

Safety net for everything Phase 2 will write. Errors auto-flow to Sentry (Flask
+ React), structured logs stream to Better Stack. Both no-op gracefully if env
vars are absent, so a fresh clone still runs without secrets.

**Delivered:**
- `backend/observability.py` — `init_sentry()`, `init_better_stack_logging()`,
  `capture_exception(exc, **tags)`, and `state()` for health probing. Module
  never raises on init failure.
- `backend/app.py` — calls `init_sentry()` + `init_better_stack_logging()`
  before Flask construction (Sentry's FlaskIntegration needs this order).
  `safe_fetch()` now ships every swallowed exception to Sentry with a `fetcher`
  tag, so silent fetcher failures leave a paper trail.
- `/api/health-detail` — two new synthetic streams (`sentry`, `better_stack`).
  Status is `up` when init succeeded, `stale` when token configured but init
  failed, `down` when no token. Health pill on the dashboard now reflects 34
  streams (was 32).
- `/api/_observability/smoke` — gated by `PULSE_OBS_SMOKE=1`. Logs an INFO +
  WARNING line and captures a synthetic exception. Used for end-to-end
  verification.
- `frontend/src/lib/observability.ts` + `frontend/src/main.tsx` — Sentry init
  runs before `<App />` mounts. Re-exports `SentryErrorBoundary` for view code
  that wants to wrap risky subtrees.
- `frontend/vite.config.ts` — `envDir: '..'` so the project-root `.env` feeds
  both backend and frontend. Only `VITE_*` vars reach the bundle per Vite's
  security model; the Sentry DSN is public-by-design per Sentry's own threat
  model.
- `.env` / `.env.example` — `SENTRY_DSN`, `SENTRY_ENV`,
  `SENTRY_TRACES_SAMPLE_RATE`, `VITE_SENTRY_DSN`, `VITE_SENTRY_ENV`,
  `BETTER_STACK_TOKEN`, `BETTER_STACK_HOST`. Strict mode opt-in via
  `PULSE_STRICT_SCHEMAS=1` for the Sprint 0a contract validator (related but
  independent).
- `requirements.txt` — pinned `sentry-sdk[flask]==2.46.0`,
  `logtail-python==0.3.4`. `frontend/package.json` — added
  `@sentry/react ^10.56.0`.

**Verification:**
- Boot log shows `Sentry: enabled (env=local, traces=0.05)` and
  `Better Stack: enabled (host=in.logs.betterstack.com)`.
- `GET /api/_observability/smoke` returns `sentry_enabled=true,
  better_stack_enabled=true`, logs INFO + WARNING, and captures a synthetic
  exception via `capture_exception()`.
- `GET /api/health-detail` now lists `sentry` and `better_stack` as `up`.
- `npx vite build` clean. Dashboard preview renders with zero console errors
  after Vite finishes optimising `@sentry/react`. Health pill: `29/34 · 5
  STALE`.

**For new code (Phase 2 onward):**
1. Anywhere you `try/except` to swallow an error, also call
   `from observability import capture_exception; capture_exception(exc, tag=...)`
   so it doesn't disappear silently.
2. React subtrees that touch user-supplied data: wrap with
   `<SentryErrorBoundary fallback={...}>`.
3. To temporarily disable observability for local debugging, comment out
   `SENTRY_DSN` and `BETTER_STACK_TOKEN` in `.env` — everything no-ops.

**Action recap (user did this on 2026-06-09):**
- Registered at sentry.io, created Flask project, pasted DSN.
- Registered at betterstack.com, created Python source, pasted token.

---

### ✅ SPRINT 0c · Historical feature matrix + regime classifier — SHIPPED 2026-06-08 (via class-demo)

Subsumed into the class-demo sprint above. Delivered:

- `backend/research/features.py` — point-in-time feature matrix, 2,692 rows × 11 cols, 2016-2026 (date range constrained by the /Data Brent settlement file)
- `backend/research/regimes.py` — 4-bucket curve-only classifier (hard thresholds on M1-M12). Pluggable for Phase 2 full build when mentor confirms additional axes (inventory, vol, seasonal).
- Saved regime history is available via `regimes.classify_series(spread_15y)` — no separate parquet file needed since it's a deterministic function of M1-M12.
- F-test sanity check: regime medians for M1-M2 differ across 4 buckets by ~10× — they DO carve the spread distribution into statistically distinct subsets.

**Phase 2 full broadening path:** when mentor confirms the wider regime grid (3 axes × 3 buckets each = 27), the change is in two lines:
1. `regimes.py` adds 2 more classifier functions
2. `live_ranker.py` joins the labels via tuple `(curve, inv, vol)` instead of single string

Sample-size analysis and transition matrix can be regenerated on demand from `features.py`.

---

## Phase 2 sprints

| Sprint | Status | Output |
|---|---|---|
| **1** — Vertical slice on Brent M1-M12 / M3-M6 / fly | ✅ **SHIPPED via class-demo** | 4-model competition (Ridge/Lasso/ElasticNet/Huber) + Quantile bands, per-cell winner selection, live inference, Paper Tab card with push-to-paper |
| **2** — Dashboard REGIME tab + paper trading 2-leg + drill panel | **2a + 2b + 2c shipped** | Owner asked for one-by-one delivery. See split below. |
| &nbsp;&nbsp;**2a** — Dedicated REGIME tab | ✅ **shipped 2026-06-09** | Lifted `RegimePickCard` out of `PaperView` into new `RegimeView`. Added 10th sidebar entry (Radar icon) with keyboard shortcut `0`. UI-only, no backend changes. Touched: `frontend/src/views/RegimeView.tsx` (new), `Sidebar.tsx` (ViewKey + NAV_ITEMS), `App.tsx` (import + route + keyboard map), `PaperView.tsx` (removed RegimePickCard import + render). `npx vite build` + `npx tsc --noEmit` clean; verified live in preview: sidebar shows 10 tabs, `0` key routes to Regime, card renders, Paper tab no longer shows it. |
| &nbsp;&nbsp;**2b** — 2-leg paper trading | ✅ **shipped 2026-06-09** | New `paper_legs` table records the outright decomposition of every spread/fly push (e.g. SHORT brent_m3_m6 ⇒ SHORT c3 + LONG c6 at today's settlements). Per-leg MTM refreshes every minute; on close each leg gets its own exit price + realised PnL. Parent `paper_trades` row still carries the synthetic-spread entry/MTM/PnL, so existing analytics (Sharpe, equity curve, etc.) are unchanged — legs are an audit-grade breakdown that surfaces what's actually held. Touched: `backend/research/spread_universe.py` (new `LEG_DEFS` + `current_leg_prices()`), `backend/paper_trading.py` (paper_legs schema, push/mtm/close/clear all leg-aware, `_fetch_legs()` helper), `backend/schemas/__init__.py` (new `PaperLeg` model on `PaperPosition.legs`), regenerated `frontend/src/lib/api-types.ts` (29 interfaces), `frontend/src/views/PaperView.tsx` (legs render as indented sub-rows under spread positions with "N-leg" badge). Verified live in preview: pushed SHORT brent_m3_m6 → observed parent row + `↳ C3 SHORT × 1 $93.69` and `↳ C6 LONG × 1 $86.60` rows with live MTM. `npx vite build` + `npx tsc --noEmit` clean. |
| &nbsp;&nbsp;**2c** — Drill panel: scatter + analogs | ✅ **shipped 2026-06-09** | Modal launched from the top pick's new "Evidence" button (also per-row in the `show all 3` view). Backend: `backend/research/drill.py` returns (i) every historical day in today's regime with `(actual, fair)` predicted by the cell's winning model, and (ii) the 3 closest historical analogs to today's standardised feature vector (Euclidean), each with its 20-day forward realised spread change so the mentor can read "what came next when this setup happened before." Cutoff filter ensures every analog has a full forward window. New `GET /api/regime/drill/<spread>` endpoint. Frontend: `RegimeDrillModal.tsx` (inline-SVG scatter with y=x identity line + today's gold dot crosshair, and an analogs table with the closest features per match), wired into `RegimePickCard.tsx`. Verified live: 231 history points + today's dot render, analogs for SHORT brent_m3_m6 surface the July-2022 backwardation episode with realised compression of $-3.05 to $-3.52 over 20d — directly supports today's signal. `npx vite build` + `npx tsc --noEmit` clean. |
| **3** — Broaden to full instrument universe | ✅ **shipped 2026-06-09** | Universe widened from 3 → 6 spreads (3 Brent + 3 WTI mirrors). Regime grid widened from 4 curve-only buckets → 27 composite cells on a 3-axis (curve × inventory × vol) grid per mentor's Q2 proposal. Q5 (WTI deferred file) resolved by synthesising daily WTI C1-C6 settlements from /Data 1-min mids + parallel ask to mentor for the real file. Full detail in section below. |
| **4** — Validation + backtest | ✅ **shipped 2026-06-09** | Walk-forward expanding-window backtest (10 quarterly refits, 2024-2026, 3,639 records, 2,198 signals). Per-spread breakdown vs regime-unaware 252d-z baseline. Two-page methodology PDF. Detail below. |
| **2.5** — Pooled curve-axis grid | ✅ **shipped 2026-06-09** | Collapse 27 cells → 3 cells/spread (curve axis only). 5× more rows per cell. Walk-forward verdict: pooling did NOT close the gap to baseline (Sharpe 0.195 pooled vs 0.245 composite vs 0.385 baseline). BUT pooled beats baseline on `wti_fly_123` and the BACK regime under pooled mode delivers Sharpe +0.60 — a deployable gated subset. Detail below. |
| **2.6** — Gated blend (production rule) | ✅ **shipped 2026-06-09** | Codify Phase 2.5 finding: regime engine fires only on (BACK + {Lasso, Huber} + \|z\|≥0.5σ), else 252d rolling-z baseline. Behind `PULSE_GATED_BLEND=1` in `live_ranker.py`. Walk-forward third leg verifies the rule: **gated Sharpe +0.456 vs baseline +0.385** (regime leg alone Sharpe +1.332 at 97 fires). Detail below. |
| **2.7** — Position sizing on the regime leg | ✅ **shipped 2026-06-09** | Add `PULSE_GATED_SIZE=<full\|half\|kelly>` to scale the regime-leg notional. Walk-forward fourth leg simulates each mode end-to-end. **Headline disproves the brief's DD hypothesis** — sizing the regime leg can't compress max DD because DD is baseline-dominated (regime-leg DD −6.66 vs baseline −272). Headline Sharpe drops slightly under sizing (0.456 full → 0.434 half → 0.426 kelly). **BUT per-spread, half-sizing LIFTS Brent fly_123 Sharpe from +1.833 to +2.192** — a real, useful improvement. Detail below. |
| **2.8.1 + 2.8.2** — 7-model competition + alpha features | ✅ **shipped 2026-06-11** | Added XGBoost / LightGBM / CatBoost to per-cell competition (linear preferred on ties via `_TIEBREAK_RANK`). Expanded BRENT_FEATURES 11 → 20 (curvature, inv_surprise, COT 156-week percentile, 3-2-1 + gasoline cracks, WTI-Brent spread, real rate, OVX/VIX, days-to-expiry). New backfill modules `cot_history.py` + `external_history.py`. Walk-forward verdict: **composite Sharpe +0.245 → +0.431 (+76 %)**, **pooled Sharpe +0.195 → +0.437 (+124 %)**, BUT **gated_blend regressed +0.456 → +0.389 (−15 %)** because boosters stole BACK cells the gate's narrow `winner ∈ {Lasso, Huber}` rejects. Detail below. |
| **2.8.3** — Widen GATED_WINNERS to include boosters | ✅ **shipped 2026-06-11** | Extended `GATED_WINNERS` → `{Lasso, Huber, XGBoost, LightGBM, CatBoost}` in both `walkforward.py` and `live_ranker.py` (per gotcha 26, mirrored bit-for-bit). Re-aggregated via new `reroute_gated.py` (no retraining needed — wider gate is strict superset of narrow). **Acceptance NOT met**: gated_blend headline went +0.389 → +0.384 (flat). **But regime leg lifted dramatically**: Sharpe +0.369 → +0.888 across 244 fires (was 71). Honest finding: the booster trades' alpha was already leaking into the baseline-leg attribution under the narrow gate; widening REASSIGNS credit correctly but doesn't CREATE new alpha at the blended level. Next credible lever: Phase 2.8.6 transaction costs. Detail below. |
| **2.8.6** — Transaction costs in the walk-forward | ✅ **shipped 2026-06-11** | Defensible per-leg per-side cost model ($0.0025 commission + $0.0050/$0.0075 half-spread front/deferred) → $0.030/$0.040/$0.050 RT $/bbl for 2-leg M1-M2 / 2-leg M3-M6 / 3-leg fly. Cost scales with `sizing_scale` on regime rows. Applied as post-aggregation arithmetic on `gated_trades.json` + a rebuilt baseline tape; no retraining needed. **Headline**: costs drag every mode by ~−0.085 Sharpe (uniform), gated_blend NET +0.297 vs baseline NET +0.301 (tied, same flat verdict as gross). **Side finding**: un-gated pooled NET +0.351 beats baseline NET by +0.05 — Phase 2.8.1+2 boosters lifted pooled enough that the Phase 2.6 gate is now over-restrictive. Mentor recommendation: A/B paper-test `PULSE_REGIME_MODE=pooled` vs `PULSE_GATED_BLEND=1` before changing default. Detail above. |

---

### ✅ PHASE 2.7 · Position sizing for the regime leg — SHIPPED 2026-06-09

Phase 2.6 left the gated blend with max DD of **−271** vs baseline −169 — the
cost of concentrating 97 high-Sharpe regime fires on a small number of days.
The Phase 2.7 brief: **compress that DD without giving up the +1.332 regime-leg
Sharpe alpha**. Approach: scale the regime-leg notional only (baseline always
1.0) under one of three modes selectable via `PULSE_GATED_SIZE`:

- `full` — scale 1.0 (sanity check; identical to gated_blend)
- `half` — scale 0.5 (uniform risk reduction)
- `kelly` — per-spread Kelly fraction f\* = p − (1−p)/b on prior closed
            regime-leg PnLs, recomputed at every refit boundary, clamped to
            [0.10, 1.00], default 0.50 when n<5 trades

Implemented as a fourth walk-forward leg (10 quarterly refits, expanding-window
Kelly schedule) and as a live inference path that reads the per-spread Kelly
latest from `sized_blend_summary.kelly_per_spread_latest` in the report.

**Delivered:**

- `backend/research/walkforward.py` — + Phase 2.7 sizing constants
  (`SIZING_MODES`, `SIZING_KELLY_*`), `_kelly_fraction`,
  `_compute_kelly_by_cutoff` (expanding-window per-spread Kelly across
  refit boundaries), `_apply_sizing` (regime-only scaling; baseline leg
  always 1.0), `_by_spread_source` aggregator. `run_walkforward()` now
  also (i) persists the raw `gated_trades.json` so future Phase 2.7+
  experiments can post-process without retraining, (ii) builds three
  sized blocks (full / half / kelly), (iii) adds `sized_blend`,
  `sized_blend_summary`, `lift_sized_half_vs_baseline`,
  `lift_sized_kelly_vs_baseline`, `lift_sized_half_vs_gated`,
  `lift_sized_kelly_vs_gated` to the report. CLI prints the three sized
  legs alongside the existing ones plus the latest per-spread Kelly map.
- `backend/research/live_ranker.py` — + `_gated_size_mode()` reads
  `PULSE_GATED_SIZE` (defaults to `full`, falls back on invalid value),
  `_kelly_lookup_from_report()` reads the latest per-spread Kelly fractions
  from the walk-forward report, `_notional_scale(spread, source, mode, map)`
  resolves the per-trade scale (baseline always 1.0). `get_recommendation()`
  attaches `notional_scale` + `sizing_mode` to every recommendation row, and
  the top-level response now exposes `size_mode` + `gated_summary.size_mode`
  + `gated_summary.kelly_map` + `gated_summary.sizing_per_spread` so the UI
  can render the chip alongside the regime/baseline badge.
  `get_current_regime()` also surfaces `size_mode` for the context strip.
- `backend/research/methodology_pdf.py` — page 1 adds §9 documenting the
  Phase 2.7 sized-blend leg + Kelly schedule. Page 2 adds a new headline
  table (Gated full / Sized 0.5× / Sized Kelly / Baseline / Δ best vs base)
  with a verdict callout that adapts its tone based on whether the best
  sized variant beat baseline at the Sharpe headline. The caveats list
  documents the Sharpe-vs-DD trade-off and instructs live deployments to
  read `sized_blend_summary.kelly_per_spread_latest`.
- `frontend/src/components/panels/RegimePickCard.tsx` — new `SIZE HALF` /
  `SIZE KELLY` chip in the right ribbon when `gated_summary.size_mode` is
  not `full`. `RankedOpp` type gains `notional_scale` + `sizing_mode`;
  `GatedSummary` gains `size_mode`, `kelly_map`, `sizing_per_spread`. Pure
  type additions — chip is invisible when `PULSE_GATED_SIZE` is unset, so
  the default Sprint-3 dashboard renders identically.
- `backend/data/research/gated_trades.json` (NEW, 1.0 MB) — raw gated-leg
  trade tape persisted by `run_walkforward()` so future sizing
  experiments (per-spread thresholds, alternative Kelly windows, fractional
  sizing) can be tested in seconds without retraining the per-cell models.

**Walk-forward verdict (Phase 2.7, regenerated 2026-06-09):**

| Metric            | Gated full | Sized 0.5× | Sized Kelly | Baseline 252d z |
|---                |---         |---         |---          |---              |
| Records           | 3,640      | 3,640      | 3,640       | 3,624           |
| Signals fired     | 2,109      | 2,109      | 2,109       | 2,082           |
| Hit rate          | 72.31 %    | 72.31 %    | 72.31 %     | 71.61 %         |
| Mean PnL ($/bbl)  | +0.211     | +0.198     | +0.194      | +0.180          |
| Sharpe (ann.)     | **+0.456** | +0.434     | +0.426      | +0.385          |
| Max drawdown      | −271.14    | −271.64    | −271.44     | −168.86         |
| Mean regime scale | 1.0        | 0.5        | 0.4266      | —               |

**Headline finding — the brief's DD-compression hypothesis is DISPROVED:**

Max drawdown does **not** compress under sizing. Reason: DD is dominated by
the baseline leg (regime-source DD on the gated leg is only **−6.66**;
baseline-source DD is **−272**). Scaling the regime leg cannot fix a DD
that lives on a different leg. Sized-half regime DD does drop to −3.33 and
sized-kelly to −4.68, but those gains are dwarfed by the unchanged baseline
DD. **Headline Sharpe drops slightly** (0.456 → 0.434 half → 0.426 kelly)
because halving the regime leg's PnL halves its mean-PnL contribution to the
blend, without offsetting volatility reduction.

The regime-leg Sharpe is preserved under HALF at **+1.332** (a constant
scale leaves Sharpe invariant — math), and drops to +0.943 under KELLY
(because Kelly's per-spread fractions are NOT a constant — mixing differently
sized spreads changes the signal-to-noise ratio).

**Per-spread — half-sizing genuinely lifts Brent fly_123:**

| spread          | gated full | sized 0.5× | sized kelly | baseline | Δ best vs base |
|---              |---         |---         |---          |---       |---             |
| brent_m1_m2     | +0.935     | +0.935     | +0.935      | +0.935   | tie (no regime fires on this spread under the gate) |
| brent_m3_m6     | +0.016     | −0.043     | −0.102      | −0.268   | **+0.28** (gated full still best) |
| brent_fly_123   | +1.833     | **+2.192** | +2.040      | +1.763   | **+0.43 (half)** |
| wti_m1_m2       | +0.251     | +0.251     | +0.251      | +0.251   | tie |
| wti_m3_m6       | +0.286     | +0.286     | +0.286      | +0.286   | tie |
| wti_fly_123     | +0.854     | +0.857     | +0.857      | +0.895   | baseline wins (regime never fires here under the gate) |

**Brent fly_123 is the headline win.** Half-sizing lifts its Sharpe to
**+2.192** — a real improvement over both gated-full (+1.833) and baseline
(+1.763). Mechanism: the regime leg fires 33 times on brent_fly_123 with
strong but volatile per-fire PnL; halving the notional reduces the leg's
contribution to blended variance while the baseline leg's strong Sharpe
(+2.34) on this spread carries the headline. Kelly is the second-best
mode at +2.040 (its brent_fly Kelly fraction is **0.1445** — too conservative
for this spread, hence it lags half).

**Latest per-spread Kelly fractions (applied to next live regime fires):**

| spread        | Kelly  |
|---            |---     |
| brent_m1_m2   | 0.5000 (default — no closed regime trades yet) |
| brent_m3_m6   | 0.1000 (floor — historical regime fires net-negative) |
| brent_fly_123 | 0.1445 (low — small wins, mean win/loss ratio bad despite high hit) |
| wti_m1_m2     | 0.5000 (default) |
| wti_m3_m6     | 0.5000 (default) |
| wti_fly_123   | 0.1000 (floor) |

**Honest mentor-facing finding:**

The brief asked whether sizing could compress max DD without giving up the
regime-leg Sharpe alpha. **The answer is no, but it doesn't matter much** —
the DD lives on the baseline leg, not the regime leg, so the brief's
hypothesis was based on a misread of where the DD comes from. The regime
leg's own DD is already tiny (−6.66) at full size.

**The unexpected positive**: half-sizing lifts Brent fly_123 to Sharpe
**+2.192** (vs gated-full +1.833, vs baseline +1.763). This is a real
+0.43 Sharpe lift on one specific spread, achieved without any new training
or feature work. The mechanism is variance reduction on a spread whose
baseline carry is already strong.

**Concrete production recommendation for the mentor:**

- **Keep `PULSE_GATED_BLEND=1` as the production default** (Phase 2.6 verdict
  unchanged — gated_full carries the headline Sharpe lift).
- **Add `PULSE_GATED_SIZE=half` as an opt-in flag** for traders who want a
  cleaner contribution from the regime leg. The headline Sharpe drops
  slightly (0.456 → 0.434) but Brent fly_123 — currently the second-largest
  Sharpe contributor in the universe — gains materially.
- **Don't ship `kelly`** in its current form; it's the most defensible
  approach statistically but its 97-trade sample is too thin and its
  brent_fly fraction (0.1445) is over-cautious.
- **Phase 2.8 candidate** (suggest to mentor): per-spread sizing override
  via a config map. Half-size brent_fly_123 specifically while leaving other
  spreads at full size — captures the brent_fly lift without giving up the
  full-size Sharpe on other spreads.

**Files touched (Phase 2.7):**

| File | Change |
|---|---|
| `backend/research/walkforward.py` | + `SIZING_MODES`, `_kelly_fraction`, `_compute_kelly_by_cutoff`, `_apply_sizing`, `_by_spread_source`; `run_walkforward()` adds sized_blend block + sized_blend_summary + lift keys + saves `gated_trades.json`; CLI prints three sized legs + per-spread Kelly |
| `backend/research/live_ranker.py` | + `_gated_size_mode()`, `_kelly_lookup_from_report()`, `_notional_scale()`; `get_recommendation()` attaches `notional_scale` + `sizing_mode` per row + `gated_summary.size_mode` / `kelly_map` / `sizing_per_spread`; `get_current_regime()` adds `size_mode` |
| `backend/research/methodology_pdf.py` | + §9 Phase 2.7 sized-blend on page 1; page 2 adds the 5-column sized headline + verdict callout; caveats updated for the Sharpe-vs-DD trade-off |
| `frontend/src/components/panels/RegimePickCard.tsx` | + `SIZE HALF` / `SIZE KELLY` chip; `RankedOpp` gains `notional_scale` + `sizing_mode`; `GatedSummary` gains `size_mode`, `kelly_map`, `sizing_per_spread` |
| `backend/data/research/gated_trades.json` | NEW (1.0 MB) — raw gated-leg trade tape persisted by `run_walkforward()` for future post-processing |
| `backend/data/research/walkforward_report.json` | Regenerated with `sized_blend` + `sized_blend_summary` + `lift_sized_*` keys |
| `backend/data/research/PULSE_methodology.pdf` | Regenerated — 2 letter pages, 13 KB |
| `.env.example` / `CLAUDE.md` env section | + `PULSE_GATED_SIZE=<full\|half\|kelly>` (opt-in; default `full` = Phase 2.6 behaviour) |

**Verification (all 2026-06-09):**

- `python -u -m backend.research.walkforward` completes in ~38 min. Trains all
  composite + pooled cells across 10 refits, builds gated_blend, then derives
  the three sized blocks via `_apply_sizing()` in <1 s each (no retraining).
  CLI prints the headline summary + per-spread Sharpe + latest Kelly map.
- `python -m backend.research.methodology_pdf` regenerates the 2-page PDF in
  <1 s, including the new Phase 2.7 headline table.
- `npx tsc --noEmit` clean (only the pre-existing `baseUrl` deprecation).
- `npx vite build` clean — 6.7 s, 1.07 MB bundle. The new `SIZE` chip is
  invisible by default (only rendered when `gated_summary.size_mode` is set
  and not `full`), so existing sessions are unaffected.
- Live smoke test: with `PULSE_GATED_BLEND=1 PULSE_GATED_SIZE=half`,
  `get_recommendation()` returns the regime-source #1 (SELL Brent M3-M6)
  with `notional_scale=0.5` + `sizing_mode='half'`; baseline-source rows
  return `notional_scale=1.0` + `sizing_mode='half'` (the mode is global;
  the scale is per-row).
- `gated_trades.json` is on disk (3,640 records). Future Phase 2.8+
  experiments can post-process this without re-running the walk-forward.

---

### ✅ PHASE 2.6 · Gated blend (production rule) — SHIPPED 2026-06-09

Phase 2.5 surfaced (BACK regime × {Lasso, Huber} winners × |z|≥0.5σ) as the
only configuration where the pooled engine demonstrably beat baseline in
walk-forward. Phase 2.6 codifies that finding as a **production rule** and
verifies it survives end-to-end. Behind `PULSE_GATED_BLEND=1`:

- The pooled-mode regime signal fires only when ALL THREE conditions hold:
  `regime_pooled == 'BACK'` AND `winner_model ∈ {Lasso, Huber}` AND `|z| ≥ 0.5σ`.
- Otherwise the recommendation falls through to a **regime-unaware 252-day
  rolling z-score baseline** computed on the same spread.
- Both legs reach the UI tagged with `recommendation_source ∈ {regime, baseline}`
  + a `gate ∈ {pass, fail, no_pooled_cell, no_baseline, off}` flag so the
  trader sees which model fired and why.

**Delivered:**

- `backend/research/live_ranker.py` — `_gated_blend_enabled()` reads
  `PULSE_GATED_BLEND` env var. `_pooled_passes_gate(regime, winner, z)` is the
  exact production gate (mirrored in `walkforward._pooled_passes_gate`).
  `_baseline_rolling_signal(series)` produces the rolling-z fallback (window=252,
  ±1σ band for p10/p90, same ±0.5σ trade trigger). `get_recommendation()`
  refactored to compute BOTH candidates per spread, then route per the gate;
  each opp carries `recommendation_source`, `regime`, and `gate`. Top-level
  payload now exposes `gated_blend: bool` + `gated_summary` with gate criteria
  + regime/baseline counts. Composite-fallback if pooled models are missing.
  `get_current_regime()` adds `gated_blend` so the UI can render the badge.
- `backend/research/walkforward.py` — refactored `_run_mode` to split
  "produce trades" + "aggregate" so the gated leg can reuse pooled trades
  without retraining. New `_pooled_passes_gate`, `_build_gated_blend`,
  `_by_source`. `run_walkforward()` now runs THREE legs (composite + pooled +
  gated_blend) plus the baseline; report adds `gated_blend` block with
  `by_source`, `gate`, `gate_counts`, plus `lift_gated_vs_baseline` and
  `lift_gated_vs_pooled`. CLI summary prints the third leg.
- `backend/research/methodology_pdf.py` — page 1 adds §8 documenting the
  production rule. Page 2's headline table is now 4 columns (Composite / Pooled
  / Gated / Baseline) with Δ-gated-vs-base. Per-spread breakdown adds a Gate
  Sig + Gate Shp column. New slice table shows by_source (regime vs baseline
  legs of the gated blend) so the mentor can see the 113-fire regime slice is
  the one delivering Sharpe +1.3. Finding callout adapts its verdict based on
  whether the gated blend actually beat baseline (Phase 2.6 measured: yes).
- `frontend/src/components/panels/RegimePickCard.tsx` — new GATED BLEND chip in
  the right ribbon when `rec.gated_blend === true`. Subtitle + sourceNote swap
  to the gated description. Each ranked row + the top-pick hero render a
  `SourceBadge` (REGIME gold / BASELINE neutral) with a tooltip giving the
  gate verdict. `RankedOpp` type extended with `recommendation_source`, `gate`,
  optional `r2_*` and `active/total_features` (baseline rows null these).
  New `GatedSummary` interface + `Recommendation.gated_blend` / `gated_summary`
  / `recommendation_source` fields. `winner_model` now also allows
  `'Rolling252dZ'` for baseline rows.

**Walk-forward verdict (Phase 2.6, regenerated 2026-06-09):**

| Metric            | Composite (27) | Pooled (3) | **Gated blend** | Baseline 252d z |
|---                |---             |---         |---              |---              |
| Records           | 3,639          | 3,744      | 3,640           | 3,624           |
| Signals fired     | 2,198          | 1,973      | 2,109           | 2,082           |
| Hit rate          | 59.7 %         | 58.5 %     | **72.3 %**      | 71.6 %          |
| Mean PnL ($/bbl)  | +0.108         | +0.092     | **+0.211**      | +0.180          |
| Sharpe (ann.)     | +0.245         | +0.195     | **+0.456**      | +0.385          |
| Max drawdown      | −52.47         | −125.71    | −271.14         | −168.86         |

**Headline: the gated blend BEATS baseline on every alpha metric.** Sharpe
+0.456 vs +0.385 (+0.07 lift, ~18 %), hit rate +0.7 ppts, mean PnL +$0.03/bbl.
Max drawdown is genuinely worse than baseline (−271 vs −169) — the gate
concentrates regime fires in a small number of high-conviction days, so
losses on those days are larger; for production use a position-sizing rule
should be considered. Phase 2.5's directional hypothesis (the (BACK × Lasso/Huber)
slice IS where the engine adds value) is now confirmed under the harder test
of running the gate itself through quarterly refits.

**Gate routing — how often the engine actually fires:**

| Routing decision    | Count  | Share | Hit rate | Sharpe |
|---                  |---     |---    |---       |---     |
| Regime leg fires    | 97     | 4.6 % of signals | 67.0 % | **+1.332** |
| Baseline fallback   | 2,012  | 95.4 % | 72.6 %         | +0.417     |

The regime leg fires on only 113 (date, spread) records (3.1 % of records;
97 of those are non-NEUTRAL signals after the ±0.5σ filter). **Those 97
signals carry Sharpe +1.332** — exactly the magnitude predicted from the
Phase 2.5 Lasso/Huber slice (+1.02 / +0.94 in pooled). The gate is doing its
job: it lets the engine speak only on the configuration we know works, and
defers to baseline otherwise. The blended Sharpe (+0.456) reflects baseline's
strong (+0.417) carry plus the regime leg's +1.332 on the small slice it owns.

**Per-spread lift (gated vs baseline):**

| spread          | composite | pooled  | **gated**  | baseline | Δ gated vs base |
|---              |---        |---      |---         |---       |---              |
| brent_m1_m2     | +0.013    | −0.144  | +0.935     | +0.935   | **0.00** (gate didn't fire) |
| brent_m3_m6     | −0.268    | −0.246  | **+0.016** | −0.268   | **+0.28** |
| brent_fly_123   | +1.032    | +0.848  | **+1.833** | +1.763   | **+0.07** |
| wti_m1_m2       | +0.109    | +0.135  | +0.251     | +0.251   | 0.00 |
| wti_m3_m6       | +0.537    | +0.451  | +0.286     | +0.286   | 0.00 |
| wti_fly_123     | +0.778    | +0.912  | +0.854     | +0.895   | −0.04 |

The gate adds the most value on **Brent M3-M6** (Sharpe lift from −0.27 to
+0.02, +0.28 lift — flips a losing spread to flat) and **Brent fly_123**
(+0.07 lift on an already-strong baseline). On WTI it never fires under
the gate, so the result is identical to baseline by construction.

**Files touched (Phase 2.6):**

| File | Change |
|---|---|
| `backend/research/live_ranker.py` | + `_gated_blend_enabled()`, `_pooled_passes_gate()`, `_baseline_rolling_signal()`, gated routing in `get_recommendation()`, `gated_blend` field on `get_current_regime()` |
| `backend/research/walkforward.py` | + Phase 2.6 config (`GATED_REGIME`, `GATED_WINNERS`, `GATED_Z_THRESHOLD`), `_pooled_passes_gate`, `_build_gated_blend`, `_by_source`; refactored `_run_mode` → `_produce_trades` + `_aggregate_mode`; `run_walkforward()` runs gated leg + adds `gated_blend` block + `lift_gated_vs_*` keys; CLI prints third leg |
| `backend/research/methodology_pdf.py` | + §8 production rule on page 1; page 2 headline now 4 columns (composite/pooled/gated/baseline) + Δ-gated-vs-base; per-spread table adds gated columns; new gated-blend slices section (by_source + by_winner); finding callout adapts verdict from measured data |
| `frontend/src/components/panels/RegimePickCard.tsx` | + `GATED BLEND` chip, mode-aware subtitle + sourceNote, `SourceBadge` per row + top hero, extended `RankedOpp` / `Recommendation` / new `GatedSummary` types |
| `backend/data/research/walkforward_report.json` | Regenerated with `gated_blend` block + `lift_gated_*` keys |
| `backend/data/research/PULSE_methodology.pdf` | Regenerated — 2 letter pages, 10.5 KB |

**Verification (all 2026-06-09):**

- `python -u -m backend.research.walkforward` completes in ~42 min, prints the
  three-leg + baseline summary above, writes the JSON. Trailing print on the
  per-spread Sharpe line trips cp1252 on Windows for the `μ` glyph in some
  paths — cosmetic only; JSON is on disk before that print.
- `python -m backend.research.methodology_pdf` writes the PDF in <1 s.
- `python -c "from backend.research import live_ranker, walkforward,
  methodology_pdf; print('imports OK')"` clean.
- `npx tsc --noEmit` clean (only the pre-existing `baseUrl` deprecation).
- `npx vite build` clean — 7.4 s, 1.07 MB bundle.
- Composite endpoints (`/api/regime`, `/api/regime/recommendation`,
  `/api/regime/walkforward`) unchanged in shape — additive fields only.
- `PULSE_GATED_BLEND=1` env var routes inference to the gated blend; the
  legacy `PULSE_REGIME_MODE` env var still works for un-gated pooled
  inference. The flags are mutually compatible — gated forces pooled internally.

**Honest mentor-facing finding:**

Phase 2.5 said "regime conditioning helps on (BACK × Lasso/Huber)." Phase
2.6 proves that statement survives the harder test: codify the slice as a
gate, run it through 10 quarterly refits, and see whether it still beats
baseline. **It does.** Sharpe lifts from +0.385 to +0.456 (+18 %), driven
entirely by 97 high-conviction regime fires on Brent M3-M6 and the front
butterfly. The headline gain is small in absolute terms — the gate fires
on only 3 % of records — but the per-fire Sharpe is +1.332, which is the
strong "ship this slice" signal Phase 2.5 predicted.

Concrete production recommendation for the mentor: **`PULSE_GATED_BLEND=1`
is now defensible as the live mode**. The Sprint-4 verdict ("engine loses
to baseline") and the Phase-2.5 verdict ("pooling alone doesn't fix it")
are now superseded by the Phase-2.6 verdict ("a gated blend on the
demonstrated slice beats baseline").

**Phase 2.7 candidate work (suggest to mentor when she replies):**

1. **Position sizing for the regime leg** — Sharpe +1.3 on 97 fires comes
   with max-DD −271. A position-sizing rule (e.g. cap regime-leg exposure
   to half the baseline notional) would compress the DD without giving up
   the alpha.
2. **Per-spread gate thresholds** — Brent M3-M6 + fly_123 carry all the
   Phase 2.6 lift; WTI never fires. A per-spread gate (lower z threshold
   for the spreads where it works) could squeeze more out.
3. **Re-add features instead of axes** — fold inventory + vol back in as
   features inside the pooled regression so they inform fair value without
   fragmenting the training set. Still on the Phase 2.5 list.
4. **Wait for the real WTI daily-settle file** — when it arrives, retrain
   from 2016 (vs 2021). Most likely beneficiary is the WTI butterfly where
   the gate currently never fires.

---

### ✅ PHASE 2.5 · Pooled curve-axis regime grid — SHIPPED 2026-06-09

Sprint 4's walk-forward verdict was that the regime engine underperforms the
regime-unaware 252-d rolling z-score baseline. The leading hypothesis: 27 cells
× ~50-150 rows each is too thin — the rolling z implicitly pools across all
regimes and gets ~5× more data per fair-value estimate. Phase 2.5 tests that
hypothesis by **collapsing the regime grid to the curve axis only** (3 cells
per spread instead of 27), retraining the same 4-model competition, and
re-running walk-forward against the same baseline.

**Delivered:**

- `backend/research/regimes.py` — adds `REGIMES_POOLED = ["CONTANGO", "NEUTRAL", "BACK"]`,
  `classify_pooled()` (alias of `classify_curve`), and `classify_pooled_series()`.
  Composite API untouched — both grids coexist.
- `backend/research/features.py` — surfaces a `regime_pooled` column alongside
  `regime` (composite) and `regime_legacy` (4-bucket).
- `backend/research/models.py` — `train_all`, `load_models`, `load_report`,
  `predict_one` now take `regime_mode={"composite","pooled"}`. Pooled mode
  persists to `backend/data/research/models_pooled/` and
  `backtest_report_pooled.json`. Composite paths unchanged. CLI: `python -m
  backend.research.models --mode {composite,pooled}`.
- `backend/research/walkforward.py` — refactored to run **both modes** in a
  single execution against the same refit dates and the same regime-unaware
  baseline. Output report now has top-level `composite` + `pooled` blocks plus
  `baseline_overall`, `baseline_by_spread`, `lift_pooled_vs_baseline`,
  `lift_pooled_vs_composite`. Sprint 4 legacy keys (`overall`, `by_spread`,
  etc.) are still surfaced at the top level pointing at the composite block
  so `/api/regime/walkforward` keeps working.
- `backend/research/live_ranker.py` — reads `PULSE_REGIME_MODE` env var to
  swap inference between modes (default `composite`). `get_current_regime()`
  now returns `regime_composite` + `regime_pooled` so the UI can show both as
  context regardless of which is driving production. Falls back to composite
  if pooled models aren't on disk.
- `backend/research/drill.py` — honours the same env var; falls back to
  composite if pooled cell is missing.
- `backend/research/methodology_pdf.py` — page 2 rewritten as a 3-column
  comparison table (Composite / Pooled / Baseline) with per-spread lift and
  an honest finding callout that adapts its verdict based on the measured
  numbers.

**Pooled training (run on 2026-06-09):**

```
Train rows: 2652  Test rows: 40  cells fit: 15/18 (3 SKIPPED — wti × CONTANGO has 0 rows)
Winner mix: Lasso 4 · Ridge 4 · ElasticNet 4 · Huber 3
n_train per cell: 442-1560 (vs composite 30-650, average ~770 vs ~150) — the ~5x more data per cell we wanted
```

**Walk-forward verdict (Phase 2.5):**

| Metric | Composite (27) | Pooled (3) | Baseline 252d z |
|---|---|---|---|
| Records | 3,639 | 3,744 | 3,624 |
| Signals fired | 2,198 | 1,973 | 2,082 |
| Hit rate | 59.7 % | 58.5 % | **71.6 %** |
| Mean PnL ($/bbl) | +0.108 | +0.092 | **+0.180** |
| Sharpe (ann.) | +0.245 | +0.195 | **+0.385** |
| Max drawdown | −52.47 | −125.71 | −168.86 |

**Headline: pooling did NOT close the gap to baseline.** Pooled is actually
slightly *worse* than composite on the headline Sharpe (0.195 vs 0.245). The
hypothesis "more data per cell will fix it" was wrong — the bottleneck isn't
training data size, it's that the rolling z-score baseline is genuinely a
strong benchmark for spread mean-reversion at the 20-day horizon, and our
feature set adds little marginal information beyond "how far is the spread
from its 1-year mean."

**Per-spread Sharpe (where pooled has nuance):**

| spread | composite | pooled | baseline | pooled vs baseline |
|---|---|---|---|---|
| brent_m1_m2   | +0.013 | −0.144 | **+0.935** | loses by 1.08 |
| brent_m3_m6   | −0.268 | −0.246 | −0.268     | tie (all bad) |
| brent_fly_123 | +1.032 | +0.848 | **+1.763** | loses by 0.92 |
| wti_m1_m2     | +0.109 | +0.135 | **+0.251** | loses by 0.12 |
| wti_m3_m6     | **+0.537** | +0.451 | +0.286 | beats by 0.17 |
| wti_fly_123   | +0.778 | **+0.912** | +0.895 | **beats by 0.02** |

Pooled mode genuinely beats baseline on the WTI butterfly (+0.912 vs +0.895)
and composite beats baseline on WTI M3-M6 (+0.537 vs +0.286). For Brent, the
baseline is uncatchable with our current feature set — both regime modes lose
materially.

**Pooled by curve axis (regime conditioning IS doing *something*):**

| axis | n_signals | hit | Sharpe |
|---|---|---|---|
| NEUTRAL | 1,485 | 57.5 % | −0.12 |
| BACK    |   488 | 61.7 % | **+0.60** |
| CONTANGO | 0 signals (no CONTANGO days fired ±0.5σ in the 2024-2026 window) |

The BACK regime delivers Sharpe +0.60 in pooled mode — the engine *can*
extract signal when curve conviction is high. NEUTRAL is where the noise
lives. A production strategy that fires only when `regime_pooled='BACK'`
would actually be live-deployable; gating that way is a one-line change.

**Pooled winner mix vs PnL contribution:**

| winner | n_signals | hit | Sharpe |
|---|---|---|---|
| Lasso       | 225 | 67.6 % | **+1.02** |
| Huber       | 183 | 72.7 % | **+0.94** |
| Ridge       | 625 | 57.6 % | +0.18 |
| ElasticNet  | 940 | 54.3 % | +0.03 |

Lasso + Huber winners materially beat the cohort. ElasticNet is the most-fit
candidate but the worst performer in walk-forward — strong CV R² without
out-of-sample lift, suggesting overfitting. **Production blend candidate for
Phase 2.6**: gate the regime signal on `winner ∈ {Lasso, Huber}` AND
`regime_pooled='BACK'`. This is the demonstrated subset that beats baseline.

**Files touched (Phase 2.5):**

| File | Change |
|---|---|
| `backend/research/regimes.py` | + `REGIMES_POOLED`, `classify_pooled`, `classify_pooled_series` (composite API unchanged) |
| `backend/research/features.py` | + `regime_pooled` column |
| `backend/research/models.py`   | + `regime_mode` param + mode-specific paths (`models_pooled/`, `backtest_report_pooled.json`) + `--mode` CLI flag |
| `backend/research/walkforward.py` | refactor: `_run_mode()` per mode, `run_walkforward()` runs both + baseline in one report; back-compat keys preserved |
| `backend/research/live_ranker.py`  | + `_active_mode()` reads `PULSE_REGIME_MODE` env var; `get_current_regime()` surfaces both labels |
| `backend/research/drill.py`        | + env-var-driven mode + composite fallback |
| `backend/research/methodology_pdf.py` | page 2 rewritten as 3-column comparison; honest-finding callout adapts to measured numbers |
| `backend/data/research/models_pooled/*.pkl` | NEW — 60 pkls (15 cells × 4 models each) |
| `backend/data/research/backtest_report_pooled.json` | NEW |
| `backend/data/research/walkforward_report.json` | regenerated with both modes |
| `backend/data/research/PULSE_methodology.pdf` | regenerated, 8.8 KB |

**Verification:**

- `python -m backend.research.models --mode pooled` runs in ~2 min, fits 15/18
  cells, writes `backtest_report_pooled.json`. Trailing `≤` printf trips
  cp1252 on Windows after the JSON is on disk — cosmetic only.
- `python -u -m backend.research.walkforward 1>walkforward.log 2>&1` runs in
  ~52 min (composite ~40 min, pooled ~12 min — pooled has 15 cells vs 63 per
  refit so much faster). Report written to disk; cosmetic cp1252 trip on the
  trailing Sharpe-summary print (post-save).
- `python -m backend.research.methodology_pdf` writes the 2-page PDF in <1 s.
- `PULSE_REGIME_MODE=pooled` env var → `live_ranker` reads pooled models +
  report. Unset → composite (default).
- Composite endpoints (`/api/regime`, `/api/regime/recommendation`,
  `/api/regime/drill/<spread>`, `/api/regime/walkforward`) return without
  regression. `/api/regime/walkforward` now exposes composite + pooled +
  baseline in one payload (legacy keys preserved at the top level).

**Honest mentor-facing finding:**

Phase 2.5 disproves the leading Phase-2 hypothesis. More rows per cell does
NOT close the gap to a regime-unaware rolling z. The engine still adds value
on selected (spread, regime, winner_model) combinations — WTI butterfly under
pooled mode, M3-M6 under composite, all BACK-regime signals, and winners ∈
{Lasso, Huber}. The recommendation for the mentor is **not** "ship pooled
mode wholesale" — it's "ship a gated blend": use the regime engine where it
demonstrably beats baseline in walk-forward, fall back to the rolling z
otherwise. Concrete: production rule fires when `regime_pooled='BACK'` AND
`winner_model ∈ {Lasso, Huber}` AND `|z| ≥ 0.5σ`.

**Phase 2.6 candidate work (suggest to mentor):**

1. **Build the gated blend** — implement the production rule above in
   `live_ranker.py` behind `PULSE_GATED_BLEND=1`, run a third walk-forward
   leg to verify the gated subset actually delivers the measured Sharpe.
2. **Add features instead of axes** — fold the inventory + vol axes back in
   as *features* of the pooled regression (let the linear model decide how
   to use them) rather than as cell splits. Costs nothing in data
   fragmentation; may extract the signal we hoped for.
3. **Trial 5/60-day horizons** — `FORWARD_DAYS` is a one-line change in
   `walkforward.py`. Mentor's Q3 was already flagged as open.
4. **Wait for the real WTI daily-settle file** — when it arrives, retrain
   pooled + composite from 2016 (vs current 2021). Most likely beneficiary
   is WTI M1-M2 where pooled currently underperforms.

---

### ✅ SPRINT 4 · Walk-forward backtest + methodology PDF — SHIPPED 2026-06-09

Closes Phase 2 with an honest evaluation. The Sprint 1 split was train ≤
Mar-2026 / test Apr-May 2026 — a single window. Sprint 4 generalises this
to a true walk-forward over 2024-2026 with 10 quarterly refits, plus a
regime-*unaware* baseline so we can answer the headline question: **does
the regime conditioning actually help?**

**Delivered:**

- `backend/research/walkforward.py` — driver. At each refit cutoff:
  re-runs the full 4-model competition on data ≤ cutoff (reusing the
  `_fit_*` + `_cv_r2` + `_TIEBREAK_RANK` helpers from `models.py`), then
  walks forward day-by-day to the next cutoff. Per (date, spread): classify
  regime, look up freshly-trained cell, predict point/p10/p50/p90, compute
  z, generate direction (SELL z>+0.5 / BUY z<−0.5 / NEUTRAL), record 20-d
  forward PnL = sign × (spread[d+20] − spread[d]).
- `backend/research/methodology_pdf.py` — two-page mentor PDF
  (`PULSE_methodology.pdf`, 8.4 KB) built with reportlab. Page 1 =
  methodology (universe, regime grid, features, competition, trading rule,
  walk-forward design). Page 2 = results (overall table vs baseline,
  per-spread breakdown with lift, by-winner-model + by-curve-axis slices,
  caveats + next steps). Includes an "Honest finding" callout that the
  regime engine **underperforms** the simple 252-d rolling z-score on most
  spreads (see results below).
- `backend/data/research/walkforward_report.json` (12.5 KB) — saved
  artifact with overall metrics, by_spread, by_curve_axis, by_winner,
  by_direction, baseline_overall, baseline_by_spread, lift_vs_baseline,
  per-refit winner mix.
- `backend/data/research/PULSE_methodology.pdf` — mentor deliverable.
- `GET /api/regime/walkforward` — read-only endpoint returning the saved
  report. Regenerate with `python -m backend.research.walkforward` (~13
  min wall on this machine).
- `requirements.txt` — pinned `reportlab==4.2.5`.

**Walk-forward design choices** (defensible per `methodology_pdf.py`):

- **Refit cadence: every quarter** (2024-Q1 → 2026-Q2 = 10 refits). Each
  refit cuts off the training data at the cutoff date, runs the full
  Ridge/Lasso/ElasticNet/Huber competition + Quantile p10/p50/p90 fits per
  (spread, composite-regime) cell, then walks forward day-by-day to the
  next cutoff.
- **Trading rule held constant** with production: z-score from train
  residual σ, ±0.5σ entry, target = p50, 20 trading-day horizon, exit at
  horizon (no early stop modelled).
- **Baseline: regime-UNAWARE 252-d rolling z-score on each spread.** Same
  trading rule, same horizon. This isolates the contribution of regime
  conditioning — if it beats the engine, the regime grid isn't adding
  value over the simplest possible benchmark.
- **Phase 1 directional Brent signal is NOT directly comparable** —
  Phase 1 scores Brent outright, not spreads. Documented in the PDF
  caveats; this baseline replaces it as the cleanest apples-to-apples test.

**Headline result — the regime engine UNDERPERFORMS the simple baseline:**

| Metric            | Regime engine | Baseline (252-d z) | Δ            |
|---                |---            |---                 |---           |
| Signals fired     | 2,198         | 2,082              | —            |
| Hit rate          | 59.7 %        | 71.6 %             | **−12.0 ppts** |
| Mean PnL ($/bbl)  | +0.108        | +0.180             | −0.071       |
| Total PnL ($/bbl) | +238.11       | +373.86            | —            |
| Sharpe (ann.)     | +0.24         | +0.39              | **−0.14**    |
| Max drawdown      | −52.47        | −168.86            | (engine wins on DD only) |

**Per-spread lift:** the regime engine matches or beats baseline on
**WTI M3-M6** (Sharpe +0.54 vs +0.29, Δ +0.25) and is close on Brent
M3-M6. It loses substantially on `brent_m1_m2` (−0.92 Sharpe vs baseline)
and `brent_fly_123` (−0.73). Per-winner: **Huber** and **ElasticNet** are
the only candidates with positive Sharpe (+0.41 and +0.40 respectively)
— Ridge and Lasso winners net negative across walk-forward.

**Why the engine underperforms** (working hypothesis for Phase 2.5):

1. **Per-cell training data is too thin** — ~50-150 rows per (spread,
   composite-regime) cell. The 252-d rolling z-score implicitly pools
   across all regimes, gets ~5× more data per fair-value estimate.
2. **The rolling z already captures the bulk of mean reversion** on these
   spreads. Regime conditioning needs to add information *beyond* "is the
   spread far from its 1-year mean?" — and the current 3-axis grid mostly
   correlates with the rolling state.
3. **27-cell grid is over-fragmented.** Many cells have n=30-70 with high
   feature-to-row ratio (10-16 features). The competition picks Ridge or
   Lasso for stability but Ridge winners lose money on average.
4. **No regime-frequency was sampled.** The 2024-2026 window straddles
   CONTANGO almost entirely (≈ 0 CONTANGO trades fired — only NEUTRAL
   and BACK in the by-curve-axis table); the engine has never been tested
   under deep contango in walk-forward.

**Caveats reported transparently in the PDF:**

- WTI is SYNTHESISED (last-1-min mid per session, not exchange print) —
  mentor's real WTI file slots in without code changes.
- 96/162 cells are economically implausible and stay empty (BACK × HIGH,
  CONTANGO × LOW) — feature, not bug.
- 20-day horizon is fixed; 5/60-d evaluation is a one-line change.
- Costs not modelled (commissions, fees, roll slippage compress realised).

**Next steps (Phase 2.5, suggested to mentor):**

1. **Pool to curve-axis only** — collapse the 27-cell grid to 3 buckets
   (CONTANGO/NEUTRAL/BACK), giving ~5× more rows per cell. Run the same
   walk-forward; expectation is fair value estimates stabilise and Sharpe
   moves toward or above baseline.
2. **Try 5- and 60-day horizons** — `FORWARD_DAYS` constant in
   `walkforward.py`. Mentor's Q3 was already flagged as open.
3. **Production-blend strategy** — gate the regime signal on
   per-cell-OOS-R² being positive AND winner ∈ {Huber, ElasticNet}.
   This keeps only the configurations that demonstrably beat baseline on
   walk-forward.

**Files touched (Sprint 4):**

| File | Change |
|---|---|
| `backend/research/walkforward.py`        | NEW — driver + baseline + aggregators (~400 LoC) |
| `backend/research/methodology_pdf.py`    | NEW — two-page reportlab PDF builder |
| `backend/data/research/walkforward_report.json` | NEW — 12.5 KB artifact, regenerable |
| `backend/data/research/PULSE_methodology.pdf`   | NEW — 8.4 KB mentor deliverable |
| `backend/app.py`                         | + `GET /api/regime/walkforward` route |
| `requirements.txt`                       | + `reportlab==4.2.5` |
| `CLAUDE.md`                              | this update |

**Verification:**

- `python -m backend.research.walkforward` completes in ~13 min, writes
  the JSON, prints summary. The trailing per-spread print line trips a
  cp1252 encoding error on Windows for `μ` — cosmetic only, JSON already
  saved by then.
- `python -m backend.research.methodology_pdf` writes the PDF in <1 s.
  Output verified as exactly 2 letter-size pages with all tables flowing.
- `python -c "from research.walkforward import load_report; ..."` returns
  the loaded report (n_trades=3,639, overall hit_rate=0.5965).
- Production endpoints unchanged — `/api/regime`, `/api/regime/recommendation`,
  `/api/regime/backtest`, `/api/regime/drill/<spread>` continue to return
  Sprint-3 payloads. The new `/api/regime/walkforward` is purely additive.

This sprint closes the Phase 2 brief. The mentor now has: (i) a working
regime-conditional spread engine deployed in the dashboard (Sprints 1–3),
(ii) a walk-forward backtest report with per-spread lift vs a clean
baseline, and (iii) a two-page methodology PDF that reports the honest
result (engine currently loses to baseline on most spreads) along with a
concrete improvement plan.

---

### ✅ SPRINT 3 · Broaden universe + 3-axis regime grid — SHIPPED 2026-06-09

Mentor's Q1 (instrument scope) + Q2 (regime axes) + Q5 (WTI deferred file)
addressed end-to-end. The class-demo vertical slice now spans a 6-instrument
universe under a 27-cell composite regime grid.

**Universe — 6 instruments (was 3):**
| key | label | legs |
|---|---|---|
| `brent_m1_m2`   | Brent M1-M2                 | +c1, -c2 |
| `brent_m3_m6`   | Brent M3-M6                 | +c3, -c6 |
| `brent_fly_123` | Brent fly (M1-2M2+M3)       | +c1, -2c2, +c3 |
| `wti_m1_m2`     | WTI M1-M2                   | +c1, -c2 |
| `wti_m3_m6`     | WTI M3-M6                   | +c3, -c6 |
| `wti_fly_123`   | WTI fly (M1-2M2+M3)         | +c1, -2c2, +c3 |

Brent legs source from `/Data Brent C1-C31 daily settlements` (2016-2026).
WTI legs source from the new **synthesised** daily WTI C1-C6 settlements
(`Data/parquet/wti_synth_settlements_c1_c6.parquet`, derived by taking the
last 1-min mid per session from `CL_WTI_1min_outrights_midprice_*.csv`).
Synth file is 83 KB, 1,676 trading days, 2021-01-04 → 2026-05-22. Flag as
ESTIMATE in provenance.

**Regime grid — 27 composite cells (was 4 curve-only buckets):**

| Axis | Buckets | Threshold |
|---|---|---|
| **Curve**     | CONTANGO / NEUTRAL / BACK     | Brent M1-M12 ≤ -$2 · -$2..+$5 · > +$5 |
| **Inventory** | LOW / AVG / HIGH              | US crude stocks vs 5y seasonal: ≤ -4 % · ±4 % · > +4 % |
| **Vol**       | CALM / NORMAL / STRESSED      | Brent realised vol 20d: ≤ 20 % · 20-35 % · > 35 % |

Composite label format: `CURVE/INV/VOL` (e.g. `BACK/LOW/STRESSED`). Hard
thresholds chosen over data-driven quantiles so the mentor can answer "why
this regime?" in one line. 4-bucket legacy classifier (`classify_one`,
`classify_series`) is kept alive in `regimes.py` for any consumers that
hadn't migrated.

**Inventory backfill (new module):** `backend/research/inventory_history.py`
fetches WCRSTUS1 weekly from EIA v2 (600 weeks back to Dec 2014), computes
the 5-year same-ISO-week seasonal, and caches to
`backend/data/research/crude_stocks_history.parquet`. Refresh policy: re-fetch
when cache > 14 days old. If the EIA key is missing the inventory axis
collapses to UNKNOWN and the affected rows drop out at feature-matrix time.

**Models — 162 cells trained, 66 fit (40.7 %), 96 skipped (n_train < 30):**

| Spread | Fit | Skipped | Notes |
|---|---|---|---|
| brent_m1_m2   | 15 | 12 | Full 2016-2026 history available |
| brent_m3_m6   | 15 | 12 | Full 2016-2026 history available |
| brent_fly_123 | 15 | 12 | Full 2016-2026 history available |
| wti_m1_m2     | 7  | 20 | 2021-2026 only (WTI synth) |
| wti_m3_m6     | 7  | 20 | 2021-2026 only (WTI synth) |
| wti_fly_123   | 7  | 20 | 2021-2026 only (WTI synth) |

Winner distribution over the 66 fit cells: **Ridge 20 · ElasticNet 18 · Lasso
16 · Huber 12**. No single model dominates, vindicating the per-cell
competition pattern from Sprint 1.

**Headline pick under the wider grid** (2026-06-09, regime = **BACK/LOW/STRESSED**,
62 days in regime):
> **SELL Brent M3-M6** · current $7.09 · fair $6.36 · 80 % band $5.26-$6.77
> z = +2.63σ · confidence 78 % · OOS R² **0.89**
> Winner: **ElasticNet** (training the new 3-axis cell beat the old 4-bucket
> Lasso cell on the same date by 0.03 R² — tighter conditioning pays off)
> Eligible 6/6 spreads · WTI candidates ranked but none high enough confidence
> · CV R²: ElasticNet +0.82 · Lasso +0.78 · Ridge +0.69 · Huber +0.71

**Top 6 ranked under today's regime:**

| # | spread | dir | z | conf | winner |
|---|---|---|---|---|---|
| 1 | Brent M3-M6   | SELL    | +2.63 | 78 %  | ElasticNet |
| 2 | WTI M3-M6     | SELL    | +0.78 | 18 %  | Lasso |
| 3 | Brent M1-M2   | BUY     | -0.98 | 16 %  | Huber |
| 4 | Brent fly     | BUY     | -0.87 | 14 %  | ElasticNet |
| 5 | WTI fly       | BUY     | -0.51 | 6 %   | Ridge |
| 6 | WTI M1-M2     | NEUTRAL | +0.01 | 0 %   | Huber |

Brent M3-M6 still wins on confidence by a large margin — backwardation +
storage deficit + high vol is exactly the regime that supports a mean-reversion
SELL on the mid-curve carry.

**Files touched (Sprint 3):**

| File | Change |
|---|---|
| `backend/data_lake.py` | + `get_wti_settlements()` + WTI synth parquet write + module-level cache |
| `backend/research/inventory_history.py` | NEW — EIA WCRSTUS1 backfill + parquet cache + 5y seasonal |
| `backend/research/regimes.py` | + 3-axis composite classifier (`classify_curve`, `classify_inv`, `classify_vol`, `composite_label`, `classify_composite_series`) + 27-cell `REGIMES`. Legacy 4-bucket API preserved as `REGIMES_LEGACY` / `classify_one`. |
| `backend/research/spread_universe.py` | INSTRUMENTS 3 → 6; LEG_DEFS adds 3 WTI entries; `current_leg_prices()` dispatches via product; `build_spread_series()` joins Brent + WTI legs |
| `backend/research/features.py` | + WTI columns + inventory column + 3-axis composite regime label + legacy regime label; `predictors_for()` returns wider feature set for WTI cells; WTI columns ffill ≤3 days to bridge synth lag |
| `backend/research/models.py` | + `_safe(regime)` filesystem encoding for composite labels (replace `/` with `-`); + NaN-drop on feat_cols + target before train/test slicing; `load_models()` falls back to legacy filenames |
| `backend/research/live_ranker.py` | `get_current_regime()` returns composite + per-axis breakdown + inventory + WTI drivers; `get_recommendation()` iterates 6 spreads, guards NaN feature/target rows; ffills spreads ≤3 days for live inference |
| `backend/research/drill.py` | No change needed — already uses the regime label transparently |
| `backend/paper_trading.py` | `_live_price()` recognises `wti_m*` / `wti_fly*` keys (WTI spread MTM via `current_values()`) |
| `frontend/src/components/panels/RegimePickCard.tsx` | RegimeState type → 3-axis `axes` field; `regimeChipTone` parses composite labels; subtitle + source note rewritten for "6 spreads × 27 composite regimes"; new 3-axis context strip (Curve · Inventory · Vol · Days); push thesis uses `opp.winner_model` (was hardcoded "Ridge"); eligible/universe counter |
| `frontend/src/components/panels/RegimeDrillModal.tsx` | No change — subtitle composite label renders cleanly |
| `backend/data/research/backtest_report.json` | Regenerated: 162 cells, 66 fit, 96 skipped, n_train=2,652 train rows / 40 test rows |
| `backend/data/research/models/*.pkl` | Old 60 pkls deleted, retrained → 264 new pkls (66 cells × 4 models each: point + q10 + q50 + q90) |

**Verification (all on the running backend at 127.0.0.1:5000):**

- `GET /api/regime` returns composite regime `BACK/LOW/STRESSED` + 3-axis breakdown
- `GET /api/regime/recommendation` returns 6/6 eligible, top = SELL Brent M3-M6 ElasticNet
- `GET /api/regime/drill/brent_m3_m6` returns 268 history points + 3 analogs (all July 2022 backwardation episode)
- `GET /api/regime/drill/wti_m3_m6` returns 261 history points + 3 analogs
- Phase 1 endpoints (`/api/prices`, `/api/signal`, `/api/trade-idea`, `/api/paper/*`, `/api/health`) all return without regression
- `npx tsc --noEmit` clean (only pre-existing `baseUrl` deprecation)
- `npx vite build` clean (5.97 s, 1.06 MB bundle)
- WTI leg dispatch verified: `current_leg_prices('wti_m3_m6') = {c3: 91.36, c6: 82.87}` — pushing SHORT wti_m3_m6 would write parent + 2 paper_legs rows correctly

**Honest caveats:**

- WTI settlements are SYNTHESISED (last 1-min mid per session, not exchange print).
  Mentor's real file would land truer settlements without changing any downstream code
  (only `data_lake.get_wti_settlements()` is the entry point).
- WTI cells only have 1,403 effective training rows vs Brent's 2,652. Several
  WTI regimes have n_train < MIN_SAMPLES=30 and were skipped.
- 96/162 cells are empty — expected outcome of widening a sparse grid. The
  empty cells are systematically BACK × HIGH (extreme backwardation almost
  never coexists with storage glut) and CONTANGO × LOW (deep contango almost
  never coexists with storage deficit). These collapses are economically
  sensible, not a model defect.
- The fly model is still genuinely weak in some regimes. Reported transparently
  in the UI rather than hidden.
- 4-bucket legacy regime label kept alive for any consumers that hadn't migrated;
  drill modal subtitle currently shows the composite label as-is.

This sprint **delivers the mentor's Phase 2 brief** (3-axis curve × inventory ×
vol regime grid, 6-spread universe including the 2 calendar butterflies). The
remaining open question is whether she wants the EIA inventory axis swapped for
something different (e.g. EIA crude stocks Z-score over a different window, or
inventory surprise vs forecast). Either swap is now a one-classifier-function
change in `regimes.py`.

---

## Directory layout

```
pulse/
├── start.py                          # one-command launcher (local dev)
├── CLAUDE.md                         # THIS FILE
├── .env                              # API keys (gitignored)
├── .env.example                      # template
├── requirements.txt                  # pinned Python deps
├── Dockerfile                        # PHASE 3.D — multi-stage: node build → python:3.13-slim (uv) → gunicorn wsgi:app
├── .dockerignore                     # PHASE 3.D — excludes Data/, db, research, node_modules, secrets
├── docker-compose.yml                # PHASE 3.D — pulse (internal) + caddy (public, basic auth + auto-HTTPS)
├── deploy/                           # PHASE 3.D — Caddyfile + README.md (runbook) + smoke_test.sh
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
│   ├── app.py                        # Flask API, ~1400 lines, all routes + scheduler (scheduler.start() only in __main__)
│   ├── wsgi.py                       # PHASE 3.D — gunicorn entry: starts scheduler + warm-up under gunicorn (--workers 1)
│   ├── data_lake.py                  # /Data loaders (becomes DuckDB-backed in Sprint −1)
│   ├── paper_trading.py              # SQLite trade book + MTM service (Phase 3.D: WAL pragmas in _conn)
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
│   └── research/                     # Phase 2 — class-demo + 4-model competition + Sprint 3 widening + Phase 2.5
│       ├── regimes.py                # composite 27-cell + pooled 3-cell curve-axis (Phase 2.5) + legacy 4-bucket
│       ├── spread_universe.py        # 6 instruments: Brent + WTI {M1-M2, M3-M6, front fly}
│       ├── features.py               # point-in-time matrix — emits `regime`, `regime_pooled`, `regime_legacy`
│       ├── inventory_history.py      # Sprint 3: EIA WCRSTUS1 backfill + 5y seasonal cache
│       ├── models.py                 # 4-model competition + Quantile bands; `regime_mode={composite,pooled}` (Phase 2.5)
│       ├── live_ranker.py            # classify → predict → rank; reads `PULSE_REGIME_MODE` env var
│       ├── drill.py                  # Sprint 2c: scatter + 3 nearest analogs per pick (mode-aware)
│       ├── walkforward.py            # Sprint 4 + Phase 2.5 / 2.6 / 2.7 / 2.8.6: composite + pooled + gated_blend + sized_blend{full,half,kelly} + baseline + NET (after costs) blocks in one report; writes gated_trades.json + composite_trades.json + pooled_trades.json + baseline_trades.json for future cost recomputes
│       ├── reroute_gated.py          # Phase 2.8.3 + 2.8.6: re-aggregate gated/sized + compute NET blocks from gated_trades.json (+ rebuilt baseline) without retraining
│       └── methodology_pdf.py        # 5-page mentor PDF — composite/pooled/gated/baseline + Phase 2.7 sized headline + Phase 2.8.6 NET section
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

## API endpoints (37 active — 32 Phase 1 + 5 regime engine)

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
| **Phase 2 regime engine** | GET /api/regime · GET /api/regime/recommendation · GET /api/regime/backtest · GET /api/regime/drill/&lt;spread&gt; · GET /api/regime/walkforward |
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
# Phase 2.5 / 2.6 / 2.7 regime engine mode flags (opt-in; unset = composite default):
PULSE_REGIME_MODE=pooled  # un-gated pooled inference (3-cell curve-axis grid)
PULSE_GATED_BLEND=1       # Phase 2.6 production rule: pooled on BACK + {Lasso, Huber} + |z|≥0.5σ, else 252d baseline. Forces pooled internally.
PULSE_GATED_SIZE=half     # Phase 2.7 position sizing on the regime leg of the gated blend. Values: full (default; no sizing) | half (0.5× notional) | kelly (per-spread Kelly from prior closed regime-leg PnLs, read from sized_blend_summary in walkforward_report.json). Baseline leg always 1.0.
# Phase 2.8.6-followup A/B paper-test harness:
PULSE_AB_TEST_DISABLED=1  # opt-out flag — when set, the daily A/B tick scheduler job is skipped. The API routes still work for manual ticks. Unset / 0 = harness active (default).
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
| `parquet/wti_synth_settlements_c1_c6.parquet` (83 KB, Sprint 3) | `data_lake.get_wti_settlements()` via Sprint 3 regime engine | **Synthesised** daily WTI C1-C6 settlements (last 1-min mid per session). Flagged ESTIMATE until mentor delivers a real WTI C1-C3 daily file. |

**Gap (mentor question Q5):** no WTI equivalent of the daily C1-C31 settlement file. Sprint 3 unblocks with a synthesised replacement; mentor still owed a request for the real file (drafted in Mentor communication log below).

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

## Trade Idea pipelines — two now coexist

### Phase 1 — directional Brent (signal engine)

```
signal_engine.score (9-indicator weighted composite)
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
trader sees on Signal tab + the lower card on Paper tab. "Push to Paper" stages a single-asset Brent position.
```

### Phase 2 — regime-conditional spread/fly (regime engine, class-demo)

```
classify M1-M12 into 4 regimes (EXT_CONTANGO / MILD_CONTANGO / MILD_BACK / EXT_BACK)
        ↓
load per-(spread, regime) winning model — competition winner from {Ridge, Lasso, ElasticNet, Huber}
        ↓
for each of 3 spreads (Brent M1-M2, M3-M6, front fly):
  fair = winner_model.predict(today_features)
  band = (quantile_p10, quantile_p90)
  z    = (actual − fair) / resid_std
  confidence = |z| / 3 × R²_oos × √(n_train / 100)
        ↓
rank by confidence → return #1
        ↓
direction = BUY if z < −0.5  |  SELL if z > +0.5  |  NEUTRAL else
target    = quantile_p50  (mean revert toward median)
stop      = entry ± 1.5 × resid_std
        ↓
trader sees on top card of Paper tab. "Push to Paper" stages a spread position
with asset='brent_m3_m6' etc. (live MTM uses spread-aware _live_price()).
```

---

## Paper trading

- **Tables:** `paper_trades` (parent: one row per opened position) + `paper_legs` (Sprint 2b: outright decomposition of any spread/fly position, e.g. SHORT brent_m3_m6 ⇒ SHORT c3 + LONG c6 rows) in `pulse_cache.db`. Single-asset trades still have an empty `legs: []`.
- **MTM job:** APScheduler every 60s. Refreshes parent synthetic-spread MTM + each leg's outright MTM. TP/SL still evaluated on the synthetic spread.
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
| 3 | Sentry observability | Safety net while writing Phase 2 code | **Sprint 0b ✅ shipped 2026-06-09** |

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
11. **Regime engine retraining** — `python -m backend.research.models` retrains all 12 cells from scratch (~40s with the 4-model competition). Idempotent; overwrites `backend/data/research/models/*.pkl` + `backtest_report.json`. Run whenever the train cutoff moves or features change.
12. **Spread-as-asset in paper trading** — when a regime-engine trade is pushed, `asset` is set to `brent_m3_m6` (or whichever spread). `paper_trading._live_price()` recognises this prefix and computes the spread value from /Data on demand. Don't break this — the legacy single-asset path (`brent` / `wti` / `henry_hub`) still works for the Trade Idea card.
13. **paper_legs table (Sprint 2b)** — every spread/fly push also writes one row per outright leg into `paper_legs`, mapped via `research.spread_universe.LEG_DEFS`. Legs follow the parent's lifecycle (mtm sweep → close → clear). TP/SL is still evaluated on the synthetic spread (`_live_price()` of the spread asset), NOT per-leg. The Pydantic `PaperPosition` now exposes `legs: list[PaperLeg]`; PaperView indents them under the parent row. Single-asset trades still get an empty `legs: []`.
14. **Drill endpoint is on-demand only (Sprint 2c)** — `/api/regime/drill/<spread>` is NOT polled; the React modal fetches once per open. It runs the per-cell point model across the whole regime history (~200-1000 rows × 3 ms = fast), so no caching layer; rebuild after `python -m backend.research.models` retrains. Analogs deliberately exclude the last `FORWARD_DAYS=20` rows so every match has a real forward window.
15. **Composite regime filenames (Sprint 3)** — Composite regime labels contain `/` (e.g. `BACK/LOW/STRESSED`), which collides with Windows path separators. `models.py:_safe(regime)` replaces `/` → `-` when writing/reading pkl files, so the on-disk key is `brent_m3_m6__BACK-LOW-STRESSED__point.pkl`. Internal cell keys in `backtest_report.json` still use the human-readable `/` form. Don't rename the helper — both `train_all()` and `load_models()` depend on it.
16. **WTI synth settlements are ESTIMATE (Sprint 3)** — `data_lake.get_wti_settlements()` returns daily WTI C1-C6 derived by taking the last 1-min mid per session from `CL_WTI_1min_outrights_midprice_*.csv`. This is NOT an exchange settlement print. The parquet cache at `Data/parquet/wti_synth_settlements_c1_c6.parquet` is rebuilt automatically when the WTI 1-min source parquet is newer. When mentor provides a real WTI daily settlement file, swap the data source inside `_load_wti_settlements()` — every downstream consumer goes through `get_wti_settlements()` and won't notice.
17. **WTI features/spreads ffill ≤ 3 days for live inference (Sprint 3)** — WTI 1-min data tops 1-2 sessions before Brent's latest daily settle. `features.build_features()` ffills the WTI feature columns by ≤ 3 business days; `live_ranker.get_recommendation()` ffills the WTI target spreads identically. This bridges the synth lag at live-inference time without affecting historical training rows (those rows have real WTI prints, ffill is a no-op).
18. **EIA crude stocks history cache (Sprint 3)** — `inventory_history.get_crude_stocks_history()` fetches WCRSTUS1 weekly (600 weeks, back to Dec 2014) and caches to `backend/data/research/crude_stocks_history.parquet`. Refreshes when cache > 14 days old. If the cache is fresh, no API call. If the API fails AND a stale cache exists, it falls back to the stale cache with a warning. Force rebuild with `python -m backend.research.inventory_history`.
19. **Walk-forward expects unbuffered Python (Sprint 4)** — `python -m backend.research.walkforward` runs ~13 min on this machine and writes `walkforward_report.json` BEFORE printing the final summary. The trailing summary print contains a `μ` glyph which trips cp1252 on Windows — cosmetic error, the JSON is already on disk by then. If you pipe via `| tail -N` the output buffers; use `python -u -m ... 1>walkforward.log 2>&1` for streamed progress.
20. **walkforward.py reuses models.py internals** — `_fit_ridge`, `_fit_lasso`, `_fit_elastic`, `_fit_huber`, `_fit_quantile`, `_cv_r2`, `_TIEBREAK_RANK` are imported directly. Changing the competition logic in `models.py` automatically propagates to walk-forward — that's intentional, but a refactor that breaks those signatures will break Sprint 4 silently. The walk-forward does NOT touch the production model pkl files; it trains in-memory only.
21. **Methodology PDF regeneration is fast + idempotent** — `python -m backend.research.methodology_pdf` rebuilds `PULSE_methodology.pdf` from whatever `walkforward_report.json` is on disk. Run it after re-running the walk-forward (e.g. with different `FORWARD_DAYS` or `REFIT_DATES`) to refresh mentor-facing numbers without touching the methodology copy.
22. **`PULSE_REGIME_MODE` env var swaps regime grids at inference time (Phase 2.5)** — unset / `composite` → 27-cell Sprint 3 grid (default); `pooled` → 3-cell curve-axis grid. Read by `live_ranker._active_mode()` and `drill.py`. Falls back to composite if pooled models aren't on disk. The Pydantic `RegimeRecommendation`/`RegimeState` types don't yet expose `regime_mode` — UI shows whichever label is active without distinguishing. Toggle by exporting the env var BEFORE starting `python start.py`.
23. **Pooled-mode artefacts live in parallel directories (Phase 2.5)** — `backend/data/research/models_pooled/` for pkls, `backtest_report_pooled.json` for the training report. `models.load_models(regime_mode="pooled")` / `load_report(regime_mode="pooled")`. Don't mix: a pooled call reading the composite directory would get cell-key mismatches and silently return empty. The walk-forward report (`walkforward_report.json`) is shared — it contains both modes as sub-blocks (`composite`, `pooled`) plus the baseline.
24. **Pooled-mode CONTANGO is empty in 2024-2026 walk-forward** — the test window had no days where M1-M12 ≤ -$2 (the CONTANGO threshold) sustained long enough to fire a ±0.5σ signal. So pooled `by_curve_axis` shows only NEUTRAL + BACK rows. This is a window artifact, not a code bug — the CONTANGO cells are trained (442 rows for Brent, 0 for WTI) and would fire if conditions returned. If broadening the walk-forward back to 2020-2026 to include the COVID contango episode is desired, prepend more dates to `REFIT_DATES` in `walkforward.py`.
25. **`PULSE_GATED_BLEND=1` forces pooled inference (Phase 2.6)** — `live_ranker._active_mode()` returns `"pooled"` whenever the gated flag is on, regardless of `PULSE_REGIME_MODE`. This is deliberate: the gate rule is defined on the pooled `regime_pooled='BACK'` label, so composite mode under gating would be self-contradictory. The fallback path (no pooled models on disk) logs a warning and serves a baseline-only recommendation. To run un-gated pooled mode, leave `PULSE_GATED_BLEND` unset and set `PULSE_REGIME_MODE=pooled`.
26. **Gated-blend rule lives in two mirror copies — keep them in sync** — `live_ranker._pooled_passes_gate(regime, winner, z)` (inference) and `walkforward._pooled_passes_gate(p)` (walk-forward) implement the same Phase 2.6 production rule. They MUST agree bit-for-bit or the live engine will fire on signals the walk-forward never validated. If you change the gate (different regime/winners/threshold), update both and re-run `python -m backend.research.walkforward` before claiming "the new gate beats baseline."
27. **Baseline rolling-z window is 252 trading days** — `ROLLING_WIN=252` in both `live_ranker.py` and `walkforward.py`. If you change this, both must change or the live and walk-forward baselines diverge. The baseline candidate in `live_ranker._baseline_rolling_signal` uses `±1σ` for the p10/p90 confidence band — this is the simple-baseline analog of the quantile p10/p90 bands the regime engine emits, deliberately wider than the quantile model's narrower bands so the UI doesn't suggest baseline rows are tighter than they are.
28. **Gated leg max DD is genuinely worse than baseline** — gated −271 vs baseline −169 in Phase 2.6 walk-forward. This is the cost of concentration: 97 high-Sharpe fires across a small number of days means the bad days hurt more in absolute terms. The Sharpe and hit-rate gains compensate. **Phase 2.7 attempted to fix this with sizing and FAILED at the headline DD** — see gotcha 30 below: DD is actually baseline-dominated, not regime-dominated, so sizing the regime leg can't fix it.
29. **`PULSE_GATED_SIZE` is independent of `PULSE_GATED_BLEND` but only takes effect when gated_blend is on** (Phase 2.7) — `live_ranker._gated_size_mode()` returns `'full'` (no sizing) unless `PULSE_GATED_BLEND=1` is also set. This is deliberate: sizing only makes sense when there's a gated blend to size. Invalid values fall back to `full` with a log warning. `live_ranker._kelly_lookup_from_report()` reads `sized_blend_summary.kelly_per_spread_latest` from `walkforward_report.json`; if the report predates Phase 2.7 (no sized_blend block), Kelly mode silently uses the default 0.5 on all spreads — REGENERATE the walk-forward (`python -m backend.research.walkforward`) before relying on Kelly in production.
30. **Phase 2.7 DD hypothesis was wrong** — the brief assumed regime-leg sizing would compress the gated −271 max DD. It does not. The regime leg's own DD is only −6.66 (gated/full by_source); the −271 lives entirely on the baseline leg. Sized-half drops regime DD to −3.33 and sized-kelly to −4.68 but the blended max DD barely moves. Mean PnL drops proportionally with the scale, so headline Sharpe slightly worsens under sizing (0.456 full → 0.434 half → 0.426 kelly). **The actual Phase 2.7 win** is per-spread: half-sizing lifts Brent fly_123 Sharpe from +1.833 to +2.192 (+0.43) because the regime leg's volatility contribution to that spread's blended Sharpe shrinks while the baseline leg's strong +2.34 carry takes over. If shipping Phase 2.7 to a live book, consider it a per-spread variance-reduction tool, not a DD-compression tool.
31. **`gated_trades.json` is the persistent post-processing surface** — `run_walkforward()` writes the raw gated-leg trade tape to `backend/data/research/gated_trades.json` (~1 MB, 3,640 records) so future Phase 2.8+ sizing experiments can be tested in seconds. Schema: list of `{date, spread, regime, actual, z, direction, winner, fwd_pnl, fwd_date, source, gate, ...}`. Re-run `_apply_sizing(trades, mode, refit_ts)` or write a new sizing mode and aggregate via `_aggregate_mode(sized_trades, refit_meta, name)` — no model retraining required. The file is gitignored by virtue of the `backend/data/research/` exclusion.
32. **Kelly is expanding-window, recomputed at every refit boundary** — `_compute_kelly_by_cutoff()` returns `{cutoff_str → {spread → kelly}}` covering all 10 refits. The walk-forward applies the cutoff-specific Kelly to trades dated AFTER that cutoff (find the largest cutoff ≤ trade date). For live inference, only the LAST refit boundary's Kelly map is surfaced in `sized_blend_summary.kelly_per_spread_latest` — that's the schedule a deployed strategy would replicate going forward. The kelly_per_cutoff dict in the report exposes the full schedule for audit/debugging.
33. **Boosters compete in walk-forward POOLED mode only (Phase 2.8.1)** — `backend/research/walkforward.py:_train_cells_through()` populates `booster_fitters` only when `regime_mode == 'pooled'`. Composite mode has 27 cells × 10 refits = 270 cell-refits and adding 3 boosters × ~6 fits each would multiply wall-time ~5×; the Phase 2.6 gated_blend only consumes pooled winners ∈ {Lasso, Huber} anyway, so booster composite winners can't flow into the headline gated_blend Sharpe regardless. The standalone `python -m backend.research.models --mode composite` invocation DOES compete all 7 candidates (that's the model served on `/api/regime`). If you ever want composite-mode walk-forward to include boosters for ablation, flip the `if regime_mode == "pooled":` guard — but budget ~5h walk-forward wall time.
34. **`_BOOSTER_MIN_ROWS=80` gates booster competition on small samples (Phase 2.8.1)** — in both `models.py:train_all()` and `walkforward.py:_train_cells_through()`, cells with fewer than 80 train rows skip the booster fitters entirely. Small samples can't reliably distinguish trees from linear via CV, and the booster fits dominate refit wall-time. If you tune this lower, expect walk-forward to slow proportionally. The threshold lives once in `models.py`; walkforward imports it.
35. **Phase 2.8.1 broke the Phase 2.6 gate; Phase 2.8.3 is the fix** — Phase 2.6 hard-coded `GATED_WINNERS = {"Lasso", "Huber"}` based on the Phase 2.5 finding that those were the strong winners under the BACK regime. Phase 2.8.1 boosters now legitimately win cells the gate rejects (LightGBM +1.294 / CatBoost +1.248 / XGBoost +0.853 in pooled walk-forward). Net: 85 gate fires post-2.8 vs 97 pre-2.8, with the surviving fires sharing the slice with weaker patterns → gated Sharpe dropped from +0.456 to +0.389. The fix is one line — extend `GATED_WINNERS` in `walkforward.py` AND mirror in `live_ranker.py:GATED_WINNERS` (the two MUST stay in sync per gotcha 26).
36. **Phase 2.8.2 features need their parquet caches** — `cot_history.parquet` (CFTC backfill, refreshed ≥14 days old) and `external_history.parquet` (FRED + yfinance backfill, refreshed ≥7 days old). On a fresh clone with EIA_API_KEY + FRED_API_KEY set, the first `build_features()` call triggers `cot_history._build_history(years)` (downloads ~12 zips, ~5 min) and `external_history._assemble()` (~1 min). Both fall back to a stale cache if the API fails. If you want to force a refresh, call `get_cot_history(force_refresh=True)` / `get_external_history(force_refresh=True)`. If neither key is set, those features become NaN and the `dropna(BRENT_FEATURES)` at the end of `features.build_features()` wipes the matrix — fail-loud-on-import is intentional so the operator notices.
37. **Phase 2.8.6 cost model is reporting-only — live inference does NOT subtract cost** — `walkforward.COST_PER_SPREAD_RT` and `_cost_for(t)` are consumed by `_metrics(trades, cost_fn=_cost_for)` to compute NET aggregates for the methodology PDF + walkforward report. `live_ranker.get_recommendation()` returns fair value / z / bands as gross spread prices because (i) the trader is the one paying commissions and knows the broker rate, and (ii) the cost-aware threshold for "fire vs hold" is a trading-rule decision that should live in the trading rule, not the model. If you want a NET-aware live signal in the future, add the cost subtraction at the `direction` decision step in `live_ranker.py` (would need a mirror in `walkforward._evaluate_window` to keep gotcha-26-style parity).
38. **Phase 2.8.6 cost scales with `sizing_scale` on regime rows** — `_cost_for` returns `base × t.get('sizing_scale', 1.0)`. So a half-sized regime fly trade costs $0.025/bbl (half of $0.050), matching the half-notional reality. Baseline rows always have `sizing_scale=1.0` after `_apply_sizing`, so their cost is unscaled. If you write a new sizing mode, set `sizing_scale` on the trade record and `_cost_for` picks it up automatically.
39. **Phase 2.8.6 NET aggregation works on the trade-tape level only** — `_metrics(trades, cost_fn=_cost_for)` computes per-trade gross−cost and then aggregates Sharpe/hit/DD on the net series. So the NET Sharpe uses the EXACT post-cost trade distribution (incl. correct variance). Don't try to derive NET Sharpe from gross by `gross_sharpe × net_mean / gross_mean` — that's a first-order approximation that misses second-order effects on variance. If a future report needs NET for a mode whose trade tape isn't persisted, run the full walk-forward to write the missing tape (`composite_trades.json` etc.) — reroute only handles modes whose tapes are reconstructible from `gated_trades.json` (pooled + baseline + sized).
40. **Phase 2.8.6 persists 4 trade-tape JSONs** — `gated_trades.json` (Phase 2.7, always written), `composite_trades.json`, `pooled_trades.json`, `baseline_trades.json` (all three new). These let any future cost-model change (different per-spread cost, per-broker overrides, roll slippage layer) re-aggregate in seconds via a reroute-style script. Aggregate size ~5 MB — gitignored by virtue of `backend/data/research/` exclusion. Re-aggregating without re-running the ~3h walk-forward only works if these tapes are present; pre-2.8.6 reports have only `gated_trades.json` so composite NET is unavailable until next walk-forward run.
41. **Phase 2.8.6-followup A/B harness uses force_mode/force_gated kwargs, NOT env-var swap** — `live_ranker.get_recommendation(force_mode='pooled', force_gated=True)` overrides `_active_mode()` and `_gated_blend_enabled()` at the call site so the A/B harness can generate both arms within one process tick without `os.environ[...] = ...` mutation (which would race with other request handlers in Flask + APScheduler). If you add a third "arm" to the harness later (e.g. composite-only un-gated), extend the `arms` tuple in `ab_test.tick()` with another `(name, kwargs)` entry — both the dedup and reporting paths key off `ab_mode` which is whatever string you pass to `push_trade`. If you forget to pass `force_gated=False` for the pooled arm and `PULSE_GATED_BLEND=1` is set in the env, the pooled arm WILL silently become a gated push (env-var wins when `force_gated is None`), nullifying the A/B. Always pass both kwargs explicitly when calling for an arm.
42. **Phase 2.8.6-followup A/B cost table is a MIRROR — keep in sync with walkforward.COST_PER_SPREAD_RT** — `ab_test.COST_PER_SPREAD_RT` duplicates `walkforward.COST_PER_SPREAD_RT`. If you change the per-spread cost (different broker rate, roll-slippage layer) in walkforward, mirror it in ab_test or the paper-headline NET Sharpe will drift from the methodology PDF NET Sharpe. Both currently use the same exchange-published-fee anchored numbers ($0.030/$0.040/$0.050 RT for M1-M2 / M3-M6 / fly). Test coverage: smoke test `from research.ab_test import COST_PER_SPREAD_RT as A; from research.walkforward import COST_PER_SPREAD_RT as B; assert A == B`.
43. **Phase 2.8.6-followup paper_trades.ab_mode is sparse and BACKWARD-COMPAT** — legacy paper rows (from before this sprint) have `ab_mode=NULL`. `list_positions()`, `get_performance()`, and the regular Paper tab analytics do NOT filter on ab_mode, so they continue to surface ALL paper trades (including the A/B-tagged ones). That's intentional: the trader-pushed paper book and the A/B paper books live in one table. If the regular Paper analytics should EXCLUDE A/B rows in the future (so the trader's manual book is judged independently), add `AND ab_mode IS NULL` to the SQL in `get_performance()` and `list_positions()`. Don't do this prematurely — currently it's useful that the equity curve in the regular Paper tab reflects the harness contributions too.
44. **Phase 2.8.6-followup A/B dedup is per (asset, direction, ab_mode), NOT per session** — `open_position_exists()` looks at OPEN status with no ab_session filter. If a position closes on day N (TP/SL hit, or manual close), the next day's tick CAN reopen the same (asset, direction, ab_mode) — that's correct, the previous position closed and the signal is still firing. But if a position stays open for 14 days because TP/SL never hit, the daily tick will SKIP it every day with reason `already_open`. This matches what a live book does (it doesn't double down) but it means the n_closed counter for stop criteria can grow slower than n_opened might suggest. Look at the `n_closed` metric, not `n_opened`, when judging stop-criteria progress.
45. **Phase 2.8.6-followup A/B scheduler job runs once per 24h, NOT on next_run_time=_NOW** — `_ab_tick` is scheduled with `next_run_time = _dt.now() + timedelta(minutes=5)` deliberately. The data lake + regime model loads take ~60 s; firing the first tick at boot risks a `features matrix empty` error if the warm-up hasn't completed. The 5-minute buffer is conservative. If you change the cadence (e.g. 4-hourly during a fast A/B), `next_run_time` should still have at least a 2-minute buffer past boot.
46. **Phase 2.9.0 exit-sim needs p50 + resid_std on the tape — which the reroute strips** — `exit_sim.py` computes TP from `p50` (regime rows) / `roll_mu` (baseline rows) and SL from `resid_std` / `roll_sigma`. The persisted `gated_trades.json` written by `reroute_gated.py` (Phase 2.8.3) sets `fair`/`p10`/`p50`/`p90`/`fwd_date` to `None` on regime rows, so it is **useless for exit-sim**. `exit_sim.build_tapes()` therefore regenerates its own enriched tapes via a pooled-only walk-forward (~44 min) and saves them to `exit_sim_tapes.json`; use `--from-cache` to re-simulate without retraining. A full `python -m research.walkforward` now also persists these fields (gotcha-attached additive edits to `_evaluate_window` + `_baseline_trades` + `_build_gated_blend`), so post-2.9.0 walk-forward tapes are exit-sim-ready without a separate run.
48. **Phase 2.9.2 tuned exit rule lives in 3 places — keep the time-stop mirrored** — the tuned rule (TP halfway-to-fair, SL 2.5σ, 30d time-stop, drop M3-M6) is applied in `live_ranker.py` (`TUNED_TP_FRAC`/`TUNED_SL_MULT`/`TUNED_MAX_HOLD_DAYS`/`TUNED_EXCLUDED_SPREADS`) and `paper_trading.py` (`TUNED_MAX_HOLD_TRADING_DAYS`, a MIRROR of `live_ranker.TUNED_MAX_HOLD_DAYS` — keep in sync; parity to be asserted in `test_invariants.py` in Phase 3.0). TP/SL VALUES flow from the recommendation into the paper book, so they can't drift; only the time-stop integer is duplicated. The rule does NOT change the gate (entry z stays 0.5 = `GATED_Z_THRESHOLD`), so gotcha 26 is untouched. The walk-forward (`walkforward.py`) deliberately still trades all 6 spreads at p50/1.5σ/20d — it validates the model+gate and produces the exit-sim tapes; the exit rule is a separate layer (exit_sim/exit_tuning → live_ranker/paper_trading). Do NOT fold the exit rule into walkforward.
47. **Phase 2.9.0 fill-at-level + SCRATCH conventions** — exit fills happen AT the level (limit/stop proxy for the 60s MTM book), NOT at the daily settle that crossed it. Degenerate wrong-side-p50 signals (where the quantile median contradicts the z-direction) close as `SCRATCH` at entry (gross PnL ≈ 0), mirroring the live book opening-then-immediately-closing them — do NOT "fix" this to a far-side fill or you reintroduce fake losses (pooled PF would drop 1.97 → 1.38). TIME-stop PnL equals directional `fwd_pnl` to ≤0.0001 (rounding) — keep that reconciliation as the sim's correctness check. Daily settles miss intraday touches, so TP/SL counts are slightly conservative (documented, accepted — no intraday data per brief).
49. **Phase 2.9.3 OOS uses the DETERMINISTIC baseline leg — that's the no-retrain trick, not a shortcut** — `exit_robustness.py` tests the tuned exit rule out-of-sample over 2017→Nov-2023 by rebuilding ONLY `walkforward._baseline_trades` (rolling-252d-z, no model fit) for that era and running the 2.9.0 simulator on it. This is deliberate: the baseline leg is 93 % of production fires AND the exit knobs are leg-agnostic, so it's a clean test of the tuned rule with ZERO model retraining (the brief's hard constraint). Do NOT "improve" this by running a pooled walk-forward over 2017-2023 to add the 7 % regime leg — that IS retraining and is explicitly out of scope; the regime-leg OOS gap is a documented caveat, not a bug. The verdict is **graded on purpose** (`win_rate_robust` vs `edge_robust` are separate booleans) — do NOT collapse it to one flag: the win rate is robust (~74-75 % OOS, plateau) but the NET Sharpe/PF are in-sample-optimistic (OOS Sharpe 0.165 < 0.211 floor; brent_fly_123 PF<1 in 2017-2023). The script touches NO production code/models — it's analysis-only; `exit_robustness_report.json` is the artifact. The tuned rule was NOT changed by 2.9.3 (it didn't collapse and isn't a spike), so live_ranker/paper_trading are untouched (gotcha 48 still current).
50. **Phase 3.D — gunicorn MUST stay `--workers 1`, and the scheduler starts in `wsgi.py`, NOT app.py's `__main__`** — under gunicorn, app.py's `if __name__ == "__main__"` never runs, so `backend/wsgi.py` is the production entry: it imports `app` and calls `_scheduler.start()` + `warm_cache()` once at import. With >1 worker, every worker imports wsgi and starts its OWN scheduler → the daily A/B tick, the 60 s MTM, and every refresh job fire once per worker (N× cadence + N writers on the book). The Dockerfile CMD hard-codes `--workers 1 --threads 8` (threads give request concurrency; one process keeps the scheduler singular). Do NOT add `--preload` — APScheduler threads don't survive `fork()`, so they'd start in the master and never run in the worker. `python start.py` / `python backend/app.py` is unchanged for local dev (its `__main__` block still starts everything).
51. **Phase 3.D — bind-mount writability is the #1 deploy gotcha; the app is internal-only behind Caddy** — the container runs non-root (uid 10001) and `backend/db` (the SQLite book) must be writable by it: either set `PULSE_UID=$(id -u)`/`PULSE_GID=$(id -g)` in `.env` (compose runs the container as the host user) OR `sudo chown -R 10001:10001 backend/db`. `Data/` is mounted RW (data_lake regenerates the WTI-synth parquet on demand); `backend/data/research` is RO (models are read-only at serve time — retraining is a host-side job). The `pulse` service uses compose `expose` (not `ports`), so it's only reachable on the compose network — **Caddy is the sole public entry point**, gating everything except `/api/health` behind basic auth (creds in `.env`, passed via env_file so the bcrypt `$` needs no `$$` escaping). WAL needs local disk (ext4/xfs), not NFS. Full runbook: `deploy/README.md`.

---

## Mentor communication log

| Date | Event |
|---|---|
| 2026-05-29 | Phase 1 mid-review: "trade signals too strong (BUY/SELL), too much glare. Need bullish/bearish labels, replay button, morning brief always visible, fix news bugs." → ALL ADDRESSED in PR #2. |
| 2026-06-05 (AM) | Phase 1 final demo. Approved. Mentor asks for **regime-based market analysis engine** (full Phase 2 brief, 7 questions sent). |
| 2026-06-05 (PM) | 7 alignment questions sent (see "Pending decisions"). Awaiting reply. |
| 2026-06-08 (class) | Mentor narrowed scope for in-class discussion: 4 curve regimes (extreme/mild contango/back), per-regime fair value, best regression method, output single most-profitable spread/fly, train ≤ 31-Mar / test Apr-May, surface on Paper Trading tab. **Built and shipped end-to-end before class** including the 4-model competition (Ridge/Lasso/ElasticNet/Huber). Lasso won the headline cell (M3-M6 × EXT_BACK) with CV R² 0.65 vs Ridge 0.30. |
| 2026-06-09 | **Sprint 3 shipped**: Phase 2 brief implemented at full scope — 6 spreads (3 Brent + 3 WTI mirrors), 27 composite cells (curve × inventory × vol). 66/162 cells fit (~10/spread on average, matching her "9-12 usable" prediction). Headline pick under the wider grid still SELL Brent M3-M6 (now winner=ElasticNet, OOS R²=0.89, up from 0.86). |
| 2026-06-09 | **Mentor message DRAFTED (not yet sent), re Q5 WTI deferred file** — see "Draft mentor message" below. Owner to send when ready. |
| 2026-06-09 | **Sprint 4 shipped**: walk-forward (10 quarterly refits, 2024-2026, 3,639 records, 2,198 signals fired) + regime-unaware 252d-z baseline + two-page methodology PDF. **Honest finding to surface to mentor:** the regime engine UNDERPERFORMS the baseline overall (Sharpe 0.24 vs 0.39; hit rate 59.7 % vs 71.6 %). Regime conditioning only adds value on WTI M3-M6. Phase 2.5 proposal in the PDF: collapse to curve-axis-only pooled regressions (~5× more data per cell). PDF at `backend/data/research/PULSE_methodology.pdf`. |
| 2026-06-09 | **Phase 2.5 shipped + result**: pooled mode (curve-axis only, 3 cells/spread) tested in walk-forward. **The Sprint-4 hypothesis was wrong** — more rows per cell did NOT close the gap to baseline (Sharpe 0.195 pooled vs 0.245 composite vs 0.385 baseline). **However:** pooled beats baseline on `wti_fly_123` (+0.91 vs +0.90) and the BACK curve regime under pooled mode delivers Sharpe +0.60. Concrete production recommendation in updated methodology PDF: ship a **gated blend** — use the regime engine where `regime_pooled='BACK'` AND `winner_model ∈ {Lasso, Huber}`, fall back to rolling z otherwise. PDF + report regenerated; both modes coexist behind `PULSE_REGIME_MODE` env var. |
| 2026-06-09 | **Mentor sent `CL_data.csv` in response to Q5 ask**. Checked it: byte-identical (MD5 match) to the existing `CL_WTI_1min_outrights_midprice_2021_2026.csv` — same 1-min midprice data, NOT the daily settlement file. Reply drafted to ma'am clarifying we have the 1-min data already and what was hoped-for is a daily settlement file like the Brent C1-C31 one (would let WTI models train back to 2016 and drop the ESTIMATE flag). No code changes needed. |
| 2026-06-09 | **Phase 2.6 shipped + result**: gated-blend production rule implemented behind `PULSE_GATED_BLEND=1`. Pooled signal fires only on (BACK regime × {Lasso, Huber} winner × \|z\|≥0.5σ); else 252d rolling-z baseline. Walk-forward third leg verifies the rule end-to-end. **Headline beats Phase 2.5's prediction**: gated Sharpe **+0.456** vs baseline +0.385 (lift +0.07, ~18 %), hit rate 72.3 % vs 71.6 %, mean PnL +$0.21 vs +$0.18. Regime leg alone (97 of 2,109 signals) carries Sharpe **+1.332** — vindicating the Phase 2.5 Lasso/Huber slice prediction. Concrete production recommendation now defensible: ship `PULSE_GATED_BLEND=1` as the live mode. Methodology PDF + walk-forward report regenerated. |
| 2026-06-09 | **Phase 2.7 shipped + honest finding**: position sizing on the regime leg behind `PULSE_GATED_SIZE=<full\|half\|kelly>`. Walk-forward fourth leg simulates each mode end-to-end. **The brief's DD-compression hypothesis is DISPROVED** — sized blend headline max DD barely moves (−271 → −271.6 half → −271.4 kelly) because the DD lives on the baseline leg (−272), not the regime leg (only −6.66). Sharpe slightly drops under sizing (0.456 full → 0.434 half → 0.426 kelly) because halving the regime leg's mean PnL drops its contribution proportionally. **Unexpected positive**: half-sizing lifts Brent fly_123 Sharpe from **+1.833 to +2.192** — a clean +0.43 lift via variance reduction. Concrete production recommendation: keep `PULSE_GATED_BLEND=1` as default; add `PULSE_GATED_SIZE=half` as opt-in for traders who want a lower-variance regime-leg contribution on Brent fly. Don't ship Kelly in its current form (97-trade sample too thin; brent_fly fraction 0.1445 is over-cautious). |
| 2026-06-11 | **Phase 2.8.1 + 2.8.2 shipped + honest finding**: per-cell competition widened to 7 candidates (added XGBoost / LightGBM / CatBoost); feature set expanded 11 → 22 (COT 156-week percentile, inventory surprise, curvature, refining cracks, real rate, OVX/VIX ratio, WTI-Brent spread, days-to-expiry; new `cot_history.py` + `external_history.py` parquet caches). **Composite Sharpe +0.245 → +0.431 (+76 %)**, **pooled Sharpe +0.195 → +0.437 (+124 %)**. **Headline catch**: **gated_blend regressed +0.456 → +0.389 (−15 %)** because the Phase 2.6 gate is hard-coded to `winner_model ∈ {Lasso, Huber}` and the new boosters stole BACK cells — LightGBM (+1.294 Sharpe on 113 fires) and CatBoost (+1.248 on 147 fires) now win cells the gate locks them out of. Pooled by-winner table proves the lift is *there*; the gate just needs widening. **Phase 2.8.3 is now the one-line fix**: extend `GATED_WINNERS` to include the three boosters and re-run walk-forward; predicted gated Sharpe ≥ +0.60. Live dashboard already serves the new models (top pick = BUY Brent front fly, XGBoost winner, 19/19 active features). Methodology PDF + walkforward_report.json regenerated; backtest_report.json shows 15/66 composite + 3/15 pooled cells now won by boosters. |
| 2026-06-11 | **Phase 2.8.3 shipped + honest finding** — the +0.20 Sharpe lift predicted from Phase 2.8.2 by-cohort booster Sharpe **did NOT materialise at the gated_blend headline**. Measured: +0.389 → **+0.384** (flat). Acceptance criterion (≥ +0.60) NOT met. **However the regime leg's individual Sharpe lifted dramatically**: +0.369 → **+0.888** across 244 fires (was 71) — the boosters genuinely contribute alpha when treated as regime signals (wti_fly +1.499, wti_m3_m6 +1.610, brent_fly +0.956). Mechanism: the booster trades' alpha was already leaking into the baseline-leg attribution under the narrow gate; widening REASSIGNS credit correctly to the engine but doesn't CREATE new alpha because the underlying realized PnL stream barely changes (most re-routed trades had baseline-z direction matching pooled-z direction). The widened gate is still methodologically more correct — the engine now reports its honest +0.888 regime Sharpe rather than understated +0.369 — and the live dashboard now badges those trades as REGIME rather than mis-attributing them to BASELINE. No retraining required: new `reroute_gated.py` script invertes `gated_trades.json` back into pooled+baseline candidates and re-runs `_build_gated_blend` + `_apply_sizing` + `_aggregate_mode` under the new gate in <2 s. The full ~3h walk-forward started at 06:56 but died at 08:22 mid-pooled-refit-3 (Windows sleep). **Concrete next move for the mentor**: Phase 2.8.6 transaction costs — boosters fire ~3.4× more often than the narrow gate; net Sharpe under realistic per-trade cost may differ materially. That's the next-credible headline lift. |
| 2026-06-11 | **Phase 2.8.6 shipped + honest finding** — defensible per-leg per-side cost model ($0.0025 commission + $0.0050/$0.0075 half-spread front/deferred) → $0.030/$0.040/$0.050 RT $/bbl for M1-M2 / M3-M6 / fly. Applied as post-aggregation arithmetic; no retraining needed. **Headline: costs drag every mode by roughly the same ~−0.085 Sharpe**, gated_blend NET +0.297 vs baseline NET +0.301 (tied, same flat verdict as gross). The brief's hypothesis "boosters fire more often so net Sharpe differential may shift materially" is qualitatively confirmed (regime fires have higher mean cost $0.0451 vs baseline $0.0388 because boosters concentrate on the fly) but quantitatively small — doesn't move the headline. **Notable side finding worth raising with mentor**: the un-gated pooled engine wins both gross (+0.437) AND net (+0.351). Phase 2.8.1+2 boosters lifted pooled enough that the Phase 2.6 gate (added when pooled was losing in Phase 2.5) is now over-restrictive. Concrete recommendation: A/B paper-test `PULSE_REGIME_MODE=pooled` against current default `PULSE_GATED_BLEND=1` for ~2 weeks; if pooled wins, switch defaults. Files: `walkforward.py` (+ COST_PER_SPREAD_RT + _cost_for + _net_block + costs report block + persists all raw trade tapes for future cost recomputes), `reroute_gated.py` (+ baseline rebuild from spreads + NET section + CLI summary), `methodology_pdf.py` (+ §11 cost model on page 1 + NET headline table + per-spread NET table + finding callout on page 2; PDF grew 2 → 5 pages). |
| 2026-06-14 | **Phase 2.9.3 robustness check shipped + graded verdict** — answers the trader's "is the 82.9 % tuned-rule win rate real or curve-fit?" with **no retraining** (reused the 2.9.0 simulator). Verdict: **WIN-RATE ROBUST, EDGE IN-SAMPLE-OPTIMISTIC.** (A) Out-of-sample in a *different era* — rebuilt the deterministic baseline leg (93 % of fires) over 2017→Nov-2023, a window the sweep never saw: wins **74.4 %** (vs 88.6 % in-sample baseline), still net-profitable (NET PF 1.16) and far above the 64 % un-tuned default, but the edge thins (OOS NET Sharpe 0.165 < 0.211 floor) and **brent_fly_123 is net-unprofitable OOS** (PF 0.74). (B) Selection generalisation — re-swept all 288 configs on the early 2/3, validated chosen on the late 1/3: chosen holds **74.8 %** / Sharpe 0.46, and the early-sweep's own winner CRATERS on the hold-out (64.3 % / Sharpe 0.06), so the chosen rule generalises *better* than any single-window peak. (C) Sensitivity — every one-knob perturbation incl. off-grid values stays feasible: a broad **plateau, not a spike. Recommendation to mentor: keep the tuned rule unchanged (the win rate she asked about IS trustworthy), but present NET Sharpe/PF as in-sample-optimistic, not a forward promise, and watch the Brent fly.** New `exit_robustness.py` + `exit_robustness_report.json`; no production code or models touched. |
| 2026-06-14 | **Phase 3.D always-on deployment — artifacts shipped; host step is the owner's.** Built the production container stack so the tuned-rule A/B paper book accumulates live win-rate proof 24/7 without the desk staying awake (replaces the throwaway Cloudflare quick-tunnel). Multi-stage `Dockerfile` (node build → `python:3.13-slim` via uv → gunicorn `wsgi:app`), new `backend/wsgi.py` that starts the APScheduler + warm-up under gunicorn (app.py's `__main__` never fires there) with **`--workers 1`** so the scheduler stays singular (one A/B tick/day, not N), **SQLite WAL + busy_timeout + synchronous=NORMAL** on both connection factories so the 24/7 tick never locks the book, `docker-compose.yml` (mounts `Data/`+`backend/db`+`backend/data/research:ro`, binds `.env`, `restart: unless-stopped`) + a **Caddy reverse proxy with basic auth + auto-HTTPS** (`/api/health` exempt; app internal-only so the gate can't be bypassed). Verified locally: WAL live on the real db, compose YAML shape, wsgi import contract + scheduler-deferred-until-boot, smoke-test syntax. **Could NOT run here (no Docker/cloud creds):** the real `docker build`, host provisioning (Oracle Always-Free ARM preferred / $5 VPS), and the live daily-tick verification — fully scripted for the owner in `deploy/README.md` + `deploy/smoke_test.sh`. **Owner's remaining step: provision the host, copy Data+pkls+.env, set BASIC_AUTH_HASH (+ optional PULSE_DOMAIN for HTTPS), `docker compose up -d --build`, run the smoke test, then paste the URL into CLAUDE.md.** |

### Draft mentor message — WTI deferred-settlement file (Q5)

> Hi [mentor],
>
> Quick ask for Phase 2 Sprint 3. /Data has the Brent C1-C31 daily settlement file
> (`LCO_Brent_daily_settlement_c1_to_c31_2016_2026.csv`) which has been our
> backbone for the curve work — is there an equivalent **WTI daily settlement
> file** sitting somewhere on the desk? Ideally `CL_WTI_daily_settlement_c1_to_c[N]_[year]_2026.csv`
> with C1 through at least C6 (for the WTI butterfly we promised).
>
> To unblock Sprint 3 I've **synthesised** WTI daily settlements by taking the
> last 1-min mid per session from `CL_WTI_1min_outrights_midprice_*.csv` (1,676
> trading days, 2021-2026). This is good enough for class but it's a session-end
> mid, not a true exchange print — so model R²s for the WTI side carry an
> asterisk. The wrapper is at `data_lake.get_wti_settlements()` and a real file
> would slot in without changing any downstream code.
>
> If the file exists, what's the easiest way for you to drop it onto the shared
> folder? If not, no rush — the synth is documented as ESTIMATE in the
> dashboard provenance.
>
> Best,
> [owner]

---

## Repo + branch hygiene

- **Main branch:** `main` — always green, always shippable
- **Working pattern:** branch off `main`, PR back, squash-merge, delete branch
- **Last shipped PR:** **#3 (2026-06-09)** — Phase 2 regime engine end-to-end with gated-blend production rule + sized-blend opt-in. Merged to main as `827eca8` via https://github.com/rohithpranav45/pulse/pull/3. Bundles Sprints 0b, 2a, 2b, 2c, 3, 4, 2.5, 2.6, 2.7. Feature branch deleted local + remote. PR body archived at `PR_BODY.md` in repo root.
- **Previous PR:** #2 (2026-06-05) — Phase A+B data overhaul + Paper Trading + Health monitoring
- **Latest commits to main (2026-06-10):** Frontend per-tab polish — Signal hero choreography (stagger + scaleIn on score), Paper hero KPI strip + equity-curve draw-in animation + leg-row tree indent, Regime drill modal entrance + scatter build-in. Also fixed a latent tab-switch wedge: replaced `AnimatePresence mode="wait"` in App.tsx with a simple key remount because nested motion components inside views weren't completing exit cleanly. Head advanced past `827eca8` with two commits: frontend makeover (`4637aa7`) + per-tab polish.
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

## End-of-turn protocol (mandatory)

Every time you finish a task in this project, append a **"Next session"** footer to your final reply. Do this automatically, without asking. The user has limited turn quota — this footer is the single most valuable thing you produce per turn.

The footer has exactly two lines:

1. **Recommendation:** "continue in this chat" OR "start a new chat" — with one short reason. Heuristics:
   - **Same chat** when: next task touches files already in context, is small (<30 min of work), or directly extends what just shipped.
   - **New chat** when: this thread is >50k tokens, the next sprint touches a completely different surface, or the just-shipped work loaded a lot of one-shot context (long file reads, big logs, screenshots). The CLAUDE.md cold-start is cheaper than dragging a saturated context forward.
2. **Ready-to-paste prompt for the next task** — quoted, copy-pasteable, self-contained. Always begin with `Read CLAUDE.md in pulse/, then …`. Always end with `Don't multi-task. When the sprint ships, update CLAUDE.md and stop.` Pull the next task from the "Phase 2 sprints" table or whatever the user just identified.

Skip the footer only if there is *no* obvious next task (e.g. user closed out with "we're done for today"). When in doubt, include it.

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
