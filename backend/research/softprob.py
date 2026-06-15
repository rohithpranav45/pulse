"""
Phase 2.8.5 — Soft regime probabilities.

The Sprint-3 grid (regimes.py) assigns each day to ONE cell via hard
thresholds on three axes. Two trading days with curve M1-M12 of -2.1
and -1.9 land in CONTANGO vs NEUTRAL even though the underlying market
state is nearly identical — the per-cell winning model + residual scale
flip discontinuously across that boundary. Phase 2.8.4's verdict
(global with regime-as-feature ties baseline) suggested the per-cell
*split* was the binding constraint; this module tests the complementary
hypothesis — does **softening** the split (sharing each day's predictive
weight across adjacent regimes) recover the alpha the hard cut leaks?

Mechanism — one logistic at each threshold, per axis:

    For an axis with K=3 buckets and cuts c1 < c2, the membership
    weights for value x with bandwidth h are:

      P(low)  = 1 - sigmoid((x - c1) / h)
      P(mid)  =     sigmoid((x - c1) / h) - sigmoid((x - c2) / h)
      P(high) =                              sigmoid((x - c2) / h)

    All non-negative, sum to 1, recover the hard classifier as h → 0,
    and converge on a uniform prior as h → ∞. The bandwidth h is set
    per axis so that a *1-unit* market move (e.g. $1/bbl on curve)
    moves the membership weight by ~25 pp at the boundary — soft
    enough to bleed signal across, sharp enough to keep the regime
    interpretation. Bandwidths recorded in `AXIS_BANDWIDTHS`.

Composite posterior:

    P(curve=c, inv=i, vol=v | x) = P_curve × P_inv × P_vol

    27-vector, sums to 1. Axes are treated independently — the same
    assumption regimes.composite_label() makes implicitly when it
    concatenates axis labels.

Pooled posterior:

    P(curve=c | x) — just the curve axis, 3-vector.

Public API
----------
  AXIS_BANDWIDTHS                              → bandwidth per axis
  axis_softprob(x, cuts, h)                    → np.ndarray(K) of probs
  curve_soft(m1_m12)                           → dict {CONTANGO:p, NEUTRAL:p, BACK:p}
  inv_soft(vs_5yr_pct)                         → dict {LOW:p, AVG:p, HIGH:p}
  vol_soft(rv_20d)                             → dict {CALM:p, NORMAL:p, STRESSED:p}
  composite_soft(curve_x, inv_x, vol_x)        → dict {27 composite labels → p}
  pooled_soft(m1_m12)                          → dict {CONTANGO:p, NEUTRAL:p, BACK:p}

All inputs accept None / NaN — in which case the function returns a
uniform prior over that axis (defensive; the walk-forward callers drop
NaN feature rows upstream, so this branch is rarely hit in practice).
"""

from __future__ import annotations

import math
from typing import Iterable

import numpy as np

from research.regimes import CURVE_BUCKETS, INV_BUCKETS, VOL_BUCKETS


# Hard cuts copied (not imported) so this module documents the soft variant
# self-contained next to its bandwidths. Mirror of regimes.classify_curve etc.
CURVE_CUTS = (-2.0,  5.0)
INV_CUTS   = (-4.0,  4.0)
VOL_CUTS   = (0.20,  0.35)

# Bandwidths — chosen so a 1-unit move ≈ 25 pp shift at the boundary for
# curve / inventory ($1/bbl or 1% of the 5y norm), and a 2.5pp vol shift
# moves vol membership by ~25 pp (vol axis is on a smaller numerical scale).
# All three picked by inspection on the trader thresholds, not tuned to PnL.
AXIS_BANDWIDTHS = {
    "curve": 1.0,
    "inv":   1.0,
    "vol":   0.025,
}


def _sigmoid(z: float) -> float:
    # Clip to keep np.exp stable for extreme z; same recipe as scipy.special.expit.
    if z >= 0:
        ez = math.exp(-z)
        return 1.0 / (1.0 + ez)
    ez = math.exp(z)
    return ez / (1.0 + ez)


