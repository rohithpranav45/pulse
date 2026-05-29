"""
Sentiment Analyser — FinBERT headline scoring
=============================================
Uses ProsusAI/finbert, a BERT model fine-tuned on financial news and analyst
reports.  Returns calibrated class probabilities (positive / negative / neutral)
and converts them to a scalar in [-1, +1].

Model weight download ~420 MB, cached in ~/.cache/huggingface/ on first run.

Public API
----------
  get_sentiment(text)            → float  [-1.0, +1.0]
  batch_score(texts)             → list[float]
  aggregate_sentiment(articles)  → dict

Recency weights:
  last 6 h  → 1.0  |  6–24 h  → 0.5  |  > 24 h  → 0.2
"""

import os as _os, sys as _sys
_BACKEND = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), ".."))
if _BACKEND not in _sys.path:
    _sys.path.insert(0, _BACKEND)

import re
import logging
from datetime import datetime, timezone, timedelta

log = logging.getLogger("pulse.sentiment")

# ── FinBERT lazy init ─────────────────────────────────────────────────────────
_finbert    = None
_FINBERT_OK = None   # None = untested; True = loaded; False = unavailable


def _get_finbert():
    """Load ProsusAI/finbert once; return None if transformers/torch unavailable."""
    global _finbert, _FINBERT_OK
    if _FINBERT_OK is False:
        return None
    if _finbert is not None:
        return _finbert
    try:
        from transformers import pipeline
        _finbert = pipeline(
            "text-classification",
            model="ProsusAI/finbert",
            top_k=None,          # return all 3 class probabilities
            truncation=True,
            max_length=512,
        )
        _FINBERT_OK = True
        log.info("FinBERT loaded (ProsusAI/finbert)")
        return _finbert
    except Exception as exc:
        _FINBERT_OK = False
        log.warning("FinBERT unavailable — sentiment scoring disabled: %s", exc)
        return None


def _to_scalar(probs: list) -> float:
    """Convert 3-class FinBERT output to a scalar in [-1, +1].
    neutral cancels out; result = positive_prob - negative_prob."""
    p = {r["label"]: r["score"] for r in probs}
    return round(p.get("positive", 0.0) - p.get("negative", 0.0), 4)


# ── Public scorers ────────────────────────────────────────────────────────────

def get_sentiment(text: str) -> float:
    """Score a single headline → float in [-1, +1]. Returns 0.0 on failure."""
    if not text or not isinstance(text, str):
        return 0.0
    pipe = _get_finbert()
    if pipe is None:
        return 0.0
    try:
        result = pipe([text.strip()], batch_size=1)
        return _to_scalar(result[0])
    except Exception as exc:
        log.warning("get_sentiment failed: %s", exc)
        return 0.0


def batch_score(texts: list) -> list:
    """
    Score a list of headlines in one FinBERT round-trip (batch_size=8).
    Returns list[float] in [-1, +1]; falls back to [0.0, ...] on failure.
    """
    if not texts:
        return []
    pipe = _get_finbert()
    if pipe is None:
        return [0.0] * len(texts)
    try:
        clean = [t.strip() if t else "" for t in texts]
        results = pipe(clean, batch_size=8)
        return [_to_scalar(r) for r in results]
    except Exception as exc:
        log.warning("batch_score failed: %s", exc)
        return [0.0] * len(texts)


# ── Recency helpers ───────────────────────────────────────────────────────────

def _parse_published(article: dict):
    """Extract a UTC-aware datetime from article dict (ISO-8601 or Xh-ago string)."""
    now = datetime.now(timezone.utc)
    published = article.get("published") or article.get("time") or ""
    if published and "T" in str(published):
        try:
            return datetime.fromisoformat(str(published).replace("Z", "+00:00"))
        except ValueError:
            pass
    m = re.match(r"(\d+)(m|h|d)\s+ago", str(published), re.I)
    if m:
        n, unit = int(m.group(1)), m.group(2).lower()
        delta = {"m": timedelta(minutes=n),
                 "h": timedelta(hours=n),
                 "d": timedelta(days=n)}.get(unit, timedelta(hours=12))
        return now - delta
    return None


