"""
Historical OHLCV fetcher with 24-hour pickle cache.
Covers: Brent, WTI, Henry Hub, DXY, S&P 500  (5-year daily)

Analytics helpers (all read from cache, no network calls):
  get_returns()          — daily pct-change series
  get_moving_average()   — rolling mean of Close
  get_volatility()       — annualised realised vol (%)
  get_percentile_rank()  — where does a value sit vs last N closes (0-100)
  get_seasonality()      — average monthly return by month number
  get_dxy_deviation()    — DXY vs its N-day moving average
"""

import math
import pickle
import time
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
import yfinance as yf

load_dotenv()

CACHE_FILE = Path(__file__).parent.parent / "cache" / "historical.pkl"
CACHE_MAX_AGE_HOURS = 24

DATASETS = {
    "Brent": "BZ=F",
    "WTI":   "CL=F",
    "HH":    "NG=F",
    "DXY":   "DX-Y.NYB",
    "SPX":   "^GSPC",
}


def _cache_age_hours() -> float:
    if not CACHE_FILE.exists():
        return float("inf")
    return (time.time() - CACHE_FILE.stat().st_mtime) / 3600


def _download() -> dict:
    """
    Download 5-year daily OHLCV for each asset individually.
    Per-ticker Ticker.history() avoids the tz-naive/tz-aware join error
    that occurs when batch-downloading mixed exchanges (e.g. DX-Y.NYB
    alongside futures like BZ=F).
    """
    result = {}
    for name, symbol in DATASETS.items():
        try:
            df = yf.Ticker(symbol).history(
                period="5y", interval="1d", auto_adjust=True
            ).dropna(how="all")
            if df.empty:
                print(f"  [WARN] historical: no data for {name} ({symbol})")
            else:
                result[name] = df
        except Exception as exc:
            print(f"  [WARN] historical download failed for {name} ({symbol}): {exc}")
    return result


def load_historical(force_refresh: bool = False) -> dict:
    """
    Return 5-year daily OHLCV DataFrames, keyed by dataset name.
    Reads from cache unless stale (>24 h) or force_refresh=True.
    """
    age = _cache_age_hours()
    if not force_refresh and age < CACHE_MAX_AGE_HOURS:
        with open(CACHE_FILE, "rb") as f:
            data = pickle.load(f)
        print(f"  [cache] Loaded from {CACHE_FILE.name}  (age: {age:.1f} h)")
        return data

    print("  [fetch] Downloading 5-year history from Yahoo Finance...")
    data = _download()

    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE_FILE, "wb") as f:
        pickle.dump(data, f)
    print(f"  [cache] Saved to {CACHE_FILE}")
    return data


def refresh_if_stale() -> dict:
    """Refresh only when cache is older than 24 hours."""
    return load_historical(force_refresh=_cache_age_hours() >= CACHE_MAX_AGE_HOURS)


# ── Analytics helpers ─────────────────────────────────────────────────────────

_VALID_ASSETS = {"Brent", "WTI", "HH", "DXY", "SPX"}

# In-memory session cache — avoids repeated disk reads when multiple
# analytics helpers are called in the same process.
_session_data: dict | None = None


def _get_data() -> dict:
    """Return historical data, loading from disk at most once per process."""
    global _session_data
    if _session_data is None:
        _session_data = load_historical()
    return _session_data


def _close(asset: str) -> pd.Series:
    """Return the Close series for *asset*, validating the key."""
    if asset not in _VALID_ASSETS:
        raise KeyError(
            f"Unknown asset '{asset}'. Valid keys: {sorted(_VALID_ASSETS)}"
        )
    return _get_data()[asset]["Close"].dropna()


def get_returns(asset: str) -> pd.Series:
    """
    Daily percentage returns for *asset*.

    Parameters
    ----------
    asset : "Brent" | "WTI" | "HH" | "DXY" | "SPX"

    Returns
    -------
    pd.Series  — daily pct_change, NaN rows dropped, index = date
    """
    return _close(asset).pct_change().dropna()


