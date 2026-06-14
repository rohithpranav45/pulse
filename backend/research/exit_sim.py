"""
Phase 2.9.0 — TP/SL-aware exit simulator.

The walk-forward (walkforward.py) scores every signal on DIRECTIONAL hit at a
fixed 20-day horizon with NO early exit:

    fwd_pnl = sign(direction) × (spread[d+20] − spread[d])

But the live paper book never holds to a fixed horizon. It closes each position
the moment the spread touches the take-profit or the stop, whichever comes
first, and only falls back to a time-stop if neither is hit:

    take-profit (TP)  regime leg  → p50  (quantile median fair value)
                      baseline    → 252d rolling mean
    stop-loss   (SL)  regime leg  → entry ± 1.5 × resid_std
                      baseline    → entry ± 1.5 × 252d rolling std

So the win rate the desk actually experiences — closed-green %, profit factor,
expectancy — has never been measured. The directional hit rate in the
methodology PDF answers a *different* question ("was the spread higher/lower 20
days later?") than the one the trader lives with ("did my TP/SL book a win?").
This module closes that gap.

Method
------
For each fired signal we walk the DAILY spread path (build_spread_series) from
entry forward up to MAX_HOLD (= FORWARD_DAYS = 20) trading days and close at:

    TP    — spread first reverts to the target level
    SL    — spread first runs to the stop level
    TIME  — neither within MAX_HOLD; exit at the horizon close. This time-stop
            PnL equals the directional fwd_pnl by construction, which gives a
            clean internal reconciliation between the two views.

Fill convention — **fill-at-level**: when a daily settle first crosses a level
we book the exit AT that level. This is the faithful daily-resolution proxy for
the live book, whose 60-second MTM loop (paper_trading.run_mtm) closes at the
live price the instant a level is crossed (≈ the level). TP and SL sit on
opposite sides of entry, so a single daily settle can satisfy at most one of
them — no intraday tie-break is needed.

Caveat (reported, not hidden): with only daily settles we cannot see intraday
touches between closes, so a level pierced and recovered within one session is
invisible. That makes the measured TP/SL counts slightly *conservative* — a
handful of true touches get classified as time-stops. No intraday data is used,
per the brief.

Run
---
    python -m backend.research.exit_sim               # regenerate the pooled tape, then simulate
    python -m backend.research.exit_sim --from-cache  # reuse the saved enriched tapes; simulate only

Writes
------
    backend/data/research/exit_sim_tapes.json   — enriched pooled/baseline/gated trade tapes
    backend/data/research/exit_sim_report.json  — TRUE win-rate metrics (overall + per spread + per source)
"""

from __future__ import annotations

import json
import logging
import os
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from research import walkforward as wf  # noqa: E402

log = logging.getLogger("pulse.research.exit_sim")

_TAPES_FILE  = Path(__file__).parent.parent / "data" / "research" / "exit_sim_tapes.json"
_REPORT_FILE = Path(__file__).parent.parent / "data" / "research" / "exit_sim_report.json"

# Trade rule — mirror live_ranker / paper_trading exactly.
MAX_HOLD = wf.FORWARD_DAYS   # 20 trading-day time-stop
SL_MULT  = 1.5               # stop = entry ± 1.5 × sigma (live_ranker lines 368/372/416/419)


# ─────────────────────────────────────────────────────────────────────────────
# Per-trade TP/SL inputs (source-agnostic)
# ─────────────────────────────────────────────────────────────────────────────
def _tp_sl_for(t: dict) -> tuple[float | None, float | None]:
    """
    Return (tp_target, sigma) for one trade row.

      • baseline leg  (source == 'baseline')  → roll_mu  + roll_sigma
      • regime / pooled leg (anything else)    → p50      + resid_std

    Pooled-tape rows carry no 'source' key and are treated as regime rows.
    Returns (None, None) when the inputs are missing or degenerate.
    """
    if t.get("source") == "baseline":
        tp, sg = t.get("roll_mu"), t.get("roll_sigma")
    else:
        tp, sg = t.get("p50"), t.get("resid_std")
    if tp is None or sg is None:
        return None, None
    try:
        tp = float(tp); sg = float(sg)
    except (TypeError, ValueError):
        return None, None
    if not np.isfinite(tp) or not np.isfinite(sg) or sg <= 0:
        return None, None
    return tp, sg


