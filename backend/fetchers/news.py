"""
Energy news fetcher — NewsAPI + Financial Juice (Apify) with fallback.
Primary:  fetch_from_financialjuice() via Apify web-scraper actor
Fallback: fetch_news() via NewsAPI

Public API:
  is_negative(headline)        — True if headline contains a risk keyword
  fetch_from_financialjuice()  — Apify scrape; returns [] on any failure
  get_energy_news()            — primary + fallback; adds is_negative flag
"""

import os
import time
from datetime import datetime, timezone, timedelta

import requests
from dotenv import load_dotenv

load_dotenv()

def _batch_score(texts: list) -> list:
    """Batch-score headlines via FinBERT; returns 0.0 per item on any failure."""
    try:
        from fetchers.sentiment import batch_score
        return batch_score(texts)
    except Exception:
        return [0.0] * len(texts)


def _aggregate(articles: list) -> dict:
    """Return aggregate sentiment dict over article list."""
    try:
        from fetchers.sentiment import aggregate_sentiment
        return aggregate_sentiment(articles)
    except Exception:
        return {"composite": 0.0, "count": 0,
                "bullish": 0, "bearish": 0, "neutral": 0, "label": "NEUTRAL"}

# ── Module-level cache ──────────────────────────────────────────────────────
# Short TTL: we serve from cache to avoid hammering RSS endpoints / Apify,
# but keep the window tight enough that "latest news" actually means latest.
_news_cache      = None
_news_cache_time = None
_NEWS_CACHE_TTL  = 180  # 3 minutes

# Per-source timeouts (seconds). Fail-fast so a slow source can't block the
# whole news endpoint — the others fill in.
# Apify FJ is intentionally tight (10s): Financial Juice moved their squawk
# behind authentication so the scrape now returns zero, but we keep the slot
# in case they restore the public feed. Real freshness comes from the direct
# energy RSS sources (OilPrice / Rigzone / Hellenic), which return minutes-old
# headlines and complete in ~2 s.
_TIMEOUT_FJ      = 8
_TIMEOUT_NEWSAPI = 8
_TIMEOUT_RSS     = 10
_TIMEOUT_DIRECT  = 12   # OilPrice + Rigzone + Hellenic, fetched in parallel

NEWS_KEY  = os.getenv("NEWSAPI_KEY")
BASE_URL  = "https://newsapi.org/v2/everything"

# ── Geopolitical / risk headline keywords ─────────────────────────────────────
NEGATIVE_KEYWORDS = [
    "war", "conflict", "sanctions", "attack",
    "shutdown", "disruption", "explosion", "crisis",
    "threat", "strike", "blockade", "invasion",
    "missile", "seizure", "embargo", "riot",
    "violence", "collapse", "emergency",
]

# Article must contain at least one of these to pass relevance gate
# Use multi-word / specific terms to prevent false matches on "oil" or "gas" alone
RELEVANCE_TERMS = [
    "crude oil", "oil price", "oil market", "oil supply", "oil demand",
    "oil production", "oil inventory", "oil stock", "oil output", "oil barrel",
    "brent", "wti crude", "light sweet",
    "natural gas", "lng ", "henry hub", "gas storage", "gas supply",
    "opec", "petroleum",
    "gasoline price", "gasoline supply", "rbob",
    "refinery", "refining margin", "crack spread",
    "heating oil", "ulsd", "distillate fuel",
    "energy market", "energy price", "energy supply",
    "shale oil", "rig count", "oil pipeline",
    "oil sanction", "production cut", "iran oil", "russia oil",
    "hormuz", "oil tanker",
]

