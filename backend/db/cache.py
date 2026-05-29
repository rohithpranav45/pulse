"""
SQLite-backed TTL cache — drop-in replacement for in-memory cache in app.py.

Schema: cache(key TEXT PRIMARY KEY, value_json TEXT, updated_at REAL)
DB:     pulse/backend/db/pulse_cache.db

get_cached(key, ttl) -> dict|None
    Returns None only when the key was never set.
    Returns value with stale=True merged in when the entry is expired.

set_cache(key, value)
    Serialises value to JSON and upserts the row.
"""

import json
import os
import sqlite3
import threading
import time
import logging

log = logging.getLogger("pulse.cache")

_DB_PATH = os.path.join(os.path.abspath(os.path.dirname(__file__)), "pulse_cache.db")
_write_lock = threading.Lock()
_local = threading.local()


def _conn() -> sqlite3.Connection:
    """Return a thread-local SQLite connection, creating the table on first use."""
    if not hasattr(_local, "conn"):
        c = sqlite3.connect(_DB_PATH, check_same_thread=False)
        c.execute("""
            CREATE TABLE IF NOT EXISTS cache (
                key        TEXT PRIMARY KEY,
                value_json TEXT,
                updated_at REAL
            )
        """)
        c.commit()
        _local.conn = c
    return _local.conn


def get_cached(key: str, ttl_seconds: int):
    """
    Return the cached value if it is younger than ttl_seconds.
    If the entry is expired, return it anyway with {"stale": True} merged in —
    stale data is always preferred over a crash or an empty response.
    Returns None only when the key has never been written.
    """
    try:
        row = _conn().execute(
            "SELECT value_json, updated_at FROM cache WHERE key=?", (key,)
        ).fetchone()
    except Exception as exc:
        log.warning("cache read %s: %s", key, exc)
        return None

    if row is None:
        return None

    try:
        value = json.loads(row[0])
    except Exception:
        return None

    if time.time() - row[1] < ttl_seconds:
        return value

    if isinstance(value, dict):
        value = {**value, "stale": True}
    return value


def set_cache(key: str, value) -> None:
    """Serialise value to JSON and upsert the cache row."""
    try:
        blob = json.dumps(value, default=str)
        with _write_lock:
            c = _conn()
            c.execute(
                "INSERT OR REPLACE INTO cache (key, value_json, updated_at) VALUES (?,?,?)",
                (key, blob, time.time()),
            )
            c.commit()
    except Exception as exc:
        log.warning("cache write %s: %s", key, exc)
