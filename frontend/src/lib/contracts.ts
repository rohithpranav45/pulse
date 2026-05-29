/**
 * Contract specifications — straight from Chapter 11 of the Oil Macro
 * Trading curriculum.  Hand-curated reference for the five core energy
 * futures every desk trades.
 */

export type ContractSpec = {
  key: string;
  ticker: string;
  bloomberg: string;
  name: string;
  exchange: 'ICE Europe' | 'CME / NYMEX';
  exchangeShort: string;
  contractSize: { value: number; unit: string };
  quoteUnit: '$/bbl' | '$/gallon' | '$/MT';
  minTick: { value: number; dollars: number };
  settlement: 'Cash (ICE Index)' | 'Physical (Cushing)' | 'Physical (NYH)' | 'Physical (ARA)';
  /** Expiry rule (plain English). */
  expiryRule: string;
  /** Function that, given a delivery month (Date for 1st of delivery month),
   *  returns the contract expiry Date.  Approximate — production desks
   *  should use the exchange calendar. */
  expiryFor: (deliveryMonth: Date) => Date;
  underlyingQuality: string;
  /** Trading hours summary. */
  hoursLabel: string;
  /** Most-active local window (used for "session open" indicator). */
  primaryHours: { tz: 'Europe/London' | 'America/Chicago'; openHour: number; closeHour: number };
  dailySettlement: string;
  keySpreads: string[];
  notes?: string;
  conversionToBbl?: number;   // multiply value by this to get $/bbl
};

const _last_business_day = (year: number, month: number): Date => {
  // month is 0-indexed; "last business day of the month" — approx, skipping Sat/Sun
  const d = new Date(Date.UTC(year, month + 1, 0));  // last day of month
  while (d.getUTCDay() === 0 || d.getUTCDay() === 6) d.setUTCDate(d.getUTCDate() - 1);
  return d;
};

const _nth_business_day_before = (year: number, month: number, dayOfMonth: number, nthBefore: number): Date => {
  // Return the Nth business day before `dayOfMonth` in (year, month)
  const target = new Date(Date.UTC(year, month, dayOfMonth));
  let count = 0;
  while (count < nthBefore) {
    target.setUTCDate(target.getUTCDate() - 1);
    if (target.getUTCDay() !== 0 && target.getUTCDay() !== 6) count++;
  }
  return target;
};

