"""Tests for the geo RAG analog engine (Sprint 5).

Hermetic — synthetic event panels prove the fingerprint similarity, the per-event
collapse, nearest-neighbour ranking (same kind ranks high, opposite-direction
ranks low), the similarity-weighted forecast, and the headline entrypoint via a
monkeypatched extractor. No /Data, no LLM, no network.
"""

import numpy as np
import pandas as pd
import pytest

from research.news_impact.geo import analogs as an
from research.news_impact.geo import event_study_geo as es


# ── fingerprint + cosine ────────────────────────────────────────────────────────
def test_fingerprint_identical_events_are_cosine_one():
    a = an.fingerprint("chokepoint", "closure", {"brent_flat": 2.0, "ho_crack": 1.0})
    b = an.fingerprint("chokepoint", "closure", {"brent_flat": 2.0, "ho_crack": 1.0})
    assert an._cosine(a, b) == pytest.approx(1.0)


def test_fingerprint_opposite_direction_scores_lower():
    """A closure (bullish crude) vs a restart (bearish crude) on the same asset:
    the flipped conviction block pulls cosine well below an exact match."""
    closure = an.fingerprint("chokepoint", "closure", {"brent_flat": 2.0, "brent_structure": 2.0})
    restart = an.fingerprint("chokepoint", "restart", {"brent_flat": -2.0, "brent_structure": -2.0})
    same = an.fingerprint("chokepoint", "closure", {"brent_flat": 2.0, "brent_structure": 2.0})
    assert an._cosine(closure, restart) < an._cosine(closure, same)


def test_cosine_zero_vector_safe():
    assert an._cosine(np.zeros(3), np.ones(3)) == 0.0


# ── synthetic panel → index ─────────────────────────────────────────────────────
def _panel_row(ts, title, atype, etype, node, conv, d1, d5):
    ps = int(np.sign(conv))
    return {"published_at": pd.Timestamp(ts), "title": title, "asset_type": atype,
            "event_type": etype, "regime": "BACK", "node": node, "conviction": conv,
            "pred_sign": ps, "d1": d1, "vn1": (d1 * ps), "hit1": float(np.sign(d1) == ps),
            "d5": d5, "vn5": (d5 * ps), "hit5": float(np.sign(d5) == ps)}


def _synthetic_panel():
    rows = [
        # two chokepoint closures (crude up) — one moved ho_crack up, one down at 5d
        _panel_row("2026-04-01", "Hormuz shut", "chokepoint", "closure", "brent_flat", 2.0, 1.0, 2.0),
        _panel_row("2026-04-01", "Hormuz shut", "chokepoint", "closure", "ho_crack", 1.0, 0.5, 1.5),
        _panel_row("2026-04-05", "Bab strait blocked", "chokepoint", "blockage", "brent_flat", 2.0, 0.8, -1.0),
        _panel_row("2026-04-05", "Bab strait blocked", "chokepoint", "blockage", "ho_crack", 1.0, 0.3, 2.0),
        # a refinery attack (cracks up, crude down) — different kind
        _panel_row("2026-04-10", "Refinery hit", "refinery", "attack", "ho_crack", 1.5, 1.0, 1.0),
        _panel_row("2026-04-10", "Refinery hit", "refinery", "attack", "brent_flat", -1.5, -0.5, -0.5),
        # a chokepoint RESTART (crude down) — opposite direction to the closures
        _panel_row("2026-04-12", "Hormuz reopens", "chokepoint", "restart", "brent_flat", -2.0, -1.0, -1.5),
    ]
    return pd.DataFrame(rows)


def test_build_index_collapses_to_events():
    idx = an.build_analog_index(_synthetic_panel())
    # 4 distinct (date, atype, etype, title) events
    assert len(idx) == 4
    closure = next(e for e in idx.events if e.event_type == "closure")
    assert set(closure.conviction) == {"brent_flat", "ho_crack"}
    assert closure.outcomes["ho_crack"]["d5"] == 1.5


def test_find_analogs_ranks_same_kind_top_and_opposite_low():
    idx = an.build_analog_index(_synthetic_panel())
    query = {"asset_type": "chokepoint", "event_type": "closure",
             "conviction": {"brent_flat": 2.0, "ho_crack": 1.0}}
    # min_sim=-1 so even the dissimilar opposite-direction restart is included to compare
    res = an.find_analogs(query, k=10, index=idx, min_sim=-1.0)
    assert res[0]["event_type"] == "closure" and res[0]["similarity"] > 0.9
    # the opposite-direction restart ranks well below the same-direction closures
    sims = {r["event_type"]: r["similarity"] for r in res}
    assert sims["restart"] < sims["closure"] and sims["restart"] < sims["blockage"]


def test_find_analogs_reports_direction_agreement():
    idx = an.build_analog_index(_synthetic_panel())
    query = {"asset_type": "chokepoint", "event_type": "closure",
             "conviction": {"brent_flat": 2.0}}
    res = an.find_analogs(query, k=4, index=idx)
    # the blockage analog moved brent_flat DOWN at 5d (d5=-1.0) → disagrees with up-prediction
    blk = next(r for r in res if r["event_type"] == "blockage")
    assert blk["node_moves"]["brent_flat"]["agree5"] is False
    assert blk["node_moves"]["brent_flat"]["agree1"] is True   # up at 1d


