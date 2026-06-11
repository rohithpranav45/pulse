"""
Backfilled history of FRED + yfinance series used by Phase 2.8 features.

This pulls and caches the long-history daily series we need to engineer the
new alpha-bearing features in features.py:

  rates_real      = DGS10 - T5YIE                  (FRED: DGS10, T5YIE)
  ovx_vix_ratio   = ^OVX / ^VIX                    (FRED: OVXCLS, VIXCLS)
  crack_321       = (2*RBOB$/bbl + HO$/bbl - 3*WTI) / 3   (yfinance: RB=F, HO=F, CL=F)
  gasoline_crack  = RBOB$/bbl - WTI                (yfinance: RB=F, CL=F)

All cached at backend/data/research/external_history.parquet. Re-fetched when
older than 7 days. Returns None if both the network and cache are unavailable.

Public API
----------
  get_external_history(force_refresh=False) → pd.DataFrame
      Date-indexed daily DataFrame, business-day frequency, ffilled.
      Columns: dgs10, t5yie, real_rate, ovx, vix, ovx_vix_ratio,
               wti_close_d, brent_close_d, rbob_bbl_d, ho_bbl_d,
               crack_321, gasoline_crack, wti_brent_spread
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger("pulse.research.external_history")

_CACHE = Path(__file__).parent.parent / "data" / "research" / "external_history.parquet"
_CACHE_MAX_AGE_DAYS = 7
_GAL_TO_BBL = 42

_FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"
_FRED_SERIES = {
    "dgs10": "DGS10",     # 10-year Treasury constant maturity (%)
    "t5yie": "T5YIE",     # 5-year breakeven inflation (%)
    "ovx":   "OVXCLS",    # CBOE crude oil VIX
    "vix":   "VIXCLS",    # CBOE equity VIX
}

_YF_TICKERS = {
    "wti_close_d":   "CL=F",
    "brent_close_d": "BZ=F",
    "rbob_gal_d":    "RB=F",
    "ho_gal_d":      "HO=F",
}

_START_DATE = "2014-01-01"


def _fetch_fred_series(series_id: str, api_key: str) -> Optional[pd.Series]:
    params = {
        "series_id":         series_id,
        "api_key":           api_key,
        "file_type":         "json",
        "observation_start": _START_DATE,
    }
    try:
        r = requests.get(_FRED_BASE, params=params, timeout=30)
        r.raise_for_status()
        rows = r.json().get("observations", [])
    except Exception as exc:
        log.warning("FRED %s fetch failed: %s", series_id, exc)
        return None
    if not rows:
        return None
    dates  = [pd.to_datetime(r["date"]) for r in rows]
    values = []
    for r in rows:
        v = r.get("value")
        try:
            values.append(float(v))
        except (TypeError, ValueError):
            values.append(np.nan)
    s = pd.Series(values, index=dates, name=series_id).sort_index()
    s = s.dropna()
    return s


def _fetch_yf_series(ticker: str) -> Optional[pd.Series]:
    try:
        import yfinance as yf
        yf_log = logging.getLogger("yfinance")
        prev = yf_log.level
        yf_log.setLevel(logging.CRITICAL)
        try:
            hist = yf.Ticker(ticker).history(start=_START_DATE, auto_adjust=True)
        finally:
            yf_log.setLevel(prev)
        if hist is None or hist.empty or "Close" not in hist.columns:
            return None
        s = hist["Close"].dropna().copy()
        s.index = pd.to_datetime(s.index).tz_localize(None)
        s.name = ticker
        return s
    except Exception as exc:
        log.warning("yfinance %s failed: %s", ticker, exc)
        return None


def _assemble() -> Optional[pd.DataFrame]:
    api_key = os.getenv("FRED_API_KEY", "").strip()
    series: dict[str, pd.Series] = {}

    if api_key:
        for col, sid in _FRED_SERIES.items():
            s = _fetch_fred_series(sid, api_key)
            if s is not None:
                series[col] = s
    else:
        log.warning("FRED_API_KEY missing — DGS10 / T5YIE / OVX / VIX will be NaN")

    for col, tk in _YF_TICKERS.items():
        s = _fetch_yf_series(tk)
        if s is not None:
            series[col] = s

    if not series:
        return None

    df = pd.DataFrame(series).sort_index()
    df.index = pd.to_datetime(df.index)
    # Snap to business-day frequency + ffill (FRED + yfinance have different
    # session calendars; ffill bridges weekends + holidays).
    bd = pd.bdate_range(df.index.min(), df.index.max())
    df = df.reindex(bd).ffill(limit=5)

    # Derived columns
    if "dgs10" in df and "t5yie" in df:
        df["real_rate"] = df["dgs10"] - df["t5yie"]
    if "ovx" in df and "vix" in df:
        with np.errstate(divide="ignore", invalid="ignore"):
            df["ovx_vix_ratio"] = df["ovx"] / df["vix"]
    if "rbob_gal_d" in df:
        df["rbob_bbl_d"] = df["rbob_gal_d"] * _GAL_TO_BBL
    if "ho_gal_d" in df:
        df["ho_bbl_d"] = df["ho_gal_d"] * _GAL_TO_BBL
    if {"rbob_bbl_d", "ho_bbl_d", "wti_close_d"}.issubset(df.columns):
        df["crack_321"] = (2 * df["rbob_bbl_d"] + df["ho_bbl_d"] - 3 * df["wti_close_d"]) / 3.0
    if {"rbob_bbl_d", "wti_close_d"}.issubset(df.columns):
        df["gasoline_crack"] = df["rbob_bbl_d"] - df["wti_close_d"]
    if {"wti_close_d", "brent_close_d"}.issubset(df.columns):
        df["wti_brent_spread"] = df["wti_close_d"] - df["brent_close_d"]
    return df


def get_external_history(force_refresh: bool = False) -> Optional[pd.DataFrame]:
    if _CACHE.exists() and not force_refresh:
        try:
            age_days = (datetime.utcnow() - datetime.utcfromtimestamp(_CACHE.stat().st_mtime)).days
        except Exception:
            age_days = 999
        if age_days < _CACHE_MAX_AGE_DAYS:
            try:
                df = pd.read_parquet(_CACHE)
                df.index = pd.to_datetime(df.index)
                log.info("external_history: loaded from cache (%d rows, %s → %s)",
                         len(df), df.index[0].date(), df.index[-1].date())
                return df
            except Exception as exc:
                log.warning("external_history cache read failed (%s); refetching", exc)

    df = _assemble()
    if df is None or df.empty:
        if _CACHE.exists():
            try:
                df = pd.read_parquet(_CACHE)
                df.index = pd.to_datetime(df.index)
                log.warning("external_history: assembly failed, serving stale cache (%d rows)", len(df))
                return df
            except Exception:
                pass
        return None
    try:
        _CACHE.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(_CACHE, compression="zstd")
        log.info("external_history: cached %d rows to %s", len(df), _CACHE.name)
    except Exception as exc:
        log.warning("external_history cache write failed: %s", exc)
    return df


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    df = get_external_history(force_refresh=True)
    if df is None:
        print("FAILED")
    else:
        print(f"rows: {len(df)}, range {df.index.min().date()} -> {df.index.max().date()}")
        print(f"cols: {list(df.columns)}")
        print("\nTail:")
        print(df.tail(5).round(3))
