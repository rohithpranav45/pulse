"""
News-impact corpus + classifier CLI.

    # backfill GDELT history, then classify everything unclassified, then stats
    python -m backend.research.news_impact --backfill --start 2021-01-01 --classify

    # just pull the last 24h live + classify (quick)
    python -m backend.research.news_impact

    # report corpus state only
    python -m backend.research.news_impact --stats
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone


def _ensure_path() -> None:
    import os
    backend = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    if backend not in sys.path:
        sys.path.insert(0, backend)


def _parse_date(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)


def main(argv=None) -> int:
    # Force UTF-8 stdout so the summary glyphs never trip a cp1252 console.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    _ensure_path()
    from research.news_impact import corpus, classify

    ap = argparse.ArgumentParser(description="News-impact corpus + classifier")
    ap.add_argument("--backfill", action="store_true", help="page GDELT history into the corpus")
    ap.add_argument("--start", type=_parse_date, default=None, help="backfill start (YYYY-MM-DD)")
    ap.add_argument("--end", type=_parse_date, default=None, help="backfill end (YYYY-MM-DD)")
    ap.add_argument("--window-days", type=int, default=7)
    ap.add_argument("--classify", action="store_true", help="classify unclassified headlines")
    ap.add_argument("--limit", type=int, default=500)
    ap.add_argument("--stats", action="store_true", help="print corpus stats and exit")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    corpus.ensure_schema()

    if args.stats:
        print(corpus.stats())
        return 0

    if args.backfill:
        start = args.start or _parse_date("2021-01-01")
        print(f"→ GDELT backfill {start.date()} … {(args.end or datetime.now(timezone.utc)).date()} "
              f"(window={args.window_days}d) — this respects GDELT's 5s rate limit, be patient")
        res = corpus.backfill_gdelt(start, args.end, window_days=args.window_days)
        print(f"  windows={res['windows']} seen={res['articles_seen']} "
              f"NEW={res['rows_inserted']} empty={res['empty_windows']}")
    else:
        # default quick path — pull the last 24h live and persist
        from fetchers.gdelt import get_gdelt_news
        live = get_gdelt_news(max_articles=50, hours=24)
        n = corpus.upsert_articles(live.get("articles", []))
        print(f"→ live pull: {len(live.get('articles', []))} articles, {n} new")

    if args.classify or not args.backfill:
        print("→ classifying…")
        c = classify.classify_corpus(limit=args.limit)
        print(f"  classified={c['classified']} by_source={c['by_source']}")
        print(f"  by_factor={c['by_factor']}")

    s = corpus.stats()
    print(f"\ncorpus: total={s['total']} classified={s['classified']} "
          f"with_ts={s['with_timestamp']} span={s['span']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
