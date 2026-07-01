/**
 * Equirectangular world projection + real coastline paths for the geo map.
 * =======================================================================
 * Land geometry is Natural Earth 110m (public domain), Douglas-Peucker simplified
 * to ~1k points (`worldLand.ts`, ~14 KB) — accurate, recognisable continents with
 * NO heavy mapping dependency. Assets plot at their exact registry lat/lon on top.
 *
 * Projection: lon ∈ [-180,180] → x ∈ [0,W]; lat ∈ [90,-90] → y ∈ [0,H].
 */

import { LAND_POLYGONS } from './worldLand';

export function projectLonLat(lon: number, lat: number, w: number, h: number): [number, number] {
  const x = ((lon + 180) / 360) * w;
  const y = ((90 - lat) / 180) * h;
  return [x, y];
}

/**
 * One SVG path `d` per landmass polygon (exterior + holes), for the given viewBox.
 * Holes are appended as extra sub-paths so `fill-rule: evenodd` cuts them out
 * (e.g. the Caspian). Cached per (w,h) since the geometry never changes.
 */
const _cache = new Map<string, string[]>();
export function landPaths(w: number, h: number): string[] {
  const key = `${w}x${h}`;
  const hit = _cache.get(key);
  if (hit) return hit;
  const paths = LAND_POLYGONS.map((poly) =>
    poly
      .map((ring) =>
        ring
          .map(([lon, lat], i) => {
            const [x, y] = projectLonLat(lon, lat, w, h);
            return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`;
          })
          .join(' ') + ' Z',
      )
      .join(' '),
  );
  _cache.set(key, paths);
  return paths;
}
