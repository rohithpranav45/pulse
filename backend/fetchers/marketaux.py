"""
MarketAux — free-tier financial news API with commodity filters.
===============================================================
Used as a secondary news source alongside GDELT. Free tier = 100 req/day,
no card required. Register: https://www.marketaux.com/

Public API
----------
  get_marketaux_news(limit=20, hours=12) -> dict
    Same envelope as `fetchers.news.get_energy_news`.
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timezone

from datetime import timedelta

import requests

_BACKEND = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from dotenv import load_dotenv
load_dotenv()

log = logging.getLogger("pulse.marketaux")

ENDPOINT = "https://api.marketaux.com/v1/news/all"


def get_marketaux_news(limit: int = 20, hours: int = 12) -> dict:
    """
    Pull commodity-tagged articles from MarketAux. Filters to oil / energy
    industry entities so we don't drown in a generic feed.

    Returns
    -------
    {
      articles:       [{title, url, source, published_at, sentiment_score?}, ...],
      negative_count: int,
      source_used:    "marketaux",
      stale:          bool,
      timestamp:      iso str,
    }
    """
    key = os.getenv("MARKETAUX_KEY", "").strip()
    if not key:
        return {
            "articles": [],
            "negative_count": 0,
            "source_used": "marketaux-no-key",
            "stale": True,
            "error": "MARKETAUX_KEY not configured",
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }

    # MarketAux free tier returns max 3 articles per request, regardless of `limit`.
    # We paginate to get more. Search uses pipe-OR (their docs syntax), NOT parens.
    # Window widened to 36h so we don't run out of fresh items overnight.
    published_after = (datetime.now(timezone.utc) - timedelta(hours=max(hours, 36))).strftime("%Y-%m-%dT%H:%M")
    base_params = {
        "api_token":       key,
        "search":          "oil | crude | Brent | WTI | OPEC | refinery | gasoline | LNG | natgas",
        "language":        "en",
        "limit":           3,                  # free-tier hard cap
        "sort":            "published_desc",
        "published_after": published_after,
    }
    # Pull up to N pages (3 articles each). MarketAux free tier = 100 req/day,
    # so we cap aggressively: 3 pages × 4 fetches/hour × 24h = 288 reqs/day max.
    # On HTTP 402 (usage_limit_reached) we stop immediately and don't retry today.
    max_pages = max(1, min(3, (limit + 2) // 3))
    items: list = []
    last_err: str | None = None
    quota_hit = False
    for page in range(1, max_pages + 1):
        try:
            r = requests.get(ENDPOINT, params={**base_params, "page": page}, timeout=15)
            if r.status_code == 402:
                last_err = "MarketAux daily quota exhausted (HTTP 402)"
                quota_hit = True
                break
            if r.status_code != 200:
                last_err = f"HTTP {r.status_code}: {r.text[:160]}"
                break
            body = r.json()
            chunk = body.get("data", []) or []
            if not chunk:
                break
            items.extend(chunk)
            # Stop early if we've exceeded the requested cap
            if len(items) >= limit:
                break
        except Exception as exc:
            last_err = str(exc)[:160]
            break

    if not items:
        if quota_hit:
            return _stale(last_err)
        if last_err:
            return _stale(last_err)
        return _stale("no articles in window")

    try:
        # English-only filter (defence-in-depth even though we request language=en)
        from fetchers.sentiment import is_english_title
        articles = []
        neg = 0
        for a in items:
            title = a.get("title") or ""
            if not is_english_title(title):
                continue
            entities = a.get("entities") or []
            # MarketAux returns per-entity sentiment_score in [-1, 1]
            scores = [e.get("sentiment_score") for e in entities if e.get("sentiment_score") is not None]
            avg_sent = round(sum(scores) / len(scores), 3) if scores else None
            if avg_sent is not None and avg_sent < -0.15:
                neg += 1
            articles.append({
                "title":            title,
                "headline":         title,
                "url":              a.get("url"),
                "source":           (a.get("source") or "marketaux"),
                "published_at":     a.get("published_at"),
                "published":        a.get("published_at"),
                "snippet":          a.get("snippet"),
                "sentiment_score":  avg_sent,
                "entities":         [{"symbol": e.get("symbol"),
                                      "type":   e.get("type"),
                                      "score":  e.get("sentiment_score")}
                                     for e in entities[:3]],
            })
        return {
            "articles":       articles,
            "negative_count": neg,
            "source_used":    "marketaux",
            "stale":          False,
            "timestamp":      datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
    except Exception as exc:
        log.warning("MarketAux fetch failed: %s", exc)
        return _stale(str(exc)[:160])


def _stale(reason: str) -> dict:
    return {
        "articles": [],
        "negative_count": 0,
        "source_used": "marketaux-error",
        "stale": True,
        "error": reason,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


if __name__ == "__main__":
    import json
    logging.basicConfig(level=logging.INFO)
    r = get_marketaux_news(limit=5)
    print("source:", r["source_used"], "articles:", len(r["articles"]))
    for a in r["articles"][:3]:
        print(f"  [{a.get('sentiment_score'):>+.2f}] {a['source']:<20} {a['title'][:80]}" if a.get('sentiment_score') else f"  [—] {a['source']:<20} {a['title'][:80]}")
