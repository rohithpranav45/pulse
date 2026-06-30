"""
Geo RAG analogs — "this event ≈ these k past events that moved node X by Y".
=============================================================================

Retrieval-augmented analogs for the geo engine. Where `event_study_geo` grades
the AVERAGE reaction (per-node hit-rate + beta across all events), this layer
answers the desk's other question: *given THIS specific headline, what are the
closest historical analogs, and what did each actually do to the price nodes?*

It is RAG in the literal sense — retrieve, then ground the answer in retrieved
evidence — but the corpus is the **graded event panel** (each past event already
carries its realised forward node moves), and the retriever is a **structured
nearest-neighbour** over an interpretable fingerprint, not a black-box embedding:

  fingerprint(event) = [ one-hot(asset_type) | one-hot(event_type) |
                         L2-normalised signed conviction vector over the nodes ]

Cosine similarity over that concat means an analog scores high when it shares the
asset class, the event verb, AND the directional impact pattern — and an opposite
event (a `restart` vs a `closure`) scores LOW because the conviction block flips
sign. No external embedding dep (consistent with the project's no-paid-embeddings
stance; Anthropic exposes no embeddings endpoint anyway).

Public API
----------
  build_analog_index(panel=, horizon=) -> AnalogIndex   (per-event fingerprint + outcomes)
  find_analogs(query, k=, index=)      -> list[dict]     ranked analogs + realised moves
  analog_forecast(query, k=, horizon=) -> dict           similarity-weighted per-node nowcast
  score_headline_analogs(title, k=)    -> dict           headline → extract → analogs + forecast
  narrate(result, ...)                 -> dict           LLM-narrated desk note (Sprint 10)

Run standalone:  python backend/research/news_impact/geo/analogs.py
"""

from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

_BACKEND = Path(__file__).resolve().parents[3]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from research.news_impact.geo import event_study_geo as es      # noqa: E402
from research.news_impact.geo import registry as reg            # noqa: E402

log = logging.getLogger("pulse.news_impact.geo.analogs")

# Fingerprint vocabularies. asset_type / event_type from the registry; node order
# is fixed so every event maps to the same column layout.
ASSET_TYPES = ["chokepoint", "refinery", "pipeline", "field", "producer", "tanker"]
EVENT_TYPES = list(reg.EVENT_TYPES)
NODES = ["brent_flat", "wti_flat", "wti_brent", "brent_structure",
         "brent_m1_m2", "brent_fly_123", "ho_crack", "gasoil_crack", "regrade"]

# Block weights — categorical structure (what kind of event, where) vs the signed
# directional impact pattern. Tuned so the three blocks contribute comparably.
W_ASSET, W_EVENT, W_CONV = 1.0, 1.0, 1.0
MIN_SIM = 0.05               # below this, an analog is "not really similar"


# ── fingerprint ────────────────────────────────────────────────────────────────
def _onehot(value, vocab: list[str], weight: float) -> np.ndarray:
    v = np.zeros(len(vocab), dtype=float)
    if value in vocab:
        v[vocab.index(value)] = weight
    return v


def _conv_block(conviction: dict, weight: float) -> np.ndarray:
    v = np.array([float(conviction.get(n, 0.0)) for n in NODES], dtype=float)
    nrm = np.linalg.norm(v)
    return (v / nrm) * weight if nrm > 0 else v


def fingerprint(asset_type, event_type, conviction: dict) -> np.ndarray:
    """[asset_type one-hot | event_type one-hot | normalised signed conviction]."""
    return np.concatenate([
        _onehot(asset_type, ASSET_TYPES, W_ASSET),
        _onehot(event_type, EVENT_TYPES, W_EVENT),
        _conv_block(conviction or {}, W_CONV),
    ])


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


# ── the index ───────────────────────────────────────────────────────────────────
@dataclass
class AnalogEvent:
    published_at: str
    title: str | None
    asset_type: str | None
    event_type: str | None
    regime: str | None
    conviction: dict                      # node -> signed conviction
    outcomes: dict                        # node -> {d1,d5,vn1,vn5,...} realised moves
    vec: np.ndarray = field(repr=False)


