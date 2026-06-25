"""
Directional accuracy — the honest track record + the selective-confidence policy.
================================================================================

The single most important fix for "is the call any good?": stop judging on one
print and **measure the directional hit-rate across the whole 2015-2026 history**,
on the REAL-consensus surprise, sliced by series / regime / surprise-size. Then make
the framework SELECTIVE — commit a directional call (and quote its historical
hit-rate) only in the (series × regime × size) cells where the call beat a coin
flip with a real binomial p-value, and abstain everywhere else.

What the data says (real-consensus surprise → release-day direction):

    CRUDE flat
      HIGH stocks (glut)   74.6%  (n=59, p≈0.000)   · big |z|≥1: 81% (p≈0.007)
      contango front       60.4%  (p≈0.012)         · big: 67.9% (p≈0.013)
      2015-2020 glut era   61.0%  (p≈0.001)
      tight / LOW / bwd    ~52-54% (NOT significant — a coin flip)   ← today
    GASOLINE flat
      backwardation        57.0%  (n=381, p≈0.008)  · big |z|≥1: 63.3% (p≈0.001)  ← today's edge
    DISTILLATE flat        ~54%   (weak; summer is its off-season)
    WTI flat / WTI-Brent   ~50%   (2021+ only = tight regime only; no edge)

So in a glut the crude flat call is genuinely 75-81% accurate; in today's tight,
backwardated regime the crude flat call is a coin flip — but GASOLINE carries a real
57-63% backwardation edge in exactly that regime. The framework therefore redirects
conviction to the series/regime where accuracy is *proven*, and is honest (abstains)
where it isn't. This is a precision-over-recall fix: we are right far more often *when
we choose to commit*.

Honest scope: these are full-sample DESCRIPTIVE hit-rates (how often the sign was
right, in that regime, with a binomial test vs 50%) — a characterisation of the
regime, not a walk-forward trading P&L. The conditioning regime is read live.

Public API
----------
  hit_rate_table(series, target="ret") -> pd.DataFrame
  applicable_hit_rate(series, inv_bucket, front_contango, inv_pct, surprise_z) -> dict
  best_series_now(inv_bucket, front_contango, inv_pct, surprise_by_series) -> dict
  accuracy_summary(series) -> dict      # everything, for the API

Run standalone:  python -m backend.research.inventory_impact.accuracy
"""

from __future__ import annotations

import logging
import sys
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

_BACKEND = Path(__file__).resolve().parent.parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from research.inventory_impact import eia_report, regime_conditioning  # noqa: E402

log = logging.getLogger("pulse.inventory_impact.accuracy")

BIG_Z = 1.0          # |surprise_z| threshold that defines a "big" surprise
P_SIG = 0.10         # binomial p-value below which a hit-rate is "significant"
MIN_N = 20           # minimum sample before we trust a cell's hit-rate


def _binom_p(k: int, n: int) -> float:
    """Two-sided binomial p-value vs 0.5 (scipy if present, else normal approx)."""
    if n == 0:
        return 1.0
    try:
        from scipy import stats
        return float(stats.binomtest(k, n, 0.5).pvalue)
    except Exception:
        # normal approximation fallback (no scipy)
        from math import erf, sqrt
        z = (k - n / 2) / (sqrt(n) / 2)
        return float(2 * (1 - 0.5 * (1 + erf(abs(z) / sqrt(2)))))


def _hit(sub: pd.DataFrame, target: str, zcol: str = "surprise_z") -> dict | None:
    """Directional hit-rate: did sign(-surprise) match sign(`target`)? The beta is
    negative (a bigger-than-expected draw → price up), so a HIT is a sign DISagreement
    between surprise_z and the target return. Returns hit/n/p/edge/significant."""
    s = sub[[zcol, target]].dropna()
    s = s[s[zcol] != 0]
    n = len(s)
    if n < 12:
        return None
    hits = float((np.sign(s[zcol]) != np.sign(s[target])).mean())
    k = int(round(hits * n))
    p = _binom_p(k, n)
    return {
        "hit": round(hits, 3), "n": n, "p": round(p, 3),
        "edge": round(hits - 0.5, 3),
        "significant": bool(p < P_SIG and hits > 0.5 and n >= MIN_N),
    }


