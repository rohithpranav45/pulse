import { useState } from 'react';
import { PageHeader, SectionHeader } from '@/components/ui/SectionHeader';
import { GeoLiveAlertsPanel } from '@/components/panels/GeoLiveAlertsPanel';
import { GeoMapPanel } from '@/components/panels/GeoMapPanel';
import { LiveHeadlinesPanel } from '@/components/panels/LiveHeadlinesPanel';
import { NewsImpactPanel } from '@/components/panels/NewsImpactPanel';
import { NewsFactorPanel } from '@/components/panels/NewsFactorPanel';
import { GeoImpactPanel } from '@/components/panels/GeoImpactPanel';
import { GeoAnalogPanel } from '@/components/panels/GeoAnalogPanel';

/**
 * News tab — oil news, decoded into price, through two complementary engines:
 *
 *   1. GEOSPATIAL — headline → physical asset (chokepoint / refinery / pipeline)
 *      → the price nodes it moves, graded by a per-node event study. Surfaces: the
 *      live geo map, the live geo-alert tape, the node-impact edge table, and the
 *      RAG analog box with an LLM-narrated desk note.
 *   2. FACTOR MODEL — headline → price-driving factor → expected Brent % move,
 *      from a per-factor event study. Surfaces: the ranked impact feed, the
 *      per-factor beta table, and the raw scored wire.
 *
 * Both are graded prior-then-learn: a measured number appears only where history
 * cleared the significance gate, else a labelled prior — never a fabricated figure.
 */

export function NewsView() {
  // Clicking an asset on the geo map pre-fills the analog lookup below.
  const [analogPrefill, setAnalogPrefill] = useState<string | null>(null);

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="News Intelligence"
        title="Oil news, decoded into price"
        desc={<>Every headline is routed through two engines — a <span className="text-gold">geospatial
          pipeline</span> (news → physical asset → price-node impact) and a <span className="text-accent-blue">factor
          model</span> (news → driver → expected Brent move). Both grade prior-then-learn: a number is shown only
          where history earned it, never a fabricated figure.</>}
        badges={<>
          <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-md border border-gold/30 bg-gold/5 text-gold text-[9px] font-mono uppercase tracking-wider">
            <span className="w-1.5 h-1.5 rounded-full bg-gold" /> Geospatial
          </span>
          <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-md border border-accent-blue/30 bg-accent-blue/5 text-accent-blue text-[9px] font-mono uppercase tracking-wider">
            <span className="w-1.5 h-1.5 rounded-full bg-accent-blue" /> Factor model
          </span>
        </>}
      />

      {/* ── 01 · geospatial engine ──────────────────────────────────── */}
      <section className="space-y-4">
        <SectionHeader
          accent="gold"
          eyebrow="Geospatial engine · 01"
          title="Location → physical asset → price node"
          desc="A headline names a chokepoint, refinery or pipeline; the registry maps it to the tradeable
                nodes it moves, graded by a per-node event study over the 2026 Hormuz-war GDELT corpus × the price
                tape (LLM geo-extraction via free Groq). Single episode — read direction, not exact p-values."
        />
        <GeoMapPanel onSelectHeadline={setAnalogPrefill} />
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-4 items-start">
          <GeoLiveAlertsPanel />
          <GeoImpactPanel />
        </div>
        <GeoAnalogPanel prefill={analogPrefill} />
      </section>

      {/* ── 02 · headline factor model ──────────────────────────────── */}
      <section className="space-y-4">
        <SectionHeader
          accent="blue"
          eyebrow="Factor model · 02"
          title="Headline → price driver → expected Brent move"
          desc="Each headline is classified into a price-driving factor (Groq zero-shot + keyword fallback),
                given a signed crude-sentiment, and turned into an expected % move by an event study of how that
                factor historically moved the tape. Measured beta only when it clears the t-stat / min-N gate —
                otherwise a labelled prior."
        />
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-4 items-start">
          <NewsImpactPanel />
          <NewsFactorPanel />
        </div>
        <LiveHeadlinesPanel />
      </section>
    </div>
  );
}
