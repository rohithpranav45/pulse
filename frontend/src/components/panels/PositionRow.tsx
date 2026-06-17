import clsx from 'clsx';
import { Chip } from '@/components/ui/Chip';
import { fmt } from '@/lib/fmt';
import type { PaperPosition } from '@/lib/api-types';

/**
 * Compact 1-row paper position renderer. Used by the DESK landing strip and
 * any other view that needs a thin "what am I holding" line. Intentionally
 * flex-based (not a table cell) so it can drop into card layouts. The full
 * PaperView table keeps its own per-leg expandable rows — different layout
 * primitive, same data.
 */
export function PositionRow({ p }: { p: PaperPosition }) {
  const dir = (p.direction ?? '').toUpperCase();
  const dirTone = dir === 'LONG' ? 'bull' : 'bear';
  const unreal = p.unrealised ?? 0;
  const sign = unreal >= 0 ? 'text-bull' : 'text-bear';
  const legs = p.legs ?? [];

  return (
    <div className="grid grid-cols-[1fr_70px_70px_80px_70px] gap-3 items-center py-1.5 px-2 border-b border-border/30 text-[11px] font-mono tabular hover:bg-bg-hover/30 transition-colors">
      <div className="flex items-center gap-2 min-w-0">
        <span className="text-text-tertiary text-[10px]">#{p.id}</span>
        <span className="uppercase font-semibold text-text-primary truncate">{p.asset ?? '—'}</span>
        <Chip tone={dirTone as any}>{dir || '—'}</Chip>
        {legs.length > 0 && (
          <span className="text-[9px] font-mono uppercase tracking-widest text-gold/70 flex-shrink-0">
            {legs.length}-LEG
          </span>
        )}
      </div>
      <div className="text-right text-text-secondary">
        ${fmt.price(p.entry_price ?? 0)}
      </div>
      <div className="text-right text-text-primary font-semibold">
        {p.mtm_price !== null && p.mtm_price !== undefined ? `$${fmt.price(p.mtm_price)}` : '—'}
      </div>
      <div className={clsx('text-right font-semibold', sign)}>
        {unreal >= 0 ? '+' : ''}${unreal.toFixed(2)}
      </div>
      <div className="text-right text-text-muted text-[10px]">
        {p.opened_at ? fmt.ago(p.opened_at) : '—'}
      </div>
    </div>
  );
}

export function PositionRowHeader() {
  return (
    <div className="grid grid-cols-[1fr_70px_70px_80px_70px] gap-3 items-center px-2 py-1 text-[9px] font-mono uppercase tracking-widest text-text-muted border-b border-border">
      <span>Asset · Dir</span>
      <span className="text-right">Entry</span>
      <span className="text-right">MTM</span>
      <span className="text-right">Unrealised</span>
      <span className="text-right">Opened</span>
    </div>
  );
}
