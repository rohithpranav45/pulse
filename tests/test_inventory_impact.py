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


@pytest.mark.skipif(not (_CACHE / "eia_report_history.parquet").exists(),
                    reason="EIA report cache not present")
@pytest.mark.parametrize("series", ["crude_ex_spr", "gasoline", "distillate"])
def test_assess_series_all_three(series):
    r = framework.assess_series(series)
    assert r["series"] == series
    for k in ("call", "p_bullish", "p_bearish", "confidence", "regime",
              "spreads", "surprise_mbbl", "surprise_z", "regime_t", "series_label"):
        assert k in r
    assert r["call"] in ("BULLISH", "BEARISH", "NEUTRAL")
    # crude delegates to the full assess_release (WTI spread attribution); non-crude
    # carry their own series-specific regime beta + product spread set.
    if series == "crude_ex_spr":
        assert "WTI" in r["spreads"]["primary"]
    else:
        assert r["spreads"]["primary"] and r["spreads"]["primary"] != "—"
    if not r["regime_sensitive"]:
        assert r["expected_brent_move_pct"] == 0.0


# ── WTI re-run of the "when it mattered" study ────────────────────────────────
def test_wti_sharpness_compare_hermetic():
    """The Brent-vs-WTI matched-window comparison computes the right per-cut betas
    and a coherent verdict from a synthetic panel — no /Data needed."""
    from backend.research.inventory_impact import regime_conditioning as rc

    rng = np.random.default_rng(1)
    n = 120
    z = rng.normal(0, 1, n)
    # WTI reacts with the textbook sign (build z>0 → price down); Brent perversely flips
    panel = pd.DataFrame({
        "surprise_z": z,
        "ret": 0.40 * z + rng.normal(0, 0.5, n),        # perverse (positive) sign
        "ret_wti": -0.60 * z + rng.normal(0, 0.5, n),   # right sign, stronger
        "d_wti_brent": -0.30 * z + rng.normal(0, 0.3, n),
        "front_contango": rng.random(n) < 0.1,
        "inv_bucket": rng.choice(["LOW", "AVG"], n, p=[0.85, 0.15]),
    }, index=pd.date_range("2021-01-06", periods=n, freq="W-WED"))

    out = rc.wti_sharpness_compare(panel)
    assert out is not None
    assert out["n"] == n and len(out["rows"]) >= 1
    overall = out["rows"][0]
    assert overall["regime"] == "all (matched window)"
    assert overall["wti_right_signed"] is True          # WTI β < 0 by construction
    assert overall["brent_right_signed"] is False        # Brent β > 0 by construction
    assert out["wti_right_signed_count"] >= 1
    assert isinstance(out["verdict"], str) and "WTI" in out["verdict"]
    # the spread reaction column is populated when d_wti_brent is present
    assert overall["wti_brent_spread_beta"] is not None


def test_wti_sharpness_compare_returns_none_without_wti():
    """No WTI history → None (graceful, gates the route field off)."""
    from backend.research.inventory_impact import regime_conditioning as rc
    panel = pd.DataFrame({
        "surprise_z": np.zeros(30), "ret": np.zeros(30),
        "front_contango": [False] * 30, "inv_bucket": ["LOW"] * 30,
    }, index=pd.date_range("2016-01-06", periods=30, freq="W-WED"))
    assert rc.wti_sharpness_compare(panel) is None


# ── real-consensus surprise + API nowcast (item 3) ────────────────────────────
def test_parse_mbbl_and_prev_friday():
    """The consensus loader's primitives: millions→MBBL parse + release→week-ending."""
    assert eia_report._parse_mbbl("-3.900M") == pytest.approx(-3900.0)
    assert eia_report._parse_mbbl("2.064M") == pytest.approx(2064.0)
    assert np.isnan(eia_report._parse_mbbl(""))
    assert np.isnan(eia_report._parse_mbbl("nan"))
    # Wed 2026-06-24 release → week ending Fri 2026-06-19
    assert eia_report._prev_friday(pd.Timestamp("2026-06-24")) == pd.Timestamp("2026-06-19")
    # Tue 2026-06-23 API → same week ending Fri 2026-06-19
    assert eia_report._prev_friday(pd.Timestamp("2026-06-23")) == pd.Timestamp("2026-06-19")
    # a Friday itself maps back a full week (the prior Friday), never to itself
    assert eia_report._prev_friday(pd.Timestamp("2026-06-19")) == pd.Timestamp("2026-06-12")


@pytest.mark.skipif(not (_CACHE / "eia_consensus_history.csv").exists(),
                    reason="consensus history CSV not present")
