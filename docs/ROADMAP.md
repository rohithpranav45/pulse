# PULSE — Roadmap & Backlog

**The *future* of the project.** Companion to `CLAUDE.md` (the *present* — current state)
and `docs/PHASE_HISTORY.md` (the *past* — how we got here). Last updated 2026-06-14.

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

## 🔴 ACTIVE NOW — Always-on deployment (waiting on Oracle capacity)

The auto-retry loop is running on this PC (`~/.oci/pulse_launch.py`, hidden Startup-folder
launcher, 90s loop). It will grab the free Oracle ARM server the moment capacity frees up and
write `~/.oci/pulse_instance.txt`. Full context: memory `pulse-deployment-pending` + `deploy/README.md`.

**D1 — Finish the deployment when the server lands.** `[M · blocked on Oracle capacity]`
SSH in → open 80/443 (VCN security list + host iptables) → copy `Data/` + model pkls + `.env` up →
`docker compose up -d --build` → set `BASIC_AUTH_HASH` + `PULSE_UID` → run `deploy/smoke_test.sh` →
paste the live URL into `CLAUDE.md` §1.
> ▶ **Prompt:** `Read CLAUDE.md in pulse/, then check Oracle: if ~/.oci/pulse_instance.txt exists, finish the PULSE deployment per deploy/README.md — SSH in with ~/.ssh/oracle_pulse (user 'ubuntu'), open ports 80/443, copy Data + model pkls + .env to the server, docker compose up -d --build, set BASIC_AUTH_HASH + PULSE_UID, run deploy/smoke_test.sh, then paste the live URL into CLAUDE.md §1 and docs/ROADMAP.md. Ask me for anything only I can do. Don't multi-task; update the docs and stop.`

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

**T1.3 — Mentor: send the WTI ask + chase the 7 sign-offs.** `[S · external/owner action]`
A draft message asking for the real WTI C1-C3 *daily settlement* file is in `PHASE_HISTORY.md`
("Draft mentor message"). Also still pending her sign-off: the 7 alignment questions (instrument scope,
regime axes, time horizon, auto-push behaviour, Phase-1 coexistence). This is an owner action — I can
prep/send drafts, you relay.
> ▶ **Prompt:** `Read CLAUDE.md in pulse/ (and the "Draft mentor message" + "Pending decisions" in docs/PHASE_HISTORY.md), then help me finalize and send the mentor the WTI daily-settlement-file request and a chase on the 7 alignment-question sign-offs. Draft them cleanly; ask me anything you need. Don't multi-task; update the docs and stop.`

---

## 🟢 TIER 2 — Model work (Phase 2.8.x backlog)

> Acceptance for Phase 2.8 overall: gated_blend NET Sharpe ≥ +0.65 over a full 2018–2026 walk-forward
> (currently ~+0.30 NET). The honest finding so far: the gate widening (2.8.3) and costs (2.8.6) didn't
> lift the headline; the credible alternative is un-gated **pooled** (NET +0.35) — which T1.2's A/B test
> is validating. Do these only if the desk wants more model lift.

**T2.1 — 2.8.8: extend the walk-forward to 2018–2026.** `[L]` *(do first — unblocks the others)*
Biggest remaining structural change (adds 2018–2020 contango coverage). A fresh full run also persists
`composite_trades.json` → unlocks full Phase-2.8.6 NET coverage for composite mode.
> ▶ **Prompt:** `Read CLAUDE.md in pulse/, then do Phase 2.8.8 — extend the walk-forward window back to 2018 (prepend dates to REFIT_DATES in walkforward.py), re-run it (python -u, ~3h+), and report whether 2018-2020 contango changes the verdict. Confirm composite_trades.json gets persisted. Regenerate the methodology PDF. Don't multi-task; update CLAUDE.md + docs/ROADMAP.md and stop.`

**T2.2 — 2.8.4: one global model with regime-as-feature.** `[M]` — collapse the per-cell grid; feed regime label as a feature instead of splitting the data.
**T2.3 — 2.8.5: soft regime probabilities.** `[M]` — replace hard regime thresholds with probabilities; blend predictions.
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
| **This week** | D1 finish deploy *(when capacity lands)* · T1.1 invariants test · T1.3 send mentor asks |
| **+1–2 weeks** | T1.2 read the A/B verdict → production-mode decision · start T2.1 (2.8.8 extended walk-forward) |
| **Internship tail** | Tier 2 model lifts as time allows (T2.2–T2.8) · T2.9 close out Phase 2.8 |
| **Only if needed** | Tier 3 hardening (real always-on usage) · Tier 4 opportunistically while in the code |

---

*Maintained alongside CLAUDE.md. If you finish or add a task, edit this file in the same session so it stays the single source of truth for "what's next."*
