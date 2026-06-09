"""
Backfilled US crude stocks history for the Phase 2 inventory regime axis.

Pulls the WCRSTUS1 weekly series from EIA v2 (~600 weeks back to Dec 2014)
and persists it to a parquet cache so regime classification doesn't need the
network at training or live-inference time.

Public API
----------
  get_crude_stocks_history(force_refresh=False) → pd.DataFrame
      Returns a date-indexed DataFrame with columns:
        crude_stocks     : weekly value in Mbbl (the EIA print)
        seasonal_5yr     : 5-year same-ISO-week average (excludes current year)
        vs_5yr_pct       : (current - seasonal) / seasonal * 100
        inv_bucket       : 'LOW' | 'AVG' | 'HIGH' bucket label

The DataFrame is sparse (one row per Wednesday report); callers should
forward-fill to daily before joining onto a daily price/feature matrix.

If the EIA key is missing or the API fails, returns None. The caller should
treat the inventory axis as collapsed to a single bucket in that case.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger("pulse.research.inventory")

_CACHE = Path(__file__).parent.parent / "data" / "research" / "crude_stocks_history.parquet"
_LENGTH = 600  # ~11.5 years of weekly observations
_ENDPOINT = "https://api.eia.gov/v2/petroleum/sum/sndw/data/"
_SERIES = "WCRSTUS1"

# Hard thresholds for the inventory bucket. The +/-4% bounds match the
# existing dashboard label cuts in fetchers/eia.py:_deviation_label.
INV_THRESHOLDS = {"LOW": -4.0, "HIGH": 4.0}  # vs_5yr_pct cuts


def _bucket(pct: Optional[float]) -> str:
    if pct is None or (isinstance(pct, float) and not np.isfinite(pct)):
        return "UNKNOWN"
    if pct <= INV_THRESHOLDS["LOW"]:
        return "LOW"
    if pct > INV_THRESHOLDS["HIGH"]:
        return "HIGH"
    return "AVG"


def _fetch_raw_weekly() -> Optional[pd.DataFrame]:
    key = os.getenv("EIA_API_KEY")
    if not key:
        log.warning("EIA_API_KEY missing — cannot backfill crude stocks history")
        return None
    params = {
        "api_key":            key,
        "frequency":          "weekly",
        "data[0]":            "value",
        "facets[series][]":   _SERIES,
        "length":             _LENGTH,
        "sort[0][column]":    "period",
        "sort[0][direction]": "desc",  # newest first; length caps at 600 most-recent
    }
    try:
        r = requests.get(_ENDPOINT, params=params, timeout=30)
        r.raise_for_status()
        rows = r.json()["response"]["data"]
    except Exception as exc:
        log.warning("EIA crude stocks fetch failed: %s", exc)
        return None
    df = pd.DataFrame(rows)
    df["date"]  = pd.to_datetime(df["period"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.dropna(subset=["date", "value"]).sort_values("date")  # ascending after sort
    df = df.set_index("date")[["value"]].rename(columns={"value": "crude_stocks"})
    return df


def _compute_seasonal(df: pd.DataFrame) -> pd.DataFrame:
    """
    For each row, compute the 5-year ISO-week seasonal average excluding the
    current row's year (matches existing /api/fundamentals semantics).
    """
    df = df.copy()
    df["iso_year"] = df.index.isocalendar().year
    df["iso_week"] = df.index.isocalendar().week

    out_vals = []
    for ts, row in df.iterrows():
        wk, yr = int(row["iso_week"]), int(row["iso_year"])
        baseline_years = range(yr - 5, yr)  # 5 prior years
        mask = (df["iso_week"] == wk) & (df["iso_year"].isin(baseline_years))
        vals = df.loc[mask, "crude_stocks"].dropna()
        out_vals.append(float(vals.mean()) if len(vals) else np.nan)

    df["seasonal_5yr"] = out_vals
    with np.errstate(invalid="ignore", divide="ignore"):
        df["vs_5yr_pct"] = (df["crude_stocks"] - df["seasonal_5yr"]) / df["seasonal_5yr"] * 100.0
    df["inv_bucket"] = df["vs_5yr_pct"].apply(_bucket)
    return df.drop(columns=["iso_year", "iso_week"])


def get_crude_stocks_history(force_refresh: bool = False) -> Optional[pd.DataFrame]:
    """
    Return a date-indexed DataFrame of weekly US crude stocks +
    5-year seasonal deviation + inv_bucket label.

    Cached at backend/data/research/crude_stocks_history.parquet. Refresh
    when older than 14 days, or when force_refresh=True.
    """
    if _CACHE.exists() and not force_refresh:
        try:
            age_days = (datetime.utcnow() - datetime.utcfromtimestamp(_CACHE.stat().st_mtime)).days
        except Exception:
            age_days = 999
        if age_days < 14:
            try:
                df = pd.read_parquet(_CACHE)
                df.index = pd.to_datetime(df.index)
                log.info("inventory_history: loaded from cache — %d weekly rows, %s to %s",
                         len(df), df.index[0].date(), df.index[-1].date())
                return df
            except Exception as exc:
                log.warning("inventory_history cache read failed (%s) — refetching", exc)

    raw = _fetch_raw_weekly()
    if raw is None or raw.empty:
        # Last-chance fallback: an older cache, even if stale, beats no data
        if _CACHE.exists():
            try:
                df = pd.read_parquet(_CACHE)
                df.index = pd.to_datetime(df.index)
                log.warning("inventory_history: API failed, falling back to stale cache "
                            "(%d rows)", len(df))
                return df
            except Exception:
                pass
        return None

    df = _compute_seasonal(raw)
    try:
        _CACHE.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(_CACHE, compression="zstd")
        log.info("inventory_history: cached %d weekly rows to %s", len(df), _CACHE.name)
    except Exception as exc:
        log.warning("inventory_history cache write failed: %s", exc)
    return df


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    df = get_crude_stocks_history(force_refresh=True)
    if df is None:
        print("FAILED — no data returned")
    else:
        print(f"rows: {len(df)}, range: {df.index.min().date()} -> {df.index.max().date()}")
        print("\nLatest 5:")
        print(df.tail(5).round(2))
        print("\nBucket distribution (full history):")
        print(df["inv_bucket"].value_counts())
