import { useCallback, useState } from 'react';
import clsx from 'clsx';
import { Panel } from '@/components/ui/Panel';
import { Chip } from '@/components/ui/Chip';
import { SkeletonRows } from '@/components/ui/Skeleton';
import { Radio, Play, ArrowUpRight, ArrowDownRight } from 'lucide-react';
import { api } from '@/lib/api';
import { usePolling } from '@/lib/hooks';

/**
 * Phase 3.1 — live signal log.
 *
 * Renders every opportunity the live engine generated against the current
 * market (from the lightstreamer 15-min feed), with the mentor's requested
 * columns: timestamp, regime, instrument, rationale, confidence, and
 * subsequent performance (live MTM move + close reason). Reads
 * /api/regime/signals; the scheduler logs daily + every 15 min, and the
 * GENERATE button fires one tick on demand for demos.
 */

interface SignalRow {
  id: number;
  signal_at: string;
  feed_as_of: string | null;
  cadence: string;
  instrument: string;
  label: string | null;
  regime: string | null;
  regime_mode: string | null;
  direction: 'BUY' | 'SELL';
  source: string | null;
  winner_model: string | null;
  confidence: number | null;
  entry: number | null;
  fair_value: number | null;
  z_score: number | null;
  target: number | null;
  stop: number | null;
  rationale: string | null;
  status: 'OPEN' | 'CLOSED';
  mtm_move: number | null;
  close_reason: string | null;
}

interface SignalsData {
  available: boolean;
  signals: SignalRow[];
  n: number;
  n_open: number;
  error?: string;
}

function fmtNum(v: number | null | undefined, digits = 3): string {
  if (v == null || !Number.isFinite(v)) return '—';
  return v.toFixed(digits);
}

