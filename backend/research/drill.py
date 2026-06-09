"""
Drill-down receipts for a regime pick.

Given a spread, return the model's *evidence*:

  scatter   — every historical day in TODAY'S regime, with the spread's actual
              value and the winning model's fair-value prediction. Lets the
              mentor see "is the model usually close to the line?" and where
              today sits in the cloud.

  analogs   — the 3 closest historical days to today's feature vector
              (Euclidean distance over standardised features), each with
              its 20-day forward realised change of the spread. Answers
              "when this setup happened before, what came next?"

Public API
----------
  get_drill_data(spread: str) -> dict
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

log = logging.getLogger("pulse.research.drill")

FORWARD_DAYS = 20  # horizon for analog "what happened next"


def get_drill_data(spread: str, *, n_analogs: int = 3) -> dict:
    """
    Build scatter + analogs payload for a single spread under today's regime.

    Today = last row of build_features(). Regime = its classifier label.
    """
    from research.features        import build_features, predictors_for
    from research.spread_universe import build_spread_series, LABELS, INSTRUMENTS

    if spread not in INSTRUMENTS:
        return {"available": False, "error": f"unknown spread {spread!r}"}

    features = build_features()
    spreads  = build_spread_series()
    if features.empty or spreads.empty:
        return {"available": False, "error": "feature/spread matrix empty"}

    # Honour active regime mode (composite by default; pooled if PULSE_REGIME_MODE=pooled
    # and pooled models exist on disk).
    mode = (os.environ.get("PULSE_REGIME_MODE") or "composite").strip().lower()
    if mode not in ("composite", "pooled"):
        mode = "composite"
    regime_col = "regime_pooled" if mode == "pooled" else "regime"

    df = features.join(spreads[[spread]], how="inner").dropna(subset=[spread])
    today = df.iloc[-1]
    regime = today[regime_col]
    as_of  = df.index[-1]

    feat_cols = predictors_for(spread)
    same_regime = df[df[regime_col] == regime].copy()
    if same_regime.empty:
        return {"available": False, "error": f"no history for regime {regime}"}

    # ── Scatter: actual vs fair value across the regime's full history ──────
    try:
        from research.models import load_models
        bundle = load_models(regime_mode=mode).get((spread, regime))
        if not bundle and mode == "pooled":
            # Fall back to composite if pooled wasn't trained
            mode = "composite"
            regime_col = "regime"
            regime = today[regime_col]
            same_regime = df[df[regime_col] == regime].copy()
            bundle = load_models(regime_mode=mode).get((spread, regime))
        if not bundle or "point" not in bundle:
            return {
                "available": False,
                "error": f"no trained model for ({spread}, {regime})",
            }
        model = bundle["point"]
        X = same_regime[feat_cols].values
        fair = model.predict(X)
    except Exception as exc:
        log.warning("drill model load failed for %s/%s: %s", spread, regime, exc)
        return {"available": False, "error": f"model load failed: {exc}"}

    scatter = [
        {
            "date":   d.strftime("%Y-%m-%d"),
            "actual": round(float(a), 4),
            "fair":   round(float(f), 4),
        }
        for d, a, f in zip(same_regime.index, same_regime[spread].values, fair)
    ]

    today_actual = float(today[spread])
    today_fair   = float(model.predict(today[feat_cols].values.reshape(1, -1))[0])

    # ── Analogs: 3 nearest historical days by standardised feature distance ─
    # Standardise features over the same-regime history only — so distance is
    # measured in regime-conditional units (a 1σ move *for this regime*).
    # Restrict candidates to days with a full FORWARD_DAYS window available in
    # `df`, so every analog can report "what happened next" instead of None.
    cutoff = df.index[max(0, len(df) - 1 - FORWARD_DAYS)]
    hist = same_regime[same_regime.index < cutoff]
    if len(hist) < n_analogs + 1:
        analogs = []
    else:
        hist_X = hist[feat_cols].values.astype(float)
        today_X = today[feat_cols].values.astype(float)

        mu  = hist_X.mean(axis=0)
        std = hist_X.std(axis=0)
        std = np.where(std < 1e-9, 1.0, std)

        z_hist  = (hist_X - mu) / std
        z_today = (today_X - mu) / std
        dists = np.linalg.norm(z_hist - z_today, axis=1)

        order = np.argsort(dists)[:n_analogs]
        analogs = []
        for rank, i in enumerate(order, start=1):
            d = hist.index[i]
            # Look up the spread value FORWARD_DAYS later in the original df
            # (forward window may overrun if the analog is very recent).
            future = df.loc[df.index > d]
            if len(future) >= FORWARD_DAYS:
                future_row = future.iloc[FORWARD_DAYS - 1]
                fwd_date   = future_row.name.strftime("%Y-%m-%d")
                fwd_spread = float(future_row[spread])
                fwd_change = round(fwd_spread - float(hist[spread].iloc[i]), 4)
            else:
                fwd_date = None
                fwd_spread = None
                fwd_change = None

            # Top 3 most-influential features for this analog (by |z-distance|)
            comp = np.abs(z_hist[i] - z_today)
            top_idx = np.argsort(comp)[-3:][::-1]
            similar_features = [
                {
                    "feature":  feat_cols[j],
                    "today":    round(float(today_X[j]), 4),
                    "analog":   round(float(hist_X[i, j]), 4),
                    "z_gap":    round(float(comp[j]), 3),
                }
                for j in top_idx
            ]

            analogs.append({
                "rank":              rank,
                "date":              d.strftime("%Y-%m-%d"),
                "distance":          round(float(dists[i]), 3),
                "spread_then":       round(float(hist[spread].iloc[i]), 4),
                "forward_days":      FORWARD_DAYS,
                "forward_date":      fwd_date,
                "forward_spread":    fwd_spread,
                "forward_change":    fwd_change,
                "similar_features":  similar_features,
            })

    # Scatter regression summary — eyeball R² across the cloud
    resid = same_regime[spread].values - fair
    ss_res = float((resid ** 2).sum())
    ss_tot = float(((same_regime[spread].values - same_regime[spread].mean()) ** 2).sum())
    in_sample_r2 = round(1.0 - ss_res / ss_tot, 4) if ss_tot > 0 else 0.0

    return {
        "available":      True,
        "spread":         spread,
        "label":          LABELS[spread],
        "regime":         regime,
        "as_of":          as_of.strftime("%Y-%m-%d"),
        "today": {
            "actual":      round(today_actual, 4),
            "fair":        round(today_fair, 4),
            "deviation":   round(today_actual - today_fair, 4),
        },
        "scatter":        scatter,
        "n_points":       len(scatter),
        "in_sample_r2":   in_sample_r2,
        "analogs":        analogs,
        "feature_cols":   feat_cols,
        "timestamp":      datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


if __name__ == "__main__":
    import json
    logging.basicConfig(level=logging.INFO)
    out = get_drill_data("brent_m3_m6")
    print(f"spread={out.get('spread')} regime={out.get('regime')} n={out.get('n_points')}")
    print(f"today actual={out['today']['actual']} fair={out['today']['fair']} dev={out['today']['deviation']}")
    print(f"in-sample R² (regime cloud) = {out['in_sample_r2']}")
    print(f"\n{len(out['analogs'])} analogs:")
    for a in out["analogs"]:
        print(f"  #{a['rank']} {a['date']}  dist={a['distance']:.2f}  "
              f"spread_then={a['spread_then']}  +{a['forward_days']}d → {a['forward_spread']} ({a['forward_change']:+.2f})")
