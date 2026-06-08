import { useCallback, useMemo, useState } from 'react';
import clsx from 'clsx';
import { Panel } from '@/components/ui/Panel';
import { Chip } from '@/components/ui/Chip';
import { Stat } from '@/components/ui/Stat';
import { SkeletonRows } from '@/components/ui/Skeleton';
import { Activity, Play, TrendingUp, TrendingDown, BarChart3, Info } from 'lucide-react';
import { api } from '@/lib/api';
import { usePolling } from '@/lib/hooks';

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

type RegimeState = {
  available: boolean;
  regime?: string;
  regime_color?: string;
  m1_m12?: number;
  days_in_regime?: number;
  as_of?: string;
  drivers?: { brent_close: number; realised_vol_20d: number; brent_ret_5d: number };
  regime_thresholds?: Record<string, string>;
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
  r2_train: number;
  r2_oos: number | null;
  band_hit_rate: number | null;
  n_train: number;
  drivers: { feature: string; coef: number }[];
};

type Recommendation = {
  available: boolean;
  regime?: string;
  as_of?: string;
  top?: RankedOpp;
  ranked?: RankedOpp[];
  method?: string;
};


function regimeChipTone(regime?: string): 'bull' | 'bear' | 'neut' {
  if (!regime) return 'neut';
  if (regime.includes('BACKWARDATION')) return 'bull';
  if (regime.includes('CONTANGO'))      return 'bear';
  return 'neut';
}


function OppRow({ opp, rank, onPush }: {
  opp: RankedOpp;
  rank: number;
  onPush?: (opp: RankedOpp) => void;
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
      <div className="text-right">
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
          `Model: Ridge, OOS R²=${opp.r2_oos?.toFixed(2) ?? '—'}, regime band ${opp.band_low.toFixed(1)}–${opp.band_high.toFixed(1)}`,
          `Top drivers: ${opp.drivers.slice(0, 3).map(d => d.feature).join(', ')}`,
        ],
        key_risk:     `Mean-reversion not guaranteed in ${regime?.regime?.replace(/_/g, ' ') ?? 'current regime'}`,
        time_horizon: '1-2 weeks',
        morning_brief:
          `- Spread: ${opp.label}\n` +
          `- Current vs fair: ${opp.current.toFixed(2)} → ${opp.fair_value.toFixed(2)} (band ${opp.band_low.toFixed(1)}–${opp.band_high.toFixed(1)})\n` +
          `- z-score: ${opp.z_score.toFixed(2)}σ in ${regime?.regime?.replace(/_/g, ' ') ?? 'current regime'}\n` +
          `- Model: Ridge, OOS R²=${opp.r2_oos?.toFixed(2) ?? '—'}, ${opp.n_train} training obs\n` +
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

  const regimeLabel = (regime.regime ?? '').replace(/_/g, ' ');
  const chipTone = regimeChipTone(regime.regime);
  const top = rec.top;
  const ranked = rec.ranked ?? [];

  // Pull this cell's training stats from the backtest report
  const cellStat = (() => {
    if (!backtest?.cells || !top) return null;
    return backtest.cells[`${top.spread}__${regime.regime}`] || null;
  })();

  return (
    <Panel
      title="Regime Pick · Phase 2 Engine"
      subtitle={`Trained ≤ 2026-03-31 · tested Apr-May 2026 · Ridge + Quantile bands`}
      accent={chipTone as any}
      source="signal_engine"
      sourceNote="4-regime curve classifier + per-regime Ridge fair value + Quantile p10/p90 confidence band. Ranks 3 spreads by |z-score| × R²_oos × √(n_train/100). #1 is surfaced for push-to-paper."
      right={
        <div className="flex items-center gap-2">
          <Chip tone={chipTone as any}>{regimeLabel}</Chip>
          <button
            onClick={() => setShowAll(s => !s)}
            className="text-[10px] font-mono uppercase tracking-widest text-text-tertiary hover:text-gold px-2 py-1 rounded hover:bg-bg-hover"
          >
            {showAll ? 'collapse' : `show all ${ranked.length}`}
          </button>
        </div>
      }
    >
      {/* Regime context strip */}
      <div className="grid grid-cols-4 gap-3 mb-4">
        <Stat label="M1-M12"        value={`$${regime.m1_m12?.toFixed(2)}`}    tone={chipTone as any} />
        <Stat label="Days in regime" value={`${regime.days_in_regime ?? '—'}d`} />
        <Stat label="Brent C1"      value={`$${regime.drivers?.brent_close?.toFixed(2)}`} />
        <Stat label="Realised vol"   value={`${((regime.drivers?.realised_vol_20d ?? 0) * 100).toFixed(0)}%`} sub="20-day annualised" />
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
            </div>
            <div className="flex items-center gap-3">
              {pushFlash === 'ok'  && <span className="text-bull text-[10px] font-mono">✓ pushed</span>}
              {pushFlash === 'err' && <span className="text-bear text-[10px] font-mono">✕ {pushErr}</span>}
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

          {/* Drivers */}
          {top.drivers?.length > 0 && (
            <div className="mt-3 pt-3 border-t border-border/40">
              <div className="text-[10px] font-mono uppercase tracking-widest text-text-muted mb-1.5">
                Top drivers in this regime
              </div>
              <div className="flex flex-wrap gap-2">
                {top.drivers.slice(0, 5).map(d => (
                  <span key={d.feature}
                        className="px-2 py-0.5 rounded text-[10px] font-mono bg-bg-card/60 border border-border/40">
                    {d.feature}
                    <span className={d.coef >= 0 ? 'text-bull ml-1' : 'text-bear ml-1'}>
                      {d.coef >= 0 ? '+' : ''}{d.coef.toFixed(3)}
                    </span>
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {top && top.direction === 'NEUTRAL' && (
        <div className="p-4 bg-bg-card/40 rounded text-center">
          <Info className="w-4 h-4 mx-auto mb-2 text-text-tertiary" />
          <div className="text-[11px] font-mono text-text-tertiary">
            All 3 spreads currently inside their 80% confidence band — no high-conviction opportunity. Wait for a deviation.
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
            <OppRow key={opp.spread} opp={opp} rank={i + 1} onPush={i === 0 ? handlePush : undefined} />
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
    </Panel>
  );
}
