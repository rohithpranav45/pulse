import { useCallback, useMemo, useState } from 'react';
import clsx from 'clsx';
import { Panel } from '@/components/ui/Panel';
import { Chip } from '@/components/ui/Chip';
import { Stat } from '@/components/ui/Stat';
import { SkeletonRows } from '@/components/ui/Skeleton';
import { GitBranch, Play, RotateCcw, TrendingUp, TrendingDown, Minus } from 'lucide-react';
import { api } from '@/lib/api';
import { usePolling } from '@/lib/hooks';
import type { ABReportData, ABArmMetrics, ABArmEquityPoint } from '@/lib/api';
import type { ABBacktestVerdict } from '@/lib/api-types';

/**
 * Phase 2.8.6-followup — A/B paper-test comparison panel.
 *
 * Two arms running in parallel paper books:
 *   pooled  — PULSE_REGIME_MODE=pooled (Phase 2.5 un-gated engine)
 *   gated   — PULSE_GATED_BLEND=1 (Phase 2.6 current default)
 *
 * Headline: per-arm n_closed, NET Sharpe, NET mean PnL, equity curve;
 * Welch's t-test on per-trade NET PnL across arms; paired t-test on
 * matched (session, asset, direction). Stop criteria + verdict ribbon.
 */

function fmtNum(v: number | null | undefined, digits = 3, suffix = ''): string {
  if (v == null || !Number.isFinite(v)) return '—';
  return v.toFixed(digits) + suffix;
}

function verdictTone(v?: string | null): 'gold' | 'bull' | 'bear' | 'muted' {
  if (v === 'pooled_wins') return 'bull';
  if (v === 'gated_wins')  return 'bull';
  if (v === 'undecided_timeout') return 'neut' as any;
  if (v === 'no_data') return 'muted';
  return 'gold';
}

function verdictLabel(v?: string | null): string {
  switch (v) {
    case 'pooled_wins':       return 'WINNER: POOLED';
    case 'gated_wins':        return 'WINNER: GATED';
    case 'undecided':         return 'UNDECIDED';
    case 'undecided_timeout': return 'TIMEOUT — UNDECIDED';
    case 'no_data':           return 'NO DATA';
    default:                  return v ? v.toUpperCase() : 'AWAITING DATA';
  }
}

// Inline-SVG equity curve. Two lines, x = trade index, y = cum NET PnL.
function EquityChart({ pooled, gated }: { pooled: ABArmEquityPoint[]; gated: ABArmEquityPoint[] }) {
  const W = 560;
  const H = 160;
  const M = { l: 38, r: 12, t: 10, b: 22 };

  const series = [
    { name: 'pooled', pts: pooled, color: 'rgb(212,175,55)' },
    { name: 'gated',  pts: gated,  color: 'rgb(77,142,255)' },
  ];

  const allVals = series.flatMap(s => s.pts.map(p => p.cum_pnl_net ?? 0));
  if (allVals.length === 0) {
    return (
      <div className="h-[160px] flex items-center justify-center text-xs text-text-tertiary">
        equity curve appears once trades close
      </div>
    );
  }
  const maxN = Math.max(...series.map(s => s.pts.length), 1);
  const yMin = Math.min(0, ...allVals);
  const yMax = Math.max(0, ...allVals);
  const yRange = (yMax - yMin) || 1;

  const xOf = (i: number) => M.l + (i / Math.max(maxN - 1, 1)) * (W - M.l - M.r);
  const yOf = (v: number) => M.t + (1 - (v - yMin) / yRange) * (H - M.t - M.b);

  // y=0 axis line
  const zeroY = yOf(0);

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-[160px]">
      {/* axes */}
      <line x1={M.l} y1={M.t} x2={M.l} y2={H - M.b} stroke="rgba(255,255,255,0.1)" />
      <line x1={M.l} y1={H - M.b} x2={W - M.r} y2={H - M.b} stroke="rgba(255,255,255,0.1)" />
      {/* y=0 */}
      <line
        x1={M.l} y1={zeroY} x2={W - M.r} y2={zeroY}
        stroke="rgba(255,255,255,0.18)" strokeDasharray="2 3"
      />
      <text x={M.l - 4} y={zeroY + 3} textAnchor="end" fontSize="9" fill="rgba(255,255,255,0.4)">0</text>
      <text x={M.l - 4} y={M.t + 8} textAnchor="end" fontSize="9" fill="rgba(255,255,255,0.4)">{yMax.toFixed(1)}</text>
      <text x={M.l - 4} y={H - M.b - 2} textAnchor="end" fontSize="9" fill="rgba(255,255,255,0.4)">{yMin.toFixed(1)}</text>

      {series.map(s => {
        if (s.pts.length === 0) return null;
        const d = s.pts
          .map((p, i) => `${i === 0 ? 'M' : 'L'} ${xOf(i)} ${yOf(p.cum_pnl_net ?? 0)}`)
          .join(' ');
        return (
          <path key={s.name} d={d} fill="none" stroke={s.color} strokeWidth={1.6} />
        );
      })}

      {/* legend */}
      <g transform={`translate(${M.l + 6}, ${M.t + 6})`}>
        <rect width="6" height="6" fill="rgb(212,175,55)" />
        <text x="10" y="6" fontSize="10" fill="rgba(255,255,255,0.7)">pooled</text>
        <rect x="60" width="6" height="6" fill="rgb(77,142,255)" />
        <text x="70" y="6" fontSize="10" fill="rgba(255,255,255,0.7)">gated</text>
      </g>
    </svg>
  );
}

