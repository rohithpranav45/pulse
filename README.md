# PULSE

### A systematic trading research stack — hypothesis, alternative data, walk-forward, production. Including the part where the hypothesis lost.

PULSE ingests ~35 financial and alternative data sources, forms testable hypotheses about
crude spread behaviour, models them with a per-regime ensemble in Python, backtests every
signal out-of-sample net of transaction costs, and deploys the survivors to a live paper book.

Built over a trading-desk internship at Futures First.

**[Live demo](https://rohithpranav45-pulse.hf.space)** · **[Methodology](docs/report/PULSE_One_Page_Report.pdf)** · **[Full project state](docs/PROJECT_STATE.md)**

```bash
pip install -r requirements.txt && python start.py   # → http://127.0.0.1:5000
```

---

## The hypothesis, and what the data said

**Hypothesis.** Crude calendar spreads mean-revert differently depending on market regime —
curve shape, inventory level, realised volatility — so a model conditioned on regime should
beat one that ignores it.

**Test.** Expanding-window walk-forward, 2018–2026, 34 quarterly refits. Point-in-time
features with no look-ahead. Every number net of a per-spread round-trip cost.

| | NET Sharpe |
|---|---|
| **Regime-unaware baseline** | **+0.372** |
| Global model, regime-as-feature | +0.380 |
| Per-spread gated regime | +0.374 |
| Pooled regime cells | +0.293 |
| Data-driven HMM regimes | +0.289 |
| Vol-targeted book | +0.198 |

**Result. A rolling z-score with no regime awareness beat all of it.**

So I attacked my own result five different ways. Collapsed the 27-cell grid and fed regime as
a one-hot feature — tied. Replaced the hard thresholds with logistic transition functions —
tied. Threw out the trader's thresholds entirely and learned regime boundaries with a
GMM + sticky-HMM forward filter — worse. Ran a Lasso stability-selection pass to prune the
feature set — worse, though it did localise where the signal lives. Vol-targeted the book —
halved max drawdown, gave up a third of the Sharpe.

Five attempts to rescue the thesis. The simple thing kept winning.

What eventually worked was abandoning regime conditioning *globally* and asking, per
instrument, whether it had earned its place. The per-spread gate enables regime on exactly
two of six — WTI M1-M2 and the WTI butterfly — and routes the rest to the baseline. NET Sharpe
+0.298 → +0.374. Insensitive to both its thresholds across a 0–0.25 × 10–30 sweep, so it is
not a fitted edge.

Parity with baseline. Not a win. It is in the README because it is in the code.

---

## Alternative data → measured signals

Three alternative datasets, each put through the same grading pipeline as the price models.

**Geopolitical news → physical assets → price nodes.** A hand-built registry of 37 geolocated
oil assets — chokepoints, refineries, pipelines, producing fields — each carrying a signed
prior over nine price nodes. A 3,564-headline GDELT corpus is run through an LLM extractor
(structured output, validated against the registry) to resolve each headline into
`{asset, event_type, severity}`, which maps to a signed conviction vector.

The extraction quality mattered more than the model. A keyword baseline could not distinguish
"Hormuz closes" from "Hormuz reopens" — the same asset and the same disruption vocabulary,
opposite sign. Swapping in LLM extraction 2.3×'d the gradeable sample (**events 68 → 112,
1,414 node-claims**) and flipped crude flat price from noise to a measured next-day edge,
because reopenings finally typed as `restart`.

**Conflict intensity.** ACLED political-violence counts for the oil-producing bloc,
2021–2025, as a causal trailing-window z-score. Graded honestly: monthly conflict intensity
is **essentially uncorrelated with Brent** (corr −0.17 level, 0.03 change, n=53). It ships as
a regime *descriptor*, not a signal, because the market prices specific supply threats rather
than generalised violence.

**Analyst consensus.** 548 weeks of scraped EIA consensus history, 2015–2026, replacing a
seasonal proxy so inventory surprises measure against what the market actually expected. The
API crude print released the day before predicts the EIA consensus surprise at **corr 0.64**,
which makes it a usable pre-release nowcast.

**Retrieval over the graded event panel.** Rather than black-box embeddings, analogs are
retrieved by an interpretable fingerprint — asset type, event type, signed conviction — so an
opposite event scores *low* by construction. Asked about a Hormuz closure, it independently
reproduced the same five-day reversal the regression found, via a completely different method.

---

## Three times the system caught itself lying

**The paper book was reporting +$110,179.**

It was not. 374 of those rows were walk-forward replay trades sized at 4,000–22,000 barrels,
sitting in the same table as the real book and drowning it. The actual live paper book was
**10 trades and −$4.26**. The headline now defaults to the live book; the replay view sits
behind an explicit flag.

**The win rate said 43.8% beside a breakdown reading 166W / 69L.**

Same table, mismatched denominator — it counted 144 break-even scratches in the denominator
while excluding them from the numerator. Win rate is now measured over decisive trades,
**70.6%**, with scratches reported separately instead of quietly dragging the headline down.

**A news factor had t = 3.0 and got demoted anyway.**

GEOPOLITICAL cleared every significance bar I had set. It also had an **18% directional hit
rate** — the t-stat came from a handful of outlier war days, not an edge. The gate now
requires a positive beta *and* a hit rate above 50% before it will label anything "measured."
The factor falls back to a labelled prior, with the rejection reason rendered on the dashboard.

There was also a thread race in the DuckDB layer that corrupted a cached frame at boot and
killed the regime engine until someone restarted the process, silently zeroing the A/B tick
in the meantime. Thread-local cursors and validate-before-cache fixed it. An inventory
endpoint that hung for over 120 seconds now answers in 0.12.

