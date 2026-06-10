import { ReactNode } from 'react';
import clsx from 'clsx';

export type ChipTone = 'bull' | 'bear' | 'neut' | 'gold' | 'blue' | 'muted';

const tones: Record<ChipTone, string> = {
  bull:  'bg-gradient-to-b from-bull-soft to-bull-soft/60 text-bull border border-bull/40 shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]',
  bear:  'bg-gradient-to-b from-bear-soft to-bear-soft/60 text-bear border border-bear/40 shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]',
  neut:  'bg-gradient-to-b from-neut-soft to-neut-soft/60 text-neut border border-neut/40 shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]',
  gold:  'bg-gradient-to-b from-gold-soft to-gold-soft/60 text-gold border border-gold/40 shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]',
  blue:  'bg-gradient-to-b from-accent-blue/15 to-accent-blue/5 text-accent-blue border border-accent-blue/40 shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]',
  muted: 'bg-bg-card/80 text-text-tertiary border border-border',
};

export function Chip({
  tone = 'muted',
  children,
  icon,
  className,
}: {
  tone?: ChipTone;
  children: ReactNode;
  icon?: ReactNode;
  className?: string;
}) {
  return (
    <span
      className={clsx(
        'inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md text-[10px] font-mono font-medium tracking-wider tabular',
        'transition-all duration-200',
        tones[tone],
        className,
      )}
    >
      {icon && <span className="flex items-center">{icon}</span>}
      {children}
    </span>
  );
}
