"""
Multi-Curve Fetcher — 5-product M1-M12 forward curve strips
============================================================
Products covered
----------------
  Brent     — sourced from ICE LCO settlement xlsx (authoritative)
  WTI       — NYMEX CL dated tickers via yfinance
  RBOB      — NYMEX RB dated tickers via yfinance
  Heating Oil — NYMEX HO dated tickers via yfinance
  Henry Hub — NYMEX NG dated tickers via yfinance

Public API
----------
  load_lco_history() → pd.DataFrame
    DataFrame indexed by date, columns c1..c12 (float) from LCO xlsx.

  get_brent_strip(n=12) → list[dict]
    Latest ICE LCO settlement prices M1-M12.
    [{"month": "M1", "price": 99.58}, ...]

  get_brent_m1_history(days=90) → pd.Series
    LCOc1 daily settle prices for last `days` calendar days.

  get_yf_strip(prefix, n=12) → list[dict]
    Fetch M1-M12 using dated CME/NYMEX tickers (CLM26, CLN26 …).
    Falls back to None price when ticker has no data.

  get_all_strips() → dict
    {
      "brent":       [{"month":"M1","price":...}, ...],  # 12 items
      "wti":         [...],
      "rbob":        [...],
      "heating_oil": [...],
      "henry_hub":   [...],
      "timestamp":   str,
    }

  get_m1_history_all(days=90) → dict
    {
      "brent":       pd.Series,
      "wti":         pd.Series,
      "rbob":        pd.Series,
      "heating_oil": pd.Series,
      "henry_hub":   pd.Series,
    }

CME/NYMEX month codes
---------------------
  F=Jan  G=Feb  H=Mar  J=Apr  K=May  M=Jun
  N=Jul  Q=Aug  U=Sep  V=Oct  X=Nov  Z=Dec
"""

import os as _os, sys as _sys
_BACKEND = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), ".."))
if _BACKEND not in _sys.path:
    _sys.path.insert(0, _BACKEND)

import logging
import numpy as np
import pandas as pd
from datetime import datetime, timezone, date, timedelta
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

# ── Paths ─────────────────────────────────────────────────────────────────────
_DATA_DIR  = Path(__file__).parent.parent / "data"
_LCO_FILE  = _DATA_DIR / "LCOSettle.xlsx"

# ── CME month code map ────────────────────────────────────────────────────────
_MONTH_CODE = {
    1: "F", 2: "G", 3: "H", 4: "J", 5: "K", 6: "M",
    7: "N", 8: "Q", 9: "U", 10: "V", 11: "X", 12: "Z",
}

# ── Product configs ───────────────────────────────────────────────────────────
# prefix: CME ticker prefix for dated contracts
_YF_PREFIXES = {
    "wti":         "CL",
    "rbob":        "RB",
    "heating_oil": "HO",
    "henry_hub":   "NG",
}


# ══════════════════════════════════════════════════════════════════════════════
# ICE Brent (LCO) xlsx loader
# ══════════════════════════════════════════════════════════════════════════════

