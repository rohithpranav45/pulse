import { InventoryImpactPanel } from '@/components/panels/InventoryImpactPanel';
import { InventoryFrameworkPanel } from '@/components/panels/InventoryFrameworkPanel';
import { InventoryReleasesPanel } from '@/components/panels/InventoryReleasesPanel';
import { InventoryReportPanel } from '@/components/panels/InventoryReportPanel';
import { InventoriesSection } from '@/views/MarketsView';

/**
 * Inventory tab — the EIA crude-release framework, end to end.
 *
 *  1. The CALL — the four Thursday deliverables (expectation · spreads · top-3 ·
 *     framework) as a forward call for the upcoming release, with a consensus
 *     calculator and the regime-gated scenario tree.
 *  2. The framework + backtested evidence (L0→L4, when-it-mattered, charts).
 *  3. The latest full report (the whole tape) + recent-release surprise history.
 *  4. The live inventory dashboard relocated from Markets.
 *
 * See backend/research/inventory_impact/DELIVERABLE.md.
 */
export function InventoryView({ all }: { all: any }) {
  return (
    <div className="space-y-4">
      <InventoryImpactPanel />
      <InventoryFrameworkPanel />
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <InventoryReportPanel />
        <InventoryReleasesPanel />
      </div>
      <div className="pt-2 text-[10px] font-mono tracking-[0.22em] text-text-muted uppercase">
        Live inventory dashboard
      </div>
      <InventoriesSection all={all} />
    </div>
  );
}
