"""
Factor classifier — map an oil headline to one price-driving FACTOR.
====================================================================

The taxonomy is aligned to PULSE's existing signal vocabulary (Curve / Inventory
/ COT / DXY / Geo / Weather …) so the news factor a headline carries lines up
with the rest of the dashboard.

Primary path: Groq zero-shot (free-tier llama-3.3-70b, JSON mode) classifies a
batch of headlines in one call — no labelled training data needed. When Groq is
unavailable (no key / error / unknown label) we fall back to a deterministic
keyword classifier, so classification never hard-fails. Every result carries a
``source`` ("groq" | "keyword") and a confidence so downstream can weight it.

Public API
----------
    FACTORS                              ordered {label: description}
    classify_headlines(titles)           -> list[{factor, confidence, source}]
    classify_corpus(limit, persist=True) -> dict   (pull unclassified -> classify -> save)
    keyword_factor(title)                -> (factor, confidence)
"""

from __future__ import annotations

import json
import os
import re
import logging

log = logging.getLogger("pulse.news_impact.classify")

# ── the 8 price-driving factors (+ NOISE catch-all) ───────────────────────────
FACTORS: dict[str, str] = {
    "SUPPLY_OPEC":        "OPEC+ policy, quotas, compliance, production cuts/hikes, non-OPEC supply",
    "GEOPOLITICAL":       "war, sanctions, attacks on infrastructure, chokepoint/shipping disruption, supply outages",
    "INVENTORY":          "EIA/API stock builds & draws, Cushing, days-of-cover, storage",
    "DEMAND_MACRO":       "global growth, China demand, recession, jobs/PMI, demand outlook, EV/transition demand",
    "MONETARY_DOLLAR":    "Fed/central-bank rates, inflation/CPI, the US dollar, bond yields, risk sentiment",
    "REFINING_PRODUCTS":  "refinery runs/outages, crack spreads, gasoline/distillate, product margins",
    "WEATHER":            "hurricanes, cold snaps, heatwaves, HDD/CDD, weather-driven supply or demand",
    "POSITIONING":        "fund flows, COT positioning, options/gamma, technical levels, expiry/settlement",
    "NOISE":              "no clear oil-price driver; corporate/ESG/general coverage with negligible price impact",
}
VALID = set(FACTORS)

# ── deterministic keyword fallback ────────────────────────────────────────────
# Order matters: first matching factor wins (most specific / highest-signal first).
_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("GEOPOLITICAL", ("hormuz", "strait", "tanker", "missile", "drone", "attack", "strike",
                      "sanction", "embargo", "war", "houthi", "red sea", "blockade",
                      "pipeline", "force majeure", "invasion", "ceasefire", "conflict")),
    ("SUPPLY_OPEC",  ("opec", "opec+", "production cut", "output cut", "production hike", "quota",
                      "compliance", "saudi", "aramco", "spare capacity", "barrels per day", "spr")),
    ("INVENTORY",    ("inventory", "stockpile", "stocks", "eia", "api", "cushing", "draw",
                      "build", "days of cover", "storage")),
    ("REFINING_PRODUCTS", ("refinery", "refining", "crack spread", "gasoline", "diesel", "distillate",
                           "heating oil", "jet fuel", "margins", "throughput", "run cuts")),
    ("WEATHER",      ("hurricane", "storm", "cold snap", "heatwave", "freeze", "polar vortex",
                      "weather", "hdd", "cdd", "gulf of mexico storm")),
    ("MONETARY_DOLLAR", ("federal reserve", "fed ", "rate cut", "rate hike", "interest rate",
                         "inflation", "cpi", "dollar", "dxy", "treasury", "yield", "recession risk")),
    ("DEMAND_MACRO", ("demand", "china", "growth", "gdp", "pmi", "jobs", "consumption",
                      "ev adoption", "transition", "slowdown", "stimulus")),
    ("POSITIONING",  ("cot", "positioning", "hedge fund", "speculator", "net long", "net short",
                      "options", "gamma", "open interest", "expiry", "settlement", "technical")),
]


def _kw_hit(text: str, kw: str) -> bool:
    """Whole-word match with an optional inflection suffix: 'war' doesn't fire
    inside 'award' and 'spr' doesn't fire inside 'spread', yet 'sanction' still
    catches 'sanctions' and 'attack' catches 'attacked'."""
    return re.search(r"\b" + re.escape(kw) + r"(?:s|es|d|ed|ing)?\b", text) is not None


def keyword_factor(title: str) -> tuple[str, float]:
    """Deterministic fallback. Returns (factor, confidence). confidence 0.5 on a
    keyword hit (lower than Groq's), 0.3 for the NOISE default."""
    t = (title or "").lower()
    for factor, kws in _KEYWORDS:
        if any(_kw_hit(t, k) for k in kws):
            return factor, 0.5
    return "NOISE", 0.3


# ── Groq zero-shot ────────────────────────────────────────────────────────────

