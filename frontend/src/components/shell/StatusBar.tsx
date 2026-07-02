import { fmt } from '@/lib/fmt';
import { motion } from 'framer-motion';
import clsx from 'clsx';

export function StatusBar({
  fundamentals,
  curve,
  cracks,
  lastUpdated,
}: {
  fundamentals: any;
  curve: any;
  cracks: any;
  lastUpdated: number | null;
}) {
  const m1m2 = curve?.brent?.[0] && curve?.brent?.[1] ? curve.brent[0].price - curve.brent[1].price : null;
  const brtWti = curve?.brent?.[0] && curve?.wti?.[0] ? curve.brent[0].price - curve.wti[0].price : null;
  const inv = fundamentals?.eia?.crude?.deviation_pct ?? null;
  const cot = fundamentals?.cot?.managed_money_pct ?? null;
  const geo = fundamentals?.geo_risk?.score ?? null;
  const crack = cracks?.crack_321?.value ?? null;

  const Item = ({ label, value, tone }: { label: string; value: string; tone?: 'bull' | 'bear' | 'neut' }) => (
    <div className="flex items-baseline gap-1.5 transition-opacity hover:opacity-90">
      <span className="text-[9px] font-mono tracking-[0.18em] text-text-muted uppercase">{label}</span>
      <span className={clsx(
        'text-[10px] font-mono tabular font-medium',
        tone === 'bull' ? 'text-bull' : tone === 'bear' ? 'text-bear' : tone === 'neut' ? 'text-neut' : 'text-text-secondary'
      )}>{value}</span>
    </div>
  );

  return (
    <motion.footer
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.42, delay: 0.1, ease: [0.16, 1, 0.3, 1] }}
      className="h-8 flex-shrink-0 flex items-center px-5 gap-5 text-[10px] font-mono z-30 relative"
      style={{
        background: 'var(--topbar-grad)',
        backdropFilter: 'blur(20px) saturate(140%)',
        WebkitBackdropFilter: 'blur(20px) saturate(140%)',
        borderTop: '1px solid var(--hairline)',
      }}
    >
      <div
        aria-hidden
        className="absolute top-0 left-0 right-0 h-px pointer-events-none"
        style={{ background: 'linear-gradient(90deg, transparent, var(--border-accent) 12%, rgba(218,182,65,0.4) 50%, var(--border-accent) 88%, transparent)' }}
      />
      <span className="flex items-center gap-1.5">
        <span className="live-dot" />
        <span className="text-gold-bright tracking-[0.26em] text-[9px] uppercase font-semibold">LIVE</span>
      </span>
      <span className="w-px h-3 bg-border" />
      <Item label="M1–M2" value={m1m2 !== null ? fmt.signed(m1m2) : '—'} tone={m1m2 !== null ? (m1m2 > 0 ? 'bull' : 'bear') : undefined} />
      <Item label="BRT–WTI" value={brtWti !== null ? `$${brtWti.toFixed(2)}` : '—'} />
      <span className="hidden md:flex items-center gap-5">
        <Item label="3-2-1" value={crack !== null ? `$${crack.toFixed(2)}` : '—'} />
        <Item label="INV·DEV" value={inv !== null ? `${inv > 0 ? '+' : ''}${inv.toFixed(1)}%` : '—'} tone={inv !== null ? (inv > 0 ? 'bear' : 'bull') : undefined} />
      </span>
      <span className="hidden lg:flex items-center gap-5">
        <Item label="COT" value={cot !== null ? `${cot.toFixed(0)}%ile` : '—'} />
        <Item label="GEO·IDX" value={geo !== null ? geo.toFixed(0) : '—'} tone={geo !== null && geo > 60 ? 'bear' : undefined} />
      </span>
      <div className="flex-1" />
      <span className="text-text-muted tracking-wider">v2.2 · React</span>
      <span className="w-px h-3 bg-border" />
      <span className="text-text-tertiary">Updated {fmt.ago(lastUpdated)}</span>
    </motion.footer>
  );
}
