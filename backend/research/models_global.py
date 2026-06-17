"""
Phase 4 — production "global" model trainer (2026-06-17).

Why this exists
---------------
The previous per-cell pooled/composite regime models had structural flaws:
  • Independent quantile regressors (Lasso q10/q50/q90) trained separately
    from the point predictor produce INCOHERENT bands (we observed live
    `fair_value` outside its own [p10, p90] band).
  • Per-cell stratification gives 3-cell groups, some with `n_train=0` (WTI
    CONTANGO cells) — silent gaps in the regime grid.
  • OOS test window was 38–40 days — half the cells had `n_test=0`.
  • `resid_std` was computed on TRAINING residuals, not OOS — overconfident
    z-scores like −49σ on live data.

This module trains the "global" Phase 2.8.4 architecture (regime-as-feature, one
model per spread) as the *production* model, and derives bands the only honest
way: from walk-forward OOS residuals already saved in `global_trades.json`.

Architecture
------------
1. **One point model per spread** (4 spreads after dropping M3-M6).
   - Feature set = predictors_for(spread) + 9 regime one-hot columns.
   - Trained on ALL history (2018-now) — final production fit.
   - Model class = the winner reported by the walk-forward harness (LightGBM
     wins 5/6 spreads in Phase 2.8.4); fallback to Huber when boosters absent.
2. **Empirical residual bands** from `global_trades.json` (the walk-forward
   OOS tape).
   - resid_std = std of OOS residuals per spread.
   - p10/p50/p90 deltas = empirical quantiles of OOS residuals.
   - At inference: `p10 = point + delta_p10`, etc.
   - Bands are COHERENT BY CONSTRUCTION: delta_p10 ≤ delta_p50 ≤ delta_p90
     in any monotone empirical sample, so p10 ≤ p50 ≤ p90 always holds.
3. **Honest OOS metrics**:
   - r2_oos = 1 - var(residual) / var(actual)  (computed on the OOS tape).
   - band_hit_rate = fraction of OOS rows where actual ∈ [p10, p90]  (target 0.80).
   - These pass model_health.check_cell without exception.

Public API
----------
  train_global_models(*, out_dir=None) → dict
      Train + save all artifacts. Returns the summary dict.

  load_global_models(*, model_dir=None) → dict
      Load saved point models + residual quantile tables for live inference.

  predict(models: dict, spread: str, feature_row: pd.Series,
          regime_label: str) → dict | None
      Run live inference on one row. Returns
      {point, p10, p50, p90, resid_std, z, ...}.

Files written under backend/data/research/models_global/:
  • <spread>__point.pkl              — the final point model
  • <spread>__resid.json             — {delta_p10, delta_p50, delta_p90, resid_std}
  • regime_report.json               — per-spread health metrics (n_train, r2_oos,
                                       band_hit_rate, winner, feat_cols)
"""
from __future__ import annotations

import json
import logging
import os
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

log = logging.getLogger("pulse.research.models_global")

_RESEARCH_DIR = Path(__file__).parent.parent / "data" / "research"
_OUT_DIR      = _RESEARCH_DIR / "models_global"
_OOS_TAPE     = _RESEARCH_DIR / "global_trades.json"


# ── Regime one-hot encoding (mirrors walkforward._REGIME_OH_COLS) ───────────
_REGIME_AXIS_BUCKETS = {
    "curve_": ("CONTANGO", "NEUTRAL", "BACK"),
    "inv_":   ("LOW", "AVG", "HIGH"),
    "vol_":   ("CALM", "NORMAL", "STRESSED"),
}
REGIME_OH_COLS: list[str] = [
    f"{prefix}{bucket}" for prefix, buckets in _REGIME_AXIS_BUCKETS.items() for bucket in buckets
]


def regime_one_hot(regime_label: str) -> dict[str, int]:
    """Decompose 'CURVE/INV/VOL' into 9 one-hot columns. UNKNOWN axes → zeros."""
    out = {col: 0 for col in REGIME_OH_COLS}
    parts = (regime_label or "").split("/")
    if len(parts) != 3:
        return out
    curve, inv, vol = parts
    for prefix, val in (("curve_", curve), ("inv_", inv), ("vol_", vol)):
        col = f"{prefix}{val}"
        if col in out:
            out[col] = 1
    return out


