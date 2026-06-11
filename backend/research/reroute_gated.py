"""
Phase 2.8.3 — re-aggregate gated_blend + sized_blend from the existing
gated_trades.json under the widened GATED_WINNERS.

The Phase 2.8.2 walk-forward already trained the pooled models with the full
7-candidate competition and persisted every (date, spread) decision into
gated_trades.json. Phase 2.8.3 widens the gate to admit XGBoost / LightGBM
/ CatBoost. Since the wider gate is a strict superset of the narrow one and
no per-cell winner has changed (we're not retraining), we can reconstruct
the original pooled_trades + baseline_trades from gated_trades.json, then
re-run the post-train aggregation. Result is identical to a fresh
walk-forward — minus the ~3h of model refitting.

Usage:
    python -m backend.research.reroute_gated
"""

from __future__ import annotations

import json
import sys
import numpy as np
import pandas as pd
from pathlib import Path

# Reuse walkforward helpers — they will pick up the widened GATED_WINNERS
# automatically from the module's module-level constants.
from research import walkforward as wf


def _reconstruct_pooled_and_baseline(
    gated_old: list[dict],
) -> tuple[list[dict], list[dict]]:
    """
    Invert gated_trades.json back into (pooled_trades, baseline_trades) as
    they were fed to _build_gated_blend pre-2.8.3.

    For source='regime' rows: the row IS the pooled trade.
    For source='baseline' rows:
      • baseline_trade fields are the row's (z, direction, fwd_pnl, ...)
      • pooled candidate is reconstructed from (pooled_z, regime, winner)
        plus fwd_move. fwd_pnl for the regime leg is computed from
        sign(pooled_z) and fwd_move under the same ±0.5σ rule used in
        _evaluate_window: SELL if pooled_z ≥ +0.5, BUY if ≤ −0.5, NEUTRAL else.
    """
    pooled: list[dict] = []
    baseline: list[dict] = []

    for t in gated_old:
        src = t.get("source")
        if src == "regime":
            # The row IS the pooled trade. fair/p10/p50/p90/fwd_date are
            # preserved if present; they have no impact on gate or _metrics.
            pooled.append({
                "date":      t["date"],
                "spread":    t["spread"],
                "regime":    t["regime"],
                "actual":    t.get("actual"),
                "fair":      t.get("fair"),
                "p10":       t.get("p10"),
                "p50":       t.get("p50"),
                "p90":       t.get("p90"),
                "z":         t["z"],
                "direction": t["direction"],
                "winner":    t["winner"],
                "fwd_move":  t.get("fwd_move"),
                "fwd_pnl":   t.get("fwd_pnl"),
                "fwd_date":  t.get("fwd_date"),
            })
            # NOTE: we don't have the baseline candidate for this (date, spread).
            # Under the wider gate this row still routes to regime, so the
            # baseline candidate is never consulted by _build_gated_blend.
            continue

        # source == 'baseline'
        baseline.append({
            "date":      t["date"],
            "spread":    t["spread"],
            "actual":    t.get("actual"),
            "z":         t["z"],
            "direction": t["direction"],
            "fwd_move":  t.get("fwd_move"),
            "fwd_pnl":   t.get("fwd_pnl"),
        })

        # Reconstruct the pooled candidate if it existed (gate='fail' means
        # we had a pooled candidate that the narrow gate rejected).
        if t.get("gate") == "fail":
            pz = t.get("pooled_z")
            fm = t.get("fwd_move")
            if pz is None or fm is None:
                continue
            if abs(pz) < wf.Z_ENTRY:
                pdir, pfwd = "NEUTRAL", 0.0
            elif pz > 0:
                pdir, pfwd = "SELL", -float(fm)
            else:
                pdir, pfwd = "BUY", float(fm)
            pooled.append({
                "date":      t["date"],
                "spread":    t["spread"],
                "regime":    t.get("regime"),
                "actual":    t.get("actual"),
                "z":         pz,
                "direction": pdir,
                "winner":    t.get("winner"),
                "fwd_move":  fm,
                "fwd_pnl":   pfwd,
            })

    return pooled, baseline


