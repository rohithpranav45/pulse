import clsx from 'clsx';
import { motion } from 'framer-motion';
import {
  LayoutGrid,
  CandlestickChart,
  BarChart3,
  Wallet,
  Radar,
  ScrollText,
  Droplets,
  Newspaper,
  PanelLeftClose,
  PanelLeftOpen,
} from 'lucide-react';
import { useLocalStorage } from '@/lib/hooks';

export type ViewKey = 'desk' | 'charts' | 'markets' | 'paper' | 'regime' | 'signals' | 'inventory' | 'news';

// Phase 4.E — Intelligence tab cut entirely. Groq brief lives on DESK; the
// stumpy analogs / news / correlation widgets were not regime-model inputs.
export const NAV_ITEMS: { key: ViewKey; label: string; icon: any; hint: string; sub?: string }[] = [
  { key: 'desk',          label: 'Desk',             icon: LayoutGrid,       hint: '1', sub: 'Top of book' },
  { key: 'charts',        label: 'Charts',           icon: CandlestickChart, hint: '2', sub: 'Price action' },
  { key: 'markets',       label: 'Markets',          icon: BarChart3,        hint: '3', sub: 'Spreads · fundamentals' },
  { key: 'paper',         label: 'Paper Book',       icon: Wallet,           hint: '4', sub: 'Live P&L' },
  { key: 'regime',        label: 'Regime',           icon: Radar,            hint: '5', sub: 'Engine · A/B · drill' },
  { key: 'inventory',     label: 'Inventory',        icon: Droplets,         hint: '6', sub: 'EIA release framework' },
  { key: 'signals',       label: 'Signal Log',       icon: ScrollText,       hint: '7', sub: 'Realised performance' },
  { key: 'news',          label: 'News Impact',      icon: Newspaper,        hint: '8', sub: 'Headline → % move' },
];

