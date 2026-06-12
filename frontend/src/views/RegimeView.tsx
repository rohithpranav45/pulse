import { RegimePickCard } from '@/components/panels/RegimePickCard';
import { ABComparePanel } from '@/components/panels/ABComparePanel';

/**
 * Phase 2 — dedicated Regime tab.
 *
 * Hosts the regime-conditional opportunity card (4-model competition) as its
 * own first-class workspace, lifted out of Paper Trading where the class-demo
 * sprint originally placed it.
 *
 * Phase 2.8.6-followup: adds the A/B paper-test panel comparing un-gated
 * pooled vs current gated_blend in parallel paper books.
 */
export function RegimeView() {
  return (
    <div className="space-y-4">
      <RegimePickCard />
      <ABComparePanel />
    </div>
  );
}
