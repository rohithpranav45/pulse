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
from functools import lru_cache
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

# The default expectation for surprise = actual − expected. "consensus" reads the
# real analyst consensus (investing.com history, ×1000 → MBBL) and falls back to
# the seasonal proxy per-week where no consensus row exists. This is what the desk
# sees by default — "surprise vs real consensus", not the seasonal proxy.
DEFAULT_SURPRISE_METHOD = "consensus"

# Real analyst consensus + the API leading indicator, staged 2026-06-25 (validated
# in CLAUDE.md §1). All four are actual/forecast(=consensus)/previous in *millions*
# of bbl → ×1000 to MBBL (thousands). release_date is %d-%m-%Y. Empty-forecast
# split rows (the mis-dated :29/:25 rows) are dropped by the loader.
_CONSENSUS_FILES = {
    "crude_ex_spr": "eia_consensus_history.csv",
    "gasoline":     "eia_consensus_gasoline.csv",
    "distillate":   "eia_consensus_distillate.csv",
}
_API_CRUDE_FILE = "api_crude_history.csv"


def _parse_mbbl(s) -> float:
    """'-3.900M' (millions) → -3900.0 MBBL (thousands). Blank → NaN."""
    s = str(s).strip().strip('"').replace("M", "").replace(",", "")
    if s in ("", "nan", "None", "-"):
        return np.nan
    try:
        return float(s) * 1000.0
    except ValueError:
        return np.nan


def _prev_friday(d: pd.Timestamp) -> pd.Timestamp:
    """The week-ending Friday for a release dated `d`. The EIA prints Wed (Thu on
    holidays) for the week ending the *preceding* Friday; the Tue API likewise.
    Maps any release weekday back to the most recent Friday strictly before it."""
    off = (d.weekday() - 4) % 7      # Friday = weekday 4
    return d - pd.Timedelta(days=7 if off == 0 else off)


@lru_cache(maxsize=8)
def _load_consensus_csv(series: str) -> pd.DataFrame:
    """
    Real analyst consensus for `series`, indexed by week-ending Friday with columns
    {consensus, actual, release_date} in MBBL. Empty-forecast split rows dropped;
    de-duped to the latest release per week (a holiday-shifted stray collapses onto
    the same Friday — keep the genuine Wed/Thu print). Empty DataFrame if no file.

    Verified against the report parquet: csv actual matches the parquet actual_change
    to ~0 MBBL median error for 99%+ of weeks, so the prev-Friday alignment is sound.
    """
    fname = _CONSENSUS_FILES.get(series)
    if not fname:
        return pd.DataFrame(columns=["consensus", "actual", "release_date"])
    path = _CACHE / fname
    if not path.exists():
        log.warning("consensus file missing for %s: %s", series, path)
        return pd.DataFrame(columns=["consensus", "actual", "release_date"])
    df = pd.read_csv(path)
    df.columns = [c.strip().strip('"').lower() for c in df.columns]
    df["release_date"] = pd.to_datetime(
        df["release_date"].astype(str).str.strip().str.strip('"'),
        format="%d-%m-%Y", errors="coerce")
    df["consensus"] = df["forecast"].map(_parse_mbbl)
    df["actual"] = df["actual"].map(_parse_mbbl)
    df = df[df["consensus"].notna() & df["release_date"].notna()].copy()
    df["week_ending"] = df["release_date"].map(_prev_friday)
    df = (df.sort_values("release_date")
            .drop_duplicates("week_ending", keep="last")
            .set_index("week_ending").sort_index())
    return df[["consensus", "actual", "release_date"]]


def consensus_series(series: str = "crude_ex_spr") -> pd.Series:
    """The real analyst consensus (forecast) for `series`, MBBL, by week-ending."""
    return _load_consensus_csv(series)["consensus"] if not _load_consensus_csv(series).empty \
        else pd.Series(dtype=float)


_last_report_refresh = 0.0   # monotonic-ish wall clock of the last live EIA pull


