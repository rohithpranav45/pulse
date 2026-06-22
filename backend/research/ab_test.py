"""
Phase 2.8.6-followup — A/B paper-test harness.
==============================================

Validates the Phase 2.8.6 side finding (un-gated pooled NET Sharpe +0.351
beats current default gated_blend NET +0.297) under live execution
before flipping the production default.

Design
------
Parallel paper books, dual-push per signal day:

  Arm A — 'pooled'    : PULSE_REGIME_MODE=pooled, no gate (Phase 2.5 engine)
  Arm B — 'gated'     : PULSE_GATED_BLEND=1 (current default since Phase 2.6)

Each daily tick generates BOTH recommendations via
`live_ranker.get_recommendation(force_mode=..., force_gated=...)`, iterates
every spread that emits BUY/SELL, and pushes one paper trade per arm tagged
with `ab_mode`. Both arms see identical market conditions — any Sharpe
differential is attributable purely to routing logic (matched-pair power).

Dedup
-----
We do NOT open a new position if an OPEN paper_trades row already exists
for the same (asset, direction, ab_mode). Persistent multi-day signals
become one paper position per signal, not N. This matches what a live book
running each mode would do (it wouldn't double down on a position it
already holds).

Stop criteria (when to declare a winner)
----------------------------------------
Three guards, evaluated together by `get_report()`:

  (1) min_n_closed   — both arms need ≥ 30 closed trades
  (2) p_value_lt     — Welch's t-test on per-trade PnL (unequal variance)
                       must give p < 0.05 to call a winner
  (3) max_days       — hard timeout at 14 calendar days from first tick

If (1) AND (2) are both satisfied → declare winner = arm with higher mean
NET PnL. Otherwise verdict stays 'undecided' until (3) elapses, at which
point we return 'undecided_timeout' with the current numbers.

NET headline
------------
Per-trade PnL is realised PnL minus a Phase 2.8.6 transaction cost
(per-spread RT cost from `walkforward.COST_PER_SPREAD_RT`). Sharpe is
annualised via √252 on per-trade % returns. Mirrors the methodology PDF
exactly so paper numbers are comparable to the walk-forward report.

Public API
----------
  tick()       → dict   : run one daily generation, return summary
  get_report() → dict   : full A/B report for /api/regime/ab
  reset(scope) → int    : clear ab-tagged paper_trades (scope='all'|'closed')
"""

from __future__ import annotations

import json
import logging
import math
import os
import sys
from datetime import datetime, timezone, timedelta
from typing import Optional

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

log = logging.getLogger("pulse.research.ab")

# ── Stop criteria ────────────────────────────────────────────────────────────
MIN_N_CLOSED  = 30        # per arm
P_VALUE_LT    = 0.05      # Welch's t-test threshold to declare winner
MAX_DAYS      = 14        # hard timeout for the A/B run

# Mirror Phase 2.8.6 cost table from walkforward.py — kept in sync per
# gotchas 26 + 37 pattern (cost is a reporting layer, not a model param,
# but the two MUST agree or paper headline diverges from methodology PDF).
COST_PER_SPREAD_RT = {
    "brent_m1_m2":   0.030,
    "brent_m3_m6":   0.040,
    "brent_fly_123": 0.050,
    "wti_m1_m2":     0.030,
    "wti_m3_m6":     0.040,
    "wti_fly_123":   0.050,
}
COST_DEFAULT_RT = 0.040


