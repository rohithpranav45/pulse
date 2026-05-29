"""
Alert System
============
Generates trading alerts from live market data.

Schema: {id, type, severity, message, timestamp}
  id        — hash(type:YYYY-MM-DD) for daily deduplication
  type      — PRICE_SHOCK | COT_EXTREME | EIA_SURPRISE | IV_SPIKE
  severity  — "warning" | "critical"

Public API
----------
  check_alerts(prices, technicals, eia, cot, iv=None) -> dict
"""

import hashlib
import logging
import os
import sys
import time
from datetime import date, datetime, timezone

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_ROOT    = os.path.abspath(os.path.join(_BACKEND, ".."))
for _p in (_BACKEND, _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

log = logging.getLogger("pulse.alerts")

_4WK_CACHE = {"value": None, "ts": 0.0}
_4WK_TTL   = 7 * 24 * 3600  # 1 week — EIA data updates weekly


def _alert_id(kind: str) -> str:
    return hashlib.md5(f"{kind}:{date.today().isoformat()}".encode()).hexdigest()[:12]


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _four_week_avg_change() -> "float | None":
    """
    Fetch 6 weeks of EIA crude stock data and return the average weekly change
    for the 4 weeks PRIOR to the most-recent observation. Caches for 1 week.
    """
    if time.time() - _4WK_CACHE["ts"] < _4WK_TTL and _4WK_CACHE["value"] is not None:
        return _4WK_CACHE["value"]
    try:
        import requests
        from dotenv import load_dotenv
        load_dotenv()
        key = os.getenv("EIA_API_KEY")
        if not key:
            return None
        resp = requests.get(
            "https://api.eia.gov/v2/petroleum/sum/sndw/data/",
            params={
                "api_key":            key,
                "frequency":          "weekly",
                "data[0]":            "value",
                "facets[series][]":   "WCRSTUS1",
                "length":             6,
                "sort[0][column]":    "period",
                "sort[0][direction]": "desc",
            },
            timeout=15,
        )
        resp.raise_for_status()
        rows = resp.json()["response"]["data"]
        if len(rows) < 6:
            return None
        # rows[0]=latest, rows[5]=oldest; prior 4 changes use rows[1..5]
        vals = [float(r["value"]) for r in rows]
        prior_changes = [vals[i] - vals[i + 1] for i in range(1, 5)]
        avg = round(sum(prior_changes) / len(prior_changes), 1)
        _4WK_CACHE["value"] = avg
        _4WK_CACHE["ts"]    = time.time()
        return avg
    except Exception as exc:
        log.debug("4-week EIA avg fetch: %s", exc)
        return _4WK_CACHE["value"]


def check_alerts(prices, technicals, eia, cot, iv=None) -> dict:
    """
    Generate real-time trading alerts.

    Parameters
    ----------
    prices      : dict  from fetchers.prices
    technicals  : dict  from fetchers.technicals
    eia         : dict  full fundamentals dict (keys: inventory, snapshot, ...)
    cot         : dict  from fetchers.cot
    iv          : dict  from fetchers.options_iv (optional)

    Returns
    -------
    {
        "alerts":      list[dict],
        "eia_change":  float | None,   # current week crude change in Mbbl
        "eia_4wk_avg": float | None,   # 4-week prior average change in Mbbl
    }
    """
    alerts_list = []
    ts          = _ts()
    eia_change  = None
    eia_4wk_avg = None

    # ── 1. PRICE SHOCK ───────────────────────────────────────────────────────
    try:
        brent_chg = float((prices or {}).get("brent", {}).get("change_pct") or 0.0)
        brent_atr = float((technicals or {}).get("Brent", {}).get("atr_pct") or 0.0)
        if brent_atr > 0 and abs(brent_chg) > 2 * brent_atr:
            sev  = "critical" if abs(brent_chg) > 3 * brent_atr else "warning"
            dir_ = "surge" if brent_chg > 0 else "drop"
            alerts_list.append({
                "id":        _alert_id("PRICE_SHOCK"),
                "type":      "PRICE_SHOCK",
                "severity":  sev,
                "message":   f"Brent {dir_}: {brent_chg:+.1f}% session (ATR {brent_atr:.1f}%)",
                "timestamp": ts,
            })
    except Exception as exc:
        log.debug("price shock check: %s", exc)

    # ── 2. COT EXTREME ──────────────────────────────────────────────────────
    try:
        cot_pct = (cot or {}).get("crude_oil", {}).get("percentile")
        if cot_pct is not None:
            if cot_pct > 85:
                alerts_list.append({
                    "id":        _alert_id("COT_LONG"),
                    "type":      "COT_EXTREME",
                    "severity":  "warning",
                    "message":   f"COT longs at {cot_pct:.0f}th pctile — crowded, unwind risk",
                    "timestamp": ts,
                })
            elif cot_pct < 15:
                alerts_list.append({
                    "id":        _alert_id("COT_SHORT"),
                    "type":      "COT_EXTREME",
                    "severity":  "warning",
                    "message":   f"COT shorts at {cot_pct:.0f}th pctile — contrarian upside potential",
                    "timestamp": ts,
                })
    except Exception as exc:
        log.debug("COT check: %s", exc)

    # ── 3. EIA SURPRISE ─────────────────────────────────────────────────────
    try:
        snap        = (eia or {}).get("snapshot", {})
        crude_snap  = snap.get("Crude Stocks", {})
        eia_change  = crude_snap.get("change")      # Mbbl, positive=build, negative=draw
        eia_4wk_avg = _four_week_avg_change()
        if eia_change is not None and eia_4wk_avg is not None:
            surprise = eia_change - eia_4wk_avg
            if abs(surprise) > 2.0:
                direction = "draw" if surprise < 0 else "build"
                sev = "critical" if abs(surprise) > 4.0 else "warning"
                alerts_list.append({
                    "id":        _alert_id("EIA_SURPRISE"),
                    "type":      "EIA_SURPRISE",
                    "severity":  sev,
                    "message":   (
                        f"EIA crude {direction} surprise: {eia_change:+.1f}M "
                        f"vs {eia_4wk_avg:+.1f}M 4-wk avg ({surprise:+.1f}M)"
                    ),
                    "timestamp": ts,
                })
    except Exception as exc:
        log.debug("EIA surprise check: %s", exc)

    # ── 4. IV SPIKE ─────────────────────────────────────────────────────────
    try:
        iv_pct = (iv or {}).get("crude_iv_pctile")
        if iv_pct is not None and iv_pct > 0.80:
            sev = "critical" if iv_pct > 0.90 else "warning"
            alerts_list.append({
                "id":        _alert_id("IV_SPIKE"),
                "type":      "IV_SPIKE",
                "severity":  sev,
                "message":   f"Crude IV at {iv_pct:.0%} pctile — elevated fear premium",
                "timestamp": ts,
            })
    except Exception as exc:
        log.debug("IV spike check: %s", exc)

    return {
        "alerts":      alerts_list,
        "eia_change":  round(eia_change, 1)  if eia_change  is not None else None,
        "eia_4wk_avg": round(eia_4wk_avg, 1) if eia_4wk_avg is not None else None,
    }


if __name__ == "__main__":
    import json
    print(json.dumps(check_alerts({}, {}, {}, {}), indent=2))
