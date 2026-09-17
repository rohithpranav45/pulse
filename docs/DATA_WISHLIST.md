# PULSE — Data Wishlist (for the Bloomberg / Reuters pull)

**Purpose.** PULSE already ingests ~35 sources and runs a regime-conditional spread engine, a
news-impact model, and an inventory-reaction framework. Several of these models are **fully built but
data-starved** — the pipeline exists, the verdict is graded "the data doesn't earn it yet." This doc lists,
in priority order, exactly what data would unlock the most, with terminal symbology and the delivery format
that drops straight into our loaders.

**How to read the priority tiers:**
- **Tier 1 — Foundational.** Fixes structural weaknesses that cap *every* model. Highest leverage by far.
- **Tier 2 — New alpha.** Data the models have never seen; each maps to a concrete new feature/signal.
- **Tier 3 — Breadth & polish.** Widens the universe and sharpens the dashboard.

Bloomberg tickers are given as `XXX Comdty/Index`; Reuters/Eikon RICs as `xxxc1`. The terminal team can
confirm exact symbology — the major ones (`CO1`/`CL1 Comdty`, `LCOc1`/`CLc1`) are standard.

### Extractability rating (verified June 2026)

Every item below is tagged with how cleanly it comes off a *standard* terminal, because "it's on the
terminal" and "an analyst can export it" are not the same thing:

- ✅ **Standard** — base terminal entitlement; pull directly via Excel `BDH`/`BDP` (Bloomberg) or
  `=TR()`/Eikon Data API (Refinitiv). No add-on. This covers all the futures curves, COT, EIA inventories,
  vol surface, FX, and calendars — i.e. the bulk of the list.
- ⚠️ **Licensed add-on** — visible only if the desk subscribes to that data package. Applies to
  **price-reporting-agency assessments (Platts/Argus)** — Dated Brent, CFDs, grade differentials, regional
  refining margins — and to **Baltic freight** and **third-party flows/storage (Kpler/Vortexa, ARA/Fujairah
  independent stocks)**. *She must confirm the desk's entitlements before promising these.*
