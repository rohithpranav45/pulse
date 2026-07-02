import { useEffect, useRef, useState } from 'react';
import { useClock, useTheme } from '@/lib/hooks';
import { fmt } from '@/lib/fmt';
import { Chip } from '@/components/ui/Chip';
import { TICKER_KEYS } from '@/lib/api';
import { Activity, RefreshCw, Maximize2, Printer, HelpCircle, Sun, Moon } from 'lucide-react';
import { motion } from 'framer-motion';
import { resetOnboarding } from '@/components/onboarding/OnboardingTour';
import { ProvenanceLegend } from '@/components/shell/ProvenanceLegend';
import { HealthPill } from '@/components/shell/HealthPill';
import clsx from 'clsx';

type Quote = { price: number; change_abs?: number; change_pct?: number };
type TickerData = Record<string, Quote>;

/** One ticker-tape cell — flashes green/red when the live price ticks. */
function TickerItem({ label, q, first }: { label: string; q?: Quote; first: boolean }) {
  const prev = useRef<number | null>(null);
  const [flash, setFlash] = useState<'up' | 'dn' | null>(null);
  const price = q?.price;

  useEffect(() => {
    if (typeof price !== 'number') return;
    if (prev.current !== null && price !== prev.current) {
      setFlash(price > prev.current ? 'up' : 'dn');
      const t = window.setTimeout(() => setFlash(null), 1250);
      prev.current = price;
      return () => window.clearTimeout(t);
    }
    prev.current = price;
  }, [price]);

  const chg = q?.change_pct ?? 0;
  const up = chg >= 0;
  return (
    <div
      className={clsx(
        'ticker-item hover:bg-gold/5 transition-colors group',
        !first && 'border-l border-border/40',
        flash === 'up' && 'animate-flash-up',
        flash === 'dn' && 'animate-flash-dn',
      )}
    >
      <span className="text-[8.5px] font-mono tracking-[0.22em] text-text-muted uppercase group-hover:text-text-tertiary transition-colors">{label}</span>
      <motion.span
        key={price ?? '—'}
        initial={{ opacity: 0.6 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.4 }}
        className={clsx('text-sm font-mono font-semibold tabular', q ? 'text-text-primary' : 'text-text-muted')}
      >
        {q ? fmt.price(q.price) : '—'}
      </motion.span>
      <span
        className={clsx(
          'text-[10px] font-mono font-semibold tabular px-1.5 py-0.5 rounded',
          up ? 'text-bull bg-bull/8' : 'text-bear bg-bear/8',
          q?.change_pct === undefined && 'opacity-0',
        )}
      >
        {up ? '▲' : '▼'} {q?.change_pct !== undefined ? `${Math.abs(q.change_pct).toFixed(2)}%` : ''}
      </span>
    </div>
  );
}

function TimeChip({ tz, label }: { tz: string; label: string }) {
  const now = useClock();
  return (
    <div className="flex flex-col items-center px-2.5">
      <span className="text-[8.5px] font-mono tracking-[0.24em] text-text-muted uppercase">{label}</span>
      <span className="text-[11px] font-mono text-text-secondary tabular leading-tight">{fmt.time(now, tz)}</span>
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
      MKT · {status.label}
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
      whileHover={{ y: -1, scale: 1.06 }}
      whileTap={{ scale: 0.94 }}
      transition={{ duration: 0.16, ease: [0.22, 1, 0.36, 1] }}
      className={clsx(
        'p-2 rounded-md text-text-tertiary hover:text-gold-bright transition-colors',
        'hover:bg-gold/8',
        className,
      )}
    >
      {children}
    </motion.button>
  );
}