def test_consensus_loader_aligns_to_parquet_actuals():
    """The CSV's own `actual` (×1000) must match the report parquet's actual_change
    on the prev-Friday-aligned week — the proof the alignment is correct."""
    if not (_CACHE / "eia_report_history.parquet").exists():
        pytest.skip("EIA report cache not present")
    c = eia_report._load_consensus_csv("crude_ex_spr")
    assert not c.empty and c.index.is_unique  # de-duped, no holiday-stray collisions
    actual_chg = eia_report.weekly_frame()["crude_ex_spr"].diff()
    j = c.join(actual_chg.rename("parquet"), how="inner").dropna(subset=["actual", "parquet"])
    match = (j["actual"] - j["parquet"]).abs().lt(200).mean()
    assert match > 0.95  # 99%+ in practice


@pytest.mark.skipif(not (_CACHE / "eia_consensus_history.csv").exists(),
                    reason="consensus history CSV not present")
@pytest.mark.skipif(not (_CACHE / "eia_report_history.parquet").exists(),
                    reason="EIA report cache not present")
@pytest.mark.parametrize("series", ["crude_ex_spr", "gasoline", "distillate"])
def test_consensus_method_surprise_uses_real_consensus(series):
    """method='consensus' yields surprise = actual − real consensus, flags the
    expected_source, and falls back to seasonal where a week has no consensus row."""
    sp = eia_report.surprise_series(series, "consensus")
    assert "expected_source" in sp.columns
    rows = sp.dropna(subset=["surprise"])
    sources = set(rows["expected_source"].unique())
    assert sources <= {"consensus", "seasonal_fallback", "seasonal"}
    assert (rows["expected_source"] == "consensus").mean() > 0.9  # ~97% coverage
    # on a consensus-sourced week the surprise equals actual − the loaded consensus
    cons = eia_report.consensus_series(series)
    we = rows[rows["expected_source"] == "consensus"].index[-1]
    assert sp.loc[we, "surprise"] == pytest.approx(
        sp.loc[we, "actual_change"] - cons.loc[we], abs=1.0)


@pytest.mark.skipif(not (_CACHE / "eia_consensus_history.csv").exists(),
                    reason="consensus history CSV not present")
def test_latest_release_is_the_freshest_print():
    """latest_release returns the real printed actual + consensus + surprise."""
    lr = eia_report.latest_release("crude_ex_spr")
    assert lr is not None
    assert lr["surprise_mbbl"] == pytest.approx(lr["actual_mbbl"] - lr["consensus_mbbl"], abs=1.0)
    assert pd.Timestamp(lr["week_ending"]) < pd.Timestamp(lr["release_date"])  # Fri before Wed


@pytest.mark.skipif(not (_CACHE / "api_crude_history.csv").exists(),
                    reason="API crude CSV not present")
def test_api_nowcast_returns_leading_indicator_or_none():
    """The API nowcast resolves the Tuesday leading indicator for a covered week and
    returns None (graceful) for an uncovered / pre-2019 week."""
    api = eia_report._load_api_crude()
    assert not api.empty
    we = api.index.max()
    nc = eia_report.api_nowcast(we)
    assert nc is not None and nc["api_actual_mbbl"] is not None
    # pre-2019 (no API coverage) → None
    assert eia_report.api_nowcast(pd.Timestamp("2016-01-08")) is None


def test_consensus_method_falls_back_to_seasonal_without_csv(monkeypatch):
    """No consensus CSV → consensus_series empty → method='consensus' degrades to a
    pure seasonal surprise (hermetic: a synthetic weekly_frame, no /Data)."""
    idx = pd.date_range("2020-01-03", periods=160, freq="W-FRI")
    rng = np.random.default_rng(3)
    wf = pd.DataFrame({"crude_ex_spr": 450000 + np.cumsum(rng.normal(0, 1500, len(idx)))}, index=idx)
    monkeypatch.setattr(eia_report, "weekly_frame", lambda *a, **k: wf)
    monkeypatch.setattr(eia_report, "consensus_series", lambda series="crude_ex_spr": pd.Series(dtype=float))
    sp_con = eia_report.surprise_series("crude_ex_spr", "consensus")
    sp_sea = eia_report.surprise_series("crude_ex_spr", "seasonal")
    # with no consensus, the consensus method must equal the seasonal surprise
    pd.testing.assert_series_equal(
        sp_con["surprise"].dropna(), sp_sea["surprise"].dropna(), check_names=False)
    assert (sp_con["expected_source"] == "seasonal_fallback").all()


