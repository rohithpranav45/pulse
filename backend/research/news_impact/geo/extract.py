"""
Geo-extraction — headline → {assets, event_type, severity} → node impact.
=========================================================================

Turns a free-text headline into the structured geo event the impact_map scores:
which registry ASSET(s) it names, the EVENT verb, and a SEVERITY. Two paths:

  * Claude (primary)  — `messages.parse()` with a Pydantic schema. Live scoring
    on Haiku 4.5 (cheap/fast); the one-time corpus backfill should run on Opus 4.8
    via the Batches API (50% off) — see `extract_headlines(..., model=)`. The model
    returns registry asset ids + the raw location strings + event/severity.
  * Deterministic fallback — registry alias resolution (`registry.resolve`) + an
    event/severity keyword pass. Always available (no API key needed), so the
    module never hard-fails and the tests are hermetic. Mirrors classify.py.

Whatever the path, asset ids are validated against the registry and unioned with a
registry keyword resolve over the title — the LLM proposes, the registry disposes.

Public API
----------
  GeoExtraction                         the per-headline record (Pydantic)
  extract_headline(title, snippet=)     -> GeoExtraction
  extract_headlines(titles, model=)     -> list[GeoExtraction]
  score_headline_geo(title, ...)        -> {extraction, impact}   (extract + impact_map)

Run standalone:  python backend/research/news_impact/geo/extract.py
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sys
import time
from pathlib import Path

from pydantic import BaseModel, Field

_BACKEND = Path(__file__).resolve().parents[3]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from research.news_impact.geo import registry as reg          # noqa: E402
from research.news_impact.geo import impact_map               # noqa: E402

log = logging.getLogger("pulse.news_impact.geo.extract")


def load_env() -> None:
    """Load .env so GROQ/ANTHROPIC keys are visible — call this in standalone /
    backfill entrypoints ONLY (never at import, so tests stay hermetic)."""
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except Exception:
        pass


# Provider models. Groq (free tier) is the DEFAULT extractor — already keyed in
# this project and capable enough for the schema; Claude is optional/paid.
# gpt-oss-120b matches llama-3.3-70b on the closure-vs-reopen polarity (verified)
# and has a SEPARATE free daily-token budget — 70B's 100k TPD is easily exhausted
# by a corpus re-grade, so this is the more robust default for the geo extractor.
GROQ_MODEL = "openai/gpt-oss-120b"
LIVE_MODEL = "claude-haiku-4-5"      # Claude live (optional, paid)
BACKFILL_MODEL = "claude-opus-4-8"   # Claude batch backfill (optional, paid)
_SEVERITIES = ("minor", "moderate", "major", "severe")

# Extraction cache (so re-grading never re-calls the LLM): title-hash -> record.
_GEO_CACHE = Path(__file__).parent.parent.parent.parent / "data" / "research" / \
    "news_impact" / "geo_extractions.json"

# Cheap high-recall geo prefilter — only candidates are sent to the LLM, so the
# free Groq budget is spent where it matters.
_GEO_FACTORS = {"GEOPOLITICAL", "SUPPLY_OPEC", "REFINING_PRODUCTS", "INVENTORY"}
_GEO_NOUNS = (
    "refinery", "refineries", "refining", "pipeline", "tanker", "vessel", "cargo",
    "strait", "canal", "terminal", "oilfield", "oil field", "port", "opec", "sanction",
    "embargo", "chokepoint", "crude", "barrel", "barrels", "output", "production",
    "supply", "export", "shipment", "platform", "rig", "field", "outage", "drone",
    "missile", "attack", "blockade", "houthi", "force majeure",
)


# ── the record ────────────────────────────────────────────────────────────────
class GeoExtraction(BaseModel):
    is_oil_relevant: bool = True
    asset_ids: list[str] = Field(default_factory=list)
    raw_locations: list[str] = Field(default_factory=list)
    asset_type: str | None = None
    event_type: str | None = None
    severity: str = "moderate"
    capacity_affected_mbd: float | None = None
    confidence: float = 0.5
    source: str = "fallback"          # "claude" | "fallback"
    rationale: str = ""


# ── deterministic fallback: event + severity keyword passes ───────────────────
# Order matters — first match wins. Attack/military patterns precede the bare
# labour "strike" so "drone strike" ≠ a walkout.
_EVENT_PATTERNS: list[tuple[str, tuple[str, ...]]] = [
    ("attack",        ("drone strike", "missile", "air strike", "airstrike", "attacked",
                       "attack on", "shelled", "bombed", "struck by", "drone")),
    ("fire",          ("fire", "ablaze", "blaze")),
    ("explosion",     ("explosion", "blast", "exploded")),
    ("opec_cut",      ("production cut", "output cut", "voluntary cut", "deeper cut",
                       "quota cut", "supply cut", "cut output", "cut production")),
    ("opec_hike",     ("production hike", "output increase", "raise output", "boost production",
                       "unwind cuts", "increase output", "hike output", "ramp up output")),
    ("sanction",      ("sanction", "embargo", "price cap", "export ban", "import ban")),
    ("force_majeure", ("force majeure", "declares fm")),
    ("blockage",      ("blocked", "blockade", "seized", "impassable", "grounded",
                       "stuck", "diverted", "rerouted", "reroute")),
    ("closure",       ("closed", "closure", "shut the", "suspend transit")),
    ("strike",        ("workers strike", "labour strike", "labor strike", "walkout",
                       "industrial action", "union strike", "strike action")),
    ("outage",        ("outage", "shutdown", "shut down", "halt", "halted", "offline",
                       "disrupted", "disruption", "suspended", "knocked out", "shut")),
    ("restart",       ("restart", "resume", "restored", "reopened", "back online",
                       "ramps up", "ramp up")),
    ("expansion",     ("expansion", "new capacity", "commissioned", "startup", "start-up")),
]

_SEVERITY_PATTERNS: list[tuple[str, tuple[str, ...]]] = [
    ("severe", ("massive", "complete", "entire", "full shutdown", "fully", "severe",
                "biggest", "total", "catastrophic")),
    ("major",  ("major", "significant", "large", "substantial", "extensive")),
    ("minor",  ("minor", "small", "partial", "brief", "limited", "temporary")),
]


def _kw(text: str, kw: str) -> bool:
    """Whole-phrase match with a light inflectional suffix on the final word, so
    'resume' catches 'resumes', 'halt' catches 'halted', 'cut' catches 'cuts'."""
    return re.search(r"(?<!\w)" + re.escape(kw) + r"(?:s|es|d|ed|ing)?(?!\w)", text) is not None


def _detect_event(text: str) -> str | None:
    for ev, pats in _EVENT_PATTERNS:
        if any(_kw(text, p) for p in pats):
            return ev
    return None


def _detect_severity(text: str) -> str:
    for sev, pats in _SEVERITY_PATTERNS:
        if any(_kw(text, p) for p in pats):
            return sev
    return "moderate"


def _resolve_assets(text: str, extra_ids: list[str] | None = None) -> list[reg.Asset]:
    """Union of registry-validated extra ids (from the LLM) + a named keyword resolve;
    falls back to the GENERIC (unnamed-asset) index only when nothing named matched."""
    out: dict[str, reg.Asset] = {}
    for a in reg.resolve(text):
        out[a.id] = a
    for aid in (extra_ids or []):
        a = reg.by_id(aid)
        if a:
            out.setdefault(a.id, a)
    if not out:
        for a in reg.resolve_generic(text):
            out[a.id] = a
    return list(out.values())


def _fallback_extract(title: str) -> GeoExtraction:
    t = (title or "").lower()
    assets = _resolve_assets(title)
    event = _detect_event(t)
    sev = _detect_severity(t)
    # OPEC member + bare "cut"/"hike" without the compound phrase
    if event is None and any(a.id == "opec" for a in assets):
        if _kw(t, "cut") or _kw(t, "cuts"):
            event = "opec_cut"
        elif _kw(t, "hike") or _kw(t, "raise") or _kw(t, "increase"):
            event = "opec_hike"
    dominant_type = assets[0].type if assets else None
    conf = 0.55 if (assets and event) else (0.4 if assets else 0.2)
    return GeoExtraction(
        is_oil_relevant=bool(assets),
        asset_ids=[a.id for a in assets],
        raw_locations=[a.name for a in assets],
        asset_type=dominant_type,
        event_type=event,
        severity=sev,
        confidence=conf,
        source="fallback",
        rationale=("keyword/registry resolve"
                   if assets else "no registry asset matched"),
    )


# ── Claude path (primary; lazy import so the module loads without the SDK) ─────
class _GeoBatch(BaseModel):
    items: list[GeoExtraction]


def _registry_catalogue() -> str:
    return "\n".join(f"- {a.id}: {a.name} ({a.type}, {a.region})" for a in reg.all_assets())


def _claude_extract_batch(titles: list[str], model: str) -> list[GeoExtraction] | None:
    """One structured-output call labelling a batch. None on any failure (→ fallback).
    Validates returned asset ids against the registry; never trusts the model blind."""
    if not os.getenv("ANTHROPIC_API_KEY", "").strip() or not titles:
        return None
    try:
        import anthropic
    except Exception:
        log.info("anthropic SDK not installed — using deterministic fallback")
        return None

    system = (
        "You are an oil-market geospatial analyst. For each headline, identify the "
        "physical oil asset(s) it concerns and the event affecting throughput.\n\n"
        "Choose asset ids ONLY from this registry (use the id; [] if none apply):\n"
        f"{_registry_catalogue()}\n\n"
        f"event_type ∈ {sorted(reg.EVENT_TYPES)} (or null if no throughput event).\n"
        f"asset_type ∈ {sorted(reg.ASSET_TYPES)}. severity ∈ {list(_SEVERITIES)}.\n"
        "Also return raw_locations (the location/asset phrases you saw, verbatim) so "
        "unmatched names can be resolved downstream. is_oil_relevant=false for "
        "non-oil/corporate/general news. Return one item per headline, in order."
    )
    numbered = "\n".join(f"{i}. {t}" for i, t in enumerate(titles))
    try:
        client = anthropic.Anthropic()
        resp = client.messages.parse(
            model=model, max_tokens=4000,
            system=system,
            messages=[{"role": "user", "content": numbered}],
            output_format=_GeoBatch,
        )
        items = resp.parsed_output.items
    except Exception as exc:
        log.info("Claude geo-extract failed (%s) — fallback", type(exc).__name__)
        return None
    if len(items) != len(titles):
        log.info("Claude geo-extract count mismatch (%d≠%d) — fallback",
                 len(items), len(titles))
        return None
    return [_finalize_item(t, it, "claude") for t, it in zip(titles, items)]


def _finalize_item(title: str, it: GeoExtraction, source: str) -> GeoExtraction:
    """Validate an LLM record against the registry, union with a keyword resolve,
    and normalise event/severity. The LLM proposes; the registry disposes."""
    valid = [aid for aid in it.asset_ids if reg.by_id(aid)]
    assets = _resolve_assets(" ".join([title, *it.raw_locations]), valid)
    it.asset_ids = [a.id for a in assets]
    it.raw_locations = it.raw_locations or [a.name for a in assets]
    it.asset_type = it.asset_type or (assets[0].type if assets else None)
    if it.severity not in _SEVERITIES:
        it.severity = "moderate"
    if it.event_type not in reg.EVENT_TYPES:
        it.event_type = None
    it.is_oil_relevant = bool(it.is_oil_relevant and it.asset_ids)
    it.source = source
    return it


# ── Groq path (FREE tier — the default extractor) ─────────────────────────────
def _registry_catalogue_compact() -> str:
    return "; ".join(f"{a.id}={a.name}" for a in reg.all_assets())


def _groq_extract_batch(titles: list[str], model: str = GROQ_MODEL,
                        retries: int = 4) -> list[GeoExtraction] | None:
    """Batch geo-extraction via Groq JSON mode (free tier). Mirrors
    classify._groq_classify_batch: 429 backoff + daily-cap detection. None on any
    failure → caller falls back. Returns one record per title, in order."""
    key = os.getenv("GROQ_API_KEY", "").strip()
    if not key or not titles:
        return None
    import requests
    system = (
        "You are an oil-market geospatial analyst. For each headline pick the oil "
        "ASSET id(s) it concerns and the throughput EVENT. Asset ids (id=name):\n"
        f"{_registry_catalogue_compact()}\n"
        f"event ∈ {sorted(reg.EVENT_TYPES)} or null. atype ∈ {sorted(reg.ASSET_TYPES)} "
        f"or null. sev ∈ {list(_SEVERITIES)}.\n"
        'Respond ONLY JSON: {"items":[{"i":<idx>,"oil":<bool>,"assets":[<ids>],'
        '"locs":[<verbatim place phrases>],"atype":<str|null>,"event":<str|null>,'
        '"sev":<str>,"conf":<0..1>}]}. oil=false for non-oil news (assets:[]). '
        "Use ONLY ids from the list; put unmatched names in locs."
    )
    numbered = "\n".join(f"{i}. {t}" for i, t in enumerate(titles))
    for attempt in range(retries + 1):
        try:
            resp = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={"model": model, "temperature": 0.0, "max_tokens": 3000,
                      "response_format": {"type": "json_object"},
                      "messages": [{"role": "system", "content": system},
                                   {"role": "user", "content": numbered}]},
                timeout=45,
            )
            if resp.status_code == 429:
                body = resp.text.lower()
                if "per day" in body or "tokens per day" in body or "daily" in body:
                    log.info("Groq daily cap reached — stopping geo-extract")
                    return None
                if attempt >= retries:
                    return None
                wait = min(float(resp.headers.get("retry-after", 0)) or (2 ** attempt * 3), 35)
                log.info("Groq 429 — wait %.0fs (%d/%d)", wait, attempt + 1, retries)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            content = (resp.json().get("choices") or [{}])[0].get("message", {}).get("content", "")
            parsed = json.loads(content)
            items = parsed.get("items") if isinstance(parsed, dict) else parsed
            if not isinstance(items, list):
                return None
        except Exception as exc:
            log.info("Groq geo-extract failed (%s) — fallback", type(exc).__name__)
            return None
        # map by index → finalize; missing indices fall back per-item later
        by_i: dict[int, dict] = {}
        for it in items:
            try:
                by_i[int(it.get("i"))] = it
            except (TypeError, ValueError):
                continue
        out: list[GeoExtraction] = []
        for i, title in enumerate(titles):
            raw = by_i.get(i)
            if raw is None:
                out.append(_fallback_extract(title)); continue
            rec = GeoExtraction(
                is_oil_relevant=bool(raw.get("oil", True)),
                asset_ids=[str(a) for a in (raw.get("assets") or [])],
                raw_locations=[str(x) for x in (raw.get("locs") or [])],
                asset_type=raw.get("atype"), event_type=raw.get("event"),
                severity=str(raw.get("sev") or "moderate"),
                confidence=float(raw.get("conf", 0.6)),
            )
            out.append(_finalize_item(title, rec, "groq"))
        return out
    return None


# ── geo prefilter (only candidates hit the LLM) ───────────────────────────────
def is_geo_candidate(title: str, factor: str | None = None) -> bool:
    t = (title or "").lower()
    if factor and factor.upper() in _GEO_FACTORS:
        return True
    if reg.resolve(t) or reg.resolve_generic(t):
        return True
    return any(_kw(t, n) for n in _GEO_NOUNS)


# ── extraction cache ──────────────────────────────────────────────────────────
def _key(title: str) -> str:
    return hashlib.sha1((title or "").strip().lower().encode("utf-8")).hexdigest()[:16]


def _load_cache() -> dict:
    if _GEO_CACHE.exists():
        try:
            return json.loads(_GEO_CACHE.read_text())
        except Exception:
            return {}
    return {}


def _save_cache(cache: dict) -> None:
    try:
        _GEO_CACHE.parent.mkdir(parents=True, exist_ok=True)
        _GEO_CACHE.write_text(json.dumps(cache))
    except Exception as exc:
        log.warning("geo cache write failed: %s", exc)


# ── orchestration ─────────────────────────────────────────────────────────────
def _llm_extract_batch(titles: list[str], provider: str,
                       model: str | None) -> list[GeoExtraction] | None:
    """Provider dispatch. 'auto' prefers FREE Groq, then Claude, else None (→ fallback)."""
    if provider in ("groq", "auto") and os.getenv("GROQ_API_KEY", "").strip():
        r = _groq_extract_batch(titles, model or GROQ_MODEL)
        if r is not None or provider == "groq":
            return r
    if provider in ("claude", "auto") and os.getenv("ANTHROPIC_API_KEY", "").strip():
        return _claude_extract_batch(titles, model or LIVE_MODEL)
    return None


def extract_headlines(titles: list[str], model: str | None = None,
                      provider: str = "auto") -> list[GeoExtraction]:
    """LLM (Groq→Claude) for the batch, deterministic fallback per missing item."""
    if not titles:
        return []
    llm = _llm_extract_batch(titles, provider, model)
    return [(llm[i] if llm and i < len(llm) and llm[i] is not None else _fallback_extract(t))
            for i, t in enumerate(titles)]


def extract_cached(titles: list[str], provider: str = "auto",
                   model: str | None = None, batch: int = 15) -> list[GeoExtraction]:
    """Cache-backed batch extraction: returns cached records, LLM-extracts only the
    misses (in small batches, persisted), so re-grading never re-calls the LLM.

    Only **LLM-sourced** records are cached — a deterministic fallback (e.g. when
    the LLM is rate-limited / daily-capped) is NOT persisted, so a later run retries
    it via the LLM rather than locking in the weaker keyword result."""
    cache = _load_cache()
    miss = [t for t in titles if _key(t) not in cache]
    if miss:
        log.info("geo extract_cached: %d cached, %d to extract", len(titles) - len(miss), len(miss))
        for s in range(0, len(miss), batch):
            chunk = miss[s:s + batch]
            recs = extract_headlines(chunk, model=model, provider=provider)
            wrote = False
            for t, rec in zip(chunk, recs):
                if rec.source != "fallback":          # never cache a fallback miss
                    cache[_key(t)] = rec.model_dump()
                    wrote = True
            if wrote:
                _save_cache(cache)
    out = []
    for t in titles:
        c = cache.get(_key(t))
        out.append(GeoExtraction(**c) if c else _fallback_extract(t))
    return out


def extract_headline(title: str, snippet: str | None = None,
                     model: str | None = None, provider: str = "auto") -> GeoExtraction:
    text = f"{title}. {snippet}" if snippet else title
    return extract_headlines([text], model=model, provider=provider)[0]


def score_headline_geo(title: str, snippet: str | None = None,
                       model: str | None = None, provider: str = "auto") -> dict:
    """Headline → {extraction, impact}: the geo entrypoint the event study /
    dashboard consume. impact is the impact_map node vector + rationale."""
    ex = extract_headline(title, snippet, model=model, provider=provider)
    assets = [reg.by_id(a) for a in ex.asset_ids if reg.by_id(a)]
    impact = impact_map.headline_impact(assets, ex.event_type, ex.severity)
    return {"extraction": ex.model_dump(), "impact": impact}


# ── standalone ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    load_env()

    prov = "groq" if os.getenv("GROQ_API_KEY") else \
           ("claude" if os.getenv("ANTHROPIC_API_KEY") else "fallback")
    print(f"extractor provider: {prov}\n")

    samples = [
        "Houthi drone strike hits oil tanker in the Red Sea, shipping rerouted",
        "Massive fire forces complete shutdown at Motiva Port Arthur refinery",
        "OPEC+ agrees a deeper voluntary production cut for next quarter",
        "Druzhba pipeline halted after explosion; Urals flows to Europe disrupted",
        "Reliance Jamnagar refinery resumes operations after maintenance",
        "Tech stocks rally on strong earnings",                 # not oil
    ]
    for s in samples:
        r = score_headline_geo(s)
        ex = r["extraction"]
        print(f"• {s[:64]}")
        print(f"    assets={ex['asset_ids']} event={ex['event_type']} "
              f"sev={ex['severity']} src={ex['source']} conf={ex['confidence']}")
        print(f"    {r['impact']['rationale']}")
        print(f"    nodes={r['impact']['nodes']}\n")
