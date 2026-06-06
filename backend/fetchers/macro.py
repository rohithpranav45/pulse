"""
FRED Macro Fetcher
==================
Fetches key macro series from the St. Louis Federal Reserve (FRED) API.

Series:
    DGS10      — 10-Year Treasury Constant Maturity Rate (%)
    DCOILWTICO — WTI Crude Oil (spot, $/bbl cross-check)
    CPIAUCSL   — CPI All Urban Consumers (index, monthly)
    DEXUSEU    — USD per Euro exchange rate

Falls back to the last in-process cached value with stale=True when
FRED_API_KEY is not set or fredapi is not installed.
"""

import os
import sys
import logging
from datetime import datetime, timezone

_BACKEND = os.path.abspath(os.path.dirname(__file__))
_ROOT    = os.path.abspath(os.path.join(_BACKEND, ".."))
for _p in (_BACKEND, _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from dotenv import load_dotenv
load_dotenv()

log = logging.getLogger("pulse.macro")

_last_known: dict = {}

SERIES = {
    "dgs10":    ("DGS10",          "10Y Treasury Yield",    "%"),
    "wti_fred": ("DCOILWTICO",     "WTI Crude (FRED)",      "$/bbl"),
    "cpi":      ("CPIAUCSL",       "CPI All Urban",         "index"),
    "eurusd":   ("DEXUSEU",        "EUR/USD",               "rate"),
    "fedfunds": ("FEDFUNDS",       "Fed Funds Rate",        "%"),
    "indpro":   ("INDPRO",         "Industrial Production", "index"),
    "mortgage": ("MORTGAGE30US",   "30Y Mortgage Rate",     "%"),
}


def get_macro_data() -> dict:
    """
    Fetch macro indicators from FRED.

    Returns a dict with keys matching SERIES above, plus:
        stale     — True if FRED_API_KEY missing or fetch failed
        source    — "FRED"
        timestamp — ISO-8601 UTC string
        error     — human-readable reason (only present when stale)

    Each series sub-dict:
        value  — latest observation (float)
        date   — "YYYY-MM-DD"
        change — difference from prior observation (float | None)
        label  — human label
        unit   — unit string
    CPI additionally carries:
        yoy    — year-over-year % change vs 12 months prior (float | None)
    """
    global _last_known

    api_key = os.getenv("FRED_API_KEY", "").strip()

    if not api_key:
        log.warning("FRED_API_KEY not set — returning stale macro data")
        if _last_known:
            result = dict(_last_known)
            result["stale"] = True
            return result
        return {
            "stale":     True,
            "source":    "FRED",
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "error":     "FRED_API_KEY not configured",
        }

    try:
        from fredapi import Fred
    except ImportError:
        log.error("fredapi not installed — run: pip install fredapi")
        if _last_known:
            result = dict(_last_known)
            result["stale"] = True
            return result
        return {
            "stale":     True,
            "source":    "FRED",
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "error":     "fredapi package not installed",
        }

    fred   = Fred(api_key=api_key)
    result = {
        "stale":     False,
        "source":    "FRED",
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }

    successes = 0
    for key, (series_id, label, unit) in SERIES.items():
        try:
            # Fetch up to 14 observations so CPI YoY (13-period lag) is computable
            obs = fred.get_series(series_id).dropna().iloc[-14:]
            if obs.empty:
                result[key] = None
                continue

            latest = float(obs.iloc[-1])
            date   = obs.index[-1].strftime("%Y-%m-%d")
            change = round(latest - float(obs.iloc[-2]), 4) if len(obs) >= 2 else None

            entry = {
                "value":  round(latest, 4),
                "date":   date,
                "change": change,
                "label":  label,
                "unit":   unit,
            }

            if key == "cpi" and len(obs) >= 13:
                year_ago   = float(obs.iloc[-13])
                entry["yoy"] = round((latest - year_ago) / year_ago * 100, 2)

            if key == "indpro" and len(obs) >= 2:
                prior = float(obs.iloc[-2])
                if prior:
                    entry["mom"] = round((latest - prior) / prior * 100, 3)

            result[key] = entry
            successes += 1

        except Exception as exc:
            log.error("FRED series %s failed: %s", series_id, exc)
            result[key] = None

    # Mark stale only if NO series actually populated (everything failed). With
    # >=1 real value we have usable data and shouldn't show the stale banner.
    result["stale"] = successes == 0
    if successes == 0:
        result["error"] = "all FRED series failed"
    _last_known = dict(result)
    return result


if __name__ == "__main__":
    import json
    data = get_macro_data()
    print(json.dumps(data, indent=2, default=str))
