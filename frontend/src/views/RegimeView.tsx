import { RegimePickCard } from '@/components/panels/RegimePickCard';
import { ABComparePanel } from '@/components/panels/ABComparePanel';
import { CalibrationPanel } from '@/components/panels/CalibrationPanel';
import { ShockMonitorPanel } from '@/components/panels/ShockMonitorPanel';

/**
 * Phase 2 — dedicated Regime tab.
 *
 * Hosts the regime-conditional opportunity card (4-model competition) as its
 * own first-class workspace, lifted out of Paper Trading where the class-demo
 * sprint originally placed it.
 *
 * Phase 2.8.6-followup: A/B paper-test panel (pooled vs gated_blend).
 * Phase 4.H: calibration panel — |z| bins vs realised 20d revert fraction.
 * Phase 2.8.9/10: shock-absorption monitor (GMM stress detector + circuit-breaker).
 */
export function RegimeView() {
  return (
    <div className="space-y-4">
      <ShockMonitorPanel />
      <RegimePickCard />
      <CalibrationPanel />
      <ABComparePanel />
    </div>
  );
}
