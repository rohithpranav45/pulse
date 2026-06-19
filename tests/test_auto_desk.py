"""
Phase 3 — live auto-trade desk (backend/research/auto_desk.py).

Hermetic behavioural tests: the live recommendation and the stress state are
monkeypatched, and the paper book is pointed at a fresh temp DB, so nothing
touches the live feed, the GMM, /Data, or the real cache.db. They prove the desk
reconciliation rules:
  • market-hours gate (weekday + fresh feed)
  • opens ONLY the gated/decorrelated `portfolio.selected`, BUY→LONG / SELL→SHORT
  • dedup: a second tick on the same book holds (no duplicate position)
  • shock breaker pauses NEW entries (open trades untouched)
  • direction flip closes the stale side ('flip') and opens the new side
  • market closed → no entries
"""
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

import paper_trading as pt              # noqa: E402
from research import auto_desk as ad    # noqa: E402


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture()
def fresh_book(monkeypatch):
    """Point paper_trading at a fresh temp cache.db and (re)create the schema."""
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "cache.db")
        monkeypatch.setattr(pt, "_DB_PATH", path)
        pt._ensure_table()
        # Clear paper_trading's short-TTL live-price cache between tests.
        pt._live_spread_cache.clear()
        # Neutralise the live-price lookup so mark_to_market (run by
        # list_positions) never auto-closes on a real /Data price — these tests
        # only exercise the open/flip/hold reconciliation, not the exit rule.
        monkeypatch.setattr(pt, "_live_price", lambda asset: None)
        yield path


