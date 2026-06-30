import { useMemo, useState } from 'react';
import clsx from 'clsx';
import { Panel } from '@/components/ui/Panel';
import { SkeletonRows } from '@/components/ui/Skeleton';
import { api } from '@/lib/api';
import { usePolling } from '@/lib/hooks';
import { projectLonLat, continentPaths } from '@/lib/worldOutline';

/**
 * Geo map (Sprint 9) — plots every placeable registry asset (chokepoint /
 * refinery / pipeline / field / producer) on a lightweight SVG world map (no map
 * dep). Each asset is sized/coloured by recent live-event activity (the Sprint-8
 * /api/news/geo/live store: event count, peak conviction, EDGE flag). Clicking an
 * asset shows its disruption_bias prior + recent headlines and pre-fills the
 * Geo-analogs lookup. Backs onto /api/news/geo/map.
 */

interface Headline {
  title: string; ts?: string | null; url?: string | null;
  conviction?: number; tradeable?: boolean; tradeable_nodes?: string[];
}
interface Activity {
  events: number; conviction: number; tradeable: boolean;
  last_ts: string | null; headlines: Headline[];
}
interface GeoAsset {
  id: string; name: string; type: string; region: string; country: string;
  lat: number; lon: number; capacity_mbd: number | null; carries: string[];
  note: string; disruption_bias: Record<string, number>; activity: Activity;
}
interface GeoMapData {
  available: boolean; count?: number; active?: number;
  assets?: GeoAsset[]; nodes?: Record<string, string>; caveat?: string;
}

const W = 720, H = 360;

const NODE_LABEL: Record<string, string> = {
  brent_flat: 'Brent flat', brent_structure: 'Brent M1-M12', wti_brent: 'WTI−Brent',
  ho_crack: 'ULSD crack', gasoil_crack: 'Gasoil crack', rbob_crack: 'RBOB crack',
  regrade: 'Regrade', wti_flat: 'WTI flat',
};
const TYPE_COLOR: Record<string, string> = {
  chokepoint: '#6aa9ff', refinery: '#c98bf0', pipeline: '#5ec8a0',
  field: '#e0a85c', producer: '#d98b8b',
};
const arrow = (v: number) => (v > 0 ? (v >= 2 ? '↑↑' : '↑') : v < 0 ? (v <= -2 ? '↓↓' : '↓') : '·');

// a synthetic, alias-resolvable headline so the analog lookup works even for an
// asset with no live headline yet (the asset name is a registry alias).
function headlineFor(a: GeoAsset): string {
  const newest = a.activity.headlines[0]?.title;
  if (newest) return newest;
  switch (a.type) {
    case 'chokepoint': return `Shipping through ${a.name} disrupted, oil flows halted`;
    case 'refinery':   return `Fire forces an outage at the ${a.name} refinery`;
    case 'pipeline':   return `${a.name} halted after an outage`;
    default:           return `Supply disruption at ${a.name}`;
  }
}

function radius(a: GeoAsset): number {
  const e = a.activity.events || 0;
  if (e <= 0) return 2.4;
  return Math.min(3 + Math.sqrt(e) * 1.9 + a.activity.conviction * 0.4, 10);
}
function fill(a: GeoAsset): string {
  if (a.activity.tradeable) return '#ffcf4d';          // EDGE → gold
  if (a.activity.events > 0) return '#f0a030';         // active prior → amber
  return TYPE_COLOR[a.type] ?? '#7a8699';
}

const fmtTime = (ts?: string | null) => {
  if (!ts) return '';
  const d = new Date(ts);
  return Number.isNaN(d.getTime()) ? '' :
    d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
};

