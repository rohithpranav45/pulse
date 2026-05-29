/**
 * Four historical case studies straight out of chapter 8 of the
 * Oil Macro Trading curriculum. Each one captures the indicators
 * that flashed, what PULSE would have said, and what actually
 * happened. Designed as a teaching tool first, a backtest hint second.
 */

export type CaseStudyKeyMetric = {
  label: string;
  value: string;
  tone?: 'bull' | 'bear' | 'neut' | 'gold';
  detail?: string;
};

export type CaseStudyIndicator = {
  name: string;
  reading: string;
  score: number;
  weight: number;
  tone: 'bull' | 'bear' | 'neut';
};

export type CaseStudyTimeline = {
  date: string;
  event: string;
  priceImpact?: string;
};

export type CaseStudy = {
  id: string;
  title: string;
  subtitle: string;
  period: string;
  priceMove: { from: number; to: number; pctChange: number };
  pulseVerdict: { label: string; score: number; conviction: 'HIGH' | 'MODERATE' | 'LOW' };
  pulseDirection: 'bull' | 'bear' | 'neut';
  pulseWouldHaveCalled: string;
  keyMetrics: CaseStudyKeyMetric[];
  indicators: CaseStudyIndicator[];
  timeline: CaseStudyTimeline[];
  lessons: string[];
  curriculumRef: string;
};

