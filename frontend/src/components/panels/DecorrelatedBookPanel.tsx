import { useMemo } from 'react';
import clsx from 'clsx';
import { Panel } from '@/components/ui/Panel';
import { Chip } from '@/components/ui/Chip';
import { SkeletonRows } from '@/components/ui/Skeleton';
import { api } from '@/lib/api';
import { usePolling } from '@/lib/hooks';
import { Layers, TrendingUp, TrendingDown, Ban } from 'lucide-react';

/**
 * Decorrelated book — the mentor's directive made visible.
 *
 *   "Take the top profitable trades but DON'T double up on correlated/similar
 *    bets, so risk doesn't accumulate."
 *
 * The regime engine ranks every spread by conviction; `gated_select` then walks
 * that list greedily and drops any lower-conviction candidate whose SIGNED P&L
 * correlation with something already held is ≥ ρ_max (positive signed-corr =
 * redundant → skip; negative = a hedge → keep). What's left is the book a desk
 * would actually put on — and it's exactly what `auto_desk` trades. This panel
 * shows that decomposition: the selected book + every candidate dropped for
 * correlation, with the ρ that knocked it out. Reads the same
 * `/api/regime/recommendation` the pick card above uses.
 */

type Ranked = {
  spread: string;
  label: string;
  direction: 'BUY' | 'SELL' | 'NEUTRAL';
  z_score: number;
  confidence: number;
  recommendation_source?: 'regime' | 'baseline';
};

type Skip = {
  spread: string;
  direction?: string;
  correlated_with?: string | null;
  rho?: number | null;
  reason?: 'correlated' | 'max_positions' | string;
};

type Portfolio = {
  selected?: string[];
  skipped?: Skip[];
  rho_max?: number;
  window?: number;
  n_actionable?: number;
  n_selected?: number;
} | null;

type Recommendation = {
  available: boolean;
  ranked?: Ranked[];
  portfolio?: Portfolio;
};

function DirChip({ dir }: { dir?: string }) {
  if (dir === 'BUY') return <Chip tone="bull" icon={<TrendingUp className="w-3 h-3" />}>BUY</Chip>;
  if (dir === 'SELL') return <Chip tone="bear" icon={<TrendingDown className="w-3 h-3" />}>SELL</Chip>;
  return <Chip tone="muted">{dir ?? '—'}</Chip>;
}

