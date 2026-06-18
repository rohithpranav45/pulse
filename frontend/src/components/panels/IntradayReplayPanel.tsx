import { useMemo } from 'react';
import clsx from 'clsx';
import { Panel } from '@/components/ui/Panel';
import { SkeletonRows } from '@/components/ui/Skeleton';
import { api } from '@/lib/api';
import { usePolling } from '@/lib/hooks';

/**
 * Live-feed sanity replay (SIGNAL LOG tab).
 *
 * Walks the recorder's REAL 15-min spread path with the live engine's overlay-
 * corrected fair value + the tuned exit rule (TP halfway-to-fair · SL 2.5σ ·
 * close-based). This is a DIAGNOSTIC of what the live engine would have done in
 * the ~6-day feed window — NOT a statistically valid backtest. The on-screen
 * caveats say so; the real validation is the walk-forward (REGIME tab) + the
 * forward A/B book.
 */

type Trade = {
  dir: 'BUY' | 'SELL';
  t_in: string;
  entry: number;
  target: number;
  stop: number;
  t_out: string;
  exit: number;
  reason: 'target' | 'stop' | 'open';
  pnl: number;
};

type Metrics = {
  trades: number;
  closed: number;
  open: number;
  wins: number;
  losses: number;
  win_rate: number;
  gross: number;
  cost: number;
  net: number;
  pf: number | null;
  mean: number;
  best: number;
  worst: number;
} | null;

type SpreadReplay = {
  spread: string;
  label: string;
  is_wti: boolean;
  fair: number;
  sigma: number;
  z_latest: number;
  n_bars: number;
  range_low: number;
  range_high: number;
  last: number;
  trades: Trade[];
  metrics: Metrics;
};

type Replay = {
  available: boolean;
  error?: string;
  feed_file?: string;
  regime?: string;
  regime_mode?: string;
  gated?: boolean;
  window?: { start: string | null; end: string | null };
  tuned_rule?: { entry_z: number; tp_frac: number; sl_mult: number; note: string };
  spreads?: SpreadReplay[];
  overall?: Metrics;
  caveats?: string[];
};

const pf = (v: number | null | undefined) => (v == null ? '∞' : v.toFixed(2));
const sgn = (v: number) => (v >= 0 ? `+${v.toFixed(3)}` : v.toFixed(3));
const tone = (v: number): 'bull' | 'bear' | 'neut' =>
  v > 0 ? 'bull' : v < 0 ? 'bear' : 'neut';
const clip = (ts?: string | null) => (ts ? ts.slice(5, 16) : '—');

function MetricStrip({ m }: { m: Metrics }) {
  if (!m) return null;
  const cells: [string, string, ('bull' | 'bear' | 'neut' | 'gold' | 'plain')?][] = [
    ['trades', `${m.trades}`, 'plain'],
    ['win rate', `${m.win_rate}%`, m.win_rate >= 50 ? 'bull' : 'bear'],
    ['gross', sgn(m.gross), tone(m.gross)],
    ['cost', `-${m.cost.toFixed(3)}`, 'plain'],
    ['NET', sgn(m.net), tone(m.net)],
    ['PF', pf(m.pf), 'gold'],
  ];
  return (
    <div className="grid grid-cols-3 sm:grid-cols-6 gap-2">
      {cells.map(([label, val, t]) => (
        <div key={label} className="rounded border border-border/40 bg-bg-card/40 px-2.5 py-1.5">
          <div className="text-[9px] uppercase tracking-wide text-text-muted">{label}</div>
          <div
            className={clsx(
              'text-[13px] font-mono font-bold tabular',
              t === 'bull' && 'text-bull',
              t === 'bear' && 'text-bear',
              t === 'neut' && 'text-neut',
              t === 'gold' && 'text-gold',
              (!t || t === 'plain') && 'text-text-secondary',
            )}
          >
            {val}
          </div>
        </div>
      ))}
    </div>
  );
}

