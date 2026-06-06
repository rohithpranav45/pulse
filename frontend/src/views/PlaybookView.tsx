import { useState } from 'react';
import { Panel } from '@/components/ui/Panel';
import { Chip } from '@/components/ui/Chip';
import { ScoreBar } from '@/components/ui/ScoreBar';
import { CASE_STUDIES, CaseStudy } from '@/lib/caseStudies';
import { Award, BookOpen, TrendingUp, TrendingDown, Calendar, Lightbulb, ChevronRight, History } from 'lucide-react';
import clsx from 'clsx';

function CaseStudyCard({ study, onOpen }: { study: CaseStudy; onOpen: () => void }) {
  const moveTone: 'bull' | 'bear' = study.priceMove.pctChange >= 0 ? 'bull' : 'bear';
  const verdictTone =
    study.pulseDirection === 'bull' ? 'bull' :
    study.pulseDirection === 'bear' ? 'bear' : 'neut';

  return (
    <button
      onClick={onOpen}
      className="text-left group"
    >
      <div className={clsx(
        'panel p-4 transition-all hover:scale-[1.01]',
        'border-2',
        verdictTone === 'bull' && 'hover:border-bull/50',
        verdictTone === 'bear' && 'hover:border-bear/50',
      )}>
        <div className="flex items-start justify-between mb-3">
          <div className="min-w-0 flex-1">
            <div className="font-display font-extrabold text-xl text-text-primary tracking-wider truncate">
              {study.title}
            </div>
            <div className="text-[11px] font-mono text-text-tertiary tabular">{study.period}</div>
          </div>
          <ChevronRight className="w-4 h-4 text-text-muted group-hover:text-gold group-hover:translate-x-1 transition-all" />
        </div>

        <div className="text-[12px] text-text-secondary leading-relaxed mb-3">
          {study.subtitle}
        </div>

        <div className="grid grid-cols-2 gap-3 pt-3 border-t border-border/40">
          <div>
            <div className="text-[9px] font-mono uppercase tracking-widest text-text-muted">Price Move</div>
            <div className={clsx(
              'text-xl font-display font-bold tabular',
              moveTone === 'bull' ? 'text-bull' : 'text-bear',
            )}>
              {moveTone === 'bull' ? '+' : ''}{study.priceMove.pctChange.toFixed(0)}%
            </div>
            <div className="text-[9px] font-mono text-text-muted tabular">
              ${study.priceMove.from} → ${study.priceMove.to}
            </div>
          </div>
          <div className="text-right">
            <div className="text-[9px] font-mono uppercase tracking-widest text-text-muted">PULSE Would Flash</div>
            <Chip tone={verdictTone}>{study.pulseVerdict.label}</Chip>
            <div className="text-[9px] font-mono text-text-muted mt-1 tabular">
              score {study.pulseVerdict.score >= 0 ? '+' : ''}{study.pulseVerdict.score} · {study.pulseVerdict.conviction}
            </div>
          </div>
        </div>
      </div>
    </button>
  );
}

