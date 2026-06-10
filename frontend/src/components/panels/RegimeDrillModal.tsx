import { useEffect, useMemo, useState } from 'react';
import clsx from 'clsx';
import { motion } from 'framer-motion';
import { Modal } from '@/components/ui/Modal';
import { Stat } from '@/components/ui/Stat';
import { SkeletonRows } from '@/components/ui/Skeleton';
import { api } from '@/lib/api';
import { staggerContainer, staggerTight, fadeUp, scaleIn } from '@/lib/motion';

/**
 * Phase 2 Sprint 2c — drill-down receipts for a regime pick.
 *
 * Opens from the top pick in `RegimePickCard`. Shows:
 *   1. Scatter of (fair, actual) over the regime's full history with an
 *      identity y=x line and today's point highlighted. Gives a visceral
 *      sense of how well the model fits this regime's cloud.
 *   2. The 3 closest historical analogs to today's feature vector
 *      (Euclidean over standardised features), with their 20-day forward
 *      realised change of the spread — "when this setup happened before,
 *      what came next?"
 */

type ScatterPoint = { date: string; actual: number; fair: number };
type SimilarFeat  = { feature: string; today: number; analog: number; z_gap: number };
type Analog = {
  rank: number;
  date: string;
  distance: number;
  spread_then: number;
  forward_days: number;
  forward_date: string | null;
  forward_spread: number | null;
  forward_change: number | null;
  similar_features: SimilarFeat[];
};

type Drill = {
  available: boolean;
  error?: string;
  spread?: string;
  label?: string;
  regime?: string;
  as_of?: string;
  today?: { actual: number; fair: number; deviation: number };
  scatter?: ScatterPoint[];
  n_points?: number;
  in_sample_r2?: number;
  analogs?: Analog[];
  feature_cols?: string[];
};

export function RegimeDrillModal({
  open, onClose, spread, label, regime,
}: {
  open: boolean;
  onClose: () => void;
  spread: string | null;
  label?: string;
  regime?: string;
}) {
  const [data, setData]     = useState<Drill | null>(null);
  const [loading, setLoad]  = useState(false);
  const [err, setErr]       = useState<string | null>(null);

  useEffect(() => {
    if (!open || !spread) { setData(null); setErr(null); return; }
    setLoad(true); setErr(null);
    api.regimeDrill(spread)
      .then((d: Drill) => {
        if (!d?.available) setErr(d?.error || 'no data');
        setData(d);
      })
      .catch((e: any) => setErr(e?.message || String(e)))
      .finally(() => setLoad(false));
  }, [open, spread]);

  return (
    <Modal
      open={open}
      onClose={onClose}
      size="xl"
      title={label ? `Drill · ${label}` : 'Drill'}
      subtitle={regime ? `regime ${regime.replace(/_/g, ' ').toLowerCase()} · evidence behind today's pick` : undefined}
    >
      {loading && <SkeletonRows rows={8} />}
      {err && !loading && (
        <motion.div
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          className="p-4 text-[12px] font-mono text-bear"
        >
          ⚠ {err}
        </motion.div>
      )}
      {data?.available && (
        <motion.div
          variants={staggerContainer}
          initial="hidden"
          animate="show"
          className="space-y-1"
        >
          <motion.div variants={fadeUp}>
            <TopStrip d={data} />
          </motion.div>
          <motion.div variants={fadeUp}>
            <ScatterPlot d={data} />
          </motion.div>
          <motion.div variants={fadeUp}>
            <AnalogsTable d={data} />
          </motion.div>
        </motion.div>
      )}
    </Modal>
  );
}

function TopStrip({ d }: { d: Drill }) {
  if (!d.today) return null;
  const devTone = d.today.deviation > 0 ? 'bear' : d.today.deviation < 0 ? 'bull' : 'neut';
  return (
    <motion.div
      variants={staggerTight}
      initial="hidden"
      animate="show"
      className="grid grid-cols-4 gap-3 mb-4"
    >
      {[
        <Stat label="Today actual" value={`$${d.today.actual.toFixed(2)}`} />,
        <Stat label="Today fair"   value={`$${d.today.fair.toFixed(2)}`} tone="gold" />,
        <Stat label="Deviation"
              value={`${d.today.deviation >= 0 ? '+' : ''}$${d.today.deviation.toFixed(2)}`}
              tone={devTone as any} />,
        <Stat label="In-sample R²"
              value={d.in_sample_r2 !== undefined ? d.in_sample_r2.toFixed(2) : '—'}
              sub={`${d.n_points ?? 0} pts in regime`} />,
      ].map((node, i) => (
        <motion.div key={i} variants={scaleIn}>{node}</motion.div>
      ))}
    </motion.div>
  );
}

