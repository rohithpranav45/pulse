import { useMemo } from 'react';
import clsx from 'clsx';
import { Panel } from '@/components/ui/Panel';
import { SkeletonRows } from '@/components/ui/Skeleton';
import { api } from '@/lib/api';
import type { NewsImpactData, NewsImpactItem } from '@/lib/api';
import { usePolling } from '@/lib/hooks';

/**
 * News Headline Impact — the ranked "what just printed and what is it worth" feed.
 * Each recent classified headline → factor · signed sentiment · expected Brent %
 * move, sorted by |expected move|. The % move uses the empirically-fitted per-
 * factor beta when it cleared the significance gate (basis = measured), else a
 * labelled economic prior (basis = prior) — the desk is never shown a fabricated-
 * precise number.
 */

const pct = (v: number | null | undefined) =>
  v == null ? '—' : `${v > 0 ? '+' : ''}${v.toFixed(2)}%`;

function dirTone(d: string | null | undefined) {
  return d === 'LONG' ? 'bull' : d === 'SHORT' ? 'bear' : 'neut';
}

export function NewsImpactPanel() {
  const { data, lastUpdated, error } = usePolling<NewsImpactData>(
    () => api.newsImpact() as Promise<NewsImpactData>,
    120_000,
  );
  const feed = useMemo<NewsImpactItem[]>(() => (data?.feed ?? []) as NewsImpactItem[], [data]);

  if (!data && !error) {
    return (
      <Panel title="Impact feed · headline → % move" accent="gold" source="news_impact"
        staticMount lastSuccess={lastUpdated} fetchError={error}>
        <SkeletonRows rows={10} />
      </Panel>
    );
  }
  if (!data?.available || feed.length === 0) {
    return (
      <Panel title="Impact feed · headline → % move" accent="gold" source="news_impact"
        staticMount lastSuccess={lastUpdated} fetchError={error}>
        <div className="text-[12px] font-mono text-text-tertiary px-3 py-6 text-center">
          {error
            ? `News impact endpoint unreachable: ${(error as any)?.message ?? String(error)}`
            : 'No classified headlines with fitted betas yet — run the corpus backfill + event study.'}
        </div>
      </Panel>
    );
  }

  const reg = data.regime ?? {};
  return (
    <Panel
      title="Impact feed · headline → % move"
      subtitle={`Brent ${data.horizon ?? '1d'} forward · ranked by |expected move|`}
      accent="gold"
      source="news_impact"
      staticMount
      lastSuccess={lastUpdated}
      fetchError={error}
      right={
        <span className="text-[9.5px] font-mono text-text-muted uppercase tracking-widest">
          regime {String((reg as any).curve ?? '—')} · n={data.n_headlines ?? 0}
        </span>
      }
    >
      <div className="grid grid-cols-[64px_60px_1fr_120px] gap-2 text-[9.5px] font-mono text-text-muted uppercase tracking-wide px-1 mb-1">
        <span>Dir</span><span className="text-right">Exp move</span><span>Headline</span>
        <span className="text-right">Factor · basis</span>
      </div>
      <div className="space-y-0.5 max-h-[520px] overflow-y-auto">
        {feed.map((s, i) => {
          const tone = dirTone(s.direction);
          const measured = s.basis === 'measured';
          return (
            <div
              key={(s.published_at ?? '') + i}
              className="grid grid-cols-[64px_60px_1fr_120px] gap-2 items-center text-[10.5px] font-mono tabular py-1 px-1 rounded hover:bg-bg-card/30"
              title={s.rationale ?? ''}
            >
              <span className={clsx('font-bold uppercase text-[9.5px] tracking-wide',
                tone === 'bull' && 'text-bull', tone === 'bear' && 'text-bear', tone === 'neut' && 'text-neut')}>
                {s.direction ?? '—'}
              </span>
              <span className={clsx('text-right font-bold',
                (s.expected_pct_move ?? 0) > 0 ? 'text-bull' : (s.expected_pct_move ?? 0) < 0 ? 'text-bear' : 'text-text-muted')}>
                {pct(s.expected_pct_move)}
              </span>
              <span className="text-text-secondary truncate" title={s.title ?? ''}>
                {s.title ?? '—'}
              </span>
              <span className="text-right flex items-center justify-end gap-1.5">
                <span className="text-text-tertiary text-[9.5px] truncate max-w-[78px]" title={s.factor_label ?? ''}>
                  {s.factor ?? '—'}
                </span>
                <span className={clsx('text-[8.5px] uppercase tracking-wider px-1 py-0.5 rounded border',
                  measured
                    ? 'text-gold-bright bg-gold/10 border-gold/30'
                    : 'text-text-muted bg-bg-card/40 border-border/40')}
                  title={measured ? `measured beta (t=${s.t_stat}, n=${s.n})` : 'labelled prior — not enough significant evidence'}>
                  {measured ? 'meas' : 'prior'}
                </span>
              </span>
            </div>
          );
        })}
      </div>
      <div className="mt-3 text-[10px] font-mono text-text-muted leading-relaxed">
        <span className="text-gold-bright">meas</span> = empirically fitted beta (|t|≥{data.t_min ?? 2} on ≥{data.min_n ?? 12} headlines);
        <span className="text-text-muted"> prior</span> = labelled economic prior until the evidence clears the gate.
        Span {data.span?.[0] ?? '—'} → {data.span?.[1] ?? '—'}.
      </div>
    </Panel>
  );
}