def _is_bad(x) -> bool:
    return x is None or (isinstance(x, float) and (math.isnan(x) or not math.isfinite(x)))


def axis_softprob(x, cuts: Iterable[float], h: float) -> np.ndarray:
    """
    K-bucket soft membership for value `x` given `K-1` boundaries `cuts`
    and bandwidth `h`. Returns a length-K numpy array summing to 1.
    """
    cuts = list(cuts)
    K = len(cuts) + 1
    if _is_bad(x):
        return np.full(K, 1.0 / K, dtype=float)
    # z_i = P(x lies above cut i) = sigmoid((x - c_i)/h), monotone in i.
    # P(bucket_0)        = 1 - z_1
    # P(bucket_k>0,<K-1) = z_k - z_{k+1}     (= mass that's above cut k but not cut k+1)
    # P(bucket_{K-1})    = z_{K-1}
    z = [_sigmoid((float(x) - c) / h) for c in cuts]
    probs = np.empty(K, dtype=float)
    probs[0] = 1.0 - z[0]
    for k in range(1, K - 1):
        probs[k] = z[k - 1] - z[k]
    probs[K - 1] = z[K - 2]
    # Numerical safety: clip negatives to zero + renormalise. The sigmoid
    # construction is monotone so the differences are non-negative in exact
    # arithmetic; this is belt-and-braces for fp underflow.
    probs = np.clip(probs, 0.0, None)
    s = probs.sum()
    if s <= 0:
        return np.full(K, 1.0 / K, dtype=float)
    return probs / s


def curve_soft(m1_m12) -> dict:
    p = axis_softprob(m1_m12, CURVE_CUTS, AXIS_BANDWIDTHS["curve"])
    return {b: float(p[i]) for i, b in enumerate(CURVE_BUCKETS)}


def inv_soft(vs_5yr_pct) -> dict:
    p = axis_softprob(vs_5yr_pct, INV_CUTS, AXIS_BANDWIDTHS["inv"])
    return {b: float(p[i]) for i, b in enumerate(INV_BUCKETS)}


def vol_soft(rv_20d) -> dict:
    p = axis_softprob(rv_20d, VOL_CUTS, AXIS_BANDWIDTHS["vol"])
    return {b: float(p[i]) for i, b in enumerate(VOL_BUCKETS)}


def composite_soft(curve_x, inv_x, vol_x) -> dict:
    """
    27-vector soft posterior over composite "{CURVE}/{INV}/{VOL}" labels.
    Independence assumption matches regimes.composite_label() concatenation.
    """
    pc = curve_soft(curve_x)
    pi = inv_soft(inv_x)
    pv = vol_soft(vol_x)
    out: dict[str, float] = {}
    for c in CURVE_BUCKETS:
        for i in INV_BUCKETS:
            for v in VOL_BUCKETS:
                out[f"{c}/{i}/{v}"] = pc[c] * pi[i] * pv[v]
    return out


def pooled_soft(m1_m12) -> dict:
    """3-vector pooled (curve-axis-only) posterior — feeds pooled_soft leg."""
    return curve_soft(m1_m12)


if __name__ == "__main__":
    # Smoke check: at the boundary the soft prob should be ~50/50 across the
    # adjacent buckets; far from the boundary it should collapse to the hard
    # classifier.
    print("curve_soft(-2.0):", curve_soft(-2.0))   # at CONTANGO/NEUTRAL boundary
    print("curve_soft( 5.0):", curve_soft( 5.0))   # at NEUTRAL/BACK boundary
    print("curve_soft(-10.):", curve_soft(-10.0))  # deep CONTANGO
    print("curve_soft( 20.):", curve_soft( 20.0))  # deep BACK
    print("vol_soft(0.20):", vol_soft(0.20))
    print("inv_soft(0.0):",  inv_soft(0.0))
    print("composite_soft(0, 0, 0.25) top 5:")
    cs = composite_soft(0.0, 0.0, 0.25)
    for k, v in sorted(cs.items(), key=lambda kv: -kv[1])[:5]:
        print(f"  {k:<28} {v:.4f}")
