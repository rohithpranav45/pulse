import { useCallback, useState } from 'react';
import clsx from 'clsx';
import { Panel } from '@/components/ui/Panel';
import { SkeletonRows } from '@/components/ui/Skeleton';
import { api } from '@/lib/api';
import { usePolling } from '@/lib/hooks';
import { Zap } from 'lucide-react';

/**
 * Live auto-trade desk monitor (REGIME tab) — Phase 3/4.
 *
 * Surfaces what the desk WOULD do right now (dry-run preview of
 * GET /api/regime/autodesk): the gated/decorrelated selected book, the two
 * entry gates (market hours + shock circuit-breaker), and the open/flip/hold
 * plan against the paper book. The "Run desk now" button forces a real tick
 * (POST /api/regime/autodesk/run) for demos / a manual desk push.
 */

type Stress = {
  p_stress?: number;
  onset?: number;
  label?: string;
  as_of?: string;
  source?: 'live_feed' | 'daily_settle';
  live?: boolean;
  live_fallback_reason?: string | null;
};
type Planned = { spread: string; direction?: string; id?: number | null };
type Flip = { spread: string; from: string; to: string; reopened: boolean };
type Skip = { spread: string; direction?: string; reason: string };
type Desk = {
  ran: boolean;
  reason?: string;
  error?: string;
  dry_run?: boolean;
  market_open?: boolean;
  market_reason?: string;
  breaker_active?: boolean;
  entries_allowed?: boolean;
  stress?: Stress;
  feed_as_of?: string;
  regime?: string;
  rho_max?: number;
  selected?: string[];
  opened?: Planned[];
  flipped?: Flip[];
  left_running?: Planned[];
  skipped?: Skip[];
  actions?: string[];
  n_held_auto?: number;
};

function Gate({ ok, label, detail }: { ok: boolean; label: string; detail: string }) {
  return (
    <div className={clsx(
      'flex flex-col gap-0.5 rounded-lg border px-3 py-2 min-w-[170px] flex-1',
      ok ? 'border-bull/40 bg-bull/5' : 'border-bear/40 bg-bear/5',
    )}>
      <div className="flex items-center gap-2">
        <span className={clsx('text-[10px] font-mono font-bold uppercase tracking-wide',
          ok ? 'text-bull' : 'text-bear')}>
          {ok ? '○ OK' : '● BLOCK'}
        </span>
        <span className="text-[10px] uppercase tracking-widest text-text-muted">{label}</span>
      </div>
      <div className="text-[11px] font-mono text-text-tertiary leading-snug">{detail}</div>
    </div>
  );
}

const REASON_COPY: Record<string, string> = {
  weekend: 'weekend — market closed',
  stale_feed: 'feed bar stale (>90 min) — no live market',
  no_feed_ts: 'no feed timestamp',
  open: 'weekday · fresh feed bar',
};

