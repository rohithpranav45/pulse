# PULSE — Project State

**PULSE** — Energy Intelligence Terminal (Futures First internship). A live energy-trading
dashboard: ingests ~35 data sources, runs quant models (fair value + a regime-conditional
spread engine), and serves a React dashboard with a paper-trading book.

- **Stack:** Flask 3 · React 18 + Vite + Tailwind · SQLite (cache + paper book) ·
  DuckDB/Parquet over a 3.5 GB `/Data` desk feed · sklearn + XGBoost/LightGBM/CatBoost
- **Run (local):** `python start.py` from the repo root → http://127.0.0.1:5000
- **Last updated:** 2026-06-30 (**Geo news-impact engine — Sprint 10: LLM-narrated RAG desk note**
  [branch `phase4-live-feature-overlay`, see §1 entry]. The generative "RAG" piece: new `analogs.narrate(result)`
  builds an **exact-number evidence block** from the analog forecast (per-node mean-Δ / agreement / n + EDGE tags),
  then either has **free Groq** (`gpt-oss-120b`) *phrase that block* under a strict no-invent prompt OR falls back to
  a **deterministic template** from the same numbers — **no key ⇒ template**, so it never hard-fails and never
  fabricates a figure. The note says which read to **trust** (EDGE/high agreement) and which to **fade** (agreement
  <50% = reversal). Surfaced at `GET /api/news/geo/analogs?narrate=1` + a gold **"Desk note"** card in
  `GeoAnalogPanel`. +6 hermetic tests (injected `llm_fn`) → **280 pass**; `tsc`/build clean. Prior: **Sprint 9:
  geo-map visualization** — a hand-rolled SVG equirectangular world (`frontend/src/lib/worldOutline.ts`, **no map
  dep**) plots all **37 placeable assets** at their registry lat/lon, sized by live event count + coloured by activity
  (muted→amber→**gold when EDGE**); `live.map_assets` + `GET /api/news/geo/map`; **`GeoMapPanel`** at the top of the
  News tab — clicking an asset shows its bias + recent alerts and **pre-fills the `GeoAnalogPanel` lookup**. Prior:
  **Sprint 8: live scheduler wiring + geo alerts**. The geo engine became a **live** analysis engine: new
  `geo/live.py` + `_geo_news_ingest` scheduler job (every `TTL_NEWS`, opt-out `PULSE_GEO_DISABLED=1`) pipes the
  cached `/api/news` wire → `is_geo_candidate` prefilter (free-Groq budget spent only on geo news) → `extract_cached`
  (fallback-not-cached guard intact) → `impact_map` node vector → `annotate_impact` EDGE/prior tags (merged across
  +1d/+5d, preferring the 5d geo edge) → an accumulating JSON store deduped by title hash. New `GET /api/news/geo/live`
  (ranked by |conviction| × tradeable) + **`GeoLiveAlertsPanel`** at the top of the News tab (newest geo headlines +
  node arrows + edge/prior tag). +7 hermetic tests → **270 pass**; `tsc`/build clean. Prior same day: **Sprint 7 —
  rbob_crack graded + dashboard geo panels**. Added `rbob_crack` to the registry + gasoline-crack
  `disruption_bias` on US/global refineries + Colonial + generics → it's now GRADED: refinery outage → gasoline
  crack UP **86–92% @1d** (n=14, right sign) but **below n≥20 → stays a labelled prior** (single episode too thin
  to certify). Put the engine on the dashboard: new `GET /api/news/geo` + **`GeoImpactPanel`** (per-node +1d/+5d
  hit-rate edge table) + **`GeoAnalogPanel`** (paste a headline → nearest past geo-events + per-node +5d nowcast)
  on the News tab; `tsc`/build clean. +1 test → **263 pass**. Prior same day: **Sprint 6 — products OHLCV feed →
  rbob_crack + June war gradeable**. A desk **hourly OHLCV feed**
  (`I:\Public\Summer Interns Energy\OHLCV`, override `PULSE_OHLCV_DIR`) for RBOB/HO/LGO/LCO/CL → new
  `geo/products_feed.py`. **`rbob_crack` is now a REAL node** (RBOB gasoline curve 2019→2026, was a declared GAP),
  and `build_node_panel` **extends the daily tape to 2026-06-26** (appends the feed tail past the lake's 05-26
  settle) — finally price-covering the **June Iran/Hormuz war**. Re-graded: events **68→112**, claims **1,400**.
  Durable @5d edges on the full war: **`wti_brent` tightens on chokepoint disruption (0.59, p=0.008)**, **`ho_crack`
  distillate firms (0.57, p=0.047)**, **`brent_flat` strongly REVERSES (0.40, p=0.000)** — risk premium round-trips
  while structural spreads persist; the Sprint-4b @1d crude-flat pop washed out (0.51) once June is included.
  Caveats: single episode, clustered events → optimistic p (trust direction). +9 tests → **262 pass**. Prior same
  day: **Sprint 5 — RAG analogs**: new `geo/analogs.py` — "this headline ≈ these k past
  geo-events, and here's what each did to the price nodes." Retrieval over the **graded event panel** (each past
  event carries its realised forward node moves) via an **interpretable** fingerprint (asset_type + event_type +
  signed conviction → cosine), so an opposite event (`restart` vs `closure`) ranks low — no black-box embeddings.
  `find_analogs` / `analog_forecast` (similarity-weighted per-node nowcast + analog-grounded direction-agreement) /
  `score_headline_analogs`; endpoint `GET /api/news/geo/analogs`. On the real 206-event index it **independently
  corroborates the Sprint-4b 5d crude-flat reversal** (nearest Hormuz-closure analogs agree ≈0–25% @5d). +11
  hermetic tests → **253 pass**. Next: the dashboard geo-map/node-impact table consuming it. Prior same day:
  **Sprint 4b — LLM geo-extraction re-grade**: ran a **free LLM** (`openai/gpt-oss-120b` on Groq —
  routed around the token-capped 70b; 8b too weak) over the GDELT corpus to fix the keyword fallback's
  closure-vs-reopen polarity error. It **2.3×'d the gradeable sample (events 30→68)** and **flipped crude-flat
  from noise to a measured edge: `brent_flat` +1d hit 0.60 (n=203, p=0.007) + beta t=3.59, `brent_structure`
  beta t=4.27** — chokepoint disruption lifts crude flat + backwardation next-day, correctly signed now that
  reopens type as `restart`. The original **`ho_crack` distillate-crack edge survives + strengthens (+5d 0.66,
  n=149, p≈0)**, while crude-flat **reverses by +5d (0.39, p=0.008)** — a real horizon structure (day-1 spike
  mean-reverts; physical distillate tightness persists). Caveats: single episode (2026 Hormuz war), clustered/
  overlapping events inflate p (read direction+pattern, not exact p), tape ends 2026-05-24. Fixed two latent
  bugs (cache no longer persists rate-limited fallbacks; `annotate_impact` honours explicit `cached={}`). No
  paid Claude. 242 tests pass. Prior same effort: **Sprint 4 — GDELT corpus + ACLED feed → a MEASURED edge**.
  A desk-supplied **GDELT oil-news corpus** (3,564 headlines,
  2026-03→06, the Iran/Hormuz war) finally gives the per-node event study a price-covered, geo-dense sample:
  `geo/datasets.py` ingests it → **30 gradeable events / 216 node-claims** (was 5/22) over 2026-03-30→05-23.
  **Graded verdict — a real, significant edge:** chokepoint disruption → **ULSD/distillate crack (`ho_crack`) UP
  over +5d, hit-rate 71% (n=35, binomial p=0.017)**, 69% all-events (p=0.024) — economically sound (Hormuz/Red-Sea
  closure tightens diesel). `brent_flat` is anti-signed @5d (0.38) because the **keyword** fallback can't tell
  "Hormuz closes" from "Hormuz reopens" — the exact direction error LLM extraction fixes (next lift). Also new
  `geo/conflict.py` — **ACLED** daily/monthly political-violence feed (2021-25) → a conflict-intensity regime
  (Iran now z≈58 HIGH) + a graded oil study: monthly oil-bloc conflict ≈ **uncorrelated with Brent** (corr
  −0.17 level / 0.03 change, n=53) — a useful risk *descriptor*, not a tradeable monthly signal. +11 tests →
  **242 collected**. Prior same day: **Sprint 3 — per-node event study** (machinery; was un-gradeable on the thin
  2021 corpus, now unblocked), **Sprint 2 — LLM geo-extraction + impact map**, **Sprint 1 — asset registry (41) +
  price-node builder**. Prior: **Inventory: actual EIA number
  pulled LIVE from the EIA v2 API** [branch
  `phase4-live-feature-overlay`, see §1 entry]. The reaction grade + the default call now anchor the ACTUAL on
  the **authoritative live EIA Weekly Petroleum Status Report API** (force-refreshed after each release via a new
  scheduler job + `?refresh=1`), not the static investing.com scrape or the API/industry proxy. Verified live:
  week ending 2026-06-19 crude actual **−6,088 MBBL** from the EIA API, vs consensus −3,900 = −2,188 surprise;
  `actual_source: "eia_api (live)"`. Falls back to the scrape only while the API hasn't yet published the week.
  Prior: **directional accuracy backtest + selective-confidence ("best results")** [see §1 entry]. The honest "is the call any good?" fix —
  measure the **directional hit-rate across all 2015-26 releases** (on real consensus), sliced by series ×
  regime × surprise-size, then make the framework **commit a directional call ONLY where history proves an
  edge** and abstain elsewhere. **The edge map:** crude flat is **75-81% in a glut/HIGH-stocks** regime
  (p<0.01) but a **coin-flip (~52%) in today's tight/backwardated** regime → abstain on crude flat; **gasoline
  flat is a real 57% in backwardation (68% on big surprises, p<0.001)** — exactly where crude is noise → the
  framework now **redirects conviction to gasoline today**. New `accuracy.py` (`applicable_hit_rate` /
  `best_series_now`); confidence leads with the measured hit-rate (`tradeable` flag); surfaced live + on the
  dashboard (track-record badge, redirect banner, per-regime hit-rate table). Intraday event study re-fit on
  real consensus too (still null in the 2021+ tight era — correctly no edge to manufacture). Prior: **Inventory:
  real consensus + API nowcast wired (item 3)** [branch `phase4-live-feature-overlay`, see §1 entry]. The framework now surprises against the **REAL analyst consensus**
  (548-wk investing.com history, all 3 series) instead of the seasonal proxy, with the **API crude leading
  indicator** as a pre-release nowcast. **Graded verdict: real consensus SHARPENS the "when it mattered" signal** —
  9/10 regime cuts get a bigger |t| (5/5 of the cells where inventories should bite), significant cuts 4→5, ALL-
  releases t −1.71→−2.48, glut HIGH-stocks β −1.03/t −3.36 → β −1.14/t −3.89, the 2015-20 glut era t −2.94→−3.79 —
  while the tight/backwardation cells stay null, exactly the pattern a real (vs proxy) surprise should produce, so
  the framework's headline is **not a seasonal artefact**. Re-anchored the live reaction grade on the **real printed
  EIA actual** (24-Jun crude −6.088M vs consensus −3.900M = a −2,188 MBBL *bullish* surprise) — the old API proxy
  −0.765M had the **wrong sign**. Prior: **Inventory: "when it mattered" re-run vs WTI** — regime conditioning is NOT
  sharper on WTI flat returns (synth WTI starts 2021 → no glut rows), but WTI is correctly signed where Brent flips;
  the near-significant matched cut is the US-specific WTI-Brent spread. Prior: **Inventory prediction framework — productionised + live-graded**. The EIA-release impact model now (1) covers **all 3 series**
  (Crude/Gasoline/Distillate) via a series toggle, each with its OWN regime betas — gasoline reacts in
  backwardation where crude is noise; (2) headlines the **WTI** move (US crude inventories move WTI ~17× more than
  Brent — proven by the spread attribution) + per-spread impacts; (3) shows a directional **point estimate +
  typical day-range** instead of a bare ≈0; (4) **grades predicted-vs-actual** from the desk 1-min feed
  (`release_reaction.py`). Today's crude print: our **bearish** call was CORRECT (flats fell, WTI-Brent +0.12 as
  flagged), magnitude muted (−0.3% « ±2.5% day range) = the low-sensitivity regime call held. Honest limits: the
  desk feed is **crude-only** (no RBOB/ULSD tape → gas/distillate reaction shown via the crude complex); the
  when-it-mattered betas were Brent-based (now **re-run vs WTI** — see the latest entry; the WTI flat-return study
  is data-limited to 2021+, so the glut signal stays Brent-only). Also **fixed the
  "stuck" live signal feed** (curve softened BACK→NEUTRAL → model fell to the global baseline whose OOS-unvalidated
  cells the health gate hard-rejected → forced NEUTRAL; now soft-fails *degrade* instead of *silence*) and the
  **News tab went live** (wire→corpus→impact ingest, live headlines scored + refresh button). Prior:
  **News Impact Sprint 3 — GEOPOLITICAL earns a measured beta** (re-classified ~1/3 NOISE with Groq 8b →
  GEOPOLITICAL 1d t=1.54→3.05, β=+0.87 %/unit MEASURED; `.gitattributes` DB-corruption fix; `OIL_CORPUS_THEMES`).
  Prior: **Sprint 2: event study + the % move.** Turns the Sprint-1
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