def get_moving_average(asset: str, window: int = 30) -> pd.Series:
    """
    Rolling simple moving average of Close prices.

    Parameters
    ----------
    asset  : see get_returns
    window : lookback in trading days (default 30)

    Returns
    -------
    pd.Series  — same index as Close, leading NaNs until window fills
    """
    return _close(asset).rolling(window=window).mean()


def get_volatility(asset: str, window: int = 30) -> float:
    """
    Annualised realised volatility over the last *window* trading days.

    Formula: std(daily_returns[-window:]) × sqrt(252) × 100

    Parameters
    ----------
    asset  : see get_returns
    window : trailing window in trading days (default 30)

    Returns
    -------
    float  — annualised vol as a percentage, e.g. 22.4 means 22.4 %
    """
    returns = get_returns(asset).iloc[-window:]
    if len(returns) < 2:
        return float("nan")
    return round(float(returns.std() * math.sqrt(252) * 100), 2)


def get_percentile_rank(
    asset: str, current_value: float, lookback: int = 252
) -> float:
    """
    Percentile rank of *current_value* within the last *lookback* daily closes.

    Answers: "what fraction of the last N closes is *below* this value?"

    Parameters
    ----------
    asset         : see get_returns
    current_value : price to rank (e.g. today's close)
    lookback      : number of trading days to look back (default 252 ≈ 1 year)

    Returns
    -------
    float  — 0-100; e.g. 82.0 means current_value > 82 % of lookback closes
    """
    close = _close(asset).iloc[-lookback:]
    if close.empty:
        return float("nan")
    pct = float((close < current_value).sum() / len(close) * 100)
    return round(pct, 1)


def get_seasonality(asset: str) -> dict:
    """
    Average monthly return for each calendar month, computed over all
    available history (up to 5 years).

    Method:
      1. Take daily pct-change returns.
      2. Group by (year, month), sum within each month → monthly return.
      3. Average those monthly returns by month number (1-12).

    Parameters
    ----------
    asset : see get_returns

    Returns
    -------
    dict  — {1: avg_pct, 2: avg_pct, ..., 12: avg_pct}
            values are percentages, e.g. 1.8 means +1.8 % average that month
    """
    returns = get_returns(asset)

    # Sum daily returns within each calendar month → one row per month
    monthly = (
        returns
        .groupby([returns.index.year, returns.index.month])
        .sum() * 100          # convert fraction → percent
    )
    monthly.index.names = ["year", "month"]

    # Average across years for each month number
    avg_by_month = monthly.groupby(level="month").mean()

    return {int(m): round(float(v), 2) for m, v in avg_by_month.items()}


def get_dxy_deviation(days: int = 30) -> float:
    """
    Current DXY minus its *days*-day simple moving average.

    A positive result → DXY is trading above its recent average (strong dollar).
    A negative result → DXY is trading below its recent average (weak dollar).

    Parameters
    ----------
    days : MA window in trading days (default 30)

    Returns
    -------
    float  — deviation in index points, rounded to 3 d.p.
    """
    close = _close("DXY")
    current = float(close.iloc[-1])
    ma      = float(close.rolling(window=days).mean().iloc[-1])
    return round(current - ma, 3)


