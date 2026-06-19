"""
Phase 3 — live auto-trade desk.

The mentor's directive (2026-06-19): "tune on live data so the dashboard
auto-takes/closes trades like a desk analyst, 5 days/wk during market hours."

This module is the loop that turns the gated, decorrelated recommendation into an
actual paper book on the live feed. It reuses the existing layers rather than
re-implementing any of them:

  • `live_engine.get_live_recommendation` — runs the regime framework on today's
    live market (live spreads + feature overlay) and hands back the `portfolio`
    block from `gated_select` (the decorrelated set of trades a desk would put on).
  • `shock_engine.live_stress_state` — the validated circuit-breaker. On a violent
    shock ONSET we PAUSE new entries; open trades keep running under their 2.5σ
    stops (gating on stress *level* was shown to hurt — onset-gating only).
  • `paper_trading` — the book itself. We open with `push_trade(source="auto_desk")`
    and let the existing 60s `mark_to_market` sweep own every exit (TP halfway to
    fair / 2.5σ stop / 30-trading-day time-stop). We never close on a stop here —
    that would duplicate the tuned exit rule that already lives in the MTM loop.

Desk rules, per fire (`run_auto_desk`):
  selected spread, no open auto position      → OPEN  (BUY→LONG, SELL→SHORT)
  selected spread, open SAME direction         → HOLD  (dedup — one position/spread)
  selected spread, open OPPOSITE direction      → FLIP  (close 'flip', open new side)
  held auto position no longer selected         → LEFT  (runs under its stop)

Entries are gated by (a) market hours — weekday AND a fresh feed bar — and (b) the
shock circuit-breaker. A FLIP still closes the stale side even when entries are
paused, but only re-opens the new side when entries are allowed.

Public API
----------
  is_market_open(feed_as_of, *, now=None, fresh_minutes=FEED_FRESH_MINUTES) -> (bool, str)
  run_auto_desk(*, dry_run=False, include_wti=True) -> dict
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timezone

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

# Module-level imports so tests can monkeypatch them on this module. The heavy
# work (feed read, GMM fit) is lazy inside the callees, so this stays cheap.
from research.live_engine import get_live_recommendation
from research.shock_engine import live_stress_state

log = logging.getLogger("pulse.research.auto_desk")

AUTO_SOURCE        = "auto_desk"   # paper_trades.source tag for desk-opened rows
FEED_FRESH_MINUTES = 90.0          # latest bar must be this fresh (mirrors signal_log)

_DIR_TO_SIDE = {"BUY": "LONG", "SELL": "SHORT"}


def _disabled() -> bool:
    return os.environ.get("PULSE_AUTO_DESK_DISABLED") == "1"


def _parse_feed_ts(feed_as_of: str | None) -> datetime | None:
    if not feed_as_of:
        return None
    try:
        dt = datetime.fromisoformat(str(feed_as_of).replace(" ", "T"))
    except (ValueError, TypeError):
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def is_market_open(feed_as_of: str | None, *, now: datetime | None = None,
                   fresh_minutes: float = FEED_FRESH_MINUTES) -> tuple[bool, str]:
    """
    Are we inside a live trading window? True only when it's a weekday AND the
    feed's most recent bar is fresh (≤ `fresh_minutes` old). Feed-freshness is the
    real gate — it naturally handles holidays, after-hours and a frozen recorder;
    the weekday check encodes the mentor's explicit "5 days a week".

    Returns (open, reason): reason ∈ {"open", "weekend", "no_feed_ts", "stale_feed"}.
    """
    now = now or datetime.now(timezone.utc)
    if now.weekday() >= 5:                       # Sat=5, Sun=6
        return False, "weekend"
    feed_dt = _parse_feed_ts(feed_as_of)
    if feed_dt is None:
        return False, "no_feed_ts"
    age_min = (now - feed_dt).total_seconds() / 60.0
    if age_min > fresh_minutes:
        return False, "stale_feed"
    return True, "open"


def _conviction(conf: float | None) -> str:
    c = conf or 0.0
    return "HIGH" if c >= 0.80 else "MODERATE" if c >= 0.60 else "LOW"


def _idea_from_row(row: dict) -> dict:
    """Map a ranked opportunity row → a paper_trading.push_trade idea dict."""
    side = _DIR_TO_SIDE.get(row.get("direction"))
    return {
        "asset":        row.get("spread"),
        "direction":    side,
        "live_price":   row.get("current"),
        "target_level": row.get("target"),
        "stop_level":   row.get("stop"),
        "conviction":   _conviction(row.get("confidence")),
        "fair_value":   row.get("fair_value"),
        "entry_thesis": row.get("rationale") or row.get("label") or "",
        "time_horizon": "tuned exit: TP halfway-to-fair · SL 2.5σ · 30d time-stop",
        "key_risk":     f"z={row.get('z_score')} · {row.get('regime')}",
    }


def _open_auto_positions() -> dict[str, dict]:
    """{asset: open_row} for positions this desk currently holds (source=auto_desk)."""
    from paper_trading import list_positions
    out: dict[str, dict] = {}
    for p in list_positions("open"):
        if p.get("source") == AUTO_SOURCE:
            out[p.get("asset")] = p
    return out


def run_auto_desk(*, dry_run: bool = False, include_wti: bool = True) -> dict:
    """
    One desk tick: read the live decorrelated book and reconcile the paper book to
    it, gated by market hours + the shock circuit-breaker.

    `dry_run=True` computes the same plan but takes no action (drives the
    read-only dashboard preview). Returns a summary the API + scheduler log.
    """
    if _disabled():
        return {"ran": False, "reason": "disabled", "dry_run": dry_run}

    rec = get_live_recommendation(include_wti=include_wti)
    if not rec.get("available"):
        return {"ran": False, "reason": "feed_unavailable",
                "error": rec.get("error"), "dry_run": dry_run}

    feed_as_of = rec.get("as_of_live") or (rec.get("live_feed") or {}).get("as_of")
    market_open, market_reason = is_market_open(feed_as_of)

    # Shock circuit-breaker (defensive: a stress-read failure must not block the
    # desk — fall back to "no breaker" and report it).
    breaker = False
    stress: dict = {}
    try:
        # Phase 4 — prefer the live-feed-driven stress read so the breaker reacts
        # intraday; it falls back to the daily-settle read until the recorder has
        # enough history (reported via live_fallback_reason).
        stress = live_stress_state(use_live_feed=True)
        breaker = bool(stress.get("breaker_active"))
    except Exception as exc:  # pragma: no cover — defensive
        log.warning("auto_desk: stress read failed (%s) — proceeding without breaker", exc)
        stress = {"error": str(exc)}

    entries_allowed = market_open and not breaker

    portfolio    = rec.get("portfolio") or {}
    selected     = list(portfolio.get("selected") or [])
    ranked_by_sp = {r.get("spread"): r for r in rec.get("ranked", [])}
    held         = _open_auto_positions()

    opened: list[dict]  = []
    flipped: list[dict] = []
    skipped: list[dict] = []
    actions: list[str]  = []   # "would …" lines for dry-run visibility

    from paper_trading import push_trade, close_trade

    for sp in selected:
        row = ranked_by_sp.get(sp)
        if not row:
            continue
        side = _DIR_TO_SIDE.get(row.get("direction"))
        if side is None:
            continue
        pos = held.get(sp)

        # Already holding this spread in the same direction → nothing to do.
        if pos and pos.get("direction") == side:
            continue

        # Holding the opposite direction → flip: close the stale side, then
        # (if entries are allowed) open the new side.
        if pos and pos.get("direction") != side:
            if dry_run:
                actions.append(f"flip {sp}: close #{pos.get('id')} ({pos.get('direction')})"
                               + (f" → open {side}" if entries_allowed else " (entries paused)"))
            else:
                close_trade(int(pos["id"]), reason="flip")
            flip_rec = {"spread": sp, "closed_id": pos.get("id"),
                        "from": pos.get("direction"), "to": side,
                        "reopened": bool(entries_allowed)}
            if entries_allowed and not dry_run:
                res = push_trade(_idea_from_row(row), source=AUTO_SOURCE)
                flip_rec["new_id"] = (res.get("trade") or {}).get("id") if res.get("ok") else None
                flip_rec["reopen_error"] = res.get("error") if not res.get("ok") else None
            flipped.append(flip_rec)
            continue

        # No position yet → open if entries are allowed, else record why not.
        if not entries_allowed:
            skipped.append({"spread": sp, "direction": side,
                            "reason": "breaker" if breaker else market_reason})
            continue
        if dry_run:
            actions.append(f"open {sp} {side} @ {row.get('current')}")
            opened.append({"spread": sp, "direction": side, "id": None, "dry_run": True})
            continue
        res = push_trade(_idea_from_row(row), source=AUTO_SOURCE)
        if res.get("ok"):
            opened.append({"spread": sp, "direction": side,
                           "id": (res.get("trade") or {}).get("id")})
        else:
            skipped.append({"spread": sp, "direction": side,
                            "reason": "push_failed", "error": res.get("error")})

    # Held auto positions whose spread dropped out of the selected book are left
    # to run under their stops (mentor's rule) — report them for visibility.
    left_running = [{"spread": sp, "direction": p.get("direction"), "id": p.get("id")}
                    for sp, p in held.items() if sp not in selected]

    return {
        "ran":             True,
        "dry_run":         dry_run,
        "market_open":     market_open,
        "market_reason":   market_reason,
        "breaker_active":  breaker,
        "entries_allowed": entries_allowed,
        "stress":          {k: stress.get(k) for k in
                            ("p_stress", "onset", "label", "as_of", "source", "live",
                             "live_fallback_reason")
                            } if stress and "error" not in stress else stress,
        "feed_as_of":      feed_as_of,
        "regime":          rec.get("regime"),
        "rho_max":         portfolio.get("rho_max"),
        "selected":        selected,
        "opened":          opened,
        "flipped":         flipped,
        "left_running":    left_running,
        "skipped":         skipped,
        "actions":         actions,
        "n_held_auto":     len(held),
        "timestamp":       datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


if __name__ == "__main__":
    import json
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    dry = "--live" not in sys.argv
    out = run_auto_desk(dry_run=dry, include_wti=("--wti" in sys.argv))
    print(json.dumps(out, indent=2, default=str))
