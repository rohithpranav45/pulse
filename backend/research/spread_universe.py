"""
Define the 3 instruments we model for the class-demo.

All sourced from /Data Brent settlements (c1..c31 daily, 2016+). For
pre-2016 history we fall back to the 15-yr xlsx which has c1 + c12 only —
so M1-M2 / M3-M6 / front fly are 2016-onward (2,713 days, plenty).

Instruments
-----------
  brent_m1_m2   :  c1 - c2                 (front carry)
  brent_m3_m6   :  c3 - c6                 (mid-curve carry)
  brent_fly_123 :  c1 - 2*c2 + c3          (front butterfly)

The mentor wants ONE recommendation per day — ranker picks among these 3.
"""

from __future__ import annotations

import os, sys
import pandas as pd

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

INSTRUMENTS = ["brent_m1_m2", "brent_m3_m6", "brent_fly_123"]

LABELS = {
    "brent_m1_m2":   "Brent M1-M2",
    "brent_m3_m6":   "Brent M3-M6",
    "brent_fly_123": "Brent front fly (M1-2×M2+M3)",
}

DESCRIPTIONS = {
    "brent_m1_m2":   "Front-month carry. Collapses in deep contango, blows out in extreme backwardation.",
    "brent_m3_m6":   "Mid-curve carry. More stable than front; regime-dependence is subtle but persistent.",
    "brent_fly_123": "Convexity of the front of the curve. Negative fly = kink, positive = smooth curve.",
}


def build_spread_series() -> pd.DataFrame:
    """
    Return a DataFrame indexed by date with one column per instrument.
    Uses /Data Brent C1-C31 settlements (2016-2026).

    Columns: brent_m1_m2, brent_m3_m6, brent_fly_123
    """
    from data_lake import get_brent_settlements
    df = get_brent_settlements()
    if df is None or df.empty:
        raise RuntimeError("Brent settlements file missing — cannot build spread universe")

    out = pd.DataFrame(index=df.index)
    out["brent_m1_m2"]   = df["c1"] - df["c2"]
    out["brent_m3_m6"]   = df["c3"] - df["c6"]
    out["brent_fly_123"] = df["c1"] - 2.0 * df["c2"] + df["c3"]
    return out.dropna(how="all")


def current_values() -> dict:
    """Most-recent value of each instrument from settlements."""
    df = build_spread_series()
    latest = df.iloc[-1]
    return {
        "as_of":         df.index[-1].strftime("%Y-%m-%d"),
        "brent_m1_m2":   float(latest["brent_m1_m2"]),
        "brent_m3_m6":   float(latest["brent_m3_m6"]),
        "brent_fly_123": float(latest["brent_fly_123"]),
    }


if __name__ == "__main__":
    df = build_spread_series()
    print(f"Spread universe: {len(df)} days, {df.index.min().date()} → {df.index.max().date()}")
    print("\nLatest values:")
    for k, v in current_values().items():
        if k == "as_of":
            print(f"  as_of: {v}")
        else:
            print(f"  {k:<18}  {v:+.3f}")
    print("\nDescriptive stats:")
    print(df.describe().T[["count", "mean", "std", "min", "max"]].round(3))
