import { RegimePickCard } from '@/components/panels/RegimePickCard';

/**
 * Phase 2 — dedicated Regime tab.
 *
 * Hosts the regime-conditional opportunity card (4-model competition) as its
 * own first-class workspace, lifted out of Paper Trading where the class-demo
 * sprint originally placed it.
 */
export function RegimeView() {
  return (
    <div className="space-y-4">
      <RegimePickCard />
    </div>
  );
}
