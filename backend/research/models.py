"""
Train + persist per-(spread, regime) regression models.

Per cell we compete SEVEN candidate models and pick the winner empirically:

    Ridge        — shrinks all coefficients toward zero, keeps all features.
                   Strong with correlated commodity predictors.
    Lasso        — zeroes out non-useful features (feature selection).
                   Strong when 3-4 features dominate and the rest are noise.
    ElasticNet   — L1 + L2 blend. Best-of-both for mixed feature sets.
    Huber        — robust loss, down-weights outliers (good for regimes
                   containing COVID 2020 / Russia 2022 shocks).
    XGBoost      — gradient boosting on decision trees. Captures non-linear
                   interactions between features. Wins where linear leaves
                   alpha on the table (Phase 2.8.1).
    LightGBM     — leaf-wise gradient boosting. Faster than XGB, similar
                   capacity. Wins on the same kinds of cells.
    CatBoost     — ordered boosting + symmetric trees. More regularised
                   than XGB/LGBM; usually safest on small samples.

Selection criterion: mean R² across a 5-fold TimeSeriesSplit on the training
data (chronology-respecting CV). Ties broken by simplicity (boosters rank
last so a tied linear model always wins — Phase 2.8.1 interpretability rule):
  ElasticNet > Lasso > Ridge > Huber > XGBoost > LightGBM > CatBoost.

For cells with held-out April-May test data, we ALSO report the final
out-of-sample R² but do NOT use it for model selection (would leak the test
set into model choice).

Quantile regression (p10/p50/p90) is fit separately and persisted alongside
— it produces the confidence band, not a point-estimate competitor.

Train: data through 2026-03-31
Test:  2026-04-01 → 2026-05-31

Public API
----------
  train_all()                    → fits, saves to disk, returns report
  load_models()                  → dict keyed by (spread, regime)
  predict_one(spread, regime, x) → {point, p10, p50, p90, model_name}
"""

from __future__ import annotations

import json
import logging
import os
import sys
import warnings
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import (
    Ridge, RidgeCV, Lasso, LassoCV,
    ElasticNet, ElasticNetCV, HuberRegressor,
    QuantileRegressor,
)
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import r2_score

# Phase 2.8.1 — gradient-boosting families. Imported lazily so a missing
# install degrades gracefully (linear competition still works).
try:
    from xgboost import XGBRegressor                        # type: ignore
    _HAS_XGB = True
except Exception:                                            # pragma: no cover
    _HAS_XGB = False
try:
    from lightgbm import LGBMRegressor                       # type: ignore
    _HAS_LGBM = True
except Exception:                                            # pragma: no cover
    _HAS_LGBM = False
try:
    from catboost import CatBoostRegressor                   # type: ignore
    _HAS_CATBOOST = True
except Exception:                                            # pragma: no cover
    _HAS_CATBOOST = False

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

log = logging.getLogger("pulse.research.models")

# ── Paths ────────────────────────────────────────────────────────────────────
_RESEARCH_DIR = Path(__file__).parent.parent / "data" / "research"
_MODELS_DIR   = _RESEARCH_DIR / "models"                  # composite (Sprint 3)
_REPORT_FILE  = _RESEARCH_DIR / "backtest_report.json"    # composite (Sprint 3)

# Phase 2.5 pooled-mode artefacts live alongside composite, suffixed by mode.
_MODELS_DIR_POOLED  = _RESEARCH_DIR / "models_pooled"
_REPORT_FILE_POOLED = _RESEARCH_DIR / "backtest_report_pooled.json"

# ── Config ───────────────────────────────────────────────────────────────────
TRAIN_END  = "2026-03-31"
TEST_START = "2026-04-01"
TEST_END   = "2026-05-31"
MIN_SAMPLES = 30
CV_SPLITS   = 5

# Simplicity tiebreak — lower number wins when R² scores tie within 0.005.
# Boosters sit at the bottom so linear models win ties (Phase 2.8.1
# interpretability rule: prefer coefficients over trees when both fit).
_TIEBREAK_RANK = {
    "ElasticNet": 0,
    "Lasso":      1,
    "Ridge":      2,
    "Huber":      3,
    "XGBoost":    4,
    "LightGBM":   5,
    "CatBoost":   6,
}

