"""
Phase 5 — research-leg unit tests (multi-horizon sweep + feature selection).

Both legs are additive post-processing / re-training passes on the Phase 2.8
walk-forward (see CLAUDE.md §1). These tests are HERMETIC — they build tiny
synthetic frames and never touch `/Data`, the model pkls, or the live cache —
so they assert the leg LOGIC (horizon recompute, annualisation, cost, stability
selection, lean-feature plumbing), not the production numbers.

Run from the repo root:  python -m pytest tests/test_phase5_research.py -v
"""

import os
import sys
import warnings

import numpy as np
import pandas as pd
import pytest

warnings.filterwarnings("ignore")

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from research import walkforward as wf  # noqa: E402


# ─────────────────────────────────────────────────────────────────────────────
# Leg 1 — multi-horizon sweep
# ─────────────────────────────────────────────────────────────────────────────
def _toy_spreads():
    """A single-spread frame whose level rises by exactly 1.0 each business day
    → forward move over H days is exactly +H, so PnL is analytically known."""
    idx = pd.bdate_range("2024-01-01", periods=40)
    vals = pd.Series(np.arange(40, dtype=float), index=idx)  # 0,1,2,...
    return pd.DataFrame({"brent_m1_m2": vals})


def test_spread_lookup_positions():
    spreads = _toy_spreads()
    lookup = wf._spread_lookup(spreads)
    arr, pos = lookup["brent_m1_m2"]
    assert len(arr) == 40
    first = spreads.index[0].normalize()
    assert pos[first] == 0
    assert arr[5] == 5.0


def test_recompute_horizon_pnls_directions_and_edges():
    spreads = _toy_spreads()
    lookup = wf._spread_lookup(spreads)
    d0 = spreads.index[0].strftime("%Y-%m-%d")
    d_last = spreads.index[-1].strftime("%Y-%m-%d")
    trades = [
        {"date": d0,     "spread": "brent_m1_m2", "direction": "BUY"},
        {"date": d0,     "spread": "brent_m1_m2", "direction": "SELL"},
        {"date": d0,     "spread": "brent_m1_m2", "direction": "NEUTRAL"},
        {"date": d_last, "spread": "brent_m1_m2", "direction": "BUY"},
    ]
    rows = wf._recompute_horizon_pnls(trades, lookup, horizons=(5, 10))
    buy, sell, neut, edge = rows
    # Level rises 1/day → BUY profits +H, SELL loses -H.
    assert buy["pnl_h5"] == 5.0 and buy["pnl_h10"] == 10.0
    assert sell["pnl_h5"] == -5.0 and sell["pnl_h10"] == -10.0
    # NEUTRAL never fills.
    assert neut["pnl_h5"] is None and neut["pnl_h10"] is None
    # Last bar has no forward data at any horizon.
    assert edge["pnl_h5"] is None and edge["pnl_h10"] is None


def test_horizon_metrics_annualisation_and_cost():
    # Six identical-direction fills with a deterministic +/- pattern so std>0.
    pnls = [1.0, 1.0, 1.0, -1.0, 1.0, 1.0]
    rows = [{"spread": "brent_m1_m2", "direction": "BUY", "pnl_h20": p} for p in pnls]
    m = wf._horizon_metrics(rows, horizon=20, pnl_key="pnl_h20")
    assert m["n_signals"] == 6
    cost = wf.COST_PER_SPREAD_RT["brent_m1_m2"]            # 0.030 RT
    net = np.array(pnls) - cost
    expected = (net.mean() / net.std(ddof=1)) * np.sqrt(252.0 / 20)
    assert m["sharpe"] == pytest.approx(round(expected, 3), abs=1e-3)
    assert m["mean_cost"] == pytest.approx(cost, abs=1e-9)
    # Shorter horizon → larger annualisation factor for the same PnL series.
    m5 = wf._horizon_metrics(rows, horizon=5, pnl_key="pnl_h20")
    assert m5["sharpe"] > m["sharpe"]


def test_horizon_metrics_empty():
    rows = [{"spread": "brent_m1_m2", "direction": "NEUTRAL", "pnl_h20": None}]
    m = wf._horizon_metrics(rows, horizon=20, pnl_key="pnl_h20")
    assert m["n_signals"] == 0 and m["sharpe"] is None and m["n_neutral"] == 1


