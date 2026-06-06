import { Panel } from '@/components/ui/Panel';
import { Chip } from '@/components/ui/Chip';
import { Stat } from '@/components/ui/Stat';
import { SkeletonRows, Skeleton } from '@/components/ui/Skeleton';
import { fmt } from '@/lib/fmt';
import clsx from 'clsx';
import { Droplets, Activity, Anchor, AlertOctagon, BarChart3, Cloud } from 'lucide-react';
import { EIASurprisePanel } from '@/components/panels/EIASurprisePanel';
import { ForwardCoverChart } from '@/components/panels/ForwardCoverChart';

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
  // Backend returns `opec.members` directly at the top level (no `compliance` wrapper).
  // Support both shapes for resilience.
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

function ForwardCoverPanel({ f }: { f: any }) {
  const crude = f?.inventory?.crude_stocks;
  if (!crude) return <Panel title="Forward Cover"><Skeleton className="h-24 w-full" /></Panel>;
  // Days of cover = stocks (Mbbl) / refinery demand (~17 Mbbl/day for US)
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

function CurveRegimePanel({ f }: { f: any }) {
  const cr = f?.curve_regime;
  if (!cr || !cr.available) {
    return (
      <Panel title="Curve Regime · 15y" source="curve_regime_15y">
        <SkeletonRows rows={3} />
      </Panel>
    );
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
    return (
      <Panel title="Order Flow · Brent" source="order_flow_model">
        <SkeletonRows rows={3} />
      </Panel>
    );
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

function RigCountPanel({ f }: { f: any }) {
  const rig = f?.rig_count;
  const season = f?.seasonality;
  if (!rig) return <Panel title="Rig Count"><SkeletonRows rows={2} /></Panel>;
  // Rig count is often unavailable — show seasonality summary instead
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

export function FundamentalsView({ all }: { all: any }) {
  const f = all?.fundamentals ?? {};
  const w = all?.weather;
  const c = all?.cracks;
  const news = all?.news;
  const surprise = all?.eia_surprise;
  const forwardCover = all?.forward_cover;

  return (
    <div className="space-y-4">
      {/* HERO — EIA Surprise Tracker */}
      <EIASurprisePanel data={surprise} />

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        <EIAInventory f={f} />
        <COTPanel f={f} />
        <OPECPanel f={f} />
      </div>

      {/* Forward Cover historical chart — full width */}
      <ForwardCoverChart data={forwardCover} />

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        <GeoRiskPanel f={f} />
        <ForwardCoverPanel f={f} />
        <RigCountPanel f={f} />
      </div>

      {/* Phase A: institutional context — 15y curve regime + per-contract order flow */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <CurveRegimePanel f={f} />
        <OrderFlowPanel f={f} />
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <CracksPanel c={c} />
        <ChokepointsPanel news={news} />
      </div>

      <WeatherPanel w={w} />
    </div>
  );
}
