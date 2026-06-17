import { useMemo, useState } from 'react';
import clsx from 'clsx';
import { motion } from 'framer-motion';
import { Panel } from '@/components/ui/Panel';
import { Chip } from '@/components/ui/Chip';
import { SkeletonRows } from '@/components/ui/Skeleton';
import { PriceDecomposition } from '@/components/panels/PriceDecomposition';
import { PositionRow, PositionRowHeader } from '@/components/panels/PositionRow';
import { RiskPanel } from '@/components/panels/RiskPanel';
import { GeoRiskCalculator } from '@/components/panels/GeoRiskCalculator';
import { IndicatorDrillDown } from '@/components/panels/IndicatorDrillDown';
import { api } from '@/lib/api';
import { usePolling } from '@/lib/hooks';
import { staggerContainer, staggerTight, fadeUp } from '@/lib/motion';
import type { PaperPosition } from '@/lib/api-types';
import { TrendingUp, TrendingDown, Activity, BookOpen, ChevronRight, Flame, Droplet, Wind, Compass } from 'lucide-react';

type ViewKey =
  | 'desk' | 'charts'
  | 'markets' | 'paper' | 'regime' | 'signals';

const INDICATOR_ASSETS = [
  { key: 'brent',     label: 'BRENT' },
  { key: 'wti',       label: 'WTI' },
  { key: 'henry_hub', label: 'NAT GAS' },
];

type RankedOpp = {
  spread: string;
  label: string;
  direction: 'BUY' | 'SELL' | 'NEUTRAL';
  current: number;
  fair_value: number;
  z_score: number;
  confidence: number;
};

type Recommendation = {
  available: boolean;
  regime?: string;
  as_of?: string;
  top?: RankedOpp;
  ranked?: RankedOpp[];
};

// ── Hero: today's regime pick ───────────────────────────────────────────────

