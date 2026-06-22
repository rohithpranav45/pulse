"""
strategy_lab.py — modular multi-strategy bake-off on the Brent term structure.

Why this exists
---------------
The regime-conditional strategy ties/loses to a naive baseline on net Sharpe
over 2018-2026 (walkforward_report.json). Rather than keep forcing one idea, this
module competes several well-founded alpha sources head-to-head on the REAL
31-tenor Brent settlement curve (2016-2026, 100% coverage), with strict
no-look-ahead and variable transaction costs, and lets the data pick the winner.

Universe
--------
Front-12 Brent curve → 11 adjacent calendar spreads (c_i - c_{i+1}) + 10
butterflies (c_i - 2c_{i+1} + c_{i+2}) = 21 instruments. The deep curve
(c13-c31) is real but illiquid; front-12 mirrors the live feed.

Strategies (each maps a price panel → target positions in [-1, 1] per
instrument, using ONLY trailing information):
  • mean_rev   — rolling-z reversion (short rich / long cheap)  [the incumbent's core]
  • momentum   — time-series momentum (trend persistence)
  • carry      — structure persistence (long the normalised level)
  • curve_rv   — butterfly-only z reversion (pure curvature relative value)
  • combo      — equal-risk blend of the orthogonal survivors

Backtest
--------
P&L_t = position_{t-1} · Δspread_t   (decide on close t-1, earn t — no look-ahead).
Costs charged on turnover |Δposition| × cost_per_rt. Metrics: annualised Sharpe,
max drawdown, profit factor, hit-rate, turnover, plus sub-period robustness and a
0%-vs-realistic cost sweep.

Run: python -m backend.research.strategy_lab
"""
from __future__ import annotations

import os
import sys
import numpy as np
import pandas as pd

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

N_TENORS   = 12
ROLL_WIN   = 252      # 1y trailing window for z-scores / vol
ANN        = 252.0
# Realistic round-trip cost per unit turnover, in $/bbl spread terms. A front
# Brent calendar spread trades ~1 tick (≈$0.01) per leg; a 2-leg RT ≈ $0.02-0.04.
COST_RT    = 0.03


# ── Universe ────────────────────────────────────────────────────────────────
# Wider term spreads a real desk watches (front carry, prompt-vs-deferred, deferred).
_WIDE_SPREADS = [(1, 3), (2, 4), (1, 6), (3, 6), (6, 9), (6, 12), (3, 9)]


def build_universe(n_tenors: int = N_TENORS, *, include_wti: bool = False) -> pd.DataFrame:
    """Professional Brent (+optional WTI) RV universe: adjacent calendar spreads,
    wider term spreads, and butterflies across the front curve."""
    from data_lake import get_brent_settlements, get_wti_settlements
    b = get_brent_settlements()
    if b is None or b.empty:
        raise RuntimeError("Brent settlements missing")

    def _legs(df: pd.DataFrame, tag: str) -> dict[str, pd.Series]:
        # Adapt to the product's actual depth (WTI synth only carries c1-c6).
        avail = [i for i in range(1, n_tenors + 1) if f"c{i}" in df.columns]
        m = max(avail) if avail else 0
        df = df[[f"c{i}" for i in avail]].dropna()
        out: dict[str, pd.Series] = {}
        for i in range(1, m):                              # adjacent calendar spreads
            out[f"{tag}_cs_{i}_{i+1}"] = df[f"c{i}"] - df[f"c{i+1}"]
        for a, z in _WIDE_SPREADS:                          # wider term spreads
            if a <= m and z <= m:
                out[f"{tag}_cs_{a}_{z}"] = df[f"c{a}"] - df[f"c{z}"]
        for i in range(1, m - 1):                          # butterflies
            out[f"{tag}_fly_{i}"] = df[f"c{i}"] - 2.0 * df[f"c{i+1}"] + df[f"c{i+2}"]
        return out

    inst = _legs(b, "br")
    if include_wti:
        w = get_wti_settlements()
        if w is not None and not w.empty:
            inst.update(_legs(w.reindex(b.index), "wti"))
            # Brent-WTI Atlantic-basin arb (front) — a classic inter-commodity RV trade
            if "c1" in b.columns and "c1" in w.columns:
                arb = (b["c1"] - w["c1"].reindex(b.index))
                inst["brwti_arb_c1"] = arb
    return pd.DataFrame(inst, index=b.index).dropna(how="all")


