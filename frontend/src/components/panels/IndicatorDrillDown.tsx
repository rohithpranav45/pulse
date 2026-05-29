import { Modal } from '@/components/ui/Modal';
import { Chip } from '@/components/ui/Chip';
import { ScoreBar } from '@/components/ui/ScoreBar';
import clsx from 'clsx';
import { Activity, Target, BookOpen, Layers } from 'lucide-react';

/**
 * Curriculum-grade reference card for each signal indicator.
 * Tells the user WHAT the indicator measures, WHY it matters, the
 * EXACT FORMULA / RULE, and CHAPTER REFERENCE in the training book.
 */
type Reference = {
  name: string;
  chapter: string;
  source: string;
  what: string;
  why: string;
  formula: string;
  interpretation: { range: string; meaning: string; tone: 'bull' | 'bear' | 'neut' }[];
  caveat?: string;
};

const REFS: Record<string, Reference> = {
  Inventory: {
    name: 'Inventory',
    chapter: 'Chapter 6 — The Inventory System',
    source: 'EIA Weekly Petroleum Status Report (Wed 10:30 EST)',
    what: 'Deviation of US crude commercial stocks from the 5-year seasonal average for the same calendar week.',
    why: 'Inventories are the oil market\'s shock absorber. When stocks are well below the 5-year average, the physical market is tight — bullish. When well above, oversupply — bearish. OECD inventories vs the 5-year average is the explicit framework OPEC+ uses to define "balanced."',
    formula: 'score = +2 if dev < −10%, +1 if dev < −4%, 0 if |dev| < 4%, −1 if dev > 4%, −2 if dev > 10%',
    interpretation: [
      { range: '< −10%', meaning: 'Very tight — extreme draw vs seasonal', tone: 'bull' },
      { range: '−10% to −4%', meaning: 'Below normal — supportive', tone: 'bull' },
      { range: '±4%', meaning: 'Balanced', tone: 'neut' },
      { range: '+4% to +10%', meaning: 'Above normal — supply heavy', tone: 'bear' },
      { range: '> +10%', meaning: 'Extreme build — oversupplied', tone: 'bear' },
    ],
    caveat: 'US-only inventory. Chinese stocks (largest single unknown) are estimated from import flows.',
  },
  Curve: {
    name: 'Curve',
    chapter: 'Chapter 8 — Market Pricing (forward curves)',
    source: 'Live ICE Brent + NYMEX WTI futures',
    what: 'Shape of the M1-M2 spread on the WTI futures curve.',
    why: 'Backwardation (M1 > M2) means buyers are paying up for prompt barrels — physical tightness. Contango (M1 < M2) means storage is incentivised — oversupply. The curve is the cleanest single read of physical balance because it reflects the willingness of refineries and end-users to pay a premium for immediate delivery.',
    formula: 'Backwardation (M1 > M2 by $1+) → +2. Mild back → +1. Flat/mild contango → 0. Steep contango → −1.',
    interpretation: [
      { range: 'Strong backwardation (>$1)', meaning: 'Tight physical market', tone: 'bull' },
      { range: 'Mild backwardation', meaning: 'Balanced, slightly tight', tone: 'bull' },
      { range: 'Flat (±$0.30)', meaning: 'Balanced', tone: 'neut' },
      { range: 'Steep contango', meaning: 'Oversupply, storage filling', tone: 'bear' },
    ],
    caveat: 'Contango cannot exceed full carry cost (~$1.5-3/bbl per month). Beyond that, storage arbitrage collapses it.',
  },
  COT: {
    name: 'COT (Positioning)',
    chapter: 'Chapter 7 — The Measurement Layer',
    source: 'CFTC Commitments of Traders (weekly, Fri PM)',
    what: '3-year percentile of Managed Money net long contracts in WTI futures.',
    why: 'Captures crowding in speculative positioning. At >85th percentile, hedge funds are crowded long — vulnerable to a sharp reversal (long squeeze). At <15th percentile, speculators are washed out — often a contrarian buy signal.',
    formula: 'Inverted: extreme long positioning (>85th %ile) = bearish (−2). Extreme short (<15) = bullish (+2). Middle = neutral.',
    interpretation: [
      { range: '<15th %ile', meaning: 'Speculatively washed out — contrarian bullish', tone: 'bull' },
      { range: '15-30', meaning: 'Lightly short — supportive', tone: 'bull' },
      { range: '30-70', meaning: 'Balanced', tone: 'neut' },
      { range: '70-85', meaning: 'Crowded long — caution', tone: 'bear' },
      { range: '>85th', meaning: 'Squeeze risk — sharp reversal possible', tone: 'bear' },
    ],
    caveat: 'COT data is reported Tuesday with a 3-day lag. Crowded positioning can stay crowded for weeks.',
  },
  'Fair Value': {
    name: 'Fair Value',
    chapter: 'Internal model — cost-of-carry + adjustments',
    source: 'PULSE fair_value.py',
    what: 'Deviation of spot price from a regression fair value built from cost-of-carry, inventory, OPEC compliance, DXY, and geo premium.',
    why: 'When price diverges substantially from model fair value without a clear fundamental driver, mean-reversion bias appears. Overvaluation = sell pressure builds; undervaluation = buy pressure builds.',
    formula: 'score = +2 if spot −8% below FV, +1 if −4 to −8%, 0 if ±4%, −1 if +4 to +8%, −2 if >+8%',
    interpretation: [
      { range: '< −8%', meaning: 'Deeply undervalued', tone: 'bull' },
      { range: '−4 to −8%', meaning: 'Undervalued', tone: 'bull' },
      { range: '±4%', meaning: 'Fair', tone: 'neut' },
      { range: '+4 to +8%', meaning: 'Overextended', tone: 'bear' },
      { range: '> +8%', meaning: 'Extreme overvalue', tone: 'bear' },
    ],
    caveat: 'Mean-reversion is asymmetric: overvalued markets can stay overvalued in trending regimes (2008, 2022).',
  },
  Sentiment: {
    name: 'Sentiment',
    chapter: 'Chapter 7 — Alternative data',
    source: 'FinBERT (ProsusAI/finbert) on energy news headlines',
    what: 'Recency-weighted composite of FinBERT sentiment scores on the last ~15 energy headlines.',
    why: 'News sentiment can move markets ahead of fundamentals showing up in data. Composite > +0.2 = strongly positive flow; < −0.2 = bearish flow.',
    formula: 'score = sign-matched scaling of composite sentiment (-1..+1) into −2..+2.',
    interpretation: [
      { range: '> +0.3', meaning: 'Strong bullish news flow', tone: 'bull' },
      { range: '+0.1 to +0.3', meaning: 'Mildly bullish flow', tone: 'bull' },
      { range: '±0.1', meaning: 'Mixed news', tone: 'neut' },
      { range: '−0.1 to −0.3', meaning: 'Mildly bearish flow', tone: 'bear' },
      { range: '< −0.3', meaning: 'Strong negative news flow', tone: 'bear' },
    ],
    caveat: 'FinBERT is general financial; not energy-fine-tuned. Mis-tags ambiguous headlines.',
  },
  Technicals: {
    name: 'Technicals',
    chapter: 'Technical analysis composite',
    source: 'Live yfinance OHLCV',
    what: 'Composite of RSI(14), MACD(12,26,9), Bollinger Bands(20,2σ), and ATR(14) on Brent/WTI daily.',
    why: 'Captures short-term momentum and overbought/oversold conditions. Useful as a timing overlay, not a directional thesis on its own.',
    formula: 'Equal-weighted blend of normalised RSI, MACD signal cross, BB position. score in [-2,+2].',
    interpretation: [
      { range: 'RSI < 30 + below LBB', meaning: 'Oversold bounce setup', tone: 'bull' },
      { range: 'MACD bull cross + RSI < 70', meaning: 'Momentum constructive', tone: 'bull' },
      { range: 'No signals', meaning: 'No technical edge', tone: 'neut' },
      { range: 'MACD bear cross + RSI > 30', meaning: 'Momentum deteriorating', tone: 'bear' },
      { range: 'RSI > 70 + above UBB', meaning: 'Overbought reversal setup', tone: 'bear' },
    ],
    caveat: 'Pure price-history reading. Blind to fundamentals.',
  },
  DXY: {
    name: 'DXY (US Dollar)',
    chapter: 'Chapter 5 + 9 — macro/dollar effects',
    source: 'Live yfinance DXY (DX-Y.NYB)',
    what: '30-day deviation of the dollar index from its 90-day mean.',
    why: 'Oil is priced in USD globally. Strong dollar makes oil more expensive for non-USD buyers, suppressing demand — bearish. Weak dollar is a tailwind.',
    formula: 'score = sign-inverted scaling of 30d DXY deviation. +1% DXY → ≈ −0.5 score.',
    interpretation: [
      { range: 'DXY weakening', meaning: 'USD tailwind for oil', tone: 'bull' },
      { range: 'DXY flat', meaning: 'Neutral', tone: 'neut' },
      { range: 'DXY strengthening', meaning: 'USD headwind for oil', tone: 'bear' },
    ],
    caveat: 'In a supply-shock regime (2022), oil and DXY can rise together. Curriculum: "Oil rising WITH dollar — supply shock overriding FX."',
  },
  'Geo Risk': {
    name: 'Geo Risk',
    chapter: 'Chapter 10 — Geopolitics & Risk',
    source: 'Composite: VIX + negative news count + spread anomaly + 30d vol',
    what: '0-100 composite index of geopolitical and macro tension.',
    why: 'Geopolitical events inject a risk premium into oil prices that fades over time as markets reassess actual supply impact. The premium is largest when spare capacity is low (Chapter 10).',
    formula: 'Index 0-100. > 60 = elevated (price-bullish premium). 30-60 = moderate. < 30 = calm.',
    interpretation: [
      { range: '> 60', meaning: 'Elevated — bullish premium', tone: 'bull' },
      { range: '30-60', meaning: 'Watch — modest premium', tone: 'neut' },
      { range: '< 30', meaning: 'Calm — premium absent', tone: 'bear' },
    ],
    caveat: 'Premiums fade fast when supply is restored or rerouted; persist only when physical disruption is confirmed.',
  },
  IV: {
    name: 'Implied Vol',
    chapter: 'Options market structure',
    source: 'Rolling IV gauge (SQLite history)',
    what: 'Current implied vol vs its 30-day percentile.',
    why: 'Vol spikes flag uncertainty. High IV (>75th %ile) tends to correspond to consolidation breakouts; low IV (<25th %ile) tends to mean range-bound markets.',
    formula: 'score = scaled %ile around the 50th mark.',
    interpretation: [
      { range: '> 75th %ile', meaning: 'Vol regime — directional move imminent', tone: 'neut' },
      { range: '25-75', meaning: 'Normal regime', tone: 'neut' },
      { range: '< 25th %ile', meaning: 'Calm — range-bound', tone: 'neut' },
    ],
    caveat: 'Direction-agnostic. Combine with technicals for entry timing.',
  },
  Weather: {
    name: 'Weather (NatGas)',
    chapter: 'Chapter 5 — Demand seasonality',
    source: 'Open-Meteo 5-city HDD/CDD vs 30y normal',
    what: 'Heating Degree Days (HDD, winter) and Cooling Degree Days (CDD, summer) deviation vs normal across 5 US cities.',
    why: 'Drives ~50% of US natural gas demand. Cold winter → high HDD → bullish gas. Hot summer → high CDD → bullish gas (power gen).',
    formula: 'Composite seasonal demand score from HDD + CDD deviations. +2 strong tight; −2 strong loose.',
    interpretation: [
      { range: 'HDD +20% or CDD +30%', meaning: 'Bullish demand', tone: 'bull' },
      { range: 'Normal', meaning: 'No signal', tone: 'neut' },
      { range: 'HDD/CDD −20%', meaning: 'Bearish demand', tone: 'bear' },
    ],
    caveat: 'Spring/fall shoulder seasons have weak weather signal — switch to inventory.',
  },
};

