# DASHBOARD REBUILD — Phase 4

> **Goal:** Collapse the current 9-tab dashboard into a focused **6-tab** layout
> that answers "what should I trade right now → what am I holding → what's the
> evidence" in three clicks, not nine. Keep the Charts tab as-is per user
> preference. Local-only first; HF deploy untouched until the rebuild is
> verified and the mentor's verdict on the strategy direction is in.
>
> **Last updated:** 2026-06-16 (planning sprint, no code yet).
> **Owner:** Rohith.
> **Status:** Plan locked, Phase 4.A ready to start in a fresh session.

---

## 0. Why this rebuild

Current dashboard problems (from the 2026-06-16 internal audit):

1. **9 tabs is too many** for a single-user desk tool. Three of them (Signal,
   Intelligence, Fundamentals) are decorative — they look impressive in a
   screenshot but nobody opens them after the first demo.
2. **No landing view** that answers "what would I trade right now." The Regime
   pick lives in tab 8; Paper Trading is in tab 7; risk lives nowhere.
3. **Three tabs (Regime, Paper, Signal Log) are three views of the same
   workflow** — opportunity → decision → tracked. The user mentally stitches
   them together every time.
4. **Signal Log floods with duplicates** in deep contango/backwardation regimes
   (one row per 15-min bar per persistent opportunity). Discussed in conversation
   on 2026-06-16; fix is in Phase 4.G below.

---

## 1. Target tab structure (6 tabs, Charts kept)

| # | Tab          | Hotkey | Role                                                                                             |
|---|--------------|--------|--------------------------------------------------------------------------------------------------|
| 1 | **DESK**     | `1`    | Landing. Current regime pick + open positions + risk + today's morning brief + price decomp.    |
| 2 | **CHARTS**   | `2`    | Brent / WTI / NG candlesticks. **Untouched** per user preference.                                |
| 3 | **REGIME**   | `3`    | Regime engine deep-dive: pick card, drill modal, walkforward report, methodology PDF, A/B panel, pattern analogs. |
| 4 | **PAPER**    | `4`    | Full paper book: open positions, closed history, equity curve, performance stats, manual entry. |
| 5 | **SIGNAL LOG** | `5`  | Live signal feed (after dedup fix — one row per opportunity, not per bar).                      |
| 6 | **MARKETS**  | `6`    | Spreads, curve shape, inventories, COT, cracks, macro (all collapsed by default).                |

### Removed from sidebar
- Old **Signal** tab — useful bits (`PriceDecomposition`, `IndicatorDrillDown`) move into DESK.
- Old **Intelligence** tab — entirely cut. Groq morning brief moves into DESK as a sidebar widget.
- Old **Fundamentals** tab — content moves into MARKETS as collapsed sections.
- Old **Playbook** tab — pattern analogs move into REGIME drill modal.
- Old **Spreads & Curve** tab — folds into MARKETS.

---

## 2. Implementation phases (one per session)

Each phase is **independently shippable**, **doesn't break the previous build**,
and produces a single PR-sized commit. Order is dependency-first: build the new
landing before cutting the old tabs.

### Phase 4.A — Build the DESK landing view
**Scope:** New file `frontend/src/views/DeskView.tsx`. Add as the *first* sidebar
entry; old tabs remain untouched. New view contains:
- **Hero card:** today's regime pick from `/api/regime/recommendation` (live, gated). One sentence: "Trade X, LONG/SHORT, z=Y, conf=Z%."
- **Open positions strip:** compact 1-row-per-trade view from `/api/paper/positions` with live MTM.
- **Risk panel** (new): sum-of-stops if all open positions hit, gross exposure by leg, correlation matrix of open trades.
- **Morning brief card:** Groq brief from `/api/intelligence/brief` (relocated from old Intelligence tab).
- **Price decomposition strip:** `PriceDecomposition` panel (relocated from Signal tab).

**Acceptance:**
- DESK loads in <500ms with skeleton states.
- Risk panel renders even with zero open positions ("no exposure" empty state).
- Rebuilt frontend (`cd frontend && npm run build`) serves at http://127.0.0.1:5000.
- Old tabs still work — additive change.

**Files touched:** `Sidebar.tsx` (add DESK as first item), new `DeskView.tsx`,
small new component `RiskPanel.tsx`, `App.tsx` (router add).

---