def refresh_report(force: bool = False, min_interval_hours: float = 6.0) -> dict:
    """
    Pull the **actual EIA Weekly Petroleum Status Report from the live EIA v2 API**
    and re-cache it, so the framework grades against the real printed number the
    moment it's out — not the static consensus scrape or an industry proxy. Throttled
    to one live pull per `min_interval_hours` (the report is weekly), unless `force`.
    The scheduler calls this after each release window; routes can trigger a throttled
    pull with `?refresh=1`.
    """
    global _last_report_refresh
    import time
    now = time.time()
    if not force and (now - _last_report_refresh) < min_interval_hours * 3600:
        return {"refreshed": False, "reason": "throttled (recent live pull)"}
    if not _EIA_KEY:
        return {"refreshed": False, "reason": "no EIA_API_KEY"}
    try:
        df = fetch_report_history(force_refresh=True)
        _last_report_refresh = now
        return {"refreshed": True, "latest_week": str(df.index.max().date()),
                "n_weeks": int(len(df)), "source": "eia_api_v2"}
    except Exception as exc:
        log.warning("live EIA report refresh failed: %s", exc)
        return {"refreshed": False, "reason": str(exc)}


def latest_release(series: str = "crude_ex_spr", refresh: bool = False) -> dict | None:
    """
    The freshest *printed* release, anchored on the **actual EIA number from the live
    EIA v2 API** (authoritative) with the real analyst consensus from the history. The
    EIA report is the live feed for the ACTUAL; the consensus CSV supplies the forecast.

    `actual_source` is "eia_api (live)" once the live report carries the week, else
    "consensus_csv_scrape" (the investing.com scrape, which equals the EIA print — used
    only while the live API hasn't yet published that week). `refresh=True` triggers a
    throttled live pull first. None when there's no printed release to grade.
    """
    if refresh:
        refresh_report()
    c = _load_consensus_csv(series)
    c = c[c["actual"].notna()]

    # The live EIA v2 API is the authoritative feed for the ACTUAL and typically
    # LEADS the scraped consensus CSV by 1+ weeks (the CSV backfill lags the weekly
    # print). Grade the freshest week EITHER source carries an actual for — so the
    # most recent release surfaces the moment the API publishes it, even before the
    # consensus scrape catches up.
    api_chg = None
    try:
        wf = weekly_frame()
        if series in wf:
            api_chg = wf[series].diff().dropna()
    except Exception:
        api_chg = None

    weeks = []
    if not c.empty:
        weeks.append(c.index.max())
    if api_chg is not None and not api_chg.empty:
        weeks.append(api_chg.index.max())
    if not weeks:
        return None
    we = max(weeks)

    # ACTUAL: prefer the authoritative live API change for this week; else the CSV
    # scrape (which equals the EIA print — used only while the API lags the week).
    actual = actual_source = None
    if api_chg is not None and we in api_chg.index and pd.notna(api_chg.loc[we]):
        actual, actual_source = float(api_chg.loc[we]), "eia_api (live)"
    elif we in c.index and pd.notna(c.loc[we, "actual"]):
        actual, actual_source = float(c.loc[we, "actual"]), "consensus_csv_scrape"
    if actual is None:
        return None

    # CONSENSUS: the real analyst consensus (CSV) when it carries this week; else the
    # seasonal-proxy expectation (labelled), so a just-printed week the scrape hasn't
    # reached is still gradeable — the same fallback surprise_series() uses.
    consensus = consensus_source = None
    if we in c.index and pd.notna(c.loc[we, "consensus"]):
        consensus, consensus_source = float(c.loc[we, "consensus"]), "consensus"
    elif api_chg is not None:
        seas = _seasonal_expected_change(api_chg)
        if we in seas.index and pd.notna(seas.loc[we]):
            consensus, consensus_source = float(seas.loc[we]), "seasonal_fallback"
    if consensus is None:
        return None

    # RELEASE DATE: the CSV's if present, else the holiday-aware scheduled Wednesday.
    if we in c.index and pd.notna(c.loc[we, "release_date"]):
        release_date = str(pd.Timestamp(c.loc[we, "release_date"]).date())
    else:
        from research.inventory_impact.release_calendar import release_datetime
        release_date = str(release_datetime(we).date())

    return {
        "series": series,
        "week_ending": str(we.date()),
        "release_date": release_date,
        "actual_mbbl": round(actual, 0),
        "consensus_mbbl": round(consensus, 0),
        "surprise_mbbl": round(actual - consensus, 0),
        "actual_source": actual_source,
        "consensus_source": consensus_source,
    }


