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
    tone === 'gold' ? 'text-gold-bright' :
    'text-text-primary';
  const glow =
    tone === 'bull' ? 'drop-shadow(0 0 12px var(--bull-ring))' :
    tone === 'bear' ? 'drop-shadow(0 0 12px var(--bear-ring))' :
    tone === 'neut' ? 'drop-shadow(0 0 12px var(--neut-ring))' :
    tone === 'gold' ? 'drop-shadow(0 0 14px var(--gold-glow))' :
    undefined;
  return (
    <div className={clsx(
      'flex flex-col gap-1.5',
      align === 'right' && 'items-end',
      align === 'center' && 'items-center',
    )}>
      <div className="text-[9px] font-mono tracking-[0.22em] text-text-muted uppercase">{label}</div>
      <div
        className={clsx(
          'text-[24px] font-display font-extrabold tabular leading-none transition-colors duration-300',
          toneColor,
        )}
        style={glow ? { filter: glow } : undefined}
      >
        {value}
      </div>
      {sub && <div className="text-[10px] font-mono text-text-tertiary tabular leading-tight">{sub}</div>}
    </div>
  );
}
