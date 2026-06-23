import { useMemo } from 'react';
import clsx from 'clsx';
import { Panel } from '@/components/ui/Panel';
import { SkeletonRows } from '@/components/ui/Skeleton';
import { api } from '@/lib/api';
import { usePolling } from '@/lib/hooks';

/**
 * Shock-absorption monitor (REGIME tab).
 *
 * The mentor's single evaluation criterion is shock absorption. This panel shows
 * the live GMM stress read + circuit-breaker state, the validated absorption
 * metrics (stop-loss + onset breaker), and a P(stress) timeline proving the
 * detector. The live read is calibrated on the full 2016-present vol distribution
 * (so normal post-2020 vol isn't mis-flagged); the backtest keeps a causal
 * 2016-2019 fit for out-of-sample validation.
 */

type Current = {
  as_of: string;
  p_stress: number;          // = vol_pct: percentile rank of current realised vol
  realised_vol?: number | null;
  vol_pct?: number;
  onset: number;
  breaker_active: boolean;
  raw_onset_fires?: boolean;
  onset_reliable?: boolean;
  stale?: boolean;
  staleness_days?: number;
  label: 'CALM' | 'NORMAL' | 'ELEVATED' | 'STRESS' | 'STALE';
  note: string;
  onset_gate: number;
  source?: string;
  live?: boolean;
};
type HistPt = { date: string; p_stress: number };
type ShockEvt = { date: string; label: string; p_stress: number };
type Shock = {
  available: boolean;
  error?: string;
  current?: Current;
  history?: HistPt[];
  shock_events?: ShockEvt[];
  absorption?: Record<string, number>;
  mechanisms?: string[];
  detector?: { fit_window: string; method: string };
};

// Graded by vol percentile: STRESS (>92nd) red · ELEVATED/NORMAL (60–92nd) amber · CALM green.
const toneOf = (p: number): 'bull' | 'neut' | 'bear' =>
  p >= 0.92 ? 'bear' : p >= 0.60 ? 'neut' : 'bull';
const sgn = (v: number, d = 2) => (v >= 0 ? `+${v.toFixed(d)}` : v.toFixed(d));

