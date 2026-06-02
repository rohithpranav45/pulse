# Expert Knowledge — Energy Markets Desk Reference

This document supplements the OilMacroTrading curriculum with veteran-trader
context: OPEC mechanics, pricing benchmarks, refining economics, storage and
logistics, geopolitics playbooks, macro linkages, positioning theory, term-
structure dynamics, historical case studies, and futures-market microstructure.

PULSE retrieves from this file via BM25 alongside the curriculum, so any
question can be answered with both the academic framing (curriculum) and the
practitioner detail (this document).

---

## OPEC+ Deep Mechanics

### Formation and member structure

OPEC was founded in Baghdad in September 1960 by five producers (Saudi Arabia,
Iran, Iraq, Kuwait, Venezuela) reacting to unilateral price cuts by the Anglo-
American "Seven Sisters" oil majors. Today the core OPEC group is 13 nations.
The "+" in OPEC+ refers to the Declaration of Cooperation signed in December
2016 bringing in 10 non-OPEC producers led by Russia, Mexico, Kazakhstan, and
Oman. OPEC+ collectively controls roughly 40% of world crude production and
about 80% of proven reserves.

### Decision-making cadence

- **Joint Ministerial Monitoring Committee (JMMC)**: meets monthly, reviews
  compliance, recommends adjustments. No formal authority but its tone moves
  markets.
- **Joint Technical Committee (JTC)**: produces the data pack the JMMC uses —
  member production, demand forecasts, OECD inventories versus 5-year average.
- **Full ministerial meeting**: usually twice a year (June and December) at
  the OPEC Secretariat in Vienna. Sets baseline quotas for the following half.
- **Extraordinary meetings**: convened when prices break out of a comfort zone
  (the famous "$70–$80 range"). 2020 April emergency and 2022 October cuts
  were both extraordinary.

### The quota system

Each member has a production baseline negotiated at a ministerial meeting.
Cuts are expressed as a fraction of that baseline — e.g. Saudi Arabia's
baseline of 10.5 mb/d minus 500 kb/d voluntary plus 1 mb/d additional
voluntary = effective quota of 9.0 mb/d. Baselines are political: Russia and
Iraq spent years arguing for higher baselines to lower their effective cuts.

### Spare capacity — the real Saudi lever

Spare capacity is barrels that can be brought online within 30 days and
sustained for 90 days. The IEA's number (typically 3–4 mb/d, almost all
Saudi Arabia + UAE + Kuwait) is the true policy variable. When spare is
below 2 mb/d, any news of disruption gets priced harshly because there's no
buffer. When spare is above 4 mb/d, the market ignores moderate disruption.
2008 and 2022 spikes both coincided with spare under 2 mb/d.

### Compliance theory

OPEC has always had a free-rider problem — every member wants the cartel to
cut but cheats on their own quota. Historically:

- **Saudi Arabia** sets the example, often cutting more than promised to
  hold the line.
- **Iraq** has been the most chronic over-producer (post-2014 reconstruction).
- **Russia** routinely reported aspirational numbers that didn't match
  Argus/Kpler tanker-tracked exports.
- **UAE** lobbied 2023–2024 for higher baseline; this is why ADIPEC headlines
  matter — UAE production trajectory affects the Saudi-led cartel cohesion.

The 2016–2024 compliance rates ran 90–110%, often boosted by Venezuela and
Iran losing barrels to sanctions and disrepair (involuntary "compliance").

### Reading OPEC actions

| Action                  | What it usually means                                     |
|-------------------------|-----------------------------------------------------------|
| Voluntary cut announced | Floor is being set; Saudi sees downside risk              |
| Quota *increase* held   | Group is confident demand absorbs current supply          |
| Surprise meeting moved  | Internal disagreement, usually UAE vs Saudi               |
| Saudi unilateral cut    | They've given up waiting for group cohesion               |
| OPEC raises demand fcst | Tape-setting — actual barrels may not back the narrative  |

---

## Crude Benchmarks and Pricing Mechanics

### Brent — the global benchmark