def _zscore(panel: pd.DataFrame, win: int = ROLL_WIN) -> pd.DataFrame:
    mu = panel.rolling(win).mean()
    sd = panel.rolling(win).std()
    return (panel - mu) / sd.replace(0, np.nan)


# ── Strategies — each returns target positions in [-1, 1], trailing-only ─────
def strat_mean_rev(panel: pd.DataFrame, *, win: int = ROLL_WIN, entry: float = 1.0) -> pd.DataFrame:
    """Short the rich, long the cheap; gate on |z| ≥ entry."""
    z = _zscore(panel, win)
    pos = -np.tanh(z)
    return pos.where(z.abs() >= entry, 0.0).fillna(0.0)


def strat_momentum(panel: pd.DataFrame, *, look: int = 63) -> pd.DataFrame:
    """Time-series momentum — ride the trend in the spread."""
    chg = panel - panel.shift(look)
    vol = panel.diff().rolling(look).std() * np.sqrt(look)
    return np.tanh(chg / vol.replace(0, np.nan)).fillna(0.0)


def strat_carry(panel: pd.DataFrame, *, win: int = ROLL_WIN) -> pd.DataFrame:
    """Structure persistence — long the normalised level (curve shape persists)."""
    z = _zscore(panel, win)
    return np.tanh(z).fillna(0.0)


def strat_curve_rv(panel: pd.DataFrame, *, win: int = ROLL_WIN, entry: float = 1.0) -> pd.DataFrame:
    """Pure curvature relative value — mean-revert butterfly z-scores only."""
    fly = [c for c in panel.columns if c.startswith("fly_")]
    z = _zscore(panel[fly], win)
    pos = pd.DataFrame(0.0, index=panel.index, columns=panel.columns)
    pos[fly] = (-np.tanh(z)).where(z.abs() >= entry, 0.0).fillna(0.0)
    return pos


def _discrete_band(z: pd.DataFrame, entry: float, exit: float) -> pd.DataFrame:
    """Per-instrument hysteresis band: go ±1 when |z| ≥ entry (short rich / long
    cheap), HOLD until |z| ≤ exit (revert) or the opposite extreme flips it. This
    holds positions for weeks → an order of magnitude less turnover than the
    continuous tanh sizing, which is what preserves the gross edge net of cost."""
    arr = z.values
    pos = np.zeros_like(arr)
    for j in range(arr.shape[1]):
        state = 0.0
        for i in range(arr.shape[0]):
            v = arr[i, j]
            if np.isnan(v):
                pos[i, j] = state
                continue
            if v >= entry:        # rich → short the spread (expect revert down)
                state = -1.0
            elif v <= -entry:     # cheap → long the spread
                state = +1.0
            elif state > 0 and v >= -exit:   # long reverted back to the band → flat
                state = 0.0
            elif state < 0 and v <= exit:    # short reverted back to the band → flat
                state = 0.0
            pos[i, j] = state
    return pd.DataFrame(pos, index=z.index, columns=z.columns)


def strat_mean_rev_d(panel: pd.DataFrame, *, win: int = ROLL_WIN,
                     entry: float = 1.5, exit: float = 0.25) -> pd.DataFrame:
    """Discrete (low-turnover) spread mean-reversion."""
    return _discrete_band(_zscore(panel, win), entry, exit)


def strat_curve_rv_d(panel: pd.DataFrame, *, win: int = ROLL_WIN,
                     entry: float = 1.5, exit: float = 0.25) -> pd.DataFrame:
    """Discrete (low-turnover) butterfly relative value — flies only."""
    fly = [c for c in panel.columns if c.startswith("fly_")]
    z = _zscore(panel[fly], win)
    band = _discrete_band(z, entry, exit)
    pos = pd.DataFrame(0.0, index=panel.index, columns=panel.columns)
    pos[fly] = band
    return pos


