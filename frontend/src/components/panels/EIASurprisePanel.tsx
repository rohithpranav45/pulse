import { useEffect, useState } from 'react';
import { Panel } from '@/components/ui/Panel';
import { Chip } from '@/components/ui/Chip';
import { SkeletonRows } from '@/components/ui/Skeleton';
import { ResponsiveContainer, ScatterChart, Scatter, XAxis, YAxis, CartesianGrid, Tooltip, ReferenceLine, Line } from 'recharts';
import { Clock, Calendar, TrendingUp, TrendingDown } from 'lucide-react';
import clsx from 'clsx';

type Release = {
  date: string;
  release_utc: string | null;
  actual_change: number;
  expected_change: number;
  surprise: number;
  bullish: boolean;
  brent_1h_return_pct: number | null;
  level: number;
};

type Regression = { slope: number; intercept: number; r2: number; n: number } | null;

function Countdown({ targetSeconds }: { targetSeconds: number }) {
  const [remaining, setRemaining] = useState(targetSeconds);
  useEffect(() => {
    setRemaining(targetSeconds);
    const t = setInterval(() => setRemaining(s => s - 1), 1000);
    return () => clearInterval(t);
  }, [targetSeconds]);

  if (remaining <= 0) {
    return <span className="text-bull font-mono">RELEASING NOW</span>;
  }
  const days = Math.floor(remaining / 86400);
  const hours = Math.floor((remaining % 86400) / 3600);
  const minutes = Math.floor((remaining % 3600) / 60);
  const seconds = remaining % 60;

  return (
    <span className="font-mono tabular text-text-primary text-lg font-semibold">
      {days > 0 && <span>{days}d </span>}
      <span>{hours.toString().padStart(2,'0')}h </span>
      <span>{minutes.toString().padStart(2,'0')}m </span>
      <span className="text-text-tertiary text-base">{seconds.toString().padStart(2,'0')}s</span>
    </span>
  );
}