// The instant, statistically-strong answer from the walk-forward backtest tapes
// (thousands of closed trades) — shown ABOVE the slow live forward book so the
// panel always leads with a real verdict instead of "accumulating forever".
function BacktestVerdictBlock({ bv }: { bv?: ABBacktestVerdict | null }) {
  if (!bv || !bv.available) return null;
  const arms = bv.arms ?? {};
  const p = bv.welch?.p_value;
  const tied = bv.verdict === 'tied';
  const tone: 'gold' | 'bull' = tied ? 'gold' : 'bull';
  const label = bv.verdict === 'pooled_wins' ? 'WINNER: POOLED'
    : bv.verdict === 'gated_wins' ? 'WINNER: GATED'
    : 'STATISTICALLY TIED';

  const tiles: { key: 'pooled' | 'gated' | 'baseline'; name: string; highlight?: boolean }[] = [
    { key: 'pooled',   name: 'pooled' },
    { key: 'gated',    name: 'gated (default)', highlight: true },
    { key: 'baseline', name: 'baseline' },
  ];

  return (
    <div className="mb-3 p-3 rounded-md border border-gold/30 bg-gold/5">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="text-[11px] font-mono font-semibold tracking-wider text-gold">
            BACKTEST VERDICT — pooled vs gated
          </span>
          <Chip tone={tone as any}>{label}</Chip>
          {p != null && Number.isFinite(p) && (
            <span className="text-[10px] font-mono text-text-tertiary">Welch p = {p.toFixed(3)}</span>
          )}
        </div>
        <span className="text-[10px] font-mono text-text-tertiary" title={bv.source ?? ''}>
          {((arms.pooled?.n_closed ?? 0) + (arms.gated?.n_closed ?? 0)).toLocaleString()} closed trades · 2018–2026
        </span>
      </div>
      <div className="grid grid-cols-3 gap-2 mb-2">
        {tiles.map(t => {
          const a = (arms as any)[t.key] as ABBacktestArm | undefined;
          return (
            <div key={t.key} className={clsx(
              'rounded border px-2.5 py-2',
              t.highlight ? 'border-accent-blue/40 bg-accent-blue/5' : 'border-border/40 bg-bg-card/40',
            )}>
              <div className="text-[9px] font-mono uppercase tracking-widest text-text-muted">{t.name}</div>
              <div className={clsx('text-[18px] font-mono font-bold tabular leading-tight',
                t.key === 'baseline' ? 'text-text-primary' : 'text-text-secondary')}>
                {a?.sharpe_net != null ? `${a.sharpe_net >= 0 ? '+' : ''}${a.sharpe_net.toFixed(3)}` : '—'}
              </div>
              <div className="text-[9px] font-mono text-text-tertiary">
                NET Sharpe · hit {a?.hit_rate != null ? `${(a.hit_rate * 100).toFixed(0)}%` : '—'}
              </div>
            </div>
          );
        })}
      </div>
      <div className="text-[10.5px] font-mono leading-relaxed text-text-secondary">
        {bv.verdict_note}
      </div>
    </div>
  );
}

