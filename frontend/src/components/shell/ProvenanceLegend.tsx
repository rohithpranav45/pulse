import { useEffect, useMemo, useState } from 'react';
import { ShieldCheck, X, Search } from 'lucide-react';
import { SOURCES, kindColour, kindLabel, ttlLabel, type SourceKind } from '@/lib/provenance';

/**
 * Top-bar button → modal with every data source the dashboard touches.
 * Single audit surface: every number on the screen traces back to one entry.
 */
export function ProvenanceLegend() {
  const [open, setOpen]   = useState(false);
  const [query, setQuery] = useState('');

  // ESC closes the modal — was missing in v1.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open]);

  const grouped = useMemo(() => {
    const g: Record<SourceKind, typeof SOURCES[string][]> = {
      live: [], cached: [], model: [], estimate: [], hardcoded: [], fallback: [],
    };
    const q = query.trim().toLowerCase();
    for (const s of Object.values(SOURCES)) {
      if (q && !(
        s.label.toLowerCase().includes(q) ||
        s.fullName.toLowerCase().includes(q) ||
        (s.notes ?? '').toLowerCase().includes(q) ||
        (s.backendFile ?? '').toLowerCase().includes(q)
      )) continue;
      const kind = s.kind as SourceKind;
      (g[kind] ?? g.cached).push(s);
    }
    // Alphabetical inside each bucket
    for (const k of Object.keys(g) as SourceKind[]) {
      g[k].sort((a, b) => a.fullName.localeCompare(b.fullName));
    }
    return g;
  }, [query]);

  const order: SourceKind[] = ['live', 'cached', 'model', 'estimate', 'hardcoded', 'fallback'];
  const kindExplain: Record<SourceKind, string> = {
    live:      'Fetched live from a public API at the listed interval. Ground truth, subject to upstream availability.',
    cached:    'Stored locally (SQLite / static file) and refreshed on schedule. May lag real-time by up to one refresh cycle.',
    model:     'Output of an in-house calculation or scoring engine. Only as good as the upstream inputs.',
    estimate:  'Derived heuristic, not a real measurement. Use as a directional indicator only.',
    hardcoded: 'Values baked into the codebase and updated manually. Treat as a snapshot, not live data.',
    fallback:  'Primary source failed — using degraded backup. Verify before acting on it.',
  };

  const totalShown = (Object.values(grouped) as any[]).reduce((s, arr) => s + arr.length, 0);

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        title="Data sources & credibility (every panel's provenance)"
        className="p-2 rounded hover:bg-bg-hover text-text-tertiary hover:text-gold transition-colors"
      >
        <ShieldCheck className="w-4 h-4" />
      </button>

      {open && (
        <div
          className="fixed inset-0 z-[200] bg-black/65 backdrop-blur-sm flex items-center justify-center p-4 animate-fade-in"
          onClick={() => setOpen(false)}
        >
          <div
            className="bg-bg-elev border border-border-strong rounded-lg shadow-2xl w-full max-w-3xl max-h-[88vh] overflow-hidden flex flex-col"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Header */}
            <div className="px-5 py-4 border-b border-border flex items-center justify-between flex-shrink-0">
              <div>
                <h2 className="font-display font-extrabold text-lg tracking-[0.18em] uppercase text-gold">
                  Data Source Ledger
                </h2>
                <p className="text-[11px] font-mono text-text-tertiary mt-0.5">
                  Every data origin, refresh interval, and honest caveat. Search to drill in.
                </p>
              </div>
              <button
                onClick={() => setOpen(false)}
                aria-label="Close"
                className="p-1.5 rounded hover:bg-bg-hover text-text-tertiary hover:text-text-primary transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Search */}
            <div className="px-5 py-2.5 border-b border-border/60 flex-shrink-0 flex items-center gap-2">
              <Search className="w-3.5 h-3.5 text-text-muted" />
              <input
                autoFocus
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search by source, file, or note…"
                className="flex-1 bg-transparent text-[12px] font-mono text-text-primary placeholder:text-text-muted outline-none"
              />
              {query && (
                <button
                  onClick={() => setQuery('')}
                  className="text-text-muted hover:text-text-primary text-[10px] font-mono"
                >
                  clear
                </button>
              )}
            </div>

            {/* Body */}
            <div className="overflow-y-auto p-5 space-y-5 text-[11px] font-mono">
              {totalShown === 0 ? (
                <div className="text-center py-10 text-text-muted">
                  No sources match <span className="text-gold">"{query}"</span>
                </div>
              ) : order.map((k) => {
                const items = grouped[k];
                if (!items.length) return null;
                const col = kindColour(k);
                return (
                  <section key={k}>
                    <div className="flex items-baseline gap-2 mb-2 pb-2 border-b border-border/40">
                      <span className={`w-2 h-2 rounded-full flex-shrink-0 ${col.dot}`} />
                      <h3 className={`text-[11px] tracking-widest uppercase font-bold flex-shrink-0 ${col.text}`}>
                        {kindLabel(k)} · {items.length}
                      </h3>
                      <span className="text-text-muted text-[10px] leading-snug">{kindExplain[k]}</span>
                    </div>
                    <div className="grid grid-cols-1 gap-y-3">
                      {items.map((s) => (
                        <div key={s.key} className="border-l-2 border-border/40 pl-3">
                          <div className="flex items-baseline justify-between gap-2 flex-wrap">
                            <span className="text-text-primary font-semibold">
                              <span className={col.text + ' mr-2'}>·</span>{s.fullName}
                            </span>
                            <span className="text-text-muted tabular flex-shrink-0">every {ttlLabel(s.ttlSeconds)}</span>
                          </div>
                          <div className="text-text-tertiary text-[10px] mt-1 flex flex-wrap gap-x-3 gap-y-0.5">
                            <span title={s.backendFile}>
                              <span className="text-text-muted">file:</span> {s.backendFile ?? '—'}
                            </span>
                            <span><span className="text-text-muted">auth:</span> {s.auth}</span>
                            {s.url && (
                              <a
                                href={s.url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="text-blue-300 hover:text-blue-200 underline-offset-2 hover:underline truncate max-w-[260px]"
                                onClick={(e) => e.stopPropagation()}
                              >
                                {s.url}
                              </a>
                            )}
                          </div>
                          {s.notes && (
                            <div className="text-text-muted/90 text-[10px] mt-1.5 leading-snug italic">
                              {s.notes}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </section>
                );
              })}
            </div>

            {/* Footer */}
            <div className="px-5 py-3 border-t border-border bg-bg-card/40 text-[10px] font-mono text-text-tertiary flex items-center justify-between flex-shrink-0">
              <span>{Object.keys(SOURCES).length} sources tracked · {totalShown} shown</span>
              <span className="text-text-muted">esc / click outside to close</span>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