# ─────────────────────────────────────────────────────────────────────────────
# Tick — generate both arms, push to paper
# ─────────────────────────────────────────────────────────────────────────────
def tick(*, ab_session: Optional[str] = None) -> dict:
    """
    Run one A/B generation step. Idempotent within a session (dedup on open
    (asset, direction, ab_mode)) so safe to call multiple times per day.

    Phase 4 fix (2026-06-17): overlays the live 15-min feed (when available)
    so each arm fires at the *current* spread value, not the most recent daily
    settlement. Without this, signals generated mid-cycle use a price the
    paper book's live MTM has already moved away from — instant TP/SL trips
    show up the next minute. Live overlay → entry, target, stop and unrealised
    are all on the same intraday clock.
    """
    from research.live_ranker import get_recommendation
    from research.live_feed   import get_live_snapshot
    from paper_trading import push_trade, open_position_exists

    session = ab_session or datetime.now(timezone.utc).date().isoformat()

    # Best-effort live overlay — both products. Falls back to daily settlement
    # when the feed is unreachable (Oracle deploy, weekend, share down).
    live_actuals: dict[str, float] = {}
    live_curve = None
    live_as_of = None
    for prod in ("CO", "CL"):
        try:
            snap = get_live_snapshot(prod)
        except Exception as exc:
            log.warning("ab_test.tick: live snapshot %s failed: %s", prod, exc)
            continue
        if not snap.get("available"):
            continue
        for k, v in (snap.get("spreads") or {}).items():
            try:
                live_actuals[k] = float(v["value"]) if isinstance(v, dict) else float(v)
            except (TypeError, ValueError, KeyError):
                continue
        if prod == "CO":
            live_curve = (snap.get("curve") or {}).get("m1_m12")
            live_as_of = snap.get("as_of")
    overlay_kwargs: dict = {}
    if live_actuals:
        overlay_kwargs["live_actuals"] = live_actuals
    if live_curve is not None:
        overlay_kwargs["live_curve_m1m12"] = live_curve

    arms = (
        ("pooled", {"force_mode": "pooled", "force_gated": False, **overlay_kwargs}),
        ("gated",  {"force_mode": "pooled", "force_gated": True,  **overlay_kwargs}),
    )

    summary: dict = {
        "session":   session,
        "ts":        _now_iso(),
        "pushed":    {"pooled": [], "gated": []},
        "skipped":   {"pooled": [], "gated": []},
        "errors":    [],
    }

    for ab_mode, kwargs in arms:
        try:
            rec = get_recommendation(**kwargs)
        except Exception as exc:
            log.warning("ab_test.tick: %s recommendation failed: %s", ab_mode, exc)
            summary["errors"].append({"arm": ab_mode, "error": str(exc)})
            continue
        if not rec or not rec.get("available"):
            summary["errors"].append({"arm": ab_mode, "error": "recommendation unavailable"})
            continue
        for opp in rec.get("ranked") or []:
            spread    = opp.get("spread")
            direction = (opp.get("direction") or "").upper()
            if direction not in ("BUY", "SELL"):
                summary["skipped"][ab_mode].append({"spread": spread, "reason": "NEUTRAL"})
                continue
            # paper_trading uses LONG/SHORT, regime engine uses BUY/SELL
            paper_dir = "LONG" if direction == "BUY" else "SHORT"
            if open_position_exists(spread, paper_dir, ab_mode):
                summary["skipped"][ab_mode].append({"spread": spread, "reason": "already_open"})
                continue
            idea = {
                "asset":        spread,
                "direction":    paper_dir,
                "live_price":   opp.get("current"),
                "target_level": opp.get("target"),
                "stop_level":   opp.get("stop"),
                "conviction":   "MODERATE",
                "entry_thesis": [
                    f"{opp.get('recommendation_source','regime')} arm under {ab_mode}",
                    f"z={opp.get('z_score'):+.2f}, fair={opp.get('fair_value')}",
                    f"winner={opp.get('winner_model')}",
                ],
                "time_horizon": "20d",
                "fair_value":   opp.get("fair_value"),
            }
            # Notional sizing: pooled arm always 1.0 (no gate, no sizing).
            # Gated arm respects whatever PULSE_GATED_SIZE is set (default full=1.0).
            size = float(opp.get("notional_scale") or 1.0) if ab_mode == "gated" else 1.0
            try:
                out = push_trade(
                    idea,
                    size=size,
                    source=f"ab_{ab_mode}",
                    ab_mode=ab_mode,
                    ab_session=session,
                )
                if out.get("ok"):
                    tr = out.get("trade") or {}
                    summary["pushed"][ab_mode].append({
                        "id":        tr.get("id"),
                        "spread":    spread,
                        "direction": paper_dir,
                        "entry":     tr.get("entry_price"),
                    })
                else:
                    summary["skipped"][ab_mode].append({
                        "spread": spread,
                        "reason": out.get("error") or "push_failed",
                    })
            except Exception as exc:
                log.warning("ab_test.tick: push %s/%s failed: %s", ab_mode, spread, exc)
                summary["errors"].append({"arm": ab_mode, "spread": spread, "error": str(exc)})

    log.info(
        "ab_test.tick session=%s pushed pooled=%d gated=%d skipped pooled=%d gated=%d errors=%d",
        session,
        len(summary["pushed"]["pooled"]),
        len(summary["pushed"]["gated"]),
        len(summary["skipped"]["pooled"]),
        len(summary["skipped"]["gated"]),
        len(summary["errors"]),
    )
    return summary


