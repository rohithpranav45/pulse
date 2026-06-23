"""
THE CENTERPIECE — "when did inventories matter, and when didn't they?"

The intraday event study (event_study.py) shows that in the 2021-26 sample the
crude release barely moves WTI: near-zero directional beta, no volatility lift
over a placebo. That is only half the answer. This module supplies the other
half — and the punchline — by measuring the surprise→price relationship on the
full **2015-2026** daily history (535 releases) and showing that its strength is
**conditional on the inventory / curve regime**:

    surprise_z  ->  Brent release-day return (%)

        HIGH stocks (glut)  :  beta -1.03 / bbl-σ   t -3.4   R² 0.17   (it MATTERS)
        AVG  stocks         :  beta -0.18           t -0.9   R² 0.01
        LOW  stocks (tight) :  beta -0.02           t -0.2   R² 0.00   (it's NOISE)
        contango front      :  beta -0.43           t -2.1
        backwardated front  :  beta -0.06           t -0.5

Economic reading: in a glut/contango regime the market is fixated on whether
stocks keep building, so the weekly print drives price. In a tight/backwardated
regime prompt scarcity, OPEC spare capacity and geopolitics set the price and the
inventory wiggle is noise. The sign is correct (a bearish surprise lowers price)
only where the regime says it should be.

This is what conditions the live call: today's regime is **LOW stocks /
backwardation**, the very regime in which inventory surprises historically did
**not** move flat price — so the framework's headline read on any given week is
low-conviction-on-flat-price unless the surprise is extreme or the regime shifts.

Public API
----------
  build_daily_panel(method="seasonal", force_refresh=False) -> pd.DataFrame
  conditional_table(panel) -> pd.DataFrame    the regime-beta table above
  current_regime() -> dict                    today's inventory/curve regime + the
                                              historical beta that applies to it

Run standalone:  python -m backend.research.inventory_impact.regime_conditioning
"""

from __future__ import annotations

import json
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
from research.inventory_impact.release_calendar import release_datetime  # noqa: E402

log = logging.getLogger("pulse.inventory_impact.regime_conditioning")

_CACHE = Path(__file__).parent.parent.parent / "data" / "research" / "inventory_impact"
_CACHE.mkdir(parents=True, exist_ok=True)
_INV_HISTORY = Path(__file__).parent.parent.parent / "data" / "research" / "crude_stocks_history.parquet"


def _ols(x: np.ndarray, y: np.ndarray) -> dict | None:
    m = np.isfinite(x) & np.isfinite(y)
    x, y = x[m], y[m]
    n = len(x)
    if n < 10 or np.std(x) == 0:
        return None
    sx, sy = x - x.mean(), y - y.mean()
    b = float((sx * sy).sum() / (sx ** 2).sum())
    yhat = y.mean() + b * (x - x.mean())
    ss_res = float(((y - yhat) ** 2).sum())
    ss_tot = float((sy ** 2).sum())
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0
    se = float(np.sqrt(ss_res / (n - 2) / (sx ** 2).sum()))
    t = b / se if se > 0 else np.nan
    return {"beta": round(b, 4), "t": round(t, 2), "r2": round(r2, 3),
            "n": n, "corr": round(float(np.corrcoef(x, y)[0, 1]), 3)}


def _brent_daily() -> pd.DataFrame:
    con = dl.duckdb_conn()
    b = con.execute("SELECT date, c1, c2 FROM brent_settlements_c1_to_c31 ORDER BY date").df()
    b["date"] = pd.to_datetime(b["date"])
    b = b.set_index("date")
    b["ret"] = b["c1"].pct_change() * 100.0          # daily close-to-close %
    b["m1_m2"] = b["c1"] - b["c2"]
    b["d_m1_m2"] = b["m1_m2"].diff()                  # daily change in front spread
    b["front_contango"] = b["c1"] < b["c2"]
    return b