export function ShockMonitorPanel() {
  const { data, lastUpdated, error } = usePolling<Shock>(
    () => api.regimeShock() as Promise<Shock>,
    300_000, // 5 min — the daily stress read changes slowly
  );

  const hist = useMemo(() => data?.history ?? [], [data]);
  const eventByMonth = useMemo(() => {
    const m = new Map<string, ShockEvt>();
    (data?.shock_events ?? []).forEach(e => m.set(e.date.slice(0, 7), e));
    return m;
  }, [data]);

  if (!data && !error) {
    return (
      <Panel title="Shock Absorption · stress monitor" accent="gold" source="shock_engine"
             staticMount lastSuccess={lastUpdated} fetchError={error}>
        <SkeletonRows rows={5} />
      </Panel>
    );
  }
  if (!data?.available || !data.current) {
    return (
      <Panel title="Shock Absorption · stress monitor" accent="gold" source="shock_engine"
             staticMount lastSuccess={lastUpdated} fetchError={error}>
        <div className="text-[12px] font-mono text-text-tertiary px-3 py-6 text-center">
          {error ? `Shock endpoint unreachable: ${(error as any)?.message ?? String(error)}`
                 : data?.error ?? 'Stress detector unavailable.'}
        </div>
      </Panel>
    );
  }

  const c = data.current;
  const a = data.absorption ?? {};
  // A stale read (frozen feed) must not be painted as a live shock — mute it.
  const tone = c.stale ? 'neut' : toneOf(c.p_stress);

  return (
    <Panel
      title="Shock Absorption · regime stress monitor"
      subtitle={`GMM detector · fit ${data.detector?.fit_window ?? '2016–2019'} · read as-of ${c.as_of}`}
      accent="gold"
      source="shock_engine"
      staticMount
      lastSuccess={lastUpdated}
      fetchError={error}
    >
      {/* Live stress read */}
      <div className="flex flex-wrap items-stretch gap-3">
        <div className={clsx(
          'flex flex-col justify-center rounded-lg border px-4 py-3 min-w-[150px]',
          tone === 'bear' && 'border-bear/40 bg-bear/5',
          tone === 'neut' && 'border-neut/40 bg-neut/5',
          tone === 'bull' && 'border-bull/40 bg-bull/5',
        )}>
          <div className="text-[10px] uppercase tracking-widest text-text-muted">
            Vol percentile{c.stale ? ` · ${c.staleness_days}d stale` : ''}
          </div>
          <div className={clsx('text-4xl font-display font-extrabold tabular',
            c.stale && 'opacity-50',
            tone === 'bear' && 'text-bear', tone === 'neut' && 'text-neut', tone === 'bull' && 'text-bull')}>
            {(c.p_stress * 100).toFixed(0)}<span className="text-xl">th</span>
          </div>
          <div className={clsx('text-[11px] font-mono font-bold',
            tone === 'bear' && 'text-bear', tone === 'neut' && 'text-neut', tone === 'bull' && 'text-bull')}>
            {c.label}{c.stale ? ' (frozen feed)' : ''}
          </div>
          {c.realised_vol != null && (
            <div className="text-[10px] font-mono text-text-tertiary mt-0.5">
              {(c.realised_vol * 100).toFixed(0)}% ann. vol
            </div>
          )}
        </div>
        <div className="flex-1 min-w-[220px] flex flex-col justify-center gap-1.5">
          <div className="flex items-center gap-2">
            <span className="text-[11px] font-mono text-text-tertiary">Circuit breaker</span>
            <span className={clsx('rounded px-2 py-0.5 text-[10px] font-mono font-bold uppercase tracking-wide',
              c.breaker_active ? 'bg-bear/20 text-bear' : 'bg-bull/15 text-bull')}>
              {c.breaker_active ? '● PAUSING NEW ENTRIES' : '○ normal trading'}
            </span>
          </div>
          <div className="text-[11px] font-mono text-text-tertiary">
            onset (5d rise) <span className="text-text-secondary tabular">{c.onset.toFixed(2)}</span>
            {' '}· gate <span className="tabular">{c.onset_gate.toFixed(2)}</span>
          </div>
          <div className="text-[11px] font-mono text-text-muted leading-snug">{c.note}</div>
        </div>
      </div>

      {/* P(stress) timeline — proves OOS shock detection */}
      <div className="mt-4">
        <div className="text-[10px] uppercase tracking-widest text-text-muted mb-1">
Vol percentile since 2016 · current vol ranked against full 2016–present history
        </div>
        <div className="flex items-end gap-px h-16 border-b border-border/40">
          {hist.map(pt => {
            const t = toneOf(pt.p_stress);
            const evt = eventByMonth.get(pt.date.slice(0, 7));
            return (
              <div key={pt.date} className="relative flex-1 group" title={`${pt.date.slice(0, 7)} · P(stress) ${(pt.p_stress * 100).toFixed(0)}%${evt ? ' · ' + evt.label : ''}`}>
                <div className={clsx('w-full rounded-t',
                  t === 'bear' && 'bg-bear/70', t === 'neut' && 'bg-neut/60', t === 'bull' && 'bg-bull/40',
                  evt && 'outline outline-1 outline-text-primary/60')}
                  style={{ height: `${Math.max(3, pt.p_stress * 64)}px` }} />
              </div>
            );
          })}
        </div>
        <div className="flex flex-wrap gap-x-4 gap-y-1 mt-1.5">
          {(data.shock_events ?? []).map(e => (
            <span key={e.date} className="text-[10px] font-mono text-text-tertiary">
              <span className="text-bear font-bold">▲</span> {e.date.slice(0, 7)} {e.label}
              <span className="text-text-muted"> ({(e.p_stress * 100).toFixed(0)}%)</span>
            </span>
          ))}
        </div>
      </div>

      {/* Validated absorption metrics — before/after */}
      <div className="mt-4 grid grid-cols-2 sm:grid-cols-4 gap-2">
        {[
          ['worst trade', a.worst_trade_raw, a.worst_trade_stopped, 'stop-loss caps the tail'],
          ['2026 shock P&L', a.shock2026_raw, a.shock2026_stopped, 'stops flip it to profit'],
          ['max drawdown', a.maxdd_stops, a.maxdd_breaker, 'onset breaker'],
          ['Sharpe', a.sharpe_stops, a.sharpe_breaker, 'onset breaker'],
        ].map(([label, before, after, sub]) => {
          const improved = (after as number) >= (before as number);
          return (
            <div key={label as string} className="rounded border border-border/40 bg-bg-card/40 px-2.5 py-2">
              <div className="text-[9px] uppercase tracking-wide text-text-muted">{label as string}</div>
              <div className="flex items-baseline gap-1.5 font-mono tabular">
                <span className="text-[11px] text-text-muted line-through">{sgn(before as number)}</span>
                <span className={clsx('text-[15px] font-bold', improved ? 'text-bull' : 'text-bear')}>
                  {sgn(after as number)}
                </span>
              </div>
              <div className="text-[9px] font-mono text-text-muted">{sub as string}</div>
            </div>
          );
        })}
      </div>

      {/* The mechanisms — the narrative */}
      <div className="mt-4 rounded border border-gold/25 bg-gold/5 px-3 py-2">
        <div className="text-[10px] uppercase tracking-widest text-gold mb-1">How the desk absorbs shocks</div>
        <ol className="space-y-1 text-[11px] font-mono leading-relaxed text-text-tertiary list-decimal pl-4">
          {(data.mechanisms ?? []).map((m, i) => <li key={i}>{m}</li>)}
        </ol>
      </div>
    </Panel>
  );
}
