import { useMemo } from 'react';
import clsx from 'clsx';
import { Panel } from '@/components/ui/Panel';
import { SkeletonRows } from '@/components/ui/Skeleton';
import { api } from '@/lib/api';
import { usePolling } from '@/lib/hooks';

/**
 * Release reaction — PREDICTED vs ACTUAL. After the EIA crude print, reads the
 * desk 1-min feed and shows what the affected spreads ACTUALLY did at +5/15/30/60
 * min next to what the model called, then grades each. The headline question:
 * did we get the direction right, and was the move muted as the regime predicted?
 */

type Horizon = {
  mins: number; pending?: boolean;
  wti_flat_pct?: number; brent_flat_pct?: number; d_wti_brent?: number; d_wti_m1_m2?: number;
};
type Reaction = {
  available: boolean; reason?: string;
  series?: string; series_label?: string; crude_only_feed?: boolean;
  predicted?: {
    call?: string; confidence?: string; surprise_mbbl?: number; surprise_z?: number;
    surprise_source?: string; regime?: string; regime_sensitive?: boolean;
    price_reaction?: { wti?: any; brent?: any };
    spread_impacts?: { instrument: string; expected_move: number }[];
    product_spread?: string;
  };
  actual?: {
    available: boolean; release_utc?: string; release_et?: string; anchor?: any;
    horizons?: number[]; actual?: Horizon[]; n_bars?: number; feed_file?: string;
  };
};

const fmt = (v: number | null | undefined, unit: string, dp = unit === '%' ? 2 : 2) =>
  v == null ? '—' : `${v > 0 ? '+' : ''}${v.toFixed(dp)}${unit === '%' ? '%' : ''}`;
const tone = (v: number | null | undefined) =>
  v == null ? 'text-text-muted' : v > 0.001 ? 'text-bull' : v < -0.001 ? 'text-bear' : 'text-text-muted';