type ABBacktestArm = NonNullable<NonNullable<ABBacktestVerdict['arms']>['pooled']>;

function ArmCard({
  title,
  description,
  tone,
  arm,
}: {
  title: string;
  description: string;
  tone: 'gold' | 'blue';
  arm: ABArmMetrics | undefined;
}) {
  if (!arm) {
    return (
      <div className="border border-border rounded-md p-3 bg-bg-card">
        <div className="text-xs text-text-tertiary">{title}: waiting for data…</div>
      </div>
    );
  }
  const borderClr = tone === 'gold' ? 'border-gold/30' : 'border-accent-blue/30';
  const titleClr  = tone === 'gold' ? 'text-gold' : 'text-accent-blue';
  return (
    <div className={clsx('border rounded-md p-3 bg-bg-card', borderClr)}>
      <div className="flex items-baseline justify-between mb-2">
        <div className={clsx('text-xs font-mono font-semibold tracking-wider', titleClr)}>{title}</div>
        <div className="text-[10px] text-text-tertiary">{description}</div>
      </div>
      <div className="grid grid-cols-3 gap-2">
        <Stat label="closed"      value={String(arm.n_closed ?? 0)} />
        <Stat label="open"        value={String(arm.n_open ?? 0)} />
        <Stat label="hit"         value={arm.hit_rate != null ? `${(arm.hit_rate * 100).toFixed(1)}%` : '—'} />
        <Stat label="sharpe NET"  value={fmtNum(arm.sharpe_net, 3)} />
        <Stat label="mean PnL NET" value={fmtNum(arm.mean_pnl_net, 3)} />
        <Stat label="max DD NET"  value={fmtNum(arm.max_dd_net, 2)} />
        <Stat label="sharpe gross" value={fmtNum(arm.sharpe_gross, 3)} />
        <Stat label="total NET"    value={fmtNum(arm.total_pnl_net, 2)} />
        <Stat label="mean cost"    value={arm.mean_cost != null ? `$${arm.mean_cost.toFixed(3)}` : '—'} />
      </div>
    </div>
  );
}

