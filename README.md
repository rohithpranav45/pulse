# PULSE

**An energy trading terminal that tells you when it doesn't know.**

PULSE ingests roughly 35 market and fundamental data sources, runs a regime-conditional
model over crude calendar spreads, and serves the result as a live dashboard with a
paper-trading book attached. It was built over a trading-desk internship at Futures First.

The interesting part isn't the dashboard. It's that the engine was honestly graded — and
where the models lost to a simple baseline, the code says so and trades the baseline instead.

🔗 **[Live demo](https://rohithpranav45-pulse.hf.space)** · 📄 **[Methodology](docs/report/PULSE_One_Page_Report.pdf)**

---

## Quick start

```bash
pip install -r requirements.txt
python start.py
```

Open http://127.0.0.1:5000.

That's it for the dashboard. The quant engine additionally needs the `/Data` parquet lake,
the trained model pickles, and a `.env` with API keys — none of which are in version control.
See [`docs/PROJECT_STATE.md`](docs/PROJECT_STATE.md) §2 and §5 to restore or rebuild them.

---

## What it does

**Reads the market.** ~35 sources — ICE and CME futures curves, EIA inventories, CFTC
positioning, FRED macro series, freight, news wires — normalised into one cache with
per-source health and provenance tracking. Stale data is shown as stale, never silently
carried forward.

**Models crude spreads.** Six instruments (Brent and WTI × M1-M2, M3-M6, butterfly) across a
three-axis regime grid: curve shape × inventory level × volatility. Seven models compete per
regime cell — Ridge, Lasso, ElasticNet, Huber, XGBoost, LightGBM, CatBoost — and the data
picks the winner.

**Takes positions.** A paper book opens the ranked, decorrelated selection during market
hours and closes on a tuned exit rule (take-profit at halfway to fair value, 2.5σ stop,
30-day time stop). Correlated same-direction trades are filtered out so the book never
doubles up on one bet.

**Grades itself.** Every claim on the dashboard traces to a named source and a measured
number. Where the evidence is thin, the interface says "prior", not a fabricated figure.

---

## Results

Validated on an expanding-window walk-forward, 2018–2026, 34 quarterly refits, net of
transaction costs.

| Strategy | NET Sharpe |
|---|---|
| Regime-unaware baseline | **+0.372** |
| Per-spread gated regime | +0.374 |
| Global model, regime-as-feature | +0.380 |
| Pooled regime cells | +0.293 |
| Data-driven HMM regimes | +0.289 |

**The headline finding is negative, and that's the point.** Regime conditioning did not beat
a simple rolling z-score baseline. Splitting the data by regime, softening the thresholds,
learning the boundaries from an HMM, and vol-targeting the book were each tried and each
failed to lift the number.

What did work was applying regime conditioning *selectively*. The per-spread gate enables it
only on the two instruments where it measurably earned its place — WTI M1-M2 and the WTI
butterfly — and routes the other four to the baseline. That brought the regime book to
parity, which is an honest result rather than an impressive one.

Two other measured edges came out of the same discipline:

- **Inventories bite in a glut, not when tight.** A crude surprise predicts release-day
  direction 75–81% of the time when stocks are high, and ~52% — a coin flip — in today's
  backwardated market. So the framework abstains on crude and redirects to gasoline, which
  holds a real 57% edge in exactly this regime.
- **Geopolitical supply shocks show up in distillate, not flat price.** A chokepoint
  disruption firms the ULSD crack 57% of the time over five days. Crude flat price spikes on
  day one and reverts by day five — the risk premium round-trips while physical tightness
  persists.

---

## Architecture

```
backend/
├── app.py           Flask API — 73 endpoints + scheduler
├── data_lake.py     DuckDB/parquet loaders over the desk feed
├── fetchers/        ~30 data-source modules
├── models/          fair value · signal engine · pattern analogs
├── research/        the quant engine (below)
└── schemas/         Pydantic models → generated TypeScript types

frontend/            React 18 + Vite + Tailwind → builds into backend/static
tests/               294 tests
docs/                methodology, roadmap, phase history
deploy/              Docker + Caddy, and the Hugging Face Space
```

Inside `backend/research/`, the pieces worth knowing:

| Module | Role |
|---|---|
| `regimes.py` | The 27-cell composite and 3-cell pooled regime grids |
| `features.py` | Point-in-time feature matrix — no look-ahead |
| `models.py` | Seven-model per-cell competition with quantile bands |
| `live_ranker.py` | Classify → predict → rank, applying the tuned exit rule |
| `gate_config.py` | Per-spread gate — the single source of truth, imported by both live and backtest so they can't drift |
| `walkforward.py` | Expanding-window backtest; writes the trade tapes |
| `vol_target.py` | Portfolio vol-targeting over the gated tape |
| `auto_desk.py` | Reconciles the paper book to the live recommendation |

The backend↔frontend seam is type-checked end to end: Pydantic response models generate the
TypeScript types, so a schema change that breaks the UI fails at compile time.

---

## Testing

```bash
python -m pytest tests/
```

294 tests. Most are hermetic — they build synthetic frames rather than touching the data
lake, so they run anywhere.

A handful are load-bearing invariants rather than unit tests. The gate rule is mirrored
between the live ranker and the backtest, and `test_invariants.py` asserts the two stay
identical. If someone tunes the live gate without re-running the walk-forward, the suite
fails. That's deliberate.

---

## Documentation

| Document | What's in it |
|---|---|
| [`docs/PROJECT_STATE.md`](docs/PROJECT_STATE.md) | Current state, how to run, architecture, gotchas. Start here. |
| [`docs/ROADMAP.md`](docs/ROADMAP.md) | What's next |
| [`docs/PHASE_HISTORY.md`](docs/PHASE_HISTORY.md) | Sprint-by-sprint log, including the experiments that failed |
| [`deploy/README.md`](deploy/README.md) | Deployment runbook |

---

## A note on the numbers

Every figure above is reproducible from the walk-forward report in the repo. Where a result
is optimistic, it's labelled: the tuned exit rule's win rate is in-sample, the geopolitical
event study covers a single episode with overlapping windows, and WTI settlements before 2021
are synthesised from one-minute mids rather than real daily settles.

Those caveats are in the code too, not just here.
