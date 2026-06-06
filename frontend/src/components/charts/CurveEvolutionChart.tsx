import { useEffect, useState } from 'react';
import { Panel } from '@/components/ui/Panel';
import { Chip } from '@/components/ui/Chip';
import { SkeletonRows } from '@/components/ui/Skeleton';
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend } from 'recharts';
import clsx from 'clsx';

type Contract = { label?: string; price?: number | null };

/**
 * Curve Evolution — overlays the current forward curve against snapshots
 * stored locally (yesterday / 7d ago / 30d ago) so the user can see how
 * the curve shape (and slope/contango) has shifted.
 *
 * We persist daily curve snapshots in localStorage keyed by date, then
 * pick the closest match for "T-7d" and "T-30d".
 */
export function CurveEvolutionChart({
  brent,
  wti,
  asset = 'brent',
}: {
  brent: Contract[] | undefined;
  wti: Contract[] | undefined;
  asset?: 'brent' | 'wti';
}) {
  const [snapshots, setSnapshots] = useState<Record<string, Contract[]>>({});
  const current = asset === 'brent' ? brent : wti;

  // Persist daily snapshot and load history
  useEffect(() => {
    if (!current || current.length === 0) return;
    const today = new Date().toISOString().slice(0, 10);
    const storageKey = `pulse.curve.snapshots.${asset}`;
    let store: Record<string, Contract[]> = {};
    try {
      store = JSON.parse(localStorage.getItem(storageKey) || '{}');
    } catch { /* ignore */ }
    store[today] = current.map(c => ({ label: c.label, price: c.price ?? null }));
    // Keep only last 60 days
    const trimmed: Record<string, Contract[]> = {};
    Object.keys(store)
      .sort()
      .slice(-60)
      .forEach(d => { trimmed[d] = store[d]; });
    try {
      localStorage.setItem(storageKey, JSON.stringify(trimmed));
    } catch { /* ignore quota */ }
    setSnapshots(trimmed);
  }, [current, asset]);

  if (!current || current.length === 0) {
    return (
      <Panel title="Forward Curve Evolution" subtitle={`${asset.toUpperCase()} · M1→M12`} source="curve_blend">
        <SkeletonRows rows={6} />
      </Panel>
    );
  }

  // Pick closest snapshot dates: today, ~7d ago, ~30d ago
  const dates = Object.keys(snapshots).sort();
  const today = dates[dates.length - 1];
  const pickClosest = (targetDaysBack: number): string | null => {
    if (!today) return null;
    const t = new Date(today).getTime();
    let best: string | null = null;
    let bestDiff = Infinity;
    for (const d of dates) {
      if (d === today) continue;
      const dt = new Date(d).getTime();
      const daysAgo = (t - dt) / 86_400_000;
      const diff = Math.abs(daysAgo - targetDaysBack);
      if (diff < bestDiff) { bestDiff = diff; best = d; }
    }
    return best;
  };
  const d7  = pickClosest(7);
  const d30 = pickClosest(30);

  // Build chart data
  const N = Math.min(12, current.length);
  const data = Array.from({ length: N }, (_, i) => {
    const row: any = { label: `M${i + 1}` };
    row.now = current[i]?.price ?? null;
    if (d7  && snapshots[d7][i])  row.d7  = snapshots[d7][i].price  ?? null;
    if (d30 && snapshots[d30][i]) row.d30 = snapshots[d30][i].price ?? null;
    return row;
  });

  // Curve structure read
  const m1 = current[0]?.price ?? null;
  const m12 = current[Math.min(11, current.length - 1)]?.price ?? null;
  const m1m2 = current[0]?.price && current[1]?.price ? current[0]!.price! - current[1]!.price! : null;
  const slope = m1 && m12 ? m12 - m1 : null;
  const structure = slope === null ? null : slope < -1 ? 'BACKWARDATION' : slope > 1 ? 'CONTANGO' : 'FLAT';
  const tone: 'bull' | 'bear' | 'neut' =
    structure === 'BACKWARDATION' ? 'bull' : structure === 'CONTANGO' ? 'bear' : 'neut';

  return (
    <Panel
      title="Forward Curve Evolution"
      subtitle={`${asset.toUpperCase()} · current vs prior snapshots`}
      source="curve_blend"
      sourceNote="Prior snapshots are stored in localStorage from past loads — they are session-local, not from a server-side history."
      right={
        structure && <Chip tone={tone}>{structure}</Chip>
      }
    >
      <div className="grid grid-cols-3 gap-2 mb-3">
        <div className="bg-bg-card/40 p-2 rounded">
          <div className="text-[9px] font-mono text-text-muted uppercase tracking-widest">M1–M2</div>
          <div className={clsx('text-sm font-mono tabular', m1m2 !== null && m1m2 > 0 ? 'text-bull' : 'text-bear')}>
            {m1m2 !== null ? `${m1m2 > 0 ? '+' : ''}${m1m2.toFixed(2)}` : '—'}
          </div>
        </div>
        <div className="bg-bg-card/40 p-2 rounded">
          <div className="text-[9px] font-mono text-text-muted uppercase tracking-widest">M1–M12 slope</div>
          <div className={clsx('text-sm font-mono tabular', slope !== null && slope < 0 ? 'text-bull' : 'text-bear')}>
            {slope !== null ? `${slope > 0 ? '+' : ''}${slope.toFixed(2)}` : '—'}
          </div>
        </div>
        <div className="bg-bg-card/40 p-2 rounded">
          <div className="text-[9px] font-mono text-text-muted uppercase tracking-widest">snapshots</div>
          <div className="text-sm font-mono tabular text-text-secondary">{Object.keys(snapshots).length}d cached</div>
        </div>
      </div>

      <ResponsiveContainer width="100%" height={280}>
        <LineChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: -8 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1c2745" />
          <XAxis dataKey="label" tick={{ fontSize: 10, fill: '#6b809e', fontFamily: 'JetBrains Mono' }} axisLine={{ stroke: '#1c2745' }} />
          <YAxis
            tick={{ fontSize: 10, fill: '#6b809e', fontFamily: 'JetBrains Mono' }}
            axisLine={{ stroke: '#1c2745' }}
            domain={['auto', 'auto']}
            tickFormatter={(v: number) => `$${v.toFixed(0)}`}
          />
          <Tooltip
            contentStyle={{ background: '#0f1729', border: '1px solid #1c2745', borderRadius: 6, fontSize: 11, fontFamily: 'JetBrains Mono' }}
            formatter={(value: any) => [`$${Number(value).toFixed(2)}`, '']}
            labelStyle={{ color: '#aebccf' }}
          />
          <Legend wrapperStyle={{ fontSize: 10, fontFamily: 'JetBrains Mono', letterSpacing: '0.15em', paddingTop: 4 }} />
          {d30 && (
            <Line type="monotone" dataKey="d30" name={`30d ago (${d30.slice(5)})`} stroke="#4a5b78" strokeWidth={1.5} strokeDasharray="4 4" dot={false} isAnimationActive={false} />
          )}
          {d7 && (
            <Line type="monotone" dataKey="d7" name={`7d ago (${d7.slice(5)})`} stroke="#a78bfa" strokeWidth={1.8} dot={false} isAnimationActive={false} />
          )}
          <Line type="monotone" dataKey="now" name="Today" stroke="#d4af37" strokeWidth={2.5} dot={{ r: 3, fill: '#d4af37' }} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>

      <div className="mt-3 pt-3 border-t border-border/40 text-[10px] font-mono text-text-tertiary leading-relaxed">
        Backwardation (M1 &gt; M12) signals near-term tightness — refiners/buyers pay up for prompt barrels.
        Contango signals oversupply; when M1–M12 contango exceeds full carry (~$18/bbl), storage arbitrage becomes economic.
      </div>
    </Panel>
  );
}