ICE Brent settles physical against a basket of five North Sea grades:
**Forties, Oseberg, Ekofisk, Troll** (collectively BFOET), plus Midland WTI
added in 2023. The contract trades 12+ years out and roughly 70% of global
crude is priced off it (Middle East to Asia is priced off Dubai but with
Brent linkages).

Key Brent quirks every desk must know:

- **Dated Brent** is the physical cargo loading 10–25 days forward. ICE
  Brent futures settle at expiry to the Dated Brent index over the prior
  three days.
- **CFD market**: short-dated price differentials between Dated and the next
  six monthly futures. Traders use these to swap between physical and paper.
- **EFP (Exchange for Physical)**: swap a futures position for a physical
  cargo at a negotiated differential. Marks the basis between paper and
  cargo.

### WTI — the inland US benchmark

NYMEX CL settles physically at **Cushing, Oklahoma**, which sits at the
intersection of major pipelines. The benchmark's main weakness is that
Cushing inventories can become disconnected from coastal flows. The April
2020 negative-price event happened because Cushing tanks were filling and
nobody wanted physical delivery — futures longs paid traders to take the oil.

Important WTI variants:

- **WTI Houston** / **WTI Midland**: priced at Gulf Coast and Permian
  origin. These are closer to global parity (Brent linked) than Cushing WTI.
- **MEH (Magellan East Houston)**: a popular pipeline grade for export.
- **TI-Brent spread**: the canonical logistics indicator. When negative, US
  is exporting; when positive (rare), oil is moving to Cushing.

### Dubai/Oman — Asian benchmark

Dubai is settled in the **Platts MOC** (Market on Close) window via partial
bid/offer mechanics — Singapore traders bid in 25 kb partials between 16:00
and 16:30 Singapore time. The window is small enough that desks watch every
print. The S&P Global Platts Dubai assessment + DME Oman + Murban (recent
addition) form the Middle East complex.

### OSPs (Official Selling Prices)

Saudi Aramco's monthly OSPs are the single most-watched pricing decision
in the global market:

- **Asia OSP** = differential to **Dubai+Oman avg** for the loading month.
- **Europe OSP** = differential to **ICE Brent avg**.
- **US OSP** = differential to **ASCI (Argus Sour Crude Index)**.

A typical OSP cycle: physical Brent demand → Saudi raises Asia OSP →
refiners protest → next month adjusts. Aramco signals tightness via
+$1 to +$3 differentials and oversupply via discounts of -$1 to -$5.
Other NOCs (ADNOC for Murban, KPC for Kuwait crude, NIOC for Iranian)
follow Aramco's lead with their own K-factors.

### Quality differentials

Crude is priced off three properties:

1. **API gravity**: lighter = higher API. Light sweet (35–45 API) is most
   valuable for gasoline. Heavy sour (< 25 API) needs coking.
2. **Sulfur content**: sweet (< 0.5%) vs sour (> 0.5%). Marine fuel sulfur
   cap (IMO 2020 at 0.5%) crushed heavy-sour discounts post-2020.
3. **TAN (Total Acid Number)**: high TAN crudes (some West African, Russian
   ESPO) corrode refineries — only specially configured units can run them.

Light sweet WTI sells at a premium over Maya (Mexican heavy sour) of
$15–$25 typically. The spread compresses when complex refiners can't process
heavy crude (turnarounds, post-IMO-2020).

---

## Refining Economics

### Configurations from simplest to most complex

| Type             | Units                                | Yield bias               |
|------------------|---------------------------------------|--------------------------|
| Topping/skim     | Atmospheric distillation only         | Low gasoline, lots HSFO  |
| Hydroskimming    | + Hydrotreater                        | Low-sulfur middle dist.  |
| Cracking         | + FCC (Fluid Catalytic Cracker)       | High gasoline yield      |
| Coking           | + Delayed Coker                       | Heavy crude capability   |
| Hydrocracking    | + Hydrocracker                        | Premium distillate yield |

The **Nelson Complexity Index** scores each unit and sums them. A simple
hydroskimmer is ~3.5; a US Gulf Coast deep-conversion refinery (Marathon
Galveston Bay, ExxonMobil Beaumont) hits 12+. Complexity = ability to take
cheap heavy crude and crack it into premium products.

### Crack spreads explained

