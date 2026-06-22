"""
vol_target.py — Phase 7 / 2.8.10 portfolio vol-targeting.

The last open Phase 2.8.x model leg. Phase 2.7 sized the regime leg uniformly
(full/half/kelly); this leg sizes the *book* so its risk is roughly constant
through time, reusing the two risk primitives already shipped:

  • shock_engine.risk_scale  — per-position vol-target × stress de-risk:
        vol_scale   = clip(target_pos_vol / forecast_vol_i, floor, cap)
        stress_scale= 1 − derisk · P(stress)
    Equalises each spread's $/bbl risk (a $-vol fly no longer dominates a tight
    front spread) and cuts size INTO a shock.
  • gated_select.select_decorrelated — the desk's actual book: greedily keep the
    highest-conviction trade, drop same-signed correlated ones (no concentration).

On top of those two, a **portfolio overlay** scales the whole book by a single
factor k so its ex-ante vol — computed from the kept positions' risks and the
trailing correlation matrix — hits a target book vol. After decorrelation the
cross-correlations are small, so the overlay mostly counts the *effective number
of independent bets* and adds exposure when the book is thin / hedged, cuts it
when it is full / correlated. That is portfolio vol-targeting.

This is a PURE POST-PROCESSING leg over the persisted walk-forward trade tapes
(like Phase 5's --horizon-only): the entry signals (z → direction) are the ones
the gated/baseline legs already fired; we only reweight the notionals. No model
retraining. The honest question: does targeting portfolio vol improve NET Sharpe
and shrink max-drawdown vs the un-targeted gated/baseline book?

Everything is dependency-injectable (spreads/stress/corr passed in) so the unit
tests are hermetic — no /Data, no model pkls, no live cache.

Public API
----------
  spread_vol_frame(spreads, win) -> pd.DataFrame   trailing annualised $/bbl vol
  book_vol(positions, corr) -> float               ex-ante book vol from risks+corr
  size_day(rows, *, fcast_vol, p_stress, corr, flags…) -> list[(row, notional)]
  apply_vol_target(tape, *, spread_vol, stress, corr, flags…) -> list[dict]
  VolTargetConfig                                  the tunables for one variant
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from research import shock_engine
from research import gated_select

# Trailing window (trading days) for each spread's realised $/bbl vol. Matches
# the 20-day forward horizon the trades are held over, so the vol estimate is in
# the same units the position's PnL is exposed to.
VOL_WIN = 20
# Stress detector burn-in: fit on 2016→2019 only (causal), score forward. Matches
# shock_engine's own validated usage — OOS for 2020+. (Tape rows in 2018-2019 see
# an in-sample stress read; the bulk 2020-2026 window is genuinely OOS.)
STRESS_FIT_UNTIL = "2019-01-01"
# Portfolio overlay clamp — never lever the book past 2x or below 0.25x of the
# per-position target, so a single quiet/violent day can't blow the exposure up.
K_FLOOR, K_CAP = 0.25, 2.0
# The decorrelated front-curve universe admits ~2 independent bets, so a book of
# two uncorrelated target-vol positions should sit near k≈1.
TARGET_N_BETS = 2.0

_DIR_SIGN = {"BUY": 1.0, "SELL": -1.0}


@dataclass
class VolTargetConfig:
    """Tunables for one vol-target variant. Toggling the four flags isolates the
    marginal contribution of each layer (decorrelation / parity / stress / book
    overlay)."""
    decorrelate:     bool  = True
    vol_scale:       bool  = True   # per-position risk parity (vol_scale leg)
    stress:          bool  = True   # stress de-risk leg of risk_scale
    portfolio:       bool  = True   # portfolio-vol overlay
    rho_max:         float = gated_select.DEFAULT_RHO_MAX
    target_pos_vol:  float | None = None   # None → median spread vol (centres ~1)
    target_book_vol: float | None = None   # None → target_pos_vol · √TARGET_N_BETS
    floor:           float = shock_engine.SIZE_FLOOR
    cap:             float = shock_engine.SIZE_CAP
    derisk:          float = shock_engine.STRESS_DERISK
    vol_win:         int   = VOL_WIN


def spread_vol_frame(spreads: pd.DataFrame, win: int = VOL_WIN) -> pd.DataFrame:
    """Trailing annualised $/bbl realised vol per spread (std of daily changes
    over `win` days × √252). Causal — value at day d uses only changes ≤ d."""
    return spreads.diff().rolling(win).std() * np.sqrt(252.0)


def stress_series(settle: pd.DataFrame | None = None,
                  *, fit_until: str = STRESS_FIT_UNTIL) -> pd.Series:
    """Date-indexed causal P(stress) from the GMM + sticky-HMM detector, fit on
    the burn-in window and scored forward (look-ahead-free filter)."""
    feats = shock_engine.build_stress_features(settle)
    det = shock_engine.StressDetector().fit(feats, fit_until=fit_until)
    return det.p_stress(feats)


def book_vol(positions: list[tuple[str, float, float]], corr: pd.DataFrame) -> float:
    """
    Ex-ante annualised book vol from a list of (spread, dir_sign, pos_risk),
    where pos_risk_i = scale_i · forecast_vol_i is the position's $/bbl risk.

    Var = Σ_i,j pos_risk_i · pos_risk_j · ρ_ij · dir_i · dir_j   (ρ_ii = 1).
    Signed by direction so a hedged (opposite-direction correlated) pair lowers
    book vol, exactly as gated_select's signed-corr selection intends.
    """
    if not positions:
        return 0.0
    var = 0.0
    for i, (sp_i, d_i, r_i) in enumerate(positions):
        for j, (sp_j, d_j, r_j) in enumerate(positions):
            rho = 1.0 if i == j else gated_select._lookup_corr(corr, sp_i, sp_j)
            var += r_i * r_j * rho * d_i * d_j
    return float(np.sqrt(var)) if var > 0 else 0.0


def size_day(
    rows: list[dict],
    *,
    fcast_vol: dict[str, float],
    p_stress: float,
    corr: pd.DataFrame,
    cfg: VolTargetConfig,
    target_pos_vol: float,
    target_book_vol: float,
) -> list[tuple[dict, float]]:
    """
    Size one day's fired trades into a vol-targeted book. Returns a list of
    (row, notional) for the positions actually held (NEUTRAL / decorrelation-
    skipped rows are dropped). `fcast_vol` maps spread → that day's forecast vol;
    `p_stress` is the day's P(stress).
    """
    fired = [r for r in rows
             if r.get("direction") in ("BUY", "SELL") and r.get("fwd_pnl") is not None]
    if not fired:
        return []

    # 1. Decorrelated selection (conviction = |z|).
    if cfg.decorrelate:
        ranked = [{"spread": r["spread"], "direction": r["direction"],
                   "confidence": abs(float(r.get("z") or 0.0))} for r in fired]
        sel = gated_select.select_decorrelated(ranked, rho_max=cfg.rho_max, corr=corr)
        keep_ids = set(sel["selected"])
        fired = [r for r in fired if r["spread"] in keep_ids]
        if not fired:
            return []

    # 2. Per-position scale via risk_scale (vol-target × stress de-risk).
    scales: dict[str, float] = {}
    risks:  list[tuple[str, float, float]] = []
    for r in fired:
        sp = r["spread"]
        fv = fcast_vol.get(sp)
        if fv is None or not np.isfinite(fv) or fv <= 0:
            fv = target_pos_vol            # unknown vol → neutral scale
        if cfg.vol_scale:
            ps = p_stress if cfg.stress else 0.0
            s = float(shock_engine.risk_scale(
                ps, fv, target_vol=target_pos_vol,
                floor=cfg.floor, cap=cfg.cap, derisk=cfg.derisk,
            ))
        else:
            # No parity: stress de-risk only (or flat 1.0 if stress off too).
            s = (1.0 - cfg.derisk * p_stress) if cfg.stress else 1.0
        scales[sp] = s
        risks.append((sp, _DIR_SIGN.get(r["direction"], 0.0), s * fv))

    # 3. Portfolio overlay: scale the whole book to target book vol.
    k = 1.0
    if cfg.portfolio:
        bv = book_vol(risks, corr)
        if bv > 0:
            k = float(np.clip(target_book_vol / bv, K_FLOOR, K_CAP))

    return [(r, k * scales[r["spread"]]) for r in fired]


def apply_vol_target(
    tape: list[dict],
    *,
    spread_vol: pd.DataFrame,
    stress: pd.Series,
    corr: pd.DataFrame,
    cfg: VolTargetConfig,
    normalize: bool = True,
) -> list[dict]:
    """
    Reweight a trade tape into a vol-targeted book. Groups rows by date, sizes
    each day via `size_day`, and (when `normalize`) rescales all notionals so the
    mean held notional = 1.0 — matched average exposure to the unit-notional
    un-targeted book, so max-drawdown is comparable (Sharpe/Calmar are
    leverage-invariant regardless).

    Each output row copies the source row with `fwd_pnl` scaled by the notional
    and `sizing_scale` set to it (so walkforward._cost_for scales the RT cost in
    step). Only held positions appear in the output.
    """
    # Centring constants.
    tpv = cfg.target_pos_vol
    if tpv is None:
        med = float(np.nanmedian(spread_vol.values)) if spread_vol.size else 1.0
        tpv = med if np.isfinite(med) and med > 0 else 1.0
    tbv = cfg.target_book_vol if cfg.target_book_vol is not None else tpv * np.sqrt(TARGET_N_BETS)

    # Group by date, preserving order.
    by_date: dict[str, list[dict]] = {}
    for r in tape:
        by_date.setdefault(r.get("date"), []).append(r)

    # Fast as-of lookups: position of each date in the (sorted) vol/stress index.
    out: list[tuple[dict, float]] = []
    for date, rows in by_date.items():
        try:
            d = pd.Timestamp(date)
        except Exception:
            continue
        # forecast vol per spread as-of d (last known ≤ d)
        fcast_vol: dict[str, float] = {}
        if not spread_vol.empty:
            sv = spread_vol.loc[:d]
            if len(sv):
                last = sv.iloc[-1]
                fcast_vol = {sp: float(last.get(sp)) for sp in spread_vol.columns
                             if pd.notna(last.get(sp))}
        ps = 0.0
        if stress is not None and len(stress):
            ss = stress.loc[:d]
            if len(ss) and np.isfinite(ss.iloc[-1]):
                ps = float(ss.iloc[-1])
        out.extend(size_day(rows, fcast_vol=fcast_vol, p_stress=ps, corr=corr,
                            cfg=cfg, target_pos_vol=tpv, target_book_vol=tbv))

    if normalize and out:
        mean_n = float(np.mean([n for _, n in out]))
        if mean_n > 0:
            out = [(r, n / mean_n) for r, n in out]

    sized: list[dict] = []
    for r, n in out:
        nr = dict(r)
        nr["fwd_pnl"] = round(float(r["fwd_pnl"]) * n, 4) if r.get("fwd_pnl") is not None else None
        nr["sizing_scale"] = round(float(n), 4)
        sized.append(nr)
    return sized


if __name__ == "__main__":
    import json
    import warnings; warnings.filterwarnings("ignore")
    from research.spread_universe import build_spread_series

    spreads = build_spread_series()
    sv = spread_vol_frame(spreads)
    ps = stress_series()
    corr = gated_select.instrument_corr_matrix()
    print("median spread vol ($/bbl ann.):", round(float(np.nanmedian(sv.values)), 3))
    tape = json.load(open(os.path.join(_BACKEND, "data", "research", "gated_trades.json")))
    sized = apply_vol_target(tape, spread_vol=sv, stress=ps, corr=corr, cfg=VolTargetConfig())
    print(f"gated tape {len(tape)} rows → vol-targeted book {len(sized)} positions")
    scales = [r["sizing_scale"] for r in sized]
    print(f"notional mean={np.mean(scales):.3f} median={np.median(scales):.3f} "
          f"min={np.min(scales):.3f} max={np.max(scales):.3f}")
