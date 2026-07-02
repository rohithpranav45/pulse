# PULSE — Roadmap & Backlog

**The *future* of the project.** Companion to `CLAUDE.md` (the *present* — current state)
and `docs/PHASE_HISTORY.md` (the *past* — how we got here). Last updated 2026-07-02
(settle-tail shipped: the regime engine's daily tape now optionally extends past the frozen lake via the
hourly OHLCV feed, `PULSE_SETTLE_TAIL=1`; prior 2026-06-22 — Phase 8 per-spread gate shipped + deployed
live; the Phase 2.8.x model backlog is closed).

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

## ✅ SHIPPED — Always-on deployment (Phase 3.E, Hugging Face Spaces, 2026-06-15; Phase 8 redeploy 2026-06-22)

**Live, free, 24/7:** https://rohithpranav45-pulse.hf.space — the A/B paper book accumulates
round-the-clock. Docker Space builds from `main` (shallow clone) + bakes the 534 MB parquet from a
private HF Dataset (`rohithpranav45/pulse-data`); `backend/hf_persist.py` syncs `pulse_cache.db`
to/from that Dataset so it survives HF's ephemeral storage; a GitHub Action pings `/api/health`
every 6h to beat the 48h idle-sleep. Build files + runbook: `deploy/hf_space/` + `deploy/HF_DEPLOY.md`.

