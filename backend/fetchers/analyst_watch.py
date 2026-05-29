"""
Analyst Watch — Live feeds for key oil market voices.

Sources
-------
  Javier Blas   → Nitter RSS  (Twitter @JavierBlas)
  Amena Bakr    → Nitter RSS  (Twitter @AmenaBakr)
  Donald Trump  → Truth Social RSS  (@realDonaldTrump)

Nitter is an open-source Twitter front-end that exposes RSS feeds
without requiring a Twitter/X API key.  Multiple public instances are
tried in order; the first that responds successfully is used.

Truth Social exposes an ActivityPub/RSS endpoint for public accounts.

Public API
----------
  get_analyst_watch() → dict
    {
      "analysts": [
        {
          "name":     str,
          "handle":   str,
          "org":      str,
          "role":     str,
          "source":   "nitter" | "truthsocial",
          "profile_url": str,
          "posts":    [
            {
              "text":      str,
              "url":       str | None,
              "published": str,   # ISO-8601 or human-readable
              "ago":       str,   # "Xm ago" / "Xh ago" / "Xd ago"
            },
            ...
          ],
          "ok":       bool,   # False if feed fetch failed
          "error":    str | None,
        },
        ...
      ],
      "timestamp": str,
    }
"""

import html
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from typing import Optional

import requests

log = logging.getLogger(__name__)

# ── Nitter public instances (tried in order until one works) ──────────────────
_NITTER_INSTANCES = [
    "https://nitter.privacydev.net",
    "https://nitter.poast.org",
    "https://nitter.unixfox.eu",
    "https://nitter.cz",
    "https://nitter.net",
]

_TIMEOUT = 8   # seconds per request
_MAX_POSTS = 5

