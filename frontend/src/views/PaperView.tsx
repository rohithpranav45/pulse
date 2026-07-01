import { Fragment, useCallback, useMemo, useState } from 'react';
import clsx from 'clsx';
import { motion, AnimatePresence } from 'framer-motion';
import { Panel } from '@/components/ui/Panel';
import { PageHeader, SectionHeader } from '@/components/ui/SectionHeader';
import { Chip } from '@/components/ui/Chip';
import { Stat } from '@/components/ui/Stat';
import { SkeletonRows } from '@/components/ui/Skeleton';
import { fmt } from '@/lib/fmt';
import { api } from '@/lib/api';
import { usePolling } from '@/lib/hooks';
import { staggerTight, fadeUp, scaleIn } from '@/lib/motion';
import {
  Play, TrendingUp, TrendingDown,
  AlertOctagon, Wallet, Activity, Trash2, Zap, Bot,
} from 'lucide-react';

/**
 * Paper-trading sandbox.
 *
 *   Suggested Trade  →  [Push to Paper] / [Dismiss]
 *   Open positions   →  live MTM, [Close] per row
 *   Closed history   →  realised PnL, exit reason
 *   Performance      →  total PnL, win%, Sharpe, max DD, equity curve
 */

type Leg = {
  id: number;
  trade_id: number;
  contract: string;
  direction: 'LONG' | 'SHORT';
  qty: number;
  entry_price: number;
  mtm_price: number | null;
  mtm_at: string | null;
  unrealised: number | null;
  exit_price: number | null;
  realised: number | null;
};

type Position = {
  id: number;
  asset: string;
  direction: 'LONG' | 'SHORT';
  size: number;
  entry_price: number;
  target_price: number | null;
  stop_price:   number | null;
  opened_at: string;
  closed_at: string | null;
  exit_price: number | null;
  close_reason: string | null;
  status: 'OPEN' | 'CLOSED';
  source: string | null;
  conviction: string | null;
  thesis: string | null;
  mtm_price: number | null;
  unrealised: number | null;
  realised: number | null;
  realised_pct: number | null;
  legs?: Leg[];
};

type Performance = {
  total_trades: number;
  wins: number;
  losses: number;
  scratches: number;
  decisive: number;
  win_rate_pct: number;
  total_pnl: number;
  total_pnl_pct: number | null;
  avg_pnl_per_trade: number;
  avg_win: number;
  avg_loss: number;
  profit_factor: number | null;
  sharpe_annualised: number | null;
  avg_holding_days: number | null;
  max_drawdown: number;
  max_drawdown_pct: number | null;
  best_trade: { id: number; pnl: number; asset: string } | null;
  worst_trade:{ id: number; pnl: number; asset: string } | null;
  equity_curve: { trade_id: number; closed_at: string; cum_pnl: number }[];
};

// ─── Auto-desk provenance helpers ───────────────────────────────────────────

const isAuto = (p: Position) => p.source === 'auto_desk';

/** Small chip marking a row the live auto-desk opened (vs a manual/A-B push). */
function AutoBadge({ source }: { source: string | null }) {
  if (source !== 'auto_desk') return null;
  return (
    <span
      title="Opened automatically by the live auto-trade desk"
      className="ml-2 inline-flex items-center gap-0.5 rounded px-1.5 py-0.5 text-[9px] font-mono font-bold uppercase tracking-widest bg-accent-blue/15 text-accent-blue border border-accent-blue/30"
    >
      <Bot className="w-2.5 h-2.5" /> auto
    </span>
  );
}

type SrcFilter = 'all' | 'auto' | 'manual';

