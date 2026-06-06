"""
Matrix-profile pattern-analog search using `stumpy`.
====================================================
Finds historical Brent windows that most closely resemble the current
~60-day price fingerprint. For each top-K analog we return:
  - start date, end date
  - similarity distance (lower = better match)
  - forward return over the matched horizon (what happened next)

This is the institutional analog-matching technique — far more rigorous
than the hand-coded analog table in `models/patterns.py`.

Install: pip install stumpy

The module gracefully no-ops if stumpy is missing OR if the /Data lake
isn't available, so the dashboard remains functional.
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

log = logging.getLogger("pulse.analogs")


def get_pattern_analogs(window_days: int = 60, top_k: int = 3, horizon_days: int = 20) -> dict:
    """
    Find top-K historical windows whose ~60-day price shape most closely
    matches the current window. Uses the 15-year LCOc1 close series from
    /Data via the data_lake.

    Returns
    -------
    {
      available:    bool,
      window_days:  int,
      top_k:        int,
      horizon_days: int,
      analogs:      [
        {
          start_date, end_date,
          distance,            # matrix-profile distance
          forward_return_pct,  # close at end+horizon vs end
          forward_horizon_days,
        }, ...
      ],
      source:    "stumpy matrix profile on /Data 15y LCOc1",
      stale:     bool,
      timestamp: iso str,
      error?:    str,
    }
    """
    out = {
        "available":    False,
        "window_days":  window_days,
        "top_k":        top_k,
        "horizon_days": horizon_days,
        "analogs":      [],
        "source":       "stumpy matrix profile on /Data 15y LCOc1",
        "stale":        True,
        "timestamp":    datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }

    # ── Soft-dependency check ──────────────────────────────────────────────
    try:
        import stumpy
    except ImportError:
        out["error"] = "stumpy not installed — run: pip install stumpy"
        return out

    # ── Load 15-yr LCOc1 series from /Data ─────────────────────────────────
    try:
        from data_lake import get_brent_settlements
        df = get_brent_settlements()
    except Exception as exc:
        out["error"] = f"data_lake error: {exc}"
        return out
    if df is None or df.empty or "c1" not in df.columns:
        out["error"] = "Brent C1 settlements unavailable"
        return out

    series = df["c1"].astype(float).dropna()
    if len(series) < window_days + horizon_days + 10:
        out["error"] = "not enough history"
        return out

    # ── Compute matrix profile ─────────────────────────────────────────────
    try:
        values = series.values.astype(np.float64)
        mp = stumpy.stump(values, m=window_days)
        # mp[:, 0] is the matrix-profile distance per window
        distances = mp[:, 0]
    except Exception as exc:
        out["error"] = f"stumpy.stump failed: {exc}"
        return out

    # ── The current window = the last window in the series ─────────────────
    current_idx = len(values) - window_days
    # Find the K nearest neighbours of the current window
    # mp[i, 1] is the index of i's NN. We want NN of current_idx specifically:
    # compute distance from current window to every other window manually
    # (faster than recomputing full self-join, and we already have the values).
    cur = values[current_idx : current_idx + window_days]
    cur_z = (cur - cur.mean()) / (cur.std() + 1e-12)

    cand_distances = []
    for i in range(0, len(values) - window_days - horizon_days):
        if abs(i - current_idx) < window_days:  # exclude trivial neighbours
            continue
        win = values[i : i + window_days]
        if win.std() == 0:
            continue
        win_z = (win - win.mean()) / (win.std() + 1e-12)
        d = float(np.linalg.norm(cur_z - win_z))
        cand_distances.append((d, i))

    cand_distances.sort()
    chosen = cand_distances[:top_k]

    analogs = []
    for dist, i in chosen:
        end_idx = i + window_days
        end_price = float(values[end_idx])
        forward_idx = min(end_idx + horizon_days, len(values) - 1)
        forward_price = float(values[forward_idx])
        forward_return = (forward_price / end_price - 1.0) * 100
        analogs.append({
            "start_date":           series.index[i].strftime("%Y-%m-%d"),
            "end_date":             series.index[end_idx].strftime("%Y-%m-%d"),
            "distance":             round(dist, 4),
            "forward_return_pct":   round(forward_return, 2),
            "forward_horizon_days": horizon_days,
        })

    # Average forward return across analogs = our backtested forward bias
    if analogs:
        avg_fwd = sum(a["forward_return_pct"] for a in analogs) / len(analogs)
        out["avg_forward_return_pct"] = round(avg_fwd, 2)
        out["bias"] = "BULLISH" if avg_fwd > 1 else "BEARISH" if avg_fwd < -1 else "NEUTRAL"

    out["available"] = True
    out["stale"]     = False
    out["analogs"]   = analogs
    out["current_window"] = {
        "start_date": series.index[current_idx].strftime("%Y-%m-%d"),
        "end_date":   series.index[-1].strftime("%Y-%m-%d"),
    }
    return out


if __name__ == "__main__":
    import json
    logging.basicConfig(level=logging.INFO)
    r = get_pattern_analogs()
    print(json.dumps(r, indent=2))
