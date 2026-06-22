"""
gated_select.py — Phase 2: gated, decorrelated trade selection.

The mentor's directive: take the top profitable opportunities but DON'T double up
on similar/correlated bets (no risk concentration). The regime engine already
ranks every spread by conviction (live_ranker.get_recommendation → `ranked`,
sorted by confidence desc). This module turns that ranked list into the SET of
trades a desk would actually put on: greedily take the highest-conviction
opportunity, then SKIP any lower-ranked candidate whose position would be too
correlated with one already chosen.

Concentration is measured on SIGNED P&L correlation, not raw instrument
correlation, because the risk of a combined book is

    Var(pnl_i + pnl_j) = Var_i + Var_j + 2·Cov(pnl_i, pnl_j),
    Cov(pnl_i, pnl_j)  ∝ corr(Δi, Δj) · dir_i · dir_j     (dir = +1 BUY / −1 SELL)

  • signed corr > 0  ⇒ the two positions win/lose together ⇒ redundant   ⇒ SKIP
  • signed corr < 0  ⇒ the two positions hedge ⇒ LOWER book variance    ⇒ KEEP

So brent_m1_m2 BUY + brent_fly BUY (raw ρ=0.87) is redundant and the weaker one is
dropped, but brent_m1_m2 BUY + brent_fly SELL is a hedge and both are kept.

The tradeable universe (after the tuned M3-M6 exclusion) is bimodal: front
carry/fly correlate ~0.76–0.87 within product and ≤0.30 across product, so the
default ρ_max=0.70 admits at most one trade per {brent-front, wti-front} cluster.

Public API
----------
  rho_max_from_env() -> float
  instrument_corr_matrix(window=CORR_WINDOW, *, spreads=None) -> pd.DataFrame   # cached
  select_decorrelated(ranked, *, rho_max=None, max_positions=None, corr=None) -> dict
"""

from __future__ import annotations

import logging
import os
import sys

import numpy as np
import pandas as pd

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

log = logging.getLogger("pulse.research.gated_select")

CORR_WINDOW      = 504    # trailing daily-change window (~2 trading years)
DEFAULT_RHO_MAX  = 0.70   # signed-P&L-corr ceiling; at/above ⇒ concentrated ⇒ skip
MIN_CORR_OVERLAP = 60     # joint non-null changes needed before a corr is trusted

_DIR_SIGN = {"BUY": 1.0, "SELL": -1.0}

# Per-process cache of the raw instrument correlation matrix (the spread history
# doesn't move within a run). Keyed by window.
_CORR_CACHE: dict[int, pd.DataFrame] = {}


def rho_max_from_env() -> float:
    """Read PULSE_DECORREL_RHO (default DEFAULT_RHO_MAX). Clamped to [0, 1]."""
    raw = (os.environ.get("PULSE_DECORREL_RHO") or "").strip()
    if not raw:
        return DEFAULT_RHO_MAX
    try:
        v = float(raw)
    except ValueError:
        log.warning("PULSE_DECORREL_RHO=%r not a float; using %.2f", raw, DEFAULT_RHO_MAX)
        return DEFAULT_RHO_MAX
    return float(np.clip(v, 0.0, 1.0))


def instrument_corr_matrix(window: int = CORR_WINDOW, *,
                           spreads: pd.DataFrame | None = None) -> pd.DataFrame:
    """
    Trailing daily-change (Pearson) correlation across the spread universe.

    Cached per-process keyed by `window` when built from disk. Pass `spreads`
    explicitly (tests / to reuse an in-memory frame) to bypass the cache. Pairs
    with fewer than MIN_CORR_OVERLAP joint observations come back NaN and are set
    to 0.0 — unknown ⇒ treat as uncorrelated rather than suppress a trade on thin
    data.
    """
    use_cache = spreads is None
    if use_cache and window in _CORR_CACHE:
        return _CORR_CACHE[window]

    if spreads is None:
        from research.spread_universe import build_spread_series
        spreads = build_spread_series()

    chg  = spreads.diff().tail(window)
    corr = chg.corr(min_periods=MIN_CORR_OVERLAP).fillna(0.0)
    if len(corr):
        np.fill_diagonal(corr.values, 1.0)

    if use_cache:
        _CORR_CACHE[window] = corr
    return corr


