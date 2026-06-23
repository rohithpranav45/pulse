"""
Trade Idea Generator
====================
Rule-based directional trade idea for Brent crude, enriched with an
optional Ollama (llama3) morning brief paragraph.

Public API
----------
  generate_trade_idea(signal_dict, fv_dict, curve_dict, tech_dict,
                      fundamentals, patterns, macro, weather, prices) -> dict
"""

import os
import sys
import logging
from datetime import datetime, timezone

_MODELS  = os.path.abspath(os.path.dirname(__file__))
_BACKEND = os.path.abspath(os.path.join(_MODELS, ".."))
_ROOT    = os.path.abspath(os.path.join(_BACKEND, ".."))
for _p in (_BACKEND, _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

log = logging.getLogger("pulse.trade_idea")

_RISK_TABLE = {
    "Inventory":  "EIA inventory print could reverse the supply narrative",
    "COT":        "Speculator position unwind risk if momentum fades",
    "Curve":      "Curve structure may shift on OPEC supply announcement",
    "Fair Value": "Mean-reversion risk if macro deteriorates sharply",
    "DXY":        "Dollar strengthening could cap oil upside",
    "Geo Risk":   "Geo-risk premium may deflate if tensions ease",
    "Sentiment":  "Sentiment reversal on macro headline risk",
    "Technicals": "Technical breakdown risk — watch key support levels",
    "Weather":    "Weather normalisation removes seasonal demand premium",
    "IV":         "Volatility compression may limit directional follow-through",
}


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _thesis_bullets(indicators: list, dir_int: int) -> list:
    scored = sorted(
        indicators,
        key=lambda i: abs(i.get("weight", 0) * i.get("score", 0)),
        reverse=True,
    )
    bullets = []
    for ind in scored:
        sc = ind.get("score", 0)
        agrees = (dir_int > 0 and sc > 0) or (dir_int < 0 and sc < 0) or dir_int == 0
        if agrees:
            bullets.append(f"{ind['name']}: {ind.get('reason', '')}")
        if len(bullets) == 3:
            break
    while len(bullets) < 3:
        bullets.append("Monitoring additional data sources.")
    return bullets


def _key_risk(indicators: list, dir_int: int) -> str:
    opposing = [i for i in indicators if i.get("score", 0) * dir_int < 0]
    if not opposing:
        opposing = sorted(indicators, key=lambda i: abs(i.get("score", 0)), reverse=True)
    if not opposing:
        return "Monitor macro and geopolitical conditions."
    worst = max(opposing, key=lambda i: abs(i.get("weight", 0) * i.get("score", 0)))
    return _RISK_TABLE.get(worst.get("name", ""), worst.get("reason", "Monitor conditions."))


def _rule_based_brief(ctx: dict) -> str:
    """
    Produce a 5-bullet context brief from structured data.
    Used as the deterministic fallback when Groq + Ollama are both unavailable.
    """
    px         = ctx.get("brent_price", 0)
    m1m2       = ctx.get("m1m2_spread")        # float | None
    struct     = ctx.get("curve_struct", "")   # "backwardation"/"contango"/"flat"
    inv_pct    = ctx.get("inv_pct")            # float | None (%)
    cot        = ctx.get("cot_pct")            # float | None
    crack      = ctx.get("crack_321")          # float | None ($/bbl)
    crack_avg  = ctx.get("crack_avg")          # float | None
    direction  = ctx.get("direction", "NEUTRAL")
    conviction = ctx.get("conviction", "LOW")
    key_risk   = ctx.get("key_risk", "")
    y10        = ctx.get("yield_10y")

    bullets: list[str] = []

    # 1 — Curve
    if m1m2 is not None and abs(m1m2) > 0.05:
        sign      = "+" if m1m2 > 0 else "-"
        struct_w  = (struct.lower() if struct else
                     ("backwardation" if m1m2 > 0 else "contango"))
        bullets.append(f"Curve: {struct_w} at {sign}${abs(m1m2):.2f} M1-M2 (Brent ${px:.2f}).")
    else:
        bullets.append(f"Curve: flat / undefined (Brent ${px:.2f}).")

    # 2 — Inventory
    if inv_pct is not None:
        ab = "below" if inv_pct < 0 else "above"
        tag = "tight" if inv_pct < -3 else "ample" if inv_pct > 3 else "balanced"
        bullets.append(f"Inventory: {abs(inv_pct):.1f}% {ab} 5Y average — {tag}.")
    else:
        bullets.append("Inventory: data unavailable.")

    # 3 — Positioning + crack
    # cot may be the "—" sentinel when COT data is unavailable; guard numerically
    # (matches the isinstance pattern used for y10/cpi below) so a missing feed
    # never crashes the brief on `cot > 75`.
    if isinstance(cot, (int, float)):
        cot_tag = ("crowded long" if cot > 75 else
                   "washed-out" if cot < 25 else "neutral")
        positioning = f"COT speculator at {cot:.0f}th percentile — {cot_tag}"
    else:
        positioning = "COT positioning unavailable"
    if crack is not None and crack_avg is not None:
        diff = crack - crack_avg
        crack_tag = ("wide" if diff > 2 else "compressed" if diff < -2 else "near norm")
        positioning += f"; 3-2-1 crack ${crack:.1f} ({crack_tag} vs ${crack_avg:.1f} 1Y avg)"
    bullets.append(f"Positioning: {positioning}.")

    # 4 — Macro
    macro_bits = []
    if isinstance(y10, (int, float)):
        macro_bits.append(f"10Y yield {y10:.2f}%")
    cpi = ctx.get("cpi")
    if isinstance(cpi, (int, float)):
        macro_bits.append(f"CPI YoY {cpi:.1f}%")
    if macro_bits:
        bullets.append(f"Macro: {', '.join(macro_bits)}.")
    else:
        bullets.append("Macro: feed warming.")

    # 5 — Bias (read as label, not action)
    bias_map = {
        "LONG":    "bullish",
        "SHORT":   "bearish",
        "NEUTRAL": "neutral",
    }
    bias_word = bias_map.get(direction.upper(), "neutral")
    conv_map  = {"HIGH": "high", "MODERATE": "moderate", "LOW": "low"}
    conv_str  = conv_map.get(conviction, "low")
    if key_risk:
        bullets.append(f"Bias: {bias_word} read, {conv_str} conviction — key risk: {key_risk[:80]}.")
    else:
        bullets.append(f"Bias: {bias_word} read, {conv_str} conviction.")

    return "\n".join(f"- {b}" for b in bullets)


# (legacy prose template removed — superseded by the bullet-point format above)


def _build_brief_prompt(ctx: dict) -> str:
    """Shared prompt used by both Ollama and Groq paths."""
    return (
        "You are a senior energy market analyst writing context for a trader. "
        "Output EXACTLY 5 short bullet points, each one line, each starting with '- '. "
        "Be informational — describe conditions, do NOT recommend buy/sell actions. "
        "Use specific numbers. Order bullets by importance:\n"
        "  1. CURVE — structure + M1-M2 spread\n"
        "  2. INVENTORY — vs 5Y average\n"
        "  3. POSITIONING — COT percentile + crack spread context\n"
        "  4. MACRO — yield/CPI/dollar/IV context\n"
        "  5. BIAS — model bias label (bullish/bearish/neutral), conviction level, and the single biggest risk.\n\n"
        "Data context:\n"
        f"  Brent spot:          ${ctx.get('brent_price', 0):.2f}/bbl\n"
        f"  Curve structure:     M1-M2 {ctx.get('m1m2_spread', '—')} "
        f"| {ctx.get('curve_struct', '—').upper()}\n"
        f"  Inventory vs 5Y avg: {ctx.get('inv_pct', '—')}%\n"
        f"  COT speculator:      {ctx.get('cot_pct', '—')}th percentile\n"
        f"  3-2-1 crack:         ${ctx.get('crack_321', '—')} "
        f"| 1Y avg ${ctx.get('crack_avg', '—')} | {ctx.get('crack_signal', 'NORMAL')}\n"
        f"  EIA crude change:    {ctx.get('eia_change', '—')} Mb wk/wk\n"
        f"  Bias label:          {ctx.get('signal', '—')} / conviction {ctx.get('conviction', '—')}\n"
        f"  Pattern:             {ctx.get('pattern', '—')}\n"
        f"  10Y yield:           {ctx.get('yield_10y', '—')}%  "
        f"| CPI YoY: {ctx.get('cpi', '—')}%\n"
        f"  Key risk:            {ctx.get('key_risk', '—')}\n\n"
        "Output ONLY the 5 bullets, nothing else. No preamble, no closing sentence."
    )


def _groq_brief(ctx: dict) -> tuple[str | None, str]:
    """
    Call Groq's free-tier llama3-70b for a higher-quality brief.
    Returns (text or None, source_label).
    Free key: https://console.groq.com/keys — env var GROQ_API_KEY.
    """
    key = os.getenv("GROQ_API_KEY", "").strip()
    if not key:
        return None, "groq-no-key"
    try:
        import requests
        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type":  "application/json",
            },
            json={
                "model": os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
                "messages": [
                    {"role": "system", "content": "You are a concise senior energy market analyst. Output plain prose, 120-140 words, no bullets."},
                    {"role": "user",   "content": _build_brief_prompt(ctx)},
                ],
                "temperature": 0.4,
                "max_tokens":  450,
            },
            timeout=15,
        )
        resp.raise_for_status()
        text = (resp.json().get("choices") or [{}])[0].get("message", {}).get("content", "").strip()
        if len(text.split()) >= 80:
            return text, "groq"
        return None, "groq-too-short"
    except Exception as exc:
        log.info("Groq brief failed (%s) — trying Ollama", type(exc).__name__)
        return None, f"groq-error: {type(exc).__name__}"