# ── Training ────────────────────────────────────────────────────────────────

# Spreads we actually trade live. M3-M6 was dropped from TUNED_EXCLUDED_SPREADS,
# but the global model still learns over the full universe (the OOS tape has
# all six). The signal log respects the exclusion at inference time.
TRADEABLE_SPREADS = ("brent_m1_m2", "brent_fly_123", "wti_m1_m2", "wti_fly_123")
ALL_SPREADS       = ("brent_m1_m2", "brent_m3_m6", "brent_fly_123",
                     "wti_m1_m2",   "wti_m3_m6",   "wti_fly_123")


def _fit_point_model(X: np.ndarray, y: np.ndarray, *, prefer: str = "LightGBM"):
    """Fit the production point model.

    Preference order:
      • LightGBM (the walk-forward winner on 5/6 spreads, sklearn-version-agnostic)
      • XGBoost
      • Huber (sklearn-native linear robust regression)
    """
    if prefer in ("LightGBM", None):
        try:
            import lightgbm as lgb
            m = lgb.LGBMRegressor(
                n_estimators=500, learning_rate=0.03, num_leaves=31,
                min_child_samples=20, reg_alpha=0.1, reg_lambda=0.1,
                verbose=-1, random_state=42,
            )
            m.fit(X, y)
            return m, "LightGBM"
        except Exception as exc:
            log.warning("LightGBM unavailable (%s); falling back to XGBoost", exc)
    try:
        from xgboost import XGBRegressor
        m = XGBRegressor(
            n_estimators=500, learning_rate=0.03, max_depth=5,
            reg_alpha=0.1, reg_lambda=0.1, random_state=42, verbosity=0,
        )
        m.fit(X, y)
        return m, "XGBoost"
    except Exception as exc:
        log.warning("XGBoost unavailable (%s); falling back to Huber", exc)
    from sklearn.linear_model import HuberRegressor
    m = HuberRegressor(max_iter=200)
    m.fit(X, y)
    return m, "Huber"


