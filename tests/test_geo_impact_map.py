"""Hermetic tests for the geo impact map (Sprint 2)."""

from research.news_impact.geo import registry as reg
from research.news_impact.geo import impact_map as im


def test_event_polarity():
    assert im.event_polarity("outage") == 1
    assert im.event_polarity("attack") == 1
    assert im.event_polarity("restart") == -1
    assert im.event_polarity("opec_hike") == -1
    assert im.event_polarity("opec_cut") == 1
    assert im.event_polarity(None) == 0
    assert im.event_polarity("merger") == 0      # unrecognised → no claim


def test_severity_scales_magnitude():
    assert im.severity_mult("minor") < im.severity_mult("moderate") < \
           im.severity_mult("major") < im.severity_mult("severe")


def test_chokepoint_closure_is_crude_bullish_brent_over_wti():
    v = im.impact_vector(reg.by_id("hormuz"), "closure", "severe")
    assert v["brent_flat"] > 0
    assert v["brent_structure"] > 0
    assert v["wti_brent"] < 0          # Brent strengthens vs WTI → WTI-Brent down


def test_refinery_outage_vs_restart_flip():
    fire = im.impact_vector(reg.by_id("port_arthur"), "fire", "major")
    assert fire["ho_crack"] > 0        # less product → crack up
    assert fire["wti_flat"] < 0        # demand destruction → crude down
    restart = im.impact_vector(reg.by_id("port_arthur"), "restart", "major")
    assert restart["ho_crack"] < 0     # exact sign flip
    assert restart["wti_flat"] > 0


def test_opec_cut_vs_hike_flip():
    cut = im.impact_vector(reg.by_id("opec"), "opec_cut", "major")
    hike = im.impact_vector(reg.by_id("opec"), "opec_hike", "major")
    assert cut["brent_flat"] > 0 and hike["brent_flat"] < 0
    assert cut["brent_flat"] == -hike["brent_flat"]


def test_unknown_event_makes_no_claim():
    assert im.impact_vector(reg.by_id("hormuz"), None) == {}
    assert im.impact_vector(reg.by_id("hormuz"), "merger") == {}


def test_headline_impact_sums_and_clamps():
    assets = [reg.by_id("druzhba"), reg.by_id("russia_supply")]
    out = im.headline_impact(assets, "sanction", "major")
    # gasoil_crack: russia(2)*1.5 + druzhba(1)*1.5 = 4.5 → clamped to 3.0
    assert out["nodes"]["gasoil_crack"] == 3.0
    assert all(abs(v) <= 3.0 for v in out["nodes"].values())
    assert len(out["contributors"]) == 2
    assert "sanction" in out["rationale"]


def test_headline_impact_no_assets_or_unknown_event():
    assert im.headline_impact([], "outage")["nodes"] == {}
    assert im.headline_impact([reg.by_id("hormuz")], None)["nodes"] == {}
    assert "no" in im.headline_impact([], "outage")["rationale"].lower()
