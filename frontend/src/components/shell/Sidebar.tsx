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
} from 'lucide-react';

export type ViewKey = 'signal' | 'charts' | 'fundamentals' | 'intelligence' | 'spreads' | 'playbook' | 'paper' | 'regime';

export const NAV_ITEMS: { key: ViewKey; label: string; icon: any; hint: string }[] = [
  { key: 'signal',        label: 'Signal',           icon: Gauge,            hint: '1' },
  { key: 'charts',        label: 'Charts',           icon: CandlestickChart, hint: '2' },
  { key: 'fundamentals',  label: 'Fundamentals',     icon: Database,         hint: '3' },
  { key: 'intelligence',  label: 'Intelligence',     icon: Brain,            hint: '4' },
  { key: 'spreads',       label: 'Spreads & Curve',  icon: TrendingUp,       hint: '5' },
  { key: 'playbook',      label: 'Playbook',         icon: History,          hint: '6' },
  { key: 'paper',         label: 'Paper Trading',    icon: Wallet,           hint: '7' },
  { key: 'regime',        label: 'Regime',           icon: Radar,            hint: '8' },
];

export function Sidebar({ active, onSelect }: { active: ViewKey; onSelect: (k: ViewKey) => void }) {
  return (
    <motion.nav
      initial={{ opacity: 0, x: -8 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.36, ease: [0.16, 1, 0.3, 1] }}
      className="w-56 flex-shrink-0 bg-bg-elev/60 border-r border-border flex flex-col gap-1 p-3 relative z-20"
    >
      <div className="px-3 py-2 mb-2">
        <div className="text-[9px] font-mono tracking-[0.24em] text-text-muted uppercase">Workspace</div>
      </div>
      {NAV_ITEMS.map(item => {
        const Icon = item.icon;
        const isActive = active === item.key;
        return (
          <button
            key={item.key}
            onClick={() => onSelect(item.key)}
            className={clsx(
              'nav-item w-full text-left relative overflow-hidden',
              isActive && 'active bg-gold-soft',
              isActive && 'shadow-[inset_2px_0_0_#d4af37]',
            )}
          >
            <Icon className="nav-icon" strokeWidth={2} />
            <span className="nav-label flex-1">{item.label}</span>
            <kbd
              className={clsx(
                'text-[9px] font-mono px-1.5 py-0.5 rounded border',
                isActive ? 'border-gold/40 text-gold' : 'border-border text-text-muted',
              )}
            >
              {item.hint}
            </kbd>
          </button>
        );
      })}
      <div className="flex-1" />
      <div className="px-3 py-2 border-t border-border/60 mt-2">
        <div className="text-[9px] font-mono tracking-widest text-text-muted uppercase mb-1">Shortcuts</div>
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
