"""
Regime classifier — Phase 2 Sprint 3 widens to a 3-axis 27-cell grid.

Axes
----
  CURVE       — Brent M1-M12 ($/bbl), 3 hard buckets:
                  CONTANGO  : M1-M12 ≤ -2
                  NEUTRAL   : -2 < M1-M12 ≤ +5
                  BACK      : M1-M12 > +5
  INVENTORY   — US crude stocks vs 5-year seasonal (from inventory_history.py):
                  LOW       : vs_5yr_pct ≤ -4 %
                  AVG       : -4 % < vs_5yr_pct ≤ +4 %
                  HIGH      : vs_5yr_pct > +4 %
  VOL         — Brent 20-day realised vol (annualised log-ret std):
                  CALM      : rv ≤ 0.20
                  NORMAL    : 0.20 < rv ≤ 0.35
                  STRESSED  : rv > 0.35

Composite label : "{CURVE}/{INV}/{VOL}", e.g. "BACK/LOW/STRESSED".
27 cells total. With 2,712 training days, average ~100 rows/cell — but
real distribution is uneven and ~10-15 cells will have usable n.

Trader-facing thresholds preferred over data-driven quantiles: when the
mentor asks "why this regime?" the answer is one-line and stable across
retrains. Thresholds documented as `REGIME_THRESHOLDS` for the UI.

Legacy 4-bucket API (used by RegimeDrillModal scatter, plus class-demo
sprint code) is kept alive as `classify_one_curve_only` so we don't
break the existing UI surface.

Public API
----------
  Composite (new, Sprint 3)
    classify_curve(m1_m12)            → 'CONTANGO' | 'NEUTRAL' | 'BACK'
    classify_inv(vs_5yr_pct)          → 'LOW' | 'AVG' | 'HIGH'
    classify_vol(rv_20d)              → 'CALM' | 'NORMAL' | 'STRESSED'
    composite_label(curve, inv, vol)  → 'BACK/LOW/STRESSED' string
    REGIMES                            → list of all 27 composite labels
    REGIME_AXES                        → dict { axis_name: [bucket strings] }
    REGIME_THRESHOLDS                  → dict for UI display

  Legacy (Sprint 1 / 2 compat)
    REGIMES_LEGACY                     → 4 curve-only labels
    classify_one(m1_m12)               → legacy 4-bucket label (kept for backward compat)
    classify_one_curve_only            → alias of classify_one
    classify_series(spread_series)     → pd.Series of legacy labels
    regime_distribution(series)        → dict (legacy)
    regime_color(regime)               → UI color (handles both legacy + composite)
"""

from __future__ import annotations

from typing import Iterable, Optional
import math
import pandas as pd

# ─────────────────────────────────────────────────────────────────────────────
# Composite 3-axis grid (Sprint 3)
# ─────────────────────────────────────────────────────────────────────────────
CURVE_BUCKETS = ["CONTANGO", "NEUTRAL", "BACK"]
INV_BUCKETS   = ["LOW", "AVG", "HIGH"]
VOL_BUCKETS   = ["CALM", "NORMAL", "STRESSED"]

REGIME_AXES = {
    "curve":     CURVE_BUCKETS,
    "inventory": INV_BUCKETS,
    "vol":       VOL_BUCKETS,
}

REGIME_THRESHOLDS = {
    "curve": {
        "CONTANGO": "Brent M1-M12 ≤ -$2",
        "NEUTRAL":  "-$2 < M1-M12 ≤ +$5",
        "BACK":     "M1-M12 > +$5",
    },
    "inventory": {
        "LOW":  "US crude stocks ≤ 5y seasonal -4 %",
        "AVG":  "within ±4 % of 5y seasonal",
        "HIGH": "stocks > 5y seasonal +4 %",
    },
    "vol": {
        "CALM":     "20d realised vol ≤ 20 %",
        "NORMAL":   "20-35 %",
        "STRESSED": "> 35 %",
    },
}


def _isnan(x) -> bool:
    return x is None or (isinstance(x, float) and (math.isnan(x) or not math.isfinite(x)))


def classify_curve(m1_m12: Optional[float]) -> str:
    if _isnan(m1_m12):    return "UNKNOWN"
    if m1_m12 <= -2.0:    return "CONTANGO"
    if m1_m12 <=  5.0:    return "NEUTRAL"
    return "BACK"


def classify_inv(vs_5yr_pct: Optional[float]) -> str:
    if _isnan(vs_5yr_pct): return "UNKNOWN"
    if vs_5yr_pct <= -4.0: return "LOW"
    if vs_5yr_pct >   4.0: return "HIGH"
    return "AVG"


def classify_vol(rv_20d: Optional[float]) -> str:
    if _isnan(rv_20d):  return "UNKNOWN"
    if rv_20d <= 0.20:  return "CALM"
    if rv_20d >  0.35:  return "STRESSED"
    return "NORMAL"


