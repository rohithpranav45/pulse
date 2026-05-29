import { Panel } from '@/components/ui/Panel';
import { Chip } from '@/components/ui/Chip';
import { SkeletonRows } from '@/components/ui/Skeleton';
import { ResponsiveContainer, ComposedChart, Line, Area, XAxis, YAxis, CartesianGrid, Tooltip, ReferenceLine, ReferenceArea } from 'recharts';
import { Droplets, AlertCircle } from 'lucide-react';
import clsx from 'clsx';

type HistoryRow = { date: string; value: number; stocks: number };

export function ForwardCoverChart({ data }: { data: any }) {
  if (!data?.history || data.history.length < 12) {
    return (
      <Panel title="Days of Forward Cover · 5y" subtitle="US crude stocks ÷ refinery demand">
        <SkeletonRows rows={6} />
      </Panel>
    );
  }

  const history: HistoryRow[] = data.history;
  const current: number = data.current ?? 0;
  const criticalLow: number = data.critical_low ?? 54;
  const comfortableHigh: number = data.comfortable_high ?? 65;
  const demand: number = data.demand_assumption ?? 17;

  // Determine current tone
  const tone: 'bull' | 'bear' | 'neut' =
    current < criticalLow ? 'bull' :       // tight = bullish for prices
    current > comfortableHigh ? 'bear' :    // ample = bearish for prices
    'neut';

  // Min/max for axis
  const values = history.map(h => h.value);
  const yMin = Math.floor(Math.min(...values) - 2);
  const yMax = Math.ceil(Math.max(...values) + 2);

  // Period-over-period stats
  const last4w = history.slice(-4);
  const avg4w = last4w.reduce((s, h) => s + h.value, 0) / last4w.length;
  const yearAgo = history[history.length - 53];
  const yoyChange = yearAgo ? current - yearAgo.value : null;

  // Compute 5-year average for current calendar period (within 4 weeks of today's week)
  const fiveYrAvg = (() => {
    const now = new Date();
    const currWeek = Math.floor((now.getTime() - new Date(now.getFullYear(), 0, 1).getTime()) / (7 * 86_400_000));
    const matches = history.filter(h => {
      const d = new Date(h.date);
      const wk = Math.floor((d.getTime() - new Date(d.getFullYear(), 0, 1).getTime()) / (7 * 86_400_000));
      return Math.abs(wk - currWeek) <= 2;
    });
    if (matches.length === 0) return null;
    return matches.reduce((s, h) => s + h.value, 0) / matches.length;
  })();

  return (
    <Panel
      title="Days of Forward Cover · 5y"
      subtitle={`US crude stocks ÷ ${demand} mbd refinery demand · chapter 6 metric`}
      accent={tone}
      right={
        <Chip tone={tone}>
          {current < criticalLow ? 'TIGHT' : current > comfortableHigh ? 'AMPLE' : 'NORMAL'}
        </Chip>
      }
    >
      {/* Hero stats */}
      <div className="grid grid-cols-4 gap-3 mb-3 pb-3 border-b border-border/40">
        <div>
          <div className="text-[9px] font-mono uppercase tracking-widest text-text-muted">Current</div>
          <div className={clsx(
            'text-2xl font-display font-bold tabular',
            tone === 'bull' && 'text-bull', tone === 'bear' && 'text-bear', tone === 'neut' && 'text-neut',
          )}>
            {current.toFixed(1)}<span className="text-[11px] text-text-muted ml-1">days</span>
          </div>
        </div>
        <div>
          <div className="text-[9px] font-mono uppercase tracking-widest text-text-muted">4-week avg</div>
          <div className="text-2xl font-display font-bold tabular text-text-secondary">
            {avg4w.toFixed(1)}<span className="text-[11px] text-text-muted ml-1">days</span>
          </div>
        </div>
        <div>
          <div className="text-[9px] font-mono uppercase tracking-widest text-text-muted">5y seasonal avg</div>
          <div className="text-2xl font-display font-bold tabular text-gold">
            {fiveYrAvg !== null ? fiveYrAvg.toFixed(1) : '—'}<span className="text-[11px] text-text-muted ml-1">days</span>
          </div>
        </div>
        <div>
          <div className="text-[9px] font-mono uppercase tracking-widest text-text-muted">YoY change</div>
          <div className={clsx(
            'text-2xl font-display font-bold tabular',
            yoyChange === null ? 'text-text-muted' :
            yoyChange > 0 ? 'text-bear' : 'text-bull',
          )}>
            {yoyChange !== null ? `${yoyChange >= 0 ? '+' : ''}${yoyChange.toFixed(1)}` : '—'}
            {yoyChange !== null && <span className="text-[11px] text-text-muted ml-1">days</span>}
          </div>
        </div>
      </div>

      {/* Chart */}
      <ResponsiveContainer width="100%" height={300}>
        <ComposedChart data={history} margin={{ top: 8, right: 16, bottom: 4, left: -8 }}>
          <defs>
            <linearGradient id="cover-grad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#22d3ee" stopOpacity={0.3} />
              <stop offset="100%" stopColor="#22d3ee" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#1c2745" />
          <XAxis
            dataKey="date"
            tick={{ fontSize: 9, fill: '#6b809e', fontFamily: 'JetBrains Mono' }}
            axisLine={{ stroke: '#1c2745' }}
            interval={Math.floor(history.length / 12)}
            tickFormatter={(d: string) => d.slice(0, 7)}
          />
          <YAxis
            domain={[yMin, yMax]}
            tick={{ fontSize: 10, fill: '#6b809e', fontFamily: 'JetBrains Mono' }}
            axisLine={{ stroke: '#1c2745' }}
            label={{ value: 'days', angle: -90, position: 'insideLeft', offset: 8, fontSize: 9, fill: '#6b809e' }}
          />
          {/* Tightness/Ample zones */}
          <ReferenceArea
            y1={yMin}
            y2={criticalLow}
            fill="#10d997"
            fillOpacity={0.06}
            label={{ value: 'TIGHT', position: 'insideTopLeft', fontSize: 10, fill: '#10d997', fontFamily: 'JetBrains Mono' }}
          />
          <ReferenceArea
            y1={comfortableHigh}
            y2={yMax}
            fill="#ff4d6d"
            fillOpacity={0.06}
            label={{ value: 'AMPLE', position: 'insideBottomLeft', fontSize: 10, fill: '#ff4d6d', fontFamily: 'JetBrains Mono' }}
          />
          {/* Critical/comfortable threshold lines */}
          <ReferenceLine
            y={criticalLow}
            stroke="#10d997"
            strokeWidth={1.5}
            strokeDasharray="6 3"
            label={{ value: `${criticalLow}d critical`, position: 'insideRight', fontSize: 9, fill: '#10d997', fontFamily: 'JetBrains Mono' }}
          />
          <ReferenceLine
            y={comfortableHigh}
            stroke="#ff4d6d"
            strokeWidth={1.5}
            strokeDasharray="6 3"
            label={{ value: `${comfortableHigh}d comfortable`, position: 'insideRight', fontSize: 9, fill: '#ff4d6d', fontFamily: 'JetBrains Mono' }}
          />
          {fiveYrAvg !== null && (
            <ReferenceLine
              y={fiveYrAvg}
              stroke="#d4af37"
              strokeDasharray="2 4"
              label={{ value: `5y μ ${fiveYrAvg.toFixed(1)}`, position: 'insideLeft', fontSize: 9, fill: '#d4af37', fontFamily: 'JetBrains Mono' }}
            />
          )}
          <Tooltip
            contentStyle={{ background: '#0f1729', border: '1px solid #1c2745', borderRadius: 6, fontSize: 11, fontFamily: 'JetBrains Mono' }}
            formatter={(value: any, name: string) => {
              if (name === 'value') return [`${Number(value).toFixed(1)} days`, 'Days cover'];
              return [value, name];
            }}
          />
          <Area
            type="monotone"
            dataKey="value"
            stroke="none"
            fill="url(#cover-grad)"
            isAnimationActive={false}
          />
          <Line
            type="monotone"
            dataKey="value"
            stroke="#22d3ee"
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4, fill: '#d4af37' }}
            isAnimationActive={false}
          />
        </ComposedChart>
      </ResponsiveContainer>

      {/* Trader's note */}
      <div className="mt-3 pt-3 border-t border-border/40 flex items-start gap-2 text-[10.5px] font-mono text-text-tertiary leading-relaxed">
        <AlertCircle className="w-3 h-3 flex-shrink-0 mt-0.5 text-gold" />
        <span>
          <span className="text-text-secondary">Reading:</span> chapter 6 of the curriculum identifies the
          <span className="text-bull"> &lt;{criticalLow}-day threshold</span> as historically associated with
          $90+ Brent. Sustained operation below it triggers refinery panic-buying. Above
          <span className="text-bear"> {comfortableHigh} days</span>, storage starts to fill, supporting contango and pressuring spot.
          {current < criticalLow && (
            <span className="text-bull font-semibold"> Today {current.toFixed(1)}d → market tight.</span>
          )}
          {current > comfortableHigh && (
            <span className="text-bear font-semibold"> Today {current.toFixed(1)}d → market loose.</span>
          )}
        </span>
      </div>

      <div className="mt-2 flex items-center gap-1.5 text-[9px] font-mono text-text-muted">
        <Droplets className="w-3 h-3" />
        <span>Assumes US refinery throughput of {demand} mbd. Cushing-only metric would differ.</span>
      </div>
    </Panel>
  );
}
