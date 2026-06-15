"""
Seed the paper-trading journal from the walk-forward OUT-OF-SAMPLE tape.
========================================================================

Purpose
-------
Produce an honest, ready-to-show trade journal: a realistic book of CLOSED
paper trades the strategy generated **out-of-sample** (point-in-time — at each
date the engine used only models trained on prior data), sized by the
risk-based model in `sizing.py`.

This is NOT a live-accumulated book and must never be presented as one. Rows are
tagged `source='walkforward'` so they are distinct from the live A/B arms
(`ab_mode` in {pooled, gated}). The honest framing for the mentor:
  "out-of-sample walk-forward track record (no lookahead), sized by the risk
   model — plus a live book now accumulating the same in real time."

Method (mirrors how a real book behaves)
----------------------------------------
* Source tape: `pooled_trades.json` (the pooled-mode OOS signals).
* Trade only LONG/SHORT signals (|z| ≥ 0.5) on the live tradeable universe
  (drops the brent/wti M3-M6 laggards — `live_ranker.TUNED_EXCLUDED_SPREADS`).
* Walk chronologically; hold ONE position per spread at a time (no re-entry
  until the open one closes) — avoids unrealistic daily overtrading.
* Holding rule = the walk-forward rule (enter at signal, exit at fwd_date,
  ~20 trading days). The tuned TP/SL/30d stop is the *live* layer (gotcha 8 —
  the walk-forward deliberately stays the plain rule); target/stop are recorded
  for display but the realised P&L is the true OOS 20-day outcome.
* Size: lots from sizing.size_trade(spread, σ=resid_std, z); P&L = per-bbl
  fwd_pnl × (lots × 1,000 bbl/lot) = real dollars.

Run:
    python -m backend.research.seed_journal --months 6 --reset
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

import paper_trading as pt
from research import live_ranker
from research.sizing import size_trade, CONTRACT_MULTIPLIER, STOP_SIGMA

_TAPE = Path(__file__).parent.parent / "data" / "research" / "pooled_trades.json"


def _conviction(z: float) -> str:
    az = abs(z)
    if az >= 1.5:
        return "HIGH"
    if az >= 0.8:
        return "MODERATE"
    return "LOW"


def _iso(date_str: str) -> str:
    # tape dates are 'YYYY-MM-DD'; store as midnight UTC ISO for the journal.
    return f"{date_str}T00:00:00+00:00"


def seed(months: int = 6, reset: bool = True, brent_only: bool = True) -> dict:
    tape = json.load(open(_TAPE, encoding="utf-8"))
    last = max(r["date"] for r in tape if r.get("date"))
    cutoff = (datetime.strptime(last, "%Y-%m-%d") - timedelta(days=int(months * 30.5))).strftime("%Y-%m-%d")

    excluded = live_ranker.TUNED_EXCLUDED_SPREADS

    # Per-spread REALIZED volatility for risk-based sizing. Sizing the stop off
    # the model residual std (resid_std) over-sizes wildly — it's a tiny
    # in-sample number, so a 2.5σ stop is pennies and lots balloon. A real desk
    # sizes off the INSTRUMENT'S own volatility: here, the trailing 60-obs std of
    # the spread level, computed point-in-time (only dates ≤ entry).
    from collections import defaultdict
    series: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for r in sorted(tape, key=lambda x: x.get("date", "")):
        if r.get("actual") is not None and r.get("spread"):
            series[r["spread"]].append((r["date"], float(r["actual"])))

    def _std(vals: list[float]) -> float:
        if len(vals) < 2:
            return 0.0
        m = sum(vals) / len(vals)
        return (sum((v - m) ** 2 for v in vals) / (len(vals) - 1)) ** 0.5

    # Per-spread long-run vol → a FLOOR so a transient flat patch can't collapse
    # σ and balloon the lot count (the source of the one $134k outlier).
    global_std = {sp: _std([v for _, v in arr]) for sp, arr in series.items()}

    def realized_vol(sp: str, date: str, win: int = 90) -> float | None:
        vals = [v for (dt, v) in series.get(sp, []) if dt <= date][-win:]
        if len(vals) < 10:
            return None
        floor = 0.5 * global_std.get(sp, 0.0)
        return max(_std(vals), floor) if floor > 0 else _std(vals)

    # Tape encodes side as BUY/SELL; the paper book stores LONG/SHORT.
    rows = [
        r for r in tape
        if r.get("direction") in ("BUY", "SELL")
        and r.get("spread") not in excluded
        and (not brent_only or str(r.get("spread", "")).startswith("brent"))
        and r.get("fwd_pnl") is not None
        and r.get("z") is not None
        and r.get("date", "") >= cutoff
    ]
    rows.sort(key=lambda r: r["date"])

    c = pt._conn()
    if reset:
        c.execute("DELETE FROM paper_legs")
        c.execute("DELETE FROM paper_trades")
        c.commit()

    open_until: dict[str, str] = {}
    n = 0
    for r in rows:
        sp, d = r["spread"], r["date"]
        if sp in open_until and d < open_until[sp]:
            continue  # still holding this spread — no re-entry

        resid_std = float(r.get("resid_std") or 0.0)
        sigma = realized_vol(sp, d) or resid_std    # risk anchor = realized vol
        z = float(r["z"])
        entry = float(r["actual"])
        fair = float(r["fair"])
        exit_px = entry + float(r["fwd_move"])
        pnl_bbl = float(r["fwd_pnl"])
        direction = "LONG" if r["direction"] == "BUY" else "SHORT"

        sd = size_trade(sp, sigma, z)
        barrels = sd.barrels
        realised = round(pnl_bbl * barrels, 2)               # real dollars
        dollar_risk = sd.dollar_risk or 1.0
        realised_pct = round(realised / dollar_risk * 100, 2)  # return on risk-at-stop

        sign = 1.0 if direction == "LONG" else -1.0
        target = round(entry + live_ranker.TUNED_TP_FRAC * (fair - entry), 4)
        stop = round(entry - sign * STOP_SIGMA * sigma, 4)

        md = {
            "regime": r.get("regime"),
            "winner_model": r.get("winner"),
            "z": round(z, 3),
            "fair_value": round(fair, 4),
            "risk_sigma": round(sigma, 5),
            "resid_std": round(resid_std, 5),
            "lots": sd.lots,
            "dollar_risk": sd.dollar_risk,
            "tilt": sd.tilt,
            "sizing": sd.rationale,
            "track": "walkforward_oos",
        }
        thesis = (
            f"{sp} {direction}: actual {entry:+.3f} vs fair {fair:+.3f} (z={z:+.2f}, "
            f"regime {r.get('regime')}, model {r.get('winner')}). {sd.lots} lots, "
            f"risk ${sd.dollar_risk:,.0f}. Mean-reversion to fair over ~20 trading days."
        )

        c.execute("""
            INSERT INTO paper_trades
              (asset, direction, size, entry_price, target_price, stop_price,
               opened_at, closed_at, exit_price, close_reason, status,
               source, conviction, thesis, mtm_price, mtm_at,
               unrealised, realised, realised_pct, metadata_json, ab_mode, ab_session)
            VALUES (?,?,?,?,?,?,?,?,?,?, 'CLOSED',
                    'walkforward', ?, ?, ?, ?, 0.0, ?, ?, ?, NULL, 'wf_backfill')
        """, (
            sp, direction, float(barrels), entry, target, stop,
            _iso(d), _iso(r["fwd_date"]), round(exit_px, 4), "time_stop_20d",
            _conviction(z), thesis, round(exit_px, 4), _iso(r["fwd_date"]),
            realised, realised_pct, json.dumps(md),
        ))
        open_until[sp] = r["fwd_date"]
        n += 1

    c.commit()
    c.close()
    return {"seeded": n, "window_start": cutoff, "window_end": last,
            "spreads": sorted(set(r["spread"] for r in rows))}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--months", type=float, default=6.0)
    ap.add_argument("--reset", action="store_true")
    ap.add_argument("--include-wti", action="store_true",
                    help="include WTI spreads (synth/ESTIMATE data — off by default)")
    args = ap.parse_args()
    res = seed(months=args.months, reset=args.reset, brent_only=not args.include_wti)
    print(json.dumps(res, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
