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
type CmpRow = {
  regime: string; n: number;
  brent_beta: number; brent_t: number; wti_beta: number; wti_t: number;
  wti_brent_spread_beta: number | null; wti_brent_spread_t: number | null;
  wti_sharper: boolean; wti_right_signed: boolean;
};
type WtiCompare = {
  window: [string, string]; n: number; buckets: Record<string, number>;
  rows: CmpRow[]; wti_sharper_overall: boolean | null; wti_sharper_count: number;
  wti_right_signed_count: number; n_cuts: number; verdict: string; note: string;
};
type Inventory = {
  available: boolean; when_it_mattered?: WhenRow[]; when_it_mattered_wti?: WhenRow[] | null;
  wti_compare?: WtiCompare | null; charts?: string[]; span?: [string, string]; n_releases?: number;
};

/** A regime-beta bar row, reused for the Brent and WTI tables. */
function BetaRow({ r, maxAbs, tone }: { r: WhenRow; maxAbs: number; tone: 'bull' | 'gold' }) {
  const sig = Math.abs(r.t) >= 2;
  const barOn = tone === 'gold' ? 'bg-gold/60' : 'bg-bull/60';
  const txtOn = tone === 'gold' ? 'text-gold' : 'text-bull';
  return (
    <div className="grid grid-cols-[150px_1fr_118px] items-center gap-2 text-[10.5px] font-mono"
      title={`β=${r.beta}%/σ · t=${r.t} · R²=${r.r2} · n=${r.n}`}>
      <span className={sig ? 'text-text-secondary' : 'text-text-muted'}>{r.regime}</span>
      <div className="relative h-3 bg-bg-card/40 rounded overflow-hidden border border-border/30">
        <div className={clsx('absolute top-0 bottom-0 left-0', sig ? barOn : 'bg-text-muted/30')}
          style={{ width: `${Math.max(2, (Math.abs(r.beta) / maxAbs) * 100)}%` }} />
      </div>
      <span className={clsx('text-right tabular', sig ? `${txtOn} font-bold` : 'text-text-muted')}>
        β={r.beta.toFixed(2)} t={r.t}{sig ? ' ★' : ''}
      </span>
    </div>
  );
}

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

export function InventoryFrameworkPanel({ series = 'crude_ex_spr' }: { series?: string }) {
  const { data, lastUpdated, error } = usePolling<Inventory>(
    () => api.regimeInventory(series) as Promise<Inventory>, 600_000, [series],
  );
  const rows = useMemo(() => data?.when_it_mattered ?? [], [data]);
  const wtiRows = useMemo(() => data?.when_it_mattered_wti ?? [], [data]);
  const cmp = data?.wti_compare ?? null;
  // share the bar scale across both benchmarks so the betas are visually comparable
  const maxAbs = useMemo(
    () => [...rows, ...wtiRows].reduce((m, r) => Math.max(m, Math.abs(r.beta)), 0.01),
    [rows, wtiRows],
  );
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
            When it mattered · surprise→<span className="text-bull">Brent</span> release-day return (% per 1σ), 2015-26
          </div>
          <div className="space-y-1 mb-4">
            {rows.map(r => <BetaRow key={`b-${r.conditioner}-${r.regime}`} r={r} maxAbs={maxAbs} tone="bull" />)}
          </div>
        </>
      )}

      {/* WTI re-run — US crude inventories are a US signal, so WTI should be sharper */}
      {wtiRows.length > 0 && (
        <>
          <div className="text-[10px] font-mono uppercase tracking-[0.15em] text-text-tertiary mb-1.5">
            Same study on <span className="text-gold">WTI</span> · surprise→WTI release-day return (% per 1σ)
          </div>
          <div className="space-y-1 mb-3">
            {wtiRows.map(r => <BetaRow key={`w-${r.conditioner}-${r.regime}`} r={r} maxAbs={maxAbs} tone="gold" />)}
          </div>
        </>
      )}

      {/* Brent-vs-WTI matched-window verdict (the graded answer) */}
      {cmp && (
        <div className="rounded border border-gold/30 bg-gold/[0.04] p-2.5 mb-4">
          <div className="text-[10px] font-mono uppercase tracking-[0.15em] text-gold mb-1.5">
            Brent vs WTI · matched window {cmp.window[0]}–{cmp.window[1]} · n={cmp.n}
            {' '}({Object.entries(cmp.buckets).map(([k, v]) => `${v} ${k}`).join(' / ')})
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-[9.5px] font-mono">
              <thead>
                <tr className="text-text-tertiary text-left">
                  <th className="pr-2 font-normal">regime</th>
                  <th className="pr-2 font-normal text-right">Brent β/t</th>
                  <th className="pr-2 font-normal text-right">WTI β/t</th>
                  <th className="pr-2 font-normal text-right">WTI-Brent β/t</th>
                  <th className="font-normal text-right">sign</th>
                </tr>
              </thead>
              <tbody>
                {cmp.rows.map(r => (
                  <tr key={r.regime} className="text-text-secondary">
                    <td className="pr-2 text-text-muted">{r.regime}</td>
                    <td className="pr-2 text-right tabular">{r.brent_beta.toFixed(2)} / {r.brent_t}</td>
                    <td className={clsx('pr-2 text-right tabular', r.wti_sharper && 'text-gold font-bold')}>
                      {r.wti_beta.toFixed(2)} / {r.wti_t}
                    </td>
                    <td className={clsx('pr-2 text-right tabular',
                      r.wti_brent_spread_t != null && Math.abs(r.wti_brent_spread_t) >= 1.5 && 'text-gold')}>
                      {r.wti_brent_spread_beta != null ? r.wti_brent_spread_beta.toFixed(2) : '—'}
                      {' / '}{r.wti_brent_spread_t ?? '—'}
                    </td>
                    <td className="text-right">{r.wti_right_signed ? '✓' : '✗'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="text-[9.5px] font-mono text-text-tertiary leading-snug mt-2">
            <span className="text-gold font-bold">Verdict · </span>{cmp.verdict}
          </div>
          <div className="text-[9px] font-mono text-text-muted leading-snug mt-1">{cmp.note}</div>
        </div>
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
