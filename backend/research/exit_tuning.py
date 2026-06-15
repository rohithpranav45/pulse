"""
Phase 2.9.1 — constrained win-rate optimization.

Builds on the Phase 2.9.0 path-aware exit simulator (exit_sim.py). Sweeps the
trading-rule knobs on the SAVED gated_blend tape (no model retraining — pure
post-processing) and finds the config that maximises win rate SUBJECT TO hard
constraints, because win rate alone is gameable (a tiny take-profit wins almost
every trade but bleeds money once fees and the occasional stop are counted).

Knobs swept
-----------
  entry threshold |z|   ∈ {0.5, 0.75, 1.0, 1.5}   (trade only |z| ≥ thr)
  TP placement (frac)   ∈ {1.0 (=p50), 0.5 (halfway), 0.25 (quarter-toward-fair)}
                          tp = entry + frac × (anchor − entry); anchor = p50
                          (regime leg) / 252d rolling mean (baseline leg)
  SL multiple           ∈ {1.0, 1.5, 2.0, 2.5} × sigma  (resid_std / rolling std)
  time-stop             ∈ {10, 20, 30} days
  spread subset         ∈ {all 6, drop the M3-M6 laggards (brent_m3_m6, wti_m3_m6)}

4 × 3 × 4 × 3 × 2 = 288 configs.

Constraints (binding — keep win-rate honest)
---------------------------------------------
  • NET profit factor > 1.0            (profitable after transaction costs)
  • NET Sharpe (ann. √(252/20)) ≥ the CURRENT default config's NET Sharpe
    (entry 0.5 / TP p50 / SL 1.5 / hold 20 / all-6 spreads). "Not worse than
    current gated NET", made apples-to-apples on the exit-sim tape.
  • n_closed ≥ MIN_N  (don't trust stats on a tiny filtered subset)

NET = gross realised PnL − Phase 2.8.6 round-trip cost (COST_PER_SPREAD_RT) per
closed trade. SCRATCH trades pay the round-trip cost (a real open+close), so
fee-dominated configs are penalised — exactly the gaming guard we want. Sharpe
is annualised at the FIXED √(252/20), NOT √(252/mean_hold): a turnover-aware
annualisation would REWARD tiny-TP fast-churn configs and defeat the guardrail.

Run
---
    python -m backend.research.exit_tuning            # uses exit_sim_tapes.json
Writes backend/data/research/exit_tuning_report.json.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from collections import Counter
from datetime import datetime
from itertools import product
from pathlib import Path

import numpy as np

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from research import exit_sim as es           # noqa: E402
from research import walkforward as wf        # noqa: E402

log = logging.getLogger("pulse.research.exit_tuning")

_REPORT_FILE = Path(__file__).parent.parent / "data" / "research" / "exit_tuning_report.json"

# ── Sweep grid ────────────────────────────────────────────────────────────────
Z_THRESHOLDS = [0.5, 0.75, 1.0, 1.5]
TP_FRACS     = [1.0, 0.5, 0.25]            # 1.0 = p50; 0.5 = halfway; 0.25 = quarter-toward-fair
SL_MULTS     = [1.0, 1.5, 2.0, 2.5]
HOLDS        = [10, 20, 30]
LAGGARDS     = {"brent_m3_m6", "wti_m3_m6"}
SUBSETS      = {
    "all6":     None,                       # None = keep every spread
    "no_m3m6":  LAGGARDS,                    # drop these
}
MIN_N        = 50                           # min closed trades for a trustworthy config

# The current production exit rule (the 2.9.0 default) — its NET Sharpe is the floor.
DEFAULT_CFG = {"z": 0.5, "tp": 1.0, "sl": 1.5, "hold": 20, "subset": "all6"}

# Phase 2.8.6 reference: documented directional gated NET Sharpe (fixed 20d, after
# costs). Shown for context; the binding floor is the default config's exit-sim
# NET Sharpe, computed below on the same tape/metric as the candidates.
DIRECTIONAL_GATED_NET_SHARPE = 0.297

ANN = np.sqrt(252.0 / 20.0)                 # fixed-horizon annualisation (gaming-resistant)


def _cost(spread: str) -> float:
    return wf.COST_PER_SPREAD_RT.get(spread, wf.COST_DEFAULT_RT)


def _filter(tape: list[dict], subset_drop, thr: float) -> list[dict]:
    """Keep fired rows in the spread subset with |z| ≥ thr."""
    out = []
    for t in tape:
        sp = t.get("spread")
        if subset_drop is not None and sp in subset_drop:
            continue
        if t.get("direction") not in ("BUY", "SELL"):
            continue
        z = t.get("z")
        if z is None or not np.isfinite(z) or abs(float(z)) < thr:
            continue
        out.append(t)
    return out


def _metrics(closed: list[dict]) -> dict:
    """Gross + NET metrics for a list of closed trades."""
    n = len(closed)
    if n == 0:
        return {"n": 0}
    gross = np.array([c["realised_pnl"] for c in closed], dtype=float)
    cost  = np.array([_cost(c["spread"]) for c in closed], dtype=float)
    net   = gross - cost
    holds = np.array([c["hold_days"] for c in closed], dtype=float)
    reasons = Counter(c["close_reason"] for c in closed)

    def _pf(a):
        w = a[a > 0].sum(); l = -a[a < 0].sum()
        return round(float(w / l), 4) if l > 0 else None

    def _sharpe(a):
        sd = a.std(ddof=1) if len(a) > 1 else 0.0
        return round(float(a.mean() / sd * ANN), 4) if sd > 0 else None

    return {
        "n":              n,
        "gross_win_rate": round(float((gross > 0).mean()), 4),
        "net_win_rate":   round(float((net   > 0).mean()), 4),
        "gross_pf":       _pf(gross),
        "net_pf":         _pf(net),
        "gross_exp":      round(float(gross.mean()), 4),
        "net_exp":        round(float(net.mean()), 4),
        "net_sharpe20":   _sharpe(net),
        "net_sharpe_turnover": (
            round(float(net.mean() / net.std(ddof=1) * np.sqrt(252.0 / max(holds.mean(), 1e-9))), 4)
            if len(net) > 1 and net.std(ddof=1) > 0 else None
        ),
        "mean_hold":      round(float(holds.mean()), 2),
        "reason_mix":     {r: int(reasons.get(r, 0)) for r in ("TP", "SL", "TIME", "SCRATCH")},
    }


def run() -> dict:
    from research.spread_universe import build_spread_series

    tapes = es.load_tapes()
    if tapes is None:
        raise FileNotFoundError(
            f"{es._TAPES_FILE} not found — run `python -m research.exit_sim` first.")
    gated = tapes["gated"]
    spreads = build_spread_series()
    log.info("Loaded gated tape: %d rows (generated_at=%s)", len(gated), tapes.get("generated_at"))

    results: list[dict] = []
    for z, tp, sl, hold, (sub_name, sub_drop) in product(
            Z_THRESHOLDS, TP_FRACS, SL_MULTS, HOLDS, SUBSETS.items()):
        rows = _filter(gated, sub_drop, z)
        closed, _ = es.simulate_tape(rows, spreads, max_hold=hold, sl_mult=sl, tp_frac=tp)
        m = _metrics(closed)
        cfg = {"z": z, "tp": tp, "sl": sl, "hold": hold, "subset": sub_name}
        results.append({"config": cfg, **m})

    # Locate the default config + its NET Sharpe floor.
    def _is(cfg, ref):
        return all(abs(cfg[k] - ref[k]) < 1e-9 if isinstance(ref[k], (int, float)) else cfg[k] == ref[k]
                   for k in ref)
    default = next(r for r in results if _is(r["config"], DEFAULT_CFG))
    floor = default.get("net_sharpe20")
    log.info("Default config NET Sharpe (floor) = %s  (gross win %.1f%%, n=%d)",
             floor, 100 * default["gross_win_rate"], default["n"])

    # Feasible = NET PF > 1, NET Sharpe ≥ floor, enough trades.
    def _feasible(r):
        return (r.get("n", 0) >= MIN_N
                and r.get("net_pf") is not None and r["net_pf"] > 1.0
                and r.get("net_sharpe20") is not None
                and floor is not None and r["net_sharpe20"] >= floor - 1e-9)

    feasible = [r for r in results if _feasible(r)]
    feasible.sort(key=lambda r: (r["gross_win_rate"], r.get("net_sharpe20") or 0, r.get("net_exp") or 0),
                  reverse=True)

    # What pure win-rate maximisation (ignoring constraints) would have chosen —
    # to show the gaming the constraints prevent.
    valid_n = [r for r in results if r.get("n", 0) >= MIN_N and r.get("gross_win_rate") is not None]
    best_unconstrained = max(valid_n, key=lambda r: r["gross_win_rate"]) if valid_n else None

    winner = feasible[0] if feasible else None
    clears_50 = any(r["gross_win_rate"] >= 0.50 for r in feasible)

    if winner is None:
        note = ("NO config satisfies NET PF>1 AND NET Sharpe ≥ default. The current "
                "default exit rule is on the efficient frontier — tuning the knobs "
                "cannot raise win rate without violating profitability/risk. Keep the default.")
    elif _is(winner["config"], DEFAULT_CFG):
        note = ("The DEFAULT config is the constrained optimum — no swept variation "
                "raises win rate while holding NET PF>1 and NET Sharpe ≥ default. Keep it.")
    elif not clears_50:
        note = (f"Best feasible win rate is {winner['gross_win_rate']*100:.1f}% (< 50%). "
                "Reporting the best achievable; not gaming TP/SL to manufacture a >50% number.")
    else:
        note = (f"Winner lifts win rate to {winner['gross_win_rate']*100:.1f}% "
                f"(default {default['gross_win_rate']*100:.1f}%) while holding NET PF "
                f"{winner['net_pf']} (>1) and NET Sharpe {winner['net_sharpe20']} "
                f"(≥ default {floor}).")

    report = {
        "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "objective": "maximize gross win_rate s.t. NET profit_factor>1.0 AND NET Sharpe(ann √(252/20)) ≥ default config, n≥%d" % MIN_N,
        "tape_generated_at": tapes.get("generated_at"),
        "grid": {"z": Z_THRESHOLDS, "tp_frac": TP_FRACS, "sl_mult": SL_MULTS,
                 "hold": HOLDS, "subset": list(SUBSETS.keys()), "n_configs": len(results)},
        "cost_model": dict(wf.COST_PER_SPREAD_RT),
        "default_config": default,
        "net_sharpe_floor": floor,
        "directional_gated_net_sharpe_ref": DIRECTIONAL_GATED_NET_SHARPE,
        "n_feasible": len(feasible),
        "winner": winner,
        "runner_ups": feasible[1:11],
        "best_unconstrained": best_unconstrained,
        "honest_note": note,
        "all_configs": results,
    }
    _REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_REPORT_FILE, "w") as f:
        json.dump(report, f, indent=2, default=str)
    log.info("Saved tuning report → %s", _REPORT_FILE)
    return report


def load_report() -> dict | None:
    if _REPORT_FILE.exists():
        with open(_REPORT_FILE) as f:
            return json.load(f)
    return None


# ── CLI ─────────────────────────────────────────────────────────────────────
def _row(r: dict) -> str:
    c = r["config"]; rm = r.get("reason_mix", {})
    return (f"  z{c['z']:<4} tp{c['tp']:<4} sl{c['sl']:<4} h{c['hold']:<3} {c['subset']:<7} "
            f"n={r['n']:>4} win={r['gross_win_rate']*100:5.1f}% "
            f"PFg={r.get('gross_pf')!s:>6} PFn={r.get('net_pf')!s:>6} "
            f"Shp_n={r.get('net_sharpe20')!s:>7} exp_n={r.get('net_exp')!s:>8} "
            f"hold={r.get('mean_hold')!s:>5} "
            f"T/S/Ti/Sc {rm.get('TP',0)}/{rm.get('SL',0)}/{rm.get('TIME',0)}/{rm.get('SCRATCH',0)}")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    rpt = run()
    d = rpt["default_config"]
    print("\n" + "=" * 96)
    print("PHASE 2.9.1 — CONSTRAINED WIN-RATE OPTIMIZATION (gated_blend tape, NET-cost guardrails)")
    print("=" * 96)
    print(f"objective: {rpt['objective']}")
    print(f"configs swept: {rpt['grid']['n_configs']}   feasible: {rpt['n_feasible']}")
    print(f"\nDEFAULT (current rule):")
    print(_row(d))
    print(f"NET Sharpe floor = {rpt['net_sharpe_floor']}  "
          f"(ref: directional gated NET Sharpe {rpt['directional_gated_net_sharpe_ref']})")

    if rpt["best_unconstrained"]:
        print(f"\n(For contrast — pure win-rate max IGNORING constraints, the gaming we block:)")
        print(_row(rpt["best_unconstrained"]))

    if rpt["winner"]:
        print(f"\n>>> WINNER (highest win rate satisfying NET PF>1 AND NET Sharpe ≥ floor):")
        print(_row(rpt["winner"]))
        print(f"\nRunner-ups:")
        for r in rpt["runner_ups"]:
            print(_row(r))
    else:
        print("\n>>> NO FEASIBLE CONFIG — see note.")
    print(f"\nVERDICT: {rpt['honest_note']}")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
