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

# ── Config ───────────────────────────────────────────────────────────────────
FORWARD_DAYS = 20
MIN_SAMPLES  = 30
Z_ENTRY      = 0.5
ROLLING_WIN  = 252
REFIT_DATES  = [
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
) -> dict:
    """
    Train one model per (spread, regime) on rows ≤ cutoff for the given mode.
    Returns dict keyed by (spread, regime) → {pipe, q10, q50, q90, resid_std, winner, n_train}.
    Cells with n_train < MIN_SAMPLES are skipped.
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

    regime_list = REGIMES_POOLED if regime_mode == "pooled" else REGIMES
    regime_col  = "regime_pooled" if regime_mode == "pooled" else "regime"

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
    booster_fitters: dict = {}
    if regime_mode == "pooled":
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
) -> list[dict]:
    """
    For each business day d in (start, end], for each spread, generate one
    record: (date, spread, regime, actual, fair, z, direction, fwd_20d_pnl).
    """
    from research.spread_universe import INSTRUMENTS

    window = joined[(joined.index > start) & (joined.index <= end)]
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
                "z":         round(z, 3),
                "direction": direction,
                "winner":    cell["winner"],
                "fwd_move":  round(fwd_move, 4) if fwd_move is not None else None,
                "fwd_pnl":   round(fwd_pnl, 4)  if fwd_pnl  is not None else None,
                "fwd_date":  fwd_date,
            })
    return trades


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

            trades.append({
                "date":      d.strftime("%Y-%m-%d"),
                "spread":    spread,
                "actual":    round(actual, 4),
                "z":         round(float(z), 3),
                "direction": direction,
                "fwd_move":  round(fwd_move, 4),
                "fwd_pnl":   round(fwd_pnl, 4),
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
        regime = t.get("regime", "")
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
        (_COMPOSITE_TRADES_FILE, composite_trades),
        (_POOLED_TRADES_FILE,    pooled_trades),
        (_BASELINE_TRADES_FILE,  baseline),
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
            "regime_modes":  ["composite", "pooled", "gated_blend", "sized_blend"],
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
        # --- Phase 2.8.6 transaction-cost NET aggregates ---
        "costs":              costs_block,
        "lift_composite_vs_baseline":   _lift(composite_block,       base_by_spread, base_overall),
        "lift_pooled_vs_baseline":      _lift(pooled_block,          base_by_spread, base_overall),
        "lift_gated_vs_baseline":       _lift(gated_block,           base_by_spread, base_overall),
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


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
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