### ✅ Inventory prediction framework — productionised + live-graded (2026-06-25)
Branch `phase4-live-feature-overlay` (not merged to main). Extends the crude-only EIA-release impact model into
a desk-ready, three-series, predicted-vs-actual framework. Files: `backend/research/inventory_impact/{framework,
regime_conditioning,release_reaction}.py`, `/api/regime/inventory[?series=][/reaction]`, frontend
`Inventory{Impact,Reaction}Panel.tsx` + the series toggle in `InventoryView.tsx`.
- **3 series (Crude/Gasoline/Distillate), each with its OWN regime betas.** `build_daily_panel(series=)` +
  `current_regime(series=)` + `framework.assess_series(series, actual, consensus)` (crude delegates to the full
  `assess_release`; gas/distillate get the regime-conditioned core). `/api/regime/inventory?series=` + a toggle on
  the tab. **Key cross-series finding:** in today's tight/backwardated/summer regime, **crude surprises are noise**
  (t≈0 across LOW-stock/tight/backwardated cuts) but **gasoline** is borderline-significant (t −1.5 to −2.3 in the
  low-stock/backwardated cuts; the consistent vs-5yr split gives t≈−1.48) — the conventional "watch crude" is
  wrong here, gasoline is the live series. Distillate is weak (summer is its off-season).
- **WTI is the affected benchmark, proven empirically.** Spread attribution: a crude surprise moves **WTI flat
  β=+0.026 (t=1.03)** vs **Brent flat β=+0.0015 (t=0.05)** — WTI reacts ~17× more; Brent ≈ no reaction (US crude
  inventories are a US signal). The call card now headlines the **WTI** move + a per-spread impact table
  (WTI-Brent, WTI M1-M2). `regime_conditioning` gained `_wti_daily()` + `ret_wti`/`d_wti_*` panel columns +
  `current_regime.applicable_beta_wti`; `assess_release` adds a `price_reaction` (WTI vs Brent, regime-gated) +
  `spread_impacts` block. **Caveat (now addressed — see the WTI re-run entry below): the "when-it-mattered"
  regime betas were measured vs Brent; the study has been re-run vs WTI and the daily flat-return result is
  data-limited to 2021+ (no glut rows), so the glut signal stays Brent-only.**
- **"≈0" → directional point estimate + day range.** The hard-gated "≈0" read as "no price change" (misleading).
  Now shows the **point estimate** (β×surprise, e.g. WTI −0.03%) + a confidence tag (significant vs `low conf ·
  not a catalyst`) + the **typical release-DAY range** (1σ ≈ ±2.5%) — so it's clear price still moves, just not
  predictably from the print. `point_move_pct` + `day_range_pct` on `price_reaction`.
- **Predicted-vs-actual release grading from the desk 1-min feed.** `release_reaction.py` snapshots the WAL 1-min
  db (`I:\…\DB\extra\bars_1min_*.db`, gotcha 14), anchors at the release minute (10:30 ET = 14:30 UTC), and
  computes the move in WTI/Brent flat + WTI-Brent + WTI M1-M2 at **+5/15/30/60 min**. `/api/regime/inventory/
  reaction?series=` returns predicted (model) + actual side by side; `InventoryReactionPanel` grades each
  (✓/✗/~) with a verdict. **Today's crude verdict (consensus −3.9M, API −0.765M → bearish surprise z+0.57):
  CORRECT direction** — flats fell (WTI −0.31%, Brent −0.41% @30min), **WTI-Brent +0.12** (our flagged spread,
  right direction), magnitude **muted** (peak −0.4% « ±2.5% typical) = the low-sensitivity regime call held.
- **Honest data limit: the desk feed is CRUDE-ONLY** (every `bars_*min_*.db` has only CL/CO — no RBOB/HO/gasoil).
  So gasoline/distillate *product* price reactions (RBOB/ULSD cracks) can't be measured; the reaction panel shows
  their predicted→Brent cross-effect vs the crude-complex move (they release jointly at 10:30 ET) with an explicit
  caveat banner naming the unavailable product crack. **A products feed (RB/HO/QS) is the unlock.**
- **Tests:** +4 (`test_assess_series_all_three` ×3, `test_release_reaction_computes_horizon_moves`). The reaction
  panel anchors today's prediction on the **API −0.765M as a proxy** for the EIA actual — re-anchor on the real
  printed EIA number for an exact grade.

### ✅ Geo news-impact engine — Sprint 11: ACLED conflict-regime slice axis + rbob_crack scope (2026-06-30)
Branch `phase4-live-feature-overlay` (not merged to main). Adds the conflict-intensity conditioning axis to the
event study (the last analytical-depth item) and honestly scopes the `rbob_crack` certification as **data-bound**.
- **New conditioning axis.** `event_study_geo.build_event_panel` now tags every event with the **causal ACLED bloc
  conflict regime** as-of its month (new `_event_conflict_level` — `conflict.conflict_regime("BLOC", asof=…)`,
  memoised per year-month so the CSV is read once per distinct month; None when ACLED is absent / UNKNOWN).
  `node_hit_table` emits a new **`node×conflict`** slice (every row also carries a `conflict` field, `*` = not
  conditioned) → directly answers "does the geo edge strengthen in HIGH-conflict months?". `compute_and_cache` records
  the conflict-level distribution (`conflict_levels`, `n_events_no_conflict`) so the coverage is visible in the map.
