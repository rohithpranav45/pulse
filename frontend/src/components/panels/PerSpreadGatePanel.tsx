import { Fragment, useMemo } from 'react';
import clsx from 'clsx';
import { Panel } from '@/components/ui/Panel';
import { Chip } from '@/components/ui/Chip';
import { SkeletonRows } from '@/components/ui/Skeleton';
import { api } from '@/lib/api';
import { usePolling } from '@/lib/hooks';
import { TrendingUp, ArrowRight } from 'lucide-react';

/**
 * Phase 8 — per-spread gate.
 *
 * Surfaces the verdict that replaced the uniform global gate with a per-spread
 * enable decision: the regime leg fires for a spread only when its out-of-sample
 * NET Sharpe beat the rolling-z baseline (decided walk-forward). The panel reads
 * as: the three NET-Sharpe headlines (baseline / uniform gate / per-spread), then
 * a per-spread decision table — regime-leg vs baseline-leg Sharpe, and which one
 * the gate keeps. Static data from the walk-forward report; regenerate with
 * `python -m backend.research.walkforward --perspread-gate-only`.
 */

type PerSpread = {
  spread: string;
  label: string;
  enabled: boolean;
  regime_sharpe: number | null;
  baseline_sharpe: number | null;
  delta: number | null;
  n_regime: number | null;
};

type PerSpreadGate = {
  available: boolean;
  error?: string;
  enabled_latest?: string[];
  n_regime?: number;
  n_baseline?: number;
  config?: { margin?: number; min_n?: number };
  headline?: {
    baseline_net_sharpe: number | null;
    global_gate_net_sharpe: number | null;
    perspread_net_sharpe: number | null;
  };
  per_spread?: PerSpread[];
  note?: string;
  source?: string;
};

function fmt(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return '—';
  return `${n >= 0 ? '+' : ''}${n.toFixed(3)}`;
}

// Map a Sharpe to a 0..100% bar width on a shared [-1.3, +1.3] scale so the two
// legs are visually comparable across spreads.
const SCALE = 1.3;
function barPct(n: number | null): number {
  if (n === null || n === undefined) return 0;
  return Math.min(100, (Math.abs(n) / SCALE) * 100);
}

/** The verdict header — three NET-Sharpe headlines, per-spread highlighted. */
function VerdictStrip({ h }: { h: NonNullable<PerSpreadGate['headline']> }) {
  const cells: { label: string; value: number | null; tone: 'neut' | 'muted' | 'gold'; sub?: string }[] = [
    { label: 'Baseline', value: h.baseline_net_sharpe, tone: 'neut', sub: 'regime-unaware 252d z' },
    { label: 'Global gate', value: h.global_gate_net_sharpe, tone: 'muted', sub: 'uniform — prior production' },
    { label: 'Per-spread gate', value: h.perspread_net_sharpe, tone: 'gold', sub: 'enabled where it earns it' },
  ];
  return (
    <div className="grid grid-cols-[1fr_auto_1fr_auto_1fr] items-stretch gap-2 mb-4">
      {cells.map((c, i) => (
        <Fragment key={c.label}>
          <div
            className={clsx(
              'rounded-md border px-3 py-2.5 flex flex-col justify-center',
              c.tone === 'gold' ? 'border-gold/40 bg-gold/5' : 'border-border/40 bg-bg-card/40',
            )}
          >
            <div className="text-[9px] font-mono uppercase tracking-widest text-text-muted">{c.label}</div>
            <div
              className={clsx(
                'text-[20px] font-mono font-bold tabular leading-tight mt-0.5',
                c.tone === 'gold' ? 'text-gold' : c.tone === 'muted' ? 'text-text-muted' : 'text-text-primary',
              )}
            >
              {fmt(c.value)}
            </div>
            <div className="text-[9px] font-mono text-text-tertiary mt-0.5">{c.sub}</div>
          </div>
          {i < cells.length - 1 && (
            <div className="flex items-center justify-center text-text-muted">
              <ArrowRight className="w-4 h-4" />
            </div>
          )}
        </Fragment>
      ))}
    </div>
  );
}

