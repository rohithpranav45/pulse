"""
Geopolitical Risk Index — composite 0-100 score.

Four equally-weighted components (25 pts each):
  1. Brent-WTI spread anomaly   — z-score vs 252-day history
  2. Oil price volatility       — 30d realised vol percentile
  3. VIX level                  — absolute threshold bands
  4. News sentiment             — negative headline count via news.py

Imports live prices and historical analytics from existing fetchers.
No external API calls — all data flows from the cache layer.
"""
import os as _os, sys as _sys
_BACKEND = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), ".."))
if _BACKEND not in _sys.path:
    _sys.path.insert(0, _BACKEND)

import numpy as np
from datetime import datetime, timezone

from fetchers.prices    import get_live_prices
from fetchers.historical import (
    load_historical,
    get_volatility,
    get_percentile_rank,
)

try:
    from fetchers.news import get_energy_news
    _NEWS_AVAILABLE = True
except ImportError:
    _NEWS_AVAILABLE = False


# ── Module-level TTL cache for calculate_geo_risk() ──────────────────────────
# Apify is called once inside _component_news(); without this guard
# get_all_signals() triggers 6 Apify runs (3 assets × fv_indicator + geo_indicator),
# blocking for 90 s on every cache miss.

_geo_cache      = None
_geo_cache_time = None
_GEO_CACHE_TTL  = 300   # seconds — matches the Flask API signal/fair_value TTL


# ── Component calculators ─────────────────────────────────────────────────────

def _component_spread_anomaly(prices: dict, hist: dict) -> tuple[float, str]:
    """
    Component 1 — Brent-WTI spread anomaly (0-25 pts).

    A wide spread signals supply-route stress or regional tightness.
    Score scales linearly with the z-score of the current spread
    relative to its 252-day mean and standard deviation.
    """
    brent = prices["brent"]["price"]
    wti   = prices["wti"]["price"]
    current_spread = brent - wti

    brent_hist   = hist["Brent"]["Close"].dropna()
    wti_hist     = hist["WTI"]["Close"].dropna()
    spread_series = (brent_hist - wti_hist).dropna()

    tail        = spread_series.tail(252)
    mean_252    = float(tail.mean())
    std_252     = float(tail.std())
    z_score     = (current_spread - mean_252) / std_252 if std_252 else 0.0

    score  = min(25.0, max(0.0, float(z_score) * 8))
    detail = (
        f"Spread ${current_spread:.2f} "
        f"({z_score:+.1f}s vs 252d avg ${mean_252:.2f})"
    )
    return score, detail


def _component_volatility(hist: dict) -> tuple[float, str]:
    """
    Component 2 — Oil price volatility (0-25 pts).

    Uses Brent 30-day annualised vol, ranked against its own 252-day history.
    High vol percentile → elevated score.
    """
    vol_30d = get_volatility("Brent", window=30)
    vol_pct = get_percentile_rank("Brent", vol_30d, lookback=252)

    score  = (vol_pct / 100) * 25
    detail = (
        f"30d vol {vol_30d:.1f}% "
        f"({vol_pct:.0f}th %ile vs 252d history)"
    )
    return score, detail


def _component_vix(prices: dict) -> tuple[float, str]:
    """
    Component 3 — VIX level (0-25 pts).

    Absolute threshold bands reflecting market-accepted fear regimes.
    """
    vix = prices.get("vix", {}).get("price", 20.0)

    if vix < 15:
        score = 5.0
    elif vix < 20:
        score = 10.0
    elif vix < 25:
        score = 16.0
    elif vix < 30:
        score = 21.0
    else:
        score = 25.0

    detail = f"VIX at {vix:.1f}"
    return score, detail


def _component_news() -> tuple[float, str]:
    """
    Component 4 — News sentiment (0-25 pts).

    Counts negative energy headlines returned by get_energy_news().
    Each negative headline contributes 5 points (capped at 25).
    Falls back to neutral 12 if the news module is unavailable or errors.
    """
    if _NEWS_AVAILABLE:
        try:
            news_data      = get_energy_news()
            negative_count = news_data.get("negative_count", 0)
            score          = min(25.0, negative_count * 5)
            detail         = f"{negative_count} negative energy headlines detected"
        except Exception:
            score  = 12.0
            detail = "News feed error — neutral estimate"
    else:
        score  = 12.0
        detail = "News module unavailable"

    return score, detail


