"""
15-year Brent curve regime statistics.
======================================
Computes proper percentile / z-score for the M1-M12 spread using the
3,693-row 15-year history file in /Data, instead of showing a bare number
with no context.

Public API
----------
  get_curve_regime() -> dict
    {
      "available":      bool,
      "current_m1_m12": float,
      "as_of":          "YYYY-MM-DD",
      "history_start":  str,
      "history_years":  float,
      "percentile":     float,   # 0..1 — where today sits in 15y
      "z_score":        float,
      "mean":           float,
      "std":            float,
      "regime":         "EXTREME_BACKWARDATION" | "BACKWARDATION" |
                        "FLAT" | "CONTANGO" | "EXTREME_CONTANGO",
      "regime_pct":     float,   # share of last 15y in same regime
      "p10":            float,
      "p90":            float,
      "history_tail":   [{"date": str, "m1_m12": float}, …],   # last 90 days for sparkline
    }
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd

_BACKEND = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

log = logging.getLogger("pulse.curve_regime")


def _classify(spread: float) -> str:
    if spread >  10.0: return "EXTREME_BACKWARDATION"
    if spread >   2.0: return "BACKWARDATION"
    if spread >  -2.0: return "FLAT"
    if spread > -10.0: return "CONTANGO"
    return "EXTREME_CONTANGO"


def get_curve_regime() -> dict:
    try:
        from data_lake import get_spread_15y
    except Exception as exc:
        return {"available": False, "error": f"data_lake import: {exc}",
                "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds")}

    df = get_spread_15y()
    if df is None or df.empty:
        return {"available": False, "error": "15y spread file missing",
                "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds")}

    s = df["m1_m12"].astype(float).dropna()
    if s.empty:
        return {"available": False, "error": "spread series empty",
                "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds")}

    current = float(s.iloc[-1])
    mean    = float(s.mean())
    std     = float(s.std()) if len(s) > 1 else 0.0
    pct     = float((s <= current).sum() / len(s))
    z       = float((current - mean) / std) if std > 0 else 0.0
    regime  = _classify(current)
    same_regime_share = float(s.apply(_classify).eq(regime).mean())

    tail_90 = df.tail(90).reset_index()
    tail_90["date"] = tail_90["date"].dt.strftime("%Y-%m-%d")
    history_tail = tail_90[["date", "m1_m12"]].to_dict(orient="records")

    yrs = (df.index[-1] - df.index[0]).days / 365.25

    return {
        "available":      True,
        "current_m1_m12": round(current, 3),
        "as_of":          df.index[-1].strftime("%Y-%m-%d"),
        "history_start":  df.index[0].strftime("%Y-%m-%d"),
        "history_years":  round(yrs, 1),
        "n_obs":          int(len(s)),
        "percentile":     round(pct, 4),
        "z_score":        round(z, 3),
        "mean":           round(mean, 3),
        "std":            round(std, 3),
        "p10":            round(float(np.percentile(s, 10)), 3),
        "p90":            round(float(np.percentile(s, 90)), 3),
        "regime":         regime,
        "regime_pct":     round(same_regime_share, 4),
        "history_tail":   history_tail,
        "source":         "ICE LCO 15-yr M1-M12 (/Data)",
        "timestamp":      datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


if __name__ == "__main__":
    import json
    r = get_curve_regime()
    # Drop the long array for printing
    summary = {k: v for k, v in r.items() if k != "history_tail"}
    print(json.dumps(summary, indent=2))
    print("history_tail (last 3):", r.get("history_tail", [])[-3:])
