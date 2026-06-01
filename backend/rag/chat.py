"""
RAG chat orchestrator.

Combines (1) BM25 retrieval over the Oil Macro Trading curriculum with
(2) the live PULSE data snapshot and (3) optional Ollama LLM generation
to answer trader-style questions about why markets are moving, what
indicators mean, and how trades work.

If Ollama (http://localhost:11434) is not running, falls back to an
extractive answer that quotes the top retrieved chunks verbatim — the
chat still works, it just looks more like a curated FAQ than a chat.

Public function:
  answer(question: str, snapshot: dict | None = None) -> dict
"""

from __future__ import annotations

import logging
import re
from typing import Optional

log = logging.getLogger("pulse.rag.chat")


def _format_snapshot(snap: Optional[dict]) -> str:
    """Convert the live PULSE snapshot into a compact prompt-ready string."""
    if not snap:
        return "(no live data attached)"
    lines: list[str] = []

    prices = snap.get("prices") or {}
    brent = prices.get("brent") or {}
    wti   = prices.get("wti")   or {}
    hh    = prices.get("henry_hub") or {}
    if brent.get("price") is not None:
        lines.append(f"BRENT spot: ${brent['price']:.2f} ({brent.get('change_pct', 0):+.2f}%)")
    if wti.get("price") is not None:
        lines.append(f"WTI spot:   ${wti['price']:.2f} ({wti.get('change_pct', 0):+.2f}%)")
    if hh.get("price") is not None:
        lines.append(f"HH gas:     ${hh['price']:.3f} ({hh.get('change_pct', 0):+.2f}%)")

    signal = snap.get("signal") or {}
    for asset_key, label in [("brent", "Brent"), ("wti", "WTI"), ("henry_hub", "NatGas")]:
        s = signal.get(asset_key)
        if isinstance(s, dict) and s.get("score") is not None:
            lines.append(f"PULSE {label} signal: {s.get('signal','—')} score {s['score']:+.2f}/2 conviction {s.get('conviction','—')}")
            ind = s.get("indicators") or []
            if ind:
                top = sorted(ind, key=lambda i: abs(i.get("score", 0) * i.get("weight", 0)), reverse=True)[:3]
                for it in top:
                    lines.append(f"  · {it.get('name')}: {it.get('reason','')} (score {it.get('score', 0):+.0f})")

    fv = snap.get("fair_value") or {}
    brent_fv = fv.get("brent") or {}
    if brent_fv.get("fair_value") is not None and brent_fv.get("live_price") is not None:
        lines.append(f"Brent fair value: ${brent_fv['fair_value']:.2f} (spot ${brent_fv['live_price']:.2f}, dev {brent_fv.get('deviation_pct', 0):+.1f}%) — {brent_fv.get('deviation_label','')}")

    curve = snap.get("curve") or {}
    bc = (curve.get("brent") or {}).get("contracts") or []
    if len(bc) >= 2 and bc[0].get("price") and bc[1].get("price"):
        spread = bc[0]["price"] - bc[1]["price"]
        struct = "backwardation" if spread > 0.1 else "contango" if spread < -0.1 else "flat"
        lines.append(f"Brent M1-M2: {spread:+.2f} ({struct})")

    cracks = (snap.get("cracks") or {}).get("crack_spreads") or {}
    c321 = cracks.get("crack_321") or {}
    if c321.get("value") is not None:
        lines.append(f"3-2-1 crack: ${c321['value']:.2f}/bbl ({c321.get('signal','')} vs 1y avg ${c321.get('avg_1y',0):.1f})")

    fund = snap.get("fundamentals") or {}
    inv = (fund.get("inventory") or {}).get("crude_stocks") or {}
    if inv.get("deviation_pct") is not None:
        lines.append(f"US crude stocks vs seasonal: {inv['deviation_pct']:+.1f}% ({inv.get('label','')})")
    geo = fund.get("geo_risk") or {}
    if geo.get("index") is not None:
        lines.append(f"Geo risk index: {geo['index']:.0f}/100 ({geo.get('label','')})")
    cot = (fund.get("cot") or {}).get("crude_oil") or {}
    if cot.get("percentile") is not None:
        lines.append(f"CFTC COT crude (managed money): {cot['percentile']:.0f}%ile ({cot.get('label','')})")

    fcov = snap.get("forward_cover") or {}
    if fcov.get("current") is not None:
        lines.append(f"Days of forward cover: {fcov['current']:.1f}d (critical <54d)")

    return "\n".join(lines) if lines else "(snapshot pending warm-up)"


