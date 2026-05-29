"""
Seasonality fetcher — monthly average price returns for crude and natural gas.

Uses 5 years of daily yfinance history (BZ=F for Brent, NG=F for Henry Hub).
No API key required.

Public function:
  get_seasonality() → dict with monthly return arrays + current-month bias
"""

import os
import sys
from datetime import datetime
from collections import defaultdict

_BACKEND = os.path.abspath(os.path.dirname(__file__))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

import yfinance as yf
import pandas as pd

MONTH_NAMES = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
               'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

_YEARS = 5
_TICKERS = {
    "brent":  "BZ=F",
    "natgas": "NG=F",
}


def _monthly_returns(ticker: str, years: int = _YEARS) -> list[float]:
    """
    Download `years` of daily history for `ticker`, resample to month-end,
    then compute the average month-over-month % return for each calendar month.

    Returns
    -------
    list of 12 floats — index 0 = Jan avg return %, index 11 = Dec avg return %.
    """
    try:
        df = yf.download(
            ticker,
            period=f"{years}y",
            interval="1d",
            progress=False,
            auto_adjust=True,
        )
    except Exception:
        return [0.0] * 12

    if df.empty:
        return [0.0] * 12

    # Flatten multi-level columns (yfinance multi-ticker behaviour)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    close = df["Close"].dropna()
    if close.empty:
        return [0.0] * 12

    # Resample to month-end closes, then compute pct change
    monthly = close.resample("ME").last()
    returns = monthly.pct_change().dropna()

    by_month: dict[int, list[float]] = defaultdict(list)
    for ts, ret in returns.items():
        if pd.notna(ret):
            by_month[ts.month - 1].append(float(ret) * 100.0)  # → %

    result = []
    for m in range(12):
        vals = by_month.get(m, [])
        result.append(round(sum(vals) / len(vals), 2) if vals else 0.0)

    return result


def _bias_label(ret: float) -> str:
    """Classify a monthly avg return into a seasonal-bias label."""
    if ret > 1.0:
        return "TAILWIND"
    if ret < -1.0:
        return "HEADWIND"
    return "NEUTRAL"


def get_seasonality() -> dict:
    """
    Compute seasonal monthly return averages for Brent crude and Natural Gas.

    Returns
    -------
    {
      "brent_monthly_returns":  list[float],  # 12 values, Jan→Dec, in %
      "natgas_monthly_returns": list[float],  # 12 values, Jan→Dec, in %
      "current_month":          int,           # 0-indexed (0=Jan … 11=Dec)
      "current_month_name":     str,           # e.g. "May"
      "brent_current_avg":      float,         # historical avg for current month
      "natgas_current_avg":     float,
      "brent_bias":             str,           # "TAILWIND" | "HEADWIND" | "NEUTRAL"
      "natgas_bias":            str,
      "data_years":             int,
    }
    """
    brent_rets  = _monthly_returns(_TICKERS["brent"],  years=_YEARS)
    natgas_rets = _monthly_returns(_TICKERS["natgas"], years=_YEARS)

    cur_month   = datetime.now().month - 1  # 0-indexed
    brent_cur   = brent_rets[cur_month]
    natgas_cur  = natgas_rets[cur_month]

    return {
        "brent_monthly_returns":  brent_rets,
        "natgas_monthly_returns": natgas_rets,
        "current_month":          cur_month,
        "current_month_name":     MONTH_NAMES[cur_month],
        "brent_current_avg":      brent_cur,
        "natgas_current_avg":     natgas_cur,
        "brent_bias":             _bias_label(brent_cur),
        "natgas_bias":            _bias_label(natgas_cur),
        "data_years":             _YEARS,
    }


if __name__ == "__main__":
    result = get_seasonality()
    print(f"Current month : {result['current_month_name']}")
    print(f"Brent avg     : {result['brent_current_avg']:+.2f}%  [{result['brent_bias']}]")
    print(f"Nat Gas avg   : {result['natgas_current_avg']:+.2f}%  [{result['natgas_bias']}]")
    print(f"Data years    : {result['data_years']}")
    print()
    print(f"{'Month':<6}  {'Brent':>8}  {'NatGas':>8}")
    print("-" * 27)
    for i, name in enumerate(MONTH_NAMES):
        marker = " ◄" if i == result["current_month"] else ""
        b = result["brent_monthly_returns"][i]
        g = result["natgas_monthly_returns"][i]
        print(f"{name:<6}  {b:>+7.2f}%  {g:>+7.2f}%{marker}")
