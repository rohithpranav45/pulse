"""
Phase 4.G — signal_log session-dedup behaviour.

These tests drive `_record_signal` directly (bypassing the live engine) on a
fresh in-temp-dir cache.db. They prove:
  • Repeated (instrument, direction) firings on later bars bump bar_count
    and keep row count = 1.
  • A direction flip closes the prior session with reason 'flip' and opens
    a new row → row count = 2.
"""
import os
import sqlite3
import sys
import tempfile

import pytest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from research import signal_log as sl  # noqa: E402


def _payload(direction: str, entry: float = 100.0):
    return {
        "cadence":        "intraday",
        "instrument":     "brent_m1_m2",
        "label":          "Brent M1-M2",
        "regime":         "BACK/LOW/STRESSED",
        "regime_mode":    "gated",
        "direction":      direction,
        "source":         "regime",
        "winner_model":   "XGBoost",
        "confidence":     0.9,
        "entry":          entry,
        "fair_value":     entry + 1.0,
        "z_score":        -3.5,
        "band_low":       None,
        "band_high":      None,
        "target":         entry + 0.5,
        "stop":           entry - 1.5,
        "notional_scale": 1.0,
        "rationale":      "test",
        "metadata_json":  None,
    }


@pytest.fixture()
def fresh_db(monkeypatch):
    """Point signal_log at a fresh temp DB for the duration of the test."""
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "cache.db")
        monkeypatch.setattr(sl, "_DB_PATH", path)
        sl.ensure_schema()
        yield path


def _count_rows(path: str) -> int:
    c = sqlite3.connect(path)
    try:
        return c.execute("SELECT COUNT(*) FROM signal_log").fetchone()[0]
    finally:
        c.close()


def _row(path: str, rowid: int = 1) -> dict:
    c = sqlite3.connect(path)
    c.row_factory = sqlite3.Row
    try:
        return dict(c.execute("SELECT * FROM signal_log WHERE id=?", (rowid,)).fetchone())
    finally:
        c.close()


def test_same_direction_across_three_bars_yields_one_row(fresh_db):
    c = sl._conn()
    try:
        for i, feed in enumerate(["2026-06-16T10:00:00", "2026-06-16T10:15:00", "2026-06-16T10:30:00"]):
            sl._record_signal(
                c,
                instrument="brent_m1_m2",
                direction="BUY",
                now_iso=f"2026-06-16T10:{i*15:02d}:01",
                feed_as_of=feed,
                row_payload=_payload("BUY", entry=100.0 + i * 0.1),
            )
        c.commit()
    finally:
        c.close()

    assert _count_rows(fresh_db) == 1
    row = _row(fresh_db)
    assert row["bar_count"] == 3
    assert row["status"] == "OPEN"
    assert row["last_seen_at"] == "2026-06-16T10:30:00"
    assert row["close_reason"] is None


def test_same_feed_as_of_is_noop(fresh_db):
    """Re-firing the daily + intraday jobs on the same bar must not bump bar_count."""
    c = sl._conn()
    try:
        for _ in range(3):
            sl._record_signal(
                c,
                instrument="brent_m1_m2",
                direction="BUY",
                now_iso="2026-06-16T10:00:01",
                feed_as_of="2026-06-16T10:00:00",
                row_payload=_payload("BUY"),
            )
        c.commit()
    finally:
        c.close()

    assert _count_rows(fresh_db) == 1
    assert _row(fresh_db)["bar_count"] == 1


