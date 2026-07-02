import { lazy, Suspense, useEffect, useMemo, useState } from 'react';
import { motion } from 'framer-motion';
import {
  RefreshCw, Printer, Maximize2, Keyboard, Sun, Moon, MessageSquareText, Compass,
} from 'lucide-react';
import { TopBar } from '@/components/shell/TopBar';
import { Sidebar, NAV_ITEMS, ViewKey } from '@/components/shell/Sidebar';
import { StatusBar } from '@/components/shell/StatusBar';
import { CommandPalette, PaletteAction } from '@/components/shell/CommandPalette';
import { ErrorBoundary } from '@/components/ui/ErrorBoundary';
import { usePolling, useLocalStorage, useTheme } from '@/lib/hooks';
import { api } from '@/lib/api';
import { DeskView } from '@/views/DeskView';
import { ChatDock } from '@/components/chat/ChatDock';
import { OnboardingTour, resetOnboarding } from '@/components/onboarding/OnboardingTour';
import { DailySheet } from '@/components/panels/DailySheet';
import { ToastStack } from '@/components/alerts/ToastStack';

// DESK stays eagerly bundled (first paint); every other view is code-split so
// the heavy chart/table dependencies load on demand instead of on boot.
const ChartsView    = lazy(() => import('@/views/ChartsView').then(m => ({ default: m.ChartsView })));
const MarketsView   = lazy(() => import('@/views/MarketsView').then(m => ({ default: m.MarketsView })));
const PaperView     = lazy(() => import('@/views/PaperView').then(m => ({ default: m.PaperView })));
const RegimeView    = lazy(() => import('@/views/RegimeView').then(m => ({ default: m.RegimeView })));
const InventoryView = lazy(() => import('@/views/InventoryView').then(m => ({ default: m.InventoryView })));
const SignalLogView = lazy(() => import('@/views/SignalLogView').then(m => ({ default: m.SignalLogView })));
const NewsView      = lazy(() => import('@/views/NewsView').then(m => ({ default: m.NewsView })));

/** Skeleton shown for the ~100ms a lazy view chunk takes to arrive. */
function ViewLoading() {
  return (
    <div className="space-y-4">
      {[160, 280, 200].map((h, i) => (
        <div key={i} className="panel overflow-hidden" style={{ height: h }}>
          <div className="skeleton w-full h-full opacity-60" />
        </div>
      ))}
    </div>
  );
}

