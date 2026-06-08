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
    c.commit()
    c.close()


_ensure_table()


# ── Helpers ─────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _live_price(asset: str) -> Optional[float]:
    """
    Pull the latest "price" for asset.
    Supports two kinds of asset key:
      • Single-asset    — "brent", "wti", "henry_hub" → from /api/prices cache
      • Spread / fly    — e.g. "brent_m1_m2", "brent_m3_m6", "brent_fly_123"
        → computed from /Data Brent settlements via research.spread_universe.
        This lets MTM compare apples-to-apples for regime-engine trades.
    """
    # ── Spread / fly asset keys ────────────────────────────────────────────
    if asset and asset.startswith("brent_"):
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


def _row_to_dict(r: sqlite3.Row) -> dict:
    d = dict(r)
    # Inflate metadata blob
    md = d.pop("metadata_json", None)
    if md:
        try: d["metadata"] = json.loads(md)
        except Exception: d["metadata"] = None
    return d


# ── Public API ───────────────────────────────────────────────────────────────

def push_trade(idea: dict, *, size: float = 1.0, source: str = "trade_idea") -> dict:
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
           mtm_price, mtm_at, unrealised, metadata_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'OPEN', ?, ?, ?, ?, ?, 0.0, ?)
    """, (asset, direction, float(size), float(entry),
          float(target) if target else None,
          float(stop)   if stop   else None,
          _now_iso(), source, conviction, str(thesis),
          float(entry), _now_iso(), json.dumps(md)))
    trade_id = cur.lastrowid
    c.commit()
    row = c.execute("SELECT * FROM paper_trades WHERE id=?", (trade_id,)).fetchone()
    c.close()
    log.info("paper trade #%d opened: %s %s @ %.2f size=%.2f tgt=%s stop=%s",
             trade_id, direction, asset, float(entry), size, target, stop)
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


def clear_trades(scope: str = "all") -> int:
    """Wipe trades. scope: 'all' or 'closed'."""
    c = _conn()
    if scope == "closed":
        n = c.execute("DELETE FROM paper_trades WHERE status='CLOSED'").rowcount
    else:
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
