"""
Signal Engine — synthesises all data sources into a directional trading signal
==============================================================================
Eight indicators (seven for crude, eight for Henry Hub) each return a score in
[-2, +2] and a human-readable reason string.  Weights are asset-specific and
calibrated to reflect how much each factor actually moves energy prices.

Public API
----------
  fv_indicator(asset)              → dict
  cot_indicator(asset)             → dict
  inventory_indicator()            → dict
  curve_indicator(asset)           → dict
  dxy_indicator()                  → dict
  geo_indicator()                  → dict
  technicals_indicator(asset)      → dict
  weather_indicator()              → dict   # Henry Hub only

  calculate_signal(asset,
                   cot_asset)      → dict   # full signal for one asset
  get_all_signals()                → dict   # brent + wti + natgas in one call

Score key:  +2 = strong bullish  |  +1 = mild bullish
             0 = neutral
            -1 = mild bearish    |  -2 = strong bearish

Weight calibration (informed by academic literature on energy price drivers)
────────────────────────────────────────────────────────────────────────────
  CRUDE (Brent / WTI)
    Inventory    0.28   — most immediate supply/demand balance signal
    Curve        0.24   — market's own view on near-term tightness
    COT          0.19   — positioning extremes are reliable contrarian signal
    Fair Value   0.14   — cost-of-carry deviation
    Sentiment    0.05   — recency-weighted VADER news sentiment (crude only)
    Technicals   0.05   — momentum confirmation only
    DXY          0.03   — dollar headwind / tailwind
    IV           0.02   — ATM implied vol percentile (USO proxy); shifted from Geo
    Geo Risk     0.00   — priced in quickly; alpha decays fast (shifted to IV)
                ─────
                1.00

  HENRY HUB (Natural Gas)
    Inventory    0.30   — gas storage vs 5-year average (key EIA release)
    Weather      0.25   — HDD/CDD deviation from normal (most direct demand driver)
    Curve        0.15   — seasonal curve (gas spreads differ from crude)
    COT          0.15   — speculator positioning
    Fair Value   0.10   — production cost floor signal
    Technicals   0.05   — momentum
                ─────
                1.00
    (DXY and Geo Risk excluded for nat gas — correlation is weak)
"""
import os as _os, sys as _sys
_BACKEND = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), ".."))
if _BACKEND not in _sys.path:
    _sys.path.insert(0, _BACKEND)

import sys
from datetime import datetime, timezone

from dotenv import load_dotenv
load_dotenv()

try:
    from db.signal_history import append_history, get_history as _get_history
    _HISTORY_OK = True
except Exception:
    _HISTORY_OK = False
    def append_history(*a, **kw): pass
    def _get_history(asset, n=24): return []


# ─────────────────────────────────────────────────────────────────────────────
# Weight tables
# ─────────────────────────────────────────────────────────────────────────────

_CRUDE_WEIGHTS = {
    "inventory":  0.28,
    "curve":      0.24,
    "cot":        0.19,
    "fair_value": 0.14,
    "sentiment":  0.05,
    "technicals": 0.05,
    "dxy":        0.03,
    "geo":        0.00,   # shifted to IV — geo alpha decays fast; IV captures fear premium
    "iv":         0.02,   # ATM implied vol percentile (USO proxy)
}

_NATGAS_WEIGHTS = {
    "inventory":  0.30,
    "weather":    0.25,
    "curve":      0.15,
    "cot":        0.15,
    "fair_value": 0.10,
    "technicals": 0.05,
}

assert abs(sum(_CRUDE_WEIGHTS.values())  - 1.0) < 1e-9, "Crude weights don't sum to 1"
assert abs(sum(_NATGAS_WEIGHTS.values()) - 1.0) < 1e-9, "NatGas weights don't sum to 1"


# ─────────────────────────────────────────────────────────────────────────────
# INDICATOR 1 — Fair Value deviation
# ─────────────────────────────────────────────────────────────────────────────

