import { useMemo } from 'react';
import clsx from 'clsx';
import { Panel } from '@/components/ui/Panel';
import { SkeletonRows } from '@/components/ui/Skeleton';
import { api } from '@/lib/api';
import { usePolling } from '@/lib/hooks';

/**
 * Recent EIA crude releases — actual vs expected, the surprise (z-scored), and
 * the quality-of-draw. The "release date" column is the Wednesday the report hit
 * the tape (the week-ending Friday is the data period). Bullish = a tighter-than-
 * expected print (surprise < 0); quality < 0 flags a draw whose internals are
 * weak/mechanical (fade it).
 */

type Release = {
  week_ending: string;
  release_date: string;
  actual_change: number | null;
  expected: number | null;
  surprise: number | null;
  surprise_z: number | null;
  bullish: boolean;
  quality: number | null;
};

type Inventory = { available: boolean; error?: string; recent_releases?: Release[] };

const mm = (v: number | null) =>
  v == null ? '—' : `${v > 0 ? '+' : ''}${(v / 1000).toFixed(1)}`;

export function InventoryReleasesPanel() {
  const { data, lastUpdated, error } = usePolling<Inventory>(
    () => api.regimeInventory() as Promise<Inventory>,
    600_000,
  );
  const rows = useMemo(() => data?.recent_releases ?? [], [data]);

  if (!data && !error) {
    return (
      <Panel title="Recent releases · surprise & quality" accent="blue" source="inventory_impact"
        staticMount lastSuccess={lastUpdated} fetchError={error}>
        <SkeletonRows rows={8} />
      </Panel>
    );
  }
  if (!data?.available || rows.length === 0) {
    return (
      <Panel title="Recent releases · surprise & quality" accent="blue" source="inventory_impact"
        staticMount lastSuccess={lastUpdated} fetchError={error}>
        <div className="text-[12px] font-mono text-text-tertiary px-3 py-6 text-center">
          {error ? `Inventory endpoint unreachable: ${(error as any)?.message ?? String(error)}`
                 : data?.error ?? 'No release history available.'}
        </div>
      </Panel>
    );
  }

  return (
    <Panel
      title="Recent releases · surprise & quality"
      subtitle="actual vs expected (MMbbl) · surprise z-scored · quality-of-draw"
      accent="blue"
      source="inventory_impact"
      staticMount
      lastSuccess={lastUpdated}
      fetchError={error}
    >
      <div className="grid grid-cols-[88px_84px_1fr_64px_64px_72px] gap-2 text-[9.5px] font-mono text-text-muted uppercase tracking-wide px-1 mb-1">
        <span>Released</span><span>Wk ending</span><span>Actual / Exp</span>
        <span className="text-right">Surprise</span><span className="text-right">z</span><span className="text-right">Quality</span>
      </div>
      <div className="space-y-0.5">
        {rows.map(r => {
          const z = r.surprise_z ?? 0;
          const qTone = r.quality == null ? 'muted' : r.quality > 0.5 ? 'bull' : r.quality < -0.5 ? 'bear' : 'neut';
          // divergence flag: bullish headline but weak quality
          const diverge = r.bullish && (r.quality ?? 0) < 0;
          return (
            <div key={r.week_ending}
              className="grid grid-cols-[88px_84px_1fr_64px_64px_72px] gap-2 items-center text-[10.5px] font-mono tabular py-0.5 px-1 rounded hover:bg-bg-card/30"
              title={diverge ? 'Headline draw but weak internals — mechanical/fade' : ''}>
              <span className="text-text-secondary">{r.release_date.slice(5)}</span>
              <span className="text-text-muted">{r.week_ending.slice(5)}</span>
              <span className="text-text-tertiary">{mm(r.actual_change)} / {mm(r.expected)}</span>
              <span className={clsx('text-right font-bold', r.bullish ? 'text-bull' : 'text-bear')}>
                {mm(r.surprise)}
              </span>
              <span className={clsx('text-right', Math.abs(z) >= 1 ? 'text-text-secondary' : 'text-text-muted')}>
                {z > 0 ? '+' : ''}{z.toFixed(1)}
              </span>
              <span className={clsx('text-right flex items-center justify-end gap-1',
                qTone === 'bull' && 'text-bull', qTone === 'bear' && 'text-bear',
                qTone === 'neut' && 'text-neut', qTone === 'muted' && 'text-text-muted')}>
                {diverge && <span className="text-bear" title="divergent — fade">⚠</span>}
                {r.quality == null ? '—' : `${r.quality > 0 ? '+' : ''}${r.quality.toFixed(1)}`}
              </span>
            </div>
          );
        })}
      </div>
      <div className="mt-3 text-[10px] font-mono text-text-muted leading-relaxed">
        <span className="text-bull">green</span> surprise = bullish (tighter than expected);
        <span className="text-bear"> red</span> = bearish (looser). Quality &gt; 0 = demand-led/coherent draw;
        <span className="text-bear"> ⚠</span> = bullish headline but weak internals (mechanical — fade).
      </div>
    </Panel>
  );
}
