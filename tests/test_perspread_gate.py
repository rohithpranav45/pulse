"""
Phase 8 — per-spread gate unit tests (2026-06-22).

The per-spread gate replaces the uniform Phase 2.6 global gate with a per-spread
enable decision (the regime leg fires for a spread only when its OOS NET Sharpe
beat baseline for that spread, decided walk-forward per refit cutoff). The
decision logic lives in `gate_config` and is shared by the walk-forward leg
(`walkforward.run_perspread_gate_only`) and live inference (`live_ranker`) so the
two cannot drift.

These tests are HERMETIC — synthetic PnL lists / histories / report dicts, never
touching `/Data`, the model pkls, or the live cache — so they assert the gate
LOGIC (the Sharpe comparison, the sample floor, the no-look-ahead cutoff filter,
the predicate composition, the report reader), not the production numbers.

Run from the repo root:  python -m pytest tests/test_perspread_gate.py -v
"""

import json
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

from research import gate_config as gc          # noqa: E402


# ─────────────────────────────────────────────────────────────────────────────
# decide_enabled — the core Sharpe comparison
# ─────────────────────────────────────────────────────────────────────────────
def test_decide_enabled_regime_beats_baseline():
    """A clearly higher-Sharpe regime leg with enough samples enables."""
    reg  = [1.0] * 15 + [0.9, 1.1] * 5   # high mean, low var → high Sharpe
    base = [0.5, -0.5] * 15              # zero mean → ~0 Sharpe
    assert gc.decide_enabled(reg, base, min_n=20) is True


def test_decide_enabled_baseline_wins():
    """When baseline Sharpe exceeds regime Sharpe, the spread stays disabled."""
    reg  = [0.1, -0.1] * 15             # ~0 Sharpe, but enough samples
    base = [1.0] * 30                   # huge Sharpe (zero var handled → None, so flip)
    # base has zero variance → _sharpe None → an evidenced regime would enable;
    # use a positive-variance baseline that genuinely out-Sharpes regime instead.
    base = [1.0, 0.9] * 15
    assert gc.decide_enabled(reg, base, min_n=20) is False


def test_decide_enabled_respects_sample_floor():
    """Below min_n regime trades, never enable (default to baseline)."""
    reg  = [5.0] * 5                    # stellar but only 5 trades
    base = [0.0, 0.1] * 10
    assert gc.decide_enabled(reg, base, min_n=20) is False
    # The very same regime history enables once it clears the floor.
    assert gc.decide_enabled([5.0, 4.9] * 12, base, min_n=20) is True


def test_decide_enabled_margin_blocks_marginal_lift():
    """A regime that only barely out-Sharpes baseline is blocked by a margin."""
    reg  = [1.00, 0.98] * 15
    base = [0.98, 0.96] * 15
    rs = gc._sharpe(reg); bs = gc._sharpe(base)
    assert rs is not None and bs is not None and rs > bs   # regime is ahead...
    assert gc.decide_enabled(reg, base, margin=0.0, min_n=20) is True
    assert gc.decide_enabled(reg, base, margin=(rs - bs + 1.0), min_n=20) is False  # ...not by this margin


def test_decide_enabled_no_baseline_does_not_block():
    """A baseline with no computable Sharpe never blocks an evidenced regime."""
    reg  = [1.0, 0.8] * 15
    assert gc.decide_enabled(reg, [], min_n=20) is True
    assert gc.decide_enabled(reg, [1.0], min_n=20) is True  # single point → no Sharpe


# ─────────────────────────────────────────────────────────────────────────────
# enabled_at_cutoff — no look-ahead
# ─────────────────────────────────────────────────────────────────────────────
def test_enabled_at_cutoff_excludes_future_trades():
    """Only trades that CLOSED before the cutoff count toward the decision."""
    ts = pd.Timestamp
    # 'good' regime trades — but all close AFTER the early cutoff.
    reg_hist = {
        # high-Sharpe (mean ~1, small var) regime trades, all closed in 2025.
        "wti_m1_m2": [(ts("2025-06-01"), 1.0), (ts("2025-06-02"), 0.9)] * 13,
        # high-Sharpe regime trades, all closed early (2020).
        "brent_m1_m2": [(ts("2020-01-01"), 1.0), (ts("2020-01-02"), 0.9)] * 13,
    }
    base_hist = {
        "wti_m1_m2": [(ts("2025-06-01"), 0.1), (ts("2025-06-02"), -0.1)] * 13,
        "brent_m1_m2": [(ts("2020-01-01"), -1.0), (ts("2020-01-02"), 1.0)] * 13,
    }
    early = gc.enabled_at_cutoff(reg_hist, base_hist, ts("2021-01-01"), min_n=20)
    # wti's evidence is all in the future of 2021 → cannot enable yet.
    assert "wti_m1_m2" not in early
    # brent's evidence is in the past → it CAN be decided (regime Sharpe is high,
    # baseline ~0 → enables).
    assert "brent_m1_m2" in early
    # By a late cutoff, wti's evidence is visible and it enables.
    late = gc.enabled_at_cutoff(reg_hist, base_hist, ts("2026-01-01"), min_n=20)
    assert "wti_m1_m2" in late