def build_daily_panel(method: str = "seasonal", force_refresh: bool = False) -> pd.DataFrame:
    """
    One row per EIA crude release 2015-2026 with:
      surprise_z      the standardised surprise (method = seasonal | nowcast)
      ret             Brent front close-to-close return on the release trading day (%)
      d_m1_m2         change in Brent M1-M2 that day ($/bbl)
      front_contango  was the Brent front in contango at the settle
      inv_bucket      HIGH / AVG / LOW  (stocks vs 5yr seasonal, from the regime axis)
      inv_pct         stocks vs 5yr seasonal (%)
      era             2015-2020 | 2021-2026
    """
    cache = _CACHE / f"daily_panel_{method}.parquet"
    if not force_refresh and cache.exists():
        return pd.read_parquet(cache)

    sp = eia_report.surprise_series("crude_ex_spr", method)
    b = _brent_daily()
    inv = pd.read_parquet(_INV_HISTORY) if _INV_HISTORY.exists() else None

    rows = []
    for we in sp.index:
        z = sp.loc[we, "surprise_z"]
        if pd.isna(z):
            continue
        rel = release_datetime(we).tz_convert("America/New_York").normalize().tz_localize(None)
        idx = b.index[b.index >= rel]
        if len(idx) == 0:
            continue
        d0 = idx[0]
        if (d0 - rel).days > 4:   # no nearby trading day → skip
            continue
        bucket, pct = "UNK", np.nan
        if inv is not None:
            ib = inv[inv.index <= we]
            if len(ib):
                bucket = ib["inv_bucket"].iloc[-1]
                pct = ib["vs_5yr_pct"].iloc[-1]
        rows.append({
            "release_day": d0,
            "surprise_z": float(z),
            "surprise": float(sp.loc[we, "surprise"]),
            "actual_change": float(sp.loc[we, "actual_change"]),
            "ret": float(b.loc[d0, "ret"]),
            "d_m1_m2": float(b.loc[d0, "d_m1_m2"]),
            "front_contango": bool(b.loc[d0, "front_contango"]),
            "inv_bucket": bucket,
            "inv_pct": float(pct) if pd.notna(pct) else np.nan,
        })
    panel = pd.DataFrame(rows).set_index("release_day").sort_index()
    panel["era"] = np.where(panel.index < "2021-01-01", "2015-2020", "2021-2026")
    try:
        panel.to_parquet(cache)
    except Exception as exc:
        log.warning("could not cache daily panel: %s", exc)
    return panel


def conditional_table(panel: pd.DataFrame, target: str = "ret") -> pd.DataFrame:
    """The regime-beta table: surprise_z → `target`, sliced by regime conditioner."""
    rows = []

    def add(label_type, label, sub):
        res = _ols(sub["surprise_z"].values, sub[target].values)
        if res:
            rows.append({"conditioner": label_type, "regime": label, **res})

    add("ALL", "all releases", panel)
    add("curve", "contango front", panel[panel["front_contango"]])
    add("curve", "backwardated front", panel[~panel["front_contango"]])
    for bk in ["HIGH", "AVG", "LOW"]:
        add("inventory", f"{bk} stocks", panel[panel["inv_bucket"] == bk])
    add("inventory", "above 5yr (glut)", panel[panel["inv_pct"] > 0])
    add("inventory", "below 5yr (tight)", panel[panel["inv_pct"] <= 0])
    for era in ["2015-2020", "2021-2026"]:
        add("era", era, panel[panel["era"] == era])
    return pd.DataFrame(rows)


def _fresh_inventory_state() -> tuple[str, float, str]:
    """
    Today's inventory bucket from the *fresh* EIA report (not the stale
    crude_stocks_history cache, which can lag the live report by weeks). Uses
    total crude incl-SPR (WCRSTUS1 basis) vs a 5yr same-ISO-week seasonal so the
    bucket is consistent with the regime axis. Returns (bucket, vs_5yr_pct, asof).
    """
    wf = eia_report.weekly_frame()
    s = wf["crude_incl_spr"].dropna()
    if len(s) == 0:
        return "UNK", np.nan, None
    iso = s.index.isocalendar().week.values
    yrs = s.index.year.values
    vals = s.values
    i = len(s) - 1
    wk, yr = iso[i], yrs[i]
    mask = (iso == wk) & (yrs < yr) & (yrs >= yr - 5)
    sample = vals[mask]
    if len(sample) < 3:
        return "UNK", np.nan, str(s.index[i].date())
    seasonal = float(np.mean(sample))
    pct = (vals[i] - seasonal) / seasonal * 100.0
    bucket = "HIGH" if pct > 4 else "LOW" if pct < -4 else "AVG"
    return bucket, float(pct), str(s.index[i].date())


