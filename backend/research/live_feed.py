"""
Phase 3.1 — live intraday market-data adapter.

The mentor now records live 15-minute OHLCV bars per futures contract into
daily SQLite files on the office share:

    I:\\Public\\Summer Interns Energy\\DB\\bars_15min_YYYYMMDD.db

Each file has one table per contract, named `{PRODUCT}_{TENOR}` where PRODUCT
is `CO` (ICE Brent) or `CL` (CME WTI) and TENOR is a futures month code +
2-digit year (e.g. `CO_Q26` = Brent Aug-2026). Schema per table:
    timestamp TEXT (UTC bar-open), open, high, low, close, volume.

This module turns that raw per-contract feed into the *same* spread instruments
the regime engine already trades (spread_universe.INSTRUMENTS) — but built from
**real** contract prices instead of the historical daily settlements (and, for
WTI, instead of the synthetic 1-min-mid estimate; see CLAUDE.md gotcha 11).

The mapping that makes this work: the engine's legs are nearby-ordinal
(`c1`=front, `c2`=2nd, `c3`=3rd, `c6`=6th, `c12`=12th). We list the live
contract tables for a product, sort by actual expiry (decoded from the month
code + year), and assign c1, c2, … in that order. Today, Brent's front listed
contract is Q26 (Jul/M26/N26 already rolled off), WTI's is N26 — they start at
different months, which is exactly why ordinal mapping (not month code) is the
right abstraction.

What this module does NOT do: it does not recompute the slow regime features
(inventory vs 5-yr, COT positioning, cracks, macro). Those move daily/weekly
and are sourced from the existing research caches. The live feed updates the
**fast** state a desk re-reads intraday — current spread level and curve shape
(m1_m12). `live_engine.py` overlays this snapshot onto the latest historical
feature row before ranking.

Public API
----------
  resolve_feed_dir()                 → Path to the live feed directory
  latest_feed_file([dir])            → most-recent bars_*.db Path (or None)
  list_contracts(conn, product)      → [(table, expiry_date), …] sorted by expiry
  get_live_snapshot(product="CO")    → dict: real spreads + curve + leg prices + meta
  CONTRACT_MONTHS                    → month-code → calendar-month map

Run `python -m research.live_feed` to print the current Brent + WTI snapshot.
"""

from __future__ import annotations

import logging
import os
import re
import sqlite3
import sys
from datetime import date
from pathlib import Path

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

log = logging.getLogger("pulse.research.live_feed")

# Default office-share location of the recorder output (the path the mentor
# shared). Override with the PULSE_LIVE_FEED_DIR env var (e.g. on the Oracle
# box, which can't see the I: share — see CLAUDE.md / the deploy notes).
_DEFAULT_FEED_DIR = r"I:\Public\Summer Interns Energy\DB"

# Futures month codes → calendar month number.
CONTRACT_MONTHS = {
    "F": 1, "G": 2, "H": 3, "J": 4, "K": 5, "M": 6,
    "N": 7, "Q": 8, "U": 9, "V": 10, "X": 11, "Z": 12,
}

# Which nearby ordinals the spread universe references — we only need to map
# this many legs. (c1, c2, c3, c6 feed the spreads; c12 feeds the curve.)
_MAX_ORDINAL = 12

_TABLE_RE = re.compile(r"^(CO|CL)_([FGHJKMNQUVXZ])(\d{2})$")


def resolve_feed_dir() -> Path:
    """Live feed directory: PULSE_LIVE_FEED_DIR override, else the office share."""
    return Path(os.environ.get("PULSE_LIVE_FEED_DIR") or _DEFAULT_FEED_DIR)


def _date_from_name(p: Path) -> str:
    """Extract the YYYYMMDD stamp from a bars_15min_YYYYMMDD.db filename."""
    m = re.search(r"(\d{8})", p.name)
    return m.group(1) if m else ""


def latest_feed_file(feed_dir: Path | None = None) -> Path | None:
    """
    Most-recent bars_*.db in the feed dir. Prefers the largest date stamp in the
    filename (one file per trading day); falls back to mtime if names are
    unstamped. Returns None when the directory is unreachable or empty.
    """
    d = feed_dir or resolve_feed_dir()
    if not d.is_dir():
        log.warning("live feed dir not reachable: %s", d)
        return None
    files = [p for p in d.glob("bars_*.db") if p.is_file()]
    if not files:
        log.warning("no bars_*.db files in feed dir: %s", d)
        return None
    files.sort(key=lambda p: (_date_from_name(p), p.stat().st_mtime))
    return files[-1]


