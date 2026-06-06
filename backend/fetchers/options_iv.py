"""
Volatility fetcher — REAL implied vol (OVX) + realised vol (1-min data).
========================================================================
Replaces the old USO-options scrape, which produced a synthetic IV from a
small handful of stale Yahoo option chain ticks.

Two independent sources, surfaced together:

  IMPLIED VOL — CBOE OVX (`fetchers.ovx.get_ovx()`)
    The institutional 30-day implied-vol benchmark for crude, sourced from
    CBOE-published OVXCLS via FRED. This is what desks actually quote.

  REALISED VOL — 1-min institutional mid prices (`fetchers.realised_vol.get_realised_vol()`)
    True 30-day annualised realised vol computed from minute-bar Brent + WTI
    mids, percentile-ranked against the full 5-year history in /Data.

Output shape is backwards-compatible with the previous module so signal /
alert code doesn't need changes. `crude_iv` now carries OVX (or RV if OVX
unavailable); `crude_iv_pctile` is the corresponding percentile.
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timezone

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_ROOT    = os.path.abspath(os.path.join(_BACKEND, ".."))
for _p in (_BACKEND, _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

log = logging.getLogger("pulse.options_iv")


def get_iv() -> dict:
    """
    Return a unified vol payload combining OVX (implied) + intraday RV (realised).
    Shape stays compatible with previous consumers (crude_iv / crude_iv_pctile /
    signal / stale / timestamp).
    """
    # ── Implied vol (OVX from FRED) ─────────────────────────────────────────────
    ovx_data = None
    try:
        from fetchers.ovx import get_ovx
        ovx_data = get_ovx()
    except Exception as exc:
        log.warning("OVX fetch failed: %s", exc)

    # ── Realised vol (from /Data 1-min mids) ────────────────────────────────────
    rv_data = None
    try:
        from fetchers.realised_vol import get_realised_vol
        rv_data = get_realised_vol()
    except Exception as exc:
        log.warning("Realised vol fetch failed: %s", exc)

    # ── Decide which is the "headline" crude vol number ─────────────────────────
    # OVX is the institutional benchmark — prefer it.
    if ovx_data and ovx_data.get("current"):
        crude_iv     = ovx_data["current"] / 100.0  # OVX is in % (e.g. 59.53), normalise to decimal
        crude_pctile = ovx_data.get("pctile_5y", 0.5)
        primary_src  = "CBOE OVX (FRED)"
        primary_date = ovx_data.get("date")
        n_obs        = ovx_data.get("n_obs", 0)
        reliable     = True
    elif rv_data and rv_data.get("crude_iv"):
        crude_iv     = rv_data["crude_iv"]
        crude_pctile = rv_data.get("crude_iv_pctile", 0.5)
        primary_src  = "Realised vol (/Data 1-min)"
        primary_date = rv_data.get("history_end")
        n_obs        = rv_data.get("crude_iv_n_obs", 0)
        reliable     = rv_data.get("crude_iv_reliable", False)
    else:
        crude_iv     = None
        crude_pctile = 0.5
        primary_src  = "unavailable"
        primary_date = None
        n_obs        = 0
        reliable     = False

    # ── HH proxy (we don't have NG implied vol — use WTI realised as proxy) ─────
    hh_iv     = rv_data.get("hh_iv") if rv_data else None
    hh_pctile = rv_data.get("hh_iv_pctile", 0.5) if rv_data else 0.5

    # ── Signal logic (preserved) ────────────────────────────────────────────────
    if   crude_pctile > 0.80: signal = -0.5
    elif crude_pctile < 0.20: signal = +0.3
    else:                     signal = 0.0

    stale = crude_iv is None and hh_iv is None

    out = {
        "crude_iv":           crude_iv,
        "crude_iv_pctile":    crude_pctile,
        "crude_iv_reliable":  reliable,
        "crude_iv_n_obs":     n_obs,
        "crude_iv_source":    primary_src,
        "crude_iv_date":      primary_date,

        "hh_iv":              hh_iv,
        "hh_iv_pctile":       hh_pctile,
        "hh_iv_reliable":     rv_data.get("hh_iv_reliable", False) if rv_data else False,
        "hh_iv_n_obs":        rv_data.get("hh_iv_n_obs", 0) if rv_data else 0,
        "hh_iv_source":       "WTI realised vol (HH proxy)",

        # Full detail blocks for transparency
        "ovx":                ovx_data,
        "realised":           rv_data,

        "signal":             signal,
        "stale":              stale,
        "timestamp":          datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    if stale:
        out["error"] = "OVX and realised vol both unavailable"
    return out


if __name__ == "__main__":
    import json
    logging.basicConfig(level=logging.INFO)
    r = get_iv()
    # Trim the nested blocks for readability
    print(json.dumps({k: v for k, v in r.items() if k not in ("ovx", "realised")}, indent=2))
