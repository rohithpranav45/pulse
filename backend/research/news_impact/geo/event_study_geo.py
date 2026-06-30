"""
Per-node geo event study — does location-news actually move each price node?
============================================================================

The empirical heart of the geo engine, in the inventory-framework tradition:
take every resolved geo-event (headline → asset(s) → event → impact_map node
vector), measure the REALISED forward move of each claimed node, and grade the
call's **directional hit-rate** (binomial vs 50%) + a magnitude **beta**
(vol-normalised move per unit conviction) — sliced by node × asset-class × curve
regime. Prior-then-learn: a node earns a MEASURED edge only where history beats a
coin flip at p < P_SIG on ≥ MIN_N events; elsewhere it stays on the impact_map
prior (sign only). Honest by construction — on a thin/keyword-extracted corpus
most slices won't clear the bar, and we say so.

Forward move: for an event at time t, anchor on the node settle strictly BEFORE
t's date and measure to the settle H trading days later (H ∈ HORIZONS) — the
close-to-close move spanning the headline. Cracks/spreads use the absolute $
change; the sign is what the hit-rate scores. Magnitude is vol-normalised
(Δ ÷ trailing-20d Δ-vol) so regimes are comparable.

Public API
----------
  build_event_panel(events=, node_panel=)   -> DataFrame  (one row per event×node)
  node_hit_table(panel, horizon)            -> list[dict]  per node / asset_type / regime
  node_betas(panel, horizon)                -> list[dict]  per-node OLS magnitude
  compute_and_cache()                       -> dict        (persisted edge map)
  load_cached()                             -> dict | None
  annotate_impact(impact, asset_type, regime, cached=) -> impact   (prior-then-learn)

Run standalone:  python backend/research/news_impact/geo/event_study_geo.py
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_BACKEND = Path(__file__).resolve().parents[3]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

log = logging.getLogger("pulse.news_impact.geo.event_study")

_CACHE = Path(__file__).parent.parent.parent.parent / "data" / "research" / "news_impact"
_CACHE.mkdir(parents=True, exist_ok=True)
_EDGE_JSON = _CACHE / "geo_event_study.json"

HORIZONS = [1, 5]            # trading days
P_SIG = 0.10                 # binomial p below which a hit-rate is "significant"
MIN_N = 20                   # min events before a slice's hit-rate is trusted
SHOW_N = 8                   # min events to report a slice at all
T_MIN = 2.0                  # |t| for a measured magnitude beta
VOL_WIN = 20                 # trailing window for the node Δ-vol normaliser


# ── stats helpers (mirror inventory/accuracy) ─────────────────────────────────
def _binom_p(k: int, n: int) -> float:
    if n == 0:
        return 1.0
    try:
        from scipy import stats
        return float(stats.binomtest(k, n, 0.5).pvalue)
    except Exception:
        from math import erf, sqrt
        z = (k - n / 2) / (sqrt(n) / 2)
        return float(2 * (1 - 0.5 * (1 + erf(abs(z) / sqrt(2)))))


def _ols(x: np.ndarray, y: np.ndarray, min_n: int = 12) -> dict | None:
    x = np.asarray(x, float); y = np.asarray(y, float)
    m = np.isfinite(x) & np.isfinite(y)
    x, y = x[m], y[m]
    n = len(x)
    if n < min_n or np.std(x) == 0:
        return None
    sx, sy = x - x.mean(), y - y.mean()
    slope = float((sx * sy).sum() / (sx ** 2).sum())
    yhat = y.mean() + slope * sx
    ss_res = float(((y - yhat) ** 2).sum())
    se = float(np.sqrt(ss_res / (n - 2) / (sx ** 2).sum())) if n > 2 else np.nan
    t = slope / se if se and se > 0 else np.nan
    return {"beta": round(slope, 4), "t": round(t, 2) if np.isfinite(t) else None, "n": n}


# ── forward node move (pure, testable) ────────────────────────────────────────
def fwd_change(series: pd.Series, ts, h_days: int,
               max_pre_gap_days: int = 7) -> tuple[float, float] | None:
    """(Δ, vol-normalised Δ) of `series` from the settle strictly before ts's date
    to H trading rows later. None if either side is missing / too stale."""
    if series is None or len(series) == 0:
        return None
    s = series.dropna()
    if s.empty:
        return None
    d = pd.Timestamp(pd.to_datetime(ts).date())
    idx = s.index
    pre_pos = idx.searchsorted(d) - 1            # last settle strictly before d
    post_pos = pre_pos + h_days
    if pre_pos < 0 or post_pos >= len(idx):
        return None
    if (d - idx[pre_pos]).days > max_pre_gap_days:
        return None
    pre, post = float(s.iloc[pre_pos]), float(s.iloc[post_pos])
    delta = post - pre
    vol = float(s.diff().rolling(VOL_WIN).std().iloc[pre_pos]) if pre_pos >= VOL_WIN else np.nan
    vn = delta / vol if vol and vol == vol and vol > 0 else np.nan
    return delta, vn


# ── event sourcing ────────────────────────────────────────────────────────────
def _events_from_corpus(limit: int = 500_000, use_llm: bool = True,
                        provider: str = "auto", until=None) -> list[dict]:
    """Resolve corpus headlines → geo events with a non-empty conviction vector.

    Only headlines passing a cheap high-recall **geo prefilter** are sent to the
    (cached) LLM extractor — so the free Groq budget is spent where it matters and
    re-grades never re-call. `until` caps to the price-covered window (defaults to
    the node tape's last date, since later events can't be graded)."""
    import pandas as pd
    from research.news_impact import corpus
    from research.news_impact.geo import extract as ex
    rows = [r for r in corpus.recent(limit=limit) if r.get("published_at") and r.get("title")]
    if until is not None:
        cap = pd.to_datetime(until, utc=True)
        rows = [r for r in rows if pd.to_datetime(r["published_at"], utc=True, errors="coerce") <= cap]
    cand = [r for r in rows if ex.is_geo_candidate(r["title"], r.get("factor"))]
    titles = [r["title"] for r in cand]
    extractions = (ex.extract_cached(titles, provider=provider) if use_llm
                   else [ex._fallback_extract(t) for t in titles])
    out = []
    for r, e in zip(cand, extractions):
        if not e.asset_ids or not e.event_type:
            continue
        assets = [a for a in (ex.reg.by_id(i) for i in e.asset_ids) if a]
        impact = ex.impact_map.headline_impact(assets, e.event_type, e.severity)
        if not impact["nodes"]:
            continue
        out.append({"published_at": r["published_at"], "title": r["title"],
                    "asset_type": e.asset_type, "event_type": e.event_type,
                    "conviction": impact["nodes"]})
    return out


_panel_cache: dict | None = None


def _gather_events(until, use_llm: bool, provider: str, source: str = "auto") -> list[dict]:
    """Source events for the study. 'auto' prefers the GDELT desk corpus (geo-dense
    + price-covered 2026 war window) when present, else the live news corpus."""
    if source in ("gdelt", "auto"):
        try:
            from research.news_impact.geo import datasets
            if datasets.available():
                evs = datasets.gdelt_events(until=until, use_llm=use_llm, provider=provider)
                if evs or source == "gdelt":
                    return evs
        except Exception as exc:
            log.info("GDELT event sourcing failed (%s)", type(exc).__name__)
    return _events_from_corpus(use_llm=use_llm, provider=provider, until=until)


def _event_conflict_level(ts, cache: dict) -> str | None:
    """Causal ACLED **bloc** conflict regime (HIGH/NORMAL/LOW) as-of an event's
    month — the extra conditioning axis: 'a Hormuz headline in a HIGH-conflict
    month is not the same event as in a calm one'. Memoised per year-month so the
    CSV is read once per distinct month, not once per event. None when the ACLED
    feed is absent or the month resolves to UNKNOWN (too little history)."""
    key = (ts.year, ts.month)
    if key in cache:
        return cache[key]
    level = None
    try:
        from research.news_impact.geo import conflict
        if conflict.available("monthly"):
            r = conflict.conflict_regime("BLOC", asof=pd.Timestamp(ts.date()))
            lv = r.get("level")
            level = lv if lv and lv != "UNKNOWN" else None
    except Exception:
        level = None
    cache[key] = level
    return level


def build_event_panel(events: list[dict] | None = None,
                      node_panel: pd.DataFrame | None = None,
                      use_llm: bool = True, provider: str = "auto",
                      source: str = "auto") -> pd.DataFrame:
    """One row per (event × claimed node): published_at, asset_type, regime,
    conflict, node, conviction, pred_sign, and per-horizon Δ / vol-normalised Δ /
    hit. `conflict` is the causal ACLED bloc conflict regime as-of the event."""
    if node_panel is None:
        from research.news_impact.geo import nodes
        node_panel = nodes.build_node_panel()
    if node_panel is None or node_panel.empty:
        return pd.DataFrame()
    if events is None:
        # cap to the price-covered window — events past the tape can't be graded
        until = node_panel.dropna(how="all").index.max()
        events = _gather_events(until, use_llm, provider, source)
    if not events:
        return pd.DataFrame()

    struct = node_panel["brent_structure"].dropna() if "brent_structure" in node_panel else None
    conf_cache: dict = {}
    rows = []
    for ev in events:
        ts = pd.to_datetime(ev["published_at"], utc=True, errors="coerce")
        if pd.isna(ts):
            continue
        regime = None
        if struct is not None and len(struct):
            d = pd.Timestamp(ts.date())
            pos = struct.index.searchsorted(d) - 1
            if pos >= 0:
                regime = "BACK" if float(struct.iloc[pos]) > 0 else "CONTANGO"
        conflict_level = _event_conflict_level(ts, conf_cache)
        for node, score in ev["conviction"].items():
            if not score or node not in node_panel.columns:
                continue
            rec = {"published_at": ts, "title": ev.get("title"),
                   "asset_type": ev.get("asset_type"),
                   "event_type": ev.get("event_type"), "regime": regime,
                   "conflict": conflict_level,
                   "node": node, "conviction": float(score),
                   "pred_sign": int(np.sign(score))}
            any_h = False
            for h in HORIZONS:
                fc = fwd_change(node_panel[node], ts, h)
                if fc is None:
                    rec[f"d{h}"] = np.nan; rec[f"vn{h}"] = np.nan; rec[f"hit{h}"] = np.nan
                else:
                    delta, vn = fc
                    rec[f"d{h}"] = delta
                    rec[f"vn{h}"] = vn * rec["pred_sign"]   # aligned (so + = correct direction)
                    rec[f"hit{h}"] = float(np.sign(delta) == rec["pred_sign"])
                    any_h = True
            if any_h:
                rows.append(rec)
    return pd.DataFrame(rows)


# ── grading ───────────────────────────────────────────────────────────────────
def _hit_cell(sub: pd.DataFrame, horizon: int) -> dict | None:
    s = sub[f"hit{horizon}"].dropna()
    n = len(s)
    if n < SHOW_N:
        return None
    hits = float(s.mean()); k = int(round(hits * n)); p = _binom_p(k, n)
    return {"hit": round(hits, 3), "n": n, "p": round(p, 3), "edge": round(hits - 0.5, 3),
            "significant": bool(p < P_SIG and hits > 0.5 and n >= MIN_N)}


def node_hit_table(panel: pd.DataFrame, horizon: int = 1) -> list[dict]:
    """Directional hit-rate per node, and per node×asset_type / node×regime /
    node×conflict where n permits, plus the pooled 'ALL' row. Every row carries a
    `conflict` field ('*' = not conflict-conditioned); the node×conflict slices
    answer 'does the geo edge strengthen in HIGH-conflict months?'."""
    if panel is None or panel.empty:
        return []
    has_conflict = "conflict" in panel.columns
    out = []
    allc = _hit_cell(panel, horizon)
    if allc:
        out.append({"slice": "ALL", "node": "*", "asset_type": "*", "regime": "*",
                    "conflict": "*", **allc})
    for node, g in panel.groupby("node"):
        c = _hit_cell(g, horizon)
        if c:
            out.append({"slice": "node", "node": node, "asset_type": "*", "regime": "*",
                        "conflict": "*", **c})
        for at, gg in g.groupby("asset_type"):
            c2 = _hit_cell(gg, horizon)
            if c2:
                out.append({"slice": "node×type", "node": node, "asset_type": at,
                            "regime": "*", "conflict": "*", **c2})
        for rg, gg in g.groupby("regime"):
            c3 = _hit_cell(gg, horizon)
            if c3:
                out.append({"slice": "node×regime", "node": node, "asset_type": "*",
                            "regime": rg, "conflict": "*", **c3})
        if has_conflict:
            for cf, gg in g.groupby("conflict"):
                c4 = _hit_cell(gg, horizon)
                if c4:
                    out.append({"slice": "node×conflict", "node": node, "asset_type": "*",
                                "regime": "*", "conflict": cf, **c4})
    out.sort(key=lambda r: (r["significant"], -r["p"]), reverse=True)
    return out


def node_betas(panel: pd.DataFrame, horizon: int = 1) -> list[dict]:
    """Per-node OLS of vol-normalised forward move on signed conviction."""
    if panel is None or panel.empty:
        return []
    rows = []
    for node, g in panel.groupby("node"):
        # un-align vn back to raw before regressing on signed conviction
        raw_vn = g[f"vn{horizon}"] * g["pred_sign"]
        o = _ols(g["conviction"].values, raw_vn.values, min_n=12)
        if o:
            o["measured"] = bool(o["t"] is not None and abs(o["t"]) >= T_MIN and o["n"] >= 12)
            rows.append({"node": node, **o})
    rows.sort(key=lambda r: abs(r.get("t") or 0), reverse=True)
    return rows


def compute_and_cache(events: list[dict] | None = None) -> dict:
    panel = build_event_panel(events=events)
    out: dict = {"available": not panel.empty, "n_events": 0, "n_claims": int(len(panel)),
                 "horizons": HORIZONS, "p_sig": P_SIG, "min_n": MIN_N,
                 "hit_tables": {}, "betas": {},
                 "source": "backend/research/news_impact/geo/event_study_geo"}
    if not panel.empty:
        out["n_events"] = int(panel["published_at"].nunique())
        out["span"] = [str(panel["published_at"].min().date()),
                       str(panel["published_at"].max().date())]
        out["by_asset_type"] = panel.groupby("asset_type")["published_at"].nunique().to_dict()
        # ACLED conflict-regime coverage of the graded events — so the degeneracy
        # (e.g. all 2026-war events mapping to one stale-ACLED level) is visible.
        if "conflict" in panel.columns:
            dist = (panel.dropna(subset=["conflict"])
                         .groupby("conflict")["published_at"].nunique().to_dict())
            out["conflict_levels"] = {str(k): int(v) for k, v in dist.items()}
            out["n_events_no_conflict"] = int(
                panel[panel["conflict"].isna()]["published_at"].nunique())
        for h in HORIZONS:
            out["hit_tables"][str(h)] = node_hit_table(panel, h)
            out["betas"][str(h)] = node_betas(panel, h)
    try:
        _EDGE_JSON.write_text(json.dumps(out, indent=2, default=str))
    except Exception as exc:
        log.warning("could not cache geo edge map: %s", exc)
    return out


def load_cached() -> dict | None:
    if not _EDGE_JSON.exists():
        return None
    try:
        return json.loads(_EDGE_JSON.read_text())
    except Exception:
        return None


# ── prior-then-learn consumer ─────────────────────────────────────────────────
def annotate_impact(impact: dict, asset_type: str | None, regime: str | None,
                    horizon: int = 1, cached: dict | None = None) -> dict:
    """Tag each node in a live impact vector with its historical directional
    hit-rate where one was earned (most specific applicable significant slice),
    else mark it prior-only. Returns impact augmented with an `edges` block."""
    cached = (load_cached() or {}) if cached is None else cached
    table = (cached.get("hit_tables") or {}).get(str(horizon), [])
    edges = {}
    for node in (impact.get("nodes") or {}):
        best = None
        for r in table:
            # conflict-conditioned slices are descriptive only — never drive the
            # live tag (we don't condition the live impact on ACLED yet).
            if r.get("conflict", "*") != "*":
                continue
            if r["node"] not in (node, "*"):
                continue
            if r["asset_type"] not in (asset_type, "*"):
                continue
            if r["regime"] not in (regime, "*"):
                continue
            if not r["significant"]:
                continue
            # prefer the most specific (fewest wildcards) significant slice
            spec = (r["asset_type"] != "*") + (r["regime"] != "*") + (r["node"] != "*")
            if best is None or spec > best[0]:
                best = (spec, r)
        if best:
            r = best[1]
            edges[node] = {"hit": r["hit"], "n": r["n"], "p": r["p"], "tradeable": True,
                           "basis": "measured", "slice": r["slice"]}
        else:
            edges[node] = {"tradeable": False, "basis": "prior"}
    out = dict(impact)
    out["edges"] = edges
    out["tradeable_nodes"] = [n for n, e in edges.items() if e.get("tradeable")]
    return out


# ── standalone grader ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    from research.news_impact.geo import extract as _ex
    _ex.load_env()                    # so the free Groq extractor is used for the grade
    prov = "groq" if __import__("os").getenv("GROQ_API_KEY") else "fallback"
    print(f"Building geo event panel (corpus × node tape) — extractor={prov} …")
    panel = build_event_panel()
    if panel.empty:
        print("EMPTY — no resolved geo-events with node coverage (corpus or /Data absent).")
        raise SystemExit(0)

    n_ev = panel["published_at"].nunique()
    print(f"\nevents={n_ev}  node-claims={len(panel)}  "
          f"({panel['published_at'].min().date()} .. {panel['published_at'].max().date()})")
    print("events by asset_type:",
          panel.groupby('asset_type')['published_at'].nunique().to_dict())
    if "conflict" in panel.columns:
        cd = (panel.dropna(subset=["conflict"]).groupby("conflict")["published_at"]
                   .nunique().to_dict())
        n_no = int(panel[panel["conflict"].isna()]["published_at"].nunique())
        print(f"events by ACLED conflict regime: {cd}  (no-ACLED: {n_no})")
        if len(cd) <= 1:
            print("  ⚠ conflict axis DEGENERATE on this corpus — ACLED ends 2025-06 so "
                  "every 2026-war event maps to one stale level; can't strengthen-test "
                  "(needs ACLED coverage through the episode — more data, not code).")

    for h in HORIZONS:
        print(f"\n=== Directional hit-rate @ {h}d (binomial vs 50%) ===")
        tbl = node_hit_table(panel, h)
        if not tbl:
            print("  (no slice reached the reporting floor)")
        for r in tbl:
            sig = "  *EDGE*" if r["significant"] else ""
            cf = "" if r.get("conflict", "*") == "*" else f"/{r['conflict']}"
            lbl = f"{r['node']}/{r['asset_type']}/{r['regime']}{cf}"
            print(f"  {lbl:40s} hit={r['hit']:.2f} n={r['n']:3d} p={r['p']:.3f}{sig}")
        print(f"--- magnitude betas @ {h}d (vn move per conviction unit) ---")
        for b in node_betas(panel, h):
            m = "  *MEASURED*" if b["measured"] else ""
            print(f"  {b['node']:16s} beta={b['beta']:+.3f} t={b['t']} n={b['n']}{m}")

    out = compute_and_cache()
    print(f"\ncached -> {_EDGE_JSON.name}  (events={out['n_events']}, claims={out['n_claims']})")
