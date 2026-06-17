import { ReactNode, useEffect, useState } from 'react';
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
  /** Epoch ms of the last successful fetch — drives the "live · N s ago" chip. */
  lastSuccess?: number | null;
  /** Truthy if the most recent fetch failed — renders a red error pill. */
  fetchError?: unknown;
  /** When true, intensifies the accent treatment for hero/feature panels. */
  feature?: boolean;
};

function relAge(ms: number): string {
  if (ms < 0) return '0s';
  if (ms < 60_000) return `${Math.round(ms / 1000)}s`;
  if (ms < 3_600_000) return `${Math.round(ms / 60_000)}m`;
  return `${Math.round(ms / 3_600_000)}h`;
}

function LiveFetchChip({ lastSuccess, fetchError }: { lastSuccess?: number | null; fetchError?: unknown }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const t = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(t);
  }, []);
  if (!lastSuccess && !fetchError) return null;
  if (fetchError) {
    const msg = (fetchError as any)?.message ?? String(fetchError);
    return (
      <span
        title={`fetch failed: ${msg}`}
        className="text-[9px] font-mono uppercase tracking-widest px-1.5 py-0.5 rounded bg-bear/15 text-bear border border-bear/30"
      >
        ⚠ ERR
      </span>
    );
  }
  if (!lastSuccess) return null;
  const age = now - lastSuccess;
  const stale = age > 90_000;
  return (
    <span
      title={`Last successful fetch: ${new Date(lastSuccess).toLocaleTimeString('en-US', { hour12: false })}`}
      className={clsx(
        'text-[9px] font-mono uppercase tracking-widest px-1.5 py-0.5 rounded border',
        stale
          ? 'bg-neut/10 text-neut border-neut/30'
          : 'bg-bg-card/60 text-text-tertiary border-border/40',
      )}
    >
      {stale ? '◌' : '●'} {relAge(age)} ago
    </span>
  );
}

const ACCENTS: Record<NonNullable<Props['accent']>, { mid: string; soft: string }> = {
  gold: { mid: 'rgba(218,182,65,0.75)', soft: 'rgba(218,182,65,0.18)' },
  bull: { mid: 'rgba(22,224,158,0.78)', soft: 'rgba(22,224,158,0.18)' },
  bear: { mid: 'rgba(255,88,116,0.78)', soft: 'rgba(255,88,116,0.18)' },
  neut: { mid: 'rgba(247,172,51,0.78)', soft: 'rgba(247,172,51,0.18)' },
  blue: { mid: 'rgba(92,158,255,0.78)', soft: 'rgba(92,158,255,0.18)' },
  none: { mid: 'transparent', soft: 'transparent' },
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
  lastSuccess,
  fetchError,
  feature,
}: Props) {
  const { mid, soft } = ACCENTS[accent];

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
      className={clsx('panel group', feature && 'panel--feature', className)}
      style={
        feature
          ? ({
              ['--accent-mid' as any]: mid,
              ['--accent-soft' as any]: soft,
            } as React.CSSProperties)
          : undefined
      }
    >
      {/* Top accent — gradient bar that intensifies on hover */}
      <div
        aria-hidden
        className="absolute inset-x-0 top-0 h-px pointer-events-none transition-opacity duration-300 opacity-80 group-hover:opacity-100"
        style={{ background: `linear-gradient(90deg, transparent 4%, ${mid} 50%, transparent 96%)` }}
      />
      {/* Corner ticks — confident terminal-grade detail */}
      <span
        aria-hidden
        className="absolute top-1.5 left-1.5 w-2 h-2 pointer-events-none opacity-60 group-hover:opacity-100 transition-opacity"
        style={{ borderTop: `1px solid ${mid}`, borderLeft: `1px solid ${mid}` }}
      />
      <span
        aria-hidden
        className="absolute top-1.5 right-1.5 w-2 h-2 pointer-events-none opacity-60 group-hover:opacity-100 transition-opacity"
        style={{ borderTop: `1px solid ${mid}`, borderRight: `1px solid ${mid}` }}
      />
      {/* Soft glow behind feature panels */}
      {feature && (
        <div
          aria-hidden
          className="absolute -inset-px rounded-[10px] pointer-events-none"
          style={{ boxShadow: `0 0 40px -8px ${soft}, 0 0 0 1px ${soft} inset` }}
        />
      )}
      {(title || right || source || lastSuccess || fetchError) && (
        <div className="panel-hdr">
          <div className="flex items-baseline gap-2 min-w-0">
            {/* Accent dot anchoring the title */}
            <span
              aria-hidden
              className="w-1.5 h-1.5 rounded-full self-center mr-0.5"
              style={{ background: mid, boxShadow: `0 0 6px ${mid}` }}
            />
            {title && <h3 className="panel-title truncate">{title}</h3>}
            {subtitle && (
              <>
                <span className="text-text-muted/40 text-[10px] font-mono">/</span>
                <span className="panel-sub truncate">{subtitle}</span>
              </>
            )}
          </div>
          <div className="flex items-center gap-2 flex-shrink-0">
            <LiveFetchChip lastSuccess={lastSuccess} fetchError={fetchError} />
            {source && <SourceTag source={source} timestamp={dataTimestamp} note={sourceNote} />}
            {right}
          </div>
        </div>
      )}
      <div className={clsx('p-4', bodyClassName)}>{children}</div>
    </motion.section>
  );
}