export function PerSpreadGatePanel() {
  const { data, lastUpdated, error } = usePolling<PerSpreadGate>(
    () => api.regimePerspreadGate() as Promise<PerSpreadGate>,
    600_000, // 10 min — only changes when the walk-forward reruns
  );

  const rows = useMemo(() => data?.per_spread ?? [], [data]);

  if (!data && !error) {
    return (
      <Panel title="Per-spread gate · Phase 8" accent="gold" source="walkforward_report"
             staticMount lastSuccess={lastUpdated} fetchError={error}>
        <SkeletonRows rows={6} />
      </Panel>
    );
  }
  if (!data?.available) {
    return (
      <Panel title="Per-spread gate · Phase 8" accent="gold" source="walkforward_report"
             staticMount lastSuccess={lastUpdated} fetchError={error}>
        <div className="text-[12px] font-mono text-text-tertiary px-3 py-6 text-center">
          {error
            ? `Per-spread gate endpoint unreachable: ${(error as any)?.message ?? String(error)}`
            : data?.error ?? 'No per-spread gate block — run the walk-forward with --perspread-gate-only.'}
        </div>
      </Panel>
    );
  }

  const h = data.headline;
  const enabled = data.enabled_latest ?? [];
  const margin = data.config?.margin ?? 0;
  const minN = data.config?.min_n ?? 20;

  return (
    <Panel
      title="Per-spread gate · Phase 8"
      subtitle={`regime leg fires only where its OOS NET Sharpe beat baseline · ${enabled.length}/${rows.length} spreads on`}
      accent="gold"
      source="walkforward_report"
      staticMount
      lastSuccess={lastUpdated}
      fetchError={error}
      right={
        <div className="flex items-center gap-2">
          <span title="The spreads whose regime leg is enabled by the per-spread gate (their walk-forward OOS NET Sharpe beat the rolling-z baseline).">
            <Chip tone="blue" icon={<TrendingUp className="w-3 h-3" />}>
              {enabled.length > 0 ? enabled.join(' · ') : 'none on'}
            </Chip>
          </span>
        </div>
      }
    >
      {h && <VerdictStrip h={h} />}

      <div className="text-[11px] font-mono text-text-tertiary leading-relaxed mb-3">
        The uniform global gate fired the regime engine on every BACK cell — dragging the book
        <span className="text-text-muted"> {fmt(h?.global_gate_net_sharpe)}</span>, below baseline
        <span className="text-text-secondary"> {fmt(h?.baseline_net_sharpe)}</span>. The per-spread gate
        enables the regime leg <span className="text-gold">only where it beat baseline out-of-sample</span>,
        lifting the book to <span className="text-gold">{fmt(h?.perspread_net_sharpe)}</span> — baseline parity.
      </div>

      {/* Per-spread decision table */}
      <div className="grid grid-cols-[1fr_84px_1fr_1fr_56px] items-center gap-3 text-[9px] font-mono uppercase tracking-widest text-text-muted border-b border-border pb-1 mb-1">
        <span>Spread</span>
        <span className="text-center">Gate</span>
        <span className="text-right">Regime leg</span>
        <span className="text-right">Baseline leg</span>
        <span className="text-right">Δ</span>
      </div>
      <div className="space-y-1.5">
        {rows.map(r => {
          const regimeWins = r.delta !== null && r.delta > 0;
          return (
            <div
              key={r.spread}
              className={clsx(
                'grid grid-cols-[1fr_84px_1fr_1fr_56px] items-center gap-3 py-1.5 px-1 rounded text-[11px] font-mono tabular',
                r.enabled && 'bg-gold/5',
              )}
              title={
                r.enabled
                  ? `${r.spread}: regime leg ENABLED — its OOS NET Sharpe (${fmt(r.regime_sharpe)}) beat baseline (${fmt(r.baseline_sharpe)}). The live engine fires the regime signal here.`
                  : `${r.spread}: regime leg OFF — baseline (${fmt(r.baseline_sharpe)}) ≥ regime (${fmt(r.regime_sharpe)}) out-of-sample, so this spread uses the 252d rolling-z baseline.`
              }
            >
              <span className="text-text-secondary font-semibold truncate" title={r.label}>{r.spread}</span>
              <div className="flex justify-center">
                {r.enabled
                  ? <Chip tone="gold">REGIME ON</Chip>
                  : <Chip tone="muted">baseline</Chip>}
              </div>
              {/* Regime leg sharpe + bar */}
              <div className="flex items-center justify-end gap-2">
                <div className="relative h-2 w-full max-w-[90px] bg-bg-card/40 rounded overflow-hidden border border-border/30">
                  <div
                    className={clsx('absolute top-0 bottom-0 left-0',
                      regimeWins ? 'bg-gold/60' : (r.regime_sharpe ?? 0) >= 0 ? 'bg-bull/40' : 'bg-bear/50')}
                    style={{ width: `${barPct(r.regime_sharpe)}%` }}
                  />
                </div>
                <span className={clsx('w-12 text-right font-bold',
                  regimeWins ? 'text-gold' : 'text-text-tertiary')}>{fmt(r.regime_sharpe)}</span>
              </div>
              {/* Baseline leg sharpe + bar */}
              <div className="flex items-center justify-end gap-2">
                <div className="relative h-2 w-full max-w-[90px] bg-bg-card/40 rounded overflow-hidden border border-border/30">
                  <div
                    className={clsx('absolute top-0 bottom-0 left-0',
                      !regimeWins ? 'bg-neut/60' : (r.baseline_sharpe ?? 0) >= 0 ? 'bg-bull/30' : 'bg-bear/40')}
                    style={{ width: `${barPct(r.baseline_sharpe)}%` }}
                  />
                </div>
                <span className={clsx('w-12 text-right font-bold',
                  !regimeWins ? 'text-neut' : 'text-text-tertiary')}>{fmt(r.baseline_sharpe)}</span>
              </div>
              <span className={clsx('text-right',
                r.delta === null ? 'text-text-muted' : r.delta > 0 ? 'text-bull' : 'text-bear')}>
                {r.delta === null ? '—' : `${r.delta >= 0 ? '+' : ''}${r.delta.toFixed(2)}`}
              </span>
            </div>
          );
        })}
      </div>

      <div className="mt-4 text-[10px] font-mono text-text-muted leading-relaxed">
        Decision rule: the regime leg is enabled for a spread when its annualised NET Sharpe beat the
        baseline by ≥ {margin} on ≥ {minN} out-of-sample trades, decided walk-forward at each refit boundary
        (so it's genuinely OOS, not in-sample selection). Δ = regime − baseline NET Sharpe (full tape; the
        live decision is the per-cutoff version — same direction). Live default-on
        (<span className="text-text-tertiary">PULSE_PERSPREAD_GATE=0</span> reverts to the uniform gate).
        Source: {data.source}.
      </div>
    </Panel>
  );
}
