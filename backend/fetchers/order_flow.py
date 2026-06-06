"""
Brent Order-Flow Imbalance per contract.
========================================
Uses the institutional daily OHLCV-with-buy/sell-volume file from /Data.
For each contract (CO1, CO2, …) computes the rolling buy/sell volume
imbalance, the latest day's pressure, and a regime label.

This is genuine order-flow microstructure data not available from any
public API — it's pure desk-feed material.

Public API
----------
  get_order_flow_imbalance(lookback_days=20) -> dict
    {
      "available": bool,
      "contracts": [
        {
          "instrument": "CO1",
          "expiry":     "CON26",
          "latest_date": "2026-05-27",
          "latest_buy":  4871,
          "latest_sell": 3113,
          "latest_imbalance": +0.36,   # (buy-sell)/(buy+sell) — bounded [-1,+1]
          "rolling_imbalance_pct": +0.21,
          "regime": "BUY_PRESSURE" | "SELL_PRESSURE" | "BALANCED",
          "rolling_buy":  pd_int,
          "rolling_sell": pd_int,
          "history_days": int,
        },
        …
      ],
      "summary":   {"net_imbalance": float, "label": str},
      "as_of":     "YYYY-MM-DD",
      "timestamp": iso str,
    }
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd

_BACKEND = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

log = logging.getLogger("pulse.order_flow")


def get_order_flow_imbalance(lookback_days: int = 20) -> dict:
    """Compute per-contract order-flow imbalance from the /Data desk feed."""
    try:
        from data_lake import get_brent_ohlcv_multi
    except Exception as exc:
        return {"available": False, "error": f"data_lake import: {exc}",
                "contracts": [], "summary": {},
                "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds")}

    df = get_brent_ohlcv_multi()
    if df is None or df.empty:
        return {"available": False, "error": "OHLCV multi-contract file missing",
                "contracts": [], "summary": {},
                "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds")}

    df = df.copy()
    # Some rows may have null volume; coerce safely
    for col in ("buyvolume", "sellvolume", "volume"):
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    cutoff   = df["timestamp"].max() - pd.Timedelta(days=lookback_days + 5)
    recent   = df[df["timestamp"] >= cutoff].copy()
    contracts_out = []

    for inst, g in recent.groupby("instrument"):
        g = g.sort_values("timestamp")
        if g.empty:
            continue
        latest = g.iloc[-1]
        # Daily imbalance for last `lookback_days`
        win = g.tail(lookback_days)
        rb  = float(win["buyvolume"].sum())
        rs  = float(win["sellvolume"].sum())
        roll_imb = (rb - rs) / (rb + rs) if (rb + rs) > 0 else 0.0

        lb = float(latest["buyvolume"])
        ls = float(latest["sellvolume"])
        lat_imb = (lb - ls) / (lb + ls) if (lb + ls) > 0 else 0.0

        if   roll_imb > 0.05: regime = "BUY_PRESSURE"
        elif roll_imb < -0.05: regime = "SELL_PRESSURE"
        else:                  regime = "BALANCED"

        contracts_out.append({
            "instrument":            inst,
            "expiry":                latest.get("expiry"),
            "latest_date":           pd.to_datetime(latest["timestamp"]).strftime("%Y-%m-%d"),
            "latest_buy":            int(lb),
            "latest_sell":           int(ls),
            "latest_imbalance":      round(lat_imb, 4),
            "rolling_imbalance_pct": round(roll_imb, 4),
            "rolling_buy":           int(rb),
            "rolling_sell":          int(rs),
            "regime":                regime,
            "history_days":          int(len(win)),
        })

    # Sort: CO1, CO2, …, CO12, then alphabetical
    def _ck(x):
        s = x["instrument"]
        try:
            return (0, int(s.replace("CO", "")))
        except Exception:
            return (1, s)
    contracts_out.sort(key=_ck)

    # Overall summary — weight front contracts more
    if contracts_out:
        weights = [1 / (i + 1) for i in range(len(contracts_out))]
        weighted_sum = sum(c["rolling_imbalance_pct"] * w for c, w in zip(contracts_out, weights))
        net_imb = weighted_sum / sum(weights)
    else:
        net_imb = 0.0

    if   net_imb >  0.05: label = "Net buy pressure — bid-side aggression"
    elif net_imb < -0.05: label = "Net sell pressure — offer-side aggression"
    else:                  label = "Balanced flow"

    return {
        "available":  True,
        "as_of":      pd.to_datetime(df["timestamp"].max()).strftime("%Y-%m-%d"),
        "contracts":  contracts_out,
        "summary":    {"net_imbalance": round(net_imb, 4), "label": label},
        "lookback_days": lookback_days,
        "source":     "Institutional desk feed (/Data multi-contract OHLCV)",
        "timestamp":  datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


if __name__ == "__main__":
    import json
    logging.basicConfig(level=logging.INFO)
    r = get_order_flow_imbalance()
    # Print just the summary + first 3 contracts for sanity
    print("available:", r.get("available"), "as_of:", r.get("as_of"))
    print("summary:", json.dumps(r.get("summary"), indent=2))
    for c in r.get("contracts", [])[:5]:
        print(json.dumps(c, indent=2))
