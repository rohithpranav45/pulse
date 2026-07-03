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
    <header className="relative flex flex-wrap items-end justify-between gap-x-6 gap-y-3 pb-4 animate-fade-in">
      {/* gold-fading hairline rule */}
      <div
        aria-hidden
        className="absolute bottom-0 left-0 right-0 h-px pointer-events-none"
        style={{ background: 'linear-gradient(90deg, var(--border-accent), var(--hairline) 45%, transparent 90%)' }}
      />
      <div className="min-w-0">
        <div className="flex items-center gap-2 text-[9px] font-mono uppercase tracking-[0.32em] text-gold/80">
          <span aria-hidden className="inline-block w-4 h-px bg-gold/60" />
          {eyebrow}
        </div>
        <h1
          className="font-display font-semibold text-[30px] leading-none text-text-primary tracking-wide mt-1"
          style={{ textShadow: '0 0 28px rgba(218,182,65,0.08)' }}
        >
          {title}
        </h1>
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
