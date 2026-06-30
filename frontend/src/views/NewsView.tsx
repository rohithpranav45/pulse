import { useState } from 'react';
import { GeoLiveAlertsPanel } from '@/components/panels/GeoLiveAlertsPanel';
import { GeoMapPanel } from '@/components/panels/GeoMapPanel';
import { LiveHeadlinesPanel } from '@/components/panels/LiveHeadlinesPanel';
import { NewsImpactPanel } from '@/components/panels/NewsImpactPanel';
import { NewsFactorPanel } from '@/components/panels/NewsFactorPanel';
import { GeoImpactPanel } from '@/components/panels/GeoImpactPanel';
import { GeoAnalogPanel } from '@/components/panels/GeoAnalogPanel';

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
  // Clicking an asset on the geo map pre-fills the analog lookup below.
  const [analogPrefill, setAnalogPrefill] = useState<string | null>(null);
  return (
    <div className="space-y-4">
      <GeoLiveAlertsPanel />
      <GeoMapPanel onSelectHeadline={setAnalogPrefill} />
      <LiveHeadlinesPanel />
      <NewsImpactPanel />
      <NewsFactorPanel />
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <GeoImpactPanel />
        <GeoAnalogPanel prefill={analogPrefill} />
      </div>
      <div className="text-[10px] font-mono text-text-muted leading-relaxed px-1">
        Geo panels: location-news → physical asset (chokepoint/refinery/pipeline) → price-node impact,
        graded by a per-node event study over the 2026 Hormuz-war GDELT corpus × the node tape (LLM
        geo-extraction via free Groq). The analog box retrieves the nearest past geo-events. Single
        episode ⇒ read direction, not exact p-values.
      </div>
      <div className="text-[10px] font-mono text-text-muted leading-relaxed px-1">
        Event-study betas fitted over the GDELT historical corpus × the /Data Brent/WTI tape.
        Sentiment is a deterministic crude-polarity lexicon (auditable, not a learned model);
        the factor is Groq zero-shot with a keyword fallback. Most factors sit on a labelled
        prior until the corpus carries enough significant evidence — by design.
      </div>
    </div>
  );
}
