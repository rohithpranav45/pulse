import { useState } from 'react';
import { Panel } from '@/components/ui/Panel';
import { Chip } from '@/components/ui/Chip';
import { ScoreBar } from '@/components/ui/ScoreBar';
import { Sparkline } from '@/components/ui/Sparkline';
import { Stat } from '@/components/ui/Stat';
import { SkeletonRows } from '@/components/ui/Skeleton';
import { fmt, signalLabel } from '@/lib/fmt';
import { ArrowUpRight, ArrowDownRight, Minus, Shield, AlertTriangle, BookOpen, ChevronRight } from 'lucide-react';
import clsx from 'clsx';
import { PriceDecomposition } from '@/components/panels/PriceDecomposition';
import { GeoRiskCalculator } from '@/components/panels/GeoRiskCalculator';
import { IndicatorDrillDown } from '@/components/panels/IndicatorDrillDown';

const ASSETS = [
  { key: 'brent',     label: 'BRENT',   sub: 'ICE · BZ=F' },
  { key: 'wti',       label: 'WTI',     sub: 'NYMEX · CL=F' },
  { key: 'henry_hub', label: 'NAT GAS', sub: 'NYMEX · NG=F' },
];

function ScoreToVerdict({ score }: { score: number | null }) {
  if (score === null || score === undefined) return null;
  const label = signalLabel(score);
  const tone = score >= 0.4 ? 'bull' : score <= -0.4 ? 'bear' : 'neut';
  const Icon = tone === 'bull' ? ArrowUpRight : tone === 'bear' ? ArrowDownRight : Minus;
  return (
    <div className="flex items-center gap-3">
      <Icon className={clsx('w-7 h-7', tone === 'bull' && 'text-bull', tone === 'bear' && 'text-bear', tone === 'neut' && 'text-neut')} strokeWidth={2.5} />
      <div>
        <div className={clsx(
          'font-display font-extrabold text-[34px] leading-none tracking-wide',
          tone === 'bull' && 'text-bull',
          tone === 'bear' && 'text-bear',
          tone === 'neut' && 'text-neut',
        )}
          style={{ textShadow: `0 0 24px ${tone === 'bull' ? 'rgba(16,217,151,0.45)' : tone === 'bear' ? 'rgba(255,77,109,0.45)' : 'rgba(245,166,35,0.4)'}` }}
        >
          {label}
        </div>
        <div className="text-[11px] font-mono text-text-tertiary mt-1 tabular">SCORE {score.toFixed(2)} / 2.00</div>
      </div>
    </div>
  );
}

