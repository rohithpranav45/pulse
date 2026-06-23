"""
L0 + L2 — the EIA Weekly Petroleum Status Report, as a surprise.

This module turns the raw weekly report into the two things the framework needs:

  L0  the SURPRISE          actual change vs the *right* expectation, z-scored.
                            "draw = bullish" is wrong; the market trades the
                            surprise vs consensus. We proxy consensus with a
                            seasonally-de-trended baseline (the systematic part
                            analysts track) and leave a one-line hook to drop a
                            real consensus series in later. Headline series is
                            COMMERCIAL crude ex-SPR (WCESTUS1) — the number the
                            market actually forecasts, *not* total-incl-SPR
                            (WCRSTUS1), which the legacy fetcher used.

  L2  the QUALITY-OF-DRAW   the whole report, not the headline. A crude draw
                            driven by an export spike or a refinery ramp is a
                            different animal from a demand-led draw. We decompose
                            the print into a surprise vector (Cushing, runs,
                            imports, exports, products-supplied / implied demand)
                            and reconstruct EIA's supply-balance ADJUSTMENT
                            factor ourselves — a large adjustment means the report
                            doesn't reconcile, so the reaction should be faded.

Public API
----------
  fetch_report_history(weeks=560, force_refresh=False) -> pd.DataFrame
      Date-indexed (report week-ending Friday) levels for every tracked series.
  weekly_frame(force_refresh=False) -> pd.DataFrame
      Levels + weekly changes + reconstructed adjustment + implied demand.
  surprise_series(series="crude_ex_spr", method="seasonal") -> pd.DataFrame
      actual_change / expected_change / surprise / surprise_z / bullish.
  decomposition(force_refresh=False) -> pd.DataFrame
      Per-week surprise vector across the report + a quality-of-draw score.

Run standalone:  python -m backend.research.inventory_impact.eia_report
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger("pulse.inventory_impact.eia_report")

_CACHE = Path(__file__).parent.parent.parent / "data" / "research" / "inventory_impact"
_CACHE.mkdir(parents=True, exist_ok=True)
_REPORT_PARQUET = _CACHE / "eia_report_history.parquet"

_EIA_KEY = os.getenv("EIA_API_KEY")
_SNDW = "https://api.eia.gov/v2/petroleum/sum/sndw/data/"

# ── The full report, as series IDs (all verified live against EIA v2) ────────
# kind: "stock" levels are MBBL; "flow" levels are MBBL/D; "pct" is utilisation.
SERIES: dict[str, tuple[str, str]] = {
    # --- stocks (MBBL) ---
    "crude_ex_spr":      ("WCESTUS1", "stock"),  # << market headline (commercial)
    "crude_incl_spr":    ("WCRSTUS1", "stock"),  # total incl SPR (legacy headline)
    "spr":               ("WCSSTUS1", "stock"),
    "cushing":           ("W_EPC0_SAX_YCUOK_MBBL", "stock"),  # WTI delivery point
    "gasoline":          ("WGTSTUS1", "stock"),
    "distillate":        ("WDISTUS1", "stock"),
    # --- flows (MBBL/D) ---
    "refinery_util":     ("WPULEUS3", "pct"),
    "refinery_input":    ("WCRRIUS2", "flow"),
    "production":        ("WCRFPUS2", "flow"),
    "imports":           ("WCEIMUS2", "flow"),
    "exports":           ("WCREXUS2", "flow"),
    "net_imports":       ("WCRNTUS2", "flow"),
    "products_supplied": ("WRPUPUS2", "flow"),  # total implied demand
    "gas_supplied":      ("WGFUPUS2", "flow"),
    "dist_supplied":     ("WDIUPUS2", "flow"),
    "jet_supplied":      ("WKJUPUS2", "flow"),
}

STOCK_SERIES = [k for k, (_, kind) in SERIES.items() if kind == "stock"]
FLOW_SERIES = [k for k, (_, kind) in SERIES.items() if kind in ("flow", "pct")]


# ── fetch ────────────────────────────────────────────────────────────────────
def _fetch_one(series_id: str, length: int) -> pd.Series:
    """Pull one weekly series from EIA v2, return a date-indexed float Series."""
    params = {
        "api_key": _EIA_KEY,
        "frequency": "weekly",
        "data[0]": "value",
        "facets[series][]": series_id,
        "length": length,
        "sort[0][column]": "period",
        "sort[0][direction]": "desc",
    }
    r = requests.get(_SNDW, params=params, timeout=30)
    r.raise_for_status()
    rows = r.json().get("response", {}).get("data", [])
    rec = {}
    for row in rows:
        try:
            rec[pd.Timestamp(row["period"])] = float(row["value"])
        except (TypeError, ValueError, KeyError):
            continue
    return pd.Series(rec, name=series_id).sort_index()


def fetch_report_history(weeks: int = 560, force_refresh: bool = False) -> pd.DataFrame:
    """
    Levels for every tracked series, indexed by report week-ending Friday.
    Cached to parquet; pass force_refresh=True (or delete the cache) to re-pull.
    Falls back to the cache if EIA is unreachable.
    """
    if not force_refresh and _REPORT_PARQUET.exists():
        return pd.read_parquet(_REPORT_PARQUET)

    if not _EIA_KEY:
        if _REPORT_PARQUET.exists():
            log.warning("EIA_API_KEY missing — serving cached report history")
            return pd.read_parquet(_REPORT_PARQUET)
        raise EnvironmentError("EIA_API_KEY not set and no cached report history")

    cols = {}
    for name, (sid, _) in SERIES.items():
        try:
            cols[name] = _fetch_one(sid, weeks)
            log.info("fetched %s (%s): %d obs", name, sid, len(cols[name]))
        except Exception as exc:  # one bad series shouldn't sink the report
            log.warning("series %s (%s) failed: %s", name, sid, exc)

    if not cols:
        if _REPORT_PARQUET.exists():
            return pd.read_parquet(_REPORT_PARQUET)
        raise RuntimeError("EIA report fetch returned nothing")

    df = pd.DataFrame(cols).sort_index()
    df.index.name = "week_ending"
    try:
        df.to_parquet(_REPORT_PARQUET)
    except Exception as exc:
        log.warning("could not cache report history: %s", exc)
    return df


# ── derive: changes + balance reconstruction ─────────────────────────────────
def weekly_frame(force_refresh: bool = False) -> pd.DataFrame:
    """
    Report levels + weekly changes + the reconstructed crude supply balance.

    Stock series get a `*_chg` column (this week minus last, MBBL).
    Flows are kept as levels (MBBL/D) plus a `*_chg` week-on-week delta.

    Reconstructed (the Pillar-2 moves):
      implied_demand   = products_supplied (MBBL/D) — total product demand proxy
      adjustment       = EIA's unaccounted-for crude (MBBL/D), backed out of the
                         weekly crude supply/disposition identity:
                            Prod + (Imp - Exp) + Adj = RefInput + dStock/7
                         => Adj = RefInput + dStock_total/7 - Prod - Imp + Exp
                         (dStock_total uses crude incl SPR — EIA's balance basis).
                         A large |adjustment| ⇒ the report doesn't reconcile.
    """
    df = fetch_report_history(force_refresh=force_refresh).copy()

    for s in STOCK_SERIES:
        if s in df:
            df[f"{s}_chg"] = df[s].diff()
    for s in FLOW_SERIES:
        if s in df:
            df[f"{s}_chg"] = df[s].diff()

    # implied demand = total products supplied (MBBL/D)
    if "products_supplied" in df:
        df["implied_demand"] = df["products_supplied"]

    # reconstruct EIA's crude adjustment (unaccounted-for), MBBL/D
    need = {"production", "imports", "exports", "refinery_input", "crude_incl_spr"}
    if need.issubset(df.columns):
        dstock_per_day = df["crude_incl_spr"].diff() / 7.0
        df["adjustment"] = (
            df["refinery_input"] + dstock_per_day
            - df["production"] - df["imports"] + df["exports"]
        )
    return df


# ── L0: the surprise ─────────────────────────────────────────────────────────
def _seasonal_expected_change(chg: pd.Series, min_years: int = 3) -> pd.Series:
    """
    Expected weekly change = average change for the same ISO week over the prior
    5 calendar years (excluding the current observation's year, so no leakage).
    This is the *systematic* seasonal pattern consensus tracks. Falls back to a
    trailing 4-week mean where seasonal history is too thin (early sample).
    """
    chg = chg.dropna()
    iso_week = chg.index.isocalendar().week.values
    years = chg.index.year.values
    out = pd.Series(index=chg.index, dtype=float)
    vals = chg.values
    for i, ts in enumerate(chg.index):
        wk, yr = iso_week[i], years[i]
        mask = (iso_week == wk) & (years < yr) & (years >= yr - 5)
        sample = vals[mask]
        if len(sample) >= min_years:
            out.iloc[i] = float(np.mean(sample))
        else:
            # fallback: trailing 4-week mean of changes (still causal)
            out.iloc[i] = float(np.mean(vals[max(0, i - 4):i])) if i >= 1 else np.nan
    return out


def nowcast_expected_change(z_window_min: int = 104) -> pd.Series:
    """
    Model-consensus expectation of this week's crude change, using ONLY information
    available before the release (prior-report fundamentals + seasonality +
    momentum). This is a far better proxy for analyst consensus than a 4-week MA:
    both are forecasts of the same number from the same pre-release info set.

    Expanding-window OLS (refit each week on all prior weeks → no look-ahead):
        change_t ~ seasonal_t + change_{t-1} + change_{t-2}
                   + d_refinery_util_{t-1} + d_net_imports_{t-1}
                   + sin/cos(week)
    Returns the fitted nowcast (MBBL). Weeks before `z_window_min` history are NaN.
    """
    wf = weekly_frame()
    chg = wf["crude_ex_spr"].diff()
    feat = pd.DataFrame(index=wf.index)
    feat["seasonal"] = _seasonal_expected_change(chg)
    feat["lag1"] = chg.shift(1)
    feat["lag2"] = chg.shift(2)
    feat["d_runs"] = wf["refinery_util"].diff().shift(1) if "refinery_util" in wf else 0.0
    feat["d_netimp"] = wf["net_imports"].diff().shift(1) if "net_imports" in wf else 0.0
    wk = wf.index.isocalendar().week.values.astype(float)
    feat["sin"] = np.sin(2 * np.pi * wk / 52.0)
    feat["cos"] = np.cos(2 * np.pi * wk / 52.0)
    feat = feat.fillna(0.0)
    X = feat.values
    y = chg.values

    out = pd.Series(index=wf.index, dtype=float)
    for i in range(len(wf)):
        if i < z_window_min:
            continue
        m = np.isfinite(y[:i])
        Xt, yt = X[:i][m], y[:i][m]
        if len(yt) < 30:
            continue
        Xt1 = np.column_stack([np.ones(len(Xt)), Xt])
        try:
            beta, *_ = np.linalg.lstsq(Xt1, yt, rcond=None)
            out.iloc[i] = float(np.r_[1.0, X[i]] @ beta)
        except Exception:
            continue
    return out


def surprise_series(
    series: str = "crude_ex_spr",
    method: str = "seasonal",
    consensus: pd.Series | None = None,
    z_window: int = 104,
) -> pd.DataFrame:
    """
    The surprise series for one report line.

    surprise = actual_change - expected_change   (MBBL, signed)
      < 0  => tighter than expected  => BULLISH surprise
      > 0  => looser  than expected  => BEARISH surprise

    expected:
      method="seasonal"   5yr same-ISO-week seasonal baseline (proxy consensus).
      method="ma4"        trailing 4-week mean of changes (naive floor).
      consensus=<Series>  if given, used as expected directly (real consensus
                          drop-in — actual - consensus).

    surprise_z = surprise / trailing std(surprise) — standardised so a "1σ
    surprise" is comparable across calm and volatile periods.
    """
    wf = weekly_frame()
    if series not in wf:
        raise KeyError(f"unknown series '{series}'")
    actual_change = wf[series].diff()

    if consensus is not None:
        expected = consensus.reindex(actual_change.index)
    elif method == "seasonal":
        expected = _seasonal_expected_change(actual_change)
    elif method == "nowcast":
        expected = nowcast_expected_change()
    elif method == "ma4":
        expected = actual_change.shift(1).rolling(4).mean()
    else:
        raise ValueError(f"unknown method '{method}'")

    surprise = actual_change - expected
    z = surprise / surprise.rolling(z_window, min_periods=20).std()

    out = pd.DataFrame({
        "level": wf[series],
        "actual_change": actual_change,
        "expected_change": expected,
        "surprise": surprise,
        "surprise_z": z,
        "bullish": surprise < 0,
    })
    return out


# ── L2: decomposition / quality-of-draw ──────────────────────────────────────
def decomposition(force_refresh: bool = False) -> pd.DataFrame:
    """
    Per-week surprise vector across the report + a quality-of-draw score.

    The quality score answers: is a crude draw *demand-led* (bullish for real)
    or *mechanical* (an export surge / import drop — weaker)? It is the signed,
    standardised sum of the components that make a draw "high quality":

        +  crude drew more than expected         (-crude_surprise_z)
        +  products drew / implied demand strong  (+demand_z)
        +  refinery runs ramped                    (+runs_z)
        +  small, well-behaved adjustment          (-|adjustment_z|)
        -  draw driven by an export spike          (-export_contribution_z)

    A high score = a genuinely tight, demand-led report; a low/negative score on
    a headline draw = a draw to fade. The headline and the quality score can
    point opposite ways — that divergence is the framework's sharpest read.
    """
    wf = weekly_frame(force_refresh=force_refresh)

    # component surprises (seasonal expectation on each line)
    comps = {}
    for s in ["crude_ex_spr", "cushing", "gasoline", "distillate"]:
        if s in wf:
            comps[f"{s}_surprise"] = surprise_series(s)["surprise"]
            comps[f"{s}_surprise_z"] = surprise_series(s)["surprise_z"]

    out = pd.DataFrame(index=wf.index)
    for k, v in comps.items():
        out[k] = v

    # demand & runs surprises (flows: surprise vs seasonal of the *level*)
    def _flow_z(col: str) -> pd.Series:
        if col not in wf:
            return pd.Series(index=wf.index, dtype=float)
        chg = wf[col].diff()
        exp = _seasonal_expected_change(chg)
        sup = chg - exp
        return sup / sup.rolling(104, min_periods=20).std()

    out["demand_z"] = _flow_z("implied_demand")
    out["runs_z"] = _flow_z("refinery_util")
    out["export_z"] = _flow_z("exports")
    out["import_z"] = _flow_z("imports")

    # adjustment standardised (coherence)
    if "adjustment" in wf:
        adj = wf["adjustment"]
        out["adjustment"] = adj
        out["adjustment_z"] = (adj - adj.rolling(104, min_periods=20).mean()) / \
            adj.rolling(104, min_periods=20).std()

    # quality-of-draw composite (signed so + = bullish/demand-led tight report)
    q = pd.Series(0.0, index=wf.index)
    q = q.add(-out.get("crude_ex_spr_surprise_z", 0), fill_value=0)   # bigger draw than expected
    q = q.add(out.get("demand_z", 0), fill_value=0)                   # strong implied demand
    q = q.add(out.get("runs_z", 0), fill_value=0)                     # refinery ramp
    q = q.add(-out.get("export_z", 0), fill_value=0)                  # not an export-driven draw
    if "adjustment_z" in out:
        q = q.add(-out["adjustment_z"].abs(), fill_value=0)          # report reconciles
    out["quality_of_draw"] = q

    return out


# ── standalone ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    pd.set_option("display.width", 160)
    pd.set_option("display.max_columns", 30)

    wf = weekly_frame()
    print(f"\nReport history: {wf.index.min().date()} .. {wf.index.max().date()}  ({len(wf)} weeks)")
    print("Series tracked:", ", ".join(SERIES))

    sp = surprise_series("crude_ex_spr")
    print("\n=== Crude (ex-SPR) surprise — last 8 releases ===")
    show = sp.dropna(subset=["surprise"]).tail(8)
    for ts, r in show.iterrows():
        tone = "BULL" if r["bullish"] else "BEAR"
        print(f"  {ts.date()}  actual {r['actual_change']:+7.0f}  "
              f"expected {r['expected_change']:+7.0f}  surprise {r['surprise']:+7.0f}  "
              f"z {r['surprise_z']:+5.2f}  [{tone}]")

    dec = decomposition()
    print("\n=== Quality-of-draw — last 6 releases ===")
    cols = ["crude_ex_spr_surprise_z", "demand_z", "runs_z", "export_z", "adjustment", "quality_of_draw"]
    print(dec[cols].dropna(how="all").tail(6).round(2).to_string())
