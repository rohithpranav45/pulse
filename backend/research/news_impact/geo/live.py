"""
Live geo news ingestion — score TODAY's wire into geo events.
=============================================================
The dashboard's standing directive is a *live* analysis engine, not a corpus-only
study. This module is the geospatial twin of `app._news_corpus_ingest`: it takes
the already-cached `/api/news` wire and turns the geo-relevant headlines into
scored, persisted geo events the dashboard can show in real time.

Pipeline (one tick):
  wire articles
    → keep only geo CANDIDATES (`extract.is_geo_candidate` prefilter, so the free
      Groq token budget is spent only on geo news)
    → `extract.extract_cached` ({assets, event, severity}; LLM-cached, and its
      "never cache a fallback" guard is preserved — we call it unchanged)
    → `impact_map.headline_impact` (signed node vector)
    → `event_study_geo.annotate_impact` (EDGE/prior tags from the graded edge map)
    → persist to a small accumulating JSON cache (`geo_live_events.json`).

Each headline is scored ONCE (deduped by title hash in the live store); the
authoritative LLM extraction cache lives in `extract.py` and is shared with the
event-study re-grade, so re-running an ingest is cheap and never re-calls Groq for
a title already scored.

Public API
----------
  ingest_wire(articles, *, extract_fn=, regime=, max_new=, store_path=) -> dict
  recent_events(limit=, store_path=)                                    -> list[dict]
  map_assets(store_path=)                                               -> list[dict]
  load_store(store_path=) / save_store(store, store_path=)

Run standalone:  python backend/research/news_impact/geo/live.py
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[3]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from research.news_impact import corpus                          # noqa: E402
from research.news_impact.geo import registry as reg             # noqa: E402
from research.news_impact.geo import impact_map                  # noqa: E402
from research.news_impact.geo import extract                     # noqa: E402
from research.news_impact.geo import event_study_geo as es       # noqa: E402

log = logging.getLogger("pulse.news_impact.geo.live")

# Accumulating live-event store (sits beside the extraction + edge-map caches).
_STORE = Path(__file__).parent.parent.parent.parent / "data" / "research" / \
    "news_impact" / "geo_live_events.json"
_MAX_STORED = 200          # keep the most recent N scored geo events


# ── persistence ───────────────────────────────────────────────────────────────
def load_store(store_path: str | Path | None = None) -> dict:
    p = Path(store_path) if store_path else _STORE
    if p.exists():
        try:
            d = json.loads(p.read_text())
            if isinstance(d, dict) and isinstance(d.get("events"), list):
                return d
        except Exception:
            pass
    return {"events": []}


def save_store(store: dict, store_path: str | Path | None = None) -> None:
    p = Path(store_path) if store_path else _STORE
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(store, default=str))
    except Exception as exc:
        log.warning("geo live store write failed: %s", exc)


# ── scoring ───────────────────────────────────────────────────────────────────
def _conviction(nodes: dict | None) -> float:
    """The headline's strongest directional node claim (max |node value|)."""
    return max((abs(float(v)) for v in (nodes or {}).values()), default=0.0)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _merge_edges(impact: dict, asset_type: str | None,
                 regime: str | None) -> tuple[dict, list]:
    """Tag each node with its best historical edge across BOTH horizons. The geo
    edges live at +5d (chokepoint → wti_brent / ho_crack), with regrade at +1d, so
    we prefer a tradeable 5d slice, then a tradeable 1d slice, else mark it prior."""
    ann5 = es.annotate_impact(impact, asset_type, regime, horizon=5)
    ann1 = es.annotate_impact(impact, asset_type, regime, horizon=1)
    e5, e1 = (ann5.get("edges") or {}), (ann1.get("edges") or {})
    edges: dict = {}
    tradeable: list = []
    for node in (impact.get("nodes") or {}):
        if e5.get(node, {}).get("tradeable"):
            edges[node] = {**e5[node], "horizon": 5}; tradeable.append(node)
        elif e1.get(node, {}).get("tradeable"):
            edges[node] = {**e1[node], "horizon": 1}; tradeable.append(node)
        else:
            edges[node] = {"tradeable": False, "basis": "prior"}
    return edges, tradeable


