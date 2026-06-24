import { useMemo } from 'react';
import clsx from 'clsx';
import { Panel } from '@/components/ui/Panel';
import { SkeletonRows } from '@/components/ui/Skeleton';
import { api } from '@/lib/api';
import { usePolling } from '@/lib/hooks';

/**
 * Live headlines strip — the current oil-news tape (NewsAPI / GDELT / marketaux),
 * each headline already scored by the news-impact model server-side: factor +
 * expected Brent % move + a clean UTC timestamp. Reads /api/news/live (which
 * enriches the wire: corpus Groq-factor when known, else keyword; GDELT's compact
 * timestamps normalised to ISO so they actually render). Newest first.
 */

type LiveItem = {
  title?: string; url?: string | null; source?: string | null;
  published_at?: string | null; factor?: string; factor_label?: string;
  direction?: string; expected_pct_move?: number | null; basis?: string;
  t_stat?: number | null; n?: number | null; news_sentiment?: number | null;
};
type LiveData = { available?: boolean; articles?: LiveItem[] };

const pctMove = (v: number | null | undefined) =>
  v == null ? '—' : `${v > 0 ? '+' : ''}${v.toFixed(2)}%`;

// Absolute UTC time (two lines: date over HH:mm) — the corpus/feed timestamps are
// UTC. Handles ISO; the backend already normalised GDELT's compact form.
function fmtTs(iso: string | null | undefined): { date: string; time: string } {
  if (!iso) return { date: '—', time: '' };
  const d = new Date(iso);
  if (isNaN(d.getTime())) return { date: '—', time: '' };
  return { date: d.toISOString().slice(0, 10), time: d.toISOString().slice(11, 16) + 'Z' };
}

function sentToneOf(s: number | null | undefined): 'bull' | 'bear' | 'neut' {
  if (typeof s !== 'number') return 'neut';
  return s > 0.05 ? 'bull' : s < -0.05 ? 'bear' : 'neut';
}

export function LiveHeadlinesPanel() {
  const { data, lastUpdated, error } = usePolling<LiveData>(
    () => api.newsLive() as Promise<LiveData>, 90_000,
  );

  const articles = useMemo<LiveItem[]>(() => {
    const list = (data?.articles ?? []) as LiveItem[];
    return [...list].sort((a, b) => {
      const ta = Date.parse((a.published_at || '') as string) || 0;
      const tb = Date.parse((b.published_at || '') as string) || 0;
      return tb - ta;   // newest first
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
            : 'No headlines on the wire right now (sources may be rate-limited).'}
        </div>
      </Panel>
    );
  }

  return (
    <Panel
      title="Live headlines · oil tape"
      subtitle="current wire · scored · NewsAPI · GDELT · marketaux"
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
      <div className="grid grid-cols-[78px_1fr_64px_96px] gap-2 text-[9.5px] font-mono text-text-muted uppercase tracking-wide px-1 mb-1">
        <span>Time · UTC</span><span>Headline</span><span className="text-right">Exp move</span>
        <span className="text-right">Factor / src</span>
      </div>
      <div className="space-y-0.5 max-h-[420px] overflow-y-auto">
        {articles.slice(0, 40).map((a, i) => {
          const title = a.title || '—';
          const ts = fmtTs(a.published_at);
          const st = sentToneOf(a.news_sentiment);
          const move = a.expected_pct_move;
          const scored = a.factor && a.factor !== 'NOISE' && move != null;
          const moveTone = (move ?? 0) > 0 ? 'bull' : (move ?? 0) < 0 ? 'bear' : 'neut';
          const row = (
            <div className="grid grid-cols-[78px_1fr_64px_96px] gap-2 items-center text-[10.5px] font-mono py-1 px-1 rounded hover:bg-bg-card/30">
              <span className="flex flex-col leading-tight text-[9px]" title={a.published_at ?? ''}>
                <span className="text-text-tertiary">{ts.date}</span>
                <span className="text-text-muted">{ts.time}</span>
              </span>
              <span className="flex items-center gap-1.5 min-w-0">
                <span className={clsx('w-1.5 h-1.5 rounded-full flex-shrink-0',
                  st === 'bull' && 'bg-bull', st === 'bear' && 'bg-bear', st === 'neut' && 'bg-text-muted')} />
                <span className="text-text-secondary truncate" title={title}>{title}</span>
              </span>
              <span className={clsx('text-right tabular font-bold',
                scored
                  ? (moveTone === 'bull' ? 'text-bull' : moveTone === 'bear' ? 'text-bear' : 'text-text-muted')
                  : 'text-text-muted/40')}>
                {scored ? pctMove(move) : '—'}
              </span>
              <span className="text-right flex flex-col items-end leading-tight"
                title={a.factor
                  ? `${a.factor}${a.basis === 'measured' ? ` · measured t=${a.t_stat}, n=${a.n}` : ' · prior'}`
                  : ''}>
                <span className="text-text-tertiary text-[9px] uppercase tracking-wider truncate max-w-[96px]">
                  {a.factor && a.factor !== 'NOISE' ? a.factor : '—'}
                </span>
                {scored && (
                  <span className={clsx('text-[8px] uppercase tracking-wider px-1 rounded border',
                    a.basis === 'measured'
                      ? 'text-gold-bright bg-gold/10 border-gold/30'
                      : 'text-text-muted bg-bg-card/40 border-border/40')}>
                    {a.basis === 'measured' ? 'meas' : 'prior'}
                  </span>
                )}
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
        The live wire, scored. <span className="text-bull">Exp move</span> = the model's expected Brent move for
        that headline; <span className="text-gold-bright">meas</span> = fitted beta cleared the gate, else a
        labelled prior. NOISE / non-oil headlines read <span className="text-text-muted/60">—</span>.
      </div>
    </Panel>
  );
}
