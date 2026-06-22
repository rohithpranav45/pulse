"""
Walk-forward backtest for the Phase 2 regime engine (Sprint 4 + Phase 2.5).

Tests the *methodology* — not the cherry-picked Mar-2026 split — by sliding the
training window through 2.5 years of recent history. At each refit point we:

  1. Train all (spread, regime) cells on data ≤ refit_date using the same
     Ridge / Lasso / ElasticNet / Huber competition that production uses
     (models.train_all).
  2. Walk forward day-by-day to the next refit, generating signals.
     - regime is re-classified each day from that day's market state
     - model lookup uses the freshly-trained cell for (spread, today's regime)
     - signal: SELL if z > +0.5, BUY if z < -0.5, NEUTRAL else
     - PnL = sign(direction) × (spread[d+20] - spread[d])
  3. Stitch results across all refits → trade tape + aggregate metrics.

Two regime modes evaluated side-by-side (Phase 2.5):

  composite  — Sprint 3 default: 27 cells (curve × inventory × vol).
               High-resolution conditioning, but ~50-150 rows/cell.
  pooled     — Phase 2.5: 3 cells per spread (curve axis only — CONTANGO /
               NEUTRAL / BACK). ~5× more rows per cell; the inventory + vol
               axes still appear on the dashboard as context but don't
               fragment the training set.

Phase 2.6 — gated blend (third leg):
  gated_blend — for each (date, spread): if the pooled signal passes the
               production gate (regime_pooled=='BACK' AND winner_model ∈
               {Lasso, Huber} AND |z|≥0.5σ) AND fires a non-NEUTRAL
               direction, take it. Otherwise fall back to the regime-unaware
               252d rolling z-score baseline. This is the strategy live
               production runs under PULSE_GATED_BLEND=1 — Phase 2.5 surfaced
               the (BACK × {Lasso,Huber}) subset as the only configuration
               where regime conditioning beat baseline; Phase 2.6 verifies
               that the same gating logic survives end-to-end walk-forward.

Phase 2.7 — sized regime leg (fourth leg):
  sized_blend — the gated blend with the regime leg's notional scaled by
               a per-(spread, refit-cutoff) factor. Baseline leg always at
               1.0. Three sizing modes are simulated end-to-end:
                 full   — scale 1.0 (identical to gated_blend; sanity check)
                 half   — scale 0.5 (uniform risk reduction)
                 kelly  — per-spread Kelly fraction from prior regime-leg
                          PnLs, clamped to [0.10, 1.00], default 0.50 when
                          fewer than 5 prior trades are closed. Recomputed
                          at every refit boundary so live deployment can
                          replicate the schedule.
               Headline question: does sizing compress the −271 max-DD that
               concentration of 97 high-Sharpe regime fires costs the leg,
               without giving up the +1.332 Sharpe alpha?

Phase 2.8.4 — global model with regime-as-feature (fifth leg):
  global      — collapse the per-cell grid: train ONE model per spread on
               ALL rows ≤ cutoff, with the composite regime fed as 9 one-hot
               axis columns (curve / inv / vol — 3+3+3). Same 7-model
               competition as the per-cell harness; each spread trains on ~5×
               more rows per refit. Tests whether the per-cell *split* was
               the binding constraint vs the regime *information*. Reuses
               the existing infrastructure: one extra refit driver, one
               extra block in the report.

Baseline for comparison: a regime-UNAWARE rolling z-score on the same spreads.
At date d, fair = 252-day rolling mean, σ = 252-day rolling std, same trading
rule and horizon. This is the cleanest answer to "does regime conditioning
help?" — it holds every other moving part fixed.

Phase 1 (9-indicator directional Brent signal) is not directly comparable —
it scores Brent outright, not spreads. The methodology PDF flags this gap.

Output: backend/data/research/walkforward_report.json
        Top-level keys: composite, pooled, gated_blend, sized_blend,
        sized_blend_summary, baseline_overall, baseline_by_spread,
        lift_composite_vs_baseline, lift_pooled_vs_baseline,
        lift_gated_vs_baseline, lift_sized_half_vs_baseline,
        lift_sized_kelly_vs_baseline, lift_pooled_vs_composite,
        lift_gated_vs_pooled.

        Also writes backend/data/research/gated_trades.json — the raw
        gated-leg trade list — so future sized-blend experiments can
        post-process without retraining (the heavy lift is the per-cell
        competition; sizing is pure arithmetic).
"""

from __future__ import annotations

import json
import logging
import math
import os
import sys
import warnings
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

log = logging.getLogger("pulse.research.walkforward")

_REPORT_FILE          = Path(__file__).parent.parent / "data" / "research" / "walkforward_report.json"
_GATED_TRADES_FILE    = Path(__file__).parent.parent / "data" / "research" / "gated_trades.json"
_COMPOSITE_TRADES_FILE = Path(__file__).parent.parent / "data" / "research" / "composite_trades.json"
_POOLED_TRADES_FILE   = Path(__file__).parent.parent / "data" / "research" / "pooled_trades.json"
_BASELINE_TRADES_FILE = Path(__file__).parent.parent / "data" / "research" / "baseline_trades.json"
_GLOBAL_TRADES_FILE   = Path(__file__).parent.parent / "data" / "research" / "global_trades.json"
_POOLED_SOFT_TRADES_FILE    = Path(__file__).parent.parent / "data" / "research" / "pooled_soft_trades.json"
_COMPOSITE_SOFT_TRADES_FILE = Path(__file__).parent.parent / "data" / "research" / "composite_soft_trades.json"
# Phase 5 — multi-horizon sweep (2.8.7) + feature-selection legs.
_HORIZON_TRADES_FILE  = Path(__file__).parent.parent / "data" / "research" / "horizon_trades.json"
_FEATSEL_TRADES_FILE  = Path(__file__).parent.parent / "data" / "research" / "featsel_trades.json"
# Phase 6 — data-driven HMM/change-point regime leg (2.8.9). Headline-K tape.
_HMM_TRADES_FILE      = Path(__file__).parent.parent / "data" / "research" / "hmm_trades.json"
# Phase 7 — portfolio vol-targeting leg (2.8.10). Headline (full) variant tape.
_VOLTARGET_TRADES_FILE = Path(__file__).parent.parent / "data" / "research" / "voltarget_trades.json"
# Phase 8 — per-spread gate leg (2026-06-22). Per-spread-gated blend tape.
_PERSPREAD_GATE_TRADES_FILE = Path(__file__).parent.parent / "data" / "research" / "gated_perspread_trades.json"

# Phase 2.8.4 — regime axes used as one-hot features in the "global" leg.
# Composite label decomposes into 3 axes; the one-hot expansion is 3+3+3=9
# columns instead of the 27 you'd get from raw composite labels — same info
# content but lower cardinality, which the linear candidates handle better.
_REGIME_AXIS_BUCKETS = {
    "curve_": ("CONTANGO", "NEUTRAL", "BACK"),
    "inv_":   ("LOW", "AVG", "HIGH"),
    "vol_":   ("CALM", "NORMAL", "STRESSED"),
}
_REGIME_OH_COLS = [
    f"{prefix}{bucket}" for prefix, buckets in _REGIME_AXIS_BUCKETS.items() for bucket in buckets
]

# ── Config ───────────────────────────────────────────────────────────────────
FORWARD_DAYS = 20
MIN_SAMPLES  = 30
Z_ENTRY      = 0.5
ROLLING_WIN  = 252
REFIT_DATES  = [
    # Phase 2.8.8 — extended back to 2018 for full 2018-2026 walk-forward coverage.
    # Brent legs span the entire window (real C1-C31 settlements from 2016).
    # WTI cells (synth from 1-min mids, 2021+) auto-skip per-refit when pre-2021
    # train rows < MIN_SAMPLES — read 2018-2020 verdict as a Brent-only story.
    "2018-01-02", "2018-04-02", "2018-07-02", "2018-10-01",
    "2019-01-02", "2019-04-01", "2019-07-01", "2019-10-01",
    "2020-01-02", "2020-04-01", "2020-07-01", "2020-10-01",
    "2021-01-04", "2021-04-01", "2021-07-01", "2021-10-01",
    "2022-01-03", "2022-04-01", "2022-07-01", "2022-10-03",
    "2023-01-03", "2023-04-03", "2023-07-03", "2023-10-02",
    "2024-01-02", "2024-04-01", "2024-07-01", "2024-10-01",
    "2025-01-02", "2025-04-01", "2025-07-01", "2025-10-01",
    "2026-01-02", "2026-04-01",
]

# Phase 2.6 gated-blend production rule. The pooled-mode signal fires only when
# all three conditions are met; otherwise the recommendation falls back to the
# regime-unaware 252d rolling z-score baseline. Surfaces both in the walk-forward
# (a third leg) and at inference time (live_ranker honours PULSE_GATED_BLEND=1).
GATED_REGIME       = "BACK"
# Phase 2.8.3 — widened to include the 3 Phase 2.8.1 boosters. The Phase 2.6
# narrow gate {Lasso, Huber} was correct for the 11-feature Phase 2.5 universe,
# but the Phase 2.8.1 7-model competition + Phase 2.8.2 22-feature set lets
# boosters win BACK cells with stronger pooled walk-forward Sharpe (LGBM +1.294
# / CatBoost +1.248 / XGB +0.853) than gate-eligible Huber +1.107 or Lasso
# +0.781. Excluding them concentrated surviving fires on a weaker slice and
# dropped gated Sharpe +0.456 → +0.389 between Phase 2.7 and 2.8.2.
GATED_WINNERS      = {"Lasso", "Huber", "XGBoost", "LightGBM", "CatBoost"}
GATED_Z_THRESHOLD  = Z_ENTRY    # |z| ≥ 0.5σ

# Phase 2.7 — position sizing for the regime leg of the gated blend. The brief:
# compress the −271 max-DD that concentration of 97 high-Sharpe regime fires
# costs the leg, without giving up the +1.332 Sharpe alpha. Baseline leg is
# always sized 1.0; only the regime leg scales.
SIZING_MODES         = ("full", "half", "kelly")
SIZING_KELLY_FLOOR   = 0.10
SIZING_KELLY_CAP     = 1.00
SIZING_KELLY_DEFAULT = 0.50
SIZING_KELLY_MIN_N   = 5

# ─── Phase 2.8.6 — Transaction costs ────────────────────────────────────────
# Defensible per-leg, per-side cost model (exchange-published fees + standard
# liquid-front-month bid-ask):
#   commission + clearing + brokerage:   $0.0025/bbl per leg per side
#       (ICE Brent ~$1.45/contract + clearing ~$0.30 + brokerage ~$0.70 = ~$2.45
#        per 1,000-bbl contract → $0.00245/bbl, rounded to $0.0025)
#   half bid-ask slippage per leg:       $0.0050/bbl for front (M1/M2),
#                                        $0.0075/bbl for deferred (M3..M6)
#       (Liquid Brent front: 1 tick = $0.01/bbl; deferred typically 1-2 ticks.)
#
# Round-trip cost in $/bbl on the spread basis:
#   N legs × 2 sides × (commission + half-spread)
#
#   2-leg M1-M2:   2 × 2 × (0.0025 + 0.0050) = $0.030/bbl RT
#   2-leg M3-M6:   2 × 2 × (0.0025 + 0.0075) = $0.040/bbl RT
#   3-leg fly:     3 × 2 × (0.0025 + 0.0058) = $0.050/bbl RT
#       (fly has two front-ish legs + one M3 leg → blended half-spread ~$0.0058)
#
# Cost scales with sizing_scale on regime rows (if you trade fewer contracts you
# pay fewer fees). NEUTRAL trades incur zero cost (no fill). Applied at the
# AGGREGATION step only — model training/CV is unaffected, so no retraining is
# required when the cost model changes. Live inference does not subtract cost
# at trade entry; the cost-aware NET metric exists for backtest reporting.
COST_PER_SPREAD_RT = {
    "brent_m1_m2":   0.030,
    "brent_m3_m6":   0.040,
    "brent_fly_123": 0.050,
    "wti_m1_m2":     0.030,
    "wti_m3_m6":     0.040,
    "wti_fly_123":   0.050,
}
COST_DEFAULT_RT = 0.040  # fallback when spread isn't in the table


def _cost_for(t: dict) -> float:
    """
    Phase 2.8.6 — round-trip transaction cost (in $/bbl) for one trade row.

    Returns 0.0 for NEUTRAL trades (no fill). For fired trades, returns the
    spread's RT cost from COST_PER_SPREAD_RT, scaled by the trade's
    sizing_scale (1.0 if absent — covers un-sized gated_trades).
    """
    if t.get("direction") == "NEUTRAL":
        return 0.0
    if t.get("fwd_pnl") is None:
        return 0.0
    base = COST_PER_SPREAD_RT.get(t.get("spread"), COST_DEFAULT_RT)
    raw_scale = t.get("sizing_scale", 1.0)
    try:
        scale = float(raw_scale) if raw_scale is not None else 1.0
    except (TypeError, ValueError):
        scale = 1.0
    return base * scale


# ─────────────────────────────────────────────────────────────────────────────
# Training helpers — reuse models.py competition; pick winner per cell
# ─────────────────────────────────────────────────────────────────────────────
def _train_cells_through(
    joined: pd.DataFrame,
    cutoff: pd.Timestamp,
    regime_mode: str = "composite",
    *,
    regime_col: str | None = None,
    regime_list: list[str] | None = None,
    enable_boosters: bool | None = None,
) -> dict:
    """
    Train one model per (spread, regime) on rows ≤ cutoff for the given mode.
    Returns dict keyed by (spread, regime) → {pipe, q10, q50, q90, resid_std, winner, n_train}.
    Cells with n_train < MIN_SAMPLES are skipped.

    Phase 6 (2.8.9) — `regime_col` / `regime_list` / `enable_boosters` optionally
    override the regime *source* so a data-driven detector (regime_hmm) can drive
    the same per-cell competition. Defaults (all None) reproduce the
    composite/pooled behaviour bit-for-bit.
    """
    from research.models          import (
        _fit_ridge, _fit_lasso, _fit_elastic, _fit_huber,
        _fit_xgb, _fit_lgbm, _fit_catboost,
        _fit_quantile, _cv_r2, _TIEBREAK_RANK,
        _HAS_XGB, _HAS_LGBM, _HAS_CATBOOST, _BOOSTER_MIN_ROWS,
    )
    from research.features        import predictors_for
    from research.spread_universe import INSTRUMENTS
    from research.regimes         import REGIMES, REGIMES_POOLED

    if regime_list is None:
        regime_list = REGIMES_POOLED if regime_mode == "pooled" else REGIMES
    if regime_col is None:
        regime_col = "regime_pooled" if regime_mode == "pooled" else "regime"

    linear_fitters = {
        "Ridge":      _fit_ridge,
        "Lasso":      _fit_lasso,
        "ElasticNet": _fit_elastic,
        "Huber":      _fit_huber,
    }
    # Phase 2.8.1: Booster competition runs only in pooled mode for walk-forward.
    # Composite (27 cells × 10 refits = 270 cells/refit) blows up wall time and
    # the Phase 2.6 gated blend only consumes pooled winners ∈ {Lasso, Huber}
    # anyway — boosters in composite-mode walk-forward never feed the headline
    # gated_blend Sharpe. The standalone composite training in models.py still
    # competes all 7 candidates (that's the deployed model on /api/regime).
    # Phase 6: the HMM leg is the pooled analog (few dense cells) so it enables
    # boosters too, via the explicit `enable_boosters` override.
    if enable_boosters is None:
        enable_boosters = (regime_mode == "pooled")
    booster_fitters: dict = {}
    if enable_boosters:
        if _HAS_XGB:
            booster_fitters["XGBoost"] = _fit_xgb
        if _HAS_LGBM:
            booster_fitters["LightGBM"] = _fit_lgbm
        if _HAS_CATBOOST:
            booster_fitters["CatBoost"] = _fit_catboost

    train_df = joined[joined.index <= cutoff]
    out: dict = {}

    for spread in INSTRUMENTS:
        feat_cols = predictors_for(spread)
        for regime in regime_list:
            sub = train_df[train_df[regime_col] == regime].dropna(subset=feat_cols + [spread])
            if len(sub) < MIN_SAMPLES:
                continue
            X = sub[feat_cols].values
            y = sub[spread].values

            cell_fitters = dict(linear_fitters)
            if len(sub) >= _BOOSTER_MIN_ROWS:
                cell_fitters.update(booster_fitters)
            scores: dict[str, float] = {}
            fitted: dict = {}
            for name, fitter in cell_fitters.items():
                try:
                    scores[name] = _cv_r2(fitter, X, y)
                    fitted[name] = fitter(X, y)
                except Exception:
                    scores[name] = float("-inf")

            valid = {n: s for n, s in scores.items() if s > float("-inf")}
            if not valid:
                continue
            best = max(valid.values())
            tie  = {n: s for n, s in valid.items() if best - s < 0.005}
            winner = min(tie.keys(), key=lambda n: _TIEBREAK_RANK[n])

            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                q10 = _fit_quantile(X, y, 0.10)
                q50 = _fit_quantile(X, y, 0.50)
                q90 = _fit_quantile(X, y, 0.90)

            resid = y - fitted[winner].predict(X)
            out[(spread, regime)] = {
                "point":      fitted[winner],
                "q10":        q10, "q50": q50, "q90": q90,
                "resid_std":  float(np.std(resid)) or 1.0,
                "winner":     winner,
                "n_train":    int(len(sub)),
                "feat_cols":  feat_cols,
                "cv_r2":      round(valid[winner], 4),
            }
    return out


