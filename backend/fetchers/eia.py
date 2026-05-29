"""
EIA API fetcher — weekly petroleum and natural gas inventory data.
For each series: latest value, prior value, week-on-week change,
and deviation from the 5-year seasonal average (same ISO week, prior 5 years).

Public analytics helpers:
  get_inventory_vs_seasonal()  — clean snake_case dict with deviation labels
  get_rig_count()              — US rig count (never crashes)
  get_inventory_snapshot()     — alias for fetch_inventories()
"""

import os
from datetime import datetime

import requests
from dotenv import load_dotenv

load_dotenv()

EIA_KEY = os.getenv("EIA_API_KEY")

# (display_name, endpoint, series_id, unit)
SERIES = [
    ("Crude Stocks",    "https://api.eia.gov/v2/petroleum/sum/sndw/data/",    "WCRSTUS1",            "Mbbl"),
    ("Cushing Stocks",  "https://api.eia.gov/v2/petroleum/sum/sndw/data/",    "WCSSTUS1",            "Mbbl"),
    ("Gasoline Stocks", "https://api.eia.gov/v2/petroleum/sum/sndw/data/",    "WGTSTUS1",            "Mbbl"),
    ("Distillate",      "https://api.eia.gov/v2/petroleum/sum/sndw/data/",    "WDISTUS1",            "Mbbl"),
    ("Nat Gas Storage", "https://api.eia.gov/v2/natural-gas/stor/wkly/data/", "NW2_EPG0_SWO_R48_BCF", "Bcf"),
]

# How many weeks to pull for 5-year seasonal average (5 yrs × 52 wks + buffer)
HISTORY_WEEKS = 275


def _fetch_series(endpoint: str, series_id: str, length: int) -> list[dict]:
    """Pull `length` most-recent weekly observations from EIA v2."""
    params = {
        "api_key":              EIA_KEY,
        "frequency":            "weekly",
        "data[0]":              "value",
        "facets[series][]":     series_id,
        "length":               length,
        "sort[0][column]":      "period",
        "sort[0][direction]":   "desc",
    }
    r = requests.get(endpoint, params=params, timeout=20)
    r.raise_for_status()
    return r.json()["response"]["data"]


def _seasonal_average(rows: list[dict], target_iso_week: int) -> float | None:
    """
    Average the values for the same ISO week number across the prior 5 calendar years.
    Excludes the most-recent year so the latest data point isn't in its own baseline.
    """
    latest_year = datetime.strptime(rows[0]["period"], "%Y-%m-%d").year
    cutoff_year = latest_year - 1          # exclude current year from baseline
    min_year    = cutoff_year - 4          # 5-year window

    vals = []
    for row in rows:
        try:
            dt   = datetime.strptime(row["period"], "%Y-%m-%d")
            yr   = dt.year
            week = dt.isocalendar()[1]
            if min_year <= yr <= cutoff_year and week == target_iso_week:
                vals.append(float(row["value"]))
        except (ValueError, KeyError):
            continue

    return round(sum(vals) / len(vals), 1) if vals else None


def fetch_inventories() -> dict:
    """
    Fetch all EIA inventory series.

    Returns
    -------
    {
      "Crude Stocks": {
          "latest":      819188,
          "previous":    821000,
          "change":      -1812,
          "change_pct":  -0.22,
          "date":        "2026-05-15",
          "five_yr_avg": 432000,
          "vs_5yr_avg":  +387188,
          "vs_5yr_pct":  +89.6,
          "unit":        "Mbbl",
      },
      ...
    }
    """
    if not EIA_KEY:
        raise EnvironmentError("EIA_API_KEY not set in environment / .env")

    result = {}

    for name, endpoint, series_id, unit in SERIES:
        rows = _fetch_series(endpoint, series_id, length=HISTORY_WEEKS)

        if len(rows) < 2:
            result[name] = {"error": "insufficient data"}
            continue

        latest_val  = float(rows[0]["value"])
        prev_val    = float(rows[1]["value"])
        latest_date = rows[0]["period"]

        change     = round(latest_val - prev_val, 1)
        change_pct = round((change / prev_val) * 100, 2) if prev_val else None

        iso_week   = datetime.strptime(latest_date, "%Y-%m-%d").isocalendar()[1]
        five_yr    = _seasonal_average(rows, iso_week)

        vs_5yr     = round(latest_val - five_yr, 1)     if five_yr is not None else None
        vs_5yr_pct = round((vs_5yr / five_yr) * 100, 2) if five_yr else None

        result[name] = {
            "latest":      latest_val,
            "previous":    prev_val,
            "change":      change,
            "change_pct":  change_pct,
            "date":        latest_date,
            "five_yr_avg": five_yr,
            "vs_5yr":      vs_5yr,
            "vs_5yr_pct":  vs_5yr_pct,
            "unit":        unit,
        }

    return result