export function EIASurprisePanel({ data }: { data: any }) {
  const releases: Release[] = data?.releases ?? [];
  const reg: Regression = data?.regression ?? null;
  const nextSeconds: number | null = data?.next_release_in_seconds ?? null;
  const nextUtc: string | null = data?.next_release_utc ?? null;

  if (releases.length === 0 && nextSeconds === null) {
    return (
      <Panel title="EIA Surprise Tracker" subtitle="Wed 10:30 EST · #1 weekly market mover">
        <SkeletonRows rows={6} />
      </Panel>
    );
  }

  const lastRelease = releases[releases.length - 1] ?? null;

  // Build scatter data for surprise→reaction visualization
  const scatterData = releases
    .filter(r => r.brent_1h_return_pct !== null)
    .map(r => ({
      x: r.surprise,
      y: r.brent_1h_return_pct as number,
      date: r.date,
    }));

  // Build regression line points
  const regLine: { x: number; y: number }[] = [];
  if (reg && scatterData.length >= 3) {
    const xs = scatterData.map(d => d.x);
    const xMin = Math.min(...xs);
    const xMax = Math.max(...xs);
    regLine.push(
      { x: xMin, y: reg.slope * xMin + reg.intercept },
      { x: xMax, y: reg.slope * xMax + reg.intercept },
    );
  }

  return (
    <Panel
      title="EIA Surprise Tracker"
      subtitle="Wed 10:30 EST · the #1 weekly market mover"
      accent="gold"
      right={
        lastRelease && (
          <Chip tone={lastRelease.bullish ? 'bull' : 'bear'}>
            LAST: {lastRelease.surprise >= 0 ? '+' : ''}{lastRelease.surprise.toFixed(0)} Mbbl
          </Chip>
        )
      }
    >
      {/* Countdown banner */}
      <div className="mb-4 p-3 bg-gradient-to-r from-bg-card/80 to-bg-card/40 rounded border border-border/60 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Clock className="w-5 h-5 text-gold" />
          <div>
            <div className="text-[10px] font-mono uppercase tracking-widest text-text-tertiary">Next EIA Release</div>
            {nextUtc && (
              <div className="text-[11px] font-mono text-text-secondary tabular">
                {new Date(nextUtc).toLocaleString('en-US', {
                  weekday: 'short', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false
                })} UTC
              </div>
            )}
          </div>
        </div>
        <div className="text-right">
          {nextSeconds !== null ? <Countdown targetSeconds={nextSeconds} /> : <span className="text-text-muted">—</span>}
        </div>
      </div>

      {/* Releases table */}
      <div className="mb-4">
        <div className="text-[9px] font-mono uppercase tracking-widest text-text-muted mb-2">
          Recent Releases · actual vs 4-wk MA expectation
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-[10.5px] font-mono tabular">
            <thead>
              <tr className="text-text-muted text-[9px] uppercase tracking-widest border-b border-border">
                <th className="text-left py-2 pl-1">Report Wk</th>
                <th className="text-right">Stocks (Mbbl)</th>
                <th className="text-right">Δ Actual</th>
                <th className="text-right">Δ Expected</th>
                <th className="text-right">Surprise</th>
                <th className="text-center">Bias</th>
                <th className="text-right pr-1">Brent +1h</th>
              </tr>
            </thead>
            <tbody>
              {[...releases].reverse().slice(0, 10).map((r, i) => {
                const tone = r.bullish ? 'text-bull' : 'text-bear';
                return (
                  <tr key={i} className="border-b border-border/30 hover:bg-bg-hover/30">
                    <td className="py-1.5 pl-1 text-text-secondary">{r.date.slice(5)}</td>
                    <td className="text-right text-text-tertiary">{Math.round(r.level).toLocaleString()}</td>
                    <td className={clsx('text-right', r.actual_change >= 0 ? 'text-bear' : 'text-bull')}>
                      {r.actual_change >= 0 ? '+' : ''}{r.actual_change.toFixed(0)}
                    </td>
                    <td className="text-right text-text-muted">
                      {r.expected_change >= 0 ? '+' : ''}{r.expected_change.toFixed(0)}
                    </td>
                    <td className={clsx('text-right font-semibold', tone)}>
                      {r.surprise >= 0 ? '+' : ''}{r.surprise.toFixed(0)}
                    </td>
                    <td className="text-center">
                      {r.bullish
                        ? <TrendingUp className="w-3.5 h-3.5 text-bull inline" />
                        : <TrendingDown className="w-3.5 h-3.5 text-bear inline" />}
                    </td>
                    <td className={clsx('text-right pr-1', r.brent_1h_return_pct === null ? 'text-text-muted' :
                                       (r.brent_1h_return_pct ?? 0) >= 0 ? 'text-bull' : 'text-bear')}>
                      {r.brent_1h_return_pct === null ? '—' :
                        `${r.brent_1h_return_pct >= 0 ? '+' : ''}${r.brent_1h_return_pct.toFixed(2)}%`}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <div className="text-[9px] font-mono text-text-muted mt-1 pl-1">
          ⬆ Surprise = Actual − Expected. Negative = bullish (more draw than expected).
        </div>
      </div>

      {/* Surprise → reaction scatter */}
      {scatterData.length >= 3 && (
        <div>
          <div className="text-[9px] font-mono uppercase tracking-widest text-text-muted mb-2">
            Surprise (Mbbl) → Brent +1h Reaction
          </div>
          <ResponsiveContainer width="100%" height={220}>
            <ScatterChart margin={{ top: 8, right: 12, bottom: 4, left: -8 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1c2745" />
              <XAxis
                type="number" dataKey="x" name="Surprise"
                tick={{ fontSize: 10, fill: '#6b809e', fontFamily: 'JetBrains Mono' }}
                axisLine={{ stroke: '#1c2745' }}
                label={{ value: 'Surprise (Mbbl)', position: 'insideBottom', offset: -2, fontSize: 9, fill: '#6b809e' }}
              />
              <YAxis
                type="number" dataKey="y" name="Brent +1h"
                tick={{ fontSize: 10, fill: '#6b809e', fontFamily: 'JetBrains Mono' }}
                axisLine={{ stroke: '#1c2745' }}
                unit="%"
                tickFormatter={(v: number) => v.toFixed(1)}
              />
              <ReferenceLine x={0} stroke="#3a4a6e" strokeWidth={1} />
              <ReferenceLine y={0} stroke="#3a4a6e" strokeWidth={1} />
              <Tooltip
                contentStyle={{ background: '#0f1729', border: '1px solid #1c2745', borderRadius: 6, fontSize: 11, fontFamily: 'JetBrains Mono' }}
                formatter={(value: any, name: string) => {
                  const v = Number(value);
                  return [
                    name === 'Surprise' ? `${v >= 0 ? '+' : ''}${v.toFixed(0)} Mbbl` : `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`,
                    name,
                  ];
                }}
                labelFormatter={(_, payload: any) => payload?.[0]?.payload?.date ?? ''}
              />
              {regLine.length === 2 && (
                <Scatter
                  name="Best Fit"
                  data={regLine}
                  line={{ stroke: '#d4af37', strokeWidth: 1.5, strokeDasharray: '4 4' }}
                  shape={() => <g />}
                  legendType="none"
                />
              )}
              <Scatter
                name="Releases"
                data={scatterData}
                fill="#22d3ee"
              />
            </ScatterChart>
          </ResponsiveContainer>
          {reg && (
            <div className="mt-2 text-[10px] font-mono text-text-tertiary tabular">
              Best fit: <span className="text-gold">
                +1h move ≈ {reg.slope >= 0 ? '+' : ''}{(reg.slope * 1000).toFixed(2)}bp per 1,000 Mbbl surprise
              </span>
              <span className="text-text-muted ml-2">r² = {reg.r2.toFixed(2)} · n = {reg.n}</span>
              <div className="text-[9.5px] text-text-muted mt-1">
                {reg.slope < 0 && reg.r2 > 0.15
                  ? `↑ Negative slope = bullish surprises (negative) lift Brent. Effect confirmed in data.`
                  : reg.r2 < 0.1
                  ? `↗ Weak fit — recent reactions noisier than the historical pattern.`
                  : `Pattern: ${reg.slope < 0 ? 'bullish' : 'mixed'} response.`}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Trader's note */}
      <div className="mt-4 pt-3 border-t border-border/40 text-[10px] font-mono text-text-tertiary leading-relaxed">
        <span className="text-text-secondary">Reading:</span> the EIA Wednesday 10:30 EST print is, per chapter 6 of the curriculum,
        "the single most market-moving regular data release in oil markets." Bullish surprises (stocks drew more than expected
        = market is tighter than thought) typically lift Brent in the first hour; bearish surprises (stocks built more) press it.
        The {scatterData.length}-week regression here is your historical reaction baseline.
      </div>
    </Panel>
  );
}
