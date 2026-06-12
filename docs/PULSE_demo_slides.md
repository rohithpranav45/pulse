# PULSE Demo Slides — Mentor Walkthrough

10-slide outline. Copy each block into PowerPoint / Google Slides. Suggested theme: dark navy background (`#0F172A`), white text, gold accent (`#F5A623`) for emphasis numbers.

Live URL (today, quick-tunnel): **https://jacket-army-appointed-racing.trycloudflare.com**

⚠ Quick-tunnel URL changes if cloudflared restarts. Upgrade to named tunnel once admin access is granted (see CLAUDE.md → Deployment).

---

## Slide 1 — Title

**PULSE Energy Intelligence Terminal**

Regime-Based Spread & Butterfly Engine
Futures First Internship · June 2026

Live demo: https://jacket-army-appointed-racing.trycloudflare.com
Best in Chrome

---

## Slide 2 — Phase 1 Recap: What's Already Live

- **35 live data streams** — prices, curve, EIA fundamentals, COT, GDELT news, OVX, weather, tankers, analogs
- **9-indicator weighted signal engine** (directional Brent / WTI / Henry Hub)
- **Groq LLaMA-3.3-70B morning brief** with Ollama + rule-based fallback
- **Paper trading sandbox** — SQLite-backed, MTM every minute, TP/SL auto-close
- **Production hardening** — Sentry + Better Stack observability, Pydantic typed API contracts, DuckDB/Parquet data lake

*Shipped as PR #2 · 5,699 lines · Mentor-reviewed ✓*

---

## Slide 3 — Phase 2 Thesis: Regime-Conditional Spread Engine

**WHY**
Rolling z-score baseline ignores market regime — the same spread can mean-revert quickly in backwardation but persist for weeks in contango. One model per (spread, regime) cell beats one model per spread.

**HOW**
Classify each day into one of 27 composite regimes (curve × inventory × vol). For each (spread, regime) cell, run a 7-model competition and pick the winner by 5-fold CV R².

**WHAT**
Ranked spread/butterfly opportunities surfaced with fair value, confidence band, and historical analogs — pushed directly to the paper trading book.

---

## Slide 4 — 27-Cell Composite Regime Grid

| Axis | Buckets | Threshold |
|---|---|---|
| **Curve** (M1–M12) | CONTANGO / NEUTRAL / BACK | ≤ −$2 / −$2..+$5 / > +$5 |
| **Inventory** (EIA WCRSTUS1 vs 5yr seasonal) | LOW / AVG / HIGH | ≤ −4 % / ±4 % / > +4 % |
| **Realised Vol** (20d Brent RV) | CALM / NORMAL / STRESSED | ≤ 20 % / 20-35 % / > 35 % |

**66 / 162 cells populated** (≥ 30 historical observations)
**Today: `BACK / LOW / STRESSED`** — backwardation + storage deficit + high vol

96 cells are economically implausible (e.g. BACK × HIGH inventory) and stay empty by design.

---

## Slide 5 — Per-Cell 7-Model Competition

**Candidates (per cell)**
Ridge · Lasso · ElasticNet · Huber · XGBoost · LightGBM · CatBoost

**Selection**
5-fold TimeSeriesSplit CV R² · sparsity tiebreak for linear ties · boosters fire only when n_train ≥ 80

**22 features**
Curve shape, curvature, inventory level + surprise, COT 156w percentile, 3-2-1 + gasoline cracks, real rate, OVX/VIX ratio, WTI-Brent spread, seasonality (sin/cos doy), lagged spreads, days to expiry

**6 spreads tracked**
Brent M1-M2 · M3-M6 · fly(M1-2M2+M3) + WTI mirrors

**Confidence bands** via Quantile p10 / p50 / p90 fit separately.

---

## Slide 6 — Walk-Forward Backtest

**10 quarterly refits, 2024-2026, 3,640 records, 2,154 signals fired**

| Mode | Gross Sharpe | NET Sharpe | Hit Rate | Mean PnL/bbl |
|---|---|---|---|---|
| Baseline 252d z | +0.385 | **+0.301** | 71.6 % | +$0.180 |
| Pooled (un-gated) | +0.437 | **+0.351** | 58.5 % | +$0.092 |
| Gated blend (current prod) | +0.384 | **+0.297** | 72.3 % | +$0.176 |

**NET** = after $0.030 / $0.040 / $0.050 round-trip costs (M1-M2 / M3-M6 / fly).

**Honest finding** — gated blend ties baseline net. The engine earns alpha on its specific slice (244 regime fires at NET Sharpe **+0.806**) but the blended headline is baseline-dominated.

---

## Slide 7 — Side Finding: Pooled Engine Wins NET

- **Pooled NET Sharpe +0.351 beats baseline NET +0.301** → **+0.05 lift, +0.05 over gated**
- Phase 2.8.1+2 boosters (XGBoost / LightGBM / CatBoost) lifted pooled gross from **+0.195 → +0.437 (+124 %)**
- The Phase 2.6 gate (added when pooled was losing) is now **over-restrictive**
- Conclusion: walk-forward says ship pooled un-gated. But we don't change production based on walk-forward alone.
- → A/B paper test launched 2026-06-11 to validate under live execution

---

## Slide 8 — Live A/B Harness

**Parallel paper books** — both arms see the SAME market each signal day for matched-pair statistical power.

- **Arm A** — `PULSE_REGIME_MODE=pooled` (un-gated)
- **Arm B** — `PULSE_GATED_BLEND=1` (current default)

**Stop criteria**
1. n_closed ≥ 30 per arm
2. AND Welch t-test p < 0.05 on per-trade NET PnL
3. Hard timeout at 14 calendar days → `undecided_timeout`

**Dedup** — one open position per (asset, direction, arm). No double-dipping on persistent signals.

**Dashboard** — `ABComparePanel` on Regime tab with verdict ribbon, per-arm KPIs, equity curve, manual TICK + RESET controls. Polls every 30 s.

*Started 2026-06-11 · Verdict expected ~2026-06-25*

---

## Slide 9 — Roadmap

**Phase 2 remaining**
- **2.8.4** — Pool to one global model with regime-as-feature
- **2.8.5** — Soft regime probabilities (replace hard thresholds)
- **2.8.7** — Multi-horizon sweep (5 / 20 / 60d) and pick per spread
- **2.8.8** — Extend walk-forward to 2018-2026 (contango coverage + composite_trades.json)
- **2.8.9** — HMM / change-point regime detection
- **2.8.10** — Portfolio-level vol targeting

**Phase 3 — production hardening**
FastAPI migration · PostgreSQL · WebSocket push · Docker + Cloudflare named-tunnel deploy with Access auth

---

## Slide 10 — Try It Now

**Live URL** — https://jacket-army-appointed-racing.trycloudflare.com

**What to look at**
- **Regime tab** → today's `BACK/LOW/STRESSED` composite regime + ranked spreads
- **Top pick today** — `BUY Brent front fly` (XGBoost winner, confidence 0.96, 19/19 active features)
- **A/B panel below** the regime card — `UNDECIDED` until the harness reaches n=30/arm
- **Paper tab** → push the top pick, watch MTM update every 60 s

**Caveats**
- Quick-tunnel demo URL — may change if my desk reboots; named tunnel coming once admin access lands
- Once-per-24h A/B scheduler tick · price feeds refresh every 60 s
- Best viewed in Chrome / Edge