// ─── Scatter: actual vs fair, with identity line + today's point ────────────

function ScatterPlot({ d }: { d: Drill }) {
  const pts = d.scatter ?? [];
  const today = d.today;

  const { minV, maxV } = useMemo(() => {
    if (!pts.length) return { minV: 0, maxV: 1 };
    const xs = pts.map(p => p.fair).concat(today ? [today.fair] : []);
    const ys = pts.map(p => p.actual).concat(today ? [today.actual] : []);
    return { minV: Math.min(...xs, ...ys), maxV: Math.max(...xs, ...ys) };
  }, [pts, today]);

  if (!pts.length) return null;

  // SVG viewport
  const W = 100, H = 100, PAD = 8;
  const scale = (v: number) => PAD + ((v - minV) / (maxV - minV || 1)) * (W - PAD * 2);
  const ySvg  = (v: number) => H - PAD - ((v - minV) / (maxV - minV || 1)) * (H - PAD * 2);

  // Identity line endpoints
  const idA = { x: scale(minV), y: ySvg(minV) };
  const idB = { x: scale(maxV), y: ySvg(maxV) };

  return (
    <div className="mb-4">
      <div className="flex items-center justify-between mb-2">
        <div className="text-[10px] font-mono uppercase tracking-widest text-text-muted">
          Actual vs fair — every day in this regime
        </div>
        <div className="flex items-center gap-2 text-[10px] font-mono text-text-tertiary">
          <span className="inline-flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-text-tertiary/60 inline-block" /> history
          </span>
          <span className="inline-flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-gold inline-block" /> today
          </span>
          <span className="inline-flex items-center gap-1">
            <span className="w-3 h-px bg-text-muted inline-block" /> y = x
          </span>
        </div>
      </div>
      <div className="border border-border/40 bg-bg-card/30 rounded p-3 overflow-hidden">
        <svg viewBox="0 0 100 100" className="w-full h-[320px]" preserveAspectRatio="none">
          {/* axes */}
          <line x1={PAD} y1={H - PAD} x2={W - PAD} y2={H - PAD} stroke="#2a3a5e" strokeWidth="0.2" />
          <line x1={PAD} y1={PAD}     x2={PAD}     y2={H - PAD} stroke="#2a3a5e" strokeWidth="0.2" />
          {/* identity line — draw in */}
          <motion.line
            x1={idA.x} y1={idA.y} x2={idB.x} y2={idB.y}
            stroke="#5a6781" strokeWidth="0.3" strokeDasharray="1 1"
            initial={{ pathLength: 0, opacity: 0 }}
            animate={{ pathLength: 1, opacity: 1 }}
            transition={{ duration: 0.7, ease: [0.16, 1, 0.3, 1], delay: 0.05 }}
          />
          {/* history points — fade in as a cloud */}
          <motion.g
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.5, delay: 0.25 }}
          >
            {pts.map((p, i) => (
              <circle key={i}
                      cx={scale(p.fair)} cy={ySvg(p.actual)}
                      r={0.5}
                      fill="rgba(180,196,224,0.55)" />
            ))}
          </motion.g>
          {/* today's point — pop in last */}
          {today && (
            <motion.g
              initial={{ opacity: 0, scale: 0.4 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1], delay: 0.55 }}
              style={{ transformOrigin: `${scale(today.fair)}px ${ySvg(today.actual)}px` }}
            >
              <circle cx={scale(today.fair)} cy={ySvg(today.actual)}
                      r={2.4} fill="#d4af37" opacity="0.18" />
              <circle cx={scale(today.fair)} cy={ySvg(today.actual)}
                      r={1.6} fill="#d4af37" stroke="#fff" strokeWidth="0.3" />
              {/* faint crosshair lines from axes to today */}
              <line x1={scale(today.fair)} y1={H - PAD} x2={scale(today.fair)} y2={ySvg(today.actual)}
                    stroke="#d4af37" strokeWidth="0.15" strokeDasharray="0.6 0.6" />
              <line x1={PAD} y1={ySvg(today.actual)} x2={scale(today.fair)} y2={ySvg(today.actual)}
                    stroke="#d4af37" strokeWidth="0.15" strokeDasharray="0.6 0.6" />
            </motion.g>
          )}
          {/* axis labels */}
          <text x={W/2} y={H - 1} fontSize="2.4" fill="#7a89a8" textAnchor="middle" fontFamily="monospace">
            fair value →
          </text>
          <text x={2} y={H/2} fontSize="2.4" fill="#7a89a8" textAnchor="middle"
                transform={`rotate(-90 2 ${H/2})`} fontFamily="monospace">
            actual →
          </text>
          {/* min/max gridline labels */}
          <text x={PAD} y={H - PAD + 3} fontSize="2.2" fill="#5a6781" fontFamily="monospace">
            ${minV.toFixed(1)}
          </text>
          <text x={W - PAD} y={H - PAD + 3} fontSize="2.2" fill="#5a6781" fontFamily="monospace" textAnchor="end">
            ${maxV.toFixed(1)}
          </text>
        </svg>
      </div>
      <div className="text-[10px] font-mono text-text-muted mt-1.5 text-center">
        Closer to y=x means model and reality agree. Today's gold dot above the line ⇒ spread is rich vs fair.
      </div>
    </div>
  );
}

