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
    Produce a professional analyst-style brief from structured context.

    Target narrative:
      "Brent prints backwardation at +$0.43 M1-M2 with inventory 3.2% below 5Y
       average. COT net long at 78th percentile. 3-2-1 crack at $28.4 below
       seasonal norm ($31.2) — refinery margin headwind. Conflicting signals:
       structural support from draw momentum offset by crowded positioning.
       Bias: long bias with reduced conviction pending crack recovery."
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

    sentences = []

    # ── Sentence 1: Curve structure + inventory ───────────────────────────────
    if m1m2 is not None and abs(m1m2) > 0.05:
        sign      = "+" if m1m2 > 0 else "-"
        struct_w  = struct.lower() if struct else ("backwardation" if m1m2 > 0 else "contango")
        s1 = f"Brent prints {struct_w} at {sign}${abs(m1m2):.2f} M1-M2"
    else:
        s1 = f"Brent at ${px:.2f}"
    if inv_pct is not None:
        ab = "below" if inv_pct < 0 else "above"
        s1 += f" with inventory {abs(inv_pct):.1f}% {ab} 5Y average"
    sentences.append(s1 + ".")

    # ── Sentence 2: COT ───────────────────────────────────────────────────────
    if cot is not None:
        if cot > 75:
            sentences.append(
                f"COT net long at {cot:.0f}th percentile — speculator positioning crowded; unwind risk elevated.")
        elif cot < 25:
            sentences.append(
                f"COT net short at {cot:.0f}th percentile — washed-out positioning creates mean-reversion upside.")
        else:
            sentences.append(f"COT speculator net long at {cot:.0f}th percentile — positioning neutral.")

    # ── Sentence 3: Crack spread ──────────────────────────────────────────────
    if crack is not None and crack_avg is not None:
        diff = crack - crack_avg
        ab2  = "above" if diff >= 0 else "below"
        impl = (
            "strong refinery demand supports crude pull" if diff > 2
            else "refinery margin headwind may dampen crude demand pull" if diff < -2
            else "refinery margins near seasonal norm"
        )
        sentences.append(
            f"3-2-1 crack at ${crack:.1f} {ab2} seasonal norm (${crack_avg:.1f}) — {impl}.")

    # ── Sentence 4: Conflicting signals ──────────────────────────────────────
    bull, bear = [], []
    if inv_pct is not None and inv_pct < -3:
        bull.append("inventory draw momentum")
    elif inv_pct is not None and inv_pct > 3:
        bear.append("inventory surplus")
    if m1m2 is not None and m1m2 > 0.3:
        bull.append("backwardation support")
    elif m1m2 is not None and m1m2 < -0.5:
        bear.append("contango drag")
    if cot is not None and cot > 75:
        bear.append("speculator crowding")
    elif cot is not None and cot < 25:
        bull.append("short-covering potential")
    if crack is not None and crack_avg is not None:
        if crack - crack_avg > 2:
            bull.append("wide refinery margins")
        elif crack - crack_avg < -2:
            bear.append("compressed refinery margins")
    if isinstance(y10, (int, float)) and y10 > 4.5:
        bear.append("rate headwind")

    if bull and bear:
        sentences.append(
            f"Conflicting signals: structural support from {', '.join(bull[:2])} "
            f"offset by {', '.join(bear[:2])}.")
    elif bear and not bull:
        sentences.append(f"Headwinds: {', '.join(bear[:3])}.")
    elif bull and not bear:
        sentences.append(f"Supporting signals: {', '.join(bull[:3])}.")

    # ── Sentence 5: Bias ──────────────────────────────────────────────────────
    conv_map = {"HIGH": "high conviction", "MODERATE": "moderate conviction", "LOW": "reduced conviction"}
    conv_str = conv_map.get(conviction, "reduced conviction")
    if key_risk:
        qualifier = key_risk[:55].lower().rstrip(".")
        sentences.append(f"Bias: {direction.lower()} bias with {conv_str} pending {qualifier}.")
    else:
        sentences.append(f"Bias: {direction.lower()} bias with {conv_str}.")

    return " ".join(sentences)


def _ollama_brief(ctx: dict) -> str:
    """
    POST to local Ollama llama3 with an enriched structured prompt.
    Falls back to _rule_based_brief() on any error (connection refused, timeout, etc.).
    """
    prompt = (
        "You are a concise senior energy market analyst at a commodity trading firm. "
        "Write a 120-140 word morning brief in plain prose — no bullet points, no headers. "
        "Lead with the curve structure and key data, identify conflicting signals, then give "
        "a directional bias. Be specific: quote prices, percentiles, percentages.\n\n"
        "Data context:\n"
        f"  Brent spot:          ${ctx.get('brent_price', 0):.2f}/bbl\n"
        f"  Curve structure:     M1-M2 {ctx.get('m1m2_spread', '—')} "
        f"| {ctx.get('curve_struct', '—').upper()}\n"
        f"  Inventory vs 5Y avg: {ctx.get('inv_pct', '—')}%\n"
        f"  COT speculator:      {ctx.get('cot_pct', '—')}th percentile\n"
        f"  3-2-1 crack:         ${ctx.get('crack_321', '—')} "
        f"| 1Y avg ${ctx.get('crack_avg', '—')} | {ctx.get('crack_signal', 'NORMAL')}\n"
        f"  EIA crude change:    {ctx.get('eia_change', '—')} Mb wk/wk\n"
        f"  Signal / conviction: {ctx.get('signal', '—')} / {ctx.get('conviction', '—')}\n"
        f"  Pattern:             {ctx.get('pattern', '—')}\n"
        f"  10Y yield:           {ctx.get('yield_10y', '—')}%  "
        f"| CPI YoY: {ctx.get('cpi', '—')}%\n"
        f"  Direction:           {ctx.get('direction', 'NEUTRAL')}\n"
        f"  Key risk:            {ctx.get('key_risk', '—')}\n\n"
        "End the brief with: 'Bias: [direction] bias with [conviction] — [key qualifier].'"
    )
    try:
        import requests
        resp = requests.post(
            "http://localhost:11434/api/generate",
            json={"model": "llama3", "prompt": prompt, "stream": False},
            timeout=20,
        )
        resp.raise_for_status()
        text = resp.json().get("response", "").strip()
        if len(text.split()) >= 80:   # sanity check — at least 80 words
            return text
    except Exception as exc:
        log.info("Ollama unavailable (%s) — using rule-based brief", type(exc).__name__)

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