def _evaluate_window(
    joined: pd.DataFrame,
    spreads: pd.DataFrame,
    cells: dict,
    start: pd.Timestamp,
    end: pd.Timestamp,
    regime_mode: str = "composite",
    *,
    regime_col: str | None = None,
) -> list[dict]:
    """
    For each business day d in (start, end], for each spread, generate one
    record: (date, spread, regime, actual, fair, z, direction, fwd_20d_pnl).

    Phase 6 (2.8.9) — `regime_col` optionally overrides the column the day's
    regime is read from (default None reproduces composite/pooled behaviour).
    """
    from research.spread_universe import INSTRUMENTS

    window = joined[(joined.index > start) & (joined.index <= end)]
    if regime_col is None:
        regime_col = "regime_pooled" if regime_mode == "pooled" else "regime"
    trades: list[dict] = []

    for d, row in window.iterrows():
        regime = str(row[regime_col])
        for spread in INSTRUMENTS:
            cell = cells.get((spread, regime))
            if cell is None:
                continue
            feat_cols = cell["feat_cols"]
            feat_vals = row[feat_cols]
            if feat_vals.isnull().any():
                continue
            actual = spreads.at[d, spread] if d in spreads.index else None
            if actual is None or not np.isfinite(actual):
                continue

            X = feat_vals.values.reshape(1, -1)
            point = float(cell["point"].predict(X)[0])
            p10   = float(cell["q10"].predict(X)[0])
            p50   = float(cell["q50"].predict(X)[0])
            p90   = float(cell["q90"].predict(X)[0])
            sigma = cell["resid_std"]
            z     = (actual - point) / sigma if sigma > 0 else 0.0

            if z > Z_ENTRY:      direction =  "SELL"; sign = -1
            elif z < -Z_ENTRY:   direction =  "BUY";  sign = +1
            else:                direction = "NEUTRAL"; sign = 0

            # Forward 20-trading-day spread move
            future = spreads.loc[spreads.index > d, spread].dropna()
            if len(future) >= FORWARD_DAYS:
                fwd_spread = float(future.iloc[FORWARD_DAYS - 1])
                fwd_move   = fwd_spread - float(actual)
                fwd_pnl    = sign * fwd_move
                fwd_date   = future.index[FORWARD_DAYS - 1].strftime("%Y-%m-%d")
            else:
                fwd_pnl = None; fwd_move = None; fwd_date = None

            trades.append({
                "date":      d.strftime("%Y-%m-%d"),
                "spread":    spread,
                "regime":    regime,
                "actual":    round(float(actual), 4),
                "fair":      round(point, 4),
                "p10":       round(p10, 4),
                "p50":       round(p50, 4),
                "p90":       round(p90, 4),
                # Phase 2.9.0 — resid_std carried so the TP/SL exit simulator
                # (exit_sim.py) can rebuild the stop level (entry ± 1.5σ)
                # without back-solving from z. Additive; no metric reads it.
                "resid_std": round(float(sigma), 6),
                "z":         round(z, 3),
                "direction": direction,
                "winner":    cell["winner"],
                "fwd_move":  round(fwd_move, 4) if fwd_move is not None else None,
                "fwd_pnl":   round(fwd_pnl, 4)  if fwd_pnl  is not None else None,
                "fwd_date":  fwd_date,
            })
    return trades


# ─────────────────────────────────────────────────────────────────────────────
# Phase 2.8.4 — global model with regime-as-feature
# ─────────────────────────────────────────────────────────────────────────────
# Reframes the 2.8.8 verdict (baseline beats every per-cell regime variant on
# long history): instead of *splitting* the data by regime, train ONE model
# per spread on ALL rows and feed the composite regime as 9 one-hot columns.
# Same 7-model competition as the per-cell harness. Each spread now has ~5×
# more training rows per refit (the union of all regime cells), so boosters
# have a real shot at finding regime × feature interactions the linear
# per-cell winners can't express.
#
# Honest test: does collapsing the grid + adding regime-as-feature beat
# baseline NET +0.372 / gated NET +0.298 / pooled NET +0.293 from the
# 2026-06-15 walk-forward?
def _regime_one_hot(row: pd.Series) -> dict:
    """Decompose a row's composite regime label into 9 one-hot axis columns.
    UNKNOWN rows (any axis) get all-zeros for that axis — already dropped
    upstream in build_features() but defensive."""
    label = str(row.get("regime") or "")
    parts = label.split("/")
    if len(parts) != 3:
        return {col: 0 for col in _REGIME_OH_COLS}
    curve, inv, vol = parts
    out: dict[str, int] = {col: 0 for col in _REGIME_OH_COLS}
    for prefix, val in (("curve_", curve), ("inv_", inv), ("vol_", vol)):
        col = f"{prefix}{val}"
        if col in out:
            out[col] = 1
    return out


def _train_global_through(
    joined: pd.DataFrame,
    cutoff: pd.Timestamp,
    base_feats_by_spread: dict[str, list[str]] | None = None,
) -> dict:
    """
    Phase 2.8.4 — train ONE model per spread on rows ≤ cutoff. Regime is fed
    as 9 one-hot axis columns instead of partitioning the training data.
    Returns dict keyed by spread → {point, q10, q50, q90, resid_std, winner,
                                    n_train, feat_cols, cv_r2}.

    Phase 5 (2.8.7-featsel) — `base_feats_by_spread` optionally overrides the
    per-spread base predictor list (the regime one-hots are always appended).
    Default None reproduces the Phase 2.8.4 global leg bit-for-bit.
    """
    from research.models          import (
        _fit_ridge, _fit_lasso, _fit_elastic, _fit_huber,
        _fit_xgb, _fit_lgbm, _fit_catboost,
        _fit_quantile, _cv_r2, _TIEBREAK_RANK,
        _HAS_XGB, _HAS_LGBM, _HAS_CATBOOST, _BOOSTER_MIN_ROWS,
    )
    from research.features        import predictors_for
    from research.spread_universe import INSTRUMENTS

    train_df = joined[joined.index <= cutoff].copy()
    # Build one-hot regime columns on the training frame.
    oh = train_df.apply(_regime_one_hot, axis=1, result_type="expand")
    for col in _REGIME_OH_COLS:
        train_df[col] = oh[col].astype(int) if col in oh.columns else 0

    linear_fitters = {
        "Ridge":      _fit_ridge,
        "Lasso":      _fit_lasso,
        "ElasticNet": _fit_elastic,
        "Huber":      _fit_huber,
    }
    booster_fitters: dict = {}
    if _HAS_XGB:      booster_fitters["XGBoost"]  = _fit_xgb
    if _HAS_LGBM:     booster_fitters["LightGBM"] = _fit_lgbm
    if _HAS_CATBOOST: booster_fitters["CatBoost"] = _fit_catboost

    out: dict = {}
    for spread in INSTRUMENTS:
        if base_feats_by_spread is not None and spread in base_feats_by_spread:
            base_feats = list(base_feats_by_spread[spread])
        else:
            base_feats = predictors_for(spread)
        feat_cols  = base_feats + _REGIME_OH_COLS
        sub = train_df.dropna(subset=base_feats + [spread])
        if len(sub) < MIN_SAMPLES:
            continue
        X = sub[feat_cols].values
        y = sub[spread].values

        cell_fitters = dict(linear_fitters)
        if len(sub) >= _BOOSTER_MIN_ROWS:
            cell_fitters.update(booster_fitters)
        scores: dict[str, float] = {}
        fitted: dict = {}
        for name, fitter in cell_fitters.items():
            try:
                scores[name] = _cv_r2(fitter, X, y)
                fitted[name] = fitter(X, y)
            except Exception:
                scores[name] = float("-inf")

        valid = {n: s for n, s in scores.items() if s > float("-inf")}
        if not valid:
            continue
        best = max(valid.values())
        tie  = {n: s for n, s in valid.items() if best - s < 0.005}
        winner = min(tie.keys(), key=lambda n: _TIEBREAK_RANK[n])

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            q10 = _fit_quantile(X, y, 0.10)
            q50 = _fit_quantile(X, y, 0.50)
            q90 = _fit_quantile(X, y, 0.90)

        resid = y - fitted[winner].predict(X)
        out[spread] = {
            "point":     fitted[winner],
            "q10":       q10, "q50": q50, "q90": q90,
            "resid_std": float(np.std(resid)) or 1.0,
            "winner":    winner,
            "n_train":   int(len(sub)),
            "feat_cols": feat_cols,
            "cv_r2":     round(valid[winner], 4),
        }
    return out


