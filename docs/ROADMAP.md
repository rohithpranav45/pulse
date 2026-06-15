# PULSE — Roadmap & Backlog

**The *future* of the project.** Companion to `CLAUDE.md` (the *present* — current state)
and `docs/PHASE_HISTORY.md` (the *past* — how we got here). Last updated 2026-06-15
(T2.3 Phase 2.8.5 soft regime probabilities shipped).

This file exists so nothing slips through the cracks again. It captures **every** task
we planned, deferred, or owe someone — with a timeline and a copy-paste prompt per task.

---

## How to use this file
- Each task has a **▶ Prompt** — paste it into a fresh Claude Code session to start that task.
- Tiers run top-down: do **Tier 1** before Tier 2, etc. Within a tier, higher = better value/effort.
- **Effort:** `S` ≈ under a session · `M` ≈ one session · `L` ≈ multi-session.
- **When a task ships:** check it off here, move the detail to `PHASE_HISTORY.md`, update `CLAUDE.md` §1.

## Rules for opening a new session
1. **One sprint per session.** Read `CLAUDE.md` end-to-end, do the *one* task, update the docs, stop.
2. **Paste the task's ▶ Prompt** from this file — they're self-contained.
3. **My preferences** (also saved in memory, so any session knows them):
   - **Ask me** before doing anything only I can do — accounts, money, cards, API keys, irreversible deletes. Never silently hand it off.
   - **Explain ops/infra step-by-step** — I'm not a DevOps/cloud expert; assume little, walk me through it.
   - **Keep everything clean and structured.** No paid tools, no credit card.
4. **Don't break the invariants** (`CLAUDE.md` §5, gotchas 7–9: gate mirror, tuned-rule mirror, A/B cost mirror) and **don't fold the exit rule into the walk-forward** (separate layers).
5. **End every session** with the footer: *continue-here vs new-chat* + a ready-to-paste next prompt.

---

## ✅ SHIPPED — Always-on deployment (Phase 3.E, Hugging Face Spaces, 2026-06-15)

**Live, free, 24/7:** https://rohithpranav45-pulse.hf.space — the A/B paper book accumulates
round-the-clock. Docker Space builds from `main` (shallow clone) + bakes the 534 MB parquet from a
private HF Dataset (`rohithpranav45/pulse-data`); `backend/hf_persist.py` syncs `pulse_cache.db`
to/from that Dataset so it survives HF's ephemeral storage; a GitHub Action pings `/api/health`
every 6h to beat the 48h idle-sleep. Build files + runbook: `deploy/hf_space/` + `deploy/HF_DEPLOY.md`.

> **Operate it:** push to `main` → *Factory rebuild* the Space (pulls latest code). Refresh data →
> re-run `deploy/hf_space/upload_data.py` then rebuild. Secrets live in the Space settings.

**Oracle ARM plan — shelved (capacity-blocked).** The auto-retry loop (`~/.oci/pulse_launch.py`,
Startup-folder launcher) never landed a free ARM instance after 400+ tries; HF supersedes it. The
loop can be stopped (remove the Startup-folder `.vbs`) — keep only if you still want a persistent VM
later. The Docker/Caddy artifacts (`Dockerfile`, `docker-compose.yml`, `deploy/README.md`) remain
valid for any VPS/Oracle host.

---

## 🔴 ACTIVE NOW — Phase 3.1: live analysis engine + signal log (mentor directive 2026-06-15)

