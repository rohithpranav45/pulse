"""
Train + persist per-(spread, regime) regression models.

For each of the 3 spreads × 4 regimes = 12 cells:
  • Ridge      (point estimate, CV-tuned α)
  • Quantile   (p10, p50, p90) → confidence bands

Train: data through 2026-03-31
Test:  2026-04-01 → 2026-05-31 (out-of-sample window mom specified)

Public API
----------
  train_all()                         → fits, saves to disk, returns report
  load_models()                       → dict of fitted models keyed by (spread, regime)
  predict_one(spread, regime, features)→ {p10, p50, p90, ridge, residual}
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge, QuantileRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

log = logging.getLogger("pulse.research.models")

# ── Paths ────────────────────────────────────────────────────────────────────
_MODELS_DIR = Path(__file__).parent.parent / "data" / "research" / "models"
_REPORT_FILE = Path(__file__).parent.parent / "data" / "research" / "backtest_report.json"

# ── Config ───────────────────────────────────────────────────────────────────
TRAIN_END  = "2026-03-31"
TEST_START = "2026-04-01"
TEST_END   = "2026-05-31"

# Minimum samples per regime to attempt a fit
MIN_SAMPLES = 30


def _fit_ridge(X: np.ndarray, y: np.ndarray, alphas=(0.1, 0.5, 1.0, 5.0, 10.0)) -> Pipeline:
    """Fit a Ridge with simple CV over α, return a sklearn Pipeline."""
    from sklearn.linear_model import RidgeCV
    pipe = Pipeline([
        ("scaler", StandardScaler()),
        ("ridge",  RidgeCV(alphas=alphas, cv=min(5, max(2, len(y) // 30)))),
    ])
    pipe.fit(X, y)
    return pipe


def _fit_quantile(X: np.ndarray, y: np.ndarray, q: float, alpha: float = 0.1) -> Pipeline:
    """Fit a quantile regressor at quantile q."""
    pipe = Pipeline([
        ("scaler", StandardScaler()),
        ("qr",     QuantileRegressor(quantile=q, alpha=alpha, solver="highs")),
    ])
    pipe.fit(X, y)
    return pipe


def _r2(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    ss_res = float(((y_true - y_pred) ** 2).sum())
    ss_tot = float(((y_true - y_true.mean()) ** 2).sum())
    if ss_tot <= 0:
        return 0.0
    return round(1.0 - ss_res / ss_tot, 4)


def train_all() -> dict:
    """
    Train all (spread, regime) pairs. Save models, return a report dict.

    Saves:
      backend/data/research/models/<spread>__<regime>__ridge.pkl
      backend/data/research/models/<spread>__<regime>__q10.pkl
      backend/data/research/models/<spread>__<regime>__q50.pkl
      backend/data/research/models/<spread>__<regime>__q90.pkl
      backend/data/research/backtest_report.json
    """
    from research.features        import build_features, predictors_for
    from research.spread_universe import build_spread_series, INSTRUMENTS, LABELS
    from research.regimes         import REGIMES

    _MODELS_DIR.mkdir(parents=True, exist_ok=True)

    features = build_features()
    spreads  = build_spread_series()

    # Align indices
    joined = features.join(spreads, how="inner")

    train_mask = joined.index <= TRAIN_END
    test_mask  = (joined.index >= TEST_START) & (joined.index <= TEST_END)
    train = joined[train_mask]
    test  = joined[test_mask]

    log.info("Train rows: %d (%s → %s)", len(train),
             train.index.min().date(), train.index.max().date())
    log.info("Test  rows: %d (%s → %s)", len(test),
             test.index.min().date() if len(test) else "—",
             test.index.max().date() if len(test) else "—")

    report = {
        "trained_at":  datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "train_end":   TRAIN_END,
        "test_start":  TEST_START,
        "test_end":    TEST_END,
        "n_train":     int(len(train)),
        "n_test":      int(len(test)),
        "cells":       {},
    }

    for spread in INSTRUMENTS:
        feat_cols = predictors_for(spread)
        for regime in REGIMES:
            key = f"{spread}__{regime}"
            sub_train = train[train["regime"] == regime]
            if len(sub_train) < MIN_SAMPLES:
                report["cells"][key] = {
                    "spread":      spread,
                    "regime":      regime,
                    "n_train":     int(len(sub_train)),
                    "skipped":     True,
                    "reason":      f"only {len(sub_train)} train rows (<{MIN_SAMPLES})",
                }
                continue

            X_tr = sub_train[feat_cols].values
            y_tr = sub_train[spread].values

            # Fit models
            ridge = _fit_ridge(X_tr, y_tr)
            q10   = _fit_quantile(X_tr, y_tr, 0.10)
            q50   = _fit_quantile(X_tr, y_tr, 0.50)
            q90   = _fit_quantile(X_tr, y_tr, 0.90)

            # Persist
            joblib.dump(ridge, _MODELS_DIR / f"{key}__ridge.pkl")
            joblib.dump(q10,   _MODELS_DIR / f"{key}__q10.pkl")
            joblib.dump(q50,   _MODELS_DIR / f"{key}__q50.pkl")
            joblib.dump(q90,   _MODELS_DIR / f"{key}__q90.pkl")

            # Compute training R²
            ridge_r2_in = _r2(y_tr, ridge.predict(X_tr))

            # Out-of-sample evaluation (only days where regime matches)
            sub_test = test[test["regime"] == regime]
            oos = None
            band_hit = None
            if len(sub_test) >= 3:
                X_te = sub_test[feat_cols].values
                y_te = sub_test[spread].values
                ridge_pred = ridge.predict(X_te)
                p10_pred   = q10.predict(X_te)
                p90_pred   = q90.predict(X_te)
                oos = _r2(y_te, ridge_pred)
                # Fraction of test points falling inside the 80% band
                in_band = ((y_te >= p10_pred) & (y_te <= p90_pred)).mean()
                band_hit = round(float(in_band), 4)

            # Extract Ridge coefficients with feature names
            coefs = dict(zip(feat_cols, ridge.named_steps["ridge"].coef_.tolist()))
            coefs_sorted = sorted(coefs.items(), key=lambda kv: abs(kv[1]), reverse=True)

            # Residual standard deviation on TRAIN — used live for z-scoring
            train_resid = y_tr - ridge.predict(X_tr)
            resid_std = float(np.std(train_resid))

            report["cells"][key] = {
                "spread":         spread,
                "spread_label":   LABELS[spread],
                "regime":         regime,
                "n_train":        int(len(sub_train)),
                "n_test":         int(len(sub_test)),
                "ridge_r2_train": ridge_r2_in,
                "ridge_r2_test":  oos,
                "band_hit_rate":  band_hit,    # frac of test in p10-p90 band
                "alpha":          float(ridge.named_steps["ridge"].alpha_),
                "top_drivers":    [
                    {"feature": f, "coef": round(c, 4)}
                    for f, c in coefs_sorted[:5]
                ],
                "resid_std":      round(resid_std, 4),
                "skipped":        False,
            }

    # Save report
    _REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_REPORT_FILE, "w") as f:
        json.dump(report, f, indent=2, default=str)
    log.info("Saved report to %s", _REPORT_FILE)
    return report


def load_models() -> dict:
    """
    Load all trained models from disk.
    Returns {(spread, regime): {"ridge": ..., "q10": ..., "q50": ..., "q90": ...}}
    """
    out = {}
    if not _MODELS_DIR.exists():
        return out
    from research.spread_universe import INSTRUMENTS
    from research.regimes         import REGIMES
    for spread in INSTRUMENTS:
        for regime in REGIMES:
            key = (spread, regime)
            bundle = {}
            for name in ("ridge", "q10", "q50", "q90"):
                path = _MODELS_DIR / f"{spread}__{regime}__{name}.pkl"
                if path.exists():
                    bundle[name] = joblib.load(path)
            if bundle:
                out[key] = bundle
    return out


def load_report() -> dict | None:
    if _REPORT_FILE.exists():
        with open(_REPORT_FILE) as f:
            return json.load(f)
    return None


def predict_one(spread: str, regime: str, features_row: pd.Series) -> dict | None:
    """
    Predict the fair value of a spread given today's features under the
    given regime. Returns None if no model exists for that cell.
    """
    from research.features import predictors_for
    feat_cols = predictors_for(spread)
    bundle = load_models().get((spread, regime))
    if not bundle:
        return None
    X = features_row[feat_cols].values.reshape(1, -1)
    return {
        "ridge": float(bundle["ridge"].predict(X)[0]),
        "p10":   float(bundle["q10"].predict(X)[0]),
        "p50":   float(bundle["q50"].predict(X)[0]),
        "p90":   float(bundle["q90"].predict(X)[0]),
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    print("Training all (spread, regime) models...\n")
    report = train_all()
    print(f"\n=== TRAINING REPORT ===")
    print(f"Train: {report['train_end']} ({report['n_train']} rows)")
    print(f"Test:  {report['test_start']} → {report['test_end']} ({report['n_test']} rows)")
    print()
    print(f"{'cell':<55}  {'n_train':>7}  {'r2_in':>6}  {'r2_oos':>6}  {'band%':>5}")
    print("-" * 95)
    for key, cell in report["cells"].items():
        if cell.get("skipped"):
            print(f"  {key:<53}  {cell['n_train']:>7}  {'—':>6}  {'—':>6}  {'—':>5}   SKIPPED")
        else:
            r2_oos = cell.get('ridge_r2_test')
            band   = cell.get('band_hit_rate')
            print(f"  {key:<53}  {cell['n_train']:>7}  "
                  f"{cell['ridge_r2_train']:>6.3f}  "
                  f"{(r2_oos if r2_oos is not None else 0.0):>6.3f}  "
                  f"{(band*100 if band is not None else 0.0):>5.1f}")