> **2026-06-22 — Phase 8 deployed + verified live.** Factory rebuild pulled the merged `main`;
> `/api/regime/perspread_gate` → 200, `gated_blend:true` (Space var `PULSE_GATED_BLEND=1`), new panels
> render. The earlier "regime endpoints broken / joblib missing" state is fully resolved (sklearn is in
> the image). `as_of` = baked-settle by design (HF runs the parquet lake, not the desk `I:\` live feed).

> **Operate it:** push to `main` → *Factory rebuild* the Space (pulls latest code). Refresh data →
> re-run `deploy/hf_space/upload_data.py` then rebuild. Secrets live in the Space settings.

**Oracle ARM plan — shelved (capacity-blocked).** The auto-retry loop (`~/.oci/pulse_launch.py`,
Startup-folder launcher) never landed a free ARM instance after 400+ tries; HF supersedes it. The
loop can be stopped (remove the Startup-folder `.vbs`) — keep only if you still want a persistent VM
later. The Docker/Caddy artifacts (`Dockerfile`, `docker-compose.yml`, `deploy/README.md`) remain
valid for any VPS/Oracle host.

---

## ✅ SHIPPED — Settle-tail: daily settle tape extended past the frozen lake (2026-07-02)

The /Data daily settles froze 2026-05-26; `backend/research/settle_tail.py` (opt-in
`PULSE_SETTLE_TAIL=1`, default OFF = lake bit-for-bit) extends the tape the regime engine reads with the
desk hourly OHLCV feed's post-lake tail (LCO=Brent, CL=WTI; extend-only, weekend-safe, rows flagged
`ohlcv_tail (ESTIMATE)`, never persisted). Feature matrix advances 05-26 → feed latest; provenance on
`as_of_source` / `live_feed.feature_overlay` / `/api/regime/live`. Overlap-validated (Brent m1_m2 proxy
error ≈ 0.36× daily vol; WTI ≈ 0.84× vs the synth lake — flagged). Training still ends at the lake — keep
the flag OFF for training/walk-forward. Detail: `CLAUDE.md` §1. **Follow-ups:** (1) set
`PULSE_SETTLE_TAIL=1` on the desk process once you want the live engine running on the extended tape
day-to-day; (2) the real WTI daily-settlement file (T1.3 ask) would arbitrate the two WTI estimates;
(3) a session-close (21:00/22:00 UTC) cut instead of the midnight-UTC grouping would tighten the proxy —
shared with the geo `products_feed`, do it there if ever needed.

---

## 🟢 FUNCTIONALLY COMPLETE — Phase 3.1: live analysis engine + signal log (mentor directive 2026-06-15)

Mentor: "run your framework on live market data" + "add a trade/signal log to the dashboard
(timestamp, regime, instrument, rationale, confidence, subsequent performance)." Feed = per-day
SQLite 15-min bar files on `I:\Public\Summer Interns Energy\DB\` (the **live** recorder; the
`…/Siddharth Raj/lightstreamer_data/` path is the **dead** old recorder — ignore it). Backend + the
Signal Log dashboard tab shipped and verified live; remaining items are operational (L2) + WTI
enablement. Full context: CLAUDE.md §1 Phase 3.1. Since then the desk also gained the auto-trade desk
(Phase 3/4), live feature overlay, decorrelated selection, and the Phase 8 per-spread gate.

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

**L2 — Live ingestion fix + operational hardening.** ✅ **INGESTION DONE 2026-06-16** — the live engine now
runs on the **actual** `I:\` feed from this office desk. The blocker was reading the recorder's live WAL db
*in place over the SMB share* → `database disk image is malformed` (and, under the old code, an
uninterruptible thread hang). Fixed via `live_feed._open_feed_local` / `_snapshot_feed_locally` (copy
`.db` + best-effort `-wal`, never the stale `-shm`, to a local temp dir; integrity-guarded, memoised).
Verified end-to-end on live 06-16 data: BACK/LOW/STRESSED, top Brent fly BUY z −3.73 conf 0.96, 4 signals
logged + API-served; 9 invariants green. **Remaining (owner/follow-up):** (1) confirm the recorder keeps
streaming continuously (currently one ever-appended file). (2) **Reboot the desk to reclaim port 5000**
(an unkillable zombie from the old hanging code squats it; run on `PORT=5050` meanwhile). (3) Pin sklearn
or retrain — pkls are sklearn-1.7.0, desk runs 1.9.0 (`InconsistentVersionWarning`). (4) Retrain WTI on the
real feed before enabling `include_wti` (still synth-trained; `CL_*` live tables already present).

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
**T2.4 — 2.8.7: multi-horizon sweep.** `[M]` ✅ **DONE 2026-06-19** — 5/10/20/30d exit-horizon sweep
(pure post-processing over the baseline + global tapes, `--horizon-only`). Verdict: the two engines'
edges live at different horizons — baseline reverts slowly (NET Sharpe peaks at **30d**, +0.530), the
global regime model carries a faster signal (peaks ~**10d**, +0.451; front spreads at 5d). Corroborates
the live 30-day time-stop on the baseline-led book. Read the *ranking* across H (longer horizons are
overlap-inflated); doesn't overturn the headline.
**T2.5 — 2.8.9: HMM / change-point regime detection.** `[L]` ✅ **DONE 2026-06-19** — `regime_hmm.py`
(GMM + causal sticky-HMM over curve level + 5d change), `--hmm-only`. Verdict: HMM K=3 NET **+0.289**
trails baseline/global, ties hard pooled — *learning* the boundary doesn't beat the hard cuts either;
the regime **partition isn't the binding constraint**. Honest positives: relocates the contango cut
−$2 → −$0.81, and it's a front-curve win (beats baseline on brent_m1_m2 / wti_m1_m2).
**T2.6 — 2.8.10: portfolio-level vol targeting.** `[M]` ✅ **DONE 2026-06-22** — `vol_target.py`
(reuses `shock_engine.risk_scale` + decorrelation + a corr-based book overlay), `--voltarget-only`.
Verdict: **a drawdown-management tool, not alpha** — halves the gated book's max-DD −281 → −112 (~60%)
but trades away NET Sharpe +0.298 → +0.198 / Calmar 2.55 → 2.01. For a DD-constrained mandate the
overlay earns its Sharpe; for a Sharpe-max mandate the baseline wins.
**T2.10 — Phase 8: per-spread gate.** `[M]` ✅ **DONE + DEPLOYED 2026-06-22** — replaces the uniform
global gate with a per-spread enable decision made walk-forward (regime leg fires for a spread only
where its OOS NET Sharpe beat baseline; `gate_config.py` shared by live + walk-forward, `--perspread-gate-only`).
Verdict: lifts the gated/regime book **+0.298 → +0.374** (baseline parity +0.372) by enabling regime on
exactly {wti_m1_m2, wti_fly_123}; doesn't beat baseline but makes the regime book competitive. Surfaced
on the REGIME tab (Per-spread gate panel + Decorrelated book panel) + `/api/regime/perspread_gate`; live.
**T2.11 — GARCH conditional vol (risk-layer study).** `[M]` ✅ **DONE 2026-06-22** — `garch_vol.py`
(causal plain-GARCH + GJR-GARCH forecast via `arch`, drop-in for `vol_target.spread_vol_frame`),
`--garch-only`. Verdict: as a 1-step *forecast* GARCH loses to trailing-20d (QLIKE, 3/6 spreads); as the
*sizing input* to Phase 7 vol-targeting it materially helps (Calmar 2.01 → 3.21, Sharpe +0.198 → +0.285,
maxDD −112 → −93, robust across specs) — a **risk-layer refinement, not alpha**; still below baseline.
Research-only dep; live path unchanged.

> **Phase 2.8.x model backlog is now COMPLETE.** Splitting (2.8.4), softening (2.8.5), long history (2.8.8),
> multi-horizon (2.8.7), data-driven regimes (2.8.9), vol-targeting (2.8.10), and per-spread gating (Phase 8)
> all shipped. **Baseline +0.372 remains the NET-Sharpe headline across every variant**; the per-spread-gated
> regime book now matches it. The conventional model knobs are tapped out — the remaining T2.7/T2.8 below are
> polish, and the live A/B verdict (T1.2) is the only thing that could promote the regime book over baseline.

**T2.7 — conformal prediction bands.** `[M]` — calibrated prediction intervals (deferred when 2.8.3 took its slot). *Polish — low priority now baseline is the headline.*
**T2.8 — per-spread sizing override.** `[S]` — config map to half-size only `brent_fly_123` (the Phase-2.7 win) without sizing the rest. *Polish.*
**T2.9 — 2.8.11: end-of-phase methodology PDF + CLAUDE.md refresh.** `[S]` ✅ **effectively DONE** — the PDF is regenerated each leg (now 29.5 kB through Phase 8) and CLAUDE.md §1 is kept current per sprint.
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
| **Done** | ~~deploy~~ ✅ (HF, + Phase 8 redeploy) · ~~T1.1 invariants~~ ✅ · ~~T2.1 extended walk-forward~~ ✅ · ~~T2.2 global~~ ✅ · ~~T2.3 soft~~ ✅ · ~~T2.4 multi-horizon~~ ✅ · ~~T2.5 HMM~~ ✅ · ~~T2.6 vol-target~~ ✅ · ~~Phase 8 per-spread gate~~ ✅ |
| **Owner actions (you)** | T1.3 send mentor asks (WTI daily file + 7 sign-offs, drafted in `mentor_followups.md`) · desk ops: reboot for port 5000, pin/retrain sklearn, retrain WTI on real feed before `include_wti` |
| **Self-accumulating** | T1.2 read the A/B verdict once ≥30 closed trades/arm — the only thing that could promote the regime book over baseline as the production default |
| **Optional polish** | T2.7 conformal bands · T2.8 per-spread sizing override (low value now baseline is the headline) |
| **Only if needed** | Tier 3 hardening (real always-on usage) · Tier 4 opportunistically while in the code |

---

*Maintained alongside CLAUDE.md. If you finish or add a task, edit this file in the same session so it stays the single source of truth for "what's next."*
