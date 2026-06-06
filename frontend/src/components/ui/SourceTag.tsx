import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import clsx from 'clsx';
import {
  ageString,
  freshness,
  kindColour,
  kindLabel,
  resolveSource,
  ttlLabel,
  type SourceMeta,
} from '@/lib/provenance';

type Props = {
  /** Key into SOURCES or a SourceMeta object */
  source: string | SourceMeta;
  /** Timestamp of the data this tag describes (ISO string or epoch ms) */
  timestamp?: string | number | null;
  /** Force-override the kind, e.g. switch to "fallback" when primary failed */
  overrideKind?: SourceMeta['kind'];
  /** Optional inline note that overrides the registry note (e.g. "Apify quota hit, NewsAPI in use") */
  note?: string;
  /** Compact mode: just the dot + label, no age */
  compact?: boolean;
  className?: string;
};

/**
 * Tiny credibility chip placed in panel headers. Dot colour = source kind.
 * Hover (or focus / click) opens a popover with full provenance: source name,
 * URL, refresh interval, age, kind explanation, honesty notes.
 *
 * Aesthetically minimal — 6.5px dot + small mono label. Designed to be glanceable
 * but unobtrusive in a dense terminal-style UI.
 */
export function SourceTag({ source, timestamp, overrideKind, note, compact, className }: Props) {
  const meta = resolveSource(source);
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<{ left: number; top: number } | null>(null);
  const ref = useRef<HTMLButtonElement | null>(null);

  if (!meta) return null;

  const kind = overrideKind ?? meta.kind;
  const col = kindColour(kind);
  const fresh = freshness(timestamp, meta.ttlSeconds);
  // If freshness is "stale" force amber dot regardless of kind
  const dotClass =
    fresh === 'stale'
      ? 'bg-bear animate-pulse'
      : fresh === 'aging'
      ? 'bg-neut'
      : col.dot;

  const openPopover = () => {
    const r = ref.current?.getBoundingClientRect();
    if (r) {
      // Anchor: prefer below-right; flip above if too close to viewport bottom
      const vh = window.innerHeight;
      const below = r.bottom + 8;
      const goAbove = vh - below < 280;
      setPos({
        left: Math.min(window.innerWidth - 340, Math.max(8, r.left)),
        top: goAbove ? Math.max(8, r.top - 280) : below,
      });
    }
    setOpen(true);
  };

  useEffect(() => {
    if (!open) return;
    const onScroll = () => setOpen(false);
    window.addEventListener('scroll', onScroll, true);
    return () => window.removeEventListener('scroll', onScroll, true);
  }, [open]);

  return (
    <>
      <button
        ref={ref}
        type="button"
        onMouseEnter={openPopover}
        onMouseLeave={() => setOpen(false)}
        onFocus={openPopover}
        onBlur={() => setOpen(false)}
        onClick={(e) => { e.stopPropagation(); openPopover(); }}
        className={clsx(
          'inline-flex items-center gap-1.5 px-1.5 py-[2px] rounded-sm',
          'text-[9px] font-mono uppercase tracking-widest',
          'text-text-tertiary hover:text-text-secondary',
          'border border-border/40 hover:border-border-strong/70',
          'bg-bg-card/30 hover:bg-bg-card/60',
          'transition-colors leading-none whitespace-nowrap',
          className,
        )}
        aria-label={`Data source: ${meta.fullName}`}
      >
        <span className={clsx('w-[6px] h-[6px] rounded-full flex-shrink-0', dotClass)} />
        <span className="truncate max-w-[110px]">{meta.label}</span>
        {!compact && (
          <span className="text-text-muted/80 tabular">· {ageString(timestamp)}</span>
        )}
      </button>

      {open && pos && createPortal(
        <div
          role="tooltip"
          className="fixed z-[100] w-[320px] bg-bg-elev/95 backdrop-blur-md border border-border-strong rounded-md shadow-2xl p-3 text-[11px] font-mono leading-relaxed pointer-events-none animate-fade-in"
          style={{ left: pos.left, top: pos.top, boxShadow: '0 8px 32px rgba(0,0,0,0.6)' }}
        >
          <div className="flex items-start gap-2 mb-2 pb-2 border-b border-border/50">
            <span className={clsx('w-2 h-2 rounded-full mt-1 flex-shrink-0', dotClass)} />
            <div className="min-w-0 flex-1">
              <div className={clsx('text-[10px] uppercase tracking-widest font-semibold', col.text)}>
                {kindLabel(kind)}
                {fresh === 'stale'  && <span className="text-bear ml-2">· STALE</span>}
                {fresh === 'aging'  && <span className="text-neut ml-2">· AGING</span>}
              </div>
              <div className="text-text-primary font-semibold text-[12px] mt-0.5 leading-tight">
                {meta.fullName}
              </div>
            </div>
          </div>

          <div className="grid grid-cols-[78px_1fr] gap-x-2 gap-y-1 text-text-tertiary">
            <span className="text-text-muted">Source</span>
            <span className="text-text-secondary truncate">{meta.label}</span>

            <span className="text-text-muted">Auth</span>
            <span className="text-text-secondary">
              {meta.auth === 'none' && 'public, no key'}
              {meta.auth === 'api-key' && 'API key required'}
              {meta.auth === 'scraped' && 'scraped (unofficial)'}
              {meta.auth === 'derived' && 'derived in-house'}
            </span>

            <span className="text-text-muted">Refresh</span>
            <span className="text-text-secondary tabular">every {ttlLabel(meta.ttlSeconds)}</span>

            <span className="text-text-muted">Last data</span>
            <span className="text-text-secondary tabular">
              {timestamp ? `${ageString(timestamp)}  ·  ${new Date(typeof timestamp === 'number' ? timestamp : timestamp).toLocaleString('en-US', { hour12: false })}` : 'unknown'}
            </span>

            {meta.backendFile && (
              <>
                <span className="text-text-muted">Fetcher</span>
                <span className="text-text-secondary truncate" title={meta.backendFile}>{meta.backendFile}</span>
              </>
            )}

            {meta.url && (
              <>
                <span className="text-text-muted">URL</span>
                <span className="text-blue-300 truncate" title={meta.url}>{meta.url}</span>
              </>
            )}
          </div>

          {(note ?? meta.notes) && (
            <div className="mt-2 pt-2 border-t border-border/50 text-text-tertiary text-[10.5px] leading-snug">
              <span className="text-neut font-semibold">⚠ honest note · </span>
              {note ?? meta.notes}
            </div>
          )}
        </div>,
        document.body,
      )}
    </>
  );
}
