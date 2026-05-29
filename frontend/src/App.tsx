import { useEffect, useState } from 'react';
import { TopBar } from '@/components/shell/TopBar';
import { Sidebar, NAV_ITEMS, ViewKey } from '@/components/shell/Sidebar';
import { StatusBar } from '@/components/shell/StatusBar';
import { ErrorBoundary } from '@/components/ui/ErrorBoundary';
import { usePolling, useLocalStorage } from '@/lib/hooks';
import { api } from '@/lib/api';
import { SignalView } from '@/views/SignalView';
import { ChartsView } from '@/views/ChartsView';
import { FundamentalsView } from '@/views/FundamentalsView';
import { IntelligenceView } from '@/views/IntelligenceView';
import { TermStructureView } from '@/views/TermStructureView';
import { SpreadsView } from '@/views/SpreadsView';
import { ContractsView } from '@/views/ContractsView';
import { PlaybookView } from '@/views/PlaybookView';
import { ChatDock } from '@/components/chat/ChatDock';
import { OnboardingTour } from '@/components/onboarding/OnboardingTour';
import { DailySheet } from '@/components/panels/DailySheet';

export default function App() {
  const [view, setView] = useLocalStorage<ViewKey>('pulse.view', 'signal');
  const { data: all, refetch, lastUpdated, loading } = usePolling(api.all, 60000);
  const { data: prices } = usePolling(api.prices, 15000);
  const { data: history } = usePolling(api.history, 3600000);
  const { data: ohlcv } = usePolling(api.ohlcv, 60000);
  const { data: tradeIdea } = usePolling(api.tradeIdea, 600000);
  const { data: alerts } = usePolling(api.alerts, 60000);
  const [refreshing, setRefreshing] = useState(false);

  // Keyboard shortcuts
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA') return;
      const k = e.key;
      const map: Record<string, ViewKey> = { '1':'signal','2':'charts','3':'fundamentals','4':'intelligence','5':'term','6':'spreads','7':'contracts','8':'playbook' };
      if (map[k]) setView(map[k]);
      if (k === 'r' || k === 'R') { setRefreshing(true); refetch().finally(() => setTimeout(() => setRefreshing(false), 600)); }
      if (k === 'f' || k === 'F') document.documentElement.requestFullscreen?.();
      if (k === 'p' || k === 'P') { e.preventDefault(); window.print(); }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [setView, refetch]);

  const liveTicker = prices ?? all?.prices ?? null;
  const merged = { ...(all ?? {}), prices: liveTicker ?? all?.prices ?? {} };
  const activeLabel = NAV_ITEMS.find(n => n.key === view)?.label ?? '';

  return (
    <div className="h-screen w-screen flex flex-col bg-bg overflow-hidden">
      <TopBar
        ticker={liveTicker}
        refreshing={refreshing}
        onRefresh={() => { setRefreshing(true); refetch().finally(() => setTimeout(() => setRefreshing(false), 600)); }}
      />
      <div className="flex flex-1 min-h-0">
        <Sidebar active={view} onSelect={setView} />
        <main className="flex-1 overflow-y-auto overflow-x-hidden bg-grid-faint" style={{ backgroundSize: '32px 32px' }}>
          {/* View header */}
          <div className="px-6 pt-5 pb-3 flex items-baseline justify-between border-b border-border/40 sticky top-0 bg-bg/85 backdrop-blur-md z-10">
            <div className="flex items-baseline gap-3">
              <h1 className="font-display font-extrabold text-2xl tracking-[0.16em] uppercase">{activeLabel}</h1>
              <span className="text-[10px] font-mono text-text-muted uppercase tracking-widest">
                {loading && !all ? 'initializing data layer…' : `${Object.keys(all ?? {}).length} streams active`}
              </span>
            </div>
            <div className="text-[10px] font-mono text-text-tertiary tabular">
              {lastUpdated ? new Date(lastUpdated).toLocaleTimeString('en-US', { hour12: false }) : ''}
            </div>
          </div>

          {/* Print-only daily sheet */}
          <DailySheet all={merged} tradeIdea={tradeIdea} />

          <div className="p-6 pb-12">
            <ErrorBoundary label={activeLabel}>
              {view === 'signal'        && <SignalView all={merged} tradeIdea={tradeIdea} alerts={Array.isArray(alerts) ? alerts : (alerts as any)?.alerts ?? []} />}
              {view === 'charts'        && <ChartsView all={merged} history={history} ohlcv={ohlcv} />}
              {view === 'fundamentals'  && <FundamentalsView all={merged} />}
              {view === 'intelligence'  && <IntelligenceView all={merged} />}
              {view === 'term'          && <TermStructureView all={merged} />}
              {view === 'spreads'       && <SpreadsView all={merged} />}
              {view === 'contracts'     && <ContractsView all={merged} />}
              {view === 'playbook'      && <PlaybookView />}
            </ErrorBoundary>
          </div>
        </main>
      </div>
      <StatusBar
        fundamentals={all?.fundamentals}
        curve={all?.curve}
        cracks={all?.cracks}
        lastUpdated={lastUpdated}
      />

      {/* Floating RAG chat dock — '/' to open */}
      <ChatDock />

      {/* First-visit onboarding tour */}
      <OnboardingTour onNavigate={setView} />
    </div>
  );
}