def _close(reason: str, exit_price: float, exit_date, hold_days: int,
           entry: float, direction: str, t: dict) -> dict:
    """Build a closed-trade record. PnL is signed for the spread position."""
    pnl = (entry - exit_price) if direction == "SELL" else (exit_price - entry)
    return {
        **t,
        "entry_price":  round(float(entry), 4),
        "exit_price":   round(float(exit_price), 4),
        "exit_date":    exit_date.strftime("%Y-%m-%d") if hasattr(exit_date, "strftime") else str(exit_date),
        "close_reason": reason,
        "hold_days":    int(hold_days),
        "realised_pnl": round(float(pnl), 4),
    }


def simulate_one(t: dict, path: pd.Series, max_hold: int = MAX_HOLD,
                 sl_mult: float = SL_MULT, tp_frac: float = 1.0) -> dict | None:
    """
    Walk the daily `path` (one spread's dropna'd settle series) forward from the
    trade's entry date and return the closed-trade record, or None when the
    trade can't be simulated (NEUTRAL, missing inputs, or no full forward
    window — the last keeps the comparison set identical to the directional
    metric, which also excludes edge trades with fwd_pnl=None).

    `tp_frac` (Phase 2.9.1) places the take-profit a fraction of the way from
    entry toward the model's fair-value anchor (p50 / rolling mean):
    tp_target = entry + tp_frac × (anchor − entry). 1.0 = the full p50 target
    (the 2.9.0 default); 0.5 = halfway; 0.25 = a quarter of the way (closer,
    easier to hit). `sl_mult` and `max_hold` are the SL multiple and time-stop.
    """
    direction = t.get("direction")
    if direction not in ("BUY", "SELL"):
        return None

    anchor, sigma = _tp_sl_for(t)
    if anchor is None:
        return None

    try:
        entry_date = pd.Timestamp(t["date"])
        pos = path.index.get_loc(entry_date)
    except (KeyError, ValueError, TypeError):
        return None
    if isinstance(pos, slice) or not isinstance(pos, (int, np.integer)):
        return None

    fwd = path.iloc[pos + 1: pos + 1 + max_hold]
    if len(fwd) < max_hold:
        return None  # incomplete forward window → exclude (matches directional set)

    entry = float(t["actual"])
    # Take-profit placed tp_frac of the way from entry toward the anchor.
    tp_target = entry + tp_frac * (anchor - entry)

    # Degenerate take-profit: the target lands on the WRONG side of entry (the
    # anchor / quantile median contradicts the z-direction). The live book
    # (paper_trading.run_mtm) opens the position then, on the very next 60-second
    # MTM tick, sees the TP condition already satisfied (e.g. SELL with px <=
    # target) and closes at the live price ≈ entry — a breakeven scratch, NOT a
    # fill at the mis-placed far target. Modelling it at the target would book a
    # fake loss the desk never takes, so we record a SCRATCH at entry (gross pnl
    # ≈ 0; under costs it's a small loss). tp_frac > 0 preserves the anchor side,
    # so this set is invariant to tp_frac.
    if (direction == "SELL" and tp_target >= entry) or (direction == "BUY" and tp_target <= entry):
        return _close("SCRATCH", entry, entry_date, 0, entry, direction, t)

    if direction == "SELL":
        sl_price = entry + sl_mult * sigma          # stop is ABOVE (spread runs against a short)
        for k, (dt, v) in enumerate(fwd.items(), start=1):
            v = float(v)
            if v <= tp_target:                       # reverted down to target → profit
                return _close("TP", tp_target, dt, k, entry, direction, t)
            if v >= sl_price:                        # ran up to the stop → loss
                return _close("SL", sl_price, dt, k, entry, direction, t)
    else:  # BUY
        sl_price = entry - sl_mult * sigma           # stop is BELOW
        for k, (dt, v) in enumerate(fwd.items(), start=1):
            v = float(v)
            if v >= tp_target:                       # rose to target → profit
                return _close("TP", tp_target, dt, k, entry, direction, t)
            if v <= sl_price:                        # fell to the stop → loss
                return _close("SL", sl_price, dt, k, entry, direction, t)

    # Neither hit within the window → time-stop at the horizon close.
    dt   = fwd.index[-1]
    vlast = float(fwd.iloc[-1])
    return _close("TIME", vlast, dt, len(fwd), entry, direction, t)


