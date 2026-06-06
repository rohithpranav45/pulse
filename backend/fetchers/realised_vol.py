"""
Realised volatility from institutional 1-min mid prices.
========================================================
Replaces the realised-vol-as-IV-proxy hack in options_iv.py.

Uses the 5-year 1-min Brent and WTI files from /Data to compute:
  • current 30-day annualised realised vol
  • percentile rank against the full 5-year history
  • IV-style signal in [-1, +1]

This is REAL realised vol — not synthetic. The percentile is computed against
~5 years of true 1-minute mid-price returns, so the rank is research-grade.
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

_BACKEND = Path(__file__).parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

log = logging.getLogger("pulse.realised_vol")

# Cache between calls — file IO is the slow part
_rv_cache: dict = {}
_HIST_TTL_SECONDS = 6 * 3600  # rebuild rolling history every 6h


def _annualise_intraday(std_per_min: float) -> float:
    """sqrt(252 trading days × 1440 minutes/day) ≈ 602.4 annualised scaler."""
    return float(std_per_min * np.sqrt(252 * 1440))


def _load_1min_close_series(file_key: str, contract: str = "c1") -> Optional[pd.Series]:
    """Load full 1-min mid series for one contract. Returns Series indexed by time."""
    try:
        from data_lake import FILES
    except Exception as exc:
        log.error("data_lake import failed: %s", exc)
        return None

    if file_key not in FILES:
        return None
    path = FILES[file_key]
    if not path.exists():
        log.warning("%s missing on disk", file_key)
        return None

    col = f"{contract}||weighted_mid"
    try:
        df = pd.read_csv(path, skiprows=1, usecols=["timestamp", col], engine="c")
    except (ValueError, KeyError):
        log.warning("Column %s not in %s", col, path.name)
        return None
    s = pd.to_datetime(df["timestamp"], errors="coerce", utc=True)
    df = df.dropna(subset=["timestamp"])
    df = df.assign(timestamp=s).set_index("timestamp").sort_index()
    series = df[col].dropna().astype(float)
    series.name = f"{file_key}_{contract}"
    return series


def _compute_rolling_rv(prices: pd.Series, window_days: int = 30) -> pd.Series:
    """
    Compute rolling annualised realised vol of 1-min log returns over the
    last `window_days`. Returns a Series of daily RV values.
    """
    if prices.empty:
        return pd.Series(dtype=float)

    log_ret = np.log(prices / prices.shift(1)).dropna()
    if log_ret.empty:
        return pd.Series(dtype=float)

    # Group log returns by day, compute std per day
    daily = log_ret.groupby(log_ret.index.date).agg(["std", "count"])
    daily.columns = ["std", "n"]
    daily.index = pd.to_datetime(daily.index)
    daily = daily[daily["n"] >= 60]  # need ≥60 minutes of data per day

    # Rolling window std over the last N days, annualised
    rolling_std = daily["std"].rolling(window=window_days, min_periods=10).mean()
    rv = rolling_std.apply(_annualise_intraday)
    return rv.dropna()


def _rv_with_percentile(file_key: str, contract: str = "c1", window_days: int = 30) -> dict:
    """
    Compute current 30-day RV + percentile against full 5y history.

    Returns
    -------
    {
      "current_rv":   float,   annualised vol, e.g. 0.42 = 42%
      "percentile":   float,   0..1
      "signal":       float,   -1..+1
      "n_obs":        int,     length of the history series
      "history_start": str,
      "history_end":   str,
      "error":         str?,
    }
    """
    cache_key = f"{file_key}:{contract}:{window_days}"
    cached = _rv_cache.get(cache_key)
    if cached and (datetime.now(timezone.utc) - cached["fetched_at"]).total_seconds() < _HIST_TTL_SECONDS:
        return cached["result"]

    prices = _load_1min_close_series(file_key, contract)
    if prices is None or len(prices) < 1000:
        return {"current_rv": None, "percentile": 0.5, "signal": 0.0,
                "n_obs": 0, "error": "not enough 1-min data"}

    rv_series = _compute_rolling_rv(prices, window_days=window_days)
    if rv_series.empty:
        return {"current_rv": None, "percentile": 0.5, "signal": 0.0,
                "n_obs": 0, "error": "RV computation produced no data"}

    current = float(rv_series.iloc[-1])
    pct     = float((rv_series <= current).sum() / len(rv_series))

    if   pct > 0.80: signal = -0.5
    elif pct < 0.20: signal = +0.3
    else:            signal = 0.0

    result = {
        "current_rv":     round(current, 4),
        "percentile":     round(pct, 4),
        "signal":         signal,
        "n_obs":          int(len(rv_series)),
        "history_start":  rv_series.index[0].strftime("%Y-%m-%d"),
        "history_end":    rv_series.index[-1].strftime("%Y-%m-%d"),
    }
    _rv_cache[cache_key] = {"result": result, "fetched_at": datetime.now(timezone.utc)}
    return result


def get_realised_vol() -> dict:
    """
    Public entry point — returns RV dict for crude (Brent) and HH-proxy (WTI).
    Mirrors the shape of options_iv.get_iv() so it can drop-in.
    """
    # Prefer the file with volume (more recent), fall back to mid-only file
    try:
        crude = _rv_with_percentile("brent_1min_volume", "c1", 30)
        if not crude.get("current_rv"):
            crude = _rv_with_percentile("brent_1min", "c1", 30)
    except Exception as exc:
        log.error("crude RV failed: %s", exc)
        crude = {"current_rv": None, "percentile": 0.5, "signal": 0.0,
                 "n_obs": 0, "error": str(exc)[:200]}

    try:
        wti_rv = _rv_with_percentile("wti_1min_volume", "c1", 30)
        if not wti_rv.get("current_rv"):
            wti_rv = _rv_with_percentile("wti_1min", "c1", 30)
    except Exception as exc:
        log.error("WTI RV failed: %s", exc)
        wti_rv = {"current_rv": None, "percentile": 0.5, "signal": 0.0,
                  "n_obs": 0, "error": str(exc)[:200]}

    crude_rv = crude.get("current_rv")
    pct      = crude.get("percentile", 0.5)
    return {
        "source":             "RV from /Data 1-min mids",
        "crude_iv":           crude_rv,      # named "iv" for compatibility, IS realised vol
        "crude_iv_pctile":    pct,
        "crude_iv_reliable":  crude.get("n_obs", 0) >= 250,
        "crude_iv_n_obs":     crude.get("n_obs", 0),
        "hh_iv":              wti_rv.get("current_rv"),  # WTI as proxy for HH (we have WTI data, not NG)
        "hh_iv_pctile":       wti_rv.get("percentile", 0.5),
        "hh_iv_reliable":     wti_rv.get("n_obs", 0) >= 250,
        "hh_iv_n_obs":        wti_rv.get("n_obs", 0),
        "wti_rv":             wti_rv.get("current_rv"),
        "wti_rv_pctile":      wti_rv.get("percentile", 0.5),
        "history_start":      crude.get("history_start"),
        "history_end":        crude.get("history_end"),
        "signal":             crude.get("signal", 0.0),
        "stale":              crude_rv is None,
        "timestamp":          datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


if __name__ == "__main__":
    import json
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    print(json.dumps(get_realised_vol(), indent=2))
