import { Fragment, ReactNode, useState } from 'react';
import { motion } from 'framer-motion';
import clsx from 'clsx';
import {
  Anchor, Ship, Droplets, Activity, AlertOctagon, BarChart3, Cloud, ChevronDown,
} from 'lucide-react';
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend } from 'recharts';

import { Panel } from '@/components/ui/Panel';
import { Chip } from '@/components/ui/Chip';
import { Stat } from '@/components/ui/Stat';
import { SkeletonRows, Skeleton } from '@/components/ui/Skeleton';
import { EIASurprisePanel } from '@/components/panels/EIASurprisePanel';
import { ForwardCoverChart } from '@/components/panels/ForwardCoverChart';
import { fmt } from '@/lib/fmt';
import { staggerContainer, fadeUp } from '@/lib/motion';

// ── LazySection: mount-once-on-first-open <details> wrapper ────────────────
// The polling/render work for each section's panels doesn't kick in until
// the user expands it. Once opened, the panels stay mounted on collapse so
// toggling doesn't thrash. Default-open sections render immediately.
function LazySection({
  id,
  title,
  subtitle,
  defaultOpen = false,
  children,
}: {
  id: string;
  title: string;
  subtitle?: string;
  defaultOpen?: boolean;
  children: ReactNode;
}) {
  const [openedOnce, setOpenedOnce] = useState(defaultOpen);
  return (
    <details
      open={defaultOpen}
      onToggle={(e) => {
        if ((e.currentTarget as HTMLDetailsElement).open && !openedOnce) {
          setOpenedOnce(true);
        }
      }}
      className="group rounded-lg border border-border/40 bg-bg-elev/20 overflow-hidden"
    >
      <summary
        data-section={id}
        className="flex items-center gap-3 px-4 py-3 cursor-pointer select-none hover:bg-bg-hover/30 transition-colors list-none"
      >
        <ChevronDown
          className="w-3.5 h-3.5 text-text-tertiary transition-transform group-open:rotate-0 -rotate-90"
        />
        <span className="font-display tracking-[0.18em] uppercase text-[12px] text-text-primary">
          {title}
        </span>
        {subtitle && (
          <span className="text-[10px] font-mono uppercase tracking-[0.24em] text-text-muted">
            · {subtitle}
          </span>
        )}
        <div className="flex-1 h-px bg-gradient-to-r from-border/40 via-border/20 to-transparent ml-2" />
        {!openedOnce && (
          <span className="text-[9px] font-mono uppercase tracking-widest text-text-muted">click to load</span>
        )}
      </summary>
      <div className="px-4 pt-3 pb-5">
        {openedOnce ? children : null}
      </div>
    </details>
  );
}

// ─── shared helpers ────────────────────────────────────────────────────────

const COLORS = ['#d4af37', '#4d8eff', '#22d3ee', '#a78bfa', '#10d997'];

function corrColor(v: number) {
  const a = Math.abs(v);
  const hue = v >= 0 ? 152 : 348;
  return `hsl(${hue}, 70%, ${15 + a * 40}%)`;
}

// ─── Spreads & Curve section panels (from SpreadsView) ─────────────────────

