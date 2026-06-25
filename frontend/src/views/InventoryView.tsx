import { useState } from 'react';
import clsx from 'clsx';
import { InventoryImpactPanel } from '@/components/panels/InventoryImpactPanel';
import { InventoryReactionPanel } from '@/components/panels/InventoryReactionPanel';
import { InventoryFrameworkPanel } from '@/components/panels/InventoryFrameworkPanel';
import { InventoryReleasesPanel } from '@/components/panels/InventoryReleasesPanel';
import { InventoryReportPanel } from '@/components/panels/InventoryReportPanel';
import { InventoriesSection } from '@/views/MarketsView';

export type InvSeries = 'crude_ex_spr' | 'gasoline' | 'distillate';
const SERIES: { key: InvSeries; label: string }[] = [
  { key: 'crude_ex_spr', label: 'Crude' },
  { key: 'gasoline',     label: 'Gasoline' },
  { key: 'distillate',   label: 'Distillate' },
];

/**
 * Inventory tab — the EIA-release impact framework, end to end, now for all three
 * series (Crude / Gasoline / Distillate). The series toggle drives the call card,
 * the regime "when-it-mattered" table, and the recent-release history — each series
 * carries its OWN regime betas (gasoline reacts in regimes where crude is noise).
 *
 *  1. The CALL — expectation · spreads · top-3 · framework, with a consensus
 *     calculator and the regime-gated scenario tree.
 *  2. The framework + backtested evidence (L0→L4, when-it-mattered, charts).
 *  3. The latest full report (whole tape) + recent-release surprise history.
 *  4. The live inventory dashboard relocated from Markets.
 */
export function InventoryView({ all }: { all: any }) {
  const [series, setSeries] = useState<InvSeries>('crude_ex_spr');
  return (
    <div className="space-y-4">
      {/* Series toggle — Crude / Gasoline / Distillate */}
      <div className="flex items-center gap-2">
        <span className="text-[10px] font-mono uppercase tracking-[0.24em] text-text-muted mr-1">Series</span>
        {SERIES.map(s => (
          <button
            key={s.key}
            onClick={() => setSeries(s.key)}
            className={clsx(
              'px-3 py-1 rounded border text-[11px] font-mono uppercase tracking-wider transition-colors',
              series === s.key
                ? 'bg-gold/15 border-gold/40 text-gold'
                : 'border-border/50 text-text-tertiary hover:text-text-secondary hover:border-border',
            )}
          >
            {s.label}
          </button>
        ))}
      </div>

      <InventoryImpactPanel series={series} />
      {/* Predicted-vs-actual reaction. Crude is anchored on today's real
          consensus (-3.9 MMbbl) + API (-0.765 MMbbl); gasoline/distillate use
          the seasonal proxy (no consensus on the wire) + show the crude-only
          feed caveat. */}
      <InventoryReactionPanel
        series={series}
        actual={series === 'crude_ex_spr' ? -765 : undefined}
        consensus={series === 'crude_ex_spr' ? -3900 : undefined}
      />
      <InventoryFrameworkPanel series={series} />
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <InventoryReportPanel />
        <InventoryReleasesPanel series={series} />
      </div>
      <div className="pt-2 text-[10px] font-mono tracking-[0.22em] text-text-muted uppercase">
        Live inventory dashboard
      </div>
      <InventoriesSection all={all} />
    </div>
  );
}