@dataclass
class AnalogIndex:
    events: list[AnalogEvent]

    def __len__(self) -> int:
        return len(self.events)


def _events_from_panel(panel: pd.DataFrame) -> list[AnalogEvent]:
    """Collapse the (event × node) panel into one record per event, carrying each
    claimed node's conviction + realised forward moves."""
    if panel is None or panel.empty:
        return []
    out: list[AnalogEvent] = []
    # an "event" = a unique (published_at, asset_type, event_type, title) group
    keys = ["published_at", "asset_type", "event_type"]
    if "title" in panel.columns:
        keys = keys + ["title"]
    for key, g in panel.groupby(keys, dropna=False):
        kd = dict(zip(keys, key if isinstance(key, tuple) else (key,)))
        conviction, outcomes = {}, {}
        for _, r in g.iterrows():
            node = r["node"]
            conviction[node] = float(r["conviction"])
            o = {}
            for h in es.HORIZONS:
                o[f"d{h}"] = (float(r[f"d{h}"]) if f"d{h}" in r and pd.notna(r[f"d{h}"]) else None)
                # un-align vn back into node space (panel stores vn aligned to pred_sign)
                vn = r.get(f"vn{h}")
                ps = r.get("pred_sign") or 1
                o[f"vn{h}"] = (float(vn) * int(ps)) if pd.notna(vn) else None
            outcomes[node] = o
        at, et = kd.get("asset_type"), kd.get("event_type")
        out.append(AnalogEvent(
            published_at=str(kd.get("published_at")), title=kd.get("title"),
            asset_type=at, event_type=et,
            regime=(g["regime"].iloc[0] if "regime" in g else None),
            conviction=conviction, outcomes=outcomes,
            vec=fingerprint(at, et, conviction),
        ))
    return out


def build_analog_index(panel: pd.DataFrame | None = None) -> AnalogIndex:
    """Build the analog index from the graded event panel (cached LLM extractions
    when `panel` is None — no re-extraction)."""
    if panel is None:
        panel = es.build_event_panel()
    return AnalogIndex(events=_events_from_panel(panel))


_INDEX_CACHE: AnalogIndex | None = None


def get_index(rebuild: bool = False) -> AnalogIndex:
    """Process-memoised analog index — building it scans /Data (DuckDB) + the
    cached extractions, so the API reuses one index across requests."""
    global _INDEX_CACHE
    if _INDEX_CACHE is None or rebuild:
        _INDEX_CACHE = build_analog_index()
    return _INDEX_CACHE


# ── retrieval ───────────────────────────────────────────────────────────────────
def find_analogs(query: dict, k: int = 5, index: AnalogIndex | None = None,
                 min_sim: float = MIN_SIM) -> list[dict]:
    """Rank the index by cosine similarity to the query event.

    `query` = {asset_type, event_type, conviction:{node:signed}}. Returns up to k
    analogs sorted by similarity, each with its realised per-node forward moves and
    whether that move agreed with the QUERY's predicted direction."""
    index = build_analog_index() if index is None else index
    if not index.events:
        return []
    qvec = fingerprint(query.get("asset_type"), query.get("event_type"),
                       query.get("conviction") or {})
    q_signs = {n: int(np.sign(s)) for n, s in (query.get("conviction") or {}).items() if s}
    scored = []
    for ev in index.events:
        sim = _cosine(qvec, ev.vec)
        if sim < min_sim:
            continue
        # how each shared node moved, relative to the query's predicted direction
        node_moves = {}
        for node, qs in q_signs.items():
            o = ev.outcomes.get(node)
            if not o:
                continue
            mv = {"d1": o.get("d1"), "d5": o.get("d5"),
                  "vn1": o.get("vn1"), "vn5": o.get("vn5")}
            for h in es.HORIZONS:
                d = o.get(f"d{h}")
                mv[f"agree{h}"] = (None if d is None else bool(np.sign(d) == qs))
            node_moves[node] = mv
        scored.append({
            "published_at": ev.published_at, "title": ev.title,
            "asset_type": ev.asset_type, "event_type": ev.event_type,
            "regime": ev.regime, "similarity": round(sim, 3),
            "conviction": ev.conviction, "node_moves": node_moves,
        })
    scored.sort(key=lambda r: r["similarity"], reverse=True)
    return scored[:k]


