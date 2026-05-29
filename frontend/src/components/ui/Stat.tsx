import { ReactNode } from 'react';
import clsx from 'clsx';

export function Stat({
  label,
  value,
  sub,
  tone,
  align = 'left',
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  tone?: 'bull' | 'bear' | 'neut' | 'gold';
  align?: 'left' | 'right' | 'center';
}) {
  const toneColor =
    tone === 'bull' ? 'text-bull' :
    tone === 'bear' ? 'text-bear' :
    tone === 'neut' ? 'text-neut' :
    tone === 'gold' ? 'text-gold' :
    'text-text-primary';
  return (
    <div className={clsx('flex flex-col gap-0.5', align === 'right' && 'items-end', align === 'center' && 'items-center')}>
      <div className="text-[10px] font-mono tracking-wider text-text-tertiary uppercase">{label}</div>
      <div className={clsx('text-xl font-display font-bold tabular leading-none', toneColor)}>{value}</div>
      {sub && <div className="text-[10px] font-mono text-text-muted tabular">{sub}</div>}
    </div>
  );
}