# ── Mapping from fetch_inventories keys → public snake_case keys ──────────────
_SERIES_KEY_MAP = {
    "Crude Stocks":    "crude_stocks",
    "Cushing Stocks":  "cushing_stocks",
    "Gasoline Stocks": "gasoline_stocks",
    "Distillate":      "distillate",
    "Nat Gas Storage": "natgas_storage",
}

# EIA rig-count endpoints to try in order
_RIG_ENDPOINTS = [
    ("https://api.eia.gov/v2/petroleum/drill/rig/data/",        "EIA drill/rig"),
    ("https://api.eia.gov/v2/petroleum/supply/weekly/wpsup/data/", "EIA supply/wpsup"),
]


def _deviation_label(pct: float | None) -> str:
    """Classify a percentage deviation from the 5-year seasonal average."""
    if pct is None:
        return "UNAVAILABLE"
    if pct > 8:
        return "WELL_ABOVE"
    if pct > 4:
        return "ABOVE"
    if pct > -4:
        return "NORMAL"
    if pct > -8:
        return "BELOW"
    return "WELL_BELOW"


def get_inventory_vs_seasonal() -> dict:
    """
    Fetch all EIA inventory series and reformat into a clean,
    dashboard-ready snake_case structure with deviation labels.

    Returns
    -------
    {
      "crude_stocks": {
        "current":       float,
        "seasonal_avg":  float | None,
        "deviation_abs": float | None,   # current - seasonal_avg
        "deviation_pct": float | None,   # (deviation_abs / seasonal_avg) * 100
        "label":         str,            # WELL_ABOVE / ABOVE / NORMAL / BELOW / WELL_BELOW / UNAVAILABLE
        "date":          str,            # "YYYY-MM-DD" of latest observation
        "unit":          str,            # "Mbbl" or "Bcf"
      },
      "cushing_stocks":  { ... },
      "gasoline_stocks": { ... },
      "distillate":      { ... },
      "natgas_storage":  { ... },
    }
    """
    raw = fetch_inventories()
    result = {}

    for display_name, snake_key in _SERIES_KEY_MAP.items():
        d = raw.get(display_name, {})

        if "error" in d:
            result[snake_key] = {
                "current":       None,
                "seasonal_avg":  None,
                "deviation_abs": None,
                "deviation_pct": None,
                "label":         "UNAVAILABLE",
                "date":          None,
                "unit":          None,
            }
            continue

        pct = d.get("vs_5yr_pct")
        result[snake_key] = {
            "current":       d.get("latest"),
            "seasonal_avg":  d.get("five_yr_avg"),
            "deviation_abs": d.get("vs_5yr"),
            "deviation_pct": pct,
            "label":         _deviation_label(pct),
            "date":          d.get("date"),
            "unit":          d.get("unit"),
        }

    return result