export function AutoDeskPanel() {
  const { data, lastUpdated, error, refetch } = usePolling<Desk>(
    () => api.regimeAutodesk() as Promise<Desk>,
    60_000, // 1 min — the desk plan tracks the 15-min bar cadence loosely
  );
  const [busy, setBusy] = useState(false);
  const [flash, setFlash] = useState<string | null>(null);

  const runNow = useCallback(async () => {
    setBusy(true); setFlash(null);
    try {
      const out = (await api.regimeAutodeskRun()) as Desk;
      const o = out.opened?.length ?? 0;
      const f = out.flipped?.length ?? 0;
      setFlash(out.ran ? `✓ opened ${o} · flipped ${f}` : `✕ ${out.reason ?? 'did not run'}`);
      refetch();
    } catch (e: any) {
      setFlash(`✕ ${e?.message ?? String(e)}`);
    } finally {
      setBusy(false);
      setTimeout(() => setFlash(null), 5000);
    }
  }, [refetch]);

  const runBtn = (
    <div className="flex items-center gap-2">
      {flash && (
        <span className={clsx('text-[11px] font-mono', flash.startsWith('✓') ? 'text-bull' : 'text-bear')}>
          {flash}
        </span>
      )}
      <button
        onClick={runNow}
        disabled={busy}
        className={clsx(
          'flex items-center gap-1.5 px-3 py-1.5 rounded-md font-mono uppercase tracking-widest text-[10px] font-bold transition-colors',
          busy ? 'bg-gold/40 text-bg cursor-wait' : 'bg-gold text-bg hover:bg-gold-bright shadow-sm',
        )}
        title="Force one real auto-desk tick (opens/flips paper trades from the decorrelated book)"
      >
        <Zap className={clsx('w-3 h-3', busy && 'animate-pulse')} />
        {busy ? 'running…' : 'Run desk now'}
      </button>
    </div>
  );

  if (!data && !error) {
    return (
      <Panel title="Auto-Trade Desk · live plan" accent="blue" source="auto_desk"
             staticMount lastSuccess={lastUpdated} fetchError={error}>
        <SkeletonRows rows={4} />
      </Panel>
    );
  }
  if (!data?.ran) {
    return (
      <Panel title="Auto-Trade Desk · live plan" accent="blue" source="auto_desk"
             staticMount lastSuccess={lastUpdated} fetchError={error} right={runBtn}>
        <div className="text-[12px] font-mono text-text-tertiary px-3 py-6 text-center">
          {error ? `Auto-desk endpoint unreachable: ${(error as any)?.message ?? String(error)}`
                 : data?.reason === 'feed_unavailable'
                   ? `Live feed unavailable: ${data?.error ?? '—'}`
                   : data?.reason === 'disabled'
                     ? 'Auto-desk disabled (PULSE_AUTO_DESK_DISABLED=1).'
                     : `Desk did not run: ${data?.reason ?? 'unknown'}`}
        </div>
      </Panel>
    );
  }

  const d = data;
  const st = d.stress ?? {};
  const marketDetail = REASON_COPY[d.market_reason ?? ''] ?? d.market_reason ?? '—';
  const breakerDetail = d.breaker_active
    ? `shock onset — P(stress) ${((st.p_stress ?? 0) * 100).toFixed(0)}% (${st.label ?? '—'})`
    : `no onset — P(stress) ${((st.p_stress ?? 0) * 100).toFixed(0)}% (${st.label ?? '—'})`;

  const selected = d.selected ?? [];

  return (
    <Panel
      title="Auto-Trade Desk · live plan"
      subtitle={`gated/decorrelated book · ρ_max ${d.rho_max ?? '—'} · feed ${d.feed_as_of ?? '—'}`}
      accent="blue"
      source="auto_desk"
      staticMount
      lastSuccess={lastUpdated}
      fetchError={error}
      right={runBtn}
    >
      {/* Entry gates */}
      <div className="flex flex-wrap gap-2">
        <Gate ok={!!d.market_open} label="Market hours (5d/wk)" detail={marketDetail} />
        <Gate ok={!d.breaker_active} label="Shock circuit-breaker" detail={breakerDetail} />
        <div className={clsx(
          'flex flex-col justify-center rounded-lg border px-3 py-2 min-w-[150px]',
          d.entries_allowed ? 'border-bull/50 bg-bull/10' : 'border-neut/40 bg-neut/5',
        )}>
          <div className="text-[10px] uppercase tracking-widest text-text-muted">New entries</div>
          <div className={clsx('text-[13px] font-mono font-bold',
            d.entries_allowed ? 'text-bull' : 'text-neut')}>
            {d.entries_allowed ? 'ALLOWED' : 'PAUSED'}
          </div>
          <div className="text-[10px] font-mono text-text-muted">
            {d.n_held_auto ?? 0} desk position{(d.n_held_auto ?? 0) === 1 ? '' : 's'} open
          </div>
        </div>
      </div>

      {/* Stress-read provenance — honest about live vs settle */}
      <div className="mt-2 text-[10px] font-mono text-text-muted">
        stress read:{' '}
        <span className={st.source === 'live_feed' ? 'text-bull' : 'text-neut'}>
          {st.source === 'live_feed' ? 'LIVE feed' : `daily settle (${st.as_of ?? '—'})`}
        </span>
        {st.source !== 'live_feed' && st.live_fallback_reason && (
          <span className="text-text-muted"> · {st.live_fallback_reason}</span>
        )}
      </div>

      {/* Selected book */}
      <div className="mt-4">
        <div className="text-[10px] uppercase tracking-widest text-text-muted mb-1.5">
          Selected book · {selected.length} trade{selected.length === 1 ? '' : 's'} (regime {d.regime ?? '—'})
        </div>
        {selected.length === 0 ? (
          <div className="text-[11px] font-mono text-text-tertiary px-2 py-3">
            No actionable, decorrelated trade right now — nothing crosses the z-gate after live re-scoring.
          </div>
        ) : (
          <div className="flex flex-wrap gap-1.5">
            {selected.map(sp => (
              <span key={sp} className="rounded border border-accent-blue/30 bg-accent-blue/5 px-2 py-1 text-[11px] font-mono text-text-secondary">
                {sp}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Plan: opens / flips / left-running / skipped */}
      {(d.actions?.length || d.flipped?.length || d.left_running?.length || d.skipped?.length) ? (
        <div className="mt-4 space-y-2 text-[11px] font-mono">
          {!!d.actions?.length && (
            <div>
              <span className="text-[10px] uppercase tracking-widest text-bull">Would open</span>
              <ul className="mt-1 space-y-0.5 text-text-tertiary">
                {d.actions.map((a, i) => <li key={i} className="pl-2">• {a}</li>)}
              </ul>
            </div>
          )}
          {!!d.flipped?.length && (
            <div>
              <span className="text-[10px] uppercase tracking-widest text-neut">Flips</span>
              <ul className="mt-1 space-y-0.5 text-text-tertiary">
                {d.flipped.map((f, i) => (
                  <li key={i} className="pl-2">• {f.spread}: {f.from} → {f.to}{f.reopened ? '' : ' (entries paused — closed only)'}</li>
                ))}
              </ul>
            </div>
          )}
          {!!d.left_running?.length && (
            <div>
              <span className="text-[10px] uppercase tracking-widest text-text-muted">Running under stops (de-selected)</span>
              <ul className="mt-1 space-y-0.5 text-text-tertiary">
                {d.left_running.map((p, i) => <li key={i} className="pl-2">• {p.spread} {p.direction}</li>)}
              </ul>
            </div>
          )}
          {!!d.skipped?.length && (
            <div>
              <span className="text-[10px] uppercase tracking-widest text-bear">Skipped</span>
              <ul className="mt-1 space-y-0.5 text-text-tertiary">
                {d.skipped.map((s, i) => <li key={i} className="pl-2">• {s.spread} {s.direction} — {s.reason}</li>)}
              </ul>
            </div>
          )}
        </div>
      ) : (
        <div className="mt-4 text-[11px] font-mono text-text-muted px-2">
          Desk in sync — no opens, flips or skips this tick.
        </div>
      )}
    </Panel>
  );
}