# Phase 2.8.1 — booster hyperparameters tuned for small-sample regimes
# (≥30 rows, up to ~2,000). Shallow trees + high regularisation + modest
# tree counts so they don't simply memorise the training fold AND don't
# blow up walk-forward refit time (10 refits × ~100 cells × 7 models × 6
# CV+full fits each).
_BOOSTER_RNG       = 42
_BOOSTER_TREES     = 150        # ↓ from 400 — shallow boosters converge fast
_BOOSTER_LR        = 0.05

_XGB_KWARGS = dict(
    n_estimators=_BOOSTER_TREES, learning_rate=_BOOSTER_LR, max_depth=3,
    subsample=0.85, colsample_bytree=0.85,
    reg_lambda=1.0, reg_alpha=0.1,
    objective="reg:squarederror",
    tree_method="hist", random_state=_BOOSTER_RNG, n_jobs=1,
    verbosity=0,
)
_LGBM_KWARGS = dict(
    n_estimators=_BOOSTER_TREES, learning_rate=_BOOSTER_LR, num_leaves=15,
    max_depth=4, min_child_samples=10,
    subsample=0.85, colsample_bytree=0.85,
    reg_lambda=1.0, reg_alpha=0.1,
    random_state=_BOOSTER_RNG, n_jobs=1, verbosity=-1,
)
_CATBOOST_KWARGS = dict(
    iterations=_BOOSTER_TREES, learning_rate=_BOOSTER_LR, depth=4,
    l2_leaf_reg=3.0, subsample=0.85,
    bootstrap_type="Bernoulli",
    random_seed=_BOOSTER_RNG, allow_writing_files=False, verbose=False,
    thread_count=1,
)

# Cells smaller than this skip the booster fits entirely — small samples
# can't reliably distinguish booster from linear via CV and the booster
# fits dominate walk-forward refit time.
_BOOSTER_MIN_ROWS = 80


def _safe(name: str) -> str:
    """Composite regime labels contain '/' — replace for filesystem safety."""
    return name.replace("/", "-")


# ── Regime mode plumbing (Phase 2.5) ─────────────────────────────────────────
# "composite" — 3-axis 27-cell grid (Sprint 3 default)
# "pooled"    — curve-axis only 3-cell grid (Phase 2.5: ~5x more rows/cell)
_VALID_MODES = ("composite", "pooled")


def _mode_paths(regime_mode: str) -> tuple[Path, Path]:
    """Return (models_dir, report_file) for the requested regime mode."""
    if regime_mode == "pooled":
        return _MODELS_DIR_POOLED, _REPORT_FILE_POOLED
    if regime_mode == "composite":
        return _MODELS_DIR, _REPORT_FILE
    raise ValueError(f"regime_mode must be one of {_VALID_MODES}, got {regime_mode!r}")


def _regime_column(regime_mode: str) -> str:
    """Feature-matrix column to use as the cell key for this mode."""
    return "regime_pooled" if regime_mode == "pooled" else "regime"


def _regimes_for(regime_mode: str) -> list[str]:
    from research.regimes import REGIMES, REGIMES_POOLED
    return list(REGIMES_POOLED) if regime_mode == "pooled" else list(REGIMES)


# ── Candidate fitters ────────────────────────────────────────────────────────

