import { useMemo, useState } from 'react';
import clsx from 'clsx';
import { motion } from 'framer-motion';
import { Panel } from '@/components/ui/Panel';
import { Chip } from '@/components/ui/Chip';
import { SkeletonRows } from '@/components/ui/Skeleton';
import { Sparkline } from '@/components/ui/Sparkline';
import { AnimatedNumber } from '@/components/ui/AnimatedNumber';
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
  // "lake" | "ohlcv_tail (ESTIMATE)" — settle-tail provenance (PULSE_SETTLE_TAIL=1)
  as_of_source?: string;
  top?: RankedOpp;
  ranked?: RankedOpp[];
};

// ── Mission control hero — the first 5 seconds of the desk ─────────────────
// Full-width cinematic band: the engine's directive in display type, a giant
// glowing z-score, the edge, and the whole ranked book as a card rail below.

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
        title="Mission Control · Regime Engine"
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
        title="Mission Control · Regime Engine"
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

  // Audit fix (2026-07-14): "LIVE" is earned by data age, not poll recency.
  // A SELL chip on 17-day-old data is an artifact, not a signal — past the
  // cutoff the hero is stamped STALE and the directive band is muted.
  const staleDays = staleDaysOf(rec.as_of);
  const isStale = staleDays > 4;

  return (
    <Panel
      title="Mission Control · Regime Engine"
      subtitle={
        (rec.regime ? `Regime ${rec.regime}` : 'live') +
        (isStale ? ` · STALE ${staleDays}d` : '')
      }
      accent={heroAccent}
      source="signal_engine"
      dataTimestamp={rec.as_of}
      right={<Chip tone={dirTone as any}>{top.direction}</Chip>}
      staticMount
      feature
      lastSuccess={lastSuccess}
      fetchError={fetchError}
    >
      {/* Directive band */}
      <div
        className={clsx(
          'relative rounded-xl px-6 py-6 mb-3 overflow-hidden border',
          isNeutral && 'hero-neut border-border/40',
          !isNeutral && top.direction === 'BUY' && 'hero-buy',
          !isNeutral && top.direction === 'SELL' && 'hero-sell',
        )}
        style={
          isNeutral
            ? undefined
            : {
                borderColor: `var(--${dirTone}-ring)`,
                boxShadow: `0 0 56px -10px var(--${dirTone}-ring), inset 0 1px 0 rgba(255,255,255,0.03)`,
              }
        }
      >
        {/* faint corner ticks */}
        <span aria-hidden className="absolute top-2 left-2 w-2 h-2 border-t border-l" style={{ borderColor: 'var(--border-accent)' }} />
        <span aria-hidden className="absolute top-2 right-2 w-2 h-2 border-t border-r" style={{ borderColor: 'var(--border-accent)' }} />
        <span aria-hidden className="absolute bottom-2 left-2 w-2 h-2 border-b border-l" style={{ borderColor: 'var(--border-accent)' }} />
        <span aria-hidden className="absolute bottom-2 right-2 w-2 h-2 border-b border-r" style={{ borderColor: 'var(--border-accent)' }} />

        {isNeutral ? (
          <div className="text-center py-4">
            <div className="text-[10px] font-mono uppercase tracking-[0.34em] text-text-muted mb-3">No-Trade Day</div>
            <div className="font-display font-black text-[34px] text-text-primary leading-none tracking-wide">
              All spreads inside band
            </div>
            <div className="text-[11px] font-mono text-text-tertiary mt-3">
              Regime <span className="text-gold">{rec.regime ?? '—'}</span> · the engine holds fire until a z-gate clears
            </div>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-[1.25fr_auto_1fr] gap-6 items-center">
            {/* LEFT: the directive in display type */}
            <div className="flex flex-col gap-2 min-w-0">
              <div className="text-[9.5px] font-mono uppercase tracking-[0.34em] text-text-muted">
                {isStale ? `Top conviction · as of ${rec.as_of}` : 'Top conviction · live'}
              </div>
              <div className="flex items-baseline gap-3 flex-wrap">
                <span
                  className={clsx(
                    'font-display font-black text-[40px] leading-none tracking-wide',
                    top.direction === 'BUY' ? 'text-bull' : 'text-bear',
                  )}
                  style={{ textShadow: `0 0 32px var(--${dirTone}-ring)` }}
                >
                  {top.direction === 'BUY' ? 'LONG' : 'SHORT'}
                </span>
                <span className="font-display font-extrabold text-[30px] leading-none text-text-primary tracking-wide truncate">
                  {top.label}
                </span>
              </div>
              <div className="flex items-center gap-2 mt-1.5">
                <span
                  className={clsx(
                    'inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md font-mono font-bold text-[10px] tracking-widest border',
                    top.direction === 'BUY' ? 'bg-bull/15 text-bull border-bull/40' : 'bg-bear/15 text-bear border-bear/40',
                  )}
                >
                  {top.direction === 'BUY' ? <TrendingUp className="w-3.5 h-3.5" /> : <TrendingDown className="w-3.5 h-3.5" />}
                  {top.direction}
                </span>
                <span className="text-[10px] font-mono text-text-tertiary uppercase tracking-widest">
                  conf {(top.confidence * 100).toFixed(0)}%
                </span>
                {rec.regime && (
                  <span className="chip chip-gold uppercase tracking-widest">{rec.regime}</span>
                )}
                {isStale && (
                  <span
                    className="inline-flex items-center px-2.5 py-1 rounded-md font-mono font-bold text-[10px] tracking-widest border"
                    style={{ background: 'var(--neut-soft)', color: 'var(--neut, #eab308)', borderColor: 'var(--neut-ring)' }}
                    title={`Signal computed on ${rec.as_of} data — ${staleDays} days old. Not a live trading signal.`}
                  >
                    ⚠ {staleDays}D-OLD DATA — NOT LIVE
                  </span>
                )}
              </div>
            </div>

            {/* MIDDLE: massive z-score */}
            <div className="flex flex-col items-center px-6 md:border-x border-border/40">
              <div className="text-[9.5px] font-mono uppercase tracking-[0.30em] text-text-muted mb-1">z-score</div>
              <div
                className={clsx(
                  'font-display font-black tabular leading-none',
                  Math.abs(top.z_score) >= 2 ? 'text-[76px]' : 'text-[64px]',
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
                      ? 'drop-shadow(0 0 24px var(--bear-ring))'
                      : 'drop-shadow(0 0 24px var(--bull-ring))',
                }}
              >
                <AnimatedNumber value={top.z_score} format={n => `${n >= 0 ? '+' : ''}${n.toFixed(2)}`} />
              </div>
              <div className="text-[9px] font-mono uppercase tracking-[0.24em] text-text-muted mt-1.5">σ from fair</div>
            </div>

            {/* RIGHT: prices + edge */}
            <div className="flex flex-col gap-2 items-start md:items-end">
              <div className="text-[9.5px] font-mono uppercase tracking-[0.30em] text-text-muted">Edge to fair</div>
              <div className="flex items-baseline gap-2">
                <span
                  className={clsx(
                    'font-display font-black text-[34px] tabular leading-none',
                    edge >= 0 ? 'text-bull' : 'text-bear',
                  )}
                >
                  <AnimatedNumber value={edge} format={n => `${n >= 0 ? '+' : ''}$${Math.abs(n).toFixed(2)}`} />
                </span>
                <span className="text-[11px] font-mono text-text-tertiary tabular">
                  ({edgePct >= 0 ? '+' : ''}{edgePct.toFixed(1)}%)
                </span>
              </div>
              <div className="text-[11px] font-mono text-text-tertiary tabular mt-1 flex items-center gap-1.5">
                <span className="text-text-secondary">${top.current.toFixed(2)}</span>
                <span className="text-gold">→</span>
                <span className="text-gold">${top.fair_value.toFixed(2)}</span>
              </div>
              <div className="text-[8.5px] font-mono uppercase tracking-[0.24em] text-text-muted">current · fair</div>
            </div>
          </div>
        )}
      </div>

      {/* Ranked book — card rail */}
      {ranked.length > 0 && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-2.5">
          {ranked.slice(0, 8).map((o, i) => {
            const Icon = o.direction === 'BUY' ? TrendingUp : o.direction === 'SELL' ? TrendingDown : Activity;
            const t = o.direction === 'BUY' ? 'text-bull' : o.direction === 'SELL' ? 'text-bear' : 'text-text-tertiary';
            return (
              <div
                key={o.spread}
                className={clsx(
                  'relative rounded-lg border px-3 py-2.5 transition-colors',
                  i === 0
                    ? 'border-gold/40 bg-gold/5'
                    : 'border-border/50 bg-bg-card/30 hover:border-border-strong',
                )}
              >
                <div className="flex items-center justify-between mb-1.5">
                  <span className={clsx(
                    'text-[8.5px] font-mono uppercase tracking-[0.22em]',
                    i === 0 ? 'text-gold font-bold' : 'text-text-muted',
                  )}>
                    #{i + 1}{i === 0 ? ' · top' : ''}
                  </span>
                  <Icon className={clsx('w-3.5 h-3.5', t)} />
                </div>
                <div className="text-[11.5px] font-mono text-text-primary truncate mb-1">{o.label}</div>
                <div className="flex items-baseline justify-between gap-2 text-[10.5px] font-mono tabular">
                  <span className={clsx(
                    'font-bold text-[15px]',
                    o.z_score > 1.5 ? 'text-bear' : o.z_score < -1.5 ? 'text-bull' : 'text-neut',
                  )}>
                    {o.z_score >= 0 ? '+' : ''}{o.z_score.toFixed(2)}σ
                  </span>
                  <span className="text-text-tertiary">
                    {o.current.toFixed(2)} <span className="text-gold">→</span> {o.fair_value.toFixed(2)}
                  </span>
                </div>
                <div className="mt-1.5 h-[3px] rounded-full bg-bg-card overflow-hidden">
                  <div
                    className={clsx('h-full rounded-full', o.direction === 'BUY' ? 'bg-bull/70' : o.direction === 'SELL' ? 'bg-bear/70' : 'bg-neut/50')}
                    style={{ width: `${Math.round((o.confidence ?? 0) * 100)}%` }}
                  />
                </div>
                <div className="mt-1 text-[8.5px] font-mono uppercase tracking-[0.18em] text-text-muted">
                  conf {(o.confidence * 100).toFixed(0)}%
                </div>
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
        {fetchError ? (
          <div className="text-[11px] font-mono text-text-tertiary p-4 text-center">
            Paper book endpoint failed: {(fetchError as any)?.message ?? String(fetchError)}
          </div>
        ) : (
          <div className="flex flex-col items-center gap-2 py-6 text-center">
            <span
              className="flex items-center justify-center w-10 h-10 rounded-xl border border-border/60 text-text-muted"
              style={{ background: 'var(--blue-soft)' }}
            >
              <BookOpen className="w-4.5 h-4.5" style={{ width: 18, height: 18 }} />
            </span>
            <div className="text-[12px] font-mono text-text-secondary">Flat book — nothing at risk.</div>
            <div className="text-[10px] font-mono text-text-muted">
              Push the mission-control pick above, or let the auto-desk take it during market hours.
            </div>
          </div>
        )}
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
        <div className="flex flex-col items-center gap-1.5 py-5 text-center">
          <BookOpen className="w-4 h-4 text-text-muted" />
          <div className="text-[11px] font-mono text-text-tertiary">The analyst hasn't filed yet.</div>
          <div className="text-[10px] font-mono text-text-muted">Brief regenerates every 10 minutes.</div>
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

// ── Stale-feed banner ───────────────────────────────────────────────────────
// The public HF Space runs on the baked parquet lake, so the engine's as_of
// can lag by weeks. Say so honestly instead of letting visitors assume the
// numbers are today's ("honesty over polish").

/** Days since the engine's as_of settle; 0 when unknown/unparseable. */
function staleDaysOf(asOf?: string): number {
  if (!asOf) return 0;
  const t = Date.parse(asOf);
  if (!Number.isFinite(t)) return 0;
  return Math.floor((Date.now() - t) / 86_400_000);
}

function StaleFeedBanner({ asOf, days, asOfSource }: { asOf: string; days: number; asOfSource?: string }) {
  const t = Date.parse(asOf);
  const isTail = Boolean(asOfSource && asOfSource !== 'lake');
  return (
    <div
      className="flex items-center gap-3 px-4 py-2.5 rounded-lg border text-[11px] font-mono"
      style={{
        background: 'var(--neut-soft)',
        borderColor: 'var(--neut-ring)',
      }}
    >
      <span className="text-neut text-[13px] flex-shrink-0">⚠</span>
      <span className="text-text-secondary">
        <span className="text-neut font-semibold">Engine data is {days} days old</span>
        {' — '}latest settle{' '}
        <span className="text-text-primary tabular">
          {new Date(t).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })}
        </span>
        {isTail
          ? '. That row is an hourly-OHLCV tail ESTIMATE (settle-tail on); the desk OHLCV export has not captured anything newer.'
          : '. The regime engine is scoring the most recent baked daily settle; the live desk feed is not visible from this host.'}
      </span>
    </div>
  );
}

// ── KPI strip ───────────────────────────────────────────────────────────────
// Premium hero strip across the top — quick orientation: regime, brent spot,
// front-month spread, BRT–WTI arb, geopolitics index. Pure presentational.

function KpiTile({
  label, value, sub, tone, icon: Icon, glow, spark, numeric, format,
}: {
  label: string;
  value: string;
  sub?: string;
  tone?: 'bull' | 'bear' | 'neut' | 'gold';
  icon?: any;
  glow?: boolean;
  /** Optional trailing daily series — renders an ambient sparkline. */
  spark?: number[];
  /** When set (with `format`), the value rolls smoothly on live updates. */
  numeric?: number | null;
  format?: (n: number) => string;
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
        {typeof numeric === 'number' && format ? <AnimatedNumber value={numeric} format={format} /> : value}
      </div>
      {sub && <div className="text-[9.5px] font-mono text-text-tertiary tabular mt-1 relative z-10">{sub}</div>}
      {spark && spark.length > 2 && (
        <div aria-hidden className="absolute right-1.5 bottom-1 opacity-50 group-hover:opacity-80 transition-opacity pointer-events-none">
          <Sparkline data={spark} width={92} height={26} />
        </div>
      )}
    </motion.div>
  );
}

function KpiStrip({
  rec, all, history,
}: {
  rec: Recommendation | null;
  all: any;
  history?: any;
}) {
  const prices = all?.prices ?? {};
  const curve = all?.curve;
  const fundamentals = all?.fundamentals;

  // Trailing 30-session sparkline series from the 90d daily history feed.
  const brentSpark = useMemo(
    () => ((history?.brent ?? []) as any[])
      .map(c => c?.c)
      .filter((x): x is number => typeof x === 'number')
      .slice(-30),
    [history],
  );
  const arbSpark = useMemo(() => {
    const b = (history?.brent ?? []) as any[];
    const w = (history?.wti ?? []) as any[];
    if (!b.length || !w.length) return [];
    const wByT = new Map(w.map(c => [c?.t, c?.c]));
    return b
      .map(c => (typeof c?.c === 'number' && typeof wByT.get(c?.t) === 'number' ? c.c - wByT.get(c.t) : null))
      .filter((x): x is number => typeof x === 'number')
      .slice(-30);
  }, [history]);

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
        spark={brentSpark}
        numeric={brent}
        format={n => `$${n.toFixed(2)}`}
      />
      <KpiTile
        label="M1 – M2"
        value={m1m2 !== null ? `${m1m2 >= 0 ? '+' : ''}$${m1m2.toFixed(2)}` : '—'}
        sub={m1m2 !== null ? (m1m2 > 0 ? 'backwardation' : 'contango') : 'front-end curve'}
        tone={m1m2 !== null ? (m1m2 > 0 ? 'bull' : 'bear') : undefined}
        icon={Flame}
        numeric={m1m2}
        format={n => `${n >= 0 ? '+' : ''}$${n.toFixed(2)}`}
      />
      <KpiTile
        label="BRT – WTI"
        value={brtWti !== null ? `$${brtWti.toFixed(2)}` : '—'}
        sub="atlantic arb"
        tone="neut"
        icon={Wind}
        spark={arbSpark}
        numeric={brtWti}
        format={n => `$${n.toFixed(2)}`}
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
  history,
  tradeIdea,
  onNavigate,
}: {
  all: any;
  history?: any;
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
        <KpiStrip rec={rec ?? null} all={all} history={history} />
      </motion.div>

      {/* >4 days covers weekends + a holiday without crying wolf. */}
      {rec?.as_of && staleDaysOf(rec.as_of) > 4 && (
        <motion.div variants={fadeUp}>
          <StaleFeedBanner asOf={rec.as_of} days={staleDaysOf(rec.as_of)} asOfSource={rec.as_of_source} />
        </motion.div>
      )}

      {/* Mission-control hero — the engine's directive, full width. */}
      <motion.div variants={fadeUp}>
        <HeroPick rec={rec ?? null} lastSuccess={recLastUpdated} fetchError={recError} />
      </motion.div>

      {/* Main desk grid — trading flow (positions → decomposition) takes the
          wide left column; context (brief, risk, geo calc) stacks on the
          right. Collapses to a single column below xl. */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4 items-start">
        <div className="xl:col-span-2 space-y-4 min-w-0">
          <motion.div variants={fadeUp}>
            <OpenPositionsStrip
              positions={pos}
              onNavigate={onNavigate}
              lastSuccess={posLastUpdated}
              fetchError={posError}
            />
          </motion.div>

          <motion.div variants={fadeUp}>
            <PriceDecomposition fairValue={fv} signal={signal} curve={curve} />
          </motion.div>
        </div>

        <div className="space-y-4 min-w-0">
          <motion.div variants={fadeUp}>
            <MorningBrief idea={tradeIdea} />
          </motion.div>

          <motion.div variants={fadeUp}>
            <RiskPanel positions={pos} correlations={correlations} />
          </motion.div>

          <motion.div variants={fadeUp}>
            <GeoRiskCalculator
              defaultSpareCapacity={spareCapacity}
              brentPrice={brentSpot}
            />
          </motion.div>
        </div>
      </div>

      <motion.div variants={fadeUp}>
        <IndicatorDrillPanel
          signal={signal}
          onPick={(asset, indicator) => setDrill({ asset, indicator })}
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
