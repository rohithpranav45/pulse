"""
Live regime classification + opportunity ranker.

Given today's market data:
  1. Classify the regime (4 buckets on M1-M12)
  2. Load the 3 trained models for this regime
  3. For each spread, predict fair value + p10-p90 band
  4. Compare to actual current spread → deviation, z-score
  5. Rank by composite confidence score
  6. Return the #1 opportunity + full receipts

Public API
----------
  get_recommendation() → dict (top-1 opportunity + all 3 ranked)
  get_current_regime() → dict (regime label + driver breakdown)
  get_backtest_report() → dict (the saved training report)
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

log = logging.getLogger("pulse.research.ranker")


def get_current_regime() -> dict:
    """
    Classify today's regime and return the label + driver breakdown.

    Uses the most-recent row from the historical feature matrix as "today".
    For true live deployment we'd use intraday data; for the class demo
    the last settled day is sufficient.
    """
    from research.features import build_features
    from research.regimes  import classify_one, regime_color

    df = build_features()
    if df.empty:
        return {"available": False, "error": "feature matrix empty"}

    latest = df.iloc[-1]
    regime = latest["regime"]
    m1_m12 = float(latest["m1_m12"])

    # How many consecutive days have we been in this regime?
    days_in_regime = 0
    for i in range(len(df) - 1, -1, -1):
        if df.iloc[i]["regime"] == regime:
            days_in_regime += 1
        else:
            break

    return {
        "available":      True,
        "regime":         regime,
        "regime_color":   regime_color(regime),
        "as_of":          df.index[-1].strftime("%Y-%m-%d"),
        "m1_m12":         round(m1_m12, 3),
        "days_in_regime": days_in_regime,
        "drivers": {
            "brent_close":      round(float(latest["brent_close"]), 2),
            "realised_vol_20d": round(float(latest["realised_vol_20d"]), 4),
            "brent_ret_5d":     round(float(latest["brent_ret_5d"]) * 100, 2),
        },
        "regime_thresholds": {
            "EXTREME_CONTANGO":      "M1-M12 ≤ -$5",
            "MILD_CONTANGO":         "-$5 < M1-M12 ≤ $0",
            "MILD_BACKWARDATION":    "$0 < M1-M12 ≤ +$10",
            "EXTREME_BACKWARDATION": "M1-M12 > +$10",
        },
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def get_recommendation() -> dict:
    """
    Run inference on all 3 spreads under the current regime, rank by
    composite confidence, return #1 opportunity + all ranked details.
    """
    from research.features        import build_features, predictors_for
    from research.spread_universe import build_spread_series, INSTRUMENTS, LABELS, DESCRIPTIONS
    from research.models          import load_models, load_report

    df       = build_features()
    spreads  = build_spread_series()
    models   = load_models()
    report   = load_report() or {}

    if df.empty:
        return {"available": False, "error": "feature matrix empty"}

    latest_features = df.iloc[-1]
    latest_spreads  = spreads.iloc[-1] if not spreads.empty else None
    regime = latest_features["regime"]
    as_of  = df.index[-1].strftime("%Y-%m-%d")

    ranked = []
    for spread in INSTRUMENTS:
        cell_key = (spread, regime)
        if cell_key not in models:
            continue
        bundle = models[cell_key]
        feat_cols = predictors_for(spread)
        X = latest_features[feat_cols].values.reshape(1, -1)

        ridge_pred = float(bundle["ridge"].predict(X)[0])
        p10        = float(bundle["q10"].predict(X)[0])
        p50        = float(bundle["q50"].predict(X)[0])
        p90        = float(bundle["q90"].predict(X)[0])

        actual = float(latest_spreads[spread]) if latest_spreads is not None else None
        if actual is None:
            continue
        deviation = actual - ridge_pred

        # Get this cell's residual std + R² from the saved report
        cell_report = report.get("cells", {}).get(f"{spread}__{regime}", {})
        resid_std    = cell_report.get("resid_std", 1.0)
        r2_oos       = cell_report.get("ridge_r2_test")
        r2_in        = cell_report.get("ridge_r2_train", 0.0)
        band_hit     = cell_report.get("band_hit_rate")
        n_train      = cell_report.get("n_train", 0)

        z_score = deviation / resid_std if resid_std > 0 else 0.0

        # Inside-band check
        inside_band = (p10 <= actual <= p90)

        # Confidence score:
        #   abs(z) penalised by max-confidence cap of 3σ
        #   × R² (OOS if available, else training)
        #   × sqrt(n / 100) up to cap of 1
        used_r2 = r2_oos if (r2_oos is not None and r2_oos > 0) else max(r2_in, 0.0)
        confidence = (
            min(abs(z_score), 3.0) / 3.0          # 0–1 from |z|
            * min(used_r2, 1.0)                   # 0–1 from R²
            * min((n_train / 100.0) ** 0.5, 1.0)  # 0–1 from sample size
        )

        # Direction: if actual > fair → spread looks RICH → SELL
        if z_score > 0.5:
            direction = "SELL"
            target    = round(p50, 3)
            stop      = round(actual + 1.5 * resid_std, 3)
        elif z_score < -0.5:
            direction = "BUY"
            target    = round(p50, 3)
            stop      = round(actual - 1.5 * resid_std, 3)
        else:
            direction = "NEUTRAL"
            target = stop = None

        # Top driver names from saved coefs
        drivers = cell_report.get("top_drivers", [])[:3]

        ranked.append({
            "spread":         spread,
            "label":          LABELS[spread],
            "description":    DESCRIPTIONS[spread],
            "direction":      direction,
            "current":        round(actual, 3),
            "fair_value":     round(ridge_pred, 3),
            "band_low":       round(p10, 3),
            "band_mid":       round(p50, 3),
            "band_high":      round(p90, 3),
            "deviation":      round(deviation, 3),
            "z_score":        round(z_score, 3),
            "inside_band":    bool(inside_band),
            "target":         target,
            "stop":           stop,
            "confidence":     round(confidence, 4),
            "r2_train":       r2_in,
            "r2_oos":         r2_oos,
            "band_hit_rate":  band_hit,
            "n_train":        n_train,
            "drivers":        drivers,
        })

    # Sort by confidence × |z_score| (favor strong, statistically-grounded signals)
    ranked.sort(key=lambda x: x["confidence"], reverse=True)

    top = ranked[0] if ranked else None

    return {
        "available":  True,
        "regime":     regime,
        "as_of":      as_of,
        "top":        top,
        "ranked":     ranked,
        "method":     "Ridge fair-value + Quantile p10/p90 band; trained on ≤ 2026-03-31",
        "timestamp":  datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def get_backtest_report() -> dict:
    """Return the saved training/backtest report from disk."""
    from research.models import load_report
    rpt = load_report()
    if not rpt:
        return {"available": False, "error": "no backtest report — run train_all() first"}
    rpt["available"] = True
    return rpt


if __name__ == "__main__":
    import json
    logging.basicConfig(level=logging.INFO)
    print("=== current regime ===")
    print(json.dumps(get_current_regime(), indent=2, default=str))
    print("\n=== recommendation ===")
    rec = get_recommendation()
    if rec.get("top"):
        t = rec["top"]
        print(f"TOP: {t['label']} — {t['direction']}")
        print(f"  current ${t['current']}  fair ${t['fair_value']}  band [{t['band_low']}, {t['band_high']}]")
        print(f"  z={t['z_score']:+.2f}  confidence={t['confidence']:.3f}  R²_oos={t['r2_oos']}")
        print(f"  target ${t['target']}  stop ${t['stop']}")
        print(f"  top drivers: {[d['feature'] for d in t['drivers']]}")
    print(f"\nAll {len(rec.get('ranked', []))} ranked:")
    for i, r in enumerate(rec.get("ranked", []), 1):
        print(f"  #{i} {r['label']:<35}  dir={r['direction']:<8}  z={r['z_score']:+.2f}  conf={r['confidence']:.3f}")