export const CONTRACTS: ContractSpec[] = [
  {
    key: 'brent',
    ticker: 'B',
    bloomberg: 'BRN',
    name: 'Brent Crude',
    exchange: 'ICE Europe',
    exchangeShort: 'ICE',
    contractSize: { value: 1000, unit: 'bbl' },
    quoteUnit: '$/bbl',
    minTick: { value: 0.01, dollars: 10 },
    settlement: 'Cash (ICE Index)',
    expiryRule: 'Last business day of the month preceding the delivery month',
    expiryFor: (d) => _last_business_day(d.getUTCFullYear(), d.getUTCMonth() - 1),
    underlyingQuality: 'BFOET basket · ~38° API · ~0.4% S · light sweet',
    hoursLabel: 'Sun 23:00 → Fri 23:00 London · 24h with 1h daily break',
    primaryHours: { tz: 'Europe/London', openHour: 7, closeHour: 17 },
    dailySettlement: '19:30–20:00 London (ICE settlement window)',
    keySpreads: ['Brent-WTI (B-CL)', 'Brent-Dubai EFS', 'Brent calendar M1-M2', 'ICE Gasoil crack'],
    notes: 'Cash-settled against ICE Brent Index — does NOT result in physical delivery.',
    conversionToBbl: 1,
  },
  {
    key: 'wti',
    ticker: 'CL',
    bloomberg: 'CL',
    name: 'WTI Crude',
    exchange: 'CME / NYMEX',
    exchangeShort: 'NYMEX',
    contractSize: { value: 1000, unit: 'bbl' },
    quoteUnit: '$/bbl',
    minTick: { value: 0.01, dollars: 10 },
    settlement: 'Physical (Cushing)',
    expiryRule: '3rd business day before the 25th of the month preceding delivery',
    expiryFor: (d) => _nth_business_day_before(d.getUTCFullYear(), d.getUTCMonth() - 1, 25, 3),
    underlyingQuality: 'Light sweet · 37–42° API · max 0.42% S · delivered at Cushing, OK',
    hoursLabel: 'Sun 18:00 → Fri 17:00 CT · 1h daily break',
    primaryHours: { tz: 'America/Chicago', openHour: 8, closeHour: 14 },
    dailySettlement: '14:28–14:30 CT (CME 2-min VWAP)',
    keySpreads: ['WTI-Brent', 'WTI calendar M1-M2', 'WTI-WCS heavy diff', '3-2-1 crack', 'WTI Midland-Cushing'],
    notes: 'Physical delivery — ROLL BEFORE EXPIRY unless taking delivery. The April 2020 negative price was a delivery-mechanics event.',
    conversionToBbl: 1,
  },
  {
    key: 'rbob',
    ticker: 'RB',
    bloomberg: 'XB',
    name: 'RBOB Gasoline',
    exchange: 'CME / NYMEX',
    exchangeShort: 'NYMEX',
    contractSize: { value: 42000, unit: 'gallons' },
    quoteUnit: '$/gallon',
    minTick: { value: 0.0001, dollars: 4.2 },
    settlement: 'Physical (NYH)',
    expiryRule: 'Last business day of the month prior to delivery (one day before CL)',
    expiryFor: (d) => {
      const prev = _last_business_day(d.getUTCFullYear(), d.getUTCMonth() - 1);
      prev.setUTCDate(prev.getUTCDate() - 1);
      while (prev.getUTCDay() === 0 || prev.getUTCDay() === 6) prev.setUTCDate(prev.getUTCDate() - 1);
      return prev;
    },
    underlyingQuality: 'ASTM D 4814 · winter (Oct–Mar) vs summer (Apr–Sep) RVP specs',
    hoursLabel: 'Sun 18:00 → Fri 17:00 CT',
    primaryHours: { tz: 'America/Chicago', openHour: 8, closeHour: 14 },
    dailySettlement: '14:28–14:30 CT',
    keySpreads: ['RBOB crack (RB-CL)', 'RBOB vs Eurobob', 'Calendar M1-M2', '3-2-1 crack'],
    notes: 'Summer/winter spec change at Apr & Oct roll creates predictable price discontinuity. Long RBOB crack Feb-Apr = one of the most reliable seasonal trades.',
    conversionToBbl: 42,
  },
  {
    key: 'ho',
    ticker: 'HO',
    bloomberg: 'HO',
    name: 'Heating Oil / ULSD',
    exchange: 'CME / NYMEX',
    exchangeShort: 'NYMEX',
    contractSize: { value: 42000, unit: 'gallons' },
    quoteUnit: '$/gallon',
    minTick: { value: 0.0001, dollars: 4.2 },
    settlement: 'Physical (NYH)',
    expiryRule: 'Last business day of the month prior to delivery',
    expiryFor: (d) => _last_business_day(d.getUTCFullYear(), d.getUTCMonth() - 1),
    underlyingQuality: 'NY Harbor ULSD · max 15ppm sulphur · (re-specced 2013)',
    hoursLabel: 'Sun 18:00 → Fri 17:00 CT',
    primaryHours: { tz: 'America/Chicago', openHour: 8, closeHour: 14 },
    dailySettlement: '14:28–14:30 CT',
    keySpreads: ['HO crack (HO-CL)', 'HO-RBOB diesel premium', 'HO vs ICE Gasoil (transatlantic diesel arb)', '3-2-1 crack'],
    notes: 'Originally NY-area heating oil; now de-facto ULSD diesel benchmark. Oct & Feb contracts carry winter heating premium.',
    conversionToBbl: 42,
  },
  {
    key: 'gasoil',
    ticker: 'GO',
    bloomberg: 'QS',
    name: 'ICE Low Sulphur Gasoil',
    exchange: 'ICE Europe',
    exchangeShort: 'ICE',
    contractSize: { value: 100, unit: 'MT' },
    quoteUnit: '$/MT',
    minTick: { value: 0.25, dollars: 25 },
    settlement: 'Physical (ARA)',
    expiryRule: '2nd business day before the 14th of the delivery month',
    expiryFor: (d) => _nth_business_day_before(d.getUTCFullYear(), d.getUTCMonth(), 14, 2),
    underlyingQuality: '0.1% S · EN 590 road-diesel spec · delivery at Amsterdam-Rotterdam-Antwerp',
    hoursLabel: 'Sun 23:00 → Fri 23:00 London',
    primaryHours: { tz: 'Europe/London', openHour: 7, closeHour: 17 },
    dailySettlement: '19:30–20:00 London (ICE)',
    keySpreads: ['ICE Gasoil crack (GO-BRN, unit-adjusted)', 'GO calendar', 'GO vs HO (transatlantic arb)', 'Jet/Gasoil spread'],
    notes: 'Quoted in $/MT — divide by ~7.45 to get $/bbl. 1 GO lot ≈ 745 bbl vs 1,000 bbl for BRN/CL — use 3:4 ratio for balanced spreads.',
    conversionToBbl: 1 / 7.45,
  },
];

