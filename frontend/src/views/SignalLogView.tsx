import { SignalLogPanel } from '@/components/panels/SignalLogPanel';
import { IntradayReplayPanel } from '@/components/panels/IntradayReplayPanel';

/**
 * Phase 3.1 — Live Signal Log tab.
 *
 * Mentor directive: "move from historical validation to a live analysis engine
 * and clearly track what the framework would be trading in the current market
 * environment." This tab hosts the live signal log fed by the lightstreamer
 * 15-min bar feed (research/live_engine + signal_log), plus an in-window
 * sanity replay of the engine over the recorder's real 15-min tape (clearly
 * labelled a diagnostic, not a backtest).
 */
export function SignalLogView() {
  return (
    <div className="space-y-4">
      <SignalLogPanel />
      <IntradayReplayPanel />
    </div>
  );
}
