import { useEffect, useMemo, useRef, useState } from 'react';
import clsx from 'clsx';
import { motion, AnimatePresence } from 'framer-motion';
import { Search, CornerDownLeft } from 'lucide-react';

export type PaletteAction = {
  id: string;
  label: string;
  group: string;          // section heading, e.g. 'Navigate' | 'Actions'
  sub?: string;           // muted description on the right
  hint?: string;          // kbd hint, e.g. '1' or 'R'
  icon?: any;             // lucide icon component
  run: () => void;
};

/**
 * Fuzzy match: every query char must appear in order in the target.
 * Score favours prefix + contiguous matches; returns -1 on no match.
 */
function fuzzyScore(target: string, query: string): number {
  const t = target.toLowerCase();
  const q = query.toLowerCase().trim();
  if (!q) return 0;
  if (t.startsWith(q)) return 100 - t.length;
  if (t.includes(q)) return 60 - t.indexOf(q);
  let ti = 0;
  let streak = 0;
  let score = 0;
  for (const ch of q) {
    const found = t.indexOf(ch, ti);
    if (found === -1) return -1;
    streak = found === ti ? streak + 1 : 1;
    score += streak * 2;
    ti = found + 1;
  }
  return score;
}

export function CommandPalette({
  open,
  onClose,
  actions,
}: {
  open: boolean;
  onClose: () => void;
  actions: PaletteAction[];
}) {
  const [query, setQuery] = useState('');
  const [sel, setSel] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  // Reset + focus when opened
  useEffect(() => {
    if (open) {
      setQuery('');
      setSel(0);
      setTimeout(() => inputRef.current?.focus(), 30);
    }
  }, [open]);

  // Window-level Escape — closes even when focus has left the search input.
  useEffect(() => {
    if (!open) return;
    const onEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { e.preventDefault(); onClose(); }
    };
    window.addEventListener('keydown', onEsc);
    return () => window.removeEventListener('keydown', onEsc);
  }, [open, onClose]);

  const filtered = useMemo(() => {
    if (!query.trim()) return actions;
    return actions
      .map(a => ({ a, s: Math.max(fuzzyScore(a.label, query), fuzzyScore(`${a.group} ${a.sub ?? ''}`, query) - 20) }))
      .filter(x => x.s >= 0)
      .sort((x, y) => y.s - x.s)
      .map(x => x.a);
  }, [actions, query]);

  // Clamp selection when the list changes
  useEffect(() => {
    setSel(s => Math.min(s, Math.max(0, filtered.length - 1)));
  }, [filtered.length]);

  // Keep the selected row in view
  useEffect(() => {
    const el = listRef.current?.querySelector<HTMLElement>(`[data-idx="${sel}"]`);
    el?.scrollIntoView({ block: 'nearest' });
  }, [sel]);

  const runAction = (a: PaletteAction | undefined) => {
    if (!a) return;
    onClose();
    // Let the palette close before the action fires (fullscreen/print need focus back)
    setTimeout(() => a.run(), 10);
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setSel(s => Math.min(s + 1, filtered.length - 1)); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setSel(s => Math.max(s - 1, 0)); }
    else if (e.key === 'Enter') { e.preventDefault(); runAction(filtered[sel]); }
    else if (e.key === 'Escape') { e.preventDefault(); onClose(); }
  };

  // Rows with group headings interleaved (groups keep the filtered order)
  const rows: ({ type: 'heading'; label: string } | { type: 'item'; action: PaletteAction; idx: number })[] = [];
  {
    let lastGroup: string | null = null;
    filtered.forEach((a, idx) => {
      if (a.group !== lastGroup) {
        rows.push({ type: 'heading', label: a.group });
        lastGroup = a.group;
      }
      rows.push({ type: 'item', action: a, idx });
    });
  }

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.16 }}
          className="fixed inset-0 z-[320] flex items-start justify-center pt-[14vh]"
          onClick={onClose}
        >
          <div className="absolute inset-0 bg-bg/70 backdrop-blur-sm" />
          <motion.div
            initial={{ opacity: 0, y: -10, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -6, scale: 0.99 }}
            transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
            className="relative w-[560px] max-w-[calc(100vw-32px)] rounded-xl overflow-hidden"
            style={{
              background: 'var(--panel-bg)',
              border: '1px solid var(--border-strong)',
              boxShadow: '0 32px 90px -20px rgba(0,0,0,0.7), 0 0 0 1px rgba(218,182,65,0.10), 0 0 60px -20px var(--gold-glow)',
              backdropFilter: 'blur(24px) saturate(150%)',
              WebkitBackdropFilter: 'blur(24px) saturate(150%)',
            }}
            onClick={e => e.stopPropagation()}
            role="dialog"
            aria-label="Command palette"
          >
            {/* gold hairline on top */}
            <div
              aria-hidden
              className="absolute top-0 inset-x-0 h-px"
              style={{ background: 'linear-gradient(90deg, transparent, rgba(218,182,65,0.6) 50%, transparent)' }}
            />
            {/* Search input */}
            <div className="flex items-center gap-3 px-4 py-3.5" style={{ borderBottom: '1px solid var(--hairline-strong)' }}>
              <Search className="w-4 h-4 text-gold flex-shrink-0" strokeWidth={2.4} />
              <input
                ref={inputRef}
                value={query}
                onChange={e => { setQuery(e.target.value); setSel(0); }}
                onKeyDown={onKeyDown}
                placeholder="Jump to a workspace or run an action…"
                className="flex-1 bg-transparent outline-none text-[13px] font-mono text-text-primary placeholder:text-text-muted"
                spellCheck={false}
              />
              <kbd className="text-[9px] font-mono px-1.5 py-0.5 rounded border border-border/50 bg-bg-card/50 text-text-muted uppercase tracking-widest">
                esc
              </kbd>
            </div>

            {/* Results */}
            <div ref={listRef} className="max-h-[46vh] overflow-y-auto py-1.5">
              {filtered.length === 0 && (
                <div className="px-4 py-8 text-center text-[11px] font-mono text-text-muted uppercase tracking-widest">
                  No matches for “{query}”
                </div>
              )}
              {rows.map((r, i) =>
                r.type === 'heading' ? (
                  <div
                    key={`h-${r.label}-${i}`}
                    className="px-4 pt-2.5 pb-1 text-[8.5px] font-mono uppercase tracking-[0.28em] text-text-muted"
                  >
                    {r.label}
                  </div>
                ) : (
                  <button
                    key={r.action.id}
                    data-idx={r.idx}
                    onClick={() => runAction(r.action)}
                    onMouseMove={() => setSel(r.idx)}
                    className={clsx(
                      'w-full flex items-center gap-3 px-4 py-2 text-left transition-colors relative',
                      r.idx === sel ? 'bg-gold/10' : 'hover:bg-bg-hover/40',
                    )}
                  >
                    {r.idx === sel && (
                      <span
                        aria-hidden
                        className="absolute left-0 top-1 bottom-1 w-0.5 rounded-r"
                        style={{ background: 'rgb(var(--gold))', boxShadow: '0 0 8px var(--gold-glow-strong)' }}
                      />
                    )}
                    {r.action.icon && (
                      <span
                        className={clsx(
                          'flex items-center justify-center w-6 h-6 rounded-md border flex-shrink-0 transition-colors',
                          r.idx === sel
                            ? 'text-gold-bright border-gold/40 bg-gold/10'
                            : 'text-text-tertiary border-border/50 bg-bg-card/40',
                        )}
                      >
                        <r.action.icon className="w-3.5 h-3.5" strokeWidth={2.2} />
                      </span>
                    )}
                    <span className={clsx(
                      'flex-1 text-[12px] font-display font-semibold uppercase tracking-[0.14em] truncate',
                      r.idx === sel ? 'text-text-primary' : 'text-text-secondary',
                    )}>
                      {r.action.label}
                    </span>
                    {r.action.sub && (
                      <span className="text-[9.5px] font-mono text-text-muted truncate max-w-[180px]">
                        {r.action.sub}
                      </span>
                    )}
                    {r.action.hint && (
                      <kbd className={clsx(
                        'text-[9px] font-mono px-1.5 py-0.5 rounded border tabular flex-shrink-0',
                        r.idx === sel
                          ? 'text-gold-bright bg-gold/10 border-gold/30'
                          : 'text-text-muted bg-bg-card/40 border-border/50',
                      )}>
                        {r.action.hint}
                      </kbd>
                    )}
                  </button>
                ),
              )}
            </div>

            {/* Footer */}
            <div
              className="flex items-center gap-4 px-4 py-2 text-[9px] font-mono text-text-muted uppercase tracking-widest"
              style={{ borderTop: '1px solid var(--hairline)' }}
            >
              <span className="flex items-center gap-1"><kbd className="px-1 rounded bg-bg-card/50 border border-border/40">↑↓</kbd> navigate</span>
              <span className="flex items-center gap-1"><CornerDownLeft className="w-2.5 h-2.5" /> run</span>
              <span className="flex-1" />
              <span className="text-gold/70">PULSE command</span>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