A system that grades its own P&L has every incentive to flatter itself. The only defence is
to go looking.

---

## Where the edges survived

**Inventories bite in a glut, not when the market is tight.** A crude surprise predicts
release-day direction 75–81% of the time when stocks are high (p < 0.01). In today's
backwardated market it is 52% — a coin flip. So the framework **abstains on crude** and
redirects to gasoline, which carries a real 57% edge in precisely the regime where crude is
noise (63–68% on large surprises, p < 0.001).

Most inventory models hand you a crude call every Wednesday. This one tells you when not to
take it.

**Geopolitical supply shocks show up in distillate, not flat price.** A chokepoint disruption
firms the ULSD crack 57% of the time over five days (n=229, p=0.047). Crude flat price spikes
on day one and reverts by day five — the risk premium round-trips while physical tightness
persists. Trade the crack, fade the spike.

**Benchmark selection is empirical, not assumed.** US crude inventories move WTI roughly 17×
more than Brent (β +0.026 vs +0.0015). The call headlines WTI because the data says WTI, not
because crude oil is conventionally quoted in Brent.

Single episode, clustered events, overlapping forward windows. Read the direction and the
cross-node coherence, not the exact p-value — and that caveat is rendered in the interface,
not just here.

---

## Methods

| Area | What is used |
|---|---|
| **Model competition** | Ridge, Lasso, ElasticNet, Huber, XGBoost, LightGBM, CatBoost — seven models run per regime cell, the data picks the winner |
| **Regime detection** | Gaussian mixture + causal sticky-HMM forward filter over curve level and 5-day change; states relabelled ordinally so cells stay stable across refits |
| **Volatility** | GARCH(1,1) and GJR-GARCH with Student-t innovations, refit every 21 days, variance recursion rolled daily between refits; scored on QLIKE against a trailing-window benchmark |
| **Feature selection** | Meinshausen-Bühlmann stability selection — a scaled Lasso at every refit cutoff, features kept at ≥50% selection frequency |
| **Inference** | OLS with t-statistics, binomial tests against 50%, Welch and paired t-tests, bootstrap-free and reported with n |
| **Risk** | Signed-correlation decorrelation filter, per-position vol targeting, stress-conditioned de-risking, portfolio vol overlay |

Uncertainty is handled by a **prior-then-learn gate** used consistently across every
empirical layer: a measured coefficient is served only when it clears |t| ≥ 2 on a minimum
sample *and* passes a directional sanity check. Otherwise the interface shows a labelled
economic prior. The desk never sees a fabricated-precise number.

---

## Out-of-sample discipline

This is the part that matters most, so it is enforced mechanically rather than by convention.

- **Point-in-time features.** Every feature is built from data available at the timestamp it
  is attached to. Tests assert prefix-stability: a value computed at day *t* must not change
  when future data is appended.
- **Causal regime labelling.** The HMM forward filter at day *d* sees only data ≤ *d*.
  Per-spread gate decisions at each refit cutoff use only trades that had *closed* before it.
- **Costs before conclusions.** A single `costs.py` defines round-trip cost; the backtest and
  the live A/B harness both import it, so a cost assumption cannot drift between them.
- **Live entry economics.** The live ranker refuses any entry whose take-profit does not clear
  twice the round-trip cost. On 13 July the top-ranked pick was WTI M1-M2 with a $0.03
  take-profit against $0.03 of cost — a trade that nets zero *when it wins*. It is blocked now.
- **Mirrored gate rule.** The gate is defined once in `gate_config.py` and imported by both
  the live engine and the backtest. `test_invariants.py` asserts they stay bit-for-bit
  identical, so tuning the live gate without re-running the walk-forward fails the suite.

Trade tapes are persisted — 10,587 rows per research leg — so every figure above is
reproducible from the repo rather than quoted from a notebook that no longer runs.

---

## From research to production

The strategies do not stop at a backtest.

```
backend/
├── app.py           Flask API — 73 endpoints, APScheduler jobs
├── data_lake.py     DuckDB over a 3.5 GB parquet lake, thread-local cursors
├── fetchers/        ~30 data-source modules with health + provenance tracking
├── research/        the engine — features, models, walk-forward, gating, risk
└── schemas/         Pydantic → generated TypeScript

frontend/            React 18 · Vite · Tailwind
tests/               294 tests
deploy/              Docker · Caddy · Hugging Face Space
```

A scheduler reconciles the live paper book to the ranked, decorrelated selection during market
hours, gated by a volatility circuit-breaker. Exits are owned by one mark-to-market sweep —
take-profit at halfway to fair value, 2.5σ stop, 30-day time stop — never reimplemented per
caller. The backend↔frontend seam is type-checked end to end: Pydantic response models
generate the TypeScript, so a schema change that would break the UI fails at compile time.

It has been running publicly, unattended, accumulating a live forward book.

---

## Testing

```bash
python -m pytest tests/    # 294 tests
```

Most are hermetic — synthetic frames, no data lake, runs anywhere. A few are not tests but
tripwires, asserting that the live path and the research path cannot silently diverge.

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
and profit factor should be read as optimistic. The geopolitical event study covers a single
episode with clustered, overlapping forward windows, so its p-values are optimistic — trust
the direction and the cross-node pattern. WTI settlements before 2021 are synthesised from
one-minute mids rather than real daily settles, and everything derived from them is flagged
`ESTIMATE` in the interface. The live A/B book is slow confirmation of a question the
walk-forward already answered on 13,758 closed trades.

Every one of those lives in the code as well as here. A number I cannot source is a number I
do not ship.