def _evaluate_window_global(
    joined: pd.DataFrame,
    spreads: pd.DataFrame,
    cells: dict,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> list[dict]:
    """
    Global-mode counterpart to _evaluate_window. One model per spread; the
    day's regime appears as a feature row, not a cell key.
    """
    from research.spread_universe import INSTRUMENTS

    window = joined[(joined.index > start) & (joined.index <= end)].copy()
    oh = window.apply(_regime_one_hot, axis=1, result_type="expand")
    for col in _REGIME_OH_COLS:
        window[col] = oh[col].astype(int) if col in oh.columns else 0

    trades: list[dict] = []
    for d, row in window.iterrows():
        regime = str(row.get("regime") or "")
        for spread in INSTRUMENTS:
            cell = cells.get(spread)
            if cell is None:
                continue
            feat_cols = cell["feat_cols"]
            feat_vals = row[feat_cols]
            if feat_vals.isnull().any():
                continue
            actual = spreads.at[d, spread] if d in spreads.index else None
            if actual is None or not np.isfinite(actual):
                continue

            X = feat_vals.values.reshape(1, -1)
            point = float(cell["point"].predict(X)[0])
            p10   = float(cell["q10"].predict(X)[0])
            p50   = float(cell["q50"].predict(X)[0])
            p90   = float(cell["q90"].predict(X)[0])
            sigma = cell["resid_std"]
            z     = (actual - point) / sigma if sigma > 0 else 0.0

            if z > Z_ENTRY:      direction =  "SELL"; sign = -1
            elif z < -Z_ENTRY:   direction =  "BUY";  sign = +1
            else:                direction = "NEUTRAL"; sign = 0

            future = spreads.loc[spreads.index > d, spread].dropna()
            if len(future) >= FORWARD_DAYS:
                fwd_spread = float(future.iloc[FORWARD_DAYS - 1])
                fwd_move   = fwd_spread - float(actual)
                fwd_pnl    = sign * fwd_move
                fwd_date   = future.index[FORWARD_DAYS - 1].strftime("%Y-%m-%d")
            else:
                fwd_pnl = None; fwd_move = None; fwd_date = None

            trades.append({
                "date":      d.strftime("%Y-%m-%d"),
                "spread":    spread,
                "regime":    regime,
                "actual":    round(float(actual), 4),
                "fair":      round(point, 4),
                "p10":       round(p10, 4),
                "p50":       round(p50, 4),
                "p90":       round(p90, 4),
                "resid_std": round(float(sigma), 6),
                "z":         round(z, 3),
                "direction": direction,
                "winner":    cell["winner"],
                "fwd_move":  round(fwd_move, 4) if fwd_move is not None else None,
                "fwd_pnl":   round(fwd_pnl, 4)  if fwd_pnl  is not None else None,
                "fwd_date":  fwd_date,
            })
    return trades


def _produce_global_trades(
    joined: pd.DataFrame,
    spreads: pd.DataFrame,
    refit_ts: list[pd.Timestamp],
    base_feats_by_spread: dict[str, list[str]] | None = None,
    tag: str = "global",
) -> tuple[list[dict], list[dict]]:
    """Quarterly-refit driver for the global regime-as-feature leg.

    Phase 5 — `base_feats_by_spread` threads the lean (stability-selected)
    per-spread feature lists into the per-refit training; `tag` only changes
    the log prefix. Default args reproduce the Phase 2.8.4 global leg."""
    all_trades: list[dict] = []
    refit_meta: list[dict] = []
    for i, cutoff in enumerate(refit_ts):
        next_cutoff = refit_ts[i + 1] if i + 1 < len(refit_ts) else joined.index.max()
        log.info("[%s] Refit %d/%d  cutoff=%s  window=(%s, %s]",
                 tag, i + 1, len(refit_ts), cutoff.date(),
                 cutoff.date(), next_cutoff.date())
        cells = _train_global_through(joined, cutoff, base_feats_by_spread=base_feats_by_spread)
        log.info("  trained %d spreads", len(cells))

        window_trades = _evaluate_window_global(joined, spreads, cells, cutoff, next_cutoff)
        log.info("  evaluated %d records", len(window_trades))

        winners: dict[str, int] = {}
        for _, c in cells.items():
            winners[c["winner"]] = winners.get(c["winner"], 0) + 1
        refit_meta.append({
            "cutoff":     cutoff.strftime("%Y-%m-%d"),
            "window_end": next_cutoff.strftime("%Y-%m-%d"),
            "n_cells":    len(cells),
            "winners":    winners,
            "n_records":  len(window_trades),
        })
        all_trades.extend(window_trades)
    return all_trades, refit_meta


def _aggregate_global(trades: list[dict], refit_meta: list[dict]) -> dict:
    """Same shape as _aggregate_mode but no per-regime/winner-by-regime split."""
    return {
        "regime_mode":   "global",
        "overall":       _metrics(trades),
        "by_spread":     _by(trades, "spread"),
        "by_curve_axis": _by_curve_axis(trades),
        "by_winner":     _by(trades, "winner"),
        "by_direction":  _by(trades, "direction"),
        "refits":        refit_meta,
        "n_trades":      len(trades),
        "feature_set":   {
            "base":     "predictors_for(spread)",
            "one_hot":  list(_REGIME_OH_COLS),
            "note":     "Phase 2.8.4 — ONE model per spread; composite regime fed as 9 one-hot axis columns (curve/inv/vol). Reuses the same 7-model competition as the per-cell harness.",
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# Phase 2.8.5 — soft regime probabilities
# ─────────────────────────────────────────────────────────────────────────────
# Reuses the per-cell trained models from `_train_cells_through` (pooled or
# composite) but evaluates each day by *blending* every cell's prediction by
# the day's soft posterior over regimes (softprob.py). Hard regimes recover
# in the limit h → 0; this leg sits at the trader-set bandwidths in
# softprob.AXIS_BANDWIDTHS.
#
# Mechanics per (date, spread):
#   1. compute axis-soft posterior for the day → 3 or 27 weights, summing 1
#   2. for each (spread, regime) cell that was trained at this refit, get
#      point / q10 / q50 / q90 / resid_std
#   3. blended point = Σ_r w_r · point_r  (linear; same for quantiles & sigma)
#   4. z = (actual - blended_point) / blended_sigma → direction by Z_ENTRY
#   5. fwd_pnl = sign × 20-day spread move (same horizon as hard variants)
#
# Weights are renormalised over the *available* cells: a cell with no trained
# model (n_train < MIN_SAMPLES at this refit, especially WTI pre-2021) drops
# out and the rest of the posterior is rescaled. This keeps the leg honest
# about cell availability without imputing a hard-zero weight that would bias
# the blended prediction toward whichever cells happened to train.
def _evaluate_window_soft(
    joined: pd.DataFrame,
    spreads: pd.DataFrame,
    cells: dict,
    start: pd.Timestamp,
    end: pd.Timestamp,
    regime_mode: str = "pooled",
) -> list[dict]:
    """
    Soft-posterior counterpart to `_evaluate_window`. Reuses cells from
    `_train_cells_through(regime_mode=...)`; `regime_mode` decides which
    soft posterior is computed (pooled = 3-bucket curve; composite = 27).
    """
    from research.spread_universe import INSTRUMENTS
    from research.softprob        import pooled_soft, composite_soft

    if regime_mode not in ("pooled", "composite"):
        raise ValueError(f"_evaluate_window_soft: unknown regime_mode {regime_mode!r}")

    # Build a {spread -> {regime -> cell}} index once so the per-day loop is cheap.
    by_spread: dict[str, dict[str, dict]] = {}
    for (sp, rg), c in cells.items():
        by_spread.setdefault(sp, {})[rg] = c

    window = joined[(joined.index > start) & (joined.index <= end)]
    trades: list[dict] = []

    for d, row in window.iterrows():
        if regime_mode == "pooled":
            posterior = pooled_soft(row.get("m1_m12"))
        else:
            posterior = composite_soft(
                row.get("m1_m12"),
                row.get("inv_vs_5yr_pct"),
                row.get("realised_vol_20d"),
            )

        for spread in INSTRUMENTS:
            cell_map = by_spread.get(spread, {})
            if not cell_map:
                continue
            # Build the (regime, weight, cell) list restricted to trained cells.
            available = [(rg, w, cell_map[rg]) for rg, w in posterior.items()
                         if rg in cell_map and w > 0.0]
            if not available:
                continue
            wsum = sum(w for _, w, _ in available)
            if wsum <= 0:
                continue

            # All cells for one spread share predictors_for(spread) → same feat_cols.
            feat_cols = available[0][2]["feat_cols"]
            feat_vals = row[feat_cols]
            if feat_vals.isnull().any():
                continue
            actual = spreads.at[d, spread] if d in spreads.index else None
            if actual is None or not np.isfinite(actual):
                continue

            X = feat_vals.values.reshape(1, -1)
            point_b = 0.0; q10_b = 0.0; q50_b = 0.0; q90_b = 0.0
            sigma_sq_b = 0.0
            top_weight = 0.0
            top_regime = ""
            top_winner = ""
            for rg, w, cell in available:
                ww = w / wsum
                point_b += ww * float(cell["point"].predict(X)[0])
                q10_b   += ww * float(cell["q10"].predict(X)[0])
                q50_b   += ww * float(cell["q50"].predict(X)[0])
                q90_b   += ww * float(cell["q90"].predict(X)[0])
                # Blend variances additively, then take sqrt — standard mixture
                # marginal variance ignoring the (small) point-prediction
                # disagreement term. Conservative: under-states sigma slightly
                # when cell predictions differ, which makes the z threshold a
                # touch easier to trip; same direction the hard variant has.
                sigma_sq_b += ww * (cell["resid_std"] ** 2)
                if ww > top_weight:
                    top_weight = ww
                    top_regime = rg
                    top_winner = cell["winner"]
            sigma_b = math.sqrt(sigma_sq_b) if sigma_sq_b > 0 else 1.0
            z = (float(actual) - point_b) / sigma_b if sigma_b > 0 else 0.0

            if z > Z_ENTRY:      direction =  "SELL"; sign = -1
            elif z < -Z_ENTRY:   direction =  "BUY";  sign = +1
            else:                direction = "NEUTRAL"; sign = 0

            future = spreads.loc[spreads.index > d, spread].dropna()
            if len(future) >= FORWARD_DAYS:
                fwd_spread = float(future.iloc[FORWARD_DAYS - 1])
                fwd_move   = fwd_spread - float(actual)
                fwd_pnl    = sign * fwd_move
                fwd_date   = future.index[FORWARD_DAYS - 1].strftime("%Y-%m-%d")
            else:
                fwd_pnl = None; fwd_move = None; fwd_date = None

            trades.append({
                "date":         d.strftime("%Y-%m-%d"),
                "spread":       spread,
                # `regime` carries the MODAL regime so by_curve_axis / by_winner
                # still aggregate sensibly; the blend itself is in posterior_*.
                "regime":       top_regime,
                "actual":       round(float(actual), 4),
                "fair":         round(point_b, 4),
                "p10":          round(q10_b, 4),
                "p50":          round(q50_b, 4),
                "p90":          round(q90_b, 4),
                "resid_std":    round(float(sigma_b), 6),
                "z":            round(z, 3),
                "direction":    direction,
                "winner":       top_winner,
                "fwd_move":     round(fwd_move, 4) if fwd_move is not None else None,
                "fwd_pnl":      round(fwd_pnl, 4)  if fwd_pnl  is not None else None,
                "fwd_date":     fwd_date,
                "soft_top_w":   round(float(top_weight), 4),
                "soft_n_cells": len(available),
            })
    return trades


def _produce_soft_trades(
    joined: pd.DataFrame,
    spreads: pd.DataFrame,
    refit_ts: list[pd.Timestamp],
    regime_mode: str,
) -> tuple[list[dict], list[dict]]:
    """Quarterly-refit driver for the soft-posterior leg of `regime_mode`."""
    if regime_mode not in ("pooled", "composite"):
        raise ValueError(regime_mode)

    all_trades: list[dict] = []
    refit_meta: list[dict] = []
    tag = f"{regime_mode}_soft"
    for i, cutoff in enumerate(refit_ts):
        next_cutoff = refit_ts[i + 1] if i + 1 < len(refit_ts) else joined.index.max()
        log.info("[%s] Refit %d/%d  cutoff=%s  window=(%s, %s]",
                 tag, i + 1, len(refit_ts), cutoff.date(),
                 cutoff.date(), next_cutoff.date())
        cells = _train_cells_through(joined, cutoff, regime_mode=regime_mode)
        log.info("  trained %d cells", len(cells))

        window_trades = _evaluate_window_soft(joined, spreads, cells, cutoff, next_cutoff,
                                              regime_mode=regime_mode)
        log.info("  evaluated %d records", len(window_trades))

        winners: dict[str, int] = {}
        for _, c in cells.items():
            winners[c["winner"]] = winners.get(c["winner"], 0) + 1
        refit_meta.append({
            "cutoff":     cutoff.strftime("%Y-%m-%d"),
            "window_end": next_cutoff.strftime("%Y-%m-%d"),
            "n_cells":    len(cells),
            "winners":    winners,
            "n_records":  len(window_trades),
        })
        all_trades.extend(window_trades)
    return all_trades, refit_meta


def _aggregate_soft(trades: list[dict], refit_meta: list[dict], regime_mode: str) -> dict:
    """Same shape as `_aggregate_mode` plus a soft-specific diagnostics block."""
    blk = _aggregate_mode(trades, refit_meta, f"{regime_mode}_soft")
    # Soft-specific diagnostics: mean top-weight (1.0 ≈ hard) + average #cells used.
    top_w = [t.get("soft_top_w") for t in trades if t.get("soft_top_w") is not None]
    n_cells = [t.get("soft_n_cells") for t in trades if t.get("soft_n_cells") is not None]
    blk["soft_diagnostics"] = {
        "mean_top_weight":     round(float(np.mean(top_w)),     4) if top_w   else None,
        "median_top_weight":   round(float(np.median(top_w)),   4) if top_w   else None,
        "mean_cells_blended":  round(float(np.mean(n_cells)),   2) if n_cells else None,
        "median_cells_blended":int(np.median(n_cells))                if n_cells else None,
        "bandwidths":          dict(__import__("research.softprob", fromlist=["AXIS_BANDWIDTHS"]).AXIS_BANDWIDTHS),
        "note":                "Phase 2.8.5 — softprob.axis_softprob blends per-(spread,regime) cell predictions by per-day posterior. Hard pooled/composite recover as h→0; flat-prior global recovers as h→∞. Bandwidths picked from trader thresholds, not tuned to PnL.",
    }
    return blk


# ─────────────────────────────────────────────────────────────────────────────
# Regime-unaware baseline (rolling z-score)
# ─────────────────────────────────────────────────────────────────────────────
def _baseline_trades(
    spreads: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> list[dict]:
    """
    For each spread, compute rolling 252-day z-score of the spread itself
    (no regime). Same trading rule + 20-day horizon. Used to isolate the
    benefit of regime conditioning.
    """
    from research.spread_universe import INSTRUMENTS

    trades: list[dict] = []
    for spread in INSTRUMENTS:
        s = spreads[spread].dropna()
        if len(s) < ROLLING_WIN + 1:
            continue
        roll_mu  = s.rolling(ROLLING_WIN).mean()
        roll_sig = s.rolling(ROLLING_WIN).std()
        z_all    = (s - roll_mu) / roll_sig

        idx = s.index[(s.index > start) & (s.index <= end)]
        for d in idx:
            actual = float(s.loc[d])
            z = z_all.loc[d]
            if not np.isfinite(z):
                continue
            if z > Z_ENTRY:     direction = "SELL"; sign = -1
            elif z < -Z_ENTRY:  direction = "BUY";  sign = +1
            else:               direction = "NEUTRAL"; sign = 0

            future = s.loc[s.index > d]
            if len(future) < FORWARD_DAYS:
                continue
            fwd_move = float(future.iloc[FORWARD_DAYS - 1]) - actual
            fwd_pnl  = sign * fwd_move

            # Phase 2.9.0 — carry the rolling mean (= baseline TP target, the
            # p50 analog) + rolling std (= baseline SL sigma) so the TP/SL exit
            # simulator can close baseline-leg trades at entry±1.5σ / revert-to-
            # mean exactly as live_ranker's baseline candidate does.
            rm = roll_mu.loc[d]
            rs = roll_sig.loc[d]

            trades.append({
                "date":      d.strftime("%Y-%m-%d"),
                "spread":    spread,
                "actual":    round(actual, 4),
                "z":         round(float(z), 3),
                "direction": direction,
                "fwd_move":  round(fwd_move, 4),
                "fwd_pnl":   round(fwd_pnl, 4),
                "roll_mu":   round(float(rm), 6) if np.isfinite(rm) else None,
                "roll_sigma":round(float(rs), 6) if np.isfinite(rs) else None,
            })
    return trades


# ─────────────────────────────────────────────────────────────────────────────
# Aggregation helpers
# ─────────────────────────────────────────────────────────────────────────────
def _metrics(trades: list[dict], cost_fn=None) -> dict:
    """
    Compute hit rate / mean PnL / Sharpe / max DD on completed (non-NEUTRAL) trades.

    Phase 2.8.6: pass cost_fn=_cost_for to compute NET metrics (PnL minus the
    per-trade round-trip cost). Hit-rate is recomputed on net PnL so a winning
    trade that costs more than it earns flips to a loss in the net view.
    """
    fired = [t for t in trades if t.get("direction") != "NEUTRAL" and t.get("fwd_pnl") is not None]
    if not fired:
        empty = {
            "n_signals":       0,
            "n_total":         len(trades),
            "n_neutral":       sum(1 for t in trades if t.get("direction") == "NEUTRAL"),
            "hit_rate":        None,
            "mean_pnl":        None,
            "median_pnl":      None,
            "total_pnl":       0.0,
            "sharpe":          None,
            "max_drawdown":    None,
            "win_pnl":         None,
            "loss_pnl":        None,
        }
        if cost_fn is not None:
            empty["mean_cost"]  = None
            empty["total_cost"] = 0.0
        return empty
    if cost_fn is not None:
        gross  = np.array([float(t["fwd_pnl"])         for t in fired], dtype=float)
        costs  = np.array([float(cost_fn(t))           for t in fired], dtype=float)
        pnls   = gross - costs
    else:
        pnls = np.array([t["fwd_pnl"] for t in fired], dtype=float)
        costs = None
    wins = pnls[pnls > 0]; losses = pnls[pnls < 0]
    cum  = np.cumsum(pnls)
    peak = np.maximum.accumulate(cum)
    dd   = cum - peak
    max_dd = float(dd.min()) if len(dd) else 0.0

    mu = float(pnls.mean()); sd = float(pnls.std(ddof=1)) if len(pnls) > 1 else 0.0
    # Sharpe with 20-trading-day horizon → annualisation factor √(252/20)
    sharpe = (mu / sd) * np.sqrt(252.0 / FORWARD_DAYS) if sd > 0 else None

    out = {
        "n_signals":     len(fired),
        "n_total":       len(trades),
        "n_neutral":     sum(1 for t in trades if t.get("direction") == "NEUTRAL"),
        "hit_rate":      round(float((pnls > 0).mean()), 4),
        "mean_pnl":      round(mu, 4),
        "median_pnl":    round(float(np.median(pnls)), 4),
        "total_pnl":     round(float(pnls.sum()), 4),
        "sharpe":        round(sharpe, 3) if sharpe is not None else None,
        "max_drawdown":  round(max_dd, 4),
        "win_pnl":       round(float(wins.mean()), 4)   if len(wins)   else None,
        "loss_pnl":      round(float(losses.mean()), 4) if len(losses) else None,
    }
    if costs is not None:
        out["mean_cost"]  = round(float(costs.mean()), 4)
        out["total_cost"] = round(float(costs.sum()), 4)
    return out


def _by(trades: list[dict], key: str, cost_fn=None) -> dict:
    """Group trades by a key (spread / regime / winner / direction) and metric each group."""
    groups: dict[str, list] = {}
    for t in trades:
        k = t.get(key) or "UNKNOWN"
        groups.setdefault(k, []).append(t)
    return {k: _metrics(v, cost_fn=cost_fn) for k, v in groups.items()}


def _by_curve_axis(trades: list[dict], cost_fn=None) -> dict:
    """Roll regime label up to its CURVE axis bucket (CONTANGO/NEUTRAL/BACK)."""
    rolled = []
    for t in trades:
        # Gated-blend baseline-fallback rows have regime=None when no pooled
        # cell was trained for (date, spread) — e.g. WTI before 2021. _by()
        # maps the empty bucket to "UNKNOWN".
        regime = t.get("regime") or ""
        curve  = regime.split("/", 1)[0] if "/" in regime else regime
        rolled.append({**t, "curve_axis": curve})
    return _by(rolled, "curve_axis", cost_fn=cost_fn)


# ─────────────────────────────────────────────────────────────────────────────
# Phase 2.6 — gated blend
# ─────────────────────────────────────────────────────────────────────────────
def _pooled_passes_gate(p: dict | None) -> bool:
    """Phase 2.6 production gate — must match live_ranker._pooled_passes_gate."""
    if p is None:
        return False
    regime = p.get("regime")
    winner = p.get("winner")
    z      = p.get("z")
    direction = p.get("direction")
    if direction == "NEUTRAL":
        return False
    if regime != GATED_REGIME:
        return False
    if winner not in GATED_WINNERS:
        return False
    if z is None or not np.isfinite(z) or abs(z) < GATED_Z_THRESHOLD:
        return False
    return True


def _build_gated_blend(
    pooled_trades: list[dict],
    baseline_trades: list[dict],
) -> list[dict]:
    """
    Phase 2.6 gated-blend simulator.

    For each (date, spread) we have a pooled-mode candidate and a baseline-mode
    candidate. Production rule:
      • If the pooled candidate passes the gate → take it (source='regime').
      • Else → take the baseline candidate (source='baseline'), regardless of
        whether it fires a signal. NEUTRAL baseline days still get recorded
        so the walk-forward distinguishes "engine declined" from "no opp".
    """
    pool_idx = {(t["date"], t["spread"]): t for t in pooled_trades}
    base_idx = {(t["date"], t["spread"]): t for t in baseline_trades}
    keys     = sorted(set(pool_idx.keys()) | set(base_idx.keys()))

    blended: list[dict] = []
    for k in keys:
        p = pool_idx.get(k)
        b = base_idx.get(k)
        if _pooled_passes_gate(p):
            blended.append({
                **p,                                # type: ignore[arg-type]
                "source":   "regime",
                "gate":     "pass",
            })
        elif b is not None:
            # Baseline fallback — preserve baseline's z + direction; carry
            # pooled context for diagnostics (regime/winner if available).
            blended.append({
                "date":      b["date"],
                "spread":    b["spread"],
                "actual":    b["actual"],
                "z":         b["z"],
                "direction": b["direction"],
                "fwd_move":  b.get("fwd_move"),
                "fwd_pnl":   b.get("fwd_pnl"),
                # Phase 2.9.0 — baseline TP/SL inputs (rolling mean + std) so
                # the exit simulator can close baseline-leg rows of the gated
                # blend. Regime rows keep p50/resid_std via the **p spread above.
                "roll_mu":   b.get("roll_mu"),
                "roll_sigma":b.get("roll_sigma"),
                # diagnostic context from the pooled candidate (if it existed)
                "regime":    (p or {}).get("regime")    if p else None,
                "winner":    (p or {}).get("winner")    if p else None,
                "pooled_z":  (p or {}).get("z")         if p else None,
                "source":    "baseline",
                "gate":      "fail" if p else "no_pooled",
            })
        # else: no data on either side — skip silently.
    return blended


def _by_source(trades: list[dict], cost_fn=None) -> dict:
    """Group gated-blend trades by which leg fired ('regime' / 'baseline')."""
    return _by(trades, "source", cost_fn=cost_fn)


def _by_spread_source(trades: list[dict], cost_fn=None) -> dict:
    """
    {spread -> {source -> metrics}} breakdown — exposes per-spread regime-leg
    stats (hit rate, win/loss PnL) so live inference can compute per-spread
    Kelly without re-deriving from the raw trade list.
    """
    out: dict[str, dict] = {}
    for t in trades:
        sp  = t.get("spread") or "UNKNOWN"
        src = t.get("source") or "UNKNOWN"
        out.setdefault(sp, {}).setdefault(src, []).append(t)
    return {sp: {src: _metrics(v, cost_fn=cost_fn) for src, v in by_src.items()} for sp, by_src in out.items()}


# ─────────────────────────────────────────────────────────────────────────────
# Phase 2.7 — position sizing for the regime leg
# ─────────────────────────────────────────────────────────────────────────────
def _kelly_fraction(pnls: list[float]) -> float:
    """
    Kelly fraction from a list of trade PnLs.

    f* = p − (1−p) / b   where   b = mean_win / |mean_loss|

    Returns SIZING_KELLY_DEFAULT when fewer than SIZING_KELLY_MIN_N samples
    are available, or when wins/losses are missing. Clamped to
    [SIZING_KELLY_FLOOR, SIZING_KELLY_CAP].
    """
    arr = [p for p in pnls if p is not None and np.isfinite(p)]
    if len(arr) < SIZING_KELLY_MIN_N:
        return SIZING_KELLY_DEFAULT
    wins   = [p for p in arr if p > 0]
    losses = [p for p in arr if p < 0]
    if not wins or not losses:
        return SIZING_KELLY_DEFAULT
    p_win  = len(wins) / len(arr)
    avg_w  = float(np.mean(wins))
    avg_l  = abs(float(np.mean(losses)))
    if avg_l <= 0:
        return SIZING_KELLY_CAP
    b      = avg_w / avg_l
    f_star = p_win - (1.0 - p_win) / b
    return float(np.clip(f_star, SIZING_KELLY_FLOOR, SIZING_KELLY_CAP))


def _compute_kelly_by_cutoff(
    gated_trades: list[dict],
    refit_ts: list[pd.Timestamp],
) -> dict:
    """
    For each refit boundary, compute Kelly per spread using only regime-leg
    trades whose forward window closed strictly BEFORE that cutoff. Returns
    {cutoff_str -> {spread -> kelly}}. Expanding-window so the per-cell
    sample grows over time.
    """
    from research.spread_universe import INSTRUMENTS

    closed: list[tuple[pd.Timestamp, str, float]] = []
    for t in gated_trades:
        if t.get("source") != "regime":
            continue
        if t.get("fwd_pnl") is None or t.get("fwd_date") is None:
            continue
        try:
            fd = pd.Timestamp(t["fwd_date"])
        except Exception:
            continue
        closed.append((fd, t["spread"], float(t["fwd_pnl"])))

    out: dict[str, dict[str, float]] = {}
    for cutoff in refit_ts:
        per_spread: dict[str, float] = {}
        for sp in INSTRUMENTS:
            pnls = [p for fd, s, p in closed if s == sp and fd < cutoff]
            per_spread[sp] = round(_kelly_fraction(pnls), 4)
        out[cutoff.strftime("%Y-%m-%d")] = per_spread
    return out


def _apply_sizing(
    gated_trades: list[dict],
    mode: str,
    refit_ts: list[pd.Timestamp],
    kelly_lookup: dict | None = None,
) -> list[dict]:
    """
    Return a new trade list with `fwd_pnl` on regime-source rows scaled by
    the per-mode notional factor. Baseline rows are unchanged. A
    `sizing_scale` field is annotated on every row (1.0 for baseline).
    """
    if mode not in SIZING_MODES:
        raise ValueError(f"unknown sizing mode: {mode!r}; expected {SIZING_MODES}")

    if mode == "full":
        def scale_fn(t):
            return 1.0 if t.get("source") == "regime" else 1.0
    elif mode == "half":
        def scale_fn(t):
            return 0.5 if t.get("source") == "regime" else 1.0
    else:  # kelly
        if kelly_lookup is None:
            kelly_lookup = _compute_kelly_by_cutoff(gated_trades, refit_ts)
        refit_keys = [(c, c.strftime("%Y-%m-%d")) for c in refit_ts]

        def scale_fn(t):
            if t.get("source") != "regime":
                return 1.0
            try:
                td = pd.Timestamp(t["date"])
            except Exception:
                return SIZING_KELLY_DEFAULT
            applicable = None
            for c, k in refit_keys:
                if td > c:
                    applicable = k
                else:
                    break
            if applicable is None:
                return SIZING_KELLY_DEFAULT
            return kelly_lookup.get(applicable, {}).get(t.get("spread"), SIZING_KELLY_DEFAULT)

    out: list[dict] = []
    for t in gated_trades:
        nt = dict(t)
        scale = float(scale_fn(t))
        if t.get("source") == "regime" and t.get("fwd_pnl") is not None:
            nt["fwd_pnl"] = round(float(t["fwd_pnl"]) * scale, 4)
        nt["sizing_scale"] = round(scale, 4)
        out.append(nt)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Mode runner — refit + evaluate the walk-forward for ONE regime mode
# ─────────────────────────────────────────────────────────────────────────────
def _produce_trades(
    joined: pd.DataFrame,
    spreads: pd.DataFrame,
    refit_ts: list[pd.Timestamp],
    regime_mode: str,
) -> tuple[list[dict], list[dict]]:
    """
    Execute the quarterly-refit walk-forward for a single regime mode and
    return (raw trades, per-refit metadata). Aggregation is split out so the
    gated-blend leg can re-use the pooled trades without retraining.
    """
    all_trades: list[dict] = []
    refit_meta: list[dict] = []

    for i, cutoff in enumerate(refit_ts):
        next_cutoff = refit_ts[i + 1] if i + 1 < len(refit_ts) else joined.index.max()
        log.info("[%s] Refit %d/%d  cutoff=%s  window=(%s, %s]",
                 regime_mode, i + 1, len(refit_ts), cutoff.date(),
                 cutoff.date(), next_cutoff.date())
        cells = _train_cells_through(joined, cutoff, regime_mode=regime_mode)
        log.info("  trained %d cells", len(cells))

        window_trades = _evaluate_window(joined, spreads, cells, cutoff, next_cutoff,
                                         regime_mode=regime_mode)
        log.info("  evaluated %d (date × spread) records", len(window_trades))

        winners: dict[str, int] = {}
        for _, c in cells.items():
            winners[c["winner"]] = winners.get(c["winner"], 0) + 1

        refit_meta.append({
            "cutoff":     cutoff.strftime("%Y-%m-%d"),
            "window_end": next_cutoff.strftime("%Y-%m-%d"),
            "n_cells":    len(cells),
            "winners":    winners,
            "n_records":  len(window_trades),
        })
        all_trades.extend(window_trades)

    return all_trades, refit_meta


def _aggregate_mode(trades: list[dict], refit_meta: list[dict], regime_mode: str) -> dict:
    """Aggregate a trades list into the standard mode-block schema."""
    return {
        "regime_mode":  regime_mode,
        "overall":      _metrics(trades),
        "by_spread":    _by(trades, "spread"),
        "by_curve_axis":_by_curve_axis(trades),
        "by_winner":    _by(trades, "winner"),
        "by_direction": _by(trades, "direction"),
        "refits":       refit_meta,
        "n_trades":     len(trades),
    }


def _net_block(trades: list[dict], include_source: bool = False) -> dict:
    """
    Phase 2.8.6 — NET aggregation for a trade list (gross PnL minus per-trade
    transaction cost). Mirrors a subset of _aggregate_mode but always uses
    _cost_for so the caller doesn't have to pass it.
    """
    blk = {
        "overall":   _metrics(trades, cost_fn=_cost_for),
        "by_spread": _by(trades, "spread", cost_fn=_cost_for),
    }
    if include_source:
        blk["by_source"]        = _by_source(trades, cost_fn=_cost_for)
        blk["by_spread_source"] = _by_spread_source(trades, cost_fn=_cost_for)
    return blk


def _run_mode(
    joined: pd.DataFrame,
    spreads: pd.DataFrame,
    refit_ts: list[pd.Timestamp],
    regime_mode: str,
) -> tuple[dict, list[dict]]:
    """
    Execute the full quarterly-refit walk-forward for a single regime mode.
    Returns (mode_block, raw_trades). Raw trades surface so the gated-blend
    leg can compose without retraining.
    """
    trades, refit_meta = _produce_trades(joined, spreads, refit_ts, regime_mode)
    return _aggregate_mode(trades, refit_meta, regime_mode), trades


def _lift(mode_block: dict, ref_by_spread: dict, ref_overall: dict) -> dict:
    """Per-spread lift of mode_block vs a reference (baseline or composite)."""
    out = {}
    for sp, r in mode_block.get("by_spread", {}).items():
        b = ref_by_spread.get(sp, {})
        out[sp] = {
            "hit_rate":      r.get("hit_rate"),
            "ref_hit_rate":  b.get("hit_rate"),
            "mean_pnl":      r.get("mean_pnl"),
            "ref_mean_pnl":  b.get("mean_pnl"),
            "sharpe":        r.get("sharpe"),
            "ref_sharpe":    b.get("sharpe"),
            "n":             r.get("n_signals"),
            "ref_n":         b.get("n_signals"),
        }
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Top-level driver
# ─────────────────────────────────────────────────────────────────────────────
def run_walkforward() -> dict:
    """
    Run the full walk-forward backtest for BOTH regime modes plus the
    regime-unaware baseline. Returns the combined report dict (also saved).
    """
    from research.features        import build_features
    from research.spread_universe import build_spread_series

    log.info("Building feature matrix + spread universe...")
    features = build_features()
    spreads  = build_spread_series()
    joined   = features.join(spreads, how="inner")
    log.info("  features: %d rows  spreads: %d rows  joined: %d rows",
             len(features), len(spreads), len(joined))

    refit_ts = [pd.Timestamp(d) for d in REFIT_DATES]
    refit_ts = [t for t in refit_ts if t >= joined.index.min() and t <= joined.index.max()]

    composite_block, composite_trades = _run_mode(joined, spreads, refit_ts, regime_mode="composite")
    pooled_block,    pooled_trades    = _run_mode(joined, spreads, refit_ts, regime_mode="pooled")

    # Phase 2.8.4 — global model with regime-as-feature (one model per spread).
    log.info("Phase 2.8.4 — global regime-as-feature leg...")
    global_trades, global_meta = _produce_global_trades(joined, spreads, refit_ts)
    global_block = _aggregate_global(global_trades, global_meta)

    # Phase 2.8.5 — soft pooled posterior. Composite-soft is opt-in
    # (`python -m research.walkforward --soft-only --composite`) because
    # retraining the 27-cell grid + soft-blending dominates wall time; the
    # pooled variant tests the same hypothesis on the cheaper grid.
    log.info("Phase 2.8.5 — pooled_soft leg...")
    pooled_soft_trades, pooled_soft_meta = _produce_soft_trades(
        joined, spreads, refit_ts, regime_mode="pooled"
    )
    pooled_soft_block = _aggregate_soft(pooled_soft_trades, pooled_soft_meta, "pooled")

    # Baseline: regime-UNAWARE 252d rolling z-score on each spread
    if refit_ts:
        baseline_start = refit_ts[0]
        baseline_end   = max(refit_ts[-1] if len(refit_ts) > 1 else joined.index.max(),
                             joined.index.max())
        log.info("Building regime-unaware baseline trades over (%s, %s]",
                 baseline_start.date(), baseline_end.date())
        baseline = _baseline_trades(spreads, baseline_start, baseline_end)
        log.info("  %d baseline records", len(baseline))
    else:
        baseline = []

    base_overall   = _metrics(baseline)
    base_by_spread = _by(baseline, "spread")

    # Phase 2.6 gated-blend leg — for each (date, spread): use pooled signal
    # only when it passes the production gate; else fall back to baseline.
    log.info("Building Phase 2.6 gated-blend leg...")
    gated_trades = _build_gated_blend(pooled_trades, baseline)
    # Reuse pooled refit_meta so the gated leg surfaces the same refit cadence.
    gated_block = _aggregate_mode(gated_trades, pooled_block["refits"], "gated_blend")
    gated_block["by_source"]        = _by_source(gated_trades)
    gated_block["by_spread_source"] = _by_spread_source(gated_trades)
    gated_block["gate"] = {
        "regime":   GATED_REGIME,
        "winners":  sorted(GATED_WINNERS),
        "z_thresh": GATED_Z_THRESHOLD,
        "note":     "Pooled signal used only when regime_pooled=='BACK' AND winner_model ∈ {Lasso, Huber} AND |z|≥0.5σ; otherwise 252d rolling-z baseline.",
    }
    # Count how often the gate fired (where regime leg overrode baseline).
    n_regime    = sum(1 for t in gated_trades if t.get("source") == "regime")
    n_baseline  = sum(1 for t in gated_trades if t.get("source") == "baseline")
    gated_block["gate_counts"] = {
        "regime_fires":     n_regime,
        "baseline_fallback":n_baseline,
        "regime_share":     round(n_regime / max(len(gated_trades), 1), 4),
    }
    log.info("  gated leg: %d records  regime=%d  baseline=%d",
             len(gated_trades), n_regime, n_baseline)

    # Persist the raw gated trades so future sized-blend experiments can be
    # post-processed (Kelly tuning, half→quarter, per-spread thresholds, …)
    # without re-running the ~40-min walk-forward.
    try:
        _GATED_TRADES_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_GATED_TRADES_FILE, "w") as f:
            json.dump(gated_trades, f, default=str)
        log.info("  saved raw gated trades → %s", _GATED_TRADES_FILE)
    except Exception as exc:  # pragma: no cover — disk-only failure
        log.warning("  failed to save gated trades: %s", exc)

    # ── Phase 2.7 — sized variants (post-processing on gated_trades) ────────
    log.info("Building Phase 2.7 sized variants on gated leg...")
    kelly_lookup = _compute_kelly_by_cutoff(gated_trades, refit_ts)
    sized_blocks: dict[str, dict] = {}
    for mode in SIZING_MODES:
        sized_trades = _apply_sizing(gated_trades, mode, refit_ts, kelly_lookup)
        blk = _aggregate_mode(sized_trades, pooled_block["refits"], f"sized_{mode}")
        blk["by_source"]        = _by_source(sized_trades)
        blk["by_spread_source"] = _by_spread_source(sized_trades)
        regime_scales = [t.get("sizing_scale", 1.0) for t in sized_trades if t.get("source") == "regime"]
        if regime_scales:
            blk["mean_regime_scale"]   = round(float(np.mean(regime_scales)), 4)
            blk["median_regime_scale"] = round(float(np.median(regime_scales)), 4)
        else:
            blk["mean_regime_scale"] = blk["median_regime_scale"] = None
        sized_blocks[mode] = blk
        log.info("  sized[%s]: n=%d signals=%d sharpe=%s mean_pnl=%s max_dd=%s",
                 mode, blk["n_trades"], blk["overall"]["n_signals"],
                 blk["overall"]["sharpe"], blk["overall"]["mean_pnl"],
                 blk["overall"]["max_drawdown"])

    # ── Phase 2.8.6 — Apply transaction costs to every mode ────────────────
    # Cost model lives in COST_PER_SPREAD_RT; scales with sizing_scale on
    # regime rows. NEUTRAL trades incur no cost. Net metrics live under
    # report["costs"] so the gross blocks above stay back-compatible.
    log.info("Phase 2.8.6 — computing NET metrics under transaction costs...")
    costs_block = {
        "model_doc":      (
            "Per-leg per-side: $0.0025 commission/clearing/brokerage + "
            "half-spread slippage ($0.0050/bbl front / $0.0075/bbl deferred). "
            "Round-trip cost = N legs × 2 sides × (commission + half-spread). "
            "2-leg M1-M2 = $0.030/bbl RT; 2-leg M3-M6 = $0.040; 3-leg fly = $0.050. "
            "Cost scales with sizing_scale on regime rows. NEUTRAL trades cost zero."
        ),
        "per_spread_rt":  dict(COST_PER_SPREAD_RT),
        "default_rt":     COST_DEFAULT_RT,
        "composite_net":  _net_block(composite_trades),
        "pooled_net":     _net_block(pooled_trades),
        "baseline_net":   _net_block(baseline),
        "global_net":     _net_block(global_trades),
        "pooled_soft_net":_net_block(pooled_soft_trades),
        "gated_blend_net":_net_block(gated_trades, include_source=True),
        "sized_blend_net":{
            mode: _net_block(_apply_sizing(gated_trades, mode, refit_ts, kelly_lookup),
                             include_source=True)
            for mode in SIZING_MODES
        },
    }
    # Headline lift NET (gated vs baseline) at the by-spread + overall level
    costs_block["lift_gated_vs_baseline_net"] = _lift(
        costs_block["gated_blend_net"],
        costs_block["baseline_net"]["by_spread"],
        costs_block["baseline_net"]["overall"],
    )
    # Phase 2.8.4 — global vs baseline NET lift
    costs_block["lift_global_vs_baseline_net"] = _lift(
        costs_block["global_net"],
        costs_block["baseline_net"]["by_spread"],
        costs_block["baseline_net"]["overall"],
    )
    # Phase 2.8.5 — soft pooled vs baseline NET lift
    costs_block["lift_pooled_soft_vs_baseline_net"] = _lift(
        costs_block["pooled_soft_net"],
        costs_block["baseline_net"]["by_spread"],
        costs_block["baseline_net"]["overall"],
    )
    for mode in SIZING_MODES:
        costs_block[f"lift_sized_{mode}_vs_baseline_net"] = _lift(
            costs_block["sized_blend_net"][mode],
            costs_block["baseline_net"]["by_spread"],
            costs_block["baseline_net"]["overall"],
        )

    # Persist raw trade tapes for composite + pooled + baseline so future cost
    # re-aggregations (different cost model, per-spread overrides, etc.) can
    # run without retraining the ~3h walk-forward. Gated tape is already saved
    # above.
    for path, tape in (
        (_COMPOSITE_TRADES_FILE,     composite_trades),
        (_POOLED_TRADES_FILE,        pooled_trades),
        (_BASELINE_TRADES_FILE,      baseline),
        (_GLOBAL_TRADES_FILE,        global_trades),
        (_POOLED_SOFT_TRADES_FILE,   pooled_soft_trades),
    ):
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w") as f:
                json.dump(tape, f, default=str)
            log.info("  saved %s (%d rows)", path.name, len(tape))
        except Exception as exc:  # pragma: no cover — disk-only failure
            log.warning("  failed to save %s: %s", path.name, exc)

    # Per-spread Kelly fractions at the LAST refit boundary — what live
    # inference would apply going forward.
    last_kelly = kelly_lookup[refit_ts[-1].strftime("%Y-%m-%d")] if refit_ts else {}
    sized_summary = {
        "modes":             list(SIZING_MODES),
        "kelly_floor":       SIZING_KELLY_FLOOR,
        "kelly_cap":         SIZING_KELLY_CAP,
        "kelly_default":     SIZING_KELLY_DEFAULT,
        "kelly_min_n":       SIZING_KELLY_MIN_N,
        "kelly_per_spread_latest": last_kelly,
        "kelly_per_cutoff":  kelly_lookup,
        "method":            "Sized blend: gated_blend trade tape with regime-leg fwd_pnl scaled by mode. full=1.0 (sanity); half=0.5; kelly=per-spread Kelly fraction on prior closed regime-leg trades, expanding window across refit boundaries, clamped to [0.10, 1.00], default 0.50 when n<5. Baseline leg always 1.0.",
    }

    report = {
        "generated_at":   datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "method":         "Walk-forward expanding-window: at each quarterly refit, retrain per-(spread, regime) cells on data ≤ cutoff via the Ridge/Lasso/ElasticNet/Huber competition; predict daily through next cutoff; signal = ±0.5σ z-score; PnL = sign × 20-trading-day spread move. Run for BOTH regime modes (composite 27-cell, pooled 3-cell curve-axis-only) PLUS a Phase 2.6 gated_blend leg that takes the pooled signal only when regime_pooled=='BACK' AND winner ∈ {Lasso, Huber} AND |z|≥0.5σ, else falls back to the 252d rolling-z baseline. Phase 2.7 sized_blend leg scales the regime-leg notional by {full=1.0, half=0.5, kelly=per-spread Kelly on prior closed regime-leg PnLs} with the baseline leg fixed at 1.0. Baseline = regime-unaware 252-day rolling z-score on the same spreads.",
        "config": {
            "forward_days":  FORWARD_DAYS,
            "min_samples":   MIN_SAMPLES,
            "z_entry":       Z_ENTRY,
            "rolling_win":   ROLLING_WIN,
            "refit_dates":   REFIT_DATES,
            "regime_modes":  ["composite", "pooled", "gated_blend", "sized_blend", "global", "pooled_soft"],
            "gated_blend": {
                "regime":   GATED_REGIME,
                "winners":  sorted(GATED_WINNERS),
                "z_thresh": GATED_Z_THRESHOLD,
            },
            "sized_blend": {
                "modes":         list(SIZING_MODES),
                "kelly_floor":   SIZING_KELLY_FLOOR,
                "kelly_cap":     SIZING_KELLY_CAP,
                "kelly_default": SIZING_KELLY_DEFAULT,
                "kelly_min_n":   SIZING_KELLY_MIN_N,
            },
        },
        # --- Phase 2.5 + 2.6 + 2.7 layout: a block per mode + baseline ---
        "composite":          composite_block,
        "pooled":             pooled_block,
        "gated_blend":        gated_block,
        "sized_blend":        sized_blocks,
        "sized_blend_summary": sized_summary,
        "baseline_overall":   base_overall,
        "baseline_by_spread": base_by_spread,
        "n_baseline":         len(baseline),
        # --- Phase 2.8.4 — one global model per spread w/ regime-as-feature ---
        "global":             global_block,
        # --- Phase 2.8.5 — soft pooled posterior (logistic transitions at threshold) ---
        "pooled_soft":        pooled_soft_block,
        # --- Phase 2.8.6 transaction-cost NET aggregates ---
        "costs":              costs_block,
        "lift_composite_vs_baseline":   _lift(composite_block,       base_by_spread, base_overall),
        "lift_pooled_vs_baseline":      _lift(pooled_block,          base_by_spread, base_overall),
        "lift_gated_vs_baseline":       _lift(gated_block,           base_by_spread, base_overall),
        "lift_global_vs_baseline":      _lift(global_block,          base_by_spread, base_overall),
        "lift_pooled_soft_vs_baseline": _lift(pooled_soft_block,     base_by_spread, base_overall),
        "lift_sized_half_vs_baseline":  _lift(sized_blocks["half"],  base_by_spread, base_overall),
        "lift_sized_kelly_vs_baseline": _lift(sized_blocks["kelly"], base_by_spread, base_overall),
        "lift_sized_half_vs_gated":     _lift(sized_blocks["half"],  gated_block.get("by_spread", {}), gated_block.get("overall", {})),
        "lift_sized_kelly_vs_gated":    _lift(sized_blocks["kelly"], gated_block.get("by_spread", {}), gated_block.get("overall", {})),
        "lift_pooled_vs_composite":     _lift(pooled_block,          composite_block.get("by_spread", {}), composite_block.get("overall", {})),
        "lift_gated_vs_pooled":         _lift(gated_block,           pooled_block.get("by_spread", {}),    pooled_block.get("overall", {})),

        # --- Sprint 4 back-compat keys: surface composite at the top level so
        # any external consumer (PDF first cut, /api/regime/walkforward) keeps
        # working without code changes. ---
        "overall":        composite_block["overall"],
        "by_spread":      composite_block["by_spread"],
        "by_curve_axis":  composite_block["by_curve_axis"],
        "by_winner":      composite_block["by_winner"],
        "by_direction":   composite_block["by_direction"],
        "refits":         composite_block["refits"],
        "n_trades":       composite_block["n_trades"],
        "lift_vs_baseline": _lift_legacy(composite_block.get("by_spread", {}), base_by_spread),
    }

    _REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_REPORT_FILE, "w") as f:
        json.dump(report, f, indent=2, default=str)
    log.info("Saved walk-forward report → %s", _REPORT_FILE)
    return report


def _lift_legacy(by_spread: dict, base_by_spread: dict) -> dict:
    """Sprint 4 legacy lift schema (key names preserved for back-compat)."""
    out = {}
    for sp, r in by_spread.items():
        b = base_by_spread.get(sp, {})
        out[sp] = {
            "regime_hit_rate":   r.get("hit_rate"),
            "baseline_hit_rate": b.get("hit_rate"),
            "regime_mean_pnl":   r.get("mean_pnl"),
            "baseline_mean_pnl": b.get("mean_pnl"),
            "regime_sharpe":     r.get("sharpe"),
            "baseline_sharpe":   b.get("sharpe"),
            "regime_n":          r.get("n_signals"),
            "baseline_n":        b.get("n_signals"),
        }
    return out


def load_report() -> dict | None:
    if _REPORT_FILE.exists():
        with open(_REPORT_FILE) as f:
            return json.load(f)
    return None


def run_global_only() -> dict:
    """
    Phase 2.8.4 — train + evaluate ONLY the global (regime-as-feature) leg
    and merge the result into the existing walkforward_report.json. Lets us
    add the new leg without re-running the ~3-h full walk-forward, since
    composite / pooled / baseline / gated / sized blocks are unaffected.
    """
    from research.features        import build_features
    from research.spread_universe import build_spread_series

    existing = load_report()
    if existing is None:
        raise RuntimeError(
            "walkforward_report.json missing — run the full walk-forward first "
            "(python -m backend.research.walkforward), then re-run with --global-only "
            "if you only want to refresh the global leg."
        )

    log.info("Building feature matrix + spread universe...")
    features = build_features()
    spreads  = build_spread_series()
    joined   = features.join(spreads, how="inner")

    refit_ts = [pd.Timestamp(d) for d in REFIT_DATES]
    refit_ts = [t for t in refit_ts if t >= joined.index.min() and t <= joined.index.max()]

    global_trades, global_meta = _produce_global_trades(joined, spreads, refit_ts)
    global_block = _aggregate_global(global_trades, global_meta)
    global_net   = _net_block(global_trades)

    # Persist raw trades.
    try:
        _GLOBAL_TRADES_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_GLOBAL_TRADES_FILE, "w") as f:
            json.dump(global_trades, f, default=str)
        log.info("  saved %s (%d rows)", _GLOBAL_TRADES_FILE.name, len(global_trades))
    except Exception as exc:
        log.warning("  failed to save %s: %s", _GLOBAL_TRADES_FILE.name, exc)

    base_by_spread = existing.get("baseline_by_spread") or {}
    base_overall   = existing.get("baseline_overall")   or {}
    base_net       = (existing.get("costs") or {}).get("baseline_net") or {}

    existing["global"] = global_block
    existing["lift_global_vs_baseline"] = _lift(global_block, base_by_spread, base_overall)

    costs = existing.setdefault("costs", {})
    costs["global_net"] = global_net
    costs["lift_global_vs_baseline_net"] = _lift(
        global_net,
        base_net.get("by_spread", {}),
        base_net.get("overall", {}),
    )

    # Update config record so consumers know global is part of the report now.
    cfg = existing.setdefault("config", {})
    modes = cfg.get("regime_modes") or []
    if "global" not in modes:
        cfg["regime_modes"] = list(modes) + ["global"]

    # Stamp the merge so the regenerated PDF reflects the new run, not the
    # original 2026-06-15 timestamp.
    existing["generated_at"] = datetime.utcnow().isoformat(timespec="seconds") + "Z"

    _REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_REPORT_FILE, "w") as f:
        json.dump(existing, f, indent=2, default=str)
    log.info("Saved walk-forward report (global leg merged) → %s", _REPORT_FILE)
    return existing


