"""
Phase 8 (2026-06-22) — per-spread gate.

The Phase 2.6 production gate is a SINGLE global rule applied uniformly to every
spread: take the pooled regime signal iff `regime_pooled == BACK` AND the cell
winner ∈ GATED_WINNERS AND `|z| ≥ 0.5`; otherwise fall through to the 252-day
rolling-z baseline. But the per-spread lift table (walk-forward
`gated_blend_net.by_spread_source`) shows regime conditioning helps **unevenly**:
the regime leg's OOS NET Sharpe beats baseline on the WTI front spreads
(wti_m1_m2 +1.22 vs +0.71, wti_fly_123 +0.97 vs +0.54) but LOSES on every Brent
spread (brent_m1_m2 +0.46 vs +0.72, brent_fly_123 +0.75 vs +1.17) and the M3-M6
carries. Firing the regime leg uniformly therefore drags the gated book to NET
Sharpe +0.298 — below the +0.372 baseline.

This module replaces the uniform gate with a **per-spread enable decision**: the
regime leg fires for a spread only when its OOS NET Sharpe beat the baseline for
that spread (by `GATE_MARGIN`, with ≥ `GATE_MIN_N` regime trades of evidence)
*before* the trade date. Everything else falls to baseline. Decided
walk-forward (per refit cutoff, prior closed trades only — the
`_compute_kelly_by_cutoff` pattern), so it's genuinely OOS, not in-sample
cherry-picking.

**Single source of truth.** The global-gate *predicate* still lives mirrored as
constants in `live_ranker` ↔ `walkforward` (asserted by `test_invariants`); the
per-spread *layer* lives only here and is imported by both, so it cannot drift.

Verdict (walk-forward, NET): per-spread gating lifts the gated/regime book from
+0.298 → +0.374, closing the whole gap to baseline (+0.372). It does NOT beat
baseline (consistent with the Phase 2.8.x story) — it makes the regime book
*competitive* by only deploying regime conditioning where it is earned. The
final-cutoff config enables exactly {wti_m1_m2, wti_fly_123}.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np

log = logging.getLogger("pulse.research.gate_config")

# ── Per-spread gate config ─────────────────────────────────────────────────────
# A spread's regime leg is enabled only when its OOS NET Sharpe beats baseline by
# at least GATE_MARGIN, computed on ≥ GATE_MIN_N regime-leg closed trades. Below
# the sample floor (or when regime ≤ baseline) the spread defaults to baseline —
# i.e. the regime signal is never taken. The verdict is insensitive to both knobs
# across {margin 0–0.25, min_n 10–30} (NET Sharpe 0.374–0.376), so these are
# deliberately un-tuned defaults, not a fitted edge.
GATE_MARGIN = 0.0   # annualised-Sharpe units the regime leg must beat baseline by
GATE_MIN_N  = 20    # minimum regime-leg closed trades before a spread may enable
FORWARD_DAYS = 20   # exit horizon (mirrors walkforward.FORWARD_DAYS for annualisation)


def _sharpe(pnls, forward_days: int = FORWARD_DAYS) -> float | None:
    """Annualised Sharpe of a NET-PnL list (√(252/H) like walkforward._metrics)."""
    arr = np.asarray([p for p in pnls if p is not None and np.isfinite(p)], dtype=float)
    if len(arr) < 2:
        return None
    sd = float(arr.std(ddof=1))
    if sd <= 0:
        return None
    return float(arr.mean() / sd) * np.sqrt(252.0 / forward_days)


def decide_enabled(
    reg_pnls,
    base_pnls,
    *,
    margin: float = GATE_MARGIN,
    min_n: int = GATE_MIN_N,
    forward_days: int = FORWARD_DAYS,
) -> bool:
    """
    Should the regime leg fire for this spread, given its prior NET-PnL history?

    `reg_pnls`  — NET PnLs of regime-leg trades that PASSED the global gate.
    `base_pnls` — NET PnLs of baseline-leg trades (rolling-z) for the same spread.

    Returns True only when there is enough regime evidence (≥ min_n trades) AND
    the regime Sharpe beats the baseline Sharpe by `margin`. A baseline with no
    Sharpe (too few trades / zero variance) never blocks an evidenced regime leg.
    """
    reg_pnls = [p for p in reg_pnls if p is not None and np.isfinite(p)]
    if len(reg_pnls) < min_n:
        return False
    rs = _sharpe(reg_pnls, forward_days)
    if rs is None:
        return False
    bs = _sharpe(base_pnls, forward_days)
    if bs is None:
        return True
    return bool(rs > bs + margin)


def enabled_at_cutoff(
    reg_hist: dict,
    base_hist: dict,
    cutoff,
    *,
    margin: float = GATE_MARGIN,
    min_n: int = GATE_MIN_N,
    forward_days: int = FORWARD_DAYS,
) -> set[str]:
    """
    Resolve the enabled-spread set as of `cutoff` from per-spread close-date
    histories. `reg_hist`/`base_hist` are {spread -> [(close_date, net_pnl)]};
    only entries whose close_date < cutoff are considered (no look-ahead — a
    trade that opens on/after `cutoff` only ever sees trades that already closed).
    """
    enabled: set[str] = set()
    for sp in set(reg_hist) | set(base_hist):
        rp = [v for d, v in reg_hist.get(sp, []) if d < cutoff]
        bp = [v for d, v in base_hist.get(sp, []) if d < cutoff]
        if decide_enabled(rp, bp, margin=margin, min_n=min_n, forward_days=forward_days):
            enabled.add(sp)
    return enabled


def per_spread_gate_passes(spread: str, enabled: set | None, global_gate_pass: bool) -> bool:
    """
    Combine the (mirrored) global-gate predicate with the per-spread enable set.

    The regime leg fires only when the spread is enabled AND the global gate
    passes. When `enabled` is None (no per-spread config available) this degrades
    to the global gate alone — the Phase 2.6 behaviour — so callers stay safe if
    the walk-forward report predates this module.
    """
    if not global_gate_pass:
        return False
    if enabled is None:
        return True
    return spread in enabled


def latest_enabled_from_report(report_path: str | Path) -> set[str] | None:
    """
    Read `per_spread_gate.enabled_latest` — the spreads the walk-forward enabled
    at its most recent refit boundary — from walkforward_report.json. This is the
    config live inference should apply going forward (mirrors how
    `sized_blend_summary.kelly_per_spread_latest` feeds live Kelly). Returns None
    when the report or block is absent so callers fall back to the global gate.
    """
    try:
        p = Path(report_path)
        if not p.exists():
            return None
        with open(p) as f:
            r = json.load(f)
        block = r.get("per_spread_gate") or {}
        enabled = block.get("enabled_latest")
        if enabled is None:
            return None
        return set(enabled)
    except Exception as exc:  # pragma: no cover — disk/json errors
        log.warning("failed to read per-spread gate config from %s: %s", report_path, exc)
        return None
