import { useEffect, useRef, useState } from 'react';
import { Panel } from '@/components/ui/Panel';
import { Chip } from '@/components/ui/Chip';
import { Skeleton } from '@/components/ui/Skeleton';
import { fmt } from '@/lib/fmt';
import { createChart, ColorType, CandlestickSeries, HistogramSeries, LineSeries } from 'lightweight-charts';
import { LineChart, Line, ResponsiveContainer, XAxis, YAxis, Tooltip, ReferenceLine, Area, AreaChart, CartesianGrid } from 'recharts';
import clsx from 'clsx';

const CHART_THEME = {
  layout: { background: { type: ColorType.Solid, color: 'transparent' }, textColor: '#aebccf', fontFamily: 'JetBrains Mono, monospace', fontSize: 11 },
  grid: { vertLines: { color: 'rgba(28,39,69,0.5)' }, horzLines: { color: 'rgba(28,39,69,0.5)' } },
  rightPriceScale: { borderColor: '#1c2745' },
  timeScale: { borderColor: '#1c2745', timeVisible: true, secondsVisible: false },
  crosshair: {
    mode: 1,
    vertLine: { color: 'rgba(212,175,55,0.3)', width: 1, style: 3, labelBackgroundColor: '#d4af37' },
    horzLine: { color: 'rgba(212,175,55,0.3)', width: 1, style: 3, labelBackgroundColor: '#d4af37' },
  },
};

function calcEMA(data: any[], period: number) {
  if (data.length < period) return [];
  const k = 2 / (period + 1);
  const out: any[] = [];
  let ema = data.slice(0, period).reduce((s, d) => s + d.close, 0) / period;
  out.push({ time: data[period - 1].time, value: ema });
  for (let i = period; i < data.length; i++) {
    ema = data[i].close * k + ema * (1 - k);
    out.push({ time: data[i].time, value: ema });
  }
  return out;
}

function Candle({ ohlcv, asset }: { ohlcv: any; asset: 'brent' | 'wti' }) {
  const wrap = useRef<HTMLDivElement>(null);
  const chartRef = useRef<any>(null);
  const [overlays, setOverlays] = useState({ ema20: true, ema50: false, vol: true });

  useEffect(() => {
    if (!wrap.current || !ohlcv?.[asset]?.length) return;
    const series = ohlcv[asset];
    // Backend uses t (ms epoch), o/h/l/c/v
    const toTime = (b: any): number =>
      typeof b.t === 'number' ? Math.floor(b.t / 1000) :
      typeof b.timestamp === 'string' ? Math.floor(new Date(b.timestamp).getTime() / 1000) : 0;
    const candles = series
      .map((b: any) => ({ time: toTime(b), open: b.o ?? b.open, high: b.h ?? b.high, low: b.l ?? b.low, close: b.c ?? b.close }))
      .filter((b: any) => b.time > 0)
      .sort((a: any, b: any) => a.time - b.time);
    const vols = candles.map((c: any, i: number) => ({
      time: c.time,
      value: series[i]?.v ?? series[i]?.volume ?? 0,
      color: c.close >= c.open ? 'rgba(16,217,151,0.45)' : 'rgba(255,77,109,0.45)',
    }));

    const chart = createChart(wrap.current, {
      ...CHART_THEME,
      width: wrap.current.clientWidth,
      height: 460,
    });
    chartRef.current = chart;
    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#10d997', downColor: '#ff4d6d',
      borderUpColor: '#10d997', borderDownColor: '#ff4d6d',
      wickUpColor: '#10d997', wickDownColor: '#ff4d6d',
    });
    candleSeries.setData(candles);

    if (overlays.vol) {
      const volSeries = chart.addSeries(HistogramSeries, {
        priceFormat: { type: 'volume' },
        priceScaleId: '',
      });
      volSeries.priceScale().applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
      volSeries.setData(vols);
    }
    if (overlays.ema20) {
      const e = calcEMA(candles, 20);
      const ema20 = chart.addSeries(LineSeries, { color: '#22d3ee', lineWidth: 2 });
      ema20.setData(e as any);
    }
    if (overlays.ema50) {
      const e = calcEMA(candles, 50);
      const ema50 = chart.addSeries(LineSeries, { color: '#a78bfa', lineWidth: 2 });
      ema50.setData(e as any);
    }
    chart.timeScale().fitContent();

    const ro = new ResizeObserver(() => {
      if (wrap.current && chartRef.current) {
        chartRef.current.applyOptions({ width: wrap.current.clientWidth });
      }
    });
    ro.observe(wrap.current);

    return () => { ro.disconnect(); chart.remove(); };
  }, [ohlcv, asset, overlays.ema20, overlays.ema50, overlays.vol]);

  return (
    <div>
      <div className="flex items-center justify-end gap-2 mb-2">
        {(['ema20','ema50','vol'] as const).map(k => (
          <button
            key={k}
            onClick={() => setOverlays(o => ({ ...o, [k]: !o[k] }))}
            className={clsx(
              'text-[10px] font-mono px-2 py-1 rounded border tracking-widest uppercase transition-all',
              overlays[k]
                ? 'border-gold/50 text-gold bg-gold-soft'
                : 'border-border text-text-tertiary hover:text-text-secondary',
            )}
          >
            {k}
          </button>
        ))}
      </div>
      <div ref={wrap} className="w-full" style={{ height: 460 }}>
        {!ohlcv && <Skeleton className="h-full w-full" />}
      </div>
    </div>
  );
}

