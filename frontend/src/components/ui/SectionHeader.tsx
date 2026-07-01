import type { ReactNode } from 'react';
import clsx from 'clsx';

/**
 * Shared page + section headers — consistent, polished framing across tabs.
 *   PageHeader    — the tab hero: eyebrow + display title + description + badges.
 *   SectionHeader — an in-tab group divider: accent bar + eyebrow + title + desc.
 */

type Accent = 'gold' | 'blue' | 'bull' | 'bear' | 'neut';

const BAR: Record<Accent, string> = {
  gold: 'bg-gold/70', blue: 'bg-accent-blue/70', bull: 'bg-bull/70',
  bear: 'bg-bear/70', neut: 'bg-neut/70',
};
const EYEBROW: Record<Accent, string> = {
  gold: 'text-gold/80', blue: 'text-accent-blue/80', bull: 'text-bull/80',
  bear: 'text-bear/80', neut: 'text-neut/80',
};

export function PageHeader({ eyebrow, title, desc, badges }: {
  eyebrow: string; title: string; desc?: ReactNode; badges?: ReactNode;
}) {
  return (
    <header className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3 border-b border-border/50 pb-4 animate-fade-in">
      <div className="min-w-0">
        <div className="text-[9px] font-mono uppercase tracking-[0.32em] text-gold/80">{eyebrow}</div>
        <h1 className="font-display text-[27px] leading-none text-text-primary tracking-wide mt-0.5">{title}</h1>
        {desc && (
          <p className="text-[11px] font-mono text-text-tertiary leading-relaxed max-w-3xl mt-1.5">{desc}</p>
        )}
      </div>
      {badges && <div className="flex items-center gap-2 shrink-0">{badges}</div>}
    </header>
  );
}

export function SectionHeader({ eyebrow, title, desc, accent = 'gold', right }: {
  eyebrow: string; title: string; desc?: ReactNode; accent?: Accent; right?: ReactNode;
}) {
  return (
    <div className="flex items-stretch gap-3 pt-1 animate-fade-in">
      <div className={clsx('w-[3px] rounded-full shrink-0', BAR[accent])} />
      <div className="min-w-0 flex-1">
        <div className={clsx('text-[9px] font-mono uppercase tracking-[0.28em]', EYEBROW[accent])}>{eyebrow}</div>
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <h2 className="font-display text-[18px] leading-tight text-text-primary tracking-wide">{title}</h2>
          {right}
        </div>
        {desc && (
          <p className="text-[10.5px] font-mono text-text-tertiary leading-relaxed max-w-4xl mt-0.5">{desc}</p>
        )}
      </div>
    </div>
  );
}
