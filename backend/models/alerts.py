"""
Alert System
============
Generates trading alerts from live market data.

Schema: {id, type, severity, message, timestamp}
  id        — hash(type:YYYY-MM-DD) for daily deduplication, or
              hash(NEWS_BREAKING:title-slug) for news headlines (per-headline)
  type      — PRICE_SHOCK | COT_EXTREME | EIA_SURPRISE | IV_SPIKE | NEWS_BREAKING
  severity  — "info" | "warning" | "critical"

Public API
----------
  check_alerts(prices, technicals, eia, cot, iv=None, news=None) -> dict
"""

import hashlib
import logging
import os
import re
import sys
import time
from datetime import date, datetime, timezone, timedelta

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_ROOT    = os.path.abspath(os.path.join(_BACKEND, ".."))
for _p in (_BACKEND, _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

log = logging.getLogger("pulse.alerts")

_4WK_CACHE = {"value": None, "ts": 0.0}
_4WK_TTL   = 7 * 24 * 3600  # 1 week — EIA data updates weekly


def _alert_id(kind: str) -> str:
    return hashlib.md5(f"{kind}:{date.today().isoformat()}".encode()).hexdigest()[:12]


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _slug(text: str, length: int = 60) -> str:
    """Stable lowercased alpha-num slug — used to build per-headline alert IDs."""
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return s[:length]


def _headline_alert_id(title: str) -> str:
    """One-per-headline ID so each breaking news item only squawks once."""
    return "news_" + hashlib.md5(_slug(title).encode()).hexdigest()[:12]


# ── Squawk keyword sets ──────────────────────────────────────────────────────
# Tier 1 (critical) — supply shock / geopolitical events that move the tape now.
# Tier 2 (warning)  — sentiment-moving but slower to cash through.
_TIER1_KEYWORDS = [
    "hormuz", "blockade", "embargo", "tanker attack", "tanker seized",
    "tanker hijack", "missile strike", "drone strike", "refinery fire",
    "pipeline rupture", "pipeline blast", "force majeure", "shut down",
    "shutdown", "shuts down", "opec emergency", "production cut",
    "production halt", "production suspended", "war begins",
    "ceasefire collapse", "us strikes", "israel strikes",
    "sanctions imposed", "secondary sanctions",
    "supply disruption", "spr release", "spr emergency",
]
_TIER2_KEYWORDS = [
    "opec+", "saudi", "iran", "russia oil", "ukraine oil", "houthi",
    "red sea", "venezuela", "nigeria", "libya", "iraq oil",
    "rig count", "inventory build", "inventory draw", "gasoline demand",
    "ev adoption", "demand destruction", "demand cut", "demand outlook",
    "futures expire", "settlement", "exchange notice", "margin call",
]


def _is_recent(published_iso: str, max_age_min: int = 60) -> bool:
    """True when the article's published_at timestamp is within max_age_min."""
    if not published_iso:
        return False
    try:
        dt = datetime.fromisoformat(published_iso.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt) <= timedelta(minutes=max_age_min)
    except Exception:
        return False


def _classify_headline(title: str) -> "tuple[str | None, str]":
    """
    Classify a headline for squawk eligibility.

    Returns
    -------
    (severity, matched_keyword) where severity is 'critical' / 'warning' / None.
    None means the headline is not squawk-worthy.
    """
    low = (title or "").lower()
    for kw in _TIER1_KEYWORDS:
        if kw in low:
            return ("critical", kw)
    for kw in _TIER2_KEYWORDS:
        if kw in low:
            return ("warning", kw)
    return (None, "")


def _check_breaking_news(news: dict, max_emit: int = 4) -> list[dict]:
    """
    Scan the latest news payload for headlines worth squawking.

    Triggers when:
      - the article is < 60 minutes old (fresh enough to act on)
      - AND either matches a tier-1 supply/geo keyword (critical)
        or a tier-2 macro/sentiment keyword (warning)
        or is_negative=True from the upstream keyword filter (warning)

    Returns up to ``max_emit`` alert dicts. Each alert ID is derived from the
    headline slug so the same article never fires twice in a session.
    """
    if not isinstance(news, dict):
        return []
    articles = news.get("articles") or []
    if not articles:
        return []

    ts = _ts()
    out: list[dict] = []
    seen_ids: set[str] = set()

    # Newest first — `articles` is already sorted that way by get_energy_news()
    for art in articles:
        title = (art.get("title") or art.get("headline") or "").strip()
        if not title:
            continue
        pub = art.get("published_at") or art.get("published") or ""
        if not _is_recent(pub, max_age_min=60):
            continue

        severity, matched_kw = _classify_headline(title)
        if severity is None:
            # No keyword hit — still squawk negative-sentiment items within 30m
            if art.get("is_negative") and _is_recent(pub, max_age_min=30):
                severity, matched_kw = "warning", "negative-sentiment"
            else:
                continue

        aid = _headline_alert_id(title)
        if aid in seen_ids:
            continue
        seen_ids.add(aid)

        # Build a short, speech-friendly message. We strip trailing source
        # attribution like " - OilPrice.com" so the squawk doesn't read it.
        clean = re.sub(r"\s+-\s+[^-]{3,40}$", "", title).strip()
        source = (art.get("source") or "").strip()
        out.append({
            "id":         aid,
            "type":       "NEWS_BREAKING",
            "severity":   severity,
            "message":    f"{clean}" + (f" ({source})" if source else ""),
            "headline":   clean,
            "source":     source,
            "matched_kw": matched_kw,
            "url":        art.get("url") or "",
            "category":   art.get("category") or "",
            "timestamp":  ts,
        })
        if len(out) >= max_emit:
            break

    return out


def _four_week_avg_change() -> "float | None":
    """
    Fetch 6 weeks of EIA crude stock data and return the average weekly change
    for the 4 weeks PRIOR to the most-recent observation. Caches for 1 week.
    """
    if time.time() - _4WK_CACHE["ts"] < _4WK_TTL and _4WK_CACHE["value"] is not None:
        return _4WK_CACHE["value"]
    try:
        import requests
        from dotenv import load_dotenv
        load_dotenv()
        key = os.getenv("EIA_API_KEY")
        if not key:
            return None
        resp = requests.get(
            "https://api.eia.gov/v2/petroleum/sum/sndw/data/",
            params={
                "api_key":            key,
                "frequency":          "weekly",
                "data[0]":            "value",
                "facets[series][]":   "WCRSTUS1",
                "length":             6,
                "sort[0][column]":    "period",
                "sort[0][direction]": "desc",
            },
            timeout=15,
        )
        resp.raise_for_status()
        rows = resp.json()["response"]["data"]
        if len(rows) < 6:
            return None
        # rows[0]=latest, rows[5]=oldest; prior 4 changes use rows[1..5]
        vals = [float(r["value"]) for r in rows]
        prior_changes = [vals[i] - vals[i + 1] for i in range(1, 5)]
        avg = round(sum(prior_changes) / len(prior_changes), 1)
        _4WK_CACHE["value"] = avg
        _4WK_CACHE["ts"]    = time.time()
        return avg
    except Exception as exc:
        log.debug("4-week EIA avg fetch: %s", exc)
        return _4WK_CACHE["value"]


def check_alerts(prices, technicals, eia, cot, iv=None, news=None) -> dict:
    """
    Generate real-time trading alerts.

    Parameters
    ----------
    prices      : dict  from fetchers.prices
    technicals  : dict  from fetchers.technicals
    eia         : dict  full fundamentals dict (keys: inventory, snapshot, ...)
    cot         : dict  from fetchers.cot
    iv          : dict  from fetchers.options_iv (optional)
    news        : dict  from fetchers.news (optional) — scanned for breaking
                  geopolitical / supply-shock headlines worth squawking.

    Returns
    -------
    {
        "alerts":      list[dict],
        "eia_change":  float | None,   # current week crude change in Mbbl
        "eia_4wk_avg": float | None,   # 4-week prior average change in Mbbl
    }
    """
    alerts_list = []
    ts          = _ts()
    eia_change  = None
    eia_4wk_avg = None

    # ── 1. PRICE SHOCK ───────────────────────────────────────────────────────
    try:
        brent_chg = float((prices or {}).get("brent", {}).get("change_pct") or 0.0)
        brent_atr = float((technicals or {}).get("Brent", {}).get("atr_pct") or 0.0)
        if brent_atr > 0 and abs(brent_chg) > 2 * brent_atr:
            sev  = "critical" if abs(brent_chg) > 3 * brent_atr else "warning"
            dir_ = "surge" if brent_chg > 0 else "drop"
            alerts_list.append({
                "id":        _alert_id("PRICE_SHOCK"),
                "type":      "PRICE_SHOCK",
                "severity":  sev,
                "message":   f"Brent {dir_}: {brent_chg:+.1f}% session (ATR {brent_atr:.1f}%)",
                "timestamp": ts,
            })
    except Exception as exc:
        log.debug("price shock check: %s", exc)

    # ── 2. COT EXTREME ──────────────────────────────────────────────────────
    try:
        cot_pct = (cot or {}).get("crude_oil", {}).get("percentile")
        if cot_pct is not None:
            if cot_pct > 85:
                alerts_list.append({
                    "id":        _alert_id("COT_LONG"),
                    "type":      "COT_EXTREME",
                    "severity":  "warning",
                    "message":   f"COT longs at {cot_pct:.0f}th pctile — crowded, unwind risk",
                    "timestamp": ts,
                })
            elif cot_pct < 15:
                alerts_list.append({
                    "id":        _alert_id("COT_SHORT"),
                    "type":      "COT_EXTREME",
                    "severity":  "warning",
                    "message":   f"COT shorts at {cot_pct:.0f}th pctile — contrarian upside potential",
                    "timestamp": ts,
                })
    except Exception as exc:
        log.debug("COT check: %s", exc)

    # ── 3. EIA SURPRISE ─────────────────────────────────────────────────────
    try:
        snap        = (eia or {}).get("snapshot", {})
        crude_snap  = snap.get("Crude Stocks", {})
        eia_change  = crude_snap.get("change")      # Mbbl, positive=build, negative=draw
        eia_4wk_avg = _four_week_avg_change()
        if eia_change is not None and eia_4wk_avg is not None:
            surprise = eia_change - eia_4wk_avg
            if abs(surprise) > 2.0:
                direction = "draw" if surprise < 0 else "build"
                sev = "critical" if abs(surprise) > 4.0 else "warning"
                alerts_list.append({
                    "id":        _alert_id("EIA_SURPRISE"),
                    "type":      "EIA_SURPRISE",
                    "severity":  sev,
                    "message":   (
                        f"EIA crude {direction} surprise: {eia_change:+.1f}M "
                        f"vs {eia_4wk_avg:+.1f}M 4-wk avg ({surprise:+.1f}M)"
                    ),
                    "timestamp": ts,
                })
    except Exception as exc:
        log.debug("EIA surprise check: %s", exc)

    # ── 4. IV SPIKE ─────────────────────────────────────────────────────────
    try:
        iv_pct = (iv or {}).get("crude_iv_pctile")
        if iv_pct is not None and iv_pct > 0.80:
            sev = "critical" if iv_pct > 0.90 else "warning"
            alerts_list.append({
                "id":        _alert_id("IV_SPIKE"),
                "type":      "IV_SPIKE",
                "severity":  sev,
                "message":   f"Crude IV at {iv_pct:.0%} pctile — elevated fear premium",
                "timestamp": ts,
            })
    except Exception as exc:
        log.debug("IV spike check: %s", exc)

    # ── 5. NEWS BREAKING (trading-floor squawk) ──────────────────────────────
    try:
        alerts_list.extend(_check_breaking_news(news or {}, max_emit=4))
    except Exception as exc:
        log.debug("news breaking check: %s", exc)

    return {
        "alerts":      alerts_list,
        "eia_change":  round(eia_change, 1)  if eia_change  is not None else None,
        "eia_4wk_avg": round(eia_4wk_avg, 1) if eia_4wk_avg is not None else None,
    }


if __name__ == "__main__":
    import json
    print(json.dumps(check_alerts({}, {}, {}, {}), indent=2))
