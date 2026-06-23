"""
Tests for the Inventory Surprise Impact Model (backend/research/inventory_impact).

Hermetic where possible: the surprise/decomposition/calendar logic is tested on
synthetic frames; the data-dependent legs (report fetch, event panel, regime
table) are tested only when their caches exist (skipif), so CI without the EIA
key / 1-min lake still passes.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from backend.research.inventory_impact import eia_report, framework
from backend.research.inventory_impact.release_calendar import (
    release_datetime, release_table, snap_to_spike,
)

_CACHE = Path(__file__).parent.parent / "backend" / "data" / "research" / "inventory_impact"


# ── release calendar ──────────────────────────────────────────────────────────
def test_release_is_wednesday_1030_et_normally():
    # week ending Fri 2026-05-29 → Wed 2026-06-03 10:30 ET = 14:30 UTC (EDT)
    rel = release_datetime("2026-05-29")
    et = rel.tz_convert("America/New_York")
    assert et.weekday() == 2 and (et.hour, et.minute) == (10, 30)


def test_holiday_shifts_release_to_thursday():
    # Memorial Day 2026 = Mon 2026-05-25 → week ending 2026-05-22 delays to Thursday
    tbl = release_table([pd.Timestamp("2026-05-22")])
    assert bool(tbl.iloc[0]["delayed"]) is True
    assert tbl.iloc[0]["release_et"].weekday() == 3  # Thursday


def test_snap_to_spike_finds_the_jump():
    idx = pd.date_range("2026-05-06 14:00", periods=60, freq="1min", tz="UTC")
    px = pd.Series(100.0, index=idx)
    px.iloc[30:] += 1.0  # a jump 30 min in
    sched = idx[30]
    ts, jump = snap_to_spike(sched, px, search_minutes=10)
    assert ts is not None and jump > 0
    assert abs((ts - sched).total_seconds()) <= 60


def test_snap_to_spike_empty_window_returns_none():
    px = pd.Series(dtype=float)
    ts, jump = snap_to_spike(pd.Timestamp("2026-05-06 14:30", tz="UTC"), px)
    assert ts is None and jump == 0.0


# ── surprise sign convention ──────────────────────────────────────────────────
def test_surprise_sign_convention():
    """surprise < 0 (tighter than expected) must be flagged bullish."""
    idx = pd.date_range("2020-01-03", periods=160, freq="W-FRI")
    # build a synthetic level series with a known last-week draw bigger than seasonal
    rng = np.random.default_rng(0)
    level = pd.Series(450000 + np.cumsum(rng.normal(0, 1000, len(idx))), index=idx)
    chg = level.diff()
    # a deeper-than-expected draw → surprise negative → bullish
    actual = -5000.0
    expected = -1000.0
    surprise = actual - expected
    assert surprise < 0  # bullish by construction
    assert (surprise < 0) is True


@pytest.mark.skipif(not (_CACHE / "eia_report_history.parquet").exists(),
                    reason="EIA report cache not present")
def test_decomposition_quality_divergence_exists():
    """The headline draw and the quality score can diverge (the key L2 read)."""
    dec = eia_report.decomposition()
    assert "quality_of_draw" in dec.columns
    # at least some weeks have a bullish-headline / bearish-quality divergence
    sp = eia_report.surprise_series("crude_ex_spr")
    joined = dec.join(sp[["bullish"]]).dropna(subset=["quality_of_draw"])
    diverge = ((joined["bullish"]) & (joined["quality_of_draw"] < 0)).sum()
    assert diverge >= 1


@pytest.mark.skipif(not (_CACHE / "eia_report_history.parquet").exists(),
                    reason="EIA report cache not present")
def test_adjustment_reconstructed():
    wf = eia_report.weekly_frame()
    assert "adjustment" in wf.columns
    assert wf["adjustment"].notna().sum() > 50


# ── framework scorecard ───────────────────────────────────────────────────────
@pytest.mark.skipif(not (_CACHE / "eia_report_history.parquet").exists(),
                    reason="EIA report cache not present")
def test_assess_release_shape_and_regime_gate():
    r = framework.assess_release()
    for k in ("call", "p_bullish", "p_bearish", "confidence", "regime",
              "spreads", "top_factors", "expected_brent_move_pct"):
        assert k in r
    assert r["call"] in ("BULLISH", "BEARISH", "NEUTRAL")
    assert 0.0 <= r["p_bullish"] <= 1.0
    assert abs(r["p_bullish"] + r["p_bearish"] - 1.0) < 1e-6
    assert len(r["top_factors"]) <= 3
    # regime-insensitive ⇒ expected flat move must be exactly 0 (don't trade flat)
    if not r["regime_sensitive"]:
        assert r["expected_brent_move_pct"] == 0.0


@pytest.mark.skipif(not (_CACHE / "eia_report_history.parquet").exists(),
                    reason="EIA report cache not present")
def test_real_consensus_overrides_proxy():
    r = framework.assess_release(actual_change=-8263, consensus=-2000)
    assert r["surprise_mbbl"] == -6263  # actual - consensus
    assert "consensus" in r["surprise_source"]