export function GeoMapPanel({ onSelectHeadline }: { onSelectHeadline?: (title: string) => void }) {
  const { data, lastUpdated, error } = usePolling<GeoMapData>(
    () => api.newsGeoMap() as Promise<GeoMapData>, 60_000);
  const [selId, setSelId] = useState<string | null>(null);

  const lands = useMemo(() => continentPaths(W, H), []);
  const graticule = useMemo(() => {
    const lines: { x1: number; y1: number; x2: number; y2: number }[] = [];
    for (let lon = -150; lon <= 150; lon += 30) {
      const [x] = projectLonLat(lon, 0, W, H);
      lines.push({ x1: x, y1: 0, x2: x, y2: H });
    }
    for (let lat = -60; lat <= 60; lat += 30) {
      const [, y] = projectLonLat(0, lat, W, H);
      lines.push({ x1: 0, y1: y, x2: W, y2: y });
    }
    return lines;
  }, []);

  if (!data && !error) {
    return (
      <Panel title="Geo map" accent="gold" source="geo_map"
        staticMount lastSuccess={lastUpdated} fetchError={error}>
        <SkeletonRows rows={6} />
      </Panel>
    );
  }

  const assets = data?.assets ?? [];
  if (!data?.available || assets.length === 0) {
    return (
      <Panel title="Geo map" accent="gold" source="geo_map"
        staticMount lastSuccess={lastUpdated} fetchError={error}>
        <div className="text-[12px] font-mono text-text-tertiary px-3 py-6 text-center">
          {error ? `Geo map unreachable: ${(error as any)?.message ?? String(error)}`
                 : 'No geo assets to plot.'}
        </div>
      </Panel>
    );
  }

  // inactive first, active last → active dots paint on top
  const ordered = [...assets].sort((a, b) => (a.activity.events || 0) - (b.activity.events || 0));
  const selected = assets.find((a) => a.id === selId) ?? null;
  const bias = selected
    ? Object.entries(selected.disruption_bias).sort((x, y) => Math.abs(y[1]) - Math.abs(x[1]))
    : [];

  return (
    <Panel
      title="Geo map"
      subtitle="Physical oil assets · sized & coloured by live geo-alert activity"
      accent="gold"
      source="geo_map"
      staticMount
      lastSuccess={lastUpdated}
      fetchError={error}
      right={
        <span className="text-[9.5px] font-mono text-text-muted uppercase tracking-widest">
          {data.active ?? 0}/{assets.length} active
        </span>
      }
    >
      <div className="rounded-md border border-border/40 bg-bg-deep/40 overflow-hidden">
        <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto block" role="img"
          aria-label="World map of physical oil assets">
          {lands.map((d, i) => (
            <path key={i} d={d} fill="var(--color-bg-card, #1a2030)" fillOpacity={0.5}
              stroke="#3a4458" strokeOpacity={0.5} strokeWidth={0.6} />
          ))}
          {graticule.map((g, i) => (
            <line key={`g${i}`} x1={g.x1} y1={g.y1} x2={g.x2} y2={g.y2}
              stroke="#3a4458" strokeOpacity={0.25} strokeWidth={0.5} />
          ))}
          {ordered.map((a) => {
            const [cx, cy] = projectLonLat(a.lon, a.lat, W, H);
            const r = radius(a);
            const isSel = a.id === selId;
            const active = a.activity.events > 0;
            return (
              <g key={a.id} className="cursor-pointer"
                onClick={() => { setSelId(a.id); onSelectHeadline?.(headlineFor(a)); }}>
                <title>
                  {`${a.name} · ${a.type}/${a.region}` +
                    (active ? ` — ${a.activity.events} live event(s), conv ${a.activity.conviction.toFixed(1)}${a.activity.tradeable ? ', EDGE' : ''}` : '')}
                </title>
                {active && (
                  <circle cx={cx} cy={cy} r={r + 3} fill={fill(a)} fillOpacity={0.18} />
                )}
                <circle cx={cx} cy={cy} r={r} fill={fill(a)}
                  fillOpacity={active ? 0.95 : 0.5}
                  stroke={isSel ? '#ffffff' : '#0c0f17'}
                  strokeWidth={isSel ? 1.6 : 0.6} />
              </g>
            );
          })}
        </svg>
      </div>

      {/* legend */}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mt-2 px-1 text-[8.5px] font-mono text-text-muted">
        {Object.entries(TYPE_COLOR).map(([t, c]) => (
          <span key={t} className="flex items-center gap-1">
            <span className="inline-block w-2 h-2 rounded-full" style={{ background: c, opacity: 0.55 }} />
            {t}
          </span>
        ))}
        <span className="flex items-center gap-1">
          <span className="inline-block w-2 h-2 rounded-full" style={{ background: '#f0a030' }} />active
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block w-2 h-2 rounded-full" style={{ background: '#ffcf4d' }} />EDGE
        </span>
        <span className="text-text-tertiary">· dot size = live event count · click an asset</span>
      </div>

      {/* selected-asset detail */}
      {selected ? (
        <div className="mt-3 border-t border-border/40 pt-3 space-y-2">
          <div className="flex items-baseline justify-between gap-2">
            <div className="min-w-0">
              <span className="text-[12px] font-mono text-text-secondary font-bold">{selected.name}</span>
              <span className="text-[9.5px] font-mono text-text-muted ml-2 uppercase tracking-wide">
                {selected.type} · {selected.region} · {selected.country}
              </span>
            </div>
            <button
              onClick={() => onSelectHeadline?.(headlineFor(selected))}
              className="shrink-0 text-[9px] font-mono uppercase tracking-wide px-2 py-1 rounded border border-gold/40 text-gold-bright bg-gold/10 hover:bg-gold/20">
              Find analogs ▸
            </button>
          </div>
          <div className="text-[10px] font-mono text-text-muted">
            {selected.capacity_mbd != null && <>≈{selected.capacity_mbd} mb/d · </>}
            carries {selected.carries.join(', ') || '—'}
            {selected.note && <span className="text-text-tertiary"> · {selected.note}</span>}
          </div>

          {/* disruption bias */}
          <div>
            <div className="text-[9px] font-mono text-text-muted uppercase tracking-wide mb-1">
              Disruption bias (desk prior · supply-reducing event)
            </div>
            <div className="flex flex-wrap gap-1">
              {bias.map(([n, v]) => (
                <span key={n}
                  className={clsx('text-[9px] font-mono rounded px-1.5 py-0.5 border',
                    v > 0 ? 'text-bull border-bull/30' : v < 0 ? 'text-bear border-bear/30' : 'text-text-muted border-border/40')}
                  title={`${NODE_LABEL[n] ?? n}: ${v > 0 ? '+' : ''}${v}`}>
                  {NODE_LABEL[n] ?? n} {arrow(v)}
                </span>
              ))}
            </div>
          </div>

          {/* recent live headlines for this asset */}
          {selected.activity.headlines.length > 0 ? (
            <div>
              <div className="text-[9px] font-mono text-text-muted uppercase tracking-wide mb-1">
                Recent live alerts ({selected.activity.events})
                {selected.activity.tradeable && <span className="text-gold-bright"> · EDGE</span>}
              </div>
              <div className="space-y-0.5">
                {selected.activity.headlines.map((h, i) => (
                  <div key={i} className="flex items-center gap-2 text-[10px] font-mono py-0.5">
                    <span className="text-text-tertiary w-[78px] shrink-0">{fmtTime(h.ts)}</span>
                    {h.url
                      ? <a href={h.url} target="_blank" rel="noreferrer"
                          className="text-text-secondary truncate hover:text-gold-bright" title={h.title}>{h.title}</a>
                      : <span className="text-text-secondary truncate" title={h.title}>{h.title}</span>}
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="text-[10px] font-mono text-text-tertiary">
              No live alerts for this asset yet — clicking “Find analogs” uses a representative disruption headline.
            </div>
          )}
        </div>
      ) : (
        <div className="mt-2 text-[10px] font-mono text-text-tertiary px-1">
          Click an asset for its disruption_bias prior, recent alerts, and to run the geo-analog lookup.
        </div>
      )}
    </Panel>
  );
}
