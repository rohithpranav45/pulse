"""
Define the 6 instruments we model in Phase 2 (Sprint 3 onward).

Brent legs sourced from /Data Brent C1-C31 daily settlements (2016-2026).
WTI legs sourced from /Data CL_WTI 1-min mids, collapsed to one settle per
session (`data_lake.get_wti_settlements()`) — flagged ESTIMATE in provenance
until the mentor delivers a real WTI C1-C3 daily settlement file (her Q5).

Instruments
-----------
  brent_m1_m2   :  c1 - c2                  (front carry)
  brent_m3_m6   :  c3 - c6                  (mid-curve carry)
  brent_fly_123 :  c1 - 2*c2 + c3           (front butterfly)
  wti_m1_m2     :  c1 - c2                  (WTI front carry)
  wti_m3_m6     :  c3 - c6                  (WTI mid-curve carry)
  wti_fly_123   :  c1 - 2*c2 + c3           (WTI front butterfly)

The mentor wants ONE recommendation per day — ranker picks among all 6.
"""

from __future__ import annotations

import os, sys
import pandas as pd

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

INSTRUMENTS = [
    "brent_m1_m2",
    "brent_m3_m6",
    "brent_fly_123",
    "wti_m1_m2",
    "wti_m3_m6",
    "wti_fly_123",
]

LABELS = {
    "brent_m1_m2":   "Brent M1-M2",
    "brent_m3_m6":   "Brent M3-M6",
    "brent_fly_123": "Brent front fly (M1-2×M2+M3)",
    "wti_m1_m2":     "WTI M1-M2",
    "wti_m3_m6":     "WTI M3-M6",
    "wti_fly_123":   "WTI front fly (M1-2×M2+M3)",
}

# Signed-quantity decomposition of each synthetic instrument.
# Positive qty = LONG that outright when the spread itself is held LONG.
# A SHORT spread position flips every leg.
# Used by paper_trading.py to open multi-leg positions and MTM each leg.
LEG_DEFS: dict[str, list[tuple[str, float]]] = {
    "brent_m1_m2":   [("c1", 1.0), ("c2", -1.0)],
    "brent_m3_m6":   [("c3", 1.0), ("c6", -1.0)],
    "brent_fly_123": [("c1", 1.0), ("c2", -2.0), ("c3", 1.0)],
    "wti_m1_m2":     [("c1", 1.0), ("c2", -1.0)],
    "wti_m3_m6":     [("c3", 1.0), ("c6", -1.0)],
    "wti_fly_123":   [("c1", 1.0), ("c2", -2.0), ("c3", 1.0)],
}

DESCRIPTIONS = {
    "brent_m1_m2":   "Front-month carry. Collapses in deep contango, blows out in extreme backwardation.",
    "brent_m3_m6":   "Mid-curve carry. More stable than front; regime-dependence is subtle but persistent.",
    "brent_fly_123": "Convexity of the front of the curve. Negative fly = kink, positive = smooth curve.",
    "wti_m1_m2":     "WTI front carry. Mirrors Brent but reacts more to Cushing inventory builds.",
    "wti_m3_m6":     "WTI mid-curve carry. Mid-back of the WTI curve, sensitive to refining demand.",
    "wti_fly_123":   "WTI front-curve convexity. Tracks short-term storage tightness.",
}


def _product(spread: str) -> str:
    return "wti" if spread.startswith("wti_") else "brent"


def _load_settlements(product: str) -> pd.DataFrame | None:
    from data_lake import get_brent_settlements, get_wti_settlements
    return get_wti_settlements() if product == "wti" else get_brent_settlements()


def current_leg_prices(spread: str) -> dict[str, float]:
    """Latest outright settlements for each contract referenced by `spread`."""
    if spread not in LEG_DEFS:
        return {}
    df = _load_settlements(_product(spread))
    if df is None or df.empty:
        return {}
    latest = df.iloc[-1]
    out: dict[str, float] = {}
    for contract, _ in LEG_DEFS[spread]:
        if contract in latest.index:
            out[contract] = float(latest[contract])
    return out


def build_spread_series() -> pd.DataFrame:
    """
    Return a DataFrame indexed by date with one column per instrument.
    Brent columns span 2016-2026 (Brent settlement file);
    WTI columns span 2021-2026 (synthesised from 1-min mids).
    Date index is the outer join — early dates may have NaN WTI values.
    """
    from data_lake import get_brent_settlements, get_wti_settlements

    brent = get_brent_settlements()
    if brent is None or brent.empty:
        raise RuntimeError("Brent settlements file missing — cannot build spread universe")

    out = pd.DataFrame(index=brent.index)
    out["brent_m1_m2"]   = brent["c1"] - brent["c2"]
    out["brent_m3_m6"]   = brent["c3"] - brent["c6"]
    out["brent_fly_123"] = brent["c1"] - 2.0 * brent["c2"] + brent["c3"]

    wti = get_wti_settlements()
    if wti is not None and not wti.empty:
        # Reindex to Brent dates so all 6 columns share the same index.
        wti_aligned = wti.reindex(out.index)
        out["wti_m1_m2"]   = wti_aligned["c1"] - wti_aligned["c2"]
        out["wti_m3_m6"]   = wti_aligned["c3"] - wti_aligned["c6"]
        out["wti_fly_123"] = wti_aligned["c1"] - 2.0 * wti_aligned["c2"] + wti_aligned["c3"]
    else:
        for col in ("wti_m1_m2", "wti_m3_m6", "wti_fly_123"):
            out[col] = float("nan")

    return out.dropna(how="all")


def current_values() -> dict:
    """Most-recent value of each instrument from settlements."""
    df = build_spread_series()
    out: dict = {"as_of": df.index[-1].strftime("%Y-%m-%d")}
    latest = df.iloc[-1]
    for k in INSTRUMENTS:
        v = latest.get(k)
        out[k] = float(v) if v is not None and v == v else None  # NaN guard
    return out


if __name__ == "__main__":
    df = build_spread_series()
    print(f"Spread universe: {len(df)} days, {df.index.min().date()} → {df.index.max().date()}")
    print("\nLatest values:")
    for k, v in current_values().items():
        if k == "as_of":
            print(f"  as_of: {v}")
        else:
            print(f"  {k:<18}  {('—' if v is None else f'{v:+.3f}')}")
    print("\nDescriptive stats (instrument coverage):")
    print(df.describe().T[["count", "mean", "std", "min", "max"]].round(3))