function SourceFilter({ value, onChange, autoCount, total }:
  { value: SrcFilter; onChange: (v: SrcFilter) => void; autoCount: number; total: number }) {
  const opts: { k: SrcFilter; label: string }[] = [
    { k: 'all', label: `All · ${total}` },
    { k: 'auto', label: `Auto-desk · ${autoCount}` },
    { k: 'manual', label: `Manual · ${total - autoCount}` },
  ];
  return (
    <div className="inline-flex rounded-md border border-border/60 overflow-hidden">
      {opts.map(o => (
        <button
          key={o.k}
          onClick={() => onChange(o.k)}
          className={clsx(
            'px-2.5 py-1 text-[10px] font-mono uppercase tracking-widest transition-colors',
            value === o.k ? 'bg-accent-blue/20 text-accent-blue' : 'text-text-tertiary hover:bg-bg-hover/40',
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}


// ─── Suggested trade card ───────────────────────────────────────────────────

function SuggestedTrade({ idea, onPush }: { idea: any; onPush: (size: number) => Promise<void> }) {
  const [busy, setBusy] = useState(false);
  const [size, setSize] = useState(1);
  const [flash, setFlash] = useState<'ok' | 'err' | null>(null);
  const [errMsg, setErrMsg] = useState<string | null>(null);

  if (!idea) return <Panel title="Suggested Trade" staticMount><SkeletonRows rows={4} /></Panel>;

  const dir = (idea.direction || 'NEUTRAL').toUpperCase();
  const isNeutral = dir === 'NEUTRAL';
  const tone: 'bull' | 'bear' | 'neut' =
    dir.includes('LONG') ? 'bull' :
    dir.includes('SHORT') ? 'bear' : 'neut';

  const push = async () => {
    setBusy(true); setFlash(null); setErrMsg(null);
    try {
      const out = await api.paperPush({ size });
      if (out?.ok) {
        setFlash('ok');
        setTimeout(() => setFlash(null), 2500);
        onPush(size).catch(() => {});
      } else {
        setFlash('err');
        setErrMsg(out?.error || 'push failed');
        setTimeout(() => setFlash(null), 4000);
      }
    } catch (e: any) {
      setFlash('err');
      setErrMsg(e?.message || String(e));
      setTimeout(() => setFlash(null), 4000);
    } finally { setBusy(false); }
  };

  return (
    <Panel
      title="Suggested Trade"
      subtitle={`${idea.time_horizon ?? '1–2W'} · ${idea.conviction ?? '—'} conviction`}
      accent={tone as any}
      source="trade_idea_rule"
      dataTimestamp={idea.timestamp}
      right={<Chip tone={tone as any}>{dir}</Chip>}
      staticMount
    >
      <motion.div
        variants={staggerTight}
        initial="hidden"
        animate="show"
        className="grid grid-cols-4 gap-3 mb-4"
      >
        {[
          { label: 'Spot',       value: `$${fmt.price(idea.live_price)}` },
          { label: 'Target',     value: `$${fmt.price(idea.target_level)}`, tone: 'bull' as const },
          { label: 'Stop',       value: `$${fmt.price(idea.stop_level)}`,   tone: 'bear' as const },
          { label: 'Fair Value', value: `$${fmt.price(idea.fair_value)}`,   tone: 'gold' as const },
        ].map(s => (
          <motion.div key={s.label} variants={scaleIn}>
            <Stat label={s.label} value={s.value} tone={s.tone} />
          </motion.div>
        ))}
      </motion.div>

      {idea.entry_thesis && (
        <motion.ul
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.15, duration: 0.32 }}
          className="p-3 bg-bg-card/40 rounded space-y-1.5 text-[11.5px] leading-relaxed text-text-secondary mb-3 list-none"
        >
          {(Array.isArray(idea.entry_thesis) ? idea.entry_thesis : [idea.entry_thesis]).slice(0, 3).map((t: string, i: number) => (
            <li key={i} className="flex items-start gap-2">
              <span className="text-gold mt-0.5 flex-shrink-0">•</span>
              <span>{t}</span>
            </li>
          ))}
        </motion.ul>
      )}

      {idea.key_risk && (
        <div className="flex items-start gap-2 text-[10px] font-mono text-neut/90 mb-3">
          <AlertOctagon className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
          <span><span className="text-text-muted uppercase tracking-widest mr-1">RISK ·</span>{idea.key_risk}</span>
        </div>
      )}

      {/* Push controls */}
      <div className="mt-4 pt-3 border-t border-border/40 flex items-center gap-3">
        <label className="flex items-center gap-2 text-[10px] font-mono text-text-tertiary uppercase tracking-widest">
          Size
          <input
            type="number"
            min={0.1}
            step={0.1}
            value={size}
            onChange={(e) => setSize(parseFloat(e.target.value) || 1)}
            className="w-16 bg-bg-card/70 border border-border rounded px-2 py-1 text-[12px] font-mono text-text-primary tabular outline-none focus:border-gold/60 transition-colors"
          />
        </label>

        <motion.button
          onClick={push}
          disabled={busy || isNeutral}
          whileHover={!busy && !isNeutral ? { y: -1 } : {}}
          whileTap={!busy && !isNeutral ? { scale: 0.97 } : {}}
          transition={{ duration: 0.16, ease: [0.22, 1, 0.36, 1] }}
          className={clsx(
            'flex items-center gap-2 px-4 py-2 rounded-md font-mono uppercase tracking-widest text-[11px] font-bold transition-colors',
            isNeutral ? 'bg-bg-elev text-text-muted cursor-not-allowed'
            : busy   ? 'bg-gold/40 text-bg cursor-wait'
                     : 'bg-gold text-bg hover:bg-gold-bright shadow-md',
          )}
        >
          <Play className="w-3.5 h-3.5" />
          {isNeutral ? 'No trade — neutral bias' : busy ? 'pushing…' : 'Push to Paper'}
        </motion.button>

        <AnimatePresence>
          {flash === 'ok'  && (
            <motion.span
              key="ok"
              initial={{ opacity: 0, x: -4 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0 }}
              className="text-bull text-[11px] font-mono"
            >
              ✓ paper trade opened
            </motion.span>
          )}
          {flash === 'err' && (
            <motion.span
              key="err"
              initial={{ opacity: 0, x: -4 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0 }}
              className="text-bear text-[11px] font-mono"
            >
              ✕ {errMsg}
            </motion.span>
          )}
        </AnimatePresence>
      </div>
    </Panel>
  );
}


// ─── Open positions table ───────────────────────────────────────────────────

function OpenPositions({ rows, onClose }: { rows: Position[]; onClose: (id: number) => Promise<void> }) {
  const [busy, setBusy] = useState<number | null>(null);
  if (!rows.length) return (
    <Panel title="Open Positions" accent="blue" staticMount>
      <div className="text-[11px] font-mono text-text-tertiary p-4 text-center">
        No open paper trades. Push one from the suggested-trade card above.
      </div>
    </Panel>
  );
  return (
    <Panel title="Open Positions" subtitle={`${rows.length} active · marked to market every minute`} accent="blue" staticMount>
      <div className="overflow-x-auto">
        <table className="w-full text-[11px] font-mono tabular">
          <thead>
            <tr className="text-text-muted text-[9px] uppercase tracking-widest border-b border-border">
              <th className="text-left py-2">#</th>
              <th className="text-left">Asset · Dir</th>
              <th className="text-right">Entry</th>
              <th className="text-right">MTM</th>
              <th className="text-right">Target</th>
              <th className="text-right">Stop</th>
              <th className="text-right">Unrealised</th>
              <th className="text-right">Size</th>
              <th className="text-right">Opened</th>
              <th className="text-right">·</th>
            </tr>
          </thead>
          <motion.tbody variants={staggerTight} initial="hidden" animate="show">
            {rows.map(t => {
              const unreal = t.unrealised ?? 0;
              const sign = unreal >= 0 ? 'text-bull' : 'text-bear';
              const dirTone = t.direction === 'LONG' ? 'bull' : 'bear';
              const legs = t.legs ?? [];
              return (
                <Fragment key={t.id}>
                  <motion.tr
                    variants={fadeUp}
                    className="border-b border-border/40 hover:bg-bg-hover/30 transition-colors"
                  >
                    <td className="py-2 text-text-tertiary">#{t.id}</td>
                    <td>
                      <span className="uppercase font-semibold text-text-primary">{t.asset}</span>
                      <Chip tone={dirTone as any} className="ml-2">{t.direction}</Chip>
                      <AutoBadge source={t.source} />
                      {legs.length > 0 && (
                        <span className="ml-2 text-[9px] font-mono uppercase tracking-widest text-gold/70">
                          · {legs.length}-LEG
                        </span>
                      )}
                    </td>
                    <td className="text-right text-text-secondary">${t.entry_price.toFixed(2)}</td>
                    <td className="text-right text-text-primary font-semibold">
                      {t.mtm_price !== null ? `$${t.mtm_price.toFixed(2)}` : '—'}
                    </td>
                    <td className="text-right text-text-tertiary">
                      {t.target_price !== null ? `$${t.target_price.toFixed(2)}` : '—'}
                    </td>
                    <td className="text-right text-text-tertiary">
                      {t.stop_price !== null ? `$${t.stop_price.toFixed(2)}` : '—'}
                    </td>
                    <td className={clsx('text-right font-semibold transition-colors', sign)}>
                      {unreal >= 0 ? '+' : ''}${unreal.toFixed(2)}
                    </td>
                    <td className="text-right text-text-secondary">{t.size}</td>
                    <td className="text-right text-text-muted text-[10px]">
                      {fmt.ago ? fmt.ago(t.opened_at) : t.opened_at?.slice(11, 16)}
                    </td>
                    <td className="text-right">
                      <motion.button
                        onClick={async () => {
                          setBusy(t.id);
                          try { await onClose(t.id); } finally { setBusy(null); }
                        }}
                        disabled={busy === t.id}
                        whileHover={{ scale: 1.05 }}
                        whileTap={{ scale: 0.95 }}
                        className="px-2 py-1 text-[10px] font-mono uppercase tracking-widest text-bear hover:bg-bear/15 rounded transition-colors"
                        title="Force close at current market"
                      >
                        {busy === t.id ? '…' : 'Close'}
                      </motion.button>
                    </td>
                  </motion.tr>
                  {legs.map((L, li) => {
                    const legUn = L.unrealised ?? 0;
                    const legSign = legUn >= 0 ? 'text-bull' : 'text-bear';
                    const legDirTone = L.direction === 'LONG' ? 'text-bull' : 'text-bear';
                    return (
                      <motion.tr
                        key={L.id}
                        initial={{ opacity: 0, x: -4 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ duration: 0.28, delay: 0.05 + li * 0.04, ease: [0.16, 1, 0.3, 1] }}
                        className="border-b border-border/20 bg-gradient-to-r from-bg-card/30 via-bg-card/20 to-transparent"
                      >
                        <td className="py-1"></td>
                        <td className="text-[10px] text-text-tertiary pl-4 relative">
                          <span className="absolute left-2 top-0 bottom-0 w-px bg-gradient-to-b from-transparent via-gold/40 to-transparent" />
                          <span className="text-gold/60 mr-1.5">↳</span>
                          <span className="uppercase text-text-secondary">{L.contract}</span>
                          <span className={clsx('ml-2 font-mono', legDirTone)}>{L.direction}</span>
                          <span className="ml-2 text-text-muted">× {L.qty}</span>
                        </td>
                        <td className="text-right text-text-tertiary text-[10px]">${L.entry_price.toFixed(2)}</td>
                        <td className="text-right text-text-secondary text-[10px]">
                          {L.mtm_price !== null ? `$${L.mtm_price.toFixed(2)}` : '—'}
                        </td>
                        <td colSpan={2}></td>
                        <td className={clsx('text-right text-[10px]', legSign)}>
                          {legUn >= 0 ? '+' : ''}${legUn.toFixed(2)}
                        </td>
                        <td colSpan={3}></td>
                      </motion.tr>
                    );
                  })}
                </Fragment>
              );
            })}
          </motion.tbody>
        </table>
      </div>
    </Panel>
  );
}


// ─── Closed history ────────────────────────────────────────────────────────

function ClosedHistory({ rows, total }: { rows: Position[]; total?: number }) {
  if (!rows.length) return (
    <Panel title="Closed Trades" staticMount>
      <div className="text-[11px] font-mono text-text-tertiary p-4 text-center">No closed trades yet.</div>
    </Panel>
  );
  const subtitle = total && total > rows.length
    ? `newest ${rows.length} of ${total} closed`
    : `${rows.length} in history`;
  return (
    <Panel title="Closed Trades" subtitle={subtitle} staticMount>
      <div className="overflow-x-auto max-h-[420px] overflow-y-auto">
        <table className="w-full text-[11px] font-mono tabular">
          <thead className="sticky top-0 bg-bg-elev">
            <tr className="text-text-muted text-[9px] uppercase tracking-widest border-b border-border">
              <th className="text-left py-2">#</th>
              <th className="text-left">Asset · Dir</th>
              <th className="text-right">Entry → Exit</th>
              <th className="text-right">Realised</th>
              <th className="text-right">%</th>
              <th className="text-right">Reason</th>
              <th className="text-right">Closed</th>
            </tr>
          </thead>
          <motion.tbody variants={staggerTight} initial="hidden" animate="show">
            {rows.map(t => {
              const r = t.realised ?? 0;
              const rPct = t.realised_pct ?? 0;
              const sign = r >= 0 ? 'text-bull' : 'text-bear';
              return (
                <motion.tr
                  key={t.id}
                  variants={fadeUp}
                  className="border-b border-border/40 hover:bg-bg-hover/30 transition-colors"
                >
                  <td className="py-1.5 text-text-tertiary">#{t.id}</td>
                  <td>
                    <span className="uppercase">{t.asset}</span>
                    <span className={clsx('ml-2 text-[9px]', t.direction === 'LONG' ? 'text-bull' : 'text-bear')}>
                      {t.direction}
                    </span>
                    <AutoBadge source={t.source} />
                  </td>
                  <td className="text-right text-text-secondary">
                    ${t.entry_price.toFixed(2)} → ${t.exit_price?.toFixed(2)}
                  </td>
                  <td className={clsx('text-right font-semibold', sign)}>
                    {r >= 0 ? '+' : ''}${r.toFixed(2)}
                  </td>
                  <td className={clsx('text-right', sign)}>
                    {rPct >= 0 ? '+' : ''}{rPct.toFixed(2)}%
                  </td>
                  <td className="text-right text-text-tertiary text-[10px] uppercase tracking-widest">
                    {(t.close_reason || '—').replace('_', ' ')}
                  </td>
                  <td className="text-right text-text-muted text-[10px]">
                    {fmt.ago ? fmt.ago(t.closed_at) : t.closed_at?.slice(11, 16)}
                  </td>
                </motion.tr>
              );
            })}
          </motion.tbody>
        </table>
      </div>
    </Panel>
  );
}


// ─── Performance panel ─────────────────────────────────────────────────────

function PerformancePanel({ perf, onClear }: { perf: Performance | null; onClear: () => void }) {
  if (!perf) return <Panel title="Performance" staticMount><SkeletonRows rows={4} /></Panel>;
  const totalTone = perf.total_pnl >= 0 ? 'bull' : 'bear';
  const sharpeTone =
    perf.sharpe_annualised === null ? 'neut' :
    perf.sharpe_annualised > 1.0 ? 'bull' :
    perf.sharpe_annualised < 0 ? 'bear' : 'neut';

  // Build mini SVG equity curve
  const eq = perf.equity_curve || [];
  const sparkPts = (() => {
    if (eq.length < 2) return '';
    const ys = eq.map(e => e.cum_pnl);
    const min = Math.min(0, ...ys);
    const max = Math.max(0.001, ...ys);
    const w = 100, h = 40;
    return eq.map((e, i) => {
      const x = (i / (eq.length - 1)) * w;
      const y = h - ((e.cum_pnl - min) / (max - min)) * h;
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    }).join(' ');
  })();

  // Build matching area-fill path under the curve
  const sparkArea = (() => {
    if (eq.length < 2) return '';
    const ys = eq.map(e => e.cum_pnl);
    const min = Math.min(0, ...ys);
    const max = Math.max(0.001, ...ys);
    const w = 100, h = 40;
    const pts = eq.map((e, i) => {
      const x = (i / (eq.length - 1)) * w;
      const y = h - ((e.cum_pnl - min) / (max - min)) * h;
      return [x, y] as const;
    });
    const first = pts[0]; const last = pts[pts.length - 1];
    return `M ${first[0]},${h} L ${pts.map(p => `${p[0]},${p[1]}`).join(' L ')} L ${last[0]},${h} Z`;
  })();

  return (
    <Panel
      title="Performance"
      subtitle="closed trades only · realised PnL"
      accent={totalTone as any}
      staticMount
      right={
        <motion.button
          onClick={onClear}
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
          className="flex items-center gap-1.5 px-2 py-1 rounded text-[10px] font-mono uppercase tracking-widest text-text-tertiary hover:text-bear hover:bg-bear/10 transition-colors"
          title="Clear closed-trade history"
        >
          <Trash2 className="w-3 h-3" />
          Reset
        </motion.button>
      }
    >
      <motion.div
        variants={staggerTight}
        initial="hidden"
        animate="show"
        className="grid grid-cols-4 gap-3 mb-4"
      >
        {[
          <Stat label="Total PnL" tone={totalTone as any}
                value={`${perf.total_pnl >= 0 ? '+' : ''}$${perf.total_pnl.toFixed(2)}`} />,
          <Stat label="Trades"    value={`${perf.total_trades}`} />,
          <Stat label="Win Rate"  tone={perf.win_rate_pct >= 50 ? 'bull' : 'bear'}
                value={`${perf.win_rate_pct.toFixed(1)}%`}
                sub={`${perf.wins}W / ${perf.losses}L${perf.scratches ? ` / ${perf.scratches}S` : ''}`} />,
          <Stat label="Sharpe (ann.)" tone={sharpeTone as any}
                value={perf.sharpe_annualised === null ? '—' : perf.sharpe_annualised.toFixed(2)} />,
        ].map((node, i) => (
          <motion.div key={i} variants={scaleIn}>{node}</motion.div>
        ))}
      </motion.div>

      <motion.div
        variants={staggerTight}
        initial="hidden"
        animate="show"
        className="grid grid-cols-4 gap-3 mb-4"
      >
        {[
          <Stat label="Avg Win"        tone="bull" value={`+$${perf.avg_win.toFixed(2)}`} />,
          <Stat label="Avg Loss"       tone="bear" value={`$${perf.avg_loss.toFixed(2)}`} />,
          <Stat label="Profit Factor"  tone={(perf.profit_factor ?? 0) > 1 ? 'bull' : 'bear'}
                value={perf.profit_factor === null ? '—' : perf.profit_factor.toFixed(2)} />,
          <Stat label="Max Drawdown"   tone="bear" value={`-$${perf.max_drawdown.toFixed(2)}`} />,
        ].map((node, i) => (
          <motion.div key={i} variants={scaleIn}>{node}</motion.div>
        ))}
      </motion.div>

      {/* Equity curve mini-spark — area + draw-in stroke */}
      {eq.length >= 2 && (
        <motion.div
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.25, duration: 0.32 }}
          className="mt-4 pt-3 border-t border-border/40"
        >
          <div className="text-[9px] font-mono uppercase tracking-widest text-text-muted mb-2 flex items-center justify-between">
            <span>Cumulative PnL · {eq.length} closed trades</span>
            <span className="text-text-tertiary">{(perf.total_pnl >= 0 ? '+$' : '-$') + Math.abs(perf.total_pnl).toFixed(2)} total</span>
          </div>
          <svg viewBox="0 0 100 40" className="w-full h-20" preserveAspectRatio="none">
            <defs>
              <linearGradient id="eqfill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%"  stopColor={totalTone === 'bull' ? '#10d997' : '#ff4d6d'} stopOpacity="0.28" />
                <stop offset="100%" stopColor={totalTone === 'bull' ? '#10d997' : '#ff4d6d'} stopOpacity="0" />
              </linearGradient>
            </defs>
            {/* zero baseline */}
            {(() => {
              const ys = eq.map(e => e.cum_pnl);
              const min = Math.min(0, ...ys);
              const max = Math.max(0.001, ...ys);
              const y0  = 40 - ((0 - min) / (max - min)) * 40;
              return <line x1="0" x2="100" y1={y0} y2={y0} stroke="#2a3a5e" strokeWidth="0.3" strokeDasharray="1 1" />;
            })()}
            {/* fill area */}
            <motion.path
              d={sparkArea}
              fill="url(#eqfill)"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.5, delay: 0.55 }}
            />
            {/* stroke — draws in left-to-right */}
            <motion.polyline
              points={sparkPts}
              fill="none"
              stroke={totalTone === 'bull' ? '#10d997' : '#ff4d6d'}
              strokeWidth="0.9"
              strokeLinecap="round"
              strokeLinejoin="round"
              initial={{ pathLength: 0, opacity: 0 }}
              animate={{ pathLength: 1, opacity: 1 }}
              transition={{ duration: 0.9, delay: 0.35, ease: [0.16, 1, 0.3, 1] }}
            />
            {/* terminal dot */}
            {eq.length >= 2 && (() => {
              const ys = eq.map(e => e.cum_pnl);
              const min = Math.min(0, ...ys);
              const max = Math.max(0.001, ...ys);
              const last = eq[eq.length - 1];
              const x = 100;
              const y = 40 - ((last.cum_pnl - min) / (max - min)) * 40;
              return (
                <motion.circle
                  cx={x} cy={y} r="0.9"
                  fill={totalTone === 'bull' ? '#10d997' : '#ff4d6d'}
                  stroke="#fff" strokeWidth="0.2"
                  initial={{ opacity: 0, scale: 0 }}
                  animate={{ opacity: 1, scale: 1 }}
                  transition={{ duration: 0.3, delay: 1.2 }}
                />
              );
            })()}
          </svg>
        </motion.div>
      )}

      {perf.best_trade && perf.worst_trade && (
        <motion.div
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.45, duration: 0.32 }}
          className="mt-3 grid grid-cols-2 gap-3 text-[10px] font-mono"
        >
          <div className="p-2 bg-bg-card/40 rounded transition-colors hover:bg-bg-card/70">
            <span className="text-text-muted uppercase tracking-widest">Best</span>
            <div className={perf.best_trade.pnl >= 0 ? 'text-bull' : 'text-bear'}>
              #{perf.best_trade.id} {perf.best_trade.asset} {perf.best_trade.pnl >= 0 ? '+$' : '-$'}{Math.abs(perf.best_trade.pnl).toFixed(2)}
            </div>
          </div>
          <div className="p-2 bg-bg-card/40 rounded transition-colors hover:bg-bg-card/70">
            <span className="text-text-muted uppercase tracking-widest">Worst</span>
            <div className={perf.worst_trade.pnl >= 0 ? 'text-bull' : 'text-bear'}>
              #{perf.worst_trade.id} {perf.worst_trade.asset} {perf.worst_trade.pnl >= 0 ? '+$' : '-$'}{Math.abs(perf.worst_trade.pnl).toFixed(2)}
            </div>
          </div>
        </motion.div>
      )}
    </Panel>
  );
}


