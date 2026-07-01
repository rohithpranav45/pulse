import { useMemo, useState } from 'react';
import clsx from 'clsx';
import { Panel } from '@/components/ui/Panel';
import { SkeletonRows } from '@/components/ui/Skeleton';
import { api } from '@/lib/api';
import { usePolling } from '@/lib/hooks';
import { projectLonLat, landPaths } from '@/lib/worldOutline';

/**
 * Geo map (Sprint 9) — plots every placeable registry asset on a lightweight but
 * polished SVG world map (real Natural-Earth coastlines, no map dependency). Each
 * asset is sized/coloured by recent live-event activity (the Sprint-8 store: event
 * count, peak conviction, EDGE flag) — EDGE assets get a gold radar pulse. Clicking
 * an asset shows its disruption_bias prior + recent headlines and pre-fills the
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
// Crop the empty poles (Antarctica / high Arctic) so the populated latitudes fill
// the frame — all assets sit between ~+59° and +2°. viewBox = lat +83° … −60°.
const VB_Y = 14, VB_H = 286;

const NODE_LABEL: Record<string, string> = {
  brent_flat: 'Brent flat', brent_structure: 'Brent M1-M12', wti_brent: 'WTI−Brent',
  ho_crack: 'ULSD crack', gasoil_crack: 'Gasoil crack', rbob_crack: 'RBOB crack',
  regrade: 'Regrade', wti_flat: 'WTI flat',
};
const TYPE_COLOR: Record<string, string> = {
  chokepoint: '#5b8def', refinery: '#b57cf0', pipeline: '#46c8a0',
  field: '#e0a24e', producer: '#e06d78',
};
const TYPE_LABEL: Record<string, string> = {
  chokepoint: 'Chokepoint', refinery: 'Refinery', pipeline: 'Pipeline',
  field: 'Field', producer: 'Producer',
};
const ACTIVE_COLOR = '#f5a623';
const EDGE_COLOR = '#ffd24d';

const arrow = (v: number) => (v > 0 ? (v >= 2 ? '↑↑' : '↑') : v < 0 ? (v <= -2 ? '↓↓' : '↓') : '·');

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
  if (e <= 0) return 2.1;
  return Math.min(3 + Math.sqrt(e) * 1.7 + a.activity.conviction * 0.35, 9);
}
function markColor(a: GeoAsset): string {
  if (a.activity.tradeable) return EDGE_COLOR;
  if (a.activity.events > 0) return ACTIVE_COLOR;
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

  const lands = useMemo(() => landPaths(W, H), []);
  const graticule = useMemo(() => {
    const lines: { d: string; major: boolean }[] = [];
    for (let lon = -150; lon <= 150; lon += 30) {
      const [x] = projectLonLat(lon, 0, W, H);
      lines.push({ d: `M${x},0 L${x},${H}`, major: lon === 0 });
    }
    for (let lat = -60; lat <= 60; lat += 30) {
      const [, y] = projectLonLat(0, lat, W, H);
      lines.push({ d: `M0,${y} L${W},${y}`, major: lat === 0 });
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
      subtitle="Physical oil assets · sized & lit by live geo-alert activity"
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
      <div className="relative rounded-lg overflow-hidden ring-1 ring-white/5 shadow-[0_2px_24px_rgba(0,0,0,0.45)]">
        <svg viewBox={`0 ${VB_Y} ${W} ${VB_H}`} className="w-full h-auto block" role="img"
          preserveAspectRatio="xMidYMid meet" aria-label="World map of physical oil assets">
          <defs>
            <linearGradient id="geoOcean" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#0c1424" />
              <stop offset="55%" stopColor="#0a1120" />
              <stop offset="100%" stopColor="#070c17" />
            </linearGradient>
            <linearGradient id="geoLand" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#233150" />
              <stop offset="100%" stopColor="#18223a" />
            </linearGradient>
            <radialGradient id="geoVignette" cx="50%" cy="46%" r="72%">
              <stop offset="60%" stopColor="#000000" stopOpacity="0" />
              <stop offset="100%" stopColor="#000000" stopOpacity="0.45" />
            </radialGradient>
            <filter id="geoGlow" x="-120%" y="-120%" width="340%" height="340%">
              <feGaussianBlur stdDeviation="3.2" result="b" />
              <feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge>
            </filter>
          </defs>

          {/* ocean */}
          <rect x="0" y="0" width={W} height={H} fill="url(#geoOcean)" />

          {/* graticule */}
          {graticule.map((g, i) => (
            <path key={`g${i}`} d={g.d} fill="none"
              stroke={g.major ? '#38507e' : '#2a3850'}
              strokeOpacity={g.major ? 0.35 : 0.16} strokeWidth={g.major ? 0.7 : 0.5} />
          ))}

          {/* land */}
          {lands.map((d, i) => (
            <path key={`l${i}`} d={d} fillRule="evenodd" fill="url(#geoLand)"
              stroke="#3d5c8c" strokeWidth={0.5} strokeOpacity={0.6} strokeLinejoin="round" />
          ))}

          {/* subtle vignette on top of land+ocean, under the markers */}
          <rect x="0" y="0" width={W} height={H} fill="url(#geoVignette)" pointerEvents="none" />

          {/* assets */}
          {ordered.map((a) => {
            const [cx, cy] = projectLonLat(a.lon, a.lat, W, H);
            const r = radius(a);
            const isSel = a.id === selId;
            const active = a.activity.events > 0;
            const c = markColor(a);
            return (
              <g key={a.id} className="group/mk cursor-pointer"
                onClick={() => { setSelId(a.id); onSelectHeadline?.(headlineFor(a)); }}>
                <title>
                  {`${a.name} · ${TYPE_LABEL[a.type] ?? a.type} · ${a.region}` +
                    (active ? ` — ${a.activity.events} live event(s), conv ${a.activity.conviction.toFixed(1)}${a.activity.tradeable ? ', EDGE' : ''}` : '')}
                </title>

                {/* EDGE radar pulse */}
                {a.activity.tradeable && (
                  <circle cx={cx} cy={cy} r={r} fill="none" stroke={EDGE_COLOR} strokeWidth={1}>
                    <animate attributeName="r" values={`${r};${r + 7};${r}`} dur="2.6s" repeatCount="indefinite" />
                    <animate attributeName="opacity" values="0.55;0;0.55" dur="2.6s" repeatCount="indefinite" />
                  </circle>
                )}

                {/* soft glow for active assets */}
                {active && (
                  <circle cx={cx} cy={cy} r={r + 2.5} fill={c} opacity={0.22} filter="url(#geoGlow)" />
                )}

                {/* hover halo */}
                <circle cx={cx} cy={cy} r={r + 3.5} fill={c}
                  className="opacity-0 group-hover/mk:opacity-25 transition-opacity duration-150" />

                {/* selection ring */}
                {isSel && (
                  <circle cx={cx} cy={cy} r={r + 3} fill="none" stroke="#ffffff"
                    strokeWidth={1.4} strokeOpacity={0.9} />
                )}

                {/* core */}
                <circle cx={cx} cy={cy} r={r} fill={c}
                  fillOpacity={active ? 0.98 : 0.62}
                  stroke="#0a0f1a" strokeWidth={0.6}
                  className="group-hover/mk:brightness-125 transition-[filter] duration-150" />
              </g>
            );
          })}
        </svg>
      </div>

      {/* legend */}
      <div className="flex flex-wrap items-center gap-x-3.5 gap-y-1.5 mt-2.5 px-1 text-[8.5px] font-mono text-text-muted">
        {Object.entries(TYPE_COLOR).map(([t, c]) => (
          <span key={t} className="flex items-center gap-1.5">
            <span className="inline-block w-2 h-2 rounded-full" style={{ background: c, opacity: 0.6 }} />
            {TYPE_LABEL[t] ?? t}
          </span>
        ))}
        <span className="w-px h-3 bg-border/50" />
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-2 h-2 rounded-full" style={{ background: ACTIVE_COLOR }} />active
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-2 h-2 rounded-full ring-2 ring-gold/40" style={{ background: EDGE_COLOR }} />EDGE
        </span>
        <span className="text-text-tertiary">· dot size = live events · click an asset</span>
      </div>

      {/* selected-asset detail */}
      {selected ? (
        <div className="mt-3 border-t border-border/40 pt-3 space-y-2.5">
          <div className="flex items-baseline justify-between gap-2">
            <div className="min-w-0 flex items-center gap-2">
              <span className="inline-block w-2.5 h-2.5 rounded-full shrink-0"
                style={{ background: markColor(selected) }} />
              <span className="text-[12.5px] font-mono text-text-secondary font-bold truncate">{selected.name}</span>
              <span className="text-[9px] font-mono text-text-muted uppercase tracking-wide shrink-0">
                {TYPE_LABEL[selected.type] ?? selected.type} · {selected.region} · {selected.country}
              </span>
            </div>
            <button
              onClick={() => onSelectHeadline?.(headlineFor(selected))}
              className="shrink-0 text-[9px] font-mono uppercase tracking-wide px-2 py-1 rounded border border-gold/40 text-gold-bright bg-gold/10 hover:bg-gold/20 transition-colors">
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
                    v > 0 ? 'text-bull border-bull/30 bg-bull/5' : v < 0 ? 'text-bear border-bear/30 bg-bear/5' : 'text-text-muted border-border/40')}
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
              No live alerts for this asset yet — “Find analogs” uses a representative disruption headline.
            </div>
          )}
        </div>
      ) : (
        <div className="mt-2.5 text-[10px] font-mono text-text-tertiary px-1">
          Click an asset for its disruption_bias prior, recent alerts, and to run the geo-analog lookup.
        </div>
      )}
    </Panel>
  );
}