### Phase 4.B — Move panels off the Signal tab
**Scope:** `PriceDecomposition`, `IndicatorDrillDown`, `GeoRiskCalculator` —
relocate from `views/SignalView.tsx` into `DeskView.tsx` as supporting panels.
Then delete `SignalView.tsx` and its sidebar entry.

**Acceptance:**
- All three panels render inside DESK.
- No 404s when clicking old `#/signal` URLs (router redirects to `#/desk`).
- Signal tab no longer in sidebar.

---

### Phase 4.C — Build MARKETS, fold in Fundamentals + Spreads
**Scope:** New `MarketsView.tsx`. Sections (each in a collapsible `<details>` block):
- **Spreads & Curve** (default open) — current `SpreadsView` content.
- **Inventories** (collapsed) — EIA crude stocks, distillates, gasoline; surprise vs 5yr avg.
- **COT positioning** (collapsed) — managed money net pct, 156w percentile.
- **Cracks** (collapsed) — 3-2-1, gasoline, distillate.
- **Macro** (collapsed) — DXY, DGS10, real rate, OVX/VIX.
- Delete `views/SpreadsView.tsx`, `views/FundamentalsView.tsx`.

**Acceptance:**
- Single MARKETS tab replaces two old tabs.
- Collapsed sections lazy-load (don't fetch until expanded — saves polling cost).
- All old endpoints still wired correctly.

---

### Phase 4.D — Fold Playbook into Regime
**Scope:** Pattern analogs move into the existing `RegimeDrillModal` as a new
"Historical analogs" section. The Playbook tab is removed from the sidebar.

**Acceptance:**
- Clicking a regime pick → drill modal → analogs section shows "the last N times
  this regime + this z fired."
- Playbook tab gone from sidebar; `views/PlaybookView.tsx` deleted.

---

### Phase 4.E — Cut Intelligence tab entirely
**Scope:**
- Groq brief → already moved to DESK in 4.A.
- Correlations, news, geo-risk: deleted (none are model inputs).
- Delete `views/IntelligenceView.tsx`, related panels.

**Acceptance:**
- Sidebar now has exactly 6 tabs.
- Nothing 500s or 404s.
- Bundle size measurably smaller (delete tracked).

---

### Phase 4.F — Polish layer (global, post-restructure)
**Scope (low-risk, additive):**
- **Global hotkeys** — `Cmd/Ctrl+1..6` for tab switch, `/` for search (later),
  `?` for help overlay. Wire in `App.tsx` via a single `useEffect`.
- **Empty states** — every panel gets an explicit "no data because X" card,
  not an infinite skeleton.
- **Error chips** — Panel header shows last-success timestamp + an error pill
  if the most recent fetch failed.
- **Dark/light persistence** — confirm `localStorage` + `prefers-color-scheme`
  both work.
- **Disable animations on poll refresh** — only animate on tab change.

**Acceptance:**
- Hotkeys work, including in inputs (Cmd+1 still navigates).
- Every panel shows a sensible state when its endpoint returns 0 rows.
- Stale-fetch indicator visible without opening dev tools.

---

### Phase 4.G — Signal Log dedup fix
**Scope:** Change `signal_log` UNIQUE constraint from
`(instrument, direction, feed_as_of, cadence)` to
`(instrument, direction, opened_at_session)` so the same opportunity logs once
per "session" (defined as: until the previous one closes via TP/SL/time-stop or
direction flips). The MTM columns (`mtm_value`, `mtm_move`) keep the per-bar
evolution.

**Backend changes:**
- `signal_log.py` — new dedup logic. Migration: keep existing rows but mark them
  with a synthetic `opened_at_session` derived from `signal_at`.
- New column or computed grouping for "active sessions per instrument."

**Frontend changes:**
- `SignalLogPanel.tsx` — one row per session, with the latest MTM in the
  subsequent-perf column. Closed sessions get the close reason chip.

**Acceptance:**
- Same opportunity persisting across 26 bars = 1 row, not 26.
- Closed-then-reopened on the same instrument = 2 rows.
- 4.A through 4.F unaffected (this is a self-contained refactor).

---

### Phase 4.H — Calibration plot (bonus, if time permits)
**Scope:** New panel in REGIME tab — a calibration chart that bins historical
z-scores (from `gated_trades.json` etc.) and plots "fraction of trades that
mean-reverted within 20 days." This is the single most-trusted plot a trader
wants. Data is already there; just needs the bin + plot.

**Acceptance:**
- Chart renders on Regime tab.
- Title says exactly: "When the model said z=X, the spread reverted Y% of the
  time in 20 days (n trades)."

---

## 3. Out of scope (deliberately)

These were called out in the audit but are NOT part of Phase 4. They go in a
separate Phase 5 / 6 once the mentor decides on the strategy direction:

- **Architecture changes** (FastAPI, Celery, Postgres, MLflow) — user
  explicitly deferred. Risky during demo prep.
- **Strategy/model changes** (HMM regimes, multi-horizon, real WTI retrain,
  baseline-led pivot) — awaiting mentor's verdict.
- **HF Spaces redeploy** — user wants HF frozen as backup until presentation.
  Rebuild ships local-only.

---

## 4. Risk register

| Risk | Mitigation |
|---|---|
| Demo today (2026-06-16). Rebuild not done. | Phase 4.A onwards starts *after* presentation. HF stays as backup. |
| Cutting tabs breaks bookmarks / mentor URLs | Old tabs redirect to nearest equivalent (4.B/E note). |
| Risk panel needs correlation data we may not have for paper book legs | Use the 30d rolling Pearson from `correlations_calc` already in the codebase. |
| Dedup fix (4.G) backfills wrong sessions | Run on a backup of `pulse_cache.db` first; verify with `pytest tests/test_invariants.py` (still green). |
| Frontend bundle gets bigger from new DESK view | Run `npm run build` and check chunk size; lazy-load REGIME and MARKETS if needed. |

---

## 5. Acceptance for Phase 4 overall

When all of 4.A → 4.G are shipped, you should be able to:

1. Open http://127.0.0.1:5000 → land on DESK → see today's pick + open book + risk in one glance.
2. Hit `Cmd/Ctrl+1..6` to navigate without the mouse.
3. See the Signal Log as a clean opportunity-per-session table, not a per-bar flood.
4. Show your mentor the 6-tab dashboard and explain each in one sentence.

The HF deploy gets touched **only after** mentor verdict on strategy direction
is in AND Phase 4 is verified locally for ≥48h with no regressions.

---

## 6. Session-by-session execution

| Session | Phase | Estimated context budget |
|---|---|---|
| 1 | 4.A — DESK skeleton + risk panel | Medium (new files, ~400 LOC) |
| 2 | 4.B — Move Signal panels, delete tab | Small |
| 3 | 4.C — MARKETS + collapsed Fundamentals | Medium |
| 4 | 4.D — Playbook → Regime drill | Small |
| 5 | 4.E — Cut Intelligence | Small |
| 6 | 4.F — Polish (hotkeys, empty states, errors) | Medium |
| 7 | 4.G — Signal Log dedup fix | Medium (backend + frontend) |
| 8 | 4.H — Calibration plot (optional) | Small |

**One phase per session.** Don't multitask. Update §1 of CLAUDE.md after each.

---

## 7. Files inventory (current, pre-rebuild)

For reference when planning each session:

**Views (9 files, 3140 LOC):**
- `ChartsView.tsx` (268) — KEEP
- `FundamentalsView.tsx` (495) — delete in 4.C
- `IntelligenceView.tsx` (366) — delete in 4.E
- `PaperView.tsx` (729) — KEEP (becomes tab 4)
- `PlaybookView.tsx` (262) — delete in 4.D
- `RegimeView.tsx` (21) — extend in 4.D
- `SignalLogView.tsx` (17) — KEEP (becomes tab 5, dedup fix in 4.G)
- `SignalView.tsx` (537) — delete in 4.B
- `SpreadsView.tsx` (466) — delete in 4.C

**Panels (10 files, 2991 LOC):**
- `DailySheet.tsx` (242) — move to DESK in 4.A
- `EIASurprisePanel.tsx` (254) — keep (used by MARKETS in 4.C)
- `ForwardCoverChart.tsx` (215) — keep (used by MARKETS in 4.C)
- `GeoRiskCalculator.tsx` (227) — move to DESK in 4.B
- `IndicatorDrillDown.tsx` (322) — move to DESK in 4.B
- `PriceDecomposition.tsx` (166) — move to DESK in 4.B
- `RegimeDrillModal.tsx` (331) — extend in 4.D
- `RegimePickCard.tsx` (619) — keep (REGIME tab hero)
- `SignalLogPanel.tsx` (238) — update in 4.G
- `ABComparePanel.tsx` (356) — keep on REGIME tab

**Total LOC delta target:** ~−1500 (mostly from killing IntelligenceView,
FundamentalsView, SignalView).