def get_rig_count() -> dict:
    """
    Fetch the most-recent US rig count from EIA.
    Tries two endpoints in sequence; returns all-None on total failure.

    Returns
    -------
    {
      "current":  float | None,
      "previous": float | None,
      "change":   float | None,
      "date":     str   | None,
      "source":   str,            # endpoint label or "unavailable"
    }
    """
    if not EIA_KEY:
        return {"current": None, "previous": None,
                "change": None, "date": None, "source": "unavailable"}

    base_params = {
        "api_key":            EIA_KEY,
        "frequency":          "weekly",
        "data[0]":            "value",
        "length":             4,
        "sort[0][column]":    "period",
        "sort[0][direction]": "desc",
    }

    for endpoint, label in _RIG_ENDPOINTS:
        try:
            r = requests.get(endpoint, params=base_params, timeout=15)
            if r.status_code != 200:
                continue
            rows = r.json().get("response", {}).get("data", [])
            if not rows:
                continue

            current  = float(rows[0]["value"])
            previous = float(rows[1]["value"]) if len(rows) > 1 else None
            change   = round(current - previous, 1) if previous is not None else None

            return {
                "current":  current,
                "previous": previous,
                "change":   change,
                "date":     rows[0].get("period"),
                "source":   label,
            }
        except Exception:
            continue

    return {"current": None, "previous": None,
            "change": None, "date": None, "source": "unavailable"}


def get_inventory_snapshot() -> dict:
    """
    Alias for fetch_inventories().
    Lets other modules import a consistent name without
    importing the lower-level fetch_inventories directly.

    Returns
    -------
    Same dict as fetch_inventories().
    """
    return fetch_inventories()


# ── 9A: OPEC Production via EIA International Data ───────────────────────────

# EIA country codes (as specified in Command 9A) → display names
_OPEC_EIA_CODES = {
    "SA":  "Saudi Arabia",
    "IQ":  "Iraq",
    "UAE": "UAE",
    "KW":  "Kuwait",
    "IR":  "Iran",
    "VE":  "Venezuela",
    "LY":  "Libya",
    "NG":  "Nigeria",
    "DZ":  "Algeria",
    "GQ":  "Eq. Guinea",
    "GA":  "Gabon",
    "CG":  "Congo",
}


def get_opec_eia_production() -> dict:
    """
    Fetch crude production for OPEC members from EIA International Data.
    Uses productId=57 (crude oil production) and country-level facets.

    Returns
    -------
    {
      "members": [
        { "name": str, "code": str,
          "actual": float,       # latest-month production, Mb/d
          "prior_year": float | None,  # same month −12 periods, Mb/d
          "change_pct": float | None,  # YoY %
        }, ...
      ],
      "total_actual":   float,
      "latest_period":  str,    # "YYYY-MM"
      "source":         "EIA INTL",
      "stale":          bool,
    }
    Falls back to {"stale": True, "members": []} on any failure.
    """
    if not EIA_KEY:
        return {"stale": True, "members": [], "error": "EIA_API_KEY not set"}

    endpoint = "https://api.eia.gov/v2/international/data/"
    params = [
        ("api_key",              EIA_KEY),
        ("frequency",            "monthly"),
        ("data[0]",              "value"),
        ("facets[productId][]",  "57"),
        ("sort[0][column]",      "period"),
        ("sort[0][direction]",   "desc"),
        ("length",               "300"),
    ]
    for code in _OPEC_EIA_CODES:
        params.append(("facets[countryRegionId][]", code))

    try:
        r = requests.get(endpoint, params=params, timeout=20)
        r.raise_for_status()
        rows = r.json()["response"]["data"]
    except Exception as exc:
        return {"stale": True, "members": [], "error": str(exc)}

    if not rows:
        return {"stale": True, "members": [], "error": "No data returned from EIA INTL"}

    # Group rows by country code (already sorted newest-first)
    by_country: dict = {}
    for row in rows:
        code = row.get("countryRegionId", "")
        if code not in by_country:
            by_country[code] = []
        by_country[code].append(row)

    members = []
    latest_period = None

    for code, name in _OPEC_EIA_CODES.items():
        country_rows = by_country.get(code, [])
        if not country_rows:
            continue
        latest_row = country_rows[0]
        if latest_period is None:
            latest_period = latest_row.get("period", "")

        try:
            raw_val = float(latest_row["value"])
        except (ValueError, KeyError, TypeError):
            continue

        # EIA INTL production is in thousand barrels/day; values > 100 confirm this
        unit = str(latest_row.get("unit") or "").upper()
        if raw_val > 100 or "THOUSAND" in unit or unit in ("TBPD", "KB/D", "KBPD"):
            actual_mbd = raw_val / 1000.0
        else:
            actual_mbd = raw_val

        prior_year_mbd = None
        change_pct     = None
        if len(country_rows) >= 13:
            try:
                py_row = country_rows[12]  # 12 months back (desc sorted)
                py_val = float(py_row["value"])
                py_unit = str(py_row.get("unit") or "").upper()
                if py_val > 100 or "THOUSAND" in py_unit:
                    prior_year_mbd = py_val / 1000.0
                else:
                    prior_year_mbd = py_val
                if prior_year_mbd and prior_year_mbd > 0:
                    change_pct = round((actual_mbd - prior_year_mbd) / prior_year_mbd * 100, 1)
            except (ValueError, KeyError, IndexError):
                pass

        members.append({
            "name":       name,
            "code":       code,
            "actual":     round(actual_mbd, 3),
            "prior_year": round(prior_year_mbd, 3) if prior_year_mbd is not None else None,
            "change_pct": change_pct,
        })

    if not members:
        return {"stale": True, "members": [], "error": "No OPEC member data parsed"}

    return {
        "members":       members,
        "total_actual":  round(sum(m["actual"] for m in members), 2),
        "latest_period": latest_period or "",
        "source":        "EIA INTL",
        "stale":         False,
    }


