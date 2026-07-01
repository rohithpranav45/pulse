"""Tests for the OHLCV products feed loader + rbob_crack node (Sprint 6).

Hermetic — a synthetic OHLCV CSV tree under tmp_path (PULSE_OHLCV_DIR), exercising
the hourly parse, the last-bar-per-UTC-date daily settle, the index-alignment fix,
the lake+feed tail-merge, and the rbob_crack conversion. No office share, no /Data.
"""

import numpy as np
import pandas as pd
import pytest

from research.news_impact.geo import products_feed as pf
from research.news_impact.geo import nodes


_HEADER = ("#RIC,Alias Underlying RIC,Domain,Date-Time,GMT Offset,Type,"
           "Open,High,Low,Last,Volume\n")


def _write_contract(root, product, n, rows):
    """rows = list of (iso_dt, last). Writes {product}/{prefix}c{n}.csv."""
    d = root / product
    d.mkdir(parents=True, exist_ok=True)
    prefix = pf.PRODUCTS[product]
    lines = [_HEADER]
    for dt, last in rows:
        lines.append(f"{prefix}c{n},{prefix}X6,Market Price,{dt},-5,Intraday 1Hour,"
                     f"{last},{last},{last},{last},100\n")
    (d / f"{prefix}c{n}.csv").write_text("".join(lines), encoding="utf-8")


@pytest.fixture
def feed_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("PULSE_OHLCV_DIR", str(tmp_path))
    return tmp_path


def test_load_continuous_parses_and_aligns(feed_dir):
    # two hourly bars on day 1, one on day 2 — the alignment bug would NaN these
    _write_contract(feed_dir, "RBOB", 1, [
        ("2026-06-01T20:00:00.000000000Z", 2.10),
        ("2026-06-01T21:00:00.000000000Z", 2.15),
        ("2026-06-02T20:00:00.000000000Z", 2.20),
    ])
    h = pf.load_continuous("RBOB", 1)
    assert h is not None and len(h) == 3
    assert h["last"].notna().all()           # the index-alignment regression guard
    assert h["last"].iloc[0] == pytest.approx(2.10)


def test_daily_curve_takes_last_bar_per_date(feed_dir):
    _write_contract(feed_dir, "RBOB", 1, [
        ("2026-06-01T20:00:00.000000000Z", 2.10),
        ("2026-06-01T21:00:00.000000000Z", 2.15),   # later bar same day → wins
        ("2026-06-02T20:00:00.000000000Z", 2.20),
    ])
    dc = pf.daily_curve("RBOB", 1)
    assert list(dc.columns) == ["c1"]
    assert len(dc) == 2
    assert dc["c1"].iloc[0] == pytest.approx(2.15)   # last bar of 06-01
    assert dc["c1"].iloc[1] == pytest.approx(2.20)


def test_absent_product_returns_none(feed_dir):
    assert pf.load_continuous("HO", 1) is None
    assert pf.daily_curve("HO", 3) is None


def test_unknown_product_raises(feed_dir):
    with pytest.raises(ValueError):
        pf.load_continuous("BRENT", 1)


def test_combine_tail_extends_only_after_lake_max():
    idx_lake = pd.to_datetime(["2026-05-24", "2026-05-25", "2026-05-26"])
    lake = pd.DataFrame({"c1": [70.0, 71.0, 72.0]}, index=idx_lake)
    idx_feed = pd.to_datetime(["2026-05-25", "2026-05-26", "2026-06-01", "2026-06-02"])
    feed = pd.DataFrame({"c1": [99.0, 99.0, 73.0, 74.0]}, index=idx_feed)   # 99s would corrupt overlap
    out = nodes._combine_tail(lake, feed)
    assert out.index.max() == pd.Timestamp("2026-06-02")
    # overlapping lake dates are PRESERVED (feed only appends strictly-after rows)
    assert out.loc[pd.Timestamp("2026-05-25"), "c1"] == 71.0
    assert out.loc[pd.Timestamp("2026-06-01"), "c1"] == 73.0


def test_combine_tail_handles_missing_sides():
    df = pd.DataFrame({"c1": [1.0]}, index=pd.to_datetime(["2026-01-01"]))
    assert nodes._combine_tail(None, df) is df
    assert nodes._combine_tail(df, None) is df


def test_compute_nodes_rbob_crack():
    idx = ["2026-06-01"]
    brent = pd.DataFrame({"c1": [72.0]}, index=pd.to_datetime(idx))
    wti = pd.DataFrame({"c1": [69.0]}, index=pd.to_datetime(idx))
    rbob = pd.DataFrame({"c1": [2.10]}, index=pd.to_datetime(idx))    # $/gal
    p = nodes.compute_nodes(brent, wti, None, None, rbob=rbob)
    assert p["rbob_crack"].iloc[0] == pytest.approx(2.10 * 42.0 - 69.0, abs=1e-6)


def test_compute_nodes_rbob_needs_wti():
    idx = ["2026-06-01"]
    brent = pd.DataFrame({"c1": [72.0]}, index=pd.to_datetime(idx))
    rbob = pd.DataFrame({"c1": [2.10]}, index=pd.to_datetime(idx))
    p = nodes.compute_nodes(brent, None, None, None, rbob=rbob)
    assert "rbob_crack" not in p.columns          # no WTI leg → omitted, no crash


def test_registry_grades_rbob_crack():
    """rbob_crack is now in the node vocabulary and US/global refineries + Colonial
    + generics carry a (positive) gasoline-crack bias, so impact_map emits it."""
    from research.news_impact.geo import registry as reg
    from research.news_impact.geo import impact_map as im
    assert "rbob_crack" in reg.NODES
    # a US refinery fire → gasoline crack UP
    pa = reg.by_id("port_arthur")
    assert pa.disruption_bias.get("rbob_crack", 0) > 0
    vec = im.impact_vector(pa, "fire", "major")
    assert vec.get("rbob_crack", 0) > 0
    # a restart flips it negative
    assert im.impact_vector(pa, "restart", "major").get("rbob_crack", 0) < 0


def test_real_feed_smoke_if_present():
    if not pf.available():
        pytest.skip("OHLCV products feed not visible")
    rb = pf.daily_curve("RBOB", 1)
    assert rb is not None and rb["c1"].dropna().gt(0).all()
