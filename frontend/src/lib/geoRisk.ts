/**
 * Geopolitical Risk Premium Scoring Framework
 *
 * Implements the exact formula from "Oil Macro Trading" curriculum,
 * Chapter 10 (Geopolitics & Risk). Three weighted dimensions yield a
 * 0-10 composite score, mapped to an implied $/bbl risk premium.
 *
 *   1. SUPPLY AT RISK (mbd)         × 40%   → 2 / 4 / 6 / 8 / 10 pts
 *   2. GLOBAL SPARE CAPACITY (mbd)  × 40%   → inverted: less spare = more pts
 *   3. DURATION UNCERTAINTY         × 20%   → days → permanent
 *
 *   Composite → implied premium:
 *     2-4 pts  →  $2-5/bbl
 *     5-6 pts  →  $5-10/bbl
 *     8-9 pts  →  $15-25/bbl
 *     10 pts   →  $25-50/bbl
 */

export type DurationBand = 'days' | 'weeks' | 'months' | 'years' | 'structural';

/** Step function for the supply-at-risk dimension. */
export function scoreSupplyAtRisk(mbd: number): number {
  if (mbd <= 0) return 0;
  if (mbd < 0.5) return 2;
  if (mbd < 1) return 4;
  if (mbd < 2) return 6;
  if (mbd < 4) return 8;
  return 10;
}

/** Inverted step function — less spare capacity = higher risk score. */
export function scoreSpareCapacity(mbdSpare: number): number {
  if (mbdSpare > 4) return 2;   // cushioned
  if (mbdSpare > 2) return 5;   // moderate
  if (mbdSpare > 1) return 8;   // vulnerable
  return 10;                    // critical
}

const DURATION_SCORE: Record<DurationBand, number> = {
  days:       2,
  weeks:      5,
  months:     5,
  years:      8,
  structural: 10,
};

export function scoreDuration(band: DurationBand): number {
  return DURATION_SCORE[band] ?? 5;
}

/**
 * Composite 0-10 score and implied $/bbl premium.
 * Uses the curriculum weights: 40 / 40 / 20.
 */
export function computeGeoRisk(input: {
  supplyAtRiskMbd: number;
  spareCapacityMbd: number;
  durationBand: DurationBand;
}): { composite: number; premium: number; band: string; weights: { supply: number; spare: number; duration: number } } {
  const s1 = scoreSupplyAtRisk(input.supplyAtRiskMbd);
  const s2 = scoreSpareCapacity(input.spareCapacityMbd);
  const s3 = scoreDuration(input.durationBand);

  // Weighted average so the composite stays on a 0-10 scale.
  const composite = s1 * 0.4 + s2 * 0.4 + s3 * 0.2;

  let premium: number;
  let band: string;
  if (composite < 2) {
    premium = composite * 1.0;             // <= $2
    band = 'MINIMAL';
  } else if (composite < 5) {
    premium = 2 + ((composite - 2) / 3) * 3;     // 2 → 5
    band = 'LOW';
  } else if (composite < 7) {
    premium = 5 + ((composite - 5) / 2) * 5;     // 5 → 10
    band = 'MODERATE';
  } else if (composite < 9) {
    premium = 10 + ((composite - 7) / 2) * 15;   // 10 → 25
    band = 'HIGH';
  } else {
    premium = 25 + Math.min(25, (composite - 9) * 25);  // 25 → 50
    band = 'EXTREME';
  }

  return {
    composite: Math.round(composite * 10) / 10,
    premium:   Math.round(premium * 10) / 10,
    band,
    weights:   { supply: s1, spare: s2, duration: s3 },
  };
}

/** Presets from the curriculum's historical disruption table (Chapter 10). */
export const HISTORICAL_PRESETS: {
  name: string;
  year: number;
  supplyAtRiskMbd: number;
  spareCapacityMbd: number;
  durationBand: DurationBand;
  actualPriceImpact: string;
  notes: string;
}[] = [
  { name: 'Arab Oil Embargo',         year: 1973, supplyAtRiskMbd: 3.0, spareCapacityMbd: 1.0, durationBand: 'months',     actualPriceImpact: '+300% in 3mo', notes: 'OPEC embargo on US/NL — broke the post-war oil order.' },
  { name: 'Iranian Revolution',       year: 1979, supplyAtRiskMbd: 4.0, spareCapacityMbd: 1.5, durationBand: 'years',      actualPriceImpact: '+100%',         notes: 'Iran production collapsed from 6→1.5 mbd.' },
  { name: 'Gulf War I (Kuwait)',      year: 1990, supplyAtRiskMbd: 4.3, spareCapacityMbd: 2.5, durationBand: 'months',     actualPriceImpact: '+100% in 3mo', notes: 'Iraq + Kuwait combined loss.' },
  { name: 'Iraq War',                 year: 2003, supplyAtRiskMbd: 2.0, spareCapacityMbd: 4.5, durationBand: 'months',     actualPriceImpact: 'Muted',         notes: 'Spare capacity absorbed the shock.' },
  { name: 'Libya Civil War',          year: 2011, supplyAtRiskMbd: 1.3, spareCapacityMbd: 3.0, durationBand: 'months',     actualPriceImpact: '+$20 in weeks', notes: 'Spare was modest; price reacted sharply.' },
  { name: 'Russia–Ukraine War',       year: 2022, supplyAtRiskMbd: 2.5, spareCapacityMbd: 1.5, durationBand: 'years',      actualPriceImpact: 'Brent → $130',  notes: 'Rerouted, not lost; spare was tight.' },
  { name: 'Houthi / Red Sea',         year: 2024, supplyAtRiskMbd: 1.5, spareCapacityMbd: 4.5, durationBand: 'months',     actualPriceImpact: 'Freight +300%', notes: 'Mostly a rerouting (Cape) cost.' },
  { name: 'Hormuz Closure scenario',  year: 0,    supplyAtRiskMbd: 13.5, spareCapacityMbd: 1.0, durationBand: 'weeks',     actualPriceImpact: 'Doomsday',      notes: 'Hypothetical: full Hormuz closure, only ~3.5 mbd bypass capacity.' },
];
