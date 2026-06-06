import { useEffect, useMemo, useState } from 'react';
import { Panel } from '@/components/ui/Panel';
import { Chip } from '@/components/ui/Chip';
import { AlertOctagon, Calculator, History, Zap } from 'lucide-react';
import clsx from 'clsx';
import {
  computeGeoRisk,
  scoreSupplyAtRisk,
  scoreSpareCapacity,
  scoreDuration,
  HISTORICAL_PRESETS,
  DurationBand,
} from '@/lib/geoRisk';

const DURATION_OPTIONS: { value: DurationBand; label: string; hint: string }[] = [
  { value: 'days',       label: 'Days',       hint: 'localized incident' },
  { value: 'weeks',      label: 'Weeks',      hint: 'cargo / refinery outage' },
  { value: 'months',     label: 'Months',     hint: 'sanctions ramp / war' },
  { value: 'years',      label: 'Years',      hint: 'sustained conflict' },
  { value: 'structural', label: 'Structural', hint: 'permanent regime change' },
];

const bandTone = (band: string): 'bull' | 'bear' | 'neut' | 'gold' =>
  band === 'EXTREME' || band === 'HIGH' ? 'bear' :
  band === 'MODERATE' ? 'neut' :
  band === 'LOW' ? 'gold' : 'bull';

function Bar({ value, max = 10, color }: { value: number; max?: number; color: string }) {
  return (
    <div className="h-1.5 bg-bg-elev rounded overflow-hidden">
      <div
        className="h-full transition-all duration-500 rounded"
        style={{ width: `${(value / max) * 100}%`, background: color }}
      />
    </div>
  );
}

