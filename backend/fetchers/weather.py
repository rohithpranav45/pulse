"""
Weather Fetcher — HDD / CDD demand signals for Henry Hub natural gas.
=====================================================================
Uses Open-Meteo (https://open-meteo.com/) — completely free, no API key.

What it does
------------
  1. Fetches a 7-day hourly temperature forecast for five major US gas-demand
     hubs (New York, Chicago, Dallas, Atlanta, Boston).
  2. Computes population-weighted daily HDD and CDD from the forecast.
  3. Compares the 7-day outlook to long-run seasonal normals (1991-2020 NOAA
     Climate Normals, hard-coded monthly averages per city).
  4. Returns a deviation from normal so the signal engine can score it.

Public API
----------
  get_weather_signal() → dict
    {
      "hdd_7day":          float,   # population-weighted 7-day HDD total
      "cdd_7day":          float,   # population-weighted 7-day CDD total
      "hdd_normal":        float,   # expected HDD for same calendar period
      "cdd_normal":        float,   # expected CDD for same calendar period
      "hdd_deviation_pct": float,   # (actual-normal)/normal * 100
      "cdd_deviation_pct": float,
      "net_demand_signal": float,   # positive = bullish demand, negative = bearish
      "summary":           str,
      "cities":            list[dict],
      "timestamp":         str,
    }

HDD / CDD definition
--------------------
  HDD = max(0, 65°F − mean_daily_temp_°F)
  CDD = max(0, mean_daily_temp_°F − 65°F)
  Balance point: 65°F / 18.3°C (US EIA standard)

City weights (proportional to residential gas consumption, approximate)
-----------------------------------------------------------------------
  New York City   25%
  Chicago         22%
  Dallas/Fort Worth 18%
  Atlanta         17%
  Boston          18%
"""

import os as _os, sys as _sys
_BACKEND = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), ".."))
if _BACKEND not in _sys.path:
    _sys.path.insert(0, _BACKEND)

import requests
import logging
from datetime import datetime, timezone, timedelta
from typing import Any

log = logging.getLogger(__name__)

# ── City definitions ─────────────────────────────────────────────────────────
#   (name, latitude, longitude, weight, monthly_normal_F[0..11])
#
#   Monthly normals: mean daily temperature in °F for each month (Jan=0).
#   Source: NOAA 1991-2020 Climate Normals (monthly mean of daily mean temps).

_CITIES = [
    {
        "name":    "New York",
        "lat":     40.71,
        "lon":    -74.01,
        "weight":  0.25,
        # Jan  Feb  Mar  Apr  May  Jun  Jul  Aug  Sep  Oct  Nov  Dec
        "normals_f": [33.0, 35.0, 43.0, 54.0, 63.0, 72.0, 77.0, 75.0, 68.0, 57.0, 47.0, 37.0],
    },
    {
        "name":    "Chicago",
        "lat":     41.88,
        "lon":    -87.63,
        "weight":  0.22,
        "normals_f": [23.0, 27.0, 37.0, 49.0, 59.0, 69.0, 74.0, 72.0, 65.0, 53.0, 40.0, 28.0],
    },
    {
        "name":    "Dallas",
        "lat":     32.78,
        "lon":    -96.80,
        "weight":  0.18,
        "normals_f": [46.0, 50.0, 58.0, 66.0, 74.0, 82.0, 86.0, 86.0, 79.0, 68.0, 57.0, 48.0],
    },
    {
        "name":    "Atlanta",
        "lat":     33.75,
        "lon":    -84.39,
        "weight":  0.17,
        "normals_f": [44.0, 48.0, 55.0, 63.0, 71.0, 78.0, 81.0, 80.0, 74.0, 63.0, 54.0, 46.0],
    },
    {
        "name":    "Boston",
        "lat":     42.36,
        "lon":    -71.06,
        "weight":  0.18,
        "normals_f": [29.0, 31.0, 39.0, 49.0, 59.0, 68.0, 74.0, 72.0, 64.0, 54.0, 44.0, 33.0],
    },
]

_BALANCE_F = 65.0      # standard US EIA HDD/CDD balance point
_TIMEOUT   = 10        # seconds per HTTP request

# ── Open-Meteo endpoint ───────────────────────────────────────────────────────
_OM_URL = (
    "https://api.open-meteo.com/v1/forecast"
    "?latitude={lat}&longitude={lon}"
    "&hourly=temperature_2m"
    "&temperature_unit=fahrenheit"
    "&forecast_days=7"
    "&timezone=America%2FNew_York"
)


