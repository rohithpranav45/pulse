"""
4-bucket curve regime classifier.

Regime is determined by the Brent M1-M12 spread in $/bbl:

    M1-M12 ≤ -5           → EXTREME_CONTANGO        (storage glut)
    -5 < M1-M12 ≤ 0       → MILD_CONTANGO            (oversupplied but calm)
    0 < M1-M12 ≤ +10      → MILD_BACKWARDATION       (normal tight)
    M1-M12 > +10          → EXTREME_BACKWARDATION    (Hormuz / Russia style)

Hard thresholds chosen over quartiles because they're self-explanatory
to a trader reading the dashboard ("+$10 IS extreme" is more defensible
than "75th percentile").

Public API
----------
  classify_one(m1_m12_value)   → regime string
  classify_series(series)      → pd.Series of regime labels indexed by date
  REGIMES                       → ordered list of regime names
  regime_distribution(history) → {regime: count}
"""

from __future__ import annotations

from typing import Iterable
import pandas as pd

# Ordered for UI display (most-contango → most-back)
REGIMES = [
    "EXTREME_CONTANGO",
    "MILD_CONTANGO",
    "MILD_BACKWARDATION",
    "EXTREME_BACKWARDATION",
]

# Thresholds in $/bbl on the M1-M12 spread
_THRESHOLDS = {
    "EXTREME_CONTANGO":      (None, -5.0),
    "MILD_CONTANGO":         (-5.0,  0.0),
    "MILD_BACKWARDATION":    ( 0.0, 10.0),
    "EXTREME_BACKWARDATION": (10.0, None),
}


def classify_one(m1_m12: float) -> str:
    """Classify a single M1-M12 spread value."""
    if m1_m12 is None or (isinstance(m1_m12, float) and m1_m12 != m1_m12):
        return "UNKNOWN"
    if m1_m12 <= -5.0:    return "EXTREME_CONTANGO"
    if m1_m12 <=  0.0:    return "MILD_CONTANGO"
    if m1_m12 <= 10.0:    return "MILD_BACKWARDATION"
    return "EXTREME_BACKWARDATION"


def classify_series(spread_series: pd.Series) -> pd.Series:
    """Classify a full pandas Series of M1-M12 values → regime labels."""
    return spread_series.apply(classify_one).rename("regime")


def regime_distribution(spread_series: pd.Series) -> dict:
    """Return {regime: count} for a historical spread series."""
    labels = classify_series(spread_series)
    counts = labels.value_counts().to_dict()
    # Fill missing regimes with 0
    for r in REGIMES:
        counts.setdefault(r, 0)
    return {r: counts[r] for r in REGIMES}


def regime_color(regime: str) -> str:
    """UI color for each regime (matches dashboard palette)."""
    return {
        "EXTREME_CONTANGO":      "#ff4d6d",  # bear red
        "MILD_CONTANGO":         "#f5a623",  # neut amber
        "MILD_BACKWARDATION":    "#22d3ee",  # cyan
        "EXTREME_BACKWARDATION": "#10d997",  # bull green
    }.get(regime, "#6b809e")  # text-tertiary


if __name__ == "__main__":
    import os, sys
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    from data_lake import get_spread_15y
    df = get_spread_15y()
    print(f"Loaded {len(df)} rows of M1-M12 history "
          f"({df.index.min().date()} → {df.index.max().date()})")
    dist = regime_distribution(df["m1_m12"])
    print("\nRegime distribution (whole history):")
    for r, n in dist.items():
        pct = n / len(df) * 100
        print(f"  {r:<25}  {n:>5} days  ({pct:>5.1f}%)")
    print(f"\nCurrent regime (last day {df.index[-1].date()}, "
          f"M1-M12={df['m1_m12'].iloc[-1]:.2f}): "
          f"{classify_one(df['m1_m12'].iloc[-1])}")
