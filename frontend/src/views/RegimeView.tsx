import { PageHeader, SectionHeader } from '@/components/ui/SectionHeader';
import { RegimePickCard } from '@/components/panels/RegimePickCard';
import { CalibrationPanel } from '@/components/panels/CalibrationPanel';
import { PerSpreadGatePanel } from '@/components/panels/PerSpreadGatePanel';
import { DecorrelatedBookPanel } from '@/components/panels/DecorrelatedBookPanel';
import { ShockMonitorPanel } from '@/components/panels/ShockMonitorPanel';
import { AutoDeskPanel } from '@/components/panels/AutoDeskPanel';

/**
 * Phase 2 — dedicated Regime tab.
 *
 * Reads top-down as the desk's decision chain:
 *   00 · risk gates    — shock circuit-breaker + the live auto-desk plan
 *   01 · the signal    — regime-conditional pick card (provenance chips intact)
 *   02 · the book      — decorrelated selection + per-spread gate verdict
 *   03 · the evidence  — |z| calibration vs realised reversion
 *
 * Phase 4.H calibration · Phase 2.8.9/10 shock monitor · Phase 3/4 auto-desk ·
 * Phase 8 per-spread gate · decorrelated book (mentor directive).
 */
export function RegimeView() {
  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Regime Engine · Phase 2→8"
        title="Regime-conditional spread engine"
        desc={<>Six Brent/WTI spreads scored against a regime-aware fair value (7-model per-cell competition),
          gated per spread only where the walk-forward proved an edge, decorrelated into a book, and
          risk-managed by a GMM shock breaker. Every number below carries its provenance — estimates are
          flagged, baselines are labelled.</>}
        badges={
          <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-md border border-gold/30 bg-gold/5 text-gold text-[9px] font-mono uppercase tracking-wider">
            <span className="w-1.5 h-1.5 rounded-full bg-gold animate-pulse-soft" /> Live engine
          </span>
        }
      />

      <section className="space-y-4">
        <SectionHeader
          accent="bear"
          eyebrow="Risk gates · 00"
          title="Shock breaker & auto-desk"
          desc="Entries pause on a stress onset; the auto-desk reconciles the paper book to the gated,
                decorrelated live recommendation during market hours."
        />
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-4 items-start">
          <ShockMonitorPanel />
          <AutoDeskPanel />
        </div>
      </section>

      <section className="space-y-4">
        <SectionHeader
          accent="gold"
          eyebrow="The signal · 01"
          title="Today's regime pick"
        />
        <RegimePickCard />
      </section>

      <section className="space-y-4">
        <SectionHeader
          accent="blue"
          eyebrow="The book · 02"
          title="Decorrelated selection & per-spread gate"
          desc="Top conviction without doubling correlated bets (signed-ρ filter), and regime conditioning
                deployed only on the spreads where it beat the rolling-z baseline out of sample."
        />
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-4 items-start">
          <DecorrelatedBookPanel />
          <PerSpreadGatePanel />
        </div>
      </section>

      <section className="space-y-4">
        <SectionHeader
          accent="bull"
          eyebrow="The evidence · 03"
          title="Calibration — did z mean anything?"
          desc="Walk-forward pass-gate trades binned by |z|: the reverted fraction should climb with
                displacement if the signal is real."
        />
        <CalibrationPanel />
      </section>
    </div>
  );
}
