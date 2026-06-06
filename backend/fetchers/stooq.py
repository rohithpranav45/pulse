"""
Stooq — free intraday quotes, no auth. Used as a fallback for yfinance.
======================================================================
Stooq publishes per-symbol CSV at predictable URLs. No registration. Often
more reliable than Yahoo for energy futures during US off-hours.

Symbols we care about:
  cl.f   — WTI crude oil futures
  bz.f   — Brent crude oil futures (ICE)
  ng.f   — Henry Hub natural gas
  ho.f   — Heating oil
  rb.f   — RBOB gasoline

CSV columns: Date,Time,Open,High,Low,Close,Volume

Public API
----------
  get_stooq_quote(symbol) -> dict | None
  get_stooq_quotes(symbols=[...]) -> dict
"""

from __future__ import annotations

import csv
import io
import logging
from datetime import datetime, timezone

import requests

log = logging.getLogger("pulse.stooq")

BASE = "https://stooq.com/q/d/l/?s={sym}&i=d"   # daily CSV (most reliable, near-realtime close)


def get_stooq_quote(symbol: str) -> dict | None:
    """Return latest close from Stooq for `symbol` (e.g. 'cl.f')."""
    try:
        r = requests.get(BASE.format(sym=symbol), timeout=12)
        if r.status_code != 200 or not r.text:
            return None
        lines = r.text.strip().splitlines()
        if len(lines) < 2:
            return None
        reader = csv.DictReader(lines)
        rows = list(reader)
        if not rows:
            return None
        last = rows[-1]
        prev = rows[-2] if len(rows) >= 2 else None
        close = float(last["Close"])
        prev_close = float(prev["Close"]) if prev else close
        return {
            "symbol":      symbol,
            "price":       round(close, 4),
            "change_abs":  round(close - prev_close, 4),
            "change_pct":  round((close - prev_close) / prev_close * 100, 4) if prev_close else 0.0,
            "high":        round(float(last["High"]), 4),
            "low":         round(float(last["Low"]), 4),
            "volume":      int(float(last.get("Volume", 0) or 0)),
            "date":        last.get("Date"),
            "source":      "stooq.com (free daily CSV)",
        }
    except Exception as exc:
        log.warning("Stooq %s failed: %s", symbol, exc)
        return None


_STOOQ_MAP = {
    "brent":       "bz.f",
    "wti":         "cl.f",
    "henry_hub":   "ng.f",
    "heating_oil": "ho.f",
    "gasoline":    "rb.f",
}


def get_stooq_quotes(keys=None) -> dict:
    """Bulk-fetch the standard PULSE keys (brent/wti/henry_hub/…)."""
    keys = keys or list(_STOOQ_MAP.keys())
    out = {}
    for k in keys:
        sym = _STOOQ_MAP.get(k)
        if not sym:
            continue
        q = get_stooq_quote(sym)
        if q:
            out[k] = q
    out["timestamp"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    out["source"]    = "stooq.com"
    return out


if __name__ == "__main__":
    import json
    logging.basicConfig(level=logging.INFO)
    print(json.dumps(get_stooq_quotes(), indent=2))
