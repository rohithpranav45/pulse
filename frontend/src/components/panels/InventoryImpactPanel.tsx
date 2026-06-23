import { useMemo, useState } from 'react';
import clsx from 'clsx';
import { Panel } from '@/components/ui/Panel';
import { SkeletonRows } from '@/components/ui/Skeleton';
import { api } from '@/lib/api';
import { usePolling } from '@/lib/hooks';

/**
 * Inventory Impact — command center. Surfaces the four Thursday deliverables
 * explicitly (expectation · spreads · top-3 factors · framework) as a forward
 * call for the UPCOMING EIA crude release, with a consensus calculator (plug in
 * Wednesday's number for the live read) and the regime-gated scenario tree.
 */

type Beta = { beta: number; t: number; r2: number; n: number } | null;
type Scenario = {
  z: number; name: string; surprise_mbbl: number;
  expected_brent_move_pct: number; glut_regime_move_pct: number;
  direction: string; conviction: string;
};
type Call = {
  week_ending?: string; release_date?: string; release_day_name?: string;
  actual_change_mbbl: number; surprise_mbbl: number; surprise_z: number;
  surprise_source: string; surprise_std_mbbl?: number;
  call: 'BULLISH' | 'BEARISH' | 'NEUTRAL'; p_bullish: number; p_bearish: number;
  confidence: 'HIGH' | 'MEDIUM' | 'LOW'; expected_brent_move_pct: number;
  regime: { regime_label: string; inv_vs_5yr_pct: number | null; sensitivity: string; applicable_beta: Beta };
  regime_sensitive: boolean; regime_beta_pct_per_sigma?: number; regime_t?: number;
  quality_of_draw: number | null;
  spreads: { primary: string; ranked: string[] };
  scenario_tree?: Scenario[];
  top_factors: string[];
};
type NextRelease = {
  week_ending: string; release_date: string; release_day_name: string;
  iso_week: number; seasonal_expected_change_mbbl: number | null;
};
type Inventory = {
  available: boolean; error?: string; call?: Call; next_release?: NextRelease;
  n_releases?: number; span?: [string, string];
};

const tone = (c: string) => (c === 'BULLISH' ? 'bull' : c === 'BEARISH' ? 'bear' : 'neut');
const mm = (v: number | null | undefined) =>
  v == null ? '—' : `${v > 0 ? '+' : ''}${(v / 1000).toFixed(1)} MMbbl`;

function DeliverableTag({ n, label }: { n: number; label: string }) {
  return (
    <div className="flex items-center gap-1.5 mb-1.5">
      <span className="flex items-center justify-center w-4 h-4 rounded-full bg-gold/20 text-gold text-[9px] font-bold">{n}</span>
      <span className="text-[10px] font-mono uppercase tracking-[0.15em] text-text-tertiary">{label}</span>
    </div>
  );
}

