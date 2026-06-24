import { useMemo } from 'react';
import clsx from 'clsx';
import { Panel } from '@/components/ui/Panel';
import { SkeletonRows } from '@/components/ui/Skeleton';
import { api } from '@/lib/api';
import type { NewsImpactData, NewsFactorRow } from '@/lib/api';
import { usePolling } from '@/lib/hooks';

/**
 * Per-factor beta table — the event study behind the impact feed. Every factor in
 * the taxonomy with its Brent beta (% move per +1 unit of crude-sentiment), the
 * t-stat / N, and whether the number is MEASURED (cleared the significance gate)
 * or a labelled PRIOR. Honest by construction: most factors sit on the prior on a
 * few-hundred-headline tape with a keyword-sentiment proxy — that's reported, not
 * hidden.
 */

const sig2 = (v: number | null | undefined) =>
  v == null ? '—' : `${v > 0 ? '+' : ''}${v.toFixed(2)}`;

export function NewsFactorPanel() {
  const { data, lastUpdated, error } = usePolling<NewsImpactData>(
    () => api.newsFactors() as Promise<NewsImpactData>,
    300_000,
  );
  const rows = useMemo<NewsFactorRow[]>(() => (data?.factors ?? []) as NewsFactorRow[], [data]);

  if (!data && !error) {
    return (
      <Panel title="Per-factor beta · sentiment → Brent %" accent="blue" source="news_impact"
        staticMount lastSuccess={lastUpdated} fetchError={error}>
        <SkeletonRows rows={9} />
      </Panel>
    );
  }
  if (rows.length === 0) {
    return (
      <Panel title="Per-factor beta · sentiment → Brent %" accent="blue" source="news_impact"
        staticMount lastSuccess={lastUpdated} fetchError={error}>
        <div className="text-[12px] font-mono text-text-tertiary px-3 py-6 text-center">
          {error ? `News factors endpoint unreachable: ${(error as any)?.message ?? String(error)}`
                 : 'No factor table yet — run the event study to fit betas.'}
        </div>
      </Panel>
    );
  }

  const nMeasured = rows.filter(r => r.significant).length;
  return (
    <Panel
      title="Per-factor beta · sentiment → Brent %"
      subtitle={`${data.horizon ?? '1d'} forward · ${nMeasured}/${rows.length} measured`}
      accent="blue"
      source="news_impact"
      staticMount
      lastSuccess={lastUpdated}
      fetchError={error}
    >
      <div className="grid grid-cols-[1fr_70px_56px_48px_64px_58px] gap-2 text-[9.5px] font-mono text-text-muted uppercase tracking-wide px-1 mb-1">
        <span>Factor</span><span className="text-right">β %/unit</span><span className="text-right">t</span>
        <span className="text-right">n</span><span className="text-right">hit</span><span className="text-right">basis</span>
      </div>
      <div className="space-y-0.5">
        {rows.map(r => {
          const measured = !!r.significant;
          const b = r.beta_pct ?? 0;
          return (
            <div key={r.factor}
              className="grid grid-cols-[1fr_70px_56px_48px_64px_58px] gap-2 items-center text-[10.5px] font-mono tabular py-1 px-1 rounded hover:bg-bg-card/30"
              title={measured ? `measured (R²=${r.r2}); WTI β=${sig2(r.beta_wti_pct)}` : (r.prior_note ?? '')}>
              <span className="text-text-secondary truncate" title={r.label ?? r.factor}>{r.factor}</span>
              <span className={clsx('text-right font-bold',
                measured ? (b > 0 ? 'text-bull' : 'text-bear') : 'text-text-tertiary')}>
                {sig2(r.beta_pct)}
              </span>
              <span className={clsx('text-right', Math.abs(r.t_stat ?? 0) >= 2 ? 'text-text-secondary' : 'text-text-muted')}>
                {r.t_stat == null ? '—' : (r.t_stat > 0 ? '+' : '') + r.t_stat.toFixed(1)}
              </span>
              <span className="text-right text-text-muted">{r.n ?? 0}</span>
              <span className="text-right text-text-muted">
                {r.aligned_hit_rate == null ? '—' : `${Math.round(r.aligned_hit_rate * 100)}%`}
              </span>
              <span className="text-right">
                <span className={clsx('text-[8.5px] uppercase tracking-wider px-1 py-0.5 rounded border',
                  measured ? 'text-gold-bright bg-gold/10 border-gold/30' : 'text-text-muted bg-bg-card/40 border-border/40')}>
                  {measured ? 'meas' : 'prior'}
                </span>
              </span>
            </div>
          );
        })}
      </div>
      <div className="mt-3 text-[10px] font-mono text-text-muted leading-relaxed">
        β = expected Brent % move per +1 unit of signed crude-sentiment. A factor shows a
        <span className="text-gold-bright"> measured</span> β only when |t|≥{data.t_min ?? 2} on ≥{data.min_n ?? 12} headlines;
        otherwise a labelled <span className="text-text-muted">prior</span>. Fitted on {data.n_headlines ?? 0} headlines.
      </div>
    </Panel>
  );
}
