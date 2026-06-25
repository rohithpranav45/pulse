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
  api_nowcast_mbbl?: number | null; blended_nowcast_mbbl?: number | null;
  api_nowcast?: { api_release_date?: string } | null; nowcast_note?: string;
};
type Inventory = {
  available: boolean; error?: string; call?: Call; next_release?: NextRelease;
  n_releases?: number; span?: [string, string];
};

const tone = (c: string) => (c === 'BULLISH' ? 'bull' : c === 'BEARISH' ? 'bear' : 'neut');
const mm = (v: number | null | undefined) =>
  v == null ? '—' : `${v > 0 ? '+' : ''}${(v / 1000).toFixed(1)} MMbbl`;

const SPREAD_LABEL: Record<string, string> = {
  wti_flat: 'WTI flat', brent_flat: 'Brent flat',
  wti_brent: 'WTI–Brent', wti_m1_m2: 'WTI M1–M2',
};

// WTI vs Brent reaction + per-spread impact. Crude inventories are US data → WTI
// is the affected benchmark (Brent barely reacts); the spread impacts are the
// event-study betas × today's surprise.
function PriceReaction({ live }: { live: any }) {
  const pr = live?.price_reaction;
  // flats are shown (regime-gated, correct sign) in the WTI/Brent cards below; the
  // spread-impact table is for the actual spreads only.
  const impacts: any[] = (live?.spread_impacts ?? []).filter((s: any) => !String(s.instrument).endsWith('_flat'));
  if (!pr?.wti && !impacts.length) return null;
  // the DIRECTIONAL point estimate (always shown); confidence comes from the t-stat
  const pointTxt = (p: any) =>
    !p || p.point_move_pct == null ? '—' : `${p.point_move_pct > 0 ? '+' : ''}${p.point_move_pct.toFixed(2)}%`;
  const moveTone = (p: any) =>
    !p ? 'text-text-muted' : (p.point_move_pct ?? 0) > 0 ? 'text-bull' : (p.point_move_pct ?? 0) < 0 ? 'text-bear' : 'text-text-muted';
  return (
    <div className="rounded-lg border border-border/50 bg-bg-card/30 p-3 mb-4">
      <div className="text-[10px] font-mono uppercase tracking-[0.15em] text-text-tertiary mb-2">
        Price reaction to the surprise · <span className="text-gold">WTI</span> is the affected benchmark (US crude) · Brent barely reacts
      </div>
      {pr?.wti && (
        <div className="grid grid-cols-2 gap-3 mb-3">
          {[['WTI', pr.wti], ['Brent', pr.brent]].map(([lab, p]: any) => (
            <div key={lab} className={clsx('rounded border px-2.5 py-1.5',
              lab === 'WTI' ? 'border-gold/40 bg-gold/5' : 'border-border/40')}>
              <div className="flex items-baseline justify-between">
                <span className="text-[12px] font-mono font-bold">{lab}</span>
                <span className={clsx('text-[14px] font-mono font-bold tabular', moveTone(p))}>{pointTxt(p)}</span>
              </div>
              <div className="flex items-center justify-between mt-0.5">
                <span className={clsx('text-[8.5px] font-mono uppercase tracking-wider px-1 rounded',
                  p?.sensitive ? 'text-bull bg-bull/10' : 'text-text-muted bg-bg-card/60')}>
                  {p?.sensitive ? 'directional signal' : 'low conf · not a catalyst'}
                </span>
                <span className="text-[8.5px] font-mono text-text-muted">
                  β{Number(p?.beta_pct_per_sigma ?? 0).toFixed(3)}/σ t={p?.t}{p?.day_range_pct != null ? ` · day ±${p.day_range_pct}%` : ''}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
      {impacts.length > 0 && (
        <>
          <div className="text-[9.5px] font-mono uppercase tracking-wide text-text-muted mb-1">
            Spread impact · expected move per the current surprise (z={live.surprise_z})
          </div>
          <div className="space-y-0.5">
            {impacts.map((s) => (
              <div key={s.instrument} className="grid grid-cols-[1fr_auto_64px] gap-2 items-center text-[10.5px] font-mono tabular">
                <span className={clsx(s.instrument === 'brent_flat' ? 'text-text-muted' : 'text-text-secondary')}>
                  {SPREAD_LABEL[s.instrument] ?? s.instrument}
                </span>
                <span className="text-[9px] text-text-muted">β {Number(s.beta_per_sigma).toFixed(4)}/σ · t={s.t}</span>
                <span className={clsx('text-right font-bold',
                  s.expected_move > 0 ? 'text-bull' : s.expected_move < 0 ? 'text-bear' : 'text-text-muted')}>
                  {s.expected_move >= 0 ? '+' : ''}{Number(s.expected_move).toFixed(3)}
                </span>
              </div>
            ))}
          </div>
        </>
      )}
      <div className="mt-1.5 text-[9.5px] font-mono text-text-muted leading-snug">
        These are the directional point estimates from the <span className="text-text-secondary">surprise alone</span> — not a
        forecast of the total move. <span className="text-text-muted">"low conf"</span> means the inventory print isn't a reliable
        directional catalyst in this regime (t&lt;2): price still moves ~<span className="text-text-secondary">±{pr?.wti?.day_range_pct ?? pr?.brent?.day_range_pct ?? '0.8'}%</span> on
        the day, just driven by other factors (geopolitics, macro), not the number. WTI reacts ~17× Brent (US data).
      </div>
    </div>
  );
}

function DeliverableTag({ n, label }: { n: number; label: string }) {
  return (
    <div className="flex items-center gap-1.5 mb-1.5">
      <span className="flex items-center justify-center w-4 h-4 rounded-full bg-gold/20 text-gold text-[9px] font-bold">{n}</span>
      <span className="text-[10px] font-mono uppercase tracking-[0.15em] text-text-tertiary">{label}</span>
    </div>
  );
}

export function InventoryImpactPanel({ series = 'crude_ex_spr' }: { series?: string }) {
  const { data, lastUpdated, error } = usePolling<Inventory>(
    () => api.regimeInventory(series) as Promise<Inventory>, 600_000, [series],
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
        series,
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
      title={`Inventory Impact · EIA ${(data as any)?.series_label ?? 'crude'} release — the call`}
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
            {(() => {
              const wti = (live as any).price_reaction?.wti;
              const mv = wti ? wti.point_move_pct : live.expected_brent_move_pct;
              const sens = wti ? wti.sensitive : live.regime_sensitive;
              return (
                <div><div className="text-text-muted">est. {wti ? 'WTI' : 'Brent'}</div>
                  <div className={clsx(sens ? 'text-text-secondary' : 'text-text-muted',
                    (mv ?? 0) > 0 ? 'text-bull' : (mv ?? 0) < 0 ? 'text-bear' : '')}
                    title={sens ? 'directional signal (significant)' : 'point estimate — low confidence, not a reliable catalyst'}>
                    {mv == null ? '—' : `${mv > 0 ? '+' : ''}${mv.toFixed(2)}%`}{!sens && '*'}
                  </div></div>
              );
            })()}
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

      {/* ── PRICE REACTION · WTI vs Brent + per-spread impact ──────── */}
      <PriceReaction live={live as any} />

      {/* ── API leading-indicator nowcast (pre-release) ──────────── */}
      {nr?.api_nowcast_mbbl != null && (
        <div className="rounded-lg border border-blue/30 bg-blue/[0.06] p-3 mb-4">
          <div className="text-[10px] font-mono uppercase tracking-[0.15em] text-blue mb-1.5">
            Pre-release nowcast · API crude leading indicator (Tue)
          </div>
          <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1 text-[11px] font-mono">
            <span className="text-text-tertiary">API actual{nr.api_nowcast?.api_release_date ? ` (${nr.api_nowcast.api_release_date})` : ''}:{' '}
              <span className="text-text-primary font-bold">{mm(nr.api_nowcast_mbbl)}</span></span>
            <span className="text-text-tertiary">seasonal: <span className="text-text-secondary">{mm(nr.seasonal_expected_change_mbbl)}</span></span>
            <span className="text-text-tertiary">blended nowcast: <span className="text-blue font-bold">{mm(nr.blended_nowcast_mbbl)}</span></span>
          </div>
          <div className="mt-1.5 text-[9.5px] font-mono text-text-muted leading-snug">
            {nr.nowcast_note ?? 'API crude (Tue) front-runs the EIA by ~1 day (corr 0.77 w/ the EIA actual, 2019+). A pre-release input — not the EIA number; the real consensus arrives Wednesday.'}
          </div>
        </div>
      )}

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
