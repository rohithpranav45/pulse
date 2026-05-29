"""
Seasonality fetcher — monthly average price returns for 5 energy products.

Uses 5 years of daily yfinance history.
No API key required.

Products:
  Brent crude   (BZ=F)
  WTI crude     (CL=F)
  Henry Hub gas (NG=F)
  RBOB gasoline (RB=F)
  Heating oil   (HO=F)

Public function:
  get_seasonality() → dict with monthly return arrays per product +
                      current-month bias labels
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
_PRODUCTS = [
    # (key, ticker, display_label)
    ("brent",        "BZ=F", "Brent"),
    ("wti",          "CL=F", "WTI"),
    ("natgas",       "NG=F", "Nat Gas"),
    ("rbob",         "RB=F", "RBOB"),
    ("heating_oil",  "HO=F", "Heating Oil"),
]


def _monthly_stats(ticker: str, years: int = _YEARS) -> dict:
    """
    Download `years` of daily history for `ticker`, resample to month-end,
    then compute mean + std of month-over-month % return for each calendar
    month.  Quiets yfinance ERROR logging for delisted/missing tickers.

    Returns
    -------
    {
      "mean":  list[12]  — average monthly return % (Jan..Dec)
      "std":   list[12]  — std dev of monthly returns
      "n":     list[12]  — number of observations per month
      "ok":    bool      — True if fetch produced a non-empty series
    }
    """
    empty = {"mean": [0.0] * 12, "std": [0.0] * 12, "n": [0] * 12, "ok": False}
    try:
        import logging as _lg
        _yf_log = _lg.getLogger("yfinance")
        _prev = _yf_log.level
        _yf_log.setLevel(_lg.CRITICAL)
        try:
            df = yf.Ticker(ticker).history(period=f"{years}y", auto_adjust=True)
        finally:
            _yf_log.setLevel(_prev)
    except Exception:
        return empty

    if df is None or df.empty or "Close" not in df.columns:
        return empty

    close = df["Close"].dropna()
    if close.empty:
        return empty

    # Resample to month-end closes, then compute pct change
    monthly = close.resample("ME").last()
    returns = monthly.pct_change().dropna()

    by_month: dict[int, list[float]] = defaultdict(list)
    for ts, ret in returns.items():
        if pd.notna(ret):
            by_month[ts.month - 1].append(float(ret) * 100.0)

    means, stds, ns = [], [], []
    for m in range(12):
        vals = by_month.get(m, [])
        if vals:
            avg = sum(vals) / len(vals)
            # population std dev (small samples)
            var = sum((v - avg) ** 2 for v in vals) / len(vals)
            sd = var ** 0.5
        else:
            avg, sd = 0.0, 0.0
        means.append(round(avg, 2))
        stds.append(round(sd, 2))
        ns.append(len(vals))

    return {"mean": means, "std": stds, "n": ns, "ok": True}


def _bias_label(ret: float) -> str:
    """Classify a monthly avg return into a seasonal-bias label."""
    if ret > 1.0:
        return "TAILWIND"
    if ret < -1.0:
        return "HEADWIND"
    return "NEUTRAL"


def get_seasonality() -> dict:
    """
    Compute seasonal monthly return averages for 5 energy products.

    Returns
    -------
    {
      "products": [
        {
          "key":              "brent",
          "label":            "Brent",
          "ticker":           "BZ=F",
          "monthly_returns":  [12 floats, Jan..Dec, %],
          "monthly_std":      [12 floats],
          "monthly_n":        [12 ints],
          "current_avg":      float,
          "current_std":      float,
          "bias":             "TAILWIND" | "HEADWIND" | "NEUTRAL"
        },
        ...
      ],
      "current_month":      int,    # 0-indexed
      "current_month_name": str,
      "data_years":         int,

      # ── Legacy keys (frontend backwards compat) ────────────────────────────
      "brent_monthly_returns":  [12 floats],
      "natgas_monthly_returns": [12 floats],
      "brent_current_avg":      float,
      "natgas_current_avg":     float,
      "brent_bias":             str,
      "natgas_bias":            str,
    }
    """
    cur_month = datetime.now().month - 1

    products = []
    for key, ticker, label in _PRODUCTS:
        stats = _monthly_stats(ticker, years=_YEARS)
        cur_avg = stats["mean"][cur_month]
        cur_std = stats["std"][cur_month]
        products.append({
            "key":             key,
            "label":           label,
            "ticker":          ticker,
            "monthly_returns": stats["mean"],
            "monthly_std":     stats["std"],
            "monthly_n":       stats["n"],
            "current_avg":     cur_avg,
            "current_std":     cur_std,
            "bias":            _bias_label(cur_avg),
            "ok":              stats["ok"],
        })

    # Legacy fields for the older frontend code path
    brent = next((p for p in products if p["key"] == "brent"), None)
    natgas = next((p for p in products if p["key"] == "natgas"), None)

    return {
        "products":               products,
        "current_month":          cur_month,
        "current_month_name":     MONTH_NAMES[cur_month],
        "data_years":             _YEARS,
        # ── legacy ─────────────────────────────────────────────────────────
        "brent_monthly_returns":  (brent  or {}).get("monthly_returns", [0.0] * 12),
        "natgas_monthly_returns": (natgas or {}).get("monthly_returns", [0.0] * 12),
        "brent_current_avg":      (brent  or {}).get("current_avg", 0.0),
        "natgas_current_avg":     (natgas or {}).get("current_avg", 0.0),
        "brent_bias":             (brent  or {}).get("bias", "NEUTRAL"),
        "natgas_bias":            (natgas or {}).get("bias", "NEUTRAL"),
    }


if __name__ == "__main__":
    result = get_seasonality()
    print(f"Current month : {result['current_month_name']}")
    print(f"Data years    : {result['data_years']}")
    print()
    header = f"{'Month':<6}" + "".join(f"  {p['label']:>11}" for p in result['products'])
    print(header)
    print("-" * len(header))
    for i, name in enumerate(MONTH_NAMES):
        marker = " ◄" if i == result["current_month"] else ""
        row = f"{name:<6}"
        for p in result['products']:
            row += f"  {p['monthly_returns'][i]:>+10.2f}%"
        print(row + marker)
    print()
    print("Current month bias:")
    for p in result['products']:
        print(f"  {p['label']:<14}  {p['current_avg']:+6.2f}%  ±{p['current_std']:.2f}  [{p['bias']}]")