def test_aggregate_horizon_best_pick_respects_min_signals(monkeypatch):
    # Build 30 fills where the 20d column has a higher Sharpe than the 5d column.
    rng = np.random.default_rng(0)
    rows = []
    for _ in range(30):
        rows.append({
            "spread": "brent_m1_m2", "direction": "BUY",
            "pnl_h5":  float(rng.normal(0.05, 1.0)),   # low signal/noise
            "pnl_h20": float(rng.normal(0.80, 1.0)),   # high signal/noise
        })
    monkeypatch.setattr(wf, "HORIZON_MIN_SIGNALS", 10)
    blk = wf._aggregate_horizon({"src": rows}, horizons=(5, 20))
    best = blk["by_source"]["src"]["best_horizon_by_spread"]["brent_m1_m2"]
    assert best["horizon"] == 20
    # With the gate above the sample size, nothing is eligible.
    monkeypatch.setattr(wf, "HORIZON_MIN_SIGNALS", 999)
    blk2 = wf._aggregate_horizon({"src": rows}, horizons=(5, 20))
    assert blk2["by_source"]["src"]["best_horizon_by_spread"]["brent_m1_m2"]["horizon"] is None


# ─────────────────────────────────────────────────────────────────────────────
# Leg 2 — feature selection (Lasso stability) + lean-feature plumbing
# ─────────────────────────────────────────────────────────────────────────────
def _toy_joined(n=80, seed=1):
    """Synthetic feature+spread frame with EVERY column the global leg touches.
    `brent_m1_m2` is driven almost entirely by `m1_m12`, so stability selection
    must keep m1_m12; the other spreads are pure noise (still trainable)."""
    from research.features import BRENT_FEATURES, WTI_EXTRA_FEATURES
    from research.spread_universe import INSTRUMENTS

    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2023-01-02", periods=n)
    cols = sorted(set(BRENT_FEATURES) | set(WTI_EXTRA_FEATURES))
    data = {c: rng.normal(0, 1, n) for c in cols}
    df = pd.DataFrame(data, index=idx)
    # Target with a single dominant driver + small noise.
    df["brent_m1_m2"] = 3.0 * df["m1_m12"] + rng.normal(0, 0.05, n)
    for sp in INSTRUMENTS:
        if sp != "brent_m1_m2":
            df[sp] = rng.normal(0, 1, n)
    df["regime"] = "BACK/AVG/NORMAL"
    return df


def test_stability_select_keeps_dominant_feature():
    joined = _toy_joined(n=90)
    cutoffs = [joined.index[i] for i in (40, 60, 88)]
    sel = wf._stability_select(joined, cutoffs, spreads_list=["brent_m1_m2"])
    info = sel["brent_m1_m2"]
    assert info["n_refits"] == 3
    assert "m1_m12" in info["selected"]
    assert info["freq"]["m1_m12"] >= 0.5
    # Never returns more than the base set; floor keeps at least MIN_KEEP.
    assert wf.FEATSEL_MIN_KEEP <= info["n_selected"] <= info["n_base"]
    # Selected list preserves canonical base-feature order.
    from research.features import predictors_for
    base = predictors_for("brent_m1_m2")
    ordered = [f for f in base if f in set(info["selected"])]
    assert info["selected"] == ordered


def test_stability_select_floor_when_nothing_stable():
    # A frame where no feature is reliably chosen still returns >= MIN_KEEP feats.
    joined = _toy_joined(n=90, seed=7)
    cutoffs = [joined.index[i] for i in (40, 60, 88)]
    sel = wf._stability_select(joined, cutoffs, spreads_list=["brent_m1_m2"],
                               freq_thresh=1.01)  # impossible threshold
    info = sel["brent_m1_m2"]
    assert info["n_selected"] == wf.FEATSEL_MIN_KEEP


def test_global_train_uses_lean_feature_override():
    joined = _toy_joined(n=70)
    cutoff = joined.index[-1]
    lean = ["m1_m12", "curvature", "brent_close"]
    cells = wf._train_global_through(
        joined, cutoff, base_feats_by_spread={"brent_m1_m2": lean}
    )
    assert "brent_m1_m2" in cells
    feat_cols = cells["brent_m1_m2"]["feat_cols"]
    # Lean base feats + the 9 regime one-hots, in that order.
    assert feat_cols == lean + list(wf._REGIME_OH_COLS)
    # A spread NOT in the override keeps its full predictor list.
    from research.features import predictors_for
    assert cells["wti_m1_m2"]["feat_cols"] == predictors_for("wti_m1_m2") + list(wf._REGIME_OH_COLS)


def test_global_override_default_none_is_full_set():
    joined = _toy_joined(n=70)
    cutoff = joined.index[-1]
    from research.features import predictors_for
    cells = wf._train_global_through(joined, cutoff)  # no override
    assert cells["brent_m1_m2"]["feat_cols"] == predictors_for("brent_m1_m2") + list(wf._REGIME_OH_COLS)
