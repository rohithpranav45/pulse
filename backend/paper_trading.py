"""
Paper-trading sandbox.
======================
Per-mentor request: when the dashboard suggests a trade, the user can "push"
it into a paper-trading book. We mark-to-market against the live price stream
every minute, auto-close on target/stop hits, and roll up per-trade and
aggregate performance (PnL, win %, Sharpe, max drawdown, profit factor).

Storage
-------
SQLite table `paper_trades` co-located with the existing pulse_cache.db.

Public API
----------
  push_trade(idea_dict, *, size=1.0, source="trade_idea") -> dict
      Opens a new paper position from the suggested-trade payload.

  list_positions(status="all") -> list[dict]
      'all' | 'open' | 'closed'. Open positions are marked-to-market against
      the most-recent live price before return.

  close_trade(trade_id, *, reason="manual") -> dict
      Force-closes an open trade at the current market price.

  clear_trades(scope="all") -> int
      'all' | 'closed' — wipes trades. Useful for demo resets.

  mark_to_market() -> dict
      Run by the APScheduler — checks every open trade, auto-closes if
      target/stop touched, otherwise updates unrealised PnL. Returns a
      summary {checked, auto_closed, still_open}.

  get_performance(window="all") -> dict
      Aggregate stats over closed trades.

Trade semantics
---------------
* LONG  : +PnL when exit > entry
* SHORT : +PnL when exit < entry
* size  : float — number of contracts (always 1 by default; we don't
          model contract multipliers in paper mode)
* target / stop : absolute price levels. The MTM loop will close at
          target on TP-hit or at stop on SL-hit, whichever comes first.
"""

from __future__ import annotations

import json
import logging
import math
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from typing import Optional

_BACKEND = os.path.abspath(os.path.dirname(__file__))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

log = logging.getLogger("pulse.paper")

_DB_PATH = os.path.join(_BACKEND, "db", "pulse_cache.db")


# ── Schema bootstrap ─────────────────────────────────────────────────────────

