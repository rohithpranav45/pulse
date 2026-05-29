"""
RSS-based news fallback — no API keys, no scraping, just feeds.
Used when both Apify (Financial Juice) and NewsAPI fail.

Sources:
  - Google News topic searches (free, no auth, returns BBC/Reuters/Bloomberg etc.)
  - Yahoo Finance commodity headlines

Returns the same `articles` shape as get_energy_news() so the frontend just
sees more news rather than less.
"""
from __future__ import annotations

import logging
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

log = logging.getLogger("pulse.rss")

# Google News RSS query URLs. Each returns ~100 recent headlines.
_GOOGLE_NEWS_FMT = (
    "https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
)

_QUERIES = [
    "crude oil price OPEC",
    "natural gas LNG market",
    "Brent WTI oil supply",
    "energy market refinery crack spread",
    "Iran Russia oil sanctions",
]

_USER_AGENT = "Mozilla/5.0 (compatible; PulseEnergy/1.0; +https://pulse.local)"


def _fetch_rss(url: str, timeout: int = 8) -> list[dict]:
    """Fetch + parse an RSS 2.0 feed, return normalized article dicts."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except Exception as exc:
        log.debug("rss fetch failed for %s: %s", url[:80], exc)
        return []

    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        log.debug("rss parse failed: %s", exc)
        return []

    items = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub = (item.findtext("pubDate") or "").strip()
        desc = (item.findtext("description") or "").strip()
        source_el = item.find("source")
        source = source_el.text.strip() if (source_el is not None and source_el.text) else "Google News"

        if not title:
            continue

        # Parse date → ISO + relative
        published_iso = None
        published_ago = ""
        try:
            dt = parsedate_to_datetime(pub)
            if dt is not None:
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                published_iso = dt.astimezone(timezone.utc).isoformat(timespec="seconds")
                age_s = max(0, (datetime.now(timezone.utc) - dt).total_seconds())
                if age_s < 3600:
                    published_ago = f"{int(age_s / 60)}m"
                elif age_s < 86400:
                    published_ago = f"{int(age_s / 3600)}h"
                else:
                    published_ago = f"{int(age_s / 86400)}d"
        except Exception:
            pass

        items.append({
            "title": title,
            "headline": title,
            "url": link,
            "source": source,
            "published": published_iso or "",
            "published_at": published_iso or "",
            "published_ago": published_ago,
            "time": published_ago or "now",
            "description": desc[:300],
        })
    return items


def fetch_rss_news(max_articles: int = 20) -> list[dict]:
    """
    Fetch energy news from Google News RSS — no key required.
    Returns deduplicated list of articles, freshest first.
    """
    seen_titles: set[str] = set()
    all_items: list[dict] = []

    for q in _QUERIES:
        encoded = urllib.parse.quote_plus(q)
        items = _fetch_rss(_GOOGLE_NEWS_FMT.format(q=encoded))
        for it in items:
            key = it["title"].lower()[:120]
            if key in seen_titles:
                continue
            seen_titles.add(key)
            all_items.append(it)

    # Sort by recency: items with a parsed timestamp first, freshest first
    def _sort_key(it):
        return it.get("published") or ""
    all_items.sort(key=_sort_key, reverse=True)

    return all_items[:max_articles]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    articles = fetch_rss_news(20)
    print(f"Got {len(articles)} articles")
    for a in articles[:8]:
        print(f"  [{a['time']:>4}] {a['source'][:18]:<18} {a['title'][:80]}")