def test_consensus_sharpening_compare_hermetic(monkeypatch):
    """consensus_sharpening_compare tallies sharper cuts + a verdict from synthetic
    seasonal/consensus panels — no /Data."""
    from backend.research.inventory_impact import regime_conditioning as rc
    rng = np.random.default_rng(5)
    n = 200
    z = rng.normal(0, 1, n)

    def panel(noise):
        return pd.DataFrame({
            "surprise_z": z + rng.normal(0, noise, n),
            "ret": -0.8 * z + rng.normal(0, 0.5, n),
            "d_m1_m2": rng.normal(0, 0.1, n),
            "front_contango": rng.random(n) < 0.3,
            "inv_bucket": rng.choice(["HIGH", "AVG", "LOW"], n),
            "inv_pct": rng.normal(0, 5, n),
            "era": np.where(np.arange(n) < 100, "2015-2020", "2021-2026"),
        }, index=pd.date_range("2016-01-06", periods=n, freq="W-WED"))

    # seasonal panel carries more surprise noise than the consensus panel → consensus sharper
    monkeypatch.setattr(rc.eia_report, "consensus_series",
                        lambda series="crude_ex_spr": pd.Series([1.0], index=[pd.Timestamp("2016-01-08")]))
    monkeypatch.setattr(rc, "build_daily_panel",
                        lambda method="consensus", **k: panel(0.05 if method == "consensus" else 0.6))
    out = rc.consensus_sharpening_compare("crude_ex_spr")
    assert out is not None
    assert out["n_cuts"] >= 1 and 0 <= out["n_sharper"] <= out["n_cuts"]
    assert out["n_sharper"] > out["n_cuts"] / 2          # consensus is the cleaner panel
    assert "SHARPEN" in out["verdict"].upper()
    for r in out["rows"]:
        assert r["sharper"] == (r["d_abs_t"] > 0)


def test_consensus_sharpening_returns_none_without_consensus(monkeypatch):
    from backend.research.inventory_impact import regime_conditioning as rc
    monkeypatch.setattr(rc.eia_report, "consensus_series",
                        lambda series="crude_ex_spr": pd.Series(dtype=float))
    assert rc.consensus_sharpening_compare("crude_ex_spr") is None


def test_release_reaction_computes_horizon_moves(tmp_path, monkeypatch):
    """Hermetic: a synthetic 1-min CO/CL feed with a known post-release ramp →
    compute_reaction returns the right %/$ moves at each horizon."""
    import sqlite3
    from datetime import datetime
    from backend.research.inventory_impact import release_reaction as rr

    db = tmp_path / "bars_1min_20260624.db"
    conn = sqlite3.connect(db)
    # release at 14:30; build 90 min of bars from 14:00. Brent flat from 100,
    # WTI flat from 80, WTI c2 = WTI - 0.5. After release WTI drifts -0.1/min.
    def make(table, base, drift):
        conn.execute(f'CREATE TABLE "{table}" (timestamp TEXT, open REAL, high REAL, low REAL, close REAL, volume REAL)')
        rows = []
        for m in range(91):
            ts = datetime(2026, 6, 24, 14, 0) + pd.Timedelta(minutes=m)
            px = base + (drift * max(0, m - 30))   # flat until release (+30min from 14:00 = 14:30)
            rows.append((str(ts), px, px, px, px, 10.0))
        conn.executemany(f'INSERT INTO "{table}" VALUES (?,?,?,?,?,?)', rows)
    make("CO_Q26", 100.0, -0.05)   # Brent
    make("CL_Q26", 80.0, -0.10)    # WTI front
    make("CL_U26", 79.5, -0.10)    # WTI 2nd (parallel → M1-M2 unchanged)
    conn.commit(); conn.close()

    monkeypatch.setenv("PULSE_INVENTORY_1MIN_DIR", str(tmp_path))
    out = rr.compute_reaction(release_utc=datetime(2026, 6, 24, 14, 30))
    assert out["available"] is True
    a = {h["mins"]: h for h in out["actual"]}
    # +30min: WTI down 30*0.10 = $3 from 80 → -3.75%; spread M1-M2 unchanged (parallel)
    assert a[30]["wti_flat_pct"] == pytest.approx(-3.75, abs=0.05)
    assert a[30]["d_wti_m1_m2"] == pytest.approx(0.0, abs=0.01)
    # WTI fell more than Brent → WTI-Brent spread narrowed (negative change)
    assert a[30]["d_wti_brent"] < 0
