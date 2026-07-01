"""Tests for the live geo news ingestion (Sprint 8).

Hermetic — a synthetic wire + a monkeypatched extractor (no network / no Groq /
no /Data). Proves: the geo-candidate prefilter spends the budget only on geo news,
each headline is scored once (deduped in the store), only headlines with a node
vector are persisted, events are ranked by |conviction| × tradeable, and EDGE
tags flow through from a (monkeypatched) graded edge map. The extractor-not-called
test guards that no token budget is spent when there are no geo candidates.
"""

import json

import pytest

from research.news_impact.geo import live as gl
from research.news_impact.geo import event_study_geo as es
from research.news_impact.geo.extract import GeoExtraction


# ── helpers ──────────────────────────────────────────────────────────────────
def _ex(asset_ids, atype, etype, sev="severe", source="groq", oil=True):
    return GeoExtraction(is_oil_relevant=oil, asset_ids=asset_ids, asset_type=atype,
                         event_type=etype, severity=sev, source=source)


def _fake_extractor(mapping):
    """Return an extract_fn(titles)->list[GeoExtraction] from a title→extraction map.
    Raises if asked for a title not in the map (so we assert exactly what's sent)."""
    def fn(titles):
        out = []
        for t in titles:
            assert t in mapping, f"unexpected title sent to extractor: {t!r}"
            out.append(mapping[t])
        return out
    return fn


def _store(tmp_path):
    return tmp_path / "geo_live_events.json"


# ── prefilter + scoring ──────────────────────────────────────────────────────
def test_ingest_scores_geo_candidate_and_skips_non_geo(tmp_path):
    hormuz = "Iran threatens to close the Strait of Hormuz amid escalation"
    wire = [
        {"title": hormuz, "url": "u://1", "source": "demo",
         "published_at": "2026-06-30T10:00:00Z"},
        {"title": "Apple unveils a new iPhone", "url": "u://2", "source": "demo"},
    ]
    ext = _fake_extractor({hormuz: _ex(["hormuz"], "chokepoint", "closure")})
    res = gl.ingest_wire(wire, extract_fn=ext, store_path=_store(tmp_path))
    assert res["scanned"] == 2
    assert res["candidates"] == 1          # only the geo headline is a candidate
    assert res["added"] == 1

    store = json.loads(_store(tmp_path).read_text())
    ev = store["events"][0]
    assert ev["asset_type"] == "chokepoint" and ev["event_type"] == "closure"
    assert ev["nodes"].get("brent_flat", 0) > 0      # closure → crude flat bid
    assert ev["conviction"] > 0


def test_extractor_not_called_when_no_geo_candidates(tmp_path):
    """No geo candidate → the LLM extractor is never invoked (budget preserved)."""
    def boom(_titles):
        raise AssertionError("extractor must not be called with no candidates")
    wire = [{"title": "Apple unveils a new iPhone", "url": "u://1"},
            {"title": "Stocks rally on earnings", "url": "u://2"}]
    res = gl.ingest_wire(wire, extract_fn=boom, store_path=_store(tmp_path))
    assert res["candidates"] == 0 and res["added"] == 0


def test_no_node_vector_not_persisted(tmp_path):
    """A resolved asset with no throughput event yields no node vector → skipped."""
    title = "Reliance Jamnagar refinery hosts an investor day"
    ext = _fake_extractor({title: _ex(["jamnagar"], "refinery", None)})
    res = gl.ingest_wire([{"title": title, "url": "u://1"}],
                         extract_fn=ext, store_path=_store(tmp_path))
    assert res["candidates"] == 1 and res["added"] == 0
    assert not _store(tmp_path).exists()   # nothing written


def test_dedup_scores_each_headline_once(tmp_path):
    hormuz = "Strait of Hormuz tanker traffic blocked after seizure"
    wire = [{"title": hormuz, "url": "u://1", "published_at": "2026-06-30T10:00:00Z"}]
    ext = _fake_extractor({hormuz: _ex(["hormuz"], "chokepoint", "blockage")})
    sp = _store(tmp_path)
    r1 = gl.ingest_wire(wire, extract_fn=ext, store_path=sp)
    r2 = gl.ingest_wire(wire, extract_fn=ext, store_path=sp)
    assert r1["added"] == 1 and r2["added"] == 0
    assert r2["total"] == 1


# ── ranking ──────────────────────────────────────────────────────────────────
def test_recent_events_ranked_by_conviction_times_tradeable(tmp_path, monkeypatch):
    # synthetic edge map: only gasoil_crack is a measured EDGE @5d (node-level)
    monkeypatch.setattr(es, "load_cached", lambda: {
        "available": True,
        "hit_tables": {"5": [{"slice": "node", "node": "gasoil_crack", "asset_type": "*",
                              "regime": "*", "hit": 0.7, "n": 40, "p": 0.01,
                              "significant": True}],
                       "1": []},
    })
    big = "Houthi attack on a Red Sea oil tanker forces a major reroute"   # gasoil_crack ↑↑
    small = "Minor brief outage on the CPC pipeline"                        # no crack, low conv
    wire = [{"title": big, "url": "u://1"}, {"title": small, "url": "u://2"}]
    ext = _fake_extractor({
        big:   _ex(["bab_el_mandeb"], "chokepoint", "attack", sev="major"),
        small: _ex(["cpc"], "pipeline", "outage", sev="minor"),
    })
    gl.ingest_wire(wire, extract_fn=ext, store_path=_store(tmp_path))
    ranked = gl.recent_events(limit=10, store_path=_store(tmp_path))
    assert len(ranked) == 2
    assert ranked[0]["title"] == big          # tradeable + higher conviction floats up
    assert ranked[0]["tradeable"] is True
    assert "gasoil_crack" in ranked[0]["tradeable_nodes"]
    assert ranked[1]["tradeable"] is False    # CPC outage stays a prior


def test_prior_tag_when_no_edge_map(tmp_path, monkeypatch):
    monkeypatch.setattr(es, "load_cached", lambda: {})   # no graded edges
    title = "Iran moves to close the Strait of Hormuz"
    ext = _fake_extractor({title: _ex(["hormuz"], "chokepoint", "closure")})
    gl.ingest_wire([{"title": title, "url": "u://1"}],
                   extract_fn=ext, store_path=_store(tmp_path))
    ev = gl.recent_events(store_path=_store(tmp_path))[0]
    assert ev["tradeable"] is False and ev["tradeable_nodes"] == []
    assert all(e.get("basis") == "prior" for e in ev["edges"].values())


def test_store_capped_to_max(tmp_path, monkeypatch):
    monkeypatch.setattr(gl, "_MAX_STORED", 3)
    monkeypatch.setattr(es, "load_cached", lambda: {})
    sp = _store(tmp_path)
    for i in range(5):
        t = f"Drone strike hits oil tanker number {i} in the Red Sea"
        ext = _fake_extractor({t: _ex(["bab_el_mandeb"], "chokepoint", "attack")})
        gl.ingest_wire([{"title": t, "url": f"u://{i}",
                         "published_at": f"2026-06-3{i}T10:00:00Z"[:20]}],
                       extract_fn=ext, store_path=sp)
    store = json.loads(sp.read_text())
    assert len(store["events"]) == 3