def run_soft_only(modes: tuple[str, ...] = ("pooled",)) -> dict:
    """
    Phase 2.8.5 — produce ONLY the soft-posterior leg(s) and merge into the
    existing walkforward_report.json. Per-cell models aren't persisted across
    runs, so we retrain via `_train_cells_through` at each refit and evaluate
    with `_evaluate_window_soft`. Composite mode is heavier (27 cells × 6
    spreads × 34 refits ≈ 5,500 cell trainings vs ~600 for pooled), so the
    default is pooled only — pass modes=("pooled","composite") to do both.
    """
    from research.features        import build_features
    from research.spread_universe import build_spread_series

    for m in modes:
        if m not in ("pooled", "composite"):
            raise ValueError(f"unknown soft regime_mode {m!r}")

    existing = load_report()
    if existing is None:
        raise RuntimeError(
            "walkforward_report.json missing — run the full walk-forward first "
            "(python -m backend.research.walkforward), then re-run with "
            "--soft-only if you only want to refresh the soft leg."
        )

    log.info("Building feature matrix + spread universe...")
    features = build_features()
    spreads  = build_spread_series()
    joined   = features.join(spreads, how="inner")
    log.info("  features: %d rows  spreads: %d rows  joined: %d rows",
             len(features), len(spreads), len(joined))

    refit_ts = [pd.Timestamp(d) for d in REFIT_DATES]
    refit_ts = [t for t in refit_ts if t >= joined.index.min() and t <= joined.index.max()]

    base_by_spread = existing.get("baseline_by_spread") or {}
    base_overall   = existing.get("baseline_overall")   or {}
    base_net       = (existing.get("costs") or {}).get("baseline_net") or {}
    costs          = existing.setdefault("costs", {})
    cfg            = existing.setdefault("config", {})
    cfg_modes      = list(cfg.get("regime_modes") or [])

    tape_paths = {
        "pooled":    _POOLED_SOFT_TRADES_FILE,
        "composite": _COMPOSITE_SOFT_TRADES_FILE,
    }
    summary: dict[str, dict] = {}

    for m in modes:
        log.info("Phase 2.8.5 — %s_soft leg...", m)
        trades, meta = _produce_soft_trades(joined, spreads, refit_ts, regime_mode=m)
        block = _aggregate_soft(trades, meta, regime_mode=m)
        net   = _net_block(trades)

        key      = f"{m}_soft"
        net_key  = f"{m}_soft_net"
        lift_key = f"lift_{m}_soft_vs_baseline"
        lift_net_key = f"lift_{m}_soft_vs_baseline_net"

        existing[key]      = block
        existing[lift_key] = _lift(block, base_by_spread, base_overall)
        costs[net_key]     = net
        costs[lift_net_key] = _lift(net, base_net.get("by_spread", {}), base_net.get("overall", {}))

        if key not in cfg_modes:
            cfg_modes.append(key)

        # Persist raw tape so future cost re-aggregations don't reretain.
        path = tape_paths[m]
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w") as f:
                json.dump(trades, f, default=str)
            log.info("  saved %s (%d rows)", path.name, len(trades))
        except Exception as exc:
            log.warning("  failed to save %s: %s", path.name, exc)

        summary[m] = {
            "gross_sharpe": block["overall"].get("sharpe"),
            "net_sharpe":   net["overall"].get("sharpe"),
            "n_signals":    net["overall"].get("n_signals"),
        }

    cfg["regime_modes"] = cfg_modes

    # Stamp the merge so the regenerated PDF reflects the new run.
    existing["generated_at"] = datetime.utcnow().isoformat(timespec="seconds") + "Z"

    _REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_REPORT_FILE, "w") as f:
        json.dump(existing, f, indent=2, default=str)
    log.info("Saved walk-forward report (soft leg merged) → %s", _REPORT_FILE)
    return existing


