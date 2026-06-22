"""
Phase 2 — gated decorrelated selection (backend/research/gated_select.py).

Behavioural tests for the greedy correlation filter that turns the ranked
opportunity list into the desk's actual (decorrelated) book. All unit tests pass
a synthetic correlation matrix so they're hermetic (no /Data, no models); one
integration test exercises the real spread universe and is skipped if /Data is
absent.
"""
import os

import pandas as pd
import pytest

from research.gated_select import (
    DEFAULT_RHO_MAX,
    instrument_corr_matrix,
    rho_max_from_env,
    select_decorrelated,
)

# Synthetic universe mirroring the real bimodal structure:
#   cluster 1 = {A, B} (ρ 0.87),  cluster 2 = {C, D} (ρ 0.76),  cross ≤ 0.30
_SPREADS = ["A", "B", "C", "D"]
_CORR = pd.DataFrame(
    [
        [1.00, 0.87, 0.30, 0.10],
        [0.87, 1.00, 0.01, 0.02],
        [0.30, 0.01, 1.00, 0.76],
        [0.10, 0.02, 0.76, 1.00],
    ],
    index=_SPREADS, columns=_SPREADS,
)


def _row(spread, direction, conf):
    return {"spread": spread, "direction": direction, "confidence": conf}


def test_same_direction_correlated_pair_drops_weaker():
    # A & B both BUY, raw ρ=0.87 ≥ 0.70 → redundant; keep higher-conviction A.
    ranked = [_row("A", "BUY", 0.9), _row("B", "BUY", 0.5)]
    out = select_decorrelated(ranked, corr=_CORR)
    assert out["selected"] == ["A"]
    assert [s["spread"] for s in out["skipped"]] == ["B"]
    skip = out["skipped"][0]
    assert skip["reason"] == "correlated"
    assert skip["correlated_with"] == "A"
    assert skip["rho"] == pytest.approx(0.87, abs=1e-6)


def test_opposite_direction_correlated_pair_is_a_hedge_kept():
    # A BUY + B SELL: signed corr = 0.87 · (+1) · (-1) = -0.87 < 0.70 → both kept.
    ranked = [_row("A", "BUY", 0.9), _row("B", "SELL", 0.5)]
    out = select_decorrelated(ranked, corr=_CORR)
    assert out["selected"] == ["A", "B"]
    assert out["skipped"] == []


def test_greedy_keeps_higher_conviction_member():
    # B ranked above A by confidence → B is the one kept, A is skipped.
    ranked = [_row("B", "BUY", 0.95), _row("A", "BUY", 0.40)]
    out = select_decorrelated(ranked, corr=_CORR)
    assert out["selected"] == ["B"]
    assert [s["spread"] for s in out["skipped"]] == ["A"]


def test_cross_cluster_both_kept():
    # A (cluster 1) + C (cluster 2), ρ=0.30 < 0.70 → both decorrelated, both kept.
    ranked = [_row("A", "BUY", 0.9), _row("C", "BUY", 0.8)]
    out = select_decorrelated(ranked, corr=_CORR)
    assert out["selected"] == ["A", "C"]
    assert out["skipped"] == []


def test_all_four_fire_one_per_cluster():
    # All four BUY, conviction A>B>C>D → take A & C, skip B (vs A) & D (vs C).
    ranked = [
        _row("A", "BUY", 0.9), _row("B", "BUY", 0.8),
        _row("C", "BUY", 0.7), _row("D", "BUY", 0.6),
    ]
    out = select_decorrelated(ranked, corr=_CORR)
    assert out["selected"] == ["A", "C"]
    skipped = {s["spread"]: s for s in out["skipped"]}
    assert set(skipped) == {"B", "D"}
    assert skipped["B"]["correlated_with"] == "A"
    assert skipped["D"]["correlated_with"] == "C"
    assert out["n_actionable"] == 4
    assert out["n_selected"] == 2


def test_neutral_rows_never_selected():
    ranked = [_row("A", "NEUTRAL", 0.99), _row("C", "BUY", 0.5)]
    out = select_decorrelated(ranked, corr=_CORR)
    assert out["selected"] == ["C"]
    assert out["n_actionable"] == 1


def test_unsorted_input_is_handled():
    # Pass rows out of confidence order; selection must still keep the strongest.
    ranked = [_row("A", "BUY", 0.40), _row("B", "BUY", 0.95)]
    out = select_decorrelated(ranked, corr=_CORR)
    assert out["selected"] == ["B"]


def test_max_positions_cap():
    ranked = [_row("A", "BUY", 0.9), _row("C", "BUY", 0.8)]  # would both pass corr
    out = select_decorrelated(ranked, corr=_CORR, max_positions=1)
    assert out["selected"] == ["A"]
    assert out["skipped"][0]["reason"] == "max_positions"


def test_empty_and_all_neutral():
    assert select_decorrelated([], corr=_CORR)["selected"] == []
    alln = [_row("A", "NEUTRAL", 0.5), _row("B", "NEUTRAL", 0.4)]
    out = select_decorrelated(alln, corr=_CORR)
    assert out["selected"] == []
    assert out["n_actionable"] == 0


def test_rho_max_from_env(monkeypatch):
    monkeypatch.delenv("PULSE_DECORREL_RHO", raising=False)
    assert rho_max_from_env() == DEFAULT_RHO_MAX
    monkeypatch.setenv("PULSE_DECORREL_RHO", "0.6")
    assert rho_max_from_env() == pytest.approx(0.6)
    monkeypatch.setenv("PULSE_DECORREL_RHO", "9")     # clamps to 1.0
    assert rho_max_from_env() == 1.0
    monkeypatch.setenv("PULSE_DECORREL_RHO", "junk")  # falls back
    assert rho_max_from_env() == DEFAULT_RHO_MAX


def test_threshold_is_inclusive():
    # A signed corr exactly == rho_max should skip (>= rule).
    corr = pd.DataFrame([[1.0, 0.70], [0.70, 1.0]], index=["A", "B"], columns=["A", "B"])
    ranked = [_row("A", "BUY", 0.9), _row("B", "BUY", 0.5)]
    out = select_decorrelated(ranked, corr=corr, rho_max=0.70)
    assert out["selected"] == ["A"]


@pytest.mark.skipif(
    not os.path.isdir(os.path.join(os.path.dirname(__file__), "..", "Data")),
    reason="/Data lake not present on this machine",
)
def test_real_universe_is_bimodal():
    """The real tradeable universe splits into two front-curve clusters."""
    m = instrument_corr_matrix()
    assert m.loc["brent_m1_m2", "brent_fly_123"] > 0.70
    assert m.loc["wti_m1_m2", "wti_fly_123"] > 0.70
    assert abs(m.loc["brent_m1_m2", "wti_m1_m2"]) < 0.70
    # All four front spreads BUY → at most one trade per cluster.
    ranked = [
        _row("brent_m1_m2", "BUY", 0.9), _row("brent_fly_123", "BUY", 0.8),
        _row("wti_m1_m2", "BUY", 0.7),   _row("wti_fly_123", "BUY", 0.6),
    ]
    out = select_decorrelated(ranked, corr=m)
    assert out["n_selected"] == 2