A crack spread is the gross margin between input crude and output products.
It does NOT include fixed costs, energy, hydrogen, catalyst — only the
revenue side.

- **3-2-1 (US Gulf benchmark)**: 3 barrels crude → 2 gasoline + 1 distillate.
  Formula: `(2 × RBOB) + (1 × HO) - (3 × WTI), all in $/bbl`. Reported
  daily.
- **5-3-2 (USGC large-coker)**: 5 crude → 3 gasoline + 2 distillate. Better
  fits Gulf Coast yield curves.
- **Brent NWE crack**: 1:1 crack vs ICE Gasoil. Watched by European refiners.
- **Singapore complex**: Dubai feedstock, MOPS gasoline, MOPS gasoil,
  separate fuel-oil components.

When crack spreads collapse (below ~$10/bbl 3-2-1), refineries cut runs —
which reduces demand for crude — which feeds back to crude weakness. When
cracks blow out ($40+/bbl 3-2-1 as seen in 2022), refineries run flat-out
and pull crude harder than supply can provide.

### Maintenance turnarounds

Spring (March–May) and fall (September–November) are heavy turnaround
seasons in the Northern Hemisphere. ~3–5% of global refining capacity is
offline during peak. This biases the **crack spread** higher in those
months and reduces crude pull.

### IMO 2020 and heavy sour discount compression

Before January 1 2020, marine bunkers could be 3.5% sulfur HSFO. After,
limit was 0.5% (VLSFO) or scrubbed HSFO with scrubbers. Demand for HSFO
collapsed by ~3 mb/d, demand for VLSFO/MGO jumped. Heavy sour crudes (Maya,
Urals, Castilla, Iranian Heavy) — which yield a lot of HSFO — saw their
discounts to Brent compress from $10–$15 to $3–$5. This rebalanced the
relative attractiveness of complex coking refiners.

---

## Storage and Logistics

### Cushing dynamics

Cushing's working capacity is ~78 million barrels with operational shell
capacity around 90 million. The hub serves 13+ pipelines and is the WTI
futures delivery point. When stocks approach 65 mb (the "tank tops"
threshold), the term structure goes deep contango — front-month falls below
storage-cost-adjusted second month — to incentivize draws. April 2020 hit
this constraint and overshot.

### The contango / floating storage trade

If `(M2 - M1) > all-in storage cost (rent + insurance + cost of capital)`,
a trader can buy M1, sell M2, store the crude, and lock in a riskless
profit. All-in costs:

- Onshore tank: ~$0.40–$0.60/bbl/month
- Floating storage on a VLCC: ~$0.80–$1.20/bbl/month + capital cost
- Total break-even contango: typically $0.55/bbl/month (~$6.60/bbl/year)

When M1-M2 contango exceeds $1, floating storage demand explodes — 200+
VLCCs at peak in 2020. This tightens tanker rates everywhere and adds to
the contango by absorbing crude.

### SPR (Strategic Petroleum Reserve)

- Capacity: 727 million barrels, fully built. Currently held ~360 mb after
  2022 historic drawdown.
- Drawdown rate cap: ~4.4 mb/d for 90 days (rarely tested).
- Refill: Treasury must allocate funds; oil bought via solicitation in
  $1–$2/bbl tranches. Replenishment is slow because of price-discipline
  rules.
- Releases historically: 1991 (Gulf War), 2005 (Katrina), 2011 (Libya),
  2022 (Russia-Ukraine — 180 mb largest ever).

SPR releases are bearish near-term (extra supply) but bullish medium-term
(future buyback demand on the curve). The 2022 release coincided with the
$130 peak — without it, prices likely run $150+.

### Tanker classifications

| Class    | DWT          | Capacity (kb)    | Routes                       |
|----------|--------------|-------------------|------------------------------|
| ULCC     | 320k+        | 2,000–3,000       | (Rare) Persian Gulf-Asia     |
| VLCC     | 200–320k     | 1,800–2,200       | AG → Asia, USGC → Asia/EU    |
| Suezmax  | 120–200k     | 800–1,000         | Med, WAF, Brazil → US        |
| Aframax  | 80–120k      | 500–800           | NW Europe, North Sea, Cuba   |
| Panamax  | 60–80k       | 350–500           | Caribbean, US Gulf shorts    |
| MR       | 35–55k       | 200–350           | Clean product trade          |

