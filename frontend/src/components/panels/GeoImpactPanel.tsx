import { useMemo } from 'react';
import clsx from 'clsx';
import { Panel } from '@/components/ui/Panel';
import { SkeletonRows } from '@/components/ui/Skeleton';
import { api } from '@/lib/api';
import { usePolling } from '@/lib/hooks';

/**
 * Geo node-impact edge map — the graded "does location-news actually move each
 * price node?" table behind the geospatial engine. For every price node it shows
 * the directional hit-rate at +1d / +5d (binomial vs 50%, prior-then-learn EDGE
 * flag) and the measured magnitude beta. Read from the cached per-node event
 * study (/api/news/geo) over the GDELT × node tape.
 */

interface HitRow {
  slice: string; node: string; asset_type: string; regime: string;
  hit: number; n: number; p: number; edge: number; significant: boolean;
}
interface BetaRow { node: string; beta: number; t: number | null; n: number; measured: boolean; }
interface CatalogRow {
  id: string; label: string; unit: string; provenance: string;
  estimate: boolean; available: boolean; gap_reason?: string;
}
interface GeoData {
  available: boolean; reason?: string;
  n_events?: number; n_claims?: number; span?: [string, string];
  by_asset_type?: Record<string, number>; min_n?: number; p_sig?: number;
  hit_tables?: Record<string, HitRow[]>; betas?: Record<string, BetaRow[]>;
  node_catalog?: CatalogRow[]; index_size?: number | null;
}

// canonical node display order + short labels
const NODE_ORDER = ['brent_flat', 'brent_structure', 'wti_brent', 'ho_crack',
  'gasoil_crack', 'rbob_crack', 'regrade'];
const NODE_LABEL: Record<string, string> = {
  brent_flat: 'Brent flat', brent_structure: 'Brent M1-M12', wti_brent: 'WTI−Brent',
  ho_crack: 'ULSD crack', gasoil_crack: 'Gasoil crack', rbob_crack: 'RBOB crack',
  regrade: 'Regrade', wti_flat: 'WTI flat', brent_m1_m2: 'Brent M1-M2',
  brent_fly_123: 'Brent fly',
};

const hitTone = (hit: number) => (hit >= 0.58 ? 'bull' : hit <= 0.42 ? 'bear' : 'neut');
const fmtHit = (h: number) => `${(h * 100).toFixed(0)}%`;

export function GeoImpactPanel() {
  const { data, lastUpdated, error } = usePolling<GeoData>(
    () => api.newsGeo() as Promise<GeoData>, 120_000);

  // node/*/* slice per horizon → {node: row}; prefer the all-asset node row
  const byNode = useMemo(() => {
    const out: Record<string, { h1?: HitRow; h5?: HitRow; b5?: BetaRow }> = {};
    const grab = (rows: HitRow[] | undefined, key: 'h1' | 'h5') => {
      for (const r of rows ?? []) {
        if (r.slice !== 'node') continue;
        (out[r.node] ??= {})[key] = r;
      }
    };
    grab(data?.hit_tables?.['1'], 'h1');
    grab(data?.hit_tables?.['5'], 'h5');
    for (const b of data?.betas?.['5'] ?? []) (out[b.node] ??= {}).b5 = b;
    return out;
  }, [data]);

  if (!data && !error) {
    return (
      <Panel title="Geo node-impact map" accent="gold" source="geo_event_study"
        staticMount lastSuccess={lastUpdated} fetchError={error}>
        <SkeletonRows rows={8} />
      </Panel>
    );
  }
  if (!data?.available) {
    return (
      <Panel title="Geo node-impact map" accent="gold" source="geo_event_study"
        staticMount lastSuccess={lastUpdated} fetchError={error}>
        <div className="text-[12px] font-mono text-text-tertiary px-3 py-6 text-center">
          {error
            ? `Geo edge-map endpoint unreachable: ${(error as any)?.message ?? String(error)}`
            : (data?.reason ?? 'No graded geo edge map cached yet — run the per-node event study.')}
        </div>
      </Panel>
    );
  }

  const nodes = NODE_ORDER.filter((n) => byNode[n]);
  return (
    <Panel
      title="Geo node-impact map"
      subtitle="Chokepoint/refinery news → realised forward node move · directional hit-rate"
      accent="gold"
      source="geo_event_study"
      staticMount
      lastSuccess={lastUpdated}
      fetchError={error}
      right={
        <span className="text-[9.5px] font-mono text-text-muted uppercase tracking-widest">
          {data.n_events ?? 0} events · {data.n_claims ?? 0} claims
        </span>
      }
    >
      <div className="grid grid-cols-[1fr_72px_72px_88px] gap-2 text-[9.5px] font-mono text-text-muted uppercase tracking-wide px-1 mb-1">
        <span>Price node</span>
        <span className="text-right">+1d hit</span>
        <span className="text-right">+5d hit</span>
        <span className="text-right">5d beta</span>
      </div>
      <div className="space-y-0.5">
        {nodes.map((n) => {
          const r = byNode[n];
          const h1 = r.h1, h5 = r.h5, b5 = r.b5;
          return (
            <div key={n}
              className="grid grid-cols-[1fr_72px_72px_88px] gap-2 items-center text-[10.5px] font-mono tabular py-1 px-1 rounded hover:bg-bg-card/30"
              title={`${NODE_LABEL[n] ?? n} — +5d ${h5 ? `${fmtHit(h5.hit)} on n=${h5.n}, p=${h5.p}` : 'n/a'}`}>
              <span className="text-text-secondary truncate">{NODE_LABEL[n] ?? n}</span>
              {[h1, h5].map((h, i) => (
                <span key={i} className="text-right flex items-center justify-end gap-1">
                  {h ? (
                    <>
                      <span className={clsx('font-bold',
                        hitTone(h.hit) === 'bull' && 'text-bull',
                        hitTone(h.hit) === 'bear' && 'text-bear',
                        hitTone(h.hit) === 'neut' && 'text-text-muted')}>
                        {fmtHit(h.hit)}
                      </span>
                      {h.significant && (
                        <span className="text-[7.5px] uppercase text-gold-bright bg-gold/10 border border-gold/30 rounded px-0.5"
                          title={`EDGE — binomial p=${h.p} on n=${h.n}`}>e</span>
                      )}
                    </>
                  ) : <span className="text-text-muted">—</span>}
                </span>
              ))}
              <span className={clsx('text-right',
                b5?.measured ? 'text-gold-bright font-bold' : 'text-text-tertiary')}
                title={b5 ? `beta ${b5.beta} (t=${b5.t}, n=${b5.n})` : ''}>
                {b5 ? `${b5.beta > 0 ? '+' : ''}${b5.beta.toFixed(2)}${b5.measured ? '*' : ''}` : '—'}
              </span>
            </div>
          );
        })}
      </div>
      <div className="mt-3 text-[10px] font-mono text-text-muted leading-relaxed">
        <span className="text-bull">green</span> = move agrees with the impact-map prior ≥58%;
        <span className="text-bear"> red</span> = reverses ≤42%; <span className="text-gold-bright">e</span> = binomial
        EDGE (p&lt;{data.p_sig ?? 0.1}, n≥{data.min_n ?? 20}); <span className="text-gold-bright">*</span> = measured beta (|t|≥2).
        Single episode (Hormuz war, {data.span?.[0]} → {data.span?.[1]}); clustered events ⇒ p optimistic — read direction.
      </div>
    </Panel>
  );
}