function SignalCard({ asset, signal, price, onIndicatorClick }: {
  asset: { key: string; label: string; sub: string };
  signal: any;
  price: any;
  onIndicatorClick?: (assetKey: string, indicator: any) => void;
}) {
  const score = signal?.score ?? null;
  const tone = score === null ? 'neut' : score >= 0.4 ? 'bull' : score <= -0.4 ? 'bear' : 'neut';
  const conv = signal?.conviction ?? '—';
  const history: number[] = signal?.history ?? [];
  const indicators: any[] = signal?.indicators ?? [];

  return (
    <Panel
      accent={tone as any}
      title={asset.label}
      subtitle={asset.sub}
      right={
        score !== null && (
          <Chip tone={conv === 'HIGH' ? 'bull' : conv === 'MODERATE' ? 'neut' : 'muted'}>
            {conv}
          </Chip>
        )
      }
      className={clsx(
        'relative overflow-hidden transition-all hover:scale-[1.005]',
      )}
    >
      <div className="flex items-start justify-between gap-4 mb-4">
        <ScoreToVerdict score={score} />
        <div className="text-right">
          <div className="text-[10px] font-mono text-text-tertiary uppercase tracking-widest">Last</div>
          <div className="text-2xl font-mono font-bold tabular text-text-primary">${fmt.price(price?.price)}</div>
          <div className={clsx(
            'text-[11px] font-mono tabular',
            (price?.change_pct ?? 0) >= 0 ? 'text-bull' : 'text-bear',
          )}>
            {price?.change_pct !== undefined ? `${fmt.signed(price.change_abs ?? 0)} (${fmt.pct(price.change_pct)})` : '—'}
          </div>
        </div>
      </div>

      <div className="mb-3">
        <ScoreBar score={score ?? 0} height={8} showLabels />
      </div>

      {history.length > 1 && (
        <div className="flex items-center justify-between gap-3 mb-4 py-2 px-3 bg-bg-card/60 rounded">
          <div>
            <div className="text-[9px] font-mono text-text-muted uppercase tracking-widest">Signal · 24p</div>
            <div className="text-[10px] font-mono text-text-tertiary tabular">{history.length} obs</div>
          </div>
          <Sparkline data={history} width={140} height={28} />
        </div>
      )}

      {indicators.length > 0 && (
        <div className="space-y-1">
          <div className="text-[9px] font-mono text-text-muted uppercase tracking-widest mb-2 flex items-center justify-between">
            <span>Indicator Breakdown</span>
            <span className="text-text-muted/70">click for detail</span>
          </div>
          {indicators.slice(0, 9).map((ind, i) => {
            const s = ind.score ?? 0;
            const t = s > 0.2 ? 'bull' : s < -0.2 ? 'bear' : 'neut';
            return (
              <button
                key={i}
                onClick={() => onIndicatorClick?.(asset.key, ind)}
                className="grid grid-cols-[80px_28px_42px_1fr_12px] items-center gap-2 text-[10px] font-mono tabular w-full text-left py-1 px-1 -mx-1 rounded hover:bg-bg-hover/50 cursor-pointer transition-colors group"
              >
                <span className="text-text-secondary truncate group-hover:text-text-primary">{ind.name}</span>
                <span className="text-text-muted text-right">{Math.round((ind.weight ?? 0) * 100)}%</span>
                <span className={clsx('text-center font-semibold', t === 'bull' && 'text-bull', t === 'bear' && 'text-bear', t === 'neut' && 'text-neut')}>
                  {s >= 0 ? '+' : ''}{s.toFixed(1)}
                </span>
                <span className="text-text-tertiary truncate text-[9.5px]">{ind.reason}</span>
                <ChevronRight className="w-3 h-3 text-text-muted opacity-0 group-hover:opacity-100 transition-opacity" />
              </button>
            );
          })}
        </div>
      )}

      {signal?.key_risk && (
        <div className="mt-4 pt-3 border-t border-border/60 flex items-start gap-2">
          <AlertTriangle className="w-3.5 h-3.5 text-neut flex-shrink-0 mt-0.5" />
          <span className="text-[10px] font-mono text-neut/90 leading-snug">{signal.key_risk}</span>
        </div>
      )}
    </Panel>
  );
}

function FairValueCard({ fv }: { fv: any }) {
  const brent = fv?.brent;
  if (!brent) return <Panel title="Fair Value · Brent"><SkeletonRows rows={6} /></Panel>;
  const components = brent.components ?? {};
  const dev = brent.deviation_pct ?? 0;
  return (
    <Panel title="Fair Value · Brent" subtitle="Multi-factor model" accent="blue">
      <div className="flex items-end justify-between mb-4">
        <div>
          <div className="text-[10px] font-mono text-text-tertiary uppercase tracking-widest">Spot</div>
          <div className="text-3xl font-display font-extrabold text-text-primary tabular">${fmt.price(brent.live_price)}</div>
        </div>
        <div className="text-center px-4">
          <div className="text-[10px] font-mono text-text-tertiary uppercase tracking-widest">vs Fair</div>
          <div className={clsx(
            'text-2xl font-display font-extrabold tabular',
            dev > 0 ? 'text-bear' : 'text-bull',
          )}>
            {dev >= 0 ? '+' : ''}{dev.toFixed(1)}%
          </div>
          <div className="text-[9px] font-mono text-text-muted mt-0.5">{brent.deviation_label}</div>
        </div>
        <div className="text-right">
          <div className="text-[10px] font-mono text-text-tertiary uppercase tracking-widest">Fair</div>
          <div className="text-3xl font-display font-extrabold text-gold tabular">${fmt.price(brent.fair_value)}</div>
        </div>
      </div>
      <div className="space-y-2">
        {Object.entries(components).map(([name, comp]: any) => {
          const v = comp?.value ?? 0;
          const label = name.replace(/_/g, ' ').replace(/\b\w/g, (l: string) => l.toUpperCase());
          return (
            <div key={name} className="grid grid-cols-[1fr_70px_60px] gap-3 items-center text-[10px] font-mono">
              <span className="text-text-secondary truncate">{label}</span>
              <div className="h-1.5 bg-bg-elev rounded overflow-hidden relative">
                <div className="absolute inset-y-0 left-1/2 w-px bg-border-strong" />
                <div
                  className="absolute inset-y-0 rounded transition-all"
                  style={{
                    left: v >= 0 ? '50%' : `${50 - Math.min(50, Math.abs(v) * 5)}%`,
                    width: `${Math.min(50, Math.abs(v) * 5)}%`,
                    background: v >= 0 ? '#10d997' : '#ff4d6d',
                  }}
                />
              </div>
              <span className={clsx('text-right tabular', v >= 0 ? 'text-bull' : 'text-bear')}>
                {v >= 0 ? '+' : ''}${v.toFixed(2)}
              </span>
            </div>
          );
        })}
      </div>
    </Panel>
  );
}