export default function App() {
  const [view, setView] = useLocalStorage<ViewKey>('pulse.view', 'desk');
  const { data: all, refetch, lastUpdated, loading } = usePolling(api.all, 60000);
  const { data: prices } = usePolling(api.prices, 15000);
  const { data: history } = usePolling(api.history, 3600000);
  const { data: ohlcv } = usePolling(api.ohlcv, 60000);
  const { data: tradeIdea } = usePolling(api.tradeIdea, 600000);
  const { data: alerts } = usePolling(api.alerts, 60000);
  const [refreshing, setRefreshing] = useState(false);

  // Legacy view keys silently coalesce — Phase 4.C folds spreads &
  // fundamentals into MARKETS (term/contracts were earlier aliases for
  // spreads); Phase 4.D sends the now-deleted Playbook tab → regime
  // (analogs live in the drill modal); Phase 4.E cuts Intelligence
  // entirely → desk; the Phase 4.B Signal tab → desk; everything else
  // unknown → desk.
  useEffect(() => {
    const valid = NAV_ITEMS.map(n => n.key) as ViewKey[];
    if (!valid.includes(view)) {
      const legacy = view as any;
      const next: ViewKey =
        legacy === 'spreads' || legacy === 'fundamentals' ||
        legacy === 'term'    || legacy === 'contracts'
          ? 'markets'
          : legacy === 'playbook'
            ? 'regime'
            : 'desk';
      setView(next);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const [helpOpen, setHelpOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [theme, toggleTheme] = useTheme();

  // Keyboard shortcuts. Bare 1..8/R/F/P only fire outside form inputs; the
  // modifier variants (Cmd/Ctrl+1..8, Cmd/Ctrl+K) fire anywhere, so tab nav
  // and the palette still work while typing in the ChatDock or a paper-trade
  // entry field.
  useEffect(() => {
    const map: Record<string, ViewKey> = {
      '1':'desk','2':'charts','3':'markets',
      '4':'paper','5':'regime','6':'inventory','7':'signals','8':'news',
    };
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      const inInput = tag === 'INPUT' || tag === 'TEXTAREA';
      const k = e.key;
      const mod = e.metaKey || e.ctrlKey;

      // Cmd/Ctrl+K — command palette, global, works in inputs too.
      if (mod && (k === 'k' || k === 'K')) {
        e.preventDefault();
        setPaletteOpen(v => !v);
        return;
      }

      // Cmd/Ctrl+1..8 — global, works in inputs too.
      if (mod && map[k]) {
        e.preventDefault();
        setView(map[k]);
        return;
      }

      // While the palette is open it owns the keyboard.
      if (paletteOpen) return;

      // ? toggles the help overlay (Shift+/ produces '?'); Esc closes it.
      if (!inInput && k === '?') { e.preventDefault(); setHelpOpen(v => !v); return; }
      if (k === 'Escape' && helpOpen) { setHelpOpen(false); return; }

      if (inInput) return;
      if (map[k]) setView(map[k]);
      if (k === 'r' || k === 'R') { setRefreshing(true); refetch().finally(() => setTimeout(() => setRefreshing(false), 600)); }
      if (k === 'f' || k === 'F') document.documentElement.requestFullscreen?.();
      if (k === 'p' || k === 'P') { e.preventDefault(); window.print(); }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [setView, refetch, helpOpen, paletteOpen]);

  // Command palette actions — navigation (with live icons from NAV_ITEMS) +
  // every global action that today only lives on a hotkey or a TopBar icon.
  const paletteActions = useMemo<PaletteAction[]>(() => [
    ...NAV_ITEMS.map(n => ({
      id: `nav-${n.key}`,
      label: n.label,
      group: 'Navigate',
      sub: n.sub,
      hint: n.hint,
      icon: n.icon,
      run: () => setView(n.key),
    })),
    {
      id: 'act-refresh', label: 'Refresh all data', group: 'Actions', hint: 'R', icon: RefreshCw,
      run: () => { setRefreshing(true); refetch().finally(() => setTimeout(() => setRefreshing(false), 600)); },
    },
    {
      id: 'act-theme',
      label: theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme',
      group: 'Actions', icon: theme === 'dark' ? Sun : Moon,
      run: toggleTheme,
    },
    {
      id: 'act-chat', label: 'Ask PULSE (RAG chat)', group: 'Actions', hint: '/', icon: MessageSquareText,
      run: () => window.dispatchEvent(new CustomEvent('pulse-open-chat')),
    },
    {
      id: 'act-print', label: 'Print daily briefing sheet', group: 'Actions', hint: 'P', icon: Printer,
      run: () => window.print(),
    },
    {
      id: 'act-fullscreen', label: 'Toggle fullscreen', group: 'Actions', hint: 'F', icon: Maximize2,
      run: () => document.documentElement.requestFullscreen?.(),
    },
    {
      id: 'act-help', label: 'Keyboard shortcuts', group: 'Actions', hint: '?', icon: Keyboard,
      run: () => setHelpOpen(true),
    },
    {
      id: 'act-tour', label: 'Restart onboarding tour', group: 'Actions', icon: Compass,
      run: () => resetOnboarding(),
    },
  ], [theme, toggleTheme, refetch, setView]);

  const liveTicker = prices ?? all?.prices ?? null;
  const merged = { ...(all ?? {}), prices: liveTicker ?? all?.prices ?? {} };
  const activeNav = NAV_ITEMS.find(n => n.key === view);
  const activeLabel = activeNav?.label ?? '';
  const activeHint = activeNav?.hint ?? '';

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
          {/* View header — chunky display heading w/ tab numeral, breadcrumb, hairline gold rule */}
          <div
            className="relative px-7 pt-6 pb-5 flex items-end justify-between sticky top-0 z-10"
            style={{
              background: 'linear-gradient(180deg, rgb(var(--bg-default) / 0.94) 0%, rgb(var(--bg-default) / 0.82) 100%)',
              backdropFilter: 'blur(20px) saturate(140%)',
              WebkitBackdropFilter: 'blur(20px) saturate(140%)',
            }}
          >
            <div
              aria-hidden
              className="absolute bottom-0 left-0 right-0 h-px pointer-events-none"
              style={{ background: 'linear-gradient(90deg, transparent, var(--border-accent) 12%, rgba(218,182,65,0.55) 50%, var(--border-accent) 88%, transparent)' }}
            />
            <div className="flex items-end gap-5">
              {/* Big numeric tab indicator */}
              <motion.div
                key={`num-${view}`}
                initial={{ opacity: 0, scale: 0.85 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ duration: 0.28, ease: [0.16, 1, 0.3, 1] }}
                className="relative flex items-center justify-center w-14 h-14 rounded-xl flex-shrink-0"
                style={{
                  background: 'linear-gradient(135deg, rgba(218,182,65,0.18) 0%, rgba(218,182,65,0.04) 100%)',
                  border: '1px solid var(--border-accent)',
                  boxShadow: '0 8px 24px -10px var(--gold-glow), inset 0 1px 0 rgba(255,255,255,0.05)',
                }}
              >
                <span
                  className="font-display font-black text-[32px] leading-none tabular"
                  style={{
                    background: 'linear-gradient(180deg, rgb(var(--gold-bright)), rgb(var(--gold)))',
                    WebkitBackgroundClip: 'text',
                    backgroundClip: 'text',
                    WebkitTextFillColor: 'transparent',
                    filter: 'drop-shadow(0 0 8px var(--gold-glow))',
                  }}
                >
                  {activeHint}
                </span>
                {/* corner ticks */}
                <span aria-hidden className="absolute top-1 left-1 w-1.5 h-1.5" style={{ borderTop: '1px solid var(--border-accent)', borderLeft: '1px solid var(--border-accent)' }} />
                <span aria-hidden className="absolute bottom-1 right-1 w-1.5 h-1.5" style={{ borderBottom: '1px solid var(--border-accent)', borderRight: '1px solid var(--border-accent)' }} />
              </motion.div>

              <div className="flex flex-col gap-1.5">
                {/* breadcrumb chip */}
                <div className="flex items-center gap-2 text-[9.5px] font-mono uppercase tracking-[0.28em] text-text-muted">
                  <span>PULSE</span>
                  <span className="text-text-muted/50">/</span>
                  <span className="text-text-tertiary">Workspace</span>
                  <span className="text-text-muted/50">/</span>
                  <span className="text-gold/80">{activeLabel}</span>
                </div>
                <motion.h1
                  key={activeLabel}
                  initial={{ opacity: 0, y: 4 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.26, ease: [0.16, 1, 0.3, 1] }}
                  className="font-display font-black text-[30px] leading-none tracking-[0.22em] uppercase text-text-primary"
                  style={{ textShadow: '0 0 24px rgba(218,182,65,0.10)' }}
                >
                  {activeLabel}
                </motion.h1>
                <div className="flex items-center gap-3 text-[10px] font-mono text-text-muted uppercase tracking-[0.22em]">
                  <span className="flex items-center gap-1.5">
                    <span className="live-dot" />
                    {loading && !all ? 'initializing data layer…' : `${Object.keys(all ?? {}).length} streams active`}
                  </span>
                  <span className="text-text-muted/40">·</span>
                  <span>{lastUpdated ? `t-sync ${new Date(lastUpdated).toLocaleTimeString('en-US', { hour12: false })}` : 'awaiting sync'}</span>
                </div>
              </div>
            </div>
            <div className="flex items-center gap-3 text-[9.5px] font-mono text-text-tertiary tabular tracking-[0.24em] uppercase pb-1.5">
              <button
                onClick={() => setPaletteOpen(true)}
                className="flex items-center gap-2 px-2 py-1 rounded-md border border-border/40 bg-bg-card/40 hover:border-gold/40 hover:text-text-primary transition-colors group"
                title="Open command palette (Ctrl/Cmd+K)"
              >
                <kbd className="text-[9px] text-text-secondary group-hover:text-gold-bright transition-colors">⌘K</kbd>
                <span>command</span>
              </button>
              <div className="flex items-center gap-2">
                <kbd className="px-1.5 py-0.5 rounded border border-border/40 bg-bg-card/40 text-text-secondary text-[9px]">?</kbd>
                <span>shortcuts</span>
              </div>
            </div>
          </div>

          {/* Print-only daily sheet */}
          <DailySheet all={merged} tradeIdea={tradeIdea} />

          <div className="p-6 pb-12">
            <ErrorBoundary label={activeLabel}>
              {/* Per-view key remount with simple enter animation. Avoiding
                  AnimatePresence mode="wait" — nested motion children inside
                  the views don't always settle their exit cleanly, which can
                  wedge wait-mode and leave the old view mounted. Each view
                  owns its own enter/stagger choreography. */}
              <motion.div
                key={view}
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
              >
                <Suspense fallback={<ViewLoading />}>
                  {view === 'desk'          && <DeskView all={merged} history={history} tradeIdea={tradeIdea} onNavigate={setView} />}
                  {view === 'charts'        && <ChartsView all={merged} history={history} ohlcv={ohlcv} />}
                  {view === 'markets'       && <MarketsView all={merged} />}
                  {view === 'paper'         && <PaperView tradeIdea={tradeIdea} />}
                  {view === 'regime'        && <RegimeView />}
                  {view === 'inventory'     && <InventoryView all={merged} />}
                  {view === 'signals'       && <SignalLogView />}
                  {view === 'news'          && <NewsView />}
                </Suspense>
              </motion.div>
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

      {/* Pop-up alert toast stack — slides in when /api/alerts produces a new id */}
      <ToastStack
        alerts={Array.isArray(alerts) ? alerts : (alerts as any)?.alerts ?? []}
        news={merged?.news}
      />

      {/* Command palette — Cmd/Ctrl+K anywhere */}
      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} actions={paletteActions} />

      <HelpOverlay open={helpOpen} onClose={() => setHelpOpen(false)} />
    </div>
  );
}

function HelpOverlay({ open, onClose }: { open: boolean; onClose: () => void }) {
  if (!open) return null;
  const isMac = typeof navigator !== 'undefined' && /Mac/i.test(navigator.platform);
  const mod = isMac ? '⌘' : 'Ctrl';
  const rows: { keys: string; desc: string }[] = [
    { keys: `${mod}+K`,      desc: 'Command palette — jump anywhere, run anything' },
    { keys: '1 – 8',         desc: 'Switch tab (outside text inputs)' },
    { keys: `${mod}+1 – 8`,  desc: 'Switch tab (works inside inputs too)' },
    { keys: '/',             desc: 'Open Ask PULSE chat' },
    { keys: 'R',             desc: 'Refresh all data' },
    { keys: 'F',             desc: 'Toggle fullscreen' },
    { keys: 'P',             desc: 'Print daily briefing sheet' },
    { keys: '?',             desc: 'Toggle this help overlay' },
    { keys: 'Esc',           desc: 'Close help / modal' },
  ];
  return (
    <div className="fixed inset-0 z-[300] flex items-center justify-center" onClick={onClose}>
      <div className="absolute inset-0 bg-bg/80 backdrop-blur-sm" />
      <div
        className="relative bg-bg-surface border border-border rounded-lg shadow-2xl p-6 w-[420px] max-w-[calc(100vw-32px)]"
        onClick={e => e.stopPropagation()}
        role="dialog"
        aria-label="Keyboard shortcuts"
      >
        <div className="text-[10px] font-mono uppercase tracking-widest text-text-tertiary mb-1">Help</div>
        <h3 className="font-display font-bold tracking-wider text-lg uppercase text-text-primary mb-4">
          Keyboard shortcuts
        </h3>
        <table className="w-full text-[12px] font-mono tabular">
          <tbody>
            {rows.map(r => (
              <tr key={r.keys} className="border-b border-border/30 last:border-b-0">
                <td className="py-1.5 pr-4 text-text-primary whitespace-nowrap">
                  <kbd className="px-1.5 py-0.5 bg-bg-card/60 text-text-secondary rounded text-[11px]">{r.keys}</kbd>
                </td>
                <td className="py-1.5 text-text-tertiary">{r.desc}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="mt-4 text-right">
          <button
            onClick={onClose}
            className="text-[10px] font-mono uppercase tracking-widest text-text-tertiary hover:text-text-primary px-2 py-1"
          >
            Close (Esc)
          </button>
        </div>
      </div>
    </div>
  );
}
