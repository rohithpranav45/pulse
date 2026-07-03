"""
Settle-tail sprint (2026-07-02) — opt-in OHLCV tail extension of the daily
settle tape (research.settle_tail + the data_lake wiring).

Hermetic: synthetic lake + synthetic feed frames, no /Data, no I:\\ share.
Proves:
  • extend-only semantics — tail rows strictly after the lake's last settle;
    overlap dates keep the LAKE value, never the feed's
  • column alignment — tail reindexed to the lake's columns (c13..c31 NaN,
    extra feed columns dropped)
  • no-lake / no-feed / no-new-rows are all safe no-ops
  • overlap agreement stats (mean/max |lake − feed| per contract + m1_m2)
  • data_lake wiring: flag OFF → bit-for-bit the lake frame; flag ON →
    extended + ESTIMATE provenance recorded in settle_tail_meta()
"""
import os
import sys

import numpy as np
import pandas as pd
import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from research import settle_tail as st  # noqa: E402


def _lake(end="2026-05-26", days=30, cols=("c1", "c2", "c6", "c12", "c31")):
    idx = pd.bdate_range(end=end, periods=days)
    base = {"c1": 65.0, "c2": 64.6, "c6": 63.8, "c12": 62.9, "c31": 61.0}
    data = {c: base[c] + np.linspace(0, 1.0, days) for c in cols}
    return pd.DataFrame(data, index=idx)


def _feed(start="2026-04-30", end="2026-06-26", offset=0.0, cols=("c1", "c2", "c6", "c12")):
    idx = pd.bdate_range(start=start, end=end)
    base = {"c1": 65.0, "c2": 64.6, "c6": 63.8, "c12": 62.9}
    data = {c: base[c] + offset + np.linspace(0, 1.0, len(idx)) for c in cols}
    return pd.DataFrame(data, index=idx)


# ── extend_with_feed (pure) ──────────────────────────────────────────────────

def test_extend_only_appends_strictly_after_lake_max():
    lake, feed = _lake(), _feed(offset=0.05)
    out, meta = st.extend_with_feed(lake, feed)
    lake_end = lake.index.max()
    assert out.index.max() == feed.index.max()
    assert meta is not None and meta["n_tail_rows"] == int((feed.index > lake_end).sum())
    assert meta["lake_end"] == "2026-05-26"
    # every pre-existing lake row is untouched (overlap keeps the LAKE value)
    pd.testing.assert_frame_equal(out.loc[:lake_end], lake)


def test_tail_columns_reindexed_to_lake_columns():
    lake = _lake()  # carries c31, feed doesn't
    feed = _feed()
    feed["c99"] = 1.0  # extra feed column must be dropped
    out, meta = st.extend_with_feed(lake, feed)
    assert list(out.columns) == list(lake.columns)
    tail = out[out.index > lake.index.max()]
    assert tail["c31"].isna().all()      # lake-only contract → NaN on tail rows
    assert "c99" not in out.columns


def test_no_lake_no_feed_no_new_rows_are_noops():
    lake = _lake()
    # no lake → nothing to extend (models were trained on the lake)
    out, meta = st.extend_with_feed(None, _feed())
    assert out is None and meta is None
    # no feed → lake unchanged
    out, meta = st.extend_with_feed(lake, None)
    assert out is lake and meta is None
    # feed ends before the lake → lake unchanged
    old_feed = _feed(start="2026-03-02", end="2026-05-20")
    out, meta = st.extend_with_feed(lake, old_feed)
    assert out is lake and meta is None


def test_estimate_provenance_string():
    out, meta = st.extend_with_feed(_lake(), _feed())
    assert meta["source"] == st.TAIL_SOURCE == "ohlcv_tail (ESTIMATE)"
    assert meta["tail_start"] > meta["lake_end"]


