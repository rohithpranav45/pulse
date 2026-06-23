"""
L1 — the conditional reaction function (the empirical heart of the framework).

For every EIA crude release in the 1-min era (2021-01 → 2026-05), align the tape
to the 10:30-ET print and measure how the market actually reacted — then ask the
two questions that separate a quant from a tout:

  1.  WHICH instrument moves, and how much per 1σ of surprise?  (spread attribution)
      We measure WTI/Brent flat price, WTI M1-M2 (front tightness, Cushing-driven),
      Brent M1-M2, and WTI-Brent (US location) at horizons 5 / 30 / 60 min + settle.

  2.  WHEN does inventory matter, and when is it noise?  (the meta-result)
      The explanatory power of surprises is itself regime-dependent. We bucket each
      release by curve regime (backwardation vs contango), season, and vol regime,
      and report the surprise→reaction slope + R² inside each bucket. The headline
      deliverable: inventory explains the move in backwardation / low-vol / coherent
      weeks and ≈nothing in contango / high-vol / incoherent weeks.

Plus DECAY: the 10:30 knee-jerk partially mean-reverts; the component that survives
to settle is the tradeable one. We quantify the retained fraction.

Robustness: anchor at the *precise* scheduled time (EIA is punctual; holiday Wed→Thu
shifts handled in release_calendar); prices median-smoothed over 3 min so a single
bad mid can't masquerade as a reaction.

Public API
----------
  build_panel(force_refresh=False) -> pd.DataFrame   one row per release
  conditional_betas(panel)         -> dict           per-instrument/horizon betas
  when_it_mattered(panel)          -> pd.DataFrame    R² by regime bucket (the meta)
  attribution(panel)               -> pd.DataFrame    surprise type -> spread
  decay_profile(panel)             -> dict            knee-jerk vs settle retention

Run standalone:  python -m backend.research.inventory_impact.event_study
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_BACKEND = Path(__file__).resolve().parent.parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import data_lake as dl  # noqa: E402
from research.inventory_impact import eia_report  # noqa: E402
from research.inventory_impact.release_calendar import release_datetime, snap_to_spike  # noqa: E402

log = logging.getLogger("pulse.inventory_impact.event_study")

_CACHE = Path(__file__).parent.parent.parent / "data" / "research" / "inventory_impact"
_CACHE.mkdir(parents=True, exist_ok=True)
_PANEL_PARQUET = _CACHE / "event_panel.parquet"

# horizons in minutes after the print; "settle" handled separately (14:30 ET)
HORIZONS = [5, 30, 60, 120]
# instruments and whether they are a price (% reaction) or a spread ($ reaction)
PRICE_INSTR = ["wti_flat", "brent_flat"]
SPREAD_INSTR = ["wti_m1_m2", "brent_m1_m2", "wti_brent"]
INSTRUMENTS = PRICE_INSTR + SPREAD_INSTR


# ── window loading ───────────────────────────────────────────────────────────
def _pull_window(view: str, lo_utc: pd.Timestamp, hi_utc: pd.Timestamp) -> pd.DataFrame:
    con = dl.duckdb_conn()
    q = f'''
        SELECT timestamp,
               "c1||weighted_mid" AS c1,
               "c2||weighted_mid" AS c2,
               "c3||weighted_mid" AS c3
        FROM {view}
        WHERE timestamp BETWEEN TIMESTAMPTZ '{lo_utc.tz_convert("UTC")}'
                            AND TIMESTAMPTZ '{hi_utc.tz_convert("UTC")}'
        ORDER BY timestamp
    '''
    df = con.execute(q).df()
    if df.empty:
        return df
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    return df.set_index("timestamp")


def _smooth_at(s: pd.Series, t: pd.Timestamp, side: str, half: int = 1) -> float | None:
    """Median mid in a small ±half-minute window for robustness to bad ticks.

    side="pre"  -> use the last `2*half+1`-min window ending at t (no leakage).
    side="post" -> use a window centred on t.
    """
    if s is None or s.empty:
        return None
    if side == "pre":
        win = s[(s.index > t - pd.Timedelta(minutes=2 * half + 1)) & (s.index <= t)]
    else:
        win = s[(s.index >= t - pd.Timedelta(minutes=half)) &
                (s.index <= t + pd.Timedelta(minutes=half))]
    win = win.dropna()
    return float(win.median()) if len(win) else None


def _instrument_series(w: pd.DataFrame, b: pd.DataFrame) -> dict[str, pd.Series]:
    """Construct the tradeable instruments from the WTI/Brent window frames."""
    out: dict[str, pd.Series] = {}
    if not w.empty:
        out["wti_flat"] = w["c1"]
        out["wti_m1_m2"] = (w["c1"] - w["c2"])
    if not b.empty:
        out["brent_flat"] = b["c1"]
        out["brent_m1_m2"] = (b["c1"] - b["c2"])
    if not w.empty and not b.empty:
        # align on the minute
        j = w[["c1"]].join(b[["c1"]], lsuffix="_w", rsuffix="_b", how="inner")
        out["wti_brent"] = (j["c1_w"] - j["c1_b"])
    return out


# ── conditioners (regime / season / vol) ─────────────────────────────────────
def _season_bucket(month: int) -> str:
    # US refined-product seasonality through the crude lens
    if month in (12, 1, 2):
        return "winter"        # heating / winter draw
    if month in (3, 4):
        return "maintenance"   # spring refinery maintenance (shoulder)
    if month in (5, 6, 7, 8):
        return "driving"       # summer driving season (peak draw)
    return "autumn"            # 9,10,11 — shoulder / pre-winter


def _daily_wti_close() -> pd.Series:
    """Daily WTI front close from the 1-min lake (for trailing realised vol)."""
    con = dl.duckdb_conn()
    q = '''SELECT CAST(timestamp AS DATE) d, last("c1||weighted_mid" ORDER BY timestamp) px
           FROM wti_1min GROUP BY 1 ORDER BY 1'''
    df = con.execute(q).df()
    return pd.Series(df["px"].values, index=pd.to_datetime(df["d"]))


# ── the panel ────────────────────────────────────────────────────────────────
def build_panel(force_refresh: bool = False) -> pd.DataFrame:
    """
    One row per EIA crude release in the 1-min era. Columns:
      surprise_z, quality_of_draw, cushing_surprise_z, export_z, ...   (the report)
      curve {BACK,CONTANGO}, season, vol_regime {LOW,MID,HIGH}         (conditioners)
      react_<instrument>_<h>    reaction at horizon h (% for prices, $ for spreads)
      react_<instrument>_settle reaction to 14:30-ET settle
      confirmed                 did a vol spike actually appear at 10:30?
    """
    if not force_refresh and _PANEL_PARQUET.exists():
        return pd.read_parquet(_PANEL_PARQUET)

    # report-side features
    sp = eia_report.surprise_series("crude_ex_spr")
    dec = eia_report.decomposition()
    wf = eia_report.weekly_frame()

    # vol regime input
    wti_close = _daily_wti_close()
    rvol = wti_close.pct_change().rolling(20).std() * np.sqrt(252)

    # lake coverage
    con = dl.duckdb_conn()
    lake_max = pd.Timestamp(con.execute("SELECT MAX(timestamp) FROM wti_1min").fetchone()[0])
    lake_max = lake_max.tz_convert("UTC") if lake_max.tzinfo else lake_max.tz_localize("UTC")
    lake_min = pd.Timestamp(con.execute("SELECT MIN(timestamp) FROM wti_1min").fetchone()[0])
    lake_min = lake_min.tz_convert("UTC") if lake_min.tzinfo else lake_min.tz_localize("UTC")

    rows = []
    for week_ending in sp.index:
        if pd.isna(sp.loc[week_ending, "surprise"]):
            continue
        sched = release_datetime(week_ending)
        if sched < lake_min + pd.Timedelta(days=1) or sched > lake_max - pd.Timedelta(hours=5):
            continue  # outside 1-min coverage

        lo = sched - pd.Timedelta(hours=2)
        hi = sched + pd.Timedelta(hours=6)
        w = _pull_window("wti_1min", lo, hi)
        b = _pull_window("brent_1min", lo, hi)
        if w.empty:
            continue
        instr = _instrument_series(w, b)

        # confirm a release-time vol spike near the scheduled minute
        _, jump = snap_to_spike(sched, w["c1"], search_minutes=4)
        confirmed = jump >= 8.0  # ≥0.8 bp/min localised move

        rec: dict = {
            "release_utc": sched,
            "surprise": sp.loc[week_ending, "surprise"],
            "surprise_z": sp.loc[week_ending, "surprise_z"],
            "actual_change": sp.loc[week_ending, "actual_change"],
            "expected_change": sp.loc[week_ending, "expected_change"],
            "bullish": bool(sp.loc[week_ending, "bullish"]),
            "confirmed": confirmed,
        }
        # report decomposition features
        for col in ["quality_of_draw", "cushing_ex_spr_surprise_z", "cushing_surprise_z",
                    "demand_z", "runs_z", "export_z", "import_z", "adjustment_z",
                    "gasoline_surprise_z", "distillate_surprise_z"]:
            if col in dec.columns:
                rec[col] = dec.loc[week_ending, col] if week_ending in dec.index else np.nan

        # conditioners
        c1 = _smooth_at(w["c1"], sched - pd.Timedelta(minutes=1), "pre")
        c3 = _smooth_at(w["c3"], sched - pd.Timedelta(minutes=1), "pre")
        rec["curve"] = "BACK" if (c1 is not None and c3 is not None and c1 > c3) else "CONTANGO"
        rec["season"] = _season_bucket(sched.tz_convert("America/New_York").month)
        rv = rvol.reindex([sched.tz_convert(None).normalize()], method="ffill")
        rec["rvol"] = float(rv.iloc[0]) if len(rv) and not pd.isna(rv.iloc[0]) else np.nan

        # reactions
        anchor_t = sched - pd.Timedelta(minutes=1)
        settle_t = sched.tz_convert("America/New_York").replace(hour=14, minute=30)
        settle_t = pd.Timestamp(settle_t).tz_convert("UTC")
        for name, s in instr.items():
            pre = _smooth_at(s, anchor_t, "pre")
            if pre is None:
                continue
            is_price = name in PRICE_INSTR
            for h in HORIZONS:
                post = _smooth_at(s, sched + pd.Timedelta(minutes=h), "post")
                if post is None:
                    continue
                rec[f"react_{name}_{h}"] = (post / pre - 1) * 100 if is_price else (post - pre)
            post_s = _smooth_at(s, settle_t, "post")
            if post_s is not None:
                rec[f"react_{name}_settle"] = (post_s / pre - 1) * 100 if is_price else (post_s - pre)
        rows.append(rec)

    panel = pd.DataFrame(rows).set_index("release_utc").sort_index()

    # vol regime as terciles of trailing realised vol over the panel
    if "rvol" in panel and panel["rvol"].notna().sum() > 6:
        panel["vol_regime"] = pd.qcut(panel["rvol"], 3, labels=["LOW", "MID", "HIGH"])
    else:
        panel["vol_regime"] = "MID"

    try:
        panel.to_parquet(_PANEL_PARQUET)
    except Exception as exc:
        log.warning("could not cache event panel: %s", exc)
    return panel


# ── regressions ──────────────────────────────────────────────────────────────
def _ols(x: np.ndarray, y: np.ndarray) -> dict | None:
    m = np.isfinite(x) & np.isfinite(y)
    x, y = x[m], y[m]
    n = len(x)
    if n < 6 or np.std(x) == 0:
        return None
    sx, sy = x - x.mean(), y - y.mean()
    slope = float((sx * sy).sum() / (sx ** 2).sum())
    intercept = float(y.mean() - slope * x.mean())
    yhat = intercept + slope * x
    ss_res = float(((y - yhat) ** 2).sum())
    ss_tot = float((sy ** 2).sum())
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0
    # slope std error + t-stat
    se = float(np.sqrt(ss_res / (n - 2) / (sx ** 2).sum())) if n > 2 else np.nan
    t = slope / se if se and se > 0 else np.nan
    return {"slope": round(slope, 4), "r2": round(r2, 3), "n": n,
            "t": round(t, 2) if np.isfinite(t) else None,
            "corr": round(float(np.corrcoef(x, y)[0, 1]), 3)}


def conditional_betas(panel: pd.DataFrame, horizon: int | str = 30) -> dict:
    """Surprise→reaction beta per instrument at one horizon, overall + by curve regime."""
    out: dict = {}
    x = panel["surprise_z"].values
    for instr in INSTRUMENTS:
        col = f"react_{instr}_{horizon}"
        if col not in panel:
            continue
        entry = {"overall": _ols(x, panel[col].values)}
        for reg in ("BACK", "CONTANGO"):
            sub = panel[panel["curve"] == reg]
            entry[reg] = _ols(sub["surprise_z"].values, sub[col].values)
        out[instr] = entry
    return out


def when_it_mattered(panel: pd.DataFrame, instr: str = "wti_flat", horizon: int | str = 30) -> pd.DataFrame:
    """
    The meta-result: surprise→reaction explanatory power inside each regime bucket.
    Returns a tidy table (bucket_type, bucket, slope, r2, t, n) — high R² where
    inventory mattered, ≈0 where it was noise.
    """
    col = f"react_{instr}_{horizon}"
    rows = []
    rows.append(("ALL", "all", _ols(panel["surprise_z"].values, panel[col].values)))
    for btype, vals in [("curve", ["BACK", "CONTANGO"]),
                        ("season", ["winter", "maintenance", "driving", "autumn"]),
                        ("vol_regime", ["LOW", "MID", "HIGH"]),
                        ("confirmed", [True, False])]:
        for v in vals:
            sub = panel[panel[btype] == v]
            if len(sub) >= 6:
                rows.append((btype, str(v), _ols(sub["surprise_z"].values, sub[col].values)))
    # coherence bucket: does the reaction follow quality-of-draw vs headline?
    out = []
    for btype, bucket, res in rows:
        if res is None:
            continue
        out.append({"bucket_type": btype, "bucket": bucket,
                    "slope": res["slope"], "r2": res["r2"], "t": res["t"], "n": res["n"]})
    return pd.DataFrame(out)


def attribution(panel: pd.DataFrame, horizon: int | str = 30) -> pd.DataFrame:
    """
    Spread attribution: which instrument responds most to which *type* of surprise.
    Rows = surprise drivers (headline, Cushing, demand/quality); cols = instruments;
    cells = regression slope (reaction per 1σ of that driver) with its R².
    """
    drivers = {
        "headline_surprise": "surprise_z",
        "cushing_surprise": "cushing_surprise_z",
        "demand_surprise": "demand_z",
        "quality_of_draw": "quality_of_draw",
        "export_surprise": "export_z",
    }
    rows = []
    for dname, dcol in drivers.items():
        if dcol not in panel:
            continue
        row = {"driver": dname}
        for instr in INSTRUMENTS:
            col = f"react_{instr}_{horizon}"
            if col not in panel:
                continue
            res = _ols(panel[dcol].values, panel[col].values)
            row[instr] = res["slope"] if res else np.nan
            row[f"{instr}_r2"] = res["r2"] if res else np.nan
        rows.append(row)
    return pd.DataFrame(rows).set_index("driver")


def decay_profile(panel: pd.DataFrame, instr: str = "wti_flat") -> dict:
    """
    Knee-jerk vs sustained: mean |reaction| at each horizon + the fraction of the
    peak intraday move retained at settle (the tradeable, persistent component).
    Computed on the surprise-aligned reaction (sign-flipped so a bullish surprise
    is a positive number) to avoid cancellation.
    """
    # align sign: bullish surprise (z<0) should be +; multiply reaction by -sign(z)
    sgn = -np.sign(panel["surprise_z"].values)
    prof = {}
    for h in HORIZONS + ["settle"]:
        col = f"react_{instr}_{h}"
        if col not in panel:
            continue
        aligned = panel[col].values * sgn
        prof[str(h)] = {
            "mean_aligned": round(float(np.nanmean(aligned)), 4),
            "mean_abs": round(float(np.nanmean(np.abs(panel[col].values))), 4),
            "hit_rate": round(float(np.nanmean(aligned > 0)), 3),
        }
    # retention = settle aligned / peak intraday aligned
    peak = max((prof[str(h)]["mean_aligned"] for h in HORIZONS if str(h) in prof), default=np.nan)
    settle = prof.get("settle", {}).get("mean_aligned", np.nan)
    prof["retention_settle_vs_peak"] = round(settle / peak, 3) if peak and np.isfinite(peak) and peak != 0 else None
    return prof


# ── standalone ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    pd.set_option("display.width", 170)
    pd.set_option("display.max_columns", 40)

    print("Building event panel (this hits the 1-min lake per release)…")
    panel = build_panel(force_refresh="--refresh" in sys.argv)
    print(f"\nReleases in panel: {len(panel)}  "
          f"({panel.index.min().date()} .. {panel.index.max().date()})  "
          f"confirmed spike: {int(panel['confirmed'].sum())}/{len(panel)}")

    print("\n=== Conditional betas: surprise_z → reaction @ 30 min ===")
    cb = conditional_betas(panel, 30)
    for instr, e in cb.items():
        o = e["overall"]; ba = e.get("BACK"); co = e.get("CONTANGO")
        def f(r): return f"β={r['slope']:+.3f} r²={r['r2']:.2f} (n={r['n']})" if r else "n/a"
        print(f"  {instr:11s}  overall {f(o)}   BACK {f(ba)}   CONTANGO {f(co)}")

    print("\n=== WHEN IT MATTERED: surprise→WTI-flat @30m R² by regime ===")
    print(when_it_mattered(panel, "wti_flat", 30).to_string(index=False))

    print("\n=== SPREAD ATTRIBUTION: reaction per 1σ driver @30m ===")
    att = attribution(panel, 30)
    show_cols = [c for c in att.columns if not c.endswith("_r2")]
    print(att[show_cols].round(3).to_string())

    print("\n=== DECAY: WTI flat (surprise-aligned) ===")
    dp = decay_profile(panel, "wti_flat")
    for k, v in dp.items():
        if isinstance(v, dict):
            print(f"  +{k:>6} : aligned {v['mean_aligned']:+.3f}%  |move| {v['mean_abs']:.3f}%  hit {v['hit_rate']:.0%}")
        else:
            print(f"  retention(settle/peak) = {v}")