# Ordered list of (category_tag, keywords_to_match_in_title_or_description)
# First matching category wins.
CATEGORIES = [
    ("OPEC",       ["opec", "opec+", "saudi arabia", "production cut", "output cut"]),
    ("GEO",        ["russia", "iran", "ukraine", "sanction", "middle east",
                    "geopolit", "houthi", "israel", "war", "conflict"]),
    ("GAS",        ["natural gas", "lng", "henry hub", "gas storage",
                    "liquefied natural gas", "gas price"]),
    ("REFINERY",   ["refin", "gasoline", "distillate", "crack spread",
                    "fuel supply", "heating oil"]),
    ("MACRO",      ["federal reserve", "fed rate", "inflation", "cpi",
                    "gdp", "interest rate", "dollar index", "dxy", "recession"]),
    ("CRUDE",      ["crude", "brent", "wti", "barrel", "oil price",
                    "petroleum", "oil market"]),
    ("ENERGY",     ["energy", "opec", "pipeline", "offshore", "shale",
                    "rig count", "drill"]),
]

# Targeted query strings — specific enough to avoid lifestyle/non-energy noise
QUERIES = [
    '"crude oil" OR "oil price" OR OPEC OR Brent OR WTI',
    '"natural gas" OR LNG OR "Henry Hub" OR "gas storage"',
    '"oil market" OR "oil supply" OR "oil demand" OR "oil production"',
    'refinery OR "heating oil" OR ULSD OR "crack spread"',
    '"OPEC+" OR "production cut" OR "oil sanction" OR "Iran oil" OR "Russia oil"',
]


def _tag(title: str, description: str) -> str:
    """Assign the first matching category tag."""
    text = (title + " " + (description or "")).lower()
    for tag, keywords in CATEGORIES:
        if any(kw in text for kw in keywords):
            return tag
    return "ENERGY"


def _fetch_query(query: str, page_size: int = 10) -> list[dict]:
    """Hit NewsAPI and return raw articles list."""
    if not NEWS_KEY:
        raise EnvironmentError("NEWSAPI_KEY not set in .env")

    r = requests.get(
        BASE_URL,
        params={
            "q":        query,
            "apiKey":   NEWS_KEY,
            "pageSize": page_size,
            "language": "en",
            "sortBy":   "publishedAt",
        },
        timeout=15,
    )
    r.raise_for_status()
    data = r.json()
    if data.get("status") != "ok":
        raise RuntimeError(f"NewsAPI error: {data.get('message')}")
    return data.get("articles", [])


def fetch_news(top_n: int = 10) -> list[dict]:
    """
    Fetch energy news, deduplicate, tag, and return top_n by recency.

    Returns
    -------
    [
      {
        "title":       "...",
        "source":      "Reuters",
        "url":         "https://...",
        "published":   "2026-05-25T10:30:00Z",
        "published_ago": "3h ago",
        "category":    "CRUDE",
        "description": "...",
      },
      ...
    ]
    """
    seen_urls = set()
    pool      = []

    for query in QUERIES:
        try:
            articles = _fetch_query(query, page_size=15)
            for a in articles:
                url = a.get("url", "")
                if not url or url in seen_urls:
                    continue

                # Relevance gate — drop articles with no energy signal
                combined_text = (
                    (a.get("title") or "") + " " + (a.get("description") or "")
                ).lower()
                if not any(term in combined_text for term in RELEVANCE_TERMS):
                    continue

                seen_urls.add(url)

                published = a.get("publishedAt", "")
                pool.append({
                    "title":       a.get("title", "").strip(),
                    "source":      a.get("source", {}).get("name", "Unknown"),
                    "url":         url,
                    "published":   published,
                    "description": a.get("description", "") or "",
                    "category":    _tag(a.get("title", ""),
                                        a.get("description", "")),
                })
        except Exception as exc:
            print(f"  [warn] query failed: {exc}")
            continue

    # Sort newest first
    def _ts(article):
        try:
            return datetime.fromisoformat(
                article["published"].replace("Z", "+00:00"))
        except Exception:
            return datetime.min.replace(tzinfo=timezone.utc)

    pool.sort(key=_ts, reverse=True)

    # Add human-readable "X ago" label
    now = datetime.now(timezone.utc)
    for a in pool:
        try:
            dt  = _ts(a)
            diff = now - dt
            mins = int(diff.total_seconds() / 60)
            if mins < 60:
                a["published_ago"] = f"{mins}m ago"
            elif mins < 1440:
                a["published_ago"] = f"{mins // 60}h ago"
            else:
                a["published_ago"] = f"{mins // 1440}d ago"
        except Exception:
            a["published_ago"] = "N/A"

    return pool[:top_n]


