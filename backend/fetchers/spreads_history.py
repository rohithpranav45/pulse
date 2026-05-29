"""
Spreads History fetcher — daily historical time series of key oil spreads.

Computes:
  - RBOB-HO spread  (gasoline-diesel premium, $/bbl)
  - 3-2-1 crack     (US refinery margin, $/bbl)
  - Gasoline crack  (RBOB-WTI, $/bbl)
  - Distillate crack (HO-WTI, $/bbl)
  - Brent-WTI       (regional crude premium, $/bbl)
  - Brent calendar M1-M2 stand-in (rolling continuous-front spread)

Unit conventions (all returned in $/bbl):
  - RBOB / HO quoted in $/gal on yfinance → multiply by 42.
  - Brent / WTI quoted in $/bbl directly.

Public function:
  get_spreads_history(days=365) → dict
    {
      "rbob_ho":     [{date, value}, ...],
      "crack_321":   [...],
      "gasoline_crack": [...],
      "distillate_crack": [...],
      "brent_wti":   [...],
      "stats": {
        "<spread>": {"current": float, "mean_252d": float, "std_252d": float,
                     "z_score": float, "min_1y": float, "max_1y": float,
                     "last_30d_avg": float}
      },
      "timestamp": str (ISO)
    }
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timezone
from typing import Optional

_BACKEND = os.path.abspath(os.path.dirname(__file__))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

import yfinance as yf
import pandas as pd

log = logging.getLogger("pulse.spreads_history")

_TICKERS = {
    "brent": "BZ=F",
    "wti":   "CL=F",
    "rbob":  "RB=F",
    "ho":    "HO=F",
}


def _silent_history(ticker: str, period: str = "2y") -> pd.Series:
    """Fetch yfinance daily Close series with yfinance ERROR logs muted."""
    yf_log = logging.getLogger("yfinance")
    prev = yf_log.level
    yf_log.setLevel(logging.CRITICAL)
    try:
        hist = yf.Ticker(ticker).history(period=period, auto_adjust=True)
    except Exception as exc:
        log.debug("history failed %s: %s", ticker, exc)
        return pd.Series(dtype=float)
    finally:
        yf_log.setLevel(prev)
    if hist is None or hist.empty or "Close" not in hist.columns:
        return pd.Series(dtype=float)
    close = hist["Close"].dropna()
    # Drop tz so we can index-align across products
    try:
        close.index = pd.to_datetime(close.index).tz_localize(None)
    except (TypeError, AttributeError):
        close.index = pd.to_datetime(close.index)
    return close


def _stats(series: pd.Series) -> dict:
    """Compute rolling stats for a spread series."""
    s = series.dropna()
    if s.empty:
        return {"current": None, "mean_252d": None, "std_252d": None,
                "z_score": None, "min_1y": None, "max_1y": None,
                "last_30d_avg": None, "n": 0}
    tail = s.tail(252) if len(s) > 252 else s
    mean = float(tail.mean())
    std = float(tail.std())
    cur = float(s.iloc[-1])
    z = (cur - mean) / std if std and std > 0 else None
    last30 = s.tail(30).mean()
    return {
        "current":      round(cur, 3),
        "mean_252d":    round(mean, 3),
        "std_252d":     round(std, 3),
        "z_score":      round(z, 2) if z is not None else None,
        "min_1y":       round(float(tail.min()), 3),
        "max_1y":       round(float(tail.max()), 3),
        "last_30d_avg": round(float(last30), 3),
        "n":            int(len(s)),
    }


def _to_records(series: pd.Series, limit_days: int = 365) -> list[dict]:
    """Convert a series to a list of {date, value} dicts, last N days only."""
    if series.empty:
        return []
    s = series.dropna().tail(limit_days)
    out = []
    for ts, val in s.items():
        try:
            out.append({"date": ts.strftime("%Y-%m-%d"), "value": round(float(val), 3)})
        except Exception:
            continue
    return out


def get_spreads_history(days: int = 365) -> dict:
    """
    Pull 2y of daily history for Brent/WTI/RBOB/HO, compute key spreads,
    return last `days` of data plus 252-day rolling stats.
    """
    series = {k: _silent_history(t) for k, t in _TICKERS.items()}

    # ── Align on the common date index by joining on Brent (most reliable) ──
    df = pd.concat(series, axis=1).dropna(how="all")
    df.columns = list(series.keys())

    # Forward-fill 1 day for occasional missing closes, then drop residuals
    df = df.ffill(limit=1)

    # Convert RBOB/HO from $/gal to $/bbl (×42)
    if "rbob" in df.columns:
        df["rbob_bbl"] = df["rbob"] * 42.0
    if "ho" in df.columns:
        df["ho_bbl"]   = df["ho"]   * 42.0

    spreads_series: dict[str, pd.Series] = {}

    # RBOB - HO spread (gasoline premium over diesel, $/bbl)
    if "rbob_bbl" in df.columns and "ho_bbl" in df.columns:
        spreads_series["rbob_ho"] = (df["rbob_bbl"] - df["ho_bbl"]).dropna()

    # 3-2-1 crack: (2×RBOB + 1×HO - 3×WTI) / 3, in $/bbl
    if all(k in df.columns for k in ("rbob_bbl", "ho_bbl", "wti")):
        spreads_series["crack_321"] = (
            (2 * df["rbob_bbl"] + df["ho_bbl"] - 3 * df["wti"]) / 3.0
        ).dropna()

    # Gasoline crack: RBOB - WTI ($/bbl)
    if "rbob_bbl" in df.columns and "wti" in df.columns:
        spreads_series["gasoline_crack"] = (df["rbob_bbl"] - df["wti"]).dropna()

    # Distillate crack: HO - WTI ($/bbl)
    if "ho_bbl" in df.columns and "wti" in df.columns:
        spreads_series["distillate_crack"] = (df["ho_bbl"] - df["wti"]).dropna()

    # Brent - WTI ($/bbl)
    if "brent" in df.columns and "wti" in df.columns:
        spreads_series["brent_wti"] = (df["brent"] - df["wti"]).dropna()

    # Build result
    series_out = {k: _to_records(v, limit_days=days) for k, v in spreads_series.items()}
    stats_out = {k: _stats(v) for k, v in spreads_series.items()}

    return {
        "rbob_ho":           series_out.get("rbob_ho", []),
        "crack_321":         series_out.get("crack_321", []),
        "gasoline_crack":    series_out.get("gasoline_crack", []),
        "distillate_crack":  series_out.get("distillate_crack", []),
        "brent_wti":         series_out.get("brent_wti", []),
        "stats":             stats_out,
        "days":              days,
        "timestamp":         datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    r = get_spreads_history(days=365)
    print(f"Generated at {r['timestamp']}")
    for k, s in r["stats"].items():
        print(f"  {k:<20}  cur={s.get('current')}  μ252={s.get('mean_252d')}  "
              f"σ={s.get('std_252d')}  z={s.get('z_score')}  n={s.get('n')}")