// ─── Run-engine button: fires ab_test.tick() on demand ─────────────────────

function RunEngineButton({ onPushed }: { onPushed: () => void }) {
  const [busy, setBusy] = useState(false);
  const [flash, setFlash] = useState<'ok' | 'err' | null>(null);
  const [summary, setSummary] = useState<string | null>(null);

  const fire = async () => {
    setBusy(true); setFlash(null); setSummary(null);
    try {
      const out = await api.regimeABTick();
      const data = (out as any)?.data ?? out;
      const pooledPushed = data?.pushed?.pooled?.length ?? 0;
      const gatedPushed  = data?.pushed?.gated?.length  ?? 0;
      const errs = data?.errors?.length ?? 0;
      if (errs > 0 && pooledPushed + gatedPushed === 0) {
        setFlash('err');
        setSummary(`engine errored (${errs}); see logs`);
      } else {
        setFlash('ok');
        setSummary(`pushed ${pooledPushed} pooled · ${gatedPushed} gated`);
      }
      onPushed();
      setTimeout(() => { setFlash(null); setSummary(null); }, 5000);
    } catch (e: any) {
      setFlash('err'); setSummary(e?.message || String(e));
      setTimeout(() => { setFlash(null); setSummary(null); }, 5000);
    } finally { setBusy(false); }
  };

  return (
    <Panel
      title="Live Engine"
      subtitle="manual A/B tick · pushes pooled + gated arms at live prices"
      accent="gold"
      bodyClassName="!p-3"
      staticMount
      right={
        <span className="text-[9px] font-mono uppercase tracking-widest text-text-tertiary">
          daily auto-push · 24h cadence
        </span>
      }
    >
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex flex-col gap-1">
          <span className="text-[10px] font-mono uppercase tracking-widest text-text-muted">
            Fire the regime engine now
          </span>
          <span className="text-[11px] font-mono text-text-tertiary">
            Generates a fresh recommendation and opens paper positions on both A/B arms at current spread prices.
          </span>
        </div>
        <div className="flex items-center gap-3">
          <AnimatePresence>
            {flash && summary && (
              <motion.span
                key={summary}
                initial={{ opacity: 0, x: -4 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0 }}
                className={clsx(
                  'text-[11px] font-mono',
                  flash === 'ok' ? 'text-bull' : 'text-bear',
                )}
              >
                {flash === 'ok' ? '✓ ' : '✕ '}{summary}
              </motion.span>
            )}
          </AnimatePresence>
          <motion.button
            onClick={fire}
            disabled={busy}
            whileHover={!busy ? { y: -1 } : {}}
            whileTap={!busy ? { scale: 0.97 } : {}}
            transition={{ duration: 0.16, ease: [0.22, 1, 0.36, 1] }}
            className={clsx(
              'flex items-center gap-2 px-4 py-2 rounded-md font-mono uppercase tracking-widest text-[11px] font-bold transition-colors',
              busy
                ? 'bg-gold/40 text-bg cursor-wait'
                : 'bg-gold text-bg hover:bg-gold-bright shadow-md',
            )}
            title="Manually trigger ab_test.tick() — pushes today's recommendation to both A/B arms"
          >
            <Zap className={clsx('w-3.5 h-3.5', busy && 'animate-pulse')} />
            {busy ? 'firing…' : 'Run engine now'}
          </motion.button>
        </div>
      </div>
    </Panel>
  );
}