function HeroPick({
  rec, lastSuccess, fetchError,
}: {
  rec: Recommendation | null;
  lastSuccess?: number | null;
  fetchError?: unknown;
}) {
  // Loading: first paint with no data yet.
  if (!rec && !fetchError) {
    return (
      <Panel
        title="Today's Pick · Regime Engine"
        accent="gold"
        source="signal_engine"
        staticMount
        feature
        lastSuccess={lastSuccess}
        fetchError={fetchError}
      >
        <SkeletonRows rows={3} />
      </Panel>
    );
  }
  // Empty: fetched ok but the engine reports unavailable (sklearn missing,
  // pkls absent, etc.) — show why, not an infinite skeleton.
  if (!rec || !rec.available || !rec.top) {
    return (
      <Panel
        title="Today's Pick · Regime Engine"
        accent="gold"
        source="signal_engine"
        staticMount
        feature
        lastSuccess={lastSuccess}
        fetchError={fetchError}
      >
        <div className="text-[12px] font-mono text-text-tertiary px-3 py-6 text-center">
          {fetchError
            ? `Regime endpoint unreachable: ${(fetchError as any)?.message ?? String(fetchError)}`
            : (rec as any)?.error
              ? `Engine unavailable: ${(rec as any).error}`
              : 'No live recommendation — the regime engine returned no signal.'}
        </div>
      </Panel>
    );
  }
  const top = rec.top;
  const ranked = rec.ranked ?? [];
  const isNeutral = top.direction === 'NEUTRAL';
  const dirTone: 'bull' | 'bear' | 'neut' =
    top.direction === 'BUY' ? 'bull' : top.direction === 'SELL' ? 'bear' : 'neut';
  const heroAccent: 'bull' | 'bear' | 'neut' | 'gold' = isNeutral ? 'gold' : dirTone;

  const edge = top.fair_value - top.current; // signed: positive → underpriced
  const edgePct = top.current !== 0 ? (edge / Math.abs(top.current)) * 100 : 0;

  return (
    <Panel
      title="Today's Pick · Regime Engine"
      subtitle={rec.regime ? `Regime ${rec.regime}` : 'live'}
      accent={heroAccent}
      source="signal_engine"
      dataTimestamp={rec.as_of}
      right={<Chip tone={dirTone as any}>{top.direction}</Chip>}
      staticMount
      feature
      lastSuccess={lastSuccess}
      fetchError={fetchError}
    >
      {/* Hero — big z, direction badge, edge */}
      <div
        className={clsx(
          'relative rounded-xl p-5 mb-4 overflow-hidden border',
          isNeutral && 'hero-neut border-border/40',
          !isNeutral && top.direction === 'BUY' && 'hero-buy',
          !isNeutral && top.direction === 'SELL' && 'hero-sell',
        )}
        style={
          isNeutral
            ? undefined
            : {
                borderColor: `var(--${dirTone}-ring)`,
                boxShadow: `0 0 40px -8px var(--${dirTone}-ring), inset 0 1px 0 rgba(255,255,255,0.03)`,
              }
        }
      >
        {/* faint corner ticks */}
        <span aria-hidden className="absolute top-2 left-2 w-2 h-2 border-t border-l" style={{ borderColor: 'var(--border-accent)' }} />
        <span aria-hidden className="absolute top-2 right-2 w-2 h-2 border-t border-r" style={{ borderColor: 'var(--border-accent)' }} />
        <span aria-hidden className="absolute bottom-2 left-2 w-2 h-2 border-b border-l" style={{ borderColor: 'var(--border-accent)' }} />
        <span aria-hidden className="absolute bottom-2 right-2 w-2 h-2 border-b border-r" style={{ borderColor: 'var(--border-accent)' }} />

        {isNeutral ? (
          <div className="text-center py-3">
            <div className="text-[10px] font-mono uppercase tracking-[0.30em] text-text-muted mb-2">No-Trade Day</div>
            <div className="font-display font-bold text-[22px] text-text-primary leading-tight">
              All spreads inside band
            </div>
            <div className="text-[11px] font-mono text-text-tertiary mt-2">
              Regime: <span className="text-gold">{rec.regime ?? '—'}</span>
            </div>
          </div>
        ) : (
          <div className="grid grid-cols-[1fr_auto_1fr] gap-6 items-center">
            {/* LEFT: instrument + direction */}
            <div className="flex flex-col gap-2">
              <div className="text-[9.5px] font-mono uppercase tracking-[0.30em] text-text-muted">Spread</div>
              <div className="font-display font-extrabold text-[22px] text-text-primary leading-tight tracking-wide truncate">
                {top.label}
              </div>
              <div className="flex items-center gap-2 mt-1">
                <span
                  className={clsx(
                    'inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md font-mono font-bold text-[11px] tracking-widest border',
                    top.direction === 'BUY' ? 'bg-bull/15 text-bull border-bull/40' : 'bg-bear/15 text-bear border-bear/40',
                  )}
                  style={{ boxShadow: `0 0 16px -4px var(--${dirTone}-ring)` }}
                >
                  {top.direction === 'BUY' ? <TrendingUp className="w-3.5 h-3.5" /> : <TrendingDown className="w-3.5 h-3.5" />}
                  {top.direction === 'BUY' ? 'LONG' : 'SHORT'}
                </span>
                <span className="text-[10px] font-mono text-text-tertiary uppercase tracking-widest">
                  conf {(top.confidence * 100).toFixed(0)}%
                </span>
              </div>
            </div>

            {/* MIDDLE: massive z-score */}
            <div className="flex flex-col items-center px-4 border-x border-border/40">
              <div className="text-[9.5px] font-mono uppercase tracking-[0.30em] text-text-muted mb-1">z-score</div>
              <div
                className={clsx(
                  'font-display font-black tabular leading-none',
                  Math.abs(top.z_score) >= 2 ? 'text-[56px]' : 'text-[48px]',
                )}
                style={{
                  background:
                    top.z_score >= 0
                      ? 'linear-gradient(180deg, rgb(var(--bear)) 0%, rgba(255,88,116,0.65) 100%)'
                      : 'linear-gradient(180deg, rgb(var(--bull)) 0%, rgba(22,224,158,0.65) 100%)',
                  WebkitBackgroundClip: 'text',
                  backgroundClip: 'text',
                  WebkitTextFillColor: 'transparent',
                  filter:
                    top.z_score >= 0
                      ? 'drop-shadow(0 0 20px var(--bear-ring))'
                      : 'drop-shadow(0 0 20px var(--bull-ring))',
                }}
              >
                {top.z_score >= 0 ? '+' : ''}{top.z_score.toFixed(2)}
              </div>
              <div className="text-[9px] font-mono uppercase tracking-[0.24em] text-text-muted mt-1.5">σ from fair</div>
            </div>

            {/* RIGHT: prices + edge */}
            <div className="flex flex-col gap-2 items-end">
              <div className="text-[9.5px] font-mono uppercase tracking-[0.30em] text-text-muted">Edge</div>
              <div className="flex items-baseline gap-2">
                <span
                  className={clsx(
                    'font-display font-extrabold text-[22px] tabular leading-tight',
                    edge >= 0 ? 'text-bull' : 'text-bear',
                  )}
                >
                  {edge >= 0 ? '+' : ''}${Math.abs(edge).toFixed(2)}
                </span>
                <span className="text-[11px] font-mono text-text-tertiary tabular">
                  ({edgePct >= 0 ? '+' : ''}{edgePct.toFixed(1)}%)
                </span>
              </div>
              <div className="text-[10px] font-mono text-text-tertiary tabular mt-1 flex items-center gap-1.5">
                <span className="text-text-secondary">${top.current.toFixed(2)}</span>
                <span className="text-gold">→</span>
                <span className="text-gold">${top.fair_value.toFixed(2)}</span>
              </div>
              <div className="text-[8.5px] font-mono uppercase tracking-[0.24em] text-text-muted">current · fair</div>
            </div>
          </div>
        )}
      </div>

      {/* Mini ranking table */}
      {ranked.length > 0 && (
        <div>
          <div className="grid grid-cols-[28px_1fr_70px_70px_60px_60px] gap-2 items-center text-[9px] font-mono uppercase tracking-widest text-text-muted border-b border-border pb-1 px-1">
            <span>#</span>
            <span>Spread</span>
            <span className="text-right">Current</span>
            <span className="text-right">Fair</span>
            <span className="text-right">z</span>
            <span className="text-right">Conf</span>
          </div>
          {ranked.map((o, i) => {
            const Icon = o.direction === 'BUY' ? TrendingUp : o.direction === 'SELL' ? TrendingDown : Activity;
            const t = o.direction === 'BUY' ? 'text-bull' : o.direction === 'SELL' ? 'text-bear' : 'text-text-tertiary';
            return (
              <div
                key={o.spread}
                className={clsx(
                  'grid grid-cols-[28px_1fr_70px_70px_60px_60px] gap-2 items-center py-1.5 px-1 text-[11px] font-mono tabular border-b border-border/30',
                  i === 0 && 'bg-bg-card/40',
                )}
              >
                <span className={clsx('uppercase tracking-widest', i === 0 ? 'text-gold font-bold' : 'text-text-muted')}>
                  #{i + 1}
                </span>
                <span className="flex items-center gap-2 min-w-0">
                  <Icon className={clsx('w-3.5 h-3.5 flex-shrink-0', t)} />
                  <span className="text-text-primary truncate">{o.label}</span>
                </span>
                <span className="text-right text-text-secondary">{o.current.toFixed(2)}</span>
                <span className="text-right text-gold">{o.fair_value.toFixed(2)}</span>
                <span className={clsx(
                  'text-right font-semibold',
                  o.z_score > 1.5 ? 'text-bear' : o.z_score < -1.5 ? 'text-bull' : 'text-neut',
                )}>
                  {o.z_score >= 0 ? '+' : ''}{o.z_score.toFixed(2)}
                </span>
                <span className="text-right text-text-tertiary">
                  {(o.confidence * 100).toFixed(0)}%
                </span>
              </div>
            );
          })}
        </div>
      )}
    </Panel>
  );
}