Mentor: "run your framework on live market data" + "add a trade/signal log to the dashboard
(timestamp, regime, instrument, rationale, confidence, subsequent performance)." Feed = per-day
SQLite 15-min bar files on `I:\Public\Siddharth Raj\lightstreamer_data\`. Full context: memory
`pulse-live-feed` + CLAUDE.md §1 Phase 3.1.

**✅ Backend shipped + verified (2026-06-15):** `research/live_feed.py` (real spreads + curve from the
share), `research/live_engine.py` (overlays live snapshot onto the ranker; additive
`live_actuals`/`live_curve_m1m12` kwargs leave the daily/A-B paths bit-for-bit unchanged),
`research/signal_log.py` (`signal_log` table + subsequent-performance MTM). API `/api/regime/live`,
`/api/regime/signals`, `POST /api/regime/signals/generate`; scheduler daily + 15-min jobs (gated by
`PULSE_LIVE_SIGNALS_DISABLED`). 9 invariants green; daily path unaffected.

**L1 — Dashboard Signal Log panel.** `[M]` ✅ **DONE 2026-06-15**
`views/SignalLogView.tsx` + `components/panels/SignalLogPanel.tsx` (sidebar key 9, `ScrollText` icon).
Columns: timestamp · instrument · dir · regime · confidence · entry→fair(z) · subsequent perf; ALL/OPEN/
CLOSED filter + GENERATE button. API methods `regimeSignals` / `regimeLive` / `regimeSignalsGenerate`.
`npm run build` clean; browser-verified (2 live Brent signals render, GENERATE round-trips, no console
errors). **Phase 3.1 functionally complete** — remaining items are operational (L2) + WTI enablement.

**L2 — Confirm with mentor + operational hardening.** `[S · owner action]` (1) The recorder is currently
**intermittent** (share file frozen 06-12 11:06) — confirm it'll stream continuously. (2) The Oracle box
can't see `I:\` → decide: run live engine on an office PC, or sync the feed to the cloud. (3) Retrain WTI
on the real feed before enabling `include_wti` (models are synth-trained).

---

## 🟡 TIER 1 — Next sessions (high value, mostly small)

**T1.1 — Phase 3.0: invariants test.** `[S]` ✅ **DONE 2026-06-14**
`tests/test_invariants.py` (pytest, **9 tests green**) asserts the gate mirror (`live_ranker` ↔
`walkforward`), the tuned exit-rule mirror (`live_ranker.TUNED_MAX_HOLD_DAYS` ==
`paper_trading.TUNED_MAX_HOLD_TRADING_DAYS` + TP/SL/excluded-spreads), and the A/B cost table
(`ab_test` ↔ `walkforward`). `pytest==9.1.0` pinned. Run: `python -m pytest tests/ -v`.

**T1.2 — Read the A/B verdict, decide the production mode.** `[S · time-gated: needs ≥30 closed trades/arm OR ~14 days of accumulation]`
Once the book has data, read `/api/regime/ab`. If `pooled_wins` → write the one-line production-default
flip PR (`PULSE_REGIME_MODE=pooled`). If `gated_wins`/`undecided` → keep the gated default. Then regenerate
the methodology PDF with the winning arm.
> ▶ **Prompt:** `Read CLAUDE.md in pulse/, then read the A/B verdict at /api/regime/ab (start the app first if needed). If a winner is declared (>=30 closed/arm AND p<0.05), make the production-mode decision: if pooled wins, flip the default and write a short PR; if gated/undecided, keep the gated default and say why. Regenerate the methodology PDF for the winning arm. Don't multi-task; update CLAUDE.md + docs/ROADMAP.md and stop.`

**T1.3 — Mentor: send the WTI ask + chase the 7 sign-offs.** `[S · owner action]` ✏️ **DRAFTED — ready to send**
Both messages are written and ready in **[`docs/mentor_followups.md`](mentor_followups.md)**: (1) the
real WTI *daily settlement* file request (the synth is ESTIMATE, capping WTI history at 2021+), and
(2) a Phase-2 status + sign-off chase on the 7 alignment questions (instrument scope, regime axes,
horizon, auto-push, Phase-1 coexistence). **Your move:** review, send, then log it in
`PHASE_HISTORY.md`'s mentor communication log.

---

## 🟢 TIER 2 — Model work (Phase 2.8.x backlog)