# ─────────────────────────────────────────────────────────────────────────────
# Phase 5 — Multi-horizon sweep (2.8.7)
# ─────────────────────────────────────────────────────────────────────────────
# The base walk-forward trades a single 20-trading-day forward horizon. But the
# regime/baseline models predict the *contemporaneous fair value* of the spread
# (a mean-reversion target), so the ENTRY signal (z → direction) is identical at
# every horizon — only the HOLD/EXIT horizon changes the realised PnL. That makes
# the sweep a pure post-processing pass over the already-validated trade tapes:
# for each fired trade we recompute fwd_pnl = sign × (spread[d+H] − spread[d]) at
# H ∈ {5, 10, 20, 30} from the freshly-built spread series, then re-aggregate NET
# of the same per-spread cost model with a horizon-aware Sharpe annualisation
# (√(252/H)). No retraining; the signals are bit-for-bit the ones the leg fired.
#
# Honest caveats carried into the report:
#   • Overlapping fills: trades fire daily, so a 30-day hold overlaps the next
#     ~30 trades. The base walk-forward already treats each (date, spread) as an
#     independent fill at 20d; we keep that convention so the horizons are
#     mutually comparable (it inflates Sharpe equally across horizons — read the
#     RANKING across H, not the absolute level).
#   • Round-trip cost is horizon-independent (one entry + one exit regardless of
#     hold length), so longer horizons amortise the same cost over a larger move.
HORIZON_SWEEP = (5, 10, 20, 30)
# A horizon's per-spread NET Sharpe is only eligible to be the "best" if it has
# at least this many fired signals — guards against a 3-trade horizon winning on
# noise.
HORIZON_MIN_SIGNALS = 25


def _spread_lookup(spreads: pd.DataFrame) -> dict[str, tuple[np.ndarray, dict]]:
    """Per-spread (values, {normalised_date -> position}) over the dropna'd
    series, so the horizon recompute is O(1) per (trade, horizon)."""
    out: dict[str, tuple[np.ndarray, dict]] = {}
    for sp in spreads.columns:
        s = spreads[sp].dropna()
        pos = {ts.normalize(): i for i, ts in enumerate(s.index)}
        out[sp] = (s.values.astype(float), pos)
    return out


def _recompute_horizon_pnls(
    trades: list[dict],
    lookup: dict[str, tuple[np.ndarray, dict]],
    horizons: tuple[int, ...] = HORIZON_SWEEP,
) -> list[dict]:
    """
    For each trade row, recompute sign × (spread[d+H] − spread[d]) at every H.
    Returns compact rows {date, spread, direction, pnl_h{H}: float|None}.
    NEUTRAL rows carry all-None pnls (counted as no-fill downstream).
    """
    out: list[dict] = []
    for t in trades:
        sp        = t.get("spread")
        direction = t.get("direction")
        if sp not in lookup:
            continue
        sign = +1 if direction == "BUY" else (-1 if direction == "SELL" else 0)
        try:
            d = pd.Timestamp(t["date"]).normalize()
        except Exception:
            continue
        arr, pos = lookup[sp]
        i = pos.get(d)
        row = {"date": t["date"], "spread": sp, "direction": direction}
        for H in horizons:
            key = f"pnl_h{H}"
            if sign == 0 or i is None or i + H >= len(arr):
                row[key] = None
            else:
                row[key] = round(float(sign * (arr[i + H] - arr[i])), 4)
        out.append(row)
    return out


def _horizon_metrics(rows: list[dict], horizon: int, pnl_key: str) -> dict:
    """
    NET metrics on a horizon's recomputed PnL column. Mirrors `_metrics` but
    (a) reads `pnl_key` instead of `fwd_pnl`, (b) annualises Sharpe by √(252/H),
    (c) subtracts the per-spread round-trip cost (sizing_scale=1.0 on these
    tapes). Hit-rate is on NET PnL, same as the cost-aware `_metrics`.
    """
    fired = [r for r in rows if r.get("direction") != "NEUTRAL" and r.get(pnl_key) is not None]
    n_neutral = sum(1 for r in rows if r.get("direction") == "NEUTRAL")
    if not fired:
        return {"n_signals": 0, "n_total": len(rows), "n_neutral": n_neutral,
                "hit_rate": None, "mean_pnl": None, "median_pnl": None,
                "total_pnl": 0.0, "sharpe": None, "gross_sharpe": None,
                "max_drawdown": None, "mean_cost": None, "total_cost": 0.0}
    gross = np.array([float(r[pnl_key]) for r in fired], dtype=float)
    costs = np.array([COST_PER_SPREAD_RT.get(r.get("spread"), COST_DEFAULT_RT) for r in fired],
                     dtype=float)
    pnls  = gross - costs
    cum   = np.cumsum(pnls); peak = np.maximum.accumulate(cum)
    max_dd = float((cum - peak).min()) if len(cum) else 0.0
    ann = np.sqrt(252.0 / horizon)
    mu  = float(pnls.mean()); sd = float(pnls.std(ddof=1)) if len(pnls) > 1 else 0.0
    gmu = float(gross.mean()); gsd = float(gross.std(ddof=1)) if len(gross) > 1 else 0.0
    return {
        "n_signals":    len(fired),
        "n_total":      len(rows),
        "n_neutral":    n_neutral,
        "hit_rate":     round(float((pnls > 0).mean()), 4),
        "mean_pnl":     round(mu, 4),
        "median_pnl":   round(float(np.median(pnls)), 4),
        "total_pnl":    round(float(pnls.sum()), 4),
        "sharpe":       round((mu / sd) * ann, 3) if sd > 0 else None,
        "gross_sharpe": round((gmu / gsd) * ann, 3) if gsd > 0 else None,
        "max_drawdown": round(max_dd, 4),
        "mean_cost":    round(float(costs.mean()), 4),
        "total_cost":   round(float(costs.sum()), 4),
    }


def _aggregate_horizon(
    rows_by_source: dict[str, list[dict]],
    horizons: tuple[int, ...] = HORIZON_SWEEP,
) -> dict:
    """Build the horizon_sweep report block from recomputed per-source rows."""
    from research.spread_universe import INSTRUMENTS

    by_source: dict[str, dict] = {}
    for source, rows in rows_by_source.items():
        overall_by_h = {str(H): _horizon_metrics(rows, H, f"pnl_h{H}") for H in horizons}
        by_spread: dict[str, dict] = {}
        for sp in INSTRUMENTS:
            sp_rows = [r for r in rows if r.get("spread") == sp]
            if not sp_rows:
                continue
            by_spread[sp] = {str(H): _horizon_metrics(sp_rows, H, f"pnl_h{H}") for H in horizons}
        # Best NET-Sharpe horizon per spread (eligible only if ≥ MIN_SIGNALS).
        best: dict[str, dict] = {}
        for sp, perh in by_spread.items():
            ref20 = (perh.get("20") or {}).get("sharpe")
            elig = [(H, perh[str(H)]["sharpe"]) for H in horizons
                    if perh[str(H)]["sharpe"] is not None
                    and (perh[str(H)]["n_signals"] or 0) >= HORIZON_MIN_SIGNALS]
            if not elig:
                best[sp] = {"horizon": None, "net_sharpe": None,
                            "default_20d_net_sharpe": ref20, "delta_vs_20d": None}
                continue
            bh, bs = max(elig, key=lambda kv: kv[1])
            best[sp] = {
                "horizon":                bh,
                "net_sharpe":             bs,
                "default_20d_net_sharpe": ref20,
                "delta_vs_20d":           round(bs - ref20, 3) if ref20 is not None else None,
            }
        by_source[source] = {
            "overall_by_horizon":     overall_by_h,
            "by_spread":              by_spread,
            "best_horizon_by_spread": best,
        }
    return {
        "horizons":   list(horizons),
        "sources":    list(rows_by_source.keys()),
        "min_signals_for_best": HORIZON_MIN_SIGNALS,
        "cost_model": dict(COST_PER_SPREAD_RT),
        "note": (
            "Phase 5 (2.8.7) — exit-horizon sweep. Entry signal (z→direction) is "
            "horizon-independent (models predict contemporaneous fair value); only the "
            "hold/exit horizon varies the realised PnL. Pure post-processing over the "
            "validated baseline/global trade tapes — no retraining. NET of the same "
            "per-spread RT cost (horizon-independent: one round trip). Sharpe annualised "
            "√(252/H). Overlapping-fill convention matches the base walk-forward, so read "
            "the RANKING of horizons per spread, not the absolute Sharpe level."
        ),
        "by_source":  by_source,
    }


def run_horizon_only(
    horizons: tuple[int, ...] = HORIZON_SWEEP,
    sources: tuple[str, ...] = ("baseline", "global"),
) -> dict:
    """
    Phase 5 (2.8.7) — recompute every fired signal's PnL at H ∈ horizons over
    the persisted baseline/global trade tapes and merge a `horizon_sweep` block
    into walkforward_report.json. No model retraining: the spread series is
    rebuilt and forward moves re-read at each horizon. Pure additive leg.
    """
    from research.spread_universe import build_spread_series

    existing = load_report()
    if existing is None:
        raise RuntimeError(
            "walkforward_report.json missing — run the full walk-forward first, "
            "then re-run with --horizon-only."
        )

    tape_files = {
        "baseline": _BASELINE_TRADES_FILE,
        "global":   _GLOBAL_TRADES_FILE,
        "pooled":   _POOLED_TRADES_FILE,
        "gated":    _GATED_TRADES_FILE,
    }

    log.info("Building spread universe for horizon recompute...")
    spreads = build_spread_series()
    lookup  = _spread_lookup(spreads)

    rows_by_source: dict[str, list[dict]] = {}
    persisted_tape: list[dict] = []
    for src in sources:
        path = tape_files.get(src)
        if path is None or not path.exists():
            log.warning("  horizon: tape for source %r missing (%s) — skipping", src, path)
            continue
        with open(path) as f:
            tape = json.load(f)
        rows = _recompute_horizon_pnls(tape, lookup, horizons)
        rows_by_source[src] = rows
        for r in rows:
            persisted_tape.append({**r, "source": src})
        log.info("  horizon[%s]: %d tape rows → %d recomputed", src, len(tape), len(rows))

    if not rows_by_source:
        raise RuntimeError("horizon sweep: no source tapes found to post-process")

    block = _aggregate_horizon(rows_by_source, horizons)
    existing["horizon_sweep"] = block

    cfg = existing.setdefault("config", {})
    cfg["horizon_sweep"] = {"horizons": list(horizons), "sources": list(rows_by_source.keys())}

    try:
        _HORIZON_TRADES_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_HORIZON_TRADES_FILE, "w") as f:
            json.dump(persisted_tape, f, default=str)
        log.info("  saved %s (%d rows)", _HORIZON_TRADES_FILE.name, len(persisted_tape))
    except Exception as exc:  # pragma: no cover — disk-only failure
        log.warning("  failed to save %s: %s", _HORIZON_TRADES_FILE.name, exc)

    existing["generated_at"] = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    _REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_REPORT_FILE, "w") as f:
        json.dump(existing, f, indent=2, default=str)
    log.info("Saved walk-forward report (horizon sweep merged) → %s", _REPORT_FILE)
    return existing


# ─────────────────────────────────────────────────────────────────────────────
# Phase 5 — Feature selection (Lasso stability selection)
# ─────────────────────────────────────────────────────────────────────────────
# The global leg trains one model per spread on all 22 (Brent) / 24 (WTI) base
# features + 9 regime one-hots. Many are correlated commodity series; if a leaner
# set holds the NET Sharpe it's strictly more interpretable. We pick the lean set
# with textbook STABILITY SELECTION (Meinshausen & Bühlmann 2010): fit a scaled
# Lasso per spread at every walk-forward refit cutoff and record which base
# features survive (|coef| > tol). A feature's SELECTION FREQUENCY across the 34
# refits is its stability; we keep features stable in ≥ 50% of refits (floor:
# the top-6 by mean |coef| so no spread is starved). The 9 regime one-hots are
# always retained — they're the regime information the global leg exists to carry,
# and they're cheap. We then re-run the global walk-forward on the lean per-spread
# sets and compare NET Sharpe vs full-global and baseline.
FEATSEL_FREQ_THRESH = 0.5
FEATSEL_MIN_KEEP    = 6
FEATSEL_COEF_TOL    = 1e-6