def simulate_tape(trades: list[dict], spreads: pd.DataFrame,
                  max_hold: int = MAX_HOLD, sl_mult: float = SL_MULT,
                  tp_frac: float = 1.0) -> tuple[list[dict], dict]:
    """
    Run the exit simulator over every fired trade in a tape. Returns
    (closed_trades, diagnostics). `spreads` is the build_spread_series() frame.
    `sl_mult` / `tp_frac` / `max_hold` are the Phase 2.9.1 trading-rule knobs.
    """
    from research.spread_universe import INSTRUMENTS
    paths = {sp: spreads[sp].dropna() for sp in INSTRUMENTS if sp in spreads.columns}

    closed: list[dict] = []
    diag = {"n_rows": len(trades), "n_neutral": 0, "n_no_inputs": 0,
            "n_incomplete": 0, "n_closed": 0, "tp_wrong_side": 0}

    for t in trades:
        direction = t.get("direction")
        if direction not in ("BUY", "SELL"):
            diag["n_neutral"] += 1
            continue
        tp_target, sigma = _tp_sl_for(t)
        if tp_target is None:
            diag["n_no_inputs"] += 1
            continue
        # Flag (don't drop) the degenerate case where the TP sits on the wrong
        # side of entry — i.e. the quantile median disagrees with the z-score
        # direction. Faithful fill-at-level still books it; we just count it.
        entry = float(t["actual"])
        if (direction == "SELL" and tp_target >= entry) or \
           (direction == "BUY"  and tp_target <= entry):
            diag["tp_wrong_side"] += 1

        path = paths.get(t.get("spread"))
        if path is None:
            diag["n_no_inputs"] += 1
            continue
        rec = simulate_one(t, path, max_hold=max_hold, sl_mult=sl_mult, tp_frac=tp_frac)
        if rec is None:
            diag["n_incomplete"] += 1
            continue
        closed.append(rec)

    diag["n_closed"] = len(closed)
    return closed, diag


# ─────────────────────────────────────────────────────────────────────────────
# Metrics
# ─────────────────────────────────────────────────────────────────────────────
def exit_metrics(closed: list[dict]) -> dict:
    """
    TRUE TP/SL metrics on a list of closed trades, plus the directional 20d
    hit rate on the SAME trades so the gap between the two is explicit.
    """
    n = len(closed)
    if n == 0:
        return {
            "n_closed": 0, "win_rate": None, "profit_factor": None,
            "avg_win": None, "avg_loss": None, "expectancy": None,
            "total_pnl": 0.0, "mean_hold_days": None,
            "n_win": 0, "n_loss": 0, "n_flat": 0,
            "close_reason_counts": {"TP": 0, "SL": 0, "TIME": 0, "SCRATCH": 0},
            "close_reason_pct":    {"TP": None, "SL": None, "TIME": None, "SCRATCH": None},
            "directional_hit_rate": None, "directional_mean_pnl": None,
            "win_rate_minus_dir_hit": None,
        }

    pnls   = np.array([c["realised_pnl"] for c in closed], dtype=float)
    holds  = np.array([c["hold_days"]   for c in closed], dtype=float)
    wins   = pnls[pnls > 0]
    losses = pnls[pnls < 0]
    n_win, n_loss, n_flat = int((pnls > 0).sum()), int((pnls < 0).sum()), int((pnls == 0).sum())

    gross_win  = float(wins.sum())
    gross_loss = float(-losses.sum())                  # positive magnitude
    profit_factor = round(gross_win / gross_loss, 4) if gross_loss > 0 else None

    reasons = Counter(c["close_reason"] for c in closed)
    counts  = {r: int(reasons.get(r, 0)) for r in ("TP", "SL", "TIME", "SCRATCH")}
    pct     = {r: round(counts[r] / n, 4) for r in counts}

    # Directional reference on the SAME closed set (20d, no early exit).
    dir_pnls = np.array([c["fwd_pnl"] for c in closed if c.get("fwd_pnl") is not None], dtype=float)
    dir_hit  = round(float((dir_pnls > 0).mean()), 4) if len(dir_pnls) else None
    dir_mean = round(float(dir_pnls.mean()), 4)       if len(dir_pnls) else None

    win_rate = round(n_win / n, 4)
    return {
        "n_closed":      n,
        "win_rate":      win_rate,
        "profit_factor": profit_factor,
        "avg_win":       round(float(wins.mean()), 4)   if len(wins)   else None,
        "avg_loss":      round(float(losses.mean()), 4) if len(losses) else None,   # negative
        "expectancy":    round(float(pnls.mean()), 4),
        "total_pnl":     round(float(pnls.sum()), 4),
        "mean_hold_days":round(float(holds.mean()), 2),
        "n_win":  n_win, "n_loss": n_loss, "n_flat": n_flat,
        "close_reason_counts": counts,
        "close_reason_pct":    pct,
        # explicit gap vs the directional view
        "directional_hit_rate":   dir_hit,
        "directional_mean_pnl":   dir_mean,
        "win_rate_minus_dir_hit": round(win_rate - dir_hit, 4) if dir_hit is not None else None,
    }