export function GeoRiskCalculator({
  defaultSpareCapacity = 4.5,
  brentPrice = null,
}: {
  defaultSpareCapacity?: number;
  brentPrice?: number | null;
}) {
  const [supply, setSupply] = useState(1.0);
  const [spare, setSpare] = useState(defaultSpareCapacity);
  const [duration, setDuration] = useState<DurationBand>('weeks');

  useEffect(() => {
    setSpare(defaultSpareCapacity);
  }, [defaultSpareCapacity]);

  const result = useMemo(
    () => computeGeoRisk({ supplyAtRiskMbd: supply, spareCapacityMbd: spare, durationBand: duration }),
    [supply, spare, duration],
  );

  const sSupply = scoreSupplyAtRisk(supply);
  const sSpare = scoreSpareCapacity(spare);
  const sDur = scoreDuration(duration);

  const applyPreset = (i: number) => {
    const p = HISTORICAL_PRESETS[i];
    setSupply(p.supplyAtRiskMbd);
    setSpare(p.spareCapacityMbd);
    setDuration(p.durationBand);
  };

  const impliedPrice = brentPrice !== null && brentPrice !== undefined
    ? brentPrice + result.premium  // adds the risk premium on top of current spot
    : null;

  return (
    <Panel
      title="Geo Risk Premium Calculator"
      subtitle="Chapter 10 framework · Supply×40 + Spare×40 + Duration×20"
      accent="bear"
      source="geo_risk_calc"
      sourceNote="Interactive what-if calculator running entirely client-side. Inputs (supply at risk, spare capacity, duration) are user-tunable; no live feed."
      right={<Calculator className="w-4 h-4 text-text-tertiary" />}
    >
      {/* RESULT BANNER */}
      <div className="grid grid-cols-3 gap-3 mb-4 p-3 bg-bg-card/60 rounded border border-border/40">
        <div className="text-center border-r border-border/40">
          <div className="text-[9px] font-mono text-text-muted uppercase tracking-widest">Composite</div>
          <div className="text-3xl font-display font-extrabold tabular text-text-primary">
            {result.composite.toFixed(1)}<span className="text-[12px] text-text-muted">/10</span>
          </div>
          <Chip tone={bandTone(result.band)} className="mt-1">{result.band}</Chip>
        </div>
        <div className="text-center border-r border-border/40">
          <div className="text-[9px] font-mono text-text-muted uppercase tracking-widest">Implied Premium</div>
          <div className="text-3xl font-display font-extrabold tabular text-bear">
            +${result.premium.toFixed(1)}<span className="text-[12px] text-text-muted">/bbl</span>
          </div>
          <div className="text-[10px] font-mono text-text-muted mt-1">added to spot</div>
        </div>
        <div className="text-center">
          <div className="text-[9px] font-mono text-text-muted uppercase tracking-widest">Implied Brent</div>
          <div className="text-3xl font-display font-extrabold tabular text-gold">
            {impliedPrice !== null ? `$${impliedPrice.toFixed(2)}` : '—'}
          </div>
          {brentPrice !== null && brentPrice !== undefined && (
            <div className="text-[10px] font-mono text-text-muted mt-1">vs spot ${brentPrice.toFixed(2)}</div>
          )}
        </div>
      </div>

      {/* SLIDERS */}
      <div className="space-y-4">
        {/* Supply at risk */}
        <div>
          <div className="flex items-baseline justify-between mb-1">
            <label className="text-[10px] font-mono uppercase tracking-widest text-text-tertiary">
              Supply at Risk · 40% weight
            </label>
            <span className="text-[11px] font-mono tabular text-text-secondary">
              {supply.toFixed(2)} mbd → <span className="text-bear font-semibold">{sSupply}/10</span>
            </span>
          </div>
          <input
            type="range" min="0" max="15" step="0.1" value={supply}
            onChange={(e) => setSupply(parseFloat(e.target.value))}
            className="w-full accent-bear h-1"
          />
          <div className="text-[9px] font-mono text-text-muted mt-1 flex justify-between">
            <span>0</span><span>0.5</span><span>1</span><span>2</span><span>4</span><span>15 mbd</span>
          </div>
          <div className="mt-1.5"><Bar value={sSupply} color="#ff4d6d" /></div>
        </div>

        {/* Spare capacity */}
        <div>
          <div className="flex items-baseline justify-between mb-1">
            <label className="text-[10px] font-mono uppercase tracking-widest text-text-tertiary">
              Global Spare Capacity · 40% weight <span className="text-text-muted">(inverted)</span>
            </label>
            <span className="text-[11px] font-mono tabular text-text-secondary">
              {spare.toFixed(2)} mbd → <span className="text-bear font-semibold">{sSpare}/10</span>
            </span>
          </div>
          <input
            type="range" min="0" max="10" step="0.1" value={spare}
            onChange={(e) => setSpare(parseFloat(e.target.value))}
            className="w-full accent-bull h-1"
          />
          <div className="text-[9px] font-mono text-text-muted mt-1 flex justify-between">
            <span>0 (critical)</span><span>1</span><span>2</span><span>4</span><span>10 mbd (abundant)</span>
          </div>
          <div className="mt-1.5"><Bar value={sSpare} color="#ff4d6d" /></div>
        </div>

        {/* Duration */}
        <div>
          <div className="flex items-baseline justify-between mb-1">
            <label className="text-[10px] font-mono uppercase tracking-widest text-text-tertiary">
              Duration Uncertainty · 20% weight
            </label>
            <span className="text-[11px] font-mono tabular text-text-secondary">
              <span className="text-bear font-semibold">{sDur}/10</span>
            </span>
          </div>
          <div className="grid grid-cols-5 gap-1.5">
            {DURATION_OPTIONS.map(opt => (
              <button
                key={opt.value}
                onClick={() => setDuration(opt.value)}
                className={clsx(
                  'px-2 py-1.5 text-[10px] font-mono tracking-widest uppercase rounded border transition-all',
                  duration === opt.value
                    ? 'border-bear/50 text-bear bg-bear-soft'
                    : 'border-border text-text-tertiary hover:text-text-secondary',
                )}
                title={opt.hint}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* HISTORICAL PRESETS */}
      <div className="mt-4 pt-4 border-t border-border/40">
        <div className="flex items-center gap-2 mb-2">
          <History className="w-3.5 h-3.5 text-text-tertiary" />
          <span className="text-[10px] font-mono uppercase tracking-widest text-text-tertiary">
            Historical Calibration
          </span>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-1.5">
          {HISTORICAL_PRESETS.map((p, i) => (
            <button
              key={i}
              onClick={() => applyPreset(i)}
              className="text-left p-2 bg-bg-card/40 hover:bg-bg-card/80 border border-border/60 hover:border-bear/40 rounded transition-all group"
              title={p.notes}
            >
              <div className="text-[10px] font-display font-semibold tracking-wider text-text-secondary group-hover:text-bear truncate">
                {p.name}
              </div>
              <div className="text-[9px] font-mono text-text-muted">
                {p.year > 0 ? p.year : 'scenario'} · {p.supplyAtRiskMbd}mbd · {p.actualPriceImpact}
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* EXPLAINER */}
      <div className="mt-4 pt-3 border-t border-border/40 flex items-start gap-2 text-[10px] font-mono text-text-tertiary leading-relaxed">
        <Zap className="w-3 h-3 flex-shrink-0 mt-0.5 text-gold" />
        <span>
          <span className="text-text-secondary">Spare capacity is the denominator that converts news into price.</span>
          <span className="text-text-muted"> When spare is below 2 mbd, even modest supply disruptions
          have outsized impact (2008, 2022). When spare is &gt;4 mbd (2014, 2020), the same disruption is absorbed.</span>
        </span>
      </div>

      <div className="mt-2 text-[9px] font-mono text-text-muted">
        Note: <AlertOctagon className="w-3 h-3 inline -mt-0.5 text-neut" /> this is the curriculum's framework, not a forecast.
        Real market premium also reflects positioning, vol, and time-decay of news.
      </div>
    </Panel>
  );
}