def _connect_ro_wal(f: Path) -> sqlite3.Connection:
    """
    Open a feed DB read-only while still seeing the live writer's WAL.

    Tries `mode=ro` first (read-only, WAL-aware via the -shm the recorder
    maintains). Falls back to a normal connection if the share rejects the URI.
    We deliberately avoid `immutable=1` — it skips the WAL, so we'd read only
    the checkpointed fragment and miss the most-recent live bars.
    """
    try:
        return sqlite3.connect(f"file:{f}?mode=ro", uri=True, timeout=5.0)
    except sqlite3.OperationalError:
        return sqlite3.connect(str(f), timeout=5.0)


def _expiry_sort_key(month_code: str, yy: str) -> date:
    """Approximate contract expiry as the 1st of its delivery month (sort only)."""
    return date(2000 + int(yy), CONTRACT_MONTHS[month_code], 1)


def list_contracts(conn: sqlite3.Connection, product: str) -> list[tuple[str, date]]:
    """
    Return [(table_name, expiry_date), …] for one product ('CO'|'CL'),
    sorted ascending by expiry (so index 0 = front = c1).
    """
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    out: list[tuple[str, date]] = []
    for (name,) in rows:
        m = _TABLE_RE.match(name)
        if not m or m.group(1) != product:
            continue
        out.append((name, _expiry_sort_key(m.group(2), m.group(3))))
    out.sort(key=lambda t: t[1])
    return out


def _latest_close(conn: sqlite3.Connection, table: str) -> tuple[str, float, float] | None:
    """(timestamp, close, volume) of the most-recent bar in `table`, or None."""
    row = conn.execute(
        f'SELECT timestamp, close, volume FROM "{table}" ORDER BY timestamp DESC LIMIT 1'
    ).fetchone()
    if row is None:
        return None
    return str(row[0]), float(row[1]), float(row[2])


def _spread_at_common_ts(
    conn: sqlite3.Connection,
    legs: list[tuple[str, float]],
    tables_by_ordinal: dict[str, str],
) -> tuple[float, str] | None:
    """
    Compute a signed-leg spread at the most-recent timestamp where EVERY leg has
    a bar (contemporaneous prices — no stale-leg mixing). `legs` is the
    spread_universe LEG_DEFS entry, e.g. [("c1",1.0),("c2",-1.0)].

    Returns (spread_value, timestamp) or None if any leg is missing / the legs
    never share a bar.
    """
    tables = []
    for ordinal, _qty in legs:
        t = tables_by_ordinal.get(ordinal)
        if t is None:
            return None
        tables.append(t)

    # Build an inner-join over timestamps across all leg tables, newest first.
    base, *rest = tables
    sql = f'SELECT b0.timestamp, ' + ", ".join(f"b{i}.close" for i in range(len(tables)))
    sql += f' FROM "{base}" b0'
    for i, t in enumerate(rest, start=1):
        sql += f' JOIN "{t}" b{i} ON b{i}.timestamp = b0.timestamp'
    sql += " ORDER BY b0.timestamp DESC LIMIT 1"
    row = conn.execute(sql).fetchone()
    if row is None:
        return None
    ts = str(row[0])
    closes = [float(x) for x in row[1:]]
    value = sum(qty * px for (_, qty), px in zip(legs, closes))
    return value, ts


