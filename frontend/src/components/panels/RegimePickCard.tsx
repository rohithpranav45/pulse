import { useCallback, useMemo, useState } from 'react';
import clsx from 'clsx';
import { Panel } from '@/components/ui/Panel';
import { Chip } from '@/components/ui/Chip';
import { Stat } from '@/components/ui/Stat';
import { SkeletonRows } from '@/components/ui/Skeleton';
import { Activity, Play, TrendingUp, TrendingDown, BarChart3, Info, Search } from 'lucide-react';
import { api } from '@/lib/api';
import { usePolling } from '@/lib/hooks';
import { RegimeDrillModal } from '@/components/panels/RegimeDrillModal';

/**
 * Phase 2 class-demo card — surfaces the top regime-conditional opportunity
 * directly on the Paper Trading tab.
 *
 *   Current regime: EXTREME BACKWARDATION (14d in regime)
 *   Top trade: Brent M3-M6 SELL @ $7.09 → fair $6.32 (band 4.49-6.78)
 *   z = +2.56, R² OOS = 0.86, confidence 74%
 *   Top drivers: m1_m12, fly_lag1, m1_m2_lag1
 *   [Push to Paper]   [Show all 3]
 *
 * Models trained on data ≤ 2026-03-31, validated on April-May 2026.
 */

type AxisReading = { bucket: string; value: number | null };

type RegimeState = {
  available: boolean;
  regime?: string;        // composite e.g. "BACK/LOW/STRESSED" or pooled "BACK"
  regime_mode?: 'composite' | 'pooled';
  gated_blend?: boolean;  // Phase 2.6 production rule active?
  regime_composite?: string;
  regime_pooled?: string;
  regime_legacy?: string; // 4-bucket legacy label
  regime_color?: string;
  days_in_regime?: number;
  as_of?: string;
  axes?: {
    curve:     AxisReading;
    inventory: AxisReading;
    vol:       AxisReading;
  };
  drivers?: {
    brent_close:      number;
    wti_close:        number | null;
    realised_vol_20d: number;
    brent_ret_5d:     number;
    inv_vs_5yr_pct:   number | null;
    m1_m12:           number;
  };
  axis_thresholds?: Record<string, Record<string, string>>;
  axis_buckets?:    Record<string, string[]>;
};

type RankedOpp = {
  spread: string;
  label: string;
  description: string;
  direction: 'BUY' | 'SELL' | 'NEUTRAL';
  current: number;
  fair_value: number;
  band_low: number;
  band_mid: number;
  band_high: number;
  deviation: number;
  z_score: number;
  inside_band: boolean;
  target: number | null;
  stop: number | null;
  confidence: number;
  r2_train: number | null;
  r2_oos: number | null;
  band_hit_rate: number | null;
  n_train: number;
  drivers: { feature: string; coef: number }[];
  // Model competition (Phase 2.8.1 — boosters added)
  winner_model?:
    | 'Ridge' | 'Lasso' | 'ElasticNet' | 'Huber'
    | 'XGBoost' | 'LightGBM' | 'CatBoost'
    | 'Rolling252dZ';
  active_features?: number | null;
  total_features?: number | null;
  competition?: Record<string, number | null>;
  // Phase 2.6 gated blend — which leg fired for this spread
  recommendation_source?: 'regime' | 'baseline';
  gate?: 'pass' | 'fail' | 'no_pooled_cell' | 'no_baseline' | 'off';
  regime?: string;
  // Phase 2.7 sizing — per-spread notional scale + active mode
  notional_scale?: number;
  sizing_mode?: 'full' | 'half' | 'kelly';
};

type GatedSummary = {
  enabled: boolean;
  regime: string;            // gate criterion: e.g. "BACK"
  winners: string[];         // e.g. ["Huber", "Lasso"]
  z_threshold: number;
  n_regime: number;
  n_baseline: number;
  method: string;
  // Phase 2.7 sizing context
  size_mode?: 'full' | 'half' | 'kelly';
  kelly_map?: Record<string, number> | null;
  sizing_per_spread?: Record<string, { source: string; notional_scale: number }>;
};