def fv_indicator(asset: str = "brent", weight: float = 0.15) -> dict:
    """
    Score how far the live price sits from the cost-of-carry fair value.

    Positive deviation (overpriced) → bearish signal.
    Negative deviation (underpriced) → bullish signal.
    """
    from models.fair_value import calculate_fair_value

    fv  = calculate_fair_value(asset)
    dev = fv["deviation_pct"]

    if dev > 8:
        score  = -2
        reason = f"Price {dev:.1f}% above fair value — extreme"
    elif dev > 4:
        score  = -1
        reason = f"Price {dev:.1f}% above fair value"
    elif dev > -4:
        score  = 0
        reason = f"Price near fair value ({dev:+.1f}%)"
    elif dev > -8:
        score  = +1
        reason = f"Price {abs(dev):.1f}% below fair value"
    else:
        score  = +2
        reason = f"Price {abs(dev):.1f}% below fair value — extreme"

    return {
        "name":      "Fair Value",
        "score":     score,
        "weight":    weight,
        "reason":    reason,
        "raw_value": round(dev, 2),
    }


# ─────────────────────────────────────────────────────────────────────────────
# INDICATOR 2 — COT speculator positioning (CONTRARIAN)
# ─────────────────────────────────────────────────────────────────────────────

def cot_indicator(asset: str = "crude_oil", weight: float = 0.20) -> dict:
    """
    Contrarian read of CFTC Managed Money positioning.

    A crowded long (high percentile) is a bearish signal.
    A crowded short is bullish.
    """
    from fetchers.cot import get_positioning_percentile

    cot = get_positioning_percentile()
    pct = cot.get(asset, {}).get("percentile", 50.0)

    if pct > 90:
        score  = -2
        reason = f"Speculators at {pct:.0f}th %ile — extreme crowded long"
    elif pct > 75:
        score  = -1
        reason = f"Speculators at {pct:.0f}th %ile — crowded long"
    elif pct > 25:
        score  = 0
        reason = f"Positioning neutral at {pct:.0f}th %ile"
    elif pct > 10:
        score  = +1
        reason = f"Speculators at {pct:.0f}th %ile — crowded short"
    else:
        score  = +2
        reason = f"Speculators at {pct:.0f}th %ile — extreme short"

    return {
        "name":      "COT",
        "score":     score,
        "weight":    weight,
        "reason":    reason,
        "raw_value": round(pct, 1),
    }


# ─────────────────────────────────────────────────────────────────────────────
# INDICATOR 3 — Inventory vs seasonal average
# ─────────────────────────────────────────────────────────────────────────────

def inventory_indicator(weight: float = 0.30) -> dict:
    """
    Compare current crude stocks to the 5-year seasonal average.

    Below-average stocks (tight supply) → bullish.
    Above-average stocks (ample supply) → bearish.
    """
    from fetchers.eia import get_inventory_vs_seasonal

    inv     = get_inventory_vs_seasonal()
    dev_pct = inv["crude_stocks"].get("deviation_pct") or 0.0

    if dev_pct < -8:
        score  = +2
        reason = f"Crude {abs(dev_pct):.1f}% below seasonal — very tight"
    elif dev_pct < -4:
        score  = +1
        reason = f"Crude {abs(dev_pct):.1f}% below seasonal — below avg"
    elif dev_pct > 8:
        score  = -2
        reason = f"Crude {dev_pct:.1f}% above seasonal — very loose"
    elif dev_pct > 4:
        score  = -1
        reason = f"Crude {dev_pct:.1f}% above seasonal — above avg"
    else:
        score  = 0
        reason = f"Crude stocks near seasonal avg ({dev_pct:+.1f}%)"

    return {
        "name":      "Inventory",
        "score":     score,
        "weight":    weight,
        "reason":    reason,
        "raw_value": round(dev_pct, 2),
    }


# ─────────────────────────────────────────────────────────────────────────────
# INDICATOR 4 — Futures curve structure
# ─────────────────────────────────────────────────────────────────────────────

