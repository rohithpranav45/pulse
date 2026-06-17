import { Fragment, useMemo } from 'react';
import clsx from 'clsx';
import { Panel } from '@/components/ui/Panel';
import { Stat } from '@/components/ui/Stat';
import { Shield, AlertOctagon, Layers } from 'lucide-react';
import type { PaperPosition } from '@/lib/api-types';

/**
 * DESK risk panel — three reads on the open paper book:
 *   1. Sum-of-stops-if-all-hit  (gross drawdown if every open position hits its SL)
 *   2. Gross exposure by leg    (signed qty by Brent/WTI contract bucket: c1/c2/c3/c6)
 *   3. 30d rolling correlation  (between underlyings held — filtered from /api/correlations)
 *
 * Renders a stable empty state when nothing is open ("risk = 0").
 */

type LegExposure = {
  product: 'brent' | 'wti';
  contract: string;        // c1, c2, c3, c6
  net_qty: number;
};

const CORR_LABELS: Record<string, string> = {
  brent: 'BRT', wti: 'WTI', hh: 'NG', dxy: 'DXY', spx: 'SPX',
};

function corrColor(v: number) {
  const a = Math.abs(v);
  const hue = v >= 0 ? 152 : 348;
  return `hsl(${hue}, 70%, ${15 + a * 40}%)`;
}

function productOf(asset: string | null | undefined): 'brent' | 'wti' | null {
  if (!asset) return null;
  if (asset.startsWith('brent')) return 'brent';
  if (asset.startsWith('wti')) return 'wti';
  return null;
}