// ── Open positions strip ────────────────────────────────────────────────────

function OpenPositionsStrip({
  positions,
  onNavigate,
  lastSuccess,
  fetchError,
}: {
  positions: PaperPosition[];
  onNavigate?: (k: ViewKey) => void;
  lastSuccess?: number | null;
  fetchError?: unknown;
}) {
  const open = useMemo(() => positions.filter(p => p.status === 'OPEN'), [positions]);
  const shown = open.slice(0, 5);
  const more = Math.max(0, open.length - shown.length);

  if (open.length === 0) {
    return (
      <Panel
        title="Open Positions"
        accent="blue"
        source="paper_book"
        staticMount
        lastSuccess={lastSuccess}
        fetchError={fetchError}
      >
        <div className="text-[11px] font-mono text-text-tertiary p-4 text-center">
          {fetchError
            ? `Paper book endpoint failed: ${(fetchError as any)?.message ?? String(fetchError)}`
            : 'No open paper trades. Push a regime pick from above.'}
        </div>
      </Panel>
    );
  }
  return (
    <Panel
      title="Open Positions"
      subtitle={`${open.length} active · live MTM`}
      accent="blue"
      source="paper_book"
      staticMount
      lastSuccess={lastSuccess}
      fetchError={fetchError}
      right={
        more > 0 && onNavigate ? (
          <button
            onClick={() => onNavigate('paper')}
            className="text-[10px] font-mono uppercase tracking-widest text-gold hover:text-gold-bright px-2 py-1 rounded hover:bg-bg-hover"
          >
            +{more} more → PAPER
          </button>
        ) : undefined
      }
    >
      <PositionRowHeader />
      {shown.map(p => <PositionRow key={p.id} p={p} />)}
    </Panel>
  );
}