function fmtTime(iso: string): string {
  // "2026-06-15T06:34:15+00:00" → "06-15 06:34"
  const m = iso?.match(/(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/);
  return m ? `${m[2]}-${m[3]} ${m[4]}:${m[5]}` : iso;
}

function closeReasonTone(reason: string | null): 'bull' | 'bear' | 'neut' | 'muted' {
  if (reason === 'target') return 'bull';
  if (reason === 'stop')   return 'bear';
  if (reason === 'time_stop') return 'neut';
  return 'muted';
}

function PerfCell({ s }: { s: SignalRow }) {
  // mtm_move is signed so favourable is +. Colour by sign.
  const move = s.mtm_move;
  const tone = move == null ? 'muted' : move > 0 ? 'bull' : move < 0 ? 'bear' : 'muted';
  const moveColor = tone === 'bull' ? 'text-bull' : tone === 'bear' ? 'text-bear' : 'text-text-tertiary';
  return (
    <div className="flex items-center gap-2 justify-end">
      <span className={clsx('tabular font-mono text-[11px]', moveColor)}>
        {move == null ? '—' : `${move > 0 ? '+' : ''}${move.toFixed(3)}`}
      </span>
      {s.status === 'CLOSED' ? (
        <Chip tone={closeReasonTone(s.close_reason) as any}>{(s.close_reason || 'closed').replace('_', ' ')}</Chip>
      ) : (
        <Chip tone="muted">open</Chip>
      )}
    </div>
  );
}

export function SignalLogPanel() {
  const [status, setStatus] = useState<'all' | 'open' | 'closed'>('all');
  const { data, loading, error, refetch } = usePolling<SignalsData>(
    () => api.regimeSignals(status, 200),
    30_000,
    [status],
  );
  const [acting, setActing] = useState(false);
  const [actMsg, setActMsg] = useState<string | null>(null);

  const onGenerate = useCallback(async () => {
    setActing(true); setActMsg(null);
    try {
      const out: any = await api.regimeSignalsGenerate({ cadence: 'daily' });
      if (out?.available === false) {
        setActMsg(`feed unavailable: ${out?.error ?? 'unknown'}`);
      } else {
        setActMsg(`logged ${out?.logged ?? 0} new · regime ${out?.regime ?? '—'} · as of ${out?.feed_as_of ?? '—'}`);
      }
      await refetch();
    } catch (e: any) {
      setActMsg(`generate failed: ${e?.message || e}`);
    } finally {
      setActing(false);
    }
  }, [refetch]);

  const signals = data?.signals ?? [];

  const headerRight = (
    <div className="flex items-center gap-2">
      <div className="flex items-center gap-0.5 rounded-md border border-border p-0.5">
        {(['all', 'open', 'closed'] as const).map(s => (
          <button
            key={s}
            onClick={() => setStatus(s)}
            className={clsx(
              'text-[9px] font-mono uppercase tracking-wider px-2 py-0.5 rounded',
              status === s ? 'bg-gold/15 text-gold' : 'text-text-tertiary hover:text-text-secondary',
            )}
          >
            {s}
          </button>
        ))}
      </div>
      <button
        onClick={onGenerate}
        disabled={acting}
        className="inline-flex items-center gap-1 text-[10px] font-mono tracking-wider px-2 py-1 rounded-md border border-gold/40 text-gold hover:bg-gold/10 disabled:opacity-50"
        title="Fire one live signal-generation step now (idempotent; the scheduler also runs daily + every 15 min)"
      >
        <Play size={11} /> GENERATE
      </button>
    </div>
  );

  return (
    <Panel
      title="Live Signal Log"
      subtitle="Phase 3.1 · what the framework would trade in the current market"
      accent="gold"
      right={headerRight}
    >
      {loading && !data && <SkeletonRows rows={5} />}
      {error && <div className="text-xs text-bear">error: {error.message}</div>}

      {data && (
        <>
          {/* summary strip */}
          <div className="flex items-center justify-between gap-3 mb-3 p-2 rounded-md border border-border bg-bg-card">
            <div className="flex items-center gap-2">
              <Radio size={14} className="text-gold" />
              <span className="text-[11px] font-mono text-text-secondary">
                {data.n ?? signals.length} signal(s) · {data.n_open ?? 0} open
              </span>
              {signals[0]?.feed_as_of && (
                <span className="text-[10px] text-text-tertiary font-mono">
                  latest feed @ {signals[0].feed_as_of}
                </span>
              )}
            </div>
            {actMsg && <div className="text-[10px] text-text-tertiary truncate max-w-[55%]">{actMsg}</div>}
          </div>

          {signals.length === 0 ? (
            <div className="py-8 text-center text-xs text-text-tertiary">
              No signals yet. The engine logs opportunities each tick once the live feed is streaming —
              or hit <span className="text-gold">GENERATE</span> to run one now.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-[11px] font-mono">
                <thead>
                  <tr className="text-[9px] uppercase tracking-wider text-text-tertiary border-b border-border">
                    <th className="text-left font-medium py-1.5 pr-2">Time</th>
                    <th className="text-left font-medium py-1.5 pr-2">Instrument</th>
                    <th className="text-left font-medium py-1.5 pr-2">Dir</th>
                    <th className="text-left font-medium py-1.5 pr-2">Regime</th>
                    <th className="text-right font-medium py-1.5 pr-2">Conf</th>
                    <th className="text-right font-medium py-1.5 pr-2">Entry→Fair (z)</th>
                    <th className="text-right font-medium py-1.5 pl-2">Subsequent perf</th>
                  </tr>
                </thead>
                <tbody>
                  {signals.map(s => (
                    <tr key={s.id} className="border-b border-border/40 align-top hover:bg-bg-card/50">
                      <td className="py-1.5 pr-2 text-text-tertiary whitespace-nowrap">{fmtTime(s.signal_at)}</td>
                      <td className="py-1.5 pr-2 max-w-[220px]">
                        <div className="text-text-primary">{s.label || s.instrument}</div>
                        {s.rationale && (
                          <div className="text-[9.5px] text-text-muted leading-tight mt-0.5 truncate" title={s.rationale}>
                            {s.rationale}
                          </div>
                        )}
                      </td>
                      <td className="py-1.5 pr-2">
                        <Chip
                          tone={s.direction === 'BUY' ? 'bull' : 'bear'}
                          icon={s.direction === 'BUY' ? <ArrowUpRight size={10} /> : <ArrowDownRight size={10} />}
                        >
                          {s.direction === 'BUY' ? 'LONG' : 'SHORT'}
                        </Chip>
                      </td>
                      <td className="py-1.5 pr-2 text-text-secondary whitespace-nowrap">{s.regime}</td>
                      <td className="py-1.5 pr-2 text-right text-text-secondary tabular">
                        {s.confidence == null ? '—' : `${(s.confidence * 100).toFixed(0)}%`}
                      </td>
                      <td className="py-1.5 pr-2 text-right text-text-secondary tabular whitespace-nowrap">
                        {fmtNum(s.entry, 3)}→{fmtNum(s.fair_value, 3)}
                        <span className="text-text-muted"> ({s.z_score == null ? '—' : `${s.z_score > 0 ? '+' : ''}${s.z_score.toFixed(2)}`})</span>
                      </td>
                      <td className="py-1.5 pl-2"><PerfCell s={s} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <div className="mt-3 text-[9.5px] text-text-muted leading-relaxed">
            Confidence = |z|/3 × model R² × √(n_train/100). Subsequent performance is the live spread
            move since the signal (favourable = +), resolved on the tuned exit rule (TP halfway to fair ·
            SL 2.5σ · 30-trading-day time-stop). Read-only — this is analysis tracking, not order entry.
          </div>
        </>
      )}
    </Panel>
  );
}