def _stability_select(
    joined: pd.DataFrame,
    refit_ts: list[pd.Timestamp],
    spreads_list: list[str] | None = None,
    freq_thresh: float = FEATSEL_FREQ_THRESH,
    min_keep: int = FEATSEL_MIN_KEEP,
) -> dict:
    """
    Lasso stability selection per spread across all refit cutoffs. Returns
    {spread -> {selected, n_selected, n_base, freq{feat->frac}, mean_abs_coef,
                n_refits}}. The Lasso design includes the regime one-hots (so a
    base feature's coefficient is conditional on regime, matching the global
    leg) but selection is scored only over base features — one-hots are always
    retained downstream.
    """
    from research.models          import _fit_lasso
    from research.features        import predictors_for
    from research.spread_universe import INSTRUMENTS

    spreads_list = spreads_list if spreads_list is not None else list(INSTRUMENTS)
    out: dict[str, dict] = {}

    for spread in spreads_list:
        base_feats = predictors_for(spread)
        counts   = {f: 0   for f in base_feats}
        coef_sum = {f: 0.0 for f in base_feats}
        n_refits = 0
        for cutoff in refit_ts:
            train_df = joined[joined.index <= cutoff].copy()
            oh = train_df.apply(_regime_one_hot, axis=1, result_type="expand")
            for col in _REGIME_OH_COLS:
                train_df[col] = oh[col].astype(int) if col in oh.columns else 0
            feat_cols = base_feats + _REGIME_OH_COLS
            sub = train_df.dropna(subset=base_feats + [spread])
            if len(sub) < MIN_SAMPLES:
                continue
            X = sub[feat_cols].values
            y = sub[spread].values
            try:
                pipe = _fit_lasso(X, y)
                coefs = pipe.named_steps["model"].coef_
            except Exception:
                continue
            n_refits += 1
            for j, f in enumerate(base_feats):   # base feats are the leading cols
                c = abs(float(coefs[j]))
                coef_sum[f] += c
                if c > FEATSEL_COEF_TOL:
                    counts[f] += 1
        if n_refits == 0:
            out[spread] = {"selected": list(base_feats), "n_selected": len(base_feats),
                           "n_base": len(base_feats), "freq": {}, "mean_abs_coef": {},
                           "n_refits": 0,
                           "note": "no refit trained (insufficient rows) — fell back to full base set"}
            continue
        freq = {f: round(counts[f] / n_refits, 4) for f in base_feats}
        mean_abs = {f: round(coef_sum[f] / n_refits, 6) for f in base_feats}
        selected = [f for f in base_feats if freq[f] >= freq_thresh]
        if len(selected) < min_keep:
            selected = sorted(base_feats, key=lambda f: mean_abs[f], reverse=True)[:min_keep]
        # Preserve the canonical base-feature order for reproducibility.
        selected = [f for f in base_feats if f in set(selected)]
        out[spread] = {
            "selected":      selected,
            "n_selected":    len(selected),
            "n_base":        len(base_feats),
            "freq":          freq,
            "mean_abs_coef": mean_abs,
            "n_refits":      n_refits,
        }
    return out


def run_featsel_only() -> dict:
    """
    Phase 5 — stability-select a lean per-spread feature set, re-run the global
    walk-forward on it, and merge `feature_selection` + `global_lean` blocks into
    walkforward_report.json. Mirrors --global-only's merge pattern.
    """
    from research.features        import build_features
    from research.spread_universe import build_spread_series

    existing = load_report()
    if existing is None:
        raise RuntimeError(
            "walkforward_report.json missing — run the full walk-forward first, "
            "then re-run with --featsel-only."
        )

    log.info("Building feature matrix + spread universe...")
    features = build_features()
    spreads  = build_spread_series()
    joined   = features.join(spreads, how="inner")

    refit_ts = [pd.Timestamp(d) for d in REFIT_DATES]
    refit_ts = [t for t in refit_ts if t >= joined.index.min() and t <= joined.index.max()]

    log.info("Phase 5 — Lasso stability selection across %d refits...", len(refit_ts))
    sel = _stability_select(joined, refit_ts)
    base_feats_by_spread = {sp: sel[sp]["selected"] for sp in sel}
    for sp, info in sel.items():
        log.info("  [%s] kept %d/%d base feats: %s",
                 sp, info["n_selected"], info["n_base"], info["selected"])

    log.info("Phase 5 — lean global walk-forward...")
    lean_trades, lean_meta = _produce_global_trades(
        joined, spreads, refit_ts, base_feats_by_spread=base_feats_by_spread, tag="global_lean"
    )
    lean_block = _aggregate_global(lean_trades, lean_meta)
    lean_block["regime_mode"] = "global_lean"
    lean_block["feature_set"] = {
        "method":   "Lasso stability selection (≥{:.0%} of refits, floor top-{} by mean |coef|); 9 regime one-hots always retained.".format(
            FEATSEL_FREQ_THRESH, FEATSEL_MIN_KEEP),
        "per_spread_base_feats": base_feats_by_spread,
        "one_hot":  list(_REGIME_OH_COLS),
    }
    lean_net = _net_block(lean_trades)

    base_by_spread = existing.get("baseline_by_spread") or {}
    base_overall   = existing.get("baseline_overall")   or {}
    base_net       = (existing.get("costs") or {}).get("baseline_net") or {}
    full_global       = existing.get("global") or {}
    full_global_net   = (existing.get("costs") or {}).get("global_net") or {}

    existing["global_lean"] = lean_block
    existing["feature_selection"] = {
        "method": (
            "Stability selection (Meinshausen & Bühlmann): scaled Lasso fit per spread "
            "at every refit cutoff over the global design (base feats + 9 regime one-hots); "
            "a base feature is kept if its non-zero-coef SELECTION FREQUENCY across the "
            f"{len(refit_ts)} refits is ≥ {FEATSEL_FREQ_THRESH:.0%} (floor: top-{FEATSEL_MIN_KEEP} "
            "by mean |coef|). Regime one-hots always retained. The lean sets are then re-run "
            "through the global walk-forward → `global_lean`."
        ),
        "freq_thresh": FEATSEL_FREQ_THRESH,
        "min_keep":    FEATSEL_MIN_KEEP,
        "per_spread":  sel,
    }
    existing["lift_global_lean_vs_baseline"] = _lift(lean_block, base_by_spread, base_overall)
    if full_global.get("by_spread"):
        existing["lift_global_lean_vs_global"] = _lift(
            lean_block, full_global.get("by_spread", {}), full_global.get("overall", {})
        )

    costs = existing.setdefault("costs", {})
    costs["global_lean_net"] = lean_net
    costs["lift_global_lean_vs_baseline_net"] = _lift(
        lean_net, base_net.get("by_spread", {}), base_net.get("overall", {})
    )
    if full_global_net.get("by_spread"):
        costs["lift_global_lean_vs_global_net"] = _lift(
            lean_net, full_global_net.get("by_spread", {}), full_global_net.get("overall", {})
        )

    cfg = existing.setdefault("config", {})
    modes = cfg.get("regime_modes") or []
    if "global_lean" not in modes:
        cfg["regime_modes"] = list(modes) + ["global_lean"]

    try:
        _FEATSEL_TRADES_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_FEATSEL_TRADES_FILE, "w") as f:
            json.dump(lean_trades, f, default=str)
        log.info("  saved %s (%d rows)", _FEATSEL_TRADES_FILE.name, len(lean_trades))
    except Exception as exc:  # pragma: no cover — disk-only failure
        log.warning("  failed to save %s: %s", _FEATSEL_TRADES_FILE.name, exc)

    existing["generated_at"] = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    _REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_REPORT_FILE, "w") as f:
        json.dump(existing, f, indent=2, default=str)
    log.info("Saved walk-forward report (feature-selection leg merged) → %s", _REPORT_FILE)
    return existing


# ─────────────────────────────────────────────────────────────────────────────
# Phase 6 — data-driven HMM / change-point regimes (2.8.9)
# ─────────────────────────────────────────────────────────────────────────────
# The Phase 2 grid splits the curve axis on HARD trader thresholds
# (CONTANGO ≤ −$2 < NEUTRAL ≤ +$5 < BACK). This leg asks whether a *fitted*
# regime detector — a Gaussian mixture + causal sticky-HMM over the curve level
# and its 5-day change (research.regime_hmm) — discovers curve regimes that beat
# both the regime-unaware baseline and the hard-threshold pooled/global variants
# on NET Sharpe.
#
# It is the pooled-mode analog: K dense data-driven curve cells per spread
# instead of the 3 hard buckets. Same 7-model competition, same 20-day horizon,
# same NET cost model, same 34 quarterly refits. At each refit the GMM is fit on
# the training slice (≤ cutoff) and the forward window is labelled CAUSALLY (the
# forward filter at day d sees only data ≤ d). States are relabelled ordinally by
# curve level (R0 = deepest contango) so a cell trained for (spread, R1) at refit
# t is looked up correctly in t's window.
N_HMM_STATES_SWEEP = (2, 3, 4)   # state-count sensitivity sweep
N_HMM_HEADLINE     = 3           # matched to the 3 hard curve buckets


def _produce_hmm_trades(
    joined: pd.DataFrame,
    spreads: pd.DataFrame,
    refit_ts: list[pd.Timestamp],
    n_states: int = N_HMM_HEADLINE,
    *,
    stay: float = None,  # type: ignore[assignment]
) -> tuple[list[dict], list[dict]]:
    """
    Quarterly-refit driver for the data-driven HMM regime leg with `n_states`.
    Per refit: fit the detector on rows ≤ cutoff, label the whole series causally,
    train one cell per (spread, R-state), evaluate the forward window. Returns
    (trades, refit_meta) where each refit_meta row carries the detector's
    state-summary (curve-level means + implied boundaries vs the −$2/+$5 cuts).
    """
    from research.regime_hmm import CurveRegimeHMM, HMM_STAY_DEFAULT

    if stay is None:
        stay = HMM_STAY_DEFAULT

    all_trades: list[dict] = []
    refit_meta: list[dict] = []
    tag = f"hmm{n_states}"
    for i, cutoff in enumerate(refit_ts):
        next_cutoff = refit_ts[i + 1] if i + 1 < len(refit_ts) else joined.index.max()
        log.info("[%s] Refit %d/%d  cutoff=%s  window=(%s, %s]",
                 tag, i + 1, len(refit_ts), cutoff.date(),
                 cutoff.date(), next_cutoff.date())
        train = joined[joined.index <= cutoff]
        try:
            det = CurveRegimeHMM(n_states=n_states, stay=stay).fit(train)
        except Exception as exc:
            log.warning("  HMM fit failed at %s: %s — skipping refit", cutoff.date(), exc)
            continue
        labels = det.label_series(joined)            # causal ordinal labels
        jl = joined.copy()
        jl["regime_hmm"] = labels

        cells = _train_cells_through(
            jl, cutoff,
            regime_col="regime_hmm", regime_list=det.state_labels,
            enable_boosters=True,
        )
        window_trades = _evaluate_window(
            jl, spreads, cells, cutoff, next_cutoff, regime_col="regime_hmm"
        )
        log.info("  trained %d cells  evaluated %d records", len(cells), len(window_trades))

        winners: dict[str, int] = {}
        for _, c in cells.items():
            winners[c["winner"]] = winners.get(c["winner"], 0) + 1
        summ = det.state_summary()
        refit_meta.append({
            "cutoff":         cutoff.strftime("%Y-%m-%d"),
            "window_end":     next_cutoff.strftime("%Y-%m-%d"),
            "n_cells":        len(cells),
            "winners":        winners,
            "n_records":      len(window_trades),
            "state_summary":  summ,
        })
        all_trades.extend(window_trades)
    return all_trades, refit_meta


def _aggregate_hmm(trades: list[dict], refit_meta: list[dict], n_states: int) -> dict:
    """Aggregate the HMM leg into the standard mode-block schema (no curve-axis
    rollup — the regime labels are R0…R{K-1}, not CONTANGO/NEUTRAL/BACK)."""
    # Mean detector boundaries across refits — the data-driven analog of the
    # hard −$2/+$5 cuts, reported once at the leg level.
    bounds_by_pos: dict[int, list[float]] = {}
    means_acc: dict[str, list[float]] = {}
    for m in refit_meta:
        summ = m.get("state_summary") or {}
        for j, b in enumerate(summ.get("implied_boundaries") or []):
            bounds_by_pos.setdefault(j, []).append(b)
        for st, v in (summ.get("state_curve_means") or {}).items():
            means_acc.setdefault(st, []).append(v)
    mean_bounds = [round(float(np.mean(vs)), 3) for _, vs in sorted(bounds_by_pos.items())]
    mean_means  = {st: round(float(np.mean(vs)), 3) for st, vs in means_acc.items()}
    return {
        "regime_mode":  f"hmm{n_states}",
        "n_states":     n_states,
        "overall":      _metrics(trades),
        "by_spread":    _by(trades, "spread"),
        "by_regime":    _by(trades, "regime"),
        "by_winner":    _by(trades, "winner"),
        "by_direction": _by(trades, "direction"),
        "refits":       refit_meta,
        "n_trades":     len(trades),
        "detector": {
            "method":             "Gaussian mixture + causal sticky-HMM forward filter over [m1_m12, curve_chg_5d]; states relabelled ordinally by curve level. Fit per-refit on ≤cutoff; forward window labelled causally.",
            "features":           list(__import__("research.regime_hmm", fromlist=["CURVE_HMM_FEATURES"]).CURVE_HMM_FEATURES),
            "mean_curve_means":   mean_means,
            "mean_boundaries":    mean_bounds,
            "hard_thresholds":    [-2.0, 5.0],
            "note":               "Phase 6 (2.8.9) — data-driven curve regimes replacing the hard −$2/+$5 trader thresholds. mean_boundaries are the average implied cut points across refits.",
        },
    }


def run_hmm_only(states: tuple[int, ...] = N_HMM_STATES_SWEEP,
                 headline: int = N_HMM_HEADLINE) -> dict:
    """
    Phase 6 (2.8.9) — fit the data-driven HMM regime detector, run the per-cell
    walk-forward over its discovered regimes for each K in `states`, and merge an
    `hmm` block into walkforward_report.json. Mirrors --global-only's merge
    pattern: composite/pooled/baseline/gated/global blocks are untouched.

    The `headline` K (default 3, matched to the 3 hard curve buckets) is the
    primary block wired into the costs/lift tables; the other K's are kept under
    `hmm["state_sweep"]` as a state-count sensitivity check.
    """
    from research.features        import build_features
    from research.spread_universe import build_spread_series

    existing = load_report()
    if existing is None:
        raise RuntimeError(
            "walkforward_report.json missing — run the full walk-forward first, "
            "then re-run with --hmm-only."
        )
    if headline not in states:
        states = tuple(sorted(set(states) | {headline}))

    log.info("Building feature matrix + spread universe...")
    features = build_features()
    spreads  = build_spread_series()
    joined   = features.join(spreads, how="inner")
    log.info("  features: %d rows  spreads: %d rows  joined: %d rows",
             len(features), len(spreads), len(joined))

    refit_ts = [pd.Timestamp(d) for d in REFIT_DATES]
    refit_ts = [t for t in refit_ts if t >= joined.index.min() and t <= joined.index.max()]

    base_by_spread = existing.get("baseline_by_spread") or {}
    base_overall   = existing.get("baseline_overall")   or {}
    base_net       = (existing.get("costs") or {}).get("baseline_net") or {}

    blocks: dict[int, dict] = {}
    nets:   dict[int, dict] = {}
    headline_trades: list[dict] = []
    for K in states:
        log.info("Phase 6 — HMM leg, K=%d states...", K)
        trades, meta = _produce_hmm_trades(joined, spreads, refit_ts, n_states=K)
        blocks[K] = _aggregate_hmm(trades, meta, K)
        nets[K]   = _net_block(trades)
        if K == headline:
            headline_trades = trades

    # Headline block (matched-cardinality K) drives the costs/lift wiring.
    hmm_block = blocks[headline]
    hmm_net   = nets[headline]
    # State-count sensitivity: overall gross/NET Sharpe per K.
    state_sweep = {
        str(K): {
            "n_states":     K,
            "gross_sharpe": blocks[K]["overall"].get("sharpe"),
            "net_sharpe":   nets[K]["overall"].get("sharpe"),
            "n_signals":    nets[K]["overall"].get("n_signals"),
            "mean_boundaries": blocks[K]["detector"].get("mean_boundaries"),
        }
        for K in states
    }
    hmm_block["state_sweep"] = state_sweep
    hmm_block["headline_states"] = headline

    existing["hmm"] = hmm_block
    existing["lift_hmm_vs_baseline"] = _lift(hmm_block, base_by_spread, base_overall)

    costs = existing.setdefault("costs", {})
    costs["hmm_net"] = hmm_net
    costs["lift_hmm_vs_baseline_net"] = _lift(
        hmm_net, base_net.get("by_spread", {}), base_net.get("overall", {})
    )
    # Lift vs the hard-threshold pooled + global legs (the direct comparators).
    pooled_net = costs.get("pooled_net") or {}
    global_net = costs.get("global_net") or {}
    if pooled_net.get("by_spread"):
        costs["lift_hmm_vs_pooled_net"] = _lift(
            hmm_net, pooled_net.get("by_spread", {}), pooled_net.get("overall", {})
        )
    if global_net.get("by_spread"):
        costs["lift_hmm_vs_global_net"] = _lift(
            hmm_net, global_net.get("by_spread", {}), global_net.get("overall", {})
        )

    cfg = existing.setdefault("config", {})
    modes = cfg.get("regime_modes") or []
    if "hmm" not in modes:
        cfg["regime_modes"] = list(modes) + ["hmm"]
    cfg["hmm"] = {"states": list(states), "headline_states": headline}

    # Persist the headline-K tape so future cost re-aggregations don't retrain.
    try:
        _HMM_TRADES_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_HMM_TRADES_FILE, "w") as f:
            json.dump(headline_trades, f, default=str)
        log.info("  saved %s (%d rows)", _HMM_TRADES_FILE.name, len(headline_trades))
    except Exception as exc:  # pragma: no cover — disk-only failure
        log.warning("  failed to save %s: %s", _HMM_TRADES_FILE.name, exc)

    existing["generated_at"] = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    _REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_REPORT_FILE, "w") as f:
        json.dump(existing, f, indent=2, default=str)
    log.info("Saved walk-forward report (HMM leg merged) → %s", _REPORT_FILE)
    return existing


