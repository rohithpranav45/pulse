import { fmt } from '@/lib/fmt';
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
    <div className="flex items-baseline gap-1.5">
      <span className="text-[9px] font-mono tracking-widest text-text-muted uppercase">{label}</span>
      <span className={clsx(
        'text-[10px] font-mono tabular',
        tone === 'bull' ? 'text-bull' : tone === 'bear' ? 'text-bear' : tone === 'neut' ? 'text-neut' : 'text-text-secondary'
      )}>{value}</span>
    </div>
  );

  return (
    <footer className="h-7 flex-shrink-0 bg-bg-elev/80 border-t border-border flex items-center px-5 gap-5 text-[10px] font-mono z-30">
      <span className="flex items-center gap-1.5">
        <span className="live-dot" />
        <span className="text-text-secondary tracking-widest text-[9px] uppercase">LIVE</span>
      </span>
      <span className="w-px h-3 bg-border" />
      <Item label="M1–M2" value={m1m2 !== null ? fmt.signed(m1m2) : '—'} tone={m1m2 !== null ? (m1m2 > 0 ? 'bull' : 'bear') : undefined} />
      <Item label="BRT–WTI" value={brtWti !== null ? `$${brtWti.toFixed(2)}` : '—'} />
      <Item label="3-2-1" value={crack !== null ? `$${crack.toFixed(2)}` : '—'} />
      <Item label="INV·DEV" value={inv !== null ? `${inv > 0 ? '+' : ''}${inv.toFixed(1)}%` : '—'} tone={inv !== null ? (inv > 0 ? 'bear' : 'bull') : undefined} />
      <Item label="COT" value={cot !== null ? `${cot.toFixed(0)}%ile` : '—'} />
      <Item label="GEO·IDX" value={geo !== null ? geo.toFixed(0) : '—'} tone={geo !== null && geo > 60 ? 'bear' : undefined} />
      <div className="flex-1" />
      <span className="text-text-muted">v2.0 · React</span>
      <span className="w-px h-3 bg-border" />
      <span className="text-text-tertiary">Updated {fmt.ago(lastUpdated)}</span>
    </footer>
  );
}