def main() -> int:
    print(f"Active gate: regime={wf.GATED_REGIME}  "
          f"winners={sorted(wf.GATED_WINNERS)}  "
          f"z_thresh={wf.GATED_Z_THRESHOLD}")

    report_path = wf._REPORT_FILE
    trades_path = wf._GATED_TRADES_FILE
    if not report_path.exists():
        print(f"ERROR: missing {report_path}", file=sys.stderr)
        return 1
    if not trades_path.exists():
        print(f"ERROR: missing {trades_path}", file=sys.stderr)
        return 1

    with open(report_path) as f:
        report = json.load(f)
    with open(trades_path) as f:
        gated_old = json.load(f)

    print(f"\nLoaded {len(gated_old)} gated trades from previous run.")
    print(f"Loaded report generated_at: {report.get('generated_at')}")

    # --- Snapshot OLD gated headline before overwriting --------------------
    old_g = report["gated_blend"]
    print("\n=== OLD gated_blend (narrow gate) ===")
    print(f"  overall sharpe   = {old_g['overall'].get('sharpe')}")
    print(f"  overall hit_rate = {old_g['overall'].get('hit_rate')}")
    print(f"  overall mean_pnl = {old_g['overall'].get('mean_pnl')}")
    print(f"  overall n_signals= {old_g['overall'].get('n_signals')}")
    print(f"  overall max_dd   = {old_g['overall'].get('max_drawdown')}")
    print(f"  by_source        = "
          f"regime n={old_g['by_source'].get('regime',{}).get('n_signals',0)} "
          f"sharpe={old_g['by_source'].get('regime',{}).get('sharpe')} | "
          f"baseline n={old_g['by_source'].get('baseline',{}).get('n_signals',0)} "
          f"sharpe={old_g['by_source'].get('baseline',{}).get('sharpe')}")
    print(f"  gate.winners (old)= {old_g.get('gate', {}).get('winners')}")

    # --- Reconstruct + re-route under the wider gate -----------------------
    pooled_trades, baseline_trades = _reconstruct_pooled_and_baseline(gated_old)
    print(f"\nReconstructed: {len(pooled_trades)} pooled candidates, "
          f"{len(baseline_trades)} baseline candidates")

    gated_new = wf._build_gated_blend(pooled_trades, baseline_trades)
    n_regime   = sum(1 for t in gated_new if t.get("source") == "regime")
    n_baseline = sum(1 for t in gated_new if t.get("source") == "baseline")
    print(f"Re-routed under wider gate: {len(gated_new)} rows "
          f"(regime={n_regime}, baseline={n_baseline})")

    # --- Re-aggregate gated_block + sized_blocks ---------------------------
    refit_meta = report["pooled"]["refits"]
    refit_ts = [pd.Timestamp(m["cutoff"]) for m in refit_meta]

    gated_block = wf._aggregate_mode(gated_new, refit_meta, "gated_blend")
    gated_block["by_source"]        = wf._by_source(gated_new)
    gated_block["by_spread_source"] = wf._by_spread_source(gated_new)
    gated_block["gate"] = {
        "regime":   wf.GATED_REGIME,
        "winners":  sorted(wf.GATED_WINNERS),
        "z_thresh": wf.GATED_Z_THRESHOLD,
        "note":     (f"Phase 2.8.3 widened gate. Pooled signal used when "
                     f"regime_pooled=='{wf.GATED_REGIME}' AND winner_model "
                     f"in {sorted(wf.GATED_WINNERS)} AND |z|>={wf.GATED_Z_THRESHOLD}; "
                     f"otherwise 252d rolling-z baseline."),
    }
    gated_block["gate_counts"] = {
        "regime_fires":      n_regime,
        "baseline_fallback": n_baseline,
        "regime_share":      round(n_regime / max(len(gated_new), 1), 4),
    }

    # --- Phase 2.7 sized variants ------------------------------------------
    kelly_lookup = wf._compute_kelly_by_cutoff(gated_new, refit_ts)
    sized_blocks: dict[str, dict] = {}
    for mode in wf.SIZING_MODES:
        sized_trades = wf._apply_sizing(gated_new, mode, refit_ts, kelly_lookup)
        blk = wf._aggregate_mode(sized_trades, refit_meta, f"sized_{mode}")
        blk["by_source"]        = wf._by_source(sized_trades)
        blk["by_spread_source"] = wf._by_spread_source(sized_trades)
        regime_scales = [t.get("sizing_scale", 1.0) for t in sized_trades
                         if t.get("source") == "regime"]
        if regime_scales:
            blk["mean_regime_scale"]   = round(float(np.mean(regime_scales)), 4)
            blk["median_regime_scale"] = round(float(np.median(regime_scales)), 4)
        else:
            blk["mean_regime_scale"] = blk["median_regime_scale"] = None
        sized_blocks[mode] = blk

    last_kelly = kelly_lookup[refit_ts[-1].strftime("%Y-%m-%d")] if refit_ts else {}
    sized_summary = {
        "modes":             list(wf.SIZING_MODES),
        "kelly_floor":       wf.SIZING_KELLY_FLOOR,
        "kelly_cap":         wf.SIZING_KELLY_CAP,
        "kelly_default":     wf.SIZING_KELLY_DEFAULT,
        "kelly_min_n":       wf.SIZING_KELLY_MIN_N,
        "kelly_per_spread_latest": last_kelly,
        "kelly_per_cutoff":  kelly_lookup,
        "method":            ("Sized blend: gated_blend trade tape with "
                              "regime-leg fwd_pnl scaled by mode. full=1.0 "
                              "(sanity); half=0.5; kelly=per-spread Kelly. "
                              "Re-aggregated 2.8.3 under widened gate."),
    }

    # --- Re-compute lifts (composite/pooled/baseline unchanged) ------------
    base_by_spread = report["baseline_by_spread"]
    base_overall   = report["baseline_overall"]
    composite_block = report["composite"]
    pooled_block    = report["pooled"]

    report["gated_blend"]         = gated_block
    report["sized_blend"]         = sized_blocks
    report["sized_blend_summary"] = sized_summary
    report["lift_gated_vs_baseline"]       = wf._lift(gated_block,           base_by_spread, base_overall)
    report["lift_sized_half_vs_baseline"]  = wf._lift(sized_blocks["half"],  base_by_spread, base_overall)
    report["lift_sized_kelly_vs_baseline"] = wf._lift(sized_blocks["kelly"], base_by_spread, base_overall)
    report["lift_sized_half_vs_gated"]     = wf._lift(sized_blocks["half"],
                                                      gated_block.get("by_spread", {}),
                                                      gated_block.get("overall", {}))
    report["lift_sized_kelly_vs_gated"]    = wf._lift(sized_blocks["kelly"],
                                                      gated_block.get("by_spread", {}),
                                                      gated_block.get("overall", {}))
    report["lift_gated_vs_pooled"]         = wf._lift(gated_block,
                                                      pooled_block.get("by_spread", {}),
                                                      pooled_block.get("overall", {}))

    # Update config + generated_at to reflect 2.8.3
    report["generated_at"] = pd.Timestamp.utcnow().isoformat(timespec="seconds").replace("+00:00", "Z")
    if "config" in report and "gated_blend" in report["config"]:
        report["config"]["gated_blend"]["winners"] = sorted(wf.GATED_WINNERS)
    report["method"] = report.get("method", "") + " [2.8.3 reroute: gated leg re-aggregated under widened GATED_WINNERS without retraining pooled models.]"

    # --- Persist ------------------------------------------------------------
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    with open(trades_path, "w") as f:
        json.dump(gated_new, f, default=str)
    print(f"\nSaved updated report -> {report_path}")
    print(f"Saved new gated trades -> {trades_path}")

    # --- Headline summary ---------------------------------------------------
    new_g = gated_block
    print("\n=== NEW gated_blend (widened gate) ===")
    print(f"  overall sharpe   = {new_g['overall'].get('sharpe')}")
    print(f"  overall hit_rate = {new_g['overall'].get('hit_rate')}")
    print(f"  overall mean_pnl = {new_g['overall'].get('mean_pnl')}")
    print(f"  overall n_signals= {new_g['overall'].get('n_signals')}")
    print(f"  overall max_dd   = {new_g['overall'].get('max_drawdown')}")
    print(f"  by_source        = "
          f"regime n={new_g['by_source'].get('regime',{}).get('n_signals',0)} "
          f"sharpe={new_g['by_source'].get('regime',{}).get('sharpe')} | "
          f"baseline n={new_g['by_source'].get('baseline',{}).get('n_signals',0)} "
          f"sharpe={new_g['by_source'].get('baseline',{}).get('sharpe')}")
    print(f"  gate.winners (new)= {new_g.get('gate', {}).get('winners')}")

    print("\n=== Δ vs OLD gated (Phase 2.8.2 narrow gate) ===")
    for k in ("sharpe", "hit_rate", "mean_pnl", "n_signals", "max_drawdown"):
        a = old_g["overall"].get(k); b = new_g["overall"].get(k)
        if a is None or b is None:
            print(f"  {k:12s} old={a} new={b}")
        else:
            print(f"  {k:12s} old={a:>+.4f}  new={b:>+.4f}  Δ={b - a:>+.4f}")

    print("\n=== per-spread gated sharpe ===")
    for sp in sorted(new_g["by_spread"]):
        a = old_g["by_spread"].get(sp, {}).get("sharpe")
        b = new_g["by_spread"][sp].get("sharpe")
        d = (b - a) if (a is not None and b is not None) else None
        a_str = f"{a:+.4f}" if a is not None else "  None"
        b_str = f"{b:+.4f}" if b is not None else "  None"
        d_str = f"{d:+.4f}" if d is not None else "  None"
        n_new = new_g["by_spread"][sp].get("n_signals")
        print(f"  {sp:14s}  old={a_str}  new={b_str}  Δ={d_str}  n_new={n_new}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
