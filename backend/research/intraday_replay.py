"""
Phase 3.1 — intraday replay of the live engine over the 15-min feed window.

NOT a statistically valid backtest. The regime strategy's native horizon is 20
trading days with a 30-trading-day time-stop; the live feed is ~3 calendar days
of 15-min bars (one regime snapshot). This walks the REAL 15-min spread path
with the engine's fair value + tuned exit rule (TP halfway-to-fair · SL 2.5σ)
to show exactly what the live engine WOULD have done in-window — a sanity
replay, not a performance claim.

Run: python -m research.intraday_replay   (reads PULSE_LIVE_FEED_DIR / share)
"""
from __future__ import annotations
import sys, os
import pandas as pd

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)


def _build_15min_series(conn, spread: str) -> pd.Series | None:
    """Real 15-min spread path over the whole feed window, contemporaneous legs."""
    from research.live_feed       import list_contracts
    from research.spread_universe import LEG_DEFS
    product = "CL" if spread.startswith("wti_") else "CO"
    contracts = list_contracts(conn, product)
    ord_table = {f"c{i}": t for i, (t, _) in enumerate(contracts[:12], start=1)}
    legs = LEG_DEFS[spread]
    cols = {}
    for ordn, _qty in legs:
        t = ord_table.get(ordn)
        if t is None:
            return None
        s = pd.read_sql(f'SELECT timestamp, close FROM "{t}" ORDER BY timestamp',
                        conn, parse_dates=["timestamp"]).set_index("timestamp")["close"]
        cols[ordn] = s
    aligned = pd.concat(cols, axis=1).dropna()
    if aligned.empty:
        return None
    series = sum(qty * aligned[ordn] for ordn, qty in legs)
    series.name = spread
    return series


def _replay(series: pd.Series, fair: float, sigma: float, z_entry: float,
            tp_frac: float, sl_mult: float) -> list[dict]:
    """Event-driven replay; close-based TP/SL; re-entry allowed after a close."""
    trades: list[dict] = []
    pos = None
    for ts, s in series.items():
        s = float(s)
        z = (s - fair) / sigma if sigma else 0.0
        if pos is None:
            if z >= z_entry:      # spread rich -> SELL (expect mean-revert down)
                pos = dict(dir="SELL", entry=s, t_in=ts,
                           tgt=s + tp_frac * (fair - s), stop=s + sl_mult * sigma)
            elif z <= -z_entry:   # spread cheap -> BUY
                pos = dict(dir="BUY", entry=s, t_in=ts,
                           tgt=s + tp_frac * (fair - s), stop=s - sl_mult * sigma)
            continue
        exit_px = reason = None
        if pos["dir"] == "SELL":
            if s <= pos["tgt"]:   exit_px, reason = pos["tgt"], "target"
            elif s >= pos["stop"]: exit_px, reason = pos["stop"], "stop"
        else:
            if s >= pos["tgt"]:   exit_px, reason = pos["tgt"], "target"
            elif s <= pos["stop"]: exit_px, reason = pos["stop"], "stop"
        if exit_px is not None:
            sign = 1 if pos["dir"] == "BUY" else -1
            trades.append({**pos, "t_out": ts, "exit": exit_px, "reason": reason,
                           "pnl": sign * (exit_px - pos["entry"])})
            pos = None
    if pos is not None:  # still open at window end -> unrealized
        s = float(series.iloc[-1]); sign = 1 if pos["dir"] == "BUY" else -1
        trades.append({**pos, "t_out": series.index[-1], "exit": s, "reason": "open",
                       "pnl": sign * (s - pos["entry"])})
    return trades


_CAVEATS = [
    "~6 calendar days is not a backtest. The strategy horizon is 20 trading days; the "
    "30-day time-stop can never trigger in-window, so trades that don't hit TP/SL are left "
    "OPEN with UNREALIZED PnL.",
    "Models are daily-trained — fair value + sigma are held constant across the window "
    "(mild look-ahead: a true walk-forward re-fits fair each day).",
    "Exits are close-based; intrabar high/low touches are not modeled. Sample is tiny, so "
    "treat every number as illustrative only.",
    "WTI fair values come from SYNTH-trained models (CLAUDE.md gotcha 11) — treat wti_* as indicative.",
]


def _trade_json(t: dict) -> dict:
    """Serialize one replay trade (Timestamps → ISO strings) for the API."""
    return {
        "dir":    t["dir"],
        "t_in":   str(t["t_in"]),
        "entry":  round(float(t["entry"]), 3),
        "target": round(float(t["tgt"]), 3),
        "stop":   round(float(t["stop"]), 3),
        "t_out":  str(t["t_out"]),
        "exit":   round(float(t["exit"]), 3),
        "reason": t["reason"],
        "pnl":    round(float(t["pnl"]), 3),
    }