// ── Morning brief ───────────────────────────────────────────────────────────

function MorningBrief({ idea }: { idea: any }) {
  if (!idea) return <Panel title="Morning Brief" source="groq_brief" staticMount><SkeletonRows rows={4} /></Panel>;
  const text = (idea.morning_brief ?? '').trim();
  if (!text) {
    return (
      <Panel title="Morning Brief" subtitle="awaiting brief" source="groq_brief" staticMount>
        <div className="text-[11px] font-mono text-text-tertiary p-3 text-center">
          Brief not generated yet. Refreshes every 10 min.
        </div>
      </Panel>
    );
  }
  const dir = (idea.direction ?? 'NEUTRAL').toUpperCase();
  const tone: 'bull' | 'bear' | 'neut' =
    dir.includes('LONG') ? 'bull' : dir.includes('SHORT') ? 'bear' : 'neut';
  const lines = text
    .split(/\n+/)
    .map((l: string) => l.replace(/^[\s•\-*]+/, '').trim())
    .filter(Boolean);

  return (
    <Panel
      title="Morning Brief"
      subtitle={`${idea.time_horizon ?? '1-2W'} · ${idea.conviction ?? '—'}`}
      accent={tone}
      source="groq_brief"
      dataTimestamp={idea.timestamp}
      right={<Chip tone={tone as any}>{dir}</Chip>}
      staticMount
    >
      <div className="flex items-center gap-1.5 text-[10px] font-mono uppercase tracking-widest text-text-tertiary mb-2">
        <BookOpen className="w-3 h-3 text-gold" />
        <span>Today's read</span>
      </div>
      <ul className="text-[12px] leading-relaxed text-text-secondary p-3 bg-bg-card/40 rounded space-y-1.5 list-none">
        {lines.length >= 2 ? lines.map((line: string, i: number) => (
          <li key={i} className="flex items-start gap-2">
            <span className="text-gold mt-0.5 flex-shrink-0">•</span>
            <span>{line}</span>
          </li>
        )) : (
          <li>{text}</li>
        )}
      </ul>
    </Panel>
  );
}

// ── Signal indicator drill entry point ─────────────────────────────────────
// Relocated from the deleted Signal tab. Lists the per-asset signal indicator
// breakdown across BRENT/WTI/NAT GAS as clickable rows that open the same
// curriculum-grade IndicatorDrillDown modal as before.

function IndicatorDrillPanel({
  signal,
  onPick,
}: {
  signal: any;
  onPick: (asset: string, indicator: any) => void;
}) {
  const buckets = useMemo(
    () =>
      INDICATOR_ASSETS.map(a => ({
        ...a,
        indicators: (signal?.[a.key]?.indicators ?? []) as any[],
      })).filter(b => b.indicators.length > 0),
    [signal],
  );

  if (buckets.length === 0) {
    return (
      <Panel title="Signal Drill" subtitle="indicator detail" source="signal_engine" staticMount>
        <SkeletonRows rows={4} />
      </Panel>
    );
  }

  return (
    <Panel
      title="Signal Drill"
      subtitle="click any indicator for curriculum-grade detail"
      accent="blue"
      source="signal_engine"
      dataTimestamp={signal?.timestamp}
      staticMount
    >
      <motion.div
        variants={staggerTight}
        initial="hidden"
        animate="show"
        className="grid grid-cols-1 lg:grid-cols-3 gap-4"
      >
        {buckets.map(b => (
          <motion.div key={b.key} variants={fadeUp} className="space-y-1">
            <div className="text-[10px] font-mono uppercase tracking-widest text-text-tertiary border-b border-border/40 pb-1 mb-1.5">
              {b.label}
            </div>
            {b.indicators.slice(0, 9).map((ind: any, i: number) => {
              const s = ind.score ?? 0;
              const t = s > 0.2 ? 'bull' : s < -0.2 ? 'bear' : 'neut';
              return (
                <button
                  key={i}
                  onClick={() => onPick(b.key, ind)}
                  className="grid grid-cols-[80px_28px_42px_1fr_12px] items-center gap-2 text-[10px] font-mono tabular w-full text-left py-1 px-1 -mx-1 rounded hover:bg-bg-hover/50 cursor-pointer transition-colors group"
                >
                  <span className="text-text-secondary truncate group-hover:text-text-primary">{ind.name}</span>
                  <span className="text-text-muted text-right">{Math.round((ind.weight ?? 0) * 100)}%</span>
                  <span
                    className={clsx(
                      'text-center font-semibold',
                      t === 'bull' && 'text-bull',
                      t === 'bear' && 'text-bear',
                      t === 'neut' && 'text-neut',
                    )}
                  >
                    {s >= 0 ? '+' : ''}{s.toFixed(1)}
                  </span>
                  <span className="text-text-tertiary truncate text-[9.5px]">{ind.reason}</span>
                  <ChevronRight className="w-3 h-3 text-text-muted opacity-0 group-hover:opacity-100 group-hover:translate-x-0.5 transition-all" />
                </button>
              );
            })}
          </motion.div>
        ))}
      </motion.div>
    </Panel>
  );
}