def _build_prompt(question: str, chunks: list[dict], snapshot_str: str) -> str:
    """Compose the LLM prompt with system instructions + retrieved + live data."""
    sources_str = ""
    for i, c in enumerate(chunks, 1):
        ch = f"Ch{c['chapter']}" if c.get("chapter") else "EXP"
        sources_str += f"[{i}] {ch} — {c.get('chapter_title','')} / {c.get('section','')}\n{c['text']}\n\n"

    return (
        "You are PULSE — a senior oil & energy trading desk strategist with 20+ years on the "
        "physical, paper, and derivatives sides. You think like a working trader, not an academic. "
        "You speak the language of the desk: spare capacity, contango / backwardation, calendar "
        "spreads, OSPs, K-factor, dated Brent, 3-2-1 cracks, COT positioning percentile, OVX skew, "
        "tank-tops at Cushing, EFP, TAS orders, Worldscale, Suezmax / VLCC freight, IMO 2020 sulfur "
        "spec, Houthi diversions, Hormuz transit math, SPR drawdown limits, G7 price cap, and the "
        "Brent-WTI logistics tell.\n\n"
        "ANSWERING RULES:\n"
        "1. Anchor every claim in either (a) the live PULSE snapshot, (b) the curriculum excerpts "
        "   (cited inline like [Ch8] for chapter-numbered hits or [EXP] for expert-knowledge hits), "
        "   or (c) a historical analogue you know cold (2008, 2014, 2016 Vienna, 2020 negative WTI, "
        "   2022 Russia + SPR, 2024 Houthi).\n"
        "2. Always quote real numbers from the snapshot when relevant — prices, percentiles, "
        "   percentages, deviations. No vague 'oil is high' answers.\n"
        "3. When the trader asks 'why is X moving', walk the supply / demand / positioning / "
        "   macro / geopolitical hierarchy and tell them which lever is dominant right now.\n"
        "4. When asked about a spread or strategy, give the trade structure (long M1 / short M2, "
        "   sizing rule of thumb, where the stop sits, when to exit) — not just the definition.\n"
        "5. Reading habits: term structure (M1-M2) tells you tightness, crack spreads tell you "
        "   downstream pull, COT percentile tells you positioning crowding, OVX tells you fear, "
        "   geo-risk index tells you tail premium. Reference these structurally.\n"
        "6. If the question is conceptual (what is contango, what's a crack spread), still ground "
        "   the answer with the CURRENT snapshot example. Theory + today's print.\n"
        "7. 150–220 words. Tight, professional, no fluff. Use bold for key terms.\n\n"
        f"=== LIVE PULSE SNAPSHOT ===\n{snapshot_str}\n\n"
        f"=== KNOWLEDGE BASE EXCERPTS (top {len(chunks)} BM25 hits — curriculum + expert) ===\n"
        f"{sources_str}\n"
        f"=== TRADER QUESTION ===\n{question}\n\n"
        "=== ANSWER ===\n"
    )


def _ollama_generate(prompt: str, model: str = "llama3", timeout: int = 30) -> Optional[str]:
    """Call local Ollama. Returns None on failure."""
    try:
        import requests
        resp = requests.post(
            "http://localhost:11434/api/generate",
            json={"model": model, "prompt": prompt, "stream": False},
            timeout=timeout,
        )
        resp.raise_for_status()
        text = (resp.json().get("response") or "").strip()
        return text or None
    except Exception as exc:
        log.info("Ollama unavailable (%s) — falling back to extractive answer", type(exc).__name__)
        return None