# ─────────────────────────────────────────────────────────────────────────────
# Reporting
# ─────────────────────────────────────────────────────────────────────────────
def _cost_for(asset: str, size: float) -> float:
    base = COST_PER_SPREAD_RT.get(asset, COST_DEFAULT_RT)
    return base * float(size or 1.0)


def _net_pnl(trade: dict) -> float:
    """Realised PnL minus Phase 2.8.6 RT cost. NaN for open trades."""
    realised = trade.get("realised")
    if realised is None:
        return float("nan")
    return float(realised) - _cost_for(trade.get("asset") or "", trade.get("size") or 1.0)


def _arm_metrics(trades: list[dict]) -> dict:
    """
    Compute per-arm headline metrics from a list of paper_trades rows.

    Counts opens + closes; Sharpe / mean PnL / hit rate over CLOSED only;
    NET applies the Phase 2.8.6 cost table.
    """
    closed = [t for t in trades if (t.get("status") == "CLOSED" and t.get("realised") is not None)]
    open_n = sum(1 for t in trades if t.get("status") == "OPEN")

    if not closed:
        return {
            "n_opened":      len(trades),
            "n_closed":      0,
            "n_open":        open_n,
            "hit_rate":      None,
            "mean_pnl_gross":None,
            "mean_pnl_net":  None,
            "total_pnl_gross": 0.0,
            "total_pnl_net":   0.0,
            "sharpe_gross":  None,
            "sharpe_net":    None,
            "max_dd_net":    0.0,
            "mean_cost":     None,
            "equity_curve":  [],
        }

    gross = [float(t["realised"]) for t in closed]
    net   = [_net_pnl(t)         for t in closed]
    costs = [_cost_for(t.get("asset") or "", t.get("size") or 1.0) for t in closed]
    wins  = sum(1 for x in net if x > 0)

    def _sharpe(seq):
        if len(seq) < 2:
            return None
        m = sum(seq) / len(seq)
        v = sum((x - m) ** 2 for x in seq) / (len(seq) - 1)
        s = math.sqrt(v) if v > 0 else 0.0
        if s == 0:
            return None
        return round((m / s) * math.sqrt(252), 3)

    # Equity curve uses NET cumulative — that's the headline trader sees.
    cum, eq = 0.0, []
    for t, n in zip(closed, net):
        cum += n
        eq.append({"closed_at": t.get("closed_at"), "cum_pnl_net": round(cum, 4), "trade_id": t.get("id")})

    peak = eq[0]["cum_pnl_net"] if eq else 0.0
    max_dd = 0.0
    for p in eq:
        v = p["cum_pnl_net"]
        if v > peak: peak = v
        if (peak - v) > max_dd: max_dd = peak - v

    return {
        "n_opened":        len(trades),
        "n_closed":        len(closed),
        "n_open":          open_n,
        "hit_rate":        round(wins / len(closed), 4),
        "mean_pnl_gross":  round(sum(gross) / len(gross), 4),
        "mean_pnl_net":    round(sum(net)   / len(net),   4),
        "total_pnl_gross": round(sum(gross), 4),
        "total_pnl_net":   round(sum(net),   4),
        "sharpe_gross":    _sharpe(gross),
        "sharpe_net":      _sharpe(net),
        "max_dd_net":      round(max_dd, 4),
        "mean_cost":       round(sum(costs) / len(costs), 4),
        "equity_curve":    eq,
    }


def _welch_t(a: list[float], b: list[float]) -> dict:
    """
    Welch's two-sample t-test on per-trade NET PnL.
    Returns {t_stat, df, p_value} or {t_stat:None,...} when n<2 in either arm.
    Two-sided p computed via scipy when available, else a normal-approx fallback.
    """
    if len(a) < 2 or len(b) < 2:
        return {"t_stat": None, "df": None, "p_value": None}
    ma = sum(a) / len(a)
    mb = sum(b) / len(b)
    va = sum((x - ma) ** 2 for x in a) / (len(a) - 1)
    vb = sum((x - mb) ** 2 for x in b) / (len(b) - 1)
    se = math.sqrt(va / len(a) + vb / len(b))
    if se == 0:
        return {"t_stat": None, "df": None, "p_value": None}
    t = (ma - mb) / se
    # Welch-Satterthwaite df
    num = (va / len(a) + vb / len(b)) ** 2
    den = (va / len(a)) ** 2 / (len(a) - 1) + (vb / len(b)) ** 2 / (len(b) - 1)
    df = num / den if den > 0 else float("nan")
    # Try scipy for the proper t-distribution p-value; fall back to normal approx.
    p_value: float
    try:
        from scipy import stats as _stats  # type: ignore
        p_value = float(2.0 * (1.0 - _stats.t.cdf(abs(t), df)))
    except Exception:
        # Normal approximation — fine when df is large; conservative otherwise.
        # erf-based two-sided p for N(0,1).
        p_value = float(math.erfc(abs(t) / math.sqrt(2.0)))
    return {
        "t_stat":  round(t, 4),
        "df":      round(float(df), 2) if df == df else None,  # filter NaN
        "p_value": round(p_value, 6),
    }