// ── KPI strip ───────────────────────────────────────────────────────────────
// Premium hero strip across the top — quick orientation: regime, brent spot,
// front-month spread, BRT–WTI arb, geopolitics index. Pure presentational.

function KpiTile({
  label, value, sub, tone, icon: Icon, glow,
}: {
  label: string;
  value: string;
  sub?: string;
  tone?: 'bull' | 'bear' | 'neut' | 'gold';
  icon?: any;
  glow?: boolean;
}) {
  const toneColor =
    tone === 'bull' ? 'text-bull' :
    tone === 'bear' ? 'text-bear' :
    tone === 'neut' ? 'text-neut' :
    tone === 'gold' ? 'text-gold-bright' :
    'text-text-primary';
  return (
    <motion.div variants={fadeUp} className="kpi-card group">
      <div className="flex items-center justify-between mb-1.5 relative z-10">
        <span className="text-[8.5px] font-mono uppercase tracking-[0.26em] text-text-muted">{label}</span>
        {Icon && (
          <span
            className={clsx(
              'flex items-center justify-center w-5 h-5 rounded-md transition-colors',
              tone === 'bull' ? 'bg-bull/10 text-bull' :
              tone === 'bear' ? 'bg-bear/10 text-bear' :
              tone === 'neut' ? 'bg-neut/10 text-neut' :
              'bg-gold/10 text-gold',
            )}
          >
            <Icon className="w-3 h-3" strokeWidth={2.4} />
          </span>
        )}
      </div>
      <div
        className={clsx(
          'font-display font-extrabold tabular leading-none text-[22px] relative z-10',
          toneColor,
        )}
        style={glow && tone === 'gold'
          ? { textShadow: '0 0 18px var(--gold-glow)' }
          : undefined
        }
      >
        {value}
      </div>
      {sub && <div className="text-[9.5px] font-mono text-text-tertiary tabular mt-1 relative z-10">{sub}</div>}
    </motion.div>
  );
}

