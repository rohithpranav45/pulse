"""
garch_vol.py — conditional-volatility (GARCH) forecasting for the risk layer.

Phase 7 vol-targeting (`vol_target.py`) sizes each position by a *trailing 20-day
realised* $/bbl vol (`vol_target.spread_vol_frame`). That window is a lagging,
equal-weight estimator. This module produces the GARCH alternative — a causal
one-step-ahead **conditional** vol forecast (vol clustering: shocks beget shocks)
— as a DROP-IN frame with the same shape, so it can be fed straight into
`vol_target.apply_vol_target(spread_vol=…)`.

Two specs: plain GARCH(1,1) and GJR-GARCH (`o=1`, asymmetric — vol reacts more to
down moves), Student-t innovations. Fit on the daily *changes* of each spread (a
calendar spread crosses zero, so % returns are undefined; $/bbl changes are the
right scale and match what `spread_vol_frame` measures).

Causality: the value at day d uses only data ≤ d. We refit every `REFIT_EVERY`
trading days on the expanding window and roll the conditional-variance recursion
    σ²_t = ω + α·ε²_{t-1} + γ·1[ε_{t-1}<0]·ε²_{t-1} + β·σ²_{t-1}
forward each day in between (so there's a fresh one-step forecast daily without a
daily refit). NaN before `MIN_TRAIN`, and a graceful fall-through if a fit fails.

**Graded verdict (see walkforward.run_garch_only / methodology PDF):** as a 1-step
*forecast*, GARCH does NOT beat the trailing-20d window (QLIKE prefers trailing on
the mean / 3-of-6 spreads). But as the *sizing input* to vol-targeting it
materially improves the risk-adjusted book — Calmar 2.01 → ~3.1, Sharpe
+0.198 → +0.28, max-DD −112 → −95 (robust across plain/GJR) — turning Phase 7
from a Sharpe-losing DD tool into a Calmar-improving one. Still below the baseline
(+0.372 / Calmar 4.99), so it doesn't change the headline; it's a risk-layer
refinement, not new alpha.

Public API
----------
  garch_vol_frame(spreads, *, asym=True, ...) -> pd.DataFrame   # cached, drop-in
  forecast_accuracy(spreads, ...) -> dict                        # QLIKE GARCH vs roll20
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

log = logging.getLogger("pulse.research.garch_vol")

# ── Config ───────────────────────────────────────────────────────────────────
SCALE       = 100.0   # fit in cents — `arch` wants O(1-1000); spread $-changes are O(0.1-0.5)
REFIT_EVERY = 21      # refit cadence in trading days (~monthly); recursion rolls daily between
MIN_TRAIN   = 252     # ~1y before the first forecast
ANNUALISE   = np.sqrt(252.0)

# Per-process cache (the spread history doesn't move within a run). Keyed by spec.
_VOL_CACHE: dict[tuple, pd.DataFrame] = {}


def _causal_sigma(d: pd.Series, *, asym: bool, refit_every: int = REFIT_EVERY,
                  min_train: int = MIN_TRAIN, scale: float = SCALE) -> pd.Series:
    """
    Causal one-step-ahead conditional vol (daily $/bbl) for one spread's change
    series. Refit every `refit_every` days; roll the variance recursion forward
    daily in between. NaN before `min_train`; on a fit failure with no prior
    params, the day is left NaN (caller falls back to the realised frame).
    """
    from arch import arch_model

    d = d.dropna()
    n = len(d)
    sig = pd.Series(index=d.index, dtype=float)
    if n <= min_train:
        return sig
    y = d.values * scale
    o = 1 if asym else 0

    params = None      # (omega, alpha, beta, gamma)
    mu = 0.0
    sig2_prev = None
    last_fit = -10 ** 9

    for t in range(n):
        if t < min_train:
            continue
        if params is None or (t - last_fit) >= refit_every:
            try:
                res = arch_model(y[:t], mean="Constant", vol="GARCH",
                                 p=1, o=o, q=1, dist="t").fit(disp="off", show_warning=False)
                p = res.params
                mu = float(p.get("mu", 0.0))
                params = (
                    float(p["omega"]),
                    float(p.get("alpha[1]", 0.0)),
                    float(p.get("beta[1]", 0.0)),
                    float(p.get("gamma[1]", 0.0)),
                )
                sig2_prev = float(res.conditional_volatility[-1] ** 2)
                last_fit = t
            except Exception as exc:  # pragma: no cover — optimiser non-convergence
                if params is None:
                    continue
                log.debug("garch refit failed at t=%d, rolling prior params: %s", t, exc)
        w, a, b, g = params
        eps_prev = y[t - 1] - mu
        ind = 1.0 if eps_prev < 0 else 0.0
        floor = w / max(1.0 - a - b - 0.5 * g, 1e-3)
        sig2_t = w + a * eps_prev ** 2 + g * ind * eps_prev ** 2 + b * (sig2_prev if sig2_prev else floor)
        sig2_t = max(sig2_t, 1e-12)
        sig.iloc[t] = np.sqrt(sig2_t) / scale
        sig2_prev = sig2_t

    return sig


def garch_vol_frame(spreads: pd.DataFrame, *, asym: bool = True,
                    refit_every: int = REFIT_EVERY, min_train: int = MIN_TRAIN,
                    use_cache: bool = True) -> pd.DataFrame:
    """
    Causal annualised $/bbl conditional-vol frame per spread — a DROP-IN for
    `vol_target.spread_vol_frame` (same index/columns, ann. by √252). `asym=True`
    uses GJR-GARCH (asymmetric); `asym=False` plain GARCH(1,1).
    """
    key = (id(spreads), asym, refit_every, min_train, tuple(spreads.columns))
    if use_cache and key in _VOL_CACHE:
        return _VOL_CACHE[key]
    out = pd.DataFrame(
        {sp: _causal_sigma(spreads[sp].diff(), asym=asym,
                           refit_every=refit_every, min_train=min_train) * ANNUALISE
         for sp in spreads.columns}
    ).reindex(spreads.index)   # same shape as vol_target.spread_vol_frame (NaN prefix)
    if use_cache:
        _VOL_CACHE[key] = out
    return out


def _qlike(realised2: np.ndarray, pred2: np.ndarray) -> tuple[float, int]:
    """QLIKE loss E[log σ²_pred + realised²/σ²_pred] — robust to the noisy
    realised-variance proxy (down-weights huge realised spikes). Lower = better."""
    m = np.isfinite(realised2) & np.isfinite(pred2) & (pred2 > 0)
    r2 = realised2[m]; p2 = pred2[m]
    if r2.size == 0:
        return float("nan"), 0
    return float(np.mean(np.log(p2) + r2 / p2)), int(m.sum())


def forecast_accuracy(spreads: pd.DataFrame, *, win: int = 20) -> dict:
    """
    Per-spread QLIKE of the next-day squared change for three 1-step variance
    forecasts: plain GARCH, GJR-GARCH, and the trailing-`win` realised window
    (what vol_target uses). Returns {spread -> {garch, gjr, roll}} + a 'mean' row.
    """
    gjr   = garch_vol_frame(spreads, asym=True)  / ANNUALISE   # back to daily $
    plain = garch_vol_frame(spreads, asym=False) / ANNUALISE
    out: dict[str, dict] = {}
    acc = {"garch": [], "gjr": [], "roll": []}
    for sp in spreads.columns:
        d = spreads[sp].diff()
        realised_next2 = (d.shift(-1) ** 2)
        roll = d.rolling(win).std()
        qg, _ = _qlike(realised_next2.reindex(plain.index).values, (plain[sp] ** 2).values)
        qj, _ = _qlike(realised_next2.reindex(gjr.index).values,   (gjr[sp] ** 2).values)
        qr, n = _qlike(realised_next2.reindex(roll.index).values,  (roll ** 2).values)
        out[sp] = {"garch": round(qg, 4), "gjr": round(qj, 4), "roll": round(qr, 4), "n": n}
        for k, v in (("garch", qg), ("gjr", qj), ("roll", qr)):
            if np.isfinite(v):
                acc[k].append(v)
    out["mean"] = {k: round(float(np.mean(v)), 4) if v else None for k, v in acc.items()}
    return out


if __name__ == "__main__":
    import warnings; warnings.filterwarnings("ignore")
    logging.basicConfig(level=logging.INFO)
    from research.spread_universe import build_spread_series

    spreads = build_spread_series()
    print("=== GARCH vs trailing-20d — 1-step variance forecast (QLIKE, lower=better) ===")
    fa = forecast_accuracy(spreads)
    print(f"  {'spread':14} {'GARCH':>9} {'GJR':>9} {'roll20':>9}  winner")
    for sp in spreads.columns:
        r = fa[sp]
        best = min(("garch", "gjr", "roll"), key=lambda k: r[k])
        tag = {"garch": "GARCH", "gjr": "GJR", "roll": "roll20"}[best]
        print(f"  {sp:14} {r['garch']:>9.4f} {r['gjr']:>9.4f} {r['roll']:>9.4f}  {tag}")
    m = fa["mean"]
    print(f"  {'MEAN':14} {m['garch']:>9.4f} {m['gjr']:>9.4f} {m['roll']:>9.4f}")
    print("\n  Verdict: trailing-20d typically wins the 1-step forecast; GARCH's value is")
    print("  in the risk/sizing layer, not point forecasting (see --garch-only leg).")