_BACKTEST_VERDICT_CACHE: dict | None = None


def backtest_verdict(*, force: bool = False) -> dict:
    """
    The pooled-vs-gated verdict from the walk-forward BACKTEST tapes — available
    instantly, on thousands of CLOSED trades, instead of waiting weeks for the
    live forward book to close 30/arm.

    Reads `pooled_trades.json` / `gated_trades.json` / `baseline_trades.json`
    (the same tapes the methodology PDF is built from), applies the Phase 2.8.6
    NET cost model (`walkforward._cost_for`, keyed by spread), and runs the same
    Welch t-test on per-trade NET PnL that the live arms use. Cached per process
    (the tapes only change when the walk-forward reruns).
    """
    global _BACKTEST_VERDICT_CACHE
    if _BACKTEST_VERDICT_CACHE is not None and not force:
        return _BACKTEST_VERDICT_CACHE

    import json
    import os

    base_dir = os.path.join(os.path.dirname(__file__), "..", "data", "research")
    try:
        from research.walkforward import _cost_for as _wf_cost
    except Exception:  # pragma: no cover — walkforward import guard
        _wf_cost = lambda r: COST_PER_SPREAD_RT.get(r.get("spread", ""), COST_DEFAULT_RT)

    def _net_from_tape(name: str) -> list[float]:
        path = os.path.join(base_dir, name)
        if not os.path.exists(path):
            return []
        with open(path) as f:
            rows = json.load(f)
        out = []
        for r in rows:
            if r.get("direction") == "NEUTRAL" or r.get("fwd_pnl") is None:
                continue
            out.append(float(r["fwd_pnl"]) - float(_wf_cost(r)))
        return out

    def _stat(net: list[float]) -> dict:
        n = len(net)
        if n < 2:
            return {"n_closed": n, "hit_rate": None, "mean_pnl_net": None, "sharpe_net": None}
        m = sum(net) / n
        v = sum((x - m) ** 2 for x in net) / (n - 1)
        s = math.sqrt(v) if v > 0 else 0.0
        return {
            "n_closed":     n,
            "hit_rate":     round(sum(1 for x in net if x > 0) / n, 4),
            "mean_pnl_net": round(m, 4),
            # 20-day horizon → annualise √(252/20), matching walkforward._metrics.
            "sharpe_net":   round((m / s) * math.sqrt(252.0 / 20.0), 3) if s > 0 else None,
        }

    pooled = _net_from_tape("pooled_trades.json")
    gated  = _net_from_tape("gated_trades.json")
    base   = _net_from_tape("baseline_trades.json")

    if not pooled or not gated:
        return {"available": False,
                "error": "backtest tapes missing — run the walk-forward first"}

    welch = _welch_t(pooled, gated)
    p = welch.get("p_value")
    arm_p, arm_g = _stat(pooled), _stat(gated)
    sp, sg = arm_p["sharpe_net"], arm_g["sharpe_net"]
    if p is not None and p < P_VALUE_LT:
        winner = "pooled" if (sp or 0) > (sg or 0) else "gated"
        verdict = f"{winner}_wins"
        note = (f"backtest: {winner} NET Sharpe higher, distinguishable "
                f"(Welch p={p} < {P_VALUE_LT}, n={arm_p['n_closed']}/{arm_g['n_closed']})")
    else:
        verdict = "tied"
        note = (f"backtest: pooled +{sp} vs gated +{sg} NET Sharpe — statistically tied "
                f"(Welch p={p}); keep the current gated default. Baseline (+{base and _stat(base)['sharpe_net']}) "
                f"is the real headline.")

    out = {
        "available":   True,
        "source":      "walk-forward tapes (2018–2026)",
        "arms": {
            "pooled":   arm_p,
            "gated":    arm_g,
            "baseline": _stat(base) if base else None,
        },
        "welch":       welch,
        "verdict":     verdict,
        "verdict_note": note,
    }
    _BACKTEST_VERDICT_CACHE = out
    return out