def analog_forecast(query: dict, k: int = 8, horizon: int = 5,
                    index: AnalogIndex | None = None) -> dict:
    """Similarity-weighted per-node nowcast from the k nearest analogs.

    For each node the query claims, aggregate the analogs that ALSO moved that node:
    similarity-weighted mean realised Δ + vol-normalised Δ, and the weighted fraction
    that agreed with the query's predicted direction (an analog-grounded hit-rate).
    Distinct from the event-study regression beta — this is retrieval, not a fit."""
    index = build_analog_index() if index is None else index
    analogs = find_analogs(query, k=k, index=index)
    q_conv = query.get("conviction") or {}
    out_nodes: dict = {}
    for node, conv in q_conv.items():
        if not conv:
            continue
        qs = int(np.sign(conv))
        ws, d_acc, vn_acc, agree_acc, n = 0.0, 0.0, 0.0, 0.0, 0
        for a in analogs:
            mv = a["node_moves"].get(node)
            if not mv or mv.get(f"d{horizon}") is None:
                continue
            w = max(a["similarity"], 0.0)
            ws += w
            d_acc += w * mv[f"d{horizon}"]
            vn_acc += w * (mv.get(f"vn{horizon}") or 0.0)
            agree_acc += w * (1.0 if mv.get(f"agree{horizon}") else 0.0)
            n += 1
        if n == 0 or ws == 0:
            out_nodes[node] = {"n_analogs": 0, "pred_dir": qs, "basis": "no_analog"}
            continue
        out_nodes[node] = {
            "n_analogs": n, "pred_dir": qs,
            "mean_move": round(d_acc / ws, 4),
            "mean_vn": round(vn_acc / ws, 3),
            "analog_agree": round(agree_acc / ws, 3),    # weighted dir-agreement
            "basis": "analog",
        }
    return {"horizon": horizon, "k": k, "n_matched": len(analogs),
            "nodes": out_nodes, "analogs": analogs}


# ── headline entrypoint (extract → analogs) ─────────────────────────────────────
def score_headline_analogs(title: str, k: int = 5, horizon: int = 5,
                           provider: str = "auto", index: AnalogIndex | None = None) -> dict:
    """Headline → geo extraction → analog forecast. The dashboard / live entrypoint:
    'this event ≈ these k past events; they moved node X by Y, agreeing Z% of the time.'"""
    from research.news_impact.geo import extract as ex
    scored = ex.score_headline_geo(title, provider=provider)
    impact = scored.get("impact") or {}
    ext = scored.get("extraction") or {}
    query = {"asset_type": ext.get("asset_type"), "event_type": ext.get("event_type"),
             "conviction": impact.get("nodes") or {}}
    if not query["conviction"]:
        return {"title": title, "extraction": ext, "available": False,
                "reason": "no geo asset/impact resolved"}
    fc = analog_forecast(query, k=k, horizon=horizon, index=index)
    return {"title": title, "extraction": ext, "query": query, "available": True, **fc}


# ── LLM-narrated desk note (Sprint 10) ──────────────────────────────────────────
# The analog forecast is structured/numeric; this layer turns it into a 2-3 sentence
# desk note. It is grounded ONLY in the retrieved analogs + the graded edge map: we
# build an exact-number evidence block first, then either (a) ask a free-Groq model
# to phrase THAT block (instructed to invent no numbers), or (b) fall back to a
# deterministic template built from the same numbers. With no key and no llm_fn it
# degrades to the template — so the desk always gets a grounded note.

GROQ_NARRATE_MODEL = "openai/gpt-oss-120b"   # free tier, separate daily budget

_NODE_LABEL = {
    "brent_flat": "crude flat (Brent)", "wti_flat": "crude flat (WTI)",
    "wti_brent": "WTI–Brent", "brent_structure": "Brent structure",
    "ho_crack": "ULSD crack", "gasoil_crack": "gasoil crack",
    "rbob_crack": "RBOB crack", "regrade": "regrade",
    "brent_m1_m2": "Brent M1-M2", "brent_fly_123": "Brent fly",
}

