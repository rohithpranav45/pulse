import { SignalLogPanel } from '@/components/panels/SignalLogPanel';

/**
 * Phase 3.1 — Live Signal Log tab.
 *
 * Mentor directive: "move from historical validation to a live analysis engine
 * and clearly track what the framework would be trading in the current market
 * environment." This tab hosts the live signal log fed by the lightstreamer
 * 15-min bar feed (research/live_engine + signal_log).
 */
export function SignalLogView() {
  return (
    <div className="space-y-4">
      <SignalLogPanel />
    </div>
  );
}