@lru_cache(maxsize=8)
def hit_rate_table(series: str = "crude_ex_spr", target: str = "ret") -> pd.DataFrame:
    """Per-regime directional hit-rate of the call, on the real-consensus surprise,
    at all-surprise sizes and big (|z|≥1) only. Cached per (series, target)."""
    panel = regime_conditioning.build_daily_panel("consensus", series=series)
    cuts: list[tuple[str, str, pd.DataFrame]] = [
        ("ALL", "all releases", panel),
        ("inventory", "HIGH stocks", panel[panel["inv_bucket"] == "HIGH"]),
        ("inventory", "AVG stocks", panel[panel["inv_bucket"] == "AVG"]),
        ("inventory", "LOW stocks", panel[panel["inv_bucket"] == "LOW"]),
        ("inventory", "glut (>5yr)", panel[panel["inv_pct"] > 0]),
        ("inventory", "tight (<=5yr)", panel[panel["inv_pct"] <= 0]),
        ("curve", "contango front", panel[panel["front_contango"]]),
        ("curve", "backwardated front", panel[~panel["front_contango"]]),
        ("era", "2015-2020", panel[panel["era"] == "2015-2020"]),
        ("era", "2021-2026", panel[panel["era"] == "2021-2026"]),
    ]
    rows = []
    for cond, label, sub in cuts:
        h_all = _hit(sub, target)
        h_big = _hit(sub[sub["surprise_z"].abs() >= BIG_Z], target)
        if not h_all:
            continue
        rows.append({
            "conditioner": cond, "regime": label,
            "hit": h_all["hit"], "n": h_all["n"], "p": h_all["p"],
            "edge": h_all["edge"], "significant": h_all["significant"],
            "hit_big": (h_big or {}).get("hit"), "n_big": (h_big or {}).get("n"),
            "p_big": (h_big or {}).get("p"), "significant_big": (h_big or {}).get("significant"),
        })
    return pd.DataFrame(rows)


def applicable_hit_rate(series: str, inv_bucket: str | None, front_contango: bool | None,
                        inv_pct: float | None, surprise_z: float | None) -> dict:
    """
    The historical hit-rate that applies to a LIVE call: among the regime cuts the
    current state satisfies (its inventory bucket, its glut/tight split, its curve
    state), at the current surprise size, pick the **strongest significant** cell —
    that is the framework's calibrated directional confidence. If none clears the
    bar, the call is a coin flip in this regime → abstain (significant=False), and we
    report the broadest honest hit-rate so the desk sees *why*.
    """
    panel = regime_conditioning.build_daily_panel("consensus", series=series)
    big = surprise_z is not None and abs(surprise_z) >= BIG_Z
    # candidate cuts the current regime belongs to (label, mask)
    cands: list[tuple[str, pd.Series]] = []
    if inv_bucket in ("HIGH", "AVG", "LOW"):
        cands.append((f"{inv_bucket} stocks", panel["inv_bucket"] == inv_bucket))
    if inv_pct is not None:
        cands.append(("glut (>5yr)" if inv_pct > 0 else "tight (<=5yr)",
                      panel["inv_pct"] > 0 if inv_pct > 0 else panel["inv_pct"] <= 0))
    if front_contango is not None:
        cands.append(("contango front" if front_contango else "backwardated front",
                      panel["front_contango"] if front_contango else ~panel["front_contango"]))

    evaluated = []
    for label, mask in cands:
        sub = panel[mask]
        # prefer the big-surprise cell when the live surprise is big and it has enough n
        h_big = _hit(sub[sub["surprise_z"].abs() >= BIG_Z], "ret") if big else None
        use_big = bool(big and h_big and h_big["n"] >= MIN_N)
        h = h_big if use_big else _hit(sub, "ret")
        if not h:
            continue
        evaluated.append({"regime": label, "size": "big (|z|>=1)" if use_big else "all", **h})

    if not evaluated:
        return {"series": series, "regime": None, "hit": None, "n": 0,
                "significant": False, "tradeable": False,
                "basis": "no historical sample for this regime"}

    sig = [e for e in evaluated if e["significant"]]
    pick = (max(sig, key=lambda e: e["edge"]) if sig
            else max(evaluated, key=lambda e: e["n"]))  # no edge → broadest honest cell
    pick = dict(pick)
    pick["series"] = series
    pick["tradeable"] = pick["significant"]
    pick["candidates"] = evaluated
    pick["basis"] = (
        f"{series} flat direction has been right {pick['hit']*100:.0f}% of the time in the "
        f"'{pick['regime']}' regime ({pick['size']} surprises, n={pick['n']}, p={pick['p']}) — "
        + ("a real edge → tradeable." if pick["significant"]
           else "not distinguishable from a coin flip → abstain on the flat direction.")
    )
    return pick


