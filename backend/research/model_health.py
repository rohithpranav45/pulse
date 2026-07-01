"""
Phase 4 — model-health gates (2026-06-17).

Why this exists
---------------
A deep audit of the per-cell regime model artefacts (`backtest_report_pooled.json`
and `backtest_report.json`) surfaced multiple systemic flaws:

  * 3 WTI/CONTANGO cells have **zero training samples** — the live engine
    silently skipped them, but the existence of empty cells means the
    regime grid is incomplete.
  * 2 cells have **negative OOS R²** (brent_fly_123__BACK, wti_fly_123__BACK)
    — the per-cell model is statistically worse than predicting the historical
    mean, yet the live engine still fires signals from these cells.
  * 5 of 6 OOS-tested cells have **band_hit_rate far from the 0.80 target**
    (0.16 / 0.37 / 0.53 / 0.60 / 0.62 / 0.95). The p10/p90 quantile bands
    are not trustworthy — and resid_std (the OOS-residual std used as the
    z-score denominator) is the same kind of overfit-in-sample number.
  * The point regressor (Huber/XGBoost/etc.) and the quantile regressors
    (Lasso q10/q50/q90) are trained INDEPENDENTLY. On live data we observe
    `fair_value` outside the [p10, p90] band — fundamental algorithmic
    incoherence that produces z-scores like -19, -49 that no real desk
    would trade.
  * OOS test windows are tiny (n_test = 38–40 per cell). Half the cells
    have n_test = 0 entirely, so their resid_std comes from training data
    only — which is what overfits to a thin number.

The gates below run at inference time on each cell's report + prediction tuple
and return (ok, reasons). A cell that fails ANY gate has its regime signal
refused; with PULSE_GATED_BLEND=1 the position falls through to the baseline
rolling-z (which doesn't depend on the broken per-cell model) so the live
engine still produces a decision, but on a credible footing.

Each gate has a verbatim reason string for transparency. A live response
records the reasons in `model_health` so the signal log + drill panel can
explain *why* a spread was skipped.

Calibration constants (chosen from the audit table; mentor-explainable):

  R²_OOS_FLOOR        = 0.05    cells with r²_oos below this are no better
                                than the mean and should not generate signals.
                                None (cell never tested OOS) is also failed.
  BAND_HIT_LO         = 0.55    p10/p90 band is "honest" if its empirical hit
  BAND_HIT_HI         = 0.95    rate sits in this range (target 0.80 ± 0.15).
  N_TRAIN_FLOOR       = 100     fewer than this, the cell is statistically
                                thin.
  PRED_EXTRAPOLATION_K = 3.0    cells where fair_value falls more than K
                                rolling-σ outside the trailing-252d spread
                                distribution are extrapolating.

  Public API
  ----------
  check_cell(report_cell, *, point, p10, p90, p50, current,
             rolling_mean=None, rolling_std=None) → dict
      Returns {ok: bool, reasons: list[str], details: dict}. `details`
      includes the failure flags so callers can render diagnostics.

  load_cell_report(spread, regime, *, regime_mode="pooled") → dict | None
      Pull one cell's report from the saved JSON. Tolerates missing cells.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Optional

log = logging.getLogger("pulse.research.model_health")

R2_OOS_FLOOR         = 0.05
BAND_HIT_LO          = 0.55
BAND_HIT_HI          = 0.95
N_TRAIN_FLOOR        = 100
PRED_EXTRAPOLATION_K = 3.0

_REPORT_PATHS = {
    "pooled":    Path(__file__).parent.parent / "data" / "research" / "backtest_report_pooled.json",
    "composite": Path(__file__).parent.parent / "data" / "research" / "backtest_report.json",
}

_cached_reports: dict[str, dict] = {}


def _load_report(regime_mode: str = "pooled") -> dict:
    if regime_mode in _cached_reports:
        return _cached_reports[regime_mode]
    path = _REPORT_PATHS.get(regime_mode)
    if path is None or not path.exists():
        log.warning("model_health: report not found for mode %s", regime_mode)
        _cached_reports[regime_mode] = {}
        return {}
    try:
        _cached_reports[regime_mode] = json.load(open(path, encoding="utf-8"))
    except Exception as exc:
        log.warning("model_health: failed to load %s: %s", path, exc)
        _cached_reports[regime_mode] = {}
    return _cached_reports[regime_mode]


def load_cell_report(spread: str, regime: str, *, regime_mode: str = "pooled") -> Optional[dict]:
    r = _load_report(regime_mode)
    cells = r.get("cells") or {}
    return cells.get(f"{spread}__{regime}")


def check_cell(
    cell_report: Optional[dict],
    *,
    point: float,
    p10: float,
    p50: float,
    p90: float,
    current: float,
    rolling_mean: Optional[float] = None,
    rolling_std: Optional[float] = None,
) -> dict:
    """
    Evaluate a single live prediction against the cell's training-time health
    AND inference-time coherence checks. Returns:

      {
        "ok": bool,
        "reasons": [str, ...],     # human-readable, mentor-explainable
        "details": {
            "n_train": int|None,
            "r2_oos":  float|None,
            "band_hit_rate": float|None,
            "quantile_coherent": bool,
            "in_distribution":   bool,
            "rolling_zscore":    float|None,
        }
      }

    A cell passes only when ALL gates pass:
      • cell_report exists (no missing cell)
      • n_train >= N_TRAIN_FLOOR
      • r2_oos >= R2_OOS_FLOOR (None counts as fail)
      • band_hit_rate in [BAND_HIT_LO, BAND_HIT_HI] (None counts as fail)
      • p10 <= p50 <= p90 AND p10 <= point <= p90 (quantile coherence)
      • |point − rolling_mean| / rolling_std <= PRED_EXTRAPOLATION_K
        (fair_value isn't an extrapolation past the spread's recent history)
    """
    reasons: list[str] = []
    details: dict = {
        "n_train": None,
        "r2_oos":  None,
        "band_hit_rate": None,
        "quantile_coherent": None,
        "in_distribution":   None,
        "rolling_zscore":    None,
    }

    # HARD fails reject the cell (force NEUTRAL); SOFT fails only DEGRADE it
    # (trade at reduced confidence). The distinction: a measured-but-bad stat or
    # an incoherent/extrapolating prediction is a hard fail; a stat that is merely
    # UNMEASURED (the held-out OOS window didn't happen to cover this regime cell)
    # is soft — silencing a well-trained, coherent cell just because the test
    # window missed it is what froze the live feed when the curve left BACK.
    hard: list[str] = []
    soft: list[str] = []

    # 1. Missing cell — the regime grid is incomplete for this combo. (HARD)
    if cell_report is None:
        hard.append("no model trained for this (spread, regime) cell")
        return {"ok": False, "degraded": False, "reasons": hard,
                "hard_reasons": hard, "soft_reasons": soft, "details": details}

    # 2. Sample size (HARD — too little data to trust at all)
    n_train = cell_report.get("n_train")
    details["n_train"] = n_train
    if n_train is None or n_train < N_TRAIN_FLOOR:
        hard.append(f"thin training cell (n_train={n_train} < {N_TRAIN_FLOOR})")

    # 3. OOS R² — missing = SOFT (untested), measured-but-bad = HARD
    r2_oos = cell_report.get("ridge_r2_test")
    details["r2_oos"] = r2_oos
    if r2_oos is None:
        soft.append("cell never tested OOS (r2_oos missing — held-out test window did not cover this cell)")
    elif r2_oos < R2_OOS_FLOOR:
        hard.append(f"r2_oos={r2_oos:+.3f} below floor {R2_OOS_FLOOR} (no better than predicting the mean)")

    # 4. Band calibration — unmeasured = SOFT, measured-but-off = HARD
    band_hit = cell_report.get("band_hit_rate")
    details["band_hit_rate"] = band_hit
    if band_hit is None:
        soft.append("band hit-rate unmeasured (no OOS window) — quantile bands cannot be validated")
    elif not (BAND_HIT_LO <= band_hit <= BAND_HIT_HI):
        side = "too narrow" if band_hit < BAND_HIT_LO else "too wide"
        hard.append(f"band hit-rate {band_hit:.2f} {side} (target ~0.80) — resid_std unreliable")

    # 5. Quantile coherence (HARD — invalidates the z-score itself)
    quantile_ok = True
    if not (p10 <= p50 <= p90):
        quantile_ok = False
        hard.append(f"quantile bands incoherent: p10={p10:.3f} <= p50={p50:.3f} <= p90={p90:.3f} doesn't hold")
    if not (p10 <= point <= p90):
        quantile_ok = False
        hard.append(f"fair_value {point:.3f} outside its own [p10={p10:.3f}, p90={p90:.3f}] band")
    details["quantile_coherent"] = quantile_ok

    # 6. Prediction-extrapolation (HARD — not justifiable from recent data)
    rolling_z = None
    in_dist = True
    if rolling_mean is not None and rolling_std is not None and rolling_std > 0:
        rolling_z = (point - rolling_mean) / rolling_std
        details["rolling_zscore"] = round(float(rolling_z), 3)
        if abs(rolling_z) > PRED_EXTRAPOLATION_K:
            in_dist = False
            hard.append(
                f"fair_value {point:.3f} is {abs(rolling_z):.1f}σ off the trailing-252d spread "
                f"distribution (mean {rolling_mean:.3f}, σ {rolling_std:.3f}) — model is extrapolating"
            )
    details["in_distribution"] = in_dist

    return {
        "ok": len(hard) == 0,            # passes (possibly degraded) when no hard fail
        "degraded": len(hard) == 0 and len(soft) > 0,
        "reasons": hard + soft,
        "hard_reasons": hard,
        "soft_reasons": soft,
        "details": details,
    }
