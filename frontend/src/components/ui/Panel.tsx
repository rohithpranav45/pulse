import { ReactNode } from 'react';
import clsx from 'clsx';

type Props = {
  title?: string;
  subtitle?: string;
  right?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
  accent?: 'gold' | 'bull' | 'bear' | 'neut' | 'blue' | 'none';
};

export function Panel({ title, subtitle, right, children, className, bodyClassName, accent = 'gold' }: Props) {
  const accentColor = {
    gold: 'rgba(212,175,55,0.45)',
    bull: 'rgba(16,217,151,0.55)',
    bear: 'rgba(255,77,109,0.55)',
    neut: 'rgba(245,166,35,0.55)',
    blue: 'rgba(77,142,255,0.55)',
    none: 'transparent',
  }[accent];

  return (
    <section className={clsx('panel animate-fade-in', className)}>
      <div
        aria-hidden
        className="absolute inset-x-3 top-0 h-px pointer-events-none"
        style={{ background: `linear-gradient(90deg, transparent, ${accentColor}, transparent)` }}
      />
      {(title || right) && (
        <div className="panel-hdr">
          <div className="flex items-baseline gap-2 min-w-0">
            {title && <h3 className="panel-title truncate">{title}</h3>}
            {subtitle && <span className="panel-sub truncate">{subtitle}</span>}
          </div>
          {right && <div className="flex items-center gap-2 flex-shrink-0">{right}</div>}
        </div>
      )}
      <div className={clsx('p-4', bodyClassName)}>{children}</div>
    </section>
  );
}
