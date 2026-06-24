"""
Tests for the News Impact Model — event study + impact layer (Sprint 2).

Fully hermetic: no network, no /Data. Price frames are synthetic and injected;
the corpus points at a throwaway PULSE_NEWS_DB; betas/regime are passed in so the
impact layer never touches the live tape. Graded-verdict / honesty conventions:
we assert the prior-then-learn gate flips correctly (measured only when earned).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backend.research.news_impact import event_study as es
from backend.research.news_impact import impact as im
from backend.research.news_impact import corpus


# ── synthetic price frames (no /Data) ─────────────────────────────────────────
def _synthetic_frames() -> dict:
    # daily settlements: a clean +1/day ramp so the +1d return is predictable
    days = pd.date_range("2026-03-02", periods=8, freq="D")           # Mon..Mon
    c1 = pd.Series(np.arange(100.0, 108.0), index=days)
    curve = pd.DataFrame({"c1": c1, "c2": c1 - 1.0, "c3": c1 - 2.0}, index=days)  # BACK (c1>c3)
    rvol = pd.Series(1.0, index=days)
    # intraday 5-min bars across one of those days, a smooth +0.1/bar ramp
    grid = pd.date_range("2026-03-03 08:00", "2026-03-03 16:00", freq="5min", tz="UTC")
    px = pd.Series(100.0 + 0.1 * np.arange(len(grid)), index=grid)
    return {
        "brent_intraday": px,
        "wti_intraday": px * 1.01,
        "brent_daily": c1,
        "wti_daily": c1 * 1.05,
        "brent_curve": curve,
        "rvol": rvol,
    }


# ── sentiment lexicon ─────────────────────────────────────────────────────────
def test_signed_sentiment_directions():
    assert es.signed_sentiment("Oil surges as drone attack halts Saudi output") > 0.3
    assert es.signed_sentiment("Crude tumbles on demand fears and record build") < -0.3
    # no polarity term → neutral
    assert es.signed_sentiment("OPEC ministers to meet Thursday in Vienna") == 0.0
    assert es.signed_sentiment("") == 0.0


def test_signed_sentiment_bounded():
    v = es.signed_sentiment("attack strike sanction outage shortage deficit surge")
    assert -1.0 <= v <= 1.0


# ── forward-return primitives ─────────────────────────────────────────────────
def test_asof_respects_staleness():
    grid = pd.date_range("2026-03-03 08:00", periods=10, freq="5min", tz="UTC")
    s = pd.Series(np.arange(10.0), index=grid)
    # in-window match
    assert es._asof(s, pd.Timestamp("2026-03-03 08:12", tz="UTC")) == 2.0
    # far past the last bar → None (overnight gap)
    assert es._asof(s, pd.Timestamp("2026-03-03 20:00", tz="UTC")) is None


def test_fwd_intraday_known_return():
    grid = pd.date_range("2026-03-03 08:00", "2026-03-03 12:00", freq="5min", tz="UTC")
    s = pd.Series(100.0 + 0.1 * np.arange(len(grid)), index=grid)
    t = pd.Timestamp("2026-03-03 09:00", tz="UTC")
    r = es._fwd_intraday(s, t, "1h")  # +12 bars → +1.2 on a base ~101.2
    assert r is not None and r > 0


def test_fwd_daily_close_to_close():
    days = pd.date_range("2026-03-02", periods=5, freq="D")
    c1 = pd.Series([100.0, 102.0, 101.0, 103.0, 104.0], index=days)
    # headline on 2026-03-03 → anchor=03-02 (100), post=03-03 (102) → +2%
    t = pd.Timestamp("2026-03-03 12:00", tz="UTC")
    r = es._fwd_daily(c1, t)
    assert r == pytest.approx(2.0, abs=1e-6)


def test_curve_regime_back_vs_contango():
    frames = _synthetic_frames()
    t = pd.Timestamp("2026-03-04 10:00", tz="UTC")
    assert es._curve_regime(frames["brent_curve"], t) == "BACK"
    # flip to contango
    contango = frames["brent_curve"].copy()
    contango["c3"] = contango["c1"] + 2.0
    assert es._curve_regime(contango, t) == "CONTANGO"


# ── event panel from injected headlines + frames ──────────────────────────────
def test_build_event_panel_columns_and_returns():
    frames = _synthetic_frames()
    heads = [
        {"title": "Drone attack halts crude output", "factor": "GEOPOLITICAL",
         "factor_conf": 0.9, "published_at": "2026-03-03T09:00:00+00:00"},
        {"title": "Record build pressures crude lower", "factor": "INVENTORY",
         "factor_conf": 0.8, "published_at": "2026-03-04T10:00:00+00:00"},
    ]
    panel = es.build_event_panel(headlines=heads, frames=frames)
    assert not panel.empty
    for col in ("factor", "sentiment", "curve", "fwd_brent_1d", "fwd_wti_1d",
                "fwd_brent_1h", "vn_brent_1d"):
        assert col in panel.columns
    # daily ramp 100..107 on 03-02..03-09. Headline on 03-04 → anchor=03-03 (101),
    # post=03-04 (102) → +0.99% (prior close → headline-day close).
    row = panel[panel["factor"] == "INVENTORY"].iloc[0]
    assert row["fwd_brent_1d"] == pytest.approx((102.0 / 101.0 - 1) * 100, abs=1e-6)
    assert row["sentiment"] < 0  # "build ... lower" is bearish


def test_build_event_panel_drops_headlines_without_price_coverage():
    frames = _synthetic_frames()
    heads = [{"title": "Old news", "factor": "NOISE",
              "published_at": "2019-01-01T00:00:00+00:00"}]   # before the tape
    panel = es.build_event_panel(headlines=heads, frames=frames)
    assert panel.empty


# ── regression / factor betas ─────────────────────────────────────────────────
def test_ols_recovers_slope_and_min_n():
    rng = np.random.default_rng(1)
    x = rng.uniform(-1, 1, 60)
    y = 0.7 * x + rng.normal(0, 0.1, 60)
    r = es._ols(x, y, min_n=8)
    assert r["slope"] == pytest.approx(0.7, abs=0.06) and r["n"] == 60
    # too few points → None
    assert es._ols(np.array([1.0, 2.0]), np.array([1.0, 2.0]), min_n=8) is None


def test_factor_table_flags_significant_and_prior():
    rng = np.random.default_rng(2)
    n = 40
    sent = rng.uniform(-1, 1, 2 * n)
    fwd = np.concatenate([0.8 * sent[:n] + rng.normal(0, 0.15, n),      # GEO: strong
                          rng.normal(0, 0.3, n)])                        # NOISE: none
    panel = pd.DataFrame({
        "factor": ["GEOPOLITICAL"] * n + ["NOISE"] * n,
        "sentiment": sent,
        "curve": ["BACK"] * n + ["CONTANGO"] * n,
        "fwd_brent_1d": fwd, "fwd_wti_1d": fwd * 1.1,
    })
    tbl = {r["factor"]: r for r in es.factor_table(panel, "1d")}
    assert tbl["GEOPOLITICAL"]["significant"] is True
    assert tbl["GEOPOLITICAL"]["beta_brent_pct"] == pytest.approx(0.8, abs=0.15)
    assert tbl["NOISE"]["significant"] is False


# ── impact layer: prior-then-learn gate ───────────────────────────────────────
def _betas_with(geo_sig: bool) -> dict:
    geo = {"factor": "GEOPOLITICAL", "n": 30, "beta_brent_pct": 0.80,
           "t_brent": 5.0 if geo_sig else 0.4, "r2_brent": 0.4,
           "beta_wti_pct": 0.88, "aligned_mean_move": 0.5, "aligned_hit_rate": 0.7,
           "significant": geo_sig, "by_curve": {"BACK": {"slope": 0.9}, "CONTANGO": {}}}
    tbl = [geo]
    return {"available": True, "headline_horizon": "1d", "n_headlines": 60,
            "tables": {"1d": tbl}, "factors": tbl}


def test_score_headline_measured_when_significant():
    s = im.score_headline("Drone attack halts Saudi crude output",
                          factor="GEOPOLITICAL", betas=_betas_with(True),
                          regime={"curve": "BACK", "as_of": "2026-06-23"})
    assert s["basis"] == "measured"
    assert s["direction"] == "LONG" and s["expected_pct_move"] > 0
    assert s["t_stat"] == 5.0
    assert s["regime_context"]["regime_beta_pct"] == 0.9


def test_score_headline_falls_back_to_prior_when_insignificant():
    s = im.score_headline("Drone attack halts Saudi crude output",
                          factor="GEOPOLITICAL", betas=_betas_with(False),
                          regime={"curve": "BACK"})
    assert s["basis"] == "prior"
    # prior magnitude for GEOPOLITICAL is positive; bullish sentiment → LONG
    assert s["beta_pct"] == pytest.approx(im.FACTOR_PRIORS["GEOPOLITICAL"][0])
    assert s["direction"] == "LONG"


def test_score_headline_noise_is_neutral():
    s = im.score_headline("Local bakery wins community award", factor="NOISE",
                          betas=_betas_with(True), regime={"curve": "BACK"})
    assert s["direction"] == "NEUTRAL" and s["expected_pct_move"] == 0.0


def test_factor_table_view_covers_taxonomy_and_marks_basis():
    rows = im.factor_table_view(betas=_betas_with(True))
    by = {r["factor"]: r for r in rows}
    # every taxonomy factor present
    assert set(by) == set(im.FACTORS)
    assert by["GEOPOLITICAL"]["basis"] == "measured"
    # an unmeasured factor falls to its labelled prior magnitude
    assert by["WEATHER"]["basis"] == "prior"
    assert by["WEATHER"]["beta_pct"] == pytest.approx(im.FACTOR_PRIORS["WEATHER"][0])


# ── impact_feed over a temp corpus (hermetic) ─────────────────────────────────
@pytest.fixture()
def temp_corpus(tmp_path, monkeypatch):
    db = tmp_path / "news_test.db"
    monkeypatch.setenv("PULSE_NEWS_DB", str(db))
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    corpus._reset_conn_for_test()
    corpus.ensure_schema()
    yield corpus
    corpus._reset_conn_for_test()


def test_impact_feed_ranks_by_expected_move(temp_corpus):
    temp_corpus.upsert_articles([
        {"url": "u1", "title": "Drone attack halts Saudi crude output",
         "published_at": "2026-06-20T09:00:00+00:00"},
        {"url": "u2", "title": "Mild weather eases heating demand",
         "published_at": "2026-06-20T10:00:00+00:00"},
        {"url": "u3", "title": "Quarterly logistics seminar concludes",
         "published_at": "2026-06-20T11:00:00+00:00"},
    ])
    temp_corpus.set_classification("u1", "GEOPOLITICAL", 0.9)
    temp_corpus.set_classification("u2", "WEATHER", 0.6)
    temp_corpus.set_classification("u3", "NOISE", 0.3)
    feed = im.impact_feed(limit=10, betas=_betas_with(True),
                          regime={"curve": "BACK", "as_of": "2026-06-23"})
    # NOISE is excluded from the impact feed (it's the "what's worth something" view)
    assert len(feed) == 2
    assert all(s["factor"] != "NOISE" for s in feed)
    # the geopolitical attack must rank first (largest |expected move|)
    assert feed[0]["factor"] == "GEOPOLITICAL"
    assert abs(feed[0]["expected_pct_move"]) >= abs(feed[1]["expected_pct_move"])


def test_impact_feed_recent_order_leads_with_newest(temp_corpus):
    temp_corpus.upsert_articles([
        {"url": "old", "title": "OPEC weighs deeper output cut",
         "published_at": "2021-03-01T09:00:00+00:00"},
        {"url": "new", "title": "Drone attack halts Saudi crude output",
         "published_at": "2026-06-20T09:00:00+00:00"},
    ])
    temp_corpus.set_classification("old", "SUPPLY_OPEC", 0.8)
    temp_corpus.set_classification("new", "GEOPOLITICAL", 0.9)
    feed = im.impact_feed(limit=10, betas=_betas_with(True),
                          regime={"curve": "BACK", "as_of": "2026-06-23"}, order="recent")
    assert feed[0]["published_at"].startswith("2026")   # newest leads, not highest-impact


def test_live_scored_normalizes_ts_and_scores(temp_corpus):
    # one headline already classified in the corpus (factor reused by url),
    # one fresh headline (keyword-classified), GDELT-compact timestamp normalised.
    temp_corpus.upsert_articles([
        {"url": "k", "title": "Drone attack halts Saudi crude output",
         "published_at": "2026-06-20T09:00:00Z"},
    ])
    temp_corpus.set_classification("k", "GEOPOLITICAL", 0.9)
    arts = [
        {"url": "k", "title": "Drone attack halts Saudi crude output",
         "published_at": "20260620T090000Z", "source": "reuters.com"},   # GDELT compact
        {"url": "x", "title": "Refinery outage widens gasoline crack spread",
         "published_at": "2026-06-21T10:00:00Z", "source": "platts.com"},
    ]
    out = im.live_scored(arts, betas=_betas_with(True),
                         regime={"curve": "BACK", "as_of": "2026-06-23"})
    assert len(out) == 2
    # GDELT compact YYYYMMDDTHHMMSSZ → ISO (so the browser can render it)
    assert out[0]["published_at"].startswith("2026-06-20T09:00")
    # factor: corpus (Groq) label for the known URL, keyword for the fresh one
    assert out[0]["factor"] == "GEOPOLITICAL" and out[0]["factor_source"] == "corpus"
    assert out[1]["factor"] == "REFINING_PRODUCTS" and out[1]["factor_source"] == "keyword"
    assert "expected_pct_move" in out[0] and out[0]["url"] == "k"


def test_current_regime_graceful_without_tape():
    # empty frames → no crash, curve None
    empty = {"brent_curve": pd.DataFrame(), "rvol": pd.Series(dtype=float)}
    assert im.current_regime(frames=empty)["curve"] is None