/**
 * Find the next live contract month for a given product as of a given date.
 * Returns the {deliveryMonth, expiry} pair for the front contract whose
 * expiry is still in the future.
 */
export function frontMonthFor(spec: ContractSpec, asOf: Date = new Date()): { deliveryMonth: Date; expiry: Date } {
  for (let i = 0; i < 24; i++) {
    const deliveryMonth = new Date(Date.UTC(asOf.getUTCFullYear(), asOf.getUTCMonth() + i, 1));
    const expiry = spec.expiryFor(deliveryMonth);
    if (expiry > asOf) return { deliveryMonth, expiry };
  }
  // Fallback — should never hit
  const fallbackMonth = new Date(Date.UTC(asOf.getUTCFullYear(), asOf.getUTCMonth(), 1));
  return { deliveryMonth: fallbackMonth, expiry: spec.expiryFor(fallbackMonth) };
}

export function isPrimarySessionOpen(spec: ContractSpec, now: Date = new Date()): boolean {
  // Get current hour in the contract's primary tz
  const tz = spec.primaryHours.tz;
  const fmt = new Intl.DateTimeFormat('en-US', { hour: 'numeric', hour12: false, timeZone: tz, weekday: 'short' });
  const parts = fmt.formatToParts(now);
  const hour = parseInt(parts.find(p => p.type === 'hour')?.value ?? '0', 10);
  const weekday = parts.find(p => p.type === 'weekday')?.value ?? '';
  if (weekday === 'Sat' || weekday === 'Sun') return false;
  return hour >= spec.primaryHours.openHour && hour < spec.primaryHours.closeHour;
}

export function daysUntil(date: Date, now: Date = new Date()): number {
  return Math.ceil((date.getTime() - now.getTime()) / 86_400_000);
}

export const MONTH_CODE: Record<number, string> = {
  0: 'F', 1: 'G', 2: 'H', 3: 'J', 4: 'K', 5: 'M',
  6: 'N', 7: 'Q', 8: 'U', 9: 'V', 10: 'X', 11: 'Z',
};

export function contractCode(spec: ContractSpec, deliveryMonth: Date): string {
  const code = MONTH_CODE[deliveryMonth.getUTCMonth()];
  const year = deliveryMonth.getUTCFullYear() % 100;
  return `${spec.ticker}${code}${year.toString().padStart(2, '0')}`;
}