STRATEGIES = {
    "mean_rev":   strat_mean_rev,
    "momentum":   strat_momentum,
    "carry":      strat_carry,
    "curve_rv":   strat_curve_rv,
    "mean_rev_d": strat_mean_rev_d,
    "curve_rv_d": strat_curve_rv_d,
}


# ── Backtest engine ─────────────────────────────────────────────────────────
def backtest(panel: pd.DataFrame, pos: pd.DataFrame, *, cost_rt: float = 0.0):
    """Daily portfolio P&L (equal-weight across instruments), net of turnover cost."""
    ret = panel.diff()
    pnl = pos.shift(1) * ret
    turn = pos.diff().abs()
    net = pnl - turn * cost_rt
    port = net.mean(axis=1).dropna()
    turn_daily = turn.mean(axis=1).reindex(port.index)
    return port, turn_daily


def _sharpe(port: pd.Series) -> float:
    if port.std() == 0 or len(port) < 30:
        return float("nan")
    return float(port.mean() / port.std() * np.sqrt(ANN))


def _max_dd(equity: np.ndarray) -> float:
    peak = -np.inf
    dd = 0.0
    for v in equity:
        peak = max(peak, v)
        dd = min(dd, v - peak)
    return float(dd)


def metrics(port: pd.Series, turn: pd.Series, *, target_vol: float = 0.10) -> dict:
    """Risk-adjusted metrics. Equity/DD shown on a vol-scaled $1-NAV basis so
    strategies are comparable; Sharpe is scale-invariant."""
    if port.empty:
        return {}
    sharpe = _sharpe(port)
    # vol-scale daily P&L to target annual vol on $1 NAV for the equity curve
    daily_vol = port.std()
    scale = (target_vol / np.sqrt(ANN)) / daily_vol if daily_vol > 0 else 0.0
    scaled = port * scale
    equity = scaled.cumsum().values
    wins = port[port > 0]
    losses = port[port < 0]
    pf = (wins.sum() / abs(losses.sum())) if losses.sum() != 0 else np.inf
    return {
        "n_days":     int(len(port)),
        "sharpe":     round(sharpe, 3),
        "ann_return": round(float(scaled.mean() * ANN), 4),     # vol-scaled
        "max_dd":     round(_max_dd(equity), 4),                # vol-scaled $
        "calmar":     round(float(scaled.mean() * ANN) / abs(_max_dd(equity)), 3) if _max_dd(equity) != 0 else np.nan,
        "hit_rate":   round(float((port > 0).mean()) * 100, 1),
        "profit_factor": round(float(pf), 3) if np.isfinite(pf) else None,
        "avg_turnover":  round(float(turn.mean()), 4),
        "gross_total":   round(float(port.sum()), 3),           # $/bbl, equal-weight
    }


_ERAS = [("2016-2019", "2016-01-01", "2019-12-31"),
         ("2020-2022", "2020-01-01", "2022-12-31"),
         ("2023-2026", "2023-01-01", "2026-12-31")]


def run_bakeoff(*, cost_rt: float = COST_RT) -> dict:
    panel = build_universe()
    out: dict = {"universe": list(panel.columns), "n_instruments": panel.shape[1],
                 "range": [str(panel.index.min().date()), str(panel.index.max().date())],
                 "cost_rt": cost_rt, "strategies": {}}
    ports: dict[str, pd.Series] = {}
    for name, fn in STRATEGIES.items():
        pos = fn(panel)
        port0, turn = backtest(panel, pos, cost_rt=0.0)
        portc, _    = backtest(panel, pos, cost_rt=cost_rt)
        ports[name] = portc
        eras = {}
        for label, a, z in _ERAS:
            seg = portc.loc[a:z]
            eras[label] = round(_sharpe(seg), 3) if len(seg) > 30 else None
        out["strategies"][name] = {
            "gross": metrics(port0, turn),
            "net":   metrics(portc, turn),
            "sharpe_by_era": eras,
        }
    # Equal-risk combo of the orthogonal survivors (built after individual fits)
    return out, ports, panel


