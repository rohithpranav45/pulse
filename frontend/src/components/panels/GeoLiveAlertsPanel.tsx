import clsx from 'clsx';
import { Panel } from '@/components/ui/Panel';
import { SkeletonRows } from '@/components/ui/Skeleton';
import { api } from '@/lib/api';
import { usePolling } from '@/lib/hooks';

/**
 * Live geo alerts — the geospatial engine's real-time strip. The `_geo_news_ingest`
 * scheduler job scores the wire's geo-relevant headlines into {asset · event · node
 * vector} events with EDGE/prior tags; this panel shows them ranked by |conviction|
 * × tradeable, with the strongest node arrows and the EDGE tag from the graded edge
 * map. Backs onto /api/news/geo/live.
 */

interface GeoEdge {
  tradeable: boolean; basis: string;
  hit?: number; n?: number; p?: number; horizon?: number; slice?: string;
}
interface GeoLiveEvent {
  key: string; title: string; url?: string | null; source?: string | null;
  ts?: string | null; asset_ids: string[]; asset_type: string | null;
  event_type: string | null; severity: string; extract_source: string;
  nodes: Record<string, number>; rationale?: string;
  edges: Record<string, GeoEdge>; tradeable_nodes: string[];
  tradeable: boolean; conviction: number; scored_at: string;
}
interface GeoLiveData {
  available: boolean; count?: number; events?: GeoLiveEvent[]; caveat?: string;
}

const NODE_LABEL: Record<string, string> = {
  brent_flat: 'Bz flat', brent_structure: 'Bz M1-12', wti_brent: 'WTI−Bz',
  ho_crack: 'ULSD', gasoil_crack: 'Gasoil', rbob_crack: 'RBOB', regrade: 'Regrade',
  wti_flat: 'WTI flat', brent_m1_m2: 'Bz M1-2', brent_fly_123: 'Bz fly',
};

const arrow = (v: number) => (v > 0 ? (v >= 2 ? '↑↑' : '↑') : v < 0 ? (v <= -2 ? '↓↓' : '↓') : '·');
const fmtTime = (ts?: string | null) => {
  if (!ts) return '—';
  const d = new Date(ts);
  return Number.isNaN(d.getTime()) ? '—'
    : d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
};

export function GeoLiveAlertsPanel() {
  const { data, lastUpdated, error } = usePolling<GeoLiveData>(
    () => api.newsGeoLive(24) as Promise<GeoLiveData>, 60_000);

  if (!data && !error) {
    return (
      <Panel title="Live geo alerts" accent="gold" source="geo_live"
        staticMount lastSuccess={lastUpdated} fetchError={error}>
        <SkeletonRows rows={5} />
      </Panel>
    );
  }

  const events = data?.events ?? [];
  if (!data?.available || events.length === 0) {
    return (
      <Panel title="Live geo alerts" accent="gold" source="geo_live"
        staticMount lastSuccess={lastUpdated} fetchError={error}>
        <div className="text-[12px] font-mono text-text-tertiary px-3 py-6 text-center">
          {error
            ? `Live geo feed unreachable: ${(error as any)?.message ?? String(error)}`
            : 'No geo-relevant headlines scored yet — the ingest job scores the wire on its next tick.'}
        </div>
      </Panel>
    );
  }

  return (
    <Panel
      title="Live geo alerts"
      subtitle="Wire headlines → physical asset → price-node vector, ranked by conviction × edge"
      accent="gold"
      source="geo_live"
      staticMount
      lastSuccess={lastUpdated}
      fetchError={error}
      right={
        <span className="text-[9.5px] font-mono text-text-muted uppercase tracking-widest">
          {data.count ?? events.length} live
        </span>
      }
    >
      <div className="space-y-0.5">
        {events.map((e) => {
          const top = Object.entries(e.nodes)
            .sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]))
            .slice(0, 4);
          return (
            <div key={e.key}
              className="grid grid-cols-[88px_1fr_auto] gap-2 items-center text-[10.5px] font-mono py-1 px-1 rounded hover:bg-bg-card/30">
              <span className="text-text-muted text-[9.5px] tabular truncate" title={e.scored_at}>
                {fmtTime(e.ts)}
              </span>
              <div className="min-w-0">
                <div className="flex items-center gap-1.5">
                  <span className="text-[8px] uppercase tracking-wide text-text-muted bg-bg-card/60 border border-border/40 rounded px-1 py-px shrink-0"
                    title={`${e.asset_type ?? '?'} · ${e.event_type ?? '?'} · ${e.severity}`}>
                    {e.asset_type ?? '?'}/{e.event_type ?? '?'}
                  </span>
                  {e.url
                    ? <a href={e.url} target="_blank" rel="noreferrer"
                        className="text-text-secondary truncate hover:text-gold-bright" title={e.title}>{e.title}</a>
                    : <span className="text-text-secondary truncate" title={e.title}>{e.title}</span>}
                </div>
                <div className="flex flex-wrap gap-1 mt-0.5">
                  {top.map(([n, v]) => {
                    const isEdge = e.tradeable_nodes.includes(n);
                    return (
                      <span key={n}
                        className={clsx('text-[8.5px] font-mono rounded px-1 py-px border',
                          v > 0 ? 'text-bull border-bull/30' : v < 0 ? 'text-bear border-bear/30' : 'text-text-muted border-border/40',
                          isEdge && 'bg-gold/10 ring-1 ring-gold/40')}
                        title={isEdge
                          ? `${NODE_LABEL[n] ?? n} ${v > 0 ? '+' : ''}${v} — EDGE (${e.edges[n]?.hit != null ? `hit ${(e.edges[n].hit! * 100).toFixed(0)}%, n=${e.edges[n].n}, +${e.edges[n].horizon}d` : 'measured'})`
                          : `${NODE_LABEL[n] ?? n} ${v > 0 ? '+' : ''}${v} — prior (impact-map sign, not yet certified)`}>
                        {NODE_LABEL[n] ?? n} {arrow(v)}
                      </span>
                    );
                  })}
                </div>
              </div>
              <span className={clsx('text-[8px] uppercase tracking-wide rounded px-1 py-px shrink-0 self-start',
                e.tradeable
                  ? 'text-gold-bright bg-gold/10 border border-gold/30'
                  : 'text-text-muted border border-border/40')}
                title={e.tradeable
                  ? `EDGE node(s): ${e.tradeable_nodes.join(', ')} — directional hit-rate beat 50% in the graded study`
                  : 'prior — impact-map sign only; no certified edge for these nodes yet'}>
                {e.tradeable ? 'edge' : 'prior'}
              </span>
            </div>
          );
        })}
      </div>
      <div className="mt-3 text-[10px] font-mono text-text-muted leading-relaxed">
        Live wire → geo extraction (free Groq) → impact-map node vector → EDGE/prior tag from the graded
        event study. <span className="text-gold-bright">edge</span> = a node whose directional hit-rate
        beat 50% in the 2026 Hormuz-war study; others are impact-map priors. Single episode — read direction.
      </div>
    </Panel>
  );
}
