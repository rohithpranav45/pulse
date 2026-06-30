/**
 * Coarse continent outlines for a lightweight equirectangular world map.
 * =====================================================================
 * Hand-simplified silhouettes (lon/lat rings) — recognisable background context
 * for plotting geo-assets, with NO heavy mapping dependency. Precision is not the
 * point: the assets are plotted at their exact registry lat/lon; the land is just
 * a faint backdrop so the Middle-East / USGC / ARA / Asia clusters read spatially.
 *
 * Equirectangular projection: lon ∈ [-180,180] → x ∈ [0,W]; lat ∈ [90,-90] → y ∈ [0,H].
 */

// [lon, lat] rings, clockwise. Coarse by design.
const CONTINENTS: [number, number][][] = [
  // North America
  [[-168, 65], [-150, 71], [-125, 70], [-95, 72], [-80, 73], [-62, 75], [-58, 60],
   [-66, 48], [-70, 42], [-76, 35], [-81, 25], [-97, 18], [-105, 20], [-114, 30],
   [-124, 40], [-128, 50], [-138, 58], [-152, 60], [-168, 65]],
  // Central America tail
  [[-92, 16], [-84, 10], [-78, 8], [-83, 15], [-92, 16]],
  // South America
  [[-80, 8], [-60, 11], [-50, 0], [-35, -6], [-40, -23], [-55, -35], [-66, -45],
   [-74, -52], [-72, -30], [-78, -15], [-81, -5], [-80, 8]],
  // Africa
  [[-17, 15], [-10, 30], [10, 37], [20, 33], [32, 31], [43, 12], [51, 12], [42, -2],
   [40, -25], [25, -34], [15, -30], [9, -2], [8, 5], [-8, 5], [-17, 15]],
  // Europe
  [[-10, 36], [-8, 44], [-2, 49], [2, 51], [6, 58], [11, 64], [26, 71], [40, 67],
   [30, 58], [28, 47], [18, 40], [8, 44], [-2, 40], [-10, 36]],
  // Asia (incl. Middle East, India, SE Asia, Russia)
  [[26, 47], [35, 37], [45, 40], [49, 30], [57, 25], [67, 25], [70, 20], [77, 8],
   [82, 16], [90, 22], [92, 21], [100, 13], [106, 9], [110, 20], [122, 30],
   [122, 41], [131, 43], [136, 55], [162, 61], [180, 67], [180, 72], [140, 74],
   [100, 77], [70, 73], [58, 68], [44, 66], [33, 67], [30, 56], [40, 50],
   [30, 46], [26, 47]],
  // Australia
  [[113, -22], [122, -18], [131, -12], [142, -11], [146, -18], [153, -28],
   [150, -38], [140, -38], [131, -32], [115, -35], [113, -22]],
];

export function projectLonLat(lon: number, lat: number, w: number, h: number): [number, number] {
  const x = ((lon + 180) / 360) * w;
  const y = ((90 - lat) / 180) * h;
  return [x, y];
}

/** SVG path `d` strings for the continent backdrop at the given viewBox size. */
export function continentPaths(w: number, h: number): string[] {
  return CONTINENTS.map((ring) =>
    ring
      .map(([lon, lat], i) => {
        const [x, y] = projectLonLat(lon, lat, w, h);
        return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`;
      })
      .join(' ') + ' Z',
  );
}
