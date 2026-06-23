"""
L4 — the scorecard. Turns the machinery into a decision-ready call.

assess_release() composes the four layers into the Thursday deliverable:
  * EXPECTATION   bullish / bearish / neutral + a probability split
  * MAGNITUDE     expected Brent move = regime beta × surprise (only credible
                  where the regime is inventory-sensitive)
  * SPREADS       which instrument the surprise *type* maps to
  * CONFIDENCE    gated by regime sensitivity, quality coherence, surprise size
  * TOP-3 FACTORS the ranked drivers of the view

The key design choice — and the framework's edge — is that conviction is
**regime-gated**. A bullish surprise is only a high-conviction bullish *trade*
when inventories are in the glut/contango regime where they historically moved
price (regime_conditioning.py). In today's LOW-stocks / backwardation regime the
same surprise is, on the evidence, noise on flat price → the call is deliberately
low-conviction-on-flat and redirected to the quality / spread reads.

Public API
----------
  assess_release(actual_change=None, consensus=None, as_of=None) -> dict
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_BACKEND = Path(__file__).resolve().parent.parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from research.inventory_impact import eia_report, regime_conditioning  # noqa: E402
from research.inventory_impact.release_calendar import release_datetime  # noqa: E402

log = logging.getLogger("pulse.inventory_impact.framework")


def next_release_context() -> dict:
    """
    The UPCOMING release the desk will trade — the week after the latest data,
    out the following Wednesday. Gives the seasonal/nowcast expectation for that
    print so a pre-release expectation can be formed before consensus is known.
    """
    sp_seasonal = eia_report.surprise_series("crude_ex_spr", "seasonal")
    latest_we = sp_seasonal.dropna(subset=["actual_change"]).index.max()
    next_we = latest_we + pd.Timedelta(days=7)
    try:
        rel = release_datetime(next_we).tz_convert("America/New_York")
        rel_date, rel_day = str(rel.date()), rel.strftime("%A")
    except Exception:
        rel_date, rel_day = None, None

    # seasonal expectation for the upcoming ISO week (5yr same-week avg change)
    wf = eia_report.weekly_frame()
    chg = wf["crude_ex_spr"].diff()
    wk = next_we.isocalendar().week
    yr = next_we.year
    iso = chg.index.isocalendar().week.values
    yrs = chg.index.year.values
    mask = (iso == wk) & (yrs < yr) & (yrs >= yr - 5)
    sample = chg.values[mask]
    seasonal_exp = float(np.nanmean(sample)) if np.isfinite(sample).any() else None

    return {
        "week_ending": str(next_we.date()),
        "release_date": rel_date,
        "release_day_name": rel_day,
        "iso_week": int(wk),
        "seasonal_expected_change_mbbl": round(seasonal_exp, 0) if seasonal_exp is not None else None,
        "latest_data_week_ending": str(latest_we.date()),
    }


def scenario_tree(regime_beta: float, sensitive: bool, surprise_std: float,
                  glut_beta: float = -1.0) -> list[dict]:
    """
    The forward reaction map: for a grid of surprise sizes, the regime-conditional
    expected Brent release-day move under (a) TODAY's regime and (b) a glut/contango
    regime. The contrast is the framework's headline — the SAME surprise barely
    moves flat price in today's tight regime but moves it ~1-2% in a glut.
    """
    grid = [
        (-2.0, "Large BULLISH — draw far above expected"),
        (-1.0, "Modest bullish — tighter than expected"),
        (0.0,  "In line with expectations"),
        (1.0,  "Modest bearish — looser than expected"),
        (2.0,  "Large BEARISH — build far above expected"),
    ]
    out = []
    for z, name in grid:
        cur = round(regime_beta * z, 3)
        glut = round(glut_beta * z, 3)
        out.append({
            "z": z,
            "name": name,
            "surprise_mbbl": round(z * surprise_std, 0),
            "expected_brent_move_pct": cur,                  # today's regime
            "glut_regime_move_pct": glut,                    # if we were in a glut
            "direction": "bullish" if z < 0 else "bearish" if z > 0 else "neutral",
            "conviction": "actionable" if sensitive else "low — regime insensitive",
        })
    return out


def spread_attribution_betas() -> dict:
    """
    Data-driven spread attribution: the measured reaction of each instrument to a
    1σ crude surprise. Flat-price (Brent) betas come from the 2015-26 daily panel
    split by inventory regime (the validated signal); the front-spread / WTI-Brent
    betas come from the 2021-26 intraday event study. Honest about significance.
    """
    out = {"flat_by_regime": [], "intraday_spreads": [], "note": ""}
    try:
        panel = regime_conditioning.build_daily_panel("seasonal")
        tbl = regime_conditioning.conditional_table(panel, "ret")
        for r in tbl.to_dict("records"):
            if r["regime"] in ("HIGH stocks", "above 5yr (glut)", "below 5yr (tight)", "LOW stocks"):
                out["flat_by_regime"].append({
                    "regime": r["regime"], "beta_pct_per_sigma": r["beta"],
                    "t": r["t"], "n": r["n"],
                    "significant": abs(r["t"]) >= 2.0,
                })
    except Exception:
        pass
    try:
        from research.inventory_impact import event_study
        ep = event_study.build_panel()
        cb = event_study.conditional_betas(ep, 30)
        for instr in ("wti_m1_m2", "wti_brent", "wti_flat", "brent_flat"):
            e = (cb.get(instr) or {}).get("overall")
            if e:
                out["intraday_spreads"].append({
                    "instrument": instr, "beta_per_sigma": e["slope"],
                    "t": e["t"], "n": e["n"], "significant": abs(e.get("t") or 0) >= 2.0,
                })
    except Exception:
        pass
    out["note"] = ("Flat price moves with the surprise only in a glut/contango regime; "
                   "the front spread (M1-M2) and WTI-Brent reactions are economically "
                   "sensible but statistically weak in 2021-26 — so the headline trade is "
                   "flat price WHEN the regime is sensitive, else the quality decomposition.")
    return out


def _spread_attribution(dec_row: pd.Series | dict) -> dict:
    """
    Map the surprise *composition* to the instrument most likely to react.

    Logic (from the decomposition + the event-study attribution):
      - Cushing-concentrated surprise   -> WTI M1-M2 + WTI-Brent (delivery point)
      - export/import-driven surprise    -> WTI-Brent (US location/arb)
      - demand (products) surprise       -> flat price + cracks
      - otherwise (headline crude)       -> WTI flat (US benchmark) > Brent flat
    """
    def g(k):
        v = dec_row.get(k) if isinstance(dec_row, dict) else dec_row.get(k, np.nan)
        return float(v) if v is not None and pd.notna(v) else 0.0

    cushing = g("cushing_surprise_z")
    export = g("export_z")
    demand = g("demand_z")
    headline = g("crude_ex_spr_surprise_z")

    scores = {
        "WTI M1-M2": abs(cushing) * 1.0,
        "WTI-Brent": abs(export) * 1.0 + abs(cushing) * 0.4,
        "Brent/WTI cracks": abs(demand) * 1.0,
        "WTI flat": abs(headline) * 0.8,
    }
    primary = max(scores, key=scores.get)
    ranked = sorted(scores, key=scores.get, reverse=True)
    return {"primary": primary, "ranked": ranked, "scores": {k: round(v, 2) for k, v in scores.items()}}


def assess_release(actual_change: float | None = None,
                   consensus: float | None = None,
                   as_of: str | None = None) -> dict:
    """
    Produce the decision-ready call for a crude release.

    Parameters
    ----------
    actual_change : the EIA WoW crude (ex-SPR) change in MBBL. If None, uses the
                    latest released number in the cached report.
    consensus     : analyst consensus for that release in MBBL (read off the desk
                    terminal for the live call). If given, surprise = actual -
                    consensus (the *real* surprise). If None, the framework falls
                    back to its seasonal/nowcast proxy surprise and says so.
    as_of         : optional label for the release date.
    """
    sp = eia_report.surprise_series("crude_ex_spr", "seasonal")
    dec = eia_report.decomposition()
    latest_we = sp.dropna(subset=["surprise"]).index.max()

    if actual_change is None:
        actual_change = float(sp.loc[latest_we, "actual_change"])
        as_of = as_of or str(latest_we.date())

    # the data period is the week ending Friday; the report is RELEASED the
    # following Wednesday (10:30 ET; holiday → Thursday). Label both so a Friday
    # week-ending date is never mistaken for a release day.
    week_ending = str(latest_we.date())
    try:
        rel_dt = release_datetime(latest_we).tz_convert("America/New_York")
        release_date = str(rel_dt.date())
        release_day_name = rel_dt.strftime("%A")
    except Exception:
        release_date, release_day_name = None, None

    # --- the surprise ---
    if consensus is not None:
        surprise = actual_change - consensus
        # standardise by the historical surprise std
        std = sp["surprise"].std()
        surprise_z = surprise / std if std else 0.0
        surprise_src = "consensus (real)"
    else:
        surprise = float(sp.loc[latest_we, "surprise"])
        surprise_z = float(sp.loc[latest_we, "surprise_z"])
        surprise_src = "seasonal proxy (no consensus supplied)"

    bullish = surprise < 0  # tighter than expected

    # --- quality of draw ---
    dec_row = dec.loc[latest_we].to_dict() if latest_we in dec.index else {}
    quality = float(dec_row.get("quality_of_draw", np.nan))

    # --- regime gate (the conviction driver) ---
    cr = regime_conditioning.current_regime()
    beta = cr.get("applicable_beta") or {}
    regime_beta = beta.get("beta", 0.0)
    regime_t = beta.get("t", 0.0)
    sensitive = abs(regime_t) >= 2.0
    expected_move_pct = round(regime_beta * surprise_z, 3) if sensitive else 0.0

    # --- direction + probability split (regime-gated) ---
    # base lean from the surprise, then shrink toward neutral by (1 - regime weight)
    regime_weight = min(1.0, abs(regime_t) / 3.0)          # 0 when insensitive
    quality_confirm = np.sign(quality) == (1 if bullish else -1) if np.isfinite(quality) else False
    lean = np.tanh(-surprise_z * 0.6)                      # +bullish ... -bearish
    lean *= (0.4 + 0.6 * regime_weight)                    # regime damping
    if quality_confirm:
        lean *= 1.15
    lean = float(np.clip(lean, -1, 1))

    p_bull = round(0.5 + 0.5 * lean, 2)
    p_bear = round(0.5 - 0.5 * lean, 2)
    # carve a neutral band that widens when the regime is insensitive
    neutral_band = 0.10 + 0.20 * (1 - regime_weight)
    if abs(lean) < neutral_band:
        call = "NEUTRAL"
    else:
        call = "BULLISH" if lean > 0 else "BEARISH"

    # --- confidence ---
    big_surprise = abs(surprise_z) >= 1.0
    if sensitive and big_surprise and quality_confirm:
        confidence = "HIGH"
    elif sensitive or (big_surprise and quality_confirm):
        confidence = "MEDIUM"
    else:
        confidence = "LOW"

    # --- spread attribution ---
    attribution = _spread_attribution(dec_row)

    # --- top-3 factors (ranked) ---
    factors = []
    factors.append((abs(surprise_z),
                    f"Surprise vs expectation: {surprise:+,.0f} MBBL "
                    f"({surprise_z:+.1f}σ, {'bullish' if bullish else 'bearish'}) — {surprise_src}"))
    factors.append((2.0 if not sensitive else 1.0,
                    f"Regime gate: {cr['regime_label']} → inventory sensitivity "
                    f"{cr['sensitivity']} (hist. beta {regime_beta:+.2f}%/σ, t={regime_t}). "
                    f"{'This regime moves price.' if sensitive else 'Inventories have not moved flat price in this regime.'}"))
    if np.isfinite(quality):
        factors.append((abs(quality) * 0.5,
                        f"Quality-of-draw {quality:+.1f}: the draw looks "
                        f"{'demand-led / coherent' if quality > 0 else 'mechanical (export/adjustment-driven) — fade'}"))
    factors.append((abs(_spread_attribution(dec_row)["scores"][attribution["primary"]]) * 0.3 + 0.2,
                    f"Most-exposed instrument: {attribution['primary']} "
                    f"(then {', '.join(attribution['ranked'][1:3])})"))
    factors = [f for _, f in sorted(factors, key=lambda x: -x[0])][:3]

    # --- forward scenario tree (the reaction map for tomorrow's print) ---
    surprise_std = float(sp["surprise"].std())
    # glut-regime beta = the strongest sensitive-regime reaction (HIGH stocks), for contrast
    glut_beta = -1.0
    try:
        _tbl = regime_conditioning.conditional_table(
            regime_conditioning.build_daily_panel("seasonal"), "ret")
        _g = _tbl[_tbl["regime"] == "HIGH stocks"]
        if len(_g):
            glut_beta = float(_g.iloc[0]["beta"])
    except Exception:
        pass
    scenarios = scenario_tree(regime_beta, sensitive, surprise_std, glut_beta)

    return {
        "as_of": as_of,
        "week_ending": week_ending,
        "release_date": release_date,
        "release_day_name": release_day_name,
        "actual_change_mbbl": round(actual_change, 0),
        "surprise_mbbl": round(surprise, 0),
        "surprise_z": round(surprise_z, 2),
        "surprise_source": surprise_src,
        "surprise_std_mbbl": round(surprise_std, 0),
        "call": call,
        "p_bullish": p_bull,
        "p_bearish": p_bear,
        "confidence": confidence,
        "expected_brent_move_pct": expected_move_pct,
        "regime": cr,
        "regime_sensitive": sensitive,
        "regime_beta_pct_per_sigma": regime_beta,
        "regime_t": regime_t,
        "quality_of_draw": round(quality, 2) if np.isfinite(quality) else None,
        "spreads": attribution,
        "scenario_tree": scenarios,
        "top_factors": factors,
    }


def _fmt(call: str) -> str:
    return {"BULLISH": "🟢 BULLISH", "BEARISH": "🔴 BEARISH", "NEUTRAL": "⚪ NEUTRAL"}.get(call, call)


if __name__ == "__main__":
    import io, json
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.WARNING)

    # default: assess the latest released number with the proxy surprise
    r = assess_release()
    print("=" * 68)
    print(f"  INVENTORY IMPACT — release {r['as_of']}")
    print("=" * 68)
    print(f"  actual crude change : {r['actual_change_mbbl']:+,.0f} MBBL")
    print(f"  surprise            : {r['surprise_mbbl']:+,.0f} MBBL ({r['surprise_z']:+.1f}σ) [{r['surprise_source']}]")
    print(f"  CALL                : {_fmt(r['call'])}   (P_bull={r['p_bullish']}, P_bear={r['p_bearish']})")
    print(f"  confidence          : {r['confidence']}")
    print(f"  regime              : {r['regime']['regime_label']}  → sensitivity {r['regime']['sensitivity']}")
    print(f"  expected Brent move  : {r['expected_brent_move_pct']:+.2f}%  "
          f"({'regime is sensitive' if r['regime_sensitive'] else 'regime insensitive → ~0, do not trade flat on the print'})")
    print(f"  most-exposed spread  : {r['spreads']['primary']}  (ranked: {', '.join(r['spreads']['ranked'][:3])})")
    print("  top-3 factors:")
    for i, f in enumerate(r["top_factors"], 1):
        print(f"    {i}. {f}")

    # illustrate a live call with a hypothetical consensus
    print("\n" + "-" * 68)
    print("  EXAMPLE live call — actual -8,263 vs consensus -2,000 (a bullish surprise):")
    r2 = assess_release(actual_change=-8263, consensus=-2000, as_of="example")
    print(f"    CALL {_fmt(r2['call'])}  conf {r2['confidence']}  "
          f"surprise {r2['surprise_mbbl']:+,.0f} ({r2['surprise_z']:+.1f}σ)  "
          f"exp move {r2['expected_brent_move_pct']:+.2f}%")