def curve_indicator(asset: str = "wti", weight: float = 0.25) -> dict:
    """
    Read the M1-M2 curve shape as a near-term supply signal.

    Backwardation → immediate supply tight (bullish).
    Steep contango → ample supply comfortable in storage (bearish).
    """
    from fetchers.curve import get_curve_metrics

    metrics   = get_curve_metrics(asset)
    spread    = metrics["m1_m2_spread"]
    shape     = metrics["shape"]
    steepness = metrics["steepness"]

    if shape == "BACKWARDATION":
        score  = +2 if abs(spread) > 1.0 else +1
        reason = f"Backwardation — immediate supply tight (M1-M2: {spread:+.2f})"
    elif steepness == "STEEP":
        score  = -1
        reason = f"Steep contango — supply comfortable (M1-M2: {spread:+.2f})"
    elif steepness == "FLAT":
        score  = +1
        reason = f"Flattening contango — supply tightening ({spread:+.2f})"
    else:
        score  = 0
        reason = f"Moderate contango — neutral signal (M1-M2: {spread:+.2f})"

    return {
        "name":      "Curve",
        "score":     score,
        "weight":    weight,
        "reason":    reason,
        "raw_value": round(spread, 3),
    }


# ─────────────────────────────────────────────────────────────────────────────
# INDICATOR 5 — DXY trend (crude only)
# ─────────────────────────────────────────────────────────────────────────────

def dxy_indicator(weight: float = 0.03) -> dict:
    """
    Compare DXY to its 10-day and 30-day moving averages.

    Rising dollar → headwind for oil (bearish).
    Falling dollar → tailwind for oil (bullish).

    Note: historical data uses key 'DXY' (not 'dxy').
    """
    from fetchers.historical import load_historical

    hist = load_historical()
    dxy  = hist["DXY"]["Close"].dropna()

    current = float(dxy.iloc[-1])
    avg_10d = float(dxy.iloc[-10:].mean()) if len(dxy) >= 10 else float(dxy.mean())
    avg_30d = float(dxy.iloc[-30:].mean()) if len(dxy) >= 30 else float(dxy.mean())

    short = round(current - avg_10d, 4)
    long_ = round(current - avg_30d, 4)

    if short > 1.5 and long_ > 2.0:
        score  = -2
        reason = f"DXY surging ({long_:+.1f} vs 30d) — strong headwind"
    elif short > 0.5 or long_ > 1.0:
        score  = -1
        reason = f"DXY rising ({long_:+.1f} vs 30d) — headwind"
    elif short < -1.5 and long_ < -2.0:
        score  = +2
        reason = f"DXY falling ({long_:+.1f} vs 30d) — strong tailwind"
    elif short < -0.5 or long_ < -1.0:
        score  = +1
        reason = f"DXY weakening ({long_:+.1f} vs 30d) — tailwind"
    else:
        score  = 0
        reason = f"DXY neutral ({long_:+.2f} vs 30d avg)"

    return {
        "name":      "DXY",
        "score":     score,
        "weight":    weight,
        "reason":    reason,
        "raw_value": round(long_, 4),
    }


# ─────────────────────────────────────────────────────────────────────────────
# INDICATOR 6 — Geopolitical risk index (crude only)
# ─────────────────────────────────────────────────────────────────────────────

def geo_indicator(weight: float = 0.02) -> dict:
    """
    Score based on the composite 0-100 geo-risk index.

    High index → supply-disruption premium warranted (bullish for price).
    Low index  → no geo premium; slight bearish gravity.
    """
    from fetchers.geo_risk import calculate_geo_risk

    geo    = calculate_geo_risk()
    idx    = int(geo["index"])
    driver = geo["primary_driver"]

    if idx > 75:
        score  = +2
        reason = f"Geo risk CRITICAL ({idx}/100) — supply threat: {driver}"
    elif idx > 55:
        score  = +1
        reason = f"Geo risk HIGH ({idx}/100) — elevated supply premium"
    elif idx > 35:
        score  = 0
        reason = f"Geo risk MODERATE ({idx}/100) — background noise"
    else:
        score  = -1
        reason = f"Geo risk LOW ({idx}/100) — no supply premium warranted"

    return {
        "name":      "Geo Risk",
        "score":     score,
        "weight":    weight,
        "reason":    reason,
        "raw_value": idx,
    }


