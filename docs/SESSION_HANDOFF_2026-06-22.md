# Session handoff — 2026-06-22 (desk → laptop)

Detailed continuation context for picking this up seamlessly on another machine.
Read this **after** `CLAUDE.md` §1. TL;DR: everything below is **shipped, merged to
`main`, and pushed**. `main` HEAD = the merge commit `e6b15c4`.

---

## 1. What shipped this session (in order)

| Commit | What |
|---|---|
| `d9dd295` | **Phase 8 — per-spread gate** (backend + 2 dashboard panels) — merged to main via PR #5 (`ed3f088`) |
| `9115619` | docs: HF Space Phase 8 deployed + verified live (corrected the stale "endpoints broken" note) |
| `fda06cd` | docs: refresh `ROADMAP.md` through Phase 8 (marked 2.8.7/2.8.9/2.8.10 + Phase 8 shipped) |
| `e8e7b86` | **GARCH conditional-vol risk-layer study** (graded leg) |
| `373d01e` | **A/B panel — lead with the instant backtest verdict** |
| `e6b15c4` | merge of the above into `main` (current HEAD) |

### 1a. Phase 8 — per-spread gate (the headline feature)
Replaced the **uniform** global gate (`BACK × winners × |z|≥0.5` on every spread) with a
**per-spread enable decision** decided walk-forward: the regime leg fires for a spread only
where its OOS NET Sharpe beat the rolling-z baseline.
- **`backend/research/gate_config.py`** (new) — single source of truth (`decide_enabled`,
  `enabled_at_cutoff`, `per_spread_gate_passes`, `latest_enabled_from_report`), imported by
  **both** `walkforward` + `live_ranker` so they can't drift.
- **`walkforward.py --perspread-gate-only`** — post-processing leg; writes `per_spread_gate`
  block + `costs.per_spread_gate_net` + `gated_perspread_trades.json`.
- **`live_ranker.py`** — splits the gate into the mirrored global predicate + per-spread enable
  layer; default-on (`PULSE_PERSPREAD_GATE=0` reverts); new `gate="spread_disabled"` reason.