def _fetch_city_temps(lat: float, lon: float) -> list[float] | None:
    """
    Fetch 7-day hourly temperature forecast from Open-Meteo.
    Returns list of hourly °F values (up to 168 values), or None on failure.
    """
    url = _OM_URL.format(lat=lat, lon=lon)
    try:
        resp = requests.get(url, timeout=_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        temps = data.get("hourly", {}).get("temperature_2m", [])
        return [float(t) for t in temps if t is not None]
    except Exception as exc:
        log.warning("Open-Meteo fetch failed for (%.2f, %.2f): %s", lat, lon, exc)
        return None


def _hourly_to_daily_hdd_cdd(hourly_temps: list[float]) -> list[dict]:
    """
    Convert hourly °F temps into daily HDD/CDD.
    Groups by 24-hour chunks (each chunk = one day).
    """
    days = []
    for i in range(0, len(hourly_temps), 24):
        chunk = hourly_temps[i : i + 24]
        if not chunk:
            continue
        mean_f = sum(chunk) / len(chunk)
        days.append({
            "mean_f": round(mean_f, 2),
            "hdd":    round(max(0.0, _BALANCE_F - mean_f), 2),
            "cdd":    round(max(0.0, mean_f - _BALANCE_F), 2),
        })
    return days


def _seasonal_normal_hdd_cdd(normals_f: list[float], n_days: int = 7) -> tuple[float, float]:
    """
    Estimate the expected HDD and CDD for the next n_days given monthly normals.
    Distributes equally across the n_days starting from today.
    """
    today = datetime.now()
    hdd_total = cdd_total = 0.0
    for offset in range(n_days):
        day = today + timedelta(days=offset)
        month_idx = day.month - 1
        norm_f = normals_f[month_idx]
        hdd_total += max(0.0, _BALANCE_F - norm_f)
        cdd_total += max(0.0, norm_f - _BALANCE_F)
    return round(hdd_total, 2), round(cdd_total, 2)


def _deviation_pct(actual: float, normal: float) -> float:
    """Percentage deviation from normal; returns 0 if normal is near zero."""
    if abs(normal) < 0.5:
        return 0.0
    return round((actual - normal) / normal * 100, 1)


# ── Fallback (returned when all API calls fail) ───────────────────────────────
def _fallback_signal() -> dict:
    """Return a neutral signal with a clear error flag when data is unavailable."""
    return {
        "hdd_7day":          0.0,
        "cdd_7day":          0.0,
        "hdd_normal":        0.0,
        "cdd_normal":        0.0,
        "hdd_deviation_pct": 0.0,
        "cdd_deviation_pct": 0.0,
        "net_demand_signal": 0.0,
        "summary":           "Weather data unavailable — API unreachable",
        "cities":            [],
        "error":             True,
        "timestamp":         datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


# ── Main public function ──────────────────────────────────────────────────────
def get_weather_signal() -> dict:
    """
    Fetch 7-day HDD/CDD outlook for five major US gas-demand hubs and compare
    to seasonal normals.

    Returns a weighted aggregate across all cities.
    """
    city_results   = []
    w_hdd          = 0.0   # weighted sum of 7-day HDD
    w_cdd          = 0.0   # weighted sum of 7-day CDD
    w_hdd_norm     = 0.0   # weighted sum of normal HDD
    w_cdd_norm     = 0.0   # weighted sum of normal CDD
    total_weight   = 0.0

    for city in _CITIES:
        hourly = _fetch_city_temps(city["lat"], city["lon"])
        if not hourly:
            log.warning("Skipping %s — no temperature data", city["name"])
            continue

        days    = _hourly_to_daily_hdd_cdd(hourly)
        hdd_7d  = sum(d["hdd"] for d in days)
        cdd_7d  = sum(d["cdd"] for d in days)
        n_days  = len(days)
        hdd_n, cdd_n = _seasonal_normal_hdd_cdd(city["normals_f"], n_days=n_days)

        w = city["weight"]
        w_hdd      += hdd_7d * w
        w_cdd      += cdd_7d * w
        w_hdd_norm += hdd_n  * w
        w_cdd_norm += cdd_n  * w
        total_weight += w

        city_results.append({
            "city":              city["name"],
            "hdd_7day":          round(hdd_7d, 1),
            "cdd_7day":          round(cdd_7d, 1),
            "hdd_normal":        hdd_n,
            "cdd_normal":        cdd_n,
            "hdd_deviation_pct": _deviation_pct(hdd_7d, hdd_n),
            "cdd_deviation_pct": _deviation_pct(cdd_7d, cdd_n),
        })

    # ── all cities failed ─────────────────────────────────────────────────────
    if total_weight == 0 or not city_results:
        log.error("All weather fetches failed — returning neutral fallback")
        return _fallback_signal()

    # ── normalise by collected weight ─────────────────────────────────────────
    # (handles case where some cities failed)
    agg_hdd      = round(w_hdd      / total_weight, 1)
    agg_cdd      = round(w_cdd      / total_weight, 1)
    agg_hdd_norm = round(w_hdd_norm / total_weight, 1)
    agg_cdd_norm = round(w_cdd_norm / total_weight, 1)

    hdd_dev = _deviation_pct(agg_hdd, agg_hdd_norm)
    cdd_dev = _deviation_pct(agg_cdd, agg_cdd_norm)

    # ── net demand signal ─────────────────────────────────────────────────────
    # HDD drives heating gas demand (bullish when above normal).
    # CDD drives cooling electricity demand which reduces pipeline pressure
    # on nat gas (mildly bullish but less direct than HDD).
    # We use a weighted sum: HDD_dev dominates in winter, CDD_dev in summer.
    month = datetime.now().month
    is_heating_season = month in (11, 12, 1, 2, 3)   # Nov – Mar
    is_cooling_season = month in (6, 7, 8, 9)         # Jun – Sep

    if is_heating_season:
        net = hdd_dev * 0.80 + cdd_dev * 0.20
        season = "heating"
    elif is_cooling_season:
        net = hdd_dev * 0.20 + cdd_dev * 0.80
        season = "cooling"
    else:
        net = hdd_dev * 0.50 + cdd_dev * 0.50   # shoulder season
        season = "shoulder"

    net = round(net, 1)

    # ── human summary ─────────────────────────────────────────────────────────
    if net > 20:
        summary = f"Much colder than normal (+{hdd_dev:.0f}% HDD) — strong demand signal"
    elif net > 8:
        summary = f"Cooler than normal (+{hdd_dev:.0f}% HDD) — above-avg demand"
    elif net > -8:
        summary = f"Near-normal temperatures — demand inline with seasonal avg"
    elif net > -20:
        summary = f"Warmer than normal ({hdd_dev:.0f}% HDD) — below-avg demand"
    else:
        summary = f"Much warmer than normal ({hdd_dev:.0f}% HDD) — weak demand signal"

    return {
        "hdd_7day":          agg_hdd,
        "cdd_7day":          agg_cdd,
        "hdd_normal":        agg_hdd_norm,
        "cdd_normal":        agg_cdd_norm,
        "hdd_deviation_pct": hdd_dev,
        "cdd_deviation_pct": cdd_dev,
        "net_demand_signal": net,
        "season":            season,
        "summary":           summary,
        "cities":            city_results,
        "error":             False,
        "timestamp":         datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


# ── __main__ — quick CLI test ─────────────────────────────────────────────────
if __name__ == "__main__":
    import json
    print("\nFetching 7-day weather signal...\n")
    result = get_weather_signal()
    print(json.dumps(result, indent=2))

    if not result.get("error"):
        print(f"\n  HDD 7-day:   {result['hdd_7day']} (normal: {result['hdd_normal']})")
        print(f"  CDD 7-day:   {result['cdd_7day']} (normal: {result['cdd_normal']})")
        print(f"  HDD dev:     {result['hdd_deviation_pct']:+.1f}%")
        print(f"  CDD dev:     {result['cdd_deviation_pct']:+.1f}%")
        print(f"  Net signal:  {result['net_demand_signal']:+.1f}")
        print(f"  Season:      {result['season']}")
        print(f"\n  Summary: {result['summary']}")
        print()
        print("  Per-city breakdown:")
        for c in result["cities"]:
            print(f"    {c['city']:<12}  HDD {c['hdd_7day']:>5.1f} (norm {c['hdd_normal']:>4.1f})  "
                  f"CDD {c['cdd_7day']:>5.1f} (norm {c['cdd_normal']:>4.1f})")
