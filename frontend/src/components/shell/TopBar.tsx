import { useClock } from '@/lib/hooks';
import { fmt } from '@/lib/fmt';
import { Chip } from '@/components/ui/Chip';
import { TICKER_KEYS } from '@/lib/api';
import { Activity, RefreshCw, Maximize2, Printer, HelpCircle } from 'lucide-react';
import { motion } from 'framer-motion';
import { resetOnboarding } from '@/components/onboarding/OnboardingTour';
import { ProvenanceLegend } from '@/components/shell/ProvenanceLegend';
import { HealthPill } from '@/components/shell/HealthPill';
import clsx from 'clsx';

type Quote = { price: number; change_abs?: number; change_pct?: number };
type TickerData = Record<string, Quote>;

function TimeChip({ tz, label }: { tz: string; label: string }) {
  const now = useClock();
  return (
    <div className="flex flex-col items-center px-2">
      <span className="text-[9px] font-mono tracking-widest text-text-muted uppercase">{label}</span>
      <span className="text-[11px] font-mono text-text-secondary tabular">{fmt.time(now, tz)}</span>
    </div>
  );
}

function MarketStatus() {
  const now = useClock();
  const dow = now.getUTCDay();
  const h = now.getUTCHours();
  let status: { label: string; tone: 'bull' | 'neut' | 'bear' };
  if (dow === 0 || dow === 6) status = { label: 'WEEKEND', tone: 'bear' };
  else if (h >= 1 && h < 23) status = { label: 'OPEN', tone: 'bull' };
  else status = { label: 'CLOSED', tone: 'neut' };
  return (
    <Chip tone={status.tone} icon={<span className={status.tone === 'bull' ? 'live-dot' : ''} />}>
      MARKET · {status.label}
    </Chip>
  );
}

function IconButton({
  onClick,
  title,
  children,
  className,
}: {
  onClick: () => void;
  title: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <motion.button
      onClick={onClick}
      title={title}
      whileHover={{ y: -1, scale: 1.05 }}
      whileTap={{ scale: 0.95 }}
      transition={{ duration: 0.16, ease: [0.22, 1, 0.36, 1] }}
      className={clsx(
        'p-2 rounded-md text-text-tertiary hover:text-gold transition-colors',
        'hover:bg-bg-hover/60',
        className,
      )}
    >
      {children}
    </motion.button>
  );
}

export function TopBar({ ticker, onRefresh, refreshing }: { ticker: TickerData | null; onRefresh: () => void; refreshing?: boolean }) {
  return (
    <motion.header
      initial={{ opacity: 0, y: -8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
      className="h-16 flex-shrink-0 bg-bg-elev/80 backdrop-blur-xl border-b border-border flex items-center px-5 gap-6 relative z-30"
    >
      {/* Logo */}
      <div className="flex items-center gap-3 flex-shrink-0">
        <motion.div
          whileHover={{ rotate: -6, scale: 1.06 }}
          transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
          className="w-9 h-9 rounded-lg bg-gradient-to-br from-gold to-gold-bright flex items-center justify-center shadow-lg shadow-gold/30"
        >
          <Activity className="w-5 h-5 text-bg" strokeWidth={2.5} />
        </motion.div>
        <div className="flex flex-col leading-tight">
          <span className="font-display font-extrabold tracking-[0.32em] text-base text-gold">PULSE</span>
          <span className="font-mono text-[8px] tracking-[0.28em] text-text-muted uppercase">Energy Intelligence</span>
        </div>
      </div>

      {/* Ticker tape */}
      <div className="flex-1 flex items-center gap-1 overflow-hidden">
        {TICKER_KEYS.map(({ key, label }) => {
          const q = ticker?.[key];
          const chg = q?.change_pct ?? 0;
          const up = chg >= 0;
          return (
            <div key={key} className="ticker-item border-r border-border/60 last:border-r-0 hover:bg-bg-hover/30 transition-colors">
              <span className="text-[9px] font-mono tracking-widest text-text-tertiary uppercase">{label}</span>
              <motion.span
                key={q?.price ?? '—'}
                initial={{ opacity: 0.6 }}
                animate={{ opacity: 1 }}
                transition={{ duration: 0.4 }}
                className={clsx('text-sm font-mono font-semibold tabular', q ? 'text-text-primary' : 'text-text-muted')}
              >
                {q ? fmt.price(q.price) : '—'}
              </motion.span>
              <span className={clsx('text-[10px] font-mono tabular px-1', up ? 'text-bull' : 'text-bear')}>
                {q?.change_pct !== undefined ? fmt.pct(q.change_pct) : ''}
              </span>
            </div>
          );
        })}
      </div>

      {/* Right cluster */}
      <div className="flex items-center gap-2 flex-shrink-0">
        <HealthPill />
        <MarketStatus />
        <div className="flex border-l border-border pl-3 ml-1">
          <TimeChip tz="America/New_York" label="NYC" />
          <TimeChip tz="Europe/London" label="LON" />
          <TimeChip tz="Asia/Singapore" label="SGP" />
        </div>
        <div className="flex items-center gap-1 pl-2 border-l border-border ml-1">
          <IconButton onClick={onRefresh} title="Refresh all data (R)">
            <RefreshCw className={clsx('w-4 h-4', refreshing && 'animate-spin')} />
          </IconButton>
          <IconButton onClick={() => window.print()} title="Print daily briefing sheet (P)">
            <Printer className="w-4 h-4" />
          </IconButton>
          <IconButton onClick={() => document.documentElement.requestFullscreen?.()} title="Fullscreen (F)">
            <Maximize2 className="w-4 h-4" />
          </IconButton>
          <ProvenanceLegend />
          <IconButton onClick={() => resetOnboarding()} title="Restart onboarding tour">
            <HelpCircle className="w-4 h-4" />
          </IconButton>
        </div>
      </div>
    </motion.header>
  );
}