export const CASE_STUDIES: CaseStudy[] = [
  // ─── 2008 SPIKE ─────────────────────────────────────────────────────────────
  {
    id: '2008',
    title: '2008 Oil Spike',
    subtitle: 'Brent to $147 — spare capacity exhausted',
    period: 'Q3 2007 → July 2008',
    priceMove: { from: 65, to: 147, pctChange: +126 },
    pulseVerdict: { label: 'STRONG BULLISH', score: 1.65, conviction: 'HIGH' },
    pulseDirection: 'bull',
    pulseWouldHaveCalled:
      'Backwardation + spare capacity at decade lows + Chinese demand boom + weak dollar = highest-conviction bull setup of the decade.',
    keyMetrics: [
      { label: 'OPEC spare capacity', value: '~1.5 mbd', tone: 'bull', detail: 'lowest since early 2000s' },
      { label: 'Chinese demand growth', value: '+800 kbd YoY', tone: 'bull', detail: 'pre-Beijing Olympics build-out' },
      { label: 'Curve structure', value: 'STEEP BACKWARDATION', tone: 'bull' },
      { label: 'DXY', value: 'weakening to 71', tone: 'bull', detail: 'Fed cutting aggressively' },
      { label: 'CFTC MM net long', value: 'record high', tone: 'bear', detail: 'speculative crowding' },
      { label: 'Non-OPEC supply', value: 'disappointing', tone: 'bull', detail: 'Russia, North Sea, Mexico all flat' },
    ],
    indicators: [
      { name: 'Curve',      reading: 'Deep backwardation — M1-M2 +$1.50',                  score: +2, weight: 0.18, tone: 'bull' },
      { name: 'Inventory',  reading: 'OECD stocks below 5y avg',                            score: +1, weight: 0.28, tone: 'bull' },
      { name: 'Geo Risk',   reading: 'Nigeria MEND attacks + Iran nuclear tension',         score: +2, weight: 0.04, tone: 'bull' },
      { name: 'DXY',        reading: 'Weak USD — Fed cutting',                              score: +2, weight: 0.05, tone: 'bull' },
      { name: 'Fair Value', reading: 'Spot ~$120 vs $80 model — extremely overvalued',     score: -2, weight: 0.12, tone: 'bear' },
      { name: 'COT',        reading: 'MM net long at record — crowded',                     score: -1, weight: 0.15, tone: 'bear' },
      { name: 'Sentiment',  reading: 'Energy news euphoric',                                score: +2, weight: 0.08, tone: 'bull' },
    ],
    timeline: [
      { date: '2007-Q3',  event: 'Brent breaks $80; backwardation deepens',                priceImpact: 'Brent +20%' },
      { date: '2008-Jan', event: 'Brent at $90; spare capacity to 1.5 mbd',                priceImpact: '' },
      { date: '2008-Mar', event: 'Brent $100; CFTC MM net long at all-time high',          priceImpact: '+11%' },
      { date: '2008-Jul', event: 'Peak $147.50 intraday',                                  priceImpact: '+50% from Jan' },
      { date: '2008-Sep', event: 'Lehman Brothers bankruptcy — demand shock',              priceImpact: '−25%' },
      { date: '2008-Dec', event: 'Brent $32 — fell from $147 in 5 months',                 priceImpact: '−78%' },
    ],
    lessons: [
      'Spare capacity is the denominator — at 1.5 mbd, every 0.3 mbd disruption became a $5+ move.',
      'Backwardation validated the physical tightness; this was NOT a financial spike.',
      'But: extreme CFTC positioning is always a final-leg warning — the reversal was vicious when demand cracked.',
      'Macro shock (Lehman) overrode oil-specific fundamentals in days.',
    ],
    curriculumRef: 'Chapter 8 §3, Chapter 2 §5 (Spare Capacity)',
  },

  // ─── 2014 SHALE CRASH ───────────────────────────────────────────────────────
  {
    id: '2014',
    title: '2014 Shale Crash',
    subtitle: 'Brent $115 → $27 — OPEC abandons swing producer role',
    period: 'June 2014 → January 2016',
    priceMove: { from: 115, to: 27, pctChange: -77 },
    pulseVerdict: { label: 'STRONG BEARISH', score: -1.55, conviction: 'HIGH' },
    pulseDirection: 'bear',
    pulseWouldHaveCalled:
      'Shale supply +1.5 mbd, OPEC refusing to cut, OECD stocks building +280 mmbbls, steep contango = textbook supply-glut bear case.',
    keyMetrics: [
      { label: 'US shale growth',      value: '+1.5 mbd YoY',  tone: 'bear' },
      { label: 'OPEC decision (Nov 14)',value: 'NO CUT',        tone: 'bear', detail: 'Saudi fights for market share' },
      { label: 'Spare capacity',       value: '~4.5 mbd',      tone: 'bear', detail: 'highest since 2010' },
      { label: 'Curve structure',      value: 'STEEP CONTANGO',tone: 'bear', detail: 'peak ~$12/bbl M1-M12' },
      { label: 'OECD stock build',     value: '+280 mmbbls',   tone: 'bear', detail: 'over 19 months' },
      { label: 'US rig count peak',    value: '1,609 (Oct 14)',tone: 'bear', detail: 'fell to 404 by May 16' },
    ],
    indicators: [
      { name: 'Inventory',  reading: 'OECD stocks +280 mmbbls vs 5y avg',                   score: -2, weight: 0.28, tone: 'bear' },
      { name: 'Curve',      reading: 'Deep contango M1-M12 ~$12',                            score: -2, weight: 0.18, tone: 'bear' },
      { name: 'Fair Value', reading: 'Spot 30% below cost-of-carry model',                   score: +1, weight: 0.12, tone: 'bull' },
      { name: 'COT',        reading: 'MM still net long — slow to short',                    score: -1, weight: 0.15, tone: 'bear' },
      { name: 'DXY',        reading: 'Strong USD - DXY rising to 100',                       score: -2, weight: 0.05, tone: 'bear' },
      { name: 'Geo Risk',   reading: 'No supply disruptions — calm geo',                     score:  0, weight: 0.04, tone: 'neut' },
      { name: 'Sentiment',  reading: 'Bearish — "lower for longer" consensus',               score: -1, weight: 0.08, tone: 'bear' },
    ],
    timeline: [
      { date: '2014-H1',  event: 'US shale adds 1.5 mbd; stocks begin building',            priceImpact: 'Brent flat $108' },
      { date: '2014-Jun', event: 'Brent peaks $115',                                         priceImpact: 'high water' },
      { date: '2014-Nov', event: 'OPEC Vienna meeting: NO CUT. Saudi defends market share', priceImpact: '−30% in 6 weeks' },
      { date: '2015-Jan', event: 'Brent $46 — half its level in 6 months',                  priceImpact: '−60%' },
      { date: '2016-Jan', event: 'Brent $27 — 13y low',                                     priceImpact: '−77% peak-trough' },
      { date: '2016-Nov', event: 'OPEC+ formed; first coordinated cut with Russia',         priceImpact: 'recovery starts' },
    ],
    lessons: [
      'Shale supply elasticity is the new ceiling — at $70+, supply responds in 6 months, not 6 years.',
      'When OPEC chooses share over price, the trough is much deeper and slower than usual.',
      'Contango ceiling at full carry (~$15/bbl over 12mo) eventually triggers storage arbitrage that absorbs excess.',
      'OPEC+ creation in 2016 was the structural response — Russia inside the tent ever since.',
    ],
    curriculumRef: 'Chapter 8 §3 (Case Study 2), Chapter 2 §3 (Capital Cycle)',
  },

  // ─── 2020 COVID NEGATIVE WTI ─────────────────────────────────────────────────
  {
    id: '2020',
    title: '2020 COVID / Negative WTI',
    subtitle: 'WTI to −$37 — physical delivery into a full Cushing',
    period: 'Mar → Apr 2020',
    priceMove: { from: 60, to: -37, pctChange: -161 },
    pulseVerdict: { label: 'STRONG BEARISH', score: -1.82, conviction: 'HIGH' },
    pulseDirection: 'bear',
    pulseWouldHaveCalled:
      'Demand crater −20 mbd + Saudi-Russia price war + Cushing at 95% + floating storage at record = unprecedented bear setup. PULSE would flash STRONG SELL through March 2020.',
    keyMetrics: [
      { label: 'Demand shock',        value: '−20 mbd in Apr', tone: 'bear', detail: 'largest in history' },
      { label: 'Saudi price war',      value: 'Mar 8',           tone: 'bear', detail: 'unilateral output hike' },
      { label: 'Cushing fill',         value: '~95% Apr 20',    tone: 'bear', detail: 'effectively full' },
      { label: 'Floating storage',     value: '180-200 mmbbl',  tone: 'bear', detail: '~200 VLCCs at sea' },
      { label: 'Curve structure',      value: 'DEEPEST CONTANGO',tone: 'bear', detail: 'M1-M2 −$10' },
      { label: 'WTI May contract',     value: '−$37 intraday',  tone: 'bear', detail: 'physical delivery mechanics' },
    ],
    indicators: [
      { name: 'Inventory',  reading: 'Stocks building at unprecedented +60 mmbbls/month',    score: -2, weight: 0.28, tone: 'bear' },
      { name: 'Curve',      reading: 'Deepest contango on record M1-M2 −$10',                score: -2, weight: 0.18, tone: 'bear' },
      { name: 'Sentiment',  reading: 'COVID lockdowns + Saudi-Russia price war',             score: -2, weight: 0.08, tone: 'bear' },
      { name: 'Fair Value', reading: 'Spot −60% below model — model breaks',                 score: +2, weight: 0.12, tone: 'bull' },
      { name: 'Geo Risk',   reading: 'OPEC+ collapse — supply war',                          score: -2, weight: 0.04, tone: 'bear' },
      { name: 'DXY',        reading: 'USD spike on flight-to-quality',                       score: -2, weight: 0.05, tone: 'bear' },
      { name: 'COT',        reading: 'Speculators flipped short historically fast',          score: +1, weight: 0.15, tone: 'bull' },
    ],
    timeline: [
      { date: '2020-Jan-30', event: 'WHO declares COVID emergency',                          priceImpact: 'Brent −5%' },
      { date: '2020-Mar-8',  event: 'Saudi launches price war on Russia',                    priceImpact: 'Brent −24% next day' },
      { date: '2020-Mar-10', event: 'Italy lockdown — Europe shutting',                      priceImpact: '−10%' },
      { date: '2020-Apr-12', event: 'OPEC+ emergency cut −9.7 mbd',                          priceImpact: 'too late' },
      { date: '2020-Apr-20', event: 'WTI May contract trades −$37 intraday',                 priceImpact: 'negative oil' },
      { date: '2020-Nov-9',  event: 'Pfizer vaccine announcement',                           priceImpact: 'Brent +8% in a day' },
    ],
    lessons: [
      'Physical delivery mechanics matter — WTI is physically settled at Cushing; Brent is cash-settled. The −$37 print was specific to that.',
      'When contango exceeds full carry, storage fills until physically impossible, then forces price discovery violently.',
      'OPEC+ cuts work, but they take weeks-to-months to drain the resulting inventory overhang.',
      'Brent stayed positive at $25 the same day — global crude was not at −$37; this was a hub bottleneck.',
    ],
    curriculumRef: 'Chapter 8 §3 (Case Study 3), Chapter 3 §2 (Cushing 2020)',
  },

  // ─── 2022 WAR / ENERGY CRISIS ───────────────────────────────────────────────
  {
    id: '2022',
    title: '2022 War / Energy Crisis',
    subtitle: 'Brent to $130 — Russia invasion + tight market',
    period: 'Feb → June 2022',
    priceMove: { from: 95, to: 130, pctChange: +37 },
    pulseVerdict: { label: 'STRONG BULLISH', score: 1.48, conviction: 'HIGH' },
    pulseDirection: 'bull',
    pulseWouldHaveCalled:
      'Russia invasion + OECD stocks well below 5y avg + spare capacity to 1.5 mbd + sanctions threatening 2-3 mbd reroute. Bullish setup amplified by low-spare-capacity vulnerability.',
    keyMetrics: [
      { label: 'Russia-Ukraine war',   value: 'Feb 24',          tone: 'bull' },
      { label: 'Spare capacity',       value: '~1.5 mbd',        tone: 'bull', detail: 'near 2008 lows' },
      { label: 'Russian supply at risk',value: '2-3 mbd',        tone: 'bull', detail: 'eventually rerouted' },
      { label: 'OECD stocks vs 5y avg', value: 'well below',     tone: 'bull' },
      { label: 'US SPR release',       value: '180 mmbbls',      tone: 'bear', detail: 'capped the spike' },
      { label: 'European TTF gas',     value: '€340/MWh',        tone: 'bull', detail: '10x historical avg' },
    ],
    indicators: [
      { name: 'Geo Risk',   reading: 'Russia-Ukraine war + sanctions',                       score: +2, weight: 0.04, tone: 'bull' },
      { name: 'Inventory',  reading: 'OECD stocks well below 5y avg',                        score: +2, weight: 0.28, tone: 'bull' },
      { name: 'Curve',      reading: 'Sharp backwardation M1-M2 +$2',                        score: +2, weight: 0.18, tone: 'bull' },
      { name: 'Sentiment',  reading: 'Bullish — supply disruption headlines daily',          score: +2, weight: 0.08, tone: 'bull' },
      { name: 'Fair Value', reading: 'Spot $130 vs model $105 — extreme overvalue',          score: -2, weight: 0.12, tone: 'bear' },
      { name: 'COT',        reading: 'MM net long crowded but justified',                    score: -1, weight: 0.15, tone: 'bear' },
      { name: 'DXY',        reading: 'Strong USD on flight-to-quality',                      score: -1, weight: 0.05, tone: 'bear' },
    ],
    timeline: [
      { date: '2022-Feb-24', event: 'Russia invades Ukraine',                                priceImpact: 'Brent +10% in 3 days' },
      { date: '2022-Mar-8',  event: 'Brent peaks $130 intraday',                             priceImpact: 'high water' },
      { date: '2022-Apr',    event: 'US announces 180 mmbbl SPR release',                    priceImpact: 'capped advance' },
      { date: '2022-Jun',    event: 'Brent retreats to $115',                                priceImpact: '−12%' },
      { date: '2022-Dec',    event: 'G7 price cap on Russian crude at $60',                  priceImpact: 'shadow fleet emerges' },
      { date: '2023-Feb',    event: 'EU bans Russian products',                              priceImpact: 'European diesel cracks blow out' },
    ],
    lessons: [
      'Sanctions reroute supply, they don\'t destroy it. The 2-3 mbd "lost" Russian crude found India and China within weeks.',
      'SPR releases (180 mmbbls) capped the spike but don\'t alter the structural balance.',
      'Spare capacity at 1.5 mbd made every headline a $3-5 move — same as 2008.',
      'Multi-fuel crisis (oil + gas + power simultaneously) is a regime change from single-commodity events.',
      'Demand destruction eventually kicks in at extreme prices — EM fuel demand fell sharply by mid-2022.',
    ],
    curriculumRef: 'Chapter 8 §3 (Case Study 4), Chapter 10 §2 (Sanctions)',
  },
];

export function getCaseStudy(id: string): CaseStudy | undefined {
  return CASE_STUDIES.find(c => c.id === id);
}
