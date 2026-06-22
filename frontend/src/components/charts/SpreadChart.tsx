import { Panel } from '@/components/ui/Panel';
import { Chip } from '@/components/ui/Chip';
import { ResponsiveContainer, AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ReferenceLine } from 'recharts';
import clsx from 'clsx';

type Series = { date: string; value: number }[];
type Stats = {
  current?: number | null;
  mean_252d?: number | null;
  std_252d?: number | null;
  z_score?: number | null;
  min_1y?: number | null;
  max_1y?: number | null;
  last_30d_avg?: number | null;
  n?: number;
};

type Props = {
  title: string;
  subtitle?: string;
  series: Series;
  stats?: Stats;
  unit?: string;                        // e.g. "$/bbl"
  color?: string;                       // primary stroke color
  height?: number;
  bullishHigh?: boolean;                // when true, high values are bullish (color cue)
  showBands?: boolean;                  // show ±1σ band lines
};

export function SpreadChart({
  title,
  subtitle,
  series,
  stats,
  unit = '$/bbl',
  color = '#22d3ee',
  height = 260,
  bullishHigh = true,
  showBands = true,
}: Props) {
  if (!series || series.length < 5) {
    return (
      <Panel title={title} subtitle={subtitle} source="yfinance_daily">
        <div className="skeleton w-full" style={{ height }} />
      </Panel>
    );
  }

  const mean = stats?.mean_252d ?? null;
  const std = stats?.std_252d ?? null;
  const cur = stats?.current ?? null;
  const z = stats?.z_score ?? null;
  const upperBand = mean !== null && std !== null ? mean + std : null;
  const lowerBand = mean !== null && std !== null ? mean - std : null;

  // Determine tone for the chip (z-score based)
  const tone: 'bull' | 'bear' | 'neut' =
    z === null
      ? 'neut'
      : (bullishHigh ? z > 0.5 : z < -0.5)
      ? 'bull'
      : (bullishHigh ? z < -0.5 : z > 0.5)
      ? 'bear'
      : 'neut';

  const Stat = ({ label, value, tone }: { label: string; value: string; tone?: string }) => (
    <div className="flex flex-col items-end">
      <div className="text-[9px] font-mono text-text-muted tracking-widest uppercase">{label}</div>
      <div className={clsx('text-[11px] font-mono tabular font-semibold', tone || 'text-text-secondary')}>{value}</div>
    </div>
  );

  return (
    <Panel
      title={title}
      subtitle={subtitle ?? `${series.length} sessions · ${unit}`}
      source="yfinance_daily"
      dataTimestamp={series[series.length - 1]?.date}
      right={
        z !== null && (
          <Chip tone={tone}>
            z {z >= 0 ? '+' : ''}{z.toFixed(2)}σ
          </Chip>
        )
      }
    >
      <div className="flex items-baseline justify-between gap-3 mb-3">
        <div>
          <div className="text-[10px] font-mono text-text-tertiary uppercase tracking-widest">Current</div>
          <div className={clsx(
            'text-2xl font-display font-bold tabular',
            cur !== null && mean !== null ? (cur >= mean ? 'text-bull' : 'text-bear') : 'text-text-primary',
          )}>
            {cur !== null ? `${cur >= 0 ? '+' : ''}${cur.toFixed(2)}` : '—'}
            <span className="text-[10px] font-mono text-text-muted ml-1">{unit}</span>
          </div>
        </div>
        <div className="flex gap-4">
          <Stat label="μ 252d" value={mean !== null ? mean.toFixed(2) : '—'} tone="text-gold" />
          <Stat label="σ" value={std !== null ? std.toFixed(2) : '—'} />
          <Stat label="30d avg" value={stats?.last_30d_avg != null ? stats.last_30d_avg.toFixed(2) : '—'} />
          <Stat label="range 1y" value={stats?.min_1y != null && stats?.max_1y != null
            ? `${stats.min_1y.toFixed(1)} → ${stats.max_1y.toFixed(1)}` : '—'} />
        </div>
      </div>

      <ResponsiveContainer width="100%" height={height}>
        <AreaChart data={series} margin={{ top: 4, right: 8, bottom: 0, left: -8 }}>
          <defs>
            <linearGradient id={`grad-${title.replace(/\s+/g, '-')}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity={0.45} />
              <stop offset="100%" stopColor={color} stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#1c2745" />
          <XAxis
            dataKey="date"
            tick={{ fontSize: 9, fill: '#6b809e', fontFamily: 'JetBrains Mono' }}
            axisLine={{ stroke: '#1c2745' }}
            interval={Math.max(1, Math.floor(series.length / 8))}
            tickFormatter={(d: string) => (d || '').slice(5)}
          />
          <YAxis
            tick={{ fontSize: 9, fill: '#6b809e', fontFamily: 'JetBrains Mono' }}
            axisLine={{ stroke: '#1c2745' }}
            domain={['auto', 'auto']}
          />
          <Tooltip
            contentStyle={{
              background: '#0f1729',
              border: '1px solid #1c2745',
              borderRadius: 6,
              fontSize: 11,
              fontFamily: 'JetBrains Mono',
            }}
            labelStyle={{ color: '#aebccf' }}
            formatter={(value: any) => [`${Number(value).toFixed(2)} ${unit}`, title]}
          />
          {mean !== null && (
            <ReferenceLine
              y={mean}
              stroke="#d4af37"
              strokeDasharray="4 4"
              label={{ value: `μ ${mean.toFixed(2)}`, fontSize: 9, fill: '#d4af37', fontFamily: 'JetBrains Mono', position: 'insideTopRight' }}
            />
          )}
          {showBands && upperBand !== null && (
            <ReferenceLine y={upperBand} stroke="#2a3a5e" strokeDasharray="2 4" />
          )}
          {showBands && lowerBand !== null && (
            <ReferenceLine y={lowerBand} stroke="#2a3a5e" strokeDasharray="2 4" />
          )}
          <ReferenceLine y={0} stroke="#3a4a6e" strokeWidth={1} />
          <Area
            type="monotone"
            dataKey="value"
            stroke={color}
            strokeWidth={1.8}
            fill={`url(#grad-${title.replace(/\s+/g, '-')})`}
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </Panel>
  );
}
