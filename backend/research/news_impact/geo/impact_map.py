"""
Impact map — (asset × event × severity) → signed price-node vector.
===================================================================

The registry holds each asset's `disruption_bias`: the node-sign vector for a
SUPPLY-REDUCING event there. This module turns that static prior into a per-event
directional vector by composing it with:

  * event polarity  — disruptive events keep the bias sign; restorative events
                      (restart / expansion / opec_hike) FLIP it; unknown → no claim;
  * severity        — a magnitude multiplier (minor … severe).

The output is a **directional conviction score per node** (sign + relative
strength), NOT a % move — the empirical per-node event study supplies magnitude
in a later sprint. Everything here is deterministic and interpretable, the
"expert prior" layer of the prior-then-learn design.

Public API
----------
  event_polarity(event_type)                  -> -1 | 0 | +1
  severity_mult(severity)                     -> float
  impact_vector(asset, event_type, severity)  -> {node: score}
  headline_impact(assets, event_type, sev)    -> {nodes, contributors, rationale}
  explain(asset, event_type, severity)        -> str

Run standalone:  python backend/research/news_impact/geo/impact_map.py
"""

from __future__ import annotations

import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[3]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from research.news_impact.geo import registry as reg  # noqa: E402
from research.news_impact.geo.registry import Asset, NODES  # noqa: E402

SEVERITY_MULT: dict[str, float] = {
    "minor": 0.5, "moderate": 1.0, "major": 1.5, "severe": 2.0,
}
DEFAULT_SEVERITY = "moderate"
_CLAMP = 3.0   # node scores are bounded conviction, not % moves


def event_polarity(event_type: str | None) -> int:
    """+1 keeps the disruption bias (supply reduced), -1 flips it (supply added),
    0 = no directional claim (unknown / non-throughput event)."""
    if event_type in reg.DISRUPTIVE_EVENTS:
        return 1
    if event_type in reg.RESTORATIVE_EVENTS:
        return -1
    return 0


def severity_mult(severity: str | None) -> float:
    return SEVERITY_MULT.get((severity or DEFAULT_SEVERITY), 1.0)


def impact_vector(asset: Asset, event_type: str | None,
                  severity: str | None = DEFAULT_SEVERITY) -> dict[str, float]:
    """Signed conviction per node for one (asset, event) pair. Empty dict when the
    event carries no directional claim (polarity 0) — honest, not a fabricated 0."""
    pol = event_polarity(event_type)
    if pol == 0:
        return {}
    mult = severity_mult(severity) * pol
    return {node: round(float(sign) * mult, 3) for node, sign in asset.disruption_bias.items()}


def _arrow(v: float) -> str:
    if v >= 2.0:   return "↑↑"
    if v > 0:      return "↑"
    if v <= -2.0:  return "↓↓"
    if v < 0:      return "↓"
    return "·"


def headline_impact(assets: list[Asset], event_type: str | None,
                    severity: str | None = DEFAULT_SEVERITY) -> dict:
    """
    Combine one event applied across the asset(s) named in a headline into a single
    node vector (summed per node, clamped), plus per-asset contributors and a
    human rationale. Returns {nodes, contributors, rationale, polarity}.
    """
    pol = event_polarity(event_type)
    combined: dict[str, float] = {}
    contributors = []
    for a in assets:
        vec = impact_vector(a, event_type, severity)
        if not vec:
            continue
        contributors.append({"asset_id": a.id, "name": a.name, "type": a.type,
                             "region": a.region, "vector": vec})
        for node, v in vec.items():
            combined[node] = combined.get(node, 0.0) + v
    combined = {n: round(max(-_CLAMP, min(_CLAMP, v)), 3) for n, v in combined.items() if v}

    if not contributors:
        rationale = ("no directional claim — "
                     + ("unrecognised event type" if pol == 0 else "no asset resolved"))
    else:
        ev = (event_type or "event").replace("_", " ")
        names = ", ".join(c["name"] for c in contributors[:3])
        parts = [f"{n} {_arrow(v)}" for n, v in sorted(combined.items(),
                 key=lambda kv: -abs(kv[1]))]
        rationale = f"{ev} ({severity}) at {names} → " + ", ".join(parts)
    return {"nodes": combined, "contributors": contributors,
            "rationale": rationale, "polarity": pol}


def explain(asset: Asset, event_type: str | None,
            severity: str | None = DEFAULT_SEVERITY) -> str:
    vec = impact_vector(asset, event_type, severity)
    if not vec:
        return f"{asset.name}: {event_type or 'event'} carries no directional claim."
    parts = [f"{NODES.get(n, n)} {_arrow(v)} ({v:+.1f})"
             for n, v in sorted(vec.items(), key=lambda kv: -abs(kv[1]))]
    return f"{asset.name} — {(event_type or '').replace('_',' ')} ({severity}): " + "; ".join(parts)


# ── standalone ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    cases = [
        (["hormuz"], "closure", "severe"),
        (["port_arthur"], "fire", "major"),
        (["port_arthur"], "restart", "moderate"),     # flips: cracks down, crude up
        (["bab_el_mandeb"], "attack", "moderate"),
        (["opec"], "opec_cut", "major"),
        (["opec"], "opec_hike", "major"),             # flips
        (["druzhba", "russia_supply"], "sanction", "major"),
    ]
    for ids, ev, sev in cases:
        assets = [reg.by_id(i) for i in ids]
        out = headline_impact(assets, ev, sev)
        print(f"\n{ids} | {ev}/{sev}")
        print("  " + out["rationale"])
        print("  nodes:", out["nodes"])
