"""Tests for the geo-map payload (Sprint 9).

Hermetic — a synthetic live store on disk (no network / no Groq / no /Data).
Proves: `map_assets` drops the GLOBAL generics + the unplaceable (0,0) assets,
keeps every registry asset's coordinates + disruption_bias, and tallies live-event
activity per asset (count / peak conviction / any-EDGE / newest ts / capped
headlines) from the Sprint-8 store.
"""

import json

from research.news_impact.geo import live as gl
from research.news_impact.geo import registry as reg


def _write_store(tmp_path, events):
    p = tmp_path / "geo_live_events.json"
    p.write_text(json.dumps({"events": events}))
    return p


def test_map_excludes_generics_and_unplaceable(tmp_path):
    assets = gl.map_assets(store_path=_write_store(tmp_path, []))
    ids = {a["id"] for a in assets}
    assert ids and not (ids & reg.GENERIC_IDS)          # no generic placeholders
    for a in assets:
        assert not (a["lat"] == 0.0 and a["lon"] == 0.0)  # real coordinates
        assert a["region"] != "GLOBAL"
        assert a["disruption_bias"]                       # every asset has a prior


def test_map_has_coords_and_bias_for_known_asset(tmp_path):
    assets = gl.map_assets(store_path=_write_store(tmp_path, []))
    hz = next(a for a in assets if a["id"] == "hormuz")
    src = reg.by_id("hormuz")
    assert hz["lat"] == src.lat and hz["lon"] == src.lon
    assert hz["disruption_bias"]["brent_flat"] > 0        # closure bids crude flat
    assert hz["activity"]["events"] == 0                  # no live store → zeroed


def test_map_tallies_activity(tmp_path):
    events = [
        {"asset_ids": ["hormuz"], "title": "Hormuz closure", "conviction": 2.0,
         "tradeable": True, "tradeable_nodes": ["wti_brent"],
         "ts": "2026-06-30T10:00:00Z", "url": "u://1"},
        {"asset_ids": ["hormuz"], "title": "Hormuz tensions ease", "conviction": 1.0,
         "tradeable": False, "ts": "2026-06-29T10:00:00Z"},
        {"asset_ids": ["port_arthur"], "title": "Port Arthur fire", "conviction": 1.5,
         "tradeable": False, "ts": "2026-06-30T09:00:00Z"},
    ]
    assets = gl.map_assets(store_path=_write_store(tmp_path, events))
    hz = next(a for a in assets if a["id"] == "hormuz")
    assert hz["activity"]["events"] == 2
    assert hz["activity"]["conviction"] == 2.0            # peak across events
    assert hz["activity"]["tradeable"] is True            # any tradeable
    assert hz["activity"]["last_ts"] == "2026-06-30T10:00:00Z"  # newest
    assert len(hz["activity"]["headlines"]) == 2
    pa = next(a for a in assets if a["id"] == "port_arthur")
    assert pa["activity"]["events"] == 1 and pa["activity"]["tradeable"] is False


def test_map_headlines_capped(tmp_path):
    events = [{"asset_ids": ["hormuz"], "title": f"event {i}", "conviction": 1.0,
               "ts": f"2026-06-30T1{i}:00:00Z"} for i in range(6)]
    assets = gl.map_assets(store_path=_write_store(tmp_path, events))
    hz = next(a for a in assets if a["id"] == "hormuz")
    assert hz["activity"]["events"] == 6
    assert len(hz["activity"]["headlines"]) == 4          # capped at 4