def _extractive_fallback(question: str, chunks: list[dict], snapshot_str: str) -> str:
    """When Ollama is offline, build a useful answer by quoting the top chunks."""
    if not chunks:
        return (
            "I couldn't find anything in the curriculum that matches that question directly. "
            "Try a more specific topic — e.g. 'what is backwardation', 'how does the 3-2-1 crack work', "
            "or 'why does Hormuz matter'."
        )

    # Find the first sentence in the top chunk that contains a query keyword
    q_terms = set(re.findall(r"[a-zA-Z]{3,}", question.lower()))
    top = chunks[0]
    sentences = re.split(r"(?<=[.!?])\s+", top["text"])
    best = None
    for s in sentences:
        s_low = s.lower()
        if any(t in s_low for t in q_terms):
            best = s.strip()
            break
    if best is None:
        best = sentences[0] if sentences else top["text"][:240]

    out = (
        f"**From {('Chapter ' + str(top['chapter'])) if top.get('chapter') else 'the curriculum'}"
        f" — {top.get('chapter_title','')} / {top.get('section','')}:**\n\n"
        f"{best}\n\n"
        f"*Top {len(chunks)} curriculum hits attached as citations. "
        f"Ollama (local llama3 at :11434) is offline, so this is extractive only — "
        f"start `ollama serve` + `ollama pull llama3` for full chat.*"
    )
    if snapshot_str.strip() and "snapshot pending" not in snapshot_str:
        out += "\n\n**Live snapshot:**\n" + snapshot_str
    return out


def answer(question: str, snapshot: Optional[dict] = None, k: int = 8) -> dict:
    """
    Answer a free-form trader question using curriculum RAG + live snapshot
    + optional Ollama LLM.

    Returns
    -------
    {
      "answer":      str (markdown),
      "citations":   [{chapter, chapter_title, section, score, text}, ...],
      "source":      "ollama" | "extractive",
      "snapshot_used":bool,
    }
    """
    from rag.retrieval import search

    question = (question or "").strip()
    if not question:
        return {"answer": "Ask me anything about oil macro — markets, fundamentals, contract specs, the curriculum.",
                "citations": [], "source": "extractive", "snapshot_used": False}

    chunks = search(question, k=k)
    snap_str = _format_snapshot(snapshot)

    if chunks:
        prompt = _build_prompt(question, chunks, snap_str)
        text = _ollama_generate(prompt)
        if text:
            return {
                "answer":    text,
                "citations": [{
                    "chapter":       c.get("chapter"),
                    "chapter_title": c.get("chapter_title"),
                    "section":       c.get("section"),
                    "score":         c.get("score"),
                    "text":          c["text"][:280] + ("…" if len(c["text"]) > 280 else ""),
                } for c in chunks],
                "source":         "ollama",
                "snapshot_used":  bool(snapshot),
            }

    return {
        "answer":    _extractive_fallback(question, chunks, snap_str),
        "citations": [{
            "chapter":       c.get("chapter"),
            "chapter_title": c.get("chapter_title"),
            "section":       c.get("section"),
            "score":         c.get("score"),
            "text":          c["text"][:280] + ("…" if len(c["text"]) > 280 else ""),
        } for c in chunks],
        "source":         "extractive",
        "snapshot_used":  bool(snapshot),
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import json
    for q in [
        "explain backwardation",
        "what is the 3-2-1 crack spread",
        "why does Hormuz matter for oil",
        "what's the difference between WTI and Brent",
    ]:
        print(f"\n=== Q: {q} ===")
        r = answer(q)
        print(f"[{r['source']}]")
        print(r["answer"][:400])
        print(f"... ({len(r['citations'])} citations)")
