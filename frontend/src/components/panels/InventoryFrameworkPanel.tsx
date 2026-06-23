import { useMemo } from 'react';
import clsx from 'clsx';
import { Panel } from '@/components/ui/Panel';
import { api } from '@/lib/api';
import { usePolling } from '@/lib/hooks';

/**
 * Deliverable 4 — the framework, explained, plus the backtested visual evidence.
 * The L0→L4 pipeline as labelled cards, the "when it mattered" regime table, and
 * the four deck charts served from the backend.
 */

type WhenRow = { conditioner: string; regime: string; beta: number; t: number; r2: number; n: number };
type Inventory = { available: boolean; when_it_mattered?: WhenRow[]; charts?: string[]; span?: [string, string]; n_releases?: number };

const LAYERS = [
  { k: 'L0', t: 'Surprise', d: 'actual − expected, z-scored. Headline = commercial crude ex-SPR (the number the market forecasts). Expected = seasonal/nowcast proxy now, real consensus on the day.' },
  { k: 'L2', t: 'Quality of draw', d: 'the whole report, not the headline — Cushing, runs, imports, exports, implied demand + a reconstructed supply-balance adjustment. Flags mechanical (export-driven) draws to fade.' },
  { k: 'L1', t: 'Reaction function', d: 'intraday event study on the 1-min tape (2021-26, 281 releases) — conditional betas, decay, and a placebo vol test.' },
  { k: '★',  t: 'Regime conditioning', d: 'the centerpiece — 535 daily releases (2015-26): surprise→price strength is conditional on the inventory/curve regime. Glut ⇒ it bites; tight ⇒ noise.' },
  { k: 'L4', t: 'Scorecard', d: 'composes into bull/bear/neutral + confidence + spread + top-3 factors. Conviction is regime-gated.' },
];

const CHART_META: Record<string, { title: string; cap: string }> = {
  when_it_mattered: { title: 'When inventories mattered', cap: 'Surprise→Brent beta by regime (green ★ = significant). Glut/contango/HIGH-stocks bite; tight/backwardated is noise.' },
  era_scatter:      { title: 'Glut vs tight scatter', cap: 'Surprise vs release-day return — a clear negative slope in a glut, flat when inventories are tight.' },
  quality:          { title: 'Quality-of-draw divergence', cap: 'Headline vs internals — red points are bullish draws with weak internals (mechanical → fade).' },
  decay_placebo:    { title: 'Release-day vol vs placebo', cap: 'In 2021-26 the print is ~1.0× a normal day at every horizon — not even a reliable vol event in this regime.' },
};

export function InventoryFrameworkPanel() {
  const { data, lastUpdated, error } = usePolling<Inventory>(
    () => api.regimeInventory() as Promise<Inventory>, 600_000,
  );
  const rows = useMemo(() => data?.when_it_mattered ?? [], [data]);
  const maxAbs = useMemo(() => rows.reduce((m, r) => Math.max(m, Math.abs(r.beta)), 0.01), [rows]);
  const charts = data?.charts ?? ['when_it_mattered', 'era_scatter', 'quality', 'decay_placebo'];

  return (
    <Panel
      title="The framework · L0→L4 + backtested evidence"
      subtitle={data?.span ? `${data.n_releases} releases · ${data.span[0]}–${data.span[1]}` : 'methodology'}
      accent="blue" source="inventory_impact" staticMount
      lastSuccess={lastUpdated} fetchError={error}
    >
      {/* L0-L4 pipeline */}
      <div className="grid grid-cols-1 md:grid-cols-5 gap-2 mb-4">
        {LAYERS.map(l => (
          <div key={l.k} className="rounded border border-border/40 bg-bg-card/40 p-2">
            <div className="flex items-center gap-1.5 mb-1">
              <span className="text-[11px] font-mono font-bold text-gold">{l.k}</span>
              <span className="text-[10.5px] font-mono text-text-primary">{l.t}</span>
            </div>
            <div className="text-[9.5px] font-mono text-text-tertiary leading-snug">{l.d}</div>
          </div>
        ))}
      </div>

      {/* when it mattered table */}
      {rows.length > 0 && (
        <>
          <div className="text-[10px] font-mono uppercase tracking-[0.15em] text-text-tertiary mb-1.5">
            When it mattered · surprise→Brent release-day return (% per 1σ), 2015-26
          </div>
          <div className="space-y-1 mb-4">
            {rows.map(r => {
              const sig = Math.abs(r.t) >= 2;
              return (
                <div key={`${r.conditioner}-${r.regime}`}
                  className="grid grid-cols-[150px_1fr_118px] items-center gap-2 text-[10.5px] font-mono"
                  title={`β=${r.beta}%/σ · t=${r.t} · R²=${r.r2} · n=${r.n}`}>
                  <span className={sig ? 'text-text-secondary' : 'text-text-muted'}>{r.regime}</span>
                  <div className="relative h-3 bg-bg-card/40 rounded overflow-hidden border border-border/30">
                    <div className={clsx('absolute top-0 bottom-0 left-0', sig ? 'bg-bull/60' : 'bg-text-muted/30')}
                      style={{ width: `${Math.max(2, (Math.abs(r.beta) / maxAbs) * 100)}%` }} />
                  </div>
                  <span className={clsx('text-right tabular', sig ? 'text-bull font-bold' : 'text-text-muted')}>
                    β={r.beta.toFixed(2)} t={r.t}{sig ? ' ★' : ''}
                  </span>
                </div>
              );
            })}
          </div>
        </>
      )}

      {/* charts gallery */}
      <div className="text-[10px] font-mono uppercase tracking-[0.15em] text-text-tertiary mb-2">
        Backtested evidence
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {charts.map(name => {
          const meta = CHART_META[name];
          if (!meta) return null;
          return (
            <figure key={name} className="rounded border border-border/40 bg-bg-card/30 overflow-hidden">
              <img src={`/api/regime/inventory/chart/${name}`} alt={meta.title} loading="lazy"
                className="w-full block" style={{ background: '#0B0F1A' }} />
              <figcaption className="px-2.5 py-1.5">
                <div className="text-[10.5px] font-mono text-text-secondary font-bold">{meta.title}</div>
                <div className="text-[9.5px] font-mono text-text-muted leading-snug">{meta.cap}</div>
              </figcaption>
            </figure>
          );
        })}
      </div>
    </Panel>
  );
}
