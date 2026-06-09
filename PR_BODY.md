## Summary

**Phase 2 closed end-to-end.** This branch ships a regime-conditional spread engine, a gated production rule, and an opt-in sizing experiment — landed in one PR because the sprints share the regime grids, training pipeline, and walk-forward harness. Mentor-facing methodology PDF is regenerated at `backend/data/research/PULSE_methodology.pdf` (gitignored — rebuild via `python -m backend.research.methodology_pdf`).

### Phase 2.7 headline finding (the latest sprint, called out per request)

- **The DD-compression hypothesis is DISPROVED.** The brief assumed scaling the regime leg would compress the gated blend's −271 max drawdown. It does not — max DD is baseline-dominated (regime-leg DD only −6.66 vs baseline-leg −272), so sizing the regime leg cannot move the headline DD. Sharpe also drops slightly under sizing (0.456 full → 0.434 half → 0.426 kelly) because halving the regime leg halves its mean-PnL contribution to the blend.
- **Per-spread, half-sizing genuinely lifts Brent fly_123 from Sharpe +1.833 → +2.192 (+0.43)** via variance reduction on a spread whose baseline carry is already strong (+2.34). This is the actual production-relevant win.
- **Recommendation:** keep `PULSE_GATED_BLEND=1` as the default; offer `PULSE_GATED_SIZE=half` as a per-trader opt-in (Kelly stays out of production — the 97-trade sample is too thin, brent_fly fraction 0.1445 is over-cautious).

### Walk-forward verdict (2024–2026, 10 quarterly refits, 3,640 records)

| Mode | Sharpe | Mean PnL | Hit | Max DD |
|---|---|---|---|---|
| Composite (27 cells) | +0.245 | +0.108 | 59.7 % | −52 |
| Pooled (3 curve cells) | +0.195 | +0.092 | 58.5 % | −126 |
| **Gated blend (Phase 2.6)** | **+0.456** | +0.211 | 72.3 % | −271 |
| Sized half (Phase 2.7) | +0.434 | +0.198 | 72.3 % | −272 |
| Sized kelly (Phase 2.7) | +0.426 | +0.194 | 72.3 % | −271 |
| Baseline 252d rolling-z | +0.385 | +0.180 | 71.6 % | −169 |

Regime leg alone (97 of 2,109 gated signals) carries Sharpe **+1.332** — vindicating the Phase 2.5 BACK × {Lasso, Huber} slice prediction.

### Sprints in this branch

- **0b** — Sentry + Better Stack observability, env-gated so a fresh clone still runs without secrets. 34 streams on `/api/health-detail` (was 32).
- **2a** — Dedicated REGIME tab; `RegimePickCard` moved out of `PaperView` into `RegimeView` with a 10th sidebar entry.
- **2b** — 2-leg paper trading. New `paper_legs` table records the outright decomposition of every spread/fly push; MTM + close are leg-aware; UI indents legs under the parent row.
- **2c** — Drill panel: scatter + 3 nearest analogs per pick. New `/api/regime/drill/<spread>` + `RegimeDrillModal`.
- **3** — Broadened universe + 3-axis regime grid. 6 spreads (3 Brent + 3 WTI mirrors) × 27 composite cells (curve × inventory × vol). WTI legs synthesised from /Data 1-min mids until mentor provides a real daily settlement file. EIA crude-stocks history backfilled (10y weekly + 5y seasonal cache).
- **4** — Walk-forward backtest + methodology PDF. Honest finding: the bare composite engine underperformed baseline overall.
- **2.5** — Pooled curve-axis grid (3 cells/spread, ~5× more rows per cell). Disproved the leading "more rows per cell will fix it" hypothesis but surfaced the (BACK × {Lasso, Huber} × |z|≥0.5σ) slice as the only configuration where regime conditioning beats baseline.
- **2.6** — Gated blend production rule behind `PULSE_GATED_BLEND=1`. Walk-forward third leg verifies it end-to-end (Sharpe +0.456 vs baseline +0.385).
- **2.7** — Position sizing on the regime leg behind `PULSE_GATED_SIZE=<full|half|kelly>` (see headline above). Raw `gated_trades.json` persisted so future Phase 2.8+ sizing experiments can be tested in seconds without retraining.

### Env vars introduced (all opt-in; unset = Sprint-3 default)

```
PULSE_REGIME_MODE=pooled   # un-gated pooled inference (3-cell curve-axis grid)
PULSE_GATED_BLEND=1        # Phase 2.6 production rule
PULSE_GATED_SIZE=half      # Phase 2.7 sizing (full | half | kelly)
SENTRY_DSN=...             # Sprint 0b
BETTER_STACK_TOKEN=...     # Sprint 0b
```

See `.env.example` for the full list with notes.

## Test plan

- [ ] Mentor reviews `backend/data/research/PULSE_methodology.pdf` (regenerated; verifies Phase 2.7 headline matches this PR description)
- [ ] `python start.py` boots cleanly; `/api/health-detail` shows 34 streams up
- [ ] Default behaviour (no env vars set) matches Sprint-3 dashboard — composite regime, Brent M3-M6 as top pick, 6/6 eligible
- [ ] `PULSE_GATED_BLEND=1 PULSE_GATED_SIZE=half python start.py` — UI shows `GATED BLEND` + `SIZE HALF` chips, regime-source rows carry `notional_scale=0.5`, baseline-source rows carry `notional_scale=1.0`
- [ ] `python -u -m backend.research.walkforward` regenerates `walkforward_report.json` + `gated_trades.json` and prints the four-leg + baseline summary
- [ ] `python -m backend.research.methodology_pdf` regenerates the 2-page PDF in <1 s
- [ ] `npx tsc --noEmit` clean (only the pre-existing `baseUrl` deprecation)
- [ ] `npx vite build` clean
- [ ] Phase 1 endpoints unchanged in shape (`/api/prices`, `/api/signal`, `/api/trade-idea`, `/api/paper/*`)