def test_weekend_feed_rows_excluded_from_tail():
    lake = _lake()
    # calendar-daily feed (includes Sat/Sun rows, like the UTC-date grouping)
    idx = pd.date_range(start="2026-05-20", end="2026-06-26", freq="D")
    feed = pd.DataFrame({"c1": 65.0, "c2": 64.6, "c6": 63.8, "c12": 62.9}, index=idx)
    out, meta = st.extend_with_feed(lake, feed)
    tail = out[out.index > lake.index.max()]
    assert (tail.index.dayofweek < 5).all()
    assert meta["n_tail_rows"] == int(len(tail))


# ── overlap_stats (pure) ─────────────────────────────────────────────────────

def test_overlap_stats_measures_known_offset():
    lake = _lake(days=20)
    # feed = lake + 0.10 on c1, exact on c12 → known per-contract errors
    feed = lake[["c1", "c2", "c6", "c12"]].copy()
    feed["c1"] = feed["c1"] + 0.10
    ov = st.overlap_stats(lake, feed)
    assert ov is not None and ov["n_days"] == 20
    assert ov["series"]["c1"]["mean_abs_diff"] == pytest.approx(0.10, abs=1e-6)
    assert ov["series"]["c1"]["max_abs_diff"] == pytest.approx(0.10, abs=1e-6)
    assert ov["series"]["c12"]["mean_abs_diff"] == pytest.approx(0.0, abs=1e-6)
    # m1_m2 spread inherits the c1 offset exactly
    assert ov["series"]["m1_m2"]["mean_abs_diff"] == pytest.approx(0.10, abs=1e-6)


def test_overlap_stats_none_without_overlap():
    lake = _lake(end="2026-05-26")
    feed = _feed(start="2026-06-01", end="2026-06-26")
    assert st.overlap_stats(lake, feed) is None
    assert st.overlap_stats(None, feed) is None
    assert st.overlap_stats(lake, None) is None


# ── data_lake wiring (flag off = bit-for-bit; flag on = extended + meta) ─────

@pytest.fixture
def _dl(monkeypatch):
    import data_lake as dl
    lake = _lake()
    monkeypatch.setattr(dl, "_load_settlements_c1_to_c31", lambda: lake.copy())
    monkeypatch.setattr(st, "_feed_daily", lambda key: _feed(offset=0.05))
    # isolate cache + meta so other tests / a warm process never leak in
    monkeypatch.setattr(dl, "_cache", {})
    monkeypatch.setattr(dl, "_TAIL_META", {})
    return dl, lake


def test_flag_off_is_bit_for_bit_lake(_dl, monkeypatch):
    dl, lake = _dl
    monkeypatch.delenv("PULSE_SETTLE_TAIL", raising=False)
    out = dl.get_brent_settlements()
    pd.testing.assert_frame_equal(out, lake)
    assert dl.settle_tail_meta() == {}


def test_flag_on_extends_and_records_meta(_dl, monkeypatch):
    dl, lake = _dl
    monkeypatch.setenv("PULSE_SETTLE_TAIL", "1")
    out = dl.get_brent_settlements()
    assert out.index.max() > lake.index.max()
    pd.testing.assert_frame_equal(out.loc[:lake.index.max()], lake)
    meta = dl.settle_tail_meta()
    assert meta["brent"]["source"] == "ohlcv_tail (ESTIMATE)"
    assert meta["brent"]["lake_end"] == "2026-05-26"
    assert meta["brent"]["n_tail_rows"] > 0


def test_flag_toggle_serves_each_variant_from_its_own_cache(_dl, monkeypatch):
    dl, lake = _dl
    monkeypatch.setenv("PULSE_SETTLE_TAIL", "1")
    extended = dl.get_brent_settlements()
    monkeypatch.delenv("PULSE_SETTLE_TAIL", raising=False)
    plain = dl.get_brent_settlements()
    pd.testing.assert_frame_equal(plain, lake)
    assert extended.index.max() > plain.index.max()
