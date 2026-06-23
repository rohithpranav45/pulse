# Inventory Surprise Impact Model — Crude

**Futures First · Wednesday inventory assignment · series chosen: Crude oil**

> One-line thesis: **the market trades the *surprise vs consensus*, not the headline draw — and only in the *regime* where inventories actually move price. Right now we are in the regime where they don't.**

Everything below is reproducible from the PULSE data lake:
`python -m backend.research.inventory_impact` (full run + console deck → `results.json`).
Charts for the deck: `python -m backend.research.inventory_impact.charts` (4 PNGs).
Live in the dashboard: **dedicated INVENTORY tab** (hotkey `6`). The four deliverables are
surfaced explicitly as a **forward call for the upcoming release**: (1) expectation + confidence
+ P(bull/bear), (2) products/spreads ranked, (3) top-3 factors, (4) the L0→L4 framework +
backtested charts. Plus a **live consensus calculator** (plug in Wednesday's actual + consensus
→ the call recomputes), the **regime-gated scenario tree** (expected Brent move per surprise size,
today's regime vs a glut contrast), the **when-it-mattered** table, the four deck charts, the
latest full report, and the recent-release history. Endpoint: `/api/regime/inventory`
(`?actual=&consensus=` for the live call); charts at `/api/regime/inventory/chart/<name>`.

---

## 1. The framework (L0 → L4)

A release is a **conditional, multi-dimensional surprise whose price impact is regime-dependent and decays.** Five layers:

| Layer | What it does | Module |
|---|---|---|
| **L0 — Surprise** | `surprise = actual − expected`, z-scored. Headline = **commercial crude ex-SPR** (WCESTUS1), the number the market forecasts — *not* total-incl-SPR. "Expected" = analyst **consensus** (live, off the terminal) or a **seasonal/nowcast proxy** for the backtest. | `eia_report.py` |
| **L2 — Quality of draw** | The whole report, not the headline. Decompose into a surprise vector (Cushing, refinery runs, imports, exports, products-supplied / implied demand) and **reconstruct EIA's supply-balance adjustment** ourselves. A draw driven by an export spike or a fat adjustment is *mechanical* — to be faded. | `eia_report.py` |
| **L1 — Reaction function** | Align the **1-min tape** to each 10:30-ET print (2021-26, 281 releases); measure conditional betas, decay, and a vol placebo. | `event_study.py` |
| **★ Regime conditioning** | The meta-result. On **2015-2026 daily** history (535 releases), measure how surprise→price strength varies by **inventory / curve regime**. | `regime_conditioning.py` |
| **L4 — Scorecard** | Compose into bull/bear/neutral + probability + confidence + most-exposed spread + top-3 factors. **Conviction is regime-gated.** | `framework.py` |

---

## 2. When did inventories matter — and when didn't they? (the core result)

`surprise_z → Brent front close-to-close return on release day`, **2015-2026, 535 releases**:

| Regime slice | Beta (%/σ) | t-stat | R² | n | Verdict |
|---|---|---|---|---|---|
| All releases | −0.18 | −1.7 | 0.005 | 535 | weak unconditionally |
| **HIGH stocks (glut)** | **−1.03** | **−3.4** | **0.165** | 59 | **inventories drive price** |
| AVG stocks | −0.18 | −0.9 | 0.006 | 126 | marginal |
| **LOW stocks (tight)** | −0.02 | −0.2 | 0.000 | 350 | **pure noise** |
| **Contango front** | **−0.43** | **−2.1** | 0.027 | 154 | matters |
| Backwardated front | −0.06 | −0.5 | 0.001 | 381 | noise |
| Era 2015-2020 | −0.43 | −2.9 | 0.033 | 254 | mattered |
| Era 2021-2026 | +0.08 | +0.5 | 0.001 | 281 | stopped mattering |

**Reading:** the sign is *correct* (a bearish surprise lowers price) and *significant* **only when inventories are already high / the curve is in contango** — a glut regime where the market is fixated on whether stocks keep building. In a **tight / backwardated** market, prompt scarcity, OPEC spare capacity and geopolitics set the price, and the weekly print is statistically indistinguishable from noise (R² ≈ 0). The calendar-era split (2015-20 mattered, 2021-26 didn't) is really this regime effect in disguise — 2015-20 was the shale-glut/contango era.

**Intraday confirmation (2021-26, 1-min, 281 releases):** surprise→WTI-flat 30-min beta ≈ 0; and a **placebo test shows release-day volatility is ~1.0× a normal day at every window from 2 min to 2 h (not significant, p≈0.5–0.8).** In the current regime the print is not even a reliable *volatility* event, let alone a directional one. This is the single most counter-consensus, defensible finding in the deck.

---

## 3. The call — this week's release

Run live with: `framework.assess_release(actual_change=<EIA>, consensus=<terminal>)`.

**Current regime (as of latest data): LOW stocks (−12.4% vs 5-yr) / backwardation → inventory sensitivity LOW.**
Historical beta in this regime: **−0.04%/σ, t = −0.3 → the print is noise on flat price here.**

On the latest released number (2026-06-12, −8.3 MM draw, proxy surprise −0.6σ):

- **Expectation: ⚪ NEUTRAL on flat price** (P_bull 0.60 / P_bear 0.40), **confidence LOW.** A draw, yes — but a near-consensus one, in the regime where draws don't move price. *The naive "big draw = bullish" call has no historical edge here.*
- **Products / spreads most affected** (in order): **WTI-Brent** (US location/arb — most exposed to import/export-driven surprises), then **WTI M1-M2** (Cushing/front tightness), then **Brent/WTI cracks** (demand surprises). Flat price is *least* reliable in this regime. *N.B. the daily M1-M2 reaction is ≈null in every regime — the inventory effect, where it exists, is a flat-price/level effect, so spread trades on the print are not supported by the data.*
- **Top-3 factors driving the view:**
  1. **Regime gate** — LOW stocks / backwardation; inventories have not moved flat price in this regime (t = −0.3). *This dominates.*
  2. **Surprise size** — only −0.6σ on the proxy; not an outlier worth fighting the regime for.
  3. **Quality of draw +1.7** — the draw looks demand-led/coherent (mild bullish tilt), but not enough to override the regime gate.

**How the call flips:** it becomes a real, higher-conviction directional trade **(a)** if consensus reveals a large surprise (≥1.5σ) **and (b)** the regime shifts toward glut/contango. Plug the Wednesday-morning consensus into `assess_release(consensus=…)` for the live read; e.g. an actual of −8.3 MM vs a +0/build consensus is a −1σ+ bullish surprise and lifts the call to BULLISH/MEDIUM — but even then `expected_move ≈ 0` is flagged honestly because the regime is insensitive.

---

## 4. Quality-of-draw — the "don't get faked out" layer

Per-release decomposition flags when the **headline and the quality diverge.** Example from the live tape (2026-05-29): a **−8.0 MM draw** (looks bullish) but **quality-of-draw −3.0** — exports spiked (+2.5σ) and runs fell, i.e. a *mechanical, export-driven draw to fade*, not a demand-led tightening. The headline and the right read point opposite ways. This layer is regime-independent and is where the framework adds value even when the flat-price reaction is dead.

---

## 5. Honesty / data notes (what would sharpen this)

- **Consensus is the one real data gap.** The backtest uses a **seasonal + nowcast proxy** for "expected"; the proxy is attenuated (errors-in-variables) so it *under*-states true betas. The *live* call uses real consensus off the desk terminal (one-line swap, already wired). A historical consensus pull (Bloomberg ECO/DOE survey export) would tighten every beta — the cleanest next step, and a legitimate desk data-ask. Even so, the regime conditioning is robust to the proxy because it's measured on *relative* strength across regimes.
- WTI synthetic settles are flagged ESTIMATE in PULSE; the centerpiece uses **real Brent settles** for the daily reaction to avoid that.
- The intraday sample is 2021-26 (1-min lake coverage); the daily sample extends to 2015 for regime power.

---

### Bottom line for the desk
Most desks will say *"draw → bullish."* The data says: **in today's tight/backwardated regime the crude print is noise on flat price — trade it only as a quality-decomposition / fade-the-mechanical-draw signal, size the directional view down, and require a real consensus surprise before fighting the tape. Inventory sensitivity will return when (not if) the curve rolls back into contango.**
