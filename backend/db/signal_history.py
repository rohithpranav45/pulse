"""
Signal History
==============
Persists the last 500 signal scores per asset to the shared SQLite database
(pulse_cache.db) for sparkline rendering in the dashboard.

Table: signal_history(id INTEGER PK AUTOINCREMENT, timestamp REAL,
                       asset TEXT, score REAL, conviction TEXT, top_driver TEXT)
Max 500 rows total across all assets — oldest rows pruned when count exceeds limit.

Public API
----------
  append_history(asset, score, conviction, top_driver) -> None
  get_history(asset, n=24) -> list[float]   # newest n scores, oldest-first
"""

import os
import sqlite3
import threading
import time
import logging

log = logging.getLogger("pulse.signal_history")

_DB_PATH  = os.path.join(os.path.abspath(os.path.dirname(__file__)), "pulse_cache.db")
_MAX_ROWS = 500
_lock     = threading.Lock()
_local    = threading.local()


def _conn() -> sqlite3.Connection:
    if not hasattr(_local, "sh_conn"):
        c = sqlite3.connect(_DB_PATH, check_same_thread=False)
        c.execute("""
            CREATE TABLE IF NOT EXISTS signal_history (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp  REAL    NOT NULL,
                asset      TEXT    NOT NULL,
                score      REAL    NOT NULL,
                conviction TEXT,
                top_driver TEXT
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS sh_asset_ts ON signal_history (asset, timestamp)")
        c.commit()
        _local.sh_conn = c
    return _local.sh_conn


def append_history(asset: str, score: float, conviction: str, top_driver: str) -> None:
    """Insert a new score observation and prune the table to _MAX_ROWS."""
    try:
        with _lock:
            c = _conn()
            c.execute(
                "INSERT INTO signal_history (timestamp, asset, score, conviction, top_driver)"
                " VALUES (?, ?, ?, ?, ?)",
                (time.time(), asset, float(score), conviction, top_driver),
            )
            c.execute(
                """DELETE FROM signal_history WHERE id IN (
                       SELECT id FROM signal_history
                       ORDER BY timestamp ASC
                       LIMIT MAX(0, (SELECT COUNT(*) FROM signal_history) - ?)
                   )""",
                (_MAX_ROWS,),
            )
            c.commit()
    except Exception as exc:
        log.debug("append_history %s: %s", asset, exc)


def get_history(asset: str, n: int = 24) -> list:
    """Return the last n scores for asset, in chronological order (oldest first)."""
    try:
        rows = _conn().execute(
            "SELECT score FROM signal_history WHERE asset=?"
            " ORDER BY timestamp DESC LIMIT ?",
            (asset, n),
        ).fetchall()
        scores = [float(r[0]) for r in rows]
        scores.reverse()
        return scores
    except Exception as exc:
        log.debug("get_history %s: %s", asset, exc)
        return []


if __name__ == "__main__":
    append_history("brent", 0.45, "MODERATE", "Inventory")
    append_history("brent", 0.72, "HIGH", "Curve")
    print("brent history:", get_history("brent"))
