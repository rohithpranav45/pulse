"""
Technicals Fetcher — RSI, MACD, Bollinger Bands, ATR
=====================================================
Computes standard technical indicators from yfinance OHLCV data.
No TA-Lib dependency — pure pandas / numpy.

Indicators
----------
  RSI(14)              — Relative Strength Index
  MACD(12, 26, 9)      — Moving Average Convergence Divergence
  Bollinger Bands(20, 2σ) — % B position (0=lower, 0.5=mid, 1=upper)
  ATR(14)              — Average True Range (normalised as % of close)

Public API
----------
  get_technicals(symbol: str = "BZ=F") → dict
    {
      "symbol":          str,
      "rsi":             float,           # 0-100
      "rsi_signal":      str,             # "OVERBOUGHT" / "OVERSOLD" / "NEUTRAL"
      "macd":            float,           # MACD line
      "macd_signal":     float,           # Signal line
      "macd_histogram":  float,           # Histogram (MACD - signal)
      "macd_crossover":  str,             # "BULLISH" / "BEARISH" / "NONE"
      "bb_pct_b":        float,           # % B (0-1 range, can exceed)
      "bb_signal":       str,             # "OVERBOUGHT" / "OVERSOLD" / "NEUTRAL"
      "atr_pct":         float,           # ATR as % of close price
      "composite_score": float,           # -2 to +2
      "composite_reason": str,
      "timestamp":       str,
    }

  get_all_technicals() → dict
    Returns get_technicals() for BZ=F, CL=F, NG=F keyed by
    "brent", "wti", "henry_hub".
"""

import os as _os, sys as _sys
_BACKEND = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), ".."))
if _BACKEND not in _sys.path:
    _sys.path.insert(0, _BACKEND)

import logging
import numpy as np
import pandas as pd
from datetime import datetime, timezone

log = logging.getLogger(__name__)

# ── Defaults ──────────────────────────────────────────────────────────────────
_RSI_PERIOD   = 14
_MACD_FAST    = 12
_MACD_SLOW    = 26
_MACD_SIGNAL  = 9
_BB_PERIOD    = 20
_BB_STD       = 2.0
_ATR_PERIOD   = 14
_LOOKBACK     = 90      # calendar days of history to fetch


# ── Core computations ─────────────────────────────────────────────────────────

def _rsi(close: pd.Series, period: int = _RSI_PERIOD) -> float:
    """Wilder-smoothed RSI, returns the latest value."""
    delta  = close.diff().dropna()
    gains  = delta.clip(lower=0)
    losses = (-delta).clip(lower=0)

    avg_gain = gains.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = losses.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

    rs  = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return round(float(rsi.iloc[-1]), 2)


def _macd(close: pd.Series,
          fast: int = _MACD_FAST,
          slow: int = _MACD_SLOW,
          signal: int = _MACD_SIGNAL) -> tuple[float, float, float]:
    """
    Returns (macd_line, signal_line, histogram).
    Uses standard EMA (span-based, not Wilder).
    """
    ema_fast   = close.ewm(span=fast,   adjust=False).mean()
    ema_slow   = close.ewm(span=slow,   adjust=False).mean()
    macd_line  = ema_fast - ema_slow
    sig_line   = macd_line.ewm(span=signal, adjust=False).mean()
    histogram  = macd_line - sig_line
    return (
        round(float(macd_line.iloc[-1]),  4),
        round(float(sig_line.iloc[-1]),   4),
        round(float(histogram.iloc[-1]),  4),
    )


def _bollinger_pct_b(close: pd.Series,
                     period: int = _BB_PERIOD,
                     std_mult: float = _BB_STD) -> tuple[float, float, float, float]:
    """
    Returns (pct_b, upper_band, mid_band, lower_band).
    %B = (Close - Lower) / (Upper - Lower).
    """
    mid   = close.rolling(period).mean()
    std   = close.rolling(period).std(ddof=0)
    upper = mid + std_mult * std
    lower = mid - std_mult * std
    band_width = (upper - lower).iloc[-1]
    if band_width < 1e-8:
        return 0.5, float(upper.iloc[-1]), float(mid.iloc[-1]), float(lower.iloc[-1])

    pct_b = (close.iloc[-1] - lower.iloc[-1]) / band_width
    return (
        round(float(pct_b), 4),
        round(float(upper.iloc[-1]), 4),
        round(float(mid.iloc[-1]),   4),
        round(float(lower.iloc[-1]), 4),
    )