function CurveChart({ curve }: { curve: any }) {
  if (!curve?.brent && !curve?.wti) return <Skeleton className="h-72 w-full" />;
  const brent = curve.brent?.contracts ?? [];
  const wti = curve.wti?.contracts ?? [];
  const data = Array.from({ length: Math.max(brent.length, wti.length) }, (_, i) => ({
    label: `M${i + 1}`,
    brent: brent[i]?.price ?? null,
    wti: wti[i]?.price ?? null,
  }));
  return (
    <ResponsiveContainer width="100%" height={300}>
      <LineChart data={data} margin={{ top: 10, right: 10, bottom: 10, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#1c2745" />
        <XAxis dataKey="label" tick={{ fontSize: 10, fill: '#6b809e', fontFamily: 'JetBrains Mono' }} axisLine={{ stroke: '#1c2745' }} />
        <YAxis tick={{ fontSize: 10, fill: '#6b809e', fontFamily: 'JetBrains Mono' }} axisLine={{ stroke: '#1c2745' }} domain={['auto', 'auto']} />
        <Tooltip contentStyle={{ background: '#0f1729', border: '1px solid #1c2745', borderRadius: 6, fontFamily: 'JetBrains Mono', fontSize: 11 }} />
        <Line type="monotone" dataKey="brent" stroke="#d4af37" strokeWidth={2.5} dot={{ r: 3, fill: '#d4af37' }} name="Brent" />
        <Line type="monotone" dataKey="wti" stroke="#4d8eff" strokeWidth={2.5} dot={{ r: 3, fill: '#4d8eff' }} name="WTI" />
      </LineChart>
    </ResponsiveContainer>
  );
}

function SpreadChart({ history }: { history: any }) {
  if (!history?.brent || !history?.wti) return <Skeleton className="h-56 w-full" />;
  const brent = history.brent;
  const wti = history.wti;
  const dateKey = (d: any) => d.date ?? d.t ?? d.timestamp;
  const closeKey = (d: any) => d.close ?? d.c;
  const map: Record<string, number> = {};
  wti.forEach((d: any) => { map[dateKey(d)] = closeKey(d); });
  const data = brent
    .filter((d: any) => map[dateKey(d)] !== undefined)
    .map((d: any) => ({ date: String(dateKey(d)).slice(5, 10), spread: +(closeKey(d) - map[dateKey(d)]).toFixed(2) }));
  if (data.length === 0) return <Skeleton className="h-56 w-full" />;
  const mean = data.reduce((s: number, d: any) => s + d.spread, 0) / data.length;
  return (
    <ResponsiveContainer width="100%" height={220}>
      <AreaChart data={data} margin={{ top: 10, right: 10, bottom: 0, left: 0 }}>
        <defs>
          <linearGradient id="spreadGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#22d3ee" stopOpacity={0.4} />
            <stop offset="100%" stopColor="#22d3ee" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="#1c2745" />
        <XAxis dataKey="date" tick={{ fontSize: 9, fill: '#6b809e' }} axisLine={{ stroke: '#1c2745' }} interval={Math.floor(data.length / 8)} />
        <YAxis tick={{ fontSize: 9, fill: '#6b809e' }} axisLine={{ stroke: '#1c2745' }} />
        <Tooltip contentStyle={{ background: '#0f1729', border: '1px solid #1c2745', borderRadius: 6, fontSize: 11 }} />
        <ReferenceLine y={mean} stroke="#d4af37" strokeDasharray="4 4" label={{ value: `μ ${mean.toFixed(2)}`, fontSize: 10, fill: '#d4af37' }} />
        <Area type="monotone" dataKey="spread" stroke="#22d3ee" strokeWidth={2} fill="url(#spreadGrad)" />
      </AreaChart>
    </ResponsiveContainer>
  );
}

export function ChartsView({ all, history, ohlcv }: { all: any; history: any; ohlcv: any }) {
  const [asset, setAsset] = useState<'brent' | 'wti'>('brent');
  const curve = all?.curve;
  const prices = all?.prices;
  const q = prices?.[asset];

  return (
    <div className="space-y-4">
      <Panel
        title={asset === 'brent' ? 'Brent Crude · ICE' : 'WTI Crude · NYMEX'}
        subtitle="Intraday OHLCV · 5m"
        right={
          <div className="flex items-center gap-2">
            {q && (
              <>
                <span className="text-lg font-mono font-bold tabular text-text-primary">${fmt.price(q.price)}</span>
                <Chip tone={(q.change_pct ?? 0) >= 0 ? 'bull' : 'bear'}>
                  {fmt.pct(q.change_pct)}
                </Chip>
              </>
            )}
            <div className="flex border border-border rounded overflow-hidden ml-2">
              {(['brent','wti'] as const).map(k => (
                <button
                  key={k}
                  onClick={() => setAsset(k)}
                  className={clsx(
                    'px-3 py-1 text-[10px] font-mono tracking-widest uppercase transition-colors',
                    asset === k ? 'bg-gold text-bg' : 'text-text-tertiary hover:text-text-primary',
                  )}
                >
                  {k === 'brent' ? 'Brent' : 'WTI'}
                </button>
              ))}
            </div>
          </div>
        }
      >
        <Candle ohlcv={ohlcv} asset={asset} />
      </Panel>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <Panel title="Forward Curve" subtitle="M1 → M12 · Brent vs WTI">
          <CurveChart curve={curve} />
        </Panel>
        <Panel title="Brent–WTI Spread" subtitle="90-day daily">
          <SpreadChart history={history} />
        </Panel>
      </div>
    </div>
  );
}