export function RiskPanel({
  positions,
  correlations,
}: {
  positions: PaperPosition[];
  correlations: any;
}) {
  const open = useMemo(() => positions.filter(p => p.status === 'OPEN'), [positions]);

  // ── 1. Sum of stops if all hit ────────────────────────────────────────────
  const sumOfStops = useMemo(() => {
    let total = 0;
    let withStops = 0;
    for (const p of open) {
      const entry = p.entry_price;
      const stop = p.stop_price;
      const size = p.size ?? 1;
      if (entry === null || entry === undefined) continue;
      if (stop === null || stop === undefined) continue;
      withStops += 1;
      // LONG: loss = (entry - stop) * size; SHORT: loss = (stop - entry) * size
      const loss = (p.direction === 'LONG' ? (entry - stop) : (stop - entry)) * size;
      // Only take negative side — if stop is on the wrong side, treat as 0 (defensive).
      total += Math.max(0, loss);
    }
    return { total, withStops };
  }, [open]);

  // ── 2. Gross exposure by leg ──────────────────────────────────────────────
  const legExposures = useMemo<LegExposure[]>(() => {
    // Keyed by `${product}:${contract}`.
    const acc = new Map<string, number>();
    for (const p of open) {
      const prod = productOf(p.asset);
      if (!prod) continue;
      const legs = p.legs ?? [];
      if (legs.length === 0) continue;
      for (const L of legs) {
        const contract = (L as any).contract as string | undefined;
        if (!contract) continue;
        const qty = (L as any).qty as number | undefined;
        const direction = ((L as any).direction as string | undefined) ?? 'LONG';
        if (qty === undefined || qty === null) continue;
        const signed = (direction === 'LONG' ? 1 : -1) * qty;
        const key = `${prod}:${contract}`;
        acc.set(key, (acc.get(key) ?? 0) + signed);
      }
    }
    const rows: LegExposure[] = [];
    for (const [key, net_qty] of acc.entries()) {
      const [prod, contract] = key.split(':');
      rows.push({ product: prod as 'brent' | 'wti', contract, net_qty });
    }
    // Sort: brent first, then by contract id
    rows.sort((a, b) => {
      if (a.product !== b.product) return a.product === 'brent' ? -1 : 1;
      return a.contract.localeCompare(b.contract, 'en', { numeric: true });
    });
    return rows;
  }, [open]);

  // ── 3. Correlations of held underlyings ───────────────────────────────────
  const heldUnderlyings = useMemo(() => {
    const set = new Set<string>();
    for (const p of open) {
      const prod = productOf(p.asset);
      if (prod) set.add(prod);
    }
    return Array.from(set);
  }, [open]);

  const corrMatrix = useMemo(() => {
    const m = correlations?.matrix?.matrix ?? correlations?.matrix;
    if (!m || typeof m !== 'object') return null;
    return m as Record<string, Record<string, number>>;
  }, [correlations]);

  // ── Empty state ───────────────────────────────────────────────────────────
  if (open.length === 0) {
    return (
      <Panel
        title="Risk"
        subtitle="open paper book"
        accent="neut"
        source="paper_book"
        staticMount
      >
        <div className="flex flex-col items-center justify-center py-8 text-center">
          <Shield className="w-6 h-6 text-text-tertiary mb-2" />
          <div className="text-[12px] font-mono text-text-secondary">
            No open positions — risk = 0
          </div>
          <div className="text-[10px] font-mono text-text-muted mt-1">
            Push a regime pick to begin.
          </div>
        </div>
      </Panel>
    );
  }

  const stopsTone = sumOfStops.total > 50 ? 'bear' : sumOfStops.total > 10 ? 'neut' : 'bull';

  return (
    <Panel
      title="Risk"
      subtitle={`${open.length} open · live`}
      accent="neut"
      source="paper_book"
      staticMount
    >
      {/* Row 1: Sum-of-stops + open count */}
      <div className="grid grid-cols-3 gap-3 mb-4">
        <Stat
          label="Sum of stops"
          value={`-$${sumOfStops.total.toFixed(2)}`}
          sub={`${sumOfStops.withStops}/${open.length} with SL`}
          tone={stopsTone as any}
        />
        <Stat
          label="Open positions"
          value={`${open.length}`}
          sub="paper book"
        />
        <Stat
          label="Underlyings"
          value={heldUnderlyings.map(u => u.toUpperCase()).join(' · ') || '—'}
          sub={legExposures.length ? `${legExposures.length} legs net` : 'no legs'}
        />
      </div>

      {/* Row 2: Gross exposure by leg */}
      <div className="mb-4 pt-3 border-t border-border/40">
        <div className="text-[10px] font-mono uppercase tracking-widest text-text-muted mb-2 flex items-center gap-2">
          <Layers className="w-3 h-3" />
          <span>Gross exposure by leg</span>
        </div>
        {legExposures.length === 0 ? (
          <div className="text-[10.5px] font-mono text-text-muted px-2 py-2">
            No leg-decomposed positions open (outright trades only).
          </div>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
            {legExposures.map(r => {
              const long = r.net_qty > 0;
              const flat = Math.abs(r.net_qty) < 1e-9;
              return (
                <div
                  key={`${r.product}-${r.contract}`}
                  className={clsx(
                    'flex items-baseline justify-between px-2 py-1.5 rounded border',
                    flat ? 'border-border/30 bg-bg-card/30'
                         : long ? 'border-bull/30 bg-bull-soft'
                                : 'border-bear/30 bg-bear-soft',
                  )}
                >
                  <span className="text-[10px] font-mono uppercase tracking-widest text-text-secondary">
                    {r.product === 'brent' ? 'BRT' : 'WTI'} {r.contract}
                  </span>
                  <span className={clsx(
                    'text-[12px] font-mono font-semibold tabular',
                    flat ? 'text-text-muted' : long ? 'text-bull' : 'text-bear',
                  )}>
                    {r.net_qty >= 0 ? '+' : ''}{r.net_qty.toFixed(1)}
                  </span>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Row 3: 30d correlation between held underlyings */}
      <div className="pt-3 border-t border-border/40">
        <div className="text-[10px] font-mono uppercase tracking-widest text-text-muted mb-2 flex items-center gap-2">
          <AlertOctagon className="w-3 h-3" />
          <span>30d rolling correlation · held underlyings</span>
        </div>
        {heldUnderlyings.length < 2 || !corrMatrix ? (
          <div className="text-[10.5px] font-mono text-text-muted px-2 py-2">
            {heldUnderlyings.length < 2
              ? `Only ${heldUnderlyings.length} underlying held — correlation needs ≥2.`
              : 'Correlation matrix unavailable.'}
          </div>
        ) : heldUnderlyings.length === 2 ? (
          // Two underlyings → one pair. A 2×2 matrix here is mostly dead cells;
          // render the single meaningful number as a compact chip instead.
          (() => {
            const [a, b] = heldUnderlyings;
            const v = corrMatrix[a]?.[b] ?? null;
            if (v === null || v === undefined) {
              return <div className="text-[10.5px] font-mono text-text-muted px-2 py-2">Pair correlation unavailable.</div>;
            }
            const strong = Math.abs(v) > 0.7;
            return (
              <div className="flex items-center gap-3 py-1">
                <div className="flex items-center gap-2 text-[11px] font-mono uppercase tracking-widest text-text-secondary">
                  <span>{CORR_LABELS[a] ?? a.toUpperCase()}</span>
                  <span className="text-text-muted">↔</span>
                  <span>{CORR_LABELS[b] ?? b.toUpperCase()}</span>
                </div>
                <div
                  className="px-3 py-1 rounded text-[13px] font-mono font-bold tabular"
                  style={{
                    background: corrColor(v),
                    color: Math.abs(v) > 0.5 ? '#fff' : '#aebccf',
                  }}
                >
                  {v >= 0 ? '+' : ''}{v.toFixed(2)}
                </div>
                <span className="text-[10px] font-mono text-text-muted">
                  {strong ? (v > 0 ? 'tightly co-moving' : 'tightly inverse') : 'loose link'}
                </span>
              </div>
            );
          })()
        ) : (
          // Three or more → real matrix, but cap cell size so it doesn't blow up.
          <div
            className="inline-grid gap-1.5"
            style={{ gridTemplateColumns: `40px repeat(${heldUnderlyings.length}, 40px)` }}
          >
            <div />
            {heldUnderlyings.map(u => (
              <div key={u} className="text-[9px] font-mono uppercase tracking-widest text-text-tertiary text-center pb-1">
                {CORR_LABELS[u] ?? u.toUpperCase()}
              </div>
            ))}
            {heldUnderlyings.map(rowU => (
              <Fragment key={`row-${rowU}`}>
                <div className="text-[9px] font-mono uppercase tracking-widest text-text-tertiary flex items-center justify-end pr-1">
                  {CORR_LABELS[rowU] ?? rowU.toUpperCase()}
                </div>
                {heldUnderlyings.map(colU => {
                  const v = corrMatrix[rowU]?.[colU] ?? null;
                  const same = rowU === colU;
                  if (same) {
                    return (
                      <div
                        key={`${rowU}-${colU}`}
                        className="w-10 h-10 rounded flex items-center justify-center text-[11px] font-mono font-bold tabular"
                        style={{ background: '#1c2745', color: '#6b809e' }}
                      >
                        —
                      </div>
                    );
                  }
                  if (v === null || v === undefined) {
                    return (
                      <div
                        key={`${rowU}-${colU}`}
                        className="w-10 h-10 rounded flex items-center justify-center text-[10px] font-mono text-text-muted"
                        style={{ background: '#1c2745' }}
                      >
                        n/a
                      </div>
                    );
                  }
                  return (
                    <div
                      key={`${rowU}-${colU}`}
                      className="w-10 h-10 rounded flex items-center justify-center text-[11px] font-mono font-bold tabular"
                      style={{
                        background: corrColor(v),
                        color: Math.abs(v) > 0.5 ? '#fff' : '#aebccf',
                      }}
                    >
                      {v.toFixed(2)}
                    </div>
                  );
                })}
              </Fragment>
            ))}
          </div>
        )}
      </div>
    </Panel>
  );
}
