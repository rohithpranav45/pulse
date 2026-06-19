import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Activity, AlertTriangle, XCircle, CheckCircle2 } from 'lucide-react';
import clsx from 'clsx';
import { api } from '@/lib/api';
import { usePolling } from '@/lib/hooks';

/**
 * Live stream-health indicator.
 *
 *   ● 32/32 streams up         (all good — quiet green)
 *   ▲ 28/32 · 4 stale          (amber, click for drill)
 *   ✕ 30/32 · 2 down           (red, pulsing)
 *
 * Polls `/api/health-detail` every 30s. Click opens a drill panel listing
 * the per-stream status, age, and last error so the trader can immediately
 * see which feed is misbehaving — no need to refresh the dashboard.
 */
type StreamRow = {
  key: string;
  label: string;
  status: 'up' | 'stale' | 'down';
  detail?: string | null;
  age_s: number | null;
  ttl_s: number;
};
type HealthPayload = {
  overall: 'ok' | 'degraded' | 'down';
  counts:  { up: number; stale: number; down: number };
  total:   number;
  streams: StreamRow[];
};

function ageStr(s: number | null): string {
  if (s === null || s === undefined) return '—';
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.round(s / 60)}m`;
  if (s < 86400) return `${Math.round(s / 3600)}h`;
  return `${Math.round(s / 86400)}d`;
}

export function HealthPill() {
  // The generated HealthDetailData widens `overall` to `string`; this component
  // works with the narrower local union, so adapt the fetcher's return type.
  const { data } = usePolling<HealthPayload>(
    api.healthDetail as unknown as () => Promise<HealthPayload>, 30_000);
  const [open, setOpen] = useState(false);
  const panelRef = useRef<HTMLDivElement | null>(null);

  // Close drill on ESC
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open]);

  if (!data) {
    return (
      <div className="px-2.5 py-1 rounded-full bg-bg-elev/70 border border-border text-[10px] font-mono uppercase tracking-widest text-text-tertiary flex items-center gap-1.5">
        <Activity className="w-3 h-3 animate-pulse" />
        <span>checking…</span>
      </div>
    );
  }

  const { overall, counts, total, streams } = data;
  const isOK       = overall === 'ok';
  const isDegraded = overall === 'degraded';
  const isDown     = overall === 'down';

  const Icon  = isDown ? XCircle : isDegraded ? AlertTriangle : CheckCircle2;
  const tone  = isDown ? 'bear'  : isDegraded ? 'neut'        : 'bull';

  const stale = counts.stale;
  const down  = counts.down;

  return (
    <>
      <button
        onClick={() => setOpen(o => !o)}
        title={`Click to drill into ${total} streams — ${counts.up} up, ${stale} stale, ${down} down`}
        className={clsx(
          'flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-[10px] font-mono uppercase tracking-widest transition-colors',
          tone === 'bull' && 'bg-bull-soft border-bull/30 text-bull hover:bg-bull/15',
          tone === 'neut' && 'bg-neut-soft border-neut/40 text-neut hover:bg-neut/15',
          tone === 'bear' && 'bg-bear-soft border-bear/40 text-bear hover:bg-bear/15 animate-pulse',
        )}
      >
        <Icon className="w-3 h-3" strokeWidth={2.5} />
        <span className="tabular">
          {counts.up}<span className="text-text-muted/80">/{total}</span>
        </span>
        {(stale > 0 || down > 0) && (
          <span className="tabular">
            · {down > 0 && <span className="text-bear">{down} down</span>}
            {down > 0 && stale > 0 && ' '}
            {stale > 0 && <span className="text-neut">{stale} stale</span>}
          </span>
        )}
        {isOK && <span>all up</span>}
      </button>

      {open && createPortal(
        <div
          className="fixed inset-0 z-[150] bg-black/60 backdrop-blur-sm flex items-center justify-center p-4 animate-fade-in"
          onClick={() => setOpen(false)}
        >
          <div
            ref={panelRef}
            className="bg-bg-elev border border-border-strong rounded-lg shadow-2xl w-full max-w-2xl max-h-[85vh] overflow-hidden flex flex-col"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="px-5 py-3 border-b border-border flex items-center justify-between flex-shrink-0">
              <div>
                <h2 className="font-display font-extrabold text-base tracking-[0.18em] uppercase text-gold flex items-center gap-2">
                  <Icon className={clsx('w-4 h-4',
                    tone === 'bull' && 'text-bull',
                    tone === 'neut' && 'text-neut',
                    tone === 'bear' && 'text-bear',
                  )} />
                  Stream Health
                </h2>
                <p className="text-[10px] font-mono text-text-tertiary mt-0.5">
                  {counts.up} up · {stale} stale · {down} down · 30s refresh
                </p>
              </div>
              <button
                onClick={() => setOpen(false)}
                className="text-text-tertiary hover:text-text-primary text-[18px] leading-none px-2"
                aria-label="Close"
              >
                ×
              </button>
            </div>

            <div className="overflow-y-auto text-[11px] font-mono">
              {/* Group: problematic first */}
              {['down', 'stale', 'up'].map(grp => {
                const items = streams.filter(s => s.status === grp);
                if (!items.length) return null;
                const grpTone =
                  grp === 'down'  ? 'text-bear'
                  : grp === 'stale' ? 'text-neut'
                  : 'text-bull';
                return (
                  <div key={grp}>
                    <div className={clsx('px-5 py-2 sticky top-0 bg-bg-elev border-b border-border/40 uppercase tracking-widest text-[10px] font-bold', grpTone)}>
                      {grp} · {items.length}
                    </div>
                    <ul className="divide-y divide-border/30">
                      {items.map(s => {
                        const dotColor = grp === 'up' ? 'bg-bull'
                                       : grp === 'stale' ? 'bg-neut'
                                       : 'bg-bear';
                        return (
                          <li key={s.key} className="px-5 py-2.5 flex items-start gap-3 hover:bg-bg-hover/40">
                            <span className={clsx('w-1.5 h-1.5 rounded-full mt-1.5 flex-shrink-0', dotColor)} />
                            <div className="flex-1 min-w-0">
                              <div className="flex items-baseline justify-between gap-2">
                                <span className="text-text-primary truncate">{s.label}</span>
                                <span className="text-text-muted text-[10px] tabular flex-shrink-0">
                                  age {ageStr(s.age_s)} · ttl {ageStr(s.ttl_s)}
                                </span>
                              </div>
                              {s.detail && (
                                <div className={clsx('text-[10px] mt-0.5 truncate',
                                  grp === 'up' ? 'text-text-tertiary' : 'text-text-secondary',
                                )} title={s.detail}>
                                  {s.detail}
                                </div>
                              )}
                              <div className="text-[9px] text-text-muted mt-0.5">{s.key}</div>
                            </div>
                          </li>
                        );
                      })}
                    </ul>
                  </div>
                );
              })}
            </div>

            <div className="px-5 py-2.5 border-t border-border bg-bg-card/40 text-[10px] font-mono text-text-tertiary flex items-center justify-between flex-shrink-0">
              <span>esc / click outside to close</span>
              <span className="text-text-muted">/api/health-detail</span>
            </div>
          </div>
        </div>,
        document.body,
      )}
    </>
  );
}