def _atr(high: pd.Series, low: pd.Series, close: pd.Series,
         period: int = _ATR_PERIOD) -> float:
    """
    Returns ATR(14) as a percentage of the latest close price.
    Uses Wilder smoothing (RMA).
    """
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low  - prev_close).abs(),
    ], axis=1).max(axis=1)

    atr = tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    last_close = float(close.iloc[-1])
    if last_close == 0:
        return 0.0
    return round(float(atr.iloc[-1]) / last_close * 100, 4)


def _macd_crossover(histogram_series: pd.Series) -> str:
    """
    Detect if MACD histogram just crossed zero in the last two bars.
    Returns "BULLISH", "BEARISH", or "NONE".
    """
    if len(histogram_series) < 2:
        return "NONE"
    prev = float(histogram_series.iloc[-2])
    curr = float(histogram_series.iloc[-1])
    if prev <= 0 < curr:
        return "BULLISH"
    if prev >= 0 > curr:
        return "BEARISH"
    return "NONE"


# ── Composite scoring ─────────────────────────────────────────────────────────

def _composite(rsi: float, histogram: float, crossover: str, pct_b: float) -> tuple[float, str]:
    """
    Combine RSI, MACD, and Bollinger %B into a single score in [-2, +2].

    Scoring logic:
      RSI < 30  → strongly oversold → +1
      RSI > 70  → strongly overbought → -1
      MACD histogram positive & rising → mild bullish momentum → +0.5
      MACD histogram negative & falling → mild bearish momentum → -0.5
      MACD crossover BULLISH → +0.5 | BEARISH → -0.5
      BB %B < 0.05 → near lower band → +0.5
      BB %B > 0.95 → near upper band → -0.5
    """
    score = 0.0
    parts = []

    # RSI
    if rsi < 30:
        score += 1.0
        parts.append(f"RSI {rsi:.0f} oversold")
    elif rsi < 40:
        score += 0.5
        parts.append(f"RSI {rsi:.0f} mildly oversold")
    elif rsi > 70:
        score -= 1.0
        parts.append(f"RSI {rsi:.0f} overbought")
    elif rsi > 60:
        score -= 0.5
        parts.append(f"RSI {rsi:.0f} mildly overbought")

    # MACD histogram direction
    if histogram > 0:
        score += 0.5
        parts.append("MACD positive momentum")
    elif histogram < 0:
        score -= 0.5
        parts.append("MACD negative momentum")

    # MACD crossover
    if crossover == "BULLISH":
        score += 0.5
        parts.append("MACD bullish crossover")
    elif crossover == "BEARISH":
        score -= 0.5
        parts.append("MACD bearish crossover")

    # Bollinger %B
    if pct_b < 0.05:
        score += 0.5
        parts.append(f"%B {pct_b:.2f} — near lower band")
    elif pct_b > 0.95:
        score -= 0.5
        parts.append(f"%B {pct_b:.2f} — near upper band")

    # Clamp to [-2, +2]
    score = max(-2.0, min(2.0, round(score, 2)))
    reason = "; ".join(parts) if parts else "No strong technical signal"
    return score, reason


# ── Data loading ──────────────────────────────────────────────────────────────

def _load_ohlcv(symbol: str) -> pd.DataFrame | None:
    """
    Load recent OHLCV from yfinance or from the shared historical cache.
    Falls back to None if unavailable.
    """
    # Try the shared historical loader first (avoids double download)
    try:
        from fetchers.historical import load_historical
        hist = load_historical()
        if symbol in hist:
            df = hist[symbol].copy()
            df.columns = [str(c).replace(" ", "_").title() for c in df.columns]
            # normalise to expected column names
            col_map = {}
            for c in df.columns:
                lc = c.lower()
                if "close" in lc and "adj" not in lc:
                    col_map[c] = "Close"
                elif "high" in lc:
                    col_map[c] = "High"
                elif "low" in lc:
                    col_map[c] = "Low"
                elif "open" in lc:
                    col_map[c] = "Open"
                elif "volume" in lc:
                    col_map[c] = "Volume"
            df.rename(columns=col_map, inplace=True)
            for needed in ("Open", "High", "Low", "Close"):
                if needed not in df.columns:
                    log.warning("Column %s missing in historical for %s", needed, symbol)
                    return None
            return df.dropna(subset=["Close"])
    except Exception as exc:
        log.debug("Historical loader failed for %s: %s", symbol, exc)

    # Direct yfinance fallback (Ticker.history avoids tz join errors)
    try:
        import yfinance as yf
        df = yf.Ticker(symbol).history(period="6mo", auto_adjust=True)
        if df.empty:
            return None
        # Flatten multi-level columns if present
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df.dropna(subset=["Close"])
    except Exception as exc:
        log.warning("yfinance fallback failed for %s: %s", symbol, exc)
        return None