function _refFor(name?: string | null): Reference | null {
  if (!name) return null;
  if (REFS[name]) return REFS[name];
  // Loose match
  const lower = name.toLowerCase();
  for (const k of Object.keys(REFS)) {
    if (k.toLowerCase() === lower || lower.includes(k.toLowerCase())) return REFS[k];
  }
  return null;
}

export function IndicatorDrillDown({
  open,
  onClose,
  indicator,
  asset,
}: {
  open: boolean;
  onClose: () => void;
  indicator: any;
  asset: string;
}) {
  if (!indicator) return null;
  const ref = _refFor(indicator.name);
  const score: number = indicator.score ?? 0;
  const weight: number = indicator.weight ?? 0;
  const reason: string = indicator.reason ?? '';
  const raw = indicator.raw_value;
  const tone: 'bull' | 'bear' | 'neut' = score > 0.2 ? 'bull' : score < -0.2 ? 'bear' : 'neut';

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={`${indicator.name} · ${asset.toUpperCase()}`}
      subtitle={ref?.chapter}
      size="lg"
      right={<Chip tone={tone}>{score >= 0 ? '+' : ''}{score.toFixed(2)}</Chip>}
    >
      {/* Headline row */}
      <div className="grid grid-cols-4 gap-3 mb-5 pb-4 border-b border-border/40">
        <div>
          <div className="text-[9px] font-mono uppercase tracking-widest text-text-muted">Score</div>
          <div className={clsx(
            'text-2xl font-display font-bold tabular',
            tone === 'bull' && 'text-bull', tone === 'bear' && 'text-bear', tone === 'neut' && 'text-neut',
          )}>
            {score >= 0 ? '+' : ''}{score.toFixed(2)}
          </div>
          <div className="mt-2"><ScoreBar score={score} height={6} /></div>
        </div>
        <div>
          <div className="text-[9px] font-mono uppercase tracking-widest text-text-muted">Weight</div>
          <div className="text-2xl font-display font-bold tabular text-gold">{(weight * 100).toFixed(0)}%</div>
          <div className="text-[10px] font-mono text-text-muted mt-2">contribution: {(score * weight).toFixed(2)}</div>
        </div>
        <div>
          <div className="text-[9px] font-mono uppercase tracking-widest text-text-muted">Raw Value</div>
          <div className="text-2xl font-display font-bold tabular text-text-primary">
            {raw !== null && raw !== undefined ? (typeof raw === 'number' ? raw.toFixed(2) : String(raw)) : '—'}
          </div>
        </div>
        <div>
          <div className="text-[9px] font-mono uppercase tracking-widest text-text-muted">Direction</div>
          <div className={clsx('text-2xl font-display font-bold tabular',
            tone === 'bull' && 'text-bull', tone === 'bear' && 'text-bear', tone === 'neut' && 'text-neut')}>
            {tone === 'bull' ? '▲ BULL' : tone === 'bear' ? '▼ BEAR' : '— NEUT'}
          </div>
        </div>
      </div>

      {/* Live reason */}
      <div className="mb-5 p-3 bg-bg-card/60 border-l-2 border-gold/40 rounded">
        <div className="text-[9px] font-mono uppercase tracking-widest text-text-muted mb-1 flex items-center gap-1.5">
          <Activity className="w-3 h-3" /> Current Reading
        </div>
        <div className="text-[12px] text-text-secondary leading-relaxed">{reason || '—'}</div>
      </div>

      {ref ? (
        <>
          {/* WHAT */}
          <section className="mb-4">
            <h4 className="text-[10px] font-mono uppercase tracking-widest text-text-tertiary mb-1 flex items-center gap-1.5">
              <Target className="w-3 h-3 text-text-tertiary" /> What it measures
            </h4>
            <p className="text-[12px] text-text-secondary leading-relaxed">{ref.what}</p>
          </section>

          {/* WHY */}
          <section className="mb-4">
            <h4 className="text-[10px] font-mono uppercase tracking-widest text-text-tertiary mb-1 flex items-center gap-1.5">
              <BookOpen className="w-3 h-3 text-text-tertiary" /> Why it matters
            </h4>
            <p className="text-[12px] text-text-secondary leading-relaxed">{ref.why}</p>
          </section>

          {/* FORMULA */}
          <section className="mb-4">
            <h4 className="text-[10px] font-mono uppercase tracking-widest text-text-tertiary mb-1 flex items-center gap-1.5">
              <Layers className="w-3 h-3 text-text-tertiary" /> Scoring rule
            </h4>
            <div className="text-[11px] font-mono text-text-secondary leading-relaxed p-2 bg-bg-elev/40 rounded border border-border/40">
              {ref.formula}
            </div>
          </section>

          {/* INTERPRETATION TABLE */}
          <section className="mb-4">
            <h4 className="text-[10px] font-mono uppercase tracking-widest text-text-tertiary mb-2">Interpretation</h4>
            <div className="space-y-1">
              {ref.interpretation.map((row, i) => (
                <div
                  key={i}
                  className="grid grid-cols-[160px_1fr_60px] gap-2 items-center text-[11px] py-1 px-2 rounded hover:bg-bg-hover/40"
                >
                  <span className="font-mono text-text-muted">{row.range}</span>
                  <span className="text-text-secondary">{row.meaning}</span>
                  <Chip tone={row.tone}>{row.tone === 'bull' ? '▲ BULL' : row.tone === 'bear' ? '▼ BEAR' : '— NEUT'}</Chip>
                </div>
              ))}
            </div>
          </section>

          {/* SOURCE + CAVEAT */}
          <section className="grid md:grid-cols-2 gap-3 mt-4 pt-3 border-t border-border/40">
            <div>
              <div className="text-[9px] font-mono uppercase tracking-widest text-text-muted">Data source</div>
              <div className="text-[11px] font-mono text-text-secondary">{ref.source}</div>
            </div>
            {ref.caveat && (
              <div>
                <div className="text-[9px] font-mono uppercase tracking-widest text-neut">⚠ Caveat</div>
                <div className="text-[11px] text-text-tertiary leading-snug">{ref.caveat}</div>
              </div>
            )}
          </section>
        </>
      ) : (
        <div className="text-[11px] font-mono text-text-muted italic">
          No detailed reference card for "{indicator.name}" yet — showing live values only.
        </div>
      )}
    </Modal>
  );
}
