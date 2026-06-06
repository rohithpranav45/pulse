import { Panel } from '@/components/ui/Panel';
import { Chip } from '@/components/ui/Chip';
import { SkeletonRows } from '@/components/ui/Skeleton';
import clsx from 'clsx';

/**
 * Brent Price Decomposition — clean, concise read.
 *
 *  Each row shows ONE driver, signed in $/bbl, with a bar centered on zero.
 *  Right side shows the dollar contribution. No cumulative cursor, no
 *  axis ticks — just "what's pushing Brent away from its baseline."
 */

const COLOURS: Record<string, string> = {
  inventory_adjustment: '#22d3ee',  // cyan
  opec_adjustment:      '#a78bfa',  // purple
  dxy_adjustment:       '#4d8eff',  // blue
  geo_premium:          '#f5a623',  // amber
};

const ROW_LABELS: Record<string, string> = {
  inventory_adjustment: 'Inventory',
  opec_adjustment:      'OPEC+',
  dxy_adjustment:       'Dollar (DXY)',
  geo_premium:          'Geo risk',
};

const ROW_HELP: Record<string, string> = {
  inventory_adjustment: 'Crude stocks vs 5-year seasonal average.',
  opec_adjustment:      'Group production vs stated quotas.',
  dxy_adjustment:       'Dollar strength vs 30-day average.',
  geo_premium:          'News-driven geopolitical risk premium.',
};

export function PriceDecomposition({
  fairValue,
}: {
  fairValue: any;
  signal?: any;
  curve?: any;
}) {
  const brentFv = fairValue?.brent;
  if (!brentFv || !brentFv.live_price) {
    return (
      <Panel title="Brent Price Decomposition" subtitle="Fair value drivers" source="fair_value_model">
        <SkeletonRows rows={6} />
      </Panel>
    );
  }

  const spot = brentFv.live_price;
  const fv   = brentFv.fair_value;
  const dev  = brentFv.deviation_pct ?? 0;
  const base = brentFv.components?.base_cost_of_carry?.value ?? 0;

  // Build the four adjustment rows from the backend payload
  const adjustmentKeys: (keyof typeof COLOURS)[] = [
    'inventory_adjustment', 'opec_adjustment', 'dxy_adjustment', 'geo_premium',
  ];
  const rows = adjustmentKeys.map(k => {
    const c = brentFv.components?.[k];
    return {
      key:   k,
      label: ROW_LABELS[k],
      help:  ROW_HELP[k],
      value: c?.value ?? 0,
      color: COLOURS[k],
    };
  });

  // Bar scale: anchor on the biggest absolute single-component contribution
  const maxAbs = Math.max(0.5, ...rows.map(r => Math.abs(r.value)));

  const devToneClass =
    dev > 4   ? 'text-bear'  :
    dev < -4  ? 'text-bull'  :
                'text-neut';
  const devLabel =
    dev > 4   ? 'Overvalued'  :
    dev < -4  ? 'Undervalued' :
                'Near fair value';

  return (
    <Panel
      title="Brent Price Decomposition"
      subtitle={`Fair value drivers — ${devLabel.toLowerCase()}`}
      accent="blue"
      source="fair_value_model"
      dataTimestamp={fairValue?.timestamp}
      sourceNote="Spot price minus modelled fair value, broken into the four explanatory drivers. Positive bars push Brent up, negative push down."
      right={<Chip tone={dev > 4 ? 'bear' : dev < -4 ? 'bull' : 'neut'}>{dev >= 0 ? '+' : ''}{dev.toFixed(1)}%</Chip>}
    >
      {/* HEADER — spot vs fair value */}
      <div className="grid grid-cols-3 gap-3 mb-5">
        <div className="text-center px-2 py-2 bg-bg-card/40 rounded">
          <div className="text-[9px] font-mono uppercase tracking-widest text-text-muted">Spot</div>
          <div className="text-2xl font-display font-bold tabular text-text-primary">${spot.toFixed(2)}</div>
        </div>
        <div className="text-center px-2 py-2 bg-bg-card/60 rounded border border-gold/25">
          <div className="text-[9px] font-mono uppercase tracking-widest text-gold">vs Fair Value</div>
          <div className={clsx('text-2xl font-display font-bold tabular', devToneClass)}>
            {dev >= 0 ? '+' : ''}{dev.toFixed(1)}%
          </div>
          <div className="text-[9px] font-mono text-text-muted mt-0.5 uppercase tracking-widest">{devLabel}</div>
        </div>
        <div className="text-center px-2 py-2 bg-bg-card/40 rounded">
          <div className="text-[9px] font-mono uppercase tracking-widest text-text-muted">Fair Value</div>
          <div className="text-2xl font-display font-bold tabular text-gold">${(fv ?? 0).toFixed(2)}</div>
        </div>
      </div>

      {/* BASELINE LINE */}
      <div className="flex items-baseline justify-between mb-3 px-1">
        <span className="text-[10px] font-mono text-text-tertiary uppercase tracking-widest">
          Baseline · cost-of-carry
        </span>
        <span className="text-[11px] font-mono tabular text-gold">${base.toFixed(2)}</span>
      </div>

      {/* ROWS */}
      <div className="space-y-2.5">
        {rows.map(r => {
          const pct = Math.abs(r.value) / maxAbs;
          const tone: 'bull' | 'bear' | 'neut' = r.value > 0.05 ? 'bull' : r.value < -0.05 ? 'bear' : 'neut';
          return (
            <div key={r.key} className="grid grid-cols-[100px_1fr_70px] gap-3 items-center" title={r.help}>
              <div className="flex items-center gap-2 min-w-0">
                <span className="w-1.5 h-1.5 rounded-full flex-shrink-0" style={{ background: r.color }} />
                <span className="text-[11px] font-mono text-text-secondary truncate">{r.label}</span>
              </div>
              <div className="relative h-2 bg-bg-elev rounded overflow-hidden">
                {/* zero centre marker */}
                <div className="absolute inset-y-0 left-1/2 w-px bg-border-strong" />
                {/* bar — extends left for negative, right for positive */}
                <div
                  className="absolute inset-y-0 rounded-sm transition-all duration-700"
                  style={{
                    left:  r.value >= 0 ? '50%' : `${50 - pct * 50}%`,
                    width: `${pct * 50}%`,
                    background: tone === 'bull' ? '#10d997' : tone === 'bear' ? '#ff4d6d' : r.color,
                    opacity: pct < 0.05 ? 0.3 : 1,
                  }}
                />
              </div>
              <div className={clsx(
                'text-right text-[11px] font-mono tabular font-semibold',
                tone === 'bull' && 'text-bull',
                tone === 'bear' && 'text-bear',
                tone === 'neut' && 'text-text-muted',
              )}>
                {r.value >= 0 ? '+' : ''}${r.value.toFixed(2)}
              </div>
            </div>
          );
        })}
      </div>

      {/* READING */}
      <div className="mt-5 pt-3 border-t border-border/40 text-[11px] font-mono text-text-tertiary leading-relaxed">
        <span className="text-text-secondary uppercase tracking-widest mr-2">How to read:</span>
        Baseline is what Brent "should" cost if nothing else mattered. Each bar shows how a real-world driver shifts that
        number — green pushes up, red pulls down. The chip top-right is spot vs the summed fair value.
      </div>
    </Panel>
  );
}