# ─────────────────────────────────────────────────────────────────────────────
# Phase 7 — portfolio vol-targeting (2.8.10)
# ─────────────────────────────────────────────────────────────────────────────
# Reweights the persisted gated trade tape into a vol-targeted book (pure
# post-processing, no retrain — same pattern as --horizon-only). Reuses
# shock_engine.risk_scale (per-position vol-target × stress de-risk) and
# gated_select.select_decorrelated (the desk's decorrelated book), plus a
# portfolio overlay that scales the whole book to a target book vol from the
# trailing correlation matrix. The four layers are toggled into ablation
# variants so the marginal contribution of each is visible. Honest question:
# does targeting portfolio vol beat the un-targeted gated/baseline book on NET
# Sharpe and shrink max-drawdown? (vol_target.py holds the sizing logic.)
_VOLTARGET_VARIANTS = ("decorrelated", "risk_parity", "parity_stress", "vol_target")


def _calmar(overall: dict) -> float | None:
    """Calmar = total NET PnL / |max drawdown| — leverage-invariant, so it's the
    cleanest cross-variant comparison when notionals differ."""
    tot = overall.get("total_pnl")
    dd  = overall.get("max_drawdown")
    if tot is None or dd is None or not dd:
        return None
    return round(float(tot) / abs(float(dd)), 3)


def _voltarget_summary(net_block: dict) -> dict:
    """Compact NET summary (overall) for one vol-target variant."""
    o = net_block.get("overall") or {}
    return {
        "n_signals":    o.get("n_signals"),
        "hit_rate":     o.get("hit_rate"),
        "mean_pnl":     o.get("mean_pnl"),
        "total_pnl":    o.get("total_pnl"),
        "sharpe":       o.get("sharpe"),
        "max_drawdown": o.get("max_drawdown"),
        "calmar":       _calmar(o),
    }


def _voltarget_cfg(name: str):
    """Build the VolTargetConfig for an ablation variant name."""
    from research.vol_target import VolTargetConfig
    flags = {
        "decorrelated":  dict(decorrelate=True,  vol_scale=False, stress=False, portfolio=False),
        "risk_parity":   dict(decorrelate=True,  vol_scale=True,  stress=False, portfolio=False),
        "parity_stress": dict(decorrelate=True,  vol_scale=True,  stress=True,  portfolio=False),
        "vol_target":    dict(decorrelate=True,  vol_scale=True,  stress=True,  portfolio=True),
    }[name]
    return VolTargetConfig(**flags)


def run_voltarget_only(headline: str = "vol_target") -> dict:
    """
    Phase 7 (2.8.10) — reweight the gated trade tape into vol-targeted books for
    each ablation variant, merge a `vol_target` block into walkforward_report.json.
    Mirrors --hmm-only's standalone-merge pattern: gated/baseline/global/etc.
    blocks are untouched. The `headline` variant (default the full overlay) drives
    the costs/lift wiring; the others are kept under `vol_target["variants"]`.
    """
    from research.spread_universe import build_spread_series
    from research import vol_target as vt
    from research import gated_select

    existing = load_report()
    if existing is None:
        raise RuntimeError(
            "walkforward_report.json missing — run the full walk-forward first, "
            "then re-run with --voltarget-only."
        )
    if not _GATED_TRADES_FILE.exists():
        raise RuntimeError(f"gated tape missing ({_GATED_TRADES_FILE}) — run the full walk-forward first.")

    log.info("Phase 7 — building spread vol / stress / correlation inputs...")
    spreads = build_spread_series()
    spread_vol = vt.spread_vol_frame(spreads)
    stress = vt.stress_series()
    corr = gated_select.instrument_corr_matrix()

    with open(_GATED_TRADES_FILE) as f:
        gated_tape = json.load(f)
    baseline_tape = []
    if _BASELINE_TRADES_FILE.exists():
        with open(_BASELINE_TRADES_FILE) as f:
            baseline_tape = json.load(f)

    # Reference books (unit notional) — recomputed here so all variants share the
    # same _metrics path and carry Calmar.
    variants: dict[str, dict] = {}
    gated_raw_net = _net_block(gated_tape)
    variants["gated_raw"]    = _voltarget_summary(gated_raw_net)
    if baseline_tape:
        variants["baseline_raw"] = _voltarget_summary(_net_block(baseline_tape))

    headline_net = None
    headline_tape: list[dict] = []
    for name in _VOLTARGET_VARIANTS:
        cfg = _voltarget_cfg(name)
        sized = vt.apply_vol_target(gated_tape, spread_vol=spread_vol, stress=stress,
                                    corr=corr, cfg=cfg)
        net = _net_block(sized)
        variants[name] = _voltarget_summary(net)
        log.info("  [%s] held=%d net_sharpe=%s maxDD=%s calmar=%s",
                 name, variants[name]["n_signals"], variants[name]["sharpe"],
                 variants[name]["max_drawdown"], variants[name]["calmar"])
        if name == headline:
            headline_net = net
            headline_tape = sized

    if headline_net is None:  # pragma: no cover — headline always in _VOLTARGET_VARIANTS
        raise RuntimeError(f"unknown headline variant {headline!r}")

    block = {
        "regime_mode":     "vol_target",
        "headline":        headline,
        "n_held":          variants[headline]["n_signals"],
        "overall":         headline_net["overall"],
        "by_spread":       headline_net["by_spread"],
        "variants":        variants,
        "config": {
            "vol_win":         vt.VOL_WIN,
            "stress_fit_until":vt.STRESS_FIT_UNTIL,
            "rho_max":         gated_select.DEFAULT_RHO_MAX,
            "target_n_bets":   vt.TARGET_N_BETS,
            "k_floor_cap":     [vt.K_FLOOR, vt.K_CAP],
            "median_spread_vol": round(float(np.nanmedian(spread_vol.values)), 4) if spread_vol.size else None,
            "variant_flags": {
                "decorrelated":  "decorrelation only (unit notional)",
                "risk_parity":   "+ per-position vol_scale (equal $/bbl risk)",
                "parity_stress": "+ stress de-risk into shocks",
                "vol_target":    "+ portfolio overlay to target book vol (headline)",
            },
        },
        "note": (
            "Phase 7 (2.8.10) — portfolio vol-targeting on the gated tape. Pure "
            "post-processing: same fired signals, reweighted notionals. Books "
            "normalised to mean notional 1.0 (matched avg exposure → max-DD "
            "comparable; Sharpe/Calmar leverage-invariant). Reuses shock_engine."
            "risk_scale + gated_select.select_decorrelated + a corr-based book "
            "overlay. Stress detector fit 2016→2019 (OOS for 2020+; 2018-19 tape "
            "rows see an in-sample stress read)."
        ),
    }
    existing["vol_target"] = block

    costs = existing.setdefault("costs", {})
    costs["vol_target_net"] = headline_net
    base_net = (costs.get("baseline_net") or {})
    gated_net = (costs.get("gated_blend_net") or {})
    if gated_net.get("by_spread"):
        existing.setdefault("lift_vol_target_vs_gated", _lift(
            headline_net, gated_net.get("by_spread", {}), gated_net.get("overall", {})))
    if base_net.get("by_spread"):
        existing.setdefault("lift_vol_target_vs_baseline", _lift(
            headline_net, base_net.get("by_spread", {}), base_net.get("overall", {})))

    cfg = existing.setdefault("config", {})
    modes = cfg.get("regime_modes") or []
    if "vol_target" not in modes:
        cfg["regime_modes"] = list(modes) + ["vol_target"]

    try:
        _VOLTARGET_TRADES_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_VOLTARGET_TRADES_FILE, "w") as f:
            json.dump(headline_tape, f, default=str)
        log.info("  saved %s (%d rows)", _VOLTARGET_TRADES_FILE.name, len(headline_tape))
    except Exception as exc:  # pragma: no cover — disk-only failure
        log.warning("  failed to save %s: %s", _VOLTARGET_TRADES_FILE.name, exc)

    existing["generated_at"] = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    _REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_REPORT_FILE, "w") as f:
        json.dump(existing, f, indent=2, default=str)
    log.info("Saved walk-forward report (vol-target leg merged) → %s", _REPORT_FILE)
    return existing


# ─────────────────────────────────────────────────────────────────────────────
# Phase 8 (2026-06-22) — per-spread gate (post-processing, no retrain — same
# standalone-merge pattern as --voltarget-only/--horizon-only). Replaces the
# uniform global gate with a per-spread enable decision made walk-forward: the
# regime leg fires for a spread only when its OOS NET Sharpe beat baseline for
# that spread BEFORE each refit cutoff (≥ GATE_MIN_N evidence). Reuses the
# persisted pooled + baseline tapes; the per-spread decision logic lives in
# gate_config.py (shared with live_ranker so the two can't drift).
# ─────────────────────────────────────────────────────────────────────────────
def _build_perspread_histories(
    pooled_trades: list[dict],
    baseline_trades: list[dict],
) -> tuple[dict, dict]:
    """
    Build {spread -> [(close_date, net_pnl)]} histories for the regime leg
    (pooled trades that PASS the global gate) and the baseline leg, used to
    decide per-spread enablement at each cutoff. Baseline rows have no fwd_date,
    so their close is approximated as date + FORWARD_DAYS business days — only
    used for the < cutoff ordering, and refits are quarterly (~63 bd) so the
    20-bd approximation never crosses a boundary spuriously.
    """
    from research.spread_universe import INSTRUMENTS

    reg_hist: dict[str, list] = {sp: [] for sp in INSTRUMENTS}
    base_hist: dict[str, list] = {sp: [] for sp in INSTRUMENTS}

    pool_idx = {(t["date"], t["spread"]): t for t in pooled_trades}
    base_idx = {(t["date"], t["spread"]): t for t in baseline_trades}

    for (dt, sp), p in pool_idx.items():
        if sp not in reg_hist:
            continue
        if _pooled_passes_gate(p) and p.get("fwd_pnl") is not None:
            fd = p.get("fwd_date")
            close = pd.Timestamp(fd) if fd else pd.Timestamp(dt) + pd.tseries.offsets.BDay(FORWARD_DAYS)
            reg_hist[sp].append((close, float(p["fwd_pnl"]) - _cost_for(p)))

    for (dt, sp), b in base_idx.items():
        if sp not in base_hist:
            continue
        if b.get("direction") != "NEUTRAL" and b.get("fwd_pnl") is not None:
            close = pd.Timestamp(dt) + pd.tseries.offsets.BDay(FORWARD_DAYS)
            base_hist[sp].append((close, float(b["fwd_pnl"]) - _cost_for(b)))

    return reg_hist, base_hist


def _build_perspread_gated_blend(
    pooled_trades: list[dict],
    baseline_trades: list[dict],
    refit_ts: list[pd.Timestamp],
) -> tuple[list[dict], dict, set]:
    """
    Per-spread variant of _build_gated_blend. For each (date, spread) the regime
    candidate is taken only when the spread is ENABLED as of the trade's refit
    cutoff AND it passes the global gate; otherwise we fall to baseline. Returns
    (blended_trades, enabled_by_cutoff, enabled_latest).
    """
    from research import gate_config

    reg_hist, base_hist = _build_perspread_histories(pooled_trades, baseline_trades)

    # Resolve the enabled set once per cutoff (decision only uses trades that
    # closed before the cutoff → genuinely out-of-sample).
    enabled_by_cutoff: dict[str, set] = {}
    for cutoff in refit_ts:
        enabled_by_cutoff[cutoff.strftime("%Y-%m-%d")] = gate_config.enabled_at_cutoff(
            reg_hist, base_hist, cutoff, forward_days=FORWARD_DAYS,
        )

    pool_idx = {(t["date"], t["spread"]): t for t in pooled_trades}
    base_idx = {(t["date"], t["spread"]): t for t in baseline_trades}
    keys     = sorted(set(pool_idx.keys()) | set(base_idx.keys()))

    blended: list[dict] = []
    for k in keys:
        dt = pd.Timestamp(k[0]); sp = k[1]
        p  = pool_idx.get(k)
        b  = base_idx.get(k)
        # cutoff = most recent refit boundary on/before the trade date
        prior = [r for r in refit_ts if r <= dt]
        cutoff = prior[-1] if prior else refit_ts[0]
        enabled = enabled_by_cutoff[cutoff.strftime("%Y-%m-%d")]
        if gate_config.per_spread_gate_passes(sp, enabled, _pooled_passes_gate(p)):
            blended.append({**p, "source": "regime", "gate": "pass"})  # type: ignore[arg-type]
        elif b is not None:
            blended.append({
                "date":      b["date"],
                "spread":    b["spread"],
                "actual":    b["actual"],
                "z":         b["z"],
                "direction": b["direction"],
                "fwd_move":  b.get("fwd_move"),
                "fwd_pnl":   b.get("fwd_pnl"),
                "roll_mu":   b.get("roll_mu"),
                "roll_sigma":b.get("roll_sigma"),
                "regime":    (p or {}).get("regime")    if p else None,
                "winner":    (p or {}).get("winner")    if p else None,
                "pooled_z":  (p or {}).get("z")         if p else None,
                "source":    "baseline",
                "gate":      "disabled" if (p and _pooled_passes_gate(p)) else ("fail" if p else "no_pooled"),
            })

    latest_key = refit_ts[-1].strftime("%Y-%m-%d")
    enabled_latest = enabled_by_cutoff[latest_key]
    return blended, enabled_by_cutoff, enabled_latest