def get_report() -> dict:
    """
    Build the full A/B report for the dashboard.

    Shape:
      {
        available:   bool,
        as_of:       iso,
        sessions:    [iso, ...],
        days_elapsed:int,
        arms: {
          pooled: { ...arm metrics... },
          gated:  { ...arm metrics... },
        },
        diff: {
          mean_pnl_net_delta:  pooled - gated,
          sharpe_net_delta:    pooled - gated,
          welch: {t_stat, df, p_value},
          paired: {n_pairs, mean_diff, t_stat, p_value}
        },
        stop_criteria: {
          min_n_closed:  30,
          p_value_lt:    0.05,
          max_days:      14,
          n_closed_ok:   bool,
          p_value_ok:    bool,
          timeout:       bool,
        },
        verdict:     'pooled_wins' | 'gated_wins' | 'undecided' | 'undecided_timeout' | 'no_data',
        verdict_note:str,
      }
    """
    from paper_trading import list_ab_trades

    pooled = list_ab_trades(ab_mode="pooled")
    gated  = list_ab_trades(ab_mode="gated")

    if not pooled and not gated:
        return {
            "available":     False,
            "as_of":         _now_iso(),
            "verdict":       "no_data",
            "verdict_note":  "no A/B-tagged paper trades on disk — run ab_test.tick() to start",
            "arms":          {"pooled": _arm_metrics([]), "gated": _arm_metrics([])},
            "diff":          {},
            "stop_criteria": {
                "min_n_closed": MIN_N_CLOSED,
                "p_value_lt":   P_VALUE_LT,
                "max_days":     MAX_DAYS,
                "n_closed_ok":  False,
                "p_value_ok":   False,
                "timeout":      False,
            },
        }

    arm_p = _arm_metrics(pooled)
    arm_g = _arm_metrics(gated)

    # Welch on per-trade NET PnL across all closed trades in each arm
    net_p = [_net_pnl(t) for t in pooled if t.get("status") == "CLOSED" and t.get("realised") is not None]
    net_g = [_net_pnl(t) for t in gated  if t.get("status") == "CLOSED" and t.get("realised") is not None]
    welch = _welch_t(net_p, net_g)

    # Paired by (session, asset, direction) — matched-pair sees identical market
    paired = _paired_t(pooled, gated)

    # Session timeline
    sessions = sorted({t.get("ab_session") for t in (pooled + gated) if t.get("ab_session")})
    days_elapsed = 0
    if sessions:
        try:
            first = datetime.fromisoformat(sessions[0]).date()
            last  = datetime.now(timezone.utc).date()
            days_elapsed = (last - first).days
        except Exception:
            days_elapsed = 0

    # Stop criteria
    n_closed_ok = (arm_p["n_closed"] >= MIN_N_CLOSED and arm_g["n_closed"] >= MIN_N_CLOSED)
    p_value_ok  = welch["p_value"] is not None and welch["p_value"] < P_VALUE_LT
    timeout     = days_elapsed >= MAX_DAYS

    # Verdict
    if n_closed_ok and p_value_ok:
        if (arm_p["mean_pnl_net"] or 0) > (arm_g["mean_pnl_net"] or 0):
            verdict = "pooled_wins"
            note    = f"pooled NET mean PnL beats gated with p={welch['p_value']}<{P_VALUE_LT}, n=({arm_p['n_closed']},{arm_g['n_closed']})"
        else:
            verdict = "gated_wins"
            note    = f"gated NET mean PnL beats pooled with p={welch['p_value']}<{P_VALUE_LT}, n=({arm_p['n_closed']},{arm_g['n_closed']})"
    elif timeout:
        verdict = "undecided_timeout"
        note    = f"max_days={MAX_DAYS} reached; n_closed=({arm_p['n_closed']},{arm_g['n_closed']}), p={welch['p_value']}"
    else:
        verdict = "undecided"
        bits = []
        if not n_closed_ok:
            bits.append(f"need >={MIN_N_CLOSED} closed/arm (have {arm_p['n_closed']}/{arm_g['n_closed']})")
        if not p_value_ok:
            bits.append(f"p={welch['p_value']} >= {P_VALUE_LT}" if welch["p_value"] is not None else "p_value unavailable (n too small)")
        note = "; ".join(bits)

    return {
        "available":  True,
        "as_of":      _now_iso(),
        "sessions":   sessions,
        "days_elapsed": days_elapsed,
        "arms":       {"pooled": arm_p, "gated": arm_g},
        "diff": {
            "mean_pnl_net_delta": round(
                (arm_p["mean_pnl_net"] or 0) - (arm_g["mean_pnl_net"] or 0), 4
            ),
            "sharpe_net_delta": (
                round((arm_p["sharpe_net"] or 0) - (arm_g["sharpe_net"] or 0), 3)
                if (arm_p["sharpe_net"] is not None and arm_g["sharpe_net"] is not None)
                else None
            ),
            "welch":  welch,
            "paired": paired,
        },
        "stop_criteria": {
            "min_n_closed": MIN_N_CLOSED,
            "p_value_lt":   P_VALUE_LT,
            "max_days":     MAX_DAYS,
            "n_closed_ok":  bool(n_closed_ok),
            "p_value_ok":   bool(p_value_ok),
            "timeout":      bool(timeout),
        },
        "verdict":     verdict,
        "verdict_note":note,
        # The instant, statistically-strong answer from the backtest tapes — the
        # live forward book above is slow confirmation of this.
        "backtest_verdict": backtest_verdict(),
    }


