import { PageHeader, SectionHeader } from '@/components/ui/SectionHeader';
import { SignalLogPanel } from '@/components/panels/SignalLogPanel';
import { IntradayReplayPanel } from '@/components/panels/IntradayReplayPanel';

/**
 * Phase 3.1 — Live Signal Log tab.
 *
 * Mentor directive: "move from historical validation to a live analysis engine
 * and clearly track what the framework would be trading in the current market
 * environment." This tab hosts the live signal log fed by the 15-min bar feed
 * (research/live_engine + signal_log), plus an in-window sanity replay of the
 * engine over the recorder's real 15-min tape (clearly labelled a diagnostic).
 */
export function SignalLogView() {
  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Signal Log · Phase 3.1"
        title="Live analysis engine"
        desc={<>What the regime framework would be trading in the current market — every non-neutral opportunity
          off the live 15-min feed, tagged with regime, confidence, entry→fair (z), and subsequent performance
          on the tuned exit rule (TP halfway-to-fair · SL 2.5σ · 30-day time-stop). Read-only analysis
          tracking, not order entry.</>}
        badges={
          /* Audit fix (2026-07-14): no unconditional pulsing "Live feed" claim —
             the panel below shows the actual feed timestamp and flags staleness. */
          <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-md border border-gold/30 bg-gold/5 text-gold text-[9px] font-mono uppercase tracking-wider">
            15-min bar feed
          </span>
        }
      />

      <SignalLogPanel />

      <SectionHeader
        accent="blue"
        eyebrow="Diagnostics"
        title="Intraday engine replay"
        desc="Sanity replay of the engine over the recorder's real 15-min tape — a diagnostic, not a backtest."
      />
      <IntradayReplayPanel />
    </div>
  );
}
