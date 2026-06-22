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

from research import live_ranker, walkforward, ab_test, gate_config
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


# ── Phase 8 per-spread gate: single source of truth ────────────────────────────
# The per-spread gate layer must NOT be duplicated — both the walk-forward leg and
# live inference call the SAME gate_config functions, so the live gate and the
# backtested gate cannot drift. (The global-gate predicate above stays mirrored as
# constants; the per-spread layer lives only in gate_config.)

def test_perspread_gate_is_single_source():
    import research.gate_config as gcmod
    assert gcmod is gate_config
    # walkforward builds its per-spread blend through gate_config (not a copy).
    assert hasattr(walkforward, "_build_perspread_gated_blend")
    # live_ranker reads the enable set through gate_config's reader.
    assert hasattr(live_ranker, "_perspread_enabled_set")
    # The shared predicate/decision functions exist and are callable.
    assert callable(gate_config.per_spread_gate_passes)
    assert callable(gate_config.decide_enabled)
    assert callable(gate_config.latest_enabled_from_report)


def test_perspread_gate_degrades_to_global_gate():
    """With no per-spread config (None), the layer must reduce to the global gate
    exactly — so a report predating Phase 8 keeps the Phase 2.6 behaviour."""
    assert gate_config.per_spread_gate_passes("any_spread", None, True) is True
    assert gate_config.per_spread_gate_passes("any_spread", None, False) is False


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


# ── Phase 4.G — signal_log session dedup ───────────────────────────────────────
# The Signal Log used to UNIQUE on (instrument, direction, feed_as_of, cadence),
# which produced one row per 15-min bar per persistent opportunity. The session
# dedup migration replaces it with (instrument, direction, opened_at_session).
# If a future change reintroduces the old key, the log floods again.

def test_signal_log_dedup_keys():
    """The only UNIQUE on signal_log must be (instrument, direction, opened_at_session)."""
    import sqlite3
    import tempfile

    from research import signal_log as sl

    # Run ensure_schema against a fresh DB so we don't depend on the live cache.
    with tempfile.TemporaryDirectory() as td:
        db_path = f"{td}/cache.db"
        original = sl._DB_PATH
        sl._DB_PATH = db_path
        try:
            sl.ensure_schema()
            c = sqlite3.connect(db_path)
            try:
                sql = c.execute(
                    "SELECT sql FROM sqlite_master WHERE type='table' AND name='signal_log'"
                ).fetchone()[0]
                assert "instrument, direction, opened_at_session" in sql, sql
                assert "feed_as_of, cadence" not in sql, sql
                cols = {r[1] for r in c.execute("PRAGMA table_info(signal_log)").fetchall()}
                assert {"opened_at_session", "bar_count", "last_seen_at"}.issubset(cols)
            finally:
                c.close()
        finally:
            sl._DB_PATH = original