# ── 9B: Spark / Dark Spread via EIA Electricity Retail Price ──────────────────

def get_spark_dark_spread(hh_price_per_mmbtu=None) -> dict:
    """
    Compute spark and dark spreads from EIA US retail electricity price.

    spark_spread = elec_$/MWh − (HH_$/MMBtu × 6.5 heat_rate)
    dark_spread  = elec_$/MWh − (65.0 coal_$/tonne / 8.0)

    Parameters
    ----------
    hh_price_per_mmbtu : float | None
        Henry Hub price in $/MMBtu. Falls back to yfinance NG=F if None.

    Returns
    -------
    {
      "spark_spread":   float,  "dark_spread":  float,
      "elec_price_mwh": float,  "hh_price":     float,
      "coal_price":     65.0,   "heat_rate":    6.5,
      "period":         str,    "stale":        bool,
    }
    """
    if not EIA_KEY:
        return {"stale": True, "error": "EIA_API_KEY not set"}

    try:
        r = requests.get(
            "https://api.eia.gov/v2/electricity/retail-sales/data/",
            params=[
                ("api_key",              EIA_KEY),
                ("frequency",            "monthly"),
                ("data[0]",              "price"),
                ("facets[stateid][]",    "US"),
                ("facets[sectorName][]", "all sectors"),
                ("sort[0][column]",      "period"),
                ("sort[0][direction]",   "desc"),
                ("length",               "2"),
            ],
            timeout=15,
        )
        r.raise_for_status()
        elec_rows = r.json()["response"]["data"]
    except Exception as exc:
        return {"stale": True, "error": f"EIA electricity fetch failed: {exc}"}

    if not elec_rows:
        return {"stale": True, "error": "No electricity price data returned"}

    try:
        elec_cents_kwh = float(elec_rows[0]["price"])
        elec_price_mwh = elec_cents_kwh * 10.0          # ¢/kWh → $/MWh
        period         = elec_rows[0].get("period", "")
    except (KeyError, ValueError, TypeError) as exc:
        return {"stale": True, "error": f"Electricity price parse failed: {exc}"}

    # HH price: use caller-supplied value, or fall back to yfinance
    if not hh_price_per_mmbtu or hh_price_per_mmbtu <= 0:
        try:
            import yfinance as yf
            hist = yf.Ticker("NG=F").history(period="5d", interval="1d")
            hh_price_per_mmbtu = float(hist["Close"].dropna().iloc[-1])
        except Exception:
            hh_price_per_mmbtu = 2.5   # last-resort fallback

    HEAT_RATE   = 6.5    # MMBtu/MWh — gas CCGT efficiency
    COAL_PRICE  = 65.0   # $/tonne — static per spec
    COAL_FACTOR = 8.0    # divisor per spec

    return {
        "spark_spread":    round(elec_price_mwh - hh_price_per_mmbtu * HEAT_RATE, 2),
        "dark_spread":     round(elec_price_mwh - COAL_PRICE / COAL_FACTOR, 2),
        "elec_price_mwh":  round(elec_price_mwh, 2),
        "hh_price":        round(hh_price_per_mmbtu, 4),
        "coal_price":      COAL_PRICE,
        "heat_rate":       HEAT_RATE,
        "period":          period,
        "stale":           False,
    }


