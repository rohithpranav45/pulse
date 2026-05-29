"""
Days of Forward Cover — historical chart.

Pulls 5 years of weekly US crude stocks from EIA, divides by US refinery
demand (~17 mbd) to get "days of forward demand cover." This is the
metric chapter 6 of the curriculum highlights:

  "Critical low: < 54 days for OECD is historically associated with
   $90+ Brent."

We use US-only crude as a proxy (OECD aggregate has a longer publication
lag). Adds a 5-year seasonal-band envelope so the user can see whether
today is unusually high/low for the calendar week.

Public function:
  get_forward_cover_history(years=5) -> dict
"""

from __future__ import annotations

import logging
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone

_BACKEND = os.path.abspath(os.path.dirname(__file__))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

log = logging.getLogger("pulse.forward_cover")

# US refinery crude demand — long-term average input rate
US_REFINERY_DEMAND_MBD = 17.0


def get_forward_cover_history(years: int = 5) -> dict:
    """
    Return a time series of US days-of-forward-cover for the last `years`
    years, plus a 5-year seasonal-band envelope keyed by ISO calendar week.

    Returns
    -------
    {
      "history": [{"date": "YYYY-MM-DD", "value": float (days), "stocks": float (Mbbl)}, ...],
      "seasonal_band": [{"week": 1..53, "p10": float, "p50": float, "p90": float}, ...],
      "current": float (days),
      "current_stocks": float (Mbbl),
      "current_date": str,
      "demand_assumption": 17.0,
      "critical_low":  54,        # curriculum: <54 days -> historically tight
      "comfortable_high": 65,
      "timestamp": str
    }
    """
    try:
        from fetchers.eia import _fetch_series
    except Exception as exc:
        log.warning("eia helper import failed: %s", exc)
        return _empty()

    weeks = years * 52 + 8  # buffer for seasonal computation
    try:
        rows = _fetch_series(
            "https://api.eia.gov/v2/petroleum/sum/sndw/data/",
            "WCRSTUS1",
            length=weeks,
        )
    except Exception as exc:
        log.warning("eia stocks fetch failed: %s", exc)
        return _empty()

    cleaned = []
    for r in reversed(rows):  # chronological
        try:
            cleaned.append({"date": r["period"], "value": float(r["value"])})
        except (KeyError, TypeError, ValueError):
            continue

    if not cleaned:
        return _empty()

    # Convert stocks (Mbbl, i.e. thousands of barrels) to days of cover:
    #   stocks_kb / (demand_mbd * 1000) = days
    history = []
    for r in cleaned:
        stocks_kb = r["value"]
        days = stocks_kb / (US_REFINERY_DEMAND_MBD * 1000.0)
        history.append({
            "date":   r["date"],
            "stocks": round(stocks_kb, 1),
            "value":  round(days, 2),
        })

    # Seasonal band: percentile of days-of-cover by ISO calendar week
    by_week: dict[int, list[float]] = defaultdict(list)
    for h in history:
        try:
            wk = datetime.strptime(h["date"], "%Y-%m-%d").isocalendar()[1]
            by_week[wk].append(h["value"])
        except ValueError:
            continue

    def _pct(vals: list[float], p: float) -> float:
        if not vals: return 0.0
        s = sorted(vals)
        idx = max(0, min(len(s) - 1, int(round(p * (len(s) - 1)))))
        return s[idx]

    seasonal_band = []
    for wk in range(1, 54):
        vals = by_week.get(wk, [])
        if vals:
            seasonal_band.append({
                "week": wk,
                "p10":  round(_pct(vals, 0.10), 2),
                "p50":  round(_pct(vals, 0.50), 2),
                "p90":  round(_pct(vals, 0.90), 2),
                "n":    len(vals),
            })

    latest = history[-1]
    return {
        "history":           history,
        "seasonal_band":     seasonal_band,
        "current":           latest["value"],
        "current_stocks":    latest["stocks"],
        "current_date":      latest["date"],
        "demand_assumption": US_REFINERY_DEMAND_MBD,
        "critical_low":      54,
        "comfortable_high":  65,
        "years":             years,
        "timestamp":         datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def _empty() -> dict:
    return {
        "history": [], "seasonal_band": [], "current": None,
        "current_stocks": None, "current_date": None,
        "demand_assumption": US_REFINERY_DEMAND_MBD,
        "critical_low": 54, "comfortable_high": 65, "years": 0,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    d = get_forward_cover_history(years=5)
    print(f"Years: {d['years']}  Series: {len(d['history'])}  Bands: {len(d['seasonal_band'])}")
    print(f"Current: {d['current']:.2f} days  ({d['current_stocks']:.0f} kb)  on {d['current_date']}")
    print(f"Critical low: {d['critical_low']}  Comfortable high: {d['comfortable_high']}")
    print()
    print("Last 8 weeks:")
    for h in d["history"][-8:]:
        print(f"  {h['date']}  {h['value']:>6.2f}d   ({h['stocks']:>8.0f} kb)")
