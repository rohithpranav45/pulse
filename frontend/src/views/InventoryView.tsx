import { useState } from 'react';
import clsx from 'clsx';
import { PageHeader, SectionHeader } from '@/components/ui/SectionHeader';
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
    <div className="space-y-6">
      <PageHeader
        eyebrow="Inventory · EIA framework"
        title="The Wednesday number, decoded"
        desc={<>Each EIA release is graded against the <span className="text-gold">real analyst consensus</span>,
          conditioned on the regime where inventories historically bit, and committed only where the measured
          directional hit-rate beat a coin flip — abstain elsewhere. Each series carries its own regime betas.</>}
        badges={
          <div className="flex items-center gap-1.5 rounded-md border border-border/60 bg-bg-card/40 p-1">
            {SERIES.map(s => (
              <button
                key={s.key}
                onClick={() => setSeries(s.key)}
                className={clsx(
                  'px-3 py-1 rounded text-[10px] font-mono uppercase tracking-wider transition-colors',
                  series === s.key
                    ? 'bg-gold/15 text-gold shadow-[inset_0_0_0_1px_rgba(218,182,65,0.35)]'
                    : 'text-text-tertiary hover:text-text-secondary',
                )}
              >
                {s.label}
              </button>
            ))}
          </div>
        }
      />

      <InventoryImpactPanel series={series} />
      {/* Predicted-vs-actual reaction. With no actual/consensus passed, the
          backend auto-anchors on the REAL printed EIA actual + consensus from the
          consensus history (e.g. 24-Jun crude -6.088M vs -3.900M = a bullish
          surprise the old API proxy -0.765M got the wrong sign on). */}
      <InventoryReactionPanel series={series} />
      <InventoryFrameworkPanel series={series} />
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <InventoryReportPanel />
        <InventoryReleasesPanel series={series} />
      </div>
      <SectionHeader
        accent="blue"
        eyebrow="Live levels"
        title="Inventory dashboard"
        desc="Current EIA stocks vs the 5-year band, forward cover, and the surprise history."
      />
      <InventoriesSection all={all} />
    </div>
  );
}