# ── EIA STEO: Short-Term Energy Outlook — Global Oil Balance ──────────────────

_STEO_BASE = "https://api.eia.gov/v2/steo/data/"

# Candidate series IDs — try in order until one succeeds
_STEO_SUPPLY_SERIES    = ["PAPR_WORLD", "COPR_WORLD", "PCPR_WORLD"]
_STEO_DEMAND_SERIES    = ["PATC_WORLD", "CODD_WORLD", "PCTC_WORLD"]


def _fetch_steo_series(series_id: str, length: int = 36) -> list[dict]:
    """Pull monthly STEO data for one series (ascending by period)."""
    params = {
        "api_key":              EIA_KEY,
        "frequency":            "monthly",
        "data[0]":              "value",
        "facets[seriesId][]":   series_id,
        "length":               length,
        "sort[0][column]":      "period",
        "sort[0][direction]":   "desc",   # newest first so we get the latest forecasts
    }
    r = requests.get(_STEO_BASE, params=params, timeout=20)
    r.raise_for_status()
    rows = r.json().get("response", {}).get("data", [])
    # Return ascending so caller can slice easily
    return sorted(rows, key=lambda x: x.get("period", ""))


def get_steo_balance() -> dict:
    """
    Fetch EIA Short-Term Energy Outlook global liquid fuels balance.

    Returns 18 months of monthly supply, demand, and implied stock change (mb/d).
    Months beyond today are STEO forecasts; past months are actuals.

    Returns
    -------
    {
      "available":          bool,
      "months":             [{"period": "YYYY-MM", "supply": float,
                              "demand": float, "balance": float,
                              "is_forecast": bool}, ...],
      "current_supply":     float | None,  # latest available month
      "current_demand":     float | None,
      "current_balance":    float | None,
      "as_of":              str | None,
      "stale":              bool,
    }
    """
    if not EIA_KEY:
        return {"available": False, "stale": True, "months": [],
                "current_supply": None, "current_demand": None,
                "current_balance": None, "as_of": None}

    supply_rows = demand_rows = None
    for sid in _STEO_SUPPLY_SERIES:
        try:
            rows = _fetch_steo_series(sid, length=24)
            if rows:
                supply_rows = rows
                break
        except Exception:
            continue

    for sid in _STEO_DEMAND_SERIES:
        try:
            rows = _fetch_steo_series(sid, length=24)
            if rows:
                demand_rows = rows
                break
        except Exception:
            continue

    if not supply_rows or not demand_rows:
        return {"available": False, "stale": True, "months": [],
                "current_supply": None, "current_demand": None,
                "current_balance": None, "as_of": None}

    supply_map = {r["period"]: float(r["value"]) for r in supply_rows if r.get("value") not in (None, "")}
    demand_map = {r["period"]: float(r["value"]) for r in demand_rows if r.get("value") not in (None, "")}

    today_ym    = datetime.utcnow().strftime("%Y-%m")
    all_periods = sorted(set(supply_map) | set(demand_map))

    # EIA STEO is a forward-looking publication — all data points are projections.
    # Show up to 18 months starting from the earliest available (nearest to today).
    selected    = all_periods[:18]
    all_periods = selected

    months = []
    for p in all_periods:
        s = supply_map.get(p)
        d = demand_map.get(p)
        bal = round(s - d, 2) if s is not None and d is not None else None
        # "near_term" = within 3 months of today (STEO's current estimate)
        near_term = p <= today_ym or (
            abs((datetime.strptime(p, "%Y-%m") -
                 datetime.strptime(today_ym, "%Y-%m")).days) <= 90
        )
        months.append({
            "period":      p,
            "supply":      round(s, 2) if s is not None else None,
            "demand":      round(d, 2) if d is not None else None,
            "balance":     bal,
            "is_forecast": not near_term,  # near-term months shown as solid
        })

    # "Current" = first STEO month (closest to today's date)
    last = months[0] if months else None

    return {
        "available":       True,
        "months":          months,
        "current_supply":  last["supply"]  if last else None,
        "current_demand":  last["demand"]  if last else None,
        "current_balance": last["balance"] if last else None,
        "as_of":           last["period"]  if last else None,
        "stale":           False,
    }


