"""
Phase 7 — research-leg unit tests (2.8.10 portfolio vol-targeting).

The vol-target leg is an additive POST-PROCESSING pass on the Phase 2.8
walk-forward (see CLAUDE.md §1): it reweights the persisted gated trade tape's
notionals (it never retrains). These tests are HERMETIC — tiny synthetic
tapes / vol / stress / correlation frames, never touching `/Data`, the model
pkls, or the live cache — so they assert the sizing LOGIC (risk parity, stress
de-risk, the decorrelated selection, the portfolio overlay, normalisation), not
the production numbers.

Run from the repo root:  python -m pytest tests/test_phase7_research.py -v
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

from research import vol_target as vt          # noqa: E402
from research import walkforward as wf         # noqa: E402


# ─────────────────────────────────────────────────────────────────────────────
# Inputs — synthetic spreads / correlation
# ─────────────────────────────────────────────────────────────────────────────
def _toy_corr(spreads):
    """Identity correlation (uncorrelated) over the given spread names."""
    return pd.DataFrame(np.eye(len(spreads)), index=spreads, columns=spreads)


def test_spread_vol_frame_annualises():
    idx = pd.bdate_range("2024-01-01", periods=60)
    # A spread whose daily change is a constant ±1 alternation → known std.
    chg = np.where(np.arange(60) % 2 == 0, 1.0, -1.0)
    level = pd.Series(np.cumsum(chg), index=idx)
    sv = vt.spread_vol_frame(pd.DataFrame({"brent_m1_m2": level}), win=20)
    v = sv["brent_m1_m2"].iloc[-1]
    # std of a ±1 series over a window ≈ 1.0; annualised by √252.
    assert v == pytest.approx(np.sqrt(252.0), rel=0.05)


# ─────────────────────────────────────────────────────────────────────────────
# book_vol — risk aggregation with sign + correlation
# ─────────────────────────────────────────────────────────────────────────────
def test_book_vol_uncorrelated_adds_in_quadrature():
    corr = _toy_corr(["a", "b"])
    # Two uncorrelated unit-risk positions → √(1²+1²).
    bv = vt.book_vol([("a", 1.0, 1.0), ("b", 1.0, 1.0)], corr)
    assert bv == pytest.approx(np.sqrt(2.0), rel=1e-6)


def test_book_vol_hedge_lowers_vol():
    corr = pd.DataFrame([[1.0, 0.9], [0.9, 1.0]], index=["a", "b"], columns=["a", "b"])
    same = vt.book_vol([("a", 1.0, 1.0), ("b", 1.0, 1.0)], corr)   # same direction
    hedge = vt.book_vol([("a", 1.0, 1.0), ("b", -1.0, 1.0)], corr) # opposite direction
    # Positively-correlated same-direction book is riskier than the hedge.
    assert hedge < same


# ─────────────────────────────────────────────────────────────────────────────
# size_day — decorrelation, parity, stress, portfolio overlay
# ─────────────────────────────────────────────────────────────────────────────
def _rows(*specs):
    """specs: (spread, direction, z, fwd_pnl)."""
    return [{"date": "2024-06-03", "spread": sp, "direction": d, "z": z, "fwd_pnl": p}
            for sp, d, z, p in specs]


def test_size_day_drops_neutral_and_missing_pnl():
    corr = _toy_corr(["brent_m1_m2", "wti_m1_m2"])
    rows = _rows(("brent_m1_m2", "BUY", 2.0, 0.5)) + [
        {"date": "2024-06-03", "spread": "wti_m1_m2", "direction": "NEUTRAL", "z": 0.1, "fwd_pnl": 0.0},
        {"date": "2024-06-03", "spread": "brent_fly_123", "direction": "BUY", "z": 1.0, "fwd_pnl": None},
    ]
    cfg = vt.VolTargetConfig(decorrelate=False, vol_scale=False, stress=False, portfolio=False)
    held = vt.size_day(rows, fcast_vol={}, p_stress=0.0, corr=corr, cfg=cfg,
                       target_pos_vol=2.0, target_book_vol=3.0)
    assert [r["spread"] for r, _ in held] == ["brent_m1_m2"]
    assert held[0][1] == pytest.approx(1.0)   # flat notional, all layers off


def test_size_day_risk_parity_equalises_risk():
    corr = _toy_corr(["a", "b"])
    rows = _rows(("a", "BUY", 2.0, 1.0), ("b", "BUY", 1.5, 1.0))
    cfg = vt.VolTargetConfig(decorrelate=False, vol_scale=True, stress=False, portfolio=False,
                             floor=0.0, cap=10.0)
    # a is twice as volatile as b → a should be sized half of b for equal risk.
    held = dict((r["spread"], n) for r, n in
                vt.size_day(rows, fcast_vol={"a": 4.0, "b": 2.0}, p_stress=0.0, corr=corr,
                            cfg=cfg, target_pos_vol=2.0, target_book_vol=3.0))
    assert held["a"] == pytest.approx(0.5)   # 2/4
    assert held["b"] == pytest.approx(1.0)   # 2/2


def test_size_day_stress_derisks():
    corr = _toy_corr(["a"])
    rows = _rows(("a", "BUY", 2.0, 1.0))
    common = dict(fcast_vol={"a": 2.0}, p_stress=1.0, corr=corr,
                  target_pos_vol=2.0, target_book_vol=3.0)
    no_stress = vt.size_day(rows, cfg=vt.VolTargetConfig(
        decorrelate=False, vol_scale=True, stress=False, portfolio=False), **common)
    with_stress = vt.size_day(rows, cfg=vt.VolTargetConfig(
        decorrelate=False, vol_scale=True, stress=True, portfolio=False, derisk=0.75), **common)
    # P(stress)=1 with derisk 0.75 → size cut to a quarter.
    assert with_stress[0][1] < no_stress[0][1]
    assert with_stress[0][1] == pytest.approx(no_stress[0][1] * 0.25, rel=1e-6)


def test_size_day_decorrelation_drops_correlated_same_direction():
    # Two highly +correlated, same-direction trades → the weaker |z| is dropped.
    corr = pd.DataFrame([[1.0, 0.9], [0.9, 1.0]],
                        index=["brent_m1_m2", "brent_fly_123"],
                        columns=["brent_m1_m2", "brent_fly_123"])
    rows = _rows(("brent_m1_m2", "BUY", 3.0, 1.0), ("brent_fly_123", "BUY", 1.0, 1.0))
    cfg = vt.VolTargetConfig(decorrelate=True, vol_scale=False, stress=False, portfolio=False,
                             rho_max=0.7)
    held = [r["spread"] for r, _ in vt.size_day(
        rows, fcast_vol={}, p_stress=0.0, corr=corr, cfg=cfg,
        target_pos_vol=2.0, target_book_vol=3.0)]
    assert held == ["brent_m1_m2"]   # higher conviction kept, fly dropped


def test_size_day_portfolio_overlay_levers_thin_book_up():
    corr = _toy_corr(["a"])
    rows = _rows(("a", "BUY", 2.0, 1.0))
    # One target-vol position → book vol = target_pos_vol < target_book_vol(√2·)
    # → overlay scales the book UP toward target.
    base = vt.size_day(rows, fcast_vol={"a": 2.0}, p_stress=0.0, corr=corr,
                       cfg=vt.VolTargetConfig(decorrelate=False, vol_scale=True,
                                              stress=False, portfolio=False),
                       target_pos_vol=2.0, target_book_vol=2.0 * np.sqrt(2))
    over = vt.size_day(rows, fcast_vol={"a": 2.0}, p_stress=0.0, corr=corr,
                       cfg=vt.VolTargetConfig(decorrelate=False, vol_scale=True,
                                              stress=False, portfolio=True),
                       target_pos_vol=2.0, target_book_vol=2.0 * np.sqrt(2))
    assert over[0][1] > base[0][1]
    assert over[0][1] == pytest.approx(base[0][1] * np.sqrt(2), rel=1e-6)


# ─────────────────────────────────────────────────────────────────────────────
# apply_vol_target — normalisation + tape reshaping
# ─────────────────────────────────────────────────────────────────────────────
def _toy_tape(n_days=40, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2024-01-01", periods=n_days)
    tape = []
    for d in idx:
        for sp in ("brent_m1_m2", "wti_m1_m2"):
            z = float(rng.normal(0, 2))
            direction = "BUY" if z < -0.5 else "SELL" if z > 0.5 else "NEUTRAL"
            tape.append({"date": d.strftime("%Y-%m-%d"), "spread": sp,
                         "direction": direction, "z": z,
                         "fwd_pnl": float(rng.normal(0, 1)) if direction != "NEUTRAL" else None})
    return tape, idx


def test_apply_vol_target_normalises_mean_notional_to_one():
    tape, idx = _toy_tape()
    spreads = pd.DataFrame(
        {"brent_m1_m2": np.cumsum(np.ones(len(idx))),
         "wti_m1_m2":   np.cumsum(np.ones(len(idx)) * 2)}, index=idx)
    sv = vt.spread_vol_frame(spreads, win=5)
    stress = pd.Series(0.1, index=idx)
    corr = _toy_corr(["brent_m1_m2", "wti_m1_m2"])
    sized = vt.apply_vol_target(tape, spread_vol=sv, stress=stress, corr=corr,
                                cfg=vt.VolTargetConfig(), normalize=True)
    assert sized, "expected a non-empty vol-targeted book"
    # mean ≈ 1.0 (sizing_scale is rounded to 4 dp, so allow rounding slack).
    assert np.mean([r["sizing_scale"] for r in sized]) == pytest.approx(1.0, abs=1e-3)
    # Only fired (non-NEUTRAL) positions survive; pnl scaled by its notional.
    assert all(r["direction"] in ("BUY", "SELL") for r in sized)


def test_apply_vol_target_feeds_cost_model_via_sizing_scale():
    """The reweighted rows must carry sizing_scale so walkforward._cost_for
    scales the round-trip cost in step (the cost↔sizing invariant)."""
    tape, idx = _toy_tape(seed=3)
    spreads = pd.DataFrame(
        {"brent_m1_m2": np.cumsum(np.ones(len(idx))),
         "wti_m1_m2":   np.cumsum(np.ones(len(idx)))}, index=idx)
    sv = vt.spread_vol_frame(spreads, win=5)
    sized = vt.apply_vol_target(tape, spread_vol=sv, stress=pd.Series(0.0, index=idx),
                                corr=_toy_corr(["brent_m1_m2", "wti_m1_m2"]),
                                cfg=vt.VolTargetConfig())
    r = sized[0]
    cost = wf._cost_for(r)
    base = wf.COST_PER_SPREAD_RT[r["spread"]]
    assert cost == pytest.approx(base * r["sizing_scale"], rel=1e-9)


# ─────────────────────────────────────────────────────────────────────────────
# walkforward plumbing — variant config + Calmar
# ─────────────────────────────────────────────────────────────────────────────
def test_voltarget_cfg_flags_per_variant():
    assert wf._voltarget_cfg("decorrelated").portfolio is False
    assert wf._voltarget_cfg("risk_parity").vol_scale is True
    assert wf._voltarget_cfg("risk_parity").stress is False
    assert wf._voltarget_cfg("parity_stress").stress is True
    full = wf._voltarget_cfg("vol_target")
    assert full.decorrelate and full.vol_scale and full.stress and full.portfolio


def test_calmar_and_summary():
    assert wf._calmar({"total_pnl": 10.0, "max_drawdown": -4.0}) == pytest.approx(2.5)
    assert wf._calmar({"total_pnl": 10.0, "max_drawdown": 0.0}) is None
    s = wf._voltarget_summary({"overall": {"sharpe": 1.2, "max_drawdown": -3.0,
                                           "total_pnl": 6.0, "n_signals": 50,
                                           "hit_rate": 0.6, "mean_pnl": 0.12}})
    assert s["calmar"] == pytest.approx(2.0) and s["sharpe"] == 1.2