def composite_label(curve: str, inv: str, vol: str) -> str:
    return f"{curve}/{inv}/{vol}"


# All 27 composite regimes, plus a wildcard UNKNOWN bucket
REGIMES = [
    composite_label(c, i, v)
    for c in CURVE_BUCKETS for i in INV_BUCKETS for v in VOL_BUCKETS
]


def classify_composite_series(
    m1_m12: pd.Series,
    vs_5yr_pct: pd.Series,
    rv_20d: pd.Series,
) -> pd.Series:
    """
    Vectorised composite classification for a feature frame.
    All three inputs must be indexed alike (typically daily date index).
    """
    idx = m1_m12.index
    curve = m1_m12.apply(classify_curve)
    inv   = vs_5yr_pct.reindex(idx).apply(classify_inv)
    vol   = rv_20d.reindex(idx).apply(classify_vol)
    return pd.Series(
        [composite_label(c, i, v) for c, i, v in zip(curve, inv, vol)],
        index=idx,
        name="regime",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Pooled curve-axis-only grid (Phase 2.5)
# ─────────────────────────────────────────────────────────────────────────────
# Sprint 4 walk-forward showed the 27-cell composite grid is over-fragmented:
# many cells have n=30-150, regression noise eats the regime-conditioning
# benefit, and a regime-UNAWARE 252-day rolling z-score beats it overall.
#
# Phase 2.5 collapses to the curve axis only — 3 buckets per spread instead
# of 27 — giving ~5× more rows per cell. Same hard thresholds as the curve
# axis of the composite grid; the inventory + vol axes still surface on the
# UI as drivers but no longer fragment the training set.
#
# Mirrors composite API: REGIMES_POOLED, classify_pooled, classify_pooled_series.
# ─────────────────────────────────────────────────────────────────────────────
REGIMES_POOLED = list(CURVE_BUCKETS)  # ["CONTANGO", "NEUTRAL", "BACK"]


def classify_pooled(m1_m12: Optional[float]) -> str:
    """Pooled regime = curve bucket only. Alias of classify_curve."""
    return classify_curve(m1_m12)


def classify_pooled_series(m1_m12: pd.Series) -> pd.Series:
    """Vectorised pooled classification (curve axis only)."""
    return m1_m12.apply(classify_pooled).rename("regime_pooled")


# ─────────────────────────────────────────────────────────────────────────────
# Legacy 4-bucket curve-only classifier (Sprint 1 / 2 compatibility)
# ─────────────────────────────────────────────────────────────────────────────
REGIMES_LEGACY = [
    "EXTREME_CONTANGO",
    "MILD_CONTANGO",
    "MILD_BACKWARDATION",
    "EXTREME_BACKWARDATION",
]


def classify_one_curve_only(m1_m12: Optional[float]) -> str:
    if _isnan(m1_m12):    return "UNKNOWN"
    if m1_m12 <= -5.0:    return "EXTREME_CONTANGO"
    if m1_m12 <=  0.0:    return "MILD_CONTANGO"
    if m1_m12 <= 10.0:    return "MILD_BACKWARDATION"
    return "EXTREME_BACKWARDATION"


# Back-compat alias — drill.py / live_ranker.py imports this name
classify_one = classify_one_curve_only


def classify_series(spread_series: pd.Series) -> pd.Series:
    return spread_series.apply(classify_one_curve_only).rename("regime")


def regime_distribution(spread_series: pd.Series) -> dict:
    labels = classify_series(spread_series)
    counts = labels.value_counts().to_dict()
    for r in REGIMES_LEGACY:
        counts.setdefault(r, 0)
    return {r: counts[r] for r in REGIMES_LEGACY}


def regime_color(regime: str) -> str:
    """
    UI color. Handles both legacy 4-bucket labels and composite
    "CURVE/INV/VOL" labels — composite resolves on the curve axis.
    """
    if regime in REGIMES_LEGACY:
        return {
            "EXTREME_CONTANGO":      "#ff4d6d",
            "MILD_CONTANGO":         "#f5a623",
            "MILD_BACKWARDATION":    "#22d3ee",
            "EXTREME_BACKWARDATION": "#10d997",
        }[regime]
    # composite: color by curve bucket
    curve = regime.split("/", 1)[0] if "/" in regime else regime
    return {
        "CONTANGO": "#ff4d6d",
        "NEUTRAL":  "#f5a623",
        "BACK":     "#10d997",
    }.get(curve, "#6b809e")


if __name__ == "__main__":
    import os, sys
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    from data_lake import get_spread_15y

    df = get_spread_15y()
    print(f"Loaded {len(df)} rows of M1-M12 history")
    print(f"current curve bucket: {classify_curve(float(df['m1_m12'].iloc[-1]))}")
    print(f"composite (placeholder inv/vol): {composite_label(classify_curve(float(df['m1_m12'].iloc[-1])), 'LOW', 'NORMAL')}")
    print(f"\nThere are {len(REGIMES)} composite regimes (3x3x3 grid).")
