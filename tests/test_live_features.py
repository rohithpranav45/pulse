"""
Phase 4 (2026-06-18) — live feature overlay (live_features.build_overlay).

These tests drive `build_overlay` on synthetic live snapshots (no model load,
no live feed), proving the fast-feature overlay is computed with the same
conventions the global model was TRAINED on (features.build_features):

  • brent_close / m1_m12 / m1_m12_sq / curvature from the CO legs+curve
  • *_lag1 mapped to the freshest live spread level
  • wti_brent_spread sign = wti_close - brent_close (NOT the reverse)
  • wti_m1_m12 = wti c1 - wti c6
  • calendar cols recomputed for the snapshot date
  • WTI cols omitted when no CL snapshot is supplied
  • an unavailable / empty CO snapshot yields an empty overlay (safe no-op)
"""
import math
import os
import sys

import pandas as pd
import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from research.live_features import build_overlay, describe_overlay, CARRIED_STALE_COLS  # noqa: E402


def _leg(close):
    return {"close": close}


def _co_snapshot():
    return {
        "available": True,
        "as_of": "2026-06-18 04:00:00",
        "curve": {"m1_m12": 4.65, "c1": 78.12, "c12": 73.47},
        "legs": {
            "c1": _leg(78.12), "c6": _leg(75.83), "c12": _leg(73.47),
        },
        "spreads": {
            "brent_m1_m2":   {"value": 0.20},
            "brent_m3_m6":   {"value": 1.54},
            "brent_fly_123": {"value": -0.35},
        },
    }


def _cl_snapshot():
    return {
        "available": True,
        "as_of": "2026-06-18 04:00:00",
        "curve": {"m1_m12": 5.89, "c1": 75.17, "c12": 69.28},
        "legs": {"c1": _leg(75.17), "c6": _leg(71.48), "c12": _leg(69.28)},
        "spreads": {
            "wti_m1_m2":   {"value": 0.74},
            "wti_m3_m6":   {"value": 2.22},
            "wti_fly_123": {"value": 0.01},
        },
    }


def test_brent_fast_features():
    ov = build_overlay(_co_snapshot())
    assert ov["brent_close"] == 78.12
    assert ov["m1_m12"] == 4.65
    assert ov["m1_m12_sq"] == pytest.approx(4.65 ** 2)
    # curvature = c1 - 2*c6 + c12
    assert ov["curvature"] == pytest.approx(78.12 - 2 * 75.83 + 73.47)


def test_lag_features_use_live_spread():
    ov = build_overlay(_co_snapshot())
    assert ov["m1_m2_lag1"] == 0.20
    assert ov["m3_m6_lag1"] == 1.54
    assert ov["fly_lag1"] == -0.35


def test_calendar_features_match_training_formula():
    ov = build_overlay(_co_snapshot())
    doy = pd.Timestamp("2026-06-18").dayofyear
    assert ov["sin_doy"] == pytest.approx(math.sin(2 * math.pi * doy / 365.25))
    assert ov["cos_doy"] == pytest.approx(math.cos(2 * math.pi * doy / 365.25))
    # 18th < 25th roll proxy → expiry 2026-06-25, busday_count is positive
    assert ov["days_to_expiry"] > 0


def test_wti_features_only_with_cl_snapshot():
    co_only = build_overlay(_co_snapshot())
    assert "wti_close" not in co_only
    assert "wti_brent_spread" not in co_only

    both = build_overlay(_co_snapshot(), _cl_snapshot())
    assert both["wti_close"] == 75.17
    # SIGN: features.py defines wti_brent_spread = wti_close - brent_close
    assert both["wti_brent_spread"] == pytest.approx(75.17 - 78.12)
    assert both["wti_brent_spread"] < 0  # WTI discounts Brent → negative
    # wti_m1_m12 = wti c1 - wti c6
    assert both["wti_m1_m12"] == pytest.approx(75.17 - 71.48)
    assert both["wti_m1_m2_lag1"] == 0.74
    assert both["wti_fly_lag1"] == 0.01


def test_unavailable_snapshot_is_safe_noop():
    assert build_overlay(None) == {}
    assert build_overlay({"available": False}) == {}


def test_describe_overlay_reports_old_new_and_stale():
    stale = pd.Series({
        "brent_close": 64.0, "m1_m12": 1.1, "inv_vs_5yr_pct": -3.0,
        "realised_vol_20d": 0.25,
    })
    ov = build_overlay(_co_snapshot())
    meta = describe_overlay(stale, ov)
    # brent_close should show the old (stale) and new (live) value
    rec = next(r for r in meta["overlaid"] if r["feature"] == "brent_close")
    assert rec["old"] == 64.0 and rec["new"] == 78.12
    # carried-stale list only includes slow cols present in the stale row
    assert "inv_vs_5yr_pct" in meta["carried_stale"]
    assert "realised_vol_20d" in meta["carried_stale"]
    assert set(meta["carried_stale"]).issubset(set(CARRIED_STALE_COLS))
