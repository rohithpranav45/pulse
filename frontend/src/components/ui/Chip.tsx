import { ReactNode } from 'react';
import clsx from 'clsx';

export type ChipTone = 'bull' | 'bear' | 'neut' | 'gold' | 'blue' | 'muted';

const tones: Record<ChipTone, string> = {
  bull: 'bg-bull-soft text-bull border border-bull/30',
  bear: 'bg-bear-soft text-bear border border-bear/30',
  neut: 'bg-neut-soft text-neut border border-neut/30',
  gold: 'bg-gold-soft text-gold border border-gold/30',
  blue: 'bg-accent-blue/10 text-accent-blue border border-accent-blue/30',
  muted: 'bg-bg-card text-text-tertiary border border-border',
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
        'inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[10px] font-mono font-medium tracking-wider tabular',
        tones[tone],
        className,
      )}
    >
      {icon && <span className="flex items-center">{icon}</span>}
      {children}
    </span>
  );
}
