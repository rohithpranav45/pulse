"""
Phase 4 (2026-06-18) — live feature overlay for the production global model.

Problem
-------
`live_ranker.get_recommendation` scores the global model on `df.iloc[-1]` — the
LATEST row of the *historical daily* feature matrix. The /Data daily settle file
froze on 2026-05-26, so that row is ~3 weeks stale. Until now only the z-score
*numerator* (`live_actuals`, the current spread level) and the regime one-hot
(`live_curve_m1m12`) were overlaid live; the feature VECTOR the model predicts
fair-value from was the entire stale row. Result: the model's fair value reflects
late-May while the live spread reflects today, and the gap blows the z-score out
to −11 / −7, tripping the |z|>8 sanity gate.

Fix
---
Overlay today's FAST, cheaply-recomputable features onto the stale row *before*
`predict()`, so the model scores on today's market state:

  brent_close, m1_m12, m1_m12_sq, curvature,
  m1_m2_lag1, m3_m6_lag1, fly_lag1,
  wti_close, wti_m1_m12, wti_brent_spread, wti_*_lag1,
  sin_doy, cos_doy, days_to_expiry

SLOW features that need an external weekly/daily source (inventory, COT, cracks,
real_rate, ovx_vix_ratio, realised_vol_20d, brent_ret_5d) are NOT overlaid — they
keep the last daily value and are reported as carried-stale, honestly. They move
slowly enough that a 3-week carry is a far smaller error than a 3-week-stale front
price, and recomputing them needs sources this desk's live feed doesn't carry
(realised_vol_20d / brent_ret_5d would need ≥5–20 days of daily closes; the
intraday recorder only spans a few days).

Semantics note — the lagged-spread features (`*_lag1`) are set to the freshest
*observed live* spread level. In training, lag1 = the previous daily close; the
live analogue is "where the spread is right now", which is the freshest point-in-
time read available intraday. That is a far better proxy for today than a 3-week-
old daily lag.

This module is pure (snapshot dicts in → overlay dict out). It does not touch
training, and the overlay is applied only on the opt-in live path (an additive
kwarg in `live_ranker.get_recommendation`), so the historical daily + A/B paths
are bit-for-bit unchanged.

Public API
----------
  build_overlay(snap_co, snap_cl=None, *, as_of=None) → dict[str, float]
      Fast-feature overlay computed from live snapshots. Only includes columns
      that could be computed from the supplied snapshots.

  CARRIED_STALE_COLS : list[str]
      Slow features deliberately NOT overlaid (documented for the meta block).
"""

from __future__ import annotations

import logging
from datetime import datetime

import numpy as np
import pandas as pd

log = logging.getLogger("pulse.research.live_features")


# Fast features we can recompute from a live intraday snapshot.
LIVE_OVERLAY_COLS: list[str] = [
    "brent_close", "m1_m12", "m1_m12_sq", "curvature",
    "m1_m2_lag1", "m3_m6_lag1", "fly_lag1",
    "wti_close", "wti_m1_m12", "wti_brent_spread",
    "wti_m1_m2_lag1", "wti_m3_m6_lag1", "wti_fly_lag1",
    "sin_doy", "cos_doy", "days_to_expiry",
]

# Slow features intentionally left carried-stale (no live source on this feed).
CARRIED_STALE_COLS: list[str] = [
    "brent_ret_5d", "realised_vol_20d",
    "inv_vs_5yr_pct", "inv_surprise", "cot_mm_pct_156w",
    "crack_321", "gasoline_crack", "real_rate", "ovx_vix_ratio",
]


def _leg_close(legs: dict | None, key: str) -> float | None:
    """Pull a finite leg close price, or None."""
    try:
        v = (legs or {}).get(key, {}).get("close")
        if v is None:
            return None
        v = float(v)
        return v if np.isfinite(v) else None
    except Exception:
        return None


def _spread_val(spreads: dict | None, key: str) -> float | None:
    try:
        v = (spreads or {}).get(key, {}).get("value")
        if v is None:
            return None
        v = float(v)
        return v if np.isfinite(v) else None
    except Exception:
        return None


def _as_timestamp(ts) -> pd.Timestamp | None:
    if ts is None:
        return None
    try:
        return pd.Timestamp(ts)
    except Exception:
        return None


def _days_to_front_expiry_one(day: pd.Timestamp) -> float:
    """Single-date trading-days-to-front-roll, mirroring
    features._days_to_front_expiry (25th-of-month roll proxy)."""
    py, pm = day.year, day.month
    if day.day < 25:
        ey, em = py, pm
    else:
        if pm == 12:
            ey, em = py + 1, 1
        else:
            ey, em = py, pm + 1
    expiry = pd.Timestamp(year=ey, month=em, day=25)
    try:
        bd = np.busday_count(day.date(), expiry.date())
    except Exception:
        bd = max(0, (expiry - day).days)
    return float(max(0, bd))