// ─── Analogs table ──────────────────────────────────────────────────────────

function AnalogsTable({ d }: { d: Drill }) {
  const rows = d.analogs ?? [];
  if (!rows.length) {
    return (
      <div className="text-[11px] font-mono text-text-tertiary p-3 text-center">
        Not enough regime history to compute analogs.
      </div>
    );
  }
  return (
    <div>
      <div className="text-[10px] font-mono uppercase tracking-widest text-text-muted mb-2">
        Historical analogs · 3 closest days by feature vector (Euclidean, standardised)
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-[11px] font-mono tabular">
          <thead>
            <tr className="text-text-muted text-[9px] uppercase tracking-widest border-b border-border">
              <th className="text-left py-2">#</th>
              <th className="text-left">Date</th>
              <th className="text-right">σ dist</th>
              <th className="text-right">Spread then</th>
              <th className="text-right">+{rows[0].forward_days}d spread</th>
              <th className="text-right">Δ over window</th>
              <th className="text-left pl-4">Closest features</th>
            </tr>
          </thead>
          <motion.tbody variants={staggerTight} initial="hidden" animate="show">
            {rows.map(a => {
              const change = a.forward_change;
              const sign = change === null ? 'text-text-muted'
                          : change > 0 ? 'text-bull' : change < 0 ? 'text-bear' : 'text-text-secondary';
              return (
                <motion.tr
                  key={a.rank}
                  variants={fadeUp}
                  className="border-b border-border/30 align-top hover:bg-bg-hover/30 transition-colors"
                >
                  <td className="py-2 text-gold font-bold">#{a.rank}</td>
                  <td className="text-text-primary">{a.date}</td>
                  <td className="text-right text-text-secondary">{a.distance.toFixed(2)}</td>
                  <td className="text-right text-text-secondary">${a.spread_then.toFixed(2)}</td>
                  <td className="text-right text-text-tertiary">
                    {a.forward_spread !== null ? `$${a.forward_spread.toFixed(2)}` : '—'}
                  </td>
                  <td className={clsx('text-right font-semibold', sign)}>
                    {change === null ? '—'
                      : `${change >= 0 ? '+' : ''}$${change.toFixed(2)}`}
                  </td>
                  <td className="pl-4">
                    <div className="flex flex-wrap gap-1.5">
                      {a.similar_features.map(f => (
                        <span key={f.feature}
                              className="px-1.5 py-0.5 rounded bg-bg-card/50 border border-border/30 text-[10px]"
                              title={`today ${f.today} vs analog ${f.analog}`}>
                          {f.feature}
                          <span className="text-text-muted ml-1">·{f.z_gap.toFixed(1)}σ</span>
                        </span>
                      ))}
                    </div>
                  </td>
                </motion.tr>
              );
            })}
          </motion.tbody>
        </table>
      </div>
      <div className="mt-3 text-[10px] font-mono text-text-muted">
        The forward column shows what the spread actually did over the next {rows[0].forward_days} trading days
        after that historical match. Use these as a sanity check on today's signal, not a guarantee.
      </div>
    </div>
  );
}

export type { Drill };
