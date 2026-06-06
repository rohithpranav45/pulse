"""
CBOE OVX (Crude Oil ETF Volatility Index) — REAL implied vol benchmark.
======================================================================
OVX measures the market's 30-day implied vol of USO ATM options. This is
the institutional reference for "crude IV" — far stronger than realised-vol
proxies. Free via FRED (series OVXCLS).

Public API
----------
  get_ovx() -> dict
    {
      "current":   float,   # latest level (annualised % vol, e.g. 35.2)
      "date":      str,     # YYYY-MM-DD
      "change":    float,
      "pctile_5y": float,   # rank within last ~1260 obs
      "pctile_1y": float,   # rank within last ~252 obs
      "n_obs":     int,
      "source":    "FRED OVXCLS",
      "stale":     bool,
      "timestamp": iso str,
      "error":     str?,
    }
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timezone

_BACKEND = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from dotenv import load_dotenv
load_dotenv()

log = logging.getLogger("pulse.ovx")

_last_known: dict = {}


def get_ovx() -> dict:
    """Pull CBOE OVX from FRED (no auth) and compute percentile ranks."""
    global _last_known

    api_key = os.getenv("FRED_API_KEY", "").strip()
    out = {
        "current":   None,
        "date":      None,
        "change":    None,
        "pctile_5y": None,
        "pctile_1y": None,
        "n_obs":     0,
        "source":    "FRED OVXCLS",
        "stale":     True,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }

    if not api_key:
        out["error"] = "FRED_API_KEY not configured"
        return _last_known if _last_known else out

    try:
        from fredapi import Fred
    except ImportError:
        out["error"] = "fredapi not installed"
        return _last_known if _last_known else out

    try:
        fred = Fred(api_key=api_key)
        s = fred.get_series("OVXCLS").dropna()
        if s.empty:
            out["error"] = "OVXCLS returned no observations"
            return _last_known if _last_known else out

        latest = float(s.iloc[-1])
        prev   = float(s.iloc[-2]) if len(s) >= 2 else latest
        # 5y window ≈ 1260 trading days
        tail5y = s.tail(1260)
        tail1y = s.tail(252)
        pct5   = float((tail5y <= latest).sum() / len(tail5y))
        pct1   = float((tail1y <= latest).sum() / len(tail1y))

        out.update({
            "current":   round(latest, 2),
            "date":      s.index[-1].strftime("%Y-%m-%d"),
            "change":    round(latest - prev, 2),
            "pctile_5y": round(pct5, 4),
            "pctile_1y": round(pct1, 4),
            "n_obs":     int(len(s)),
            "stale":     False,
        })
        _last_known = dict(out)
        return out

    except Exception as exc:
        log.error("FRED OVX fetch failed: %s", exc)
        out["error"] = str(exc)[:200]
        return _last_known if _last_known else out


if __name__ == "__main__":
    import json
    logging.basicConfig(level=logging.INFO)
    print(json.dumps(get_ovx(), indent=2))