// ─── KPI tile ──────────────────────────────────────────────────────────────

type KpiTone = 'plain' | 'bull' | 'bear' | 'gold' | 'blue';
const kpiColor: Record<KpiTone, string> = {
  plain: 'text-text-primary', bull: 'text-bull', bear: 'text-bear',
  gold: 'text-gold', blue: 'text-accent-blue',
};

function Kpi({ label, value, sub, tone = 'plain', icon }: {
  label: string; value: string; sub?: string; tone?: KpiTone; icon?: React.ReactNode;
}) {
  return (
    <div className="rounded-lg border border-border/50 bg-bg-surface/40 px-3.5 py-3 transition-colors hover:border-border-strong/60">
      <div className="flex items-center gap-1.5 text-[9px] font-mono uppercase tracking-widest text-text-muted">
        {icon}{label}
      </div>
      <div className={clsx('mt-1.5 text-[22px] font-display font-extrabold tabular leading-none', kpiColor[tone])}>
        {value}
      </div>
      {sub && <div className="mt-1 text-[9.5px] font-mono text-text-tertiary truncate">{sub}</div>}
    </div>
  );
}


// ─── Top-level view ────────────────────────────────────────────────────────

export function PaperView({ tradeIdea }: { tradeIdea: any }) {
  const [refreshTick, setRefreshTick] = useState(0);
  const bump = useCallback(() => setRefreshTick(t => t + 1), []);

  // Poll positions every 15s, perf every 30s. Bump tick on push/close for instant refresh.
  // The generated API types mark fields optional that this view treats as present;
  // adapt the fetchers' return types to the local row/perf shapes.
  const { data: positions, refetch: refetchPos } =
    usePolling<Position[]>(api.paperPositions as unknown as () => Promise<Position[]>,
      15_000, [refreshTick]);
  const { data: perf, refetch: refetchPerf } =
    usePolling<Performance>(api.paperPerformance as unknown as () => Promise<Performance>,
      30_000, [refreshTick]);

  const [srcFilter, setSrcFilter] = useState<SrcFilter>('all');
  const matchesSrc = useCallback(
    (p: Position) => srcFilter === 'all' || (srcFilter === 'auto' ? isAuto(p) : !isAuto(p)),
    [srcFilter],
  );

  const allOpen   = useMemo(() => (positions ?? []).filter(p => p.status === 'OPEN'), [positions]);
  const allClosed = useMemo(() => (positions ?? []).filter(p => p.status === 'CLOSED'), [positions]);
  const open   = useMemo(() => allOpen.filter(matchesSrc), [allOpen, matchesSrc]);
  const closed = useMemo(() => allClosed.filter(matchesSrc), [allClosed, matchesSrc]);
  // Source-filter counts over the whole loaded book (open + closed), not just open.
  const autoBookCount = useMemo(() => (positions ?? []).filter(isAuto).length, [positions]);
  const bookLoaded = allOpen.length + allClosed.length;

  const handleClose = useCallback(async (id: number) => {
    try { await api.paperClose(id); } finally { bump(); }
  }, [bump]);

  const handleClear = useCallback(async () => {
    if (!confirm('Reset all closed paper trades? Open positions are NOT affected.')) return;
    await api.paperClear('closed'); bump();
  }, [bump]);

  const handlePush = useCallback(async (_size: number) => { bump(); }, [bump]);

  // KPIs reflect the whole book from the authoritative performance endpoint
  // (closed count via perf.total_trades, not the capped positions list).
  const openCount = allOpen.length;
  const closedCount = perf?.total_trades ?? allClosed.length;
  const realisedTotal = perf?.total_pnl ?? 0;
  const realisedTone: KpiTone = realisedTotal >= 0 ? 'bull' : 'bear';
  const pf = perf?.profit_factor ?? null;
  const wr = perf?.win_rate_pct ?? null;

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Paper Book"
        title="Paper trading book"
        desc={<>The live forward book: the regime engine's <span className="text-accent-blue">A/B arms</span>{' '}
          (pooled vs gated) plus manual and <span className="text-accent-blue">auto-desk</span> pushes, marked to
          market every minute on the live tape. Exits on the tuned rule — TP halfway-to-fair · SL 2.5σ · 30-day
          time-stop. Win rate is over decisive trades (break-even scratches excluded).</>}
        badges={
          <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-md border border-bull/30 bg-bull/5 text-bull text-[9px] font-mono uppercase tracking-wider">
            <span className="w-1.5 h-1.5 rounded-full bg-bull animate-pulse-soft" /> Live MTM · 60s
          </span>
        }
      />

      {/* KPI strip — the book at a glance */}
      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3">
        <Kpi label="Open" value={`${openCount}`} sub="positions now" tone="blue"
             icon={<Wallet className="w-3 h-3 text-accent-blue" />} />
        <Kpi label="Closed" value={`${closedCount}`} sub="trades in book" tone="plain"
             icon={<Activity className="w-3 h-3 text-text-muted" />} />
        <Kpi label="Realised PnL" tone={realisedTone}
             value={perf ? `${realisedTotal >= 0 ? '+$' : '-$'}${Math.abs(realisedTotal).toLocaleString(undefined, { maximumFractionDigits: 0 })}` : '—'}
             sub={perf?.total_pnl_pct != null ? `${perf.total_pnl_pct >= 0 ? '+' : ''}${perf.total_pnl_pct.toFixed(2)}% on NAV` : 'realised only'}
             icon={realisedTotal >= 0 ? <TrendingUp className="w-3 h-3 text-bull" /> : <TrendingDown className="w-3 h-3 text-bear" />} />
        <Kpi label="Win rate" tone={wr == null ? 'plain' : wr >= 50 ? 'bull' : 'bear'}
             value={wr == null ? '—' : `${wr.toFixed(1)}%`}
             sub={perf ? `${perf.wins}W / ${perf.losses}L${perf.scratches ? ` / ${perf.scratches}S` : ''}` : 'decisive trades'} />
        <Kpi label="Profit factor" tone={pf == null ? 'plain' : pf >= 1 ? 'gold' : 'bear'}
             value={pf == null ? '—' : pf.toFixed(2)}
             sub={perf?.avg_holding_days != null ? `~${perf.avg_holding_days.toFixed(0)}d avg hold` : 'gross win / loss'} />
        <Kpi label="Sharpe / Max DD"
             tone={perf?.sharpe_annualised == null ? 'plain' : perf.sharpe_annualised >= 1 ? 'bull' : perf.sharpe_annualised < 0 ? 'bear' : 'plain'}
             value={perf?.sharpe_annualised == null ? '—' : perf.sharpe_annualised.toFixed(2)}
             sub={perf ? `-$${Math.abs(perf.max_drawdown).toLocaleString(undefined, { maximumFractionDigits: 0 })} max DD` : 'annualised'} />
      </div>

      {/* Manual A/B engine trigger + the suggested trade to push */}
      <RunEngineButton onPushed={bump} />
      <SuggestedTrade idea={tradeIdea} onPush={handlePush} />

      {/* Positions */}
      <SectionHeader
        accent="blue"
        eyebrow="Book · 01"
        title="Open positions"
        desc="Marked to market every minute on the live tape; each row exits on the tuned rule. Spread trades expand to their per-leg fills."
        right={
          <SourceFilter value={srcFilter} onChange={setSrcFilter}
            autoCount={autoBookCount} total={bookLoaded} />
        }
      />
      <OpenPositions rows={open} onClose={handleClose} />

      {/* Performance + closed history */}
      <SectionHeader
        accent="gold"
        eyebrow="Book · 02"
        title="Performance & closed history"
        desc="Realised PnL over closed trades only. Sharpe is holding-period-aware (annualised by average hold, not naive √252); win rate excludes break-even scratches."
      />
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4 items-start">
        <PerformancePanel perf={perf} onClear={handleClear} />
        <ClosedHistory rows={closed} total={perf?.total_trades} />
      </div>
    </div>
  );
}