def _trade_metrics(trades: list[dict]) -> dict | None:
    """Aggregate gross/net metrics for a trade list. pf=None means no losing
    trades (infinite profit factor — the frontend renders this as ∞)."""
    from research.walkforward import COST_PER_SPREAD_RT, COST_DEFAULT_RT
    if not trades:
        return None
    pnls   = [t["pnl"] for t in trades]
    wins   = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    closed = [t for t in trades if t["reason"] != "open"]
    opn    = [t for t in trades if t["reason"] == "open"]
    gross  = sum(pnls)
    cost   = sum(COST_PER_SPREAD_RT.get(t["spread"], COST_DEFAULT_RT) for t in trades)
    gl     = abs(sum(losses))
    pf     = (sum(wins) / gl) if gl > 0 else None
    return {
        "trades":   len(trades),
        "closed":   len(closed),
        "open":     len(opn),
        "wins":     len(wins),
        "losses":   len(losses),
        "win_rate": round(100 * len(wins) / len(pnls), 1),
        "gross":    round(gross, 3),
        "cost":     round(cost, 3),
        "net":      round(gross - cost, 3),
        "pf":       (round(pf, 2) if pf is not None else None),
        "mean":     round(gross / len(pnls), 3),
        "best":     round(max(pnls), 3),
        "worst":    round(min(pnls), 3),
    }