# ── Per-symbol analysis ───────────────────────────────────────────────────────

def get_technicals(symbol: str = "BZ=F") -> dict:
    """
    Compute all technical indicators for a single symbol.
    Returns a best-effort dict; falls back to neutral values on data failure.
    """
    df = _load_ohlcv(symbol)

    if df is None or len(df) < _MACD_SLOW + _MACD_SIGNAL + 5:
        log.warning("Insufficient data for technicals on %s", symbol)
        return {
            "symbol":           symbol,
            "rsi":              50.0,
            "rsi_signal":       "NEUTRAL",
            "macd":             0.0,
            "macd_signal":      0.0,
            "macd_histogram":   0.0,
            "macd_crossover":   "NONE",
            "bb_pct_b":         0.5,
            "bb_upper":         None,
            "bb_mid":           None,
            "bb_lower":         None,
            "bb_signal":        "NEUTRAL",
            "atr_pct":          0.0,
            "composite_score":  0.0,
            "composite_reason": "Insufficient historical data",
            "error":            True,
            "timestamp":        datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }

    close = df["Close"].astype(float)
    high  = df["High"].astype(float)
    low   = df["Low"].astype(float)

    # ── indicators ────────────────────────────────────────────────────────────
    rsi_val = _rsi(close)
    rsi_sig = ("OVERBOUGHT" if rsi_val > 70
               else "OVERSOLD" if rsi_val < 30
               else "NEUTRAL")

    macd_val, sig_val, hist_val = _macd(close)

    # Need histogram series for crossover detection
    ema_f   = close.ewm(span=_MACD_FAST,   adjust=False).mean()
    ema_s   = close.ewm(span=_MACD_SLOW,   adjust=False).mean()
    macd_s  = (ema_f - ema_s).ewm(span=_MACD_SIGNAL, adjust=False).mean()
    hist_s  = (ema_f - ema_s) - macd_s
    cross   = _macd_crossover(hist_s)

    pct_b, bb_upper, bb_mid, bb_lower = _bollinger_pct_b(close)
    bb_sig = ("OVERBOUGHT" if pct_b > 0.95
              else "OVERSOLD" if pct_b < 0.05
              else "NEUTRAL")

    atr_pct = _atr(high, low, close)

    score, reason = _composite(rsi_val, hist_val, cross, pct_b)

    return {
        "symbol":           symbol,
        "rsi":              rsi_val,
        "rsi_signal":       rsi_sig,
        "macd":             macd_val,
        "macd_signal":      sig_val,
        "macd_histogram":   hist_val,
        "macd_crossover":   cross,
        "bb_pct_b":         pct_b,
        "bb_upper":         bb_upper,
        "bb_mid":           bb_mid,
        "bb_lower":         bb_lower,
        "bb_signal":        bb_sig,
        "atr_pct":          atr_pct,
        "composite_score":  score,
        "composite_reason": reason,
        "error":            False,
        "timestamp":        datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


# ── Mapper for signal engine keys ─────────────────────────────────────────────
_SYMBOL_MAP = {
    "brent":     "BZ=F",
    "wti":       "CL=F",
    "henry_hub": "NG=F",
}


def get_all_technicals() -> dict:
    """
    Return technicals for Brent, WTI, and Henry Hub.

    {
      "brent":     {...},
      "wti":       {...},
      "henry_hub": {...},
      "timestamp": str,
    }
    """
    result = {}
    for key, sym in _SYMBOL_MAP.items():
        result[key] = get_technicals(sym)
    result["timestamp"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return result


# ── __main__ — quick CLI test ─────────────────────────────────────────────────
if __name__ == "__main__":
    import json

    for key, sym in _SYMBOL_MAP.items():
        print(f"\n{'─'*50}")
        print(f"  {key.upper()} ({sym})")
        print(f"{'─'*50}")
        t = get_technicals(sym)
        if t.get("error"):
            print(f"  ERROR: {t['composite_reason']}")
        else:
            print(f"  RSI:        {t['rsi']:.1f}  →  {t['rsi_signal']}")
            print(f"  MACD:       {t['macd']:+.4f}  (hist: {t['macd_histogram']:+.4f})  "
                  f"crossover: {t['macd_crossover']}")
            print(f"  Bollinger:  %B = {t['bb_pct_b']:.3f}  →  {t['bb_signal']}")
            print(f"  ATR:        {t['atr_pct']:.2f}% of price")
            sgn = "+" if t['composite_score'] >= 0 else ""
            print(f"  Composite:  {sgn}{t['composite_score']:.2f}  —  {t['composite_reason']}")