if __name__ == "__main__":
    ASSETS = ["Brent", "WTI", "HH", "DXY", "SPX"]
    MONTH_NAMES = {
        1:"Jan", 2:"Feb", 3:"Mar", 4:"Apr", 5:"May", 6:"Jun",
        7:"Jul", 8:"Aug", 9:"Sep", 10:"Oct", 11:"Nov", 12:"Dec",
    }

    # Load once — all helpers below re-use the same cache hit
    print("Loading historical cache...\n")
    load_historical()

    # ── 1. get_returns ────────────────────────────────────────────────────────
    print("=" * 60)
    print("  [1] get_returns()  — last 5 daily returns")
    print("=" * 60)
    print(f"  {'Asset':<8}  {'Date':<12}  {'Return':>8}")
    print("  " + "-" * 36)
    for asset in ASSETS:
        r = get_returns(asset)
        for date, val in r.tail(5).items():
            print(f"  {asset:<8}  {str(date.date()):<12}  {val*100:>+7.3f}%")
        print()

    # ── 2. get_moving_average ─────────────────────────────────────────────────
    print("=" * 60)
    print("  [2] get_moving_average()  — latest MA values")
    print("=" * 60)
    print(f"  {'Asset':<8}  {'MA-20':>10}  {'MA-50':>10}  {'MA-200':>10}  {'Current':>10}")
    print("  " + "-" * 56)
    for asset in ASSETS:
        close   = _close(asset)
        current = close.iloc[-1]
        ma20    = get_moving_average(asset, 20).iloc[-1]
        ma50    = get_moving_average(asset, 50).iloc[-1]
        ma200   = get_moving_average(asset, 200).iloc[-1]
        print(f"  {asset:<8}  {ma20:>10.3f}  {ma50:>10.3f}  {ma200:>10.3f}  {current:>10.3f}")
    print()

    # ── 3. get_volatility ─────────────────────────────────────────────────────
    print("=" * 60)
    print("  [3] get_volatility()  — annualised realised vol (%)")
    print("=" * 60)
    print(f"  {'Asset':<8}  {'10d vol':>8}  {'30d vol':>8}  {'90d vol':>8}  {'252d vol':>9}")
    print("  " + "-" * 48)
    for asset in ASSETS:
        v10  = get_volatility(asset, 10)
        v30  = get_volatility(asset, 30)
        v90  = get_volatility(asset, 90)
        v252 = get_volatility(asset, 252)
        print(f"  {asset:<8}  {v10:>7.1f}%  {v30:>7.1f}%  {v90:>7.1f}%  {v252:>8.1f}%")
    print()

    # ── 4. get_percentile_rank ────────────────────────────────────────────────
    print("=" * 60)
    print("  [4] get_percentile_rank()  — current price vs last 252 closes")
    print("=" * 60)
    print(f"  {'Asset':<8}  {'Current':>10}  {'52w Hi':>10}  {'52w Lo':>10}  {'Percentile':>11}")
    print("  " + "-" * 58)
    for asset in ASSETS:
        close   = _close(asset)
        current = float(close.iloc[-1])
        hi_52   = float(close.iloc[-252:].max())
        lo_52   = float(close.iloc[-252:].min())
        pct     = get_percentile_rank(asset, current, lookback=252)
        bar     = "#" * int(pct / 5)      # 0-20 hashes
        print(f"  {asset:<8}  {current:>10.3f}  {hi_52:>10.3f}  {lo_52:>10.3f}  {pct:>9.1f}%  {bar}")
    print()

    # ── 5. get_seasonality ────────────────────────────────────────────────────
    print("=" * 60)
    print("  [5] get_seasonality()  — avg monthly return (%) by asset")
    print("=" * 60)

    # Header row
    header_months = "  ".join(f"{MONTH_NAMES[m]:>5}" for m in range(1, 13))
    print(f"  {'Asset':<8}  {header_months}")
    print("  " + "-" * 80)
    for asset in ASSETS:
        seas = get_seasonality(asset)
        row = "  ".join(
            f"{seas.get(m, float('nan')):>+5.1f}" for m in range(1, 13)
        )
        print(f"  {asset:<8}  {row}")
    print()

    # ── 6. get_dxy_deviation ─────────────────────────────────────────────────
    print("=" * 60)
    print("  [6] get_dxy_deviation()  — DXY vs its moving average")
    print("=" * 60)
    close_dxy = _close("DXY")
    current_dxy = float(close_dxy.iloc[-1])
    print(f"  DXY current  : {current_dxy:.3f}")
    for d in [10, 20, 30, 50, 200]:
        dev = get_dxy_deviation(days=d)
        direction = "above" if dev >= 0 else "below"
        print(f"  vs {d:>3}d MA   : {dev:>+7.3f}  ({direction} MA)")
    print()