function CaseStudyDetail({ study }: { study: CaseStudy }) {
  const moveTone: 'bull' | 'bear' = study.priceMove.pctChange >= 0 ? 'bull' : 'bear';
  const verdictTone: 'bull' | 'bear' | 'neut' = study.pulseDirection;

  return (
    <div className="space-y-4">
      {/* Hero */}
      <Panel accent={verdictTone} source="static_reference">
        <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-4">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-2">
              <History className="w-5 h-5 text-gold" />
              <span className="text-[10px] font-mono uppercase tracking-widest text-text-tertiary">
                {study.curriculumRef}
              </span>
            </div>
            <h2 className="font-display font-extrabold text-3xl tracking-wider mb-1">{study.title}</h2>
            <div className="text-[13px] text-text-secondary mb-2">{study.subtitle}</div>
            <div className="text-[11px] font-mono text-text-muted tabular">{study.period}</div>
          </div>

          <div className="grid grid-cols-2 gap-4 md:gap-6 flex-shrink-0">
            <div>
              <div className="text-[9px] font-mono uppercase tracking-widest text-text-muted">Brent Move</div>
              <div className={clsx(
                'text-3xl font-display font-extrabold tabular',
                moveTone === 'bull' ? 'text-bull' : 'text-bear',
              )}>
                {moveTone === 'bull' ? <TrendingUp className="w-5 h-5 inline mr-1" /> : <TrendingDown className="w-5 h-5 inline mr-1" />}
                {study.priceMove.pctChange >= 0 ? '+' : ''}{study.priceMove.pctChange.toFixed(0)}%
              </div>
              <div className="text-[10px] font-mono text-text-tertiary tabular">
                ${study.priceMove.from} → ${study.priceMove.to}
              </div>
            </div>
            <div>
              <div className="text-[9px] font-mono uppercase tracking-widest text-text-muted">PULSE Verdict</div>
              <Chip tone={verdictTone}>{study.pulseVerdict.label}</Chip>
              <div className="text-[11px] font-mono text-text-secondary tabular mt-1">
                score {study.pulseVerdict.score >= 0 ? '+' : ''}{study.pulseVerdict.score.toFixed(2)} · {study.pulseVerdict.conviction}
              </div>
            </div>
          </div>
        </div>

        <div className="mt-4 pt-3 border-t border-border/40 flex items-start gap-2">
          <Award className={clsx(
            'w-4 h-4 flex-shrink-0 mt-0.5',
            verdictTone === 'bull' ? 'text-bull' : verdictTone === 'bear' ? 'text-bear' : 'text-neut',
          )} />
          <span className="text-[12px] text-text-secondary leading-relaxed italic">
            {study.pulseWouldHaveCalled}
          </span>
        </div>
      </Panel>

      {/* Key metrics grid + Indicator breakdown */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <Panel title="Key Market Conditions" subtitle="snapshot at the inflection" source="static_reference">
          <div className="grid grid-cols-2 gap-3">
            {study.keyMetrics.map((m, i) => {
              const toneClass =
                m.tone === 'bull' ? 'border-bull/30 bg-bull-soft' :
                m.tone === 'bear' ? 'border-bear/30 bg-bear-soft' :
                m.tone === 'gold' ? 'border-gold/30 bg-gold-soft' :
                'border-border/60 bg-bg-card/40';
              return (
                <div key={i} className={clsx('p-3 rounded border', toneClass)}>
                  <div className="text-[9px] font-mono uppercase tracking-widest text-text-muted">{m.label}</div>
                  <div className={clsx(
                    'text-sm font-display font-bold tabular',
                    m.tone === 'bull' && 'text-bull',
                    m.tone === 'bear' && 'text-bear',
                    m.tone === 'gold' && 'text-gold',
                    !m.tone && 'text-text-primary',
                  )}>
                    {m.value}
                  </div>
                  {m.detail && (
                    <div className="text-[9px] font-mono text-text-tertiary mt-0.5 leading-snug">{m.detail}</div>
                  )}
                </div>
              );
            })}
          </div>
        </Panel>

        <Panel title="What PULSE Would Have Said" subtitle="indicator-by-indicator breakdown" accent={verdictTone} source="static_reference">
          <div className="space-y-2">
            {study.indicators.map((ind, i) => (
              <div key={i} className="grid grid-cols-[88px_36px_46px_1fr] items-center gap-2 text-[10.5px] font-mono tabular border-b border-border/30 pb-2 last:border-b-0">
                <span className="text-text-secondary truncate">{ind.name}</span>
                <span className="text-text-muted text-right">{(ind.weight * 100).toFixed(0)}%</span>
                <span className={clsx(
                  'text-center font-bold',
                  ind.tone === 'bull' && 'text-bull',
                  ind.tone === 'bear' && 'text-bear',
                  ind.tone === 'neut' && 'text-neut',
                )}>
                  {ind.score >= 0 ? '+' : ''}{ind.score}
                </span>
                <span className="text-text-tertiary text-[10px] leading-snug">{ind.reading}</span>
              </div>
            ))}
          </div>
          <div className="mt-3 pt-3 border-t border-border/40">
            <ScoreBar score={study.pulseVerdict.score} height={8} showLabels />
            <div className="mt-2 text-center">
              <span className="text-[10px] font-mono text-text-muted uppercase tracking-widest">composite</span>
              <span className={clsx(
                'ml-2 text-[14px] font-display font-bold tabular',
                verdictTone === 'bull' ? 'text-bull' : verdictTone === 'bear' ? 'text-bear' : 'text-neut',
              )}>
                {study.pulseVerdict.score >= 0 ? '+' : ''}{study.pulseVerdict.score.toFixed(2)} → {study.pulseVerdict.label}
              </span>
            </div>
          </div>
        </Panel>
      </div>

      {/* Timeline */}
      <Panel title="Timeline" subtitle="how the trade played out" source="static_reference" right={<Calendar className="w-4 h-4 text-text-tertiary" />}>
        <div className="relative">
          <div className="absolute left-[80px] top-0 bottom-0 w-px bg-border" />
          <div className="space-y-3">
            {study.timeline.map((t, i) => (
              <div key={i} className="grid grid-cols-[72px_24px_1fr_160px] items-center gap-3 text-[11px]">
                <span className="text-right font-mono tabular text-text-tertiary text-[10px]">{t.date}</span>
                <div className="w-2 h-2 rounded-full bg-gold mx-auto" style={{ boxShadow: '0 0 8px rgba(212,175,55,0.5)' }} />
                <span className="text-text-secondary leading-snug">{t.event}</span>
                {t.priceImpact && (
                  <span className="text-right text-[10px] font-mono tabular text-text-tertiary">{t.priceImpact}</span>
                )}
              </div>
            ))}
          </div>
        </div>
      </Panel>

      {/* Lessons */}
      <Panel title="Lessons" subtitle="what to remember" accent="gold" source="static_reference" right={<Lightbulb className="w-4 h-4 text-gold" />}>
        <ul className="space-y-2">
          {study.lessons.map((lesson, i) => (
            <li key={i} className="flex items-start gap-2 text-[12px] text-text-secondary leading-relaxed">
              <span className="font-display font-bold text-gold mt-0.5 flex-shrink-0">{i + 1}.</span>
              <span>{lesson}</span>
            </li>
          ))}
        </ul>
      </Panel>
    </div>
  );
}

export function PlaybookView() {
  const [activeId, setActiveId] = useState<string | null>(null);
  const active = activeId ? CASE_STUDIES.find(c => c.id === activeId) : null;

  if (active) {
    return (
      <div className="space-y-4">
        <button
          onClick={() => setActiveId(null)}
          className="flex items-center gap-1.5 text-[11px] font-mono uppercase tracking-widest text-text-tertiary hover:text-gold transition-colors"
        >
          ← back to playbook index
        </button>
        <CaseStudyDetail study={active} />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <Panel
        title="Historical Playbook"
        subtitle="four case studies from chapter 8 — how PULSE would have read each"
        accent="gold"
        source="static_reference"
        right={<BookOpen className="w-4 h-4 text-text-tertiary" />}
      >
        <p className="text-[12px] text-text-secondary leading-relaxed">
          The four oil events every macro analyst is expected to know. For each, we show the
          live market conditions, the indicator readings PULSE's signal engine would have
          produced at the time, and the lessons that drive how those indicators are weighted
          today. <span className="text-gold">Click any card to dive in.</span>
        </p>
      </Panel>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {CASE_STUDIES.map(study => (
          <CaseStudyCard key={study.id} study={study} onOpen={() => setActiveId(study.id)} />
        ))}
      </div>
    </div>
  );
}