- **`annotate_impact` is untouched in behaviour** — it now **skips** `conflict != "*"` rows, so the conflict axis is
  **descriptive only** and never drives the live prior-then-learn tag (we don't condition the live impact on ACLED).
  A pre-Sprint-11 cache (rows without a `conflict` key) still works (`.get("conflict","*")` defaults to `*`).
- **Graded verdict (honest, data-bound): the axis is DEGENERATE on this corpus, so the strengthening question can't be
  answered yet.** Re-grade: all **112 war events map to a single ACLED level (`LOW`)** — because **ACLED ends 2025-06**
  and the gradeable events are all 2026-03→06, so every event's causal as-of read returns the one stale 2025-06 bloc
  value. The `node×conflict` slices therefore just **mirror the pooled rows** (e.g. `wti_brent/*/*/LOW` 0.57 n=284 =
  `wti_brent/*/*` 0.57 n=284; `ho_crack .../LOW` 0.56; `regrade .../LOW` 0.80 EDGE) — zero discrimination. **The
  machinery is proven on synthetic data** (a HIGH-conflict edge of 0.8 vs a NORMAL coin flip is correctly split), but
  the real test needs **ACLED coverage through the 2026 episode** — more data, not code.
- **`rbob_crack` certification — scoped, deferred (more-data-not-code).** Still a labelled **prior** (refinery outage →
  gasoline crack 86–92% @1d but **n=14 < MIN_N=20**, single episode). Certifying it (and adding an **RBOB M1-M2**
  gasoline-curve node) is **not a code gap** — `rbob_crack` is already priceable (Sprint 6 OHLCV feed) and graded
  (Sprint 7 registry bias); it needs a **thicker, cross-episode refinery sample** (broaden the GDELT corpus beyond the
  single 2026 war, or a price-covered backfill of past refinery outages) so the n clears the bar across independent
  episodes. Flagged as the standing data unlock, not a build task.
- **Tests:** +4 hermetic (`tests/test_geo_event_study.py` — `node×conflict` slice flags a synthetic strengthening
  edge [HIGH 0.8 sig vs NORMAL coin-flip], `annotate_impact` ignores conflict-conditioned rows, `build_event_panel`
  tags the conflict regime via a monkeypatched `conflict` module, and yields `None` + no conflict axis without ACLED).
  **284 pass** (was 280). Re-grade: `python backend/research/news_impact/geo/event_study_geo.py`.
- **Next:** the geo roadmap's planned sprints are complete; remaining unlocks are **data, not code** — ACLED through
  the episode (to make the conflict axis live) + a cross-episode refinery corpus (to certify `rbob_crack`).

### ✅ Geo news-impact engine — Sprint 10: LLM-narrated RAG desk note (2026-06-30)
Branch `phase4-live-feature-overlay` (not merged to main). The analogs were structured/numeric (retrieval, no
generation step) — this adds the **generative** "RAG" piece: a 2-3 sentence desk note, grounded ONLY in the
retrieved analogs + the graded edge map.
- **New `analogs.narrate(result, *, horizon=, provider=, llm_fn=)`.** It first builds an **exact-number evidence
  block** from the analog forecast (`_evidence` → per-node `mean Δ`, `analog_agree`, `n`, sorted EDGE-first; EDGE
  flags via `event_study_geo.annotate_impact` across both horizons) — so **no path can invent a figure**. Then it
  either (a) asks **free Groq** (`openai/gpt-oss-120b`, text completion) to *phrase that block* under a strict system
  prompt ("use ONLY the facts and numbers given — never invent, never re-round"), or (b) falls back to a
  **deterministic template** built from the same numbers. `provider="template"` forces the rule-based note; an
  injectable `llm_fn(system,user)` makes it testable / provider-agnostic. **No key + no llm_fn → degrades to the
  template** (the desk always gets a grounded note). The note names the read to **trust** (high agreement / EDGE)
  and the one to **fade** (agreement <50% = the analogs reversed it) + the single-episode caveat.
- **Surfaced:** `GET /api/news/geo/analogs?narrate=1` attaches a `narration` block (`{available, source, note,
  horizon, evidence}`); `api.newsGeoAnalogs(title,k,horizon,narrate)`. **`GeoAnalogPanel`** now requests `narrate=1`
  and renders a gold **"Desk note"** card above the per-node table with a `Groq`/`rule-based` source chip.
- **Verified (Flask test client, real index):** "Iran closes the Strait of Hormuz" → *"5 past chokepoint/closure
  analog(s), closest similarity 1.00. They moved WTI–Brent +1.01 over 5d, agreeing 60% (n=5) (certified EDGE) —
  trust this read. ULSD crack reversed (0% agreement, n=5) — fade it. Single-episode evidence …"* (source `template`,
  no key in that shell) — every number traces to the evidence block.
- **Tests:** +6 hermetic (`tests/test_geo_analogs.py` — template is grounded [quotes real `n=`], injected-LLM is fed
  the exact-number facts + the no-invent instruction, **degrades to template with no Groq**, graded EDGE flows into
  the evidence, unavailable-result + no-analog-rows are graceful; monkeypatched `load_cached` + injected `llm_fn`, no
  network/Groq/Data). **280 pass** (was 274). `tsc` clean (only the pre-existing TS5101); `npm run build` clean.
- **Next:** Sprint 11 — condition the event study on the **ACLED conflict regime** + certify `rbob_crack` (needs a
  thicker cross-episode refinery sample — more data, not code).

### ✅ Geo news-impact engine — Sprint 9: geo-map visualization (2026-06-30)
Branch `phase4-live-feature-overlay` (not merged to main). Puts the registry on a **map** — the assets the engine
reasons about, where they physically are, lit by live geo-alert activity.
- **No heavy new dep.** The bundle has no map lib (only `recharts`/`lightweight-charts`), so the map is a hand-rolled
  **SVG equirectangular world** — new `frontend/src/lib/worldOutline.ts` (coarse continent silhouettes as lon/lat
  rings + a `projectLonLat` / `continentPaths` projection into a 720×360 viewBox; precision isn't the point — assets
  plot at their exact registry lat/lon, the land is a faint backdrop). Bundle 1,295 → **1,304 kB JS** (+9 kB, no dep).
- **New backend `live.map_assets(store_path=)` + `GET /api/news/geo/map`.** Joins every **placeable** registry asset
  (drops the 4 GLOBAL generics at 0,0 → **37 plotted**) with its static facts + `disruption_bias` prior + **live
  activity** tallied from the Sprint-8 `geo_live_events.json` store (`_activity_index`: per-asset event count, peak
  conviction, any-EDGE flag, newest ts, ≤4 headlines). Registry stays the single source of truth for coords + priors;
  activity is the live overlay. `api.newsGeoMap`.
- **Dashboard — `GeoMapPanel.tsx`** (top of the News tab, under the live-alerts strip). Plots the 37 assets; each dot
  is **sized by live event count** and **coloured by activity** (muted by asset-type when quiet → amber when active →
  **gold when EDGE-tagged**), inactive dots painted under active ones, native `<title>` hover. **Clicking an asset**
  selects it → a detail card (capacity/carries/note + the `disruption_bias` node arrows + its recent live alerts) **and
  pre-fills the `GeoAnalogPanel` lookup** (lifted `analogPrefill` state in `NewsView`; a clicked asset hands over its
  newest live headline, or a synthetic alias-resolvable disruption headline when it has none, and `GeoAnalogPanel`'s
  new `prefill` prop runs the analog query). Legend + click hint included.
- **Verified (Flask test client):** `/api/news/geo/map` → 200, `count:37 active:0` on this machine (no live store),
  Hormuz at **26.57/56.25** with `disruption_bias.brent_flat:2`. Activity overlay exercised by the hermetic store test.
- **Tests:** +4 hermetic (`tests/test_geo_map.py` — generic/unplaceable exclusion, coords+bias for a known asset,
  activity tally [count/peak-conviction/any-EDGE/newest-ts], headline cap; synthetic on-disk store, no network/Groq/
  Data). **274 pass** (was 270). `tsc` clean (only the pre-existing TS5101 `baseUrl` deprecation); `npm run build` clean.
- **Next:** Sprint 10 LLM-narrated RAG desk note (free-Groq `analogs.narrate`), Sprint 11 ACLED conditioning + certify
  `rbob_crack` (needs a thicker cross-episode refinery sample — more data, not code).

