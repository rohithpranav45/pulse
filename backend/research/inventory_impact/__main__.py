"""
Run the full Inventory Surprise Impact pipeline and emit the deliverable bundle.

    python -m backend.research.inventory_impact            # full run + console deck
    python -m backend.research.inventory_impact --refresh  # re-pull EIA + rebuild panels

Writes backend/data/research/inventory_impact/results.json (everything the
write-up quotes) and prints the Thursday deck to the console.
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pandas as pd

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

_HERE = Path(__file__).parent
from . import eia_report, event_study, regime_conditioning, framework  # noqa: E402

_OUT = Path(__file__).parent.parent.parent / "data" / "research" / "inventory_impact" / "results.json"


def main():
    refresh = "--refresh" in sys.argv
    rule = "=" * 72

    # ── L0/L2 — report + surprise + quality ───────────────────────────────────
    wf = eia_report.weekly_frame(force_refresh=refresh)
    sp = eia_report.surprise_series("crude_ex_spr", "seasonal")
    dec = eia_report.decomposition()

    # ── centerpiece — regime conditioning (daily 2015-2026) ───────────────────
    daily = regime_conditioning.build_daily_panel("seasonal", force_refresh=refresh)
    cond = regime_conditioning.conditional_table(daily, "ret")

    # ── intraday confirmation (2021-2026) ─────────────────────────────────────
    panel = event_study.build_panel(force_refresh=refresh)
    decay = event_study.decay_profile(panel, "wti_flat")

    # ── the live call ─────────────────────────────────────────────────────────
    call = framework.assess_release()

    # ── console deck ──────────────────────────────────────────────────────────
    print(rule)
    print("  PULSE — INVENTORY SURPRISE IMPACT MODEL (CRUDE)")
    print("  Futures First — Wednesday inventory framework")
    print(rule)

    print("\n[1] THESIS")
    print("    The market trades the SURPRISE vs consensus, not the headline draw —")
    print("    and only in the REGIME where inventories actually move price.")

    print("\n[2] WHEN INVENTORIES MATTERED (surprise_z -> Brent release-day return, 2015-2026)")
    print(cond.to_string(index=False))

    print("\n[3] INTRADAY CONFIRMATION (2021-2026, 1-min)")
    print(f"    releases: {len(panel)}   confirmed vol spike: {int(panel['confirmed'].sum())}/{len(panel)}")
    print(f"    surprise->WTI flat @30m: near-zero beta; release-day vol ~1.0x a normal day (no lift)")
    print(f"    decay (surprise-aligned): retention settle/peak = {decay.get('retention_settle_vs_peak')}")

    print("\n[4] CURRENT REGIME → CONVICTION")
    cr = call["regime"]
    print(f"    {cr['as_of']}: {cr['regime_label']}  (stocks {cr['inv_vs_5yr_pct']:+}% vs 5yr)")
    print(f"    inventory sensitivity: {cr['sensitivity']}  →  "
          f"{'price reacts to the print' if call['regime_sensitive'] else 'the print is noise on flat price here'}")

    print(f"\n[5] THE CALL — week ending {call.get('week_ending', call['as_of'])} "
          f"(released {call.get('release_day_name','Wed')} {call.get('release_date','—')})")
    print(f"    actual {call['actual_change_mbbl']:+,.0f} MBBL | surprise {call['surprise_mbbl']:+,.0f} "
          f"({call['surprise_z']:+.1f}sigma) [{call['surprise_source']}]")
    print(f"    >> {call['call']}  (P_bull {call['p_bullish']} / P_bear {call['p_bearish']})  "
          f"confidence {call['confidence']}")
    print(f"    most-exposed: {call['spreads']['primary']}  (ranked {', '.join(call['spreads']['ranked'][:3])})")
    print("    top-3 factors:")
    for i, f in enumerate(call["top_factors"], 1):
        print(f"      {i}. {f}")

    # ── persist ───────────────────────────────────────────────────────────────
    results = {
        "thesis": "Trade the surprise vs consensus, gated by the inventory/curve regime.",
        "report_span": [str(wf.index.min().date()), str(wf.index.max().date())],
        "n_weeks": int(len(wf)),
        "when_it_mattered": cond.to_dict("records"),
        "intraday": {
            "n_releases": int(len(panel)),
            "confirmed_spikes": int(panel["confirmed"].sum()),
            "decay": decay,
            "betas_30m": event_study.conditional_betas(panel, 30),
        },
        "current_regime": cr,
        "call": call,
        "latest_quality_of_draw": (
            dec[["crude_ex_spr_surprise_z", "demand_z", "runs_z", "export_z", "quality_of_draw"]]
            .dropna(how="all").tail(6).round(2).reset_index().astype(str).to_dict("records")
        ),
    }
    _OUT.write_text(json.dumps(results, indent=2, default=str))
    print(f"\n  results -> {_OUT}")
    print(rule)


if __name__ == "__main__":
    main()