if __name__ == "__main__":
    # ── 1. get_inventory_vs_seasonal ─────────────────────────────────────────
    print("=" * 65)
    print("  [1] get_inventory_vs_seasonal()")
    print("=" * 65)

    LABEL_PAD = {
        "WELL_ABOVE":  "WELL ABOVE",
        "ABOVE":       "ABOVE     ",
        "NORMAL":      "NORMAL    ",
        "BELOW":       "BELOW     ",
        "WELL_BELOW":  "WELL BELOW",
        "UNAVAILABLE": "N/A       ",
    }

    seasonal = get_inventory_vs_seasonal()
    print(f"\n  {'Series':<18} {'Current':>12} {'5yr Avg':>12} "
          f"{'Dev Abs':>12} {'Dev %':>7}  Label")
    print("  " + "-" * 72)

    for key, d in seasonal.items():
        if d["current"] is None:
            print(f"  {key:<18}  {'N/A':>12}")
            continue

        unit  = d["unit"] or ""
        label = LABEL_PAD.get(d["label"], d["label"])
        dev_pct_str = f"{d['deviation_pct']:>+6.1f}%" if d["deviation_pct"] is not None else "   N/A "
        dev_abs_str = f"{d['deviation_abs']:>+12,.0f}"  if d["deviation_abs"] is not None else "         N/A"
        avg_str     = f"{d['seasonal_avg']:>12,.0f}"    if d["seasonal_avg"]  is not None else "         N/A"

        print(
            f"  {key:<18} {d['current']:>12,.0f} {avg_str} "
            f"{dev_abs_str} {dev_pct_str}  {label}  [{unit}  {d['date']}]"
        )

    # ── 2. get_rig_count ─────────────────────────────────────────────────────
    print(f"\n\n{'=' * 65}")
    print("  [2] get_rig_count()")
    print("=" * 65)

    rig = get_rig_count()
    print(f"\n  Source   : {rig['source']}")
    if rig["current"] is not None:
        chg_str = f"{rig['change']:>+.0f}" if rig["change"] is not None else "N/A"
        print(f"  Date     : {rig['date']}")
        print(f"  Current  : {rig['current']:>8,.0f} rigs")
        print(f"  Previous : {rig['previous']:>8,.0f} rigs")
        print(f"  Change   : {chg_str} rigs")
    else:
        print("  Status   : No data returned from either endpoint")

    # ── 3. get_inventory_snapshot ─────────────────────────────────────────────
    print(f"\n\n{'=' * 65}")
    print("  [3] get_inventory_snapshot()  — alias check")
    print("=" * 65)

    snap = get_inventory_snapshot()
    print(f"\n  Keys returned : {list(snap.keys())}")
    print(f"  Series count  : {len(snap)}")
    first_key = next(iter(snap))
    first     = snap[first_key]
    print(f"  Sample [{first_key}]:")
    for field, val in first.items():
        val_fmt = f"{val:,.1f}" if isinstance(val, float) else str(val)
        print(f"    {field:<14}: {val_fmt}")
