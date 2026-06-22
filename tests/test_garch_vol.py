"""
GARCH risk-layer study — unit tests (2026-06-22).

`garch_vol.py` produces a causal conditional-vol frame (a drop-in for
`vol_target.spread_vol_frame`) and a QLIKE forecast-accuracy comparison. These
tests are HERMETIC — a small synthetic vol-clustered series, no `/Data`, no model
pkls, no live cache — so they assert the forecasting MECHANICS (causality /
prefix-stability, annualisation, the QLIKE loss, the accuracy table shape), not
the production numbers (those are graded in walkforward.run_garch_only).

Run from the repo root:  python -m pytest tests/test_garch_vol.py -v
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

pytest.importorskip("arch")  # research-only dep; skip cleanly if not installed
from research import garch_vol as gv  # noqa: E402


def _vol_clustered_series(n=200, seed=0):
    """A GARCH-ish level series: alternating calm/turbulent vol regimes so the
    fit has something to grab, indexed on business days."""
    rng = np.random.default_rng(seed)
    sig = np.where((np.arange(n) // 25) % 2 == 0, 0.1, 0.5)  # 25-day vol blocks
    chg = rng.normal(0, 1, n) * sig
    level = np.cumsum(chg) + 50.0
    return pd.Series(level, index=pd.bdate_range("2020-01-01", periods=n))


# ── QLIKE loss ─────────────────────────────────────────────────────────────────
def test_qlike_lower_for_better_forecast():
    """A forecast matching the realised variance beats a badly-scaled one."""
    realised2 = np.full(500, 4.0)          # realised variance ≈ 4
    good = np.full(500, 4.0)               # spot on
    bad  = np.full(500, 40.0)              # 10× too high
    q_good, n = gv._qlike(realised2, good)
    q_bad, _  = gv._qlike(realised2, bad)
    assert n == 500
    assert q_good < q_bad


def test_qlike_ignores_nonfinite_and_nonpositive():
    realised2 = np.array([1.0, np.nan, 4.0, 9.0])
    pred2     = np.array([1.0, 2.0, 0.0, 9.0])   # idx1 nan-realised, idx2 zero-pred → dropped
    _, n = gv._qlike(realised2, pred2)
    assert n == 2


# ── garch_vol_frame — shape + causality ─────────────────────────────────────────
def test_frame_shape_and_nan_prefix():
    s = _vol_clustered_series(160)
    df = pd.DataFrame({"sp": s})
    out = gv.garch_vol_frame(df, asym=False, refit_every=20, min_train=60, use_cache=False)
    assert list(out.columns) == ["sp"]
    assert len(out) == len(s)
    # No forecast before min_train; positive (annualised $) after it warms up.
    assert out["sp"].iloc[:60].isna().all()
    warm = out["sp"].iloc[80:].dropna()
    assert len(warm) > 0
    assert (warm > 0).all()


def test_frame_is_causal_prefix_stable():
    """The forecast at day t must not change when FUTURE data is appended —
    refits land on fixed offsets from the start, so a prefix reproduces it."""
    s = _vol_clustered_series(180)
    short = gv.garch_vol_frame(pd.DataFrame({"sp": s.iloc[:120]}),
                               asym=False, refit_every=20, min_train=60, use_cache=False)
    full = gv.garch_vol_frame(pd.DataFrame({"sp": s}),
                              asym=False, refit_every=20, min_train=60, use_cache=False)
    # Compare the overlap up to a refit-safe cutoff (avoid the boundary day where
    # the longer series triggers a refit the prefix hasn't reached).
    a = short["sp"].iloc[60:100]
    b = full["sp"].iloc[60:100]
    common = a.dropna().index.intersection(b.dropna().index)
    assert len(common) > 10
    np.testing.assert_allclose(a.loc[common].values, b.loc[common].values, rtol=1e-9, atol=1e-12)


def test_annualisation_factor():
    """garch_vol_frame is annualised by √252 (matches vol_target.spread_vol_frame)."""
    assert gv.ANNUALISE == pytest.approx(np.sqrt(252.0))


def test_gjr_differs_from_plain():
    """The asymmetric (GJR) spec should produce a different vol path than plain
    GARCH on a series with sign-asymmetric shocks — i.e. the o=1 term is live."""
    rng = np.random.default_rng(3)
    n = 200
    shock = rng.normal(0, 1, n)
    shock[shock < 0] *= 2.0   # down-moves twice as large → asymmetry
    level = np.cumsum(shock * 0.3) + 50
    df = pd.DataFrame({"sp": pd.Series(level, index=pd.bdate_range("2020-01-01", periods=n))})
    plain = gv.garch_vol_frame(df, asym=False, refit_every=20, min_train=60, use_cache=False)
    gjr   = gv.garch_vol_frame(df, asym=True,  refit_every=20, min_train=60, use_cache=False)
    warm = slice(80, n)
    diff = (plain["sp"].iloc[warm] - gjr["sp"].iloc[warm]).abs().dropna()
    assert diff.mean() > 0  # the two specs are genuinely distinct


# ── forecast_accuracy table ─────────────────────────────────────────────────────
def test_forecast_accuracy_shape():
    df = pd.DataFrame({"a": _vol_clustered_series(160, 1), "b": _vol_clustered_series(160, 2)})
    fa = gv.forecast_accuracy(df, win=20)
    assert set(fa.keys()) == {"a", "b", "mean"}
    for sp in ("a", "b"):
        assert set(fa[sp]) >= {"garch", "gjr", "roll", "n"}
    assert set(fa["mean"]) == {"garch", "gjr", "roll"}


def test_degenerate_series_does_not_crash():
    """A flat (zero-variance) series can't be fit — should yield NaNs, not raise."""
    df = pd.DataFrame({"sp": pd.Series(np.full(160, 50.0), index=pd.bdate_range("2020-01-01", periods=160))})
    out = gv.garch_vol_frame(df, asym=False, refit_every=20, min_train=60, use_cache=False)
    assert len(out) == 160  # produced a frame; values may be NaN (no fit possible)