def _groq_classify_batch(titles: list, retries: int = 4) -> list | None:
    """
    Classify a batch of headlines in one Groq call (JSON mode). Returns a list
    aligned to ``titles`` of {factor, confidence} dicts, or None if Groq is
    unavailable / the response can't be parsed. Unknown labels are dropped to
    None so the caller can fall back per-headline.

    Free-tier Groq rate-limits (per-minute request/token caps) surface as HTTP
    429; we honour the ``retry-after`` header with bounded exponential backoff so
    a bulk re-classify doesn't silently fall back to keywords on every throttle.
    A 429 whose message names the *daily* cap is terminal (no point retrying).
    """
    key = os.getenv("GROQ_API_KEY", "").strip()
    if not key or not titles:
        return None
    taxonomy = "\n".join(f"- {k}: {v}" for k, v in FACTORS.items())
    numbered = "\n".join(f"{i}. {t}" for i, t in enumerate(titles))
    system = (
        "You are an oil-market analyst. Classify each news headline into exactly ONE "
        "factor — the dominant driver of crude oil prices it concerns. Factors:\n"
        f"{taxonomy}\n"
        'Respond ONLY with JSON: {"items":[{"i":<index>,"factor":"<LABEL>",'
        '"confidence":<0..1>}]}. Use the exact LABELs above. confidence = how '
        "clearly the headline maps to that factor."
    )
    import time
    import requests
    for attempt in range(retries + 1):
        try:
            resp = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={
                    "model": os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": numbered},
                    ],
                    "temperature": 0.0,
                    "max_tokens": 1500,
                    "response_format": {"type": "json_object"},
                },
                timeout=30,
            )
            if resp.status_code == 429:
                body = resp.text.lower()
                if "per day" in body or "daily" in body or "tokens per day" in body:
                    log.info("Groq daily token cap reached — stopping Groq classification")
                    return None
                if attempt >= retries:
                    log.info("Groq 429 — out of retries, keyword fallback")
                    return None
                wait = float(resp.headers.get("retry-after", 0)) or (2 ** attempt * 3)
                wait = min(wait, 35)   # TPM windows reset within ~30s; cap the wait
                log.info("Groq 429 — waiting %.1fs (attempt %d/%d)", wait, attempt + 1, retries)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            content = (resp.json().get("choices") or [{}])[0].get("message", {}).get("content", "")
            parsed = json.loads(content)
            items = parsed.get("items") if isinstance(parsed, dict) else parsed
            if not isinstance(items, list):
                return None
            out: list = [None] * len(titles)
            for it in items:
                try:
                    i = int(it.get("i"))
                    factor = str(it.get("factor", "")).upper().strip()
                    conf = float(it.get("confidence", 0.6))
                except (TypeError, ValueError):
                    continue
                if 0 <= i < len(titles) and factor in VALID:
                    out[i] = {"factor": factor, "confidence": max(0.0, min(1.0, conf))}
            return out
        except Exception as exc:
            log.info("Groq classify failed (%s) — keyword fallback", type(exc).__name__)
            return None
    return None


def classify_headlines(titles: list) -> list:
    """
    Classify a batch. Tries Groq once for the whole batch; any headline Groq
    didn't return (or when Groq is unavailable) falls back to the keyword
    classifier. Always returns one {factor, confidence, source} per input.
    """
    if not titles:
        return []
    groq = _groq_classify_batch(titles)
    out = []
    for i, title in enumerate(titles):
        g = groq[i] if groq and i < len(groq) else None
        if g:
            out.append({**g, "source": "groq"})
        else:
            f, c = keyword_factor(title)
            out.append({"factor": f, "confidence": c, "source": "keyword"})
    return out


def classify_corpus(limit: int = 200, persist: bool = True) -> dict:
    """
    Pull unclassified headlines from the corpus, classify them, and (by default)
    persist the factor back. Returns a summary {classified, by_factor, by_source}.
    """
    from . import corpus

    rows = corpus.unclassified(limit=limit)
    if not rows:
        return {"classified": 0, "by_factor": {}, "by_source": {}}
    titles = [r["title"] for r in rows]
    results = classify_headlines(titles)
    by_factor: dict[str, int] = {}
    by_source: dict[str, int] = {}
    for row, res in zip(rows, results):
        by_factor[res["factor"]] = by_factor.get(res["factor"], 0) + 1
        by_source[res["source"]] = by_source.get(res["source"], 0) + 1
        if persist:
            corpus.set_classification(row["url"], res["factor"], res["confidence"])
    return {"classified": len(rows), "by_factor": by_factor, "by_source": by_source}


def reclassify_factor(target_factor: str = "NOISE", *, batch_size: int = 50,
                      sleep_between: float = 2.5, max_batches: int | None = None) -> dict:
    """
    Re-run Groq classification over headlines CURRENTLY labelled ``target_factor``
    and overwrite the stored factor. The point of Sprint 3: the keyword fallback
    over-assigns NOISE (no keyword hit ⇒ NOISE), and the broad theme pull dumps
    non-oil news into GEOPOLITICAL — 70b fixes both.

    Groq-only on purpose: if a batch fails (rate limit / parse), we **skip** it
    rather than fall back to keywords (which would just re-confirm NOISE and burn
    the row). Naturally resumable — rows that move out of ``target_factor`` drop
    out of the next run's queue. Returns a summary incl. how many moved out.
    """
    import time
    from . import corpus

    rows = [r for r in corpus.recent(limit=10_000_000, factor=target_factor) if r.get("title")]
    summary = {"target": target_factor, "considered": len(rows), "reclassified": 0,
               "moved_out": 0, "by_factor": {}, "batches_ok": 0, "batches_failed": 0}
    for bi, start in enumerate(range(0, len(rows), batch_size)):
        if max_batches is not None and bi >= max_batches:
            break
        chunk = rows[start:start + batch_size]
        res = _groq_classify_batch([r["title"] for r in chunk])
        if res is None:
            summary["batches_failed"] += 1
            time.sleep(sleep_between)
            continue
        summary["batches_ok"] += 1
        for r, g in zip(chunk, res):
            if not g:
                continue
            corpus.set_classification(r["url"], g["factor"], g["confidence"])
            summary["reclassified"] += 1
            summary["by_factor"][g["factor"]] = summary["by_factor"].get(g["factor"], 0) + 1
            if g["factor"] != target_factor:
                summary["moved_out"] += 1
        time.sleep(sleep_between)
    return summary
