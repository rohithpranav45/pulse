import { NewsImpactPanel } from '@/components/panels/NewsImpactPanel';
import { NewsFactorPanel } from '@/components/panels/NewsFactorPanel';

/**
 * News Impact tab — one step deeper than headline sentiment.
 *
 * Every oil headline is classified into a price-driving FACTOR (Groq zero-shot +
 * keyword fallback), given a signed crude-polarity sentiment, and turned into an
 * expected Brent % move via an empirical event study of how that factor has
 * historically moved the tape (+1h/+4h/+1d, regime-gated). The number shown is a
 * MEASURED beta only when it cleared a t-stat/min-N gate, else a labelled prior —
 * the same prior-then-learn honesty as the per-spread gate.
 *
 * Backend: backend/research/news_impact/{corpus,classify,event_study,impact}.py
 */
export function NewsView() {
  return (
    <div className="space-y-4">
      <NewsImpactPanel />
      <NewsFactorPanel />
      <div className="text-[10px] font-mono text-text-muted leading-relaxed px-1">
        Event-study betas fitted over the GDELT historical corpus × the /Data Brent/WTI tape.
        Sentiment is a deterministic crude-polarity lexicon (auditable, not a learned model);
        the factor is Groq zero-shot with a keyword fallback. Most factors sit on a labelled
        prior until the corpus carries enough significant evidence — by design.
      </div>
    </div>
  );
}
