import { Fragment } from 'react';
import { Panel } from '@/components/ui/Panel';
import { Chip } from '@/components/ui/Chip';
import { SkeletonRows } from '@/components/ui/Skeleton';
import { fmt } from '@/lib/fmt';
import { ExternalLink, Newspaper, Activity } from 'lucide-react';
import clsx from 'clsx';

const ASSETS = ['brent', 'wti', 'hh', 'dxy', 'spx'];
const LABELS: Record<string, string> = { brent: 'BRT', wti: 'WTI', hh: 'NG', dxy: 'DXY', spx: 'SPX' };

function corrColor(v: number) {
  const a = Math.abs(v);
  const hue = v >= 0 ? 152 : 348; // green / red
  return `hsl(${hue}, 70%, ${15 + a * 40}%)`;
}

function CorrelationsPanel({ corr }: { corr: any }) {
  // Server shape: { matrix: { matrix: {brent:{wti,...}, ...}, pairs, alerts }, brent_wti, curve }
  const m = corr?.matrix?.matrix ?? corr?.matrix;
  if (!m || typeof m !== 'object') return <Panel title="Correlations"><SkeletonRows rows={5} /></Panel>;
  return (
    <Panel title="Cross-Asset Correlations" subtitle="30d rolling · Pearson" source="correlations_calc" dataTimestamp={corr?.timestamp}>
      <div className="grid grid-cols-[60px_repeat(5,1fr)] gap-1.5">
        <div />
        {ASSETS.map(a => <div key={a} className="text-[9px] font-mono uppercase tracking-widest text-text-tertiary text-center pb-1">{LABELS[a]}</div>)}
        {ASSETS.map(rowA => (
          <Fragment key={rowA}>
            <div className="text-[9px] font-mono uppercase tracking-widest text-text-tertiary flex items-center justify-end pr-1">{LABELS[rowA]}</div>
            {ASSETS.map(colA => {
              const v = m[rowA]?.[colA] ?? 0;
              const same = rowA === colA;
              return (
                <div
                  key={`${rowA}-${colA}`}
                  className="aspect-square rounded flex items-center justify-center text-[11px] font-mono font-bold tabular transition-transform hover:scale-110 cursor-default"
                  style={{
                    background: same ? '#1c2745' : corrColor(v),
                    color: same ? '#6b809e' : Math.abs(v) > 0.5 ? '#fff' : '#aebccf',
                  }}
                >
                  {same ? '—' : v.toFixed(2)}
                </div>
              );
            })}
          </Fragment>
        ))}
      </div>
    </Panel>
  );
}

function NewsPanel({ news }: { news: any }) {
  if (!news) return <Panel title="News"><SkeletonRows rows={6} /></Panel>;
  const articles = news.articles ?? [];
  const cs = news.composite_sentiment;
  const composite: number =
    typeof cs === 'number' ? cs :
    typeof cs?.composite === 'number' ? cs.composite : 0;
  const tone = composite > 0.15 ? 'bull' : composite < -0.15 ? 'bear' : 'neut';

  const clusters = news.clusters ?? {};
  const hasClusters = Object.keys(clusters).length > 0;

  return (
    <Panel
      title="Energy News · FinBERT"
      subtitle={`${articles.length} articles`}
      accent={tone as any}
      source={news.source_used === 'gdelt' ? 'gdelt_doc' : news.source_used === 'marketaux' ? 'marketaux' : 'news_apify'}
      sourceNote={`Active source: ${news.source_used ?? 'unknown'}. Pipeline: GDELT → MarketAux → Apify → NewsAPI → RSS. ${news.composite_sentiment?.count ? `Sentiment via FinBERT (${news.composite_sentiment.count} articles, ${news.composite_sentiment.label}).` : ''}`}
      dataTimestamp={news.timestamp ?? articles[0]?.published_at ?? articles[0]?.published}
      right={
        <div className="flex items-center gap-2">
          <Chip tone={tone as any}>SENTIMENT {composite >= 0 ? '+' : ''}{composite.toFixed(2)}</Chip>
          <Newspaper className="w-4 h-4 text-text-tertiary" />
        </div>
      }
    >
      <div className="space-y-2 max-h-[480px] overflow-y-auto pr-2">
        {hasClusters ? (
          Object.entries(clusters).map(([theme, items]: any) => (
            <div key={theme} className="mb-3">
              <div className="text-[9px] font-mono uppercase tracking-widest text-gold mb-1.5 flex items-center gap-2">
                <div className="w-1.5 h-1.5 bg-gold rounded-full" />
                {theme} · {items.length}
              </div>
              {items.slice(0, 3).map((a: any, i: number) => <NewsRow key={i} a={a} />)}
            </div>
          ))
        ) : (
          articles.slice(0, 12).map((a: any, i: number) => <NewsRow key={i} a={a} />)
        )}
      </div>
    </Panel>
  );
}