_NARRATE_SYSTEM = (
    "You are an oil-futures desk analyst. Write a SHORT desk note (2-3 sentences) "
    "interpreting the geo-analog evidence below. Use ONLY the facts and numbers "
    "given — never invent a number, never re-round, never add a figure that is not "
    "present. Say which node read to TRUST (high agreement / a certified EDGE) and "
    "which to FADE (agreement below 50% means the analogs reversed it). End with the "
    "single-episode caveat. Plain prose — no preamble, no bullet points, no headers."
)


def _edge_nodes(query: dict, horizon: int) -> set[str]:
    """Which of the query's nodes carry a certified EDGE in the graded map (either
    horizon). Reuses event_study_geo.annotate_impact; no live regime in this path."""
    impact = {"nodes": query.get("conviction") or {}}
    at = query.get("asset_type")
    tradeable: set[str] = set()
    for h in {horizon, 1, 5}:
        try:
            ann = es.annotate_impact(impact, at, None, horizon=h)
            tradeable |= set(ann.get("tradeable_nodes") or [])
        except Exception:
            pass
    return tradeable


def _evidence(result: dict, horizon: int) -> dict:
    """Collapse an analog result into an exact-number evidence block (the only
    figures any narration may use)."""
    nodes = result.get("nodes") or {}
    analogs = result.get("analogs") or []
    query = result.get("query") or {}
    n_matched = result.get("n_matched")
    if n_matched is None:
        n_matched = len(analogs)
    top_sim = analogs[0]["similarity"] if analogs else None
    edges = _edge_nodes(query, horizon)
    rows = []
    for node, f in nodes.items():
        if f.get("basis") != "analog":
            continue
        mv, agree, n = f.get("mean_move"), f.get("analog_agree"), f.get("n_analogs")
        if mv is None or not n:
            continue
        rows.append({"node": node, "label": _NODE_LABEL.get(node, node),
                     "move": float(mv), "agree": (None if agree is None else float(agree)),
                     "n": int(n), "edge": node in edges})
    # EDGE nodes first, then by |move| — the strongest read leads
    rows.sort(key=lambda r: (r["edge"], abs(r["move"])), reverse=True)
    return {"asset_type": query.get("asset_type"), "event_type": query.get("event_type"),
            "n_matched": int(n_matched), "top_sim": top_sim, "horizon": horizon, "rows": rows}


def _facts_block(ev: dict) -> str:
    head = (f"Event: {ev['asset_type'] or 'geo'}/{ev['event_type'] or 'event'}; "
            f"{ev['n_matched']} analog(s)")
    if ev["top_sim"] is not None:
        head += f", closest similarity {ev['top_sim']:.2f}"
    lines = [head]
    for r in ev["rows"]:
        agree = "n/a" if r["agree"] is None else f"{r['agree']:.0%}"
        lines.append(f"- {r['label']}: analogs moved it {r['move']:+.2f} over "
                     f"{ev['horizon']}d, agreement {agree}, n={r['n']}"
                     + (" [certified EDGE]" if r["edge"] else " [prior]"))
    return "\n".join(lines)


def _template_note(ev: dict) -> str:
    """Deterministic, fully-grounded fallback note built from the evidence numbers."""
    if not ev["rows"]:
        return "No analog node reads to summarise for this event."
    at, et, h = ev["asset_type"] or "geo", ev["event_type"] or "event", ev["horizon"]
    sim = f", closest similarity {ev['top_sim']:.2f}" if ev["top_sim"] is not None else ""
    parts = [f"{ev['n_matched']} past {at}/{et} analog(s){sim}."]
    agree_rows = [r for r in ev["rows"] if (r["agree"] or 0) >= 0.5]
    fade_rows = [r for r in ev["rows"] if r["agree"] is not None and r["agree"] < 0.5]
    if agree_rows:
        r = agree_rows[0]
        edge = " (certified EDGE)" if r["edge"] else ""
        parts.append(f"They moved {r['label']} {r['move']:+.2f} over {h}d, agreeing "
                     f"{r['agree']:.0%} (n={r['n']}){edge} — trust this read.")
    if fade_rows:
        r = fade_rows[0]
        parts.append(f"{r['label']} reversed ({r['agree']:.0%} agreement, n={r['n']}) — fade it.")
    parts.append("Single-episode evidence (2026 Hormuz war) — read direction, not exact magnitude.")
    return " ".join(parts)