### Freight rate signals

- **BDTI (Baltic Dirty Tanker Index)**: clean crude tanker rates.
- **BCTI (Baltic Clean Tanker Index)**: product (gasoline, diesel) rates.
- **Worldscale (WS)**: flat-rate quotation. WS100 means standard rate per
  ton. WS75 means -25% to the flat. WS200 in tight markets.

Freight spikes (BDTI rising fast) signal: tight supply of VLCCs (often
linked to floating storage), longer routes (Red Sea diversions via Cape),
or sudden demand (China stockpiling). When AG-Asia WS > 100, that
incrementally adds $2–$4/bbl to landed Brent for Asian refiners.

---

## Geopolitics Playbook

### Hormuz scenarios (probability-weighted)

The Strait of Hormuz handles ~21 mb/d of oil + ~10 bcf/d of LNG (Qatar).
Iran sits on the north shore; UAE/Oman south. Three credible scenarios:

1. **Full closure** — politically unimaginable. Iran loses its own export
   route. Saudi could reroute ~5 mb/d via East-West pipeline (Petroline)
   to Yanbu on the Red Sea, but West Africa and Asian gulf buyers lose
   their primary supply. Expected price reaction: +$30–$50/bbl in days,
   strategic SPR response, military intervention.
2. **Partial / shadow disruption** — Iran's playbook. Limpet mines, GPS
   spoofing, IRGC boat swarming. Insurance war-risk premiums jump 10x;
   tanker rates double; freight adds $4–$8/bbl. Price reaction: $5–$15.
   Examples: 2019 Limpet mine attacks, 2024 IRGC seizures.
3. **Symbolic posture** — drills, naval exercises, missile launches into
   the Gulf. Insurance ticks up but flows continue. Price reaction:
   $1–$3 and decays in a week.

### Iran sanctions mechanics

Iran exports ~1.0–1.8 mb/d depending on enforcement and Chinese teapot
appetite. The route:

- **SWIFT**: Iran cut from interbank messaging since 2018. Workaround: barter,
  yuan settlement, gold, INSTEX (largely inert).
- **Secondary sanctions**: US Treasury can sanction any foreign entity buying
  Iranian crude. Enforcement intensity varies wildly with administration.
- **Tanker rebranding**: dark fleet (~80 VLCCs) with AIS spoofing, transponder
  switch-offs, and Tehran-funded P&I insurance. Tanker tracking via Kpler /
  Vortexa relies on partial AIS + satellite identification.

### Russia and the G7 price cap

The G7 price cap (December 2022, $60/bbl initially) prohibits Western
services (insurance, shipping, finance) for Russian crude sold above the
cap. Enforced via attestations down the chain. Russia's response:

- Shadow fleet: built or repurposed ~200 tankers under non-Western flags
  (Liberia, Marshall Islands, plus Russian state) with Russian insurance.
- India/China discount: Urals sells at ~$15–$25 discount to Brent. Indian
  refiners (Reliance, Indian Oil) take it and re-export refined products
  back to Europe under a different tariff classification — a sanctions
  bypass that everyone tolerates.
- ESPO grade flows direct to China via Kozmino pipeline + tankers from
  Sakhalin. ESPO trades at near-Brent parity into China.

### Houthi attacks and Red Sea routing

Yemen's Houthi militants began Red Sea / Bab el-Mandeb attacks in October
2023 in response to the Israel-Hamas war. Effects:

- ~70% of normal Suez Canal traffic diverted around Cape of Good Hope.
- Adds 10–15 days to Asia-Europe oil routes.
- Insurance hike: war-risk premium for Red Sea transit went from 0.05% to
  0.7% of hull value briefly — $400k+ extra per VLCC.
- Refinery feedstock cost in NW Europe: +$2–$4/bbl during peak diversion.

### Venezuela, Libya, Iraq

- **Venezuela**: Production declined from 3.0 mb/d (2014) to ~0.8 mb/d
  (2023) due to PDVSA collapse. Chevron has OFAC license to operate four
  joint ventures since 2022; 200 kb/d incremental supply.
