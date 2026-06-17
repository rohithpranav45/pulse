import { useMemo } from 'react';
import clsx from 'clsx';
import { Panel } from '@/components/ui/Panel';
import { SkeletonRows } from '@/components/ui/Skeleton';
import { api } from '@/lib/api';
import { usePolling } from '@/lib/hooks';

/**
 * Phase 4.H — calibration plot.
 *
 * Bins gated_trades.json by |z| and shows the fraction of trades that moved
 * favourably (fwd_pnl > 0) within the 20-day window. The title for each bar
 * reads exactly: "When the model said z=X, the spread reverted Y% of the
 * time in 20 days (n trades)." which is the single sanity check a trader
 * wants before sizing.
 */

type Bin = {
  z_lo: number;
  z_hi: number | null;
  n: number;
  reverted_frac: number;
  mean_fwd_pnl: number;
};

type Calibration = {
  available: boolean;
  error?: string;
  include?: 'pass' | 'all';
  horizon_days?: number;
  n_total?: number;
  overall_reverted?: number;
  bins?: Bin[];
  source?: string;
};

function binLabel(b: Bin): string {
  const lo = b.z_lo.toFixed(1);
  if (b.z_hi == null) return `|z| ≥ ${lo}`;
  return `|z| ${lo}–${b.z_hi.toFixed(1)}`;
}

function binCenter(b: Bin): string {
  if (b.z_hi == null) return `${b.z_lo.toFixed(1)}+`;
  const mid = (b.z_lo + b.z_hi) / 2;
  return mid.toFixed(2);
}

export function CalibrationPanel() {
  const { data, lastUpdated, error } = usePolling<Calibration>(
    () => api.regimeCalibration('pass') as Promise<Calibration>,
    600_000, // 10 min — the source file only changes when the walk-forward reruns
  );

  const bins = useMemo(() => data?.bins ?? [], [data]);
  const maxN = useMemo(() => bins.reduce((m, b) => Math.max(m, b.n), 0), [bins]);

  if (!data && !error) {
    return (
      <Panel
        title="Calibration · model conviction vs realised reversion"
        accent="gold"
        source="walkforward_report"
        staticMount
        lastSuccess={lastUpdated}
        fetchError={error}
      >
        <SkeletonRows rows={6} />
      </Panel>
    );
  }
  if (!data?.available) {
    return (
      <Panel
        title="Calibration · model conviction vs realised reversion"
        accent="gold"
        source="walkforward_report"
        staticMount
        lastSuccess={lastUpdated}
        fetchError={error}
      >
        <div className="text-[12px] font-mono text-text-tertiary px-3 py-6 text-center">
          {error
            ? `Calibration endpoint unreachable: ${(error as any)?.message ?? String(error)}`
            : data?.error ?? 'No calibration data available — run the walk-forward to populate gated_trades.json.'}
        </div>
      </Panel>
    );
  }

  const overall = data.overall_reverted ?? 0;
  const overallPct = (overall * 100).toFixed(0);

  return (
    <Panel
      title="Calibration · model conviction vs realised reversion"
      subtitle={`gate=pass trades · ${data.horizon_days ?? 20}d horizon · n=${data.n_total ?? 0}`}
      accent="gold"
      source="walkforward_report"
      staticMount
      lastSuccess={lastUpdated}
      fetchError={error}
    >
      <div className="text-[11px] font-mono text-text-tertiary leading-relaxed mb-3">
        Read each bar as: <span className="text-text-secondary">"When the model said z=X, the spread
        reverted Y% of the time in {data.horizon_days ?? 20} days (n trades)."</span> Higher
        |z| should reward higher revert frequency for a well-calibrated mean-reversion model.
        Baseline (any |z|): <span className="text-gold">{overallPct}%</span>.
      </div>

      <div className="space-y-2">
        {bins.map(b => {
          const pct = b.reverted_frac * 100;
          const tone: 'bull' | 'bear' | 'neut' = pct >= 60 ? 'bull' : pct >= 50 ? 'neut' : 'bear';
          const widthCol = `${Math.max(2, (b.n / Math.max(1, maxN)) * 100)}%`;
          return (
            <div
              key={`${b.z_lo}-${b.z_hi ?? 'inf'}`}
              className="grid grid-cols-[110px_60px_1fr_70px] items-center gap-3 text-[11px] font-mono tabular"
              title={`When the model said z=${binCenter(b)}, the spread reverted ${pct.toFixed(1)}% of the time in ${data.horizon_days ?? 20} days (n=${b.n} trades).`}
            >
              <span className="text-text-secondary whitespace-nowrap">{binLabel(b)}</span>
              <span
                className={clsx(
                  'text-right font-bold',
                  tone === 'bull' && 'text-bull',
                  tone === 'bear' && 'text-bear',
                  tone === 'neut' && 'text-neut',
                )}
              >
                {pct.toFixed(0)}%
              </span>
              <div className="relative h-3.5 bg-bg-card/40 rounded overflow-hidden border border-border/30">
                {/* 50% reference line */}
                <div
                  aria-hidden
                  className="absolute top-0 bottom-0 w-px bg-text-muted/40"
                  style={{ left: '50%' }}
                />
                {/* revert-fraction fill */}
                <div
                  className={clsx(
                    'absolute top-0 bottom-0 left-0',
                    tone === 'bull' && 'bg-bull/60',
                    tone === 'bear' && 'bg-bear/60',
                    tone === 'neut' && 'bg-neut/60',
                  )}
                  style={{ width: `${pct}%` }}
                />
                {/* sample-size width chip (right-aligned faint bar) */}
                <div
                  aria-hidden
                  className="absolute top-0 bottom-0 right-0 bg-text-muted/15"
                  style={{ width: widthCol }}
                  title={`n=${b.n} trades`}
                />
              </div>
              <span className="text-right text-text-tertiary tabular">n={b.n}</span>
            </div>
          );
        })}
      </div>

      <div className="mt-4 text-[10px] font-mono text-text-muted leading-relaxed">
        Reverted = forward 20-day move was favourable to the signal direction
        (<span className="text-text-tertiary">fwd_pnl &gt; 0</span> in the walk-forward tape).
        Gate=pass = trades the live engine would actually have fired (|z| ≥ engine threshold and
        regime/winner whitelist matched). Source: {data.source}.
      </div>
    </Panel>
  );
}
