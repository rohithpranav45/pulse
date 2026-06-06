import { Panel } from '@/components/ui/Panel';
import { Chip } from '@/components/ui/Chip';
import { Stat } from '@/components/ui/Stat';
import { SkeletonRows } from '@/components/ui/Skeleton';
import { Anchor, Ship } from 'lucide-react';
import clsx from 'clsx';

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
              <tr key={i} className="border-b border-border/40 hover:bg-bg-hover/30">
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
  // Setup required when backend explicitly opted out (no key) or set the flag.
  const setup = tw.setup_required || tw.available === false;

  const riskTone = (level: string | undefined): 'bull' | 'neut' | 'bear' | 'muted' => {
    switch ((level ?? '').toUpperCase()) {
      case 'CRITICAL':
      case 'HIGH':
      case 'ELEVATED':   return 'bear';
      case 'MODERATE':   return 'neut';
      case 'LOW':        return 'bull';
      default:           return 'muted'; // MONITORING / unknown
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
            // If we have specific vessel names, show those; otherwise fall back to the context blurb.
            const topVessels = (cp.tanker_list ?? []).slice(0, 2).map((t: any) => t.name).join(' · ');
            const sub = topVessels || cp.context || cp.flow || '';
            return (
              <div key={i} className="flex items-center gap-3 p-2 bg-bg-card/40 rounded">
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

  /**
   * Backend shape:  grades.Arab Light = { Asia: {vs_benchmark, benchmark}, NWE: {...}, USGC: {...} }
   * Older shapes:   { asia: number, nwe: number, usgc: number }
   * Read both: deep object → vs_benchmark; flat number → direct.
   */
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

export function SpreadsView({ all }: { all: any }) {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <CalendarSpreadMatrix curve={all?.curve} />
        <STEOPanel steo={all?.steo} />
      </div>
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <VLCCPanel cracks={all?.cracks} />
        <OSPPanel cracks={all?.cracks} />
        <TankerWatchPanel tw={all?.tanker_watch} />
      </div>
    </div>
  );
}