def is_negative(headline: str) -> bool:
    """
    Return True if the headline contains any word from NEGATIVE_KEYWORDS.

    Parameters
    ----------
    headline : str  — article title or any short text

    Returns
    -------
    bool
    """
    text = headline.lower()
    return any(kw in text for kw in NEGATIVE_KEYWORDS)


def fetch_from_financialjuice() -> list[dict]:
    """
    Scrape Financial Juice energy headlines via the Apify web-scraper actor.

    Uses the APIFY_API_KEY from .env.
    Filters scraped text against RELEVANCE_TERMS so only energy items pass.

    Returns
    -------
    list[dict]  — [{headline, time, source, category}, ...]
                  Empty list [] on any failure (caller falls back to NewsAPI).
    """
    try:
        from apify_client import ApifyClient

        api_key = os.getenv("APIFY_API_TOKEN")
        if not api_key:
            return []

        client = ApifyClient(api_key)

        # apify/web-scraper requires a pageFunction that runs inside the browser.
        # This function pulls every non-empty text node from the feed page,
        # deduplicates, and returns items between 30-300 chars (headline length).
        run_input = {
            "startUrls": [{"url": "https://financialjuice.com/feed"}],
            "maxCrawlPages": 1,
            "maxCrawlDepth": 0,
            "maxRequestsPerCrawl": 1,
            # Apify web-scraper v3 injects jQuery into the browser page and
            # exposes it as context.jQuery (not context.$).
            # nodeType === 3 is the browser-DOM standard for text nodes
            # (Cheerio's type==='text' does NOT work here — this is live DOM).
            # waitFor(10s) lets the Angular app finish rendering before we walk.
            # The code/script guard drops obvious JS fragments so only
            # human-readable strings reach the Python relevance filter.
            "pageFunction": """
                async function pageFunction(context) {
                    const { jQuery, request, waitFor } = context;

                    await waitFor(10000);

                    const CODE_RE = /[{};]|function |var |const |let |\\$\\(|<iframe/;
                    const seen    = new Set();
                    const items   = [];

                    jQuery('*').each((i, el) => {
                        const ownText = jQuery(el)
                            .contents()
                            .filter((j, node) => node.nodeType === 3)
                            .text()
                            .trim();

                        if (ownText.length >= 30
                                && ownText.length <= 300
                                && !seen.has(ownText)
                                && !CODE_RE.test(ownText)) {
                            seen.add(ownText);
                            items.push({
                                headline:  ownText,
                                url:       request.url,
                                timestamp: new Date().toISOString(),
                            });
                        }
                    });

                    return items.slice(0, 150);
                }
            """,
        }

        run = client.actor("apify/web-scraper").call(
            run_input=run_input,
            run_timeout=timedelta(seconds=60),  # max 60 s — don't block forever
            memory_mbytes=512,                  # 256 caused page crashes on Puppeteer
        )

        # apify_client v1 returns a plain dict; v2+ returns a Run object.
        dataset_id = (
            run["defaultDatasetId"] if isinstance(run, dict)
            else run.default_dataset_id
        )
        items = list(client.dataset(dataset_id).iterate_items())

        results = []
        seen    = set()

        for item in items:
            # pageFunction stores headline directly; keep legacy fallback keys too
            text = (
                item.get("headline") or
                item.get("text")     or
                item.get("title")    or
                item.get("pageTitle") or ""
            ).strip()

            if not text or text in seen:
                continue

            text_lower = text.lower()
            if not any(term in text_lower for term in RELEVANCE_TERMS):
                continue

            seen.add(text)
            results.append({
                "headline": text,
                "time":     item.get("loadedTime") or item.get("timestamp") or "N/A",
                "source":   "Financial Juice",
                "category": _tag(text, ""),
            })

        return results

    except Exception as exc:
        print(f"  [warn] Financial Juice / Apify: {exc}")
        return []