type Recommendation = {
  available: boolean;
  regime?: string;
  regime_mode?: 'composite' | 'pooled';
  gated_blend?: boolean;
  gated_summary?: GatedSummary | null;
  recommendation_source?: 'regime' | 'baseline' | null;
  as_of?: string;
  n_eligible?: number;
  n_universe?: number;
  excluded_spreads?: string[];
  // Phase 2.9.1 tuned exit rule — the EXIT logic, surfaced so the mentor sees
  // how trades close (TP/SL/time-stop) and which spreads are dropped, not just
  // the entry signal.
  tuned_rule?: {
    entry_z: number;
    tp_frac: number;
    sl_mult: number;
    max_hold_days: number;
    excluded_spreads: string[];
    note?: string;
  } | null;
  top?: RankedOpp;
  ranked?: RankedOpp[];
  method?: string;
};


function regimeChipTone(regime?: string): 'bull' | 'bear' | 'neut' {
  if (!regime) return 'neut';
  // Composite labels start with the curve axis: "BACK/…" | "CONTANGO/…" | "NEUTRAL/…"
  const curve = regime.split('/', 1)[0];
  if (curve === 'BACK' || regime.includes('BACKWARDATION')) return 'bull';
  if (curve === 'CONTANGO')                                 return 'bear';
  return 'neut';
}


function SourceBadge({ source, gate }: { source?: string; gate?: string }) {
  if (!source) return null;
  const isRegime = source === 'regime';
  const tone = isRegime ? 'gold' : 'neut';
  const label = isRegime ? 'REGIME' : 'BASELINE';
  const tip = isRegime
    ? `Regime engine fired (gate=${gate ?? 'pass'})`
    : `Fell through to 252d rolling-z baseline (gate=${gate ?? 'fail'})`;
  return (
    <span title={tip}>
      <Chip tone={tone as any}>{label}</Chip>
    </span>
  );
}


function OppRow({ opp, rank, onPush, onDrill }: {
  opp: RankedOpp;
  rank: number;
  onPush?: (opp: RankedOpp) => void;
  onDrill?: (opp: RankedOpp) => void;
}) {
  const dirTone =
    opp.direction === 'BUY'  ? 'bull' :
    opp.direction === 'SELL' ? 'bear' : 'neut';

  const Icon =
    opp.direction === 'BUY'  ? TrendingUp :
    opp.direction === 'SELL' ? TrendingDown : Activity;

  return (
    <div className={clsx(
      'grid grid-cols-[28px_1fr_120px_90px_60px_72px_72px] gap-3 items-center py-2 px-2 border-b border-border/30',
      rank === 1 && 'bg-bg-card/50',
    )}>
      <span className={clsx('text-[10px] font-mono uppercase tracking-widest tabular',
        rank === 1 ? 'text-gold font-bold' : 'text-text-muted'
      )}>
        #{rank}
      </span>
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <Icon className={clsx('w-3.5 h-3.5 flex-shrink-0',
            dirTone === 'bull' && 'text-bull',
            dirTone === 'bear' && 'text-bear',
            dirTone === 'neut' && 'text-text-tertiary',
          )} />
          <span className="text-[11.5px] font-mono font-semibold text-text-primary truncate">
            {opp.label}
          </span>
          <Chip tone={dirTone as any}>{opp.direction}</Chip>
          {opp.recommendation_source && (
            <SourceBadge source={opp.recommendation_source} gate={opp.gate} />
          )}
        </div>
        <div className="text-[10px] font-mono text-text-tertiary mt-0.5 truncate" title={opp.description}>
          {opp.description}
        </div>
      </div>
      <div className="text-right">
        <div className="text-[10px] font-mono text-text-muted uppercase tracking-widest">Cur / Fair</div>
        <div className="text-[11.5px] font-mono tabular text-text-secondary">
          {opp.current.toFixed(2)} <span className="text-text-muted">/</span> {opp.fair_value.toFixed(2)}
        </div>
        <div className="text-[9px] font-mono text-text-muted tabular">
          band {opp.band_low.toFixed(1)}–{opp.band_high.toFixed(1)}
        </div>
      </div>
      <div className="text-right">
        <div className="text-[10px] font-mono text-text-muted uppercase tracking-widest">z</div>
        <div className={clsx('text-[14px] font-mono font-bold tabular',
          opp.z_score > 1.5 ? 'text-bear' :
          opp.z_score < -1.5 ? 'text-bull' : 'text-neut',
        )}>
          {opp.z_score >= 0 ? '+' : ''}{opp.z_score.toFixed(2)}
        </div>
      </div>
      <div className="text-right">
        <div className="text-[10px] font-mono text-text-muted uppercase tracking-widest">Conf</div>
        <div className="text-[11.5px] font-mono tabular text-text-primary">
          {(opp.confidence * 100).toFixed(0)}%
        </div>
      </div>
      <div className="text-right">
        <div className="text-[10px] font-mono text-text-muted uppercase tracking-widest">R²·oos</div>
        <div className="text-[11.5px] font-mono tabular text-text-tertiary">
          {opp.r2_oos !== null && opp.r2_oos !== undefined ? opp.r2_oos.toFixed(2) : '—'}
        </div>
      </div>
      <div className="text-right flex items-center justify-end gap-1">
        {onDrill && (
          <button
            onClick={() => onDrill(opp)}
            className="flex items-center gap-1 px-2 py-1 rounded text-[10px] font-mono uppercase tracking-widest text-text-tertiary hover:text-gold hover:bg-bg-hover transition-colors"
            title={`Evidence for ${opp.label}`}
          >
            <Search className="w-3 h-3" />
          </button>
        )}
        {onPush && rank === 1 && opp.direction !== 'NEUTRAL' && (
          <button
            onClick={() => onPush(opp)}
            className="flex items-center gap-1 px-2 py-1 rounded text-[10px] font-mono uppercase tracking-widest bg-gold/15 hover:bg-gold/30 text-gold transition-colors"
            title={`Push ${opp.direction} ${opp.label} to paper`}
          >
            <Play className="w-3 h-3" />
            Push
          </button>
        )}
      </div>
    </div>
  );
}


