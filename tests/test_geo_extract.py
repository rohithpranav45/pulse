"""Tests for geo-extraction (Sprint 2).

Exercises the deterministic fallback (no API key needed) end-to-end, the
extract→impact_map integration, and the Claude orchestration via monkeypatch so
no network call is made.
"""

import pytest

from research.news_impact.geo import registry as reg
from research.news_impact.geo import extract as ex
from research.news_impact.geo.extract import GeoExtraction


@pytest.fixture(autouse=True)
def _no_api_keys(monkeypatch):
    """Force the deterministic fallback path — never hit a live LLM in tests."""
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


def test_fallback_resolves_asset_and_event():
    r = ex.extract_headline("Houthi drone strike hits a tanker in the Red Sea",
                            provider="fallback")
    assert r.source == "fallback"
    assert r.asset_ids == ["bab_el_mandeb"]
    assert r.event_type == "attack"
    assert r.is_oil_relevant


def test_inflection_catches_resumes_and_halted():
    assert ex.extract_headline("Jamnagar refinery resumes operations").event_type == "restart"
    assert ex.extract_headline("Druzhba pipeline halted after a blast").event_type in (
        "outage", "explosion")        # 'blast' (explosion) or 'halted' (outage) both valid


def test_severity_detection():
    r = ex.extract_headline("Massive fire forces complete shutdown at Port Arthur")
    assert r.severity == "severe"
    r2 = ex.extract_headline("Minor outage briefly hits Pernis refinery")
    assert r2.severity == "minor"


def test_non_oil_headline_has_no_assets():
    r = ex.extract_headline("Tech stocks rally on strong quarterly earnings")
    assert r.asset_ids == []
    assert r.is_oil_relevant is False
    assert r.event_type is None


def test_opec_cut_and_hike_inferred_from_member_plus_verb():
    assert ex.extract_headline("OPEC+ agrees a deeper production cut").event_type == "opec_cut"
    assert ex.extract_headline("OPEC+ to raise output next month").event_type == "opec_hike"


def test_score_headline_geo_integration():
    out = ex.score_headline_geo("Fire forces shutdown at Motiva Port Arthur refinery")
    assert out["extraction"]["asset_ids"] == ["port_arthur"]
    nodes = out["impact"]["nodes"]
    assert nodes.get("ho_crack", 0) > 0 and nodes.get("wti_flat", 0) < 0
    # non-oil → no node claim
    assert ex.score_headline_geo("Quarterly earnings beat")["impact"]["nodes"] == {}


def test_resolve_assets_validates_and_unions():
    # invalid id dropped; valid id kept; text-resolved asset unioned
    assets = ex._resolve_assets("trouble near the Strait of Hormuz",
                                extra_ids=["not_a_real_id", "opec"])
    ids = {a.id for a in assets}
    assert "hormuz" in ids and "opec" in ids and "not_a_real_id" not in ids


def test_orchestration_prefers_llm_then_falls_back(monkeypatch):
    crafted = GeoExtraction(asset_ids=["hormuz"], event_type="closure",
                            severity="severe", source="groq", confidence=0.9)
    monkeypatch.setattr(ex, "_llm_extract_batch", lambda titles, provider, model: [crafted])
    got = ex.extract_headlines(["anything"])
    assert got[0].source == "groq" and got[0].event_type == "closure"

    # when the LLM is unavailable (returns None), fall back deterministically
    monkeypatch.setattr(ex, "_llm_extract_batch", lambda titles, provider, model: None)
    got2 = ex.extract_headlines(["Drone strike in the Red Sea"])
    assert got2[0].source == "fallback" and got2[0].asset_ids == ["bab_el_mandeb"]


def test_llm_batches_short_circuit_without_keys():
    # _no_api_keys fixture cleared both — provider dispatch yields no LLM
    assert ex._claude_extract_batch(["x"], ex.LIVE_MODEL) is None
    assert ex._groq_extract_batch(["x"], ex.GROQ_MODEL) is None
    assert ex._llm_extract_batch(["x"], "auto", None) is None


def test_geo_prefilter_high_recall():
    assert ex.is_geo_candidate("Drone strike on Saudi oil facility")
    assert ex.is_geo_candidate("US refinery utilisation rises")        # generic noun
    assert ex.is_geo_candidate("Random headline", factor="GEOPOLITICAL")  # factor gate
    assert not ex.is_geo_candidate("Local school board meeting recap")