export function InventoryImpactPanel() {
  const { data, lastUpdated, error } = usePolling<Inventory>(
    () => api.regimeInventory() as Promise<Inventory>, 600_000,
  );
  // consensus calculator (manual override)
  const [actualIn, setActualIn] = useState('');
  const [consensusIn, setConsensusIn] = useState('');
  const [override, setOverride] = useState<Call | null>(null);
  const [busy, setBusy] = useState(false);

  const live = override ?? data?.call;

  async function compute() {
    setBusy(true);
    try {
      const r = await api.regimeInventoryLive(
        actualIn === '' ? undefined : Number(actualIn) * 1000,
        consensusIn === '' ? undefined : Number(consensusIn) * 1000,
      ) as Inventory;
      if (r?.call) setOverride(r.call);
    } finally { setBusy(false); }
  }

  const maxGlut = useMemo(
    () => Math.max(0.1, ...(live?.scenario_tree ?? []).map(s => Math.abs(s.glut_regime_move_pct))),
    [live],
  );

  if (!data && !error) {
    return (
      <Panel title="Inventory Impact · the call" accent="gold" source="inventory_impact" staticMount
        lastSuccess={lastUpdated} fetchError={error}><SkeletonRows rows={8} /></Panel>
    );
  }
  if (!data?.available || !live) {
    return (
      <Panel title="Inventory Impact · the call" accent="gold" source="inventory_impact" staticMount
        lastSuccess={lastUpdated} fetchError={error}>
        <div className="text-[12px] font-mono text-text-tertiary px-3 py-6 text-center">
          {error ? `Inventory endpoint unreachable: ${(error as any)?.message ?? String(error)}`
                 : data?.error ?? 'Run `python -m backend.research.inventory_impact`.'}
        </div>
      </Panel>
    );
  }

  const nr = data.next_release;
  const t = tone(live.call);
  const ab = live.regime.applicable_beta;

  return (
    <Panel
      title="Inventory Impact · EIA crude release — the call"
      subtitle={nr
        ? `next release: week ending ${nr.week_ending} · out ${nr.release_day_name} ${nr.release_date} · ${data.n_releases} releases backtested`
        : `${data.n_releases} releases backtested`}
      accent="gold" source="inventory_impact" staticMount
      lastSuccess={lastUpdated} fetchError={error}
    >
      {/* ── HERO ───────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 mb-4">
        {/* DELIVERABLE 1 — expectation */}
        <div className={clsx('rounded-lg border p-3',
          t === 'bull' && 'border-bull/40 bg-bull/5', t === 'bear' && 'border-bear/40 bg-bear/5', t === 'neut' && 'border-neut/40 bg-neut/5')}>
          <DeliverableTag n={1} label="Expectation" />
          <div className="flex items-end gap-3">
            <span className={clsx('text-3xl font-display font-extrabold leading-none',
              t === 'bull' && 'text-bull', t === 'bear' && 'text-bear', t === 'neut' && 'text-neut')}>
              {live.call}
            </span>
            <span className="text-[11px] font-mono text-text-tertiary mb-0.5">on flat price</span>
          </div>
          <div className="grid grid-cols-3 gap-2 mt-2 text-[10.5px] font-mono">
            <div><div className="text-text-muted">confidence</div><div className="text-text-secondary font-bold">{live.confidence}</div></div>
            <div><div className="text-text-muted">P(bull/bear)</div><div className="text-text-secondary">{live.p_bullish.toFixed(2)} / {live.p_bearish.toFixed(2)}</div></div>
            <div><div className="text-text-muted">exp. move</div><div className={live.regime_sensitive ? 'text-text-secondary' : 'text-text-muted'}>{live.regime_sensitive ? `${live.expected_brent_move_pct > 0 ? '+' : ''}${live.expected_brent_move_pct.toFixed(2)}%` : '≈0'}</div></div>
          </div>
        </div>
        {/* regime gate — the why */}
        <div className={clsx('rounded-lg border p-3 flex flex-col justify-center',
          live.regime.sensitivity === 'LOW' && 'border-bear/30 bg-bear/5',
          live.regime.sensitivity === 'HIGH' && 'border-bull/30 bg-bull/5',
          live.regime.sensitivity === 'MEDIUM' && 'border-border/50')}>
          <div className="text-[10px] font-mono uppercase tracking-[0.15em] text-text-tertiary mb-1">Why · regime gate</div>
          <div className="text-[12px] font-mono text-text-secondary leading-snug">
            <span className="font-bold">{live.regime.regime_label}</span>
            {live.regime.inv_vs_5yr_pct != null && <span className="text-text-tertiary"> ({live.regime.inv_vs_5yr_pct > 0 ? '+' : ''}{live.regime.inv_vs_5yr_pct}% vs 5yr)</span>}
          </div>
          <div className="text-[11px] font-mono mt-1">
            inventory sensitivity{' '}
            <span className={clsx('font-bold',
              live.regime.sensitivity === 'LOW' && 'text-bear', live.regime.sensitivity === 'HIGH' && 'text-bull', live.regime.sensitivity === 'MEDIUM' && 'text-neut')}>
              {live.regime.sensitivity}
            </span>
            {ab && <span className="text-text-muted"> · β {ab.beta.toFixed(2)}%/σ, t={ab.t} ({Math.abs(ab.t) >= 2 ? 'price reacts' : 'print is noise here'})</span>}
          </div>
        </div>
      </div>

      {/* ── DELIVERABLE 2 + 3 ──────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-4">
        <div>
          <DeliverableTag n={2} label="Products / spreads most affected" />
          <ol className="text-[11px] font-mono space-y-1">
            {live.spreads.ranked.slice(0, 4).map((s, i) => (
              <li key={s} className="flex items-center gap-2">
                <span className={clsx('w-1.5 h-1.5 rounded-full', i === 0 ? 'bg-gold' : 'bg-text-muted')} />
                <span className={i === 0 ? 'text-text-primary font-bold' : 'text-text-tertiary'}>{s}</span>
                {i === 0 && <span className="text-[9px] text-gold">primary</span>}
              </li>
            ))}
          </ol>
        </div>
        <div>
          <DeliverableTag n={3} label="Top-3 factors driving the view" />
          <ol className="text-[11px] font-mono text-text-secondary space-y-1 list-decimal list-inside marker:text-gold">
            {live.top_factors.map((f, i) => <li key={i} className="leading-snug">{f}</li>)}
          </ol>
        </div>
      </div>

      {/* ── consensus calculator ───────────────────────────────── */}
      <div className="rounded-lg border border-gold/30 bg-gold/5 p-3 mb-4">
        <div className="text-[10px] font-mono uppercase tracking-[0.15em] text-gold mb-2">
          Live calculator · plug in {nr?.release_day_name ?? 'Wednesday'}'s print
        </div>
        <div className="flex flex-wrap items-end gap-3">
          <label className="text-[10.5px] font-mono text-text-tertiary">
            EIA actual (MMbbl)
            <input value={actualIn} onChange={e => setActualIn(e.target.value)} placeholder="-3.1"
              className="block mt-0.5 w-24 bg-bg-card border border-border rounded px-2 py-1 text-text-primary text-[12px] font-mono" />
          </label>
          <label className="text-[10.5px] font-mono text-text-tertiary">
            Consensus (MMbbl)
            <input value={consensusIn} onChange={e => setConsensusIn(e.target.value)} placeholder="-1.0"
              className="block mt-0.5 w-24 bg-bg-card border border-border rounded px-2 py-1 text-text-primary text-[12px] font-mono" />
          </label>
          <button onClick={compute} disabled={busy}
            className="px-3 py-1.5 rounded bg-gold/20 border border-gold/40 text-gold text-[11px] font-mono font-bold hover:bg-gold/30 disabled:opacity-50">
            {busy ? 'computing…' : 'Compute call'}
          </button>
          {override && (
            <button onClick={() => setOverride(null)}
              className="px-2 py-1.5 rounded border border-border text-text-tertiary text-[10px] font-mono hover:text-text-secondary">
              reset
            </button>
          )}
          <span className="text-[10px] font-mono text-text-muted">
            surprise = actual − consensus · σ ≈ {((live?.surprise_std_mbbl ?? data.call?.surprise_std_mbbl ?? 0) / 1000).toFixed(1)} MMbbl
            {override && <span className="text-gold"> · showing computed call (surprise {mm(override.surprise_mbbl)}, {override.surprise_z?.toFixed(1)}σ)</span>}
          </span>
        </div>
      </div>

      {/* ── scenario tree ──────────────────────────────────────── */}
      {live.scenario_tree && (
        <div>
          <div className="text-[10px] font-mono uppercase tracking-[0.15em] text-text-tertiary mb-2">
            Scenario tree · expected Brent release-day move by surprise size
          </div>
          <div className="space-y-1.5">
            {live.scenario_tree.map(s => {
              const stone = s.direction === 'bullish' ? 'bull' : s.direction === 'bearish' ? 'bear' : 'neut';
              return (
                <div key={s.z} className="grid grid-cols-[1fr_92px_92px] items-center gap-2 text-[10.5px] font-mono">
                  <div className="flex items-center gap-2 min-w-0">
                    <span className={clsx('tabular font-bold w-8',
                      stone === 'bull' && 'text-bull', stone === 'bear' && 'text-bear', stone === 'neut' && 'text-text-muted')}>
                      {s.z > 0 ? '+' : ''}{s.z}σ
                    </span>
                    <span className="text-text-tertiary truncate">{s.name}</span>
                  </div>
                  {/* today */}
                  <div className="text-right">
                    <span className="text-text-muted text-[9px]">today </span>
                    <span className={live.regime_sensitive ? 'text-text-secondary' : 'text-text-muted'}>
                      {s.expected_brent_move_pct > 0 ? '+' : ''}{s.expected_brent_move_pct.toFixed(2)}%
                    </span>
                  </div>
                  {/* glut contrast */}
                  <div className="relative h-4 bg-bg-card/40 rounded overflow-hidden border border-border/30" title={`In a glut regime: ${s.glut_regime_move_pct > 0 ? '+' : ''}${s.glut_regime_move_pct}%`}>
                    <div className="absolute top-0 bottom-0 bg-text-muted/40" style={{ left: '50%', width: '1px' }} />
                    <div className={clsx('absolute top-0 bottom-0', s.glut_regime_move_pct >= 0 ? 'bg-bull/50' : 'bg-bear/50')}
                      style={{
                        left: s.glut_regime_move_pct >= 0 ? '50%' : `${50 - (Math.abs(s.glut_regime_move_pct) / maxGlut) * 48}%`,
                        width: `${(Math.abs(s.glut_regime_move_pct) / maxGlut) * 48}%`,
                      }} />
                    <span className="absolute inset-0 flex items-center justify-center text-[9px] text-text-secondary">
                      glut {s.glut_regime_move_pct > 0 ? '+' : ''}{s.glut_regime_move_pct}%
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
          <div className="mt-2 text-[10px] font-mono text-text-muted leading-relaxed">
            The same surprise barely moves flat price in <span className="text-bear">today's tight regime</span> (left number)
            but moves it ~1–2% in a <span className="text-bull">glut/contango regime</span> (bar) — that conditionality is the
            framework's core. Use the calculator above once {nr?.release_day_name ?? "Wed"}'s consensus + actual print.
          </div>
        </div>
      )}
    </Panel>
  );
}