> Acceptance for Phase 2.8 overall: gated_blend NET Sharpe ≥ +0.65 over a full 2018–2026 walk-forward.
> **2026-06-15 update (T2.1 done):** full 34-refit 2018–2026 run came back at gated NET `+0.298` —
> bar missed by ~2×. Worse, the regime-unaware **baseline +0.372 beats every regime variant** on long
> history (pooled +0.293 · sized_half +0.282 · sized_kelly +0.281). Per-spread: baseline wins 4/6
> outright. So 2.8.4/2.8.5/2.8.9 below are now the *credible* routes to lift the headline — the
> conventional gate/sizing knobs are tapped out. Live A/B (T1.2) is still the right arbiter for the
> live production default; do not flip to baseline-led production from this verdict alone.
>
> **2026-06-15 update (T2.2 done):** Phase 2.8.4 global model with regime-as-feature came back at
> NET `+0.380` — ties baseline (`+0.372`), beats every per-cell variant by `+0.08-0.09`. The per-cell
> *split* WAS the binding constraint vs the regime *information* — collapsing the grid recovers what
> fragmentation cost — but on this 6-spread universe regime info alone doesn't lift the headline
> above baseline. Bar still missed by ~2×. Next credible routes now narrow to **2.8.5 soft
> probabilities** (does the hard 3-bucket curve threshold leak info?) and **2.8.9 HMM/change-point**
> (are the trader thresholds even the right regimes?).
>
> **2026-06-15 update (T2.3 done):** Phase 2.8.5 soft regime probabilities came back at
> NET `+0.297` — **ties hard pooled** (`+0.293`, Δ +0.004), still trails baseline (`+0.372`) and
> global (`+0.380`). New `backend/research/softprob.py` replaces the indicator-function classifier
> with per-axis logistic transitions (bandwidth $1/bbl curve & inventory, 2.5pp vol), and
> evaluates each day's prediction as the posterior-weighted blend across all pooled cells trained
> at that refit. Mean modal posterior weight 0.86 over ~2.5 cells blended per fire — softening
> *did* kick in, but the blend landed where the dominant cell already was. **The discontinuity at
> the trader thresholds was not the binding constraint.** With both *splitting* (2.8.4) and
> *softening* (2.8.5) ruled out as headline lifts, the credible remaining routes are now
> **2.8.9 HMM/change-point regimes** (the trader thresholds themselves may be wrong), **2.8.7
> multi-horizon sweep** (the 20-day horizon may not be optimal per spread), and **2.8.10
> portfolio vol-targeting** (a sizing-layer lift on top of any of the above). Composite-soft is
> available behind `--soft-only --composite` but is unlikely to flip the verdict — the flat-prior
> composite limit ≈ global, and 2.8.4 global already gave us that answer.

**T2.1 — 2.8.8: extend the walk-forward to 2018–2026.** `[L]` ✅ **DONE 2026-06-15**
34 quarterly refits 2018-Q1 → 2026-Q2. `composite_trades.json` now persisted (8,421 rows);
`pooled_trades.json` 10,416 rows; `baseline_trades.json` 9,906 rows. NET-Sharpe verdict above.
2018-2020 reads as a Brent-only story (WTI synth starts 2021; pre-2021 WTI cells auto-skip per
`MIN_SAMPLES`). Bug fix shipped same sprint: `walkforward._by_curve_axis` now tolerates `regime=None`
on gated baseline-fallback rows (latent crash, never triggered in the old 2024+ window).
Methodology PDF regenerated (`backend/data/research/PULSE_methodology.pdf`).

**T2.2 — 2.8.4: one global model with regime-as-feature.** `[M]` ✅ **DONE 2026-06-15**
ONE model per spread on all rows + composite regime as 9 one-hot axis columns (curve/inv/vol).
Same 7-model competition; 34 refits 2018-2026; same NET cost model. **Verdict: NET Sharpe +0.380**
(vs baseline `+0.372` / gated `+0.298` / pooled `+0.293`) — ties baseline, beats every per-cell
variant by `+0.08-0.09`. Per-spread NET: baseline 3 / global 2 / 1 tied. Honest read — the per-cell
*split* was the binding constraint, but on this universe regime information itself isn't lifting the
headline; Phase 2.8 acceptance bar (`+0.65`) still unmet. Raw tape persisted to `global_trades.json`
(10,587 rows); re-run alone via `python -m backend.research.walkforward --global-only`.
**T2.3 — 2.8.5: soft regime probabilities.** `[M]` ✅ **DONE 2026-06-15**
New `backend/research/softprob.py` replaces hard axis indicators with logistic membership functions
(bandwidth $1/bbl on curve & inventory, 2.5pp on vol). `walkforward._evaluate_window_soft` blends
each day's prediction across all trained cells weighted by the posterior; `run_soft_only` retrains
pooled cells, evaluates the soft leg, and merges into `walkforward_report.json` (~6 min).
**Verdict: pooled_soft NET Sharpe +0.297** (vs baseline `+0.372` / global `+0.380` / gated `+0.298` /
hard pooled `+0.293`) — ties hard pooled within noise. Mean modal posterior weight 0.86 / ~2.5 cells
blended per fire — softening kicked in but didn't move the headline. Per-spread soft pooled tracks
hard pooled almost exactly; baseline still wins 4/6. Phase 2.8 acceptance bar (`+0.65`) still unmet.
Raw tape `pooled_soft_trades.json` (10,587 rows). Composite-soft available via
`python -m backend.research.walkforward --soft-only --composite` but not run this sprint —
the pooled finding makes a flip unlikely (flat-prior composite ≈ global ≈ baseline).
**T2.4 — 2.8.7: multi-horizon sweep.** `[M]` — evaluate 5/20/60-day horizons, pick the best per spread (`FORWARD_DAYS`).
**T2.5 — 2.8.9: HMM / change-point regime detection.** `[L]` — data-driven regimes vs the hand-set thresholds.
**T2.6 — 2.8.10: portfolio-level vol targeting.** `[M]` — size the blended book to a vol target (addresses the baseline-dominated max-DD, gotcha 30).
**T2.7 — conformal prediction bands.** `[M]` — calibrated prediction intervals (deferred when 2.8.3 took its slot).
**T2.8 — per-spread sizing override.** `[S]` — config map to half-size only `brent_fly_123` (the Phase-2.7 win) without sizing the rest.
**T2.9 — 2.8.11: end-of-phase methodology PDF + CLAUDE.md refresh.** `[S]` — do once Phase 2.8 closes.
> ▶ **Generic Tier-2 prompt:** `Read CLAUDE.md in pulse/, then do [TASK ID + name] from docs/ROADMAP.md Tier 2. Reuse the existing research/ harness; report the honest verdict vs baseline; regenerate the methodology PDF. Don't multi-task; update CLAUDE.md + docs/ROADMAP.md and stop.`

