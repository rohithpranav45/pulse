import { useMemo, useState } from 'react';
import { Panel } from '@/components/ui/Panel';
import { Chip } from '@/components/ui/Chip';
import { Stat } from '@/components/ui/Stat';
import { fmt } from '@/lib/fmt';
import { useClock } from '@/lib/hooks';
import {
  CONTRACTS,
  frontMonthFor,
  isPrimarySessionOpen,
  daysUntil,
  contractCode,
} from '@/lib/contracts';
import { AlertTriangle, Clock, ArrowRightLeft, FileText, Layers, ExternalLink } from 'lucide-react';
import clsx from 'clsx';

const MONTH_FULL = ['January','February','March','April','May','June','July','August','September','October','November','December'];

function ContractCard({
  spec,
  livePrice,
  liveChange,
}: {
  spec: typeof CONTRACTS[number];
  livePrice?: number | null;
  liveChange?: number | null;
}) {
  const now = useClock();
  const { deliveryMonth, expiry } = useMemo(() => frontMonthFor(spec, now), [spec, now]);
  const dte = daysUntil(expiry, now);
  const sessionOpen = isPrimarySessionOpen(spec, now);
  const code = contractCode(spec, deliveryMonth);

  const rollSoon = dte <= 5;

  return (
    <Panel
      title={`${spec.name}`}
      subtitle={`${spec.bloomberg} · ${spec.exchangeShort}`}
      accent={rollSoon ? 'bear' : 'gold'}
      right={
        <div className="flex items-center gap-1.5">
          {sessionOpen ? (
            <Chip tone="bull" icon={<span className="live-dot" />}>SESSION OPEN</Chip>
          ) : (
            <Chip tone="muted">SESSION CLOSED</Chip>
          )}
        </div>
      }
    >
      {/* Live price strip */}
      {(livePrice !== undefined && livePrice !== null) && (
        <div className="flex items-baseline justify-between mb-3 pb-3 border-b border-border/40">
          <div>
            <div className="text-[9px] font-mono uppercase tracking-widest text-text-muted">Live front</div>
            <div className="text-2xl font-display font-bold tabular text-text-primary">
              ${fmt.price(livePrice)} <span className="text-[10px] text-text-muted">{spec.quoteUnit}</span>
            </div>
          </div>
          {liveChange !== undefined && liveChange !== null && (
            <Chip tone={liveChange >= 0 ? 'bull' : 'bear'}>{fmt.pct(liveChange)}</Chip>
          )}
        </div>
      )}

      {/* Front contract + roll alert */}
      <div className={clsx(
        'p-3 rounded mb-3',
        rollSoon ? 'bg-bear-soft border border-bear/40' : 'bg-bg-card/50',
      )}>
        <div className="flex items-baseline justify-between mb-2">
          <div className="flex items-baseline gap-2">
            <span className="text-[10px] font-mono uppercase tracking-widest text-text-tertiary">Front</span>
            <span className="text-[14px] font-display font-bold tabular text-gold tracking-wider">{code}</span>
          </div>
          <span className={clsx(
            'text-[11px] font-mono tabular',
            rollSoon ? 'text-bear font-semibold' : 'text-text-secondary',
          )}>
            {dte > 0 ? `${dte}d to expiry` : 'expired'}
          </span>
        </div>
        <div className="text-[10px] font-mono text-text-muted">
          {MONTH_FULL[deliveryMonth.getUTCMonth()]} {deliveryMonth.getUTCFullYear()} delivery · expires{' '}
          {expiry.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
        </div>
        {rollSoon && (
          <div className="mt-2 flex items-start gap-1.5 text-[10px] font-mono text-bear/95 leading-snug">
            <AlertTriangle className="w-3 h-3 flex-shrink-0 mt-0.5" />
            <span><strong>Roll alert</strong> — front-month expires in {dte}d. Roll to M2 if you do not intend delivery.</span>
          </div>
        )}
      </div>

      {/* Spec grid */}
      <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-[10.5px] font-mono tabular">
        <div className="flex justify-between border-b border-border/30 pb-1">
          <span className="text-text-muted">Exchange</span>
          <span className="text-text-secondary">{spec.exchange}</span>
        </div>
        <div className="flex justify-between border-b border-border/30 pb-1">
          <span className="text-text-muted">Size</span>
          <span className="text-text-secondary">{spec.contractSize.value.toLocaleString()} {spec.contractSize.unit}</span>
        </div>
        <div className="flex justify-between border-b border-border/30 pb-1">
          <span className="text-text-muted">Quote</span>
          <span className="text-text-secondary">{spec.quoteUnit}</span>
        </div>
        <div className="flex justify-between border-b border-border/30 pb-1">
          <span className="text-text-muted">Tick</span>
          <span className="text-text-secondary">{spec.minTick.value} = ${spec.minTick.dollars}/lot</span>
        </div>
        <div className="flex justify-between border-b border-border/30 pb-1">
          <span className="text-text-muted">Settlement</span>
          <span className={spec.settlement.startsWith('Physical') ? 'text-bear' : 'text-bull'}>
            {spec.settlement}
          </span>
        </div>
        <div className="flex justify-between border-b border-border/30 pb-1">
          <span className="text-text-muted">Daily fix</span>
          <span className="text-text-secondary text-[9.5px]">{spec.dailySettlement}</span>
        </div>
      </div>

      {/* Quality + hours */}
      <div className="mt-3 space-y-2 text-[10.5px]">
        <div>
          <div className="text-[9px] font-mono uppercase tracking-widest text-text-muted mb-0.5">Quality</div>
          <div className="text-text-secondary leading-snug">{spec.underlyingQuality}</div>
        </div>
        <div>
          <div className="text-[9px] font-mono uppercase tracking-widest text-text-muted mb-0.5 flex items-center gap-1">
            <Clock className="w-3 h-3" /> Hours
          </div>
          <div className="text-text-secondary leading-snug">{spec.hoursLabel}</div>
        </div>
      </div>

      {/* Key spreads */}
      <div className="mt-3 pt-3 border-t border-border/40">
        <div className="text-[9px] font-mono uppercase tracking-widest text-text-muted mb-1.5">Key spreads</div>
        <div className="flex flex-wrap gap-1">
          {spec.keySpreads.map((s, i) => (
            <span key={i} className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-bg-card/60 text-text-tertiary border border-border/40">
              {s}
            </span>
          ))}
        </div>
      </div>

      {/* Trader's note */}
      {spec.notes && (
        <div className="mt-3 pt-3 border-t border-border/40 flex items-start gap-2 text-[10px] font-mono text-text-tertiary leading-relaxed">
          <FileText className="w-3 h-3 flex-shrink-0 mt-0.5 text-gold" />
          <span>{spec.notes}</span>
        </div>
      )}
    </Panel>
  );
}

function UnitConverter() {
  const [bbl, setBbl] = useState<string>('100');
  const [mt, setMt] = useState<string>('');
  const [gal, setGal] = useState<string>('');
  // Distillate density default (0.845 kg/L → 1 MT ≈ 7.45 bbl for gasoil/diesel)
  const [densityBblPerMt, setDensityBblPerMt] = useState<number>(7.45);

  // Conversions
  const fromBbl = (val: number) => {
    setMt((val / densityBblPerMt).toFixed(4));
    setGal((val * 42).toFixed(2));
  };
  const fromMt = (val: number) => {
    const b = val * densityBblPerMt;
    setBbl(b.toFixed(4));
    setGal((b * 42).toFixed(2));
  };
  const fromGal = (val: number) => {
    const b = val / 42;
    setBbl(b.toFixed(4));
    setMt((b / densityBblPerMt).toFixed(4));
  };

  // Init derived fields
  useMemo(() => fromBbl(parseFloat(bbl || '0')), []);  // eslint-disable-line

  return (
    <Panel title="Unit Converter" subtitle="$/bbl ↔ $/gallon ↔ $/MT" accent="blue" right={<ArrowRightLeft className="w-4 h-4 text-text-tertiary" />}>
      <div className="space-y-3">
        <div>
          <label className="text-[10px] font-mono uppercase tracking-widest text-text-tertiary">Dollars per barrel</label>
          <input
            type="number" step="0.01" value={bbl}
            onChange={(e) => { setBbl(e.target.value); fromBbl(parseFloat(e.target.value || '0')); }}
            className="mt-1 w-full px-2 py-1.5 bg-bg-elev border border-border rounded text-[14px] font-mono tabular text-text-primary focus:border-gold/50 focus:outline-none"
          />
        </div>
        <div>
          <label className="text-[10px] font-mono uppercase tracking-widest text-text-tertiary">Dollars per gallon</label>
          <input
            type="number" step="0.0001" value={gal}
            onChange={(e) => { setGal(e.target.value); fromGal(parseFloat(e.target.value || '0')); }}
            className="mt-1 w-full px-2 py-1.5 bg-bg-elev border border-border rounded text-[14px] font-mono tabular text-text-primary focus:border-gold/50 focus:outline-none"
          />
          <div className="text-[9px] font-mono text-text-muted mt-0.5">× 42 to get $/bbl (RBOB, HO)</div>
        </div>
        <div>
          <label className="text-[10px] font-mono uppercase tracking-widest text-text-tertiary">Dollars per metric tonne</label>
          <input
            type="number" step="0.01" value={mt}
            onChange={(e) => { setMt(e.target.value); fromMt(parseFloat(e.target.value || '0')); }}
            className="mt-1 w-full px-2 py-1.5 bg-bg-elev border border-border rounded text-[14px] font-mono tabular text-text-primary focus:border-gold/50 focus:outline-none"
          />
          <div className="text-[9px] font-mono text-text-muted mt-0.5">÷ {densityBblPerMt} bbl/MT to get $/bbl (Gasoil)</div>
        </div>
        <div className="pt-2 border-t border-border/40">
          <label className="text-[10px] font-mono uppercase tracking-widest text-text-tertiary">Density · bbl per MT</label>
          <div className="flex items-center gap-2 mt-1">
            <input
              type="range" min="6.5" max="8.5" step="0.05" value={densityBblPerMt}
              onChange={(e) => { setDensityBblPerMt(parseFloat(e.target.value)); fromBbl(parseFloat(bbl || '0')); }}
              className="flex-1 accent-gold h-1"
            />
            <span className="text-[11px] font-mono tabular text-text-secondary w-12 text-right">{densityBblPerMt.toFixed(2)}</span>
          </div>
          <div className="text-[9px] font-mono text-text-muted mt-1">
            Gasoil ≈ 7.45 · Light crude ≈ 7.50 · Heavy crude ≈ 6.80
          </div>
        </div>
      </div>
    </Panel>
  );
}

function CrackRatioCalculator() {
  // 3-2-1 crack ratio sizing — given a target gross exposure in barrels,
  // compute the matching lot sizes for CL / RB / HO.
  const [bblExposure, setBblExposure] = useState<number>(3000);
  // CL = 1000 bbl; RB = 1000 bbl (42000 gal); HO = 1000 bbl (42000 gal)
  const clLots = Math.round(bblExposure / 1000);
  const rbLots = Math.round((bblExposure * 2 / 3) / 1000);
  const hoLots = Math.round((bblExposure * 1 / 3) / 1000);

  return (
    <Panel
      title="3-2-1 Crack Sizing"
      subtitle="balanced lot ratio for refinery margin trade"
      accent="gold"
      right={<Layers className="w-4 h-4 text-text-tertiary" />}
    >
      <label className="text-[10px] font-mono uppercase tracking-widest text-text-tertiary">Gross crude exposure (bbl)</label>
      <input
        type="number" step="1000" value={bblExposure}
        onChange={(e) => setBblExposure(parseInt(e.target.value || '0', 10))}
        className="mt-1 w-full px-2 py-1.5 bg-bg-elev border border-border rounded text-[14px] font-mono tabular text-text-primary focus:border-gold/50 focus:outline-none"
      />
      <div className="grid grid-cols-3 gap-2 mt-3">
        <Stat label="WTI (CL)" value={`${clLots} lots`} sub="short" tone="bear" />
        <Stat label="RBOB (RB)" value={`${rbLots} lots`} sub="long" tone="bull" />
        <Stat label="HO" value={`${hoLots} lots`} sub="long" tone="bull" />
      </div>
      <div className="mt-3 text-[10px] font-mono text-text-tertiary leading-relaxed">
        Formula: <span className="text-text-secondary">3 CL : 2 RB : 1 HO</span> — the standard US refinery yield ratio.
        Short crude, long the two product cracks; profits widen when refining margins expand.
      </div>
    </Panel>
  );
}

export function ContractsView({ all }: { all: any }) {
  const prices = all?.prices ?? {};
  // Map our contract keys to the price keys served by the backend
  const priceMap: Record<string, string | null> = {
    brent: 'brent',
    wti: 'wti',
    rbob: 'gasoline',     // backend serves 'gasoline' for RB=F
    ho: 'heating_oil',    // backend serves 'heating_oil' for HO=F
    gasoil: null,         // not served by free yfinance feed
  };

  return (
    <div className="space-y-4">
      {/* Summary strip */}
      <Panel title="Contract Reference · 5 Core Energy Futures" subtitle="curriculum chapter 11 — desk reference" accent="gold">
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3 text-[10.5px] font-mono">
          {CONTRACTS.map(c => {
            const pkey = priceMap[c.key];
            const p = pkey ? prices[pkey] : null;
            return (
              <div key={c.key} className="p-2 bg-bg-card/50 rounded text-center">
                <div className="font-display font-bold tracking-widest text-gold">{c.bloomberg}</div>
                <div className="text-[9px] text-text-muted">{c.exchangeShort}</div>
                {p && (
                  <div className="mt-1">
                    <div className="text-text-primary tabular">${fmt.price(p.price)}</div>
                    <div className={clsx('text-[9px] tabular', (p.change_pct ?? 0) >= 0 ? 'text-bull' : 'text-bear')}>
                      {fmt.pct(p.change_pct)}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </Panel>

      {/* One card per contract */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        {CONTRACTS.map(c => {
          const pkey = priceMap[c.key];
          const p = pkey ? prices[pkey] : null;
          return (
            <ContractCard
              key={c.key}
              spec={c}
              livePrice={p?.price}
              liveChange={p?.change_pct}
            />
          );
        })}
      </div>

      {/* Tools */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <UnitConverter />
        <CrackRatioCalculator />
      </div>

      {/* Cheat-sheet link */}
      <Panel title="Cross-Contract Spread Quick Reference" subtitle="the 3 spreads every desk watches" accent="blue">
        <div className="space-y-2 text-[11px] font-mono">
          <div className="p-2 bg-bg-card/50 rounded flex items-start gap-3">
            <ExternalLink className="w-3 h-3 mt-1 text-gold flex-shrink-0" />
            <div>
              <div className="text-text-primary font-semibold">Brent-WTI (B − CL)</div>
              <div className="text-text-tertiary leading-relaxed">
                Cross-Atlantic crude premium. Widens when US can't export or North Sea is disrupted. Normal $2-6/bbl;
                blew out to $28 during 2011-13 Cushing crisis. Both lots = 1,000 bbl, same unit ($/bbl) — clean 1:1 spread.
              </div>
            </div>
          </div>
          <div className="p-2 bg-bg-card/50 rounded flex items-start gap-3">
            <ExternalLink className="w-3 h-3 mt-1 text-gold flex-shrink-0" />
            <div>
              <div className="text-text-primary font-semibold">3-2-1 Crack (2RB + 1HO − 3CL)/3</div>
              <div className="text-text-tertiary leading-relaxed">
                US refinery margin proxy. RB and HO quoted in $/gal — multiply by 42 to align with WTI's $/bbl.
                Wide cracks ($25+/bbl) = product market tight, supports crude demand.
              </div>
            </div>
          </div>
          <div className="p-2 bg-bg-card/50 rounded flex items-start gap-3">
            <ExternalLink className="w-3 h-3 mt-1 text-gold flex-shrink-0" />
            <div>
              <div className="text-text-primary font-semibold">ICE Gasoil Crack (GO − BRN, unit-adjusted)</div>
              <div className="text-text-tertiary leading-relaxed">
                European diesel margin. GO in $/MT — divide by ~7.45 to get $/bbl before computing. Lot ratio 3 GO : 4 BRN
                balances DV01 because GO lot ≈ 745 bbl vs BRN lot = 1,000 bbl.
              </div>
            </div>
          </div>
        </div>
      </Panel>
    </div>
  );
}