def build_overlay(snap_co: dict | None, snap_cl: dict | None = None,
                  *, as_of=None) -> dict[str, float]:
    """
    Compute the fast-feature overlay from live snapshots.

    Parameters
    ----------
    snap_co : the Brent ("CO") snapshot from live_feed.get_live_snapshot.
    snap_cl : optional WTI ("CL") snapshot — only then are WTI features overlaid.
    as_of   : optional override for the calendar date (defaults to the CO
              snapshot's as_of). Drives sin_doy / cos_doy / days_to_expiry.

    Returns
    -------
    {col: value} containing ONLY the columns we could compute from the supplied
    snapshots. Missing inputs simply omit that column (the caller keeps the stale
    daily value for anything absent).
    """
    overlay: dict[str, float] = {}
    if not snap_co or not snap_co.get("available"):
        return overlay

    legs    = snap_co.get("legs") or {}
    curve   = snap_co.get("curve") or {}
    spreads = snap_co.get("spreads") or {}

    c1  = _leg_close(legs, "c1")
    c6  = _leg_close(legs, "c6")
    c12 = _leg_close(legs, "c12")
    m1_m12 = curve.get("m1_m12")

    if c1 is not None:
        overlay["brent_close"] = c1
    if m1_m12 is not None and np.isfinite(float(m1_m12)):
        overlay["m1_m12"]    = float(m1_m12)
        overlay["m1_m12_sq"] = float(m1_m12) ** 2
    if c1 is not None and c6 is not None and c12 is not None:
        # curvature = c1 - 2*c6 + c12 (matches features.build_features)
        overlay["curvature"] = c1 - 2.0 * c6 + c12

    # Lagged spreads → freshest observed live spread level (see module docstring).
    for live_key, lag_col in (("brent_m1_m2", "m1_m2_lag1"),
                              ("brent_m3_m6", "m3_m6_lag1"),
                              ("brent_fly_123", "fly_lag1")):
        v = _spread_val(spreads, live_key)
        if v is not None:
            overlay[lag_col] = v

    # Calendar features for *today* (otherwise stale at the last daily date).
    day = _as_timestamp(as_of or snap_co.get("as_of"))
    if day is not None:
        doy = int(day.dayofyear)
        overlay["sin_doy"]        = float(np.sin(2 * np.pi * doy / 365.25))
        overlay["cos_doy"]        = float(np.cos(2 * np.pi * doy / 365.25))
        overlay["days_to_expiry"] = _days_to_front_expiry_one(day)

    # WTI features — only when a live CL snapshot is supplied + available.
    if snap_cl and snap_cl.get("available"):
        wlegs    = snap_cl.get("legs") or {}
        wspreads = snap_cl.get("spreads") or {}
        wc1 = _leg_close(wlegs, "c1")
        wc6 = _leg_close(wlegs, "c6")
        if wc1 is not None:
            overlay["wti_close"] = wc1
            if c1 is not None:
                # features.py convention: wti_brent_spread = wti_close - brent_close
                overlay["wti_brent_spread"] = wc1 - c1
        if wc1 is not None and wc6 is not None:
            # features.py: wti_m1_m12 = wti c1 - wti c6 (synth tops at c6)
            overlay["wti_m1_m12"] = wc1 - wc6
        for live_key, lag_col in (("wti_m1_m2", "wti_m1_m2_lag1"),
                                  ("wti_m3_m6", "wti_m3_m6_lag1"),
                                  ("wti_fly_123", "wti_fly_lag1")):
            v = _spread_val(wspreads, live_key)
            if v is not None:
                overlay[lag_col] = v

    return overlay


def describe_overlay(stale_row: pd.Series, overlay: dict[str, float]) -> dict:
    """
    Build an honest meta block: which columns were overlaid live (old→new) and
    which slow columns were carried stale. Consumed by live_engine for the
    `feature_overlay` response block + the signal-log rationale.
    """
    applied = []
    for col, new in overlay.items():
        old = stale_row.get(col) if col in stale_row.index else None
        applied.append({
            "feature": col,
            "old": round(float(old), 4) if old is not None and pd.notna(old) else None,
            "new": round(float(new), 4),
        })
    carried = [c for c in CARRIED_STALE_COLS if c in stale_row.index]
    return {
        "overlaid":      applied,
        "carried_stale": carried,
        "n_overlaid":    len(applied),
        "n_carried":     len(carried),
    }


if __name__ == "__main__":
    import json
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    from research.live_feed import get_live_snapshot

    co = get_live_snapshot("CO")
    cl = get_live_snapshot("CL")
    ov = build_overlay(co, cl)
    print(f"feed as_of: {co.get('as_of')}")
    print(json.dumps(ov, indent=2))