def _fresh_feed_ts() -> str:
    """A feed bar timestamp that reads as 'fresh' to is_market_open."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _rec(selected, ranked, *, available=True, feed_ts=None):
    """Build a canned get_live_recommendation payload."""
    return {
        "available": available,
        "as_of_live": feed_ts or _fresh_feed_ts(),
        "regime": "BACK/LOW/STRESSED",
        "ranked": ranked,
        "portfolio": {"selected": selected, "rho_max": 0.70},
        "live_feed": {"as_of": feed_ts or _fresh_feed_ts()},
    }


def _row(spread, direction, *, conf=0.9, cur=1.0, target=0.5, stop=2.5):
    return {
        "spread": spread, "direction": direction, "confidence": conf,
        "current": cur, "target": target, "stop": stop,
        "fair_value": cur - 0.5, "z_score": -3.0, "regime": "BACK",
        "label": spread, "winner_model": "XGBoost", "rationale": "test thesis",
    }


def _patch_engine(monkeypatch, rec, *, breaker=False, market_open=True):
    monkeypatch.setattr(ad, "get_live_recommendation", lambda **k: rec)
    monkeypatch.setattr(ad, "live_stress_state",
                        lambda *a, **k: {"breaker_active": breaker, "p_stress": 0.4,
                                         "onset": 0.3 if breaker else 0.0, "label": "STRESS",
                                         "as_of": "2026-06-19"})
    monkeypatch.setattr(ad, "is_market_open", lambda *a, **k: (market_open, "open" if market_open else "weekend"))
    monkeypatch.delenv("PULSE_AUTO_DESK_DISABLED", raising=False)


def _open_assets(status="open"):
    return {p["asset"]: p for p in pt.list_positions(status) if p.get("source") == ad.AUTO_SOURCE}


# ── is_market_open ───────────────────────────────────────────────────────────

def test_market_open_weekday_fresh_feed():
    wed = datetime(2026, 6, 17, 14, 0, tzinfo=timezone.utc)   # Wednesday
    feed = (wed - timedelta(minutes=10)).isoformat(timespec="seconds")
    ok, reason = ad.is_market_open(feed, now=wed)
    assert ok and reason == "open"


def test_market_closed_on_weekend():
    sat = datetime(2026, 6, 20, 14, 0, tzinfo=timezone.utc)   # Saturday
    feed = (sat - timedelta(minutes=5)).isoformat(timespec="seconds")
    ok, reason = ad.is_market_open(feed, now=sat)
    assert not ok and reason == "weekend"


def test_market_closed_on_stale_feed():
    wed = datetime(2026, 6, 17, 14, 0, tzinfo=timezone.utc)
    feed = (wed - timedelta(minutes=120)).isoformat(timespec="seconds")   # > 90 min
    ok, reason = ad.is_market_open(feed, now=wed)
    assert not ok and reason == "stale_feed"


def test_market_no_feed_ts():
    wed = datetime(2026, 6, 17, 14, 0, tzinfo=timezone.utc)
    ok, reason = ad.is_market_open(None, now=wed)
    assert not ok and reason == "no_feed_ts"


# ── run_auto_desk ────────────────────────────────────────────────────────────

def test_opens_only_selected_buy_maps_to_long(fresh_book, monkeypatch):
    # ranked has two spreads but only one is selected → open exactly that one.
    ranked = [_row("brent_m1_m2", "BUY"), _row("wti_m1_m2", "SELL")]
    rec = _rec(["brent_m1_m2"], ranked)
    _patch_engine(monkeypatch, rec)

    out = ad.run_auto_desk()
    assert out["ran"] and out["entries_allowed"]
    assert [o["spread"] for o in out["opened"]] == ["brent_m1_m2"]

    held = _open_assets()
    assert set(held) == {"brent_m1_m2"}
    assert held["brent_m1_m2"]["direction"] == "LONG"   # BUY → LONG
    assert held["brent_m1_m2"]["source"] == ad.AUTO_SOURCE


def test_sell_maps_to_short(fresh_book, monkeypatch):
    rec = _rec(["wti_m1_m2"], [_row("wti_m1_m2", "SELL")])
    _patch_engine(monkeypatch, rec)
    ad.run_auto_desk()
    assert _open_assets()["wti_m1_m2"]["direction"] == "SHORT"


def test_dedup_same_direction_holds(fresh_book, monkeypatch):
    rec = _rec(["brent_m1_m2"], [_row("brent_m1_m2", "BUY")])
    _patch_engine(monkeypatch, rec)
    ad.run_auto_desk()
    out2 = ad.run_auto_desk()          # second tick on the same book
    assert out2["opened"] == []        # nothing new opened
    assert len(_open_assets()) == 1    # still exactly one position


def test_breaker_pauses_new_entries(fresh_book, monkeypatch):
    rec = _rec(["brent_m1_m2"], [_row("brent_m1_m2", "BUY")])
    _patch_engine(monkeypatch, rec, breaker=True)
    out = ad.run_auto_desk()
    assert out["breaker_active"] and not out["entries_allowed"]
    assert out["opened"] == []
    assert out["skipped"][0]["reason"] == "breaker"
    assert _open_assets() == {}


def test_market_closed_no_entries(fresh_book, monkeypatch):
    rec = _rec(["brent_m1_m2"], [_row("brent_m1_m2", "BUY")])
    _patch_engine(monkeypatch, rec, market_open=False)
    out = ad.run_auto_desk()
    assert not out["entries_allowed"]
    assert out["opened"] == []
    assert _open_assets() == {}


def test_flip_closes_stale_side_and_opens_new(fresh_book, monkeypatch):
    # First tick: open BUY/LONG.
    rec_buy = _rec(["brent_m1_m2"], [_row("brent_m1_m2", "BUY")])
    _patch_engine(monkeypatch, rec_buy)
    ad.run_auto_desk()
    first = _open_assets()["brent_m1_m2"]
    assert first["direction"] == "LONG"

    # Second tick: the engine now wants SELL on the same spread → flip.
    rec_sell = _rec(["brent_m1_m2"], [_row("brent_m1_m2", "SELL")])
    _patch_engine(monkeypatch, rec_sell)
    out = ad.run_auto_desk()
    assert len(out["flipped"]) == 1
    assert out["flipped"][0]["from"] == "LONG" and out["flipped"][0]["to"] == "SHORT"

    # Old row closed with reason 'flip'; new SHORT row is open.
    closed = [p for p in pt.list_positions("closed") if p["id"] == first["id"]]
    assert closed and closed[0]["close_reason"] == "flip"
    held = _open_assets()
    assert set(held) == {"brent_m1_m2"} and held["brent_m1_m2"]["direction"] == "SHORT"


def test_deselected_position_left_running(fresh_book, monkeypatch):
    # Open brent; then the book no longer selects it → it must stay open.
    rec1 = _rec(["brent_m1_m2"], [_row("brent_m1_m2", "BUY")])
    _patch_engine(monkeypatch, rec1)
    ad.run_auto_desk()

    rec2 = _rec([], [_row("brent_m1_m2", "NEUTRAL")])
    _patch_engine(monkeypatch, rec2)
    out = ad.run_auto_desk()
    assert [r["spread"] for r in out["left_running"]] == ["brent_m1_m2"]
    assert set(_open_assets()) == {"brent_m1_m2"}   # untouched, runs under its stop


def test_disabled_env_short_circuits(fresh_book, monkeypatch):
    rec = _rec(["brent_m1_m2"], [_row("brent_m1_m2", "BUY")])
    _patch_engine(monkeypatch, rec)
    monkeypatch.setenv("PULSE_AUTO_DESK_DISABLED", "1")
    out = ad.run_auto_desk()
    assert out["ran"] is False and out["reason"] == "disabled"
    assert _open_assets() == {}


def test_feed_unavailable(fresh_book, monkeypatch):
    monkeypatch.setattr(ad, "get_live_recommendation",
                        lambda **k: {"available": False, "error": "feed down"})
    monkeypatch.delenv("PULSE_AUTO_DESK_DISABLED", raising=False)
    out = ad.run_auto_desk()
    assert out["ran"] is False and out["reason"] == "feed_unavailable"


def test_dry_run_takes_no_action(fresh_book, monkeypatch):
    rec = _rec(["brent_m1_m2"], [_row("brent_m1_m2", "BUY")])
    _patch_engine(monkeypatch, rec)
    out = ad.run_auto_desk(dry_run=True)
    assert out["dry_run"] and out["actions"]            # planned, not executed
    assert _open_assets() == {}                         # nothing opened