- **Libya**: Eastern (LNA/Haftar) vs Western (GNU/Tripoli) factions
  alternate shutting in El-Sharara and El-Feel fields. Production oscillates
  500–1,200 kb/d.
- **Iraq**: Northern Kurdistan via Ceyhan (Turkey) versus southern Basra
  via Persian Gulf. Kurdish pipeline shut March 2023 in legal dispute —
  450 kb/d offline. Still partially shut as of 2026.

---

## Macro Linkages

### DXY-oil inverse correlation

Oil is priced in dollars, so a stronger dollar mechanically makes oil more
expensive for non-dollar buyers, suppressing demand. The inverse correlation
runs roughly -0.5 to -0.7 over rolling 30-day windows. It strengthens
during macro stress and decouples during oil-specific events (e.g. OPEC cut
news moves oil regardless of DXY).

A useful adjustment: **DXY-deflated oil** (Brent / DXY × 100) removes the
currency effect and reveals true demand-driven moves.

### Real yields and the inflation hedge

When the 10y TIPS real yield falls, real assets (gold, oil, copper) rally.
The mechanism: lower real yields = lower discount rate on future commodity
cash flows + greater attractiveness of inflation hedges. Oil-gold
correlation historically ~0.3 but jumps to 0.6+ during stagflation regimes.

### China demand — the marginal buyer

China imports ~11 mb/d of crude (~50% of seaborne). Key tells:

- **Strategic reserves build**: SPR equivalents in Dalian, Zhoushan,
  Huangdao. When refining margins are weak but imports stay strong, that's
  SPR building.
- **Independent refiners (teapots)**: Shandong-based small refiners with
  variable utilization. They're the price-takers — drop runs hard in low-
  margin environments.
- **EV penetration**: gasoline demand peaked in 2023 per CNPC estimates.
  Diesel and jet fuel still growing for now.

### Recession signals and oil demand

- **US yield curve inversion** (2y > 10y) precedes recession by 12–18m. In
  every recession since 1973, oil demand fell 1–3 mb/d.
- **Global manufacturing PMI < 47**: distillate demand weakens sharply.
- **US gasoline demand**: track 4-week average from EIA weekly. Below
  9 mb/d in summer = weak driving season.
- **Jet fuel demand**: TSA throughput is a high-frequency proxy.

### FOMC reaction function

Oil moves Fed policy through CPI. Headline CPI has ~6% direct energy
weight + indirect effects via transport, food. A $20 rally adds ~0.5pp to
y/y CPI. Watch for hawkish Fed pivots after large oil rallies; the 2022
Fed hiking cycle was accelerated by Russia-driven oil + food spikes.

---

## Positioning and Sentiment Theory

### CFTC COT (Commitment of Traders) deep read

CFTC publishes Tuesday positioning every Friday. Three categories matter:

1. **Managed Money (speculators)**: hedge funds and CTAs. Net long
   position from 100k to 300k contracts typical. Above 350k = crowded
   long. Below 50k = crowded short.
2. **Producers/Merchants (commercials)**: oil companies, refiners
   hedging physical exposure. Always net short (hedging future
   production).
3. **Swap Dealers**: investment banks intermediating ETF flows. The
   USO ETF's flow is reflected here.

The contrarian rule: when Managed Money percentile (vs 5-year history)
exceeds 85th, expect rolling longs to unwind on the next bad headline.
When below 15th, contrarian upside.

### Open interest dynamics — the index roll

S&P GSCI and Bloomberg BCOM index funds roll long futures positions
between the 5th and 9th business day of each month, selling the front
contract and buying the next. This generates predictable selling pressure
on the front-month / buying pressure on the 2nd month for that 5-day
window. Astute traders fade the calendar-spread move that the roll
creates.

### Volatility surface — beyond the IV percentile

- **OVX**: the oil VIX. Below 30 = complacent. Above 50 = stressed.
- **Skew (25-delta risk reversal)**: difference between out-of-the-money
  put IV and OTM call IV. Negative skew = puts more expensive = downside
  fear dominant. Positive skew = call skew = upside fear (rare, supply
  shock scenarios).
