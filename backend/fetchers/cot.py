"""
CFTC COT (Commitments of Traders) fetcher.
Downloads annual legacy-format XLS zips, caches to pkl, computes
net speculator position and 3-year percentile rank for 4 energy markets.

Public analytics helper:
  get_positioning_percentile()  — standardised contrarian signal per market
"""

import io
import os
import pickle
import time
import zipfile
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv()

CACHE_FILE       = Path(__file__).parent.parent / "cache" / "cot.pkl"
CACHE_MAX_AGE_H  = 24          # refresh once per day

# CFTC Disaggregated Futures report — contains energy/commodity markets
COT_URL_TMPL = "https://www.cftc.gov/files/dea/history/fut_disagg_xls_{year}.zip"

# Unique substrings matching the highest-OI contracts for each energy market
MARKETS = {
    "Crude Oil (WTI)": "CRUDE OIL, LIGHT SWEET-WTI",      # ICE Futures Europe — largest WTI pool
    "Nat Gas":         "NAT GAS ICE LD1",                   # ICE LD1 — 8M OI, dominant benchmark
    "Gasoline (RBOB)": "GASOLINE RBOB - NEW YORK",          # NYMEX RBOB
    "ULSD (Heat Oil)": "NY HARBOR ULSD",                    # Modern diesel/heat oil benchmark
}

# ── helpers ─────────────────────────────────────────────────────────────────

def _cache_age_h() -> float:
    if not CACHE_FILE.exists():
        return float("inf")
    return (time.time() - CACHE_FILE.stat().st_mtime) / 3600


def _find_date_col(df: pd.DataFrame) -> str | None:
    for col in df.columns:
        if "date" in col.lower():
            return col
    return None


def _parse_date(val) -> pd.Timestamp | None:
    """Handle YYMMDD ints and MM/DD/YYYY strings."""
    try:
        s = str(val).strip()
        if len(s) == 6 and s.isdigit():          # YYMMDD
            return pd.to_datetime(s, format="%y%m%d")
        return pd.to_datetime(s)
    except Exception:
        return None


def _download_year(year: int) -> pd.DataFrame | None:
    url = COT_URL_TMPL.format(year=year)
    try:
        r = requests.get(url, timeout=60)
        if r.status_code != 200:
            return None
        z    = zipfile.ZipFile(io.BytesIO(r.content))
        name = next((f for f in z.namelist()
                     if f.lower().endswith((".xls", ".xlsx"))), None)
        if not name:
            return None
        df = pd.read_excel(z.open(name))
        return df
    except Exception as exc:
        print(f"  [warn] COT {year}: {exc}")
        return None


def _build_combined(years: list[int]) -> pd.DataFrame:
    frames = []
    for yr in years:
        print(f"  [fetch] COT {yr}...", end=" ", flush=True)
        df = _download_year(yr)
        if df is not None:
            print(f"{len(df):,} rows")
            frames.append(df)
        else:
            print("skipped")
    if not frames:
        raise RuntimeError("No COT data could be downloaded.")
    combined = pd.concat(frames, ignore_index=True)

    # Normalise date column → datetime
    date_col = _find_date_col(combined)
    if date_col:
        combined["_date"] = combined[date_col].apply(_parse_date)
    else:
        combined["_date"] = pd.NaT

    return combined


def _load_combined(force_refresh: bool = False) -> pd.DataFrame:
    if not force_refresh and _cache_age_h() < CACHE_MAX_AGE_H:
        with open(CACHE_FILE, "rb") as f:
            df = pickle.load(f)
        print(f"  [cache] Loaded COT from {CACHE_FILE.name}  ({_cache_age_h():.1f} h old)")
        return df

    now   = datetime.now()
    years = [now.year - 3, now.year - 2, now.year - 1, now.year]
    combined = _build_combined(years)

    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE_FILE, "wb") as f:
        pickle.dump(combined, f)
    print(f"  [cache] Saved COT ({len(combined):,} rows total)")
    return combined


# ── main public function ────────────────────────────────────────────────────

def fetch_cot(force_refresh: bool = False) -> dict:
    """
    Fetch and parse CFTC COT data for 4 energy markets.

    Returns
    -------
    {
      "Crude Oil": {
          "net":            +128_432,
          "long":           312_000,
          "short":          183_568,
          "prev_net":       +125_000,
          "change":         +3_432,
          "change_pct":     2.74,
          "percentile_3yr": 67.4,    # 0-100; high = historically long
          "as_of":          "2024-10-01",
      },
      ...
    }
    """
    df = _load_combined(force_refresh=force_refresh)

    results = {}
    cutoff  = pd.Timestamp.now() - pd.DateOffset(years=3)

    for name, keyword in MARKETS.items():
        mask   = df["Market_and_Exchange_Names"].str.contains(
                    keyword, case=False, na=False)
        subset = df[mask].copy()

        if subset.empty:
            results[name] = {"error": "No matching rows"}
            continue

        # Sort chronologically
        subset = subset.sort_values("_date", na_position="first")

        # Disaggregated report uses Managed Money (M_Money) columns
        long_col  = "M_Money_Positions_Long_ALL"
        short_col = "M_Money_Positions_Short_ALL"
        if long_col not in subset.columns or short_col not in subset.columns:
            results[name] = {"error": f"Expected columns not found. "
                                      f"Available: {list(subset.columns[:8])}"}
            continue

        subset["net"] = (pd.to_numeric(subset[long_col], errors="coerce") -
                         pd.to_numeric(subset[short_col], errors="coerce"))
        subset = subset.dropna(subset=["net"])

        if subset.empty:
            results[name] = {"error": "No valid net positions"}
            continue

        latest   = subset.iloc[-1]
        prev_row = subset.iloc[-2] if len(subset) >= 2 else None

        net      = int(latest["net"])
        longs    = int(pd.to_numeric(latest[long_col],  errors="coerce"))
        shorts   = int(pd.to_numeric(latest[short_col], errors="coerce"))
        as_of    = latest["_date"].strftime("%Y-%m-%d") if pd.notna(latest["_date"]) else "N/A"

        prev_net   = int(prev_row["net"]) if prev_row is not None else None
        change     = net - prev_net         if prev_net is not None else None
        change_pct = round(change / abs(prev_net) * 100, 2) \
                     if (prev_net and prev_net != 0) else None

        # 3-year percentile rank
        hist_mask = subset["_date"] >= cutoff
        hist_net  = subset.loc[hist_mask, "net"].values
        pct_rank  = round(float(np.sum(hist_net < net) / len(hist_net) * 100), 1) \
                    if len(hist_net) > 0 else None

        results[name] = {
            "net":            net,
            "long":           longs,
            "short":          shorts,
            "prev_net":       prev_net,
            "change":         change,
            "change_pct":     change_pct,
            "percentile_3yr": pct_rank,
            "as_of":          as_of,
        }

    return results


