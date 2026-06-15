import clsx from 'clsx';
import { motion } from 'framer-motion';
import {
  Gauge,
  CandlestickChart,
  Database,
  Brain,
  TrendingUp,
  History,
  Wallet,
  Radar,
  ScrollText,
} from 'lucide-react';

export type ViewKey = 'signal' | 'charts' | 'fundamentals' | 'intelligence' | 'spreads' | 'playbook' | 'paper' | 'regime' | 'signals';

export const NAV_ITEMS: { key: ViewKey; label: string; icon: any; hint: string }[] = [
  { key: 'signal',        label: 'Signal',           icon: Gauge,            hint: '1' },
  { key: 'charts',        label: 'Charts',           icon: CandlestickChart, hint: '2' },
  { key: 'fundamentals',  label: 'Fundamentals',     icon: Database,         hint: '3' },
  { key: 'intelligence',  label: 'Intelligence',     icon: Brain,            hint: '4' },
  { key: 'spreads',       label: 'Spreads & Curve',  icon: TrendingUp,       hint: '5' },
  { key: 'playbook',      label: 'Playbook',         icon: History,          hint: '6' },
  { key: 'paper',         label: 'Paper Trading',    icon: Wallet,           hint: '7' },
  { key: 'regime',        label: 'Regime',           icon: Radar,            hint: '8' },
  { key: 'signals',       label: 'Signal Log',       icon: ScrollText,       hint: '9' },
];

export function Sidebar({ active, onSelect }: { active: ViewKey; onSelect: (k: ViewKey) => void }) {
  return (
    <motion.nav
      initial={{ opacity: 0, x: -6 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.36, ease: [0.16, 1, 0.3, 1] }}
      className="w-56 flex-shrink-0 bg-bg-elev/40 flex flex-col gap-0.5 px-2 py-4 relative z-20"
      style={{ borderRight: '1px solid rgba(255,255,255,0.05)' }}
    >
      <div className="px-3 pb-3 mb-2" style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
        <div className="text-[9px] font-mono tracking-[0.28em] text-text-muted uppercase">Workspace</div>
      </div>
      {NAV_ITEMS.map(item => {
        const Icon = item.icon;
        const isActive = active === item.key;
        return (
          <button
            key={item.key}
            onClick={() => onSelect(item.key)}
            className={clsx('nav-item w-full text-left', isActive && 'active')}
          >
            <Icon className="nav-icon" strokeWidth={2} />
            <span className="nav-label flex-1">{item.label}</span>
            <kbd
              className={clsx(
                'text-[9px] font-mono px-1.5 py-0.5 rounded',
                isActive
                  ? 'text-gold bg-gold/10'
                  : 'text-text-muted bg-bg-card/60',
              )}
            >
              {item.hint}
            </kbd>
          </button>
        );
      })}
      <div className="flex-1" />
      <div className="px-3 pt-3 mt-2" style={{ borderTop: '1px solid rgba(255,255,255,0.04)' }}>
        <div className="text-[9px] font-mono tracking-[0.22em] text-text-muted uppercase mb-2">Shortcuts</div>
        <div className="flex flex-col gap-1 text-[10px] font-mono text-text-tertiary">
          <div className="flex justify-between"><span>Refresh</span><kbd className="text-text-secondary">R</kbd></div>
          <div className="flex justify-between"><span>Fullscreen</span><kbd className="text-text-secondary">F</kbd></div>
          <div className="flex justify-between"><span>Print sheet</span><kbd className="text-text-secondary">P</kbd></div>
          <div className="flex justify-between"><span>Help</span><kbd className="text-text-secondary">?</kbd></div>
        </div>
      </div>
    </motion.nav>
  );
}