export function ABComparePanel() {
  const { data, loading, error, refetch } = usePolling<ABReportData>(api.regimeAB, 30_000);
  const [acting, setActing] = useState<null | 'tick' | 'reset'>(null);
  const [actMsg, setActMsg] = useState<string | null>(null);

  const onTick = useCallback(async () => {
    setActing('tick'); setActMsg(null);
    try {
      const out: any = await api.regimeABTick({});
      const pushed = (out?.pushed?.pooled?.length ?? 0) + (out?.pushed?.gated?.length ?? 0);
      const skipped = (out?.skipped?.pooled?.length ?? 0) + (out?.skipped?.gated?.length ?? 0);
      setActMsg(`tick: pushed ${pushed}, skipped ${skipped}`);
      await refetch();
    } catch (e: any) {
      setActMsg(`tick failed: ${e?.message || e}`);
    } finally {
      setActing(null);
    }
  }, [refetch]);

  const onReset = useCallback(async () => {
    if (!window.confirm('Wipe ALL A/B-tagged paper trades? This does NOT touch your regular paper book.')) return;
    setActing('reset'); setActMsg(null);
    try {
      const out: any = await api.regimeABReset('all');
      setActMsg(`reset: removed ${out?.removed ?? 0}`);
      await refetch();
    } catch (e: any) {
      setActMsg(`reset failed: ${e?.message || e}`);
    } finally {
      setActing(null);
    }
  }, [refetch]);

  const pooledEq = useMemo(() => data?.arms?.pooled?.equity_curve ?? [], [data]);
  const gatedEq  = useMemo(() => data?.arms?.gated?.equity_curve  ?? [], [data]);

  // Accumulation state — the panel looks "blank" when nothing has closed yet, so
  // surface the live state explicitly instead of a wall of "—".
  const pClosed = data?.arms?.pooled?.n_closed ?? 0;
  const gClosed = data?.arms?.gated?.n_closed ?? 0;
  const pOpen   = data?.arms?.pooled?.n_open ?? 0;
  const gOpen   = data?.arms?.gated?.n_open ?? 0;
  const pOpened = data?.arms?.pooled?.n_opened ?? 0;
  const gOpened = data?.arms?.gated?.n_opened ?? 0;
  const totalClosed = pClosed + gClosed;
  const accumulating = !!data && totalClosed === 0;

  const verdict = data?.verdict;
  const verdictNote = data?.verdict_note;
  const stop = data?.stop_criteria;
  const diff = data?.diff;

  const headerRight = (
    <div className="flex items-center gap-2">
      <button
        onClick={onTick}
        disabled={acting != null}
        className="inline-flex items-center gap-1 text-[10px] font-mono tracking-wider px-2 py-1 rounded-md border border-gold/40 text-gold hover:bg-gold/10 disabled:opacity-50"
        title="Manually fire one A/B push (idempotent; the scheduler does this once per day)"
      >
        <Play size={11} /> TICK
      </button>
      <button
        onClick={onReset}
        disabled={acting != null}
        className="inline-flex items-center gap-1 text-[10px] font-mono tracking-wider px-2 py-1 rounded-md border border-border text-text-tertiary hover:bg-bg-card disabled:opacity-50"
        title="Wipe all A/B-tagged paper trades. Does not touch the regular paper book."
      >
        <RotateCcw size={11} /> RESET
      </button>
    </div>
  );

  return (
    <Panel
      title="A/B Paper-Test — Pooled vs Gated"
      subtitle="backtest verdict (instant, 13.8k trades) + live forward confirmation"
      accent="gold"
      right={headerRight}
    >
      {loading && !data && <SkeletonRows rows={4} />}
      {error && (
        <div className="text-xs text-bear">error: {error.message}</div>
      )}

      {data && (
        <>
          {/* Backtest verdict — the instant, strong answer (leads the panel) */}
          <BacktestVerdictBlock bv={data.backtest_verdict} />

          {/* Live forward book — slow real-time confirmation of the backtest */}
          <div className="flex items-center gap-2 mb-2 mt-1">
            <span className="text-[10px] font-mono uppercase tracking-widest text-text-muted">
              Live forward book — slow confirmation
            </span>
            <div className="flex-1 h-px bg-border/40" />
          </div>

          {/* Verdict ribbon */}
          <div className="flex items-center justify-between gap-3 mb-3 p-2 rounded-md border border-border bg-bg-card">
            <div className="flex items-center gap-2">
              <GitBranch size={14} className="text-gold" />
              <Chip tone={verdictTone(verdict) as any}>{verdictLabel(verdict)}</Chip>
              {data.sessions && data.sessions.length > 0 && (
                <span className="text-[10px] text-text-tertiary font-mono">
                  {data.sessions.length} session(s) · day {data.days_elapsed ?? 0}/{stop?.max_days ?? 14}
                </span>
              )}
            </div>
            <div className="text-[10px] text-text-tertiary truncate max-w-[60%]" title={verdictNote ?? ''}>
              {verdictNote || 'waiting on trades…'}
            </div>
          </div>

          {/* Accumulating banner — explains the "blank" state honestly instead of
              leaving the user staring at empty cards + dashes. */}
          {accumulating && (
            <div className="mb-3 p-2.5 rounded-md border border-neut/30 bg-neut/5 text-[11px] font-mono leading-relaxed text-text-secondary">
              <span className="text-neut font-semibold">Accumulating — no trades have closed yet.</span>{' '}
              Opened so far: <span className="text-gold">{pOpened} pooled</span> /{' '}
              <span className="text-accent-blue">{gOpened} gated</span> ({pOpen}+{gOpen} still open) across{' '}
              {data.sessions?.length ?? 0} session(s) over {data.days_elapsed ?? 0} day(s). The equity curve,
              t-tests and verdict only appear once trades <span className="text-text-primary">close</span> —
              and trades hold up to ~6 weeks (30 trading-day time-stop), so closes are slow. Two known limits
              gate this: the run times out at {stop?.max_days ?? 14} days (shorter than one trade's max hold),
              and it needs ≥{stop?.min_n_closed ?? 30} closed per arm. Use{' '}
              <span className="text-gold">TICK</span> to push a signal now; closes still take time.
            </div>
          )}

          {/* Two arm cards */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-3">
            <ArmCard
              title="ARM A — POOLED"
              description="PULSE_REGIME_MODE=pooled (un-gated)"
              tone="gold"
              arm={data.arms?.pooled}
            />
            <ArmCard
              title="ARM B — GATED"
              description="PULSE_GATED_BLEND=1 (current default)"
              tone="blue"
              arm={data.arms?.gated}
            />
          </div>

          {/* Equity curve */}
          <div className="mb-3 p-2 rounded-md border border-border bg-bg-card">
            <div className="text-[10px] font-mono tracking-wider text-text-tertiary mb-1">
              CUMULATIVE NET PnL (PHASE 2.8.6 COST-AWARE)
            </div>
            <EquityChart pooled={pooledEq as any} gated={gatedEq as any} />
          </div>

          {/* Stats panel */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div className="p-2 rounded-md border border-border bg-bg-card">
              <div className="text-[10px] font-mono tracking-wider text-text-tertiary mb-2">
                DIFFERENCE (POOLED − GATED)
              </div>
              <div className="grid grid-cols-2 gap-2">
                <Stat
                  label="mean PnL NET Δ"
                  value={fmtNum(diff?.mean_pnl_net_delta, 4)}
                />
                <Stat
                  label="sharpe NET Δ"
                  value={fmtNum(diff?.sharpe_net_delta, 3)}
                />
                <Stat
                  label="Welch t"
                  value={fmtNum(diff?.welch?.t_stat, 3)}
                />
                <Stat
                  label="Welch p"
                  value={fmtNum(diff?.welch?.p_value, 4)}
                />
                <Stat
                  label="paired n"
                  value={String(diff?.paired?.n_pairs ?? 0)}
                />
                <Stat
                  label="paired p"
                  value={fmtNum(diff?.paired?.p_value, 4)}
                />
              </div>
            </div>

            <div className="p-2 rounded-md border border-border bg-bg-card">
              <div className="text-[10px] font-mono tracking-wider text-text-tertiary mb-2">
                STOP CRITERIA
              </div>
              <div className="space-y-1.5">
                <CriterionRow
                  ok={!!stop?.n_closed_ok}
                  label={`closed ≥ ${stop?.min_n_closed ?? 30} per arm`}
                  detail={`${data.arms?.pooled?.n_closed ?? 0} / ${data.arms?.gated?.n_closed ?? 0}`}
                />
                <CriterionRow
                  ok={!!stop?.p_value_ok}
                  label={`Welch p < ${stop?.p_value_lt ?? 0.05}`}
                  detail={fmtNum(diff?.welch?.p_value, 4)}
                />
                <CriterionRow
                  ok={!stop?.timeout}
                  invert
                  label={`day < ${stop?.max_days ?? 14}`}
                  detail={`${data.days_elapsed ?? 0}`}
                />
              </div>
              {actMsg && <div className="mt-2 text-[10px] text-text-tertiary">{actMsg}</div>}
            </div>
          </div>
        </>
      )}
    </Panel>
  );
}

function CriterionRow({
  ok,
  invert,
  label,
  detail,
}: { ok: boolean; invert?: boolean; label: string; detail: string }) {
  // For "day < max_days" we WANT ok=true (i.e. not timed out). The `invert`
  // prop lets that row use the bull/bear tones based on the same boolean.
  const tone = ok ? 'bull' : (invert ? 'bear' : 'muted');
  const Icon = ok ? TrendingUp : (invert ? TrendingDown : Minus);
  const color = ok ? 'text-bull' : (invert ? 'text-bear' : 'text-text-tertiary');
  return (
    <div className="flex items-center justify-between text-[11px] font-mono">
      <div className="flex items-center gap-1.5">
        <Icon size={11} className={color} />
        <span className="text-text-secondary">{label}</span>
      </div>
      <span className={color}>{detail}</span>
    </div>
  );
}