def best_series_now(inv_bucket: str | None, front_contango: bool | None,
                    inv_pct: float | None, surprise_by_series: dict[str, float | None]) -> dict:
    """
    Across crude/gasoline/distillate, which series carries the strongest PROVEN
    directional edge in TODAY's regime? Redirects conviction to where accuracy is
    real — e.g. in today's backwardation, gasoline (57-63%) beats crude flat (coin
    flip). `surprise_by_series` is each series' current surprise_z (for the size
    gate). Returns the ranked list + the recommended series (or None to abstain).
    """
    ranked = []
    for series in ("crude_ex_spr", "gasoline", "distillate"):
        a = applicable_hit_rate(series, inv_bucket, front_contango, inv_pct,
                                surprise_by_series.get(series))
        ranked.append(a)
    ranked.sort(key=lambda a: (a.get("significant", False), a.get("edge") or -1), reverse=True)
    best = ranked[0] if ranked and ranked[0].get("significant") else None
    return {
        "recommended_series": best["series"] if best else None,
        "recommended_hit": best["hit"] if best else None,
        "recommended_regime": best["regime"] if best else None,
        "ranked": ranked,
        "note": (f"In this regime the proven directional edge is {best['series']} "
                 f"({best['hit']*100:.0f}% in '{best['regime']}'). Crude flat is a coin flip here."
                 if best else
                 "No series has a statistically proven flat-direction edge in this regime — "
                 "trade the spread/quality reads, not the flat print direction."),
    }


def accuracy_summary(series: str = "crude_ex_spr") -> dict:
    """Everything the API/dashboard needs: the per-regime table + the live applicable
    hit-rate for today's regime + the best-series-now redirect."""
    cr = regime_conditioning.current_regime(series=series)
    z_by = {}
    for s in ("crude_ex_spr", "gasoline", "distillate"):
        sp = eia_report.surprise_series(s, "consensus").dropna(subset=["surprise_z"])
        z_by[s] = float(sp["surprise_z"].iloc[-1]) if len(sp) else None
    applicable = applicable_hit_rate(series, cr.get("inv_bucket"), cr.get("front_contango"),
                                     cr.get("inv_vs_5yr_pct"), z_by.get(series))
    best = best_series_now(cr.get("inv_bucket"), cr.get("front_contango"),
                           cr.get("inv_vs_5yr_pct"), z_by)
    tbl = hit_rate_table(series, "ret")
    return {
        "series": series,
        "regime_label": cr.get("regime_label"),
        "applicable": applicable,
        "best_series_now": best,
        "by_regime": tbl.to_dict("records"),
        "note": ("Full-sample directional hit-rate (sign of the call vs the actual release-day "
                 "move) on the REAL-consensus surprise, 2015-2026; binomial vs 50%. Descriptive "
                 "regime characterisation, not a walk-forward P&L."),
    }


if __name__ == "__main__":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.WARNING)
    pd.set_option("display.width", 160)

    for series in ("crude_ex_spr", "gasoline", "distillate"):
        print(f"\n=== DIRECTIONAL HIT-RATE — {series} (real-consensus surprise → release-day dir) ===")
        t = hit_rate_table(series, "ret")
        print(t[["regime", "hit", "n", "p", "significant", "hit_big", "n_big", "p_big"]].to_string(index=False))

    summ = accuracy_summary("crude_ex_spr")
    print("\n=== LIVE — today's regime:", summ["regime_label"], "===")
    a = summ["applicable"]
    print("  crude applicable:", a["basis"])
    b = summ["best_series_now"]
    print("  best series now :", b["note"])