function NewsRow({ a }: { a: any }) {
  // Backend uses `sentiment` (FinBERT result with score/label) or per-article score
  const sent = a.sentiment;
  const score: number =
    typeof a.sentiment_score === 'number' ? a.sentiment_score :
    typeof sent === 'number' ? sent :
    typeof sent?.score === 'number' ? (sent.label === 'negative' ? -sent.score : sent.label === 'positive' ? sent.score : 0) :
    0;
  const tone = score > 0.1 ? 'bull' : score < -0.1 ? 'bear' : 'neut';
  const title = a.title || a.headline || '';
  const when = a.published_at || a.published || null;
  const ago = when ? fmt.ago(when) : (a.time || '—');
  const url = a.url || '';
  const Inner = (
    <>
      <div className="flex-1 min-w-0">
        <div className="text-[11.5px] text-text-secondary group-hover:text-text-primary line-clamp-2 leading-snug">{title}</div>
        <div className="text-[9px] font-mono text-text-muted mt-1 flex items-center gap-2 tabular">
          <span className="truncate max-w-[120px]">{a.source}</span>
          <span>·</span>
          <span>{ago}</span>
          {a.category && <span className="text-text-tertiary">· {a.category}</span>}
          <span className={clsx(
            'ml-auto px-1.5 py-0.5 rounded text-[9px]',
            tone === 'bull' && 'bg-bull-soft text-bull',
            tone === 'bear' && 'bg-bear-soft text-bear',
            tone === 'neut' && 'bg-neut-soft text-neut',
          )}>{score >= 0 ? '+' : ''}{score.toFixed(2)}</span>
        </div>
      </div>
      {url && <ExternalLink className="w-3 h-3 text-text-muted group-hover:text-gold flex-shrink-0 mt-0.5 opacity-0 group-hover:opacity-100 transition-opacity" />}
    </>
  );
  const className = "group flex items-start gap-2 p-2 rounded hover:bg-bg-hover/60 transition-colors border-l-2";
  const style = { borderLeftColor: tone === 'bull' ? '#10d997' : tone === 'bear' ? '#ff4d6d' : '#f5a623' };
  return url
    ? <a href={url} target="_blank" rel="noopener noreferrer" className={className} style={style}>{Inner}</a>
    : <div className={className} style={style}>{Inner}</div>;
}