# ─────────────────────────────────────────────────────────────────────────────
# INDICATOR 6b — Options implied volatility (crude only)
# ─────────────────────────────────────────────────────────────────────────────

def iv_indicator(weight: float = 0.02) -> dict:
    """
    ATM implied volatility percentile for USO (crude proxy).

    High IV percentile signals elevated fear / risk premium already priced in
    (slightly bearish — market has discounted the upside).
    Low IV percentile signals complacency (mildly bullish — vol pop potential).

    Score:
      pctile > 0.80  → -1  (fear premium priced in)
      pctile < 0.20  → +1  (complacency — mild bullish)
      else           →  0
    """
    try:
        from fetchers.options_iv import get_iv

        iv_data  = get_iv()
        pctile   = iv_data.get("crude_iv_pctile", 0.5)
        crude_iv = iv_data.get("crude_iv")

        if pctile > 0.80:
            score  = -1
            reason = f"IV at {pctile*100:.0f}th %ile — fear premium priced in (IV {crude_iv*100:.1f}%)" \
                     if crude_iv else f"IV at {pctile*100:.0f}th %ile — fear premium elevated"
        elif pctile < 0.20:
            score  = +1
            reason = f"IV at {pctile*100:.0f}th %ile — low vol; complacency (IV {crude_iv*100:.1f}%)" \
                     if crude_iv else f"IV at {pctile*100:.0f}th %ile — low vol; complacency"
        else:
            score  = 0
            reason = f"IV at {pctile*100:.0f}th %ile — normal vol regime"
            if crude_iv:
                reason += f" (IV {crude_iv*100:.1f}%)"

        return {
            "name":      "IV",
            "score":     score,
            "weight":    weight,
            "reason":    reason,
            "raw_value": {"pctile": round(pctile, 4), "iv": crude_iv},
        }
    except Exception as exc:
        return {
            "name":      "IV",
            "score":     0,
            "weight":    weight,
            "reason":    f"IV data unavailable ({exc})",
            "raw_value": None,
        }


# ─────────────────────────────────────────────────────────────────────────────
# INDICATOR 7 — Technical momentum
# ─────────────────────────────────────────────────────────────────────────────

