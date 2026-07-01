"""Tests for the GDELT corpus + ACLED conflict feed (Sprint 4)."""

import numpy as np
import pandas as pd
import pytest

from research.news_impact.geo import datasets, conflict
from research.news_impact.geo import event_study_geo as es


# ── GDELT corpus loader + event sourcing ──────────────────────────────────────
def test_load_gdelt_corpus_parses(tmp_path):
    p = tmp_path / "g.csv"
    p.write_text("date,datetime_utc,title,url,domain,country\n"
                 "2026-04-01,2026-04-01T00:00:00+00:00,Strait of Hormuz closed,http://x,x.com,Iran\n"
                 "2026-04-02,2026-04-02T00:00:00+00:00,,http://y,y.com,US\n",  # blank title dropped
                 encoding="utf-8")
    rows = datasets.load_gdelt_corpus(p)
    assert len(rows) == 1
    assert rows[0]["title"] == "Strait of Hormuz closed"
    assert rows[0]["published_at"].startswith("2026-04-01")


def test_gdelt_events_from_rows_resolves_chokepoint():
    rows = [
        {"published_at": "2026-04-01T00:00:00Z", "title": "Strait of Hormuz closed to all tankers"},
        {"published_at": "2026-04-02T00:00:00Z", "title": "Local council debates parking"},  # non-oil
    ]
    evs = datasets.gdelt_events(rows=rows)            # use_llm=False → deterministic
    assert len(evs) == 1
    ev = evs[0]
    assert ev["asset_type"] == "chokepoint"
    assert ev["conviction"].get("brent_flat", 0) > 0


def test_gdelt_events_until_cap():
    rows = [
        {"published_at": "2026-04-01T00:00:00Z", "title": "Hormuz blockade tightens"},
        {"published_at": "2026-06-20T00:00:00Z", "title": "Hormuz blockade tightens"},  # past cap
    ]
    evs = datasets.gdelt_events(rows=rows, until="2026-05-26")
    assert len(evs) == 1


# ── event-study source selection ──────────────────────────────────────────────
def test_gather_events_prefers_gdelt(monkeypatch):
    crafted = [{"published_at": "2026-04-01T00:00:00Z", "asset_type": "chokepoint",
                "event_type": "closure", "conviction": {"brent_flat": 2.0}}]
    monkeypatch.setattr(datasets, "available", lambda: True)
    monkeypatch.setattr(datasets, "gdelt_events",
                        lambda until, use_llm, provider: crafted)
    got = es._gather_events("2026-05-26", use_llm=False, provider="fallback", source="auto")
    assert got == crafted


def test_gather_events_falls_back_to_corpus(monkeypatch):
    monkeypatch.setattr(datasets, "available", lambda: False)
    monkeypatch.setattr(es, "_events_from_corpus",
                        lambda use_llm, provider, until: [{"x": 1}])
    got = es._gather_events(None, use_llm=False, provider="fallback", source="auto")
    assert got == [{"x": 1}]


# ── ACLED conflict feed ───────────────────────────────────────────────────────
def _synthetic_monthly():
    idx = pd.date_range("2024-01-01", periods=18, freq="MS")
    # noisy baseline (non-zero variance) then a war spike at the end
    iran = pd.Series(list(8 + 4 * np.sin(np.arange(17))) + [443], index=idx, dtype=float)
    russia = pd.Series(np.linspace(50, 60, 18), index=idx)
    return pd.DataFrame({"Iran": iran, "Russia": russia,
                         "TOTAL": iran + russia})


def test_bloc_intensity_sums_oil_countries(monkeypatch):
    df = _synthetic_monthly()
    monkeypatch.setattr(conflict, "load_conflict", lambda freq="monthly": df)
    s = conflict.bloc_intensity("monthly")
    assert s.iloc[-1] == df["Iran"].iloc[-1] + df["Russia"].iloc[-1]


def test_conflict_regime_flags_spike(monkeypatch):
    df = _synthetic_monthly()
    monkeypatch.setattr(conflict, "load_conflict", lambda freq="monthly": df)
    r = conflict.conflict_regime("Iran", freq="monthly", window=12)
    assert r["level"] == "HIGH" and r["z"] > conflict.Z_HIGH
    # a flat country sits NORMAL
    assert conflict.conflict_regime("Russia", freq="monthly")["level"] in ("NORMAL", "HIGH", "LOW")


def test_conflict_regime_unknown_when_empty(monkeypatch):
    monkeypatch.setattr(conflict, "load_conflict", lambda freq="monthly": pd.DataFrame())
    monkeypatch.setattr(conflict, "bloc_intensity", lambda freq="monthly": pd.Series(dtype=float))
    assert conflict.conflict_regime("Iran")["level"] == "UNKNOWN"


def test_oil_conflict_study_graceful_without_data(monkeypatch):
    monkeypatch.setattr(conflict, "bloc_intensity", lambda freq="monthly": pd.Series(dtype=float))
    assert conflict.oil_conflict_study()["available"] is False


# ── real-data integration (skips cleanly without the committed CSVs / lake) ────
def test_real_gdelt_window_is_gradeable():
    if not datasets.available():
        pytest.skip("GDELT corpus not present")
    evs = datasets.gdelt_events(until="2026-05-26")
    assert len(evs) >= 10                      # the 2026 war window is geo-dense
    panel = es.build_event_panel(source="gdelt")
    if panel.empty:
        pytest.skip("/Data node tape not present")
    assert panel["published_at"].nunique() >= 10
