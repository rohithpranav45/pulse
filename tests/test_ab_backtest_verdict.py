"""
A/B backtest-verdict tests (2026-06-22).

The live A/B forward book can't reach a verdict fast (trades hold ~6 weeks; it
needs ≥30 closed/arm), so `ab_test.backtest_verdict()` surfaces the SAME
pooled-vs-gated comparison computed instantly from the walk-forward tapes
(thousands of closed trades). These tests run against the committed tapes
(skip cleanly if they're absent) and assert the shape + internal consistency,
not the exact production numbers.

Run from the repo root:  python -m pytest tests/test_ab_backtest_verdict.py -v
"""

import math
import os
import sys
import warnings

import pytest

warnings.filterwarnings("ignore")

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from research import ab_test  # noqa: E402

_TAPES = os.path.join(_BACKEND, "data", "research")
_HAVE_TAPES = (os.path.exists(os.path.join(_TAPES, "pooled_trades.json"))
               and os.path.exists(os.path.join(_TAPES, "gated_trades.json")))
needs_tapes = pytest.mark.skipif(not _HAVE_TAPES, reason="walk-forward tapes not present")


@needs_tapes
def test_backtest_verdict_shape():
    bv = ab_test.backtest_verdict(force=True)
    assert bv["available"] is True
    for arm in ("pooled", "gated", "baseline"):
        a = bv["arms"][arm]
        assert a is not None and a["n_closed"] > 100         # thousands in practice
        assert 0.0 <= a["hit_rate"] <= 1.0
    assert bv["verdict"] in {"tied", "pooled_wins", "gated_wins"}
    assert bv["welch"]["p_value"] is not None


@needs_tapes
def test_verdict_consistent_with_welch_and_sharpe():
    """A 'win' must mean p<0.05 AND the higher Sharpe; 'tied' means p>=0.05."""
    bv = ab_test.backtest_verdict(force=True)
    p = bv["welch"]["p_value"]
    sp = bv["arms"]["pooled"]["sharpe_net"]
    sg = bv["arms"]["gated"]["sharpe_net"]
    if bv["verdict"] == "tied":
        assert p >= ab_test.P_VALUE_LT
    else:
        assert p < ab_test.P_VALUE_LT
        winner = "pooled" if (sp or 0) > (sg or 0) else "gated"
        assert bv["verdict"] == f"{winner}_wins"


@needs_tapes
def test_report_embeds_backtest_verdict():
    """get_report() must carry the instant backtest verdict alongside the live arms."""
    rpt = ab_test.get_report()
    assert "backtest_verdict" in rpt
    assert rpt["backtest_verdict"]["available"] is True


def test_welch_t_basic():
    """Sanity on the reused Welch helper: identical samples → ~0 t-stat, high p."""
    a = [1.0, 2.0, 3.0, 4.0, 5.0]
    out = ab_test._welch_t(a, list(a))
    assert out["t_stat"] is not None and abs(out["t_stat"]) < 1e-6
    assert out["p_value"] is not None and out["p_value"] > 0.9


def test_welch_t_too_few():
    assert ab_test._welch_t([1.0], [2.0, 3.0])["p_value"] is None