def test_analog_forecast_weighted_aggregation():
    idx = an.build_analog_index(_synthetic_panel())
    query = {"asset_type": "chokepoint", "event_type": "closure",
             "conviction": {"brent_flat": 2.0, "ho_crack": 1.0}}
    fc = an.analog_forecast(query, k=8, horizon=5, index=idx)
    bf = fc["nodes"]["brent_flat"]
    assert bf["basis"] == "analog" and bf["n_analogs"] >= 2
    assert 0.0 <= bf["analog_agree"] <= 1.0
    assert bf["pred_dir"] == 1


def test_analog_forecast_no_analog_node():
    idx = an.build_analog_index(_synthetic_panel())
    query = {"asset_type": "chokepoint", "event_type": "closure",
             "conviction": {"regrade": 2.0}}     # no analog claims regrade
    fc = an.analog_forecast(query, k=8, horizon=5, index=idx)
    assert fc["nodes"]["regrade"]["basis"] == "no_analog"


def test_score_headline_analogs_via_monkeypatched_extractor(monkeypatch):
    from research.news_impact.geo import extract as ex
    idx = an.build_analog_index(_synthetic_panel())
    monkeypatch.setattr(ex, "score_headline_geo", lambda title, provider="auto": {
        "extraction": {"asset_type": "chokepoint", "event_type": "closure"},
        "impact": {"nodes": {"brent_flat": 2.0}},
    })
    res = an.score_headline_analogs("anything", k=4, horizon=5, index=idx)
    assert res["available"] is True
    assert res["nodes"]["brent_flat"]["basis"] == "analog"


def test_score_headline_analogs_non_geo_returns_unavailable(monkeypatch):
    from research.news_impact.geo import extract as ex
    monkeypatch.setattr(ex, "score_headline_geo", lambda title, provider="auto": {
        "extraction": {"asset_type": None, "event_type": None}, "impact": {"nodes": {}},
    })
    res = an.score_headline_analogs("local council parking debate", index=an.AnalogIndex(events=[]))
    assert res["available"] is False


def test_empty_index_safe():
    assert an.find_analogs({"conviction": {"brent_flat": 1.0}}, index=an.AnalogIndex(events=[])) == []
    assert an.build_analog_index(pd.DataFrame()).events == []


# ── narration (Sprint 10) ───────────────────────────────────────────────────────
def _result(query, horizon=5):
    idx = an.build_analog_index(_synthetic_panel())
    fc = an.analog_forecast(query, k=8, horizon=horizon, index=idx)
    return {"query": query, "available": True, **fc}


_QUERY = {"asset_type": "chokepoint", "event_type": "closure",
          "conviction": {"brent_flat": 2.0, "ho_crack": 1.0}}


def test_narrate_template_is_grounded(monkeypatch):
    """The deterministic fallback cites exact analog numbers + the single-episode caveat."""
    monkeypatch.setattr(es, "load_cached", lambda: {})        # no edges → no disk read
    nb = an.narrate(_result(_QUERY), provider="template")
    assert nb["available"] is True and nb["source"] == "template"
    assert "Single-episode" in nb["note"]
    # the note quotes a real per-node figure from the evidence (n=… appears)
    assert any(f"n={r['n']}" in nb["note"] for r in nb["evidence"]["rows"])


def test_narrate_uses_injected_llm(monkeypatch):
    """An injected LLM phrases the note; it is fed ONLY the exact-number facts block."""
    monkeypatch.setattr(es, "load_cached", lambda: {})
    captured = {}

    def fake_llm(system, user):
        captured["system"], captured["user"] = system, user
        return "Trust the ULSD-crack read; fade crude flat. Single episode — read direction."

    nb = an.narrate(_result(_QUERY), llm_fn=fake_llm)
    assert nb["source"] == "llm" and nb["note"].startswith("Trust")
    # the facts block carried the labelled node + the agreement/n figures (not invented)
    assert "ULSD crack" in captured["user"] and "agreement" in captured["user"]
    assert "invent" in captured["system"].lower()             # the no-numbers instruction


def test_narrate_degrades_gracefully_without_groq(monkeypatch):
    """No Groq key + no llm_fn → the template, not a crash or an empty note."""
    monkeypatch.setattr(es, "load_cached", lambda: {})
    monkeypatch.setattr(an, "_groq_narrate", lambda *a, **k: None)   # simulate no key/failure
    nb = an.narrate(_result(_QUERY), provider="auto")
    assert nb["available"] is True and nb["source"] == "template" and nb["note"]


def test_narrate_marks_certified_edge(monkeypatch):
    monkeypatch.setattr(es, "load_cached", lambda: {
        "available": True,
        "hit_tables": {"5": [{"slice": "node", "node": "ho_crack", "asset_type": "*",
                              "regime": "*", "hit": 0.7, "n": 40, "p": 0.01,
                              "significant": True}], "1": []},
    })
    nb = an.narrate(_result(_QUERY), provider="template")
    ho = next(r for r in nb["evidence"]["rows"] if r["node"] == "ho_crack")
    assert ho["edge"] is True                                  # graded EDGE flows into evidence


def test_narrate_unavailable_result_is_graceful():
    nb = an.narrate({"available": False, "reason": "no geo asset/impact resolved"})
    assert nb["available"] is False and "resolved" in nb["note"]


def test_narrate_no_analog_rows_is_graceful(monkeypatch):
    monkeypatch.setattr(es, "load_cached", lambda: {})
    # a node nothing in the index claims → no analog rows to narrate
    res = _result({"asset_type": "chokepoint", "event_type": "closure",
                   "conviction": {"regrade": 2.0}})
    nb = an.narrate(res, provider="template")
    assert nb["available"] is False and "No analog node reads" in nb["note"]