# ── News Clustering ───────────────────────────────────────────────────────────
# 4-theme keyword scoring — no ML, pure token matching.
# Each article is scored against every theme; assigned to highest-scoring theme.

_CLUSTER_KEYWORDS: dict[str, list[str]] = {
    "Supply / Geopolitical": [
        "supply", "disruption", "pipeline", "russia", "iran", "ukraine",
        "sanction", "houthi", "attack", "tanker", "hormuz", "blockade",
        "conflict", "war", "strike", "militia", "vessel", "shutdown",
        "outage", "rig count", "shale", "offshore", "refinery fire",
        "hurricane", "force majeure", "embargo", "seizure",
    ],
    "Demand Outlook": [
        "demand", "consumption", "growth", "china", "india", "asia",
        "economy", "gdp", "slowdown", "recession", "ev", "electric vehicle",
        "jet fuel", "aviation", "driving season", "travel", "industrial",
        "manufacturing", "iea forecast", "outlook", "inventory draw",
        "summer demand", "winter heating",
    ],
    "OPEC+ Production": [
        "opec", "opec+", "saudi", "aramco", "production cut", "output cut",
        "quota", "compliance", "barrels per day", "mbd", "spare capacity",
        "voluntary cut", "output increase", "production hike", "barkindo",
        "uae", "iraq", "kuwait", "nigeria", "algeria", "kazakhstan",
        "supply cut", "crude output", "production target",
    ],
    "Macro / Dollar": [
        "dollar", "dxy", "federal reserve", "fed", "interest rate",
        "inflation", "cpi", "yield", "bond", "treasury", "rate hike",
        "rate cut", "monetary", "fomc", "powell", "ecb", "currency",
        "usd", "risk off", "risk on", "equity", "stock market",
        "recession", "gdp growth", "economic data",
    ],
}

_CLUSTER_ORDER = [
    "OPEC+ Production",
    "Supply / Geopolitical",
    "Demand Outlook",
    "Macro / Dollar",
]


def _score_article(text: str, keywords: list[str]) -> int:
    """Count how many keywords appear in text (case-insensitive)."""
    tl = text.lower()
    return sum(1 for kw in keywords if kw in tl)


def _cluster_articles(articles: list[dict]) -> dict[str, list[dict]]:
    """
    Group articles into the 4 market themes using keyword scoring.

    Each article is scored against all 4 theme keyword sets; it is
    assigned to the highest-scoring theme.  Ties go to the first theme
    in _CLUSTER_ORDER.  Articles with zero score on all themes are
    assigned to 'Supply / Geopolitical' as default.

    Returns
    -------
    {theme_label: [articles]} — preserving original article dicts.
    Themes with no articles are included as empty lists.
    """
    buckets: dict[str, list] = {t: [] for t in _CLUSTER_ORDER}

    for art in articles:
        text = (art.get("headline") or art.get("title") or "") + " " + (
            art.get("description") or ""
        )
        best_theme = _CLUSTER_ORDER[0]   # default
        best_score = 0
        for theme in _CLUSTER_ORDER:
            s = _score_article(text, _CLUSTER_KEYWORDS[theme])
            if s > best_score:
                best_score = s
                best_theme = theme
        buckets[best_theme].append(art)

    return buckets


def _relative_time(iso_ts: str) -> str:
    """Convert an ISO-8601 timestamp into a short relative label (e.g. '12m')."""
    if not iso_ts:
        return "now"
    try:
        dt = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        age_s = max(0, (datetime.now(timezone.utc) - dt).total_seconds())
    except Exception:
        return "now"
    if age_s < 60:    return "now"
    if age_s < 3600:  return f"{int(age_s/60)}m"
    if age_s < 86400: return f"{int(age_s/3600)}h"
    return f"{int(age_s/86400)}d"


