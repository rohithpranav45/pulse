"""
Phase 6 — research-leg unit tests (2.8.9 data-driven HMM / change-point regimes).

The HMM leg is an additive re-training pass on the Phase 2.8 walk-forward (see
CLAUDE.md §1): it replaces the hard −$2/+$5 curve thresholds with a fitted
Gaussian-mixture + causal sticky-HMM detector and re-runs the per-cell
competition over the discovered regimes. These tests are HERMETIC — tiny
synthetic frames, never touching `/Data`, the model pkls, or the live cache —
so they assert the leg LOGIC (ordinal relabelling, causal labelling, the
regime-source override threading), not the production numbers.

Run from the repo root:  python -m pytest tests/test_phase6_research.py -v
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

from research import walkforward as wf            # noqa: E402
from research import regime_hmm as rh             # noqa: E402


# ─────────────────────────────────────────────────────────────────────────────
# Detector — ordinal relabelling, causal labelling, state summary
# ─────────────────────────────────────────────────────────────────────────────
def _bimodal_curve(n=160, seed=0):
    """A curve series with a deep-contango block then a backwardation block, so a
    2/3-state GMM separates cleanly and the ordinal labels are deterministic."""
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2022-01-03", periods=n)
    half = n // 2
    lo = rng.normal(-6.0, 0.6, half)     # deep contango
    hi = rng.normal(+8.0, 0.6, n - half) # backwardation
    return pd.Series(np.concatenate([lo, hi]), index=idx, name="m1_m12")


def test_state_labels_and_count():
    det = rh.CurveRegimeHMM(n_states=3).fit(pd.DataFrame({"m1_m12": _bimodal_curve()}))
    assert det.state_labels == ["R0", "R1", "R2"]


def test_ordinal_relabel_by_curve_level():
    det = rh.CurveRegimeHMM(n_states=2).fit(pd.DataFrame({"m1_m12": _bimodal_curve()}))
    summ = det.state_summary()
    means = list(summ["state_curve_means"].values())
    # R0 is the lowest-curve (contango) state by construction of the relabelling.
    assert means == sorted(means)
    assert means[0] < 0 < means[-1]
    # Boundary sits between the two cluster means; hard thresholds reported.
    assert means[0] < summ["implied_boundaries"][0] < means[-1]
    assert summ["hard_thresholds"] == [-2.0, 5.0]


def test_label_series_aligned_and_burn_in_unknown():
    curve = _bimodal_curve()
    df = pd.DataFrame({"m1_m12": curve})
    det = rh.CurveRegimeHMM(n_states=2).fit(df)
    labels = det.label_series(df)
    # One label per input row.
    assert list(labels.index) == list(df.index)
    # The 5-day change burn-in at the very start is UNKNOWN; the rest are states.
    assert (labels.iloc[:rh._CHG_WINDOW] == "UNKNOWN").all()
    assert set(labels.iloc[rh._CHG_WINDOW:].unique()) <= set(det.state_labels)
    # A clearly deep-contango early day lands in R0; a backwardation day does not.
    assert labels.iloc[rh._CHG_WINDOW + 5] == "R0"
    assert labels.iloc[-1] != "R0"


def test_labelling_is_causal():
    """The forward filter at day d uses only data ≤ d, so labels on an early
    slice must not change when future rows are appended."""
    curve = _bimodal_curve()
    df = pd.DataFrame({"m1_m12": curve})
    det = rh.CurveRegimeHMM(n_states=3).fit(df)        # params frozen
    full = det.label_series(df)
    k = 100
    trunc = det.label_series(df.iloc[:k])
    # Overlapping prefix is identical — no look-ahead leakage.
    pd.testing.assert_series_equal(full.iloc[:k], trunc, check_names=False)


def test_fit_rejects_too_few_rows():
    det = rh.CurveRegimeHMM(n_states=4)
    with pytest.raises(RuntimeError):
        det.fit(pd.DataFrame({"m1_m12": _bimodal_curve(n=12)}))


# ─────────────────────────────────────────────────────────────────────────────
# Walk-forward plumbing — regime-source override + HMM aggregation
# ─────────────────────────────────────────────────────────────────────────────
def _toy_joined(n=140, seed=1):
    """Synthetic feature+spread frame with every column the per-cell competition
    touches, plus a curve-driven `m1_m12` and a clean reverting `brent_m1_m2`."""
    from research.features import BRENT_FEATURES, WTI_EXTRA_FEATURES
    from research.spread_universe import INSTRUMENTS

    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2022-01-03", periods=n)
    cols = sorted(set(BRENT_FEATURES) | set(WTI_EXTRA_FEATURES))
    data = {c: rng.normal(0, 1, n) for c in cols}
    df = pd.DataFrame(data, index=idx)
    # A genuinely bimodal curve so the HMM finds two dense regimes.
    half = n // 2
    df["m1_m12"] = np.concatenate([rng.normal(-6, 0.6, half), rng.normal(8, 0.6, n - half)])
    df["m1_m12_sq"] = df["m1_m12"] ** 2
    for sp in INSTRUMENTS:
        df[sp] = 2.0 * df["m1_m12"] + rng.normal(0, 0.3, n)
    df["regime"] = "BACK/AVG/NORMAL"
    df["regime_pooled"] = "BACK"
    return df


def test_train_cells_regime_source_override():
    joined = wf.pd.DataFrame(_toy_joined())
    cutoff = joined.index[-1]
    det = rh.CurveRegimeHMM(n_states=2).fit(joined.loc[:cutoff])
    joined = joined.copy()
    joined["regime_hmm"] = det.label_series(joined)
    cells = wf._train_cells_through(
        joined, cutoff, regime_col="regime_hmm",
        regime_list=det.state_labels, enable_boosters=True,
    )
    assert cells, "expected at least one trained HMM cell"
    # Every cell is keyed by an HMM ordinal state, not a hard curve bucket.
    regimes_seen = {rg for (_, rg) in cells.keys()}
    assert regimes_seen <= set(det.state_labels)
    spreads_seen = {sp for (sp, _) in cells.keys()}
    assert "brent_m1_m2" in spreads_seen


def test_train_cells_default_is_unchanged():
    """Default args (no override) still read regime_pooled / the pooled list."""
    joined = _toy_joined()
    cutoff = joined.index[-1]
    cells = wf._train_cells_through(joined, cutoff, regime_mode="pooled")
    # All rows are regime_pooled=='BACK' here → only BACK cells exist.
    assert {rg for (_, rg) in cells.keys()} == {"BACK"}


def test_evaluate_window_regime_col_override():
    joined = _toy_joined()
    cut = joined.index[len(joined) // 2]
    end = joined.index[-1]
    det = rh.CurveRegimeHMM(n_states=2).fit(joined.loc[:cut])
    joined = joined.copy()
    joined["regime_hmm"] = det.label_series(joined)
    spreads = joined[[c for c in joined.columns if c.startswith(("brent_", "wti_"))]]
    cells = wf._train_cells_through(
        joined, cut, regime_col="regime_hmm",
        regime_list=det.state_labels, enable_boosters=False,
    )
    trades = wf._evaluate_window(joined, spreads, cells, cut, end, regime_col="regime_hmm")
    assert trades
    # Recorded regimes are HMM states.
    assert {t["regime"] for t in trades} <= set(det.state_labels)


def test_aggregate_hmm_shape_and_detector_block():
    trades = [
        {"date": "2024-01-02", "spread": "brent_m1_m2", "regime": "R0",
         "direction": "BUY", "winner": "Lasso", "fwd_pnl": 1.2},
        {"date": "2024-01-03", "spread": "brent_m1_m2", "regime": "R1",
         "direction": "SELL", "winner": "Huber", "fwd_pnl": -0.4},
    ]
    meta = [{
        "cutoff": "2024-01-01", "window_end": "2024-04-01", "n_cells": 2,
        "winners": {"Lasso": 1, "Huber": 1}, "n_records": 2,
        "state_summary": {"n_states": 3, "stay": 0.95,
                          "state_curve_means": {"R0": -3.0, "R1": 2.0, "R2": 7.0},
                          "implied_boundaries": [-0.5, 4.5],
                          "hard_thresholds": [-2.0, 5.0]},
    }]
    blk = wf._aggregate_hmm(trades, meta, n_states=3)
    assert blk["regime_mode"] == "hmm3" and blk["n_states"] == 3
    assert set(blk["by_regime"].keys()) == {"R0", "R1"}
    det = blk["detector"]
    assert det["mean_boundaries"] == [-0.5, 4.5]
    assert det["hard_thresholds"] == [-2.0, 5.0]
    assert det["mean_curve_means"] == {"R0": -3.0, "R1": 2.0, "R2": 7.0}