def _build_record(title: str, ex, impact: dict, *, url, source,
                  ts: str | None, regime: str | None) -> dict:
    nodes = impact.get("nodes") or {}
    edges, tradeable_nodes = _merge_edges(impact, ex.asset_type, regime)
    return {
        "key":            extract._key(title),
        "title":          title,
        "url":            url,
        "source":         source,
        "ts":             ts,                 # ISO publication time (may be None)
        "asset_ids":      list(ex.asset_ids),
        "asset_type":     ex.asset_type,
        "event_type":     ex.event_type,
        "severity":       ex.severity,
        "extract_source": ex.source,          # "groq" | "claude" | "fallback"
        "nodes":          nodes,
        "rationale":      impact.get("rationale"),
        "edges":          edges,
        "tradeable_nodes": tradeable_nodes,
        "tradeable":      bool(tradeable_nodes),
        "conviction":     round(_conviction(nodes), 3),
        "scored_at":      _now_iso(),
    }


def ingest_wire(articles: list, *, extract_fn=None, regime: str | None = None,
                max_new: int = 40, store_path: str | Path | None = None) -> dict:
    """Score the geo-candidate headlines in `articles` into the live store.

    `extract_fn(titles) -> list[GeoExtraction]` defaults to `extract.extract_cached`
    (LLM-cached, fallback-not-cached). Each title is scored once (deduped on title
    hash). Only headlines that resolve to a non-empty node vector are persisted —
    a headline that names no asset / carries no throughput event is not a geo
    alert. Returns a small summary dict.
    """
    extract_fn = extract_fn or extract.extract_cached
    store = load_store(store_path)
    known = {e.get("key") for e in store["events"]}

    cands: list[tuple[str, str, dict]] = []
    for a in articles or []:
        title = (a.get("title") or a.get("headline") or "").strip()
        if not title:
            continue
        factor = a.get("factor") or a.get("category")
        if not extract.is_geo_candidate(title, factor):
            continue
        k = extract._key(title)
        if k in known:
            continue
        known.add(k)                          # de-dup within this batch too
        cands.append((k, title, a))
        if len(cands) >= max_new:
            break

    if not cands:
        return {"scanned": len(articles or []), "candidates": 0,
                "added": 0, "total": len(store["events"])}

    titles = [t for _, t, _ in cands]
    exs = extract_fn(titles)
    added = 0
    for (k, title, a), ex in zip(cands, exs):
        assets = [reg.by_id(x) for x in ex.asset_ids if reg.by_id(x)]
        impact = impact_map.headline_impact(assets, ex.event_type, ex.severity)
        if not (impact.get("nodes") or {}):   # no directional claim → not an alert
            continue
        ts = corpus._norm_ts(a.get("published_at") or a.get("published") or a.get("time"))
        store["events"].append(_build_record(
            title, ex, impact, url=a.get("url"), source=a.get("source"),
            ts=ts, regime=regime))
        added += 1

    # newest first (publication time, scored_at fallback), capped
    store["events"].sort(key=lambda e: (e.get("ts") or e.get("scored_at") or ""),
                         reverse=True)
    store["events"] = store["events"][:_MAX_STORED]
    if added:
        save_store(store, store_path)
    return {"scanned": len(articles or []), "candidates": len(cands),
            "added": added, "total": len(store["events"])}


def _rank_key(e: dict):
    """Rank by |conviction| weighted up for a tradeable (EDGE-tagged) event,
    tie-broken by recency — the most actionable alert floats to the top."""
    conv = float(e.get("conviction") or 0.0) * (1.5 if e.get("tradeable") else 1.0)
    return (conv, e.get("ts") or e.get("scored_at") or "")


