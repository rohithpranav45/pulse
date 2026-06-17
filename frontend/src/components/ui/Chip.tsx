import { ReactNode } from 'react';
import clsx from 'clsx';

export type ChipTone = 'bull' | 'bear' | 'neut' | 'gold' | 'blue' | 'muted';

// Flat tone blocks with a subtle inner halo. Terminal aesthetic — no faux 3D.
const tones: Record<ChipTone, string> = {
  bull:  'bg-bull-soft text-bull border-bull/35 shadow-[inset_0_0_0_1px_rgba(22,224,158,0.08),0_0_10px_-4px_var(--bull-ring)]',
  bear:  'bg-bear-soft text-bear border-bear/35 shadow-[inset_0_0_0_1px_rgba(255,88,116,0.08),0_0_10px_-4px_var(--bear-ring)]',
  neut:  'bg-neut-soft text-neut border-neut/35 shadow-[inset_0_0_0_1px_rgba(247,172,51,0.08),0_0_10px_-4px_var(--neut-ring)]',
  gold:  'bg-gold-soft text-gold-bright border-gold/35 shadow-[inset_0_0_0_1px_rgba(218,182,65,0.10),0_0_12px_-4px_var(--gold-glow)]',
  blue:  'bg-accent-blue/10 text-accent-blue border-accent-blue/35 shadow-[inset_0_0_0_1px_rgba(92,158,255,0.08),0_0_10px_-4px_rgba(92,158,255,0.40)]',
  muted: 'bg-bg-card text-text-tertiary border-border',
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
        'inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md text-[10px] font-mono font-medium tracking-wider tabular border',
        tones[tone],
        className,
      )}
    >
      {icon && <span className="flex items-center">{icon}</span>}
      {children}
    </span>
  );
}
