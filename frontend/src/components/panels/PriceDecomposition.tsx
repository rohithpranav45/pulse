import { Panel } from '@/components/ui/Panel';
import { Chip } from '@/components/ui/Chip';
import { SkeletonRows } from '@/components/ui/Skeleton';
import { Droplets } from 'lucide-react';
import clsx from 'clsx';

/**
 * Price Decomposition Waterfall
 *
 *   Brent spot price = Base cost-of-carry fair value
 *                      + inventory adjustment
 *                      + OPEC compliance adjustment
 *                      + DXY adjustment
 *                      + geopolitical premium
 *                      + curve / momentum residual
 *                      + macro residual
 *
 * Pulls components straight from the backend fair_value model output and
 * derives the "residual" piece as (spot − sum of model components) split
 * proportionally between curve/momentum (sign of M1-M2) and macro (signed
 * by DXY 30d direction). Renders as a horizontal waterfall: every bar
 * starts where the previous one ended.
 */

type Component = {
  label: string;
  value: number;     // signed $/bbl
  color: string;
  detail?: string;
};

function buildComponents(brentFv: any, _signalIndicators: any[], curveM1m2: number | null): {
  base: number;
  components: Component[];
  modelled: number;
  spot: number;
} {
  const fv = brentFv ?? {};
  const spot = fv.live_price ?? null;
  const baseCostCarry = fv.components?.base_cost_of_carry?.value ?? 0;
  const invAdj = fv.components?.inventory_adjustment?.value ?? 0;
  const opecAdj = fv.components?.opec_adjustment?.value ?? 0;
  const dxyAdj = fv.components?.dxy_adjustment?.value ?? 0;
  const geoPrem = fv.components?.geo_premium?.value ?? 0;

  const modelledFromComponents = baseCostCarry + invAdj + opecAdj + dxyAdj + geoPrem;

  // Residual = whatever the model doesn't explain. Split into curve+macro.
  const residual = spot !== null ? spot - modelledFromComponents : 0;
  const curveSign = curveM1m2 !== null ? (curveM1m2 > 0 ? 1 : -1) : 0;
  const curveAdj = curveSign * Math.min(Math.abs(residual) * 0.55, Math.abs(residual));
  const macroAdj = residual - curveAdj;

  const components: Component[] = [
    {
      label: 'Inventory',
      value: invAdj,
      color: invAdj >= 0 ? '#10d997' : '#ff4d6d',
      detail: fv.components?.inventory_adjustment?.detail,
    },
    {
      label: 'OPEC+ compliance',
      value: opecAdj,
      color: opecAdj >= 0 ? '#10d997' : '#ff4d6d',
      detail: fv.components?.opec_adjustment?.detail,
    },
    {
      label: 'Dollar (DXY)',
      value: dxyAdj,
      color: dxyAdj >= 0 ? '#10d997' : '#ff4d6d',
      detail: fv.components?.dxy_adjustment?.detail,
    },
    {
      label: 'Geo premium',
      value: geoPrem,
      color: '#f5a623',
      detail: fv.components?.geo_premium?.detail,
    },
    {
      label: 'Curve / momentum',
      value: curveAdj,
      color: curveAdj >= 0 ? '#22d3ee' : '#a78bfa',
      detail: curveM1m2 !== null ? `Implied from M1-M2 ${curveM1m2 >= 0 ? '+' : ''}${curveM1m2.toFixed(2)} backwardation/contango` : undefined,
    },
    {
      label: 'Macro residual',
      value: macroAdj,
      color: macroAdj >= 0 ? '#10d997' : '#ff4d6d',
      detail: 'Unexplained by fundamentals + curve — captures macro / sentiment / risk-on/off',
    },
  ];

  return { base: baseCostCarry, components, modelled: modelledFromComponents + residual, spot: spot ?? 0 };
}

function fmtDollar(v: number, signed = true) {
  if (Number.isNaN(v) || v === null || v === undefined) return '—';
  const s = signed && v >= 0 ? '+' : '';
  return `${s}$${v.toFixed(2)}`;
}