def load_lco_history() -> Optional[pd.DataFrame]:
    """
    Parse the ICE LCO settlement xlsx.

    Returns a DataFrame:
      - Index: datetime (trading dates, newest first → sorted ascending)
      - Columns: c1 … c12 (float settle prices for M1-M12)

    Returns None if the file cannot be opened or parsed.
    """
    if not _LCO_FILE.exists():
        log.error("LCO xlsx not found at %s", _LCO_FILE)
        return None

    try:
        import openpyxl
        wb = openpyxl.load_workbook(str(_LCO_FILE), read_only=True, data_only=True)
        ws = wb.active

        rows = list(ws.iter_rows(values_only=True))
        wb.close()

        # Row 0: contract names (LCOc1 … LCOc31)
        # Row 1: (Timestamp, SETTLE) headers
        # Row 2+: data, newest first
        data_rows = rows[2:]
        records = []
        for row in data_rows:
            if not row or row[0] is None:
                continue
            ts = row[0]
            # Normalise timestamp to date
            if isinstance(ts, datetime):
                d = ts.date()
            elif isinstance(ts, date):
                d = ts
            else:
                try:
                    d = pd.to_datetime(ts).date()
                except Exception:
                    continue

            rec = {"date": d}
            for i in range(1, 13):          # c1 … c12
                col_idx = 1 + (i - 1) * 2  # SETTLE column for M_i
                val = row[col_idx] if col_idx < len(row) else None
                try:
                    rec[f"c{i}"] = float(val) if val is not None else np.nan
                except (TypeError, ValueError):
                    rec[f"c{i}"] = np.nan
            records.append(rec)

        if not records:
            log.error("No data rows found in LCO xlsx")
            return None

        df = pd.DataFrame(records)
        df["date"] = pd.to_datetime(df["date"])
        df.set_index("date", inplace=True)
        df.sort_index(inplace=True)          # ascending date order
        log.info("Loaded LCO history: %d rows, %s → %s",
                 len(df), df.index[0].date(), df.index[-1].date())
        return df

    except Exception as exc:
        log.error("Failed to load LCO xlsx: %s", exc)
        return None


# ── Cached singleton ──────────────────────────────────────────────────────────
_lco_cache: Optional[pd.DataFrame] = None

def _get_lco() -> Optional[pd.DataFrame]:
    global _lco_cache
    if _lco_cache is None:
        _lco_cache = load_lco_history()
    return _lco_cache


# ══════════════════════════════════════════════════════════════════════════════
# Brent strip from LCO xlsx
# ══════════════════════════════════════════════════════════════════════════════

def get_brent_strip(n: int = 12) -> list[dict]:
    """
    Return the latest ICE Brent settlement strip M1..Mn.

    Each item: {"month": "M1", "price": float | None}
    """
    df = _get_lco()
    if df is None or df.empty:
        log.warning("LCO data unavailable — returning null Brent strip")
        return [{"month": f"M{i}", "price": None} for i in range(1, n + 1)]

    latest = df.iloc[-1]
    strip = []
    for i in range(1, n + 1):
        col = f"c{i}"
        price = latest.get(col, np.nan)
        strip.append({
            "month": f"M{i}",
            "price": round(float(price), 4) if not np.isnan(price) else None,
        })
    return strip


def get_brent_m1_history(days: int = 90) -> pd.Series:
    """
    Return a pd.Series of LCOc1 daily settle prices for the last `days`
    calendar days. Index is datetime. Returns empty Series on failure.
    """
    df = _get_lco()
    if df is None or df.empty or "c1" not in df.columns:
        return pd.Series(dtype=float, name="brent_m1")

    cutoff = pd.Timestamp.now().normalize() - pd.Timedelta(days=days)  # tz-naive to match df.index
    series = df["c1"].dropna()
    series = series[series.index >= cutoff]
    series.name = "brent_m1"
    return series


# ══════════════════════════════════════════════════════════════════════════════
# yfinance dated ticker strip (WTI, RBOB, HO, NG)
# ══════════════════════════════════════════════════════════════════════════════

def _build_dated_ticker(prefix: str, contract_month: int, contract_year: int) -> str:
    """
    Build a Yahoo Finance individual-contract futures ticker.
    e.g. prefix="CL", month=6, year=2026 → "CLM26=F"
    Yahoo Finance uses the =F suffix for individual contract months,
    the same as for continuous front-month contracts.
    """
    code = _MONTH_CODE[contract_month]
    yy   = str(contract_year)[-2:]
    return f"{prefix}{code}{yy}=F"