# ── Analytics helper ────────────────────────────────────────────────────────

# Maps public snake_case keys → fetch_cot display-name keys
_MARKET_KEY_MAP = {
    "crude_oil":   "Crude Oil (WTI)",
    "natural_gas": "Nat Gas",
    "gasoline":    "Gasoline (RBOB)",
    "heating_oil": "ULSD (Heat Oil)",
}

_SIGNAL_MAP = {
    "EXTREME_LONG":  -2,
    "LONG":          -1,
    "NEUTRAL":        0,
    "SHORT":         +1,
    "EXTREME_SHORT": +2,
}


def _positioning_label(percentile: float) -> str:
    """Classify a 0-100 percentile into a positioning label."""
    if percentile > 90:
        return "EXTREME_LONG"
    if percentile > 65:
        return "LONG"
    if percentile > 35:
        return "NEUTRAL"
    if percentile > 10:
        return "SHORT"
    return "EXTREME_SHORT"


def get_positioning_percentile() -> dict:
    """
    Fetch COT data and return standardised contrarian positioning signals
    for four energy markets.

    A HIGH percentile (crowded long) → negative signal score (contrarian SELL).
    A LOW  percentile (crowded short) → positive signal score (contrarian BUY).

    Returns
    -------
    {
      "crude_oil": {
        "percentile": float,   # 0-100; 3-year rank of current net position
        "label":      str,     # EXTREME_LONG / LONG / NEUTRAL / SHORT / EXTREME_SHORT
        "signal":     int,     # contrarian: -2 (sell) .. 0 .. +2 (buy)
        "net":        int,     # raw Managed Money net contracts
        "date":       str,     # as-of date of latest COT release
      },
      "natural_gas": { ... },
      "gasoline":    { ... },
      "heating_oil": { ... },
    }
    """
    raw = fetch_cot()
    result = {}

    for snake_key, display_name in _MARKET_KEY_MAP.items():
        d = raw.get(display_name, {})

        if "error" in d:
            result[snake_key] = {
                "percentile": 50.0,
                "label":      "NEUTRAL",
                "signal":     0,
                "net":        None,
                "date":       None,
            }
            continue

        pct = d.get("percentile_3yr")

        # Graceful None handling — default to neutral
        if pct is None:
            label  = "NEUTRAL"
            signal = 0
            pct    = 50.0
        else:
            label  = _positioning_label(pct)
            signal = _SIGNAL_MAP[label]

        result[snake_key] = {
            "percentile": pct,
            "label":      label,
            "signal":     signal,
            "net":        d.get("net"),
            "date":       d.get("as_of"),
        }

    return result


# ── test block ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Fetching COT positioning percentiles...\n")
    pos = get_positioning_percentile()

    # Signal bar: filled blocks proportional to |signal|, direction shows bias
    SIGNAL_BARS = {
        -2: "<<  EXTREME LONG  (contrarian SELL)",
        -1: "<   LONG          (contrarian lean sell)",
         0: "    NEUTRAL",
        +1: ">   SHORT         (contrarian lean buy)",
        +2: ">>  EXTREME SHORT (contrarian BUY)",
    }

    # Percentile spark — 20-char bar
    def _pct_bar(pct: float) -> str:
        filled = round(pct / 5)          # 0-20 blocks
        return "[" + "#" * filled + "-" * (20 - filled) + "]"

    print(f"  {'Market':<14} {'Pct':>5}  {'Bar (0%→100%)':<24}  "
          f"{'Net Contracts':>14}  {'Sig':>4}  Positioning")
    print("  " + "-" * 90)

    for key, d in pos.items():
        pct    = d["percentile"]
        net    = d["net"]
        signal = d["signal"]
        date   = d["date"] or "N/A"

        net_str = f"{net:>+14,}" if net is not None else f"{'N/A':>14}"
        bar     = _pct_bar(pct)
        sig_str = f"{signal:>+2}"

        print(f"  {key:<14} {pct:>4.1f}%  {bar}  "
              f"{net_str}  {sig_str:>4}  {SIGNAL_BARS[signal]}")

    print(f"\n  As of : {next(iter(pos.values()))['date']}")
    print(f"\n  Signal key:  +2 = crowded short → contrarian BUY")
    print(f"               -2 = crowded long  → contrarian SELL")
    print(f"                0 = neutral, no strong contrarian edge")
