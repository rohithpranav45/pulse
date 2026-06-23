"""
News corpus — the timestamped headline tape behind the impact model.
====================================================================

Persists every oil-news headline (live fetches + a GDELT historical backfill)
into the ``news_history`` table in the shared ``pulse_cache.db``, deduplicated by
URL. This is the corpus the event study fits its per-factor betas on — so it must
carry a clean ``published_at`` timestamp we can align to the Brent/WTI tape.

Why a backfill: headlines were never persisted before (live-only fetches), so the
event study has a cold start. GDELT DOC 2.0 indexes full-text articles from ~2017
onward; ``backfill_gdelt`` pages the date range in windows to build ~years of
history in one pass. Live persistence (``upsert_articles`` called from the news
fetcher / scheduler) then grows it continuously.

Public API
----------
    ensure_schema()
    upsert_articles(articles)            -> int     (new rows inserted)
    backfill_gdelt(start, end, ...)      -> dict     (windowed historical pull)
    recent(limit, factor=, since=)       -> list[dict]
    unclassified(limit)                  -> list[dict]
    set_classification(url, factor, conf)
    set_sentiment(url, score)
    stats()                              -> dict
"""

from __future__ import annotations

import os
import sqlite3
import threading
import time
import logging
from datetime import datetime, timezone, timedelta

log = logging.getLogger("pulse.news_impact.corpus")