---

## 🔵 TIER 3 — Production hardening (Phase 3, only once Phase 2 + deploy are stable)

From the tech-debt register — deliberately batched for *after* real data is flowing, so each upgrade is
justified by measurement, not guesswork. Most are **only worth doing if a real always-on user appears.**

| Item | Effort | Note |
|---|---|---|
| FastAPI migration (Flask → FastAPI) | L | enables async + auto OpenAPI; risk to the 30+ streams |
| Async fetchers (`httpx.AsyncClient`) | M | latency win on slow I/O |
| Postgres + TimescaleDB | L | only when SQLite scale hurts |
| Redis cache + dependency invalidation | M | auto-bust (prices → fair value) |
| WebSocket push (replace polling) | M | UX; not blocking |
| Better Stack uptime monitor + log dashboards | S | pairs with the live deploy (Sentry/Better Stack already wired) |
| ~~Docker + HTTPS deploy~~ | — | ✅ done in Phase 3.D (host step pending — see D1) |
| ~~Named Cloudflare tunnel + Access~~ | — | likely **obsolete** now we have Oracle + Caddy; drop unless needed |

> ▶ **Prompt:** `Read CLAUDE.md in pulse/, then do [Tier-3 item] from docs/ROADMAP.md — but first measure the current behaviour so the upgrade is justified empirically. Keep the 30+ data streams working. Don't multi-task; update the docs and stop.`

---

## ⚪ TIER 4 — Opportunistic / cleanup (do when touching adjacent code)

- **Real test coverage** — `tests/` is empty (just `__init__.py`). Add pytest + vcrpy as you touch code; start with T1.1.
- **Migrate legacy fetchers to DuckDB** — `realised_vol._load_1min_close_series` still reads CSV directly; move to `data_lake.load_1min_tail` / `duckdb_conn` (Sprint-1 leftover).
- **Frontend: TanStack Query** (replace homegrown `usePolling`) · **Zustand** (cross-tab state) · **unify charting** (5 libs → 1).
- **MLflow** model tracking for the per-regime experiments.
- **`.git` is ~868 MB** (big blobs in history). Shrinking needs a history rewrite (BFG/filter-repo) that changes every commit hash and can break the GitHub remote — **only do this deliberately, with a backup first.**

---

## Suggested timeline (relative — adjust to mentor cadence + when the server lands)

| When | Focus |
|---|---|
| **This week** | D1 finish deploy *(when capacity lands)* · ~~T1.1 invariants test~~ ✅ · T1.3 send mentor asks · ~~T2.1 extended walk-forward~~ ✅ |
| **+1–2 weeks** | T1.2 read the A/B verdict → production-mode decision · start T2.5 (HMM/change-point) — with both T2.2 (split) and T2.3 (soften) ruled out as headline lifts, T2.5 is the credible remaining regime route |
| **Internship tail** | Tier 2 model lifts as time allows (T2.3–T2.8) · T2.9 close out Phase 2.8 |
| **Only if needed** | Tier 3 hardening (real always-on usage) · Tier 4 opportunistically while in the code |

---

*Maintained alongside CLAUDE.md. If you finish or add a task, edit this file in the same session so it stays the single source of truth for "what's next."*