function HeatmapPanel({ ts }: { ts: any }) {
  const raw = ts?.correlation_matrix;
  if (!raw) return <Panel title="Term Heatmap"><SkeletonRows rows={5} /></Panel>;
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
    <Panel title="5-Product Correlation" subtitle={`M1 returns · ${raw.data_days ?? 90}d`} source="term_structure_calc" dataTimestamp={ts?.timestamp}>
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
    <Panel title="Forward Strip Matrix" subtitle="M1 → M12 settlements" source="multi_curve" dataTimestamp={ts?.timestamp}>
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
                <tr key={p} className="border-b border-border/40 hover:bg-bg-hover/30 transition-colors">
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
    <Panel title="Normalized Forward Curves" subtitle="% deviation from M1" source="multi_curve" dataTimestamp={ts?.timestamp}>
      <ResponsiveContainer width="100%" height={320}>
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

function CalendarSpreadMatrix({ curve }: { curve: any }) {
  if (!curve?.brent) return <Panel title="Calendar Spreads"><SkeletonRows rows={6} /></Panel>;
  const brent = curve.brent?.contracts ?? [];
  const wti = curve.wti?.contracts ?? [];
  const rows: any[] = [];
  for (let i = 0; i < 11; i++) {
    const b = brent[i]?.price && brent[i + 1]?.price ? brent[i].price - brent[i + 1].price : null;
    const w = wti[i]?.price && wti[i + 1]?.price ? wti[i].price - wti[i + 1].price : null;
    rows.push({ label: `M${i + 1}–M${i + 2}`, brent: b, wti: w });
  }
  const cell = (v: number | null) => {
    if (v === null) return <span className="text-text-muted">—</span>;
    const tone = v > 0 ? 'text-bull' : 'text-bear';
    return <span className={clsx('font-mono tabular font-semibold', tone)}>{v >= 0 ? '+' : ''}{v.toFixed(2)}</span>;
  };
  return (
    <Panel title="Calendar Spread Ladder" subtitle="Brent · WTI · M1→M12" source="curve_blend" dataTimestamp={curve?.timestamp}>
      <table className="w-full text-[11px] font-mono">
        <thead>
          <tr className="text-text-muted text-[9px] uppercase tracking-widest border-b border-border">
            <th className="text-left py-2">Spread</th>
            <th className="text-right">Brent</th>
            <th className="text-right">WTI</th>
            <th className="text-right">Diff</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => {
            const diff = r.brent !== null && r.wti !== null ? r.brent - r.wti : null;
            return (
              <tr key={i} className="border-b border-border/40 hover:bg-bg-hover/30 transition-colors">
                <td className="py-1.5 text-text-secondary">{r.label}</td>
                <td className="text-right">{cell(r.brent)}</td>
                <td className="text-right">{cell(r.wti)}</td>
                <td className="text-right">{cell(diff)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <div className="flex gap-2 mt-3 text-[10px] font-mono">
        <Chip tone="bull">+ Backwardation</Chip>
        <Chip tone="bear">− Contango</Chip>
      </div>
    </Panel>
  );
}

function STEOPanel({ steo }: { steo: any }) {
  const months = steo?.months;
  if (!months || months.length === 0) return <Panel title="EIA · STEO"><SkeletonRows rows={6} /></Panel>;
  const rows = months.slice(-12);
  return (
    <Panel title="Global Oil Balance · EIA STEO" subtitle="12-month outlook · Mb/d" source="eia_steo" dataTimestamp={steo?.as_of ?? steo?.timestamp}>
      <table className="w-full text-[10.5px] font-mono tabular">
        <thead>
          <tr className="text-text-muted text-[9px] uppercase tracking-widest border-b border-border">
            <th className="text-left py-2">Month</th>
            <th className="text-right">Supply</th>
            <th className="text-right">Demand</th>
            <th className="text-right">Balance</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r: any, i: number) => {
            const bal = r.balance ?? ((r.supply ?? 0) - (r.demand ?? 0));
            return (
              <tr key={i} className="border-b border-border/40">
                <td className="py-1 text-text-secondary">
                  {r.period}{r.is_forecast && <span className="ml-1 text-[8px] text-gold/70">F</span>}
                </td>
                <td className="text-right text-bull">{r.supply?.toFixed(2) ?? '—'}</td>
                <td className="text-right text-accent-blue">{r.demand?.toFixed(2) ?? '—'}</td>
                <td className={clsx('text-right font-semibold', bal > 0 ? 'text-bear' : 'text-bull')}>
                  {bal >= 0 ? '+' : ''}{bal.toFixed(2)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </Panel>
  );
}

function TankerWatchPanel({ tw }: { tw: any }) {
  if (!tw) return <Panel title="Tanker Watch"><SkeletonRows rows={4} /></Panel>;
  const chokepoints = tw.chokepoints ?? [];
  const setup = tw.setup_required || tw.available === false;

  const riskTone = (level: string | undefined): 'bull' | 'neut' | 'bear' | 'muted' => {
    switch ((level ?? '').toUpperCase()) {
      case 'CRITICAL':
      case 'HIGH':
      case 'ELEVATED':   return 'bear';
      case 'MODERATE':   return 'neut';
      case 'LOW':        return 'bull';
      default:           return 'muted';
    }
  };

  return (
    <Panel
      title="Tanker Watch · AIS"
      subtitle={tw.note ?? tw.source ?? 'aisstream.io / marinetraffic'}
      accent="blue"
      source="aisstream"
      dataTimestamp={tw.timestamp ?? tw.chokepoints?.[0]?.last_updated}
      sourceNote={setup ? 'AISSTREAM_API_KEY not configured — falling back to news-driven risk only.' : undefined}
      right={<Ship className="w-4 h-4 text-text-tertiary" />}
    >
      {setup ? (
        <div className="text-[11px] font-mono text-text-tertiary leading-relaxed p-3 bg-bg-card/60 rounded space-y-2">
          <div className="text-neut font-semibold">⚠ Live AIS feed requires API key</div>
          <div>Add <code className="text-gold bg-bg px-1.5 py-0.5 rounded">AISSTREAM_API_KEY</code> to <code className="text-gold bg-bg px-1.5 py-0.5 rounded">backend/.env</code></div>
          <div className="text-text-muted">Free key: aisstream.io · falls back to news-driven chokepoint detection</div>
        </div>
      ) : (
        <div className="space-y-3">
          {chokepoints.map((cp: any, i: number) => {
            const tone = riskTone(cp.risk_level);
            const tankers = cp.tankers ?? cp.tanker_count ?? 0;
            const vessels = cp.vessels ?? 0;
            const topVessels = (cp.tanker_list ?? []).slice(0, 2).map((t: any) => t.name).join(' · ');
            const sub = topVessels || cp.context || cp.flow || '';
            return (
              <div key={i} className="flex items-center gap-3 p-2 bg-bg-card/40 rounded transition-colors hover:bg-bg-card/70">
                <Anchor className={clsx(
                  'w-4 h-4',
                  tone === 'bear' && 'text-bear',
                  tone === 'neut' && 'text-neut',
                  tone === 'bull' && 'text-bull',
                  tone === 'muted' && 'text-text-tertiary',
                )} />
                <div className="flex-1 min-w-0">
                  {cp.marine_traffic_url ? (
                    <a
                      href={cp.marine_traffic_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-[11px] font-display font-semibold tracking-wider hover:text-gold transition-colors"
                    >
                      {cp.name}
                    </a>
                  ) : (
                    <span className="text-[11px] font-display font-semibold tracking-wider">{cp.name}</span>
                  )}
                  <div className="text-[9px] font-mono text-text-muted truncate">{sub}</div>
                </div>
                <div className="text-right">
                  <div className="text-lg font-mono font-bold tabular">{tankers}</div>
                  <div className="text-[9px] font-mono text-text-muted">
                    tankers{vessels ? <span className="text-text-tertiary"> · {vessels} ships</span> : null}
                  </div>
                </div>
                <Chip tone={tone as any}>{(cp.risk_level || '').toUpperCase() || 'CALM'}</Chip>
              </div>
            );
          })}
          {tw.note && (
            <div className="mt-2 text-[9px] font-mono text-text-muted leading-snug">{tw.note}</div>
          )}
        </div>
      )}
    </Panel>
  );
}

function VLCCPanel({ cracks }: { cracks: any }) {
  const v = cracks?.vlcc_proxy;
  if (!v) return <Panel title="VLCC Freight"><SkeletonRows rows={3} /></Panel>;
  const ratePct = v.rate_proxy ?? v.estimated_rate ?? 0;
  return (
    <Panel title="VLCC Freight Proxy" subtitle="Brent–Dubai derived" source="vlcc_estimate" right={<Chip tone="muted">ESTIMATED</Chip>}>
      <div className="grid grid-cols-2 gap-3">
        <Stat label="Brent" value={`$${(v.brent ?? cracks?.input_prices?.brent)?.toFixed(2) ?? '—'}`} />
        <Stat label="Dubai (est)" value={`$${(v.dubai_estimate ?? v.dubai_est)?.toFixed(2) ?? '—'}`} tone="gold" />
        <Stat label="Spread" value={`$${(v.brent_dubai_spread ?? v.spread)?.toFixed(2) ?? '—'}`} />
        <Stat label="Rate Proxy" value={ratePct?.toFixed?.(1) ?? '—'} tone={ratePct > 60 ? 'bull' : 'neut'} />
      </div>
    </Panel>
  );
}

function OSPPanel({ cracks }: { cracks: any }) {
  const osp = cracks?.saudi_osp;
  if (!osp) return <Panel title="Saudi OSP"><SkeletonRows rows={5} /></Panel>;
  const grades = osp.grades ?? osp.differentials ?? {};
  const list = Array.isArray(grades)
    ? grades
    : Object.entries(grades).map(([name, vals]: any) => ({ name, ...vals }));

  const valueFor = (row: any, ...keys: string[]): number | null => {
    for (const k of keys) {
      const v = row?.[k];
      if (v === null || v === undefined) continue;
      if (typeof v === 'number') return v;
      if (typeof v === 'object' && typeof v.vs_benchmark === 'number') return v.vs_benchmark;
    }
    return null;
  };

  return (
    <Panel
      title="Saudi OSP · Aramco"
      subtitle={osp.as_of ?? osp.month ?? osp.effective ?? '—'}
      source="saudi_osp_hc"
      sourceNote={`Values reflect ${osp.as_of ?? 'last update'}. Aramco does not publish a machine-readable feed — these are hand-copied from the monthly press release.`}
      right={<Chip tone="muted">{osp.data_source ?? 'HARDCODED'}</Chip>}
    >
      <table className="w-full text-[11px] font-mono tabular">
        <thead>
          <tr className="text-text-muted text-[9px] uppercase tracking-widest border-b border-border">
            <th className="text-left py-2">Grade</th>
            <th className="text-right">Asia</th>
            <th className="text-right">NWE</th>
            <th className="text-right">USGC</th>
          </tr>
        </thead>
        <tbody>
          {list.slice(0, 6).map((g: any, i: number) => {
            const cell = (v: number | null) => {
              if (v === null) return <span className="text-text-muted">—</span>;
              const tone = v >= 0 ? 'text-bull' : 'text-bear';
              return <span className={tone}>{v >= 0 ? '+' : ''}{v.toFixed(2)}</span>;
            };
            return (
              <tr key={i} className="border-b border-border/40">
                <td className="py-1.5 text-text-secondary">{g.name}</td>
                <td className="text-right">{cell(valueFor(g, 'Asia', 'asia'))}</td>
                <td className="text-right">{cell(valueFor(g, 'NWE', 'nwe', 'europe', 'Europe'))}</td>
                <td className="text-right">{cell(valueFor(g, 'USGC', 'usgc', 'us', 'US'))}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {osp.note && (
        <div className="mt-2 text-[9px] font-mono text-text-muted leading-snug">{osp.note}</div>
      )}
    </Panel>
  );
}

function SectionTitle({ kicker, title }: { kicker: string; title: string }) {
  return (
    <div className="flex items-baseline gap-3 pt-2">
      <span className="text-[9px] font-mono uppercase tracking-[0.32em] text-gold/80">{kicker}</span>
      <span className="text-[11px] font-display tracking-[0.18em] uppercase text-text-tertiary">{title}</span>
      <div className="flex-1 h-px bg-gradient-to-r from-border via-border/40 to-transparent" />
    </div>
  );
}

function SpreadsAndCurveSection({ all }: { all: any }) {
  const ts = all?.term_structure;
  return (
    <motion.div className="space-y-5" variants={staggerContainer} initial="hidden" animate="show">
      <motion.div variants={fadeUp}>
        <SectionTitle kicker="01" title="Calendar spreads — front-of-curve carry" />
      </motion.div>
      <motion.div variants={fadeUp} className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <CalendarSpreadMatrix curve={all?.curve} />
        <STEOPanel steo={all?.steo} />
      </motion.div>
      <motion.div variants={fadeUp}>
        <SectionTitle kicker="02" title="Term structure — full curve view" />
      </motion.div>
      <motion.div variants={fadeUp} className="grid grid-cols-1 xl:grid-cols-2 gap-4">
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
      </motion.div>
      <motion.div variants={fadeUp}><StripTable ts={ts} /></motion.div>
      <motion.div variants={fadeUp}><NormalizedCurve ts={ts} /></motion.div>
      <motion.div variants={fadeUp}>
        <SectionTitle kicker="03" title="Physical risk — freight, OSP, chokepoints" />
      </motion.div>
      <motion.div variants={fadeUp} className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <VLCCPanel cracks={all?.cracks} />
        <OSPPanel cracks={all?.cracks} />
        <TankerWatchPanel tw={all?.tanker_watch} />
      </motion.div>
    </motion.div>
  );
}

// ─── Inventories section panels (from FundamentalsView) ────────────────────

function EIAInventory({ f }: { f: any }) {
  const inv = f?.inventory ?? {};
  const crude = inv.crude_stocks;
  if (!crude) return <Panel title="EIA · Inventory"><SkeletonRows rows={5} /></Panel>;
  const dev = crude.deviation_pct ?? 0;
  return (
    <Panel
      title="EIA Inventory"
      subtitle={`Crude · ${crude.date ?? 'weekly'}`}
      accent={dev > 0 ? 'bear' : 'bull'}
      source="eia_inv"
      dataTimestamp={crude.date}
      right={<Chip tone={dev > 0 ? 'bear' : 'bull'}>{crude.label?.replace('_', ' ') ?? (dev > 0 ? 'BUILD' : 'DRAW')}</Chip>}
    >
      <div className="flex items-center gap-3 mb-4">
        <Droplets className={clsx('w-7 h-7', dev > 0 ? 'text-bear' : 'text-bull')} />
        <div>
          <div className="text-2xl font-display font-bold tabular">
            {fmt.int(crude.current / 1000)} <span className="text-sm text-text-tertiary">MMbbl</span>
          </div>
          <div className={clsx('text-[11px] font-mono tabular', dev > 0 ? 'text-bear' : 'text-bull')}>
            {fmt.pct(dev)} vs seasonal
          </div>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <Stat label="Current" value={fmt.int(crude.current) + ' kb'} />
        <Stat label="Seasonal Avg" value={fmt.int(crude.seasonal_avg) + ' kb'} tone="gold" />
      </div>
      {inv.cushing_stocks && (
        <div className="mt-3 pt-3 border-t border-border/40 grid grid-cols-2 gap-3">
          <Stat label="Cushing" value={fmt.int(inv.cushing_stocks.current) + ' kb'} sub={fmt.pct(inv.cushing_stocks.deviation_pct)} />
          {inv.distillate && <Stat label="Distillate" value={fmt.int(inv.distillate.current) + ' kb'} sub={fmt.pct(inv.distillate.deviation_pct)} />}
        </div>
      )}
    </Panel>
  );
}

function ForwardCoverPanel({ f }: { f: any }) {
  const crude = f?.inventory?.crude_stocks;
  if (!crude) return <Panel title="Forward Cover"><Skeleton className="h-24 w-full" /></Panel>;
  const days = crude.days_of_cover ?? (crude.current ? (crude.current / 1000) / 17 : null);
  const v = days ?? 28;
  const tone = v < 25 ? 'bear' : v < 32 ? 'neut' : 'bull';
  return (
    <Panel title="Days of Forward Cover" subtitle="EIA crude / refinery demand" accent={tone as any} source="eia_inv" dataTimestamp={crude.date} sourceNote="Days = EIA crude stocks / 17 Mbbl-day assumed refinery throughput. Throughput is a constant, not live.">
      <div className="flex items-end gap-3 mb-2">
        <span className={clsx('text-4xl font-display font-extrabold tabular', tone === 'bull' && 'text-bull', tone === 'bear' && 'text-bear', tone === 'neut' && 'text-neut')}>
          {v.toFixed(1)}
        </span>
        <span className="text-[11px] font-mono text-text-tertiary uppercase tracking-widest mb-1">days</span>
      </div>
      <div className="relative h-2.5 bg-bg-elev rounded overflow-hidden">
        <div className="absolute inset-y-0 left-0 transition-all" style={{ width: `${Math.min(100, (v / 40) * 100)}%`, background: tone === 'bull' ? '#10d997' : tone === 'neut' ? '#f5a623' : '#ff4d6d' }} />
        <div className="absolute inset-y-0 w-px bg-gold" style={{ left: '67.5%' }} title="54-day critical" />
      </div>
      <div className="flex justify-between text-[9px] font-mono text-text-muted mt-1 tabular">
        <span>20</span><span className="text-gold">crit 27</span><span>40</span>
      </div>
    </Panel>
  );
}

function WeatherPanel({ w }: { w: any }) {
  if (!w?.cities) return <Panel title="Weather"><SkeletonRows rows={3} /></Panel>;
  return (
    <Panel
      title="Weather · HDD/CDD"
      subtitle={`${w.season ?? '7d'} · ${w.summary ?? 'demand outlook'}`}
      accent={(w.net_demand_signal ?? 0) > 0 ? 'bull' : (w.net_demand_signal ?? 0) < 0 ? 'bear' : 'neut'}
      source="open_meteo"
      dataTimestamp={w.timestamp}
      right={<Cloud className="w-4 h-4 text-text-tertiary" />}
    >
      <div className="grid grid-cols-3 gap-3 mb-3">
        <Stat label="HDD 7d" value={`${w.hdd_7day?.toFixed(0) ?? '—'}`} sub={`vs ${w.hdd_normal?.toFixed(0)} normal`} tone={(w.hdd_deviation_pct ?? 0) > 0 ? 'bull' : 'bear'} />
        <Stat label="CDD 7d" value={`${w.cdd_7day?.toFixed(0) ?? '—'}`} sub={`vs ${w.cdd_normal?.toFixed(0)} normal`} tone={(w.cdd_deviation_pct ?? 0) > 0 ? 'bear' : 'neut'} />
        <Stat label="Signal" value={(w.net_demand_signal ?? 0) > 0 ? 'TIGHT' : (w.net_demand_signal ?? 0) < 0 ? 'WEAK' : 'NEUTRAL'} tone={(w.net_demand_signal ?? 0) > 0 ? 'bull' : (w.net_demand_signal ?? 0) < 0 ? 'bear' : 'neut'} />
      </div>
      <div className="space-y-1.5">
        {w.cities.slice(0, 5).map((c: any, i: number) => (
          <div key={i} className="grid grid-cols-[1fr_64px_72px_72px] gap-2 items-baseline text-[10.5px] font-mono tabular border-b border-border/40 pb-1.5 last:border-b-0">
            <span className="text-text-secondary">{c.city}</span>
            <span className="text-right text-text-primary">HDD {c.hdd_7day?.toFixed(0)}</span>
            <span className={clsx('text-right', (c.hdd_deviation_pct ?? 0) > 0 ? 'text-bull' : 'text-bear')}>
              {c.hdd_deviation_pct >= 0 ? '+' : ''}{c.hdd_deviation_pct?.toFixed(0)}%
            </span>
            <span className={clsx('text-right', (c.cdd_deviation_pct ?? 0) > 0 ? 'text-bear' : 'text-text-muted')}>
              CDD {c.cdd_deviation_pct >= 0 ? '+' : ''}{c.cdd_deviation_pct?.toFixed(0)}%
            </span>
          </div>
        ))}
      </div>
    </Panel>
  );
}

function InventoriesSection({ all }: { all: any }) {
  const f = all?.fundamentals ?? {};
  const surprise = all?.eia_surprise;
  const forwardCover = all?.forward_cover;
  const w = all?.weather;
  return (
    <div className="space-y-4">
      <EIASurprisePanel data={surprise} />
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <EIAInventory f={f} />
        <ForwardCoverPanel f={f} />
      </div>
      <ForwardCoverChart data={forwardCover} />
      <WeatherPanel w={w} />
    </div>
  );
}

// ─── COT positioning section ───────────────────────────────────────────────

function COTPanel({ f }: { f: any }) {
  const cot = f?.cot;
  if (!cot) return <Panel title="COT Positioning"><SkeletonRows rows={4} /></Panel>;
  const rows = [
    { l: 'Crude Oil',   v: cot.crude_oil?.percentile,   net: cot.crude_oil?.net,   label: cot.crude_oil?.label },
    { l: 'Natural Gas', v: cot.natural_gas?.percentile, net: cot.natural_gas?.net, label: cot.natural_gas?.label },
    { l: 'Gasoline',    v: cot.gasoline?.percentile,    net: cot.gasoline?.net,    label: cot.gasoline?.label },
    { l: 'Heating Oil', v: cot.heating_oil?.percentile, net: cot.heating_oil?.net, label: cot.heating_oil?.label },
  ];
  return (
    <Panel title="CFTC · COT" subtitle="3-yr percentile" accent="blue" source="cftc_cot" dataTimestamp={cot.crude_oil?.date}>
      <div className="space-y-3">
        {rows.map((r, i) => (
          <div key={i}>
            <div className="flex items-baseline justify-between mb-1">
              <span className="text-[10px] font-mono tracking-widest text-text-tertiary uppercase">{r.l}</span>
              <span className="text-[12px] font-mono tabular text-text-secondary">{r.v !== undefined ? `${r.v.toFixed(0)}%ile` : '—'}</span>
            </div>
            <div className="h-2.5 rounded overflow-hidden bg-bg-elev">
              <div
                className="h-full transition-all duration-1000"
                style={{
                  width: `${Math.max(0, Math.min(100, r.v ?? 0))}%`,
                  background: r.v > 70 ? '#ff4d6d' : r.v < 30 ? '#10d997' : '#f5a623',
                }}
              />
            </div>
            {r.net !== undefined && (
              <div className="text-[10px] font-mono text-text-muted text-right tabular mt-0.5">net {fmt.int(r.net)}</div>
            )}
          </div>
        ))}
      </div>
    </Panel>
  );
}

function OPECPanel({ f }: { f: any }) {
  const opec = f?.opec;
  const jodi = f?.opec_jodi;
  const members: any[] = opec?.members ?? opec?.compliance?.members ?? [];
  if (!members.length) return <Panel title="OPEC+ Compliance" source="opec_static"><SkeletonRows rows={4} /></Panel>;
  const totalQuota  = opec?.total_quota  ?? members.reduce((s: number, m: any) => s + (m.quota ?? 0),  0);
  const totalActual = opec?.total_actual ?? members.reduce((s: number, m: any) => s + (m.actual ?? 0), 0);
  const rate = opec?.overall_compliance_rate ?? (totalQuota > 0 ? totalActual / totalQuota : null);
  const month = opec?.month ?? opec?.as_of ?? opec?.compliance?.month ?? 'monthly';
  const jodiOk = jodi?.available && jodi?.opec_total_kbd;
  return (
    <Panel
      title="OPEC+ Compliance"
      subtitle={`${month}${jodiOk ? ` · JODI ${jodi.as_of}` : ''}`}
      source={jodiOk ? 'jodi_oil' : 'opec_static'}
      sourceNote={jodiOk
        ? `JODI-Oil reports ${jodi.opec_total_kbd.toFixed(0)} kbd OPEC total for ${jodi.as_of}. Compliance ratio still uses calibrated static quotas — JODI gives the realised production cross-check.`
        : 'Production figures are static estimates (IEA / Platts) baked into backend/fetchers/opec.py. JODI not yet loaded.'}
      right={rate != null && <Chip tone={rate > 1.0 ? 'bear' : 'bull'}>{(rate * 100).toFixed(0)}%</Chip>}
    >
      <div className="grid grid-cols-2 gap-3 mb-3">
        <Stat label="Actual" value={`${totalActual.toFixed(2)} Mb/d`} />
        <Stat label="Quota" value={`${totalQuota.toFixed(2)} Mb/d`} tone="gold" />
      </div>
      <div className="space-y-1 mt-3 border-t border-border/60 pt-3">
        {members.slice(0, 6).map((m: any, i: number) => (
          <div key={i} className="grid grid-cols-[1fr_60px_50px] gap-2 text-[10px] font-mono tabular items-baseline">
            <span className="text-text-tertiary truncate">{m.name}</span>
            <span className="text-text-secondary text-right">{m.actual?.toFixed(2)} Mb/d</span>
            <span className={clsx(
              'text-right text-[9px] font-semibold',
              m.status === 'OVER' ? 'text-bear' : m.status === 'UNDER' ? 'text-bull' : 'text-text-secondary',
            )}>{m.status}</span>
          </div>
        ))}
      </div>
    </Panel>
  );
}

function RigCountPanel({ f }: { f: any }) {
  const rig = f?.rig_count;
  const season = f?.seasonality;
  if (!rig) return <Panel title="Rig Count"><SkeletonRows rows={2} /></Panel>;
  if (rig.current == null) {
    if (!season) return <Panel title="Seasonality"><SkeletonRows rows={2} /></Panel>;
    const bias = (season.brent_bias ?? '').toUpperCase();
    const tone = bias.includes('BULL') ? 'bull' : bias.includes('BEAR') ? 'bear' : 'neut';
    return (
      <Panel title="Seasonality · Brent" subtitle={`${season.current_month_name ?? ''} · ${season.data_years ?? 5}y avg`} accent={tone as any} source="yfinance_5y">
        <div className="grid grid-cols-2 gap-3">
          <Stat label="Current Month" value={fmt.pct(season.brent_current_avg)} tone={tone as any} />
          <Stat label="Bias" value={bias || 'NEUTRAL'} tone={tone as any} />
        </div>
        {season.natgas_bias && (
          <div className="mt-3 pt-3 border-t border-border/40 grid grid-cols-2 gap-3">
            <Stat label="NG Current" value={fmt.pct(season.natgas_current_avg)} />
            <Stat label="NG Bias" value={season.natgas_bias.toUpperCase()} />
          </div>
        )}
      </Panel>
    );
  }
  return (
    <Panel title="US Rig Count" subtitle={`Baker Hughes · ${rig.date ?? 'weekly'}`} source="eia_rigs" dataTimestamp={rig.date} right={<Activity className="w-4 h-4 text-text-tertiary" />}>
      <div className="grid grid-cols-2 gap-3">
        <Stat label="Total" value={fmt.int(rig.current)} sub={rig.change != null ? `${rig.change >= 0 ? '+' : ''}${rig.change} w/w` : ''} />
        <Stat label="Previous" value={fmt.int(rig.previous)} tone="gold" />
      </div>
    </Panel>
  );
}

function COTSection({ all }: { all: any }) {
  const f = all?.fundamentals ?? {};
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
      <COTPanel f={f} />
      <OPECPanel f={f} />
      <RigCountPanel f={f} />
    </div>
  );
}

// ─── Cracks section ────────────────────────────────────────────────────────

function CracksPanel({ c }: { c: any }) {
  const cs = c?.crack_spreads;
  if (!cs) return <Panel title="Crack Spreads"><SkeletonRows rows={5} /></Panel>;
  const rows = [
    { l: '3-2-1 (WTI)',     v: cs.crack_321?.value,       avg: cs.crack_321?.avg_1y,       sig: cs.crack_321?.signal },
    { l: '5-3-2',           v: cs.crack_532?.value,       avg: cs.crack_532?.avg_1y,       sig: cs.crack_532?.signal },
    { l: 'Gasoline',        v: cs.gasoline_crack?.value,  avg: cs.gasoline_crack?.avg_1y,  sig: cs.gasoline_crack?.signal },
    { l: 'Heating Oil',     v: cs.heating_oil_crack?.value, avg: cs.heating_oil_crack?.avg_1y, sig: cs.heating_oil_crack?.signal },
    { l: 'Brent Crack',     v: cs.brent_crack?.value,     avg: cs.brent_crack?.avg_1y,     sig: cs.brent_crack?.signal },
  ];
  return (
    <Panel title="Crack Spreads" subtitle="USD/bbl · refinery margins" source="yfinance" dataTimestamp={c.timestamp} right={<BarChart3 className="w-4 h-4 text-text-tertiary" />}>
      <table className="w-full">
        <thead>
          <tr className="text-[9px] font-mono uppercase tracking-widest text-text-muted border-b border-border">
            <th className="text-left py-2">Spread</th>
            <th className="text-right">Value</th>
            <th className="text-right">1Y Avg</th>
            <th className="text-right">Signal</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-b border-border/40">
              <td className="py-2 text-[11px] font-mono text-text-secondary">{r.l}</td>
              <td className="text-right font-mono tabular text-text-primary">{r.v !== undefined ? `$${r.v.toFixed(2)}` : '—'}</td>
              <td className="text-right font-mono tabular text-text-tertiary">{r.avg !== undefined ? `$${r.avg.toFixed(2)}` : '—'}</td>
              <td className="text-right py-1">
                {r.sig && <Chip tone={r.sig === 'WIDE' || r.sig === 'STRONG' ? 'bull' : r.sig === 'NARROW' || r.sig === 'WEAK' ? 'bear' : 'neut'}>{r.sig}</Chip>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Panel>
  );
}

function CracksSection({ all }: { all: any }) {
  return <CracksPanel c={all?.cracks} />;
}

// ─── Macro section ─────────────────────────────────────────────────────────

const MACRO_ASSETS = ['brent', 'wti', 'hh', 'dxy', 'spx'];
const MACRO_LABELS: Record<string, string> = { brent: 'BRT', wti: 'WTI', hh: 'NG', dxy: 'DXY', spx: 'SPX' };

function CorrelationsPanel({ corr }: { corr: any }) {
  const m = corr?.matrix?.matrix ?? corr?.matrix;
  if (!m || typeof m !== 'object') return <Panel title="Correlations"><SkeletonRows rows={5} /></Panel>;
  return (
    <Panel title="Cross-Asset Correlations" subtitle="30d rolling · Pearson · DXY · SPX" source="correlations_calc" dataTimestamp={corr?.timestamp}>
      <div className="grid grid-cols-[60px_repeat(5,1fr)] gap-1.5">
        <div />
        {MACRO_ASSETS.map(a => <div key={a} className="text-[9px] font-mono uppercase tracking-widest text-text-tertiary text-center pb-1">{MACRO_LABELS[a]}</div>)}
        {MACRO_ASSETS.map(rowA => (
          <Fragment key={rowA}>
            <div className="text-[9px] font-mono uppercase tracking-widest text-text-tertiary flex items-center justify-end pr-1">{MACRO_LABELS[rowA]}</div>
            {MACRO_ASSETS.map(colA => {
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

function CurveRegimePanel({ f }: { f: any }) {
  const cr = f?.curve_regime;
  if (!cr || !cr.available) {
    return <Panel title="Curve Regime · 15y" source="curve_regime_15y"><SkeletonRows rows={3} /></Panel>;
  }
  const pct = (cr.percentile ?? 0) * 100;
  const z   = cr.z_score ?? 0;
  const regime = cr.regime ?? 'UNKNOWN';
  const tone: 'bull' | 'bear' | 'neut' =
    regime.includes('BACKWARDATION') ? 'bull'
    : regime.includes('CONTANGO')   ? 'bear'
    : 'neut';
  return (
    <Panel
      title="Curve Regime · 15y context"
      subtitle={`M1-M12 spread · ${cr.history_years}y history · n=${cr.n_obs}`}
      accent={tone as any}
      source="curve_regime_15y"
      dataTimestamp={cr.as_of}
      sourceNote={`Today's M1-M12 sits at the ${pct.toFixed(1)}th percentile of ${cr.history_years} years. ${(cr.regime_pct * 100).toFixed(0)}% of history was in the same regime.`}
      right={<Chip tone={tone as any}>{regime.replace(/_/g, ' ')}</Chip>}
    >
      <div className="flex items-baseline gap-3 mb-3">
        <span className={clsx('text-3xl font-display font-extrabold tabular',
          tone === 'bull' && 'text-bull', tone === 'bear' && 'text-bear', tone === 'neut' && 'text-neut'
        )}>
          {cr.current_m1_m12 >= 0 ? '+' : ''}{cr.current_m1_m12?.toFixed(2)}
        </span>
        <span className="text-[11px] font-mono text-text-tertiary tabular">M1−M12 · $</span>
      </div>
      <div className="grid grid-cols-3 gap-3 text-[10.5px] font-mono tabular">
        <Stat label="15y Pctile" value={`${pct.toFixed(0)}%`} tone={tone as any} />
        <Stat label="Z-score"    value={`${z >= 0 ? '+' : ''}${z.toFixed(2)}σ`} />
        <Stat label="15y Mean"   value={`${(cr.mean ?? 0).toFixed(2)}`} tone="gold" />
      </div>
      <div className="mt-3 text-[10px] font-mono text-text-muted">
        15y range: <span className="text-text-secondary tabular">{(cr.p10 ?? 0).toFixed(2)}</span>
        {' '}…{' '}
        <span className="text-text-secondary tabular">{(cr.p90 ?? 0).toFixed(2)}</span>
        {' '}(P10–P90)
      </div>
    </Panel>
  );
}

function OrderFlowPanel({ f }: { f: any }) {
  const of_ = f?.order_flow;
  if (!of_ || !of_.available) {
    return <Panel title="Order Flow · Brent" source="order_flow_model"><SkeletonRows rows={3} /></Panel>;
  }
  const sm = of_.summary ?? {};
  const tone: 'bull' | 'bear' | 'neut' =
    (sm.net_imbalance ?? 0) >  0.05 ? 'bull'
    : (sm.net_imbalance ?? 0) < -0.05 ? 'bear'
    : 'neut';
  const contracts = of_.contracts ?? [];
  return (
    <Panel
      title="Order Flow · buy/sell imbalance"
      subtitle={`${of_.lookback_days}d rolling · ${of_.as_of}`}
      accent={tone as any}
      source="order_flow_model"
      dataTimestamp={of_.as_of}
      sourceNote="Imbalance = (buy − sell) / (buy + sell). Above-zero = bid-side aggression. From institutional desk feed."
      right={<Chip tone={tone as any}>{sm.label ?? 'flow'}</Chip>}
    >
      <div className="space-y-2">
        {contracts.slice(0, 6).map((c: any) => {
          const t: 'bull' | 'bear' | 'neut' =
            c.rolling_imbalance_pct >  0.05 ? 'bull'
            : c.rolling_imbalance_pct < -0.05 ? 'bear'
            : 'neut';
          return (
            <div key={c.instrument} className="grid grid-cols-[60px_1fr_64px] gap-2 items-center text-[10.5px] font-mono tabular">
              <span className="text-text-secondary">{c.instrument}</span>
              <div className="h-1.5 bg-bg-elev rounded overflow-hidden relative">
                <div className="absolute inset-y-0 left-1/2 w-px bg-border-strong" />
                <div
                  className="absolute inset-y-0 rounded"
                  style={{
                    left:  c.rolling_imbalance_pct >= 0 ? '50%' : `${50 - Math.min(50, Math.abs(c.rolling_imbalance_pct) * 100 * 5)}%`,
                    width: `${Math.min(50, Math.abs(c.rolling_imbalance_pct) * 100 * 5)}%`,
                    background: t === 'bull' ? '#10d997' : t === 'bear' ? '#ff4d6d' : '#f5a623',
                  }}
                />
              </div>
              <span className={clsx('text-right',
                t === 'bull' && 'text-bull', t === 'bear' && 'text-bear', t === 'neut' && 'text-neut'
              )}>
                {c.rolling_imbalance_pct >= 0 ? '+' : ''}{(c.rolling_imbalance_pct * 100).toFixed(1)}%
              </span>
            </div>
          );
        })}
      </div>
      <div className="mt-3 pt-2 border-t border-border/40 text-[9.5px] font-mono text-text-muted">
        Net (front-weighted): <span className={clsx('tabular',
          tone === 'bull' && 'text-bull', tone === 'bear' && 'text-bear', tone === 'neut' && 'text-neut'
        )}>{(sm.net_imbalance * 100).toFixed(2)}%</span>
      </div>
    </Panel>
  );
}

function GeoRiskPanel({ f }: { f: any }) {
  const g = f?.geo_risk;
  if (!g) return <Panel title="Geo Risk"><SkeletonRows rows={3} /></Panel>;
  const score = g.index ?? 0;
  const tone = score > 60 ? 'bear' : score > 30 ? 'neut' : 'bull';
  const components = g.components ?? {};
  return (
    <Panel title="Geopolitical Risk" subtitle={g.primary_driver ?? 'composite'} accent={tone as any} source="geo_risk_calc" dataTimestamp={g.timestamp}>
      <div className="flex items-center gap-4 mb-3">
        <AlertOctagon className={clsx('w-8 h-8', tone === 'bear' && 'text-bear', tone === 'neut' && 'text-neut', tone === 'bull' && 'text-bull')} />
        <div>
          <div className={clsx('text-3xl font-display font-extrabold tabular', tone === 'bear' && 'text-bear', tone === 'neut' && 'text-neut', tone === 'bull' && 'text-bull')}>{score.toFixed(0)}</div>
          <div className="text-[10px] font-mono text-text-tertiary uppercase tracking-widest">{g.label ?? 'NORMAL'}</div>
        </div>
      </div>
      <div className="h-2 bg-bg-elev rounded overflow-hidden">
        <div
          className="h-full transition-all duration-1000"
          style={{
            width: `${Math.min(100, score)}%`,
            background: score > 60 ? '#ff4d6d' : score > 30 ? '#f5a623' : '#10d997',
          }}
        />
      </div>
      <div className="mt-3 text-[10px] font-mono text-text-tertiary space-y-1">
        {Object.entries(components).slice(0, 4).map(([name, c]: any) => (
          <div key={name} className="flex justify-between gap-2">
            <span className="capitalize">{name.replace(/_/g, ' ')}</span>
            <span className="text-text-secondary tabular">{c.score?.toFixed?.(1) ?? '—'}</span>
          </div>
        ))}
      </div>
    </Panel>
  );
}

function ChokepointsPanel({ news }: { news: any }) {
  const chokepoints = [
    { name: 'Hormuz', flow: '21% global oil', weight: 100 },
    { name: 'Bab-el-Mandeb', flow: 'Suez gateway', weight: 70 },
    { name: 'Suez', flow: '10% global trade', weight: 65 },
    { name: 'Malacca', flow: 'Asia transit', weight: 60 },
  ];
  const articles = news?.articles ?? [];
  const scan = (kw: string[]) => articles.filter((a: any) => kw.some(k => (a.title ?? '').toLowerCase().includes(k))).length;
  const risks: Record<string, number> = {
    'Hormuz':       Math.min(100, scan(['hormuz','iran','strait']) * 25),
    'Bab-el-Mandeb':Math.min(100, scan(['bab','houthi','red sea','yemen']) * 25),
    'Suez':         Math.min(100, scan(['suez','egypt']) * 25),
    'Malacca':      Math.min(100, scan(['malacca','singapore','indonesia']) * 25),
  };
  return (
    <Panel title="Chokepoint Risk" subtitle="News-driven monitor" accent="neut" source="news_apify" sourceNote="Risk levels are derived by keyword-scanning recent news headlines. Not a live AIS/intel feed." right={<Anchor className="w-4 h-4 text-text-tertiary" />}>
      <div className="space-y-3">
        {chokepoints.map(cp => {
          const risk = risks[cp.name] ?? 0;
          const tone = risk > 60 ? 'bear' : risk > 30 ? 'neut' : 'bull';
          return (
            <div key={cp.name}>
              <div className="flex items-center justify-between mb-1">
                <div className="flex items-center gap-2">
                  <span className="text-[11px] font-display font-semibold tracking-wider">{cp.name}</span>
                  <span className="text-[9px] font-mono text-text-muted">{cp.flow}</span>
                </div>
                <Chip tone={tone as any}>{risk > 60 ? 'ELEVATED' : risk > 30 ? 'WATCH' : 'CALM'}</Chip>
              </div>
              <div className="h-1.5 bg-bg-elev rounded overflow-hidden">
                <div
                  className="h-full transition-all"
                  style={{ width: `${Math.max(5, risk)}%`, background: tone === 'bear' ? '#ff4d6d' : tone === 'neut' ? '#f5a623' : '#10d997' }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </Panel>
  );
}

function MacroSection({ all }: { all: any }) {
  const f = all?.fundamentals ?? {};
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <CorrelationsPanel corr={all?.correlations} />
        <CurveRegimePanel f={f} />
      </div>
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <OrderFlowPanel f={f} />
        <GeoRiskPanel f={f} />
      </div>
      <ChokepointsPanel news={all?.news} />
    </div>
  );
}

// ─── Top-level MARKETS view ────────────────────────────────────────────────

export function MarketsView({ all }: { all: any }) {
  return (
    <div className="space-y-3">
      <LazySection id="spreads" title="Spreads & Curve" subtitle="calendar · term · physical" defaultOpen>
        <SpreadsAndCurveSection all={all} />
      </LazySection>
      <LazySection id="inventories" title="Inventories" subtitle="EIA crude · distillates · gasoline · surprise">
        <InventoriesSection all={all} />
      </LazySection>
      <LazySection id="cot" title="COT positioning" subtitle="CFTC managed money · OPEC+ · rigs">
        <COTSection all={all} />
      </LazySection>
      <LazySection id="cracks" title="Cracks" subtitle="3-2-1 · gasoline · distillate">
        <CracksSection all={all} />
      </LazySection>
      <LazySection id="macro" title="Macro" subtitle="DXY · SPX · curve regime · geo · order flow">
        <MacroSection all={all} />
      </LazySection>
    </div>
  );
}