function ThemeToggle() {
  const [theme, toggle] = useTheme();
  const dark = theme === 'dark';
  return (
    <IconButton onClick={toggle} title={dark ? 'Switch to light mode' : 'Switch to dark mode'}>
      <motion.span
        key={theme}
        initial={{ rotate: -90, opacity: 0, scale: 0.6 }}
        animate={{ rotate: 0, opacity: 1, scale: 1 }}
        transition={{ duration: 0.32, ease: [0.16, 1, 0.3, 1] }}
        className="block"
      >
        {dark ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
      </motion.span>
    </IconButton>
  );
}

export function TopBar({ ticker, onRefresh, refreshing }: { ticker: TickerData | null; onRefresh: () => void; refreshing?: boolean }) {
  return (
    <motion.header
      initial={{ opacity: 0, y: -8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
      className="h-16 flex-shrink-0 flex items-center px-5 gap-6 relative z-30"
      style={{
        background: 'var(--topbar-grad)',
        backdropFilter: 'blur(20px) saturate(140%)',
        WebkitBackdropFilter: 'blur(20px) saturate(140%)',
        borderBottom: '1px solid var(--hairline)',
      }}
    >
      {/* hairline gold accent at the bottom edge */}
      <div
        aria-hidden
        className="absolute bottom-0 left-0 right-0 h-px pointer-events-none"
        style={{ background: 'linear-gradient(90deg, transparent, var(--border-accent) 14%, rgba(218,182,65,0.6) 50%, var(--border-accent) 86%, transparent)' }}
      />
      {/* subtle scanline gradient overlay */}
      <div
        aria-hidden
        className="absolute inset-0 pointer-events-none opacity-40"
        style={{ background: 'radial-gradient(ellipse 30% 100% at 0% 50%, rgba(218,182,65,0.05), transparent 70%)' }}
      />

      {/* Logo */}
      <div className="flex items-center gap-3 flex-shrink-0 relative">
        <motion.div
          whileHover={{ rotate: -6, scale: 1.06 }}
          transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
          className="relative w-10 h-10 rounded-xl flex items-center justify-center"
          style={{
            background: 'linear-gradient(135deg, rgb(var(--gold-bright)), rgb(var(--gold)))',
            boxShadow: '0 8px 24px -8px var(--gold-glow-strong), 0 0 0 1px rgba(218,182,65,0.30), inset 0 1px 0 rgba(255,255,255,0.20)',
          }}
        >
          <Activity className="w-5 h-5 text-bg" strokeWidth={2.6} />
          {/* aura */}
          <span
            aria-hidden
            className="absolute -inset-2 rounded-2xl pointer-events-none"
            style={{ background: 'radial-gradient(circle, var(--gold-glow) 0%, transparent 70%)', filter: 'blur(8px)', opacity: 0.7 }}
          />
        </motion.div>
        <div className="flex flex-col leading-tight relative">
          <span
            className="font-display font-extrabold tracking-[0.34em] text-[18px] leading-none"
            style={{
              background: 'linear-gradient(180deg, rgb(var(--gold-bright)) 0%, rgb(var(--gold)) 100%)',
              WebkitBackgroundClip: 'text',
              backgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
              filter: 'drop-shadow(0 0 12px var(--gold-glow))',
            }}
          >
            PULSE
          </span>
          <span className="font-mono text-[8px] tracking-[0.30em] text-text-muted uppercase mt-0.5">Energy · Intel · Terminal</span>
        </div>
      </div>

      <span className="w-px h-8 bg-border" />

      {/* Ticker tape */}
      <div className="flex-1 flex items-center gap-0 overflow-hidden">
        {TICKER_KEYS.map(({ key, label }, idx) => (
          <TickerItem key={key} label={label} q={ticker?.[key]} first={idx === 0} />
        ))}
      </div>

      {/* Right cluster */}
      <div className="flex items-center gap-2 flex-shrink-0">
        <HealthPill />
        <MarketStatus />
        <div className="flex border-l border-border pl-2 ml-1">
          <TimeChip tz="America/New_York" label="NYC" />
          <TimeChip tz="Europe/London" label="LON" />
          <TimeChip tz="Asia/Singapore" label="SGP" />
        </div>
        <div className="flex items-center gap-0.5 pl-2 border-l border-border ml-1">
          <ThemeToggle />
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