def run_replay(*, include_wti: bool = True) -> dict:
    """
    Structured intraday replay for the API / dashboard (SIGNAL LOG tab).

    Same engine + tuned exit rule as the CLI `main()`, but returns a JSON-able
    dict instead of printing. `available=False` when the live feed is down.
    Read-only — does not persist anything.
    """
    from research.live_feed       import latest_feed_file, _open_feed_local
    from research.live_engine     import get_live_recommendation
    from research.live_ranker     import (TUNED_TP_FRAC, TUNED_SL_MULT,
                                          TUNED_EXCLUDED_SPREADS, GATED_Z_THRESHOLD)
    from research.spread_universe import LABELS

    f = latest_feed_file()
    rec = get_live_recommendation(include_wti=include_wti)
    if not rec.get("available"):
        return {"available": False, "error": rec.get("error"),
                "feed_file": str(f) if f else None}

    params: dict[str, dict] = {}
    for r in rec.get("ranked", []):
        sp = r.get("spread")
        if sp in TUNED_EXCLUDED_SPREADS:
            continue
        fair, cur, z = r.get("fair_value"), r.get("current"), r.get("z_score")
        if fair is None or cur is None or not z:
            continue
        params[sp] = {"fair": fair, "sigma": (cur - fair) / z, "z_latest": z}

    conn = _open_feed_local(f)
    spreads_out: list[dict] = []
    all_trades: list[dict] = []
    win_start = win_end = None
    try:
        for sp, p in params.items():
            series = _build_15min_series(conn, sp)
            if series is None or len(series) < 2:
                continue
            tr = _replay(series, p["fair"], p["sigma"], GATED_Z_THRESHOLD,
                         TUNED_TP_FRAC, TUNED_SL_MULT)
            for t in tr:
                t["spread"] = sp
            all_trades += tr
            s0, s1 = series.index[0], series.index[-1]
            win_start = s0 if (win_start is None or s0 < win_start) else win_start
            win_end   = s1 if (win_end   is None or s1 > win_end)   else win_end
            spreads_out.append({
                "spread":     sp,
                "label":      LABELS[sp],
                "is_wti":     sp.startswith("wti_"),
                "fair":       round(float(p["fair"]), 3),
                "sigma":      round(float(p["sigma"]), 4),
                "z_latest":   round(float(p["z_latest"]), 2),
                "n_bars":     int(len(series)),
                "range_low":  round(float(series.min()), 3),
                "range_high": round(float(series.max()), 3),
                "last":       round(float(series.iloc[-1]), 3),
                "trades":     [_trade_json(t) for t in tr],
                "metrics":    _trade_metrics(tr),
            })
    finally:
        conn.close()

    from datetime import datetime, timezone
    return {
        "available":   True,
        "feed_file":   str(f),
        "regime":      rec.get("regime"),
        "regime_mode": rec.get("regime_mode"),
        "gated":       rec.get("gated_blend"),
        "window":      {"start": str(win_start) if win_start is not None else None,
                        "end":   str(win_end)   if win_end   is not None else None},
        "tuned_rule":  {"entry_z": GATED_Z_THRESHOLD, "tp_frac": TUNED_TP_FRAC,
                        "sl_mult": TUNED_SL_MULT,
                        "note": "TP halfway-to-fair · SL 2.5σ · close-based · re-entry allowed"},
        "spreads":     spreads_out,
        "overall":     _trade_metrics(all_trades),
        "caveats":     _CAVEATS,
        "timestamp":   datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    from research.live_feed       import latest_feed_file, _open_feed_local
    from research.live_engine     import get_live_recommendation
    from research.live_ranker     import (TUNED_TP_FRAC, TUNED_SL_MULT,
                                          TUNED_EXCLUDED_SPREADS, GATED_Z_THRESHOLD)
    from research.walkforward     import COST_PER_SPREAD_RT, COST_DEFAULT_RT
    from research.spread_universe import LABELS

    f = latest_feed_file()
    print(f"feed file : {f}")
    rec = get_live_recommendation(include_wti=True)
    if not rec.get("available"):
        print("live engine unavailable:", rec.get("error")); return
    regime = rec.get("regime")
    print(f"regime    : {regime}   (mode={rec.get('regime_mode')}, gated={rec.get('gated_blend')})")

    # fair + sigma per tradeable spread from the engine (sigma = (current-fair)/z = resid_std)
    params = {}
    for r in rec.get("ranked", []):
        sp = r.get("spread")
        if sp in TUNED_EXCLUDED_SPREADS:
            continue
        fair, cur, z = r.get("fair_value"), r.get("current"), r.get("z_score")
        if fair is None or cur is None or not z:
            continue
        params[sp] = {"fair": fair, "sigma": (cur - fair) / z, "z_latest": z}

    conn = _open_feed_local(f)
    all_trades = []
    try:
        print("\n" + "=" * 110)
        print("INTRADAY REPLAY — 3-day 15-min window  (TP halfway-to-fair · SL 2.5σ · close-based · re-entry allowed)")
        print("=" * 110)
        for sp, p in params.items():
            series = _build_15min_series(conn, sp)
            if series is None or len(series) < 2:
                continue
            tr = _replay(series, p["fair"], p["sigma"], GATED_Z_THRESHOLD,
                         TUNED_TP_FRAC, TUNED_SL_MULT)
            for t in tr:
                t["spread"] = sp
            all_trades += tr
            print(f"\n■ {LABELS[sp]}  ({sp})")
            print(f"   window {series.index[0]} → {series.index[-1]}  ({len(series)} bars)")
            print(f"   spread range [{series.min():+.3f}, {series.max():+.3f}]   last {series.iloc[-1]:+.3f}")
            print(f"   engine fair {p['fair']:+.3f}  σ {p['sigma']:.3f}  z(latest) {p['z_latest']:+.2f}")
            if not tr:
                print("   no entry (|z| never ≥ 0.5 in-window)")
                continue
            print(f"   {'#':<2}{'dir':<5}{'t_in':<17}{'entry':>9}{'target':>9}{'stop':>9}"
                  f"{'t_out':<17}{'exit':>9}{'reason':>8}{'pnl':>9}")
            for i, t in enumerate(tr, 1):
                print(f"   {i:<2}{t['dir']:<5}{str(t['t_in'])[5:16]:<17}{t['entry']:>9.3f}"
                      f"{t['tgt']:>9.3f}{t['stop']:>9.3f}{str(t['t_out'])[5:16]:<17}"
                      f"{t['exit']:>9.3f}{t['reason']:>8}{t['pnl']:>+9.3f}")
    finally:
        conn.close()

    # ── Aggregate metrics (gross + net) ──────────────────────────────────────
    print("\n" + "=" * 110)
    print("METRICS  (gross PnL in $/bbl spread terms; NET subtracts round-trip cost per filled trade)")
    print("=" * 110)
    if not all_trades:
        print("no trades generated."); return

    def block(name, ts):
        if not ts:
            return
        pnls = [t["pnl"] for t in ts]
        closed = [t for t in ts if t["reason"] != "open"]
        opn = [t for t in ts if t["reason"] == "open"]
        wins = [p for p in pnls if p > 0]; losses = [p for p in pnls if p < 0]
        gross = sum(pnls)
        cost = sum(COST_PER_SPREAD_RT.get(t["spread"], COST_DEFAULT_RT) for t in ts)
        net = gross - cost
        gw, gl = sum(wins), abs(sum(losses))
        pf = (gw / gl) if gl > 0 else float("inf")
        print(f"\n{name}")
        print(f"   trades {len(ts)}  (closed {len(closed)}, still-open {len(opn)})   "
              f"wins {len(wins)}  losses {len(losses)}  "
              f"win-rate {100*len(wins)/len(pnls):.0f}%")
        print(f"   GROSS total {gross:+.3f}   mean {gross/len(pnls):+.3f}   "
              f"best {max(pnls):+.3f}   worst {min(pnls):+.3f}")
        print(f"   cost (RT)   {cost:.3f}   NET total {net:+.3f}   "
              f"profit-factor(gross) {pf:.2f}")
        if opn:
            print(f"   note: {len(opn)} trade(s) still OPEN at window end — PnL is UNREALIZED "
                  f"(neither TP nor SL nor the 30-day time-stop reached in 3 days)")

    block("OVERALL", all_trades)
    by = {}
    for t in all_trades:
        by.setdefault(t["spread"], []).append(t)
    for sp, ts in by.items():
        block(f"  {sp}", ts)

    print("\n" + "-" * 110)
    print("CAVEATS — read before quoting any number:")
    print("  • 3 calendar days ≠ a backtest. Strategy horizon is 20 trading days; the 30-day time-stop")
    print("    can never trigger here, so trades that don't hit TP/SL are left OPEN with unrealized PnL.")
    print("  • Models are DAILY-trained; fair value + σ are held constant across the window.")
    print("  • Exits are close-based (intrabar high/low touches not modeled). Sample is tiny → illustrative only.")
    print("  • WTI fair values come from SYNTH-trained models (CLAUDE.md gotcha 11) — treat wti_* as indicative.")


if __name__ == "__main__":
    main()
