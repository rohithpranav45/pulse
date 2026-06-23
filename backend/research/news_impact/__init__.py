"""
PULSE — News Headline Impact Model.

One step deeper than headline sentiment: classify each oil-news headline into one
of the major price-driving FACTORS, then quantify the expected price impact (a %
move) from an event study of how that factor historically moved the Brent/WTI tape
— regime-gated, the same conditional-reaction thesis as the inventory framework.

Layered design (built incrementally, one sprint each):
    corpus.py    timestamped headline corpus (GDELT historical backfill + live
                 persistence into the `news_history` table in pulse_cache.db)
    classify.py  Groq zero-shot factor classification (+ keyword fallback) into
                 the 8-factor taxonomy
    event_study  per-factor forward-return betas, regime-gated         (sprint 2)
    impact.py    headline -> {factor, direction, expected_%_move, t}    (sprint 2)

Run the corpus + classifier:  python -m backend.research.news_impact
"""

from .classify import FACTORS  # noqa: F401