def recent_events(limit: int = 30, store_path: str | Path | None = None) -> list[dict]:
    """Live-scored geo events ranked by |conviction| × tradeable (then recency)."""
    store = load_store(store_path)
    evs = list(store.get("events") or [])
    evs.sort(key=_rank_key, reverse=True)
    return evs[: max(1, int(limit))]


# ── geo map (Sprint 9) ────────────────────────────────────────────────────────
def _activity_index(store: dict) -> dict[str, dict]:
    """Tally live-event activity per asset id from the live store: how many recent
    geo events named the asset, its peak conviction, whether any carried an EDGE,
    the newest timestamp, and a few headlines (for the map's click-through card)."""
    idx: dict[str, dict] = {}
    for e in store.get("events") or []:
        ts = e.get("ts") or e.get("scored_at")
        conv = float(e.get("conviction") or 0.0)
        tradeable = bool(e.get("tradeable"))
        for aid in e.get("asset_ids") or []:
            a = idx.setdefault(aid, {"events": 0, "conviction": 0.0,
                                     "tradeable": False, "last_ts": None,
                                     "headlines": []})
            a["events"] += 1
            a["conviction"] = max(a["conviction"], conv)
            a["tradeable"] = a["tradeable"] or tradeable
            if ts and (a["last_ts"] is None or ts > a["last_ts"]):
                a["last_ts"] = ts
            if len(a["headlines"]) < 4 and e.get("title"):
                a["headlines"].append({
                    "title": e["title"], "ts": ts, "url": e.get("url"),
                    "conviction": round(conv, 3), "tradeable": tradeable,
                    "tradeable_nodes": list(e.get("tradeable_nodes") or []),
                })
    return idx


def map_assets(store_path: str | Path | None = None) -> list[dict]:
    """The geo-map payload: every PLACEABLE registry asset (drops the GLOBAL
    generics at 0,0) with its static facts + disruption_bias + recent live-event
    activity from the store. The registry stays the single source of truth for the
    coordinates and the desk priors; the activity overlay is the live colour/size."""
    store = load_store(store_path)
    act = _activity_index(store)
    out: list[dict] = []
    for a in reg.all_assets():
        if a.id in reg.GENERIC_IDS or a.region == "GLOBAL" \
                or (a.lat == 0.0 and a.lon == 0.0):
            continue                          # generic / unplaceable → off the map
        out.append({
            "id": a.id, "name": a.name, "type": a.type, "region": a.region,
            "country": a.country, "lat": a.lat, "lon": a.lon,
            "capacity_mbd": a.capacity_mbd, "carries": list(a.carries),
            "note": a.note, "disruption_bias": dict(a.disruption_bias),
            "activity": act.get(a.id, {"events": 0, "conviction": 0.0,
                                       "tradeable": False, "last_ts": None,
                                       "headlines": []}),
        })
    return out


# ── standalone ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    extract.load_env()

    # A small synthetic wire so the standalone runs without the live /api/news.
    demo = [
        {"title": "Iran threatens to close the Strait of Hormuz amid escalation",
         "url": "demo://1", "source": "demo", "published_at": _now_iso()},
        {"title": "Massive fire forces shutdown at Motiva Port Arthur refinery",
         "url": "demo://2", "source": "demo", "published_at": _now_iso()},
        {"title": "Tech stocks rally on strong earnings", "url": "demo://3",
         "source": "demo", "published_at": _now_iso()},
    ]
    res = ingest_wire(demo)
    print(f"ingest: {res}\n")
    for e in recent_events(limit=10):
        tag = "EDGE" if e["tradeable"] else "prior"
        print(f"• [{tag}] conv={e['conviction']:.2f} {e['asset_type']}/{e['event_type']} "
              f"— {e['title'][:60]}")
        print(f"    nodes={e['nodes']}  tradeable={e['tradeable_nodes']}")