function PatternsPanel({ patterns }: { patterns: any }) {
  // Server: { pattern: {name, confidence, detail}, analogs: [...], playbook?, summary }
  const det = patterns?.brent ?? patterns;
  if (!det || !(det.pattern || det.summary || det.playbook)) {
    return <Panel title="Patterns"><SkeletonRows rows={4} /></Panel>;
  }
  const playbook = det.playbook;
  const patObj = det.pattern;
  const patName = typeof patObj === 'string' ? patObj : (patObj?.name ?? null);
  const patDetail = typeof patObj === 'object' ? patObj?.detail : null;
  const confidence = typeof patObj === 'object' ? patObj?.confidence : null;
  const analogs = det.analogs ?? [];
  return (
    <Panel
      title="Pattern Recognition"
      subtitle={`Brent · scipy ${confidence != null ? `· conf ${(confidence * 100).toFixed(0)}%` : ''}`}
      source="pattern_scipy"
      dataTimestamp={det.timestamp ?? patterns?.timestamp}
      right={patName && <Chip tone="gold">{patName}</Chip>}
    >
      {patName ? (
        <>
          <div className="text-[12px] text-text-secondary leading-relaxed mb-3">
            {patDetail ?? det.summary ?? playbook?.description ?? 'Detected on recent close series.'}
          </div>
          {analogs.length > 0 && (
            <div className="space-y-1.5 mb-3 pb-3 border-b border-border/40">
              <div className="text-[9px] font-mono uppercase tracking-widest text-text-muted">Historical Analogs</div>
              {analogs.slice(0, 3).map((a: any, i: number) => (
                <div key={i} className="flex items-baseline justify-between text-[10.5px] font-mono tabular">
                  <span className="text-text-secondary">{a.period}</span>
                  <span className="text-text-tertiary">{a.match_pct?.toFixed(0)}% match</span>
                  <span className={clsx(a.forward_return >= 0 ? 'text-bull' : 'text-bear')}>
                    {a.forward_return >= 0 ? '+' : ''}{a.forward_return?.toFixed(1)}% / {a.forward_weeks}w
                  </span>
                </div>
              ))}
            </div>
          )}
          {playbook && (
            <div className="space-y-3 p-3 bg-bg-card/60 rounded">
              <div className="grid grid-cols-3 gap-2">
                <div className="text-center">
                  <div className="text-[9px] font-mono uppercase tracking-widest text-text-muted">Bullish</div>
                  <div className="text-bull text-lg font-display font-bold tabular">{playbook.bullish_pct}%</div>
                </div>
                <div className="text-center">
                  <div className="text-[9px] font-mono uppercase tracking-widest text-text-muted">Bearish</div>
                  <div className="text-bear text-lg font-display font-bold tabular">{playbook.bearish_pct}%</div>
                </div>
                <div className="text-center">
                  <div className="text-[9px] font-mono uppercase tracking-widest text-text-muted">Median Move</div>
                  <div className="text-gold text-lg font-display font-bold tabular">{playbook.median_move_pct?.toFixed(1)}%</div>
                </div>
              </div>
              <div className="h-2 flex rounded overflow-hidden">
                <div className="bg-bull" style={{ width: `${playbook.bullish_pct}%` }} />
                <div className="bg-bear" style={{ width: `${playbook.bearish_pct}%` }} />
              </div>
              {playbook.case_studies && (
                <div className="space-y-1.5 mt-2 pt-2 border-t border-border/60">
                  <div className="text-[9px] font-mono uppercase tracking-widest text-text-muted">Case Studies</div>
                  {playbook.case_studies.slice(0, 3).map((cs: any, i: number) => (
                    <div key={i} className="text-[10.5px] font-mono tabular text-text-tertiary flex items-baseline justify-between">
                      <span className="text-text-secondary">{cs.date}</span>
                      <span>{cs.outcome}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </>
      ) : (
        <div className="text-[11px] font-mono text-text-muted py-4 text-center">No active pattern detected</div>
      )}
    </Panel>
  );
}

function AnalystWatchPanel({ watch }: { watch: any }) {
  if (!watch) return <Panel title="Analyst Watch"><SkeletonRows rows={5} /></Panel>;
  // Backend serves `analysts` (current) — older clients used `sources`. Accept both.
  const sources: any[] = watch.analysts ?? watch.sources ?? [];
  if (sources.length === 0) {
    return (
      <Panel title="Analyst Watch" subtitle="warming up" source="nitter_rss" right={<Activity className="w-4 h-4 text-text-tertiary" />}>
        <SkeletonRows rows={4} />
      </Panel>
    );
  }
  return (
    <Panel title="Analyst Watch" subtitle="Nitter · Truth Social" source="nitter_rss" dataTimestamp={watch?.timestamp ?? sources[0]?.posts?.[0]?.published} right={<Activity className="w-4 h-4 text-text-tertiary" />}>
      <div className="space-y-3">
        {sources.slice(0, 3).map((src: any, i: number) => {
          const posts: any[] = src.posts ?? [];
          return (
            <div key={i} className="p-3 bg-bg-card/50 rounded border border-border/60">
              <div className="flex items-center gap-2 mb-2">
                <div className="w-8 h-8 rounded-full bg-bg-elev flex items-center justify-center font-display font-bold text-text-secondary">
                  {(src.name ?? src.handle ?? 'X')[0]}
                </div>
                <div className="flex-1 min-w-0">
                  <a
                    href={src.profile_url ?? '#'}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-[11px] font-display font-semibold tracking-wider hover:text-gold transition-colors"
                  >
                    {src.name}
                  </a>
                  <div className="text-[9px] font-mono text-text-muted truncate">
                    {src.handle} {src.org && <span>· {src.org}</span>}
                  </div>
                </div>
                <Chip tone={posts.length > 0 ? 'blue' : 'muted'}>{posts.length}</Chip>
              </div>
              {posts.slice(0, 2).map((p: any, j: number) => (
                <a
                  key={j}
                  href={p.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="block text-[11px] text-text-secondary mt-1.5 leading-snug border-l-2 border-border pl-2 hover:text-text-primary hover:border-gold/50 transition-colors"
                >
                  {p.text?.slice(0, 220)}{p.text?.length > 220 ? '…' : ''}
                  {p.ago && <span className="block text-[9px] font-mono text-text-muted mt-0.5">{p.ago}</span>}
                </a>
              ))}
              {src.fallback_note && (
                <div className="mt-2 text-[9px] font-mono text-neut/80 leading-snug">⚠ {src.fallback_note}</div>
              )}
            </div>
          );
        })}
      </div>
    </Panel>
  );
}

function AnalogsPanel({ analogs }: { analogs: any }) {
  if (!analogs) return <Panel title="Pattern Analogs · matrix profile" source="analogs_stumpy"><SkeletonRows rows={4} /></Panel>;
  if (!analogs.available) {
    return (
      <Panel title="Pattern Analogs · matrix profile" source="analogs_stumpy" sourceNote={analogs.error}>
        <div className="text-[11px] font-mono text-text-tertiary leading-relaxed p-3 bg-bg-card/60 rounded">
          <div className="text-neut font-semibold mb-1">⚠ stumpy unavailable</div>
          <div className="text-text-muted">{analogs.error || 'Analog matching engine is not currently producing results.'}</div>
        </div>
      </Panel>
    );
  }
  const list = analogs.analogs ?? [];
  const avg  = analogs.avg_forward_return_pct ?? 0;
  const bias = analogs.bias ?? 'NEUTRAL';
  const tone: 'bull' | 'bear' | 'neut' =
    bias === 'BULLISH' ? 'bull' : bias === 'BEARISH' ? 'bear' : 'neut';

  return (
    <Panel
      title="Pattern Analogs · matrix profile"
      subtitle={`stumpy · ${analogs.window_days}d window · top-${analogs.top_k}`}
      accent={tone as any}
      source="analogs_stumpy"
      dataTimestamp={analogs.timestamp}
      sourceNote={`Top ${list.length} historical windows ranked by z-normalised Euclidean distance to the current ${analogs.window_days}-day fingerprint.`}
      right={<Chip tone={tone as any}>{bias}</Chip>}
    >
      <div className="mb-3 pb-3 border-b border-border/40 grid grid-cols-3 gap-3 text-center">
        <div>
          <div className="text-[9px] font-mono uppercase tracking-widest text-text-muted">Avg Fwd</div>
          <div className={clsx('text-2xl font-display font-bold tabular',
            tone === 'bull' && 'text-bull', tone === 'bear' && 'text-bear', tone === 'neut' && 'text-neut'
          )}>{avg >= 0 ? '+' : ''}{avg.toFixed(2)}%</div>
        </div>
        <div>
          <div className="text-[9px] font-mono uppercase tracking-widest text-text-muted">Horizon</div>
          <div className="text-2xl font-display font-bold tabular text-text-secondary">{analogs.horizon_days}d</div>
        </div>
        <div>
          <div className="text-[9px] font-mono uppercase tracking-widest text-text-muted">Current Window</div>
          <div className="text-[11px] font-mono tabular text-gold leading-tight mt-1">
            {analogs.current_window?.start_date}
            <br/>→ {analogs.current_window?.end_date}
          </div>
        </div>
      </div>
      <div className="space-y-2">
        {list.map((a: any, i: number) => {
          const t: 'bull' | 'bear' | 'neut' =
            a.forward_return_pct >  1 ? 'bull'
            : a.forward_return_pct < -1 ? 'bear'
            : 'neut';
          return (
            <div key={i} className="grid grid-cols-[18px_1fr_70px_70px] gap-2 items-baseline text-[10.5px] font-mono tabular py-1 border-b border-border/30 last:border-b-0">
              <span className="text-text-muted">#{i + 1}</span>
              <span className="text-text-secondary truncate">{a.start_date} → {a.end_date}</span>
              <span className="text-text-tertiary text-right">d={a.distance?.toFixed(2)}</span>
              <span className={clsx('text-right font-semibold',
                t === 'bull' && 'text-bull', t === 'bear' && 'text-bear', t === 'neut' && 'text-neut'
              )}>
                {a.forward_return_pct >= 0 ? '+' : ''}{a.forward_return_pct?.toFixed(2)}%
              </span>
            </div>
          );
        })}
      </div>
    </Panel>
  );
}

export function IntelligenceView({ all }: { all: any }) {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <NewsPanel news={all?.news} />
        <CorrelationsPanel corr={all?.correlations} />
      </div>
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <PatternsPanel patterns={all?.patterns} />
        <AnalogsPanel analogs={all?.analogs} />
      </div>
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <AnalystWatchPanel watch={all?.analyst_watch} />
      </div>
    </div>
  );
}
