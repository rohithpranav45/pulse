"""
GDELT 2.0 — research-grade news + tone (free, no auth).
=======================================================
Two endpoints:
  • DOC API     — full-text article search with theme/source filters.
  • GKG tone    — Global Knowledge Graph aggregate tone for energy themes,
                  used to feed the geo-risk index.

GDELT enforces a 5-second rate limit per IP — we throttle internally.

Public API
----------
  get_gdelt_news(max_articles=30, hours=12, themes=None) -> dict
      News articles with energy theme filter.

  get_gdelt_tone(themes=("ECON_OILPRICE",), hours=24) -> dict
      Aggregate tone score (negative → bearish/risk-on).

  get_byline_articles(handles=("Javier Blas", "Amena Bakr"), hours=72) -> dict
      Articles authored by named analysts. Replaces the dead Nitter feed.
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import time
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import quote

import requests

_BACKEND = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

log = logging.getLogger("pulse.gdelt")

UA   = "Mozilla/5.0 (compatible; PULSE-Dashboard/1.0; +contact: pulse@local)"
DOC  = "https://api.gdeltproject.org/api/v2/doc/doc"

# Rate-limit lock — GDELT asks for 1 request per 5 seconds.
_lock = threading.Lock()
_last_call = 0.0


def _rate_limited_get(url: str, timeout: int = 20, retries: int = 2) -> Optional[requests.Response]:
    """
    Throttled GET that respects GDELT's 5s rate limit, with automatic retry on
    429 (backoff: 8s, then 15s). Returns the Response on success, None on
    persistent failure.
    """
    global _last_call
    for attempt in range(retries + 1):
        with _lock:
            delay = 5.0 - (time.time() - _last_call)
            if delay > 0:
                time.sleep(delay)
            try:
                r = requests.get(url, headers={"User-Agent": UA}, timeout=timeout)
            except Exception as exc:
                log.warning("GDELT GET failed: %s", exc)
                r = None
            _last_call = time.time()
        if r is not None and r.status_code == 200:
            return r
        if r is not None and r.status_code == 429 and attempt < retries:
            backoff = 8.0 if attempt == 0 else 15.0
            log.info("GDELT 429 — backing off %ss (attempt %d/%d)", backoff, attempt + 1, retries)
            time.sleep(backoff)
            continue
        if r is not None:
            log.warning("GDELT non-200 %s — %s", r.status_code, r.text[:120])
        return None
    return None


# Themes most relevant to oil
ENERGY_THEMES = [
    "ECON_OILPRICE",
    "ENV_OIL",
    "ENV_NATURALGAS",
    "ECON_SHALE",
    "MILITARY",      # supply-disruption signal
    "WB_MENA_ENERGY",
]

# Tighter, oil-only theme set for the impact-model corpus backfill. Drops MILITARY
# and WB_MENA_ENERGY: those pull generic war / regional news (e.g. a Kabul drone
# strike) that the classifier then mislabels GEOPOLITICAL, polluting the corpus
# with non-oil headlines. The remaining four are all directly oil/energy-priced.
OIL_CORPUS_THEMES = [
    "ECON_OILPRICE",
    "ENV_OIL",
    "ENV_NATURALGAS",
    "ECON_SHALE",
]


def get_gdelt_news(
    max_articles: int = 30,
    hours: int = 12,
    extra_query: str = "",
) -> dict:
    """
    Pull recent oil-related articles via the DOC API.
    Returns the same shape as `fetchers.news.get_energy_news` so the
    consumer doesn't have to branch.
    """
    # Theme filter — articles tagged ECON_OILPRICE OR any of the others.
    # English-only via sourcelang filter; FinBERT downstream is English-only too.
    theme_q = " OR ".join(f'theme:{t}' for t in ENERGY_THEMES)
    query = f"({theme_q}) sourcelang:english"
    if extra_query:
        query = f"({query}) AND ({extra_query})"

    url = (
        f"{DOC}?query={quote(query)}"
        f"&mode=artlist&maxrecords={max_articles}"
        f"&timespan={hours}h&format=json&sort=DateDesc"
    )
    r = _rate_limited_get(url)
    if r is None:
        return {
            "articles": [],
            "negative_count": 0,
            "source_used": "gdelt-unavailable",
            "stale": True,
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }

    try:
        body = r.json()
    except Exception:
        return {"articles": [], "negative_count": 0, "source_used": "gdelt-parse-error",
                "stale": True, "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds")}

    items = body.get("articles", []) or []
    out = []
    for a in items:
        title = a.get("title") or ""
        out.append({
            "headline":     title,
            "title":        title,
            "url":          a.get("url"),
            "source":       a.get("domain"),
            "published_at": a.get("seendate"),
            "published":    a.get("seendate"),
            "language":     a.get("language"),
            "tone":         a.get("tone"),  # may be None on DOC mode
        })

    # Crude negativity heuristic — kept compatible with prior news fetcher
    neg_keywords = ("attack", "strike", "sanction", "outage", "halt",
                    "shutdown", "drone", "missile", "embargo", "war")
    neg_count = sum(
        1 for a in out
        if any(k in (a["title"] or "").lower() for k in neg_keywords)
    )

    return {
        "articles":       out,
        "negative_count": neg_count,
        "source_used":    "gdelt",
        "stale":          False,
        "timestamp":      datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def get_gdelt_articles_between(
    start: datetime,
    end: datetime,
    max_articles: int = 250,
    themes=None,
    extra_query: str = "",
) -> dict:
    """
    Historical DOC-API pull over an explicit [start, end) datetime window.

    Unlike `get_gdelt_news` (which uses `timespan` = "last N hours"), this uses
    GDELT's `startdatetime`/`enddatetime` parameters so we can backfill a
    timestamped headline corpus for the event study. GDELT DOC 2.0 indexes
    full-text articles from ~2017 onward; windows before that return empty.

    Both datetimes are coerced to UTC and formatted YYYYMMDDHHMMSS. Returns the
    same article shape as `get_gdelt_news` (`articles` carry `published_at` as
    the GDELT `seendate`). Caller is responsible for windowing/paging the range.
    """
    if themes is None:
        themes = ENERGY_THEMES

    def _fmt(dt: datetime) -> str:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).strftime("%Y%m%d%H%M%S")

    theme_q = " OR ".join(f"theme:{t}" for t in themes)
    query = f"({theme_q}) sourcelang:english"
    if extra_query:
        query = f"({query}) AND ({extra_query})"

    url = (
        f"{DOC}?query={quote(query)}"
        f"&mode=artlist&maxrecords={max_articles}"
        f"&startdatetime={_fmt(start)}&enddatetime={_fmt(end)}"
        f"&format=json&sort=DateDesc"
    )
    r = _rate_limited_get(url)
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if r is None:
        return {"articles": [], "source_used": "gdelt-unavailable", "stale": True, "timestamp": ts}
    try:
        body = r.json()
    except Exception:
        return {"articles": [], "source_used": "gdelt-parse-error", "stale": True, "timestamp": ts}

    out = []
    for a in body.get("articles", []) or []:
        title = a.get("title") or ""
        out.append({
            "headline":     title,
            "title":        title,
            "url":          a.get("url"),
            "source":       a.get("domain"),
            "published_at": a.get("seendate"),
            "published":    a.get("seendate"),
            "language":     a.get("language"),
        })
    return {"articles": out, "source_used": "gdelt", "stale": False, "timestamp": ts}


def get_gdelt_tone(themes=("ECON_OILPRICE",), hours: int = 24) -> dict:
    """
    GDELT aggregate tone for given themes. Uses `tonechart` mode (artlist
    doesn't return tone field). Returns mean weighted tone over the period —
    negative = crisis/anxiety in coverage, bullish for oil risk premium.
    """
    theme_q = " OR ".join(f'theme:{t}' for t in themes)
    url = (
        f"{DOC}?query={quote(theme_q)}"
        f"&mode=tonechart&timespan={hours}h&format=json"
    )
    r = _rate_limited_get(url)
    if r is not None:
        try:
            body = r.json()
            bins = body.get("tonechart", []) or []
            total    = sum(int(b.get("count", 0)) for b in bins)
            weighted = sum(float(b.get("bin", 0)) * int(b.get("count", 0)) for b in bins)
            if total:
                mean = round(weighted / total, 3)
                bins_sorted = sorted(bins, key=lambda b: float(b.get("bin", 0)))
                return {
                    "mean_tone":  mean,
                    "min_bin":    float(bins_sorted[0].get("bin", 0)) if bins_sorted else None,
                    "max_bin":    float(bins_sorted[-1].get("bin", 0)) if bins_sorted else None,
                    "n":          total,
                    "n_bins":     len(bins),
                    "themes":     list(themes),
                    "hours":      hours,
                    "mode":       "tonechart",
                    "stale":      False,
                    "timestamp":  datetime.now(timezone.utc).isoformat(timespec="seconds"),
                }
        except Exception as exc:
            log.warning("tonechart parse failed: %s", exc)

    return {"mean_tone": None, "n": 0, "stale": True,
            "themes": list(themes), "hours": hours,
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds")}


def get_byline_articles(handles=("Javier Blas", "Amena Bakr"), hours: int = 72) -> dict:
    """
    Returns articles authored by named analysts. Uses GDELT full-text search
    for the author's name in quotes — works well for distinctive names.
    Replaces the dead Nitter feed.
    """
    out_by_author = []
    for name in handles:
        query = f'"{name}"'
        url = (
            f"{DOC}?query={quote(query)}"
            f"&mode=artlist&maxrecords=10&timespan={hours}h"
            f"&sort=DateDesc&format=json"
        )
        r = _rate_limited_get(url)
        items = []
        if r is not None:
            try:
                body = r.json()
                for a in body.get("articles", []) or []:
                    items.append({
                        "url":       a.get("url"),
                        "title":     a.get("title"),
                        "domain":    a.get("domain"),
                        "published": a.get("seendate"),
                    })
            except Exception as exc:
                log.warning("byline parse for %s: %s", name, exc)
        out_by_author.append({
            "name":  name,
            "handle": name.replace(" ", "").lower(),
            "org":   "via GDELT byline search",
            "posts": items[:5],
            "ok":    bool(items),
            "fallback_note": None if items else "no articles in past window",
        })
    return {
        "analysts":  out_by_author,
        "source":    "GDELT DOC API byline search",
        "stale":     False,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


if __name__ == "__main__":
    import json
    logging.basicConfig(level=logging.INFO)
    print("=== news ===")
    n = get_gdelt_news(max_articles=5, hours=24)
    print("source:", n["source_used"], "articles:", len(n["articles"]), "neg:", n["negative_count"])
    for a in n["articles"][:3]:
        print(f"  {a['source']:<25} {a['headline'][:80]}")
    print("\n=== tone ===")
    print(json.dumps(get_gdelt_tone(), indent=2))
    print("\n=== bylines ===")
    b = get_byline_articles()
    for a in b["analysts"]:
        print(f"  {a['name']:<15} {len(a['posts'])} posts  ok={a['ok']}")
