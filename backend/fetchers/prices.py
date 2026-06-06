"""
Live price fetcher — yfinance
Returns {name: {price, change_pct, timestamp}} for all core energy/macro tickers.
"""

import os
from datetime import datetime, timezone
from dotenv import load_dotenv
import yfinance as yf

load_dotenv()

# ── Legacy map (used by fetch_prices) ────────────────────────────────────────
TICKERS = {
    "Brent Crude":  "BZ=F",
    "WTI Crude":    "CL=F",
    "Henry Hub":    "NG=F",
    "DXY":          "DX-Y.NYB",
    "S&P 500 Fut":  "ES=F",
    "Gold":         "GC=F",
    "VIX":          "^VIX",
    "Gasoline":     "RB=F",
    "Heating Oil":  "HO=F",
}

# ── Asset-code map (used by get_live_prices) ─────────────────────────────────
ASSET_MAP = {
    "brent":        "BZ=F",
    "wti":          "CL=F",
    "henry_hub":    "NG=F",
    "dxy":          "DX-Y.NYB",
    "sp500":        "ES=F",
    "gold":         "GC=F",
    "vix":          "^VIX",
    "gasoline":     "RB=F",
    "heating_oil":  "HO=F",
    "treasury_10y": "^TNX",
}

# Module-level stale-value cache — persists across calls within a process
_last_known: dict = {}


def fetch_prices() -> dict:
    """
    Fetch latest close + 1-day % change for every ticker in TICKERS.

    Returns
    -------
    dict
        {
          "Brent Crude": {
              "ticker":     "BZ=F",
              "price":      61.23,
              "change_pct": -1.42,
              "timestamp":  "2026-05-25T14:30:00+00:00"
          },
          ...
        }
    Tickers that fail are omitted from the result and their error is printed.
    """
    result     = {}
    fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    for name, symbol in TICKERS.items():
        try:
            # Per-ticker download avoids tz-naive/tz-aware join errors in batch mode
            hist  = yf.Ticker(symbol).history(period="5d", interval="1d", auto_adjust=True)
            close = hist["Close"].dropna()

            if len(close) < 2:
                print(f"  [WARN] {name} ({symbol}): not enough rows ({len(close)})")
                continue

            price      = float(close.iloc[-1])
            prev_price = float(close.iloc[-2])
            change_pct = round((price - prev_price) / prev_price * 100, 2)

            result[name] = {
                "ticker":     symbol,
                "price":      round(price, 4),
                "change_pct": change_pct,
                "timestamp":  fetched_at,
            }

        except Exception as exc:
            print(f"  [ERROR] {name} ({symbol}): {exc}")

    return result


def get_live_prices() -> dict:
    """
    Fetch live OHLC + change data for all assets, keyed by asset code.

    Returns
    -------
    {
      "brent": {
          "price":      100.21,
          "change_abs": -3.32,
          "change_pct": -3.21,
          "high":       101.50,
          "low":         99.80,
          "timestamp":  "2026-05-25T14:30:00+00:00",
          "stale":      False,
      },
      ...
    }
    On a per-asset fetch failure the last known good values are returned
    with stale=True.  Assets with no prior data are omitted on failure.
    """
    global _last_known

    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    result    = {}

    for code, symbol in ASSET_MAP.items():
        try:
            # Per-ticker history() avoids tz-naive/tz-aware join errors
            # that occur with multi-symbol yf.download() on mixed exchanges.
            hist  = yf.Ticker(symbol).history(period="5d", interval="1d", auto_adjust=True)
            close = hist["Close"].dropna()
            high  = hist["High"].dropna()
            low   = hist["Low"].dropna()

            if len(close) < 2:
                raise ValueError(f"Only {len(close)} row(s) — need ≥2")

            price      = round(float(close.iloc[-1]), 4)
            prev_close = round(float(close.iloc[-2]), 4)
            change_abs = round(price - prev_close, 4)
            change_pct = round(change_abs / prev_close * 100, 2) if prev_close else 0.0
            day_high   = round(float(high.iloc[-1]), 4)
            day_low    = round(float(low.iloc[-1]),  4)

            entry = {
                "price":      price,
                "change_abs": change_abs,
                "change_pct": change_pct,
                "high":       day_high,
                "low":        day_low,
                "timestamp":  timestamp,
                "stale":      False,
            }
            _last_known[code] = entry          # update stale-value cache
            result[code] = entry

        except Exception as exc:
            print(f"  [WARN] {code} ({symbol}): {exc} — trying Stooq fallback")
            # Try Stooq as a second-source feed before giving up
            try:
                from fetchers.stooq import get_stooq_quote, _STOOQ_MAP
                stooq_sym = _STOOQ_MAP.get(code)
                q = get_stooq_quote(stooq_sym) if stooq_sym else None
                if q and q.get("price"):
                    entry = {
                        "price":      q["price"],
                        "change_abs": q["change_abs"],
                        "change_pct": q["change_pct"],
                        "high":       q.get("high",  q["price"]),
                        "low":        q.get("low",   q["price"]),
                        "timestamp":  timestamp,
                        "stale":      False,
                        "source":     "stooq.com (fallback)",
                    }
                    _last_known[code] = entry
                    result[code] = entry
                    continue
            except Exception:
                pass
            if code in _last_known:
                stale_entry = dict(_last_known[code])
                stale_entry["stale"] = True
                result[code] = stale_entry
            # else: asset simply omitted from result on first-ever failure

    return result


