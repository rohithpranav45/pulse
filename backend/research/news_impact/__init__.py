"""
PULSE — News Headline Impact Model.

One step deeper than headline sentiment: classify each oil-news headline into one
of the major price-driving FACTORS, then quantify the expected price impact (a %
move) from an event study of how that factor historically moved the Brent/WTI tape
— regime-gated, the same conditional-reaction thesis as the inventory framework.

Layered design (built incrementally, one sprint each):
    corpus.py     timestamped headline corpus (GDELT historical backfill + live
                  persistence into the `news_history` table in pulse_cache.db)
    classify.py   Groq zero-shot factor classification (+ keyword fallback) into
                  the 8-factor taxonomy
    event_study.py  per-factor forward-return betas (+1h/+4h/+1d), regime-gated,
                  vol-normalised — fitted over the corpus × the /Data price tape
    impact.py     headline -> {factor, direction, expected_%_move, t-stat, regime},
                  prior-then-learn gate (measured beta only when significant)

Run the corpus + classifier:  python -m backend.research.news_impact
Fit + cache the betas:        python -m backend.research.news_impact.event_study
Score the live feed:          python -m backend.research.news_impact.impact
"""

from .classify import FACTORS  # noqa: F401