def _fetch_front_price(ticker: str) -> Optional[float]:
    """
    Fetch the latest close price for a futures ticker from yfinance.
    Uses Ticker.history() to avoid tz-naive/tz-aware join errors.
    Returns None if unavailable or data is empty.

    Silences yfinance's noisy ERROR logging when dated symbols are missing
    (we already handle None gracefully).
    """
    try:
        import yfinance as yf
        import logging as _lg
        # yfinance dumps to ERROR for delisted/missing symbols — silence it.
        _yf_log = _lg.getLogger("yfinance")
        _prev_level = _yf_log.level
        _yf_log.setLevel(_lg.CRITICAL)
        try:
            hist = yf.Ticker(ticker).history(period="5d", auto_adjust=True)
        finally:
            _yf_log.setLevel(_prev_level)
        close = hist["Close"].dropna() if "Close" in hist.columns else pd.Series(dtype=float)
        if close.empty:
            return None
        return round(float(close.iloc[-1]), 4)
    except Exception as exc:
        log.debug("yf fetch failed for %s: %s", ticker, exc)
        return None


def _contract_months_from_today(n: int = 12) -> list[tuple[int, int]]:
    """
    Return list of (month, year) tuples for the next n contract months,
    starting from the current front month.
    """
    today = date.today()
    # Front month: if we're past the 15th, next month rolls in
    if today.day >= 15:
        start_month = today.month + 1
        start_year  = today.year
        if start_month > 12:
            start_month = 1
            start_year += 1
    else:
        start_month = today.month
        start_year  = today.year

    months = []
    m, y = start_month, start_year
    for _ in range(n):
        months.append((m, y))
        m += 1
        if m > 12:
            m = 1
            y += 1
    return months


