"""
Phase 4 — live-feed-driven stress read (shock_engine + live_feed).

Two layers:
  • live_feed.recent_daily_frame — resamples the 15-min feed to a daily c1/c12
    close frame (hermetic: builds a tiny temp feed db, no office share).
  • shock_engine.live_stress_state(use_live_feed=True) — scores the fitted
    detector on those live daily closes, and FALLS BACK to the daily-settle read
    until the recorder has enough history. The detector fit needs /Data, so the
    two stress-state tests are skipped when the lake is absent.
"""
import os
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_BACKEND = os.path.join(_ROOT, "backend")
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from research import live_feed as lf       # noqa: E402
from research import shock_engine as se    # noqa: E402

_HAS_DATA = os.path.isdir(os.path.join(_ROOT, "Data"))

# 12 contracts in ascending-expiry order → c1 = first, c12 = last.
_MONTHS = ["Q26", "U26", "V26", "X26", "Z26", "F27",
           "G27", "H27", "J27", "K27", "M27", "N27"]


def _make_feed_db(path: str):
    """A minimal bars_*.db: 12 CO contracts, 2 trading days of 15-min bars each."""
    conn = sqlite3.connect(path)
    try:
        for i, mc in enumerate(_MONTHS):
            tbl = f"CO_{mc}"
            conn.execute(
                f'CREATE TABLE "{tbl}" (timestamp TEXT, open REAL, high REAL, '
                f'low REAL, close REAL, volume REAL)'
            )
            # Two days; the LAST bar each day is what daily-resample must pick.
            rows = []
            for day in ("2026-06-18", "2026-06-19"):
                for hh, close in (("09:00", 80 - i + 0.0), ("16:45", 80 - i + 0.5)):
                    rows.append((f"{day} {hh}:00", close, close, close, close, 100))
            conn.executemany(
                f'INSERT INTO "{tbl}" VALUES (?,?,?,?,?,?)', rows
            )
        conn.commit()
    finally:
        conn.close()


def test_recent_daily_frame_resamples(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        db = os.path.join(td, "bars_15min_20260619.db")
        _make_feed_db(db)
        monkeypatch.setenv("PULSE_LIVE_FEED_DIR", td)

        df = lf.recent_daily_frame("CO", days=40)
        assert df is not None and not df.empty
        assert list(df.columns) == ["c1", "c12"]
        # Two calendar days resampled → two rows, last close per day.
        assert len(df) == 2
        # c1 = front contract (i=0) last close = 80.5; c12 = last (i=11) = 69.5.
        assert df["c1"].iloc[-1] == pytest.approx(80.5)
        assert df["c12"].iloc[-1] == pytest.approx(69.5)


def test_recent_daily_frame_none_when_no_feed(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        monkeypatch.setenv("PULSE_LIVE_FEED_DIR", td)   # empty dir, no bars_*.db
        assert lf.recent_daily_frame("CO") is None


def _synthetic_daily(n: int, *, vol: float = 0.01, seed: int = 0) -> pd.DataFrame:
    """n business days of c1/c12 closes — a calm series (low realised vol)."""
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range(end=datetime(2026, 6, 19), periods=n)
    c1 = 80.0 * np.cumprod(1 + rng.normal(0, vol, n))
    return pd.DataFrame({"c1": c1, "c12": c1 - 6.0}, index=idx)


@pytest.mark.skipif(not _HAS_DATA, reason="/Data lake (detector fit) not present")
def test_live_stress_uses_feed_when_enough_history(monkeypatch):
    # 45 calm daily closes → enough for a clean 20d window → live read engages.
    monkeypatch.setattr(lf, "recent_daily_frame",
                        lambda *a, **k: _synthetic_daily(45))
    out = se.live_stress_state(use_live_feed=True, refit=True)
    assert out["live"] is True
    assert out["source"] == "live_feed"
    assert out["live_fallback_reason"] is None
    assert 0.0 <= out["p_stress"] <= 1.0


@pytest.mark.skipif(not _HAS_DATA, reason="/Data lake (detector fit) not present")
def test_live_stress_falls_back_on_thin_history(monkeypatch):
    # Only 5 daily rows → can't form a 20d window → honest fall back to settle.
    monkeypatch.setattr(lf, "recent_daily_frame",
                        lambda *a, **k: _synthetic_daily(5))
    out = se.live_stress_state(use_live_feed=True, refit=True)
    assert out["live"] is False
    assert out["source"] == "daily_settle"
    assert out["live_fallback_reason"] and "insufficient" in out["live_fallback_reason"]


@pytest.mark.skipif(not _HAS_DATA, reason="/Data lake (detector fit) not present")
def test_live_stress_falls_back_when_feed_absent(monkeypatch):
    monkeypatch.setattr(lf, "recent_daily_frame", lambda *a, **k: None)
    out = se.live_stress_state(use_live_feed=True, refit=True)
    assert out["live"] is False and out["source"] == "daily_settle"
