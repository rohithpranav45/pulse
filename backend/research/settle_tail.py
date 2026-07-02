"""
Opt-in OHLCV tail extension for the regime engine's daily settle tape.
=====================================================================

The /Data parquet lake's Brent daily settlements froze on **2026-05-26**; the
synth WTI file is bounded by the same 1-min source. The regime engine trains on
that tape and builds its feature matrix from it, so every historical row after
the freeze simply doesn't exist — the Phase-4 live feature overlay
(`live_features.py`) can recompute TODAY's fast features from the 15-min feed,
but the slow features and the feature-matrix date itself stay carried from
05-26.

The desk hourly OHLCV feed (`products_feed` — LCO = ICE Brent, CL = CME WTI,
continuous c1..c12, 2026-04-30 → present) already extends the geo node panel
past the lake via `nodes._combine_tail`. This module applies the same
extend-only pattern to the settle tape the regime engine reads:

  * daily settle = last hourly bar per UTC date (a session-end proxy, the same
    synthesis as the lake's own WTI file — flagged **ESTIMATE** in provenance);
  * feed rows are appended ONLY for dates strictly after the lake's last
    settle — lake rows are never overwritten;
  * tail columns are aligned to the lake's columns (Brent lake carries c1..c31,
    the feed c1..c12 → c13..c31 are NaN on tail rows; the engine's features
    only need c1/c2/c3/c6/c12).

**OPT-IN**: nothing happens unless `PULSE_SETTLE_TAIL=1`. With the flag off the
daily path, A/B harness and walk-forward are bit-for-bit unchanged. The tail
feeds *inference* (feature matrix freshness + z-scores); model training was NOT
re-run on tail rows — the pkls' effective history still ends at the lake.

Public API
----------
  tail_enabled()                          → is PULSE_SETTLE_TAIL set?
  extend_with_feed(lake, feed)            → (extended_frame, meta|None)  [pure]
  extend_settlements(lake, product)       → (extended_frame, meta|None)  [reads feed]
  overlap_stats(lake, feed, ...)          → per-contract lake-vs-feed agreement  [pure]

Run standalone for the overlap validation report:
  python -m backend.research.settle_tail
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_BACKEND = str(Path(__file__).resolve().parents[1])
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

log = logging.getLogger("pulse.research.settle_tail")

# Provenance string for tail rows wherever as_of / source is surfaced.
TAIL_SOURCE = "ohlcv_tail (ESTIMATE)"

# product feed key per settle tape
FEED_PRODUCT = {"brent": "LCO", "wti": "CL"}


def tail_enabled() -> bool:
    """PULSE_SETTLE_TAIL=1 turns the tail extension on (default OFF)."""
    return os.getenv("PULSE_SETTLE_TAIL", "").strip().lower() in ("1", "true", "on", "yes")


def extend_with_feed(lake: pd.DataFrame | None,
                     feed: pd.DataFrame | None) -> tuple[pd.DataFrame | None, dict | None]:
    """
    EXTEND the lake settle frame with feed rows dated strictly after the lake's
    last settle. Pure: frames in → (frame, meta) out.

    Extend-only semantics (mirrors geo `nodes._combine_tail`):
      * lake rows are never overwritten — overlap dates keep the lake value;
      * without a lake there is nothing to extend (the engine's models were
        trained on the lake) → returns the lake unchanged, meta None;
      * tail columns are reindexed to the lake's columns (missing → NaN,
        extra feed columns dropped).

    meta = {source, lake_end, tail_start, tail_end, n_tail_rows} when rows were
    appended, else None.
    """
    if lake is None or lake.empty or feed is None or feed.empty:
        return lake, None
    lake_end = lake.index.max()
    tail = feed[feed.index > lake_end]
    # the feed's UTC-date grouping yields Saturday/Sunday rows (the weekend
    # electronic open = the first thin hours of Monday's trade date); the lake
    # settle tape never has weekend rows — keep the calendar consistent
    tail = tail[tail.index.dayofweek < 5]
    if tail.empty:
        return lake, None
    tail = tail.reindex(columns=lake.columns)
    out = pd.concat([lake, tail], axis=0).sort_index()
    meta = {
        "source":      TAIL_SOURCE,
        "lake_end":    lake_end.strftime("%Y-%m-%d"),
        "tail_start":  tail.index.min().strftime("%Y-%m-%d"),
        "tail_end":    tail.index.max().strftime("%Y-%m-%d"),
        "n_tail_rows": int(len(tail)),
    }
    return out, meta


def _feed_daily(product_key: str) -> pd.DataFrame | None:
    """Daily c1..c12 settle frame from the hourly OHLCV feed for 'brent'/'wti'."""
    try:
        from research.news_impact.geo import products_feed as pf
        if not pf.available():
            return None
        return pf.daily_curve(FEED_PRODUCT[product_key])
    except Exception as exc:
        log.info("settle_tail: OHLCV feed unavailable (%s)", type(exc).__name__)
        return None


def extend_settlements(lake: pd.DataFrame | None,
                       product_key: str) -> tuple[pd.DataFrame | None, dict | None]:
    """`extend_with_feed` with the feed loaded from the OHLCV share.
    product_key ∈ {'brent', 'wti'}. Degrades to (lake, None) on any feed issue."""
    if product_key not in FEED_PRODUCT:
        raise ValueError(f"unknown product_key {product_key!r}")
    if lake is None or lake.empty:
        return lake, None
    feed = _feed_daily(product_key)
    ext, meta = extend_with_feed(lake, feed)
    if meta is not None:
        # measured lake↔feed agreement over the overlap window, so the proxy
        # error travels with the provenance (desk read 2026-07-02: Brent m1_m2
        # mean|Δ| ≈ 0.36× its daily vol, WTI ≈ 0.84× vs the synth lake)
        meta["overlap"] = overlap_stats(lake, feed)
    return ext, meta


def overlap_stats(lake: pd.DataFrame | None, feed: pd.DataFrame | None,
                  contracts: tuple[str, ...] = ("c1", "c12")) -> dict | None:
    """
    Validate the feed's session-end proxy against the lake on their overlap
    window: per contract (+ the m1_m2 spread), mean/max |lake − feed| across
    common dates, alongside the lake's own daily-change vol of that series so
    the proxy error is readable in vol units. Pure. None if no overlap.
    """
    if lake is None or lake.empty or feed is None or feed.empty:
        return None
    common = lake.index.intersection(feed.index)
    if common.empty:
        return None

    def _series(df: pd.DataFrame, name: str) -> pd.Series | None:
        if name == "m1_m2":
            if "c1" in df.columns and "c2" in df.columns:
                return df["c1"] - df["c2"]
            return None
        return df[name] if name in df.columns else None

    out: dict = {
        "overlap_start": common.min().strftime("%Y-%m-%d"),
        "overlap_end":   common.max().strftime("%Y-%m-%d"),
        "n_days":        int(len(common)),
        "series":        {},
    }
    for name in list(contracts) + ["m1_m2"]:
        ls, fs = _series(lake, name), _series(feed, name)
        if ls is None or fs is None:
            continue
        diff = (ls.reindex(common) - fs.reindex(common)).dropna()
        if diff.empty:
            continue
        daily_vol = float(ls.dropna().diff().std())
        mean_abs, max_abs = float(diff.abs().mean()), float(diff.abs().max())
        out["series"][name] = {
            "mean_abs_diff": round(mean_abs, 4),
            "max_abs_diff":  round(max_abs, 4),
            "n":             int(len(diff)),
            "lake_daily_vol": round(daily_vol, 4) if np.isfinite(daily_vol) else None,
            "mean_abs_vs_vol": round(mean_abs / daily_vol, 2)
                               if np.isfinite(daily_vol) and daily_vol > 0 else None,
        }
    return out if out["series"] else None


# ── standalone: overlap validation report ────────────────────────────────────
if __name__ == "__main__":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.WARNING, format="%(message)s")

    import data_lake as dl

    print(f"PULSE_SETTLE_TAIL enabled: {tail_enabled()}")
    for key, lake in (("brent", dl.get_brent_settlements()),
                      ("wti",   dl.get_wti_settlements())):
        feed = _feed_daily(key)
        print(f"\n=== {key.upper()}  (feed product {FEED_PRODUCT[key]}) ===")
        if lake is None or lake.empty:
            print("  lake settle tape unavailable")
            continue
        print(f"  lake: {len(lake)} rows  {lake.index.min().date()} .. {lake.index.max().date()}")
        if feed is None or feed.empty:
            print("  OHLCV feed unavailable on this machine (set PULSE_OHLCV_DIR)")
            continue
        print(f"  feed: {len(feed)} rows  {feed.index.min().date()} .. {feed.index.max().date()}")
        ext, meta = extend_with_feed(lake, feed)
        if meta:
            print(f"  tail: +{meta['n_tail_rows']} rows  {meta['tail_start']} .. {meta['tail_end']}"
                  f"  [{meta['source']}]")
        else:
            print("  tail: none (feed does not extend past the lake)")
        ov = overlap_stats(lake, feed)
        if not ov:
            print("  overlap: none")
            continue
        print(f"  overlap {ov['overlap_start']} .. {ov['overlap_end']}  ({ov['n_days']} common days)")
        print(f"  {'series':8s} {'mean|Δ|':>9s} {'max|Δ|':>9s} {'n':>4s} {'daily vol':>10s} {'mean/vol':>9s}")
        for name, s in ov["series"].items():
            print(f"  {name:8s} {s['mean_abs_diff']:9.4f} {s['max_abs_diff']:9.4f} "
                  f"{s['n']:4d} {str(s['lake_daily_vol']):>10s} {str(s['mean_abs_vs_vol']):>9s}")