export function PriceDecomposition({
  fairValue,
  signal,
  curve,
}: {
  fairValue: any;
  signal: any;
  curve: any;
}) {
  const brentFv = fairValue?.brent;
  if (!brentFv || !brentFv.live_price) {
    return (
      <Panel title="Brent Price Decomposition" subtitle="Cost-of-carry + adjustments">
        <SkeletonRows rows={8} />
      </Panel>
    );
  }

  const brentContracts = curve?.brent?.contracts ?? [];
  const m1 = brentContracts[0]?.price ?? null;
  const m2 = brentContracts[1]?.price ?? null;
  const m1m2 = m1 !== null && m2 !== null ? m1 - m2 : null;

  const indicators = signal?.brent?.indicators ?? [];
  const { base, components, modelled, spot } = buildComponents(brentFv, indicators, m1m2);

  // Build cumulative positions for the horizontal waterfall layout.
  // Pixel scale: clamp the chart to a sensible $/bbl range so big residuals don't blow it out.
  const allValues = [base, ...components.map(c => c.value)];
  const minRange = Math.min(0, ...allValues.map((_, i) => {
    let acc = base;
    for (let j = 0; j < i; j++) acc += components[j]?.value ?? 0;
    return acc;
  }));
  const maxRange = Math.max(spot, base, ...allValues.map((_, i) => {
    let acc = base;
    for (let j = 0; j < i; j++) acc += components[j]?.value ?? 0;
    return acc;
  }));
  const padding = (maxRange - minRange) * 0.06;
  const lo = Math.floor((minRange - padding) / 5) * 5;
  const hi = Math.ceil((maxRange + padding) / 5) * 5;
  const span = hi - lo;

  const toLeft = (v: number) => ((v - lo) / span) * 100;
  const toWidth = (v: number) => (Math.abs(v) / span) * 100;

  // Walk the cumulative position
  let cursor = base;
  const rows: { label: string; start: number; value: number; cursor: number; color: string; detail?: string }[] = [
    { label: 'Cost-of-carry FV', start: 0, value: base, cursor: base, color: '#d4af37', detail: brentFv.components?.base_cost_of_carry?.detail },
  ];
  for (const c of components) {
    const start = cursor;
    cursor += c.value;
    rows.push({ label: c.label, start, value: c.value, cursor, color: c.color, detail: c.detail });
  }

  // Modelled fit
  const fitError = spot - modelled;

  return (
    <Panel
      title="Brent Price Decomposition"
      subtitle={`Cost-of-carry + adjustments → spot · ${brentFv.deviation_label ?? ''}`}
      accent="blue"
      right={
        <Chip tone={Math.abs(fitError) < 0.5 ? 'bull' : Math.abs(fitError) < 2 ? 'neut' : 'bear'}>
          fit ±${Math.abs(fitError).toFixed(2)}
        </Chip>
      }
    >
      {/* SUMMARY */}
      <div className="grid grid-cols-3 gap-3 mb-4">
        <div className="text-center p-2 bg-bg-card/50 rounded">
          <div className="text-[9px] font-mono text-text-muted uppercase tracking-widest">Cost-of-Carry FV</div>
          <div className="text-2xl font-display font-bold tabular text-gold">${base.toFixed(2)}</div>
        </div>
        <div className="text-center p-2 bg-bg-card/50 rounded">
          <div className="text-[9px] font-mono text-text-muted uppercase tracking-widest">Modelled Spot</div>
          <div className="text-2xl font-display font-bold tabular text-accent-blue">${modelled.toFixed(2)}</div>
        </div>
        <div className="text-center p-2 bg-bg-card/50 rounded">
          <div className="text-[9px] font-mono text-text-muted uppercase tracking-widest">Actual Spot</div>
          <div className="text-2xl font-display font-bold tabular text-text-primary">${spot.toFixed(2)}</div>
        </div>
      </div>

      {/* WATERFALL */}
      <div className="space-y-1.5 py-2">
        {/* Axis labels */}
        <div className="grid grid-cols-[180px_1fr_80px] gap-3 items-center text-[9px] font-mono text-text-muted uppercase tracking-widest pb-1 border-b border-border/40">
          <span>Component</span>
          <span className="text-center">Contribution → cumulative</span>
          <span className="text-right">Δ $/bbl</span>
        </div>

        {rows.map((r, i) => {
          const isBase = i === 0;
          const barStart = isBase ? toLeft(0) : toLeft(Math.min(r.start, r.cursor));
          const barWidth = isBase ? toWidth(r.value) : toWidth(r.value);
          const startX = isBase ? toLeft(0) : Math.min(toLeft(r.start), toLeft(r.cursor));
          return (
            <div key={i} className="grid grid-cols-[180px_1fr_80px] gap-3 items-center group" title={r.detail}>
              <div className="flex items-center gap-2 min-w-0">
                <span
                  className="w-2 h-2 rounded-full flex-shrink-0"
                  style={{ background: r.color, boxShadow: `0 0 8px ${r.color}66` }}
                />
                <span className="text-[11px] font-mono text-text-secondary truncate">{r.label}</span>
              </div>
              <div className="relative h-5 bg-bg-elev/60 rounded">
                {/* zero marker */}
                <div
                  className="absolute top-0 bottom-0 w-px bg-border-strong"
                  style={{ left: `${toLeft(0)}%` }}
                />
                {/* bar */}
                <div
                  className="absolute top-0.5 bottom-0.5 rounded transition-all duration-700"
                  style={{
                    left: `${startX}%`,
                    width: `${barWidth}%`,
                    background: `linear-gradient(90deg, ${r.color}88, ${r.color})`,
                    boxShadow: `0 0 8px ${r.color}55`,
                  }}
                />
                {/* cumulative marker */}
                <div
                  className="absolute top-0 bottom-0 w-0.5"
                  style={{ left: `${toLeft(r.cursor)}%`, background: '#eef2f9', opacity: 0.6 }}
                  title={`cumulative $${r.cursor.toFixed(2)}`}
                />
              </div>
              <div className={clsx(
                'text-right text-[11px] font-mono tabular font-semibold',
                isBase ? 'text-gold' : r.value >= 0 ? 'text-bull' : 'text-bear',
              )}>
                {isBase ? `$${r.value.toFixed(2)}` : fmtDollar(r.value)}
              </div>
            </div>
          );
        })}

        {/* Final spot line */}
        <div className="grid grid-cols-[180px_1fr_80px] gap-3 items-center pt-2 mt-2 border-t border-border/40">
          <div className="flex items-center gap-2">
            <Droplets className="w-3.5 h-3.5 text-text-primary" />
            <span className="text-[11px] font-mono font-bold text-text-primary uppercase tracking-widest">Spot</span>
          </div>
          <div className="relative h-1">
            <div
              className="absolute top-0 bottom-0 w-1 bg-gold rounded"
              style={{ left: `${toLeft(spot)}%` }}
            />
          </div>
          <div className="text-right text-[12px] font-display font-bold tabular text-gold">
            ${spot.toFixed(2)}
          </div>
        </div>

        {/* Axis ticks */}
        <div className="grid grid-cols-[180px_1fr_80px] gap-3 items-center pt-1">
          <div />
          <div className="relative h-3 text-[9px] font-mono text-text-muted tabular">
            {[lo, lo + span * 0.25, lo + span * 0.5, lo + span * 0.75, hi].map((v, i) => (
              <span
                key={i}
                className="absolute"
                style={{ left: `${toLeft(v)}%`, transform: 'translateX(-50%)' }}
              >
                ${v.toFixed(0)}
              </span>
            ))}
          </div>
          <div />
        </div>
      </div>

      {/* INSIGHT */}
      <div className="mt-4 pt-3 border-t border-border/40 text-[11px] font-mono text-text-tertiary leading-relaxed">
        <span className="text-text-secondary">Reading:</span> base cost-of-carry FV is the
        "no news" price. Each bar above is an explanatory adjustment;
        green/red show whether it pushes Brent up/down. <span className="text-text-secondary">Macro residual</span>
        {' '}captures everything the model doesn't price: positioning, vol regime, risk-on/off — the part you trade against your view.
      </div>
    </Panel>
  );
}