def get_single_price(asset_code: str) -> dict:
    """
    Return live price data for one asset by its code.

    Parameters
    ----------
    asset_code : str
        One of: brent, wti, henry_hub, dxy, sp500, gold, vix,
                gasoline, heating_oil

    Returns
    -------
    dict  — same shape as a single entry from get_live_prices()

    Raises
    ------
    KeyError  if asset_code is not recognised
    """
    if asset_code not in ASSET_MAP:
        raise KeyError(
            f"Unknown asset code '{asset_code}'. "
            f"Valid codes: {sorted(ASSET_MAP)}"
        )
    return get_live_prices()[asset_code]


if __name__ == "__main__":
    print("Fetching live prices...\n")
    prices = get_live_prices()

    # Display labels aligned with asset codes
    LABELS = {
        "brent":       ("Brent Crude",  "BZ=F",     "$/bbl"),
        "wti":         ("WTI Crude",    "CL=F",     "$/bbl"),
        "henry_hub":   ("Henry Hub",    "NG=F",     "$/MMBtu"),
        "dxy":         ("DXY",          "DX-Y.NYB", "index"),
        "sp500":       ("S&P 500 Fut",  "ES=F",     "pts"),
        "gold":        ("Gold",         "GC=F",     "$/oz"),
        "vix":         ("VIX",          "^VIX",     "index"),
        "gasoline":    ("Gasoline",     "RB=F",     "$/gal"),
        "heating_oil": ("Heating Oil",  "HO=F",     "$/gal"),
    }

    print(f"  {'Asset':<16} {'Ticker':<12} {'Price':>10} "
          f"{'Chg':>9} {'Chg%':>7}  {'High':>10} {'Low':>10}  {'Unit':<9}  Status")
    print("  " + "-" * 98)

    for code, (label, ticker, unit) in LABELS.items():
        if code not in prices:
            print(f"  {label:<16} {ticker:<12}  {'N/A':>10}")
            continue

        d     = prices[code]
        arrow = "+" if d["change_pct"] >= 0 else "-"
        flag  = " [STALE]" if d["stale"] else ""

        print(
            f"  {label:<16} {ticker:<12}"
            f"  {d['price']:>10.3f}"
            f"  {d['change_abs']:>+9.3f}"
            f"  {d['change_pct']:>+6.2f}%"
            f"  {d['high']:>10.3f}"
            f"  {d['low']:>10.3f}"
            f"  {unit:<9}"
            f"{flag}"
        )

    ts = next(iter(prices.values()))["timestamp"]
    stale_count = sum(1 for v in prices.values() if v["stale"])
    print(f"\n  Fetched at : {ts}")
    print(f"  Assets     : {len(prices)}/{len(ASSET_MAP)} returned"
          + (f"  |  {stale_count} stale" if stale_count else ""))