def test_collapse_duplicate_open_sessions(fresh_db):
    """
    Repair pass: when multiple OPEN rows exist for the same (instrument,
    direction) — the legacy v1→v2 migration scenario that left phantom rows
    in the live cache.db — _collapse_duplicate_open_sessions should:
      • keep the oldest opened_at_session row as canonical
      • fold all duplicate bar_counts into it
      • refresh last_seen_at to the newest seen across the group
      • close every duplicate with close_reason='duplicate'
    Idempotent: a second call leaves the DB untouched.
    """
    timestamps = [
        "2026-06-16T10:00:00",
        "2026-06-16T10:15:00",
        "2026-06-16T10:30:00",
        "2026-06-16T10:45:00",
        "2026-06-16T11:00:00",
    ]
    c = sl._conn()
    try:
        for i, ts in enumerate(timestamps):
            c.execute(
                """INSERT INTO signal_log
                   (signal_at, feed_as_of, cadence, instrument, label, direction,
                    confidence, entry, fair_value, z_score,
                    opened_at_session, last_seen_at, bar_count, status)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    ts, ts,
                    "intraday", "brent_m1_m2", "Brent M1-M2", "BUY",
                    0.9, 100.0 + i, 101.0, -3.5,
                    ts, ts, 1, "OPEN",
                ),
            )
        c.commit()
        assert _count_rows(fresh_db) == 5

        # First call collapses 4 dupes → 1 canonical OPEN + 4 CLOSED.
        n = sl._collapse_duplicate_open_sessions(c)
        c.commit()
        assert n == 4

        keeper = c.execute(
            "SELECT id, status, bar_count, last_seen_at, opened_at_session FROM signal_log WHERE status='OPEN'"
        ).fetchall()
        assert len(keeper) == 1
        k = dict(keeper[0])
        # oldest opened_at_session preserved as canonical
        assert k["opened_at_session"] == "2026-06-16T10:00:00"
        # bar counts summed
        assert k["bar_count"] == 5
        # newest last_seen_at promoted
        assert k["last_seen_at"] == "2026-06-16T11:00:00"

        closed = c.execute(
            "SELECT close_reason FROM signal_log WHERE status='CLOSED'"
        ).fetchall()
        assert len(closed) == 4
        assert all(r["close_reason"] == "duplicate" for r in closed)

        # Idempotent: a second collapse is a no-op.
        n2 = sl._collapse_duplicate_open_sessions(c)
        assert n2 == 0
    finally:
        c.close()


def test_perf_close_books_at_target_level_not_live(fresh_db, monkeypatch):
    # Disable the staleness guard — fake snapshots use an old timestamp.
    monkeypatch.setattr(sl, "_FEED_STALE_MINUTES", 10_000_000.0)
    """
    When TP trips, the row's close_value + realised_move must be booked at the
    TARGET LEVEL, not at the (potentially-overshot) live price. Mirrors
    exit_sim's fill-at-level semantics and prevents the optimistic over-counting
    that the previous code had (it used live `cur` for both close_value and
    realised_move).
    """
    # Open a BUY signal at 100 with target 105, stop 90.
    c = sl._conn()
    try:
        sl._record_signal(
            c,
            instrument="brent_m1_m2",
            direction="BUY",
            now_iso="2026-06-16T10:00:01",
            feed_as_of="2026-06-16T10:00:00",
            row_payload={**_payload("BUY", entry=100.0),
                         "target": 105.0, "stop": 90.0,
                         "fair_value": 110.0},
        )
        c.commit()
    finally:
        c.close()

    # Force the live snapshot to report 110 (overshoot past the 105 target).
    def fake_snap(product):
        if product == "CO":
            return {
                "available": True,
                "as_of": "2026-06-16 10:30:00",
                "spreads": {
                    "brent_m1_m2": {"value": 110.0, "as_of": "2026-06-16 10:30:00"}
                },
            }
        return {"available": False}
    monkeypatch.setattr(sl, "_cached_live_snapshot", fake_snap)

    res = sl.update_signal_performance()
    assert res["closed"] == 1

    row = _row(fresh_db)
    assert row["status"] == "CLOSED"
    assert row["close_reason"] == "target"
    # Book at level (105), NOT at live overshoot (110).
    assert row["close_value"] == 105.0
    assert row["realised_move"] == 5.0   # 105 - 100, not 110 - 100
    # mtm_value still records the actual observed live price for transparency.
    assert row["mtm_value"] == 110.0


def test_perf_ambiguous_bar_resolves_to_stop(fresh_db, monkeypatch):
    """A bar where both TP and SL conditions are true → resolve conservatively
    as 'stop', not optimistically as 'target'."""
    monkeypatch.setattr(sl, "_FEED_STALE_MINUTES", 10_000_000.0)
    c = sl._conn()
    try:
        sl._record_signal(
            c,
            instrument="brent_m1_m2",
            direction="BUY",
            now_iso="2026-06-16T10:00:01",
            feed_as_of="2026-06-16T10:00:00",
            row_payload={**_payload("BUY", entry=100.0),
                         "target": 101.0, "stop": 99.0,
                         "fair_value": 110.0},
        )
        c.commit()
    finally:
        c.close()

    # Live price equally past target (101) and stop (99) — impossible
    # simultaneously in reality but possible across a single 15-min poll on a
    # gap; we accept either side.
    # Simulate by reporting a price that crosses both — use stop side.
    def fake_snap(product):
        if product == "CO":
            return {
                "available": True,
                "as_of": "2026-06-16 10:30:00",
                "spreads": {
                    # value at 102 triggers TP only; we need both, so simulate
                    # by hitting target side but the perf sees stop already
                    # crossed in a prior tick (we'll set the test up so both
                    # checks return True for this case using a value past both
                    # — not physically possible, but exercises the safety net).
                    # The BUY rule: tp_hit = cur >= 101, sl_hit = cur <= 99.
                    # Both true → cur must satisfy >=101 AND <=99: impossible.
                    # So instead, raise the stop above target to manufacture
                    # the ambiguous-bar case.
                    "brent_m1_m2": {"value": 100.5, "as_of": "2026-06-16 10:30:00"}
                },
            }
        return {"available": False}
    monkeypatch.setattr(sl, "_cached_live_snapshot", fake_snap)

    # Re-key the row so the ambiguous case fires: set stop > target.
    cc = sl._conn()
    cc.execute("UPDATE signal_log SET target=99.5, stop=101.5 WHERE id=1")
    cc.commit(); cc.close()

    res = sl.update_signal_performance()
    assert res["closed"] == 1
    row = _row(fresh_db)
    assert row["close_reason"] == "stop"
    assert row["close_value"] == 101.5
    assert row["realised_move"] == 1.5     # 101.5 - 100


def test_perf_stale_feed_skips_sweep(fresh_db, monkeypatch):
    """If the live feed bar is older than the staleness threshold, the perf
    sweep returns early — no rows are touched, no time-stop can fire on
    wall-clock against frozen prices."""
    c = sl._conn()
    try:
        sl._record_signal(
            c, instrument="brent_m1_m2", direction="BUY",
            now_iso="2026-06-16T10:00:01", feed_as_of="2026-06-16T10:00:00",
            row_payload=_payload("BUY", entry=100.0),
        )
        c.commit()
    finally:
        c.close()

    # Snapshot reports a bar from 4 hours ago — well past _FEED_STALE_MINUTES.
    def fake_snap(product):
        if product == "CO":
            return {
                "available": True,
                "as_of": "2026-06-16 06:00:00",   # 4h before "now" in the test
                "spreads": {
                    "brent_m1_m2": {"value": 95.0, "as_of": "2026-06-16 06:00:00"}
                },
            }
        return {"available": False}
    monkeypatch.setattr(sl, "_cached_live_snapshot", fake_snap)
    # Freeze "now" 4h after the snapshot timestamp.
    class _FakeDT:
        @staticmethod
        def now(tz=None):
            from datetime import datetime
            return datetime(2026, 6, 16, 10, 0, 0, tzinfo=tz or sl.timezone.utc)
        @staticmethod
        def fromisoformat(s):
            from datetime import datetime
            return datetime.fromisoformat(s)
    monkeypatch.setattr(sl, "datetime", _FakeDT)

    res = sl.update_signal_performance()
    assert res.get("skipped_stale_feed") is True
    # Row untouched.
    row = _row(fresh_db)
    assert row["status"] == "OPEN"
    assert row["mtm_value"] is None


def test_direction_flip_closes_prior_session_and_opens_new(fresh_db):
    c = sl._conn()
    try:
        sl._record_signal(
            c,
            instrument="brent_m1_m2",
            direction="BUY",
            now_iso="2026-06-16T10:00:01",
            feed_as_of="2026-06-16T10:00:00",
            row_payload=_payload("BUY", entry=100.0),
        )
        sl._record_signal(
            c,
            instrument="brent_m1_m2",
            direction="SELL",
            now_iso="2026-06-16T10:30:01",
            feed_as_of="2026-06-16T10:30:00",
            row_payload=_payload("SELL", entry=101.0),
        )
        c.commit()
    finally:
        c.close()

    assert _count_rows(fresh_db) == 2
    closed = _row(fresh_db, rowid=1)
    opened = _row(fresh_db, rowid=2)
    assert closed["status"] == "CLOSED"
    assert closed["close_reason"] == "flip"
    assert opened["status"] == "OPEN"
    assert opened["direction"] == "SELL"
    assert opened["bar_count"] == 1