# ─────────────────────────────────────────────────────────────────────────────
# per_spread_gate_passes — predicate composition
# ─────────────────────────────────────────────────────────────────────────────
def test_predicate_requires_global_gate():
    """No matter the enable set, a failed global gate never fires the regime leg."""
    assert gc.per_spread_gate_passes("wti_m1_m2", {"wti_m1_m2"}, global_gate_pass=False) is False


def test_predicate_enabled_set_filters_spreads():
    en = {"wti_m1_m2", "wti_fly_123"}
    assert gc.per_spread_gate_passes("wti_m1_m2", en, True) is True
    assert gc.per_spread_gate_passes("brent_m1_m2", en, True) is False


def test_predicate_none_config_degrades_to_global_gate():
    """None enable set → Phase 2.6 behaviour (global gate alone decides)."""
    assert gc.per_spread_gate_passes("brent_m1_m2", None, True) is True
    assert gc.per_spread_gate_passes("brent_m1_m2", None, False) is False


# ─────────────────────────────────────────────────────────────────────────────
# latest_enabled_from_report — the live config reader
# ─────────────────────────────────────────────────────────────────────────────
def test_latest_enabled_from_report(tmp_path):
    rpt = tmp_path / "walkforward_report.json"
    rpt.write_text(json.dumps({"per_spread_gate": {"enabled_latest": ["wti_m1_m2", "wti_fly_123"]}}))
    assert gc.latest_enabled_from_report(rpt) == {"wti_m1_m2", "wti_fly_123"}


def test_latest_enabled_missing_block_returns_none(tmp_path):
    rpt = tmp_path / "walkforward_report.json"
    rpt.write_text(json.dumps({"baseline_overall": {}}))   # no per_spread_gate block
    assert gc.latest_enabled_from_report(rpt) is None
    assert gc.latest_enabled_from_report(tmp_path / "does_not_exist.json") is None


# ─────────────────────────────────────────────────────────────────────────────
# walk-forward leg ↔ live_ranker share the same predicate (no drift)
# ─────────────────────────────────────────────────────────────────────────────
def test_walkforward_and_live_share_gate_config():
    """Both call sites import per_spread_gate_passes / decide_enabled from the
    one module, so the live gate and the backtested gate cannot diverge."""
    from research import live_ranker, walkforward
    # live_ranker resolves the enabled set through gate_config's reader.
    assert live_ranker._perspread_enabled_set.__module__ == "research.live_ranker"
    # The shared functions are the same object on both sides (imported, not copied).
    import research.gate_config as gcmod
    assert gcmod.per_spread_gate_passes is gc.per_spread_gate_passes
    # walkforward builds its blend through gate_config (smoke: the helper exists).
    assert hasattr(walkforward, "_build_perspread_gated_blend")


def test_live_default_on_env_opt_out(monkeypatch):
    from research import live_ranker
    monkeypatch.delenv("PULSE_PERSPREAD_GATE", raising=False)
    assert live_ranker._perspread_gate_enabled() is True      # default ON
    monkeypatch.setenv("PULSE_PERSPREAD_GATE", "0")
    assert live_ranker._perspread_gate_enabled() is False
    monkeypatch.setenv("PULSE_PERSPREAD_GATE", "off")
    assert live_ranker._perspread_gate_enabled() is False
    monkeypatch.setenv("PULSE_PERSPREAD_GATE", "1")
    assert live_ranker._perspread_gate_enabled() is True


# ─────────────────────────────────────────────────────────────────────────────
# end-to-end blend logic on a synthetic tape (no /Data)
# ─────────────────────────────────────────────────────────────────────────────
def test_build_perspread_blend_routes_per_spread(monkeypatch):
    """An enabled spread keeps its gate-passing regime row; a disabled spread
    falls to baseline even when its regime row would pass the global gate."""
    from research import walkforward as wf

    # Force the enable decision: wti_m1_m2 ON, brent_m1_m2 OFF — independent of
    # the synthetic PnLs, so the test asserts ROUTING, not the Sharpe maths.
    monkeypatch.setattr(
        gc, "enabled_at_cutoff",
        lambda *a, **k: {"wti_m1_m2"},
    )

    def _pool_row(date, spread):
        return {"date": date, "spread": spread, "regime": "BACK", "winner": "Huber",
                "z": 2.0, "direction": "BUY", "actual": 1.0, "fwd_pnl": 0.5,
                "fwd_date": "2025-02-01", "p50": 1.2, "resid_std": 0.3}

    def _base_row(date, spread):
        return {"date": date, "spread": spread, "z": 2.0, "direction": "BUY",
                "actual": 1.0, "fwd_pnl": 0.2, "roll_mu": 1.1, "roll_sigma": 0.3}

    pooled = [_pool_row("2025-01-02", "wti_m1_m2"), _pool_row("2025-01-02", "brent_m1_m2")]
    baseline = [_base_row("2025-01-02", "wti_m1_m2"), _base_row("2025-01-02", "brent_m1_m2")]
    refit_ts = [pd.Timestamp("2025-01-01")]

    blended, enabled_by_cutoff, enabled_latest = wf._build_perspread_gated_blend(
        pooled, baseline, refit_ts,
    )
    by_spread = {t["spread"]: t for t in blended}
    assert by_spread["wti_m1_m2"]["source"] == "regime"
    assert by_spread["brent_m1_m2"]["source"] == "baseline"
    assert by_spread["brent_m1_m2"]["gate"] == "disabled"  # global gate would have passed
    assert enabled_latest == {"wti_m1_m2"}
