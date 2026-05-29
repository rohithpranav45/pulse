import { Panel } from '@/components/ui/Panel';
import { Chip } from '@/components/ui/Chip';
import { SkeletonRows } from '@/components/ui/Skeleton';
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ReferenceLine } from 'recharts';
import clsx from 'clsx';

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

const COLORS: Record<string, string> = {
  brent:       '#d4af37',
  wti:         '#4d8eff',
  natgas:      '#22d3ee',
  rbob:        '#10d997',
  heating_oil: '#ff4d6d',
};

const LABELS: Record<string, string> = {
  brent:       'Brent',
  wti:         'WTI',
  natgas:      'Nat Gas',
  rbob:        'RBOB',
  heating_oil: 'Heat Oil',
};

type Product = {
  key: string;
  label: string;
  monthly_returns: number[];
  monthly_std?: number[];
  current_avg: number;
  current_std?: number;
  bias: 'TAILWIND' | 'HEADWIND' | 'NEUTRAL';
  ok: boolean;
};

export function SeasonalityChart({ data }: { data: any }) {
  if (!data?.products || data.products.length === 0) {
    return (
      <Panel title="Seasonality · 5 Products" subtitle="Monthly average % return">
        <SkeletonRows rows={6} />
      </Panel>
    );
  }

  const products: Product[] = data.products;
  const currentMonth = data.current_month ?? new Date().getMonth();
  const years = data.data_years ?? 5;

  // Build chart data: 12 rows, one column per product
  const chartData = MONTHS.map((m, i) => {
    const row: any = { month: m, idx: i };
    products.forEach(p => {
      if (p.ok) row[p.key] = p.monthly_returns[i];
    });
    return row;
  });

  return (
    <Panel
      title="Seasonality · 5 Products"
      subtitle={`${years}-year average monthly returns · ${MONTHS[currentMonth]} highlighted`}
      right={
        <div className="flex items-center gap-2">
          <Chip tone="muted">{years}Y</Chip>
        </div>
      }
    >
      <ResponsiveContainer width="100%" height={340}>
        <LineChart data={chartData} margin={{ top: 10, right: 16, bottom: 0, left: -8 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1c2745" />
          <XAxis
            dataKey="month"
            tick={{ fontSize: 10, fill: '#6b809e', fontFamily: 'JetBrains Mono' }}
            axisLine={{ stroke: '#1c2745' }}
          />
          <YAxis
            tick={{ fontSize: 10, fill: '#6b809e', fontFamily: 'JetBrains Mono' }}
            axisLine={{ stroke: '#1c2745' }}
            unit="%"
            tickFormatter={(v: number) => `${v >= 0 ? '+' : ''}${v.toFixed(1)}`}
          />
          <Tooltip
            contentStyle={{
              background: '#0f1729',
              border: '1px solid #1c2745',
              borderRadius: 6,
              fontSize: 11,
              fontFamily: 'JetBrains Mono',
            }}
            formatter={(value: any, name: string) => [`${Number(value).toFixed(2)}%`, LABELS[name] || name]}
            labelStyle={{ color: '#aebccf' }}
          />
          <Legend
            wrapperStyle={{ fontSize: 10, fontFamily: 'JetBrains Mono', letterSpacing: '0.15em', paddingTop: 4 }}
            formatter={(value: string) => LABELS[value] || value}
          />
          <ReferenceLine y={0} stroke="#2a3a5e" strokeWidth={1} />
          <ReferenceLine
            x={MONTHS[currentMonth]}
            stroke="#d4af37"
            strokeWidth={2}
            strokeDasharray="3 3"
            label={{ value: 'NOW', position: 'top', fontSize: 9, fill: '#d4af37', fontFamily: 'JetBrains Mono' }}
          />
          {products.filter(p => p.ok).map(p => (
            <Line
              key={p.key}
              type="monotone"
              dataKey={p.key}
              stroke={COLORS[p.key] || '#aebccf'}
              strokeWidth={2}
              dot={{ r: 3, fill: COLORS[p.key] || '#aebccf', strokeWidth: 0 }}
              activeDot={{ r: 5 }}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>

      {/* Per-product current-month bias chips */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-2 mt-3 pt-3 border-t border-border/40">
        {products.map(p => {
          const tone: 'bull' | 'bear' | 'neut' =
            p.bias === 'TAILWIND' ? 'bull' : p.bias === 'HEADWIND' ? 'bear' : 'neut';
          return (
            <div key={p.key} className="flex flex-col gap-1 p-2 bg-bg-card/40 rounded">
              <div className="flex items-baseline justify-between">
                <span
                  className="text-[10px] font-mono uppercase tracking-widest"
                  style={{ color: COLORS[p.key] || '#aebccf' }}
                >
                  {LABELS[p.key]}
                </span>
                <span className={clsx('text-[10px] font-mono tabular', `text-${tone}`)}>
                  {p.current_avg >= 0 ? '+' : ''}{p.current_avg.toFixed(2)}%
                </span>
              </div>
              <Chip tone={tone}>{p.bias}</Chip>
            </div>
          );
        })}
      </div>
    </Panel>
  );
}
