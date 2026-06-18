"""
Live regime classification + opportunity ranker (Sprint 3).

Given today's market data:
  1. Classify today into the COMPOSITE 3-axis regime (curve / inv / vol).
  2. For each of the 6 spreads, look up the per-(spread, regime) winner
     model + quantile bands.
  3. Predict fair, p10, p50, p90; compute deviation + z-score from train resid std.
  4. Rank by composite confidence score.
  5. Return the #1 opportunity + the full ranked list + receipts.

Public API
----------
  get_recommendation()   → dict (top-1 + ranked, all 6 spreads)
  get_current_regime()   → dict (composite label + axis drivers + thresholds)
  get_backtest_report()  → dict (the saved training report)
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

log = logging.getLogger("pulse.research.ranker")


def _active_mode() -> str:
    """
    Resolve the regime mode for live inference.

    Phase 4 (2026-06-17): production default is now "global" — the regime-as-
    feature single-coherent-model architecture with empirical OOS residual bands
    (see models_global.py). The previous per-cell pooled/composite models had
    structural flaws documented in model_health.py.

    Set PULSE_REGIME_MODE=pooled to fall back to the legacy 3-cell pooled
    engine (composite is also supported). Phase 2.6: `PULSE_GATED_BLEND=1`
    forces pooled because the gated rule is defined on pooled labels.
    """
    if _gated_blend_enabled():
        return "pooled"
    mode = (os.environ.get("PULSE_REGIME_MODE") or "global").strip().lower()
    if mode not in ("composite", "pooled", "global"):
        mode = "global"
    return mode


# ─────────────────────────────────────────────────────────────────────────────
# Phase 2.6 — gated blend (production rule)
# ─────────────────────────────────────────────────────────────────────────────
# Mirrors backend.research.walkforward._pooled_passes_gate so the rule
# evaluated in walk-forward is bit-for-bit the rule served live.
GATED_REGIME      = "BACK"
# Phase 2.8.3 — mirrors walkforward.GATED_WINNERS (kept in lockstep per
# gotcha 26). Widened from {Lasso, Huber} to include the 3 Phase 2.8.1
# boosters whose pooled BACK-cell Sharpe beats the linear gate-eligible
# winners under the Phase 2.8.2 22-feature universe.
GATED_WINNERS     = {"Lasso", "Huber", "XGBoost", "LightGBM", "CatBoost"}
GATED_Z_THRESHOLD = 0.5
ROLLING_WIN       = 252  # baseline z-score window

# ─── Phase 2.9.1 tuned exit rule (chosen by exit_tuning.py constrained sweep) ──
# The 288-config sweep on the gated tape maximised realised TP/SL win rate
# (64.2% → 82.9%) SUBJECT TO NET profit-factor > 1 and NET Sharpe ≥ the prior
# default — and the winner improves every metric (NET PF 1.26→1.99, NET Sharpe
# 0.211→0.475). live_ranker computes target/stop from these; paper_trading
# mirrors TUNED_MAX_HOLD_DAYS as a live time-stop (NEW INVARIANT — keep the two
# in sync; assert parity in test_invariants.py in Phase 3.0). The entry trigger
# is UNCHANGED at |z| ≥ GATED_Z_THRESHOLD (0.5), so the gate stays bit-for-bit
# identical to walk-forward (gotcha 26) — no gate-sync needed.
TUNED_TP_FRAC          = 0.5    # take-profit halfway from entry to fair value (p50 / rolling mean)
TUNED_SL_MULT          = 2.5    # stop at entry ± 2.5 × sigma (resid_std / rolling std); was 1.5
TUNED_MAX_HOLD_DAYS    = 30     # time-stop in trading days (enforced live by paper_trading.mark_to_market)
TUNED_EXCLUDED_SPREADS = {"brent_m3_m6", "wti_m3_m6"}  # PF<1 under TP/SL — dropped from the tradeable universe

# Phase 2.7 — sizing on the regime leg of the gated blend. Mirrors
# backend.research.walkforward.SIZING_*.
SIZING_MODES         = ("full", "half", "kelly")
SIZING_KELLY_FLOOR   = 0.10
SIZING_KELLY_CAP     = 1.00
SIZING_KELLY_DEFAULT = 0.50
_WF_REPORT           = Path(__file__).parent.parent / "data" / "research" / "walkforward_report.json"


def _gated_blend_enabled() -> bool:
    """Read PULSE_GATED_BLEND env var. Accepts 1/true/yes (case-insensitive)."""
    raw = (os.environ.get("PULSE_GATED_BLEND") or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _gated_size_mode() -> str:
    """
    Read PULSE_GATED_SIZE env var (Phase 2.7). Accepts full|half|kelly,
    defaults to full (Phase 2.6 behaviour — no sizing). Invalid values
    fall back to full and log a warning once per process.
    """
    raw = (os.environ.get("PULSE_GATED_SIZE") or "full").strip().lower()
    if raw not in SIZING_MODES:
        log.warning("PULSE_GATED_SIZE=%r is not one of %s; defaulting to 'full'", raw, SIZING_MODES)
        return "full"
    return raw


def _kelly_lookup_from_report() -> dict[str, float]:
    """
    Read the per-spread Kelly fractions saved by walkforward.run_walkforward.

    The walk-forward stores `sized_blend_summary.kelly_per_spread_latest`
    keyed by spread — these are the fractions computed at the last refit
    boundary, which is what live inference should apply going forward.
    Returns an empty dict if the report is absent / malformed; the caller
    falls back to SIZING_KELLY_DEFAULT.
    """
    try:
        if not _WF_REPORT.exists():
            return {}
        with open(_WF_REPORT) as f:
            r = json.load(f)
        latest = (r.get("sized_blend_summary") or {}).get("kelly_per_spread_latest") or {}
        return {sp: float(v) for sp, v in latest.items()}
    except Exception as exc:  # pragma: no cover — disk/json errors
        log.warning("failed to read Kelly lookup from %s: %s", _WF_REPORT, exc)
        return {}


def _notional_scale(spread: str, source: str, mode: str, kelly_map: dict) -> float:
    """
    Resolve the per-trade notional scale.

    - Baseline rows always 1.0 (the gate decides who speaks; sizing scales
      only what the regime engine claims).
    - mode='full' → 1.0 everywhere.
    - mode='half' → 0.5 on regime rows.
    - mode='kelly' → per-spread Kelly fraction from the walk-forward report,
                     defaults to SIZING_KELLY_DEFAULT when absent.
    """
    if source != "regime":
        return 1.0
    if mode == "full":
        return 1.0
    if mode == "half":
        return 0.5
    if mode == "kelly":
        v = kelly_map.get(spread)
        if v is None or not np.isfinite(v):
            return SIZING_KELLY_DEFAULT
        return float(np.clip(v, SIZING_KELLY_FLOOR, SIZING_KELLY_CAP))
    return 1.0


def _pooled_passes_gate(regime_pooled: str, winner: str | None, z: float) -> bool:
    """Phase 2.6 production gate."""
    if regime_pooled != GATED_REGIME:
        return False
    if winner not in GATED_WINNERS:
        return False
    if not np.isfinite(z) or abs(z) < GATED_Z_THRESHOLD:
        return False
    return True


def _baseline_rolling_signal(series: pd.Series, n: int = ROLLING_WIN,
                             live_actual: float | None = None) -> dict | None:
    """
    Compute the regime-unaware rolling-z signal for one spread on the most
    recent observation. Returns None if insufficient history.

    Phase 3.1: pass `live_actual` to score the live spread level against the
    historical rolling mean/σ (so a gated baseline-fallback leg uses the same
    current price as the regime leg, not the stale daily settle).
    """
    s = series.dropna()
    if len(s) < n + 1:
        return None
    window = s.iloc[-n:]
    mu     = float(window.mean())
    sigma  = float(window.std(ddof=1))
    if not np.isfinite(sigma) or sigma <= 0:
        return None
    actual = float(live_actual) if (live_actual is not None and np.isfinite(live_actual)) else float(s.iloc[-1])
    z      = (actual - mu) / sigma
    if z > GATED_Z_THRESHOLD:
        direction = "SELL"
    elif z < -GATED_Z_THRESHOLD:
        direction = "BUY"
    else:
        direction = "NEUTRAL"
    # Symmetric ±1σ band as the simple-baseline analog of p10/p90.
    band_low  = mu - sigma
    band_high = mu + sigma
    return {
        "actual":    actual,
        "fair":      mu,
        "sigma":     sigma,
        "z":         z,
        "direction": direction,
        "p10":       band_low,
        "p50":       mu,
        "p90":       band_high,
        "n_window":  int(len(window)),
    }


def get_current_regime() -> dict:
    """
    Classify today's regime and return the composite label + axis breakdown.

    Uses the most-recent row from the historical feature matrix as "today".
    For true intraday deployment we'd swap to live prints; daily settles
    are sufficient for the class demo.
    """
    from research.features import build_features
    from research.regimes  import (
        REGIME_AXES, REGIME_THRESHOLDS, regime_color,
        classify_curve, classify_inv, classify_vol,
    )

    df = build_features()
    if df.empty:
        return {"available": False, "error": "feature matrix empty"}

    latest = df.iloc[-1]
    mode = _active_mode()
    regime_col = "regime_pooled" if mode == "pooled" else "regime"
    regime = str(latest[regime_col])
    regime_legacy = str(latest.get("regime_legacy", ""))
    regime_composite = str(latest.get("regime", ""))
    regime_pooled = str(latest.get("regime_pooled", ""))

    # Per-axis labels (already in `regime`, but pull explicitly for the UI)
    curve_b = classify_curve(float(latest["m1_m12"]))
    inv_b   = classify_inv(float(latest["inv_vs_5yr_pct"])) if pd.notna(latest["inv_vs_5yr_pct"]) else "UNKNOWN"
    vol_b   = classify_vol(float(latest["realised_vol_20d"]))

    # How many consecutive days in the active regime?
    days_in_regime = 0
    for i in range(len(df) - 1, -1, -1):
        if str(df.iloc[i][regime_col]) == regime:
            days_in_regime += 1
        else:
            break

    return {
        "available":      True,
        "regime":         regime,             # active-mode label (composite or pooled)
        "regime_mode":    mode,
        "gated_blend":    _gated_blend_enabled(),
        "regime_composite": regime_composite, # always surfaced for the UI context strip
        "regime_pooled":  regime_pooled,
        "regime_legacy":  regime_legacy,
        "regime_color":   regime_color(regime),
        "size_mode":      _gated_size_mode() if _gated_blend_enabled() else None,
        "as_of":          df.index[-1].strftime("%Y-%m-%d"),
        "days_in_regime": days_in_regime,
        "axes": {
            "curve":     {"bucket": curve_b, "value": round(float(latest["m1_m12"]), 3)},
            "inventory": {"bucket": inv_b,   "value": round(float(latest["inv_vs_5yr_pct"]), 2) if pd.notna(latest["inv_vs_5yr_pct"]) else None},
            "vol":       {"bucket": vol_b,   "value": round(float(latest["realised_vol_20d"]) * 100, 2)},
        },
        "drivers": {
            "brent_close":      round(float(latest["brent_close"]), 2),
            "wti_close":        round(float(latest["wti_close"]), 2) if pd.notna(latest.get("wti_close")) else None,
            "realised_vol_20d": round(float(latest["realised_vol_20d"]), 4),
            "brent_ret_5d":     round(float(latest["brent_ret_5d"]) * 100, 2),
            "inv_vs_5yr_pct":   round(float(latest["inv_vs_5yr_pct"]), 2) if pd.notna(latest["inv_vs_5yr_pct"]) else None,
            "m1_m12":           round(float(latest["m1_m12"]), 3),
        },
        "axis_thresholds":  REGIME_THRESHOLDS,
        "axis_buckets":     REGIME_AXES,
        "timestamp":        datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def get_recommendation(*, force_mode: str | None = None, force_gated: bool | None = None,
                       live_actuals: dict | None = None,
                       live_curve_m1m12: float | None = None,
                       live_feature_overlay: dict | None = None) -> dict:
    """
    Run inference on all 6 spreads under the current regime, rank by composite
    confidence, return #1 opportunity + every spread.

    Phase 2.6: when PULSE_GATED_BLEND=1, internal mode is forced to pooled and
    each spread's signal is gated. Spreads that pass the gate keep the regime
    signal (source='regime'); spreads that fail it fall through to a 252-day
    rolling-z baseline signal (source='baseline'). The mix shows up in the
    response as `recommendation_source` per spread + a top-level summary.

    Phase 2.8.6-followup (A/B harness): pass force_mode='pooled' / force_gated=True
    to override env vars at call-time without process-wide side effects. The A/B
    harness uses this to generate both arms in one tick.

    Phase 3.1 (live engine): pass `live_actuals` (a {spread: current_value} map
    from the live intraday feed) and/or `live_curve_m1m12` (today's Brent M1-M12
    from live prices) to evaluate the framework against the CURRENT market
    instead of the latest daily settle. Both are additive and default to None —
    when omitted, behaviour is bit-for-bit the historical daily path, so the
    A/B harness + dashboard cards are unaffected. The slow regime features
    (inventory / COT / vol / macro) still come from the latest historical row;
    only the fast state (spread level + curve-axis regime) is overlaid live.

    Phase 4 (2026-06-18, live feature overlay): pass `live_feature_overlay` — a
    {feature_col: value} map of today's FAST features (brent_close, m1_m12,
    curvature, *_lag1, wti_brent_spread, calendar cols …) from
    `live_features.build_overlay` — to score the model on today's market state
    instead of the stale daily row. Without it, fair_value is predicted from the
    last daily settle (frozen 2026-05-26) while `actual` is live, which inflates
    z-scores past the |z|>8 sanity gate. Additive: default None reproduces the
    prior behaviour bit-for-bit; slow features absent from the overlay stay
    carried from the latest historical row.
    """
    from research.features        import build_features, predictors_for
    from research.spread_universe import build_spread_series, INSTRUMENTS, LABELS, DESCRIPTIONS
    from research.models          import load_models, load_report

    gated    = _gated_blend_enabled() if force_gated is None else bool(force_gated)
    size_mode = _gated_size_mode() if gated else "full"
    kelly_map = _kelly_lookup_from_report() if (gated and size_mode == "kelly") else {}
    if force_mode is not None:
        mode = force_mode if force_mode in ("composite", "pooled") else _active_mode()
        # Gated rule is defined on pooled labels — overrides any composite forcing.
        if gated:
            mode = "pooled"
    else:
        mode = _active_mode()  # honours gated → pooled
    regime_col = "regime_pooled" if mode == "pooled" else "regime"
    df       = build_features()
    spreads  = build_spread_series()

    # Phase 4 (2026-06-17) — `mode == "global"` uses the single-coherent-model
    # architecture (one point model per spread, regime fed as 9 one-hot
    # features, p10/p50/p90 derived from empirical OOS residual quantiles).
    # Loaded separately because the shape differs from the per-cell {(spread,
    # regime): bundle} dict the legacy paths consume.
    global_models: dict = {}
    if mode == "global":
        from research.models_global import load_global_models
        global_models = load_global_models()
        if not global_models:
            log.warning("global models not found on disk; falling back to pooled")
            mode = "pooled"
        else:
            # Composite regime label is still used for one-hot encoding;
            # don't need legacy per-cell models when in global mode.
            models = {}
            report = {}

    if mode != "global":
        models   = load_models(regime_mode=mode)
        report   = load_report(regime_mode=mode) or {}
        # Fall back to composite if pooled mode is requested but not yet trained.
        if mode == "pooled" and not models:
            log.warning("pooled models not found on disk; falling back to composite")
            mode = "composite"
            regime_col = "regime"
            models   = load_models(regime_mode=mode)
            report   = load_report(regime_mode=mode) or {}
            if gated:
                log.warning("PULSE_GATED_BLEND=1 but no pooled models; falling back to baseline-only for gated leg")

    if df.empty:
        return {"available": False, "error": "feature matrix empty"}

    latest_features = df.iloc[-1]
    # Phase 4 (2026-06-18) — overlay today's fast features onto the (possibly
    # stale) latest daily row so the model predicts fair value from today's
    # market state, not the last daily settle. Additive: no overlay → unchanged.
    overlaid_features: list[str] = []
    if live_feature_overlay:
        latest_features = latest_features.copy()
        for col, val in live_feature_overlay.items():
            if col in latest_features.index and val is not None and np.isfinite(val):
                latest_features[col] = float(val)
                overlaid_features.append(col)
    # Forward-fill spreads up to 3 business days so WTI cells still have a
    # "today" reading when the synth file lags Brent's latest settle by a
    # session. Mirrors the ffill(limit=3) inside build_features() so feature
    # vector and target are time-aligned for live inference.
    spreads_ffilled = spreads.ffill(limit=3) if not spreads.empty else spreads
    latest_spreads  = spreads_ffilled.iloc[-1] if not spreads_ffilled.empty else None
    regime = str(latest_features[regime_col])
    as_of  = df.index[-1].strftime("%Y-%m-%d")

    # Phase 3.1 — live overlay: recompute today's regime from the live curve.
    # The curve axis is defined on Brent M1-M12 (regimes.classify_curve), so a
    # single live curve value re-buckets the regime; inventory + vol carry from
    # the latest historical row (slow features). Pooled regime == curve bucket.
    live_overlay = (live_actuals is not None) or (live_curve_m1m12 is not None) or bool(live_feature_overlay)
    if live_curve_m1m12 is not None and np.isfinite(live_curve_m1m12):
        from research.regimes import classify_curve, classify_inv, classify_vol
        curve_b = classify_curve(float(live_curve_m1m12))
        if mode == "pooled":
            regime = curve_b
        else:
            inv_v = latest_features.get("inv_vs_5yr_pct")
            vol_v = latest_features.get("realised_vol_20d")
            inv_b = classify_inv(float(inv_v)) if pd.notna(inv_v) else "UNKNOWN"
            vol_b = classify_vol(float(vol_v)) if pd.notna(vol_v) else "UNKNOWN"
            regime = f"{curve_b}/{inv_b}/{vol_b}"

    ranked = []
    for spread in INSTRUMENTS:
        if spread in TUNED_EXCLUDED_SPREADS:
            continue  # Phase 2.9.1 — PF<1 under TP/SL; dropped from the tradeable universe
        feat_cols = predictors_for(spread)

        feat_vals = latest_features[feat_cols]
        feats_ok  = not feat_vals.isnull().any()

        # Phase 3.1 — prefer the live spread value when supplied; else daily settle.
        actual_raw = None
        if live_actuals is not None and spread in live_actuals:
            actual_raw = live_actuals.get(spread)
        if actual_raw is None and latest_spreads is not None:
            actual_raw = latest_spreads.get(spread)
        if actual_raw is None or (isinstance(actual_raw, float) and not np.isfinite(actual_raw)):
            continue
        actual = float(actual_raw)

        # ── 1. Compute regime candidate
        regime_candidate: dict | None = None

        # Phase 4 — global model path (production default).
        if mode == "global" and feats_ok and spread in global_models:
            from research.models_global import predict as _global_predict
            pred = _global_predict(global_models, spread, latest_features, regime)
            if pred is not None:
                point_pred = pred["point"]
                p10 = pred["p10"]; p50 = pred["p50"]; p90 = pred["p90"]
                resid_std = pred["resid_std"] or 1.0
                winner    = pred["winner"]
                n_train   = pred["n_train"]
                r2_oos    = pred["r2_oos"]
                r2_in     = 0.0   # not surfaced for global
                band_hit  = pred["band_hit_rate"]
                active_features = total_features = len(global_models[spread]["feat_cols"])
                competition = {}

                deviation = actual - point_pred
                z_score   = deviation / resid_std if resid_std > 0 else 0.0
                inside_band = (p10 <= actual <= p90)
                confidence = (
                    min(abs(z_score), 3.0) / 3.0
                    * min(max(r2_oos or 0.0, 0.0), 1.0)
                    * min((n_train / 100.0) ** 0.5, 1.0)
                )

                # Model-health gate (bands are coherent by construction; this
                # still catches extrapolating fair_value vs the trailing 252d).
                from research.model_health import check_cell
                sp_series = spreads[spread].dropna()
                rolling   = sp_series.tail(252) if len(sp_series) > 1 else sp_series
                roll_mean = float(rolling.mean()) if len(rolling) else None
                roll_std  = float(rolling.std())  if len(rolling) > 1 else None
                synthetic_cell_report = {
                    "n_train":       n_train,
                    "ridge_r2_test": r2_oos,
                    "band_hit_rate": band_hit,
                }
                health = check_cell(
                    synthetic_cell_report,
                    point=point_pred, p10=p10, p50=p50, p90=p90,
                    current=actual,
                    rolling_mean=roll_mean, rolling_std=roll_std,
                )

                if z_score > GATED_Z_THRESHOLD:
                    direction = "SELL"
                    target = round(actual + TUNED_TP_FRAC * (p50 - actual), 3)
                    stop   = round(actual + TUNED_SL_MULT * resid_std, 3)
                elif z_score < -GATED_Z_THRESHOLD:
                    direction = "BUY"
                    target = round(actual + TUNED_TP_FRAC * (p50 - actual), 3)
                    stop   = round(actual - TUNED_SL_MULT * resid_std, 3)
                else:
                    direction = "NEUTRAL"; target = stop = None

                if not health["ok"]:
                    direction  = "NEUTRAL"
                    target     = stop = None
                    confidence = 0.0

                regime_candidate = {
                    "spread":          spread,
                    "label":           LABELS[spread],
                    "description":     DESCRIPTIONS[spread],
                    "direction":       direction,
                    "current":         round(actual, 3),
                    "fair_value":      round(point_pred, 3),
                    "band_low":        round(p10, 3),
                    "band_mid":        round(p50, 3),
                    "band_high":       round(p90, 3),
                    "deviation":       round(deviation, 3),
                    "z_score":         round(z_score, 3),
                    "inside_band":     bool(inside_band),
                    "target":          target,
                    "stop":            stop,
                    "confidence":      round(confidence, 4),
                    "r2_train":        r2_in,
                    "r2_oos":          r2_oos,
                    "band_hit_rate":   band_hit,
                    "n_train":         n_train,
                    "drivers":         [],
                    "winner_model":    winner,
                    "active_features": active_features,
                    "total_features":  total_features,
                    "competition":     competition,
                    "recommendation_source": "regime",
                    "regime":          regime,
                    "model_health":    health,
                }

        # ── Legacy per-cell pooled/composite candidate (skipped when in global)
        cell_key = (spread, regime)
        if regime_candidate is None and mode != "global" and feats_ok and cell_key in models:
            bundle = models[cell_key]
            X = feat_vals.values.reshape(1, -1)
            point_pred = float(bundle["point"].predict(X)[0])
            p10        = float(bundle["q10"].predict(X)[0])
            p50        = float(bundle["q50"].predict(X)[0])
            p90        = float(bundle["q90"].predict(X)[0])

            deviation = actual - point_pred
            cell_report = report.get("cells", {}).get(f"{spread}__{regime}", {})
            resid_std       = cell_report.get("resid_std", 1.0) or 1.0
            r2_oos          = cell_report.get("ridge_r2_test")
            r2_in           = cell_report.get("ridge_r2_train", 0.0) or 0.0
            band_hit        = cell_report.get("band_hit_rate")
            n_train         = cell_report.get("n_train", 0)
            winner          = cell_report.get("winner")
            active_features = cell_report.get("active_features")
            total_features  = cell_report.get("total_features")
            competition     = cell_report.get("competition", {})

            z_score = deviation / resid_std if resid_std > 0 else 0.0
            inside_band = (p10 <= actual <= p90)
            used_r2 = r2_oos if (r2_oos is not None and r2_oos > 0) else max(r2_in, 0.0)
            confidence = (
                min(abs(z_score), 3.0) / 3.0
                * min(used_r2, 1.0)
                * min((n_train / 100.0) ** 0.5, 1.0)
            )
            # ── Phase 4 — model-health gate (2026-06-17). Cells with broken
            # quantile bands, negative OOS R², miscalibrated band hit-rate, or
            # predictions that extrapolate past the trailing-252d spread range
            # are refused at the regime layer. With PULSE_GATED_BLEND=1 the
            # row falls through to the rolling-z baseline below; with gating
            # off the row is dropped entirely. The full reason list is attached
            # so the dashboard can show *why* a spread was skipped.
            from research.model_health import check_cell
            sp_series = spreads[spread].dropna()
            rolling = sp_series.tail(252) if len(sp_series) > 1 else sp_series
            roll_mean = float(rolling.mean()) if len(rolling) else None
            roll_std  = float(rolling.std())  if len(rolling) > 1 else None
            health = check_cell(
                cell_report,
                point=point_pred, p10=p10, p50=p50, p90=p90,
                current=actual,
                rolling_mean=roll_mean, rolling_std=roll_std,
            )

            if z_score > GATED_Z_THRESHOLD:
                direction = "SELL"
                target    = round(actual + TUNED_TP_FRAC * (p50 - actual), 3)  # halfway to fair
                stop      = round(actual + TUNED_SL_MULT * resid_std, 3)
            elif z_score < -GATED_Z_THRESHOLD:
                direction = "BUY"
                target    = round(actual + TUNED_TP_FRAC * (p50 - actual), 3)  # halfway to fair
                stop      = round(actual - TUNED_SL_MULT * resid_std, 3)
            else:
                direction = "NEUTRAL"
                target = stop = None

            # Refuse the regime signal when health gates fail. Confidence is
            # zeroed out so the row never tops the ranking even if a downstream
            # caller ignores the health block (defensive).
            if not health["ok"]:
                direction  = "NEUTRAL"
                target     = stop = None
                confidence = 0.0

            drivers = cell_report.get("top_drivers", [])[:3]

            regime_candidate = {
                "spread":          spread,
                "label":           LABELS[spread],
                "description":     DESCRIPTIONS[spread],
                "direction":       direction,
                "current":         round(actual, 3),
                "fair_value":      round(point_pred, 3),
                "band_low":        round(p10, 3),
                "band_mid":        round(p50, 3),
                "band_high":       round(p90, 3),
                "deviation":       round(deviation, 3),
                "z_score":         round(z_score, 3),
                "inside_band":     bool(inside_band),
                "target":          target,
                "stop":            stop,
                "confidence":      round(confidence, 4),
                "r2_train":        r2_in,
                "r2_oos":          r2_oos,
                "band_hit_rate":   band_hit,
                "n_train":         n_train,
                "drivers":         drivers,
                "winner_model":    winner,
                "active_features": active_features,
                "total_features":  total_features,
                "competition":     competition,
                "recommendation_source": "regime",
                "regime":          regime,
                "model_health":    health,
            }

        # ── 2. Compute the rolling-z baseline candidate (always, for gated mode)
        baseline_candidate: dict | None = None
        if gated:
            live_base = live_actuals.get(spread) if live_actuals is not None else None
            base = _baseline_rolling_signal(spreads[spread], live_actual=live_base)
            if base is not None:
                b_actual = base["actual"]
                if base["direction"] == "SELL":
                    b_target = round(b_actual + TUNED_TP_FRAC * (base["p50"] - b_actual), 3)  # halfway to mean
                    b_stop   = round(b_actual + TUNED_SL_MULT * base["sigma"], 3)
                elif base["direction"] == "BUY":
                    b_target = round(b_actual + TUNED_TP_FRAC * (base["p50"] - b_actual), 3)  # halfway to mean
                    b_stop   = round(b_actual - TUNED_SL_MULT * base["sigma"], 3)
                else:
                    b_target = b_stop = None
                # Confidence scaling that mirrors the regime path: |z|/3 ×
                # band-confidence ≈ 0.5 (1σ band), × sqrt window.
                b_conf = (
                    min(abs(base["z"]), 3.0) / 3.0
                    * 0.5
                    * min((base["n_window"] / 100.0) ** 0.5, 1.0)
                )
                baseline_candidate = {
                    "spread":          spread,
                    "label":           LABELS[spread],
                    "description":     DESCRIPTIONS[spread],
                    "direction":       base["direction"],
                    "current":         round(b_actual, 3),
                    "fair_value":      round(base["fair"], 3),
                    "band_low":        round(base["p10"], 3),
                    "band_mid":        round(base["p50"], 3),
                    "band_high":       round(base["p90"], 3),
                    "deviation":       round(b_actual - base["fair"], 3),
                    "z_score":         round(base["z"], 3),
                    "inside_band":     bool(base["p10"] <= b_actual <= base["p90"]),
                    "target":          b_target,
                    "stop":            b_stop,
                    "confidence":      round(b_conf, 4),
                    "r2_train":        None,
                    "r2_oos":          None,
                    "band_hit_rate":   None,
                    "n_train":         base["n_window"],
                    "drivers":         [],
                    "winner_model":    "Rolling252dZ",
                    "active_features": None,
                    "total_features":  None,
                    "competition":     {},
                    "recommendation_source": "baseline",
                    "regime":          regime,
                }

        # ── 3. Pick the winner per spread (or the only one we have)
        if gated:
            # Phase 2.6 gate: regime candidate must pass; else baseline.
            # Phase 4 addendum: regime candidate must ALSO pass model_health.
            # When a cell is broken (negative OOS R², incoherent quantiles,
            # extrapolating fair_value), the gate fails and we fall through
            # to the rolling-z baseline, which doesn't depend on the broken
            # per-cell model.
            chosen = None
            regime_health_ok = (
                regime_candidate is not None
                and (regime_candidate.get("model_health") or {}).get("ok") is not False
            )
            regime_pool_pass = regime_candidate is not None and _pooled_passes_gate(
                regime, regime_candidate.get("winner_model"), regime_candidate.get("z_score") or 0.0,
            )
            if regime_candidate is not None and regime_pool_pass and regime_health_ok:
                chosen = regime_candidate
                chosen["gate"] = "pass"
            elif baseline_candidate is not None:
                chosen = baseline_candidate
                if regime_candidate is None:
                    chosen["gate"] = "no_pooled_cell"
                elif not regime_health_ok:
                    chosen["gate"] = "health_fail"
                    chosen["regime_skipped_reasons"] = (regime_candidate.get("model_health") or {}).get("reasons")
                else:
                    chosen["gate"] = "fail"
            elif regime_candidate is not None:
                # No baseline (insufficient history) — surface the regime
                # candidate but label it clearly, since the gate is bypassed
                # only because we couldn't construct a fallback.
                chosen = regime_candidate
                chosen["gate"] = "no_baseline"
                chosen["recommendation_source"] = "regime"
            if chosen is not None:
                # Phase 2.7 — attach notional scale + sizing mode for the UI /
                # paper-trading downstream. Baseline rows always carry 1.0 so
                # the chip and push-notional logic don't need to special-case.
                src = chosen.get("recommendation_source") or "regime"
                chosen["notional_scale"] = round(_notional_scale(spread, src, size_mode, kelly_map), 4)
                chosen["sizing_mode"]    = size_mode
                ranked.append(chosen)
        else:
            # Sprint-3/Phase-2.5 behaviour: regime candidate only (composite or pooled).
            if regime_candidate is not None:
                regime_candidate["gate"] = "off"
                regime_candidate["notional_scale"] = 1.0
                regime_candidate["sizing_mode"]    = "full"
                ranked.append(regime_candidate)

    ranked.sort(key=lambda x: x["confidence"], reverse=True)
    top = ranked[0] if ranked else None

    method_blurb = (
        "Pooled curve-axis regime (CONTANGO/NEUTRAL/BACK)"
        if mode == "pooled"
        else "3-axis composite regime (curve × inventory × vol)"
    )

    # Gated-blend summary counts — what the user is actually being shown
    gated_summary = None
    if gated:
        n_regime   = sum(1 for r in ranked if r.get("recommendation_source") == "regime")
        n_baseline = sum(1 for r in ranked if r.get("recommendation_source") == "baseline")
        # Phase 2.7 — surface per-spread sizing so the UI can render the chip
        # alongside the regime/baseline badge.
        sizing_per_spread = {}
        for r in ranked:
            sp  = r.get("spread")
            src = r.get("recommendation_source") or "regime"
            sizing_per_spread[sp] = {
                "source":         src,
                "notional_scale": r.get("notional_scale", 1.0),
            }
        gated_summary = {
            "enabled":          True,
            "regime":           GATED_REGIME,
            "winners":          sorted(GATED_WINNERS),
            "z_threshold":      GATED_Z_THRESHOLD,
            "n_regime":         n_regime,
            "n_baseline":       n_baseline,
            "method":           "Pooled signal taken only when regime_pooled=='BACK' AND winner_model ∈ {Lasso, Huber} AND |z|≥0.5σ; else 252d rolling-z baseline.",
            # Phase 2.7 sizing context
            "size_mode":        size_mode,
            "kelly_map":        kelly_map if size_mode == "kelly" else None,
            "sizing_per_spread": sizing_per_spread,
        }
        size_note = ""
        if size_mode == "half":
            size_note = " sized to 0.5× notional on the regime leg"
        elif size_mode == "kelly":
            size_note = " sized per-spread Kelly on the regime leg"
        method_blurb = (
            "Phase 2.6 gated blend — pooled curve-axis engine on BACK + Lasso/Huber, "
            "else 252-day rolling-z baseline" + size_note
        )

    return {
        "available":             True,
        "regime":                regime,
        "regime_mode":           mode,
        "live":                  bool(live_overlay),  # Phase 3.1 — ran on live feed vs daily settle
        "overlaid_features":     overlaid_features,   # Phase 4 — fast features scored live
        "gated_blend":           bool(gated),
        "gated_summary":         gated_summary,
        "size_mode":             size_mode if gated else None,  # Phase 2.7
        "recommendation_source": (top.get("recommendation_source") if top else None),
        "as_of":                 as_of,
        "n_eligible":            len(ranked),
        "n_universe":            len(INSTRUMENTS) - len(TUNED_EXCLUDED_SPREADS),
        "excluded_spreads":      sorted(TUNED_EXCLUDED_SPREADS),
        # Phase 2.9.1 tuned exit rule — surfaced so the RegimePickCard shows the
        # EXIT logic (TP/SL/time-stop/dropped spreads), not just the entry signal.
        "tuned_rule": {
            "entry_z":          GATED_Z_THRESHOLD,
            "tp_frac":          TUNED_TP_FRAC,
            "sl_mult":          TUNED_SL_MULT,
            "max_hold_days":    TUNED_MAX_HOLD_DAYS,
            "excluded_spreads": sorted(TUNED_EXCLUDED_SPREADS),
            "note":             "TP halfway to fair · SL 2.5σ · 30d time-stop · M3-M6 dropped (Phase 2.9.1)",
        },
        "top":                   top,
        "ranked":                ranked,
        "method":                f"Per-(spread, regime) winner from 7-model competition (Ridge/Lasso/ElasticNet/Huber/XGBoost/LightGBM/CatBoost — Phase 2.8.1); Quantile p10/p90 bands; trained ≤ 2026-03-31; {method_blurb}.",
        "timestamp":             datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def get_backtest_report() -> dict:
    from research.models import load_report
    mode = _active_mode()
    rpt = load_report(regime_mode=mode)
    if not rpt:
        return {"available": False, "error": "no backtest report — run train_all() first"}
    rpt["available"] = True
    rpt["regime_mode"] = mode
    return rpt


if __name__ == "__main__":
    import json
    logging.basicConfig(level=logging.INFO)
    print("=== current regime ===")
    cr = get_current_regime()
    print(f"composite: {cr.get('regime')}  (days in regime: {cr.get('days_in_regime')})")
    print(f"axes: {cr.get('axes')}")
    print(f"drivers: {cr.get('drivers')}")

    print("\n=== recommendation ===")
    rec = get_recommendation()
    print(f"regime={rec.get('regime')}  eligible={rec.get('n_eligible')}/{rec.get('n_universe')}")
    if rec.get("top"):
        t = rec["top"]
        print(f"TOP: {t['label']} -- {t['direction']}")
        print(f"  current ${t['current']}  fair ${t['fair_value']}  band [{t['band_low']}, {t['band_high']}]")
        print(f"  z={t['z_score']:+.2f}  conf={t['confidence']:.3f}  R2_oos={t['r2_oos']}  winner={t['winner_model']}")
    print(f"\nAll {len(rec.get('ranked', []))} ranked:")
    for i, r in enumerate(rec.get("ranked", []), 1):
        print(f"  #{i} {r['label']:<35}  dir={r['direction']:<8}  z={r['z_score']:+.2f}  "
              f"conf={r['confidence']:.3f}  winner={r['winner_model']}")