def _by_spread(closed: list[dict]) -> dict:
    groups: dict[str, list] = {}
    for c in closed:
        groups.setdefault(c.get("spread") or "UNKNOWN", []).append(c)
    return {sp: exit_metrics(v) for sp, v in groups.items()}


def _by_source(closed: list[dict]) -> dict:
    groups: dict[str, list] = {}
    for c in closed:
        groups.setdefault(c.get("source") or "regime", []).append(c)
    return {src: exit_metrics(v) for src, v in groups.items()}


# ─────────────────────────────────────────────────────────────────────────────
# Tape generation (the expensive part — pooled retrain across refits)
# ─────────────────────────────────────────────────────────────────────────────
def build_tapes() -> dict:
    """
    Regenerate the enriched pooled + baseline + gated_blend tapes via the
    pooled walk-forward (the composite leg is NOT needed — gated_blend = gated
    pooled + baseline fallback). The tapes carry the Phase 2.9.0 TP/SL inputs
    (p50/resid_std on regime rows, roll_mu/roll_sigma on baseline rows). Saved
    to disk so re-runs / metric tweaks can use --from-cache and skip the retrain.
    """
    from research.features        import build_features
    from research.spread_universe import build_spread_series

    log.info("Building feature matrix + spread universe...")
    features = build_features()
    spreads  = build_spread_series()
    joined   = features.join(spreads, how="inner")
    log.info("  joined %d rows  range=%s..%s", len(joined),
             joined.index.min().date(), joined.index.max().date())

    refit_ts = [pd.Timestamp(d) for d in wf.REFIT_DATES]
    refit_ts = [t for t in refit_ts if t >= joined.index.min() and t <= joined.index.max()]

    log.info("Producing pooled trades (quarterly refits, with boosters)...")
    pooled_trades, _ = wf._produce_trades(joined, spreads, refit_ts, regime_mode="pooled")
    log.info("  pooled tape: %d rows", len(pooled_trades))

    baseline_start = refit_ts[0]
    baseline_end   = max(refit_ts[-1] if len(refit_ts) > 1 else joined.index.max(),
                         joined.index.max())
    log.info("Building baseline tape over (%s, %s]...", baseline_start.date(), baseline_end.date())
    baseline_trades = wf._baseline_trades(spreads, baseline_start, baseline_end)
    log.info("  baseline tape: %d rows", len(baseline_trades))

    log.info("Building gated_blend tape...")
    gated_trades = wf._build_gated_blend(pooled_trades, baseline_trades)
    n_regime   = sum(1 for t in gated_trades if t.get("source") == "regime")
    n_baseline = sum(1 for t in gated_trades if t.get("source") == "baseline")
    log.info("  gated tape: %d rows  regime=%d  baseline=%d", len(gated_trades), n_regime, n_baseline)

    payload = {
        "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "gate":   {"regime": wf.GATED_REGIME, "winners": sorted(wf.GATED_WINNERS),
                   "z_thresh": wf.GATED_Z_THRESHOLD},
        "pooled":   pooled_trades,
        "baseline": baseline_trades,
        "gated":    gated_trades,
    }
    _TAPES_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_TAPES_FILE, "w") as f:
        json.dump(payload, f, default=str)
    log.info("Saved enriched tapes → %s", _TAPES_FILE)
    return payload


def load_tapes() -> dict | None:
    if _TAPES_FILE.exists():
        with open(_TAPES_FILE) as f:
            return json.load(f)
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Driver
# ─────────────────────────────────────────────────────────────────────────────
def run(from_cache: bool = False) -> dict:
    """Build (or load) the tapes, simulate exits on pooled + gated, write report."""
    from research.spread_universe import build_spread_series

    if from_cache:
        tapes = load_tapes()
        if tapes is None:
            raise FileNotFoundError(
                f"{_TAPES_FILE} not found — run without --from-cache to regenerate it.")
        log.info("Loaded cached tapes (generated_at=%s)", tapes.get("generated_at"))
    else:
        tapes = build_tapes()

    spreads = build_spread_series()

    pooled_closed, pooled_diag = simulate_tape(tapes["pooled"], spreads)
    gated_closed,  gated_diag  = simulate_tape(tapes["gated"],  spreads)

    report = {
        "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "method": (
            "Path-aware TP/SL exit simulation on the daily spread series. For each "
            "fired signal, walk forward up to MAX_HOLD trading days; close at TP "
            "(regime: p50 / baseline: 252d mean), SL (entry ± 1.5σ; regime sigma = "
            "resid_std, baseline sigma = 252d std), or a time-stop at the horizon. "
            "Fill-at-level. Time-stop PnL reconciles with the directional fwd_pnl."
        ),
        "config": {
            "max_hold_days": MAX_HOLD,
            "sl_mult":       SL_MULT,
            "z_entry":       wf.Z_ENTRY,
            "rolling_win":   wf.ROLLING_WIN,
            "fill":          "at-level",
            "gate":          tapes.get("gate"),
            "tapes_generated_at": tapes.get("generated_at"),
        },
        "pooled": {
            "diagnostics": pooled_diag,
            "overall":     exit_metrics(pooled_closed),
            "by_spread":   _by_spread(pooled_closed),
        },
        "gated_blend": {
            "diagnostics": gated_diag,
            "overall":     exit_metrics(gated_closed),
            "by_spread":   _by_spread(gated_closed),
            "by_source":   _by_source(gated_closed),
        },
    }
    _REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_REPORT_FILE, "w") as f:
        json.dump(report, f, indent=2, default=str)
    log.info("Saved exit-sim report → %s", _REPORT_FILE)
    return report


