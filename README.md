# PULSE

### Most trading dashboards are built to look right. This one is built to catch itself being wrong.

PULSE is an energy trading terminal — 35 data feeds, a regime-conditional model over crude
calendar spreads, a live paper book, and a React front end. Built over a trading-desk
internship at Futures First.

It also spent a week trying to lie to me, and most of what follows is about how I caught it.

**[Live demo](https://rohithpranav45-pulse.hf.space)** · **[Methodology](docs/report/PULSE_One_Page_Report.pdf)** · **[Full project state](docs/PROJECT_STATE.md)**

```bash
pip install -r requirements.txt && python start.py   # → http://127.0.0.1:5000
```

---

## The result I didn't want

Expanding-window walk-forward. 2018–2026. 34 quarterly refits. Net of costs.

| | NET Sharpe |
|---|---|
| **Regime-unaware baseline** | **+0.372** |
| Global model, regime-as-feature | +0.380 |
| Per-spread gated regime | +0.374 |
| Pooled regime cells | +0.293 |
| Data-driven HMM regimes | +0.289 |
| Vol-targeted book | +0.198 |

The entire thesis of this project is that crude spreads behave differently across curve,
inventory and volatility regimes. I built a 27-cell regime grid, ran seven models in
competition inside every cell, and tested it properly.

**A rolling z-score with no regime awareness beat all of it.**

So I tried to break that result. Collapsed the grid and fed regime as a feature — tied.
Softened the hard thresholds into logistic transitions — tied. Threw out the trader's
thresholds entirely and learned the boundaries with an HMM — worse. Vol-targeted the book —
halved the drawdown and gave up a third of the Sharpe.

Five attempts. The simple thing kept winning.

What finally worked was giving up on regime conditioning *everywhere* and asking where it had
actually earned its place. The per-spread gate enables it on exactly two instruments — WTI
M1-M2 and the WTI butterfly — and routes the other four to the baseline. That closed the gap
from +0.298 to +0.374.

Parity. Not a win. The README says so because the code does too.

---

## Three times the system caught itself lying

**The paper book was reporting +$110,179.**

It wasn't. 374 of those rows were walk-forward replay trades sized at 4,000–22,000 barrels,
sitting in the same table as the real book and drowning it. The actual live paper book was
**10 trades and −$4.26**. The headline now defaults to the live book only; the replay view is
behind an explicit flag.

**The win rate said 43.8% next to a breakdown reading 166W / 69L.**

Both were computed from the same table. The denominator included 144 break-even scratches
that the numerator excluded. Win rate is now measured over decisive trades — **70.6%** — and
scratches are reported as their own number instead of quietly dragging the headline down.

**A news factor had a t-statistic of 3.0 and got demoted anyway.**

GEOPOLITICAL cleared every significance bar I had set. It also had an 18% directional hit
rate — the t-stat came from a handful of outlier war days, not a real edge. The gate now
requires a positive beta *and* a hit rate above 50% before it will call anything "measured."
The factor falls back to a labelled prior, with the rejection reason shown on the dashboard.

There was also a thread race in the DuckDB layer that corrupted a cached frame at boot and
killed the regime engine with `KeyError c6` until someone restarted the process — silently
zeroing the A/B tick in the meantime. Thread-local cursors and validate-before-cache fixed it.
An inventory endpoint that hung for over 120 seconds now answers in 0.12.

None of this is in the repo because it went well. It is here because a system that reports its
own P&L has every incentive to flatter itself, and the only defence is to go looking.

---

## Where the edges actually are

Two survived honest grading.

**Inventories bite in a glut, not when the market is tight.** A crude surprise predicts
release-day direction 75–81% of the time when stocks are high (p < 0.01). In today's
backwardated market it is 52% — a coin flip. So the framework abstains on crude and redirects
to gasoline, which holds a real 57% edge in exactly the regime where crude is noise.

Most inventory models will hand you a crude call every Wednesday. This one tells you when not
to take it.

**Geopolitical shocks show up in distillate, not flat price.** A chokepoint disruption firms
the ULSD crack 57% of the time over five days. Crude flat price spikes on day one and reverts
by day five — the risk premium round-trips while the physical tightness persists. Trade the
crack, fade the spike.

Single episode, overlapping windows, optimistic p-values. Labelled as such wherever it appears.

---

## What is in it

```
backend/
├── app.py           Flask API — 73 endpoints + scheduler
├── data_lake.py     DuckDB over a 3.5 GB parquet lake
├── fetchers/        ~30 data-source modules
├── research/        the engine
└── schemas/         Pydantic → generated TypeScript

frontend/            React 18 · Vite · Tailwind
tests/               294 tests
```

| Module | Role |
|---|---|
| `features.py` | Point-in-time feature matrix. No look-ahead, and the tests prove it. |
| `models.py` | Seven models compete per regime cell — Ridge, Lasso, ElasticNet, Huber, XGB, LightGBM, CatBoost. The data picks. |
| `gate_config.py` | The gate rule, defined once. Imported by both the live ranker and the backtest so they physically cannot diverge. |
| `walkforward.py` | Expanding-window backtest. Writes the trade tapes every number here comes from. |
| `live_ranker.py` | Classify → predict → rank, with a cost gate that refuses any entry whose take-profit does not clear twice the round-trip cost. |

That last one is worth a sentence. On 13 July the engine's top pick was WTI M1-M2 with a $0.03
take-profit against a $0.03 round-trip cost — a trade that nets zero *when it wins*. The gate
blocks it now.

---

## Testing

```bash
python -m pytest tests/    # 294 tests
```

Most are hermetic — synthetic frames, no data lake, runs anywhere.

A few are not tests at all, they are tripwires. The gate rule is mirrored between the live
engine and the backtest, and `test_invariants.py` asserts the two stay bit-for-bit identical.
Tune the live gate without re-running the walk-forward and the suite fails. That is the point.

The backend↔frontend seam is type-checked end to end: Pydantic response models generate the
TypeScript, so a schema change that would break the UI fails at compile time instead of in the
browser.

---

## Reading further

| | |
|---|---|
| [`docs/PROJECT_STATE.md`](docs/PROJECT_STATE.md) | Current state, architecture, and every gotcha worth knowing. Start here. |
| [`docs/PHASE_HISTORY.md`](docs/PHASE_HISTORY.md) | Sprint by sprint — including all five failed attempts to beat the baseline |
| [`docs/ROADMAP.md`](docs/ROADMAP.md) | What is next |
| [`deploy/README.md`](deploy/README.md) | Deployment runbook |

---

## The caveats, up front

The tuned exit rule's 82.9% win rate is in-sample; out-of-sample it is ~74–75%, and the Sharpe
and profit factor should be read as optimistic. The geopolitical event study covers one
episode with overlapping forward windows, so trust the direction and not the p-value. WTI
settlements before 2021 are synthesised from one-minute mids rather than real daily settles,
and anything derived from them is flagged `ESTIMATE` in the interface.

Every one of those is in the code as well as here. A number you cannot source is a number I
do not ship.