def technicals_indicator(asset: str = "brent", weight: float = 0.05) -> dict:
    """
    RSI(14) + MACD + Bollinger %B composite momentum signal.

    Confirmation role only — low weight, but can tip conviction at extremes.
    """
    from fetchers.technicals import get_technicals, _SYMBOL_MAP

    symbol = _SYMBOL_MAP.get(asset, "BZ=F")
    tech   = get_technicals(symbol)

    score  = tech["composite_score"]
    reason = tech["composite_reason"]

    # Clamp to [-2, +2] integer for display consistency
    rounded = int(round(max(-2.0, min(2.0, score))))

    return {
        "name":      "Technicals",
        "score":     rounded,
        "weight":    weight,
        "reason":    reason,
        "raw_value": {
            "rsi":      tech["rsi"],
            "macd_hist": tech["macd_histogram"],
            "bb_pct_b": tech["bb_pct_b"],
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# INDICATOR 8 — Weather / HDD-CDD demand (Henry Hub only)
# ─────────────────────────────────────────────────────────────────────────────

def weather_indicator(weight: float = 0.25) -> dict:
    """
    7-day HDD/CDD deviation from seasonal normals for major US gas demand hubs.

    Above-normal heating demand (HDD) → bullish for nat gas price.
    Below-normal demand (warm weather) → bearish.
    """
    from fetchers.weather import get_weather_signal

    wx  = get_weather_signal()

    if wx.get("error"):
        return {
            "name":      "Weather",
            "score":     0,
            "weight":    weight,
            "reason":    "Weather data unavailable — neutral",
            "raw_value": None,
        }

    net = wx["net_demand_signal"]   # positive = more demand than normal
    hdd_dev = wx["hdd_deviation_pct"]
    cdd_dev = wx["cdd_deviation_pct"]
    season  = wx.get("season", "shoulder")

    if net > 30:
        score  = +2
        reason = f"Much colder than normal (HDD +{hdd_dev:.0f}%) — strong demand pull"
    elif net > 10:
        score  = +1
        reason = f"Cooler than normal (HDD +{hdd_dev:.0f}%) — above-avg demand"
    elif net > -10:
        score  = 0
        reason = f"Near-normal temps — demand in line with seasonal avg"
    elif net > -30:
        score  = -1
        reason = f"Warmer than normal (HDD {hdd_dev:.0f}%) — below-avg demand"
    else:
        score  = -2
        reason = f"Much warmer than normal (HDD {hdd_dev:.0f}%) — weak demand"

    return {
        "name":      "Weather",
        "score":     score,
        "weight":    weight,
        "reason":    reason,
        "raw_value": {
            "hdd_7day":          wx["hdd_7day"],
            "cdd_7day":          wx["cdd_7day"],
            "hdd_deviation_pct": hdd_dev,
            "cdd_deviation_pct": cdd_dev,
            "net_demand_signal": net,
            "season":            season,
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# INDICATOR 9 — News sentiment (crude only; nat gas news is less reliable)
# ─────────────────────────────────────────────────────────────────────────────

def sentiment_indicator(weight: float = 0.05) -> dict:
    """
    Recency-weighted VADER composite sentiment over recent energy headlines.

    Positive composite → bullish market narrative.
    Negative composite → bearish / risk-off narrative.

    Only wired into crude (Brent / WTI) signals; nat gas news correlation
    is weaker and the indicator is excluded from the Henry Hub weight table.

    Score mapping:
      composite > +0.30  → +2  (strong bullish narrative)
      composite > +0.10  → +1  (mild bullish)
      composite ≥ -0.10  →  0  (neutral / mixed)
      composite < -0.10  → -1  (mild bearish)
      composite < -0.30  → -2  (strong bearish narrative)
    """
    try:
        from fetchers.news import get_energy_news
        news_data  = get_energy_news()
        sent_agg   = news_data.get("composite_sentiment", {})
        composite  = sent_agg.get("composite", 0.0)
        label      = sent_agg.get("label", "NEUTRAL")
        bull_count = sent_agg.get("bullish", 0)
        bear_count = sent_agg.get("bearish", 0)
    except Exception as exc:
        return {
            "name":      "Sentiment",
            "score":     0,
            "weight":    weight,
            "reason":    f"Sentiment data unavailable ({exc})",
            "raw_value": None,
        }

    if composite > 0.30:
        score  = +2
        reason = (f"News sentiment strongly {label} "
                  f"(composite {composite:+.2f}, {bull_count} bullish headlines)")
    elif composite > 0.10:
        score  = +1
        reason = (f"News sentiment mildly {label} "
                  f"(composite {composite:+.2f})")
    elif composite >= -0.10:
        score  = 0
        reason = (f"News sentiment neutral/mixed "
                  f"(composite {composite:+.2f})")
    elif composite >= -0.30:
        score  = -1
        reason = (f"News sentiment mildly {label} "
                  f"(composite {composite:+.2f})")
    else:
        score  = -2
        reason = (f"News sentiment strongly {label} "
                  f"(composite {composite:+.2f}, {bear_count} bearish headlines)")

    return {
        "name":      "Sentiment",
        "score":     score,
        "weight":    weight,
        "reason":    reason,
        "raw_value": round(composite, 4),
    }


# ─────────────────────────────────────────────────────────────────────────────
# MAIN — composite signal
# ─────────────────────────────────────────────────────────────────────────────

def calculate_signal(asset: str = "brent",
                     cot_asset: str = "crude_oil") -> dict:
    """
    Combine all indicators into a single directional signal.

    For crude (brent / wti): 7 indicators with _CRUDE_WEIGHTS.
    For henry_hub (nat gas):  6 indicators with _NATGAS_WEIGHTS.

    Parameters
    ----------
    asset     : price / fair-value key  ("brent", "wti", "henry_hub")
    cot_asset : COT positioning key     ("crude_oil", "natural_gas",
                                          "gasoline", "heating_oil")

    Returns
    -------
    Full signal dict — see module docstring for schema.
    """
    is_natgas = (asset == "henry_hub")

    if is_natgas:
        W = _NATGAS_WEIGHTS
        indicators = [
            inventory_indicator(weight=W["inventory"]),
            weather_indicator(weight=W["weather"]),
            curve_indicator(asset, weight=W["curve"]),
            cot_indicator(cot_asset, weight=W["cot"]),
            fv_indicator(asset, weight=W["fair_value"]),
            technicals_indicator(asset, weight=W["technicals"]),
        ]
    else:
        W = _CRUDE_WEIGHTS
        indicators = [
            inventory_indicator(weight=W["inventory"]),
            curve_indicator("wti", weight=W["curve"]),
            cot_indicator(cot_asset, weight=W["cot"]),
            fv_indicator(asset, weight=W["fair_value"]),
            sentiment_indicator(weight=W["sentiment"]),
            technicals_indicator(asset, weight=W["technicals"]),
            dxy_indicator(weight=W["dxy"]),
            geo_indicator(weight=W["geo"]),
            iv_indicator(weight=W["iv"]),
        ]

    # ── weighted composite score ──────────────────────────────────────────────
    weighted_score = sum(i["score"] * i["weight"] for i in indicators)
    weighted_score = round(weighted_score, 4)

    # ── label ─────────────────────────────────────────────────────────────────
    if weighted_score > 1.2:
        signal_label = "STRONG BULLISH"
    elif weighted_score > 0.4:
        signal_label = "MILD BULLISH"
    elif weighted_score > -0.4:
        signal_label = "NEUTRAL"
    elif weighted_score > -1.2:
        signal_label = "MILD BEARISH"
    else:
        signal_label = "STRONG BEARISH"

    # ── direction integer ─────────────────────────────────────────────────────
    if weighted_score > 0.4:
        direction = +1
    elif weighted_score < -0.4:
        direction = -1
    else:
        direction = 0

    # ── conviction ────────────────────────────────────────────────────────────────────────────
    if direction != 0:
        agreeing = sum(1 for i in indicators if i["score"] * direction > 0)
    else:
        agreeing = sum(1 for i in indicators if i["score"] == 0)

    n = len(indicators)
    if agreeing >= max(5, n - 1):
        conviction = "HIGH"
    elif agreeing >= max(3, n // 2):
        conviction = "MODERATE"
    else:
        conviction = "LOW"

    # ── factor lists ───────────────────────────────────────────────────────────────────────────
    bullish_factors = [i["reason"] for i in indicators if i["score"] > 0]
    bearish_factors = [i["reason"] for i in indicators if i["score"] < 0]

    # ── key risk ────────────────────────────────────────────────────────────────────────────
    if direction > 0:
        opposing = [i for i in indicators if i["score"] < 0]
        key_risk_str = "No bearish factors identified"
    elif direction < 0:
        opposing = [i for i in indicators if i["score"] > 0]
        key_risk_str = "No bullish factors identified"
    else:
        opposing = sorted(indicators, key=lambda i: abs(i["score"]), reverse=True)
        key_risk_str = "No dominant risk factor"

    if opposing:
        opp = max(opposing, key=lambda i: abs(i["score"]))
        key_risk_str = f"{opp['name']} — {opp['reason']}"

    # ── history tracking ─────────────────────────────────────────────────────
    top_ind    = max(indicators, key=lambda i: abs(i["score"] * i["weight"]), default=None)
    top_driver = top_ind["name"] if (top_ind and top_ind["score"] != 0) else "None"
    append_history(asset, weighted_score, conviction, top_driver)
    history = _get_history(asset, 24)

    return {
        "asset":           asset.upper(),
        "signal":          signal_label,
        "score":           weighted_score,
        "conviction":      conviction,
        "direction":       direction,
        "indicators":      indicators,
        "bullish_factors": bullish_factors,
        "bearish_factors": bearish_factors,
        "key_risk":        key_risk_str,
        "history":         history,
        "timestamp":       datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


# ────────────────────────────────────────────────────────────────────────────
# MULTI-ASSET — brent + wti + natgas
# ────────────────────────────────────────────────────────────────────────────

_ASSET_CONFIGS = [
    # (price_key,    cot_key,         display_label)
    ("brent",        "crude_oil",     "BRENT CRUDE"),
    ("wti",          "crude_oil",     "WTI CRUDE"),
    ("henry_hub",    "natural_gas",   "HENRY HUB NAT GAS"),
]


def get_all_signals() -> dict:
    results = {}
    for price_key, cot_key, _ in _ASSET_CONFIGS:
        results[price_key] = calculate_signal(price_key, cot_key)

    results["timestamp"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return results


# ────────────────────────────────────────────────────────────────────────────
# __main__ — formatted signal cards
# ────────────────────────────────────────────────────────────────────────────

def _signal_arrow(signal: str) -> str:
    arrows = {
        "STRONG BULLISH": "▲▲",
        "MILD BULLISH":   "▲",
        "NEUTRAL":        "→",
        "MILD BEARISH":   "▼",
        "STRONG BEARISH": "▼▼",
    }
    return arrows.get(signal, "→")


def _score_icon(score: int) -> str:
    if score > 0:
        return f"[+{score}]"
    if score < 0:
        return f"[{score}]"
    return "[ 0]"


def _print_signal_card(result: dict, label: str) -> None:
    RULE = "━" * 50

    arrow = _signal_arrow(result["signal"])
    score = result["score"]
    conv  = result["conviction"]
    sign  = "+" if score >= 0 else ""

    print(f"  {RULE}")
    print(f"  PULSE SIGNAL — {label}")
    print(f"  {arrow} {result['signal']}  |  Score: {sign}{score:.2f}"
          f"  |  Conviction: {conv}")
    print(f"  {RULE}")

    bull = [i for i in result["indicators"] if i["score"] > 0]
    bear = [i for i in result["indicators"] if i["score"] < 0]
    neut = [i for i in result["indicators"] if i["score"] == 0]

    if bear:
        print("  BEARISH FACTORS:")
        for i in bear:
            print(f"    ✗ {i['name']:<12} {_score_icon(i['score'])}  {i['reason']}")

    if bull:
        print("  BULLISH FACTORS:")
        for i in bull:
            print(f"    ✓ {i['name']:<12} {_score_icon(i['score'])}  {i['reason']}")

    if neut:
        print("  NEUTRAL:")
        for i in neut:
            print(f"    → {i['name']:<12} {_score_icon(i['score'])}  {i['reason']}")

    print(f"\n  KEY RISK:  {result['key_risk']}")
    print(f"  Timestamp: {result['timestamp']}")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    print("\nCalculating signals for all assets...\n")

    all_sig = get_all_signals()

    for price_key, _, display_label in _ASSET_CONFIGS:
        sig = all_sig[price_key]
        _print_signal_card(sig, display_label)
        print()

    RULE = "━" * 50
    print(f"  {RULE}")
    print(f"  {'Asset':<20}  {'Signal':<16}  {'Score':>6}  {'Conv.'}")
    print(f"  {'-'*48}")
    for price_key, _, display_label in _ASSET_CONFIGS:
        s   = all_sig[price_key]
        sc  = s["score"]
        sgn = "+" if sc >= 0 else ""
        print(f"  {display_label:<20}  {s['signal']:<16}  "
              f"{sgn}{sc:.2f}    {s['conviction']}")
    print(f"  {RULE}")
    print(f"\n  All signals as of: {all_sig['timestamp']}\n")