- **Endpoint** `GET /api/regime/perspread_gate`.
- **Dashboard (REGIME tab):** new `PerSpreadGatePanel.tsx` (verdict strip + per-spread decision
  table) + new `DecorrelatedBookPanel.tsx` (the mentor's risk-concentration directive surfaced)
  + `RegimePickCard` chips (`PER-SPREAD` + `⊘ SPREAD OFF`).
- **Verdict:** lifts the gated/regime book **+0.298 → +0.374** NET Sharpe (baseline parity
  +0.372) by enabling regime on exactly `{wti_m1_m2, wti_fly_123}`. Doesn't beat baseline, but
  makes the regime book competitive. Deployed live on HF earlier this session (Factory rebuild).

### 1b. GARCH conditional-vol — risk-layer study (research-only)
- **`backend/research/garch_vol.py`** (new) — causal one-step-ahead GARCH(1,1) + GJR-GARCH vol
  forecast (via `arch` pkg) on daily $/bbl spread changes; drop-in for `vol_target.spread_vol_frame`.
- **`walkforward.py --garch-only`** — re-runs the Phase 7 vol-target ablation under realised vs
  GARCH vol; writes `garch` block + `garch_trades.json`. `arch==8.0.0` added to requirements.
- **Verdict (two questions):** (1) as a 1-step *forecast* GARCH **loses** to trailing-20d
  (QLIKE, 3/6 spreads — spreads are low-vol, clustering edge muted). (2) as the *sizing input*
  it **materially helps** the vol-target book: NET Sharpe +0.198 → **+0.285**, Calmar 2.01 →
  **3.21**, maxDD −112 → −93 (robust across plain & GJR). **Risk-layer refinement, not alpha —
  still below baseline +0.372 / Calmar 4.99.**
- **NOT in the live path** — the live desk trades the decorrelated equal-notional gated book;
  vol-targeting (and thus GARCH) is research-only.

### 1c. A/B panel — lead with the backtest verdict
The A/B panel "looked broken / always blank" because the **live forward book can't reach a
verdict**: it times out at `MAX_DAYS=14` but a trade holds up to ~6 weeks (30 trading-day
time-stop) and needs ≥30 closed/arm — jointly unreachable; and on the sleepy free HF Space the
daily tick barely fires (keep-alive only pings `/api/health`). **Not a bug; a cadence mismatch.**
- **`ab_test.backtest_verdict()`** (new) — computes pooled-vs-gated **instantly** from the
  walk-forward tapes (NET via `walkforward._cost_for`, reusing `_welch_t`). **13,758 closed
  trades:** pooled **+0.293** vs gated **+0.298**, **Welch p=0.74 → statistically tied**;
  baseline **+0.372** is the headline. Embedded in `get_report()` → `/api/regime/ab` carries
  `backtest_verdict`.
- **`ABComparePanel.tsx`** now **leads with a Backtest-verdict block** + reframes the live book
  as "slow confirmation" with an honest **accumulating banner** (no more dashes that look dead).
- **Decision delivered:** pooled vs gated is a **tie → keep `gated` default**; baseline wins.

### Tests / build
- **114 pytest green** (added `tests/test_perspread_gate.py` 14, `tests/test_garch_vol.py` 8,
  `tests/test_ab_backtest_verdict.py` 5, +2 invariants).
- Frontend `npm run build` + `tsc` clean (only the pre-existing TS5101 `baseUrl` deprecation).
- Methodology PDF regenerated (Phase 8 + GARCH sections, → 31.3 kB).

---

## 2. Current state (verified)
- `main` (local **and** `origin`) = `e6b15c4`. Working tree clean.
- **Dashboard verified running** on the desk at http://127.0.0.1:5000 — `/api/regime/perspread_gate`
  (enabled `{wti_fly_123, wti_m1_m2}`) and `/api/regime/ab` (`backtest_verdict: tied`) both serve.
- Port 5000 reclaimed (the old zombie + a duplicate `app.py`/`start.py` were force-killed this
  session — see §4).

---

## 3. Decisions / verdicts to remember (mentor-facing)
- **Per-spread gate:** the regime book only earns its keep on the two WTI front spreads; everything
  else → baseline. Reaches baseline parity, doesn't beat it.
- **GARCH:** improves *risk management* (Calmar/DD) but not *alpha*; not promoted to live.
- **pooled vs gated:** **tied** (p=0.74) on 13.8k trades → keep `gated`. The live A/B was only ever
  going to confirm this slowly.
- **Across the whole project, baseline (regime-unaware 252d z) remains the NET-Sharpe headline.**

---

## 4. Operational notes / gotchas discovered
- **`pulse_cache.db` is a tracked live SQLite file.** A running server holds it locked → a normal
  `git merge`/`checkout`/`reset` that touches it fails on Windows ("unable to unlink … Invalid
  argument"). This session the merge was done **in git's object store** (`merge-tree --write-tree`
  → `commit-tree` → `push origin <commit>:main`) to avoid the lock. If you hit this again: either
  stop the server, or use the object-store merge, or `git update-index --skip-worktree
  backend/db/pulse_cache.db`. (Consider untracking the db long-term — it causes recurring churn.)
- **Port-5000 zombie (gotcha 4):** killed both `start.py` (PID was 24772) and `app.py` (41816) to
  free the lock + port. A reboot also reclaims it.
- **WAL corruption from force-kill + `git reset` (fixed 2026-06-22 09:56):** force-killing the server
  mid-WAL-write and then `git reset --hard` overwriting `pulse_cache.db` left a **stale `-wal`/`-shm`**
  that didn't match the reset `.db` → SQLite reported **"database disk image is malformed"** on every
  cache op → all panels went stale/down. The `.db` itself was fine (`integrity_check: ok`, 376 paper
  trades + 52 signals intact). **Fix:** stop server → back up `backend/db/` → delete the stale
  `-wal`/`-shm` → restart (SQLite rebuilds clean sidecars). Backup at
  `backend/db/_corrupt_backup_20260622_095604/`. **Lesson: never force-kill the server or `git reset`
  while `pulse_cache.db` is live; stop it gracefully first. (Strong argument to UNTRACK the db.)**
- **Desk vs laptop:** the **live feed** (`I:\Public\Summer Interns Energy\DB\`) is only visible from
  the **office desk** — the laptop/HF can't see it. `/Data` (3.5 GB) + model pkls + `.env` are all
  gitignored (CLAUDE.md §5) — the laptop needs them restored to run the dashboard or research legs.
  **Code/docs work is fully doable on the laptop; running the app/research needs /Data + models.**

---

## 5. Pending / next steps
1. **HF redeploy for the A/B verdict panel.** The Space was Factory-rebuilt earlier for Phase 8,
   but the **GARCH + A/B-backtest-verdict** commits landed *after* that. GARCH is research-only
   (no live effect), but the **A/B backtest-verdict panel is a live change** → needs another
   **Factory rebuild** (Settings → Factory rebuild) to show on https://rohithpranav45-pulse.hf.space.
2. **Live A/B harness is structurally stuck** (MAX_DAYS=14 < ~6-week hold; needs ≥30 closed/arm;
   tick barely fires on sleepy HF). We side-stepped it with the backtest verdict. If you want the
   *live forward* A/B to actually function: raise `ab_test.MAX_DAYS` (→ ~60), lower `MIN_N_CLOSED`,
   and make the keep-alive Action POST `/api/regime/ab/tick`. **Not done — your call (changes the
   experiment's statistical claim).**
3. **Owner actions (unchanged):** send the mentor WTI-daily-file + 7-sign-off messages (drafted in
   `docs/mentor_followups.md`); desk ops — pin/retrain sklearn (pkls 1.7.0 vs desk 1.9.0), retrain
   WTI on the real feed before `include_wti`.
4. **Optional:** put GARCH-sizing live as an **opt-in A/B arm** (via the existing
   `PULSE_GATED_SIZE` hook) — default off, measured forward. Only if the mandate is DD-constrained.
5. **Backlog polish (low value):** T2.7 conformal bands, T2.8 per-spread sizing override
   (see `docs/ROADMAP.md`).

---

## 6. Continuation prompt (paste into a fresh session on the laptop)

> Read `CLAUDE.md` and `docs/SESSION_HANDOFF_2026-06-22.md` in pulse/ first. I'm continuing the
> 2026-06-22 session on my laptop. Current `main` = `e6b15c4` (all merged + pushed; `git pull`
> first). Context: Phase 8 per-spread gate, the GARCH risk-layer study (research-only), and the
> A/B backtest-verdict panel all shipped this session; baseline is still the NET-Sharpe headline
> and pooled-vs-gated is a tie (keep gated). Note the laptop can't see the live feed `I:\` and may
> not have `/Data`/model pkls (CLAUDE.md §5) — so favour code/docs tasks unless I've restored those.
> What I want to do next: <PICK ONE — e.g. "trigger the HF Factory rebuild to ship the A/B verdict
> panel" · "fix the live A/B harness criteria (MAX_DAYS/keep-alive tick) so it can actually reach a
> verdict" · "wire GARCH-sizing as an opt-in PULSE_GATED_SIZE arm" · "send the mentor follow-ups">.
> Don't multi-task; do the one thing, update CLAUDE.md + docs, and stop.
