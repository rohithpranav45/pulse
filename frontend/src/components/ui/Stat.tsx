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
    <div className={clsx(
      'flex flex-col gap-1',
      align === 'right' && 'items-end',
      align === 'center' && 'items-center',
    )}>
      <div className="text-[9.5px] font-mono tracking-[0.18em] text-text-tertiary uppercase">{label}</div>
      <div className={clsx(
        'text-[22px] font-display font-bold tabular leading-none',
        'transition-colors duration-300',
        toneColor,
      )}>
        {value}
      </div>
      {sub && <div className="text-[10px] font-mono text-text-muted tabular leading-tight">{sub}</div>}
    </div>
  );
}