def run_perspread_gate_only(headline: str = "per_spread_gate") -> dict:
    """
    Phase 8 (2026-06-22) — build a per-spread-gated blend from the persisted
    pooled + baseline tapes and merge a `per_spread_gate` block into
    walkforward_report.json. Mirrors --voltarget-only's standalone-merge pattern:
    every other block is untouched. No retrain.

    The decision (which spreads fire regime) is made walk-forward in
    gate_config.enabled_at_cutoff — the same module live_ranker reads for
    inference — so the live gate and the backtested gate cannot drift.
    """
    from research import gate_config

    existing = load_report()
    if existing is None:
        raise RuntimeError(
            "walkforward_report.json missing — run the full walk-forward first, "
            "then re-run with --perspread-gate-only."
        )
    if not _POOLED_TRADES_FILE.exists() or not _BASELINE_TRADES_FILE.exists():
        raise RuntimeError(
            "pooled/baseline tapes missing — run the full walk-forward first, "
            "then re-run with --perspread-gate-only."
        )

    with open(_POOLED_TRADES_FILE) as f:
        pooled_tape = json.load(f)
    with open(_BASELINE_TRADES_FILE) as f:
        baseline_tape = json.load(f)

    refit_ts = [pd.Timestamp(d) for d in REFIT_DATES]
    blended, enabled_by_cutoff, enabled_latest = _build_perspread_gated_blend(
        pooled_tape, baseline_tape, refit_ts,
    )

    net = _net_block(blended, include_source=True)
    n_regime   = sum(1 for t in blended if t.get("source") == "regime")
    n_baseline = sum(1 for t in blended if t.get("source") == "baseline")

    block = {
        "regime_mode":   "per_spread_gate",
        "headline":      headline,
        "overall":       net["overall"],
        "by_spread":     net["by_spread"],
        "by_source":     net["by_source"],
        "by_spread_source": net["by_spread_source"],
        "n_trades":      len(blended),
        "n_regime":      n_regime,
        "n_baseline":    n_baseline,
        "enabled_latest": sorted(enabled_latest),
        "enabled_by_cutoff": {k: sorted(v) for k, v in enabled_by_cutoff.items()},
        "config": {
            "margin":        gate_config.GATE_MARGIN,
            "min_n":         gate_config.GATE_MIN_N,
            "global_gate":   {"regime": GATED_REGIME, "winners": sorted(GATED_WINNERS), "z_thresh": GATED_Z_THRESHOLD},
        },
        "note": (
            "Phase 8 (2026-06-22) — per-spread gate. Replaces the uniform global "
            "gate with a per-spread enable decision made walk-forward (regime leg "
            "fires for a spread only when its OOS NET Sharpe beat baseline for that "
            "spread before each refit, ≥ min_n evidence). Pure post-processing on "
            "the pooled + baseline tapes; same fired signals, re-routed regime vs "
            "baseline per spread. Decision logic shared with live_ranker via "
            "gate_config.py."
        ),
    }
    existing["per_spread_gate"] = block

    costs = existing.setdefault("costs", {})
    costs["per_spread_gate_net"] = {k: net[k] for k in ("overall", "by_spread")}
    base_net  = (costs.get("baseline_net") or {})
    gated_net = (costs.get("gated_blend_net") or {})
    if gated_net.get("by_spread"):
        existing["lift_perspread_gate_vs_gated"] = _lift(
            net, gated_net.get("by_spread", {}), gated_net.get("overall", {}))
    if base_net.get("by_spread"):
        existing["lift_perspread_gate_vs_baseline"] = _lift(
            net, base_net.get("by_spread", {}), base_net.get("overall", {}))

    cfg = existing.setdefault("config", {})
    modes = cfg.get("regime_modes") or []
    if "per_spread_gate" not in modes:
        cfg["regime_modes"] = list(modes) + ["per_spread_gate"]

    try:
        _PERSPREAD_GATE_TRADES_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_PERSPREAD_GATE_TRADES_FILE, "w") as f:
            json.dump(blended, f, default=str)
        log.info("  saved %s (%d rows)", _PERSPREAD_GATE_TRADES_FILE.name, len(blended))
    except Exception as exc:  # pragma: no cover — disk-only failure
        log.warning("  failed to save %s: %s", _PERSPREAD_GATE_TRADES_FILE.name, exc)

    existing["generated_at"] = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    _REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_REPORT_FILE, "w") as f:
        json.dump(existing, f, indent=2, default=str)
    log.info("Saved walk-forward report (per-spread gate leg merged) → %s", _REPORT_FILE)
    return existing


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if "--perspread-gate-only" in sys.argv:
        rpt = run_perspread_gate_only()
        blk = rpt["per_spread_gate"]
        ps_net   = rpt["costs"]["per_spread_gate_net"]["overall"]
        gate_net = (rpt["costs"].get("gated_blend_net") or {}).get("overall", {})
        base_net = rpt["costs"]["baseline_net"]["overall"]
        print()
        print("=== Phase 8 (2026-06-22) — per-spread gate (NET, on pooled+baseline tapes) ===")
        print(f"  config: margin={blk['config']['margin']}  min_n={blk['config']['min_n']}")
        print(f"  enabled at latest cutoff: {blk['enabled_latest']}")
        print(f"  regime fires={blk['n_regime']}  baseline={blk['n_baseline']}")
        print()
        print("=== NET-Sharpe verdict — per-spread gate vs global gate vs baseline ===")
        print(f"  baseline             {base_net['sharpe']:+.3f}")
        print(f"  gated_blend (global) {(gate_net.get('sharpe') or 0.0):+.3f}")
        print(f"  per_spread_gate      {(ps_net.get('sharpe') or 0.0):+.3f}")
        print()
        print("=== Per-spread NET Sharpe — per-spread gate vs global gate vs baseline ===")
        psp = rpt["costs"]["per_spread_gate_net"]["by_spread"]
        gsp = (rpt["costs"].get("gated_blend_net") or {}).get("by_spread", {})
        bsp = rpt["costs"]["baseline_net"]["by_spread"]
        for sp in sorted(set(list(psp.keys()) + list(bsp.keys()))):
            ps = (psp.get(sp) or {}).get("sharpe")
            g  = (gsp.get(sp) or {}).get("sharpe")
            b  = (bsp.get(sp) or {}).get("sharpe")
            en = "ON " if sp in blk["enabled_latest"] else "off"
            print(f"  {sp:<14} [{en}]  perspread={ps}  global={g}  baseline={b}")
        sys.exit(0)

    if "--voltarget-only" in sys.argv:
        rpt = run_voltarget_only()
        blk = rpt["vol_target"]
        v = blk["variants"]
        print()
        print("=== Phase 7 (2.8.10) — portfolio vol-targeting (NET, on gated tape) ===")
        print(f"  config: vol_win={blk['config']['vol_win']}  rho_max={blk['config']['rho_max']}"
              f"  median_spread_vol={blk['config']['median_spread_vol']}")
        print()
        order = ["baseline_raw", "gated_raw", "decorrelated", "risk_parity",
                 "parity_stress", "vol_target"]
        print(f"  {'variant':<16} {'held':>6} {'NET Shp':>9} {'maxDD':>9} {'Calmar':>8} {'mean PnL':>9}")
        for name in order:
            m = v.get(name)
            if not m:
                continue
            tag = name + ("  ←headline" if name == blk["headline"] else "")
            print(f"  {tag:<16} {(m['n_signals'] or 0):>6} "
                  f"{(m['sharpe'] if m['sharpe'] is not None else 0.0):>+9.3f} "
                  f"{(m['max_drawdown'] if m['max_drawdown'] is not None else 0.0):>+9.2f} "
                  f"{(m['calmar'] if m['calmar'] is not None else 0.0):>+8.3f} "
                  f"{(m['mean_pnl'] if m['mean_pnl'] is not None else 0.0):>+9.4f}")
        print()
        print("=== Per-spread NET Sharpe — vol_target headline vs gated_raw ===")
        vt_sp = rpt["costs"]["vol_target_net"]["by_spread"]
        g_sp  = (rpt["costs"].get("gated_blend_net") or {}).get("by_spread", {})
        for sp in sorted(set(list(vt_sp.keys()) + list(g_sp.keys()))):
            a = (vt_sp.get(sp) or {}).get("sharpe")
            b = (g_sp.get(sp) or {}).get("sharpe")
            print(f"  {sp:<14}  vol_target={a}  gated={b}")
        sys.exit(0)

    if "--hmm-only" in sys.argv:
        rpt = run_hmm_only()
        hmm = rpt["hmm"]
        hmm_net  = rpt["costs"]["hmm_net"]["overall"]
        base_net = rpt["costs"]["baseline_net"]["overall"]
        pool_net = (rpt["costs"].get("pooled_net") or {}).get("overall") or {}
        gl_net   = (rpt["costs"].get("global_net") or {}).get("overall") or {}
        gate_net = (rpt["costs"].get("gated_blend_net") or {}).get("overall") or {}
        det = hmm["detector"]
        print()
        print("=== Phase 6 (2.8.9) — data-driven HMM / change-point regimes ===")
        print(f"  headline K           {hmm['headline_states']} states (matched to 3 hard curve buckets)")
        print(f"  detector features    {det['features']}")
        print(f"  mean curve means $   {det['mean_curve_means']}")
        print(f"  mean boundaries $    {det['mean_boundaries']}   (hard thresholds: -2 / +5)")
        print(f"  records              {hmm['n_trades']:>6}")
        print(f"  signals fired        {hmm['overall']['n_signals']:>6}")
        print(f"  hit rate             {hmm['overall']['hit_rate']}")
        print(f"  GROSS Sharpe         {hmm['overall']['sharpe']}")
        print(f"  NET   Sharpe         {hmm_net['sharpe']}")
        print(f"  max drawdown (gross) {hmm['overall']['max_drawdown']}")
        print()
        print("=== State-count sensitivity (overall NET Sharpe) ===")
        for K, row in hmm["state_sweep"].items():
            print(f"  K={K}  net={ (row['net_sharpe'] if row['net_sharpe'] is not None else 0.0):+.3f}"
                  f"  gross={row['gross_sharpe']}  n={row['n_signals']}  bounds={row['mean_boundaries']}")
        print()
        print("=== NET-Sharpe verdict — HMM vs hard-threshold variants ===")
        print(f"  baseline             {base_net['sharpe']:+.3f}")
        if pool_net: print(f"  pooled (hard 3-bucket){pool_net['sharpe']:+.3f}")
        if gate_net: print(f"  gated_blend          {gate_net['sharpe']:+.3f}")
        if gl_net:   print(f"  global (regime-feat) {gl_net['sharpe']:+.3f}")
        print(f"  hmm (data-driven K={hmm['headline_states']}){hmm_net['sharpe']:+.3f}")
        print()
        print("=== Per-spread NET Sharpe — HMM vs pooled vs baseline ===")
        hnet_sp = rpt["costs"]["hmm_net"]["by_spread"]
        pnet_sp = (rpt["costs"].get("pooled_net") or {}).get("by_spread", {})
        bnet_sp = rpt["costs"]["baseline_net"]["by_spread"]
        for sp in sorted(set(list(hnet_sp.keys()) + list(bnet_sp.keys()))):
            h = (hnet_sp.get(sp) or {}).get("sharpe")
            p = (pnet_sp.get(sp) or {}).get("sharpe")
            b = (bnet_sp.get(sp) or {}).get("sharpe")
            print(f"  {sp:<14}  hmm={h}  pooled={p}  baseline={b}")
        sys.exit(0)

    if "--horizon-only" in sys.argv:
        rpt = run_horizon_only()
        hs = rpt["horizon_sweep"]
        print()
        print("=== Phase 5 (2.8.7) -- Multi-horizon sweep (NET Sharpe, annualised sqrt(252/H)) ===")
        print(f"  horizons {hs['horizons']}   sources {hs['sources']}")
        for src, blk in hs["by_source"].items():
            print(f"\n  [{src}] overall NET Sharpe by horizon:")
            for H in hs["horizons"]:
                m = blk["overall_by_horizon"][str(H)]
                print(f"    {H:>3}d  net={ (m['sharpe'] if m['sharpe'] is not None else 0.0):+.3f}"
                      f"  hit={m['hit_rate']}  n={m['n_signals']}")
            print(f"  [{src}] best NET-Sharpe horizon per spread (vs 20d default):")
            for sp, b in blk["best_horizon_by_spread"].items():
                print(f"    {sp:<14} best={b['horizon']}d net={b['net_sharpe']}"
                      f"  (20d={b['default_20d_net_sharpe']}  Δ={b['delta_vs_20d']})")
        sys.exit(0)

    if "--featsel-only" in sys.argv:
        rpt = run_featsel_only()
        lean = rpt["global_lean"]["overall"]
        lean_net = rpt["costs"]["global_lean_net"]["overall"]
        gl      = (rpt.get("global") or {}).get("overall") or {}
        gl_net  = (rpt["costs"].get("global_net") or {}).get("overall") or {}
        base_net = rpt["costs"]["baseline_net"]["overall"]
        print()
        print("=== Phase 5 — Feature selection (Lasso stability) ===")
        for sp, info in rpt["feature_selection"]["per_spread"].items():
            print(f"  {sp:<14} kept {info['n_selected']:>2}/{info['n_base']}  -> {info['selected']}")
        print()
        print("=== NET-Sharpe verdict — lean global vs full global vs baseline ===")
        print(f"  baseline             {base_net['sharpe']:+.3f}")
        print(f"  global (full feats)  {(gl_net.get('sharpe') or 0.0):+.3f}")
        print(f"  global_lean          {(lean_net.get('sharpe') or 0.0):+.3f}")
        print(f"  (gross: full={gl.get('sharpe')}  lean={lean.get('sharpe')})")
        print()
        print("=== Per-spread NET Sharpe — lean vs full global vs baseline ===")
        lsp = rpt["costs"]["global_lean_net"]["by_spread"]
        gsp = (rpt["costs"].get("global_net") or {}).get("by_spread", {})
        bsp = rpt["costs"]["baseline_net"]["by_spread"]
        for sp in sorted(set(list(lsp.keys()) + list(gsp.keys()))):
            l = (lsp.get(sp) or {}).get("sharpe")
            g = (gsp.get(sp) or {}).get("sharpe")
            b = (bsp.get(sp) or {}).get("sharpe")
            print(f"  {sp:<14} lean={l}  full={g}  baseline={b}")
        sys.exit(0)

    if "--soft-only" in sys.argv:
        soft_modes: tuple[str, ...] = ("pooled",)
        if "--composite" in sys.argv:
            soft_modes = ("pooled", "composite")
        rpt = run_soft_only(modes=soft_modes)
        base_net = rpt["costs"]["baseline_net"]["overall"]
        pool_net = rpt["costs"]["pooled_net"]["overall"]
        gate_net = rpt["costs"]["gated_blend_net"]["overall"]
        gl_net   = rpt["costs"]["global_net"]["overall"]
        print()
        print("=== Phase 2.8.5 — soft regime probabilities ===")
        for m in soft_modes:
            blk     = rpt[f"{m}_soft"]["overall"]
            net     = rpt["costs"][f"{m}_soft_net"]["overall"]
            diag    = rpt[f"{m}_soft"].get("soft_diagnostics", {})
            print(f"  [{m}_soft]")
            print(f"    records              {rpt[f'{m}_soft']['n_trades']:>6}")
            print(f"    signals fired        {blk['n_signals']:>6}")
            print(f"    hit rate             {blk['hit_rate']}")
            print(f"    GROSS Sharpe         {blk['sharpe']}")
            print(f"    NET   Sharpe         {net['sharpe']}")
            print(f"    max drawdown (gross) {blk['max_drawdown']}")
            print(f"    soft top-weight mean {diag.get('mean_top_weight')}  cells blended mean {diag.get('mean_cells_blended')}")
        print()
        print("=== NET-Sharpe verdict (Phase 2.8.5 vs 2026-06-15 headline) ===")
        print(f"  baseline             {base_net['sharpe']:+.3f}")
        print(f"  global  (Phase 2.8.4){gl_net['sharpe']:+.3f}")
        print(f"  gated_blend          {gate_net['sharpe']:+.3f}")
        print(f"  pooled  (hard)       {pool_net['sharpe']:+.3f}")
        for m in soft_modes:
            net = rpt["costs"][f"{m}_soft_net"]["overall"]
            print(f"  {m}_soft           {net['sharpe']:+.3f}")
        print()
        print("=== Per-spread NET Sharpe — soft vs baseline ===")
        bnet_sp = rpt["costs"]["baseline_net"]["by_spread"]
        for m in soft_modes:
            snet_sp = rpt["costs"][f"{m}_soft_net"]["by_spread"]
            print(f"  [{m}_soft]")
            for sp in sorted(set(list(snet_sp.keys()) + list(bnet_sp.keys()))):
                s = (snet_sp.get(sp) or {}).get("sharpe")
                b = (bnet_sp.get(sp) or {}).get("sharpe")
                print(f"    {sp:<14}  soft={s}  baseline={b}")
        sys.exit(0)

    if "--global-only" in sys.argv:
        rpt = run_global_only()
        gl = rpt["global"]["overall"]
        gl_net = rpt["costs"]["global_net"]["overall"]
        base = rpt["baseline_overall"]
        base_net = rpt["costs"]["baseline_net"]["overall"]
        gate = rpt["gated_blend"]["overall"]
        gate_net = rpt["costs"]["gated_blend_net"]["overall"]
        pool = rpt["pooled"]["overall"]
        pool_net = rpt["costs"]["pooled_net"]["overall"]
        print()
        print("=== Phase 2.8.4 — Global model (regime-as-feature) ===")
        print(f"  records              {rpt['global']['n_trades']:>6}")
        print(f"  signals fired        {gl['n_signals']:>6}")
        print(f"  hit rate             {gl['hit_rate']}")
        print(f"  mean PnL             {gl['mean_pnl']}")
        print(f"  GROSS Sharpe         {gl['sharpe']}")
        print(f"  NET  Sharpe          {gl_net['sharpe']}")
        print(f"  max drawdown (gross) {gl['max_drawdown']}")
        print()
        print("=== NET-Sharpe verdict (Phase 2.8.4 vs 2026-06-15 headline) ===")
        print(f"  baseline             {base_net['sharpe']:+.3f}")
        print(f"  gated_blend          {gate_net['sharpe']:+.3f}")
        print(f"  pooled               {pool_net['sharpe']:+.3f}")
        print(f"  global (Phase 2.8.4) {gl_net['sharpe']:+.3f}")
        print()
        print("=== Per-spread NET Sharpe — global vs baseline ===")
        gnet_sp = rpt["costs"]["global_net"]["by_spread"]
        bnet_sp = rpt["costs"]["baseline_net"]["by_spread"]
        for sp in sorted(set(list(gnet_sp.keys()) + list(bnet_sp.keys()))):
            g  = (gnet_sp.get(sp) or {}).get("sharpe")
            b  = (bnet_sp.get(sp) or {}).get("sharpe")
            print(f"  {sp:<14}  global={g}  baseline={b}")
        sys.exit(0)
    rpt = run_walkforward()
    base = rpt["baseline_overall"]
    print()
    for label, key, sub in (
        ("Composite (27 cells)",        "composite",   None),
        ("Pooled (3 curve cells)",      "pooled",      None),
        ("Gated blend (Phase 2.6)",     "gated_blend", None),
        ("Sized blend FULL (Phase 2.7)",  "sized_blend", "full"),
        ("Sized blend HALF (Phase 2.7)",  "sized_blend", "half"),
        ("Sized blend KELLY (Phase 2.7)", "sized_blend", "kelly"),
    ):
        blk = rpt[key] if sub is None else rpt[key][sub]
        o = blk["overall"]
        print(f"=== {label} ===")
        print(f"  refits           {len(blk['refits'])}")
        print(f"  records          {blk['n_trades']:>6}")
        print(f"  signals fired    {o['n_signals']:>6} (rest NEUTRAL)")
        print(f"  hit rate         {o['hit_rate']}")
        print(f"  mean PnL         {o['mean_pnl']}")
        print(f"  Sharpe (ann.)    {o['sharpe']}")
        print(f"  max drawdown     {o['max_drawdown']}")
        if key == "gated_blend":
            gc = blk.get("gate_counts", {})
            print(f"  gate fires       regime={gc.get('regime_fires')}  baseline={gc.get('baseline_fallback')}  regime_share={gc.get('regime_share')}")
        if key == "sized_blend":
            print(f"  mean scale       {blk.get('mean_regime_scale')}  median={blk.get('median_regime_scale')}")
        print()
    print("=== Baseline (regime-unaware 252d z) ===")
    print(f"  signals fired    {base['n_signals']:>6}")
    print(f"  hit rate         {base['hit_rate']}")
    print(f"  mean PnL         {base['mean_pnl']}")
    print(f"  Sharpe (ann.)    {base['sharpe']}")
    print()
    print("=== Per-spread Sharpe -- composite / pooled / gated / size-half / size-kelly / baseline ===")
    by_c  = rpt["composite"]["by_spread"]
    by_p  = rpt["pooled"]["by_spread"]
    by_g  = rpt["gated_blend"]["by_spread"]
    by_sh = rpt["sized_blend"]["half"]["by_spread"]
    by_sk = rpt["sized_blend"]["kelly"]["by_spread"]
    by_b  = rpt["baseline_by_spread"]
    for sp in by_c:
        c  = (by_c.get(sp)  or {}).get("sharpe")
        p  = (by_p.get(sp)  or {}).get("sharpe")
        g  = (by_g.get(sp)  or {}).get("sharpe")
        sh = (by_sh.get(sp) or {}).get("sharpe")
        sk = (by_sk.get(sp) or {}).get("sharpe")
        b  = (by_b.get(sp)  or {}).get("sharpe")
        print(f"  {sp:<14}  composite={c}  pooled={p}  gated={g}  half={sh}  kelly={sk}  baseline={b}")

    klp = rpt.get("sized_blend_summary", {}).get("kelly_per_spread_latest", {})
    if klp:
        print()
        print("=== Latest Kelly fractions (applied to next live regime fires) ===")
        for sp, k in klp.items():
            print(f"  {sp:<14}  kelly={k}")

    costs = rpt.get("costs") or {}
    if costs:
        print()
        print("=== Phase 2.8.6 — NET (after transaction costs) ===")
        print(f"  cost model: {costs.get('model_doc', '')[:90]}...")
        print(f"  per-spread RT: {costs.get('per_spread_rt')}")
        print()
        print(f"  {'mode':<24} {'gross Shp':>10} {'net Shp':>10} {'gross mPnL':>11} {'net mPnL':>11} {'n_sig':>7}")
        rows = [
            ("baseline 252d z", rpt["baseline_overall"], costs["baseline_net"]["overall"]),
            ("pooled (un-gated)", rpt["pooled"]["overall"], costs["pooled_net"]["overall"]),
            ("gated_blend",     rpt["gated_blend"]["overall"], costs["gated_blend_net"]["overall"]),
            ("sized_full",      rpt["sized_blend"]["full"]["overall"],  costs["sized_blend_net"]["full"]["overall"]),
            ("sized_half",      rpt["sized_blend"]["half"]["overall"],  costs["sized_blend_net"]["half"]["overall"]),
            ("sized_kelly",     rpt["sized_blend"]["kelly"]["overall"], costs["sized_blend_net"]["kelly"]["overall"]),
        ]
        for name, gross, net in rows:
            print(f"  {name:<24} "
                  f"{(gross.get('sharpe') if gross.get('sharpe') is not None else 0.0):>+10.3f} "
                  f"{(net.get('sharpe')   if net.get('sharpe')   is not None else 0.0):>+10.3f} "
                  f"{(gross.get('mean_pnl') if gross.get('mean_pnl') is not None else 0.0):>+11.4f} "
                  f"{(net.get('mean_pnl')   if net.get('mean_pnl')   is not None else 0.0):>+11.4f} "
                  f"{(net.get('n_signals')  or 0):>7}")
