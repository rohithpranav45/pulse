"""
External geo datasets — GDELT oil-news corpus + ACLED conflict feed.
====================================================================

Two desk-supplied datasets that make the geo engine gradeable and add a
quantitative geopolitical-risk channel:

  * GDELT oil-news corpus — `gdelt_oil_news_corpus.csv`: timestamped oil
    headlines spanning the **2026 Iran/Hormuz war** (2026-03→06). The window
    BEFORE the price tape's last settle is geo-dense AND price-covered, so it's
    the sample the per-node event study (event_study_geo) needed — far richer
    than the 2021 GDELT backfill in the live corpus.
  * ACLED conflict feed — see `conflict.py` (daily/monthly political-violence
    counts for the oil producers/transit states).

This module loads the GDELT CSV and turns it into the `events` the event study
consumes (extract → impact_map node vector), cached so re-grades don't re-extract.

Public API
----------
  GDELT_CSV                              default path (committed under data/)
  load_gdelt_corpus(path=)               -> list[{published_at, title, url, domain, country}]
  gdelt_events(until=, use_llm=, ...)    -> list[event dicts]   (for event_study_geo)
  available()                            -> bool

Run standalone:  python backend/research/news_impact/geo/datasets.py
"""

from __future__ import annotations

import csv
import logging
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[3]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

log = logging.getLogger("pulse.news_impact.geo.datasets")

_GEO_DATA = Path(__file__).parent.parent.parent.parent / "data" / "research" / "news_impact" / "geo"
GDELT_CSV = _GEO_DATA / "gdelt_oil_news_corpus.csv"


def available() -> bool:
    return GDELT_CSV.exists()


def load_gdelt_corpus(path: str | Path | None = None) -> list[dict]:
    """Parse the GDELT CSV → rows with a normalised `published_at` (ISO UTC).
    Empty list if the file is absent (caller treats as no-coverage)."""
    p = Path(path) if path else GDELT_CSV
    if not p.exists():
        log.info("GDELT corpus not found at %s", p)
        return []
    out = []
    with open(p, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            title = (r.get("title") or "").strip()
            ts = (r.get("datetime_utc") or r.get("date") or "").strip()
            if not title or not ts:
                continue
            out.append({"published_at": ts, "title": title, "url": r.get("url"),
                        "domain": r.get("domain"), "country": r.get("country")})
    return out


def gdelt_events(until=None, use_llm: bool = False, provider: str = "auto",
                 rows: list[dict] | None = None) -> list[dict]:
    """GDELT headlines → resolved geo events with a non-empty conviction vector.
    `until` (a date/Timestamp) caps to the price-covered window. Only geo-candidate
    headlines hit the (optionally cached LLM) extractor. Returns the event dicts
    event_study_geo.build_event_panel consumes."""
    import pandas as pd
    from research.news_impact.geo import extract as ex

    rows = rows if rows is not None else load_gdelt_corpus()
    if not rows:
        return []
    if until is not None:
        cap = pd.to_datetime(until, utc=True)
        rows = [r for r in rows
                if pd.to_datetime(r["published_at"], utc=True, errors="coerce") <= cap]
    cand = [r for r in rows if ex.is_geo_candidate(r["title"])]
    titles = [r["title"] for r in cand]
    exts = (ex.extract_cached(titles, provider=provider) if use_llm
            else [ex._fallback_extract(t) for t in titles])
    events = []
    for r, e in zip(cand, exts):
        if not e.asset_ids or not e.event_type:
            continue
        assets = [a for a in (ex.reg.by_id(i) for i in e.asset_ids) if a]
        impact = ex.impact_map.headline_impact(assets, e.event_type, e.severity)
        if not impact["nodes"]:
            continue
        events.append({"published_at": r["published_at"], "title": r["title"],
                       "asset_type": e.asset_type, "event_type": e.event_type,
                       "conviction": impact["nodes"]})
    return events


# ── standalone ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.WARNING)

    rows = load_gdelt_corpus()
    print(f"GDELT corpus: {len(rows)} headlines"
          + (f"  ({rows[0]['published_at'][:10]} .. {rows[-1]['published_at'][:10]})" if rows else ""))
    evs = gdelt_events(until="2026-05-26")
    print(f"price-covered geo events with node claim: {len(evs)}")
    from collections import Counter
    print("by event_type:", dict(Counter(e['event_type'] for e in evs).most_common(10)))
    print("by asset_type:", dict(Counter(e['asset_type'] for e in evs).most_common()))
