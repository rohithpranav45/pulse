"""
Backfilled COT (Commitments of Traders) history for Phase 2.8 features.

The production cot.py fetcher only caches the last ~3-4 years of weekly COT
reports — enough for a "current positioning percentile" tile, not enough for
a 156-week percentile feature in the regime regression matrix.

This module downloads ~12 years of CFTC disaggregated futures zips (one zip
per calendar year) for Crude Oil WTI and caches a clean weekly history to
parquet. Features.py then ffills it to daily and emits two columns:

  cot_mm_net           — Managed Money net longs (contracts, signed)
  cot_mm_pct_156w      — rolling 156-week percentile rank of cot_mm_net
                         (0-100 scale; high = crowded long → contrarian SELL)

Public API
----------
  get_cot_history(force_refresh=False) -> pd.DataFrame | None
      Date-indexed weekly DataFrame with columns
        cot_mm_long, cot_mm_short, cot_mm_net, cot_mm_pct_156w
      If the network is unreachable and no cache exists, returns None.
"""

from __future__ import annotations

import io
import logging
import os
import time
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import requests

log = logging.getLogger("pulse.research.cot_history")

_CACHE = Path(__file__).parent.parent / "data" / "research" / "cot_history.parquet"
_CACHE_MAX_AGE_DAYS = 14
_URL_TMPL = "https://www.cftc.gov/files/dea/history/fut_disagg_xls_{year}.zip"
_KEYWORD  = "CRUDE OIL, LIGHT SWEET-WTI"
_FIRST_YEAR = 2014  # disaggregated reports start in 2010; 2014+ gives a clean
                    # 156-week rolling window for the 2016+ Brent feature matrix.


def _download_year(year: int) -> Optional[pd.DataFrame]:
    url = _URL_TMPL.format(year=year)
    try:
        r = requests.get(url, timeout=60)
        if r.status_code != 200:
            log.debug("COT %d HTTP %d", year, r.status_code)
            return None
        z = zipfile.ZipFile(io.BytesIO(r.content))
        name = next((f for f in z.namelist() if f.lower().endswith((".xls", ".xlsx"))), None)
        if not name:
            return None
        return pd.read_excel(z.open(name))
    except Exception as exc:
        log.warning("COT %d download failed: %s", year, exc)
        return None


def _parse_date(val) -> Optional[pd.Timestamp]:
    try:
        s = str(val).strip()
        if len(s) == 6 and s.isdigit():
            return pd.to_datetime(s, format="%y%m%d")
        return pd.to_datetime(s)
    except Exception:
        return None


def _build_history(years: list[int]) -> pd.DataFrame:
    frames = []
    for yr in years:
        log.info("COT %d ...", yr)
        df = _download_year(yr)
        if df is None or df.empty:
            continue
        # Normalise date column
        date_col = next((c for c in df.columns if "date" in c.lower()), None)
        if date_col is None:
            continue
        df["_date"] = df[date_col].apply(_parse_date)
        # Filter to WTI Crude
        if "Market_and_Exchange_Names" not in df.columns:
            continue
        sub = df[df["Market_and_Exchange_Names"].str.contains(_KEYWORD, case=False, na=False)].copy()
        if sub.empty:
            continue
        long_col  = "M_Money_Positions_Long_ALL"
        short_col = "M_Money_Positions_Short_ALL"
        if long_col not in sub.columns or short_col not in sub.columns:
            continue
        sub["cot_mm_long"]  = pd.to_numeric(sub[long_col], errors="coerce")
        sub["cot_mm_short"] = pd.to_numeric(sub[short_col], errors="coerce")
        sub["cot_mm_net"]   = sub["cot_mm_long"] - sub["cot_mm_short"]
        sub = sub.dropna(subset=["_date", "cot_mm_net"])
        # WTI keyword can match multiple contracts (NYMEX + ICE); keep the
        # highest open-interest row per date so we get the dominant pool.
        oi_col = "Open_Interest_All"
        if oi_col in sub.columns:
            sub[oi_col] = pd.to_numeric(sub[oi_col], errors="coerce")
            sub = sub.sort_values([oi_col], ascending=False).drop_duplicates("_date", keep="first")
        else:
            sub = sub.drop_duplicates("_date", keep="first")
        frames.append(sub[["_date", "cot_mm_long", "cot_mm_short", "cot_mm_net"]]
                       .set_index("_date").sort_index())
        time.sleep(0.4)  # be polite to CFTC
    if not frames:
        raise RuntimeError("No COT history could be downloaded.")
    out = pd.concat(frames).sort_index()
    out = out[~out.index.duplicated(keep="last")]
    return out


def _annotate_percentile(df: pd.DataFrame, window_weeks: int = 156) -> pd.DataFrame:
    """Rolling 156-week percentile of cot_mm_net (0..100)."""
    df = df.copy()
    def _pct(window: np.ndarray) -> float:
        cur = window[-1]
        if not np.isfinite(cur):
            return np.nan
        return float((window < cur).sum() / len(window) * 100.0)
    df["cot_mm_pct_156w"] = (
        df["cot_mm_net"]
          .rolling(window_weeks, min_periods=26)
          .apply(_pct, raw=True)
    )
    return df


def get_cot_history(force_refresh: bool = False) -> Optional[pd.DataFrame]:
    """Return weekly COT history with rolling 156-week percentile, or None on failure."""
    if _CACHE.exists() and not force_refresh:
        try:
            age_days = (datetime.utcnow() - datetime.utcfromtimestamp(_CACHE.stat().st_mtime)).days
        except Exception:
            age_days = 999
        if age_days < _CACHE_MAX_AGE_DAYS:
            try:
                df = pd.read_parquet(_CACHE)
                df.index = pd.to_datetime(df.index)
                log.info("cot_history: loaded from cache (%d rows, %s → %s)",
                         len(df), df.index[0].date(), df.index[-1].date())
                return df
            except Exception as exc:
                log.warning("cot_history cache read failed (%s); refetching", exc)

    this_year = datetime.utcnow().year
    years = list(range(_FIRST_YEAR, this_year + 1))
    try:
        raw = _build_history(years)
    except Exception as exc:
        log.warning("COT history fetch failed: %s", exc)
        if _CACHE.exists():
            try:
                df = pd.read_parquet(_CACHE)
                df.index = pd.to_datetime(df.index)
                log.warning("cot_history: serving stale cache (%d rows)", len(df))
                return df
            except Exception:
                pass
        return None

    df = _annotate_percentile(raw, window_weeks=156)
    try:
        _CACHE.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(_CACHE, compression="zstd")
        log.info("cot_history: cached %d weekly rows to %s", len(df), _CACHE.name)
    except Exception as exc:
        log.warning("cot_history cache write failed: %s", exc)
    return df


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    df = get_cot_history(force_refresh=True)
    if df is None:
        print("FAILED — no data")
    else:
        print(f"rows: {len(df)}, range {df.index.min().date()} -> {df.index.max().date()}")
        print("\nTail:")
        print(df.tail(8).round(1))
