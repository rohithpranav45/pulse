"""
Phase 3.1 — live analysis engine.

Glue between the live intraday feed (`live_feed.get_live_snapshot`) and the
existing regime ranker (`live_ranker.get_recommendation`). It overlays the
current real spread levels + live curve onto the framework and returns the
ranking the engine WOULD trade in the current market — the mentor's ask:
"move from historical validation to a live analysis engine."

Design choices (see the Phase 3.1 plan):
  • Brent-first. The Brent models are real-on-real, so the Brent live overlay
    is clean. WTI is opt-in (`include_wti=True`) because the WTI models were
    trained on the SYNTHETIC WTI estimate (CLAUDE.md gotcha 11), so live real
    WTI may carry a level offset until retrained on the real feed.
  • Honours the same env config as the rest of the engine (PULSE_GATED_BLEND /
    PULSE_REGIME_MODE / PULSE_GATED_SIZE) so the live engine reflects the
    production default, not a separate hard-coded mode.
  • The slow regime features (inventory / COT / vol / macro) still come from the
    latest historical row; only the fast state (spread level + curve regime) is
    live. That mirrors how a desk re-reads its screen intraday.

Public API
----------
  get_live_recommendation(*, include_wti=False) → dict
      Ranker output with live overlay + a `live_feed` meta block (as_of,
      source_file, per-spread snapshot). `available=False` if the feed is down.
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timezone

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

log = logging.getLogger("pulse.research.live_engine")


def get_live_recommendation(*, include_wti: bool = False) -> dict:
    """
    Run the regime framework against the current market from the live feed.

    Returns the standard `get_recommendation` payload (top + ranked + receipts)
    augmented with a `live_feed` block, or {"available": False, ...} if the feed
    is unreachable / empty.
    """
    from research.live_feed     import get_live_snapshot
    from research.live_features import build_overlay, CARRIED_STALE_COLS
    from research.live_ranker   import get_recommendation

    snap_co = get_live_snapshot("CO")
    if not snap_co.get("available"):
        return {
            "available": False,
            "live": True,
            "error": f"live feed unavailable: {snap_co.get('error')}",
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }

    live_actuals: dict[str, float] = {
        k: v["value"] for k, v in (snap_co.get("spreads") or {}).items()
    }
    live_curve = (snap_co.get("curve") or {}).get("m1_m12")

    snap_cl = None
    if include_wti:
        snap_cl = get_live_snapshot("CL")
        if snap_cl.get("available"):
            for k, v in (snap_cl.get("spreads") or {}).items():
                live_actuals[k] = v["value"]

    # Phase 4 (2026-06-18) — overlay today's fast features so the model predicts
    # fair value from today's market, not the (stale) latest daily settle. WTI
    # legs are only overlaid when the WTI snapshot was actually pulled.
    overlay = build_overlay(snap_co, snap_cl if include_wti else None)

    rec = get_recommendation(live_actuals=live_actuals, live_curve_m1m12=live_curve,
                             live_feature_overlay=overlay)
    if not rec.get("available"):
        rec["live"] = True
        return rec

    # Brent-first: unless WTI was explicitly overlaid, keep the live ranking to
    # the instruments we actually fed live prices for, so the log doesn't mix a
    # live Brent signal with a stale-settle WTI one.
    if not include_wti:
        rec["ranked"] = [r for r in rec.get("ranked", []) if r.get("spread", "").startswith("brent_")]
        rec["ranked"].sort(key=lambda x: x.get("confidence", 0.0), reverse=True)
        rec["top"] = rec["ranked"][0] if rec["ranked"] else None
        rec["n_eligible"] = len(rec["ranked"])

    rec["live_feed"] = {
        "as_of":        snap_co.get("as_of"),
        "source_file":  snap_co.get("source_file"),
        "curve_m1_m12": live_curve,
        "spreads":      live_actuals,
        "products":     ["CO"] + (["CL"] if (include_wti and snap_cl and snap_cl.get("available")) else []),
        "legs_co":      snap_co.get("legs"),
        # Phase 4 — which fast features were scored live (honest provenance:
        # everything else carried from the latest daily row).
        "feature_overlay": {
            "overlaid":      sorted(rec.get("overlaid_features", [])),
            "n_overlaid":    len(rec.get("overlaid_features", [])),
            "carried_stale": CARRIED_STALE_COLS,
        },
    }
    rec["live"] = True
    rec["as_of_live"] = snap_co.get("as_of")
    return rec


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    rec = get_live_recommendation(include_wti=("--wti" in sys.argv))
    if not rec.get("available"):
        print("UNAVAILABLE:", rec.get("error"))
        sys.exit(1)
    lf = rec.get("live_feed", {})
    print(f"=== LIVE recommendation  (feed as_of {lf.get('as_of')}) ===")
    print(f"  source     : {lf.get('source_file')}")
    print(f"  regime     : {rec.get('regime')}  (mode={rec.get('regime_mode')}, gated={rec.get('gated_blend')})")
    print(f"  curve M1-M12: {lf.get('curve_m1_m12')}")
    print(f"  eligible   : {rec.get('n_eligible')}")
    top = rec.get("top")
    if top:
        print(f"\n  TOP: {top['label']}  ->  {top['direction']}")
        print(f"    current {top['current']}  fair {top['fair_value']}  z={top['z_score']:+.2f}  conf={top['confidence']:.3f}")
        print(f"    target {top.get('target')}  stop {top.get('stop')}  winner={top.get('winner_model')}  src={top.get('recommendation_source')}")
    print(f"\n  All {len(rec.get('ranked', []))} live-ranked Brent spreads:")
    for i, r in enumerate(rec.get("ranked", []), 1):
        print(f"    #{i} {r['label']:<32} dir={r['direction']:<8} z={r['z_score']:+.2f} "
              f"conf={r['confidence']:.3f} src={r.get('recommendation_source','regime')}")