def _norm_fj(arts: list[dict]) -> list[dict]:
    """Normalize Financial Juice / Apify articles to the unified shape."""
    out = []
    now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for a in arts or []:
        headline = (a.get("headline") or "").strip()
        if not headline:
            continue
        out.append({
            "headline":    headline,
            "title":       headline,
            "url":         a.get("url", ""),
            "source":      a.get("source", "Financial Juice"),
            "published":   a.get("timestamp", now_iso),
            "published_at":a.get("timestamp", now_iso),
            "time":        a.get("time") or _relative_time(a.get("timestamp", now_iso)),
            "category":    a.get("category") or _tag(headline, ""),
            "feed":        "financialjuice",
            "is_negative": is_negative(headline),
        })
    return out


def _norm_newsapi(arts: list[dict]) -> list[dict]:
    """Normalize NewsAPI articles to the unified shape."""
    out = []
    for a in arts or []:
        title = (a.get("title") or "").strip()
        if not title:
            continue
        pub = a.get("published") or ""
        out.append({
            "headline":    title,
            "title":       title,
            "url":         a.get("url", ""),
            "source":      a.get("source", "NewsAPI"),
            "published":   pub,
            "published_at":pub,
            "time":        a.get("published_ago") or _relative_time(pub),
            "category":    a.get("category") or _tag(title, ""),
            "feed":        "newsapi",
            "is_negative": is_negative(title),
        })
    return out


def _norm_rss(arts: list[dict]) -> list[dict]:
    """Normalize Google News RSS articles to the unified shape."""
    out = []
    for a in arts or []:
        title = (a.get("title") or "").strip()
        if not title:
            continue
        pub = a.get("published") or a.get("published_at") or ""
        out.append({
            "headline":    title,
            "title":       title,
            "url":         a.get("url", ""),
            "source":      a.get("source", "Google News"),
            "published":   pub,
            "published_at":pub,
            "time":        a.get("time") or _relative_time(pub),
            "category":    _tag(title, a.get("description", "")),
            "feed":        "rss",
            "is_negative": is_negative(title),
        })
    return out


def _norm_direct(arts: list[dict]) -> list[dict]:
    """Normalize direct energy RSS feed articles to the unified shape.

    Same shape as RSS but tagged feed='direct' so attribution in the response
    correctly reflects that these come from energy-industry primary sources.
    """
    out = []
    for a in arts or []:
        title = (a.get("title") or "").strip()
        if not title:
            continue
        pub = a.get("published") or a.get("published_at") or ""
        out.append({
            "headline":    title,
            "title":       title,
            "url":         a.get("url", ""),
            "source":      a.get("source", "Energy RSS"),
            "published":   pub,
            "published_at":pub,
            "time":        a.get("time") or _relative_time(pub),
            "category":    _tag(title, a.get("description", "")),
            "feed":        "direct",
            "is_negative": is_negative(title),
        })
    return out


def _dedupe_key(article: dict) -> str:
    """Stable dedupe key: lowercased first 120 chars of the title."""
    return (article.get("title") or article.get("headline") or "").lower().strip()[:120]