function TradeIdeaCard({ idea }: { idea: any }) {
  if (!idea) return <Panel title="Trade Idea · Brent"><SkeletonRows rows={4} /></Panel>;
  const dir = idea.direction?.toUpperCase() ?? 'NEUTRAL';
  const tone = dir.includes('LONG') ? 'bull' : dir.includes('SHORT') ? 'bear' : 'neut';
  const thesis = Array.isArray(idea.entry_thesis) ? idea.entry_thesis.join(' ') : idea.thesis;

  return (
    <Panel
      title="Trade Idea · Brent"
      subtitle={`${idea.time_horizon ?? '1–2W'} · ${idea.conviction ?? '—'}`}
      accent={tone as any}
      right={<Chip tone={tone as any}>{dir}</Chip>}
    >
      <div className="grid grid-cols-4 gap-3 mb-4">
        <Stat label="Spot" value={`$${fmt.price(idea.live_price)}`} />
        <Stat label="Target" value={`$${fmt.price(idea.target_level)}`} tone="bull" />
        <Stat label="Stop" value={`$${fmt.price(idea.stop_level)}`} tone="bear" />
        <Stat label="Fair Value" value={`$${fmt.price(idea.fair_value)}`} tone="gold" />
      </div>
      {thesis && (
        <div className="p-3 bg-bg-card/60 rounded border-l-2 border-gold/40 text-[12px] leading-relaxed text-text-secondary">
          {thesis}
        </div>
      )}
      {idea.key_risk && (
        <div className="mt-2 flex items-start gap-2 text-[10px] font-mono text-neut/90">
          <Shield className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
          <span><span className="text-text-muted uppercase tracking-widest mr-1">RISK ·</span>{idea.key_risk}</span>
        </div>
      )}
      {idea.morning_brief && (
        <details className="mt-3 group">
          <summary className="cursor-pointer text-[10px] font-mono text-text-tertiary uppercase tracking-widest hover:text-gold flex items-center gap-1.5">
            <BookOpen className="w-3 h-3" />
            <span>Morning Brief</span>
            <span className="ml-auto text-text-muted group-open:rotate-180 transition-transform">▾</span>
          </summary>
          <div className="mt-2 text-[11.5px] leading-relaxed text-text-secondary p-3 bg-bg-card/40 rounded">
            {idea.morning_brief}
          </div>
        </details>
      )}
    </Panel>
  );
}

function MacroPanel({ macro }: { macro: any }) {
  if (!macro) return <Panel title="Macro Signals"><SkeletonRows rows={5} /></Panel>;
  const items = [
    { label: '10Y Yield', val: macro.DGS10?.value, unit: '%', trend: macro.DGS10?.change_pct },
    { label: 'CPI YoY', val: macro.CPIAUCSL?.yoy_pct, unit: '%' },
    { label: 'EUR/USD', val: macro.DEXUSEU?.value },
    { label: 'Fed Funds', val: macro.FEDFUNDS?.value, unit: '%' },
    { label: 'INDPRO MoM', val: macro.INDPRO?.mom_pct, unit: '%' },
    { label: '30Y Mortgage', val: macro.MORTGAGE30US?.value, unit: '%' },
  ];
  return (
    <Panel title="Macro Signals" subtitle="FRED">
      <div className="grid grid-cols-2 gap-x-4 gap-y-3">
        {items.map((it, i) => (
          <div key={i} className="flex items-baseline justify-between border-b border-border/40 pb-2">
            <span className="text-[10px] font-mono text-text-tertiary uppercase tracking-widest">{it.label}</span>
            <span className="text-[14px] font-mono font-semibold tabular text-text-primary">
              {it.val !== null && it.val !== undefined ? `${it.val.toFixed(2)}${it.unit ?? ''}` : '—'}
            </span>
          </div>
        ))}
      </div>
    </Panel>
  );
}

function AlertsBanner({ alerts }: { alerts: any[] }) {
  if (!alerts || alerts.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-2 mb-1">
      {alerts.slice(0, 4).map((a, i) => {
        const tone = a.severity === 'critical' ? 'bear' : a.severity === 'warning' ? 'neut' : 'blue';
        return (
          <Chip key={i} tone={tone as any} icon={<AlertTriangle className="w-3 h-3" />}>
            <span className="font-semibold mr-1">{a.type}</span>
            <span className="opacity-80">{a.message}</span>
          </Chip>
        );
      })}
    </div>
  );
}

