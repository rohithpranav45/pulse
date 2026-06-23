import { useMemo } from 'react';
import clsx from 'clsx';
import { Panel } from '@/components/ui/Panel';
import { SkeletonRows } from '@/components/ui/Skeleton';
import { api } from '@/lib/api';
import { usePolling } from '@/lib/hooks';

/**
 * Latest EIA report snapshot — the whole report, not just the headline. Levels +
 * weekly change for crude/Cushing/gasoline/distillate/runs/imports/exports/
 * implied-demand, plus the reconstructed supply-balance adjustment (a large
 * |adjustment| ⇒ the report doesn't reconcile → fade the reaction).
 */

type Line = { label: string; unit: string; level: number | null; change: number | null };
type Report = { week_ending: string; release_date: string; adjustment: number | null; lines: Line[] };
type Inventory = { available: boolean; error?: string; latest_report?: Report };

function fmtLevel(v: number | null, unit: string): string {
  if (v == null) return '—';
  if (unit === 'MMbbl') return (v / 1000).toFixed(1);
  if (unit === '%') return v.toFixed(1);
  return (v / 1000).toFixed(2); // Mb/d -> show as M b/d
}
function fmtChg(v: number | null, unit: string): string {
  if (v == null) return '—';
  const s = v > 0 ? '+' : '';
  if (unit === 'MMbbl') return `${s}${(v / 1000).toFixed(2)}`;
  if (unit === '%') return `${s}${v.toFixed(1)}`;
  return `${s}${(v / 1000).toFixed(2)}`;
}

export function InventoryReportPanel() {
  const { data, lastUpdated, error } = usePolling<Inventory>(
    () => api.regimeInventory() as Promise<Inventory>,
    600_000,
  );
  const rep = useMemo(() => data?.latest_report, [data]);

  if (!data && !error) {
    return (
      <Panel title="Latest report · the whole tape" accent="gold" source="inventory_impact"
        staticMount lastSuccess={lastUpdated} fetchError={error}>
        <SkeletonRows rows={8} />
      </Panel>
    );
  }
  if (!data?.available || !rep) {
    return (
      <Panel title="Latest report · the whole tape" accent="gold" source="inventory_impact"
        staticMount lastSuccess={lastUpdated} fetchError={error}>
        <div className="text-[12px] font-mono text-text-tertiary px-3 py-6 text-center">
          {error ? `Inventory endpoint unreachable: ${(error as any)?.message ?? String(error)}`
                 : data?.error ?? 'No report snapshot available.'}
        </div>
      </Panel>
    );
  }

  const bigAdj = rep.adjustment != null && Math.abs(rep.adjustment) > 500;

  return (
    <Panel
      title="Latest report · the whole tape"
      subtitle={`week ending ${rep.week_ending} · released ${rep.release_date}`}
      accent="gold"
      source="inventory_impact"
      staticMount
      lastSuccess={lastUpdated}
      fetchError={error}
    >
      <div className="grid grid-cols-[1fr_84px_84px_42px] gap-2 text-[9.5px] font-mono text-text-muted uppercase tracking-wide px-1 mb-1">
        <span>Series</span><span className="text-right">Level</span><span className="text-right">Δ wk</span><span className="text-right">unit</span>
      </div>
      <div className="space-y-0.5">
        {rep.lines.map(l => {
          // a draw (negative change) on a stock series is bullish-coloured
          const isStock = l.unit === 'MMbbl';
          const chgTone = l.change == null ? 'muted'
            : isStock ? (l.change < 0 ? 'bull' : 'bear')
            : 'neut';
          return (
            <div key={l.label}
              className="grid grid-cols-[1fr_84px_84px_42px] gap-2 items-center text-[10.5px] font-mono tabular py-0.5 px-1 rounded hover:bg-bg-card/30">
              <span className="text-text-secondary">{l.label}</span>
              <span className="text-right text-text-tertiary">{fmtLevel(l.level, l.unit)}</span>
              <span className={clsx('text-right font-bold',
                chgTone === 'bull' && 'text-bull', chgTone === 'bear' && 'text-bear',
                chgTone === 'neut' && 'text-text-secondary', chgTone === 'muted' && 'text-text-muted')}>
                {fmtChg(l.change, l.unit)}
              </span>
              <span className="text-right text-text-muted">{l.unit}</span>
            </div>
          );
        })}
      </div>
      <div className={clsx('mt-3 text-[10.5px] font-mono rounded border px-3 py-2 leading-relaxed',
        bigAdj ? 'border-bear/30 bg-bear/5' : 'border-border/40')}>
        <span className="text-text-tertiary">Reconstructed adjustment: </span>
        <span className={clsx('font-bold', bigAdj ? 'text-bear' : 'text-text-secondary')}>
          {rep.adjustment == null ? '—' : `${rep.adjustment > 0 ? '+' : ''}${rep.adjustment.toFixed(0)} kb/d`}
        </span>
        <span className="text-text-muted">
          {' '}— {bigAdj ? 'large: the balance does not reconcile → fade the reaction.'
                       : 'small: the report reconciles cleanly.'}
        </span>
      </div>
      <div className="mt-2 text-[10px] font-mono text-text-muted leading-relaxed">
        Stock series in MMbbl, flows in M b/d. A crude draw is only bullish if it is demand-led
        (runs up, implied demand strong, exports not the cause). Adjustment = EIA's unaccounted-for
        crude, backed out of the weekly supply/disposition identity.
      </div>
    </Panel>
  );
}
