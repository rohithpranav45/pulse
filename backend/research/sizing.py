"""
Position sizing — risk-based lot allocation for the automated paper book.
=========================================================================

A real desk does NOT trade a fixed number of lots. It sizes each position so
that **every trade risks the same small fraction of capital at its stop** —
volatility parity — then tilts by conviction and clamps with hard limits.

Model
-----
    risk_budget   R    = risk_pct × NAV                         ($/trade)
    stop_distance      = STOP_SIGMA × sigma                     ($/bbl, the tuned 2.5σ stop)
    risk_per_lot       = stop_distance × CONTRACT_MULTIPLIER     ($/lot; crude = 1,000 bbl/lot)
    base_lots          = floor( R / risk_per_lot )
    conviction_tilt    = clamp(|z| / Z_REF, TILT_MIN, TILT_MAX)
    lots               = clamp(round(base_lots × tilt), 1, MAX_LOTS_PER_TRADE)

Because risk_per_lot scales with the spread's own volatility, a wide-σ fly
automatically gets fewer lots than a tight front spread — each position risks
≈ the same dollars if it hits its stop. Stronger signals (bigger |z|) are
tilted up, capped so one trade can't dominate the book.

Worked example (NAV $1M, risk 0.75% → R=$7,500):
    Brent M1-M2  σ=$0.38 → stop $0.95 → $950/lot → base 7 lots; |z|=2.1 → ×1.5 → ~10 lots
    Brent fly    σ=$0.80 → stop $2.00 → $2,000/lot → base 3 lots

Everything is explainable in one line (mentor mandate: interpretability).

INVARIANT: STOP_SIGMA mirrors live_ranker.TUNED_SL_MULT — the sizing stop and
the live exit stop MUST be the same number, or lots are risked to a stop the
book never honours. Asserted in tests/test_invariants.py.
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass, asdict

# Crude futures: 1,000 barrels per lot, quoted $/bbl → $1,000 P&L per $1 move per lot.
CONTRACT_MULTIPLIER = 1_000

# Stop in sigmas — mirrors live_ranker.TUNED_SL_MULT (keep in lockstep).
STOP_SIGMA = 2.5

# Conviction tilt on entry z-score.
Z_REF    = 1.0
TILT_MIN = 0.5
TILT_MAX = 1.5

# Hard caps.
MAX_LOTS_PER_TRADE   = 50      # no single trade dominates the book
MAX_PORTFOLIO_RISK_PCT = 0.05  # total open risk-at-stop ≤ 5% of NAV


def _nav() -> float:
    try:
        return float(os.environ.get("PULSE_PAPER_NAV", "1000000"))
    except ValueError:
        return 1_000_000.0


def _risk_pct() -> float:
    try:
        return float(os.environ.get("PULSE_PAPER_RISK_PCT", "0.0075"))
    except ValueError:
        return 0.0075


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


@dataclass
class SizeDecision:
    lots: int                 # contracts to trade
    barrels: int              # lots × CONTRACT_MULTIPLIER (the paper book's `size`)
    risk_per_lot: float       # $ at stop, per lot
    dollar_risk: float        # $ at stop, this position
    stop_distance: float      # $/bbl
    tilt: float               # conviction multiplier applied
    rationale: str            # one-line, mentor-facing

    def as_dict(self) -> dict:
        return asdict(self)


def size_trade(
    spread: str,
    sigma: float,
    z: float,
    *,
    nav: float | None = None,
    risk_pct: float | None = None,
) -> SizeDecision:
    """Risk-based lots for one spread trade.

    sigma : the σ used for the stop ($/bbl) — resid_std (model) or rolling std (baseline).
    z     : entry z-score (signed); only |z| matters for sizing.
    """
    nav = _nav() if nav is None else float(nav)
    risk_pct = _risk_pct() if risk_pct is None else float(risk_pct)

    sigma = abs(float(sigma))
    if sigma <= 0 or not math.isfinite(sigma):
        # Degenerate σ — fall back to a single lot rather than divide by zero.
        return SizeDecision(1, CONTRACT_MULTIPLIER, 0.0, 0.0, 0.0, 1.0,
                            f"{spread}: σ≤0, defaulting to 1 lot")

    risk_budget   = risk_pct * nav
    stop_distance = STOP_SIGMA * sigma
    risk_per_lot  = stop_distance * CONTRACT_MULTIPLIER
    base_lots     = risk_budget / risk_per_lot

    tilt = _clamp(abs(z) / Z_REF, TILT_MIN, TILT_MAX)
    lots = int(round(base_lots * tilt))
    lots = int(_clamp(lots, 1, MAX_LOTS_PER_TRADE))

    dollar_risk = lots * risk_per_lot
    rationale = (
        f"{spread}: R=${risk_budget:,.0f} ({risk_pct:.2%}×${nav:,.0f}); "
        f"stop {STOP_SIGMA}σ=${stop_distance:.2f}/bbl → ${risk_per_lot:,.0f}/lot; "
        f"base {base_lots:.1f} × tilt {tilt:.2f} (|z|={abs(z):.1f}) → {lots} lots "
        f"(risk ${dollar_risk:,.0f})"
    )
    return SizeDecision(
        lots=lots,
        barrels=lots * CONTRACT_MULTIPLIER,
        risk_per_lot=round(risk_per_lot, 2),
        dollar_risk=round(dollar_risk, 2),
        stop_distance=round(stop_distance, 4),
        tilt=round(tilt, 3),
        rationale=rationale,
    )


def portfolio_risk_ok(open_dollar_risk: float, new_dollar_risk: float,
                      nav: float | None = None) -> bool:
    """True if adding new_dollar_risk keeps total open risk ≤ MAX_PORTFOLIO_RISK_PCT of NAV."""
    nav = _nav() if nav is None else float(nav)
    return (open_dollar_risk + new_dollar_risk) <= MAX_PORTFOLIO_RISK_PCT * nav
