"""
Options Implied Volatility Fetcher
====================================
Fetches ATM implied volatility for USO (crude proxy) and UNG (Henry Hub proxy)
from yfinance option chains.  Maintains a rolling 30-entry SQLite history per
ticker so the percentile rank survives server restarts.

Signal logic
------------
  crude_iv_pctile > 0.80  →  -1   (high fear premium — bearish lean)
  crude_iv_pctile < 0.20  →  +1   (complacency — mild bullish)
  else                    →   0

Public API
----------
  get_iv() -> dict
"""

import os
import sys
import logging
import sqlite3
import time
from datetime import datetime, timezone, date

import numpy as np

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_ROOT    = os.path.abspath(os.path.join(_BACKEND, ".."))
for _p in (_BACKEND, _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

log = logging.getLogger("pulse.options_iv")

# ── SQLite persistence for IV history ────────────────────────────────────────
_DB_PATH   = os.path.join(_BACKEND, "db", "pulse_cache.db")
_IV_MAXLEN = 30   # rolling window

def _ensure_iv_table():
    """Create iv_history table if it doesn't exist."""
    try:
        c = sqlite3.connect(_DB_PATH, check_same_thread=False)
        c.execute("""
            CREATE TABLE IF NOT EXISTS iv_history (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker    TEXT NOT NULL,
                iv        REAL NOT NULL,
                ts        REAL NOT NULL
            )
        """)
        c.commit()
        c.close()
    except Exception as exc:
        log.warning("iv_history table init: %s", exc)

_ensure_iv_table()


def _get_iv_history(ticker: str) -> list:
    """Return last _IV_MAXLEN IV values for this ticker (oldest first)."""
    try:
        c = sqlite3.connect(_DB_PATH, check_same_thread=False)
        rows = c.execute(
            "SELECT iv FROM iv_history WHERE ticker=? ORDER BY ts DESC LIMIT ?",
            (ticker, _IV_MAXLEN)
        ).fetchall()
        c.close()
        return [r[0] for r in reversed(rows)]
    except Exception as exc:
        log.warning("iv_history read %s: %s", ticker, exc)
        return []


def _append_iv_history(ticker: str, iv: float):
    """Append a new IV value and prune to _IV_MAXLEN rows."""
    try:
        c = sqlite3.connect(_DB_PATH, check_same_thread=False)
        c.execute(
            "INSERT INTO iv_history (ticker, iv, ts) VALUES (?,?,?)",
            (ticker, iv, time.time())
        )
        # Prune oldest rows beyond max length
        c.execute(
            """
            DELETE FROM iv_history WHERE ticker=? AND id NOT IN (
                SELECT id FROM iv_history WHERE ticker=? ORDER BY ts DESC LIMIT ?
            )
            """,
            (ticker, ticker, _IV_MAXLEN)
        )
        c.commit()
        c.close()
    except Exception as exc:
        log.warning("iv_history write %s: %s", ticker, exc)


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _get_atm_iv(ticker_sym: str) -> dict:
    """
    Fetch ATM implied volatility for *ticker_sym* (USO or UNG).

    Picks the nearest expiry with > 7 days remaining, finds the ATM strike,
    and returns the average of the call and put implied volatilities there.

    Returns dict with keys: iv (float|None), pctile (float), error? (str).
    """
    import yfinance as yf

    try:
        ticker = yf.Ticker(ticker_sym)
        today  = date.today()

        # ── spot price ────────────────────────────────────────────────────────
        info = ticker.fast_info
        spot = getattr(info, "last_price", None) or getattr(info, "previous_close", None)
        if not spot or spot <= 0:
            hist = ticker.history(period="2d")
            if hist.empty:
                return {"iv": None, "pctile": 0.5, "error": "no spot price"}
            spot = float(hist["Close"].iloc[-1])

        # ── pick expiry ───────────────────────────────────────────────────────
        expiries = ticker.options or []
        valid = []
        for exp_str in expiries:
            try:
                exp_date = datetime.strptime(exp_str, "%Y-%m-%d").date()
                days = (exp_date - today).days
                if days > 7:
                    valid.append((days, exp_str))
            except ValueError:
                continue

        if not valid:
            return {"iv": None, "pctile": 0.5, "error": "no expiry with >7d remaining"}

        valid.sort()
        expiry = valid[0][1]

        # ── option chain ──────────────────────────────────────────────────────
        chain = ticker.option_chain(expiry)
        calls = chain.calls.copy()
        puts  = chain.puts.copy()

        if calls.empty:
            return {"iv": None, "pctile": 0.5, "error": "empty option chain"}

        # ── ATM strike ────────────────────────────────────────────────────────
        strikes = calls["strike"].values
        atm_idx = int(np.argmin(np.abs(strikes - spot)))
        atm_k   = strikes[atm_idx]

        call_iv_arr = calls.loc[calls["strike"] == atm_k, "impliedVolatility"].values
        put_iv_arr  = puts.loc[puts["strike"]   == atm_k, "impliedVolatility"].values \
                      if not puts.empty else np.array([])

        if not len(call_iv_arr):
            return {"iv": None, "pctile": 0.5, "error": "no ATM call IV"}

        c_iv   = float(call_iv_arr[0])
        p_iv   = float(put_iv_arr[0]) if len(put_iv_arr) else c_iv
        atm_iv = (c_iv + p_iv) / 2.0

        if atm_iv <= 0 or np.isnan(atm_iv):
            return {"iv": None, "pctile": 0.5, "error": "invalid IV value"}

        # ── percentile rank (SQLite-backed, survives restart) ─────────────────
        _append_iv_history(ticker_sym, atm_iv)
        hist_arr = _get_iv_history(ticker_sym)
        pctile   = float(sum(x <= atm_iv for x in hist_arr)) / max(1, len(hist_arr))
        n_obs    = len(hist_arr)

        return {
            "iv":      round(atm_iv, 4),
            "pctile":  round(pctile, 4),
            "n_obs":   n_obs,
            "reliable": n_obs >= 10,  # flag: need ≥10 obs for meaningful percentile
        }

    except Exception as exc:
        log.warning("IV fetch failed for %s: %s", ticker_sym, exc)
        return {"iv": None, "pctile": 0.5, "error": str(exc)[:140]}


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────────

def get_iv() -> dict:
    """
    Fetch ATM implied volatility for USO (crude proxy) and UNG (HH proxy).

    Returns
    -------
    dict:
        crude_iv, crude_iv_pctile, crude_iv_reliable,
        hh_iv, hh_iv_pctile, hh_iv_reliable,
        signal, stale, timestamp
    """
    crude = _get_atm_iv("USO")
    hh    = _get_atm_iv("UNG")

    crude_iv     = crude.get("iv")
    crude_pctile = crude.get("pctile", 0.5)
    hh_iv        = hh.get("iv")
    hh_pctile    = hh.get("pctile", 0.5)

    stale  = crude_iv is None and hh_iv is None
    result = {
        "crude_iv":          crude_iv,
        "crude_iv_pctile":   crude_pctile,
        "crude_iv_reliable": crude.get("reliable", False),
        "crude_iv_n_obs":    crude.get("n_obs", 0),
        "hh_iv":             hh_iv,
        "hh_iv_pctile":      hh_pctile,
        "hh_iv_reliable":    hh.get("reliable", False),
        "hh_iv_n_obs":       hh.get("n_obs", 0),
        "signal":            -0.5 if crude_pctile > 0.80 else +0.3 if crude_pctile < 0.20 else 0.0,
        "stale":             stale,
        "timestamp":         datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    if stale:
        result["error"] = crude.get("error") or hh.get("error") or "no options data"
    return result


if __name__ == "__main__":
    import json
    print(json.dumps(get_iv(), indent=2))