def _groq_narrate(system: str, user: str, model: str = GROQ_NARRATE_MODEL) -> str | None:
    """Free-Groq text completion. None on any failure (→ template fallback)."""
    key = os.getenv("GROQ_API_KEY", "").strip()
    if not key:
        return None
    try:
        import requests
        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"model": model, "temperature": 0.2, "max_tokens": 320,
                  "messages": [{"role": "system", "content": system},
                               {"role": "user", "content": user}]},
            timeout=30,
        )
        if resp.status_code != 200:
            return None
        content = (resp.json().get("choices") or [{}])[0].get("message", {}).get("content", "")
        return content.strip() or None
    except Exception as exc:
        log.info("Groq narrate failed (%s) — template fallback", type(exc).__name__)
        return None


def narrate(result: dict, *, horizon: int | None = None, provider: str = "auto",
            llm_fn=None) -> dict:
    """Turn an analog result into a grounded 2-3 sentence desk note.

    `result` is the dict from `score_headline_analogs` / `analog_forecast`. The note
    references ONLY the retrieved analogs' realised moves + the graded edge tags;
    numbers come from an exact evidence block, so neither path can invent figures.
    `provider="template"` forces the deterministic note (no LLM). `llm_fn(system,
    user)->str|None` is injectable (tests / a non-Groq LLM); otherwise free Groq is
    used when keyed, else it degrades gracefully to the template."""
    if not result or not result.get("available", True):
        return {"available": False, "source": "none",
                "note": (result or {}).get("reason") or "No geo impact resolved — no analogs to narrate."}
    h = int(horizon or result.get("horizon") or 5)
    ev = _evidence(result, h)
    if not ev["rows"]:
        return {"available": False, "source": "none", "evidence": ev,
                "note": "No analog node reads to narrate for this event."}

    note, source = _template_note(ev), "template"
    if provider != "template":
        user = _facts_block(ev) + "\n\nWrite the desk note now."
        out = (llm_fn(_NARRATE_SYSTEM, user) if llm_fn else
               _groq_narrate(_NARRATE_SYSTEM, user))
        if out:
            note, source = out.strip(), ("llm" if llm_fn else "groq")
    return {"available": True, "source": source, "note": note,
            "horizon": h, "evidence": ev}


# ── standalone ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    from research.news_impact.geo import extract as _ex
    _ex.load_env()

    idx = build_analog_index()
    print(f"analog index: {len(idx)} graded geo events")
    if not idx.events:
        print("(no events — corpus or /Data absent)"); raise SystemExit(0)

    demos = [
        "Iran closes Strait of Hormuz to oil tankers after airstrikes",
        "Drone strike sparks fire at major Saudi refinery",
        "Strait of Hormuz reopens as ceasefire holds, crude tumbles",
    ]
    for title in demos:
        print(f"\n=== {title}")
        res = score_headline_analogs(title, k=4, horizon=5, provider="fallback")
        if not res.get("available"):
            print("  (no geo impact resolved)"); continue
        q = res["query"]
        print(f"  query: {q['asset_type']}/{q['event_type']}  "
              f"nodes={ {n: round(v,1) for n,v in q['conviction'].items()} }")
        for n, f in res["nodes"].items():
            if f.get("basis") == "analog":
                print(f"    {n:15s} {f['n_analogs']} analogs → mean Δ{res['horizon']}d="
                      f"{f['mean_move']:+.3f}  agree={f['analog_agree']:.0%}")
        print("  nearest analogs:")
        for a in res["analogs"][:4]:
            print(f"    [{a['similarity']:.2f}] {a['asset_type']}/{a['event_type']} "
                  f"{a['published_at'][:10]}  {str(a['title'])[:54]}")
        nb = narrate(res, provider="auto")     # Groq if keyed, else template
        print(f"  desk note [{nb['source']}]: {nb['note']}")
