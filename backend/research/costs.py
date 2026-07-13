"""
Round-trip transaction costs — SINGLE SOURCE OF TRUTH.
======================================================

Audit fix (2026-07-14). The per-spread RT cost table used to live as two
hand-mirrored copies (`walkforward.COST_PER_SPREAD_RT` ↔
`ab_test.COST_PER_SPREAD_RT`, kept in sync by an invariant test), and LIVE
inference didn't consult it at all — the entry gate could fire trades whose
take-profit was smaller than their own round trip (WTI M1-M2: TP $0.03 vs RT
cost $0.03 on the 2026-07-13 hero pick = zero net expectancy on a TP hit).

Both research modules now import from here (their module-level names are kept
so the mirror invariant still holds trivially), and `live_ranker` uses
`min_edge_for` to refuse entries that can't pay their own way.

Values are $/bbl per ROUND TRIP (entry + exit), quoted off desk guidance:
1 tick/leg + half-spread slippage; flies pay 3 legs, hence the higher RT.
"""

from __future__ import annotations

COST_PER_SPREAD_RT: dict[str, float] = {
    "brent_m1_m2":   0.030,
    "brent_m3_m6":   0.040,
    "brent_fly_123": 0.050,
    "wti_m1_m2":     0.030,
    "wti_m3_m6":     0.040,
    "wti_fly_123":   0.050,
}
COST_DEFAULT_RT = 0.040  # fallback when spread isn't in the table

# Live entry economics: the tuned exit takes profit at TP_FRAC × |deviation|
# (halfway to fair). For a trade to be worth firing, that expected capture must
# exceed the round trip by a margin — otherwise the desk is paying the broker
# to run stop-loss risk for free.
MIN_EDGE_COST_MULT = 2.0


def rt_cost_for(spread: str) -> float:
    """Round-trip cost ($/bbl) for one spread."""
    return COST_PER_SPREAD_RT.get(spread, COST_DEFAULT_RT)


def min_edge_for(spread: str, *, mult: float = MIN_EDGE_COST_MULT) -> float:
    """The minimum TP-capture ($/bbl) an entry must offer: `mult` × RT cost."""
    return mult * rt_cost_for(spread)