def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(_DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


def _ensure_table() -> None:
    c = _conn()
    c.execute("""
        CREATE TABLE IF NOT EXISTS paper_trades (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            asset         TEXT    NOT NULL,
            direction     TEXT    NOT NULL CHECK (direction IN ('LONG','SHORT')),
            size          REAL    NOT NULL DEFAULT 1.0,
            entry_price   REAL    NOT NULL,
            target_price  REAL,
            stop_price    REAL,
            opened_at     TEXT    NOT NULL,
            closed_at     TEXT,
            exit_price    REAL,
            close_reason  TEXT,
            status        TEXT    NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN','CLOSED')),
            source        TEXT,
            conviction    TEXT,
            thesis        TEXT,
            mtm_price     REAL,
            mtm_at        TEXT,
            unrealised    REAL,
            realised      REAL,
            realised_pct  REAL,
            metadata_json TEXT
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_paper_status ON paper_trades(status)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_paper_opened ON paper_trades(opened_at)")
    # Phase 2.8.6-followup: A/B test column. NULL = legacy / non-AB row.
    # Values: 'pooled' (un-gated PULSE_REGIME_MODE=pooled arm) or
    # 'gated' (Phase 2.6 PULSE_GATED_BLEND=1 arm). Added via ALTER for
    # backward-compat on existing DBs.
    try:
        c.execute("ALTER TABLE paper_trades ADD COLUMN ab_mode TEXT DEFAULT NULL")
    except sqlite3.OperationalError:
        pass  # column already present
    try:
        c.execute("ALTER TABLE paper_trades ADD COLUMN ab_session TEXT DEFAULT NULL")
    except sqlite3.OperationalError:
        pass
    c.execute("CREATE INDEX IF NOT EXISTS idx_paper_ab_mode ON paper_trades(ab_mode)")
    # Phase 2 Sprint 2b: per-leg book for spread/butterfly positions.
    # Parent paper_trades row still records the synthetic-spread entry/MTM/PnL
    # so all existing analytics (Sharpe, equity curve, etc.) keep working.
    # Legs are an audit-grade breakdown that lets us show what's actually held.
    c.execute("""
        CREATE TABLE IF NOT EXISTS paper_legs (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_id     INTEGER NOT NULL,
            contract     TEXT    NOT NULL,
            direction    TEXT    NOT NULL CHECK (direction IN ('LONG','SHORT')),
            qty          REAL    NOT NULL,
            entry_price  REAL    NOT NULL,
            mtm_price    REAL,
            mtm_at       TEXT,
            unrealised   REAL,
            exit_price   REAL,
            realised     REAL,
            FOREIGN KEY (trade_id) REFERENCES paper_trades(id)
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_paper_legs_trade ON paper_legs(trade_id)")
    c.commit()
    c.close()


_ensure_table()


def _leg_defs_for(asset: str) -> list[tuple[str, float]]:
    """Return [(contract, signed_qty), ...] for a known spread, else []."""
    try:
        from research.spread_universe import LEG_DEFS
        return list(LEG_DEFS.get(asset, []))
    except Exception:
        return []


def _leg_prices_for(asset: str) -> dict[str, float]:
    try:
        from research.spread_universe import current_leg_prices
        return current_leg_prices(asset)
    except Exception as exc:
        log.warning("leg-price lookup failed for %s: %s", asset, exc)
        return {}


# ── Helpers ─────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _live_price(asset: str) -> Optional[float]:
    """
    Pull the latest "price" for asset.
    Supports two kinds of asset key:
      • Single-asset    — "brent", "wti", "henry_hub" → from /api/prices cache
      • Spread / fly    — e.g. "brent_m1_m2", "brent_m3_m6", "brent_fly_123",
        "wti_m1_m2", "wti_m3_m6", "wti_fly_123"
        → computed from /Data settlements via research.spread_universe.
        This lets MTM compare apples-to-apples for regime-engine trades.
    """
    # ── Spread / fly asset keys (Brent + WTI from Sprint 3 onward) ─────────
    if asset and (
        asset.startswith("brent_") or asset.startswith("wti_m") or asset.startswith("wti_fly")
    ):
        try:
            from research.spread_universe import current_values
            vals = current_values()
            v = vals.get(asset)
            if v is not None:
                return float(v)
        except Exception as exc:
            log.warning("spread price lookup failed for %s: %s", asset, exc)
            return None
    # ── Single-asset live price (Brent/WTI/HH) ─────────────────────────────
    try:
        from db.cache import get_cached
        prices = get_cached("prices", 600) or {}
        return float(prices.get(asset, {}).get("price")) if prices.get(asset) else None
    except Exception as exc:
        log.warning("live price lookup failed for %s: %s", asset, exc)
        return None


def _pnl(direction: str, entry: float, exit_px: float, size: float) -> float:
    """Per-trade dollar PnL — long: exit-entry, short: entry-exit, × size."""
    if direction == "LONG":
        return round((exit_px - entry) * size, 4)
    return round((entry - exit_px) * size, 4)


def _row_to_dict(r: sqlite3.Row, *, with_legs: bool = True) -> dict:
    d = dict(r)
    # Inflate metadata blob
    md = d.pop("metadata_json", None)
    if md:
        try: d["metadata"] = json.loads(md)
        except Exception: d["metadata"] = None
    if with_legs:
        d["legs"] = _fetch_legs(int(d["id"]))
    return d


def _fetch_legs(trade_id: int) -> list[dict]:
    c = _conn()
    rows = c.execute(
        "SELECT * FROM paper_legs WHERE trade_id=? ORDER BY id ASC", (trade_id,)
    ).fetchall()
    c.close()
    return [dict(r) for r in rows]


# ── Public API ───────────────────────────────────────────────────────────────

def push_trade(
    idea: dict,
    *,
    size: float = 1.0,
    source: str = "trade_idea",
    ab_mode: str | None = None,
    ab_session: str | None = None,
) -> dict:
    """
    Open a new paper position from a trade-idea payload.

    Required idea fields:
      direction       — "LONG" / "SHORT" / "NEUTRAL"  (NEUTRAL is rejected)
      live_price      — entry price (falls back to /api/prices cache)
      target_level    — target price
      stop_level      — stop price
    Optional:
      asset           — "brent" / "wti" / "henry_hub"  (default: brent)
      conviction      — "HIGH" / "MODERATE" / "LOW"
      entry_thesis    — list[str] or string
      time_horizon    — string

    A/B harness (Phase 2.8.6-followup):
      ab_mode         — 'pooled' | 'gated' | None
      ab_session      — opaque session/run id (e.g. ISO date 'YYYY-MM-DD')
    """
    direction = (idea.get("direction") or "").upper()
    if direction not in ("LONG", "SHORT"):
        return {"ok": False, "error": f"cannot push direction={direction!r} (must be LONG or SHORT)"}

    asset      = (idea.get("asset") or "brent").lower()
    entry      = idea.get("live_price") or _live_price(asset)
    if not entry or float(entry) <= 0:
        return {"ok": False, "error": "no entry price available"}

    target     = idea.get("target_level")
    stop       = idea.get("stop_level")
    conviction = idea.get("conviction") or "LOW"
    thesis     = idea.get("entry_thesis") or idea.get("thesis") or ""
    if isinstance(thesis, list):
        thesis = " · ".join(str(x) for x in thesis)

    md = {
        "time_horizon":   idea.get("time_horizon"),
        "key_risk":       idea.get("key_risk"),
        "fair_value":     idea.get("fair_value"),
        "morning_brief":  (idea.get("morning_brief") or "")[:1000],
    }

    c = _conn()
    cur = c.execute("""
        INSERT INTO paper_trades
          (asset, direction, size, entry_price, target_price, stop_price,
           opened_at, status, source, conviction, thesis,
           mtm_price, mtm_at, unrealised, metadata_json, ab_mode, ab_session)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'OPEN', ?, ?, ?, ?, ?, 0.0, ?, ?, ?)
    """, (asset, direction, float(size), float(entry),
          float(target) if target else None,
          float(stop)   if stop   else None,
          _now_iso(), source, conviction, str(thesis),
          float(entry), _now_iso(), json.dumps(md),
          ab_mode, ab_session))
    trade_id = cur.lastrowid

    # Spread / butterfly: record per-leg book using today's outright settlements.
    leg_defs = _leg_defs_for(asset)
    if leg_defs:
        leg_prices = _leg_prices_for(asset)
        for contract, signed_qty in leg_defs:
            px = leg_prices.get(contract)
            if px is None:
                log.warning("paper trade #%d: missing leg price for %s; skipped",
                            trade_id, contract)
                continue
            # Long spread keeps the sign; short spread flips every leg.
            leg_signed = signed_qty if direction == "LONG" else -signed_qty
            leg_dir = "LONG" if leg_signed > 0 else "SHORT"
            leg_qty = abs(leg_signed) * float(size)
            c.execute("""
                INSERT INTO paper_legs
                  (trade_id, contract, direction, qty, entry_price,
                   mtm_price, mtm_at, unrealised)
                VALUES (?, ?, ?, ?, ?, ?, ?, 0.0)
            """, (trade_id, contract, leg_dir, leg_qty, float(px),
                  float(px), _now_iso()))

    c.commit()
    row = c.execute("SELECT * FROM paper_trades WHERE id=?", (trade_id,)).fetchone()
    c.close()
    log.info("paper trade #%d opened: %s %s @ %.2f size=%.2f tgt=%s stop=%s legs=%d",
             trade_id, direction, asset, float(entry), size, target, stop,
             len(leg_defs))
    return {"ok": True, "trade": _row_to_dict(row)}


def close_trade(trade_id: int, *, reason: str = "manual") -> dict:
    """Force-close an open trade at the live price."""
    c = _conn()
    row = c.execute("SELECT * FROM paper_trades WHERE id=?", (trade_id,)).fetchone()
    if not row:
        c.close(); return {"ok": False, "error": f"trade {trade_id} not found"}
    if row["status"] == "CLOSED":
        c.close(); return {"ok": False, "error": "already closed", "trade": _row_to_dict(row)}

    exit_px = _live_price(row["asset"]) or row["mtm_price"] or row["entry_price"]
    realised = _pnl(row["direction"], row["entry_price"], exit_px, row["size"])
    realised_pct = round((realised / (row["entry_price"] * row["size"])) * 100, 4) if row["entry_price"] else 0.0

    c.execute("""
        UPDATE paper_trades
           SET status='CLOSED', closed_at=?, exit_price=?, close_reason=?,
               realised=?, realised_pct=?
         WHERE id=?
    """, (_now_iso(), exit_px, reason, realised, realised_pct, trade_id))

    # Finalise legs (if any) at today's outright settlements.
    leg_prices = _leg_prices_for(row["asset"])
    if leg_prices:
        legs = c.execute(
            "SELECT * FROM paper_legs WHERE trade_id=?", (trade_id,)
        ).fetchall()
        for leg in legs:
            px = leg_prices.get(leg["contract"])
            if px is None:
                continue
            pnl = _pnl(leg["direction"], leg["entry_price"], px, leg["qty"])
            c.execute("""
                UPDATE paper_legs
                   SET exit_price=?, mtm_price=?, mtm_at=?, unrealised=?, realised=?
                 WHERE id=?
            """, (float(px), float(px), _now_iso(), pnl, pnl, leg["id"]))

    c.commit()
    out = c.execute("SELECT * FROM paper_trades WHERE id=?", (trade_id,)).fetchone()
    c.close()
    log.info("paper trade #%d closed (%s): exit=%.2f pnl=%.2f (%.2f%%)",
             trade_id, reason, exit_px, realised, realised_pct)
    return {"ok": True, "trade": _row_to_dict(out)}


def mark_to_market() -> dict:
    """Sweep all OPEN trades, auto-close on TP/SL hit, refresh MTM otherwise."""
    c = _conn()
    rows = c.execute("SELECT * FROM paper_trades WHERE status='OPEN'").fetchall()
    summary = {"checked": len(rows), "auto_closed": 0, "still_open": 0}
    for r in rows:
        px = _live_price(r["asset"])
        if px is None:
            summary["still_open"] += 1
            continue
        direction = r["direction"]; entry = r["entry_price"]; size = r["size"]
        tp = r["target_price"]; sl = r["stop_price"]
        # Check whether target / stop has been touched
        if direction == "LONG":
            if tp is not None and px >= tp:
                c.close(); close_trade(r["id"], reason="target_hit"); c = _conn()
                summary["auto_closed"] += 1; continue
            if sl is not None and px <= sl:
                c.close(); close_trade(r["id"], reason="stop_hit"); c = _conn()
                summary["auto_closed"] += 1; continue
        else:  # SHORT
            if tp is not None and px <= tp:
                c.close(); close_trade(r["id"], reason="target_hit"); c = _conn()
                summary["auto_closed"] += 1; continue
            if sl is not None and px >= sl:
                c.close(); close_trade(r["id"], reason="stop_hit"); c = _conn()
                summary["auto_closed"] += 1; continue
        # Otherwise update unrealised PnL
        unreal = _pnl(direction, entry, px, size)
        c.execute("UPDATE paper_trades SET mtm_price=?, mtm_at=?, unrealised=? WHERE id=?",
                  (px, _now_iso(), unreal, r["id"]))
        # Refresh leg-level MTM for spread trades.
        leg_prices = _leg_prices_for(r["asset"])
        if leg_prices:
            legs = c.execute(
                "SELECT * FROM paper_legs WHERE trade_id=?", (r["id"],)
            ).fetchall()
            for leg in legs:
                lp = leg_prices.get(leg["contract"])
                if lp is None:
                    continue
                lpnl = _pnl(leg["direction"], leg["entry_price"], lp, leg["qty"])
                c.execute(
                    "UPDATE paper_legs SET mtm_price=?, mtm_at=?, unrealised=? WHERE id=?",
                    (float(lp), _now_iso(), lpnl, leg["id"]),
                )
        summary["still_open"] += 1
    c.commit(); c.close()
    return summary


def list_positions(status: str = "all", limit: int = 200) -> list[dict]:
    """Return positions, newest first. Marks open positions to market first."""
    if status == "all" or status == "open":
        mark_to_market()
    c = _conn()
    where = ""
    args: tuple = ()
    if status == "open":
        where = "WHERE status='OPEN'"
    elif status == "closed":
        where = "WHERE status='CLOSED'"
    rows = c.execute(f"SELECT * FROM paper_trades {where} ORDER BY id DESC LIMIT ?",
                     args + (limit,)).fetchall()
    c.close()
    return [_row_to_dict(r) for r in rows]


def open_position_exists(asset: str, direction: str, ab_mode: str) -> bool:
    """
    Phase 2.8.6-followup dedup: does an OPEN paper trade already exist for the
    given (asset, direction, ab_mode)? Prevents the A/B harness from stacking
    multiple positions on a persistent signal across days.
    """
    c = _conn()
    row = c.execute(
        "SELECT 1 FROM paper_trades WHERE status='OPEN' AND asset=? AND direction=? AND ab_mode=? LIMIT 1",
        (asset, direction, ab_mode),
    ).fetchone()
    c.close()
    return row is not None


def list_ab_trades(ab_mode: str | None = None, status: str = "all") -> list[dict]:
    """
    Phase 2.8.6-followup: return paper_trades rows filtered by ab_mode.
    ab_mode=None returns every A/B-tagged row (both arms). status filters
    OPEN / CLOSED / all.
    """
    c = _conn()
    clauses = []
    args: list = []
    if ab_mode is None:
        clauses.append("ab_mode IS NOT NULL")
    else:
        clauses.append("ab_mode = ?")
        args.append(ab_mode)
    if status == "open":
        clauses.append("status='OPEN'")
    elif status == "closed":
        clauses.append("status='CLOSED'")
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    rows = c.execute(
        f"SELECT * FROM paper_trades{where} ORDER BY id ASC",
        tuple(args),
    ).fetchall()
    c.close()
    return [_row_to_dict(r, with_legs=False) for r in rows]


def clear_trades(scope: str = "all") -> int:
    """Wipe trades (and their legs). scope: 'all' or 'closed'."""
    c = _conn()
    if scope == "closed":
        c.execute("""
            DELETE FROM paper_legs
             WHERE trade_id IN (SELECT id FROM paper_trades WHERE status='CLOSED')
        """)
        n = c.execute("DELETE FROM paper_trades WHERE status='CLOSED'").rowcount
    else:
        c.execute("DELETE FROM paper_legs")
        n = c.execute("DELETE FROM paper_trades").rowcount
    c.commit(); c.close()
    return n


# ── Performance analytics ────────────────────────────────────────────────────

def _sharpe(returns: list[float]) -> Optional[float]:
    """Sharpe of per-trade % returns. Annualised assuming 252 trades/yr."""
    if len(returns) < 2:
        return None
    mean = sum(returns) / len(returns)
    var  = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    std  = math.sqrt(var) if var > 0 else 0.0
    if std == 0.0:
        return None
    return round((mean / std) * math.sqrt(252), 3)


def _max_drawdown(equity_curve: list[float]) -> float:
    """Max peak-to-trough drawdown in absolute dollars (cumulative PnL series)."""
    if not equity_curve:
        return 0.0
    peak = equity_curve[0]
    max_dd = 0.0
    for v in equity_curve:
        if v > peak: peak = v
        dd = peak - v
        if dd > max_dd: max_dd = dd
    return round(max_dd, 4)


def get_performance(window: str = "all") -> dict:
    """
    Aggregate stats over closed trades.

    Returns
    -------
    {
      total_trades, wins, losses, win_rate_pct,
      total_pnl, avg_pnl_per_trade, avg_win, avg_loss,
      profit_factor (gross_win / gross_loss),
      sharpe_annualised,
      max_drawdown,
      best_trade, worst_trade,
      equity_curve  : [{trade_id, closed_at, cum_pnl}, ...]
    }
    """
    c = _conn()
    rows = c.execute("""
        SELECT id, asset, direction, entry_price, exit_price, realised, realised_pct,
               opened_at, closed_at, close_reason
          FROM paper_trades
         WHERE status='CLOSED' AND realised IS NOT NULL
         ORDER BY id ASC
    """).fetchall()
    c.close()

    if not rows:
        return {
            "total_trades":     0,
            "wins":             0,
            "losses":           0,
            "win_rate_pct":     0.0,
            "total_pnl":        0.0,
            "avg_pnl_per_trade":0.0,
            "avg_win":          0.0,
            "avg_loss":         0.0,
            "profit_factor":    None,
            "sharpe_annualised":None,
            "max_drawdown":     0.0,
            "best_trade":       None,
            "worst_trade":      None,
            "equity_curve":     [],
            "timestamp":        _now_iso(),
        }

    pnls = [r["realised"] for r in rows]
    pcts = [r["realised_pct"] or 0.0 for r in rows]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    gross_w = sum(wins)
    gross_l = abs(sum(losses))
    cum, equity = 0.0, []
    for r in rows:
        cum += r["realised"]
        equity.append({
            "trade_id": r["id"],
            "closed_at": r["closed_at"],
            "cum_pnl":  round(cum, 4),
        })
    best  = max(rows, key=lambda r: r["realised"])
    worst = min(rows, key=lambda r: r["realised"])

    return {
        "total_trades":      len(rows),
        "wins":              len(wins),
        "losses":            len(losses),
        "win_rate_pct":      round(len(wins) / len(rows) * 100, 2),
        "total_pnl":         round(sum(pnls), 4),
        "avg_pnl_per_trade": round(sum(pnls) / len(pnls), 4),
        "avg_win":           round(sum(wins) / len(wins), 4) if wins else 0.0,
        "avg_loss":          round(sum(losses) / len(losses), 4) if losses else 0.0,
        "profit_factor":     round(gross_w / gross_l, 3) if gross_l > 0 else None,
        "sharpe_annualised": _sharpe(pcts),
        "max_drawdown":      _max_drawdown([e["cum_pnl"] for e in equity]),
        "best_trade":        {"id": best["id"],  "pnl": best["realised"],  "asset": best["asset"]},
        "worst_trade":       {"id": worst["id"], "pnl": worst["realised"], "asset": worst["asset"]},
        "equity_curve":      equity,
        "timestamp":         _now_iso(),
    }


if __name__ == "__main__":
    import json as _j
    logging.basicConfig(level=logging.INFO)
    print("=== open positions ===")
    print(_j.dumps(list_positions("open"), indent=2, default=str))
    print("\n=== performance ===")
    print(_j.dumps(get_performance(), indent=2, default=str))