def get_live_snapshot(product: str = "CO", feed_dir: Path | None = None) -> dict:
    """
    Build a live market snapshot for one product from the most-recent feed file.

    product : 'CO' (Brent) | 'CL' (WTI)

    Returns
    -------
    {
      "available": bool,
      "product":   "CO"|"CL",
      "source_file": "<path>",
      "as_of":     "<latest bar timestamp seen across legs, UTC>",
      "n_contracts": int,
      "legs": { "c1": {"table","expiry","close","volume","ts"}, ... },
      "curve": { "m1_m12": float|None, "c1": float, "c12": float|None },
      "spreads": { "<engine spread key>": {"value": float, "as_of": ts}, ... },
      "error": "<message>"   # only when available is False
    }

    Engine spread keys use the spread_universe naming so the snapshot drops
    straight into the ranker: brent_m1_m2 / brent_m3_m6 / brent_fly_123 for CO,
    wti_* for CL.
    """
    from research.spread_universe import LEG_DEFS

    prod = product.upper()
    if prod not in ("CO", "CL"):
        return {"available": False, "error": f"unknown product {product!r} (expected CO|CL)"}
    engine_prefix = "brent" if prod == "CO" else "wti"

    f = latest_feed_file(feed_dir)
    if f is None:
        return {"available": False, "error": f"no live feed file under {resolve_feed_dir()}"}

    # Read-only connection that STILL sees the live writer's WAL. The recorder
    # keeps most recent bars in the -wal file; `immutable=1` would skip it and
    # we'd read only the (tiny) checkpointed fragment, so we must NOT use it.
    # Plain `mode=ro` replays/reads the WAL via the -shm the writer maintains.
    # Fall back to a normal connection if the share rejects the ro URI.
    conn = _connect_ro_wal(f)

    try:
        contracts = list_contracts(conn, prod)
        if not contracts:
            return {"available": False, "error": f"no {prod}_* tables in {f.name}",
                    "source_file": str(f)}

        # Map nearby ordinals c1..c12 to actual tables by expiry order.
        tables_by_ordinal: dict[str, str] = {}
        legs_meta: dict[str, dict] = {}
        as_of = ""
        for i, (table, expiry) in enumerate(contracts[:_MAX_ORDINAL], start=1):
            ordinal = f"c{i}"
            tables_by_ordinal[ordinal] = table
            lc = _latest_close(conn, table)
            if lc is not None:
                ts, close, vol = lc
                as_of = max(as_of, ts)
                legs_meta[ordinal] = {
                    "table":  table,
                    "expiry": expiry.strftime("%Y-%m"),
                    "close":  round(close, 4),
                    "volume": vol,
                    "ts":     ts,
                }

        # Real spreads at contemporaneous prices.
        spreads: dict[str, dict] = {}
        for engine_key, legs in LEG_DEFS.items():
            if not engine_key.startswith(engine_prefix + "_"):
                continue
            res = _spread_at_common_ts(conn, legs, tables_by_ordinal)
            if res is not None:
                value, ts = res
                spreads[engine_key] = {"value": round(value, 4), "as_of": ts}

        # Curve m1_m12 = c1 - c12 at a common timestamp.
        curve = {"m1_m12": None, "c1": None, "c12": None}
        c1 = legs_meta.get("c1", {}).get("close")
        c12 = legs_meta.get("c12", {}).get("close")
        curve["c1"], curve["c12"] = c1, c12
        m1_m12 = _spread_at_common_ts(conn, [("c1", 1.0), ("c12", -1.0)], tables_by_ordinal)
        if m1_m12 is not None:
            curve["m1_m12"] = round(m1_m12[0], 4)
        elif c1 is not None and c12 is not None:
            curve["m1_m12"] = round(c1 - c12, 4)  # fallback: last-close diff

        return {
            "available":   True,
            "product":     prod,
            "source_file": str(f),
            "as_of":       as_of or None,
            "n_contracts": len(contracts),
            "legs":        legs_meta,
            "curve":       curve,
            "spreads":     spreads,
        }
    finally:
        conn.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    import json
    print(f"feed dir : {resolve_feed_dir()}")
    print(f"latest   : {latest_feed_file()}")
    for prod in ("CO", "CL"):
        snap = get_live_snapshot(prod)
        print(f"\n=== {prod} snapshot ===")
        if not snap.get("available"):
            print("  UNAVAILABLE:", snap.get("error"))
            continue
        print(f"  as_of   : {snap['as_of']}  ({snap['n_contracts']} contracts)")
        print(f"  curve   : m1_m12={snap['curve']['m1_m12']}  "
              f"(c1={snap['curve']['c1']} c12={snap['curve']['c12']})")
        print("  legs (c1..c6):")
        for o in ("c1", "c2", "c3", "c4", "c5", "c6"):
            m = snap["legs"].get(o)
            if m:
                print(f"    {o:>3}  {m['table']:<8} exp={m['expiry']}  close={m['close']:<9} vol={m['volume']}")
        print("  spreads :")
        for k, v in snap["spreads"].items():
            print(f"    {k:<16} {v['value']:+.4f}  @ {v['as_of']}")