- ⛔ **Not a clean terminal export** — needs a separate premium product. This is **bulk historical news**:
  the Refinitiv/Eikon Data API caps news-headline history at **15 months / 100 headlines per call**
  ([confirmed](https://community.developers.refinitiv.com/questions/55223/news-headlines-older-than-15months.html));
  older requires **Refinitiv Tick History / DataScope**. Bloomberg's base terminal lets you *read/search*
  news but blocks bulk export — that needs **MRN / Event-Driven Feeds / B-PIPE**. See §1.3 for the realistic
  scope.

---

## TL;DR — if she can only pull three things

1. ✅ **Real WTI (NYMEX CL) daily settlement curve, C1–C24, back to 2010.** Today WTI is *synthesised* from
   1-min mids, only C1–C6, only 2021+. This one file removes the `ESTIMATE` flag, **triples the WTI history
   (5y → 15y)**, and gives a real curve. It is the reason half our walk-forward verdicts read "WTI cells
   auto-skip pre-2021" — fixing it could genuinely change conclusions. **Trivially extractable** (Excel
   `BDH`), so this is both the highest-leverage *and* lowest-effort ask.
2. ⛔→⚠️ **A timestamped oil-news archive — but scoped to what's actually pullable.** Our News-Impact model
   is built but trained on 2,999 GDELT headlines (2021 only, 80% non-oil noise, lagged timestamps). **Honest
   caveat (verified):** a clean *2015→now* newswire archive is **not** a base-terminal export — Eikon's API
   only serves the **last 15 months** of headlines, and Bloomberg blocks bulk news export. So the realistic
   ask is one of: (a) the **last ~15 months** of oil-tagged headlines with timestamps via the Eikon Data API
   (free with her terminal, enough to *re-fit* the model on clean data), or (b) a **Refinitiv News Analytics /
   MRN historical extract** if the desk has that feed. See §1.3.
3. ⚠️ **Physical crude benchmarks: Dated Brent, Brent CFDs/DFL, Brent–WTI EFS.** The desk trades on the
   *physical* structure; our model has **zero** physical inputs — only futures, so this is the biggest class
   of alpha we're blind to. **Caveat:** these are Platts/Argus assessments — **licensed add-on**, only if the
   desk's terminal carries the PRA data package. Worth asking; not guaranteed.

---

## Tier 1 — Foundational (unlock what's already built)

### 1.1 Real WTI futures settlement curve  ⭐ highest leverage  ✅ standard, trivial to extract
- **What:** NYMEX WTI (CL) **official daily settlement** prices, generic contracts **C1 through C24**,
  back to **2010** (earlier is bonus).
- **Bloomberg:** `CL1 Comdty` … `CL24 Comdty`, field `PX_SETTLE` (not `PX_LAST`). **Reuters:** `CLc1`…`CLc24`,
  settlement field.
- **Why:** Right now `data_lake.get_wti_settlements()` fakes WTI by taking the last 1-min mid of each session
  (C1–C6 only, 2021+). Consequences that show up verbatim in our results:
  - WTI spreads are flagged **ESTIMATE**; not exchange truth.
  - WTI history starts **2021** → every pre-2021 WTI regime cell auto-skips → the whole 2018–2020 deep-contango
    episode is a **Brent-only** story. "Baseline beats regime" is partly a *data-depth* artifact.
  - We use **C6 as the C12 proxy** for WTI curve shape because we don't have the back end.
- **Unlocks:** re-running the entire walk-forward (Phases 2.8.4–8, vol-target, HMM) on a *real, deep* WTI tape;
  proper WTI curve features; honest WTI butterflies.

### 1.2 Real Brent settlement curve to the back end + longer history  ✅ standard
- **What:** ICE Brent official settlements **C1–C24** (we have C1–C31 from 2016 — good; the ask is **pre-2016
  history back to ~2008–2010** to cover the 2008 and 2014–16 crashes).
- **Bloomberg:** `CO1 Comdty`…`CO24 Comdty`, `PX_SETTLE`. **Reuters:** `LCOc1`…`LCOc24`.
- **Why:** more regime episodes (2008 super-backwardation, 2014–16 collapse, 2020 negative-WTI shock) = more
  training data for the regime grid and the GARCH/vol-target risk layer. Our models currently never see a
  pre-2016 crisis.

### 1.3 Timestamped oil-news archive  ⛔→⚠️ extractability caveat — read this carefully
- **What we'd love:** a crude-oil/energy-filtered **newswire** archive, **2015→now**, machine-readable, with
  **exact publication timestamp (to the minute)** and a topic/ticker tag.
- **Why our current corpus is the bottleneck (graded honestly):** GDELT gave us 2,999 headlines, **2021 only**
  (IP-soft-banned mid-backfill), **80% NOISE** (its broad military theme drags in non-oil news), and its
  `seendate` **lags true publication** — which breaks our +1h event-study window. No factor clears |t|≥2, so
  every factor falls back to a hand-set prior. The model architecture (event study → per-factor β → expected
  % Brent move, regime-gated) is **done and tested**; it just needs a real tape.
- **The honest extractability problem (verified):** a 2015→now newswire archive is **not** something an
  analyst exports from a base terminal:
  - **Refinitiv/Eikon Data API** (`ek.get_news_headlines`) only serves the **last ~15 months** of headlines,
    **100 per request**
    ([source](https://community.developers.refinitiv.com/questions/55223/news-headlines-older-than-15months.html)).
    Older history needs **Refinitiv Tick History / DataScope Select** — a separate licensed feed.
  - **Bloomberg** lets you read/search news (`N`, `NSE`) but **blocks bulk historical export**; machine-readable
    news at scale is **MRN / Event-Driven Feeds / B-PIPE** — premium products, not the base terminal.
- **So the realistic ask (pick the one her desk can do):**
  1. **Easiest / free with her terminal:** the **last ~15 months** of oil-tagged headlines + timestamps via the
     Eikon Data API. ~15 months of *clean, well-timestamped* headlines beats our 8 months of noisy GDELT — it's
     enough to honestly **re-fit and re-grade** the model, even if it won't reach 2015.
  2. **If the desk has it:** a **Refinitiv News Analytics / MRN** or **Bloomberg news-feed** historical extract
     (2015→now) — the full unlock, but an entitlements question for her data team.
  3. **Pragmatic free alternative we can do ourselves:** keep extending the GDELT/RSS live capture forward (it
     grows daily) and pair it with a cleaner oil filter — no terminal needed, just slower.
- **Must-haves whichever path:** (a) **precise publication timestamp** (non-negotiable for the intraday event
  study); (b) an **oil/energy filter or ticker tags** so we're not 80% noise.

---

## Tier 2 — New alpha features (each maps to a concrete model input)

### 2.1 Physical crude market structure  ⚠️ licensed add-on (Platts/Argus) — confirm entitlement first
- **Dated Brent** (physical North Sea benchmark): Platts `PCAAS00`; **Reuters:** Platts `AAS`/`DTD`.
- **Brent CFDs / DFL** (Dated-to-frontline, the physical-vs-paper roll): the 1st–8th week CFD curve.
- **Brent–WTI EFS** (Exchange for Swaps) and the **arb (Brent–WTI futures spread)** as a physical print, not
  just our futures-derived `wti_brent_spread`.
- **Key physical grade differentials:** WTI Midland, Forties, Bonny Light, Urals (where available).
- **⚠️ Extractability:** these are **Platts/Argus price-reporting-agency assessments** (`PCAAS00` is a Platts
  code, [confirmed S&P Global](https://www.spglobal.com/energy/en/pricing-benchmarks/assessments/crude-oil/dated-brent-price-explained)).
  They show on a terminal **only with the PRA data licence** — *not* base Bloomberg/Reuters. **The single
  question to ask her: "does the desk's terminal carry Platts (or Argus) crude assessments?"** If yes, this is
  the highest-value Tier-2 pull; if no, it's off the table via the terminal. The **Brent–WTI EFS/arb** is the
  most likely piece to be available without the PRA licence (more exchange-quoted).
- **Why:** the physical premium/discount and the CFD structure **lead** the front futures carry (m1_m2). A
  positive Dated-vs-future signals physical tightness before the futures curve backwardates. This is a whole
  new feature family for the regime model and a strong candidate leading indicator for `brent_m1_m2`.

### 2.2 Cushing & global inventories (beyond US weekly crude)
- ✅ **Cushing, OK crude stocks** ⭐ (the WTI delivery point — *directly* drives `wti_m1_m2`). This is the EIA
  weekly series (`W_EPC0_SAX_YCUOK_MBBL`,
  [EIA](https://www.eia.gov/dnav/pet/hist/LeafHandler.ashx?n=PET&s=W_EPC0_SAX_YCUOK_MBBL&f=W)) — public and
  carried on both terminals. *(I'm not 100% sure of the exact Bloomberg ticker string, so give her the EIA
  series name as the source of truth; she/the terminal will map it.)*
- ✅ **Singapore** product stocks (Enterprise Singapore) and **US/OECD** EIA-STEO series — government data,
  standard.
- ⚠️ **ARA** (Amsterdam-Rotterdam-Antwerp) independent stocks, **Fujairah** stocks, and **floating storage**
  (Vortexa/Kpler) — these are **third-party providers** (Insights Global, FEDCom/S&P, Kpler), licensed
  add-ons, *not* base terminal. Ask only if the desk subscribes.
- **Why:** our inventory regime axis is **US-only weekly crude**. Cushing specifically is the single most
  important miss for WTI front spreads — and it's free/clean, so it should be in the *first* pull alongside
  the WTI curve. ARA/Singapore extend the inventory-reaction framework to the Brent complex.

### 2.3 Full positioning (beyond CFTC managed-money WTI)  ✅ standard (public regulator data)
- **ICE Brent COT** ⭐ (we only have CFTC **WTI**; Brent positioning drives Brent spreads).
- **Full disaggregated COT**: producer/merchant, swap dealers, money managers, other reportables — not just
  managed-money net.
- **Bloomberg:** clean COT via `CFTC`/positioning functions; **Reuters** carries ICE COT.
- **Why:** positioning crowdedness is a contrarian signal we apply to WTI but **not Brent**. Adding Brent
  positioning + the full trader breakdown gives the `cot_*_pct` features real cross-sectional coverage.

### 2.4 Implied-vol surface & skew (beyond a single OVX index)  ✅ standard (historical depth varies)
- **ATM implied vol by tenor** for Brent & WTI (1m/2m/3m/6m).
- **25-delta risk reversals** (put-call skew) and **butterflies** ⭐.
- **Bloomberg:** `OVDV`/`OVML` on `CO1`/`CL1 Comdty`; vol surface fields. *Live surface is standard; deep
  historical skew series can be patchy — ask for as much history as the terminal returns.*
- **Why:** today the only vol input is `ovx_vix_ratio` (one ATM crude-vol index ÷ equity VIX). **Skew/risk
  reversals are a leading crash/regime signal** — when downside skew steepens, the vol regime is shifting
  before realised vol moves. This feeds both the regime vol-axis and the shock/circuit-breaker engine, which
  currently lean on 20-day *realised* vol (a lagging measure).

### 2.5 Refining margins & runs (upgrade the crack proxy)  ✅/⚠️ mixed
- ✅ **Refinery utilisation / runs (US weekly)** — EIA, standard. ✅ **Product cracks** (gasoil/jet/fuel-oil)
  — Bloomberg computes these from futures, standard.
- ⚠️ **Regional gross refining margins** (NWE/USGC/Singapore GRM) — typically **Platts/Argus-assessed**
  (licensed) unless taken as a Bloomberg-calculated crack. Prefer the Bloomberg-calculated version to stay
  inside the base entitlement.
- **Why:** demand-side regime conditioning. Our `crack_321`/`gasoline_crack` are yfinance-futures proxies; real
  GRMs + runs let the model distinguish a demand-led vs supply-led curve move.

### 2.6 Freight & flows  ⚠️ mostly licensed
- ⚠️ **Dirty tanker rates**: Baltic Dirty Tanker Index (`BIDY Index`), VLCC TD3C, Suezmax TD20 — **Baltic
  Exchange data**, licensed but commonly carried on terminals (confirm entitlement).
- ⚠️ **Crude flows/exports & arrivals** (Kpler/Vortexa) — **third-party premium**, not base terminal.
- **Why:** freight is a *leg* of the Brent-WTI arb; flows are a leading inventory signal. These sharpen the
  arb feature and add a genuinely exogenous demand pulse — but only worth chasing if the desk already pays
  for them.

---

## Tier 3 — Breadth & dashboard polish

- **More products on the same curve framework:** ICE Gasoil (`QS1 Comdty`/`LGOc1`), RBOB (`XB1`), ULSD/HO
  (`HO1`), and the **WTI–Brent arb** as its own tradeable. We already pull 1-min mids for HO/Gasoil — real
  settlement curves would let us model their spreads too (expand the 6-instrument universe to ~10).
- **OPEC+ production** — Bloomberg's monthly OPEC survey is more timely than JODI (we just cached JODI/OPEC;
  Bloomberg's survey leads it by weeks).
- **Macro:** `DXY Curncy` (dollar), real rates curve, China activity proxies — context features for the
  cross-asset regime.
- **Exact contract expiry / roll calendar** for Brent & WTI — our `days_to_expiry` feature uses a crude
  "25th-of-month" approximation; the real expiry schedule makes the roll feature exact.
- **EIA/IEA/OPEC release calendar with exact timestamps** — improves the news/inventory event studies
  (knowing the *exact* release minute tightens the reaction window).

---

## Delivery format (so it drops straight into our loaders)

Our loaders read **CSV or Excel, one row per trading day, a date column + one column per contract** (this is
exactly the shape of the existing Brent file). The most useful hand-off:

- **Futures curves (WTI, Brent, products):** one CSV per product —
  `Date, C1, C2, …, C24` of **daily settlements**, full history. Daily granularity is enough for the models
  (we have separate 1-min mids already). → drops into `Data/` and `data_lake.py` picks it up; lets us delete
  the WTI synthesis path entirely.
- **Weekly series (Cushing, ARA, COT, inventories):** `Date, value` CSV, one file per series.
- **Vol surface:** `Date, tenor, atm_vol, rr25, bf25` (long format is fine).
- **News (whatever window is pullable — even just the last 15 months):** `timestamp_utc, headline, [body],
  source, topic/ticker_tag` — **timestamp to the minute** is the one field we can't compromise on.
- **Physical (Dated Brent, CFDs, EFS — only if PRA-licensed):** `Date, value` daily.

CSV/Excel preferred over a live terminal API — a one-time historical extract per series is exactly what we
need to backfill, and we can refresh periodically. No streaming required.

---

## What each ask changes (honest, graded — the PULSE house style)

| Ask | Extractability | Model it unblocks | Expected impact |
|---|---|---|---|
| Real WTI curve (1.1) | ✅ standard, trivial | Whole regime engine, walk-forward, vol-target | **High** — could flip "baseline wins" verdicts; removes the ESTIMATE caveat that qualifies every WTI number |
| Real Brent back-history (1.2) | ✅ standard | Regime grid + risk layer on pre-2016 crises | **Medium-high** |
| News archive (1.3) | ⛔ 2015→now / ⚠️ 15-mo via API | News-Impact model | **High** *if pullable* — but capped at ~15 months unless the desk has MRN/Tick History |
| Cushing stocks (2.2) | ✅ standard (EIA) | WTI front-spread inventory axis | **Medium-high** — most direct WTI inventory driver; free, pull it first |
| Brent COT (2.3) | ✅ standard | Positioning feature for Brent | **Medium** |
| Vol skew (2.4) | ✅ standard (depth varies) | Regime vol-axis + shock engine | **Medium-high** — leading vs our lagging realised-vol |
| Physical Brent (2.1) | ⚠️ Platts/Argus licence | New feature family for carry spreads | **High** *if entitled* — the desk's real edge; else off-terminal |
| GRM/runs (2.5) | ✅/⚠️ mixed | Demand-side regime conditioning | **Medium** |
| Freight / flows (2.6) | ⚠️ Baltic/Kpler licence | Arb-leg + demand pulse | **Medium** — only if already subscribed |
| Tier 3 | ✅ standard | Universe breadth + dashboard | **Polish** |

> **Honesty note for the mentor (the PULSE house style — graded, not spun):**
> - The **two cleanest, highest-value pulls are both ✅ standard and need no add-on**: the **real WTI curve
>   (1.1)** and **Cushing stocks (2.2)**. Start there — they're free with her terminal and directly attack our
>   biggest structural weakness (synthetic, shallow WTI).
> - The **news archive (1.3)**, which I'd earlier called a top-2 unlock, is the one item that is **not a clean
>   terminal export** — verified: ~15 months max via the Eikon API, bulk history needs a separate licensed
>   feed. Still worth the 15-month pull (clean beats our noisy GDELT), but I've reset expectations honestly.
> - **Physical Brent (2.1)** and **freight/flows (2.6)** are real alpha but **gated on whether the desk
>   already licenses Platts/Argus/Baltic/Kpler** — so they're a *"can you?"* question to her, not a
>   *"please pull"* instruction.
>
> One question answers half the doc: **"Does the desk's terminal carry Platts/Argus crude assessments and a
> historical news feed (MRN / Tick History), or just the base market-data entitlement?"**