def _recency_weight(published_dt) -> float:
    if published_dt is None:
        return 0.2
    now   = datetime.now(timezone.utc)
    age_h = (now - published_dt).total_seconds() / 3600.0
    if age_h <= 6:
        return 1.0
    if age_h <= 24:
        return 0.5
    return 0.2


# ── Recency-weighted aggregate ────────────────────────────────────────────────

def aggregate_sentiment(articles: list) -> dict:
    """
    Compute a recency-weighted composite sentiment score over a list of articles.
    Articles missing a 'sentiment' key are batch-scored via FinBERT automatically.
    """
    if not articles:
        return {
            "composite": 0.0, "count": 0,
            "bullish": 0, "bearish": 0, "neutral": 0,
            "label": "NEUTRAL", "stale": _FINBERT_OK is False,
        }

    # Batch-score any articles that don't yet have a pre-computed score
    unscored = [i for i, a in enumerate(articles) if a.get("sentiment") is None]
    if unscored:
        texts  = [(articles[i].get("headline") or articles[i].get("title") or "")
                  for i in unscored]
        scores = batch_score(texts)
        for idx, sc in zip(unscored, scores):
            articles[idx]["sentiment"] = sc

    weighted_sum = 0.0
    weight_total = 0.0
    bullish = bearish = neutral = 0

    for art in articles:
        score  = art.get("sentiment") or 0.0
        dt     = _parse_published(art)
        weight = _recency_weight(dt)

        weighted_sum += score * weight
        weight_total += weight

        if score > 0.05:
            bullish += 1
        elif score < -0.05:
            bearish += 1
        else:
            neutral += 1

    composite = round(weighted_sum / weight_total, 4) if weight_total else 0.0
    label = "BULLISH" if composite > 0.05 else "BEARISH" if composite < -0.05 else "NEUTRAL"

    return {
        "composite": composite,
        "count":     len(articles),
        "bullish":   bullish,
        "bearish":   bearish,
        "neutral":   neutral,
        "label":     label,
        "stale":     _FINBERT_OK is False,
    }


# ── __main__ sanity check ─────────────────────────────────────────────────────

if __name__ == "__main__":
    samples = [
        "Iran warns of consequences as US tightens oil sanctions — Hormuz uncertainty rising",
        "Iraq and Nigeria overproduction drawing concern ahead of OPEC+ meeting",
        "NWS issues colder-than-normal forecast for Northeast US — HH futures rally 2%",
        "Dollar hits 3-week high after strong jobs data — headwind for commodity complex",
        "API crude draw 2.1M barrels vs consensus 1.2M — bullish EIA setup tonight",
        "OPEC+ compliance slips as Gulf producers ramp output",
        "Brent crude stable amid thin summer liquidity — range-bound expected",
        "Supply disruption fears ease as Strait of Hormuz remains open",
    ]

    print(f"\nLoading FinBERT model (first run downloads ~420 MB)...\n")
    scores = batch_score(samples)

    print(f"{'Headline':<70} {'Score':>7}")
    print("─" * 80)
    for text, sc in zip(samples, scores):
        bar  = "▓" * int(abs(sc) * 20)
        sign = "+" if sc >= 0 else ""
        print(f"{text[:68]:<70} {sign}{sc:+.3f}  {bar}")

    agg = aggregate_sentiment([
        {"headline": s, "sentiment": sc, "published": "2026-05-27T12:00:00Z"}
        for s, sc in zip(samples, scores)
    ])
    print(f"\nAggregate → composite={agg['composite']:+.4f}  label={agg['label']}")
    print(f"  Bullish={agg['bullish']}  Bearish={agg['bearish']}  Neutral={agg['neutral']}")
    print(f"  Stale={agg['stale']}")