function KpiStrip({
  rec, all,
}: {
  rec: Recommendation | null;
  all: any;
}) {
  const prices = all?.prices ?? {};
  const curve = all?.curve;
  const fundamentals = all?.fundamentals;

  const brent = prices?.brent?.price ?? null;
  const brentChg = prices?.brent?.change_pct ?? null;
  const wti = prices?.wti?.price ?? null;
  const m1m2 =
    curve?.brent?.[0] && curve?.brent?.[1]
      ? curve.brent[0].price - curve.brent[1].price
      : null;
  const brtWti = brent !== null && wti !== null ? brent - wti : null;
  const geo = fundamentals?.geo_risk?.score ?? null;

  const regimeLabel = rec?.regime ?? '—';
  const regimeTone: 'bull' | 'bear' | 'neut' | 'gold' = (() => {
    if (!regimeLabel || regimeLabel === '—') return 'gold';
    const upper = regimeLabel.toUpperCase();
    if (upper.includes('BACK')) return 'bull';
    if (upper.includes('CONT')) return 'bear';
    return 'gold';
  })();

  return (
    <motion.div
      variants={staggerTight}
      initial="hidden"
      animate="show"
      className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3"
    >
      <KpiTile
        label="Regime · live"
        value={regimeLabel}
        sub="curve · inv · vol composite"
        tone={regimeTone}
        icon={Compass}
        glow
      />
      <KpiTile
        label="Brent · spot"
        value={brent !== null ? `$${brent.toFixed(2)}` : '—'}
        sub={brentChg !== null ? `${brentChg >= 0 ? '+' : ''}${brentChg.toFixed(2)}% intraday` : 'awaiting feed'}
        tone={brentChg !== null ? (brentChg >= 0 ? 'bull' : 'bear') : undefined}
        icon={Droplet}
      />
      <KpiTile
        label="M1 – M2"
        value={m1m2 !== null ? `${m1m2 >= 0 ? '+' : ''}$${m1m2.toFixed(2)}` : '—'}
        sub={m1m2 !== null ? (m1m2 > 0 ? 'backwardation' : 'contango') : 'front-end curve'}
        tone={m1m2 !== null ? (m1m2 > 0 ? 'bull' : 'bear') : undefined}
        icon={Flame}
      />
      <KpiTile
        label="BRT – WTI"
        value={brtWti !== null ? `$${brtWti.toFixed(2)}` : '—'}
        sub="atlantic arb"
        tone="neut"
        icon={Wind}
      />
      <KpiTile
        label="Geo · idx"
        value={geo !== null ? geo.toFixed(0) : '—'}
        sub={geo !== null ? (geo > 60 ? 'elevated risk' : 'baseline') : 'aggregated headlines'}
        tone={geo !== null && geo > 60 ? 'bear' : 'gold'}
        icon={Activity}
      />
    </motion.div>
  );
}

// ── Top-level view ──────────────────────────────────────────────────────────

export function DeskView({
  all,
  tradeIdea,
  onNavigate,
}: {
  all: any;
  tradeIdea: any;
  onNavigate?: (k: ViewKey) => void;
}) {
  const { data: rec, lastUpdated: recLastUpdated, error: recError } =
    usePolling<Recommendation>(api.regimeRecommendation, 60_000);
  const { data: positions, lastUpdated: posLastUpdated, error: posError } =
    usePolling<PaperPosition[]>(api.paperPositions, 15_000);

  const fv = all?.fair_value;
  const signal = all?.signal;
  const curve = all?.curve;
  const correlations = all?.correlations;
  const prices = all?.prices ?? {};
  const pos = positions ?? [];

  const brentSpot = prices?.brent?.price ?? null;
  const steoSpare =
    all?.steo?.opec_spare_capacity ??
    all?.steo?.spare_capacity ??
    null;
  const spareCapacity = typeof steoSpare === 'number' && steoSpare > 0 ? steoSpare : 4.5;

  const [drill, setDrill] = useState<{ asset: string; indicator: any } | null>(null);

  return (
    <motion.div
      className="space-y-4"
      variants={staggerContainer}
      initial="hidden"
      animate="show"
    >
      <motion.div variants={fadeUp}>
        <KpiStrip rec={rec ?? null} all={all} />
      </motion.div>

      <motion.div variants={fadeUp}>
        <HeroPick rec={rec ?? null} lastSuccess={recLastUpdated} fetchError={recError} />
      </motion.div>

      <motion.div variants={fadeUp}>
        <OpenPositionsStrip
          positions={pos}
          onNavigate={onNavigate}
          lastSuccess={posLastUpdated}
          fetchError={posError}
        />
      </motion.div>

      <motion.div variants={fadeUp}>
        <RiskPanel positions={pos} correlations={correlations} />
      </motion.div>

      <motion.div variants={fadeUp}>
        <MorningBrief idea={tradeIdea} />
      </motion.div>

      <motion.div variants={fadeUp}>
        <PriceDecomposition fairValue={fv} signal={signal} curve={curve} />
      </motion.div>

      <motion.div variants={fadeUp}>
        <IndicatorDrillPanel
          signal={signal}
          onPick={(asset, indicator) => setDrill({ asset, indicator })}
        />
      </motion.div>

      <motion.div variants={fadeUp}>
        <GeoRiskCalculator
          defaultSpareCapacity={spareCapacity}
          brentPrice={brentSpot}
        />
      </motion.div>

      <IndicatorDrillDown
        open={drill !== null}
        onClose={() => setDrill(null)}
        indicator={drill?.indicator}
        asset={drill?.asset ?? ''}
      />
    </motion.div>
  );
}
