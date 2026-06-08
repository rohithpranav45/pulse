"""
Point-in-time feature matrix for the regime regressions.

Features chosen for the class demo are tight and fully backfillable
from data we already have on disk + FRED. No EIA/COT for v1 (would
need ~10 yrs of API calls — out of scope for today's session).

Features (per day, lagged so no future leakage):
  m1_m12        : the regime variable (kept as feature for level info)
  m1_m12_sq     : non-linear regime term
  m1_m2_lag1    : yesterday's M1-M2 (autocorrelation)
  m3_m6_lag1    : yesterday's M3-M6
  fly_lag1      : yesterday's front fly
  brent_close   : level of C1 (normalised)
  brent_ret_5d  : 5-day Brent return
  realised_vol  : 20-day realised vol of C1
  sin_month     : seasonal sine
  cos_month     : seasonal cosine

When modelling a target spread, we drop its own lag (no self-leakage)
but keep the others as cross-curve features.

Public API
----------
  build_features() → pd.DataFrame indexed by date, columns above + 'regime'
"""

from __future__ import annotations

import os, sys
import numpy as np
import pandas as pd

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)


def build_features() -> pd.DataFrame:
    """
    Return point-in-time feature matrix.

    Index: date. All features available as-of CLOSE of that day.
    Lagged features are explicit (lag1 = previous day's close).
    """
    from data_lake import get_brent_settlements
    from research.regimes import classify_series
    from research.spread_universe import build_spread_series

    settle  = get_brent_settlements()
    spreads = build_spread_series()

    if settle is None or settle.empty:
        raise RuntimeError("Brent settlements missing")

    # Join the two sources on date (settlements has M1-M12 via c1-c12)
    df = pd.DataFrame(index=settle.index)
    df["m1_m12"]    = settle["c1"] - settle["c12"]
    df["m1_m12_sq"] = df["m1_m12"] ** 2

    # Cross-spread features
    df["brent_close"] = settle["c1"]
    df["brent_ret_5d"] = settle["c1"].pct_change(5)

    # Realised vol — 20d std of daily log returns
    log_ret = np.log(settle["c1"] / settle["c1"].shift(1))
    df["realised_vol_20d"] = log_ret.rolling(20).std() * np.sqrt(252)

    # Seasonal: sin/cos of day-of-year
    day_of_year = pd.Series(df.index.dayofyear, index=df.index)
    df["sin_doy"] = np.sin(2 * np.pi * day_of_year / 365.25)
    df["cos_doy"] = np.cos(2 * np.pi * day_of_year / 365.25)

    # Spread lags (yesterday's values)
    df["m1_m2_lag1"]   = spreads["brent_m1_m2"].shift(1)
    df["m3_m6_lag1"]   = spreads["brent_m3_m6"].shift(1)
    df["fly_lag1"]     = spreads["brent_fly_123"].shift(1)

    # Regime label
    df["regime"] = classify_series(df["m1_m12"])

    # Drop early rows missing lag/vol/return features
    df = df.dropna()
    return df


def predictors_for(target_spread: str) -> list[str]:
    """
    Return the feature column names for a target spread.
    Drops the target's own lag1 to prevent self-leakage.
    """
    base = ["m1_m12", "m1_m12_sq", "brent_close", "brent_ret_5d",
            "realised_vol_20d", "sin_doy", "cos_doy",
            "m1_m2_lag1", "m3_m6_lag1", "fly_lag1"]
    self_lag = {
        "brent_m1_m2":   "m1_m2_lag1",
        "brent_m3_m6":   "m3_m6_lag1",
        "brent_fly_123": "fly_lag1",
    }[target_spread]
    return [c for c in base if c != self_lag]


if __name__ == "__main__":
    df = build_features()
    print(f"Feature matrix: {df.shape[0]} rows × {df.shape[1]} cols")
    print(f"Date range: {df.index.min().date()} → {df.index.max().date()}")
    print(f"\nColumns: {list(df.columns)}")
    print(f"\nRegime distribution:")
    for r, n in df['regime'].value_counts().items():
        print(f"  {r:<25}  {n:>5}")
    print(f"\nLatest row:")
    print(df.iloc[-1].to_dict())