# ── Analyst definitions ───────────────────────────────────────────────────────
_ANALYSTS = [
    {
        "name":        "Javier Blas",
        "handle":      "@JavierBlas",
        "twitter_user":"JavierBlas",
        "org":         "Bloomberg Opinion",
        "role":        "Energy & Commodities columnist",
        "source":      "nitter",
    },
    {
        "name":        "Amena Bakr",
        "handle":      "@AmenaBakr",
        "twitter_user":"AmenaBakr",
        "org":         "Energy Intelligence",
        "role":        "Chief OPEC correspondent",
        "source":      "nitter",
    },
    {
        "name":        "Donald Trump",
        "handle":      "@realDonaldTrump",
        "twitter_user":"realDonaldTrump",
        "org":         "Truth Social / White House",
        "role":        "47th US President — tariffs, energy policy, sanctions",
        "source":      "truthsocial",
        "fallback_url":"https://truthsocial.com/@realDonaldTrump",
        "fallback_note":"Truth Social restricts unauthenticated API access. Visit profile directly for latest posts — Trump energy-related statements tracked via news feed.",
    },
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ago(dt: datetime) -> str:
    """Human-readable 'X ago' from a UTC-aware datetime."""
    try:
        now   = datetime.now(timezone.utc)
        delta = now - dt.astimezone(timezone.utc)
        secs  = int(delta.total_seconds())
        if secs < 60:
            return "just now"
        if secs < 3600:
            return f"{secs // 60}m ago"
        if secs < 86400:
            return f"{secs // 3600}h ago"
        return f"{secs // 86400}d ago"
    except Exception:
        return "—"


def _strip_html(text: str) -> str:
    """Remove HTML tags and decode entities from RSS description text."""
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _parse_rss_items(xml_text: str, base_url: str = "") -> list[dict]:
    """
    Parse RSS <item> or Atom <entry> elements into post dicts.
    Handles both RSS 2.0 and Atom 1.0 (used by Mastodon / Truth Social).
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        log.warning("RSS parse error: %s", exc)
        return []

    # Detect namespace (Atom uses xmlns="http://www.w3.org/2005/Atom")
    ns = ""
    tag = root.tag
    if tag.startswith("{"):
        ns = tag[:tag.index("}") + 1]

    # Support both RSS <item> and Atom <entry>
    items = list(root.iter("item")) or list(root.iter(f"{ns}entry")) or list(root.iter("entry"))

    posts = []
    for item in items:
        def _t(tag_name: str) -> str:
            """Get text from tag with or without namespace."""
            el = item.find(tag_name) or item.find(f"{ns}{tag_name}")
            return (el.text or "").strip() if el is not None else ""

        # Content: prefer <content> / <description> / <summary> / <title>
        content = (
            _strip_html(_t("content") or _t("description") or _t("summary")) or
            _strip_html(_t("title"))
        )
        if not content:
            continue

        # Date: pubDate (RSS) or updated/published (Atom)
        pub_str = _t("pubDate") or _t("updated") or _t("published")
        try:
            pub_dt  = parsedate_to_datetime(pub_str)
            pub_iso = pub_dt.isoformat(timespec="seconds")
            ago_str = _ago(pub_dt)
        except Exception:
            # Atom dates are ISO-8601 — try direct parse
            try:
                pub_dt  = datetime.fromisoformat(pub_str.replace("Z", "+00:00"))
                pub_iso = pub_dt.isoformat(timespec="seconds")
                ago_str = _ago(pub_dt)
            except Exception:
                pub_iso = pub_str
                ago_str = "—"

        # Link: <link href="..."> (Atom) or <link>text</link> (RSS)
        link_el = item.find("link") or item.find(f"{ns}link")
        if link_el is not None:
            link_raw = link_el.get("href") or link_el.text or ""
        else:
            link_raw = ""
        link_raw = link_raw.strip()

        link_out = link_raw
        if base_url and link_raw.startswith(base_url):
            link_out = link_raw.replace(base_url, "https://x.com", 1)

        posts.append({
            "text":      content[:400],
            "url":       link_out or None,
            "published": pub_iso,
            "ago":       ago_str,
        })

    return posts[:_MAX_POSTS]


# ── Nitter fetcher ────────────────────────────────────────────────────────────

def _fetch_nitter(twitter_user: str) -> tuple[list[dict], Optional[str]]:
    """
    Try each Nitter instance until one returns a valid RSS feed.

    Returns (posts, error_msg).  On success error_msg is None.
    """
    last_error = "All Nitter instances failed"
    for instance in _NITTER_INSTANCES:
        url = f"{instance}/{twitter_user}/rss"
        try:
            resp = requests.get(url, timeout=_TIMEOUT, headers={
                "User-Agent": "PULSE/1.0 (energy dashboard; RSS reader)"
            })
            if resp.status_code == 200 and "<?xml" in resp.text[:100]:
                posts = _parse_rss_items(resp.text, base_url=instance)
                if posts:
                    log.info("Nitter OK: %s via %s (%d posts)", twitter_user, instance, len(posts))
                    return posts, None
                # Empty feed — try next instance
                last_error = f"Empty feed from {instance}"
            else:
                last_error = f"HTTP {resp.status_code} from {instance}"
        except requests.Timeout:
            last_error = f"Timeout from {instance}"
        except Exception as exc:
            last_error = str(exc)

    return [], last_error


# ── Truth Social fetcher ──────────────────────────────────────────────────────

def _fetch_truthsocial(ts_user: str) -> tuple[list[dict], Optional[str]]:
    """
    Fetch public posts from Truth Social via Mastodon-compatible API.

    Truth Social serves HTML (SPA) for RSS URLs; uses the Mastodon API
    for public account statuses instead.

    Step 1: account lookup  → GET /api/v1/accounts/lookup?acct={user}
    Step 2: statuses fetch  → GET /api/v1/accounts/{id}/statuses?limit=5
    """
    base = "https://truthsocial.com"
    headers = {
        "User-Agent": "PULSE/1.0 (energy dashboard; public API reader)",
        "Accept":     "application/json",
    }
    try:
        # Step 1 — look up account ID
        lu_resp = requests.get(
            f"{base}/api/v1/accounts/lookup",
            params={"acct": ts_user},
            headers=headers,
            timeout=_TIMEOUT,
        )
        if lu_resp.status_code != 200:
            return [], f"Account lookup failed: HTTP {lu_resp.status_code}"
        account = lu_resp.json()
        acct_id = account.get("id")
        if not acct_id:
            return [], "Account ID not found in lookup response"

        # Step 2 — fetch recent statuses
        st_resp = requests.get(
            f"{base}/api/v1/accounts/{acct_id}/statuses",
            params={"limit": _MAX_POSTS, "exclude_replies": "true"},
            headers=headers,
            timeout=_TIMEOUT,
        )
        if st_resp.status_code != 200:
            return [], f"Statuses fetch failed: HTTP {st_resp.status_code}"

        statuses = st_resp.json()
        if not isinstance(statuses, list):
            return [], "Unexpected statuses response format"

        posts = []
        for s in statuses[:_MAX_POSTS]:
            # Content is HTML — strip tags
            raw = _strip_html(s.get("content") or "")
            if not raw:
                continue
            pub_str = s.get("created_at", "")
            try:
                pub_dt  = datetime.fromisoformat(pub_str.replace("Z", "+00:00"))
                pub_iso = pub_dt.isoformat(timespec="seconds")
                ago_str = _ago(pub_dt)
            except Exception:
                pub_iso = pub_str
                ago_str = "—"
            url_out = s.get("url") or f"{base}/@{ts_user}"
            posts.append({
                "text":      raw[:400],
                "url":       url_out,
                "published": pub_iso,
                "ago":       ago_str,
            })

        log.info("Truth Social API OK: %s (%d posts)", ts_user, len(posts))
        return posts, None if posts else "No statuses returned"

    except requests.Timeout:
        return [], "Truth Social API timeout"
    except Exception as exc:
        return [], str(exc)


# ── Public API ────────────────────────────────────────────────────────────────

def get_analyst_watch() -> dict:
    """
    Fetch latest posts/tweets from all tracked analysts.

    Returns the dict described in the module docstring.
    Failures per-analyst are captured in the `ok`/`error` fields
    so one bad fetch doesn't break the whole result.
    """
    results = []
    for analyst in _ANALYSTS:
        profile_url = (
            f"https://x.com/{analyst['twitter_user']}"
            if analyst["source"] == "nitter"
            else analyst.get("fallback_url", f"https://truthsocial.com/@{analyst['twitter_user']}")
        )
        entry = {
            "name":         analyst["name"],
            "handle":       analyst["handle"],
            "org":          analyst["org"],
            "role":         analyst["role"],
            "source":       analyst["source"],
            "profile_url":  profile_url,
            "fallback_note":analyst.get("fallback_note"),
            "posts":  [],
            "ok":     False,
            "error":  None,
        }

        if analyst["source"] == "nitter":
            posts, err = _fetch_nitter(analyst["twitter_user"])
        else:
            posts, err = _fetch_truthsocial(analyst["twitter_user"])

        entry["posts"] = posts
        entry["ok"]    = len(posts) > 0
        entry["error"] = err

        results.append(entry)

    return {
        "analysts":  results,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


if __name__ == "__main__":
    import json
    print("Fetching analyst watch feeds...\n")
    data = get_analyst_watch()
    for a in data["analysts"]:
        status = "✓" if a["ok"] else f"✗ ({a['error']})"
        print(f"\n{'='*60}")
        print(f"  {a['name']} ({a['handle']}) — {a['org']}  {status}")
        print(f"{'='*60}")
        for i, p in enumerate(a["posts"], 1):
            print(f"  [{i}] {p['ago']}")
            print(f"      {p['text'][:120]}")
            if p["url"]:
                print(f"      → {p['url']}")
