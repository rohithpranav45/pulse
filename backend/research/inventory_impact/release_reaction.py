"""
Release reaction — what the spreads ACTUALLY did after the EIA print.
=====================================================================

The framework predicts the reaction; this measures it. Reads the desk's 1-minute
bar feed (``I:\\Public\\Summer Interns Energy\\DB\\extra\\bars_1min_*.db`` —
per-contract OHLCV, CO_=Brent / CL_=WTI, identical format to the 15-min live
feed), anchors at the EIA release minute (10:30 ET = 14:30 UTC), and computes the
move in each affected instrument at +5 / +15 / +30 / +60 min:

    WTI flat      % return
    Brent flat    % return
    WTI-Brent     $/bbl change   (the cleanest expression of a US crude surprise)
    WTI M1-M2     $/bbl change   (prompt physical tightness)

So the dashboard can put PREDICTED next to ACTUAL and grade the call.

Public API
----------
    compute_reaction(release_utc=None, horizons=(5,15,30,60)) -> dict
"""

from __future__ import annotations

import os
import re
import sqlite3
import shutil
import tempfile
import logging
from glob import glob
from datetime import datetime, timezone

import pandas as pd

log = logging.getLogger("pulse.inventory_impact.release_reaction")

_MONTH = {"F": 1, "G": 2, "H": 3, "J": 4, "K": 5, "M": 6,
          "N": 7, "Q": 8, "U": 9, "V": 10, "X": 11, "Z": 12}
HORIZONS = (5, 15, 30, 60)


def _feed_dir() -> str:
    return os.getenv("PULSE_INVENTORY_1MIN_DIR",
                     r"I:\Public\Summer Interns Energy\DB\extra")


def _latest_db(feed_dir: str) -> str | None:
    files = sorted(glob(os.path.join(feed_dir, "bars_1min_*.db")))
    return files[-1] if files else None


def _feed_date(db_path: str) -> str | None:
    m = re.search(r"bars_1min_(\d{8})\.db", os.path.basename(db_path))
    return m.group(1) if m else None


def _snapshot(db_path: str) -> str:
    """Copy the WAL db (+ -wal, never the stale -shm) to a local temp file and
    read the copy — reading a WAL db in place over the SMB share raises
    'database disk image is malformed' (gotcha 14)."""
    tmpdir = tempfile.mkdtemp(prefix="pulse_invrx_")
    local = os.path.join(tmpdir, os.path.basename(db_path))
    shutil.copy2(db_path, local)
    wal = db_path + "-wal"
    if os.path.exists(wal):
        try:
            shutil.copy2(wal, local + "-wal")
        except Exception:
            pass
    return local


def _expiry(table: str):
    m = re.match(r"(CO|CL)_([FGHJKMNQUVXZ])(\d{2})", table)
    if not m:
        return (table, 9999, 99)
    return (m.group(1), 2000 + int(m.group(3)), _MONTH[m.group(2)])


def _ordered(conn: sqlite3.Connection, product: str) -> list[str]:
    tabs = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    p = [t for t in tabs if t.startswith(product + "_")]
    return sorted(p, key=lambda t: (_expiry(t)[1], _expiry(t)[2]))


def _close(conn: sqlite3.Connection, table: str) -> pd.Series:
    df = pd.read_sql(f'SELECT timestamp, close FROM "{table}"', conn,
                     parse_dates=["timestamp"]).set_index("timestamp")["close"]
    return df[df > 0].sort_index()


def _spread_frame(conn: sqlite3.Connection) -> pd.DataFrame | None:
    co = _ordered(conn, "CO")
    cl = _ordered(conn, "CL")
    if len(co) < 1 or len(cl) < 2:
        return None
    co1 = _close(conn, co[0])
    cl1, cl2 = _close(conn, cl[0]), _close(conn, cl[1])
    idx = co1.index.union(cl1.index).union(cl2.index)
    f = pd.DataFrame({
        "brent_flat": co1, "wti_flat": cl1,
        "wti_brent": (cl1 - co1), "wti_m1_m2": (cl1 - cl2),
    }).reindex(idx).ffill().dropna()
    return f if not f.empty else None


def compute_reaction(release_utc: datetime | None = None,
                     horizons=HORIZONS) -> dict:
    """
    Actual post-release spread moves at each horizon. ``release_utc`` defaults to
    the feed-date's EIA release minute (14:30 UTC = 10:30 ET). Returns the move in
    each instrument at +N min vs the release-minute anchor.
    """
    feed_dir = _feed_dir()
    db = _latest_db(feed_dir)
    if db is None or not os.path.exists(db):
        return {"available": False, "reason": f"no 1-min feed in {feed_dir}"}

    try:
        local = _snapshot(db)
        conn = sqlite3.connect(local)
        try:
            if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                return {"available": False, "reason": "feed integrity check failed"}
            frame = _spread_frame(conn)
        finally:
            conn.close()
    except Exception as exc:
        log.warning("reaction read failed: %s", exc)
        return {"available": False, "reason": str(exc)}

    if frame is None or frame.empty:
        return {"available": False, "reason": "no spread series in feed"}

    if release_utc is None:
        fd = _feed_date(db) or frame.index[0].strftime("%Y%m%d")
        d = datetime.strptime(fd, "%Y%m%d")
        release_utc = datetime(d.year, d.month, d.day, 14, 30, 0)  # 10:30 ET
    rel = pd.Timestamp(release_utc).tz_localize(None)

    pre = frame[frame.index <= rel]
    if pre.empty:
        return {"available": False, "reason": "no bars at/before the release minute"}
    base = pre.iloc[-1]
    anchor_ts = pre.index[-1]

    actual = []
    for mins in horizons:
        tgt = rel + pd.Timedelta(minutes=mins)
        post_rows = frame[frame.index <= tgt]
        if post_rows.empty or frame.index[-1] < tgt - pd.Timedelta(minutes=2):
            # not enough tape yet for this horizon
            if frame.index[-1] < tgt:
                actual.append({"mins": mins, "pending": True})
                continue
        post = post_rows.iloc[-1]
        actual.append({
            "mins": mins,
            "wti_flat_pct":   round(float(post["wti_flat"] / base["wti_flat"] - 1) * 100, 3),
            "brent_flat_pct": round(float(post["brent_flat"] / base["brent_flat"] - 1) * 100, 3),
            "d_wti_brent":    round(float(post["wti_brent"] - base["wti_brent"]), 3),
            "d_wti_m1_m2":    round(float(post["wti_m1_m2"] - base["wti_m1_m2"]), 3),
            "pending": False,
        })

    return {
        "available": True,
        "release_utc": rel.strftime("%Y-%m-%d %H:%M") + "Z",
        "release_et": (rel - pd.Timedelta(hours=4)).strftime("%H:%M") + " ET",
        "anchor_ts": str(anchor_ts),
        "anchor": {
            "wti_flat": round(float(base["wti_flat"]), 2),
            "brent_flat": round(float(base["brent_flat"]), 2),
            "wti_brent": round(float(base["wti_brent"]), 2),
            "wti_m1_m2": round(float(base["wti_m1_m2"]), 2),
        },
        "horizons": list(horizons),
        "actual": actual,
        "n_bars": int(len(frame)),
        "feed_span": [str(frame.index[0]), str(frame.index[-1])],
        "feed_file": os.path.basename(db),
        "source": "desk 1-min feed (CO/CL bars)",
    }


if __name__ == "__main__":
    import json
    logging.basicConfig(level=logging.INFO)
    print(json.dumps(compute_reaction(), indent=2, default=str))
