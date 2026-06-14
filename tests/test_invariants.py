"""
PULSE cross-module invariants — Phase 3.0.

Several constants are deliberately duplicated across modules (for decoupling), but
they MUST stay in sync, or:
  • the live engine fires on signals the walk-forward never validated,
  • the paper book closes positions on the wrong horizon, or
  • the paper NET headline drifts from the methodology PDF.

These tests assert the duplicates by *importing both sides and comparing the live
values*, so they fail loudly the moment one side changes without the other.
See CLAUDE.md §5 gotchas 7-9 (and history gotchas 26 / 35 / 42 / 48).

Run from the repo root:  python -m pytest tests/test_invariants.py -v
"""

from research import live_ranker, walkforward, ab_test
import paper_trading


# ── Gate mirror: live_ranker ↔ walkforward ─────────────────────────────────────
# The production gate (regime + winning model + entry z) must be bit-for-bit
# identical, or the live engine fires on a rule the backtest never scored.

def test_gate_winners_match():
    assert live_ranker.GATED_WINNERS == walkforward.GATED_WINNERS


def test_gate_regime_matches():
    assert live_ranker.GATED_REGIME == walkforward.GATED_REGIME


def test_gate_z_threshold_matches():
    assert live_ranker.GATED_Z_THRESHOLD == walkforward.GATED_Z_THRESHOLD


def test_rolling_baseline_window_matches():
    assert live_ranker.ROLLING_WIN == walkforward.ROLLING_WIN


# ── Tuned exit-rule mirror: live_ranker ↔ paper_trading ────────────────────────
# The time-stop is the one tuned-rule value duplicated as an integer (TP/SL flow
# through the recommendation, so they can't drift); keep the mirror exact.

def test_time_stop_mirror():
    assert live_ranker.TUNED_MAX_HOLD_DAYS == paper_trading.TUNED_MAX_HOLD_TRADING_DAYS


def test_tuned_exit_params_are_sane():
    assert 0 < live_ranker.TUNED_TP_FRAC <= 1.0
    assert live_ranker.TUNED_SL_MULT > 0
    assert live_ranker.TUNED_MAX_HOLD_DAYS > 0


def test_excluded_spreads_are_the_m3m6_laggards():
    # Phase 2.9.1 dropped the two PF<1 spreads from the live tradeable universe.
    assert live_ranker.TUNED_EXCLUDED_SPREADS == {"brent_m3_m6", "wti_m3_m6"}


# ── A/B cost mirror: ab_test ↔ walkforward ─────────────────────────────────────
# The cost table is a reporting layer duplicated in the A/B harness; if it drifts,
# the live paper NET Sharpe no longer matches the methodology PDF's NET Sharpe.

def test_ab_cost_table_matches_walkforward():
    assert ab_test.COST_PER_SPREAD_RT == walkforward.COST_PER_SPREAD_RT


def test_ab_cost_default_matches_walkforward():
    assert ab_test.COST_DEFAULT_RT == walkforward.COST_DEFAULT_RT