def _paired_t(pooled: list[dict], gated: list[dict]) -> dict:
    """
    Paired t-test on matched (session, asset, direction) closed trades.
    Same market exposure → tighter inference than the Welch unpaired test.
    """
    def key(t):
        return (t.get("ab_session"), t.get("asset"), t.get("direction"))

    p_map = {key(t): _net_pnl(t) for t in pooled if t.get("status") == "CLOSED" and t.get("realised") is not None}
    g_map = {key(t): _net_pnl(t) for t in gated  if t.get("status") == "CLOSED" and t.get("realised") is not None}
    common = sorted(set(p_map) & set(g_map))
    diffs = [p_map[k] - g_map[k] for k in common]
    if len(diffs) < 2:
        return {"n_pairs": len(diffs), "mean_diff": None, "t_stat": None, "p_value": None}
    m = sum(diffs) / len(diffs)
    v = sum((x - m) ** 2 for x in diffs) / (len(diffs) - 1)
    s = math.sqrt(v) if v > 0 else 0.0
    if s == 0:
        return {"n_pairs": len(diffs), "mean_diff": round(m, 4), "t_stat": None, "p_value": None}
    se = s / math.sqrt(len(diffs))
    t = m / se
    df = len(diffs) - 1
    try:
        from scipy import stats as _stats  # type: ignore
        p = float(2.0 * (1.0 - _stats.t.cdf(abs(t), df)))
    except Exception:
        p = float(math.erfc(abs(t) / math.sqrt(2.0)))
    return {
        "n_pairs":   len(diffs),
        "mean_diff": round(m, 4),
        "t_stat":    round(t, 4),
        "p_value":   round(p, 6),
    }


def reset(scope: str = "all") -> int:
    """
    Wipe A/B-tagged paper trades (and their legs). scope='all'|'closed'.
    Does NOT touch non-A/B paper rows.
    """
    import sqlite3
    from paper_trading import _DB_PATH  # type: ignore
    c = sqlite3.connect(_DB_PATH)
    c.row_factory = sqlite3.Row
    if scope == "closed":
        c.execute("""
            DELETE FROM paper_legs
             WHERE trade_id IN (SELECT id FROM paper_trades WHERE ab_mode IS NOT NULL AND status='CLOSED')
        """)
        n = c.execute("DELETE FROM paper_trades WHERE ab_mode IS NOT NULL AND status='CLOSED'").rowcount
    else:
        c.execute("""
            DELETE FROM paper_legs
             WHERE trade_id IN (SELECT id FROM paper_trades WHERE ab_mode IS NOT NULL)
        """)
        n = c.execute("DELETE FROM paper_trades WHERE ab_mode IS NOT NULL").rowcount
    c.commit(); c.close()
    return n


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import json as _j
    print("=== tick ===")
    print(_j.dumps(tick(), indent=2, default=str))
    print("\n=== report ===")
    print(_j.dumps(get_report(), indent=2, default=str))