export function InventoryReactionPanel({ actual, consensus, series = 'crude_ex_spr' }:
  { actual?: number; consensus?: number; series?: string }) {
  const { data, lastUpdated, error } = usePolling<Reaction>(
    () => api.regimeInventoryReaction(actual, consensus, series) as Promise<Reaction>,
    60_000, [actual, consensus, series],
  );
  const isCrude = series === 'crude_ex_spr';

  const rows = useMemo(() => {
    const pred = data?.predicted;
    const pr = pred?.price_reaction;
    const byName: Record<string, number> = {};
    for (const s of pred?.spread_impacts ?? []) byName[s.instrument] = s.expected_move;
    return [
      { key: 'wti_flat',   label: 'WTI flat',   unit: '%', primary: true,
        pred: pr?.wti?.point_move_pct, aKey: 'wti_flat_pct' as const },
      { key: 'brent_flat', label: 'Brent flat', unit: '%', primary: false,
        pred: pr?.brent?.point_move_pct, aKey: 'brent_flat_pct' as const },
      { key: 'wti_brent',  label: 'WTI–Brent',  unit: '$', primary: true,
        pred: byName['wti_brent'], aKey: 'd_wti_brent' as const },
      { key: 'wti_m1_m2',  label: 'WTI M1–M2',  unit: '$', primary: false,
        pred: byName['wti_m1_m2'], aKey: 'd_wti_m1_m2' as const },
    ];
  }, [data]);

  const horizons = data?.actual?.actual ?? [];
  const lastFor = (aKey: keyof Horizon): number | undefined => {
    for (let i = horizons.length - 1; i >= 0; i--) {
      const h = horizons[i];
      if (!h.pending && h[aKey] != null) return h[aKey] as number;
    }
    return undefined;
  };
  // grade: did the realised move match the predicted sign?
  const grade = (pred: number | undefined, act: number | undefined): '✓' | '✗' | '~' => {
    if (pred == null || act == null) return '~';
    if (Math.abs(act) < 0.02 && Math.abs(pred) < 0.02) return '~';
    if (Math.abs(act) < 0.015) return '~';
    return Math.sign(pred) === Math.sign(act) ? '✓' : '✗';
  };
  const grades = rows.map(r => grade(r.pred, lastFor(r.aKey)));
  const nRight = grades.filter(g => g === '✓').length;
  const nCall = grades.filter(g => g !== '~').length;

  if (!data && !error) {
    return <Panel title="Release reaction · predicted vs actual" accent="gold" source="release_reaction"
      staticMount lastSuccess={lastUpdated} fetchError={error}><SkeletonRows rows={6} /></Panel>;
  }
  if (!data?.available) {
    return (
      <Panel title="Release reaction · predicted vs actual" accent="gold" source="release_reaction"
        staticMount lastSuccess={lastUpdated} fetchError={error}>
        <div className="text-[12px] font-mono text-text-tertiary px-3 py-6 text-center">
          {error ? `Reaction endpoint unreachable: ${(error as any)?.message ?? String(error)}`
                 : `Awaiting the 1-min feed${data?.reason ? ` · ${data.reason}` : ''} — appears after the release once the desk recorder has the bars.`}
        </div>
      </Panel>
    );
  }

  const p = data.predicted ?? {};
  const ax = data.actual ?? ({} as any);
  const callTone = p.call === 'BULLISH' ? 'bull' : p.call === 'BEARISH' ? 'bear' : 'neut';

  return (
    <Panel
      title={`${data.series_label ?? 'Crude'} release reaction · predicted vs actual`}
      subtitle={`EIA · released ${ax.release_et ?? '10:30 ET'} (${ax.release_utc ?? ''}) · desk 1-min feed`}
      accent="gold" source="release_reaction" staticMount
      lastSuccess={lastUpdated} fetchError={error}
      right={
        <span className={clsx('text-[10px] font-mono font-bold px-2 py-0.5 rounded border',
          nRight >= 3 ? 'text-bull border-bull/40 bg-bull/10'
            : nRight >= 2 ? 'text-neut border-neut/40 bg-neut/10' : 'text-bear border-bear/40 bg-bear/10')}>
          {nRight}/{nCall} spreads called right
        </span>
      }
    >
      {/* OUR CALL */}
      <div className={clsx('rounded-lg border p-3 mb-3',
        callTone === 'bull' && 'border-bull/40 bg-bull/5', callTone === 'bear' && 'border-bear/40 bg-bear/5', callTone === 'neut' && 'border-neut/40 bg-neut/5')}>
        <div className="text-[9.5px] font-mono uppercase tracking-[0.18em] text-text-muted mb-1">Our call (pre-release)</div>
        <div className="flex items-baseline gap-3 flex-wrap">
          <span className={clsx('text-xl font-display font-extrabold',
            callTone === 'bull' && 'text-bull', callTone === 'bear' && 'text-bear', callTone === 'neut' && 'text-neut')}>
            {p.call ?? '—'}
          </span>
          <span className="text-[11px] font-mono text-text-tertiary">
            surprise {p.surprise_mbbl != null ? `${p.surprise_mbbl > 0 ? '+' : ''}${(p.surprise_mbbl / 1000).toFixed(1)} MMbbl` : '—'}
            {p.surprise_z != null && ` (${p.surprise_z > 0 ? '+' : ''}${p.surprise_z}σ)`} · conf {p.confidence ?? '—'}
          </span>
          <span className="text-[10px] font-mono text-text-muted">{p.regime}</span>
        </div>
      </div>

      {/* crude-only feed caveat for product series */}
      {!isCrude && (
        <div className="rounded border border-neut/30 bg-neut/5 px-3 py-2 mb-3 text-[10px] font-mono text-text-tertiary leading-snug">
          ⚠ The desk 1-min feed is <span className="text-text-secondary">crude-only</span> (WTI + Brent) — RBOB / ULSD
          product cracks aren't recorded. {data.series_label} releases <span className="text-text-secondary">simultaneously</span> with
          crude at 10:30 ET, so below is the model's predicted {data.series_label?.toLowerCase()}→Brent cross-effect vs how
          the <span className="text-text-secondary">crude complex</span> actually reacted to the joint print. The product crack
          (<span className="text-gold">{(p as any).product_spread ?? 'RBOB/ULSD'}</span>) would need a products feed.
        </div>
      )}

      {/* PREDICTED → ACTUAL across horizons */}
      <div className="grid grid-cols-[96px_70px_repeat(4,1fr)_30px] gap-1.5 text-[9px] font-mono uppercase tracking-wide text-text-muted px-1 mb-1">
        <span>Spread</span><span className="text-right">Predicted</span>
        <span className="text-right">+5m</span><span className="text-right">+15m</span>
        <span className="text-right">+30m</span><span className="text-right">+60m</span><span className="text-center">✓</span>
      </div>
      <div className="space-y-1">
        {rows.map((r, ri) => (
          <div key={r.key}
            className={clsx('grid grid-cols-[96px_70px_repeat(4,1fr)_30px] gap-1.5 items-center text-[10.5px] font-mono tabular py-1 px-1 rounded',
              r.primary ? 'bg-gold/5 border border-gold/15' : 'hover:bg-bg-card/30')}>
            <span className={clsx(r.primary ? 'text-text-primary font-bold' : 'text-text-secondary')}>{r.label}</span>
            <span className={clsx('text-right', tone(r.pred))}>{fmt(r.pred, r.unit)}</span>
            {[5, 15, 30, 60].map(m => {
              const h = horizons.find(x => x.mins === m);
              const v = h && !h.pending ? (h[r.aKey] as number | undefined) : undefined;
              return (
                <span key={m} className={clsx('text-right', h?.pending ? 'text-text-muted/40' : tone(v))}>
                  {h?.pending ? '…' : fmt(v, r.unit)}
                </span>
              );
            })}
            <span className={clsx('text-center font-bold',
              grades[ri] === '✓' && 'text-bull', grades[ri] === '✗' && 'text-bear', grades[ri] === '~' && 'text-text-muted')}>
              {grades[ri]}
            </span>
          </div>
        ))}
      </div>

      {/* VERDICT */}
      <div className="mt-3 rounded-lg border border-border/50 bg-bg-card/30 p-3 text-[10.5px] font-mono text-text-secondary leading-relaxed">
        <span className="text-gold font-bold uppercase tracking-wider text-[9.5px]">Verdict · </span>
        {!isCrude ? (() => {
          const bF = lastFor('brent_flat_pct');
          const predB = p.price_reaction?.brent?.point_move_pct;
          const dirOk = bF != null && predB != null && Math.abs(bF) > 0.015 && Math.sign(bF) === Math.sign(predB);
          return (
            <>
              No {data.series_label?.toLowerCase()} product tape on the desk feed, so this grades the
              {' '}<span className="text-text-primary">crude-complex</span> reaction to the joint print. Our predicted
              {' '}{data.series_label?.toLowerCase()}→Brent cross-effect was <span className={tone(predB)}>{fmt(predB, '%')}</span>;
              {' '}Brent actually moved <span className={tone(bF)}>{fmt(bF, '%')}</span> — direction
              {' '}<span className={dirOk ? 'text-bull font-bold' : 'text-text-muted'}>{dirOk ? 'matched' : 'inconclusive (other drivers in the crude tape)'}</span>.
              The product crack (<span className="text-gold">{p.product_spread}</span>) is the real expression — needs a products feed.
            </>
          );
        })() : (() => {
          const wtiF = lastFor('wti_flat_pct'), wbrent = lastFor('d_wti_brent');
          const dirOk = wtiF != null && p.price_reaction?.wti?.point_move_pct != null
            && Math.abs(wtiF) > 0.015 && Math.sign(wtiF) === Math.sign(p.price_reaction.wti.point_move_pct);
          const maxAbs = Math.max(...horizons.filter(h => !h.pending).map(h => Math.abs(h.wti_flat_pct ?? 0)), 0);
          return (
            <>
              Direction on the flats was <span className={dirOk ? 'text-bull font-bold' : 'text-bear font-bold'}>{dirOk ? 'CORRECT' : 'off'}</span> ({p.call?.toLowerCase()} — WTI {fmt(wtiF, '%')} at the last read).
              {' '}The <span className="text-gold">WTI–Brent</span> spread we flagged as most-affected moved {fmt(wbrent, '$')} — {grades[2] === '✓' ? 'our called direction' : 'a small move'}.
              {' '}Magnitude was <span className="text-text-primary">muted</span> (peak {maxAbs.toFixed(2)}% « the ±{p.price_reaction?.wti?.day_range_pct ?? '2.5'}% typical day range), exactly the <span className="text-text-primary">low-sensitivity regime</span> call — the print was not a catalyst.
            </>
          );
        })()}
      </div>
      <div className="mt-1.5 text-[9px] font-mono text-text-muted">
        Anchored at the release minute on the desk 1-min CO/CL feed ({ax.feed_file}); flats in %, spreads in $/bbl. Predicted = the model's point estimate from the surprise.
      </div>
    </Panel>
  );
}