export function IntradayReplayPanel() {
  const { data, lastUpdated, error } = usePolling<Replay>(
    () => api.regimeIntradayReplay() as Promise<Replay>,
    600_000, // 10 min — the recorder advances slowly and the replay re-reads the feed
  );

  const spreads = useMemo(() => data?.spreads ?? [], [data]);

  if (!data && !error) {
    return (
      <Panel title="Live-feed sanity replay" accent="gold" source="intraday_replay"
             staticMount lastSuccess={lastUpdated} fetchError={error}>
        <SkeletonRows rows={5} />
      </Panel>
    );
  }
  if (!data?.available) {
    return (
      <Panel title="Live-feed sanity replay" accent="gold" source="intraday_replay"
             staticMount lastSuccess={lastUpdated} fetchError={error}>
        <div className="text-[12px] font-mono text-text-tertiary px-3 py-6 text-center">
          {error
            ? `Replay endpoint unreachable: ${(error as any)?.message ?? String(error)}`
            : data?.error ?? 'Live feed unavailable — the recorder share must be reachable to replay.'}
        </div>
      </Panel>
    );
  }

  const w = data.window;

  return (
    <Panel
      title="Live-feed sanity replay"
      subtitle={`${clip(w?.start)} → ${clip(w?.end)} · ${data.regime ?? '—'} · ${data.tuned_rule?.note ?? ''}`}
      accent="gold"
      source="intraday_replay"
      staticMount
      lastSuccess={lastUpdated}
      fetchError={error}
    >
      {/* Diagnostic banner — keep the honesty front-and-centre */}
      <div className="mb-3 rounded border border-gold/30 bg-gold/5 px-3 py-2 text-[11px] font-mono leading-relaxed text-text-tertiary">
        <span className="text-gold font-bold">DIAGNOSTIC · not a backtest.</span>{' '}
        What the live engine would have done on the recorder's real 15-min tape over this
        ~6-day window. The real validation is the walk-forward (REGIME tab) + the forward A/B book.
      </div>

      {/* Overall metrics */}
      <div className="mb-2 text-[10px] uppercase tracking-wide text-text-muted">Overall ($/bbl spread)</div>
      <MetricStrip m={data.overall} />

      {/* Per-spread breakdown */}
      <div className="mt-4 space-y-2">
        {spreads.map(s => (
          <details key={s.spread} className="group rounded border border-border/40 bg-bg-card/30">
            <summary className="flex cursor-pointer list-none items-center justify-between gap-2 px-3 py-2 text-[12px] font-mono">
              <span className="flex items-center gap-2">
                <span className="text-text-secondary">{s.label}</span>
                {s.is_wti && (
                  <span className="rounded bg-neut/15 px-1.5 py-0.5 text-[9px] uppercase tracking-wide text-neut"
                        title="WTI models trained on synthetic settlements (gotcha 11) — indicative only">
                    synth
                  </span>
                )}
              </span>
              <span className="flex items-center gap-3 tabular">
                <span className="text-text-muted">fair {sgn(s.fair)} · z{sgn(s.z_latest)}</span>
                {s.metrics && (
                  <>
                    <span className="text-text-tertiary">{s.metrics.trades}t · {s.metrics.win_rate}%</span>
                    <span className={clsx('font-bold',
                      s.metrics.net > 0 ? 'text-bull' : s.metrics.net < 0 ? 'text-bear' : 'text-neut')}>
                      NET {sgn(s.metrics.net)}
                    </span>
                  </>
                )}
                <span className="text-text-muted transition-transform group-open:rotate-90">›</span>
              </span>
            </summary>
            <div className="border-t border-border/40 px-3 py-2">
              <div className="mb-2 text-[10px] font-mono text-text-muted">
                {s.n_bars} bars · range [{sgn(s.range_low)}, {sgn(s.range_high)}] · last {sgn(s.last)} · σ {s.sigma.toFixed(3)}
              </div>
              {s.trades.length === 0 ? (
                <div className="text-[11px] font-mono text-text-tertiary py-1">
                  no entry (|z| never crossed the threshold in-window)
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-[11px] font-mono tabular">
                    <thead>
                      <tr className="text-text-muted text-left">
                        <th className="pr-2 font-normal">#</th>
                        <th className="pr-2 font-normal">dir</th>
                        <th className="pr-2 font-normal">in</th>
                        <th className="pr-2 font-normal text-right">entry</th>
                        <th className="pr-2 font-normal text-right">tgt</th>
                        <th className="pr-2 font-normal text-right">stop</th>
                        <th className="pr-2 font-normal">out</th>
                        <th className="pr-2 font-normal text-right">exit</th>
                        <th className="pr-2 font-normal">why</th>
                        <th className="font-normal text-right">pnl</th>
                      </tr>
                    </thead>
                    <tbody>
                      {s.trades.map((t, i) => (
                        <tr key={i} className="border-t border-border/20">
                          <td className="pr-2 text-text-muted">{i + 1}</td>
                          <td className={clsx('pr-2 font-bold', t.dir === 'BUY' ? 'text-bull' : 'text-bear')}>{t.dir}</td>
                          <td className="pr-2 text-text-tertiary">{clip(t.t_in)}</td>
                          <td className="pr-2 text-right text-text-secondary">{t.entry.toFixed(3)}</td>
                          <td className="pr-2 text-right text-text-muted">{t.target.toFixed(3)}</td>
                          <td className="pr-2 text-right text-text-muted">{t.stop.toFixed(3)}</td>
                          <td className="pr-2 text-text-tertiary">{clip(t.t_out)}</td>
                          <td className="pr-2 text-right text-text-secondary">{t.exit.toFixed(3)}</td>
                          <td className={clsx('pr-2',
                            t.reason === 'target' ? 'text-bull' : t.reason === 'stop' ? 'text-bear' : 'text-neut')}>
                            {t.reason}
                          </td>
                          <td className={clsx('text-right font-bold',
                            t.pnl > 0 ? 'text-bull' : t.pnl < 0 ? 'text-bear' : 'text-neut')}>
                            {sgn(t.pnl)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </details>
        ))}
      </div>

      {/* Caveats */}
      {data.caveats && data.caveats.length > 0 && (
        <div className="mt-4 rounded border border-border/40 bg-bg-card/20 px-3 py-2">
          <div className="text-[10px] uppercase tracking-wide text-text-muted mb-1">Read before quoting any number</div>
          <ul className="space-y-1 text-[10px] font-mono leading-relaxed text-text-tertiary list-disc pl-4">
            {data.caveats.map((c, i) => <li key={i}>{c}</li>)}
          </ul>
        </div>
      )}
    </Panel>
  );
}