def _ollama_brief(ctx: dict) -> str:
    """
    Source priority for the morning brief:
      1. Groq cloud (free tier, llama-3.3-70b)  — needs GROQ_API_KEY
      2. Local Ollama llama3                     — needs ollama daemon running
      3. Rule-based deterministic template       — always works

    The function signature stays `_ollama_brief` for backwards compatibility
    with the existing call site; the chosen source is logged.
    """
    # 1) Groq first — generally higher quality + faster than local llama3
    text, src = _groq_brief(ctx)
    if text:
        log.info("morning brief source: %s", src)
        return text

    # 2) Local Ollama
    prompt = _build_brief_prompt(ctx)
    try:
        import requests
        resp = requests.post(
            "http://localhost:11434/api/generate",
            json={"model": "llama3", "prompt": prompt, "stream": False},
            timeout=20,
        )
        resp.raise_for_status()
        text = resp.json().get("response", "").strip()
        if len(text.split()) >= 80:
            log.info("morning brief source: ollama")
            return text
    except Exception as exc:
        log.info("Ollama unavailable (%s)", type(exc).__name__)

    # 3) Rule-based fallback
    log.info("morning brief source: rule-based")
    return _rule_based_brief(ctx)


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────────

def generate_trade_idea(
    signal_dict, fv_dict, curve_dict, tech_dict,
    fundamentals=None, patterns=None, macro=None, weather=None, prices=None,
    cracks=None,
) -> dict:
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")

    # ── Brent signal ─────────────────────────────────────────────────────────
    brent_sig  = (signal_dict or {}).get("brent", {})
    score      = float(brent_sig.get("score", 0.0))
    conviction = brent_sig.get("conviction", "LOW")
    signal_lbl = brent_sig.get("signal", "NEUTRAL")
    indicators = brent_sig.get("indicators", [])

    # ── Live price + fair value ───────────────────────────────────────────────
    brent_fv   = (fv_dict or {}).get("brent", {})
    fv_price   = brent_fv.get("fair_value")
    live_price = brent_fv.get("live_price")
    if live_price is None:
        live_price = ((prices or {}).get("brent") or {}).get("price")
    if live_price is None:
        try:
            import yfinance as yf
            info = yf.Ticker("BZ=F").fast_info
            live_price = getattr(info, "last_price", None) or getattr(info, "previous_close", None) or 80.0
        except Exception:
            live_price = 80.0

    # ── Direction ─────────────────────────────────────────────────────────────
    if score > 0.5 and fv_price and live_price < fv_price:
        direction, dir_int = "LONG",  1
    elif score < -0.5 and fv_price and live_price > fv_price:
        direction, dir_int = "SHORT", -1
    else:
        direction, dir_int = "NEUTRAL", 0

    # ── Entry thesis ──────────────────────────────────────────────────────────
    entry_thesis = _thesis_bullets(indicators, dir_int)

    # ── ATR ───────────────────────────────────────────────────────────────────
    atr = None
    try:
        bt = (tech_dict or {})
        bt = bt.get("Brent") or bt.get("brent") or bt.get("BZ=F") or {}
        atr = bt.get("atr") or bt.get("ATR")
    except Exception:
        pass
    if not atr:
        atr = live_price * 0.015   # fallback: 1.5% of spot

    # ── Stop / target ─────────────────────────────────────────────────────────
    if direction == "LONG":
        stop_level   = round(live_price - 1.5 * atr, 2)
        target_level = round(live_price + 0.5 * (fv_price - live_price), 2) if fv_price else None
    elif direction == "SHORT":
        stop_level   = round(live_price + 1.5 * atr, 2)
        target_level = round(live_price - 0.5 * (live_price - fv_price), 2) if fv_price else None
    else:
        stop_level   = round(live_price - 1.5 * atr, 2)
        target_level = round(live_price + 1.5 * atr, 2)

    # ── Key risk ──────────────────────────────────────────────────────────────
    key_risk     = _key_risk(indicators, dir_int)
    time_horizon = "1-2 weeks" if (atr / live_price * 100) > 3.0 else "3-4 weeks"

    # ── Context for Ollama brief ──────────────────────────────────────────────
    eia_change = cot_pct = hdd_dev = yield_10y = cpi_val = None
    pat_name   = "Ranging"
    analog_summ = "No analogs found."

    try:
        inv = (fundamentals or {}).get("inventory", {})
        eia_change = (inv.get("crude_stocks") or {}).get("change")
    except Exception:
        pass
    try:
        co  = ((fundamentals or {}).get("cot") or {}).get("crude_oil") or {}
        cot_pct = co.get("percentile")
    except Exception:
        pass
    try:
        hdd_dev = (weather or {}).get("hdd_deviation_pct")
    except Exception:
        pass
    try:
        m = macro or {}
        yield_10y = (m.get("DGS10") or {}).get("value")
        cpi_val   = (m.get("CPIAUCSL") or {}).get("value")
    except Exception:
        pass
    try:
        p = patterns or {}
        pat_name    = (p.get("pattern") or {}).get("name", "Ranging")
        analog_summ = p.get("summary", "No analogs found.")
    except Exception:
        pass

    # ── Curve structure + crack spread context ────────────────────────────────
    m1m2_spread = curve_struct_val = None
    crack_321 = crack_321_avg = crack_signal_val = None
    inv_pct = None
    try:
        brent_curve = (curve_dict or {}).get("brent", {})
        m1m2_spread     = brent_curve.get("spread_m1_m2")
        curve_struct_val = brent_curve.get("structure", "flat")
    except Exception:
        pass
    try:
        inv_pct = (
            (fundamentals or {})
            .get("inventory", {})
            .get("crude_stocks", {})
            .get("deviation_pct")
        )
    except Exception:
        pass
    try:
        cs = (cracks or {}).get("crack_spreads", {}).get("crack_321", {})
        crack_321      = cs.get("value")
        crack_321_avg  = cs.get("avg_1y")
        crack_signal_val = cs.get("signal", "NORMAL")
    except Exception:
        pass

    brief_ctx = {
        "brent_price":    live_price,
        "signal":         signal_lbl,
        "score":          score,
        "conviction":     conviction,
        "direction":      direction,
        "pattern":        pat_name,
        "analog_summary": analog_summ,
        "eia_change":     eia_change if eia_change is not None else "—",
        "cot_pct":        round(cot_pct) if cot_pct is not None else "—",
        "hdd_dev":        round(hdd_dev, 1) if hdd_dev is not None else "—",
        "yield_10y":      round(yield_10y, 2) if yield_10y is not None else "—",
        "cpi":            round(cpi_val, 1) if cpi_val is not None else "—",
        "thesis_0":       entry_thesis[0] if entry_thesis else "",
        "key_risk":       key_risk,
        # — new Phase 4A context —
        "m1m2_spread":    round(m1m2_spread, 2) if m1m2_spread is not None else None,
        "curve_struct":   curve_struct_val or "flat",
        "inv_pct":        round(inv_pct, 1) if inv_pct is not None else None,
        "crack_321":      round(crack_321, 1) if crack_321 is not None else None,
        "crack_avg":      round(crack_321_avg, 1) if crack_321_avg is not None else None,
        "crack_signal":   crack_signal_val or "NORMAL",
    }

    morning_brief = _ollama_brief(brief_ctx)

    return {
        "direction":     direction,
        "score":         score,
        "signal":        signal_lbl,
        "conviction":    conviction,
        "entry_thesis":  entry_thesis,
        "stop_level":    stop_level,
        "target_level":  target_level,
        "live_price":    round(live_price, 2),
        "fair_value":    round(fv_price, 2) if fv_price else None,
        "key_risk":      key_risk,
        "time_horizon":  time_horizon,
        "morning_brief": morning_brief,
        "timestamp":     ts,
    }


if __name__ == "__main__":
    import json
    print(json.dumps(generate_trade_idea({}, {}, {}, {}), indent=2, default=str))