# Share pulse_cache.db with the rest of the app, but allow tests to point at a
# throwaway DB via PULSE_NEWS_DB so they never touch the live corpus.
_DEFAULT_DB = os.path.join(
    os.path.abspath(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
    "db", "pulse_cache.db",
)
_write_lock = threading.Lock()
_local = threading.local()


def _db_path() -> str:
    return os.getenv("PULSE_NEWS_DB", _DEFAULT_DB)


def _apply_pragmas(c: sqlite3.Connection) -> None:
    # Mirror db/cache.py — WAL + busy_timeout so the corpus coexists with the
    # paper book / A/B writer on the same file.
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA busy_timeout=5000")
    c.execute("PRAGMA synchronous=NORMAL")


def _conn() -> sqlite3.Connection:
    """Thread-local connection to the active DB path (re-opens if the path changed)."""
    path = _db_path()
    if getattr(_local, "path", None) != path or not hasattr(_local, "conn"):
        try:
            if hasattr(_local, "conn"):
                _local.conn.close()
        except Exception:
            pass
        c = sqlite3.connect(path, check_same_thread=False)
        _apply_pragmas(c)
        _local.conn = c
        _local.path = path
        _ensure_schema(c)
    return _local.conn


def _ensure_schema(c: sqlite3.Connection) -> None:
    c.execute("""
        CREATE TABLE IF NOT EXISTS news_history (
            url           TEXT PRIMARY KEY,
            title         TEXT NOT NULL,
            source        TEXT,
            published_at  TEXT,           -- ISO-8601 UTC
            factor        TEXT,           -- NULL until classified
            factor_conf   REAL,
            sentiment     REAL,           -- FinBERT scalar [-1,+1], NULL until scored
            classified_at TEXT,
            ingested_at   REAL NOT NULL
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_news_published ON news_history(published_at)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_news_factor ON news_history(factor)")
    c.commit()


def ensure_schema() -> None:
    _ensure_schema(_conn())


def _reset_conn_for_test() -> None:
    """Drop the cached thread-local connection (tests flip PULSE_NEWS_DB)."""
    try:
        if hasattr(_local, "conn"):
            _local.conn.close()
    except Exception:
        pass
    for attr in ("conn", "path"):
        if hasattr(_local, attr):
            delattr(_local, attr)


# ── timestamp normalisation ───────────────────────────────────────────────────

def _norm_ts(raw) -> str | None:
    """
    Normalise a published timestamp to ISO-8601 UTC. Accepts GDELT's compact
    ``YYYYMMDDTHHMMSSZ`` seendate, plain ISO strings, and ``Xh ago`` is rejected
    (no absolute time). Returns None when unparseable.
    """
    if not raw:
        return None
    s = str(raw).strip()
    # GDELT seendate: 20260525T103000Z  (or without separators)
    digits = s.replace("T", "").replace("Z", "").replace("-", "").replace(":", "")
    if len(digits) == 14 and digits.isdigit():
        try:
            dt = datetime.strptime(digits, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
            return dt.isoformat(timespec="seconds")
        except ValueError:
            pass
    if "T" in s:
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).isoformat(timespec="seconds")
        except ValueError:
            pass
    return None


# ── writes ────────────────────────────────────────────────────────────────────

def upsert_articles(articles: list) -> int:
    """
    Insert any new headlines (dedup on URL — first write wins, so a later live
    re-fetch never clobbers a classification). Returns the count of NEW rows.
    Articles missing a URL or title are skipped; missing timestamps are kept
    (NULL published_at) but excluded from the event study downstream.
    """
    if not articles:
        return 0
    rows = []
    now = time.time()
    for a in articles:
        url = (a.get("url") or "").strip()
        title = (a.get("title") or a.get("headline") or "").strip()
        if not url or not title:
            continue
        ts = _norm_ts(a.get("published_at") or a.get("published") or a.get("seendate"))
        src = a.get("source") or a.get("domain")
        rows.append((url, title, src, ts, now))
    if not rows:
        return 0
    with _write_lock:
        c = _conn()
        before = c.total_changes
        c.executemany(
            "INSERT OR IGNORE INTO news_history "
            "(url, title, source, published_at, ingested_at) VALUES (?,?,?,?,?)",
            rows,
        )
        c.commit()
        return c.total_changes - before


def set_classification(url: str, factor: str, conf: float) -> None:
    with _write_lock:
        c = _conn()
        c.execute(
            "UPDATE news_history SET factor=?, factor_conf=?, classified_at=? WHERE url=?",
            (factor, float(conf), datetime.now(timezone.utc).isoformat(timespec="seconds"), url),
        )
        c.commit()


def set_sentiment(url: str, score: float) -> None:
    with _write_lock:
        c = _conn()
        c.execute("UPDATE news_history SET sentiment=? WHERE url=?", (float(score), url))
        c.commit()


# ── reads ─────────────────────────────────────────────────────────────────────

def _row_to_dict(r) -> dict:
    return {
        "url": r[0], "title": r[1], "source": r[2], "published_at": r[3],
        "factor": r[4], "factor_conf": r[5], "sentiment": r[6],
        "classified_at": r[7],
    }


_COLS = "url, title, source, published_at, factor, factor_conf, sentiment, classified_at"


def recent(limit: int = 100, factor: str | None = None, since: str | None = None) -> list:
    """Most-recent headlines first (by published_at, NULLs last). Optional factor / since filter."""
    q = f"SELECT {_COLS} FROM news_history"
    cond, args = [], []
    if factor:
        cond.append("factor = ?"); args.append(factor)
    if since:
        cond.append("published_at >= ?"); args.append(since)
    if cond:
        q += " WHERE " + " AND ".join(cond)
    q += " ORDER BY published_at IS NULL, published_at DESC LIMIT ?"
    args.append(int(limit))
    return [_row_to_dict(r) for r in _conn().execute(q, args).fetchall()]


def unclassified(limit: int = 200) -> list:
    """Headlines with no factor yet — the classifier's work queue (newest first)."""
    q = (f"SELECT {_COLS} FROM news_history WHERE factor IS NULL "
         f"ORDER BY published_at IS NULL, published_at DESC LIMIT ?")
    return [_row_to_dict(r) for r in _conn().execute(q, (int(limit),)).fetchall()]


def stats() -> dict:
    c = _conn()
    total = c.execute("SELECT COUNT(*) FROM news_history").fetchone()[0]
    classified = c.execute("SELECT COUNT(*) FROM news_history WHERE factor IS NOT NULL").fetchone()[0]
    with_ts = c.execute("SELECT COUNT(*) FROM news_history WHERE published_at IS NOT NULL").fetchone()[0]
    span = c.execute(
        "SELECT MIN(published_at), MAX(published_at) FROM news_history WHERE published_at IS NOT NULL"
    ).fetchone()
    by_factor = dict(c.execute(
        "SELECT factor, COUNT(*) FROM news_history WHERE factor IS NOT NULL GROUP BY factor"
    ).fetchall())
    return {
        "total": total,
        "classified": classified,
        "with_timestamp": with_ts,
        "span": [span[0], span[1]] if span and span[0] else None,
        "by_factor": by_factor,
    }


# ── historical backfill ───────────────────────────────────────────────────────

def backfill_gdelt(
    start: datetime,
    end: datetime | None = None,
    *,
    window_days: int = 7,
    max_per_window: int = 250,
    sleep_between: float = 0.0,
    fetch_fn=None,
) -> dict:
    """
    Page the GDELT DOC API across [start, end) in ``window_days`` windows,
    upserting every article. GDELT throttles to ~1 req / 5 s (handled inside the
    fetcher), so a multi-year backfill takes a while — run it as a one-off.

    ``fetch_fn`` defaults to the live GDELT fetcher; tests inject a synthetic one
    to stay hermetic. Returns a summary: windows pulled, articles seen, NEW rows
    inserted, and any windows that came back empty/unavailable.
    """
    if fetch_fn is None:
        from fetchers.gdelt import get_gdelt_articles_between as fetch_fn

    if end is None:
        end = datetime.now(timezone.utc)
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)

    windows = 0
    seen = 0
    inserted = 0
    empty = 0
    cur = start
    step = timedelta(days=window_days)
    while cur < end:
        nxt = min(cur + step, end)
        try:
            res = fetch_fn(cur, nxt, max_articles=max_per_window)
            arts = res.get("articles", []) or []
            seen += len(arts)
            inserted += upsert_articles(arts)
            if not arts:
                empty += 1
        except Exception as exc:
            log.warning("backfill window %s..%s failed: %s", cur.date(), nxt.date(), exc)
            empty += 1
        windows += 1
        if sleep_between:
            time.sleep(sleep_between)
        cur = nxt

    return {
        "windows": windows,
        "articles_seen": seen,
        "rows_inserted": inserted,
        "empty_windows": empty,
        "range": [start.isoformat(timespec="seconds"), end.isoformat(timespec="seconds")],
    }