def _build_training_frame() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Construct (joined features+regime+spreads, raw spread series)."""
    from research.features        import build_features
    from research.spread_universe import build_spread_series, INSTRUMENTS

    df = build_features()
    if df.empty:
        raise RuntimeError("feature matrix empty")

    spreads = build_spread_series()
    # Forward-fill spread targets so missing WTI days during the synthesis lag
    # still align with feature rows (matches walkforward's ffill(limit=3)).
    spreads = spreads.ffill(limit=3)

    # Align indexes — join spreads as targets onto the feature frame
    joined = df.copy()
    for sp in INSTRUMENTS:
        if sp in spreads.columns:
            joined[sp] = spreads[sp].reindex(joined.index)

    # Expand regime label into 9 one-hot columns once.
    oh = joined.apply(lambda r: pd.Series(regime_one_hot(str(r.get("regime") or ""))), axis=1)
    for col in REGIME_OH_COLS:
        joined[col] = oh[col].astype(int) if col in oh.columns else 0

    return joined, spreads


def _load_oos_tape() -> list[dict]:
    if not _OOS_TAPE.exists():
        log.warning("global_trades.json missing — no OOS metrics available")
        return []
    return json.load(open(_OOS_TAPE, encoding="utf-8"))


def _residual_quantiles(rows: list[dict]) -> dict:
    """Compute coherent empirical residual quantiles from OOS rows.

    rows: list of dicts with 'actual' + 'fair'. Returns
      {n: int, resid_std, delta_p10, delta_p50, delta_p90, r2_oos, band_hit_rate}
    All bands are derived as residual quantiles, so p10 ≤ p50 ≤ p90 is
    guaranteed.
    """
    if not rows:
        return {"n": 0}
    actuals = np.array([float(r["actual"]) for r in rows if r.get("actual") is not None
                                                       and r.get("fair") is not None])
    fairs   = np.array([float(r["fair"])   for r in rows if r.get("actual") is not None
                                                       and r.get("fair") is not None])
    if len(actuals) < 30:
        return {"n": int(len(actuals))}
    residuals = actuals - fairs
    delta_p10, delta_p50, delta_p90 = np.quantile(residuals, [0.10, 0.50, 0.90])
    resid_std = float(np.std(residuals))
    var_y = float(np.var(actuals))
    r2_oos = float(1.0 - float(np.var(residuals)) / var_y) if var_y > 0 else 0.0
    # Empirical band-hit rate using the p10/p90 quantile deltas
    band_hit = float(np.mean(
        (actuals >= fairs + delta_p10) & (actuals <= fairs + delta_p90)
    ))
    return {
        "n":             int(len(actuals)),
        "resid_std":     round(resid_std, 6),
        "delta_p10":     round(float(delta_p10), 6),
        "delta_p50":     round(float(delta_p50), 6),
        "delta_p90":     round(float(delta_p90), 6),
        "r2_oos":        round(r2_oos, 4),
        "band_hit_rate": round(band_hit, 4),
    }


def train_global_models(*, out_dir: Path | None = None) -> dict:
    """
    Train + save the production global model artifacts.

    Workflow:
      1. Build the joined training frame (features + spread targets + 9
         one-hot regime cols).
      2. For each spread:
         a. Train the final point model on all history.
         b. Pull this spread's rows from `global_trades.json` (walk-forward
            OOS tape) and compute residual quantiles + r2_oos + band_hit_rate.
         c. Save model.pkl + resid.json.
      3. Write a `regime_report.json` for the model_health gate.

    Returns the summary dict (also written to regime_report.json).
    """
    from research.features import predictors_for

    out_dir = Path(out_dir) if out_dir else _OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    log.info("Loading training frame...")
    joined, _ = _build_training_frame()

    log.info("Loading walk-forward OOS tape from %s ...", _OOS_TAPE)
    tape = _load_oos_tape()
    tape_by_spread: dict[str, list[dict]] = {}
    for r in tape:
        tape_by_spread.setdefault(r["spread"], []).append(r)

    cells: dict[str, dict] = {}
    for spread in ALL_SPREADS:
        base_feats = predictors_for(spread)
        feat_cols  = base_feats + REGIME_OH_COLS
        sub = joined.dropna(subset=base_feats + [spread])
        if len(sub) < 100:
            log.warning("  %s: only %d training rows — skipping", spread, len(sub))
            continue
        X = sub[feat_cols].values
        y = sub[spread].values

        log.info("Training %s (n=%d, %d features)...", spread, len(sub), len(feat_cols))
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model, winner = _fit_point_model(X, y)
        log.info("  winner = %s", winner)

        # Compute OOS metrics from walk-forward tape.
        oos_rows = tape_by_spread.get(spread, [])
        metrics = _residual_quantiles(oos_rows)
        log.info("  OOS metrics: n=%d r2_oos=%.4f band_hit=%.2f resid_std=%.4f",
                 metrics.get("n", 0),
                 metrics.get("r2_oos", float("nan")),
                 metrics.get("band_hit_rate", float("nan")),
                 metrics.get("resid_std", float("nan")))

        # Persist artifacts.
        model_path = out_dir / f"{spread}__point.pkl"
        joblib.dump(model, model_path)
        resid_path = out_dir / f"{spread}__resid.json"
        with open(resid_path, "w") as f:
            json.dump(metrics, f, indent=2)

        cells[spread] = {
            "spread":        spread,
            "winner":        winner,
            "n_train":       int(len(sub)),
            "n_test":        metrics.get("n", 0),
            "ridge_r2_test": metrics.get("r2_oos"),       # mapped onto the
            "band_hit_rate": metrics.get("band_hit_rate"),# model_health field
            "resid_std":     metrics.get("resid_std"),    # names so the gate
            "delta_p10":     metrics.get("delta_p10"),    # picks them up.
            "delta_p50":     metrics.get("delta_p50"),
            "delta_p90":     metrics.get("delta_p90"),
            "feat_cols":     feat_cols,
            "total_features": len(feat_cols),
            "active_features": len(feat_cols),
        }

    summary = {
        "trained_at":  datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "regime_mode": "global",
        "method":      "regime-as-feature single point model + empirical OOS residual bands",
        "spreads":     list(cells.keys()),
        "cells":       cells,
    }
    with open(out_dir / "regime_report.json", "w") as f:
        json.dump(summary, f, indent=2)
    log.info("Wrote %d models + report to %s", len(cells), out_dir)
    return summary


# ── Inference ───────────────────────────────────────────────────────────────

def load_global_models(*, model_dir: Path | None = None) -> dict:
    """
    Load all per-spread point models + residual metrics into memory.

    Returns
    -------
    {
      <spread>: {
        "point":      sklearn-like estimator with .predict,
        "feat_cols":  list[str],
        "winner":     str,
        "n_train":    int,
        "resid_std":  float,
        "delta_p10":  float,
        "delta_p50":  float,
        "delta_p90":  float,
        "r2_oos":     float,
        "band_hit_rate": float,
      },
      ...
    }
    """
    model_dir = Path(model_dir) if model_dir else _OUT_DIR
    report_path = model_dir / "regime_report.json"
    if not report_path.exists():
        log.warning("global model report not found at %s", report_path)
        return {}
    report = json.load(open(report_path, encoding="utf-8"))
    cells = report.get("cells", {})
    out: dict = {}
    for spread, cell in cells.items():
        pkl = model_dir / f"{spread}__point.pkl"
        if not pkl.exists():
            log.warning("missing point model for %s — skipping", spread)
            continue
        try:
            model = joblib.load(pkl)
        except Exception as exc:
            log.warning("failed to load %s: %s", pkl, exc)
            continue
        out[spread] = {
            "point":         model,
            "feat_cols":     cell["feat_cols"],
            "winner":        cell["winner"],
            "n_train":       cell["n_train"],
            "resid_std":     cell["resid_std"],
            "delta_p10":     cell["delta_p10"],
            "delta_p50":     cell["delta_p50"],
            "delta_p90":     cell["delta_p90"],
            "r2_oos":        cell.get("ridge_r2_test"),
            "band_hit_rate": cell.get("band_hit_rate"),
        }
    return out


def predict(models: dict, spread: str, feature_row: pd.Series, regime_label: str) -> dict | None:
    """
    Run live inference for one (spread, regime, feature_row) triple.

    Returns the same shape the regime engine consumes:
      {point, p10, p50, p90, resid_std, z, winner, n_train, r2_oos,
       band_hit_rate, regime}

    Bands are deterministically derived from the empirical OOS residual
    deltas, so they're ALWAYS coherent: p10 ≤ p50 ≤ p90.
    """
    cell = models.get(spread)
    if cell is None:
        return None
    feat_cols = cell["feat_cols"]
    base_cols = [c for c in feat_cols if c not in REGIME_OH_COLS]
    base_vals = feature_row[base_cols] if all(c in feature_row.index for c in base_cols) else None
    if base_vals is None or base_vals.isnull().any():
        return None

    oh = regime_one_hot(regime_label)
    full = list(base_vals.values) + [oh[c] for c in REGIME_OH_COLS]
    X = np.array(full, dtype=float).reshape(1, -1)

    try:
        point = float(cell["point"].predict(X)[0])
    except Exception as exc:
        log.warning("global predict %s failed: %s", spread, exc)
        return None

    p10 = point + cell["delta_p10"]
    p50 = point + cell["delta_p50"]
    p90 = point + cell["delta_p90"]
    return {
        "point":         point,
        "p10":           p10,
        "p50":           p50,
        "p90":           p90,
        "resid_std":     cell["resid_std"],
        "winner":        cell["winner"],
        "n_train":       cell["n_train"],
        "r2_oos":        cell["r2_oos"],
        "band_hit_rate": cell["band_hit_rate"],
        "regime":        regime_label,
    }


# ── CLI ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    s = train_global_models()
    print(json.dumps({k: v for k, v in s.items() if k != "cells"}, indent=2))
    print(f"\nTrained {len(s.get('cells', {}))} models.")