export function Sidebar({ active, onSelect }: { active: ViewKey; onSelect: (k: ViewKey) => void }) {
  // Manual collapse (persisted). Even when expanded, the label column only
  // exists from lg: up — below that the sidebar is an icon rail automatically.
  const [collapsed, setCollapsed] = useLocalStorage<boolean>('pulse.sidebar.collapsed', false);
  // 'hidden lg:*' = responsive auto-rail below lg; plain 'hidden' = manual
  // collapse. Literal strings only — Tailwind's scanner can't see
  // interpolated class names.
  const L = {
    flex:        collapsed ? 'hidden' : 'hidden lg:flex',
    block:       collapsed ? 'hidden' : 'hidden lg:block',
    inline:      collapsed ? 'hidden' : 'hidden lg:inline',
    inlineBlock: collapsed ? 'hidden' : 'hidden lg:inline-block',
  };

  return (
    <motion.nav
      initial={{ opacity: 0, x: -6 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.36, ease: [0.16, 1, 0.3, 1] }}
      className={clsx(
        'flex-shrink-0 flex flex-col gap-0.5 px-2 py-4 relative z-20 transition-[width] duration-300',
        collapsed ? 'w-[64px]' : 'w-[64px] lg:w-60',
      )}
      style={{
        background: 'var(--sidebar-grad)',
        backdropFilter: 'blur(8px)',
        borderRight: '1px solid var(--hairline)',
      }}
    >
      {/* vertical gold accent rail at the right edge */}
      <div
        aria-hidden
        className="absolute top-0 right-0 bottom-0 w-px pointer-events-none"
        style={{ background: 'linear-gradient(180deg, transparent, var(--border-accent) 18%, var(--hairline) 50%, var(--border-accent) 82%, transparent)' }}
      />
      <div
        className={clsx('pb-3 mb-2 flex items-center', collapsed ? 'justify-center px-0' : 'justify-center lg:justify-between px-0 lg:px-3')}
        style={{ borderBottom: '1px solid var(--hairline)' }}
      >
        <div className={clsx('text-[9px] font-mono tracking-[0.30em] text-text-muted uppercase', L.block)}>Workspace</div>
        <div className="flex items-center gap-1">
          <span className="live-dot" />
          <span className={clsx('text-[8.5px] font-mono tracking-[0.20em] text-text-tertiary uppercase', L.inline)}>live</span>
        </div>
      </div>
      {NAV_ITEMS.map((item, i) => {
        const Icon = item.icon;
        const isActive = active === item.key;
        return (
          <motion.button
            key={item.key}
            onClick={() => onSelect(item.key)}
            initial={{ opacity: 0, x: -8 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.28, delay: 0.04 + i * 0.025, ease: [0.16, 1, 0.3, 1] }}
            whileHover={{ x: 2 }}
            title={`${item.label} (${item.hint})`}
            className={clsx(
              'nav-item w-full text-left',
              isActive && 'active',
              collapsed ? 'justify-center' : 'justify-center lg:justify-start',
            )}
          >
            <span
              className={clsx(
                'flex items-center justify-center w-7 h-7 rounded-md border transition-all flex-shrink-0',
                isActive ? 'text-gold-bright' : 'text-text-tertiary',
              )}
              style={
                isActive
                  ? {
                      background: 'rgb(var(--gold) / 0.14)',
                      borderColor: 'rgb(var(--gold) / 0.42)',
                      boxShadow: 'inset 0 0 0 1px rgba(255,255,255,0.04), 0 0 12px -4px var(--gold-glow)',
                    }
                  : {
                      background: 'transparent',
                      borderColor: 'var(--hairline-strong)',
                    }
              }
            >
              <Icon className="w-4 h-4" strokeWidth={2} />
            </span>
            <span className={clsx('flex-1 flex-col leading-tight gap-0.5 min-w-0', L.flex)}>
              <span className="nav-label truncate">{item.label}</span>
              {item.sub && (
                <span className={clsx(
                  'font-mono text-[8.5px] tracking-[0.14em] uppercase truncate',
                  isActive ? 'text-gold/65' : 'text-text-muted',
                )}>
                  {item.sub}
                </span>
              )}
            </span>
            <kbd
              className={clsx(
                'text-[9px] font-mono px-1.5 py-0.5 rounded border tabular',
                L.inlineBlock,
                isActive
                  ? 'text-gold-bright bg-gold/10 border-gold/30'
                  : 'text-text-muted bg-bg-card/40 border-border/50',
              )}
            >
              {item.hint}
            </kbd>
          </motion.button>
        );
      })}
      <div className="flex-1" />
      <div className={clsx('pt-3 mt-2', L.block, 'px-3')} style={{ borderTop: '1px solid var(--hairline)' }}>
        <div className="text-[9px] font-mono tracking-[0.24em] text-text-muted uppercase mb-2">Shortcuts</div>
        <div className="flex flex-col gap-1 text-[10px] font-mono text-text-tertiary">
          <div className="flex justify-between items-center"><span>Command</span><kbd className="text-text-secondary px-1 rounded bg-bg-card/40 border border-border/40 text-[9px]">⌘K</kbd></div>
          <div className="flex justify-between items-center"><span>Refresh</span><kbd className="text-text-secondary px-1 rounded bg-bg-card/40 border border-border/40 text-[9px]">R</kbd></div>
          <div className="flex justify-between items-center"><span>Fullscreen</span><kbd className="text-text-secondary px-1 rounded bg-bg-card/40 border border-border/40 text-[9px]">F</kbd></div>
          <div className="flex justify-between items-center"><span>Print sheet</span><kbd className="text-text-secondary px-1 rounded bg-bg-card/40 border border-border/40 text-[9px]">P</kbd></div>
          <div className="flex justify-between items-center"><span>Help</span><kbd className="text-text-secondary px-1 rounded bg-bg-card/40 border border-border/40 text-[9px]">?</kbd></div>
        </div>
        <div className="mt-4 pt-3 border-t border-border/40 flex items-center justify-between">
          <div className="flex flex-col leading-none gap-0.5">
            <span className="text-[8.5px] font-mono tracking-[0.22em] text-text-muted uppercase">Build</span>
            <span className="text-[10px] font-mono text-text-tertiary tabular">v2.2 · phase 8</span>
          </div>
          <span
            aria-hidden
            className="w-2 h-2 rounded-full"
            style={{ background: 'rgb(var(--gold))', boxShadow: '0 0 8px var(--gold-glow)' }}
          />
        </div>
      </div>
      {/* Collapse toggle — icon rail ⇄ full labels (persisted) */}
      <button
        onClick={() => setCollapsed(!collapsed)}
        title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        className={clsx(
          'mt-2 hidden lg:flex items-center gap-2 rounded-md py-2 text-text-muted hover:text-gold-bright hover:bg-gold/5 transition-colors',
          collapsed ? 'justify-center px-0' : 'justify-center lg:justify-start px-3',
        )}
      >
        {collapsed ? <PanelLeftOpen className="w-4 h-4" /> : <PanelLeftClose className="w-4 h-4" />}
        <span className={clsx('text-[9px] font-mono uppercase tracking-[0.22em]', L.inline)}>Collapse</span>
      </button>
    </motion.nav>
  );
}