export function DecorrelatedBookPanel() {
  const { data, lastUpdated, error } = usePolling<Recommendation>(
    () => api.regimeRecommendation() as Promise<Recommendation>,
    60_000,
  );

  const ranked = useMemo(() => data?.ranked ?? [], [data]);
  const pf = data?.portfolio ?? null;

  // spread → ranked row, for joining the portfolio (which carries IDs only)
  const bySpread = useMemo(() => {
    const m: Record<string, Ranked> = {};
    for (const r of ranked) m[r.spread] = r;
    return m;
  }, [ranked]);
  const labelOf = (sp: string) => bySpread[sp]?.label ?? sp;

  if (!data && !error) {
    return (
      <Panel title="Decorrelated book · top non-correlated trades" accent="gold" source="signal_engine"
             staticMount lastSuccess={lastUpdated} fetchError={error}>
        <SkeletonRows rows={4} />
      </Panel>
    );
  }
  if (!data?.available || !pf) {
    return (
      <Panel title="Decorrelated book · top non-correlated trades" accent="gold" source="signal_engine"
             staticMount lastSuccess={lastUpdated} fetchError={error}>
        <div className="text-[12px] font-mono text-text-tertiary px-3 py-6 text-center">
          {error
            ? `Recommendation endpoint unreachable: ${(error as any)?.message ?? String(error)}`
            : 'No decorrelated book available — the regime engine produced no portfolio this tick.'}
        </div>
      </Panel>
    );
  }

  const selected = pf.selected ?? [];
  const skipped = pf.skipped ?? [];
  const correlatedSkips = skipped.filter(s => s.reason === 'correlated');

  return (
    <Panel
      title="Decorrelated book · top non-correlated trades"
      subtitle="mentor directive — take the best ideas, never double up on correlated bets (no risk concentration)"
      accent="gold"
      source="signal_engine"
      staticMount
      lastSuccess={lastUpdated}
      fetchError={error}
      right={
        <div className="flex items-center gap-2">
          <span title={`Signed-P&L correlation ceiling: a candidate is dropped when it correlates ≥ ${pf.rho_max ?? 0.7} with a position already held (trailing ${pf.window ?? 504}d daily changes).`}>
            <Chip tone="neut">ρ_max {pf.rho_max ?? '—'}</Chip>
          </span>
          <span title="Trades kept after decorrelation vs total actionable (BUY/SELL) candidates.">
            <Chip tone="gold" icon={<Layers className="w-3 h-3" />}>
              {pf.n_selected ?? selected.length}/{pf.n_actionable ?? '—'} kept
            </Chip>
          </span>
        </div>
      }
    >
      {/* Selected book — the trades the desk actually puts on */}
      <div className="text-[10px] font-mono uppercase tracking-widest text-gold mb-2">
        Selected book — {selected.length} position{selected.length === 1 ? '' : 's'} (conviction order)
      </div>
      {selected.length === 0 ? (
        <div className="p-3 bg-bg-card/40 rounded text-[11px] font-mono text-text-tertiary text-center">
          No actionable trade right now — every spread is inside its band, so nothing to decorrelate.
        </div>
      ) : (
        <div className="space-y-1.5">
          {selected.map((sp, i) => {
            const r = bySpread[sp];
            return (
              <div
                key={sp}
                className="grid grid-cols-[24px_1fr_88px_72px_72px] items-center gap-3 py-1.5 px-2 rounded bg-gold/5 border border-gold/25 text-[11px] font-mono tabular"
              >
                <span className="text-[10px] text-gold font-bold">#{i + 1}</span>
                <span className="text-text-primary font-semibold truncate" title={sp}>{labelOf(sp)}</span>
                <div className="flex justify-center"><DirChip dir={r?.direction} /></div>
                <span className={clsx('text-right font-bold',
                  (r?.z_score ?? 0) > 1.5 ? 'text-bear' : (r?.z_score ?? 0) < -1.5 ? 'text-bull' : 'text-neut')}>
                  {r ? `${r.z_score >= 0 ? '+' : ''}${r.z_score.toFixed(2)}σ` : '—'}
                </span>
                <span className="text-right text-text-secondary">
                  {r ? `${(r.confidence * 100).toFixed(0)}%` : '—'}
                </span>
              </div>
            );
          })}
        </div>
      )}

      {/* Dropped for correlation — the risk-concentration filter at work */}
      {correlatedSkips.length > 0 && (
        <div className="mt-4">
          <div className="text-[10px] font-mono uppercase tracking-widest text-text-muted mb-2 flex items-center gap-1.5">
            <Ban className="w-3 h-3" /> Dropped — too correlated with a held position
          </div>
          <div className="space-y-1.5">
            {correlatedSkips.map((s, i) => (
              <div
                key={`${s.spread}-${i}`}
                className="grid grid-cols-[1fr_88px_1fr] items-center gap-3 py-1.5 px-2 rounded bg-bg-card/30 border border-border/30 text-[11px] font-mono tabular"
                title={`${s.spread} ${s.direction ?? ''} would move with ${s.correlated_with} (signed P&L ρ=${s.rho}) ≥ ρ_max ${pf.rho_max} → redundant risk, dropped.`}
              >
                <span className="text-text-tertiary line-through decoration-text-muted/50 truncate">{labelOf(s.spread)}</span>
                <div className="flex justify-center opacity-70"><DirChip dir={s.direction} /></div>
                <span className="text-right text-text-tertiary">
                  ρ <span className="text-bear font-bold">{s.rho}</span> with {labelOf(s.correlated_with ?? '')}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="mt-4 text-[10px] font-mono text-text-muted leading-relaxed">
        Concentration is measured on <span className="text-text-tertiary">signed</span> P&L correlation, so a
        same-direction correlated pair is redundant (dropped) but an opposite-direction one is a hedge that
        lowers book variance (kept). The tradeable universe is bimodal — front carry/fly correlate ~0.76–0.87
        within product and ≤0.30 across — so ρ_max {pf.rho_max ?? 0.7} admits at most one trade per
        {' '}{'{'}brent-front, wti-front{'}'} cluster. This selected book is exactly what the live auto-desk trades.
      </div>
    </Panel>
  );
}