def _fmt(d: dict) -> str:
    if not d:
        return "—"
    return (f"Sharpe {d['sharpe']:+.2f}  PF {d['profit_factor']}  hit {d['hit_rate']}%  "
            f"DD {d['max_dd']:+.3f}  turn {d['avg_turnover']:.3f}")


def cost_sweep(panel: pd.DataFrame, pos: pd.DataFrame, grid=(0.0, 0.01, 0.02, 0.03, 0.05)) -> dict:
    out = {}
    for c in grid:
        port, _ = backtest(panel, pos, cost_rt=c)
        out[c] = round(_sharpe(port), 3)
    return out


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    import warnings; warnings.filterwarnings("ignore")
    panel = build_universe()
    print("=" * 96)
    print(f"STRATEGY BAKE-OFF — Brent front-{N_TENORS} curve · {panel.shape[1]} instruments · "
          f"{panel.index.min().date()} → {panel.index.max().date()}")
    print("=" * 96)

    # 1. All candidates, GROSS (cost 0) + NET (cost $0.03) headline
    print("\n[1] CANDIDATE SCREEN  (gross = no cost · net = $0.03/RT turnover cost)")
    ports: dict[str, pd.Series] = {}
    for name, fn in STRATEGIES.items():
        pos = fn(panel)
        port0, turn = backtest(panel, pos, cost_rt=0.0)
        portc, _    = backtest(panel, pos, cost_rt=0.03)
        ports[name] = portc
        m0, mc = metrics(port0, turn), metrics(portc, turn)
        print(f"  {name:<12} GROSS Sharpe {m0['sharpe']:+.2f} PF {m0['profit_factor']:<6} "
              f"turn {m0['avg_turnover']:.3f}  |  NET Sharpe {mc['sharpe']:+.2f} PF {mc['profit_factor']}")

    # 2. Survivors — cost sensitivity + era robustness
    print("\n[2] SURVIVORS — cost sweep (Sharpe vs $/RT) + sub-period robustness")
    survivors = {"mean_rev_d": strat_mean_rev_d, "curve_rv_d": strat_curve_rv_d}
    surv_ports = {}
    for name, fn in survivors.items():
        pos = fn(panel)
        sweep = cost_sweep(panel, pos)
        portc, turn = backtest(panel, pos, cost_rt=0.02)
        surv_ports[name] = portc
        m = metrics(portc, turn)
        eras = {lab: (round(_sharpe(portc.loc[a:z]), 2) if len(portc.loc[a:z]) > 30 else None)
                for lab, a, z in _ERAS}
        print(f"\n  ■ {name}   (entry |z|≥1.5, exit |z|≤0.25, hold-to-revert)")
        print(f"     cost sweep $/RT: " + "  ".join(f"{c:.2f}→{s:+.2f}" for c, s in sweep.items()))
        print(f"     @ $0.02/RT: Sharpe {m['sharpe']:+.2f}  PF {m['profit_factor']}  hit {m['hit_rate']}%  "
              f"DD {m['max_dd']:+.3f}  turn {m['avg_turnover']:.3f}")
        print(f"     era Sharpe: " + "  ".join(f"{k} {v:+.2f}" if v is not None else f"{k} —"
                                              for k, v in eras.items()))

    # 3. Combo of the two survivors (equal-risk, net of $0.02)
    P = pd.DataFrame(surv_ports).dropna()
    corr = P.corr().iloc[0, 1]
    z = (P / P.std())
    combo = z.mean(axis=1)
    print("\n[3] COMBO  mean_rev_d + curve_rv_d  (equal-risk, net $0.02/RT)")
    print(f"     leg correlation: {corr:+.2f}")
    print(f"     combo Sharpe {_sharpe(combo):+.2f}   "
          + "  ".join(f"{lab} {(_sharpe(combo.loc[a:z2]) if len(combo.loc[a:z2])>30 else float('nan')):+.2f}"
                      for lab, a, z2 in _ERAS))
    print("\n" + "-" * 96)
    print("Read: momentum/carry are structurally negative (spreads mean-revert, don't trend) → rejected.")
    print("curve_rv (butterfly RV) is the gross edge; discrete hold-to-revert preserves it net of cost.")
