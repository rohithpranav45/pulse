"""Hermetic tests for the geo asset registry (Sprint 1, Phase 0)."""

from research.news_impact.geo import registry as reg


def test_registry_integrity():
    assets = reg.all_assets()
    assert len(assets) >= 30
    ids = [a.id for a in assets]
    assert len(ids) == len(set(ids)), "duplicate asset ids"
    for a in assets:
        assert a.type in reg.ASSET_TYPES
        assert a.carries, f"{a.id} has no carries"
        assert -90 <= a.lat <= 90 and -180 <= a.lon <= 180, f"{a.id} bad coords"
        # every bias node must be a canonical node, every sign in range
        for node, sign in a.disruption_bias.items():
            assert node in reg.NODES, f"{a.id}: unknown node {node}"
            assert sign in (-2, -1, 0, 1, 2), f"{a.id}: bad sign {sign}"


def test_every_type_populated():
    for t in reg.ASSET_TYPES:
        assert reg.by_type(t), f"no assets of type {t}"


def test_resolve_chokepoint_and_alias():
    hits = reg.resolve("Houthi attack on a tanker in the Red Sea overnight")
    assert hits and hits[0].id == "bab_el_mandeb"
    # alias resolution + bias sign: shipping reroute is bullish gasoil crack
    assert hits[0].disruption_bias.get("gasoil_crack", 0) > 0


def test_resolve_refinery_outage_bias_is_crack_positive_crude_negative():
    hits = reg.resolve("Fire forces a shutdown at Motiva Port Arthur refinery")
    assert hits and hits[0].id == "port_arthur"
    bias = hits[0].disruption_bias
    assert bias.get("ho_crack", 0) > 0          # less product → crack up
    assert bias.get("wti_flat", 0) < 0          # demand destruction → crude down


def test_resolve_specificity_longest_alias_wins():
    # "strait of hormuz" should win over a generic gulf mention
    hits = reg.resolve("Tankers diverted near the Strait of Hormuz")
    assert hits[0].id == "hormuz"


def test_resolve_empty_and_nomatch():
    assert reg.resolve("") == []
    assert reg.resolve("quarterly earnings beat expectations") == []


def test_alias_index_points_to_real_assets():
    idx = reg.alias_index()
    assert idx
    for alias, aid in idx.items():
        assert reg.by_id(aid) is not None


def test_event_type_partition():
    # disruptive + restorative partition the recognised verbs (no overlap)
    assert reg.DISRUPTIVE_EVENTS <= reg.EVENT_TYPES
    assert reg.RESTORATIVE_EVENTS <= reg.EVENT_TYPES
    assert not (reg.DISRUPTIVE_EVENTS & reg.RESTORATIVE_EVENTS)