def _lookup_corr(corr: pd.DataFrame, a: str, b: str) -> float:
    """Raw correlation between two spreads; 0.0 if either is absent from the matrix."""
    try:
        return float(corr.at[a, b])
    except (KeyError, ValueError, TypeError):
        return 0.0


def select_decorrelated(ranked: list[dict], *, rho_max: float | None = None,
                        max_positions: int | None = None,
                        corr: pd.DataFrame | None = None) -> dict:
    """
    Greedy decorrelated selection over a conviction-sorted opportunity list.

    `ranked` is live_ranker's list (each row carries 'spread', 'direction',
    'confidence', …). Rows are (re-)sorted by confidence desc defensively, then
    walked: take the first actionable (direction BUY/SELL) row; for each
    subsequent candidate, skip it if its SIGNED P&L correlation with ANY
    already-selected position is ≥ rho_max. NEUTRAL rows are never selected.

    Returns a summary dict:
      {
        "selected":     [spread, …]   # order taken (i.e. conviction order)
        "skipped":      [{"spread", "direction", "correlated_with", "rho", "reason"}]
        "rho_max":      float,
        "window":       int,
        "n_actionable": int,
        "n_selected":   int,
      }
    """
    if rho_max is None:
        rho_max = rho_max_from_env()
    if corr is None:
        corr = instrument_corr_matrix()

    # Defensive stable sort by confidence (get_recommendation already sorts; this
    # makes the function order-robust for direct callers / tests).
    actionable = sorted(
        [r for r in ranked if r.get("direction") in ("BUY", "SELL")],
        key=lambda r: (r.get("confidence") or 0.0),
        reverse=True,
    )

    selected: list[dict] = []
    selected_ids: list[str] = []
    skipped: list[dict] = []

    for cand in actionable:
        sp     = cand.get("spread")
        d_cand = _DIR_SIGN.get(cand.get("direction"), 0.0)

        if max_positions is not None and len(selected) >= max_positions:
            skipped.append({
                "spread":          sp,
                "direction":       cand.get("direction"),
                "correlated_with": None,
                "rho":             None,
                "reason":          "max_positions",
            })
            continue

        # Worst (largest positive) signed correlation against anything held.
        worst_with: str | None = None
        worst_rho = 0.0
        for chosen in selected:
            d2     = _DIR_SIGN.get(chosen.get("direction"), 0.0)
            signed = _lookup_corr(corr, sp, chosen.get("spread")) * d_cand * d2
            if signed > worst_rho:
                worst_rho  = signed
                worst_with = chosen.get("spread")

        if worst_with is not None and worst_rho >= rho_max:
            skipped.append({
                "spread":          sp,
                "direction":       cand.get("direction"),
                "correlated_with": worst_with,
                "rho":             round(float(worst_rho), 3),
                "reason":          "correlated",
            })
            continue

        selected.append(cand)
        selected_ids.append(sp)

    return {
        "selected":     selected_ids,
        "skipped":      skipped,
        "rho_max":      round(float(rho_max), 3),
        "window":       CORR_WINDOW,
        "n_actionable": len(actionable),
        "n_selected":   len(selected_ids),
    }


if __name__ == "__main__":
    import warnings; warnings.filterwarnings("ignore")
    logging.basicConfig(level=logging.INFO)
    from research.live_ranker import get_recommendation

    m = instrument_corr_matrix()
    print("Instrument correlation (trailing %dd daily changes):" % CORR_WINDOW)
    print(m.round(2).to_string())

    rec = get_recommendation()
    ranked = rec.get("ranked", [])
    print("\nRanked opportunities (conviction order):")
    for i, r in enumerate(ranked, 1):
        print(f"  #{i} {r['spread']:<14} {r['direction']:<8} z={r['z_score']:+.2f} conf={r['confidence']:.3f}")

    pf = select_decorrelated(ranked)
    print(f"\nDecorrelated book (rho_max={pf['rho_max']}): {pf['selected']}")
    for s in pf["skipped"]:
        print(f"  skipped {s['spread']:<14} ({s['reason']}"
              + (f", rho={s['rho']} vs {s['correlated_with']}" if s['reason'] == 'correlated' else "")
              + ")")