- **Term structure of IV**: when front IV exceeds back IV by > 5 vol
  points, it's a "vol spike" — short front vol, long back vol is a classic
  trade if no event imminent.

### Sentiment composite read

Combine: CFTC percentile (positioning), OVX level (vol regime), IV skew
(directional fear), and news sentiment (FinBERT composite). When all four
align bearishly, capitulation is near. When all four align bullishly,
exhaustion top.

---

## Term Structure and Calendar Spread Trading

### Backwardation vs contango — what they signal

**Backwardation** (M1 > M2 > M3 …): physical buyers paying a premium for
immediate delivery. Causes:

- Inventory tightness (visible stocks below 5-year average)
- Geopolitical risk premium (supply uncertainty)
- Refinery pull (high crack spreads → run flat-out)

When the M1-M2 spread exceeds +$1.50 on Brent, you're in steep
backwardation — short-term hedgers are paying up.

**Contango** (M1 < M2 < M3 …): excess supply. Storage arbitrage opens at
$0.50+/bbl/month. Causes:

- Oversupply (OPEC+ adds, weak demand)
- Refinery turnarounds (less crude pull)
- Recession / demand destruction

Super-contango (M1-M2 < -$2) was last seen in April 2020. Reliable
recession signal.

### M1-M2 as a fast tell

Watch the M1-M2 spread vs implied storage cost:

| M1-M2 spread       | Read                                      |
|--------------------|-------------------------------------------|
| > +$2              | Severe immediate tightness, draw expected |
| +$0.50 to +$2      | Mild backwardation, normal tightness      |
| ~$0                | Flat, undecided                           |
| -$0.50 to -$1.50   | Mild contango, building inventory         |
| < -$1.50           | Storage play opening, deep oversupply     |

### Calendar spread trades

- **Long M1 / short M2** = bullish front (backwardation steepening). Profits
  when M1 climbs faster than M2. Risk: front collapses on bearish data.
- **Long M1 / short M12** (long-dated) = backwardation-flattening directional
  trade. Sensitive to forward curve shape, less to spot moves.
- **Bull spreads in WTI versus Brent**: trade WTI calendar spread vs Brent
  calendar spread. Captures regional differences in storage/logistics.

### Brent-WTI as logistics tell

The Brent-WTI spread is structurally positive (Brent > WTI) because of US
crude oversupply (shale boom). Watch widening when:

- US production grows faster than export capacity (pipeline / port
  constraints).
- Brent rallies on geopolitics (Russia, Iran) before WTI catches up.
- Cushing inventories build (WTI suppression).

Narrowing or going negative is rare and signals: US export bottleneck
relieved, Cushing draws, Atlantic basin tightness, or Permian production
disappointment.

---

## Historical Case Studies (Trader Lens)

### 2008 — $147 oil peak and crash to $32

Setup: China demand inflated by Olympics/infrastructure, weak dollar,
financial speculation peak, low spare capacity (~1.5 mb/d). July 2008 spot
$147.27. By December: $32.40. Demand destruction was the trigger
(global recession); supply unchanged. Lesson: oil over $130 always brings
demand destruction within 6 months historically.

### 2014–2016 — Saudi market share war and shale shakeout

OPEC November 2014 decision: maintain production rather than cut against
shale. Brent fell from $110 to $26 by January 2016. Saudi's bet: shale
breakeven was ~$65; sustained $40 would bankrupt them. Result: shale
adapted (drilling efficiency up 50% in 18 months), Saudi ran $90 billion
deficit, OPEC capitulated November 2016 — first cut in 8 years. Lesson:
shale is more elastic than NOCs expected; market share strategy backfires.

### 2020 — Negative WTI and the storage crisis

COVID-19 demand crash + Saudi-Russia price war = 30 mb/d demand drop
plus OPEC+ failure. Cushing tanks filled by mid-April. May WTI futures
expired April 20 at -$37.63 — sellers paid buyers to take crude. The
mechanism: most futures longs were ETF-driven retail (USO), unable to
take delivery, scrambling to sell at expiry. Lesson: storage constraints
matter enormously. Cushing tank-tops thesis is real.