def current_regime() -> dict:
    """
    Classify today's inventory/curve regime and return the historical beta that
    applies to it — i.e. how much price has historically moved per 1σ surprise in
    *this* regime. This is what sets the live call's conviction.

    Reads the **fresh** EIA report for the inventory bucket (the crude_stocks
    cache can lag the live report by weeks — that staleness previously made the
    gate read 3-week-old inventory state).
    """
    bucket, pct, asof = _fresh_inventory_state()

    b = _brent_daily()
    contango = bool(b["front_contango"].iloc[-1])

    panel = build_daily_panel("seasonal")
    glut = panel[panel["inv_pct"] > 0]
    tight = panel[panel["inv_pct"] <= 0]
    applicable = _ols((glut if pct > 0 else tight)["surprise_z"].values,
                      (glut if pct > 0 else tight)["ret"].values)
    bucket_beta = _ols(panel[panel["inv_bucket"] == bucket]["surprise_z"].values,
                       panel[panel["inv_bucket"] == bucket]["ret"].values)

    return {
        "as_of": asof,
        "inv_bucket": bucket,
        "inv_vs_5yr_pct": round(pct, 1) if pd.notna(pct) else None,
        "front_contango": contango,
        "regime_label": f"{bucket} stocks / {'contango' if contango else 'backwardation'}",
        "applicable_beta": applicable,        # by glut/tight split
        "bucket_beta": bucket_beta,           # by HIGH/AVG/LOW bucket
        "sensitivity": ("HIGH" if (pct is not None and pct > 4 and contango)
                        else "LOW" if (pct is not None and pct < -4 and not contango)
                        else "MEDIUM"),
    }


def to_results(method: str = "seasonal") -> dict:
    panel = build_daily_panel(method)
    tbl = conditional_table(panel, "ret")
    tbl_spread = conditional_table(panel, "d_m1_m2")
    return {
        "n_releases": int(len(panel)),
        "span": [str(panel.index.min().date()), str(panel.index.max().date())],
        "method": method,
        "conditional_flat": tbl.to_dict("records"),
        "conditional_m1m2": tbl_spread.to_dict("records"),
        "current_regime": current_regime(),
    }


if __name__ == "__main__":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    pd.set_option("display.width", 160)

    panel = build_daily_panel("seasonal", force_refresh="--refresh" in sys.argv)
    print(f"\nDaily reaction panel: {len(panel)} releases  "
          f"({panel.index.min().date()} .. {panel.index.max().date()})\n")

    print("=== WHEN INVENTORIES MATTERED — surprise_z → Brent release-day return (%) ===")
    tbl = conditional_table(panel, "ret")
    print(tbl.to_string(index=False))

    print("\n=== Same, on the Brent M1-M2 daily change ($/bbl) — note: ~null everywhere ===")
    print(conditional_table(panel, "d_m1_m2").to_string(index=False))

    cr = current_regime()
    print("\n=== CURRENT REGIME (sets live conviction) ===")
    print(f"  as of {cr['as_of']}: {cr['regime_label']}  (stocks {cr['inv_vs_5yr_pct']:+}% vs 5yr)")
    print(f"  inventory sensitivity: {cr['sensitivity']}")
    if cr["applicable_beta"]:
        ab = cr["applicable_beta"]
        print(f"  historical beta in this regime: {ab['beta']:+.3f}%/σ  (t={ab['t']}, R²={ab['r2']}, n={ab['n']})")
        print("  => a 1σ surprise has historically moved Brent "
              f"{abs(ab['beta']):.2f}% on the day in this regime "
              f"({'SIGNIFICANT' if abs(ab['t'])>=2 else 'NOT significant — inventory is noise here'}).")

    # persist results.json
    out = to_results("seasonal")
    (_CACHE / "regime_conditioning_results.json").write_text(json.dumps(out, indent=2))
    print(f"\nresults -> {_CACHE / 'regime_conditioning_results.json'}")