@lru_cache(maxsize=1)
def _load_api_crude() -> pd.DataFrame:
    """API weekly crude (the Tuesday leading indicator), indexed by week-ending
    Friday with the API *actual* in MBBL. The API forecast column is sparse, so we
    use the API actual (validated: corr 0.77 with the EIA actual, predicts the EIA
    consensus surprise at corr 0.64 / slope 0.63). Coverage 2019+ only."""
    path = _CACHE / _API_CRUDE_FILE
    if not path.exists():
        return pd.DataFrame(columns=["api_actual", "release_date"])
    df = pd.read_csv(path)
    df.columns = [c.strip().strip('"').lower() for c in df.columns]
    df["release_date"] = pd.to_datetime(
        df["release_date"].astype(str).str.strip().str.strip('"'),
        format="%d-%m-%Y", errors="coerce")
    df["api_actual"] = df["actual"].map(_parse_mbbl)
    df = df[df["api_actual"].notna() & df["release_date"].notna()].copy()
    df["week_ending"] = df["release_date"].map(_prev_friday)
    df = (df.sort_values("release_date")
            .drop_duplicates("week_ending", keep="last")
            .set_index("week_ending").sort_index())
    return df[["api_actual", "release_date"]]


def api_nowcast(week_ending) -> dict | None:
    """
    The API crude leading indicator for the EIA week ending `week_ending` — the
    Tuesday print that front-runs Wednesday's EIA number by ~1 day. Returns the API
    actual (MBBL) + its release date, or None if the API didn't cover that week
    (coverage 2019+; the most recent week may not have printed yet). This is a
    pre-release nowcast input, NOT the EIA number.
    """
    api = _load_api_crude()
    if api.empty:
        return None
    we = pd.Timestamp(week_ending).normalize()
    if we not in api.index:
        return None
    row = api.loc[we]
    return {
        "week_ending": str(we.date()),
        "api_actual_mbbl": round(float(row["api_actual"]), 0),
        "api_release_date": str(pd.Timestamp(row["release_date"]).date()),
        "coverage_note": "API weekly crude (Tue) - corr 0.77 w/ EIA actual; 2019+ only",
    }

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
      method="consensus"  real analyst consensus (investing.com history), with the
                          seasonal baseline as a per-week fallback where no consensus
                          row exists. THIS IS THE DEFAULT — actual - real consensus.
      method="seasonal"   5yr same-ISO-week seasonal baseline (proxy consensus).
      method="ma4"        trailing 4-week mean of changes (naive floor).
      consensus=<Series>  if given, used as expected directly (real consensus
                          drop-in — actual - consensus), overriding `method`.

    surprise_z = surprise / trailing std(surprise) — standardised so a "1σ
    surprise" is comparable across calm and volatile periods.

    `expected_source` column flags each week as "consensus" (a real consensus row
    was used) vs "seasonal_fallback" (no consensus that week → seasonal proxy), so
    the desk is never misled about whether a surprise is vs a real number.
    """
    wf = weekly_frame()
    if series not in wf:
        raise KeyError(f"unknown series '{series}'")
    actual_change = wf[series].diff()
    seasonal = _seasonal_expected_change(actual_change)
    expected_source = pd.Series("seasonal", index=actual_change.index)

    if consensus is not None:
        expected = consensus.reindex(actual_change.index)
        expected_source = pd.Series(
            np.where(expected.notna(), "consensus", "seasonal_fallback"),
            index=actual_change.index)
        expected = expected.fillna(seasonal)
    elif method == "consensus":
        cons = consensus_series(series).reindex(actual_change.index)
        expected_source = pd.Series(
            np.where(cons.notna(), "consensus", "seasonal_fallback"),
            index=actual_change.index)
        expected = cons.fillna(seasonal)
    elif method == "seasonal":
        expected = seasonal
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
        "expected_source": expected_source,
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