### 2022 — Russia invasion, SPR release, $130 peak

February 24 invasion. Brent $90 → $128 by March 8 (peak intraday $139).
G7 announced unprecedented 180 mb SPR release; Biden trip to Saudi
asking for cooperation (denied). By December, OPEC+ cut 2 mb/d ahead of
the price cap implementation. End-2022: Brent $80. Lesson: SPR releases
suppress the spike but transfer the rally to next-year curve (forward
buyback). Watch curve flattening rather than spot for true tightness.

### 2024 — Houthi attacks and Cape rerouting

October 2023 Israel-Hamas → Houthi Red Sea attacks November onward.
Tanker rates AG-Europe via Cape +50%. Insurance premiums spiked. Asian
refiners' landed cost +$3–$5/bbl. Yet Brent didn't break $90 because
spare capacity (~5 mb/d at the time) was ample. Lesson: routing
disruptions matter for differentials and freight, not flat price, when
spare capacity is high.

---

## Market Microstructure

### Settlement windows

- **ICE Brent**: settles to ICE Brent Index based on volume-weighted
  trades during 19:28–19:30 GMT (4:28–4:30 PM London winter, 19:28–19:30
  London summer).
- **NYMEX WTI**: settles to volume-weighted trades during 14:28–14:30 ET.
- **TAS (Trade-at-Settlement)**: orders that lock in the settlement
  price ± a defined differential, executed during settlement window.
  Used heavily by index funds for clean execution.

### Expiry mechanics

- WTI: front-month expires on the third business day before the 25th of
  the month prior to delivery month. Most traders roll well before
  expiry to avoid physical delivery.
- Brent: expires on the last business day of the second month before
  delivery (cash settled, no physical at exchange level).

### Roll mechanics

The "GSCI roll" (5th–9th business day each month) is the major
calendar-spread event:

- GSCI and BCOM index funds need to roll long futures forward.
- Generates ~$50 billion in calendar-spread flow per roll.
- Tends to widen contango or compress backwardation during the roll.
- Astute traders sell M1-M2 a few days before, buy back during the roll.

### Options structures

- **Risk reversal**: buy OTM call, sell OTM put. Bullish directional, cheap.
- **Collar**: buy ATM put, sell OTM call. Protected long.
- **Iron condor**: sell put spread, sell call spread. Range-bound
  premium-collection.
- **Calendar spread**: long back-month option, short front-month. Capture
  vol surface skew.

### Exchange minimums and SPAN margin

- Brent contract = 1,000 barrels. Tick size $0.01 = $10/contract.
- WTI contract = 1,000 barrels. Same tick economics.
- Initial margin: ~$8–$10k per contract in normal vol regime. Doubles in
  stress.
- Maintenance margin: ~75% of initial. Below = margin call.
- SPAN methodology nets spreads against outright positions (calendar
  spreads have 80%+ margin offsets).

### EFP and EFS mechanics

- **EFP (Exchange for Physical)**: swap a futures position for a physical
  cargo. Negotiated bilaterally, reported to the exchange. Establishes the
  basis between paper and physical.
- **EFS (Exchange for Swap)**: swap futures for an OTC swap. Used to
  manage roll exposure or basis differentials.

Both clear via the exchange clearinghouse and count toward open interest.

---

## Quick-Reference Decision Heuristics

When asked "what does X mean for oil," anchor in this hierarchy:

1. **Supply event** (disruption, cut, sanctions) → check **spare capacity**.
   If < 2 mb/d, big move. If > 4 mb/d, contained.
2. **Demand event** (recession, China, EV) → check **inventory direction**.
   If draws continue despite weak data, supply tightness wins.
3. **Geopolitics** → check **freight rates** and **insurance premia** as
   real-time tells, not headlines.
4. **OPEC action** → check **compliance** of prior commitments before
   trusting new ones.
5. **Macro shift** (DXY, real yields) → adjust for the currency-deflated
   move before judging fundamental direction.

When uncertain, watch what the **term structure** says — it aggregates
physical traders' real-time bets on tightness. The curve front (M1-M2)
is the single highest-information variable in oil markets.
