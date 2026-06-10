import { ReactNode } from 'react';
import clsx from 'clsx';
import { motion } from 'framer-motion';
import { SourceTag } from '@/components/ui/SourceTag';
import type { SourceMeta } from '@/lib/provenance';
import { fadeUp } from '@/lib/motion';

type Props = {
  title?: string;
  subtitle?: string;
  right?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
  accent?: 'gold' | 'bull' | 'bear' | 'neut' | 'blue' | 'none';
  /** Optional provenance — registry key or full SourceMeta. Renders a credibility chip in the header. */
  source?: string | SourceMeta;
  /** ISO timestamp / epoch ms for the data shown — drives the "age" indicator on the source chip. */
  dataTimestamp?: string | number | null;
  /** Optional one-off note to append to the registry's honesty note */
  sourceNote?: string;
  /** Disable framer-motion mount (use when parent already orchestrates stagger via variants). */
  staticMount?: boolean;
};

export function Panel({
  title,
  subtitle,
  right,
  children,
  className,
  bodyClassName,
  accent = 'gold',
  source,
  dataTimestamp,
  sourceNote,
  staticMount,
}: Props) {
  const accentColor = {
    gold: 'rgba(212,175,55,0.45)',
    bull: 'rgba(16,217,151,0.55)',
    bear: 'rgba(255,77,109,0.55)',
    neut: 'rgba(245,166,35,0.55)',
    blue: 'rgba(77,142,255,0.55)',
    none: 'transparent',
  }[accent];

  const motionProps = staticMount
    ? {}
    : ({
        variants: fadeUp,
        initial: 'hidden' as const,
        animate: 'show' as const,
      });

  return (
    <motion.section
      {...motionProps}
      whileHover={{ y: -1, transition: { duration: 0.18, ease: [0.22, 1, 0.36, 1] } }}
      className={clsx('panel group', className)}
    >
      <div
        aria-hidden
        className="absolute inset-x-3 top-0 h-px pointer-events-none transition-opacity duration-300 group-hover:opacity-100 opacity-80"
        style={{ background: `linear-gradient(90deg, transparent, ${accentColor}, transparent)` }}
      />
      {(title || right || source) && (
        <div className="panel-hdr">
          <div className="flex items-baseline gap-2 min-w-0">
            {title && <h3 className="panel-title truncate">{title}</h3>}
            {subtitle && <span className="panel-sub truncate">{subtitle}</span>}
          </div>
          <div className="flex items-center gap-2 flex-shrink-0">
            {source && <SourceTag source={source} timestamp={dataTimestamp} note={sourceNote} />}
            {right}
          </div>
        </div>
      )}
      <div className={clsx('p-4', bodyClassName)}>{children}</div>
    </motion.section>
  );
}