### ✅ Geo news-impact engine — Sprint 8: live scheduler wiring + geo alerts (2026-06-30)
Branch `phase4-live-feature-overlay` (not merged to main). Turns the corpus-only study into a **live** analysis
engine (the mentor's standing directive) — TODAY's wire is scored into geo events in real time.
- **New `backend/research/news_impact/geo/live.py`.** `ingest_wire(articles, *, extract_fn=, regime=, max_new=,
  store_path=)` is the geospatial twin of `app._news_corpus_ingest`: it takes the already-cached `/api/news` wire,
  keeps only **geo candidates** (`extract.is_geo_candidate` prefilter, so the free-Groq token budget is spent only on
  geo headlines), scores each via **`extract.extract_cached`** (the LLM-extraction cache is reused with the desk
  re-grade, and its **"never cache a fallback" guard is left untouched** — we call it unchanged) → `impact_map.
  headline_impact` (signed node vector) → `event_study_geo.annotate_impact` (EDGE/prior tags). Edges are **merged
  across +1d and +5d** (preferring a tradeable 5d slice — the geo edges live at +5d: chokepoint → `wti_brent`/
  `ho_crack`; with `regrade` at +1d), so a Hormuz closure surfaces its certified 5d EDGE nodes. Persisted to an
  **accumulating JSON store** (`geo_live_events.json`, deduped by title hash, capped 200, newest-first). `recent_events
  (limit)` ranks by **|conviction| × tradeable** then recency. Only headlines that resolve to a non-empty node vector
  are stored (a headline naming no asset / no throughput event is not an alert). Standalone:
  `python backend/research/news_impact/geo/live.py`.
- **Scheduler + endpoint.** New `_geo_news_ingest` job in `app.py` (every `TTL_NEWS`, kicked +3 min after boot,
  opt-out `PULSE_GEO_DISABLED=1`; also fired on the manual `POST /api/news/refresh`). New **`GET /api/news/geo/live?
  limit=`** → recent live-scored geo events ranked by conviction × tradeable + a single-episode caveat. `api.newsGeoLive`.
- **Dashboard — `GeoLiveAlertsPanel.tsx`** at the **top of the News tab** (above the Live Headlines strip): each
  alert shows the publication time, an `asset_type/event_type` chip, the headline (links out when a url exists), the
  strongest 4 **node arrows** (↑↑/↑/↓/↓↓, bull/bear-toned, gold-ringed when that node is a certified EDGE), and an
  `edge`/`prior` tag — reusing the Panel freshness/error chips. Empty-state copy when the ingest job hasn't ticked yet.
- **Verified end-to-end (Flask test client + standalone):** Hormuz closure → `chokepoint/closure`, nodes brent_flat↑↑
  / wti_brent↓ / brent_structure↑↑, **EDGE @5d on `wti_brent` + `ho_crack`**; Aramco drone strike → `field/attack`;
  re-running the same wire adds 0 (dedup); a non-geo headline ("Apple unveils iPhone") never reaches the extractor.
- **Tests:** +7 hermetic (`tests/test_geo_live.py` — geo-candidate prefilter scores+skips, extractor-not-called with
  no candidates, no-node-vector-not-persisted, dedup-scores-once, ranking by conviction×tradeable, prior-tag without
  an edge map, store cap; monkeypatched wire + extractor, no network/Groq/`/Data`). **270 pass** (was 263).
  `tsc --noEmit` clean (only the pre-existing TS5101 `baseUrl` deprecation); `npm run build` clean (1,295 kB JS).
- **Next:** Sprint 9 geo-map (registry lat/lon on the News tab), Sprint 10 LLM-narrated RAG desk note, Sprint 11
  ACLED conditioning + certify `rbob_crack` (needs a thicker, cross-episode refinery sample — more data, not code).

### ✅ Geo news-impact engine — Sprint 7: rbob_crack graded + dashboard geo panels (2026-06-30)
Branch `phase4-live-feature-overlay` (not merged to main). Closes the products-feed payoff and puts the geo
engine on the dashboard.
- **`rbob_crack` is now GRADED (not just priceable).** Added `rbob_crack` to the registry node vocabulary
  (`registry.NODES`) and a positive gasoline-crack `disruption_bias` to the assets that actually drive it — US
  refineries **+2** / non-US **+1** (the `_ref` template), **Colonial** (the literal US gasoline pipeline) **+2**,
  and `generic_refinery` / `generic_product_pipeline` **+1**. `impact_map` iterates `disruption_bias`, so it now
  emits `rbob_crack` automatically; the re-grade claims it. **Verdict (honest prior-then-learn):** refinery outage
  → **gasoline crack UP, hit 86–92% @1d** (rbob_crack/refinery 0.92 n=12; rbob_crack/* 0.86 n=14) — economically
  dead-on and the right sign — **but n=14 < MIN_N=20, so it stays a labelled PRIOR, not a certified EDGE.** The
  products feed made gasoline-crack reactions *measurable*; the single 2026 episode is just too thin (few refinery
  events) to certify yet. claims 1,400 → **1,414**.
- **Dashboard — two geo panels on the News tab.** New endpoint **`GET /api/news/geo`** (serves the cached per-node
  edge map + node catalog + analog-index size; loose-jsonify like `/api/news/live`) and `api.newsGeo` /
  `api.newsGeoAnalogs`. **`GeoImpactPanel.tsx`** — the node-impact edge table: per price node, the +1d/+5d
  directional hit-rate (tone-coded, `e` EDGE chip when binomial-significant) + the measured 5d beta (`*`), over the
  graded study. **`GeoAnalogPanel.tsx`** — paste/click a headline → calls `/api/news/geo/analogs` → shows the
  query's resolved asset/event, a similarity-weighted **per-node +5d nowcast** (mean Δ + analog-agreement %), and
  the **nearest past analogs** (cosine + asset/event + date + title); 3 example headlines as quick-fill chips.
  Wired into `NewsView` (responsive 2-col). `npm run build` clean (1,291 kB JS), `tsc` clean (only the pre-existing
  TS5101 `baseUrl` deprecation).
- **Tests:** +1 (`test_registry_grades_rbob_crack` — node in vocab, US-refinery bias > 0, impact_map emits it,
  restart flips it negative); registry/impact-map suites still green (they assert sign-correctness, not exact
  dicts). **263 pass** (was 262). Endpoints verified via the Flask test client (geo: 112 events / 1,414 claims /
  index 312 / rbob_crack in the 5d slices; analogs: refinery/strike resolves + matches).
- **Next:** a gasoline-curve node (RBOB M1-M2) + thicker refinery sample to certify the rbob_crack edge; an actual
  geo-MAP (lat/lon from the registry) on the dashboard; condition the study on the ACLED conflict regime; push the
  OHLCV tail-extension into the live regime engine (currently desk runs on the daily settle tape ending 05-26).

### ✅ Geo news-impact engine — Sprint 6: products OHLCV feed → rbob_crack + June war now gradeable (2026-06-30)
Branch `phase4-live-feature-overlay` (not merged to main). A desk-supplied **hourly OHLCV** feed landed on the
share — `I:\Public\Summer Interns Energy\OHLCV` (override `PULSE_OHLCV_DIR`) — continuous contracts c1..c12 for
**RBOB / HO / LGO / LCO / CL**. Two real unlocks, both wired in.
- **New `backend/research/news_impact/geo/products_feed.py`.** Loads the hourly CSVs → daily settle frames
  (`daily_curve` = last hourly `Last` per UTC date, the same session-end proxy as the synth crude settles);
  `daily_settles()` returns every product's c1..c12 daily frame. **Coverage:** RBOB is full history **2019-01 →
  2026-06-26** (the gasoline curve the lake never had); HO/LGO/LCO/CL are **2026-04-30 → 2026-06-26** (~50 days,
  but critically *past* the lake's last settle 2026-05-26). **Bug fixed at birth:** passing `index=ts` while the
  column Series still carried their 0..N integer index made pandas align on mismatched labels → every row NaN →
  silent empty frame; fixed by building columns from `.to_numpy()`.
- **`rbob_crack` is now a REAL node (was a declared GAP).** `compute_nodes` gained an optional `rbob` arg →
  `rbob_crack = RBOB×42 − WTI` (catalog flipped `gap`→`feed`/available, ESTIMATE since the settle is a session-end
  proxy). Merged-panel median **+$22.7/bbl** (plausible US gasoline crack). **`build_node_panel(use_products_feed=
  True)`** now prefers real lake history and **appends only the feed's post-05-26 tail** (`_combine_tail`), so the
  daily node panel **extends to 2026-06-26** — finally price-covering the **June Iran/Hormuz war**, the #1 blocker
  the prior sprints kept flagging.
- **Re-grade on the June-extended tape — the bigger sample sharpens the honest story.** Events **68 → 112**,
  node-claims 879 → **1,400** (2026-03-30→06-23; asset mix chokepoint 95 / producer 35 / refinery 13). The
  durable, economically-coherent **@5d** signals on the full war:
  - **`wti_brent`/chokepoint 0.59 (n=229, p=0.008 EDGE)** — a Mideast chokepoint scare tightens **Brent relative
    to WTI** (waterborne/Mideast-linked vs landlocked US), the predicted direction, over 5d. *New* this sprint.
  - **`ho_crack`/chokepoint 0.57 (n=229, p=0.047 EDGE)** — the US distillate-crack edge **holds** on the bigger,
    fuller sample (was 0.66 on n=149; hit-rate softer but still significant).
  - **`brent_flat` REVERSES, now strongly: 0.40 (n=305, p=0.000)** — crude *flat* reliably mean-reverts 5d after a
    chokepoint headline (the risk premium round-trips), `gasoil_crack` similarly 0.42 (p=0.008). Measured betas
    @5d: `brent_structure` +0.190 t=3.24, `regrade` −0.99 t=−3.37 (n=20, thin).
  - **The @1d crude-flat edge from Sprint 4b (0.60) washed out to a coin flip (0.51, n=307)** once June (the
    de-escalation/price decline) is included — honest: the May-only intraday pop didn't survive the full episode;
    only `gasoil_crack` keeps a measured @1d magnitude beta (+0.194 t=3.42). **Read: the robust geo reads are at
    5d and in the STRUCTURAL nodes** (Brent-rel-WTI tightening + distillate firming + flat-price fade), not the
    flat-price direction intraday.
- **Honest caveats (now sharper):** still a **single episode** (2026 Hormuz war), and the 1,400 claims come from
  112 clustered events with heavily overlapping forward windows → p-values are **very** optimistic; trust the
  **direction + cross-node coherence**, not the exact p. `rbob_crack` is now priceable but **not yet graded** — the
  registry `disruption_bias` covers the 7 canonical nodes only, so events don't claim it yet (add an `rbob_crack`
  bias row to grade gasoline-crack reactions — clean next step). Daily settles are last-hourly-bar ESTIMATEs.
- **Tests:** +9 hermetic (`tests/test_geo_products_feed.py` — hourly parse + the index-alignment regression guard,
  last-bar-per-date settle, absent/unknown product, `_combine_tail` extends-only-after-lake-max + preserves overlap
  + missing-side, `rbob_crack` conversion + needs-WTI, real-feed smoke skipif) + updated the node catalog test
  (`rbob_crack` now available, `brent_dubai` stays the gap). **262 pass** (was 253). Standalone:
  `python backend/research/news_impact/geo/products_feed.py`.
- **Next:** add `rbob_crack` to the registry `disruption_bias` (grade gasoline cracks) + a gasoline-curve node
  (RBOB M1-M2); the dashboard geo-map/node-impact table; the same OHLCV tail-extension could feed the live regime
  engine past 2026-05-26 (currently the desk runs on the daily settle tape).

### ✅ Geo news-impact engine — Sprint 5: RAG analogs ("this event ≈ these k past events") (2026-06-30)
Branch `phase4-live-feature-overlay` (not merged to main). Where `event_study_geo` grades the AVERAGE reaction
(per-node hit-rate + beta), this layer answers the desk's other question — *given THIS headline, what are the
closest historical geo-events and what did each actually do to the price nodes?* New
**`backend/research/news_impact/geo/analogs.py`**:
- **RAG in the literal sense, but interpretable.** The "corpus" is the **graded event panel** (each past event
  already carries its realised forward node moves); the retriever is a **structured nearest-neighbour**, not a
  black-box embedding (consistent with the no-paid-embeddings stance — Anthropic has no embeddings endpoint).
  `fingerprint(event) = [one-hot(asset_type) | one-hot(event_type) | L2-normalised signed conviction vector]`;
  cosine similarity over the concat scores an analog high when it shares asset class + event verb + the
  **directional** impact pattern, and an opposite event (a `restart` vs a `closure`) scores LOW because the
  conviction block flips sign. Added a `title` column to `build_event_panel` so analogs cite the source headline.
- **API.** `build_analog_index` (collapses the panel to one record per event, memoised via `get_index`),
  `find_analogs(query, k)` (ranked analogs + each shared node's realised Δ + whether it agreed with the query's
  predicted direction), `analog_forecast(query, k, horizon)` (similarity-weighted per-node nowcast: mean realised
  Δ, mean vol-normalised Δ, and an **analog-grounded direction-agreement** — distinct from the regression beta,
  this is retrieval not a fit), `score_headline_analogs(title)` (headline → extract → analogs, the live
  entrypoint). New endpoint **`GET /api/news/geo/analogs?title=&k=&horizon=`** (loose-jsonify pattern like
  `/api/news/live`; reuses the memoised index + cached extractions).
- **Verified on the real index (206 graded geo-events).** "Iran closes Strait of Hormuz" → chokepoint/closure,
  retrieves chokepoint analogs at cosine ≈1.0; "Drone strike at a Saudi refinery" → refinery/attack, retrieves
  refinery attack/fire/outage analogs. **It independently corroborates the Sprint-4b 5d reversal:** for a Hormuz
  closure the nearest analogs show `brent_flat` **agree≈0–25% @5d** (they mostly moved crude flat DOWN by day 5) —
  the same horizon structure the event-study regression flagged, recovered by a completely different (retrieval)
  method. Honest scope: the index is the single 2026-Hormuz episode, so analogs are within-episode (same caveat as
  Sprint 4b); the agreement %/mean-move are descriptive retrieval stats, not a fitted edge.
- **Tests:** +11 hermetic (`tests/test_geo_analogs.py` — fingerprint identical→cosine 1 / opposite-direction
  scores lower / zero-vector safe; panel→event collapse; nearest-neighbour ranks same-kind top + opposite-direction
  low; direction-agreement flags; weighted forecast aggregation + no-analog node; headline entrypoint via
  monkeypatched extractor; non-geo unavailable; empty-index safe). Fixed the same falsy-empty trap as Sprint 4b
  (`index or build_analog_index()` → `is None`, since `AnalogIndex.__len__` makes an empty index falsy). **253
  tests pass** (was 242). Standalone: `python backend/research/news_impact/geo/analogs.py`.
- **Next:** the **dashboard geo-map + node-impact table** (News tab) consuming `/api/news/geo/analogs` +
  `/api/regime/inventory`-style edge surfaces — a self-contained UI sprint; optionally a typed Pydantic schema for
  the analogs payload (currently loose-jsonify). Bigger result-unlock remains a price tape past 2026-05-24.

### ✅ Geo news-impact engine — Sprint 4b: LLM geo-extraction re-grade (the polarity fix lands) (2026-06-30)
Branch `phase4-live-feature-overlay` (not merged to main). Sprint 4's MEASURED edge was on the **keyword**
fallback, which can't tell "Hormuz closes" from "Hormuz reopens" — so `brent_flat` was anti-signed and most
slices were coin-flips. This session ran a **free LLM re-grade** over the GDELT corpus to fix the
closure-vs-reopen event-polarity error, and it materially strengthened the result.
- **Free-LLM routing around the Groq 70b cap.** 70b (`llama-3.3-70b-versatile`) was token-capped (99.7k/100k
  TPD) and `llama-3.1-8b-instant` is too weak (it *nulls* reopen events instead of typing them `restart`, so
  they'd just be dropped). Found **`openai/gpt-oss-120b`** (and `qwen/qwen3-32b`) on Groq match 70b on the
  polarity test (closure↔restart↔opec_hike all correct, "drone strike"→attack) and have a **separate** free
  daily budget → made it the default `extract.GROQ_MODEL`. **Fixed two latent bugs:** (1) `extract_cached` now
  **only caches LLM-sourced records** (a rate-limited fallback is no longer persisted — last session's cache was
  1,009 poisoned keyword rows that silently shadowed the LLM, producing byte-identical "re-grades"); (2)
  `annotate_impact` now honours an **explicitly-passed `cached={}`** (was `cached or load_cached()`, so an empty
  map silently reloaded the real edge file — exposed once a real `brent_flat` edge existed).
- **Result: the LLM extraction 2.3× the gradeable sample AND flipped crude-flat from noise to a measured edge.**
  Gradeable **events 30 → 68**, node-claims 216 → 879 (the LLM resolves far more headlines to asset+event than
  keyword); event mix now carries the sign-flippers keyword conflated — 10 `restart` / 10 `closure` / 18
  `blockage` / 8 `attack` / 8 `force_majeure` / 8 `sanction` / 2 `opec_hike`. The graded edge map (cached to
  `geo_event_study.json`), 2026-03-30→05-24:
  - **@1d (immediate reaction):** `brent_flat` **0.51 coin-flip → 0.60 hit (n=203, p=0.007 EDGE)**, **measured
    beta +0.137 t=3.59**; `brent_structure` **measured beta +0.150 t=4.27** (the strongest). Chokepoint
    disruption lifts crude flat + backwardation next-day — correctly signed now that closures vs reopens are
    distinguished.
  - **@5d (week-out):** the original **`ho_crack` (US distillate crack) edge SURVIVES and strengthens — 0.66
    hit (n=149, p≈0.000 EDGE)** (was 0.69/n=35/p=0.017). BUT `brent_flat` **reverses to 0.39 (p=0.008,
    anti-signed)** and `gasoil_crack` 0.40 (p=0.012) — the day-1 crude spike mean-reverts as the risk premium
    bleeds off, while genuine physical tightness persists in the **US distillate crack** (rerouting/voyage
    length keeps diesel bid). A real **horizon structure** the keyword pass was blind to: trade the crude-flat
    +1d pop and fade it; hold the distillate crack for the week. `brent_structure` measured beta +0.191 t=2.14 @5d.
- **Honest caveats (load-bearing):** (1) **single episode** — this is the 2026 Iran/Hormuz war, a *within-episode*
  reaction study, not yet validated across independent chokepoint episodes; (2) **p-values are optimistic** — the
  879 claims come from 68 clustered events with overlapping forward windows in one 2-month episode, so they are
  not independent and the binomial test overstates significance → read the **direction + cross-node/horizon
  pattern** (brent_flat↑@1d, ho_crack↑@5d, brent_flat reverses@5d) as the signal, not the exact p; (3) still
  bounded by the price tape ending **2026-05-24** — the June war peak remains ungradeable (a refreshed `/Data`
  feed is the #1 unlock, not more LLM). **No paid Claude used** (Groq free tier throughout; a Claude Max
  *subscription* is chat/Claude-Code, not an API key, and can't clear the binding data blockers anyway).
- **Tests:** 47 geo tests green (the `annotate_impact` fix kept `test_empty_inputs_dont_crash` honest); **242
  pass** total. Re-run the grade: `python backend/research/news_impact/geo/event_study_geo.py` (uses the cached
  LLM extractions; set `ANTHROPIC_API_KEY` to prefer Claude, else free Groq gpt-oss-120b).
- **Next:** RAG geo-analogs (reuse `backend/rag/` — "this event ≈ these k past events that moved node X by Y%")
  + dashboard geo-map/node-impact table + `/api/news/geo`; optionally condition on the ACLED conflict regime;
  the bigger result-unlock is a price tape past 2026-05-24 (and a products feed for direct crack reactions).

### ✅ Geo news-impact engine — Sprint 4: GDELT corpus + ACLED feed → a MEASURED edge (2026-06-29)
Branch `phase4-live-feature-overlay` (not merged to main). A friend/desk supplied four datasets; two are
load-bearing and unblock Sprint 3's "not gradeable" verdict. Copied into `backend/data/research/news_impact/geo/`
(committed): `gdelt_oil_news_corpus.csv` (3,564 headlines, **2026-03-30→06-23**, the Iran/Hormuz war),
`acled_conflict_{daily,monthly}.csv` (political-violence counts for the oil bloc, 2021→2025-06).
- **`geo/datasets.py` — GDELT ingest.** `load_gdelt_corpus()` parses the CSV; `gdelt_events(until=)` runs the
  geo-candidate prefilter → extraction (fallback by default; cached) → impact_map → event dicts. The window
  **before the price tape's last settle (2026-05-26)** is both geo-dense and price-covered — exactly the sample
  the event study lacked. `event_study_geo._gather_events` now **prefers GDELT** (`source="auto"`) and falls back
  to the live corpus. Result: **30 gradeable events / 216 node-claims** (was 5/22), 2026-03-30→05-23, asset-mix
  chokepoint 26 / producer 5 / refinery 3 (Hormuz-dominated, as expected for the war).
- **Graded verdict — the engine's first MEASURED edge.** Directional hit-rate (binomial vs 50%):
  **`ho_crack` (ULSD/distillate crack) +5d = 71% for chokepoint events (n=35, p=0.017 → *EDGE*)**, 69% all-events
  (n=39, p=0.024); economically sound — a Hormuz/Red-Sea closure tightens diesel/distillate (longer voyages +
  feedstock fear), and it shows up over **days, not intraday** (the +1d slice is flat). Magnitude beta corroborates
  weakly (brent_structure +5d β=+0.34 t=1.69). **Honest caveat:** `brent_flat` is *anti-signed* @5d (hit 0.38)
  and overall directional accuracy is ~coin-flip (0.53, p=0.37) because the **keyword fallback can't distinguish
  "Hormuz closes" from "Hormuz reopens"** — both contain the asset + a disruption word, so crude-flat *direction*
  is inverted across the war's escalation→de-escalation arc. This is precisely the event-polarity error **LLM
  extraction fixes** (the impact_map already flips restart/opec_hike; the *keyword* event-typing is the weak link).
  So the selective read: trust the **distillate-crack** call (proven edge), abstain on crude flat under keyword
  extraction. Cached to `geo_event_study.json`.
- **`geo/conflict.py` — ACLED geopolitical-risk channel.** `load_conflict(freq)` + `bloc_intensity()` +
  `conflict_regime(country, asof=)` (causal trailing-window z-score → HIGH/NORMAL/LOW; Iran now **z≈58 HIGH** off
  the war spike 8→443) + `oil_conflict_study()`. **Graded:** monthly oil-bloc conflict count vs same-month Brent
  move over 2021-2025 (n=53) is **essentially uncorrelated** — corr −0.17 (level) / 0.03 (Δ) / 0.11 (Iran Δ). So
  ACLED is a useful **regime descriptor** (it correctly flags the Iran war as HIGH) but **not a tradeable monthly
  oil signal** — the market prices specific supply-threatening events (Hormuz), not generalized violence counts.
  Available as a conditioner for the geo nodes (next sprint can slice the event study by conflict regime).
- **Tests:** +11 hermetic (`tests/test_geo_datasets.py` — GDELT parse + event resolution + until-cap; event-study
  source preference [GDELT-first / corpus-fallback] via monkeypatch; ACLED bloc-intensity sum, conflict-regime
  spike→HIGH + empty→UNKNOWN, oil-study graceful-without-data; real-data integration skipif). **242 collected**
  (was 231). Standalones: `python backend/research/news_impact/geo/{datasets,conflict,event_study_geo}.py`.
- **Next:** wire **Groq/Claude extraction** over the GDELT corpus (fixes the closure-vs-reopen direction error and
  should lift the crude-flat + structure slices the keyword pass inverts; Groq 70b daily cap was exhausted today —
  retry when it resets, or use 8b) → re-grade; then RAG geo-analogs + the dashboard geo-map/node-impact table;
  optionally condition the event study on the ACLED conflict regime.

### ✅ Geo news-impact engine — Sprint 3: per-node empirical event study (graded) (2026-06-29)
Branch `phase4-live-feature-overlay` (not merged to main). The empirical layer, in the inventory-framework
tradition: does location-news actually move each price node? New **`backend/research/news_impact/geo/
event_study_geo.py`**:
- **Measurement (pure, testable).** `fwd_change(series, ts, h)` anchors on the node settle strictly BEFORE a
  headline's date and measures the close-to-close move H trading days later (H∈{1,5}), vol-normalised by the
  node's trailing-20d Δ-vol; staleness-guarded. `build_event_panel()` resolves corpus headlines → geo events
  (extract → impact_map node vector), and emits one row per (event × claimed node): conviction, pred_sign,
  per-horizon Δ / aligned vn / hit.
- **Grading (mirrors `inventory_impact/accuracy.py`).** `node_hit_table()` = directional hit-rate per node, and
  per node×asset_type / node×regime, binomial vs 50% (`P_SIG=0.10`, `MIN_N=20`, report floor 8); `node_betas()`
  = per-node OLS of the vol-normalised move on signed conviction (measured at |t|≥2). `compute_and_cache()` →
  `geo_event_study.json`. **`annotate_impact(impact, asset_type, regime)`** is the prior-then-learn consumer:
  tags each live node claim with the most-specific *significant* historical slice (`tradeable`) or leaves it
  `prior` — the same selective-confidence design as the inventory accuracy layer.
- **Graded verdict — NOT measurable yet (honest, n far too thin).** Only **5 events / 22 node-claims** land in
  the price-covered window: the 2021 GDELT backfill is geo-sparse under keyword extraction, and the geo-rich
  live corpus is all **2026-06**, which **postdates the /Data tape (ends 2026-05-26)** so there's no forward
  price to grade it against. Result: hit **0.46@1d (p=0.83)** / **0.59@5d (p=0.52)** — no edge, every node stays
  on the impact-map prior. This is the truthful "pipeline is the deliverable, data is the constraint" outcome
  (cf. the news-impact Sprint-2 verdict). **Recall lift this sprint:** added 4 GLOBAL **generic assets**
  (refinery/crude-pipeline/product-pipeline/tanker — last-resort `registry.resolve_generic`, attached only when
  no *named* asset matched, so "Port Arthur refinery" is never double-tagged) + an Ever-Given→Suez alias; this
  raised gradeable events 1→5. **The clear unlocks:** (1) **Claude extraction** (the keyword fallback resolved
  only 5 of the price-covered geo headlines — Claude recovers far more across 2021-2025); (2) a **price-covered
  corpus backfill** (resume GDELT for 2021-2025 geo themes); (3) a **refreshed price tape** past 2026-05-26 so
  the rich live geo events become gradeable.
- **Tests:** +6 hermetic (`tests/test_geo_event_study.py` — fwd-change direction/staleness, panel hit+regime
  assembly, **hit-table flags a real synthetic edge** + coin-flip stays insignificant, beta measured when move
  tracks conviction, `annotate_impact` prior-then-learn + most-specific-slice preference, empty-input safety).
  The machinery is proven to detect an edge on synthetic data even though the real corpus can't supply one yet.
  **231 tests collected** (was 225). Standalone grader: `python backend/research/news_impact/geo/event_study_geo.py`.
- **Next:** RAG geo-analogs (reuse `backend/rag/` — "this event ≈ these k past events that moved node X by Y%");
  dashboard geo-map + node-impact table; live scheduler wiring of the extractor; then re-grade once Claude
  extraction + a price-covered backfill land enough events.

### ✅ Geo news-impact engine — Sprint 2: LLM geo-extraction + impact map (2026-06-29)
Branch `phase4-live-feature-overlay` (not merged to main). Second sprint: turn a headline into a structured geo
event and score it into a signed price-node vector — the extraction + interpretable-prior layers on top of
Sprint 1's registry/nodes. Two new modules in `backend/research/news_impact/geo/`:
- **`impact_map.py` — (asset × event × severity) → node vector.** Composes the registry `disruption_bias`
  (sign for a supply-REDUCING event) with **event polarity** (`event_polarity`: disruptive→+1 keeps sign,
  restart/expansion/opec_hike→−1 FLIPs, unknown→0 = no claim) × **severity** (minor .5 / moderate 1 / major 1.5
  / severe 2) → a bounded directional **conviction** per node (±3, NOT a % move — the event study supplies
  magnitude later). `impact_vector(asset, event, sev)` + `headline_impact(assets, event, sev)` (sums across the
  assets a headline names, clamps, emits contributors + a human rationale) + `explain()`. Verified desk-correct:
  Hormuz closure → brent_flat ↑↑ / brent_structure ↑↑ / wti_brent ↓↓ / cracks ↑; Port Arthur fire → ho_crack ↑↑
  / wti_flat ↓; **restart and opec_hike produce exact sign flips**; Druzhba+Russia sanction sums then clamps.
- **`extract.py` — headline → {assets, event_type, severity}.** **Claude structured-output primary**
  (`messages.parse` with a Pydantic `GeoExtraction`; `LIVE_MODEL=claude-haiku-4-5` for live, `BACKFILL_MODEL=
  claude-opus-4-8` for the one-time corpus relabel — Batches-API 50%-off backfill noted as the next refinement),
  the model returns registry ids + raw locations + event/severity; ids are **validated against the registry and
  unioned with a keyword `registry.resolve`** (the LLM proposes, the registry disposes). **Deterministic
  fallback** (registry alias resolve + inflection-tolerant event/severity keyword passes + OPEC member-plus-verb
  inference) means it never hard-fails and runs with **no API key** (mirrors `classify.py`). `score_headline_geo()`
  is the headline→{extraction, impact} entrypoint the event study / dashboard will consume. Lazy `anthropic`
  import; `anthropic>=0.40` added to `requirements.txt` (optional, gated on `ANTHROPIC_API_KEY`). Verified on
  fallback: "Houthi drone strike…Red Sea"→bab_el_mandeb/attack→gasoil_crack ↑↑; "Jamnagar…resumes"→restart
  (flips cracks down); non-oil → no assets / no claim.
- **Tests:** +17 hermetic (`tests/test_geo_impact_map.py` ×8 — polarity, severity ordering, chokepoint/refinery
  signs, outage↔restart + opec cut↔hike flips, unknown-event no-claim, multi-asset sum+clamp, empty cases;
  `tests/test_geo_extract.py` ×9 — fallback resolve, inflection [resumes/halted], severity detection, non-oil
  empties, OPEC member+verb, score integration, asset validate+union, Claude orchestration via monkeypatch [no
  network], no-key short-circuit). **225 tests collected** (was 208). Standalones:
  `python backend/research/news_impact/geo/{impact_map,extract}.py`.
- **Next:** per-node empirical event study (reuse the inventory-framework "when it mattered" methodology over the
  HO/Gasoil intraday tapes — measure each node's forward move on resolved geo-events, prior-then-learn gate +
  directional hit-rate, so the conviction vector earns measured magnitudes where history proves an edge) →
  RAG geo-analogs → dashboard geo-map + node-impact table → live scheduler wiring of the extractor.

### ✅ Geo news-impact engine — Sprint 1: asset registry + price-node builder (2026-06-29)
Branch `phase4-live-feature-overlay` (not merged to main). First sprint of the **geospatial oil-news impact
engine** (full plan: location-aware news → physical asset → price nodes/spreads → directional impact, gated by
regime, prior-then-learn, with RAG analogs — agreed scope across chokepoints/refineries/pipelines and
all priceable products/spreads). This sprint builds the two foundations everything else regresses against.
New package **`backend/research/news_impact/geo/`**:
- **`registry.py` — the asset reference layer.** 37 curated assets (**7 chokepoints** Hormuz/Bab-el-Mandeb/
  Suez/Malacca/Turkish+Danish Straits/Panama; **16 refineries** Jamnagar/Port Arthur/Pernis/Jurong/…; **6
  pipelines** Druzhba/CPC/Keystone/Colonial/TMX/Forcados; **8 fields+producers** Ghawar/OPEC/Russia/Iran/…),
  each with static facts (type/region/lat-lon/capacity/carries) + a signed **`disruption_bias`** over 7
  canonical NODES (the desk prior for how a supply-REDUCING event moves each node; restart/expansion flips it).
  **Sign convention is asset-type-specific** (the core thesis): a crude chokepoint is bullish crude flat +
  backwardation; a refinery outage is *bearish crude, bullish cracks*; a reroute chokepoint (Red Sea) is
  strongly bullish the gasoil crack. Deterministic `resolve(text)` keyword pass (longest-alias-wins) + alias
  index — the baseline matcher the LLM geo-extractor will later supersede but resolve *against*. 157 aliases.
- **`nodes.py` — the price-node builder.** Daily node panel from the /Data tape: `brent_flat`, `wti_flat`,
  `wti_brent`, `brent_structure` (M1-M12), `brent_m1_m2`, `brent_fly_123`, and the **product nodes** —
  `ho_crack` (HO×42 − WTI = US ULSD/heating distillate crack), `gasoil_crack` (Gasoil÷7.45 − Brent = ARA
  distillate crack), `regrade` (Gasoil − ULSD $/bbl). **Unit conversions verified against the lake** (HO
  ≈$2.47/gal, Gasoil ≈$733/tonne, crude $/bbl → cracks land ≈$30) + a cents/gal autoscale guard. HO/Gasoil/WTI
  daily settles are SYNTHESISED (last 1-min mid/session, like `get_wti_settlements`) and flagged ESTIMATE; pure
  `compute_nodes()` is I/O-free + unit-tested. **Honest GAP register** (declared, not faked): `rbob_crack` (no
  gasoline curve), `brent_dubai` (no Dubai/sour curve), Cushing/grade diffs — the products/sour-feed unlocks.
  Verified on /Data: 3,167 days 2016→2026, medians ho_crack +$31.96 / gasoil_crack +$21.97 / regrade −$6.88 /
  wti_brent −$3.83 / brent_structure +$3.02 — all desk-plausible.
- **Tests:** +13 hermetic (`tests/test_geo_registry.py` ×8 — integrity, every type populated, chokepoint/refinery
  bias-sign correctness, longest-alias specificity, empty/no-match, alias→asset integrity, event-type partition;
  `tests/test_geo_nodes.py` ×5 — crack/regrade math, cents autoscale, partial-input omission, gap register
  disjoint+documented, real-/Data plausibility band [skips without the lake]). **208 tests collected** (was 195).
  Standalones: `python backend/research/news_impact/geo/{registry,nodes}.py`.
- **Next sprints** (sequence): geo-extraction (LLM: Opus-4.8-batch backfill / Haiku-4.5 live, resolve against the
  registry) → impact_map (asset_type × event_type → node signs) → per-node event study (reuse inventory-framework
  "when it mattered" methodology over the HO/Gasoil intraday tapes, prior-then-learn gate + directional hit-rate)
  → RAG geo-analogs (reuse `backend/rag/`) → dashboard geo-map + node-impact table.

### ✅ Inventory — actual EIA number pulled LIVE from the EIA v2 API (2026-06-25)
Branch `phase4-live-feature-overlay` (not merged to main). User: "take actual and correct EIA data after the
release from the live feed." The reaction grade was anchoring on the static investing.com consensus-CSV scrape
(and earlier an API/industry proxy). Now the **ACTUAL is sourced from the authoritative live EIA Weekly Petroleum
Status Report (EIA v2 API)**, force-refreshed after each release, with the consensus from the history CSV.
- **`eia_report.refresh_report(force, min_interval_hours=6)`** — pulls the report live from the EIA v2 API and
  re-caches `eia_report_history.parquet`; throttled to one live pull / 6h (the report is weekly) unless forced;
  no-ops without `EIA_API_KEY`. **`latest_release(series, refresh=False)`** now anchors the ACTUAL on the live
  EIA report (`weekly_frame`) where it carries the week — `actual_source="eia_api (live)"` — pairing it with the
  real consensus; it falls back to the CSV scrape (`actual_source="consensus_csv_scrape"`, which equals the EIA
  print) only while the API hasn't yet published that week. `assess_release`/`assess_series` add `actual_source`
  (default path reads the EIA-API-backed `weekly_frame` → "eia_api (live)"; "supplied" when a number is passed).
- **Scheduler `_eia_report_refresh`** (app.py, ~2 min after boot then every 6h, opt-out
  `PULSE_EIA_REFRESH_DISABLED=1`) keeps the cached report current with the live EIA actual, so the Wed 10:30-ET
  release is reflected within hours; the reaction route also accepts **`?refresh=1`** for an on-demand throttled
  pull. **Verified live:** the EIA API published week ending **2026-06-19** with crude actual **−6,088 MBBL**
  (was missing from the stale parquet, latest 06-12); reaction route now reports `anchored_on / actual_source =
  "eia_api (live)"`, actual −6,088 vs consensus −3,900 = −2,188 surprise.
- **Dashboard:** `InventoryReactionPanel` "Our call" block gains an **EIA-actual provenance line** — the actual +
  consensus + a `● EIA API · live` (or `◌ scrape` fallback) chip + the week-ending — so the desk sees the number
  it's graded against came from the EIA feed, live.
- **Tests:** +3 hermetic (`latest_release` prefers the live EIA actual; falls back to the scrape when the API
  lags; `refresh_report` throttle + no-key no-op). **195 pytest green** (was 192). Frontend `tsc` + `vite build`
  clean. Server restarted; reaction route verified anchoring on the live EIA actual.

### ✅ Inventory — directional accuracy backtest + selective confidence ("best results") (2026-06-25)
Branch `phase4-live-feature-overlay` (not merged to main). User asked to "do everything to fix accuracy — I want
THE BEST results" after the real-consensus re-anchor made a single print's directional call grade as *wrong*. The
honest fix is **precision over recall**: stop judging on one print, measure the directional hit-rate across the
whole 2015-2026 history (on the real-consensus surprise), and make the framework **commit a directional call only
in the (series × regime × surprise-size) cells where it beat a coin flip with a real binomial p-value** — abstain
everywhere else, and redirect conviction to the series/regime that carries the edge. New
**`backend/research/inventory_impact/accuracy.py`** + wiring through `framework.py` / `app.py` / the dashboard.
- **The measured edge map (real-consensus surprise → release-day direction, binomial vs 50%):**
  - **CRUDE flat:** HIGH-stocks/glut **74.6%** (n=59, p≈0.000), **81%** on big |z|≥1 surprises (p≈0.007); contango
    **60.4%** (p≈0.012, 67.9% big); 2015-20 glut era **61%** (p≈0.001). **BUT tight/LOW/backwardation ≈ 52-54%,
    not significant — a coin flip.** Today's regime is LOW-stocks/backwardation → **abstain on crude flat.**
  - **GASOLINE flat:** **57% in backwardation** (n=381, p≈0.008), **63-68% on big surprises** (p<0.001) — a real
    edge in *exactly* today's regime, where crude is noise. So the live call **redirects to gasoline.**
  - **DISTILLATE** weak (~54%, summer off-season); **WTI flat / WTI-Brent** ≈ 50% (2021+ data only = tight regime
    only, no edge). Consistent with the whole framework thesis: inventories bite in a glut, not when tight.
- **`accuracy.py` API.** `hit_rate_table(series, target)` (per-regime hit% at all + big sizes, lru-cached);
  `applicable_hit_rate(series, bucket, contango, inv_pct, z)` — among the cuts the live regime belongs to, picks
  the **strongest significant** cell (the calibrated confidence) or, if none clears the bar, the broadest honest
  cell flagged `tradeable=False`; `best_series_now(...)` ranks crude/gas/distillate by their proven edge today and
  recommends one (or None → "trade the spread/quality, not the flat"). `accuracy_summary(series)` bundles it for
  the API. Honest scope: **full-sample DESCRIPTIVE hit-rates** (regime characterisation + binomial test), not a
  walk-forward P&L; the conditioning regime is read live.
- **Confidence now leads with the hit-rate.** `framework._confidence_from`: HIGH only when this series/regime has
  a *proven* edge (`significant`) AND the surprise is big; MEDIUM on a proven edge OR a sensitive regime/big-
  confirmed surprise; LOW (abstain on the flat direction) otherwise. `assess_release`/`assess_series` add
  `tradeable`, `historical_accuracy`, `best_series_now` to the call.
- **Intraday event study re-fit on real consensus** (`event_study.build_panel` now uses the consensus surprise;
  `event_panel.parquet` rebuilt, 281 releases). Betas @30m stay near-zero/insignificant (t<1) — correct: the
  1-min era is 2021+ = all tight regime, so there is **no intraday edge to manufacture**, on proxy or real
  consensus. Corroborates the daily finding rather than overturning it.
- **Dashboard (Inventory tab).** (1) `InventoryImpactPanel` — a **track-record card** above the hero: the
  applicable hit-rate (big % number), a `✓ TRADEABLE` / `⊘ COIN FLIP — ABSTAIN ON FLAT` chip, and a **redirect
  banner** ("↪ Trade Gasoline today — proven 57% edge; crude flat is a coin flip here"). (2) `InventoryFrameworkPanel`
  — a **per-regime directional track-record table** (hit% · n · p · big-|z| · ✓edge/coin-flip) so the desk sees
  *where* the call can be trusted. New `accuracy` block on `/api/regime/inventory`.
- **Why this is the real fix (for the user's question):** accuracy didn't actually fall when the data improved —
  the old API-proxy "win" was luck from a wrong-signed number. You can't measure accuracy from n=1; over history
  the call is genuinely **75-81% in a glut and a coin-flip when tight**, so the BEST result is to be *selective* —
  right far more often *when we choose to commit* — and to point the desk at the series (gasoline) that actually
  has an edge in today's regime instead of forcing a crude-flat call that history says is noise.
- **Tests:** +5 hermetic in `tests/test_inventory_impact.py` (hit-direction logic, applicable picks the
  significant cut, best-series redirect, all-coin-flips→None, dual-import-safe monkeypatch on
  `acc.regime_conditioning`). **192 pytest green** (was 188). Frontend `tsc` + `vite build` clean (only the
  pre-existing TS5101 `baseUrl` deprecation). Server restarted; dashboard verified serving the new bundle +
  accuracy surfaces live.

### ✅ Inventory item 3 — real consensus surprise + API nowcast wired (2026-06-25)
Branch `phase4-live-feature-overlay` (not merged to main). Turned the staged datasets below into the live surprise:
the framework now defaults to **surprise = actual − REAL analyst consensus** (with the seasonal proxy as a per-week
fallback) across all 3 series, plus the **API crude leading indicator** as a pre-release nowcast and a re-anchored
live reaction grade. Files: `eia_report.py` (loaders + `method="consensus"`), `regime_conditioning.py`
(`consensus_sharpening_compare()` + default method), `framework.py` (nowcast + labels), `app.py`
(`/api/regime/inventory[/reaction]`), frontend `Inventory{Impact,Framework}Panel.tsx` + `InventoryView.tsx`.
- **Real-consensus surprise (all 3 series).** New `eia_report._load_consensus_csv(series)` parses the investing.com
  history (×1000 → MBBL, drops empty-forecast `:29/:25` split rows, de-dupes the one holiday-stray week, keys by the
  **prev-Friday** week-ending). **Validated:** the CSV's own `actual` matches the report parquet's `actual_change` to
  **median 0 / 99%+ within 200 MBBL**, proving the alignment. `surprise_series(series, method="consensus")` →
  `actual − consensus`, seasonal fallback where a week has no consensus row, + an honest **`expected_source`** column
  (`consensus` ~97% of weeks vs `seasonal_fallback`). `framework`/`regime_conditioning`/the API all default to it.
- **Graded verdict (item 3 deliverable): real consensus SHARPENS the "when it mattered" signal.** Re-fit on the real
  surprise, **9/10 regime cuts get a bigger |t|** than the seasonal proxy (the only one that doesn't is the already-
  null 2021-26 era), **5/5 of the cells where inventories should bite**, significant cuts **4 → 5**. Key betas:
  ALL-releases t **−1.71 → −2.48** (now significant); HIGH-stocks (glut) β −1.03/t −3.36 → **β −1.14/t −3.89**;
  above-5yr glut t −3.05 → −3.54; contango front t −2.06 → −2.36; 2015-20 glut era t −2.94 → **−3.79**. The
  tight/backwardation cells **stay null** (LOW-stocks t −0.17 → −0.65, still « 2). So removing the proxy measurement
  error tightens exactly the glut/contango regime where the thesis says inventories bite while leaving the noise
  cells noisy — confirming the headline is **not a seasonal artefact**. Surfaced as `consensus_sharpening` on
  `/api/regime/inventory` + a per-series table in `InventoryFrameworkPanel`. (Per-series honesty: crude sharpens
  9/10, gasoline only 4/10 — the seasonal proxy was already a faithful stand-in for gasoline consensus.)
- **API nowcast (pre-release input).** New `eia_report._load_api_crude()` + `api_nowcast(week_ending)` expose the Tue
  API crude print (corr **0.77** w/ the EIA actual, 2019+ coverage) for the upcoming EIA week; `next_release_context`
  surfaces the API actual + a labelled **50/50 blend with the seasonal expectation** (clearly NOT the EIA number —
  the real consensus arrives Wednesday). Rendered as a blue pre-release card in `InventoryImpactPanel`.
- **Re-anchored live reaction grade on the REAL printed EIA actual.** `eia_report.latest_release(series)` returns the
  freshest printed actual+consensus from the history (one week ahead of the report parquet); the reaction route
  auto-anchors on it when the caller supplies nothing (`anchored_on="real_eia_print"`), and the frontend stopped
  hard-coding the API proxy. **This flips a sign:** 24-Jun crude **actual −6.088M vs consensus −3.900M = −2,188 MBBL
  bullish** surprise (bigger draw than expected), where the old API-proxy actual −0.765M gave a +3,135 *bearish*
  surprise — the proxy had the wrong sign.
- **Tests:** +8 in `tests/test_inventory_impact.py` (parse/prev-Friday primitives, consensus↔parquet alignment,
  consensus-method surprise + source flag ×3 series, latest_release, API nowcast covered/uncovered, no-CSV →
  seasonal fallback, sharpening hermetic + None-without-consensus). **188 pytest green** (was 178; +8 here, +2
  elsewhere). Frontend `tsc` + `vite build` clean (only the pre-existing TS5101 `baseUrl` deprecation). New consensus
  panels committed (`daily_panel_{,gasoline_,distillate_}consensus.parquet`). **Still open** (next-session): re-fit
  the intraday event study on the real surprise too; a real pre-2021 WTI daily settlement (gotcha 11) for the WTI
  glut regime; Cushing consensus (investing carries none).

### 📥 Real EIA consensus + API leading-indicator history staged (✅ now wired — see entry above) (2026-06-25)
User scraped investing.com event histories (DOM scrape — the old `more-history` AJAX endpoint now 404s; logged-in,
manually-expanded, then read the rendered table) into `backend/data/research/inventory_impact/`. **Four datasets, all
`actual / forecast(=consensus) / previous` in millions of bbl** (loader must ×1000 → MBBL thousands; drop the 1-2
empty-forecast mis-dated `:29/:25` split rows per file; parse `release_date` as `%d-%m-%Y`):
- `eia_consensus_history.csv` — **crude (ex-SPR)**, 548 wk 2015-12→2026-06, 99% forecast, surprise std ≈4.8M bbl.
- `eia_consensus_gasoline.csv` — **gasoline**, 548 wk, 98% forecast, std ≈2.6M, `prev[t]≈actual[t-1]` to 14 MBBL.
- `eia_consensus_distillate.csv` — **distillate**, 558 wk 2015-10→2026-06, 98% forecast, std ≈2.4M, clean to 7 MBBL.
- `api_crude_history.csv` — **API weekly crude** (the Tue leading indicator), 389 wk 2019-01→2026-06. Forecast sparse
  (73% — use the API **actual**, not its consensus). **Validated as a real leading indicator:** asof-aligned to the
  EIA print, corr(API actual, EIA actual)=**0.77**, and API actual predicts the EIA **consensus surprise** at
  corr **0.64** / slope **0.63** (n=383) — the Tue API release front-runs the Wed EIA number.
**Not yet wired** — input for item 3 (sharpen the nowcast): add a `method="consensus"` path to
`eia_report.surprise_series` (all 3 series) so `surprise = actual − consensus` across history; feed the API actual as a
nowcast feature for the upcoming EIA print; re-fit the regime study on the real surprise; re-anchor the live reaction
grade on the real printed EIA actual (24-Jun crude −6.088M). Cushing skipped (investing carries no Cushing consensus;
levels already come from the EIA API). Next-session work.

### ✅ Inventory: "when it mattered" re-run vs WTI (2026-06-25)
Priority item 1 of the inventory-improvement backlog. The regime "when-it-mattered" study (`surprise_z → release-day
return`, sliced by inventory/curve regime) was Brent-based; US crude inventories are a US signal, so WTI *should*
be the sharper benchmark. Re-ran the study with `ret_wti` as the target alongside Brent + a matched-window
comparison. Files: `regime_conditioning.wti_sharpness_compare()` + WTI table in `to_results`/`__main__`;
`/api/regime/inventory` gains `when_it_mattered_wti` + `wti_compare` (crude-only); `InventoryFrameworkPanel` renders
the WTI table (gold) + a matched-window verdict table.
- **Graded verdict: regime conditioning is NOT sharper on WTI flat returns — but not because WTI under-reacts.**
  The synth WTI settlements start 2021 (`data_lake.get_wti_settlements()`), so the WTI panel is **281 rows, 2021-26
  only** vs Brent's 535 (2016-26) — and has **zero glut/HIGH-stocks rows** (matched window = 260 LOW + 21 AVG, no
  HIGH). The headline Brent signal (HIGH stocks β −1.03, t −3.36, R² 0.17) lives in a regime that **predates the WTI
  series**, so it simply can't be reproduced on WTI flat returns.
- **What the matched 2021-26 window DOES show (both benchmarks in the same tight regime):** both flat reactions are
  statistically null (no |t|≥2), but **WTI is correctly signed in 3/4 cuts (build → price down) where Brent
  perversely flips positive in 0/4** — WTI behaves like the textbook US-inventory benchmark. The sharpest matched
  cut is **AVG stocks: WTI β −0.51, t −1.54, R² 0.111** vs Brent β +0.11, t 0.30; and the **US-specific WTI-Brent
  spread** at AVG stocks (β −0.37, t −1.80, R² 0.145) is the closest thing to significance anywhere in the matched
  window — exactly where a US-crude surprise should show up. The 17× WTI/Brent flat-beta ratio quoted in the prior
  entry is a *within-tight-regime intraday-spread* result (event study), not a daily-flat-return regime result.
- **Honest limit + unlock:** the daily flat-return "glut bites" headline stays **Brent-only** until a real pre-2021
  WTI daily settlement file exists (gotcha 11 — current WTI is synth from 1-min mids, 2021+). That swap-in would let
  the WTI study cover the glut regime and properly test the "WTI is sharper" thesis on flat returns.
- **Tests:** +2 (`test_wti_sharpness_compare_hermetic` — synthetic panel, sign/sharper/spread-beta logic + verdict;
  `test_wti_sharpness_compare_returns_none_without_wti`). **178 pytest green**, frontend `tsc`+`vite build` clean
  (only pre-existing TS5101 `baseUrl` deprecation). Branch stays `phase4-live-feature-overlay` (not merged to main).

### 🩹 Live signal feed "stuck at 18 Jun" — health gate over-rejected OOS-unvalidated cells (2026-06-25)
**Not a feed problem** — `live_feed` reads live to today. The **signal log** froze because: the curve softened
from strong BACK (m1_m12 ~+7) to mild backwardation (~+2/+3) → regime **NEUTRAL** → the per-spread gate turns off
→ every spread falls to the **global baseline** model, whose OOS stats (`r2_oos`, `band_hit_rate`) are `None` for
cells the held-out test window didn't cover. `model_health.check_cell` treated *unmeasured* the same as *failed*
→ hard NEUTRAL on everything → nothing actionable logged once the regime left BACK. **Fix:** split health checks
into **HARD** fails (incoherent quantiles, out-of-distribution, thin training, measured-but-bad stats → NEUTRAL)
vs **SOFT** fails (stats merely *unmeasured* → `degraded`). A coherent, well-trained cell now trades at a capped
z-based confidence with a `model_health_degraded` flag instead of being silenced; `live_ranker` honours it.
Verified: live rec now emits `wti_fly_123 SELL` (z=0.87, conf 0.21) at the current timestamp; the signal log
advances to today. Genuinely incoherent cells (e.g. `brent_m1_m2` with p10>p50) still abstain. **Caveat:** these
NEUTRAL-regime signals are degraded/low-confidence by design.

### ✅ News tab went live (wire → corpus → impact) + live-headlines strip (2026-06-25)
The Impact feed was scoring only the 2021 backfill. New scheduler job `_news_corpus_ingest` (app.py, every
`TTL_NEWS`, opt-out `PULSE_NEWS_IMPACT_DISABLED=1`) pipes the cached `/api/news` wire → `corpus.upsert_articles`
→ `classify.classify_corpus`, so the corpus grows with today's headlines and the feed scores them (corpus span
now reaches 2026-06). `impact_feed` gained `order="recent"` (live API leads with newest, NOISE excluded). New
**`LiveHeadlinesPanel`** (raw wire, each headline scored via `/api/news/live` + `impact.live_scored` — factor
from corpus-by-url else keyword, GDELT compact-ts normalised) at the top of the News tab + a **Time·UTC column**
on the Impact feed + a **Refresh-news button** (async `/api/news/refresh`, lock-coalesced). Alert toasts bumped
to 30/18/10s. Groq key wired in `.env` (gitignored). `trade_idea` cot-crash fixed earlier (isinstance guard).

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
- **Live feed wiring (the News tab is now actually live):** a scheduler job **`_news_corpus_ingest`** (app.py,
  every `TTL_NEWS`, opt-out `PULSE_NEWS_IMPACT_DISABLED=1`) pipes the cached `/api/news` wire → `corpus.upsert_articles`
  → `classify.classify_corpus` (dedup on URL, classifies only the new rows), so the corpus grows with today's
  headlines and the Impact feed scores them. `impact_feed` gained `order="recent"` (the live API now leads with
  the **newest** headlines, not the highest-impact historical ones) and **excludes NOISE** (the impact feed is
  "what's worth something"; the raw tape lives in the new panel). Verified end-to-end: 40 live headlines
  ingested → corpus span now extends to **2026-06-24**, feed leads with today's oil headlines scored
  (GEOPOLITICAL measured). **Two new frontend surfaces on the News tab:** **`LiveHeadlinesPanel`** (raw current
  wire, unscored, NewsAPI/GDELT/marketaux, top of tab) + a **Time·UTC column** on the Impact feed.
- **Tests:** +2 (`test_corpus_theme_set_is_oil_only`, `test_impact_feed_recent_order_leads_with_newest`);
  **171 pytest green**, frontend `tsc`+build clean. Branch stays `phase4-live-feature-overlay` (not merged to main).

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
17. **Products OHLCV feed** (`I:\Public\Summer Interns Energy\OHLCV`, override `PULSE_OHLCV_DIR`) — hourly
    continuous contracts c1..c12 for RBOB/HO/LGO/LCO/CL, read by `geo/products_feed.py`. RBOB is 2019→2026 (the
    gasoline curve → `rbob_crack`); HO/LGO/LCO/CL are only ~2026-04-30→06-26 but extend the node tape past the
    lake's 2026-05-26 settle (`nodes.build_node_panel` appends only the post-lake tail). **Pandas gotcha when
    parsing:** build the OHLCV columns from `.to_numpy()` before attaching the datetime index — passing
    `index=ts` while the columns keep their 0..N integer index makes pandas align on mismatched labels and
    silently NaN every row.

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