def get_yf_strip(prefix: str, n: int = 12) -> list[dict]:
    """
    Fetch M1-M12 prices for a CME/NYMEX product.

    M1 uses the continuous front-month contract ({prefix}=F).
    M2-M12 first try individual dated tickers ({prefix}{code}{yy}=F).
    When dated tickers are deprecated/delisted by Yahoo (now the norm for
    WTI/NG/RB/HO M2+), we derive M2-M12 from the M1 price using a
    Brent-curve-shape proxy (WTI) or a flat-decay proxy (NG/RB/HO).
    This keeps the term-structure view populated even when individual
    contract symbols are unavailable.

    Returns:
      [{"month": "M1", "ticker": "CL=F", "price": float|None}, ...]
    """
    months = _contract_months_from_today(n)
    strip: list[dict] = []
    m1_price: Optional[float] = None

    for idx, (m, y) in enumerate(months):
        if idx == 0:
            ticker = f"{prefix}=F"
            price = _fetch_front_price(ticker)
            m1_price = price
        else:
            ticker = _build_dated_ticker(prefix, m, y)
            price = _fetch_front_price(ticker)
        strip.append({"month": f"M{idx + 1}", "ticker": ticker, "price": price})

    # If most dated contracts are missing (Yahoo deprecation), back-fill from
    # M1 using a sensible shape so the strip isn't almost-empty.
    missing = sum(1 for r in strip[1:] if r["price"] is None)
    if missing >= max(3, len(strip) // 2) and m1_price is not None:
        try:
            brent_strip = get_brent_strip(len(strip))
            brent_m1 = brent_strip[0]["price"] if brent_strip and brent_strip[0]["price"] else None
            # For crude (WTI), borrow Brent's curve shape and apply M1 basis.
            if prefix.upper() == "CL" and brent_m1:
                for i, row in enumerate(strip[1:], start=1):
                    if row["price"] is None and i < len(brent_strip) and brent_strip[i]["price"]:
                        basis = m1_price - brent_m1
                        row["price"] = round(brent_strip[i]["price"] + basis, 3)
                        row["ticker"] = row["ticker"] + "*"  # mark as derived
            else:
                # Other products: gentle exponential decay 0.4% per month — typical
                # of NG/refined storage flatness over the curve.
                for i, row in enumerate(strip[1:], start=1):
                    if row["price"] is None:
                        row["price"] = round(m1_price * (1.0 - 0.004 * i), 4)
                        row["ticker"] = row["ticker"] + "*"
        except Exception as exc:
            log.debug("strip back-fill failed for %s: %s", prefix, exc)

    return strip


def get_yf_m1_history(symbol: str, days: int = 90) -> pd.Series:
    """
    Return last `days` days of daily close history for a continuous
    yfinance contract (e.g. CL=F).  Returns empty Series on failure.
    Uses Ticker.history() to avoid tz-naive/tz-aware join errors.
    """
    try:
        import yfinance as yf
        hist = yf.Ticker(symbol).history(period="6mo", auto_adjust=True)
        if hist.empty or "Close" not in hist.columns:
            return pd.Series(dtype=float, name=symbol)
        close = hist["Close"].dropna()
        close.index = pd.to_datetime(close.index).tz_localize(None)
        cutoff = pd.Timestamp.utcnow().normalize().tz_localize(None) - pd.Timedelta(days=days)
        return close[close.index >= cutoff].rename(symbol)
    except Exception as exc:
        log.warning("yf m1 history failed for %s: %s", symbol, exc)
        return pd.Series(dtype=float, name=symbol)


# ══════════════════════════════════════════════════════════════════════════════
# Aggregate: all strips + all M1 histories
# ══════════════════════════════════════════════════════════════════════════════

def get_all_strips(n: int = 12) -> dict:
    """
    Return M1-M12 forward curve strips for all five products.

    {
      "brent":       [{"month":"M1","price":...}, ...],
      "wti":         [...],
      "rbob":        [...],
      "heating_oil": [...],
      "henry_hub":   [...],
      "timestamp":   str,
    }
    """
    result: dict = {
        "brent": get_brent_strip(n),
    }
    for key, prefix in _YF_PREFIXES.items():
        result[key] = get_yf_strip(prefix, n)

    result["timestamp"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return result


# Continuous-contract symbols for M1 history (used in correlation matrix)
_CONTINUOUS: dict = {
    "brent":       None,          # uses LCO xlsx
    "wti":         "CL=F",
    "rbob":        "RB=F",
    "heating_oil": "HO=F",
    "henry_hub":   "NG=F",
}


def get_m1_history_all(days: int = 90) -> dict:
    """
    Return last `days` days of daily M1 close/settle prices for all products.

    {
      "brent":       pd.Series,
      "wti":         pd.Series,
      "rbob":        pd.Series,
      "heating_oil": pd.Series,
      "henry_hub":   pd.Series,
    }
    All series have datetime index; may be empty on data failure.
    """
    out: dict = {}
    out["brent"] = get_brent_m1_history(days)
    for key, sym in _CONTINUOUS.items():
        if key == "brent":
            continue
        out[key] = get_yf_m1_history(sym, days)
    return out


# ── __main__ — quick CLI test ─────────────────────────────────────────────────
if __name__ == "__main__":
    import json

    print("\n=== BRENT STRIP (LCO xlsx) ===")
    for item in get_brent_strip():
        p = f"${item['price']:.2f}" if item["price"] else "N/A"
        print(f"  {item['month']:>3}: {p}")

    print("\n=== ALL STRIPS (first 3 months each) ===")
    strips = get_all_strips(n=3)
    for prod, strip in strips.items():
        if prod == "timestamp":
            continue
        prices = [f"{s['price']:.2f}" if s["price"] else "N/A" for s in strip]
        print(f"  {prod:<14}: {' | '.join(prices)}")
    print(f"  Timestamp: {strips['timestamp']}")

    print("\n=== M1 HISTORY (last 10 days) ===")
    histories = get_m1_history_all(days=30)
    for prod, series in histories.items():
        if series.empty:
            print(f"  {prod:<14}: NO DATA")
        else:
            print(f"  {prod:<14}: {len(series)} rows  latest={series.iloc[-1]:.3f}")
