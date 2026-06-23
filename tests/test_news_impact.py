"""
Tests for the News Headline Impact Model — corpus + classifier (Sprint 1).

Fully hermetic: every test points PULSE_NEWS_DB at a throwaway sqlite file (never
the live corpus), and the GDELT backfill + Groq classifier are injected/forced
into their fallbacks so no network is touched. GROQ_API_KEY is cleared so the
classifier exercises its deterministic keyword path.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.research.news_impact import corpus, classify


@pytest.fixture()
def temp_corpus(tmp_path, monkeypatch):
    """Fresh on-disk corpus per test; no Groq key so classify uses keywords."""
    db = tmp_path / "news_test.db"
    monkeypatch.setenv("PULSE_NEWS_DB", str(db))
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    corpus._reset_conn_for_test()
    corpus.ensure_schema()
    yield corpus
    corpus._reset_conn_for_test()


def _art(url, title, ts="20260525T103000Z", source="reuters.com"):
    return {"url": url, "title": title, "published_at": ts, "source": source}


# ── timestamp normalisation ───────────────────────────────────────────────────

def test_norm_ts_gdelt_seendate():
    assert corpus._norm_ts("20260525T103000Z") == "2026-05-25T10:30:00+00:00"

def test_norm_ts_iso():
    assert corpus._norm_ts("2026-05-25T10:30:00Z") == "2026-05-25T10:30:00+00:00"

def test_norm_ts_relative_rejected():
    # "3h ago" has no absolute time → None (excluded from the event study)
    assert corpus._norm_ts("3h ago") is None
    assert corpus._norm_ts("") is None


# ── corpus writes / dedup ─────────────────────────────────────────────────────

def test_upsert_inserts_new_rows(temp_corpus):
    n = temp_corpus.upsert_articles([_art("u1", "OPEC cuts output"), _art("u2", "Iran tension")])
    assert n == 2
    assert temp_corpus.stats()["total"] == 2

def test_upsert_dedupes_on_url(temp_corpus):
    temp_corpus.upsert_articles([_art("u1", "OPEC cuts output")])
    # same URL again → 0 new rows, original kept
    n = temp_corpus.upsert_articles([_art("u1", "OPEC cuts output (edited)")])
    assert n == 0
    assert temp_corpus.stats()["total"] == 1

def test_upsert_skips_missing_url_or_title(temp_corpus):
    n = temp_corpus.upsert_articles([
        {"url": "", "title": "no url"},
        {"url": "u9", "title": ""},
        _art("u10", "valid one"),
    ])
    assert n == 1

def test_classification_survives_relabel_reupsert(temp_corpus):
    """A live re-fetch of an already-classified URL must not wipe its factor."""
    temp_corpus.upsert_articles([_art("u1", "OPEC cuts output")])
    temp_corpus.set_classification("u1", "SUPPLY_OPEC", 0.9)
    temp_corpus.upsert_articles([_art("u1", "OPEC cuts output")])  # re-seen
    row = temp_corpus.recent(10)[0]
    assert row["factor"] == "SUPPLY_OPEC" and row["factor_conf"] == 0.9


# ── reads ─────────────────────────────────────────────────────────────────────

def test_recent_orders_newest_first(temp_corpus):
    temp_corpus.upsert_articles([
        _art("old", "older", ts="20260101T000000Z"),
        _art("new", "newer", ts="20260601T000000Z"),
    ])
    rows = temp_corpus.recent(10)
    assert [r["url"] for r in rows] == ["new", "old"]

def test_unclassified_excludes_classified(temp_corpus):
    temp_corpus.upsert_articles([_art("u1", "a"), _art("u2", "b")])
    temp_corpus.set_classification("u1", "INVENTORY", 0.7)
    urls = [r["url"] for r in temp_corpus.unclassified(10)]
    assert urls == ["u2"]

def test_recent_filters_by_factor(temp_corpus):
    temp_corpus.upsert_articles([_art("u1", "a"), _art("u2", "b")])
    temp_corpus.set_classification("u1", "GEOPOLITICAL", 0.8)
    temp_corpus.set_classification("u2", "WEATHER", 0.6)
    rows = temp_corpus.recent(10, factor="WEATHER")
    assert [r["url"] for r in rows] == ["u2"]


# ── stats ─────────────────────────────────────────────────────────────────────

def test_stats_shape(temp_corpus):
    temp_corpus.upsert_articles([
        _art("u1", "a", ts="20260101T000000Z"),
        _art("u2", "b", ts="20260601T000000Z"),
        {"url": "u3", "title": "no ts", "published_at": None},
    ])
    temp_corpus.set_classification("u1", "SUPPLY_OPEC", 0.9)
    s = temp_corpus.stats()
    assert s["total"] == 3
    assert s["classified"] == 1
    assert s["with_timestamp"] == 2
    assert s["span"] == ["2026-01-01T00:00:00+00:00", "2026-06-01T00:00:00+00:00"]
    assert s["by_factor"] == {"SUPPLY_OPEC": 1}


# ── backfill (injected fetcher — no network) ──────────────────────────────────

def test_backfill_pages_windows_and_inserts(temp_corpus):
    calls = []

    def fake_fetch(start, end, max_articles=250):
        calls.append((start, end))
        # one unique article per window
        tag = start.strftime("%Y%m%d")
        return {"articles": [_art(f"u-{tag}", f"headline {tag}",
                                  ts=start.strftime("%Y%m%dT000000Z"))]}

    res = temp_corpus.backfill_gdelt(
        datetime(2026, 1, 1, tzinfo=timezone.utc),
        datetime(2026, 1, 22, tzinfo=timezone.utc),
        window_days=7, fetch_fn=fake_fetch,
    )
    assert res["windows"] == 3            # 21 days / 7
    assert res["rows_inserted"] == 3
    assert res["empty_windows"] == 0
    assert len(calls) == 3

def test_backfill_counts_empty_windows(temp_corpus):
    res = temp_corpus.backfill_gdelt(
        datetime(2026, 1, 1, tzinfo=timezone.utc),
        datetime(2026, 1, 15, tzinfo=timezone.utc),
        window_days=7, fetch_fn=lambda *a, **k: {"articles": []},
    )
    assert res["windows"] == 2 and res["rows_inserted"] == 0 and res["empty_windows"] == 2


# ── classifier (keyword fallback path, no Groq key) ───────────────────────────

@pytest.mark.parametrize("title,expected", [
    ("OPEC+ agrees deeper production cut", "SUPPLY_OPEC"),
    ("Tanker attacked near Strait of Hormuz", "GEOPOLITICAL"),
    ("EIA reports surprise crude inventory draw at Cushing", "INVENTORY"),
    ("Refinery outage widens gasoline crack spread", "REFINING_PRODUCTS"),
    ("Hurricane bears down on Gulf of Mexico platforms", "WEATHER"),
    ("Fed signals rate cut as inflation cools, dollar slips", "MONETARY_DOLLAR"),
    ("China demand outlook weakens on slowing GDP", "DEMAND_MACRO"),
    ("Hedge funds cut net long positioning ahead of expiry", "POSITIONING"),
    ("Local bakery wins community award", "NOISE"),
])
def test_keyword_factor(title, expected):
    factor, conf = classify.keyword_factor(title)
    assert factor == expected
    assert 0.0 < conf <= 1.0

def test_classify_headlines_falls_back_to_keyword(temp_corpus):
    res = classify.classify_headlines(["OPEC cuts output", "Hurricane hits Gulf"])
    assert [r["factor"] for r in res] == ["SUPPLY_OPEC", "WEATHER"]
    assert all(r["source"] == "keyword" for r in res)

def test_classify_corpus_persists(temp_corpus):
    temp_corpus.upsert_articles([
        _art("u1", "OPEC+ deepens production cut"),
        _art("u2", "Drone strike on refinery"),
    ])
    out = classify.classify_corpus(limit=10)
    assert out["classified"] == 2
    assert out["by_source"] == {"keyword": 2}
    # factors persisted → nothing left unclassified
    assert temp_corpus.unclassified(10) == []
    factors = {r["url"]: r["factor"] for r in temp_corpus.recent(10)}
    assert factors == {"u1": "SUPPLY_OPEC", "u2": "GEOPOLITICAL"}

def test_all_keyword_factors_are_valid_labels():
    for _, kws in classify._KEYWORDS:
        pass
    assert set(f for f, _ in classify._KEYWORDS) <= classify.VALID
    assert "NOISE" in classify.VALID