def load_report() -> dict | None:
    if _REPORT_FILE.exists():
        with open(_REPORT_FILE) as f:
            return json.load(f)
    return None


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────
def _fmt(v, nd=4, pct=False):
    if v is None:
        return "  n/a"
    if pct:
        return f"{v*100:5.1f}%"
    return f"{v:+.{nd}f}"


def _print_block(name: str, blk: dict) -> None:
    o = blk["overall"]
    d = blk["diagnostics"]
    print(f"\n=== {name} ===")
    print(f"  closed trades       {o['n_closed']:>6}  "
          f"(rows={d['n_rows']} neutral={d['n_neutral']} incomplete={d['n_incomplete']} "
          f"no_inputs={d['n_no_inputs']} tp_wrong_side={d['tp_wrong_side']})")
    print(f"  WIN RATE (TP/SL)    {_fmt(o['win_rate'], pct=True)}   "
          f"[directional 20d hit {_fmt(o['directional_hit_rate'], pct=True)}  "
          f"Δ {_fmt(o['win_rate_minus_dir_hit'])}]")
    print(f"  profit factor       {_fmt(o['profit_factor'])}")
    print(f"  avg win / avg loss  {_fmt(o['avg_win'])} / {_fmt(o['avg_loss'])}")
    print(f"  expectancy / trade  {_fmt(o['expectancy'])}   total {_fmt(o['total_pnl'])}")
    print(f"  mean hold (days)    {o['mean_hold_days']}")
    c = o["close_reason_counts"]; p = o["close_reason_pct"]
    print(f"  close-reason mix    TP {c['TP']} ({_fmt(p['TP'], pct=True)})  "
          f"SL {c['SL']} ({_fmt(p['SL'], pct=True)})  "
          f"TIME {c['TIME']} ({_fmt(p['TIME'], pct=True)})  "
          f"SCRATCH {c['SCRATCH']} ({_fmt(p['SCRATCH'], pct=True)})")
    print(f"  win/loss/flat       {o['n_win']} / {o['n_loss']} / {o['n_flat']}")
    print(f"  -- per spread --")
    for sp in sorted(blk["by_spread"]):
        m = blk["by_spread"][sp]
        cc = m['close_reason_counts']
        print(f"    {sp:<14} n={m['n_closed']:>4}  win={_fmt(m['win_rate'], pct=True)}  "
              f"PF={_fmt(m['profit_factor'])}  exp={_fmt(m['expectancy'])}  "
              f"[dir hit {_fmt(m['directional_hit_rate'], pct=True)}]  "
              f"TP/SL/TIME/SC {cc['TP']}/{cc['SL']}/{cc['TIME']}/{cc['SCRATCH']}")


def main(argv: list[str]) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    from_cache = "--from-cache" in argv
    rpt = run(from_cache=from_cache)

    print("\n" + "=" * 78)
    print("PHASE 2.9.0 — TRUE TP/SL WIN RATE (paper-book exit rule, not 20d directional)")
    print("=" * 78)
    _print_block("POOLED (un-gated regime engine)", rpt["pooled"])
    _print_block("GATED_BLEND (production default)", rpt["gated_blend"])

    # Gated-blend by-source slice (regime leg vs baseline fallback)
    bs = rpt["gated_blend"].get("by_source", {})
    if bs:
        print("\n=== GATED_BLEND by source ===")
        for src in sorted(bs):
            m = bs[src]
            print(f"  {src:<10} n={m['n_closed']:>4}  win={_fmt(m['win_rate'], pct=True)}  "
                  f"PF={_fmt(m['profit_factor'])}  exp={_fmt(m['expectancy'])}  "
                  f"[dir hit {_fmt(m['directional_hit_rate'], pct=True)}]")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
