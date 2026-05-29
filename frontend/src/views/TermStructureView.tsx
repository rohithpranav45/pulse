import { Fragment } from 'react';
import { Panel } from '@/components/ui/Panel';
import { Chip } from '@/components/ui/Chip';
import { SkeletonRows } from '@/components/ui/Skeleton';
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend } from 'recharts';
import clsx from 'clsx';

const COLORS = ['#d4af37', '#4d8eff', '#22d3ee', '#a78bfa', '#10d997'];

function corrColor(v: number) {
  const a = Math.abs(v);
  const hue = v >= 0 ? 152 : 348;
  return `hsl(${hue}, 70%, ${15 + a * 40}%)`;
}

function HeatmapPanel({ ts }: { ts: any }) {
  // Server shape: { correlation_matrix: { labels: ["Brent","WTI","RBOB","Heat Oil","Nat Gas"], matrix: [[...],[...]], data_days } }
  const raw = ts?.correlation_matrix;
  if (!raw) return <Panel title="Term Heatmap"><SkeletonRows rows={5} /></Panel>;
  // Convert dict-of-dicts → labels+matrix if needed
  let labels: string[] = raw.labels ?? [];
  let matrix: number[][] = Array.isArray(raw.matrix) ? raw.matrix : [];
  if ((!labels.length || !matrix.length) && raw.matrix && typeof raw.matrix === 'object' && !Array.isArray(raw.matrix)) {
    labels = Object.keys(raw.matrix);
    matrix = labels.map(r => labels.map(c => raw.matrix[r]?.[c] ?? 0));
  }
  if (!labels.length || !matrix.length) {
    return <Panel title="Term Heatmap"><SkeletonRows rows={5} /></Panel>;
  }
  return (
    <Panel title="5-Product Correlation" subtitle={`M1 returns · ${raw.data_days ?? 90}d`}>
      <div className="grid gap-1.5" style={{ gridTemplateColumns: `80px repeat(${labels.length}, 1fr)` }}>
        <div />
        {labels.map(l => <div key={l} className="text-[9px] font-mono uppercase tracking-widest text-text-tertiary text-center pb-1">{l}</div>)}
        {labels.map((rowL, ri) => (
          <Fragment key={rowL}>
            <div className="text-[9px] font-mono uppercase tracking-widest text-text-tertiary flex items-center justify-end pr-1">{rowL}</div>
            {labels.map((colL, ci) => {
              const v = matrix[ri]?.[ci] ?? 0;
              const same = ri === ci;
              return (
                <div
                  key={`${rowL}-${colL}`}
                  className="aspect-square rounded flex items-center justify-center text-[10px] font-mono font-bold tabular transition-transform hover:scale-110 cursor-default"
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

function _stripArray(s: any): any[] {
  if (Array.isArray(s)) return s;
  if (Array.isArray(s?.prices)) return s.prices;
  if (Array.isArray(s?.contracts)) return s.contracts;
  return [];
}

function StripTable({ ts }: { ts: any }) {
  if (!ts?.strips) return <Panel title="Forward Strips"><SkeletonRows rows={6} /></Panel>;
  const strips = ts.strips;
  const products = Object.keys(strips);
  const months = ['M1','M2','M3','M4','M5','M6','M7','M8','M9','M10','M11','M12'];
  return (
    <Panel title="Forward Strip Matrix" subtitle="M1 → M12 settlements">
      <div className="overflow-x-auto">
        <table className="w-full text-[10.5px] font-mono tabular">
          <thead>
            <tr className="text-text-muted text-[9px] uppercase tracking-widest border-b border-border">
              <th className="text-left py-2">Product</th>
              {months.map(m => <th key={m} className="text-right px-2">{m}</th>)}
              <th className="text-right px-2">M1–M12</th>
            </tr>
          </thead>
          <tbody>
            {products.map((p, i) => {
              const strip = _stripArray(strips[p]);
              const m1 = strip[0]?.price ?? 0;
              const m12 = strip[11]?.price ?? 0;
              const spread = m12 - m1;
              return (
                <tr key={p} className="border-b border-border/40 hover:bg-bg-hover/30">
                  <td className="py-1.5 font-display font-semibold tracking-wider text-text-secondary" style={{ color: COLORS[i % COLORS.length] }}>{p}</td>
                  {months.map((_, mi) => (
                    <td key={mi} className="text-right px-2 text-text-secondary">
                      {strip[mi]?.price ? strip[mi].price.toFixed(2) : '—'}
                    </td>
                  ))}
                  <td className={clsx('text-right px-2 font-semibold', spread > 0 ? 'text-bear' : 'text-bull')}>
                    {spread >= 0 ? '+' : ''}{spread.toFixed(2)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}

function NormalizedCurve({ ts }: { ts: any }) {
  if (!ts?.strips) return <Panel title="Normalized Curves"><SkeletonRows rows={5} /></Panel>;
  const strips = ts.strips;
  const products = Object.keys(strips);
  const data = Array.from({ length: 12 }, (_, i) => {
    const row: any = { label: `M${i + 1}` };
    products.forEach(p => {
      const strip = _stripArray(strips[p]);
      const m1 = strip[0]?.price ?? 0;
      const v = strip[i]?.price;
      if (m1 && v) row[p] = +((v / m1 - 1) * 100).toFixed(2);
    });
    return row;
  });

  return (
    <Panel title="Normalized Forward Curves" subtitle="% deviation from M1">
      <ResponsiveContainer width="100%" height={340}>
        <LineChart data={data} margin={{ top: 10, right: 20, bottom: 5, left: -10 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1c2745" />
          <XAxis dataKey="label" tick={{ fontSize: 10, fill: '#6b809e' }} axisLine={{ stroke: '#1c2745' }} />
          <YAxis tick={{ fontSize: 10, fill: '#6b809e' }} axisLine={{ stroke: '#1c2745' }} unit="%" />
          <Tooltip contentStyle={{ background: '#0f1729', border: '1px solid #1c2745', borderRadius: 6, fontSize: 11 }} />
          <Legend wrapperStyle={{ fontSize: 10, fontFamily: 'JetBrains Mono', letterSpacing: '0.15em' }} />
          {products.map((p, i) => (
            <Line key={p} type="monotone" dataKey={p} stroke={COLORS[i]} strokeWidth={2.5} dot={{ r: 3, fill: COLORS[i] }} />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </Panel>
  );
}

export function TermStructureView({ all }: { all: any }) {
  const ts = all?.term_structure;
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <HeatmapPanel ts={ts} />
        <Panel title="Curve Structure Read" subtitle="Snapshot interpretation">
          <div className="space-y-3 text-[12px] text-text-secondary leading-relaxed">
            <p>
              Backwardation (negative M1–M12 spread) signals near-term tightness — physical buyers paying up for prompt barrels.
              Contango (positive spread) reflects oversupply and easier storage economics.
            </p>
            <div className="grid grid-cols-2 gap-2 mt-3">
              <Chip tone="bull">BACKWARDATION ⇒ Bullish</Chip>
              <Chip tone="bear">CONTANGO ⇒ Bearish</Chip>
            </div>
          </div>
        </Panel>
      </div>
      <StripTable ts={ts} />
      <NormalizedCurve ts={ts} />
    </div>
  );
}