export function RegimePickCard() {
  const { data: regime }   = usePolling<RegimeState>(api.regime, 60_000);
  const { data: rec }      = usePolling<Recommendation>(api.regimeRecommendation, 60_000);
  const { data: backtest } = usePolling<any>(api.regimeBacktest, 300_000);
  const [showAll, setShowAll]   = useState(false);
  const [pushBusy, setPushBusy] = useState(false);
  const [pushFlash, setPushFlash] = useState<'ok' | 'err' | null>(null);
  const [pushErr, setPushErr]   = useState<string | null>(null);
  const [drillFor, setDrillFor] = useState<RankedOpp | null>(null);
  const openDrill = useCallback((opp: RankedOpp) => setDrillFor(opp), []);
  const closeDrill = useCallback(() => setDrillFor(null), []);

  const handlePush = useCallback(async (opp: RankedOpp) => {
    setPushBusy(true); setPushFlash(null); setPushErr(null);
    try {
      // Push as the spread itself (asset key = opp.spread).
      // Paper book MTMs by computing the spread value from /Data each minute,
      // so entry/target/stop are all in the same units (spread $).
      const approxDir = opp.direction === 'BUY' ? 'LONG' : 'SHORT';
      const idea = {
        asset:         opp.spread,            // e.g. "brent_m3_m6"
        direction:     approxDir,
        live_price:    opp.current,
        target_level:  opp.target,
        stop_level:    opp.stop,
        conviction:    opp.confidence > 0.6 ? 'HIGH' : opp.confidence > 0.3 ? 'MODERATE' : 'LOW',
        entry_thesis: [
          `${opp.label}: ${opp.direction} — current ${opp.current.toFixed(2)} vs fair ${opp.fair_value.toFixed(2)} (z=${opp.z_score.toFixed(2)}σ)`,
          `Model: ${opp.winner_model ?? 'Ridge'}, OOS R²=${opp.r2_oos?.toFixed(2) ?? '—'}, regime band ${opp.band_low.toFixed(1)}–${opp.band_high.toFixed(1)}`,
          `Top drivers: ${opp.drivers.slice(0, 3).map(d => d.feature).join(', ')}`,
        ],
        key_risk:     `Mean-reversion not guaranteed in ${regime?.regime ?? 'current regime'}`,
        time_horizon: '1-2 weeks',
        morning_brief:
          `- Spread: ${opp.label}\n` +
          `- Current vs fair: ${opp.current.toFixed(2)} → ${opp.fair_value.toFixed(2)} (band ${opp.band_low.toFixed(1)}–${opp.band_high.toFixed(1)})\n` +
          `- z-score: ${opp.z_score.toFixed(2)}σ in regime ${regime?.regime ?? '—'}\n` +
          `- Model: ${opp.winner_model ?? 'Ridge'}, OOS R²=${opp.r2_oos?.toFixed(2) ?? '—'}, ${opp.n_train} training obs\n` +
          `- Bias: ${opp.direction} on mean-reversion to regime fair value`,
        source: 'regime_engine',
      };
      const out = await api.paperPush({ idea, size: 1.0, source: 'regime_engine' });
      if (out?.ok) {
        setPushFlash('ok');
        setTimeout(() => setPushFlash(null), 3000);
      } else {
        setPushFlash('err');
        setPushErr(out?.error || 'push failed');
        setTimeout(() => setPushFlash(null), 5000);
      }
    } catch (e: any) {
      setPushFlash('err');
      setPushErr(e?.message || String(e));
      setTimeout(() => setPushFlash(null), 5000);
    } finally {
      setPushBusy(false);
    }
  }, [regime]);

  if (!regime || !regime.available || !rec || !rec.available) {
    return <Panel title="Regime Pick · Phase 2 Engine" source="signal_engine"><SkeletonRows rows={4} /></Panel>;
  }

  const regimeLabel = regime.regime ?? '—';
  const chipTone = regimeChipTone(regime.regime);
  const top = rec.top;
  const ranked = rec.ranked ?? [];

  // Phase 2.6 — show active mode + which leg sourced #1
  const gated      = Boolean(rec.gated_blend);
  const activeMode = rec.regime_mode ?? regime.regime_mode ?? 'composite';
  const topSource  = rec.recommendation_source ?? top?.recommendation_source ?? null;
  const summary    = rec.gated_summary ?? null;

  // Pull this cell's training stats from the backtest report
  const cellStat = (() => {
    if (!backtest?.cells || !top) return null;
    return backtest.cells[`${top.spread}__${regime.regime}`] || null;
  })();

  const axes = regime.axes;
  const eligible = rec.n_eligible ?? ranked.length;
  const universe = rec.n_universe ?? ranked.length;

  return (
    <Panel
      title="Regime Pick · Phase 2 Engine"
      subtitle={
        gated
          ? `Phase 2.6 GATED BLEND · pooled regime on BACK + {Lasso/Huber} + |z|≥${summary?.z_threshold ?? 0.5}σ · else 252d rolling-z baseline`
          : (activeMode === 'pooled'
              ? `Pooled curve-axis regime · 3 cells/spread · 4-model competition`
              : `3-axis composite regime · 6 spreads × 27 cells · 4-model competition`)
      }
      accent={chipTone as any}
      source="signal_engine"
      sourceNote={
        gated
          ? `Phase 2.6 production rule: pooled engine fires only when regime_pooled='BACK' AND winner_model ∈ {Lasso, Huber} AND |z|≥0.5σ. All other (spread, day) pairs fall through to the regime-unaware 252-day rolling-z baseline. Walk-forward verifies the gate end-to-end before live trading.`
          : `3-axis composite regime (curve × inventory × vol) + per-cell {Ridge / Lasso / ElasticNet / Huber} competition + Quantile p10/p90 bands. Ranks 6 spreads (3 Brent + 3 WTI) by |z| × R²_oos × √(n_train/100). #1 is surfaced for push-to-paper.`
      }
      right={
        <div className="flex items-center gap-2">
          {gated && <Chip tone="gold">GATED BLEND</Chip>}
          {gated && summary?.size_mode && summary.size_mode !== 'full' && (
            <span title={`Phase 2.7: regime-leg notional sized by ${summary.size_mode}${summary.size_mode === 'kelly' ? ' (per-spread)' : ''}`}>
              <Chip tone="neut">{`SIZE ${summary.size_mode.toUpperCase()}`}</Chip>
            </span>
          )}
          {rec.tuned_rule && (
            <span title={`Phase 2.9.1 tuned exit rule (chosen via constrained win-rate sweep): take-profit ${Math.round(rec.tuned_rule.tp_frac * 100)}% of the way to fair value, stop at ${rec.tuned_rule.sl_mult}σ, ${rec.tuned_rule.max_hold_days}-trading-day time-stop. Dropped (PF<1 under TP/SL): ${(rec.tuned_rule.excluded_spreads || []).join(', ') || 'none'}. Lifts realised win rate 64%→83%.`}>
              <Chip tone="neut">{`EXIT TP ${Math.round(rec.tuned_rule.tp_frac * 100)}%·fair · ${rec.tuned_rule.sl_mult}σ · ${rec.tuned_rule.max_hold_days}d`}</Chip>
            </span>
          )}
          <Chip tone={chipTone as any}>{regimeLabel}</Chip>
          {gated && summary && (
            <span className="text-[10px] font-mono text-text-tertiary tabular" title={summary.method}>
              regime {summary.n_regime} / baseline {summary.n_baseline}
            </span>
          )}
          <span className="text-[10px] font-mono text-text-tertiary tabular">
            {eligible}/{universe} eligible
          </span>
          <button
            onClick={() => setShowAll(s => !s)}
            className="text-[10px] font-mono uppercase tracking-widest text-text-tertiary hover:text-gold px-2 py-1 rounded hover:bg-bg-hover"
          >
            {showAll ? 'collapse' : `show all ${ranked.length}`}
          </button>
        </div>
      }
    >
      {/* 3-axis regime context strip */}
      <div className="grid grid-cols-4 gap-3 mb-4">
        <Stat
          label="Curve"
          value={axes?.curve?.bucket ?? '—'}
          sub={axes?.curve?.value !== null && axes?.curve?.value !== undefined
                ? `M1-M12 $${axes.curve.value.toFixed(2)}` : undefined}
          tone={chipTone as any}
        />
        <Stat
          label="Inventory"
          value={axes?.inventory?.bucket ?? '—'}
          sub={axes?.inventory?.value !== null && axes?.inventory?.value !== undefined
                ? `${axes.inventory.value >= 0 ? '+' : ''}${axes.inventory.value.toFixed(1)}% vs 5y` : '5y backfill'}
          tone={axes?.inventory?.bucket === 'LOW' ? 'bull' : axes?.inventory?.bucket === 'HIGH' ? 'bear' : 'neut'}
        />
        <Stat
          label="Vol"
          value={axes?.vol?.bucket ?? '—'}
          sub={axes?.vol?.value !== null && axes?.vol?.value !== undefined
                ? `RV20 ${axes.vol.value.toFixed(0)}%` : undefined}
          tone={axes?.vol?.bucket === 'STRESSED' ? 'bear' : 'neut'}
        />
        <Stat
          label="Days in regime"
          value={`${regime.days_in_regime ?? '—'}d`}
          sub={regime.as_of ? `as of ${regime.as_of}` : undefined}
        />
      </div>

      {/* Top opportunity hero */}
      {top && top.direction !== 'NEUTRAL' && (
        <div className="border border-gold/30 bg-gold/5 rounded-md p-3 mb-3">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <span className="text-[10px] font-mono uppercase tracking-widest text-gold">
                #1 Pick — most profitable
              </span>
              <Chip tone={top.direction === 'BUY' ? 'bull' : 'bear' as any}>
                {top.direction} {top.label}
              </Chip>
              {gated && topSource && (
                <SourceBadge source={topSource} gate={top.gate} />
              )}
            </div>
            <div className="flex items-center gap-3">
              {pushFlash === 'ok'  && <span className="text-bull text-[10px] font-mono">✓ pushed</span>}
              {pushFlash === 'err' && <span className="text-bear text-[10px] font-mono">✕ {pushErr}</span>}
              <button
                onClick={() => openDrill(top)}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded font-mono uppercase tracking-widest text-[11px] font-bold border border-gold/40 text-gold hover:bg-gold/15 transition-colors"
                title="See the model's evidence — scatter + historical analogs"
              >
                <Search className="w-3 h-3" />
                Evidence
              </button>
              <button
                onClick={() => handlePush(top)}
                disabled={pushBusy}
                className={clsx(
                  'flex items-center gap-1.5 px-3 py-1.5 rounded font-mono uppercase tracking-widest text-[11px] font-bold transition-colors',
                  pushBusy ? 'bg-gold/30 text-bg cursor-wait' : 'bg-gold hover:bg-gold-bright text-bg',
                )}
              >
                <Play className="w-3 h-3" />
                {pushBusy ? 'pushing…' : 'Push to Paper'}
              </button>
            </div>
          </div>

          <div className="grid grid-cols-5 gap-3 mt-3">
            <Stat label="Current"     value={`$${top.current.toFixed(2)}`} />
            <Stat label="Fair value"  value={`$${top.fair_value.toFixed(2)}`} tone="gold" />
            <Stat label="80% band"    value={`${top.band_low.toFixed(2)} – ${top.band_high.toFixed(2)}`} />
            <Stat label="Target"      value={top.target !== null ? `$${top.target.toFixed(2)}` : '—'} tone="bull" />
            <Stat label="Stop"        value={top.stop   !== null ? `$${top.stop.toFixed(2)}`   : '—'} tone="bear" />
          </div>

          <div className="grid grid-cols-4 gap-3 mt-3 pt-3 border-t border-border/40">
            <Stat label="z-score"
                  value={`${top.z_score >= 0 ? '+' : ''}${top.z_score.toFixed(2)}σ`}
                  tone={top.z_score > 1.5 ? 'bear' : top.z_score < -1.5 ? 'bull' : 'neut'} />
            <Stat label="Confidence"  value={`${(top.confidence * 100).toFixed(0)}%`} />
            <Stat label="R²·OOS"      value={top.r2_oos !== null ? top.r2_oos.toFixed(2) : '—'} sub="Apr–May test" />
            <Stat label="Band hit"    value={top.band_hit_rate !== null ? `${(top.band_hit_rate * 100).toFixed(0)}%` : '—'} sub="Apr–May test" />
          </div>

          {/* Model winner + competition */}
          {top.winner_model && (
            <div className="mt-3 pt-3 border-t border-border/40">
              <div className="flex items-center justify-between mb-2">
                <div className="text-[10px] font-mono uppercase tracking-widest text-text-muted">
                  Winning model
                </div>
                <div className="flex items-center gap-2">
                  <Chip tone="gold">{top.winner_model}</Chip>
                  {top.active_features !== undefined && top.total_features !== undefined && (
                    <span className="text-[10px] font-mono text-text-tertiary">
                      {top.active_features}/{top.total_features} features active
                    </span>
                  )}
                </div>
              </div>
              {top.competition && Object.keys(top.competition).length > 0 && (
                <div className={clsx(
                  'gap-1.5 mb-2 grid',
                  Object.keys(top.competition).length > 4 ? 'grid-cols-4 md:grid-cols-7' : 'grid-cols-4',
                )}>
                  {(['Ridge', 'Lasso', 'ElasticNet', 'Huber',
                     'XGBoost', 'LightGBM', 'CatBoost'] as const)
                    .filter(name => top.competition && name in top.competition)
                    .map(name => {
                    const score = top.competition?.[name];
                    const isWinner = name === top.winner_model;
                    const display = (score === null || score === undefined) ? '—' :
                                    `${score >= 0 ? '+' : ''}${score.toFixed(2)}`;
                    return (
                      <div key={name} className={clsx(
                        'px-2 py-1 rounded text-center border',
                        isWinner ? 'border-gold/50 bg-gold/10' : 'border-border/40 bg-bg-card/40',
                      )}>
                        <div className={clsx(
                          'text-[9px] font-mono uppercase tracking-widest',
                          isWinner ? 'text-gold' : 'text-text-muted',
                        )}>
                          {name}{isWinner && ' ✓'}
                        </div>
                        <div className={clsx(
                          'text-[11px] font-mono tabular font-semibold',
                          isWinner ? 'text-text-primary' :
                          (score !== null && score !== undefined && score > 0) ? 'text-text-secondary' : 'text-text-muted',
                        )}>
                          {display}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
              <div className="text-[9px] font-mono text-text-muted text-center">
                CV R² across 4 candidates · winner picked by max mean R² (sparsity tiebreak)
              </div>
            </div>
          )}

          {/* Drivers */}
          {top.drivers?.length > 0 && (
            <div className="mt-3 pt-3 border-t border-border/40">
              <div className="text-[10px] font-mono uppercase tracking-widest text-text-muted mb-1.5">
                Top drivers in this regime (winner-model coefficients)
              </div>
              <div className="flex flex-wrap gap-2">
                {top.drivers.slice(0, 5).map(d => {
                  const isActive = Math.abs(d.coef) > 0.001;
                  return (
                    <span key={d.feature}
                          className={clsx(
                            'px-2 py-0.5 rounded text-[10px] font-mono border',
                            isActive ? 'bg-bg-card/60 border-border/40' : 'bg-bg-elev/40 border-border/20 text-text-muted',
                          )}>
                      {d.feature}
                      <span className={clsx(
                        'ml-1',
                        !isActive ? 'text-text-muted' : d.coef >= 0 ? 'text-bull' : 'text-bear',
                      )}>
                        {d.coef >= 0 ? '+' : ''}{d.coef.toFixed(3)}
                      </span>
                    </span>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      )}

      {top && top.direction === 'NEUTRAL' && (
        <div className="p-4 bg-bg-card/40 rounded text-center">
          <Info className="w-4 h-4 mx-auto mb-2 text-text-tertiary" />
          <div className="text-[11px] font-mono text-text-tertiary">
            All eligible spreads currently inside their 80% confidence band — no high-conviction opportunity. Wait for a deviation.
          </div>
        </div>
      )}

      {/* All ranked rows (collapsed by default) */}
      {showAll && ranked.length > 0 && (
        <div className="mt-3 pt-3 border-t border-border/40">
          <div className="text-[10px] font-mono uppercase tracking-widest text-text-muted mb-2">
            All {ranked.length} ranked
          </div>
          <div className="grid grid-cols-[28px_1fr_120px_90px_60px_72px_72px] gap-3 items-center text-[9px] font-mono uppercase tracking-widest text-text-muted border-b border-border pb-1">
            <span>#</span>
            <span>Spread</span>
            <span className="text-right">Cur / Fair / Band</span>
            <span className="text-right">z</span>
            <span className="text-right">Conf</span>
            <span className="text-right">R² OOS</span>
            <span></span>
          </div>
          {ranked.map((opp, i) => (
            <OppRow key={opp.spread} opp={opp} rank={i + 1}
                    onPush={i === 0 ? handlePush : undefined}
                    onDrill={openDrill} />
          ))}
        </div>
      )}

      {/* Method footer */}
      <div className="mt-3 pt-3 border-t border-border/40 flex items-center gap-2 text-[10px] font-mono text-text-muted">
        <BarChart3 className="w-3 h-3" />
        <span>
          {rec.method}
          {backtest?.n_train && backtest?.n_test &&
            ` · ${backtest.n_train} train / ${backtest.n_test} test rows · ${Object.keys(backtest.cells ?? {}).length} (spread × regime) cells`}
        </span>
      </div>

      <RegimeDrillModal
        open={drillFor !== null}
        onClose={closeDrill}
        spread={drillFor?.spread ?? null}
        label={drillFor?.label}
        regime={regime.regime}
      />
    </Panel>
  );
}
