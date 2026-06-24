import { useMemo } from 'react';
import clsx from 'clsx';
import { Panel } from '@/components/ui/Panel';
import { Chip } from '@/components/ui/Chip';
import { SkeletonRows } from '@/components/ui/Skeleton';
import { api } from '@/lib/api';
import type { NewsData, NewsArticle, NewsImpactData, NewsImpactItem } from '@/lib/api';
import { usePolling } from '@/lib/hooks';

/**
 * Live headlines strip — the current oil-news tape, straight from /api/news
 * (NewsAPI / GDELT / marketaux). Each headline is joined (by title) to the news-
 * impact feed, so when the model has scored it we show the factor + expected
 * Brent % move right on the row. Newest first, with source, sentiment tone, and
 * a relative timestamp.
 */

const pctMove = (v: number | null | undefined) =>
  v == null ? '—' : `${v > 0 ? '+' : ''}${v.toFixed(2)}%`;

function relAgo(iso: string | null | undefined): string {
  if (!iso) return '';
  const t = Date.parse(iso);
  if (isNaN(t)) return '';
  const s = Math.max(0, Math.round((Date.now() - t) / 1000));
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.round(s / 60)}m`;
  if (s < 86400) return `${Math.round(s / 3600)}h`;
  return `${Math.round(s / 86400)}d`;
}

const catTone = (c: string | null | undefined): 'bull' | 'bear' | 'neut' | 'muted' => {
  switch ((c ?? '').toUpperCase()) {
    case 'GEO':   return 'bear';
    case 'OPEC':  return 'neut';
    case 'MACRO': return 'neut';
    case 'CRUDE': return 'muted';
    default:      return 'muted';
  }
};

function sentTone(a: NewsArticle): 'bull' | 'bear' | 'neut' {
  const s = (a as any).sentiment_score ?? a.sentiment;
  if (typeof s === 'number') return s > 0.05 ? 'bull' : s < -0.05 ? 'bear' : 'neut';
  if (a.is_negative) return 'bear';
  return 'neut';
}

export function LiveHeadlinesPanel() {
  const { data, lastUpdated, error } = usePolling<NewsData>(
    () => api.news() as Promise<NewsData>, 90_000,
  );
  // Join to the impact feed so scored headlines show their factor + expected move.
  const { data: impact } = usePolling<NewsImpactData>(
    () => api.newsImpact() as Promise<NewsImpactData>, 120_000,
  );
  const impactByTitle = useMemo(() => {
    const m = new Map<string, NewsImpactItem>();
    for (const it of (impact?.feed ?? []) as NewsImpactItem[]) {
      if (it.title) m.set(it.title.trim().toLowerCase(), it);
    }
    return m;
  }, [impact]);

  const articles = useMemo<NewsArticle[]>(() => {
    const list = (data?.articles ?? []) as NewsArticle[];
    // newest first by whatever timestamp the source provided
    return [...list].sort((a, b) => {
      const ta = Date.parse((a.published_at || a.published || a.time || '') as string) || 0;
      const tb = Date.parse((b.published_at || b.published || b.time || '') as string) || 0;
      return tb - ta;
    });
  }, [data]);

  if (!data && !error) {
    return (
      <Panel title="Live headlines · oil tape" accent="blue" source="news_live"
        staticMount lastSuccess={lastUpdated} fetchError={error}>
        <SkeletonRows rows={6} />
      </Panel>
    );
  }
  if (!articles.length) {
    return (
      <Panel title="Live headlines · oil tape" accent="blue" source="news_live"
        staticMount lastSuccess={lastUpdated} fetchError={error}>
        <div className="text-[12px] font-mono text-text-tertiary px-3 py-6 text-center">
          {error
            ? `News endpoint unreachable: ${(error as any)?.message ?? String(error)}`
            : 'No headlines on the wire right now (NewsAPI may be rate-limited).'}
        </div>
      </Panel>
    );
  }

  return (
    <Panel
      title="Live headlines · oil tape"
      subtitle="current wire · NewsAPI · GDELT · marketaux"
      accent="blue"
      source="news_live"
      staticMount
      lastSuccess={lastUpdated}
      fetchError={error}
      right={
        <span className="text-[9.5px] font-mono text-text-muted uppercase tracking-widest">
          {articles.length} on wire
        </span>
      }
    >
      <div className="space-y-0.5 max-h-[360px] overflow-y-auto">
        {articles.slice(0, 40).map((a, i) => {
          const title = a.title || a.headline || '—';
          const ago = relAgo((a.published_at || a.published || a.time) as string);
          const st = sentTone(a);
          const imp = title !== '—' ? impactByTitle.get(title.trim().toLowerCase()) : undefined;
          const move = imp?.expected_pct_move;
          const moveTone = (move ?? 0) > 0 ? 'bull' : (move ?? 0) < 0 ? 'bear' : 'neut';
          const row = (
            <div className="grid grid-cols-[40px_1fr_72px_auto] gap-2 items-center text-[10.5px] font-mono py-1 px-1 rounded hover:bg-bg-card/30">
              <span className="text-text-muted tabular text-right text-[9.5px]">{ago || '—'}</span>
              <span className="flex items-center gap-1.5 min-w-0">
                <span className={clsx('w-1.5 h-1.5 rounded-full flex-shrink-0',
                  st === 'bull' && 'bg-bull', st === 'bear' && 'bg-bear', st === 'neut' && 'bg-text-muted')} />
                <span className="text-text-secondary truncate" title={title}>{title}</span>
              </span>
              {/* impact (joined from the scored feed) — expected Brent move + factor */}
              <span
                className="flex flex-col items-end leading-tight"
                title={imp ? `${imp.factor} · ${imp.basis === 'measured' ? `measured t=${imp.t_stat}` : 'prior'}` : 'not scored yet'}
              >
                {imp ? (
                  <>
                    <span className={clsx('tabular font-bold text-[10px]',
                      moveTone === 'bull' && 'text-bull', moveTone === 'bear' && 'text-bear', moveTone === 'neut' && 'text-text-muted')}>
                      {pctMove(move)}
                    </span>
                    <span className="text-text-muted text-[8px] uppercase tracking-wider truncate max-w-[72px]">
                      {imp.factor}
                    </span>
                  </>
                ) : (
                  <span className="text-text-muted/40 text-[9px]">—</span>
                )}
              </span>
              <span className="flex items-center gap-1.5 flex-shrink-0">
                {a.category && <Chip tone={catTone(a.category) as any}>{a.category}</Chip>}
                <span className="text-text-muted text-[9px] truncate max-w-[80px]" title={a.source ?? ''}>
                  {a.source ?? ''}
                </span>
              </span>
            </div>
          );
          return a.url ? (
            <a key={(a.url ?? '') + i} href={a.url} target="_blank" rel="noopener noreferrer" className="block">
              {row}
            </a>
          ) : (
            <div key={i}>{row}</div>
          );
        })}
      </div>
      <div className="mt-2 text-[10px] font-mono text-text-muted leading-relaxed">
        The live wire. The <span className="text-bull">+/-%</span> is the model's expected Brent move for that
        headline (factor below it) — shown once the headline has been classified + scored; a fresh headline reads
        <span className="text-text-muted/60"> —</span> until the next ingest tick. NOISE headlines stay unscored.
      </div>
    </Panel>
  );
}