def get_energy_news(max_articles: int = 15) -> dict:
    """
    Fetch energy news from every available source concurrently, merge,
    dedupe by title, and return the freshest articles first.

    Sources (all run in parallel; whichever returns within its timeout wins):
      - Google News RSS      (no auth, ~7 s, headlines are minutes-to-hours old)
      - NewsAPI              (free tier — 24h lag, but rich coverage)
      - Financial Juice      (Apify scrape, 25s timeout — included whenever it
                              returns anything, even a single article)

    Each source's output is normalised to a common shape with `published_at`
    in ISO-8601 UTC. Articles are deduplicated by lowercased title, sorted by
    publication time descending, and truncated to `max_articles`.

    Parameters
    ----------
    max_articles : int — maximum articles to return (default 15)

    Returns
    -------
    {
      "articles":            [{...}],   # normalised, freshest first
      "clusters":            {...},     # by Phase-4 themes
      "negative_count":      int,
      "composite_sentiment": {...},
      "source_used":         str,       # legacy: feed of the freshest article
      "sources_used":        {feed: count, ...},
      "latency_seconds":     int|None,  # age of the freshest article in seconds
      "timestamp":           str,       # ISO-8601 UTC of this fetch
    }
    """
    from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

    global _news_cache, _news_cache_time

    # Honor ?nocache=1 from the Flask request context (debug bypass).
    _bypass = False
    try:
        from flask import has_request_context, request as _req
        if has_request_context() and _req.args.get("nocache"):
            _bypass = True
    except Exception:
        pass

    if not _bypass and _news_cache is not None and _news_cache_time is not None:
        age = (datetime.now() - _news_cache_time).total_seconds()
        if age < _NEWS_CACHE_TTL:
            return _news_cache

    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")

    # ── Run every available source concurrently ───────────────────────────────
    # Each task isolates failures: if one times out, the others still land.
    try:
        from fetchers.rss_news import fetch_rss_news, fetch_direct_energy_rss
    except Exception:
        fetch_rss_news = None             # type: ignore
        fetch_direct_energy_rss = None    # type: ignore

    def _safe_fj() -> list[dict]:
        try:
            return fetch_from_financialjuice()
        except Exception as exc:
            print(f"  [warn] financialjuice fetch failed: {exc}")
            return []

    def _safe_newsapi() -> list[dict]:
        try:
            return fetch_news(top_n=max_articles * 2)
        except Exception as exc:
            print(f"  [warn] newsapi fetch failed: {exc}")
            return []

    def _safe_rss() -> list[dict]:
        if fetch_rss_news is None:
            return []
        try:
            return fetch_rss_news(max_articles * 2)
        except Exception as exc:
            print(f"  [warn] rss fetch failed: {exc}")
            return []

    def _safe_direct() -> list[dict]:
        if fetch_direct_energy_rss is None:
            return []
        try:
            return fetch_direct_energy_rss(max_articles * 2)
        except Exception as exc:
            print(f"  [warn] direct rss fetch failed: {exc}")
            return []

    fj_raw:     list[dict] = []
    na_raw:     list[dict] = []
    rss_raw:    list[dict] = []
    direct_raw: list[dict] = []

    # Shared time budget. Direct + Google RSS finish in ~2-7s; NewsAPI in ~3s;
    # Apify is unlikely to land before its 8s budget given the FJ site went
    # behind auth. Total wall time is bounded by max(timeouts).
    t_start = time.time()

    with ThreadPoolExecutor(max_workers=4) as ex:
        f_direct = ex.submit(_safe_direct)
        f_rss    = ex.submit(_safe_rss)
        f_na     = ex.submit(_safe_newsapi)
        f_fj     = ex.submit(_safe_fj)
        # Order matters for dedup priority later (we drain in this order):
        # direct (fastest+freshest) → rss → newsapi → fj.
        futures = {f_direct: ("direct",         _TIMEOUT_DIRECT),
                   f_rss:    ("rss",            _TIMEOUT_RSS),
                   f_na:     ("newsapi",        _TIMEOUT_NEWSAPI),
                   f_fj:     ("financialjuice", _TIMEOUT_FJ)}

        for fut, (label, budget) in futures.items():
            remaining = max(0.0, budget - (time.time() - t_start))
            try:
                data = fut.result(timeout=remaining)
                if   label == "direct":  direct_raw = data
                elif label == "rss":     rss_raw    = data
                elif label == "newsapi": na_raw     = data
                else:                    fj_raw     = data
            except FuturesTimeout:
                print(f"  [info] {label} exceeded its budget ({budget}s) — skipping")
                fut.cancel()
            except Exception as exc:
                print(f"  [warn] {label} fetch error: {exc}")

    # ── Normalise + apply relevance gate to RSS / NewsAPI ─────────────────────
    fj_arts     = _norm_fj(fj_raw)
    na_arts     = _norm_newsapi(na_raw)
    rss_arts    = _norm_rss(rss_raw)
    direct_arts = _norm_direct(direct_raw)

    # RSS / NewsAPI come from broad searches — filter for energy relevance the
    # same way fetch_from_financialjuice already does internally. Direct feeds
    # (OilPrice / Rigzone / Hellenic) are already energy-only by source so we
    # skip the keyword gate to avoid culling shipping or LNG headlines that
    # don't trip the narrow RELEVANCE_TERMS list.
    def _is_energy_relevant(art: dict) -> bool:
        blob = (art.get("title", "") + " " + art.get("source", "")).lower()
        return any(term in blob for term in RELEVANCE_TERMS)

    na_arts  = [a for a in na_arts  if _is_energy_relevant(a)]
    rss_arts = [a for a in rss_arts if _is_energy_relevant(a)]

    # ── Merge + dedupe ────────────────────────────────────────────────────────
    # Priority: direct energy feeds (freshest + curated) > Google News RSS >
    # Apify FJ > NewsAPI (24h-delayed). Dict insertion order is preserved so
    # earlier writes (higher priority) keep their attribution and timestamp.
    merged: dict[str, dict] = {}
    for art in direct_arts + rss_arts + fj_arts + na_arts:
        k = _dedupe_key(art)
        if k and k not in merged:
            merged[k] = art

    # Sort by publication time descending — newest first.
    all_articles = sorted(
        merged.values(),
        key=lambda a: a.get("published_at") or "",
        reverse=True,
    )

    articles = all_articles[:max_articles]

    # ── Per-source counts (over what we actually return) ──────────────────────
    sources_used: dict[str, int] = {}
    for a in articles:
        sources_used[a.get("feed", "unknown")] = sources_used.get(a.get("feed", "unknown"), 0) + 1

    # ── FinBERT sentiment (one batched round-trip) ────────────────────────────
    _scores = _batch_score([a["headline"] for a in articles])
    for _art, _sc in zip(articles, _scores):
        _art["sentiment"] = _sc

    # ── Freshness metric: age of the freshest returned article ────────────────
    latency_seconds: int | None = None
    if articles:
        try:
            top = articles[0].get("published_at") or ""
            if top:
                dt = datetime.fromisoformat(top.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                latency_seconds = int(max(0, (datetime.now(timezone.utc) - dt).total_seconds()))
        except Exception:
            pass

    negative_count = sum(1 for a in articles if a["is_negative"])
    composite_sentiment = _aggregate(articles)
    legacy_source_used = articles[0].get("feed") if articles else "none"

    result = {
        "articles":            articles,
        "clusters":            _cluster_articles(articles),
        "negative_count":      negative_count,
        "composite_sentiment": composite_sentiment,
        "source_used":         legacy_source_used,
        "sources_used":        sources_used,
        "latency_seconds":     latency_seconds,
        "timestamp":           timestamp,
    }
    _news_cache      = result
    _news_cache_time = datetime.now()
    return result


if __name__ == "__main__":
    print("Fetching energy news via get_energy_news()...\n")
    result = get_energy_news(max_articles=15)

    CAT_PAD = {
        "CRUDE":    "[CRUDE]   ",
        "OPEC":     "[OPEC]    ",
        "GAS":      "[GAS]     ",
        "REFINERY": "[REFINERY]",
        "MACRO":    "[MACRO]   ",
        "GEO":      "[GEO]     ",
        "ENERGY":   "[ENERGY]  ",
    }

    print(f"  Source   : {result['source_used'].upper()}")
    print(f"  Articles : {len(result['articles'])}")
    print(f"  Negative : {result['negative_count']} / {len(result['articles'])}")
    print(f"  At       : {result['timestamp']}")
    print()

    for i, a in enumerate(result["articles"], 1):
        tag      = CAT_PAD.get(a["category"], f"[{a['category']:8}]")
        headline = a["headline"][:72] + ("..." if len(a["headline"]) > 72 else "")
        neg_flag = " [!]" if a["is_negative"] else "    "
        print(f"  {i:>2}.{neg_flag} {tag}  {a['time']:>8}  |  {a['source']}")
        print(f"        {headline}")
        print()

    neg_headlines = [a["headline"] for a in result["articles"] if a["is_negative"]]
    if neg_headlines:
        print(f"  --- Negative / risk headlines ({len(neg_headlines)}) ---")
        for h in neg_headlines:
            print(f"    [!] {h[:80]}")

    comp = result.get("composite_sentiment", {})
    print(f"\n  Composite sentiment: {comp.get('composite', 0.0):+.4f}  [{comp.get('label', 'N/A')}]")