def _fit_ridge(X: np.ndarray, y: np.ndarray) -> Pipeline:
    alphas = (0.05, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 25.0)
    cv = TimeSeriesSplit(n_splits=min(CV_SPLITS, max(2, len(y) // 25)))
    pipe = Pipeline([
        ("scaler", StandardScaler()),
        ("model",  RidgeCV(alphas=alphas, cv=cv)),
    ])
    pipe.fit(X, y)
    return pipe


def _fit_lasso(X: np.ndarray, y: np.ndarray) -> Pipeline:
    cv = TimeSeriesSplit(n_splits=min(CV_SPLITS, max(2, len(y) // 25)))
    pipe = Pipeline([
        ("scaler", StandardScaler()),
        ("model",  LassoCV(alphas=None, cv=cv, max_iter=10000, n_jobs=1)),
    ])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        pipe.fit(X, y)
    return pipe


def _fit_elastic(X: np.ndarray, y: np.ndarray) -> Pipeline:
    cv = TimeSeriesSplit(n_splits=min(CV_SPLITS, max(2, len(y) // 25)))
    pipe = Pipeline([
        ("scaler", StandardScaler()),
        ("model",  ElasticNetCV(
            l1_ratio=[0.1, 0.3, 0.5, 0.7, 0.9],   # mixing parameter grid
            alphas=None, cv=cv, max_iter=10000, n_jobs=1,
        )),
    ])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        pipe.fit(X, y)
    return pipe


def _fit_huber(X: np.ndarray, y: np.ndarray) -> Pipeline:
    pipe = Pipeline([
        ("scaler", StandardScaler()),
        ("model",  HuberRegressor(max_iter=400, alpha=0.001)),
    ])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        pipe.fit(X, y)
    return pipe


# ── Phase 2.8.1 booster fitters ──────────────────────────────────────────────
# Trees don't need feature scaling, but we keep the StandardScaler in the
# pipeline so the upstream `_extract_coefs` / `_active_features` helpers can
# inspect named_steps["model"] consistently with the linear candidates.

def _fit_xgb(X: np.ndarray, y: np.ndarray) -> Pipeline:
    pipe = Pipeline([
        ("scaler", StandardScaler()),
        ("model",  XGBRegressor(**_XGB_KWARGS)),
    ])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        pipe.fit(X, y)
    return pipe


def _fit_lgbm(X: np.ndarray, y: np.ndarray) -> Pipeline:
    pipe = Pipeline([
        ("scaler", StandardScaler()),
        ("model",  LGBMRegressor(**_LGBM_KWARGS)),
    ])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        pipe.fit(X, y)
    return pipe


def _fit_catboost(X: np.ndarray, y: np.ndarray) -> Pipeline:
    pipe = Pipeline([
        ("scaler", StandardScaler()),
        ("model",  CatBoostRegressor(**_CATBOOST_KWARGS)),
    ])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        pipe.fit(X, y)
    return pipe


def _fit_quantile(X: np.ndarray, y: np.ndarray, q: float, alpha: float = 0.1) -> Pipeline:
    pipe = Pipeline([
        ("scaler", StandardScaler()),
        ("model",  QuantileRegressor(quantile=q, alpha=alpha, solver="highs")),
    ])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        pipe.fit(X, y)
    return pipe


# ── Cross-validation R² (chronology-respecting) ──────────────────────────────

def _cv_r2(fit_fn, X: np.ndarray, y: np.ndarray, n_splits: int = CV_SPLITS) -> float:
    """
    Time-series cross-validated mean R². Each fold trains on the past,
    predicts on the future — no leakage. Returns -inf if any fold fails.
    """
    n_splits = min(n_splits, max(2, len(y) // 25))
    tscv = TimeSeriesSplit(n_splits=n_splits)
    scores: list[float] = []
    for train_idx, val_idx in tscv.split(X):
        if len(train_idx) < 10 or len(val_idx) < 3:
            continue
        try:
            pipe = fit_fn(X[train_idx], y[train_idx])
            pred = pipe.predict(X[val_idx])
            scores.append(r2_score(y[val_idx], pred))
        except Exception:
            return float("-inf")
    if not scores:
        return float("-inf")
    return float(np.mean(scores))


# ── Helpers ──────────────────────────────────────────────────────────────────

def _r2(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Manual R² (also valid when y_true is constant — returns 0)."""
    ss_res = float(((y_true - y_pred) ** 2).sum())
    ss_tot = float(((y_true - y_true.mean()) ** 2).sum())
    if ss_tot <= 0:
        return 0.0
    return round(1.0 - ss_res / ss_tot, 4)


def _extract_coefs(pipe: Pipeline, feat_cols: list[str]) -> list[dict]:
    """
    Pull (feature, coef) pairs from a fitted pipeline, scaled-space.
    For tree models (boosters), use feature_importances_ as a 'coef' proxy
    so the driver list stays informative even when the winner isn't linear.
    """
    model = pipe.named_steps.get("model")
    if model is None:
        return []
    if hasattr(model, "coef_"):
        coefs = list(zip(feat_cols, model.coef_.tolist()))
        coefs.sort(key=lambda kv: abs(kv[1]), reverse=True)
        return [{"feature": f, "coef": round(c, 4)} for f, c in coefs]
    if hasattr(model, "feature_importances_"):
        imps = list(zip(feat_cols, [float(v) for v in model.feature_importances_]))
        imps.sort(key=lambda kv: abs(kv[1]), reverse=True)
        return [{"feature": f, "coef": round(c, 4)} for f, c in imps]
    return []


def _active_features(pipe: Pipeline, feat_cols: list[str], tol: float = 1e-6) -> int:
    """
    Count of features the model actually relies on.
    Linear: non-zero coefficients. Trees: features with importance > tol.
    """
    model = pipe.named_steps.get("model")
    if model is None:
        return len(feat_cols)
    if hasattr(model, "coef_"):
        return int(np.sum(np.abs(model.coef_) > tol))
    if hasattr(model, "feature_importances_"):
        return int(np.sum(np.asarray(model.feature_importances_) > tol))
    return len(feat_cols)


def _candidate_alpha(pipe: Pipeline) -> float | None:
    """Pull the chosen α (regularization) from CV-tuned linear models."""
    m = pipe.named_steps.get("model")
    return float(getattr(m, "alpha_", None)) if m and hasattr(m, "alpha_") else None


# ── Main: train all cells, select winner per cell ────────────────────────────

def train_all(regime_mode: str = "composite") -> dict:
    """
    Per (spread, regime):
      1. Run all 4 candidates with time-series CV on TRAIN data
      2. Pick winner by mean CV R² (sparsity tiebreak)
      3. Fit winner on full TRAIN; persist
      4. Also fit Quantile p10/p50/p90; persist
      5. If held-out test exists, report final OOS R² (informational only)

    regime_mode = "composite" (Sprint 3, 27 cells/spread) or
                  "pooled"    (Phase 2.5, 3 cells/spread on curve axis only).
    Each mode persists models + report to its own paths so both can coexist.
    """
    from research.features        import build_features, predictors_for
    from research.spread_universe import build_spread_series, INSTRUMENTS, LABELS

    if regime_mode not in _VALID_MODES:
        raise ValueError(f"regime_mode must be one of {_VALID_MODES}, got {regime_mode!r}")
    models_dir, report_file = _mode_paths(regime_mode)
    regime_col = _regime_column(regime_mode)
    regime_list = _regimes_for(regime_mode)

    models_dir.mkdir(parents=True, exist_ok=True)

    features = build_features()
    spreads  = build_spread_series()
    joined   = features.join(spreads, how="inner")

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
        "regime_mode": regime_mode,
        "train_end":   TRAIN_END,
        "test_start":  TEST_START,
        "test_end":    TEST_END,
        "n_train":     int(len(train)),
        "n_test":      int(len(test)),
        "method":      "Per-cell: Ridge / Lasso / ElasticNet / Huber / XGBoost / LightGBM / CatBoost competed via 5-fold TimeSeriesSplit CV. Winner = max mean CV R² (Phase 2.8.1 tiebreak: linear preferred when CV scores tie within 0.005, then boosters by listed order). Quantile p10/p50/p90 fit separately for confidence bands.",
        "candidates":  ["Ridge", "Lasso", "ElasticNet", "Huber", "XGBoost", "LightGBM", "CatBoost"],
        "cells":       {},
    }

    linear_fitters: dict[str, callable] = {
        "Ridge":      _fit_ridge,
        "Lasso":      _fit_lasso,
        "ElasticNet": _fit_elastic,
        "Huber":      _fit_huber,
    }
    booster_fitters: dict[str, callable] = {}
    if _HAS_XGB:
        booster_fitters["XGBoost"] = _fit_xgb
    if _HAS_LGBM:
        booster_fitters["LightGBM"] = _fit_lgbm
    if _HAS_CATBOOST:
        booster_fitters["CatBoost"] = _fit_catboost

    for spread in INSTRUMENTS:
        feat_cols = predictors_for(spread)
        for regime in regime_list:
            key = f"{spread}__{regime}"
            sub_train = train[train[regime_col] == regime]
            # Drop rows where any feature OR the target is NaN.
            # WTI rows (target NaN pre-2021, features NaN pre-2021) fall out
            # for WTI cells; Brent cells keep their full history.
            sub_train = sub_train.dropna(subset=feat_cols + [spread])
            if len(sub_train) < MIN_SAMPLES:
                report["cells"][key] = {
                    "spread":   spread,
                    "regime":   regime,
                    "n_train":  int(len(sub_train)),
                    "skipped":  True,
                    "reason":   f"only {len(sub_train)} train rows (<{MIN_SAMPLES})",
                }
                continue

            X_tr = sub_train[feat_cols].values
            y_tr = sub_train[spread].values

            # ── Competition: CV R² per candidate ─────────────────────────
            # Boosters only compete when the cell has enough rows (small-n
            # cells can't reliably distinguish tree from linear via CV and
            # the booster fits dominate refit time).
            cell_fitters = dict(linear_fitters)
            if len(sub_train) >= _BOOSTER_MIN_ROWS:
                cell_fitters.update(booster_fitters)
            cv_scores: dict[str, float] = {}
            fitted: dict[str, Pipeline] = {}
            for name, fitter in cell_fitters.items():
                try:
                    cv_scores[name] = _cv_r2(fitter, X_tr, y_tr)
                    # Also fit on full training data for the persisted model
                    fitted[name] = fitter(X_tr, y_tr)
                except Exception as exc:
                    log.warning("%s on %s failed: %s", name, key, exc)
                    cv_scores[name] = float("-inf")

            # ── Pick winner — best CV R², simplicity tiebreak within 0.005
            valid = {n: s for n, s in cv_scores.items() if s > float("-inf")}
            if not valid:
                report["cells"][key] = {
                    "spread": spread, "regime": regime, "n_train": int(len(sub_train)),
                    "skipped": True, "reason": "all candidates failed CV",
                }
                continue
            best_score = max(valid.values())
            within_tie = {n: s for n, s in valid.items() if best_score - s < 0.005}
            winner = min(within_tie.keys(), key=lambda n: _TIEBREAK_RANK[n])
            best_model = fitted[winner]

            # ── Quantile regression for confidence band (separately) ─────
            q10 = _fit_quantile(X_tr, y_tr, 0.10)
            q50 = _fit_quantile(X_tr, y_tr, 0.50)
            q90 = _fit_quantile(X_tr, y_tr, 0.90)

            # ── Persist the WINNER + the three quantile models ───────────
            safe = f"{spread}__{_safe(regime)}"
            joblib.dump(best_model, models_dir / f"{safe}__point.pkl")
            joblib.dump(q10,        models_dir / f"{safe}__q10.pkl")
            joblib.dump(q50,        models_dir / f"{safe}__q50.pkl")
            joblib.dump(q90,        models_dir / f"{safe}__q90.pkl")

            # ── Held-out test R² (if any test days match this regime) ────
            sub_test = test[test[regime_col] == regime].dropna(subset=feat_cols + [spread])
            r2_oos = None
            band_hit = None
            if len(sub_test) >= 3:
                X_te = sub_test[feat_cols].values
                y_te = sub_test[spread].values
                r2_oos = _r2(y_te, best_model.predict(X_te))
                p10p = q10.predict(X_te); p90p = q90.predict(X_te)
                band_hit = float(((y_te >= p10p) & (y_te <= p90p)).mean())

            # ── Residual std on train (used live for z-scoring) ──────────
            resid_std = float(np.std(y_tr - best_model.predict(X_tr)))

            cell = {
                "spread":         spread,
                "spread_label":   LABELS[spread],
                "regime":         regime,
                "n_train":        int(len(sub_train)),
                "n_test":         int(len(sub_test)),
                "winner":         winner,
                "alpha":          _candidate_alpha(best_model),
                "active_features": _active_features(best_model, feat_cols),
                "total_features":  len(feat_cols),
                "competition":    {n: round(s, 4) if s > float("-inf") else None
                                    for n, s in cv_scores.items()},
                "ridge_r2_train": _r2(y_tr, best_model.predict(X_tr)),
                "ridge_r2_test":  r2_oos,
                "band_hit_rate":  round(band_hit, 4) if band_hit is not None else None,
                "top_drivers":    _extract_coefs(best_model, feat_cols)[:5],
                "resid_std":      round(resid_std, 4),
                "skipped":        False,
            }
            report["cells"][key] = cell

    # Save report
    report_file.parent.mkdir(parents=True, exist_ok=True)
    with open(report_file, "w") as f:
        json.dump(report, f, indent=2, default=str)
    log.info("Saved report to %s", report_file)
    return report


# ── Model loading + inference ────────────────────────────────────────────────

def load_models(regime_mode: str = "composite") -> dict:
    out = {}
    models_dir, _ = _mode_paths(regime_mode)
    if not models_dir.exists():
        return out
    from research.spread_universe import INSTRUMENTS
    for spread in INSTRUMENTS:
        for regime in _regimes_for(regime_mode):
            key = (spread, regime)
            bundle = {}
            safe = f"{spread}__{_safe(regime)}"
            for name in ("point", "q10", "q50", "q90"):
                path = models_dir / f"{safe}__{name}.pkl"
                # Legacy fallbacks: Sprint 1/2 used 4-bucket regimes + the
                # "ridge" name for the point model. (composite dir only.)
                if regime_mode == "composite" and not path.exists():
                    legacy = models_dir / f"{spread}__{regime}__{name}.pkl"
                    if legacy.exists():
                        path = legacy
                if regime_mode == "composite" and not path.exists() and name == "point":
                    legacy = models_dir / f"{spread}__{regime}__ridge.pkl"
                    if legacy.exists():
                        path = legacy
                if path.exists():
                    bundle[name] = joblib.load(path)
            if bundle:
                # Aliases for backward compat
                if "point" in bundle and "ridge" not in bundle:
                    bundle["ridge"] = bundle["point"]
                out[key] = bundle
    return out


def load_report(regime_mode: str = "composite") -> dict | None:
    _, report_file = _mode_paths(regime_mode)
    if report_file.exists():
        with open(report_file) as f:
            return json.load(f)
    return None


def predict_one(spread: str, regime: str, features_row: pd.Series,
                regime_mode: str = "composite") -> dict | None:
    from research.features import predictors_for
    feat_cols = predictors_for(spread)
    bundle = load_models(regime_mode).get((spread, regime))
    if not bundle:
        return None
    X = features_row[feat_cols].values.reshape(1, -1)
    return {
        "point": float(bundle["point"].predict(X)[0]),
        "p10":   float(bundle["q10"].predict(X)[0]),
        "p50":   float(bundle["q50"].predict(X)[0]),
        "p90":   float(bundle["q90"].predict(X)[0]),
    }


if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Train per-cell regression models.")
    parser.add_argument("--mode", choices=_VALID_MODES, default="composite",
                        help="Regime mode (composite=27 cells, pooled=3 curve-axis cells)")
    args = parser.parse_args()

    print(f"Training all cells with 7-model competition + sparsity tiebreak [mode={args.mode}]...\n")
    report = train_all(regime_mode=args.mode)
    print(f"\n=== TRAINING REPORT - winner per cell (mode={args.mode}) ===")
    print(f"Train <= {report['train_end']} ({report['n_train']} rows)")
    print(f"Test  {report['test_start']} -> {report['test_end']} ({report['n_test']} rows)")
    print(f"Method: {report['method']}\n")
    hdr = f"  {'cell':<55} {'winner':<11} {'#f':>3}  {'r2_in':>6}  {'r2_oos':>6}  {'band%':>5}"
    print(hdr); print("-" * len(hdr))
    for key, cell in report["cells"].items():
        if cell.get("skipped"):
            print(f"  {key:<55} SKIPPED ({cell.get('reason')})")
            continue
        r2_oos = cell.get('ridge_r2_test')
        band   = cell.get('band_hit_rate')
        print(f"  {key:<55} {cell['winner']:<11} "
              f"{cell['active_features']:>2}/{cell['total_features']}  "
              f"{cell['ridge_r2_train']:>6.3f}  "
              f"{(r2_oos if r2_oos is not None else 0.0):>6.3f}  "
              f"{(band*100 if band is not None else 0.0):>5.1f}")
    # Per-cell competition table
    cand_order = report.get("candidates", ["Ridge","Lasso","ElasticNet","Huber"])
    print("\n=== Per-cell CV R² competition ===")
    for key, cell in report["cells"].items():
        if cell.get("skipped"): continue
        comp = cell.get("competition", {})
        bits = [f"{n}={comp[n]:+.3f}" if comp.get(n) is not None else f"{n}=NaN" for n in cand_order]
        marker = f"  <- WINNER: {cell['winner']}"
        print(f"  {key:<55} {' '.join(bits)}{marker}")

    # Winner distribution rollup
    win_counts: dict[str, int] = {}
    for cell in report["cells"].values():
        if cell.get("skipped"): continue
        w = cell.get("winner")
        if w:
            win_counts[w] = win_counts.get(w, 0) + 1
    print("\n=== Winner distribution ===")
    for w, n in sorted(win_counts.items(), key=lambda kv: -kv[1]):
        print(f"  {w:<12} {n:>4}")