export function SignalView({ all, tradeIdea, alerts }: { all: any; tradeIdea: any; alerts: any[] }) {
  const prices = all?.prices ?? {};
  const signal = all?.signal ?? {};
  const fv = all?.fair_value;
  const macro = all?.macro;
  const curve = all?.curve;
  const brentSpot = prices?.brent?.price ?? null;
  // Derive a rough spare-capacity estimate from EIA STEO if available, else fall back.
  const steoSpare =
    all?.steo?.opec_spare_capacity ??
    all?.steo?.spare_capacity ??
    null;
  const spareCapacity = typeof steoSpare === 'number' && steoSpare > 0 ? steoSpare : 4.5;

  // Drill-down modal state
  const [drill, setDrill] = useState<{ asset: string; indicator: any } | null>(null);

  return (
    <div className="space-y-4">
      <AlertsBanner alerts={alerts} />

      {/* Hero signal cards */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {ASSETS.map(a => (
          <SignalCard
            key={a.key}
            asset={a}
            signal={signal[a.key]}
            price={prices[a.key]}
            onIndicatorClick={(assetKey, indicator) => setDrill({ asset: assetKey, indicator })}
          />
        ))}
      </div>

      {/* Row 2 — Price Decomposition Waterfall (the standout visual) */}
      <PriceDecomposition fairValue={fv} signal={signal} curve={curve} />

      {/* Row 3: trade idea + fair value */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2">
          <TradeIdeaCard idea={tradeIdea} />
        </div>
        <FairValueCard fv={fv} />
      </div>

      {/* Row 4 — Geo Risk Premium Calculator (curriculum chapter 10 framework) */}
      <GeoRiskCalculator
        defaultSpareCapacity={spareCapacity}
        brentPrice={brentSpot}
      />

      {/* Indicator drill-down modal */}
      <IndicatorDrillDown
        open={drill !== null}
        onClose={() => setDrill(null)}
        indicator={drill?.indicator}
        asset={drill?.asset ?? ''}
      />


      {/* Row 3: macro */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <MacroPanel macro={macro} />
        <Panel title="Composite Read" subtitle="Cross-asset bias" accent="gold">
          <div className="grid grid-cols-3 gap-4">
            {ASSETS.map(a => {
              const s = signal?.[a.key]?.score ?? null;
              const tone = s === null ? 'neut' : s >= 0.4 ? 'bull' : s <= -0.4 ? 'bear' : 'neut';
              return (
                <div key={a.key} className="text-center p-3 bg-bg-card/50 rounded">
                  <div className="text-[10px] font-mono tracking-widest text-text-tertiary uppercase mb-1">{a.label}</div>
                  <div className={clsx(
                    'text-2xl font-display font-extrabold tabular',
                    tone === 'bull' && 'text-bull',
                    tone === 'bear' && 'text-bear',
                    tone === 'neut' && 'text-neut',
                  )}>
                    {s !== null ? (s >= 0 ? '+' : '') + s.toFixed(2) : '—'}
                  </div>
                  <div className={clsx(
                    'text-[10px] font-mono mt-1 uppercase tracking-widest',
                    tone === 'bull' && 'text-bull',
                    tone === 'bear' && 'text-bear',
                    tone === 'neut' && 'text-neut',
                  )}>{signalLabel(s)}</div>
                </div>
              );
            })}
          </div>
          <div className="mt-4 grid grid-cols-2 gap-3 text-[11px] font-mono text-text-tertiary">
            <div className="flex justify-between p-2 bg-bg-card/40 rounded">
              <span>Avg Score</span>
              <span className="text-text-secondary tabular">
                {(() => {
                  const xs = ASSETS.map(a => signal?.[a.key]?.score).filter(x => typeof x === 'number');
                  return xs.length ? (xs.reduce((s, x) => s + x, 0) / xs.length).toFixed(2) : '—';
                })()}
              </span>
            </div>
            <div className="flex justify-between p-2 bg-bg-card/40 rounded">
              <span>Conviction</span>
              <span className="text-text-secondary tracking-widest">
                {(() => {
                  const cs = ASSETS.map(a => signal?.[a.key]?.conviction).filter(Boolean);
                  if (cs.includes('HIGH')) return 'HIGH';
                  if (cs.includes('MODERATE')) return 'MOD';
                  return 'LOW';
                })()}
              </span>
            </div>
          </div>
        </Panel>
      </div>
    </div>
  );
}