# ── Label helpers ─────────────────────────────────────────────────────────────

def _risk_label(total: int) -> str:
    if total > 80:
        return "CRITICAL"
    if total > 65:
        return "HIGH"
    if total > 45:
        return "ELEVATED"
    if total > 25:
        return "MODERATE"
    return "LOW"


# ── Main public function ──────────────────────────────────────────────────────

def calculate_geo_risk() -> dict:
    """
    Calculate the composite Geopolitical Risk Index.

    Fetches live prices and historical data once, then runs all four
    component scorers. Each component contributes 0-25 points.

    Result is cached in-process for _GEO_CACHE_TTL seconds so that
    callers within the same warm cycle (e.g. get_all_signals() iterating
    three assets) share a single Apify run instead of six.

    Returns
    -------
    {
      "index":          int,    0-100 composite score
      "label":          str,    LOW / MODERATE / ELEVATED / HIGH / CRITICAL
      "primary_driver": str,    component key with the highest score
      "components": {
        "spread_anomaly": {"score": float, "detail": str},
        "volatility":     {"score": float, "detail": str},
        "vix_level":      {"score": float, "detail": str},
        "news_sentiment": {"score": float, "detail": str},
      },
      "timestamp":      str,    ISO-8601 UTC
    }
    """
    global _geo_cache, _geo_cache_time

    # Return cached result if still fresh
    if _geo_cache is not None and _geo_cache_time is not None:
        age = (datetime.now() - _geo_cache_time).seconds
        if age < _GEO_CACHE_TTL:
            return _geo_cache

    # Pull shared data once — both components that need it reuse the same objects
    prices = get_live_prices()
    hist   = load_historical()

    score_1, detail_1 = _component_spread_anomaly(prices, hist)
    score_2, detail_2 = _component_volatility(hist)
    score_3, detail_3 = _component_vix(prices)
    score_4, detail_4 = _component_news()

    components = {
        "spread_anomaly": {"score": round(score_1, 2), "detail": detail_1},
        "volatility":     {"score": round(score_2, 2), "detail": detail_2},
        "vix_level":      {"score": round(score_3, 2), "detail": detail_3},
        "news_sentiment": {"score": round(score_4, 2), "detail": detail_4},
    }

    total          = min(100, max(0, int(score_1 + score_2 + score_3 + score_4)))
    label          = _risk_label(total)
    primary_driver = max(components, key=lambda k: components[k]["score"])

    result = {
        "index":          total,
        "label":          label,
        "primary_driver": primary_driver,
        "components":     components,
        "timestamp":      datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }

    # Store in module-level cache
    _geo_cache      = result
    _geo_cache_time = datetime.now()
    return result


# ── Test block ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Calculating Geopolitical Risk Index...\n")
    result = calculate_geo_risk()

    LABEL_COLOURS = {
        "CRITICAL": "!!!",
        "HIGH":     "!! ",
        "ELEVATED": "!  ",
        "MODERATE": "~  ",
        "LOW":      "   ",
    }

    flag  = LABEL_COLOURS.get(result["label"], "   ")
    index = result["index"]

    # Composite bar (50 chars wide)
    filled = round(index / 2)
    bar    = "[" + "#" * filled + "-" * (50 - filled) + "]"

    print(f"  {flag} GEO-RISK INDEX : {index:>3} / 100   {result['label']}")
    print(f"  {bar}")
    print(f"  Primary driver  : {result['primary_driver']}")
    print(f"  Timestamp       : {result['timestamp']}")

    print(f"\n  {'Component':<18}  {'Score':>6}  {'Max':>4}   Detail")
    print("  " + "-" * 78)

    max_score = {"spread_anomaly": 25, "volatility": 25,
                 "vix_level": 25, "news_sentiment": 25}

    for key, comp in result["components"].items():
        s     = comp["score"]
        mx    = max_score[key]
        share = round(s / mx * 20) if mx else 0
        mini  = "[" + "#" * share + "-" * (20 - share) + "]"
        star  = " <-- driver" if key == result["primary_driver"] else ""
        print(f"  {key:<18}  {s:>5.1f}  /{mx:>2}   {mini}  {comp['detail']}{star}")

    print(f"\n  Component sum   : {sum(c['score'] for c in result['components'].values()):.1f}")
    print(f"  Capped index    : {index}")
